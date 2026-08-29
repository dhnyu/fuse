#!/usr/bin/env python3
"""Production P7/P9 cold-path cache, preload, and acceptance runtime."""

from __future__ import annotations

import argparse
import concurrent.futures
import contextlib
import fcntl
import hashlib
import json
import multiprocessing as mp
import os
import random
import resource
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import psutil
import torch
import torch.distributed as dist
import jsonschema

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "python"), str(ROOT / "scripts")]

from canonical_config import canonical_json_bytes, load_strict_yaml  # noqa: E402
from p6_data import GEOMETRY_LAYOUT_VERSION  # noqa: E402
from p7_geometry_cache import (GeometryCacheReader, GeometryCacheWriter, cache_record,
                               canonical_digest, sha256_file, tensor_sha256,
                               validate_payload)  # noqa: E402
from p7_prototype_training import (DeterministicBatchLookahead, activate_rank_stochastic_seed,
                                   checkpoint_state, common_inputs, configure_process, geometry,
                                   geometry_cache_sample, geometry_cache_specs, model_and_state,
                                   restore_checkpoint, save_checkpoint, train_update,
                                   validation_metrics, wrap_ddp)  # noqa: E402
from p7_training import collate, state_content_digest, to_device  # noqa: E402
from p7_cold_path_runtime import (load_runtime_config, memory_snapshot, required_memory_bytes,
                                  prepared_manifest as make_prepared_manifest, select_worker_tier,
                                  validate_fixed_indices as validate_runtime_indices,
                                  validate_staging_root)  # noqa: E402

RUNTIME_CONFIG_PATH = ROOT / "config/p7_cold_path_runtime.yml"
RUNTIME_CONFIG = load_runtime_config(RUNTIME_CONFIG_PATH)
ACCEPTED_CACHE = Path(RUNTIME_CONFIG["inputs"]["accepted_cache"])
ACCEPTED_AUTHORITY = Path(RUNTIME_CONFIG["inputs"]["accepted_authority"])
ACCEPTED_TRACE = Path(RUNTIME_CONFIG["inputs"]["accepted_trace"])
PROBLEM_VIEW = "augv_0c7fb311e3c582cf84136d90"

_CPU_VALUES: dict[str, Any] | None = None
_CPU_MODEL_CONFIG: dict[str, Any] | None = None
_CPU_IMPLEMENTATION = ""
_CPU_ACCEPTED: dict[str, dict[str, Any]] = {}
_CPU_PREPARED = Path("/")


def json_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_bytes(canonical_json_bytes(value))
    os.replace(temporary, path)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def input_args() -> SimpleNamespace:
    inputs = RUNTIME_CONFIG["inputs"]
    return SimpleNamespace(
        config=str(ROOT / inputs["p7_config"]), p6_config=str(ROOT / inputs["p6_config"]),
        architecture=inputs["architecture"], preprocessing=inputs["preprocessing"],
        p6_acceptance=inputs["p6_acceptance"], prototype=inputs["prototype"],
        prototype_manifest=inputs["prototype_manifest"], p3_root=inputs["p3_root"],
        p4_root=inputs["p4_root"], p5_root=inputs["p5_root"], categories=inputs["categories"],
        geometry_cache="",
    )


def thread_limits() -> None:
    for name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS",
                 "BLIS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "GDAL_NUM_THREADS", "ARROW_NUM_THREADS"):
        os.environ[name] = "1"
    torch.set_num_threads(1)


def cpu_initializer(prepared: str) -> None:
    global _CPU_VALUES, _CPU_MODEL_CONFIG, _CPU_IMPLEMENTATION, _CPU_ACCEPTED, _CPU_PREPARED
    thread_limits()
    if torch.cuda.is_initialized():
        raise RuntimeError("CPU preparation worker initialized CUDA")
    _CPU_VALUES = common_inputs(input_args())
    _CPU_MODEL_CONFIG = load_strict_yaml(ROOT / "config/p6_model_dataloader.yml")
    _CPU_IMPLEMENTATION = sha256_file(ROOT / "python/prototype_encoder.py")
    _CPU_ACCEPTED = {row["lookup_key"]: row for row in json.loads(ACCEPTED_CACHE.read_text())["entries"]}
    _CPU_PREPARED = Path(prepared)


def cpu_prepare(task: tuple[int, tuple[str, str, int | None]]) -> dict[str, Any]:
    index, spec = task
    assert _CPU_VALUES is not None and _CPU_MODEL_CONFIG is not None
    usage0 = resource.getrusage(resource.RUSAGE_SELF); started = time.perf_counter()
    sample = geometry_cache_sample(_CPU_VALUES["data"], spec)
    materialize = time.perf_counter() - started
    if sample["geometry_layout_version"] != GEOMETRY_LAYOUT_VERSION:
        raise ValueError("CPU preparation produced incompatible geometry layout")
    record = cache_record(sample, _CPU_VALUES["config"]["parents"], _CPU_MODEL_CONFIG["model"]["geometry"],
                          _CPU_IMPLEMENTATION, spec[0])
    accepted = _CPU_ACCEPTED.get(record["lookup_key"])
    if accepted is None or accepted["cache_key"] != record["cache_key"]:
        raise ValueError("CPU preparation cache identity mismatch")
    if sample["view_id"] == PROBLEM_VIEW:
        coordinates = int(sample["resources"]["part_coordinates"] + sample["resources"]["ring_coordinates"])
        if coordinates != 28:
            raise ValueError("problem candidate did not contain exactly 28 coordinates")
    sample_digest = state_content_digest(sample)
    payload = {"global_index": index, "spec": list(spec), "record": record,
               "sample_digest": sample_digest, "sample": sample}
    path = _CPU_PREPARED / f"{index:06d}.pt"; temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    t = time.perf_counter(); torch.save(payload, temporary); os.replace(temporary, path); write_wall = time.perf_counter() - t
    t = time.perf_counter(); restored = torch.load(path, map_location="cpu", weights_only=False); read_wall = time.perf_counter() - t
    if restored["global_index"] != index or state_content_digest(restored["sample"]) != sample_digest:
        raise ValueError("prepared sample round-trip mismatch")
    usage1 = resource.getrusage(resource.RUSAGE_SELF)
    return {
        "global_index": index, "lookup_key": record["lookup_key"], "cache_key": record["cache_key"],
        "record": record, "sample_digest": sample_digest, "payload_size_bytes": path.stat().st_size,
        "payload_sha256": sha256_file(path), "materialize_seconds": materialize,
        "write_seconds": write_wall, "readback_seconds": read_wall,
        "wall_seconds": time.perf_counter() - started, "peak_rss_kib": usage1.ru_maxrss,
        "minor_faults": usage1.ru_minflt - usage0.ru_minflt,
        "major_faults": usage1.ru_majflt - usage0.ru_majflt,
        "coordinates": int(sample["resources"]["part_coordinates"] + sample["resources"]["ring_coordinates"]),
        "entities": int(sample["entities"]["entity_type"].numel()),
    }


