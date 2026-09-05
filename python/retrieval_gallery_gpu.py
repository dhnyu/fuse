"""Locked original-only supplemental GPU work; frozen P10 numerical kernels."""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import subprocess
import time

import numpy as np
import torch

from p10_evaluation import (_device, _load_model, _model_values, _rows,
                            _to_device_nonblocking, resolve_model_bindings)
from p10_prepared_input import _geometry_worker
from p9_model_families import family_contract
from retrieval_gallery_inputs import digest


LOCK_ROOT = Path("/mnt/hdd002/dhnyu/fusedata/runtime/gpu_locks")


@contextmanager
def lock(name):
    LOCK_ROOT.mkdir(parents=True, exist_ok=True)
    with (LOCK_ROOT / name).open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def write_new(path, value):
    with Path(path).open("x") as handle:
        json.dump(value, handle, sort_keys=True, indent=2, allow_nan=False)


class PreparedBatches(torch.utils.data.Dataset):
    def __init__(self, root, rows):
        self.root, self.rows = Path(root), rows

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, index):
        row = self.rows[index]
        path = self.root / row["relative_path"]
        if digest(path) != row["payload_sha256"]:
            raise ValueError("Prepared batch checksum mismatch")
        return torch.load(path, map_location="cpu", weights_only=False)


def _geometry_task(gpu, rows, inputs, output, input_id, cache_id, config):
    with lock(f"gpu{gpu}.lock"):
        _geometry_worker(gpu, rows, inputs, output, input_id, cache_id, config)


def _inference_task(gpu, bindings, contract, inputs, geometry, output):
    os.environ["CUDA_VISIBLE_DEVICES"] = str(gpu)
    os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
    with lock(f"gpu{gpu}.lock"):
        device = _device(contract)
        manifest = json.loads((Path(inputs) / "prepared_manifest.json").read_text())
        geometry_manifest = json.loads((Path(geometry) / "geometry_manifest.json").read_text())
        configurations = _rows(contract)
        for binding in bindings:
            start = time.monotonic()
            values = _model_values(contract, binding, configurations[binding.configuration_id])
            model = _load_model(binding, values, device)
            dataset = PreparedBatches(inputs, manifest["batches"])
            loader = torch.utils.data.DataLoader(dataset, batch_size=None, num_workers=8,
                pin_memory=True, prefetch_factor=2, persistent_workers=True,
                multiprocessing_context="spawn")
            torch.cuda.reset_peak_memory_stats(device)
            embeddings, scene_ids, forward_seconds, wait_seconds = [], [], [], []
            previous = time.monotonic()
            with torch.inference_mode():
                for index, payload in enumerate(loader):
                    wait_seconds.append(time.monotonic() - previous)
                    if payload["cache_id"] != manifest["cache_id"]:
                        raise ValueError("Input cache identity mismatch")
                    batch = _to_device_nonblocking(payload["batch"], device)
                    ds = payload["ds_raster"].to(device, non_blocking=True) if binding.family == "DS" else None
                    features = None
                    if "geometry" in family_contract(binding.family).modalities:
                        row = geometry_manifest["entries"][index]
                        path = Path(geometry) / row["relative_path"]
                        if digest(path) != row["payload_sha256"]:
                            raise ValueError("Geometry checksum mismatch")
                        stored = torch.load(path, map_location="cpu", weights_only=False)
                        if stored["identity"] != payload["identity"]:
                            raise ValueError("Geometry batch identity mismatch")
                        features = (stored["magnitude"].to(device), stored["phase"].to(device))
                    torch.cuda.synchronize(device)
                    tick = time.monotonic()
                    vector = torch.nn.functional.normalize(model.online(batch, features, ds)["scene_embedding"], dim=1)
                    torch.cuda.synchronize(device)
                    forward_seconds.append(time.monotonic() - tick)
                    embeddings.append(vector.cpu().numpy())
                    scene_ids.extend(payload["batch"]["scene_ids"])
                    if index == 0:
                        repeat = torch.nn.functional.normalize(model.online(batch, features, ds)["scene_embedding"], dim=1)
                        if not torch.equal(vector, repeat):
                            raise ValueError("Deterministic bounded embedding rerun mismatch")
                    previous = time.monotonic()
            array = np.concatenate(embeddings)
            if array.dtype != np.float32 or array.shape != (len(scene_ids), 128) or not np.isfinite(array).all():
                raise ValueError("Supplemental embedding contract failed")
            path = Path(output) / (binding.configuration_id + ".npy")
            with path.open("xb") as handle:
                np.save(handle, array, allow_pickle=False)
            write_new(path.with_suffix(".json"), {"status": "PASS", "configuration_id": binding.configuration_id,
                "checkpoint_id": binding.checkpoint_id, "checkpoint_sha256": binding.payload_sha256,
                "input_cache_id": manifest["cache_id"], "geometry_cache_id": geometry_manifest["cache_id"],
                "scene_ids": scene_ids, "shape": list(array.shape), "dtype": "float32", "amp": False, "tf32": False,
                "deterministic_bounded_rerun": True, "sha256": digest(path), "gpu": gpu,
                "wall_seconds": time.monotonic() - start, "forward_seconds": forward_seconds,
                "input_wait_seconds": wait_seconds, "peak_allocated_vram_bytes": torch.cuda.max_memory_allocated(device)})
            del model, loader
            torch.cuda.empty_cache()


