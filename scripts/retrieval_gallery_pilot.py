"""Bounded, noncanonical spatial pilot for the supplementary retrieval gallery.

This entry point cannot publish an acceptance or start production/inference.
Existing scientific artifacts are opened read-only and snapshotted for comparison.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import threading

import pyarrow.parquet as pq
import psutil
import yaml


def sha(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def write_new(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as handle:
        json.dump(value, handle, sort_keys=True, indent=2, allow_nan=False)
        handle.write("\n")


def preservation():
    cfg = yaml.safe_load(Path("config/p10_evaluation.yml").read_text())
    roots = [Path(cfg["publication_root"]), Path(cfg["inputs"]["p9_canonical_root"])]
    for name in ("p11_downstream_dataset", "p11_spatial_readiness_acceptance",
                 "p11_ridge_evaluation_acceptance", "p11_diagnostic_probe_acceptance"):
        pointer = yaml.safe_load(Path(f"config/{name}.yml").read_text())
        roots.append(Path(pointer["acceptance_path"]).parent)
    roots.append(Path("/mnt/hdd002/dhnyu/fusedata/scene_data/reduced/index"))
    files = sorted({p for root in roots for p in root.rglob("*") if p.is_file()})
    return {str(p): {"size": p.stat().st_size, "sha256": sha(p)} for p in files}


def run_job(job):
    root = Path(job["root"])
    root.mkdir(parents=True, exist_ok=False)
    path = root / "job.json"
    write_new(path, job)
    env = {**os.environ, **{k: "1" for k in (
        "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "GDAL_NUM_THREADS")}}
    start = time.monotonic()
    peak_rss = 0
    with (root / "worker.log").open("x") as log:
        result = subprocess.Popen(["Rscript", "scripts/retrieval_gallery.R", "spatial", str(path)],
                                  env=env, stdout=log, stderr=subprocess.STDOUT)
        process = psutil.Process(result.pid)
        while result.poll() is None:
            try:
                peak_rss = max(peak_rss, sum(p.memory_info().rss for p in [process] + process.children(recursive=True)))
            except psutil.NoSuchProcess:
                pass
            time.sleep(.25)
    return {"branch_id": job["branch_id"], "returncode": result.returncode,
            "wall_seconds": time.monotonic() - start, "root": str(root), "peak_process_tree_rss_bytes": peak_rss}


def monitor_resources(stop, samples):
    process = psutil.Process()
    while not stop.is_set():
        try:
            rss = sum(child.memory_info().rss for child in process.children(recursive=True))
        except psutil.NoSuchProcess:
            continue
        cpu = psutil.cpu_times_percent(interval=.5)
        samples.append({"monotonic_seconds": time.monotonic(), "children_rss_bytes": rss,
                        "host_iowait_percent": getattr(cpu, "iowait", None)})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--count", type=int, choices=(100, 500, 1000), required=True)
    parser.add_argument("--workers", type=int, choices=(4, 8, 16, 32), required=True)
    parser.add_argument("--scaling-pilots", type=Path, nargs=2)
    args = parser.parse_args()
    if args.workers == 32:
        if not args.scaling_pilots or args.count != 1000:
            raise ValueError("32 workers require the completed 500/8 and 1000/16 scaling pilots")
        lower, upper = [json.loads(p.read_text()) for p in args.scaling_pilots]
        if (lower["status"] != "SPATIAL_PASS" or upper["status"] != "SPATIAL_PASS"
                or (lower["count"], lower["workers"], upper["count"], upper["workers"]) != (500, 8, 1000, 16)
                or upper["count"] / upper["wall_seconds"] <= lower["count"] / lower["wall_seconds"]):
            raise ValueError("Lower-concurrency throughput benefit was not demonstrated")
    args.root.mkdir(parents=True, exist_ok=False)
    before = preservation()
    write_new(args.root / "preservation_before.json", before)
    rows = pq.read_table(args.index).slice(0, args.count).to_pylist()
    index_id = "retridx_" + sha(args.index)[:24]
    jobs = []
    for offset in range(0, len(rows), 25):
        scenes = [{k: row[k] for k in ("scene_id", "split", "center_x", "center_y",
                  "xmin", "ymin", "xmax", "ymax")} for row in rows[offset:offset+25]]
        for scene in scenes:
            scene["scene_footprint_id"] = scene["scene_id"]
            scene["estimated_cost"] = 0
        identity = hashlib.sha256(json.dumps(scenes, sort_keys=True).encode()).hexdigest()
        branch = "retrbr_" + identity[:24]
        jobs.append({"root": str(args.root / branch), "branch_id": branch,
                     "dataset_id": index_id, "index_id": index_id, "scenes": scenes})
    start = time.monotonic()
    samples, stop = [], threading.Event()
    monitor = threading.Thread(target=monitor_resources, args=(stop, samples))
    monitor.start()
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
            results = list(pool.map(run_job, jobs))
    finally:
        stop.set()
        monitor.join()
    write_new(args.root / "resource_samples.json", samples)
    processing_seconds = time.monotonic() - start
    after = preservation()
    failures = [r for r in results if r["returncode"]]
    result = {"status": "BLOCKED" if failures or before != after else "SPATIAL_PASS",
              "count": args.count, "workers": args.workers, "threads_per_worker": 1,
              "wall_seconds": processing_seconds, "branches": results,
              "peak_aggregate_rss_bytes": max((s["children_rss_bytes"] for s in samples), default=0),
              "preservation_pass": before == after,
              "production_authorized": False, "inference_executions": 0}
    write_new(args.root / "pilot_result.json", result)
    print(json.dumps(result, indent=2), flush=True)
    raise SystemExit(1 if result["status"] == "BLOCKED" else 0)


if __name__ == "__main__":
    main()