def configure_gpu(gpu: int) -> torch.device:
    thread_limits(); os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
    torch.use_deterministic_algorithms(True, warn_only=False)
    torch.backends.cuda.matmul.allow_tf32 = False; torch.backends.cudnn.allow_tf32 = False
    torch.backends.cudnn.deterministic = True; torch.backends.cudnn.benchmark = False
    torch.cuda.set_device(gpu)
    available = sorted(os.sched_getaffinity(0)); midpoint = len(available) // 2
    selected = available[:midpoint] if gpu == 0 else available[midpoint:]
    if selected: os.sched_setaffinity(0, selected)
    return torch.device("cuda", gpu)


def gpu_producer(gpu: int, plan_path: Path, prepared: Path, stage: Path, output: Path) -> None:
    device = configure_gpu(gpu); usage0 = resource.getrusage(resource.RUSAGE_SELF)
    values = common_inputs(input_args()); values["model_config"] = load_strict_yaml(ROOT / "config/p6_model_dataloader.yml")
    accepted = {row["lookup_key"]: row for row in json.loads(ACCEPTED_CACHE.read_text())["entries"]}
    plan = json.loads(plan_path.read_text()); writer = GeometryCacheWriter(stage)
    phases = {name: 0.0 for name in ("queue_wait", "load", "collate", "h2d", "fourier", "d2h", "write")}
    entries = failures = raw_bytes = 0; started = time.perf_counter()
    for row in plan["entries"]:
        index = int(row["global_index"])
        if index % 2 != gpu: continue
        path = prepared / f"{index:06d}.pt"; wait_started = time.perf_counter()
        while not path.is_file():
            if time.perf_counter() - wait_started > 3600: raise TimeoutError(f"prepared index timeout: {index}")
            time.sleep(0.02)
        phases["queue_wait"] += time.perf_counter() - wait_started
        t = time.perf_counter(); payload = torch.load(path, map_location="cpu", weights_only=False); phases["load"] += time.perf_counter() - t
        if payload["global_index"] != index or payload["record"]["lookup_key"] != row["lookup_key"]:
            raise ValueError("GPU producer fixed-index mismatch")
        sample = payload["sample"]; record = payload["record"]; truth = accepted[record["lookup_key"]]
        if record["cache_key"] != truth["cache_key"] or state_content_digest(sample) != payload["sample_digest"]:
            raise ValueError("GPU producer input identity mismatch")
        t = time.perf_counter(); batch_cpu = collate([sample], values["vocabulary"]); phases["collate"] += time.perf_counter() - t
        t = time.perf_counter(); batch = to_device(batch_cpu, device); torch.cuda.synchronize(device); phases["h2d"] += time.perf_counter() - t
        t = time.perf_counter(); magnitude, phase = geometry(batch, values["model_config"], device); torch.cuda.synchronize(device); phases["fourier"] += time.perf_counter() - t
        t = time.perf_counter(); magnitude = magnitude.cpu().contiguous(); phase = phase.cpu().contiguous(); phases["d2h"] += time.perf_counter() - t
        if tensor_sha256(magnitude) != truth["magnitude"]["sha256"] or tensor_sha256(phase) != truth["phase"]["sha256"]:
            failures += 1; raise ValueError("candidate Fourier tensor differs from accepted cache")
        t = time.perf_counter(); writer.put(record, magnitude, phase); phases["write"] += time.perf_counter() - t
        entries += 1; raw_bytes += magnitude.numel() * magnitude.element_size() + phase.numel() * phase.element_size()
    usage1 = resource.getrusage(resource.RUSAGE_SELF)
    json_write(output, {"gpu": gpu, "entries": entries, "failures": failures, "raw_tensor_bytes": raw_bytes,
                        "wall_seconds": time.perf_counter() - started, "phases": phases,
                        "peak_rss_kib": usage1.ru_maxrss, "minor_faults": usage1.ru_minflt - usage0.ru_minflt,
                        "major_faults": usage1.ru_majflt - usage0.ru_majflt,
                        "peak_vram_allocated_bytes": int(torch.cuda.max_memory_allocated(device)),
                        "peak_vram_reserved_bytes": int(torch.cuda.max_memory_reserved(device))})