def run_pair(target, arguments, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    start = time.monotonic()
    with lock("gpu_pair.lock"), (output / "gpu_samples.csv").open("x") as log:
        monitor = subprocess.Popen(["nvidia-smi", "--query-gpu=timestamp,index,utilization.gpu,memory.used",
                                    "--format=csv,noheader,nounits", "--loop-ms=100"], stdout=log, stderr=subprocess.STDOUT)
        try:
            ctx = multiprocessing.get_context("spawn")
            processes = [ctx.Process(target=target, args=args) for args in arguments]
            for process in processes:
                process.start()
            for process in processes:
                process.join()
            if any(p.exitcode for p in processes):
                raise RuntimeError("Supplemental GPU stage failed; no acceptance published")
        finally:
            monitor.terminate()
            monitor.wait()
    return time.monotonic() - start


def build_geometry(inputs, output, accepted_manifest):
    inputs, output = Path(inputs), Path(output)
    manifest = json.loads((inputs / "prepared_manifest.json").read_text())
    accepted = json.loads(Path(accepted_manifest).read_text())
    if digest(Path(__file__).with_name("prototype_encoder.py")) != accepted["plan"]["implementation_sha256"]:
        raise ValueError("Accepted Fourier implementation checksum mismatch")
    config = accepted["plan"]["geometry_config"]
    identity = {"version": "retrieval-geometry-v1", "input_id": manifest["cache_id"],
                "accepted_geometry_sha256": digest(accepted_manifest), "geometry_config": config}
    cache_id = "retrgeo_" + hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:24]
    rows = manifest["batches"]
    arguments = [(gpu, rows[gpu::2], str(inputs), str(output), manifest["cache_id"], cache_id, config) for gpu in (0, 1)]
    wall = run_pair(_geometry_task, arguments, output)
    entries = []
    for row in rows:
        filename = f"{row['split']}-{row['kind']}-{row['batch_index']:04d}.pt"
        path = output / filename
        entries.append({"relative_path": filename, "payload_sha256": digest(path), "size_bytes": path.stat().st_size})
    write_new(output / "geometry_manifest.json", {"status": "PASS", "cache_id": cache_id,
                "identity": identity, "entries": entries, "wall_seconds": wall})


def infer_all(contract, inputs, geometry, output):
    bindings = resolve_model_bindings(contract)
    if len(bindings) != 8:
        raise ValueError("All eight accepted models required")
    arguments = [(gpu, bindings[gpu::2], contract, str(inputs), str(geometry), str(output)) for gpu in (0, 1)]
    return run_pair(_inference_task, arguments, output)
