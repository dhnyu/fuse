"""Summarize bounded pilot receipts and time exact query-only ranking, without publishing rankings."""
from __future__ import annotations

import argparse
import csv
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

import numpy as np
from p10_evaluation import evaluation_population, load_contract, resolve_model_bindings
from retrieval_gallery_pipeline import publish_json, read
from retrieval_gallery_ranking import rank_gallery
from retrieval_gallery_inputs import digest


def size(root):
    return sum(p.stat().st_size for p in Path(root).rglob("*") if p.is_file())


def quantiles(values):
    return dict(zip(("p50", "p95"), np.quantile(values, (.5, .95)).tolist()))


def compare_workers(left_path, right_path, output):
    import pyarrow.parquet as pq
    left, right = read(left_path), read(right_path)
    if any(p["status"] != "SPATIAL_PASS" or p["count"] != 1000 for p in (left, right)):
        raise ValueError("Two complete 1000-scene spatial pilots are required")
    a = {b["branch_id"]: read(Path(b["root"]) / "spatial_result.json") for b in left["branches"]}
    b = {r["branch_id"]: read(Path(r["root"]) / "spatial_result.json") for r in right["branches"]}
    if set(a) != set(b):
        raise ValueError("Worker comparison shard identities differ")
    checked, byte_identical, count, arrays = 0, 0, 0, 0
    for branch in a:
        if a[branch]["scene_ids"] != b[branch]["scene_ids"]:
            raise ValueError("Worker comparison scene ordering differs")
        count += a[branch]["count"]
        for stage, files in a[branch]["files"].items():
            other = {Path(p).name: Path(p) for p in b[branch]["files"][stage]}
            for first in map(Path, files):
                if first.suffix != ".parquet":
                    continue
                second = other[first.name]
                if digest(first) == digest(second):
                    byte_identical += 1
                elif not pq.read_table(first).equals(pq.read_table(second), check_metadata=False):
                    raise ValueError("Worker comparison scientific table differs: " + str(first))
                checked += 1
        qa, qb = [read(next(p for p in r[branch]["files"]["raster"] if Path(p).name == "branch_qc.json"))
                  for r in (a, b)]
        if qa["zarr"] != qb["zarr"]:
            raise ValueError("Worker comparison raster array hashes/attributes differ")
        arrays += 1
    return publish_json(output, {"status": "PASS", "count": count, "parquet_tables_checked": checked,
        "byte_identical_parquet_tables": byte_identical, "raster_shards_checked": arrays,
        "left_receipt_sha256": digest(left_path), "right_receipt_sha256": digest(right_path),
        "execution_metadata_excluded": True})