class Monitor:
    def __init__(self, output: Path) -> None:
        self.output = output; self.stop = threading.Event(); self.rows: list[dict[str, Any]] = []; self.process_rows: list[dict[str, Any]] = []
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while not self.stop.wait(0.5):
            timestamp = time.time()
            try:
                root = psutil.Process(os.getpid()); processes = [root, *root.children(recursive=True)]
                rss = sum(process.memory_info().rss for process in processes if process.is_running())
                io = psutil.disk_io_counters()
                swap = psutil.swap_memory()
                self.process_rows.append({"timestamp": timestamp, "process_count": len(processes), "aggregate_rss_bytes": rss,
                                          "system_cpu_percent": psutil.cpu_percent(interval=None),
                                          "swap_sin_bytes": int(getattr(swap, "sin", 0)),
                                          "disk_read_bytes": io.read_bytes if io else None,
                                          "disk_write_bytes": io.write_bytes if io else None})
            except Exception:
                pass
            try:
                lines = subprocess.check_output([
                    "nvidia-smi", "--query-gpu=index,utilization.gpu,utilization.memory,memory.used,power.draw,clocks.sm",
                    "--format=csv,noheader,nounits"], text=True, timeout=2).splitlines()
                for line in lines:
                    fields = [value.strip() for value in line.split(",")]
                    if int(fields[0]) in (0, 1):
                        self.rows.append({"timestamp": timestamp, "gpu": int(fields[0]), "utilization": float(fields[1]),
                                          "memory_utilization": float(fields[2]), "memory_mib": float(fields[3]),
                                          "power_w": float(fields[4]), "clock_mhz": float(fields[5])})
            except Exception:
                pass

    def __enter__(self): self.thread.start(); return self
    def __exit__(self, *_):
        self.stop.set(); self.thread.join(); json_write(self.output, {"interval_seconds": 0.5, "rows": self.rows,
                                                                      "process_rows": self.process_rows})


@contextlib.contextmanager
def gpu_locks():
    root = Path(RUNTIME_CONFIG["gpu_lock_root"]); root.mkdir(parents=True, exist_ok=True); streams = []
    try:
        for name in ("gpu_pair.lock", "gpu0.lock", "gpu1.lock"):
            stream = (root / name).open("a+"); fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB); streams.append(stream)
        yield
    finally:
        for stream in reversed(streams): fcntl.flock(stream.fileno(), fcntl.LOCK_UN); stream.close()


