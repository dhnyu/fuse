"""Finish a bounded spatial pilot with original-only caches and frozen forwards."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys
import time
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "python"))

import pyarrow.parquet as pq
import yaml

from p3_deterministic_tar import write, validate
from retrieval_gallery_pilot import sha, write_new, monitor_resources
from retrieval_gallery_inputs import prepare_originals
from retrieval_gallery_gpu import build_geometry, infer_all


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spatial-root", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, choices=(4, 8, 16), required=True)
    args = parser.parse_args()
    spatial = json.loads((args.spatial_root / "pilot_result.json").read_text())
    if spatial["status"] != "SPATIAL_PASS" or spatial["count"] not in (100, 500, 1000):
        raise ValueError("Bounded spatial pilot PASS is required")
    args.output.mkdir(parents=True, exist_ok=False)
    catalog = []
    stage_times = {}
    start = time.monotonic()
    for branch in spatial["branches"]:
        root = Path(branch["root"])
        result = json.loads((root / "spatial_result.json").read_text())
        spec = json.loads(Path(result["serialization_spec"]).read_text())
        path = args.output / "shards" / (branch["branch_id"] + ".tar")
        members = write(spec, str(path))
        validate(path, members)
        checksum = sha(path)
        write_new(path.with_suffix(".json"), {"status": "PASS", "sha256": checksum, "members": members})
        for scene_id in result["scene_ids"]:
            catalog.append({"scene_id": scene_id, "split": "retrieval_only", "branch_id": branch["branch_id"],
                            "payload_filename": path.name, "payload_path": str(path), "payload_sha256": checksum})
    stage_times["serialization_seconds"] = time.monotonic() - start
    ordered_ids = pq.read_table(args.index, columns=["scene_id"]).slice(0, spatial["count"]).column(0).to_pylist()
    by_id = {r["scene_id"]: r for r in catalog}
    if set(ordered_ids) != set(by_id) or len(catalog) != spatial["count"]:
        raise ValueError("Pilot catalog population mismatch")
    catalog = [by_id[s] for s in ordered_ids]
    write_new(args.output / "catalog.json", catalog)
    contract = yaml.safe_load((ROOT / "config/p10_evaluation.yml").read_text())
    prepared = prepare_originals(catalog, contract, args.output / "prepared", args.workers)
    stage_times["tensor_seconds"] = prepared["tensor_seconds"]
    stage_times["batch_seconds"] = prepared["batch_seconds"]
    geometry_authority = (Path(contract["prepared_input"]["geometry_root"]) /
        "p10geo_8cdab54a6886cb8217c0088b/prepared_geometry_manifest.json")
    start = time.monotonic()
    build_geometry(args.output / "prepared", args.output / "geometry", geometry_authority)
    stage_times["geometry_seconds"] = time.monotonic() - start
    stage_times["inference_seconds"] = infer_all(contract, args.output / "prepared", args.output / "geometry",
                                               args.output / "embeddings")
    spec = importlib.util.spec_from_file_location("retrieval_inspector", ROOT / "tools/retrieval_inspector/inspector.py")
    inspector = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(inspector)
    start = time.monotonic()
    hashes = inspector._scene_assets(ROOT, {}, set(ordered_ids), args.output / "render",
                                      catalog_rows=catalog, geographic_metadata={})
    stage_times["render_seconds"] = time.monotonic() - start
    if len(hashes) != spatial["count"]:
        raise ValueError("Missing pilot render assets")
    write_new(args.output / "input_pilot_result.json", {"status": "PASS", "count": spatial["count"],
        "stage_times": stage_times, "scene_asset_sha256": hashes, "models": 8,
        "bytes_written": sum(p.stat().st_size for p in args.output.rglob("*") if p.is_file()),
        "production_authorized": False})
    return args.output


if __name__ == "__main__":
    samples, stop = [], threading.Event()
    monitor = threading.Thread(target=monitor_resources, args=(stop, samples))
    monitor.start()
    try:
        output = main()
    finally:
        stop.set()
        monitor.join()
    write_new(output / "resource_samples.json", samples)