def summarize(spatial_path, input_path, contract, query_ids, canonical_ids):
    spatial, inputs = read(spatial_path), read(input_path)
    n = spatial["count"]
    if n not in (100, 500, 1000) or spatial["status"] != "SPATIAL_PASS" or inputs["status"] != "PASS":
        raise ValueError("Only complete bounded pilots may be summarized")
    root = Path(input_path).parent
    branches = [read(Path(b["root"]) / "spatial_result.json") for b in spatial["branches"]]
    stages = {}
    for stage in branches[0]["timings"]:
        values = [b["timings"][stage] for b in branches]
        total = sum(values)
        paths = {Path(p).parent for b in branches for p in b["files"][stage]}
        stages[stage] = {"worker_wall_seconds": total, "shard_seconds": quantiles(values),
            "scenes_per_worker_second": n / total, "bytes": sum(size(p) for p in paths)}
    entities = sum(b["entities"] for b in branches)
    edges = sum(b["relation_edges"] for b in branches)
    stages["vector"]["entities_per_worker_second"] = entities / stages["vector"]["worker_wall_seconds"]
    stages["relations"]["edges_per_worker_second"] = edges / stages["relations"]["worker_wall_seconds"]
    telemetry = {}
    for stage in ("geometry", "embeddings"):
        rows = list(csv.reader((root / stage / "gpu_samples.csv").read_text().splitlines()))
        telemetry[stage] = {}
        for gpu in (0, 1):
            values = [(float(r[2]), float(r[3])) for r in rows if len(r) == 4 and int(r[1]) == gpu]
            telemetry[stage][str(gpu)] = {"utilization_mean_percent": float(np.mean([v[0] for v in values])),
                "utilization_p95_percent": float(np.quantile([v[0] for v in values], .95)),
                "peak_used_vram_mib": max(v[1] for v in values)}
    preparation = read(root / "prepared/prepared_manifest.json")
    prepared_ids = preparation["scene_ids"]
    # Centers are recovered from frozen tensor batches, not rounded inspector assets.
    import torch
    centers = []
    for row in preparation["batches"]:
        payload = torch.load(root / "prepared" / row["relative_path"], map_location="cpu", weights_only=False)
        centers.extend(payload["batch"]["scene_center_5186"].numpy().tolist())
    models = {}
    for binding in resolve_model_bindings(contract):
        model = binding.configuration_id
        record = read(root / "embeddings" / (model + ".json"))
        old = Path(contract["publication_root"]) / "execution_attempts/p10exec_7fee193dac532190c79e02c6/evaluations" / model
        with np.load(old / "evaluation_embeddings_ranks_analysis.npz") as stored:
            vectors = np.concatenate([stored["embeddings"][3200:], np.load(root / "embeddings" / (model + ".npy"))])
            xy = np.concatenate([stored["centers"][3200:], np.asarray(centers)])
        durations = []
        for _ in range(3):
            start = time.perf_counter()
            ranks = rank_gallery(canonical_ids + prepared_ids, xy, vectors, query_ids, already_normalized=True)
            durations.append(time.perf_counter() - start)
            assert all(len(ranks[q]["standard"]["indices"]) == 1599 + n for q in query_ids)
        models[model] = {"wall_seconds": record["wall_seconds"], "scenes_per_second": n / record["wall_seconds"],
            "input_wait_seconds": sum(record["input_wait_seconds"]), "forward_seconds": sum(record["forward_seconds"]),
            "peak_allocated_vram_bytes": record["peak_allocated_vram_bytes"],
            "deterministic_bounded_rerun": record["deterministic_bounded_rerun"], "ranking_seconds": durations}
    resources = read(root / "resource_samples.json")
    return {"count": n, "workers": spatial["workers"], "spatial_wall_seconds": spatial["wall_seconds"],
        "spatial_scenes_per_second": n / spatial["wall_seconds"], "entities": entities, "relation_edges": edges,
        "spatial_shard_seconds": quantiles([b["wall_seconds"] for b in spatial["branches"]]),
        "spatial_peak_aggregate_rss_bytes": spatial["peak_aggregate_rss_bytes"], "spatial_stages": stages,
        "input_stage_seconds": inputs["stage_times"], "tensor_shard_seconds": quantiles(preparation["shard_timings"]),
        "input_peak_aggregate_children_rss_bytes": max(r["children_rss_bytes"] for r in resources),
        "storage_bytes": {p.name: size(p) for p in root.iterdir() if p.is_dir()}, "gpu_telemetry": telemetry,
        "models": models, "ranking_gallery_count": 1600 + n, "published_rankings": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spatial", type=Path, nargs=3, required=True)
    parser.add_argument("--inputs", type=Path, nargs=3, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    contract = load_contract(ROOT / "config/p10_evaluation.yml")
    _, gallery = evaluation_population(contract)
    queries = read(Path(contract["publication_root"]) / "qualitative/p10qq_dd7d0775f5809a793575342b.json")["selected_scene_ids"]
    rows = [summarize(a, b, contract, queries, [r["scene_id"] for r in gallery]) for a, b in zip(args.spatial, args.inputs)]
    if [r["count"] for r in rows] != [100, 500, 1000]:
        raise ValueError("Ordered nested 100/500/1000 pilots required")
    print(publish_json(args.output, {"status": "BENCHMARK_ONLY", "production_authorized": False, "pilots": rows}))


if __name__ == "__main__":
    main()
