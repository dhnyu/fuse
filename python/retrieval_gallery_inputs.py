"""Original-only supplemental input preparation using frozen P3/P10 kernels.

No canonical catalog is modified and no augmentation or inference is performed.
"""
from __future__ import annotations

import concurrent.futures
import hashlib
import json
import multiprocessing
from pathlib import Path
import time

import torch

from p6_data import build_vocabulary, read_original_scene, tensorize_scene
from p7_training import collate
from p9_model_families import ds_raster_from_batch
from p10_prepared_input import _atomic_torch


def digest(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


class SupplementalCatalog:
    """Resolve only explicitly supplied, hash-bound original-scene shards."""

    def __init__(self, rows):
        self.rows = {row["scene_id"]: row for row in rows}
        if len(self.rows) != len(rows):
            raise ValueError("Duplicate supplemental scene ID")
        verified = {}
        for row in rows:
            if not row["scene_id"].startswith("retrscn_") or row["split"] != "retrieval_only":
                raise ValueError("Non-supplemental scene in supplemental catalog")
            path = row["payload_path"]
            if path not in verified:
                verified[path] = digest(path)
            if verified[path] != row["payload_sha256"]:
                raise ValueError("Supplemental shard checksum mismatch")

    def p3_tar(self, scene_id):
        row = self.rows[scene_id]
        return Path(row["payload_path"]), row


def _prepare_shard(task):
    rows, preprocessing_path, categories_path, output = task
    torch.set_num_threads(1)
    catalog = SupplementalCatalog(rows)
    preprocessing = json.loads(Path(preprocessing_path).read_text())
    vocabulary = build_vocabulary(categories_path)
    start = time.monotonic()
    result = []
    for row in rows:
        scene = read_original_scene(catalog, row["scene_id"])
        sample = tensorize_scene(scene, preprocessing, vocabulary)
        sample["scene_center_5186"] = torch.tensor(scene["center"], dtype=torch.float64)
        ds = ds_raster_from_batch(collate([sample], vocabulary))[0]
        path = Path(output) / (row["scene_id"] + ".pt")
        _atomic_torch(path, {"scene_id": row["scene_id"], "sample": sample, "ds_raster": ds})
        check = torch.load(path, map_location="cpu", weights_only=False)
        if check["scene_id"] != row["scene_id"]:
            raise ValueError("Prepared scene roundtrip mismatch")
        result.append({"scene_id": row["scene_id"], "path": str(path), "sha256": digest(path),
                       "size_bytes": path.stat().st_size})
    return {"scenes": result, "wall_seconds": time.monotonic() - start}


def prepare_originals(catalog_rows, contract, output, workers):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    scene_root = output / "scenes"
    scene_root.mkdir()
    by_shard = {}
    for row in catalog_rows:
        by_shard.setdefault(row["payload_path"], []).append(row)
    tasks = [(rows, contract["inputs"]["preprocessing"], contract["inputs"]["categories"], str(scene_root))
             for rows in by_shard.values()]
    start = time.monotonic()
    with concurrent.futures.ProcessPoolExecutor(max_workers=workers,
            mp_context=multiprocessing.get_context("spawn")) as pool:
        prepared = list(pool.map(_prepare_shard, tasks))
    tensor_seconds = time.monotonic() - start
    inventory = {row["scene_id"]: row for shard in prepared for row in shard["scenes"]}
    ordered_ids = [row["scene_id"] for row in catalog_rows]
    identity = {"version": "retrieval-original-input-v1", "scene_ids": ordered_ids,
                "preprocessing_sha256": digest(contract["inputs"]["preprocessing"]),
                "vocabulary_sha256": digest(contract["inputs"]["categories"]),
                "source_shards": [{"scene_id": r["scene_id"], "payload_sha256": r["payload_sha256"]}
                                  for r in catalog_rows],
                "implementation": {name: digest(Path(__file__).parent / name) for name in
                    ("retrieval_gallery_inputs.py", "p6_data.py", "p7_training.py", "p9_model_families.py")},
                "batch_size": 8, "original_only": True}
    cache_id = "retrpi_" + hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:24]
    vocabulary = build_vocabulary(contract["inputs"]["categories"])
    (output / "batches").mkdir()
    batches = []
    start = time.monotonic()
    for offset in range(0, len(ordered_ids), 8):
        ids = ordered_ids[offset:offset+8]
        bundles = [torch.load(inventory[s]["path"], map_location="cpu", weights_only=False) for s in ids]
        spec = {"split": "retrieval_only", "kind": "gallery", "batch_index": offset // 8,
                "records": [{"scene_id": scene_id, "view": None} for scene_id in ids]}
        relative = f"batches/retrieval_only-gallery-{offset // 8:04d}.pt"
        path = output / relative
        _atomic_torch(path, {"schema_version": "1.0.0", "cache_id": cache_id, "identity": spec,
                             "batch": collate([b["sample"] for b in bundles], vocabulary),
                             "ds_raster": torch.stack([b["ds_raster"] for b in bundles]).contiguous()})
        batches.append({**spec, "relative_path": relative, "payload_sha256": digest(path),
                        "size_bytes": path.stat().st_size})
        check = torch.load(path, map_location="cpu", weights_only=False)
        if check["identity"] != spec or check["batch"]["scene_ids"] != ids:
            raise ValueError("Prepared batch roundtrip identity mismatch")
    intermediate_bytes = sum(row["size_bytes"] for row in inventory.values())
    # Match the accepted P10 architecture: scene bundles are temporary; only the
    # verified tensor-ready batches persist. Delete only this run's own files.
    for row in inventory.values():
        Path(row["path"]).unlink()
    scene_root.rmdir()
    manifest = {"status": "PASS", "cache_id": cache_id, "identity": identity, "batches": batches,
                "workers": workers, "threads_per_worker": 1,
                "scene_ids": ordered_ids, "intermediate_scene_bytes": intermediate_bytes,
                "shard_timings": [p["wall_seconds"] for p in prepared],
                "tensor_seconds": tensor_seconds, "batch_seconds": time.monotonic() - start}
    with (output / "prepared_manifest.json").open("x") as handle:
        json.dump(manifest, handle, sort_keys=True, indent=2)
    return manifest
