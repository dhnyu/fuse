#!/usr/bin/env python3
"""Fail-soft, pass-scoped controller for P5 fixed-query branches."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

THREAD_ENV = {
    "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1",
    "BLIS_NUM_THREADS": "1", "VECLIB_MAXIMUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1",
    "GDAL_NUM_THREADS": "1", "ARROW_NUM_THREADS": "1", "PYTHONDONTWRITEBYTECODE": "1",
}
RETRYABLE = {"FAILED_NATIVE", "FAILED_RESOURCE", "UNATTEMPTED"}
ACTIVE: dict[str, subprocess.Popen[str]] = {}
ACTIVE_LOCK = threading.Lock()


def canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def classify(returncode: int, output: str) -> str:
    lowered = output.lower()
    if returncode < 0 or any(token in lowered for token in ("segmentation fault", "sigsegv", "sigabrt", "bus error")):
        return "FAILED_NATIVE"
    if any(token in lowered for token in ("out of memory", "oom", "no space left", "too many open files", "resource temporarily unavailable")):
        return "FAILED_RESOURCE"
    return "FAILED_SCIENTIFIC"


def process_rss(pid: int) -> int:
    try:
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) * 1024
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        pass
    return 0


def validate_canonical(spec: dict[str, object], final: Path) -> dict[str, object]:
    manifest = json.loads((final / "branch_manifest.json").read_text())
    payload = final / manifest["payload"]["filename"]
    if (manifest.get("branch_id") != spec["branch_id"] or
            not payload.is_file() or sha256_file(payload) != manifest["payload"]["sha256"]):
        raise RuntimeError(f"immutable canonical collision: {spec['branch_id']}")
    return manifest


def publish(build: Path, final: Path, spec: dict[str, object]) -> str:
    if final.exists():
        validate_canonical(spec, final)
        shutil.rmtree(build)
        return "REUSED_IDENTICAL"
    final.parent.mkdir(parents=True, exist_ok=True)
    os.rename(build, final)
    validate_canonical(spec, final)
    return "PUBLISHED"


def run_branch(spec_path: Path, staging_root: Path, cli: Path, pass_name: str, workers: int) -> dict[str, object]:
    spec = json.loads(spec_path.read_text())
    branch_id = spec["branch_id"]
    final = Path(spec["output_directory"])
    if (final / "branch_manifest.json").exists():
        manifest = validate_canonical(spec, final)
        return {"branch_id": branch_id, "status": "COMPLETED", "returncode": 0,
                "split": spec["split"], "query_count": manifest["query_count"],
                "payload_bytes": manifest["payload"]["size_bytes"],
                "payload_sha256": manifest["payload"]["sha256"],
                "publication": "REUSED_IDENTICAL", "wall_seconds": 0, "staging_path": None}
    stage = staging_root / branch_id
    build = stage / "build"
    stage.mkdir(parents=True, exist_ok=False)
    started = time.time()
    env = {**os.environ, **THREAD_ENV, "FUSE_P5_EXECUTION_PASS": pass_name,
           "FUSE_P5_REQUESTED_WORKERS": str(workers)}
    command = [sys.executable, str(cli), "branch", "--spec", str(spec_path), "--output-dir", str(build)]
    process = subprocess.Popen(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    with ACTIVE_LOCK:
        ACTIVE[branch_id] = process
    output, _ = process.communicate()
    with ACTIVE_LOCK:
        ACTIVE.pop(branch_id, None)
    (stage / "builder.log").write_text(output)
    if process.returncode:
        return {"branch_id": branch_id, "status": classify(process.returncode, output),
                "returncode": process.returncode, "wall_seconds": time.time() - started,
                "staging_path": str(stage), "error": output[-4000:]}
    config_path = stage / "runtime_config.json"
    config_path.write_bytes(canonical(spec["config"]))
    validation = stage / "independent_validation.json"
    checked = subprocess.run([sys.executable, str(cli), "validate",
                              "--manifest", str(build / "branch_manifest.json"),
                              "--config-json", str(config_path), "--output", str(validation)],
                             env=env, capture_output=True, text=True)
    if checked.returncode:
        detail = checked.stdout + checked.stderr
        return {"branch_id": branch_id, "status": "FAILED_SCIENTIFIC", "returncode": checked.returncode,
                "wall_seconds": time.time() - started, "staging_path": str(stage), "error": detail[-4000:]}
    verdict = json.loads(validation.read_text())
    if verdict.get("status") != "PASS":
        return {"branch_id": branch_id, "status": "FAILED_SCIENTIFIC", "returncode": 0,
                "wall_seconds": time.time() - started, "staging_path": str(stage), "error": "validator rejected branch"}
    try:
        publication = publish(build, final, spec)
    except Exception as error:
        return {"branch_id": branch_id, "status": "FAILED_SCIENTIFIC", "returncode": 0,
                "wall_seconds": time.time() - started, "staging_path": str(stage), "error": str(error)}
    manifest = validate_canonical(spec, final)
    return {"branch_id": branch_id, "status": "COMPLETED", "returncode": 0,
            "split": spec["split"], "query_count": manifest["query_count"],
            "payload_bytes": manifest["payload"]["size_bytes"],
            "payload_sha256": manifest["payload"]["sha256"], "publication": publication,
            "wall_seconds": time.time() - started, "staging_path": str(stage)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan-dir", required=True)
    parser.add_argument("--pass-name", choices=("A", "B", "C"), required=True)
    parser.add_argument("--workers", type=int, required=True)
    parser.add_argument("--staging-root", required=True)
    parser.add_argument("--ledger", required=True)
    parser.add_argument("--retry-ledger")
    args = parser.parse_args()
    expected = {"A": 40, "B": 10, "C": 5}[args.pass_name]
    if args.workers != expected:
        raise SystemExit(f"pass {args.pass_name} requires {expected} workers")
    root = Path(__file__).resolve().parents[1]
    specs = sorted(Path(args.plan_dir).glob("spec-*.json"))
    if args.pass_name == "A":
        if len(specs) != 192:
            raise SystemExit("Pass A requires all 192 intended branches")
    else:
        if not args.retry_ledger:
            raise SystemExit("recovery pass requires prior ledger")
        previous = json.loads(Path(args.retry_ledger).read_text())
        retry_ids = {row["branch_id"] for row in previous["branches"] if row["status"] in RETRYABLE}
        specs = [path for path in specs if json.loads(path.read_text())["branch_id"] in retry_ids]
    staging_root = Path(args.staging_root)
    staging_root.mkdir(parents=True, exist_ok=False)
    ledger_path = Path(args.ledger)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.time(); peak_concurrency = peak_rss_sum = peak_rss_worker = 0
    results: list[dict[str, object]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        pending = {pool.submit(run_branch, path, staging_root, root / "scripts/p5_fixed_queries.py",
                               args.pass_name, args.workers): path for path in specs}
        while pending:
            done, _ = concurrent.futures.wait(pending, timeout=1, return_when=concurrent.futures.FIRST_COMPLETED)
            with ACTIVE_LOCK:
                processes = list(ACTIVE.values())
            rss = [process_rss(process.pid) for process in processes]
            peak_concurrency = max(peak_concurrency, len(processes)); peak_rss_sum = max(peak_rss_sum, sum(rss))
            peak_rss_worker = max([peak_rss_worker, *rss])
            for future in done:
                path = pending.pop(future)
                try:
                    results.append(future.result())
                except Exception as error:
                    branch_id = json.loads(path.read_text())["branch_id"]
                    results.append({"branch_id": branch_id, "status": "FAILED_SCIENTIFIC",
                                    "returncode": 0, "error": repr(error), "wall_seconds": 0})
            summary = {status: sum(row["status"] == status for row in results)
                       for status in ("COMPLETED", "FAILED_NATIVE", "FAILED_RESOURCE", "FAILED_SCIENTIFIC")}
            print(json.dumps({"completed_results": len(results), "running": len(processes),
                              "remaining": len(pending), **summary}, sort_keys=True), flush=True)
    ordered = sorted(results, key=lambda row: row["branch_id"])
    ledger = {"schema_version": "1.0.0", "pass": args.pass_name, "requested_workers": args.workers,
              "input_branches": len(specs), "peak_observed_concurrency": peak_concurrency,
              "peak_rss_sum_bytes": peak_rss_sum, "peak_rss_worker_bytes": peak_rss_worker,
              "wall_seconds": time.time() - started, "branches": ordered}
    ledger["status_counts"] = {status: sum(row["status"] == status for row in ordered)
                               for status in ("COMPLETED", "FAILED_NATIVE", "FAILED_RESOURCE", "FAILED_SCIENTIFIC", "UNATTEMPTED")}
    ledger["content_sha256"] = hashlib.sha256(canonical({key: value for key, value in ledger.items() if key != "wall_seconds"})).hexdigest()
    ledger_path.write_bytes(canonical(ledger))
    if ledger["status_counts"]["FAILED_SCIENTIFIC"]:
        raise SystemExit(2)
    if sum(value for key, value in ledger["status_counts"].items() if key != "COMPLETED"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