def build_plan(path: Path, limit: int = 0) -> dict[str, Any]:
    values = common_inputs(input_args()); accepted = json.loads(ACCEPTED_CACHE.read_text())
    accepted_index = {row["lookup_key"]: row for row in accepted["entries"]}; entries = []
    for index, spec in enumerate(geometry_cache_specs(values)):
        role, scene, selector = spec
        if role == "training":
            match = next(row for row in values["data"].catalog.k8[scene] if int(row["master_view_id"]) == int(selector))
            lookup = f"{role}\0{scene}\0{match['candidate_id']}"
        elif role == "validation_query":
            query = next(row for row in values["data"].catalog.query_rows["validation"]
                         if row["scene_id"] == scene and int(row["query_index"]) == int(selector))
            lookup = f"{role}\0{scene}\0{query['query_id']}"
        else:
            lookup = f"{role}\0{scene}\0original"
        if lookup not in accepted_index: raise ValueError(f"planned lookup absent from accepted cache: {lookup}")
        entries.append({"global_index": index, "spec": list(spec), "lookup_key": lookup,
                        "accepted_cache_key": accepted_index[lookup]["cache_key"]})
    if limit:
        stride = max(1, len(entries) // limit)
        selected = entries[::stride][:limit]
        problem = next(row for row in entries if PROBLEM_VIEW in row["lookup_key"])
        if all(row["lookup_key"] != problem["lookup_key"] for row in selected): selected[-1] = problem
        entries = [{**row, "global_index": index} for index, row in enumerate(sorted(selected, key=lambda row: row["lookup_key"]))]
    expected = limit or 2144
    if len(entries) != expected or len({row["lookup_key"] for row in entries}) != expected:
        raise ValueError("production cache plan is incomplete or duplicated")
    value = {"schema_version": "1.0.0", "entry_count": len(entries), "entries": entries}
    value["plan_sha256"] = digest(value); json_write(path, value); return value


def summarize_monitor(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text()); rows = value["rows"]; result = {}
    for gpu in (0, 1):
        selected = [row for row in rows if row["gpu"] == gpu]
        result[str(gpu)] = {"samples": len(selected),
                            "mean_utilization": sum(row["utilization"] for row in selected) / len(selected) if selected else None,
                            "zero_utilization_samples": sum(row["utilization"] == 0 for row in selected),
                            "peak_memory_mib": max((row["memory_mib"] for row in selected), default=None),
                            "mean_power_w": sum(row["power_w"] for row in selected) / len(selected) if selected else None}
    process_rows = value.get("process_rows", [])
    return {"gpus": result,
            "peak_aggregate_rss_bytes": max((row["aggregate_rss_bytes"] for row in process_rows), default=None),
            "peak_process_count": max((row["process_count"] for row in process_rows), default=None),
            "mean_system_cpu_percent": (sum(row["system_cpu_percent"] for row in process_rows) / len(process_rows)
                                         if process_rows else None),
            "disk_read_bytes_delta": ((process_rows[-1]["disk_read_bytes"] - process_rows[0]["disk_read_bytes"])
                                      if len(process_rows) > 1 and process_rows[0]["disk_read_bytes"] is not None else None),
            "disk_write_bytes_delta": ((process_rows[-1]["disk_write_bytes"] - process_rows[0]["disk_write_bytes"])
                                       if len(process_rows) > 1 and process_rows[0]["disk_write_bytes"] is not None else None),
            "swap_in_bytes_delta": ((process_rows[-1]["swap_sin_bytes"] - process_rows[0]["swap_sin_bytes"])
                                    if len(process_rows) > 1 else None)}


def validate_fixed_indices(rows: list[dict[str, Any]], expected: int) -> None:
    validate_runtime_indices(rows, expected)


def publish_prepared_manifest(plan: dict[str, Any], rows: list[dict[str, Any]], path: Path) -> dict[str, Any]:
    value = make_prepared_manifest(plan, rows, GEOMETRY_LAYOUT_VERSION)
    json_write(path, value); return value


def finalize_runtime_cache(stage: Path, authority_id: str,
                           expected_records: list[dict[str, Any]]) -> dict[str, Any]:
    """Publish the valid marker last and leave an identical completed cache untouched."""
    manifest_path = stage / "geometry_cache_manifest.json"
    complete_path = stage / "COMPLETE.json"
    by_key = {record["cache_key"]: record for record in expected_records}
    if len(by_key) != len(expected_records):
        raise ValueError("duplicate geometry-cache key")
    if len({record["lookup_key"] for record in expected_records}) != len(expected_records):
        raise ValueError("duplicate geometry-cache lookup identity")
    if manifest_path.exists() or complete_path.exists():
        if not manifest_path.is_file() or not complete_path.is_file():
            raise ValueError("partial geometry-cache publication")
        reader = GeometryCacheReader(manifest_path, maximum_memory_bytes=0)
        existing = reader.manifest
        existing_keys = {row["cache_key"] for row in existing["entries"]}
        if existing.get("training_authority_id") != authority_id or existing_keys != set(by_key):
            raise ValueError("completed geometry-cache publication has foreign coverage")
        return existing
    rows = []
    raw_bytes = disk_bytes = 0
    for key in sorted(by_key):
        record = by_key[key]
        path = stage / "entries" / f"{key}.pt"
        if not path.is_file():
            raise ValueError(f"missing geometry-cache entry: {key}")
        payload = torch.load(path, map_location="cpu", weights_only=False)
        magnitude, phase = validate_payload(record, payload)
        size = path.stat().st_size
        raw = (magnitude.numel() * magnitude.element_size()
               + phase.numel() * phase.element_size())
        disk_bytes += size
        raw_bytes += raw
        rows.append({**payload["manifest"], "relative_path": f"entries/{key}.pt",
                     "payload_size_bytes": size, "payload_sha256": sha256_file(path),
                     "raw_tensor_bytes": raw})
    value = {"schema_version": "3.0.0", "status": "PASS",
             "geometry_layout_version": GEOMETRY_LAYOUT_VERSION,
             "training_authority_id": authority_id, "entry_count": len(rows),
             "total_raw_tensor_bytes": raw_bytes, "entries": rows}
    value["content_sha256"] = canonical_digest(value)
    value["cache_id"] = "p7gc_" + value["content_sha256"][:24]
    value["total_disk_bytes"] = disk_bytes
    json_write(manifest_path, value)
    json_write(complete_path, {"cache_id": value["cache_id"],
                               "manifest_sha256": sha256_file(manifest_path)})
    GeometryCacheReader(manifest_path, maximum_memory_bytes=0)
    return value


def build_cache(args: argparse.Namespace) -> None:
    disk_admission = validate_staging_root(args.root, RUNTIME_CONFIG)
    snapshot = memory_snapshot()
    admission = select_worker_tier(
        RUNTIME_CONFIG, snapshot["mem_available_bytes"], snapshot["current_process_rss_bytes"],
        requested_workers=args.workers, swap_in_delta_bytes=0,
    )
    workers = int(admission["selected_workers"])
    root = args.root; root.mkdir(parents=True, exist_ok=False); prepared = root / "prepared"; prepared.mkdir()
    stage = root / "candidate_cache"; stage.mkdir(); plan = build_plan(root / "plan.json", args.limit)
    processes = []
    for gpu in (0, 1):
        output = root / f"gpu-{gpu}.json"
        command = [sys.executable, str(Path(__file__).resolve()), "gpu-producer", "--gpu", str(gpu),
                   "--plan", str(root / "plan.json"), "--prepared", str(prepared), "--stage", str(stage), "--output", str(output)]
        processes.append((subprocess.Popen(command, cwd=ROOT), output))
    usage0 = resource.getrusage(resource.RUSAGE_SELF); started = time.perf_counter(); cpu_rows = []
    monitor_path = root / "nvml-build.json"
    try:
        with Monitor(monitor_path), concurrent.futures.ProcessPoolExecutor(
                max_workers=workers, mp_context=mp.get_context("spawn"),
                initializer=cpu_initializer, initargs=(str(prepared),)) as pool:
            tasks = [(row["global_index"], tuple(row["spec"])) for row in plan["entries"]]
            for row in pool.map(cpu_prepare, tasks, chunksize=1): cpu_rows.append(row)
        for process, _ in processes:
            if process.wait(timeout=3600) != 0: raise RuntimeError("GPU producer failed")
    except Exception:
        for process, _ in processes:
            if process.poll() is None: process.terminate()
        raise
    cpu_complete = time.perf_counter() - started
    monitor_summary = summarize_monitor(monitor_path)
    if int(monitor_summary["peak_aggregate_rss_bytes"] or 0) > int(admission["required_bytes"]):
        raise MemoryError("cold-path aggregate RSS exceeded the admitted tier cap")
    if int(monitor_summary["swap_in_bytes_delta"] or 0) > int(RUNTIME_CONFIG["memory_admission"]["maximum_swap_in_delta_bytes"]):
        raise MemoryError("cold-path cache build caused swap-in activity")
    validate_fixed_indices(cpu_rows, int(plan["entry_count"]))
    prepared_manifest = publish_prepared_manifest(plan, cpu_rows, root / "prepared_manifest.json")
    records = [row["record"] for row in sorted(cpu_rows, key=lambda row: row["global_index"])]
    authority_id = json.loads(ACCEPTED_AUTHORITY.read_text())["training_authority_id"]
    finalize_started = time.perf_counter()
    manifest = finalize_runtime_cache(stage, authority_id, records)
    first_manifest_sha = sha256_file(stage / "geometry_cache_manifest.json")
    manifest_stat = (stage / "geometry_cache_manifest.json").stat()
    complete_stat = (stage / "COMPLETE.json").stat()
    repeated = finalize_runtime_cache(stage, authority_id, records)
    second_manifest_sha = sha256_file(stage / "geometry_cache_manifest.json")
    if first_manifest_sha != second_manifest_sha or manifest != repeated:
        raise ValueError("candidate manifest reconstruction is nondeterministic")
    if ((stage / "geometry_cache_manifest.json").stat().st_mtime_ns != manifest_stat.st_mtime_ns
            or (stage / "COMPLETE.json").stat().st_mtime_ns != complete_stat.st_mtime_ns):
        raise ValueError("repeated cache finalization rewrote completed publication")
    accepted = json.loads(ACCEPTED_CACHE.read_text()); candidate = json.loads((stage / "geometry_cache_manifest.json").read_text())
    accepted_rows = {row["lookup_key"]: row for row in accepted["entries"]}
    parity_failures = []
    for row in candidate["entries"]:
        truth = accepted_rows.get(row["lookup_key"])
        if truth is None or row["cache_key"] != truth["cache_key"] or row["magnitude"] != truth["magnitude"] or row["phase"] != truth["phase"]:
            parity_failures.append(row["lookup_key"])
    usage1 = resource.getrusage(resource.RUSAGE_SELF); gpu_rows = [json.loads(path.read_text()) for _, path in processes]
    final_memory = memory_snapshot()
    result = {"status": "PASS" if not parity_failures else "FAIL", "workers": workers,
              "memory_admission": admission, "memory_before": snapshot, "memory_after": final_memory,
              "disk_admission": disk_admission,
              "entry_count": len(candidate["entries"]), "missing": int(plan["entry_count"]) - len(candidate["entries"]),
              "duplicate": len(candidate["entries"]) - len({row["lookup_key"] for row in candidate["entries"]}),
              "parity_failures": parity_failures, "candidate_cache_id": candidate["cache_id"],
              "accepted_cache_id": accepted["cache_id"], "manifest_sha256": first_manifest_sha,
              "repeat_manifest_sha256": second_manifest_sha, "plan_sha256": plan["plan_sha256"],
              "wall_seconds": time.perf_counter() - started, "cpu_and_gpu_pipeline_seconds": cpu_complete,
              "finalize_seconds": time.perf_counter() - finalize_started,
              "prepared_disk_bytes": sum(row["payload_size_bytes"] for row in cpu_rows),
              "prepared_manifest_sha256": sha256_file(root / "prepared_manifest.json"),
              "prepared_content_sha256": prepared_manifest["content_sha256"],
              "candidate_disk_bytes": int(candidate["total_disk_bytes"]),
              "cpu": {"sum_materialize_seconds": sum(row["materialize_seconds"] for row in cpu_rows),
                      "sum_write_seconds": sum(row["write_seconds"] for row in cpu_rows),
                      "sum_readback_seconds": sum(row["readback_seconds"] for row in cpu_rows),
                      "maximum_worker_rss_kib": max(row["peak_rss_kib"] for row in cpu_rows),
                      "minor_faults": sum(row["minor_faults"] for row in cpu_rows),
                      "major_faults": sum(row["major_faults"] for row in cpu_rows),
                      "coordinates": sum(row["coordinates"] for row in cpu_rows),
                      "entities": sum(row["entities"] for row in cpu_rows)},
              "gpus": gpu_rows, "nvml": monitor_summary,
              "controller_peak_rss_kib": usage1.ru_maxrss,
              "controller_minor_faults": usage1.ru_minflt - usage0.ru_minflt}
    json_write(root / "build_result.json", result)
    if result["status"] != "PASS": raise ValueError("candidate cache parity failed")


def validate_cache(args: argparse.Namespace) -> None:
    started = time.perf_counter(); reader = GeometryCacheReader(args.manifest, maximum_memory_bytes=0)
    accepted = json.loads(ACCEPTED_CACHE.read_text()); truth = {row["lookup_key"]: row for row in accepted["entries"]}
    failures = []
    for row in reader.manifest["entries"]:
        identity = row["identity"]; magnitude, phase = reader._get(identity["role"], identity["scene_id"], identity["view_id"])
        accepted_row = truth.get(row["lookup_key"])
        if (accepted_row is None or row["cache_key"] != accepted_row["cache_key"]
                or tensor_sha256(magnitude) != accepted_row["magnitude"]["sha256"]
                or tensor_sha256(phase) != accepted_row["phase"]["sha256"]):
            failures.append(row["lookup_key"])
    json_write(args.output, {"status": "PASS" if not failures else "FAIL", "entry_count": len(reader.manifest["entries"]),
                             "failures": failures, "manifest_sha256": sha256_file(args.manifest),
                             "accepted_manifest_sha256": sha256_file(ACCEPTED_CACHE),
                             "wall_seconds": time.perf_counter() - started, "reader_stats": reader.stats()})
    if failures: raise ValueError("candidate cache readback differs from accepted tensors")


def finalize_prepared(args: argparse.Namespace) -> None:
    plan = json.loads(args.plan.read_text()); rows = []
    for row in plan["entries"]:
        index = int(row["global_index"]); path = args.prepared / f"{index:06d}.pt"
        payload = torch.load(path, map_location="cpu", weights_only=False)
        if payload["global_index"] != index or payload["record"]["lookup_key"] != row["lookup_key"]:
            raise ValueError("prepared fixed-index identity mismatch")
        rows.append({"global_index": index, "lookup_key": row["lookup_key"], "cache_key": payload["record"]["cache_key"],
                     "sample_digest": payload["sample_digest"], "payload_size_bytes": path.stat().st_size,
                     "payload_sha256": sha256_file(path)})
    value = publish_prepared_manifest(plan, rows, args.output); print(value["content_sha256"])


def finalize_identity(value: dict[str, Any], prefix: str, field: str) -> dict[str, Any]:
    scientific = {key: item for key, item in value.items() if key not in {field, "content_sha256"}}
    value["content_sha256"] = digest(scientific); value[field] = prefix + value["content_sha256"][:24]
    return value


def validate_json(value: dict[str, Any], schema_path: Path) -> None:
    jsonschema.Draft202012Validator(json.loads(schema_path.read_text())).validate(value)


def build_runtime_contract(args: argparse.Namespace) -> None:
    authority = json.loads(ACCEPTED_AUTHORITY.read_text())
    acceptance = json.loads(Path(RUNTIME_CONFIG["inputs"]["accepted_acceptance"]).read_text())
    p6_acceptance = json.loads(Path(RUNTIME_CONFIG["inputs"]["p6_acceptance"]).read_text())
    cache = json.loads(ACCEPTED_CACHE.read_text())
    parents = RUNTIME_CONFIG["parents"]
    if (p6_acceptance["model_data_acceptance_id"] != parents["p6_aggregate_acceptance_id"]
            or authority["training_authority_id"] != parents["p7_training_authority_id"]
            or acceptance["acceptance_id"] != parents["p7_acceptance_id"]
            or acceptance["run_id"] != parents["p7_run_id"]
            or cache["cache_id"] != parents["p7_geometry_cache_id"]
            or cache["schema_version"] != "3.0.0"
            or cache["geometry_layout_version"] != "3.0.0"
            or acceptance["best_checkpoint"]["checkpoint_id"] != parents["p7_best_checkpoint_id"]
            or acceptance["latest_checkpoint"]["checkpoint_id"] != parents["p7_latest_checkpoint_id"]):
        raise ValueError("cold-path runtime parent lineage mismatch")
    source_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    configuration = {key: RUNTIME_CONFIG[key] for key in (
        "cpu_preparation", "memory_admission", "gpu_producers", "disk_staging", "eager_preload",
        "scientific_invariants", "p8", "future_p9", "prohibited_variants", "experimental_evidence")}
    value = {"schema_version": "1.0.0", "status": "PASS", "contract_name": RUNTIME_CONFIG["contract_name"],
             "source_commit": source_commit, "parents": parents, "configuration": configuration,
             "checksums": {"runtime_config_sha256": sha256_file(RUNTIME_CONFIG_PATH),
                           "runtime_module_sha256": sha256_file(ROOT / "python/p7_cold_path_runtime.py"),
                           "runtime_script_sha256": sha256_file(Path(__file__)),
                           "p6_acceptance_sha256": sha256_file(RUNTIME_CONFIG["inputs"]["p6_acceptance"]),
                           "p7_acceptance_sha256": sha256_file(RUNTIME_CONFIG["inputs"]["accepted_acceptance"]),
                           "p7_cache_manifest_sha256": sha256_file(ACCEPTED_CACHE)},
             "invariants": {"scientific_configuration_unchanged": True, "existing_p7_artifacts_immutable": True,
                            "p8_parent_unchanged": True, "future_p9_runtime_binding_required": True,
                            "full_p7_execution_zero": True, "p8_p9_execution_zero": True}}
    finalize_identity(value, "p7rt_", "contract_id")
    validate_json(value, args.schema); json_write(args.output, value)


def build_runtime_acceptance(args: argparse.Namespace) -> None:
    contract = json.loads(args.contract.read_text()); verification = json.loads(args.verification.read_text())
    if contract.get("status") != "PASS" or verification.get("status") != "PASS":
        raise ValueError("runtime contract or verification did not pass")
    required = {"cache_entry_count": 2144, "cache_parity_failures": 0, "cache_missing": 0,
                "cache_duplicate": 0, "first_40_trace_exact": True, "validation_exact": True,
                "resume_exact": True, "preload_rng_unchanged": True, "accepted_artifact_mutations": 0,
                "target_store_mutations": 0, "existing_cache_checkpoint_mutations": 0,
                "dissertation_mutations": 0, "full_p7_executions": 0, "p8_p9_executions": 0}
    for key, expected in required.items():
        if verification.get(key) != expected: raise ValueError(f"runtime verification mismatch: {key}")
    if verification.get("selected_workers") not in (32, 24, 16):
        raise ValueError("runtime verification used an unadmitted worker tier")
    if not (0 < float(verification["cache_build_wall_seconds"])
            < float(RUNTIME_CONFIG["experimental_evidence"]["accepted_cache_build_wall_seconds"])):
        raise ValueError("runtime verification did not improve cache-build wall time")
    value = {"schema_version": "1.0.0", "status": "PASS", "contract_id": contract["contract_id"],
             "source_commit": contract["source_commit"], "parents": contract["parents"],
             "verification": verification,
             "memory_admission": {"worker_tiers": [32, 24, 16],
                                  "selected_active_tier": verification["selected_workers"],
                                  "required_bytes_by_tier": {str(tier): required_memory_bytes(RUNTIME_CONFIG, tier)
                                                             for tier in (32, 24, 16)},
                                  "safety_margin_fraction": 0.25},
             "compatibility": {"existing_p7_acceptance_unchanged": True,
                               "p8_acceptance_id": RUNTIME_CONFIG["p8"]["canonical_acceptance_id"],
                               "p8_checkpoint_id": RUNTIME_CONFIG["p8"]["canonical_checkpoint_id"],
                               "future_p9_runtime_acceptance_required": True},
             "non_mutation": {key: verification[key] for key in (
                 "accepted_artifact_mutations", "target_store_mutations",
                 "existing_cache_checkpoint_mutations", "dissertation_mutations")}}
    finalize_identity(value, "p7rta_", "acceptance_id")
    validate_json(value, args.schema); json_write(args.output, value)


class EagerData:
    def __init__(self, base: Any, plan: dict[str, Any], prepared: Path) -> None:
        self.members, self.catalog = base.members, base.catalog
        self.samples: dict[str, dict[str, Any]] = {}; self.spec_lookup: dict[tuple[str, str, int | None], str] = {}
        manifest = json.loads((prepared.parent / "prepared_manifest.json").read_text())
        scientific = {key: value for key, value in manifest.items() if key != "content_sha256"}
        if (manifest.get("status") != "PASS" or manifest.get("geometry_layout_version") != GEOMETRY_LAYOUT_VERSION
                or manifest.get("plan_sha256") != plan["plan_sha256"] or manifest.get("content_sha256") != digest(scientific)):
            raise ValueError("incomplete or incompatible prepared-view manifest")
        manifest_rows = {int(row["global_index"]): row for row in manifest["entries"]}
        for row in plan["entries"]:
            index = int(row["global_index"]); path = prepared / f"{index:06d}.pt"; expected = manifest_rows.get(index)
            if (expected is None or expected["lookup_key"] != row["lookup_key"] or path.stat().st_size != expected["payload_size_bytes"]
                    or sha256_file(path) != expected["payload_sha256"]): raise ValueError("eager prepared payload checksum mismatch")
            payload = torch.load(path, map_location="cpu", weights_only=False)
            if (state_content_digest(payload["sample"]) != payload["sample_digest"]
                    or payload["sample_digest"] != expected["sample_digest"]): raise ValueError("eager sample corruption")
            self.samples[row["lookup_key"]] = payload["sample"]
            role, scene, selector = row["spec"]; self.spec_lookup[(role, scene, selector)] = row["lookup_key"]
        if len(self.samples) != int(plan["entry_count"]): raise ValueError("eager preload coverage mismatch")

    def training_view(self, scene: str, master: int): return self.samples[self.spec_lookup[("training", scene, master)]]
    def validation_query(self, scene: str, index: int): return self.samples[self.spec_lookup[("validation_query", scene, index)]]
    def validation_gallery(self, scene: str): return self.samples[self.spec_lookup[("validation_gallery", scene, None)]]


def rank_rng_digest(rank: int) -> str:
    return state_content_digest({"python": random.getstate(), "numpy": np.random.get_state(),
                                 "cpu": torch.get_rng_state(), "cuda": torch.cuda.get_rng_state(rank)})


def trajectory_worker(args: argparse.Namespace) -> None:
    rank = int(os.environ["RANK"]); config = load_strict_yaml(ROOT / "config/p7_deterministic_training.yml")
    started = time.perf_counter(); device = configure_process(config, rank); dist.init_process_group("nccl")
    values = common_inputs(input_args()); values["model_config"] = load_strict_yaml(ROOT / "config/p6_model_dataloader.yml")
    values["authority"] = json.loads(ACCEPTED_AUTHORITY.read_text())
    before = rank_rng_digest(rank); preload_started = time.perf_counter()
    plan = json.loads(args.plan.read_text()); values["data"] = EagerData(values["data"], plan, args.prepared)
    preload_wall = time.perf_counter() - preload_started; after = rank_rng_digest(rank)
    if before != after: raise ValueError("eager preload consumed scientific RNG")
    preload_rows: list[Any] = [None] * dist.get_world_size()
    dist.all_gather_object(preload_rows, {"rank": rank, "seconds": preload_wall,
                                         "entry_count": len(values["data"].samples),
                                         "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                                         "rng_unchanged": before == after})
    reader = GeometryCacheReader(args.geometry_cache, 4 * 1024**3)
    if reader.manifest["training_authority_id"] != values["authority"]["training_authority_id"]:
        raise ValueError("foreign trajectory cache")
    values["geometry_cache"] = reader
    model, optimizer, scheduler, queue = model_and_state(values, device); ddp = wrap_ddp(model, device, config)
    activate_rank_stochastic_seed(config, rank)
    trace: list[dict[str, Any]] = []; validations: list[dict[str, Any]] = []; selector = {"best": None, "patience": 0}
    progress = {"completed_epoch": 0, "next_batch_index": 0}
    if args.resume_checkpoint:
        state = restore_checkpoint(args.resume_checkpoint, model, optimizer, scheduler, queue, rank, values["authority"])
        trace = state["training_trace"]; validations = state["validation_events"]; selector = state["selector_state"]; progress = state["progress"]
    values["lookahead"] = DeterministicBatchLookahead(values, rank); model.train(); step_walls = []
    while scheduler.completed_updates < args.max_updates:
        epoch = scheduler.completed_updates // 8 + 1; batch_index = scheduler.completed_updates % 8
        result = train_update(ddp, model, optimizer, scheduler, queue, values, epoch, batch_index, rank, device)
        step_walls.append(float(result["step_wall_seconds"])); trace.append({key: value for key, value in result.items() if key != "step_wall_seconds"})
        progress = {"completed_epoch": scheduler.completed_updates // 8, "next_batch_index": scheduler.completed_updates % 8}
    values["lookahead"].close()
    validation_wall = 0.0
    if args.with_validation:
        dist.barrier(); t = time.perf_counter(); event = validation_metrics(model, values, device, rank); validation_wall = time.perf_counter() - t
        event["epoch"] = args.max_updates // 8; selector = {"best": dict(event), "patience": 0}
        event["selected_best"] = True; event["patience_after_event"] = 0; validations = [event]
    checkpoint_started = time.perf_counter()
    state = checkpoint_state(model, optimizer, scheduler, queue, progress, trace, validations, selector, rank, values["authority"])
    manifest = save_checkpoint(args.stage, state, "experiment", rank, values["authority"])
    checkpoint_wall = time.perf_counter() - checkpoint_started
    if rank == 0:
        accepted = json.loads(ACCEPTED_TRACE.read_text()); trace_exact = trace == accepted["steps"][:args.max_updates]
        validation_exact = not args.with_validation or all(
            event.get(key) == accepted["validation_events"][0].get(key)
            for key in ("validation_retrieval_loss", "mean_source_separation_margin", "embedding_digest",
                        "distributed_coverage_count", "distributed_duplicate_count", "distributed_missing_count"))
        json_write(args.output, {"status": "PASS" if trace_exact and validation_exact and before == after else "FAIL",
                                 "rank": rank, "preload_seconds": preload_wall, "preload_entry_count": len(values["data"].samples),
                                 "preload_ranks": preload_rows,
                                 "rng_before": before, "rng_after": after, "rng_unchanged": before == after,
                                 "trace_exact": trace_exact, "validation_exact": validation_exact,
                                 "step_count": len(trace), "step_walls": step_walls,
                                 "validation": validations[0] if validations else None,
                                 "validation_wall_seconds": validation_wall,
                                 "checkpoint_wall_seconds": checkpoint_wall,
                                 "state_content_sha256": manifest["state_content_sha256"],
                                 "checkpoint_id": manifest["checkpoint_id"],
                                 "checkpoint_path": str(args.stage / "checkpoints" / manifest["checkpoint_id"] / "checkpoint.pt"),
                                 "cache_stats": reader.stats(), "total_wall_seconds": time.perf_counter() - started,
                                 "peak_vram_allocated_bytes": int(torch.cuda.max_memory_allocated(device)),
                                 "peak_vram_reserved_bytes": int(torch.cuda.max_memory_reserved(device)),
                                 "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss})
    dist.barrier(); dist.destroy_process_group()


def launch_trajectory(args: argparse.Namespace) -> None:
    args.root.mkdir(parents=True, exist_ok=False); output = args.root / "trajectory.json"; stage = args.root / "stage"; stage.mkdir()
    command = [sys.executable, "-m", "torch.distributed.run", "--standalone", "--nproc_per_node=2",
               str(Path(__file__).resolve()), "trajectory-worker", "--plan", str(args.plan),
               "--prepared", str(args.prepared), "--geometry-cache", str(args.geometry_cache),
               "--stage", str(stage), "--output", str(output), "--max-updates", str(args.max_updates)]
    if args.with_validation: command.append("--with-validation")
    if args.resume_checkpoint: command += ["--resume-checkpoint", str(args.resume_checkpoint)]
    env = os.environ.copy(); env.update({"CUDA_VISIBLE_DEVICES": "0,1", "CUBLAS_WORKSPACE_CONFIG": ":4096:8",
        "PYTHONDONTWRITEBYTECODE": "1", "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1",
        "NUMEXPR_NUM_THREADS": "1", "NCCL_P2P_DISABLE": "1", "NCCL_IB_DISABLE": "1", "TORCH_NCCL_BLOCKING_WAIT": "1"})
    monitor_path = args.root / "nvml.json"
    with gpu_locks(), Monitor(monitor_path), (args.root / "torchrun.log").open("w") as log:
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        assert process.stdout is not None
        for line in process.stdout: log.write(line); log.flush(); print(line, end="", flush=True)
        code = process.wait()
    if code: raise RuntimeError(f"trajectory torchrun failed: {code}")
    value = json.loads(output.read_text()); value["nvml"] = summarize_monitor(monitor_path); json_write(output, value)
    if value["status"] != "PASS": raise ValueError("trajectory parity failed")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(); sub = p.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build-cache"); build.add_argument("--root", type=Path, required=True); build.add_argument("--workers", type=int, choices=(32, 24, 16), default=32); build.add_argument("--limit", type=int, default=0)
    gpu = sub.add_parser("gpu-producer"); gpu.add_argument("--gpu", type=int, required=True); gpu.add_argument("--plan", type=Path, required=True)
    gpu.add_argument("--prepared", type=Path, required=True); gpu.add_argument("--stage", type=Path, required=True); gpu.add_argument("--output", type=Path, required=True)
    worker = sub.add_parser("trajectory-worker"); worker.add_argument("--plan", type=Path, required=True); worker.add_argument("--prepared", type=Path, required=True)
    worker.add_argument("--geometry-cache", type=Path, required=True); worker.add_argument("--stage", type=Path, required=True); worker.add_argument("--output", type=Path, required=True)
    worker.add_argument("--max-updates", type=int, required=True); worker.add_argument("--with-validation", action="store_true"); worker.add_argument("--resume-checkpoint", type=Path)
    run = sub.add_parser("trajectory"); run.add_argument("--root", type=Path, required=True); run.add_argument("--plan", type=Path, required=True)
    run.add_argument("--prepared", type=Path, required=True); run.add_argument("--geometry-cache", type=Path, required=True); run.add_argument("--max-updates", type=int, required=True)
    run.add_argument("--with-validation", action="store_true"); run.add_argument("--resume-checkpoint", type=Path)
    validate = sub.add_parser("validate-cache"); validate.add_argument("--manifest", type=Path, required=True); validate.add_argument("--output", type=Path, required=True)
    prepared = sub.add_parser("finalize-prepared"); prepared.add_argument("--plan", type=Path, required=True)
    prepared.add_argument("--prepared", type=Path, required=True); prepared.add_argument("--output", type=Path, required=True)
    contract = sub.add_parser("contract"); contract.add_argument("--schema", type=Path, required=True); contract.add_argument("--output", type=Path, required=True)
    acceptance = sub.add_parser("acceptance"); acceptance.add_argument("--contract", type=Path, required=True)
    acceptance.add_argument("--verification", type=Path, required=True); acceptance.add_argument("--schema", type=Path, required=True); acceptance.add_argument("--output", type=Path, required=True)
    return p


def main() -> None:
    args = parser().parse_args()
    if args.command == "build-cache":
        with gpu_locks(): build_cache(args)
    elif args.command == "gpu-producer": gpu_producer(args.gpu, args.plan, args.prepared, args.stage, args.output)
    elif args.command == "trajectory-worker": trajectory_worker(args)
    elif args.command == "trajectory": launch_trajectory(args)
    elif args.command == "validate-cache": validate_cache(args)
    elif args.command == "finalize-prepared": finalize_prepared(args)
    elif args.command == "contract": build_runtime_contract(args)
    else: build_runtime_acceptance(args)


if __name__ == "__main__": main()
