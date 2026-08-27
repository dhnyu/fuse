#!/usr/bin/env python3
"""Failure-isolated execution-only runner for P2 relation branches."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import signal
import time
from datetime import datetime
from pathlib import Path


THREAD_ENV = {
    "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1",
    "BLIS_NUM_THREADS": "1", "VECLIB_MAXIMUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1",
    "GDAL_NUM_THREADS": "1", "ARROW_NUM_THREADS": "1", "PYTHONDONTWRITEBYTECODE": "1",
}


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def proc_metrics(pids: list[int]) -> dict[str, float | int]:
    rss = []
    for pid in pids:
        try:
            status = Path(f"/proc/{pid}/status").read_text(encoding="utf-8")
            rss.append(int(next(line.split()[1] for line in status.splitlines() if line.startswith("VmRSS:"))))
        except (FileNotFoundError, StopIteration, PermissionError):
            pass
    available = 0
    try:
        meminfo = Path("/proc/meminfo").read_text(encoding="utf-8")
        available = int(next(line.split()[1] for line in meminfo.splitlines() if line.startswith("MemAvailable:")))
    except (FileNotFoundError, StopIteration):
        pass
    return {
        "active_workers": len(pids), "worker_rss_sum_kb": sum(rss),
        "worker_rss_max_kb": max(rss, default=0), "system_available_kb": available,
        "load_1m": os.getloadavg()[0],
    }


def result_classification(returncode: int, stderr: str, pass_id: str) -> str:
    suffix = {"pass_a_40": "PASS_A", "pass_b_10": "PASS_B", "pass_c_5": "PASS_C"}[pass_id]
    if returncode < 0 or returncode in (128 + signal.SIGSEGV, 128 + signal.SIGABRT, 139, 134):
        return f"FAILED_NATIVE_{suffix}"
    if any(term in stderr.lower() for term in ("out of memory", "oom", "no space left", "too many open files")):
        return f"FAILED_RESOURCE_{suffix}"
    return f"FAILED_SCIENTIFIC_{suffix}"


async def execute(manifest: dict, pass_id: str, workers: int, selected: list[dict], root: Path) -> dict:
    pass_root = root / "passes" / pass_id
    logs = pass_root / "logs"
    results_dir = root / "results" / pass_id
    logs.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)
    monitor_path = pass_root / "monitor.jsonl"
    semaphore = asyncio.Semaphore(workers)
    running: dict[str, asyncio.subprocess.Process] = {}
    records: dict[str, dict] = {}
    started = time.time()
    peak_concurrency = 0
    peak_rss_kb = 0
    peak_worker_rss_kb = 0

    async def run_branch(branch: dict) -> None:
        nonlocal peak_concurrency
        async with semaphore:
            branch_id = branch["branch_id"]
            log_path = logs / f"{branch_id}.log"
            env = os.environ.copy()
            env.update(THREAD_ENV)
            command = ["Rscript", "scripts/run_p2_relation_branch.R", str(Path(args.manifest).resolve()), pass_id, branch_id]
            launched = time.time()
            with log_path.open("wb") as log:
                process = await asyncio.create_subprocess_exec(*command, stdout=log, stderr=asyncio.subprocess.STDOUT, env=env)
                running[branch_id] = process
                peak_concurrency = max(peak_concurrency, len(running))
                returncode = await process.wait()
            running.pop(branch_id, None)
            result_path = results_dir / f"{branch_id}.json"
            if result_path.exists():
                record = json.loads(result_path.read_text(encoding="utf-8"))
            else:
                text = log_path.read_text(encoding="utf-8", errors="replace")[-10000:]
                record = {
                    "schema_version": "1.0.0", "pass": pass_id, "branch_id": branch_id,
                    "status": result_classification(returncode, text, pass_id), "final_status": "FAILED",
                    "returncode": returncode, "started_at": datetime.fromtimestamp(launched).astimezone().isoformat(),
                    "completed_at": now(), "wall_time_seconds": time.time() - launched,
                    "error_tail": text,
                }
                atomic_json(result_path, record)
            record["returncode"] = returncode
            records[branch_id] = record

    tasks = [asyncio.create_task(run_branch(branch)) for branch in selected]
    while any(not task.done() for task in tasks):
        metrics = proc_metrics([process.pid for process in running.values() if process.returncode is None])
        peak_rss_kb = max(peak_rss_kb, int(metrics["worker_rss_sum_kb"]))
        peak_worker_rss_kb = max(peak_worker_rss_kb, int(metrics["worker_rss_max_kb"]))
        counts: dict[str, int] = {}
        for record in records.values():
            counts[record["status"]] = counts.get(record["status"], 0) + 1
        event = {"timestamp": now(), "pass": pass_id, **metrics, "completed_records": len(records), "status_counts": counts}
        with monitor_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, sort_keys=True) + "\n")
        await asyncio.sleep(10)
    await asyncio.gather(*tasks)
    counts: dict[str, int] = {}
    for record in records.values():
        counts[record["status"]] = counts.get(record["status"], 0) + 1
    summary = {
        "schema_version": "1.0.0", "pass": pass_id, "requested_workers": workers,
        "thread_environment": THREAD_ENV, "input_branch_count": len(selected),
        "input_branch_ids": [branch["branch_id"] for branch in selected],
        "records": records, "status_counts": counts,
        "started_at": datetime.fromtimestamp(started).astimezone().isoformat(),
        "completed_at": now(), "wall_time_seconds": time.time() - started,
        "peak_concurrency": peak_concurrency, "peak_worker_rss_sum_kb": peak_rss_kb,
        "peak_single_worker_rss_kb": peak_worker_rss_kb,
        "automatic_retries": 0,
    }
    atomic_json(pass_root / "summary.json", summary)
    return summary


def retry_selection(manifest: dict, previous: dict, previous_pass: str) -> list[dict]:
    suffix = {"pass_a_40": "PASS_A", "pass_b_10": "PASS_B"}[previous_pass]
    allowed = {
        f"FAILED_NATIVE_{suffix}", f"FAILED_RESOURCE_{suffix}", f"UNATTEMPTED_{suffix}",
    }
    records = previous.get("records", {})
    return [branch for branch in manifest["branches"] if records.get(branch["branch_id"], {}).get("status") in allowed]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--pass-id", choices=("pass_a_40", "pass_b_10", "pass_c_5"), required=True)
    parser.add_argument("--workers", type=int, required=True)
    parser.add_argument("--previous-summary")
    args = parser.parse_args()
    expected = {"pass_a_40": 40, "pass_b_10": 10, "pass_c_5": 5}
    if args.workers != expected[args.pass_id]:
        raise SystemExit(f"worker contract mismatch: {args.pass_id} requires {expected[args.pass_id]}")
    manifest_path = Path(args.manifest).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    root = manifest_path.parent
    if args.pass_id == "pass_a_40":
        selected = manifest["branches"]
    else:
        if not args.previous_summary:
            raise SystemExit("recovery passes require --previous-summary")
        previous = json.loads(Path(args.previous_summary).read_text(encoding="utf-8"))
        previous_pass = "pass_a_40" if args.pass_id == "pass_b_10" else "pass_b_10"
        selected = retry_selection(manifest, previous, previous_pass)
    summary = asyncio.run(execute(manifest, args.pass_id, args.workers, selected, root))
    print(json.dumps({"pass": args.pass_id, "status_counts": summary["status_counts"]}, sort_keys=True))
