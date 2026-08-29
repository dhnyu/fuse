"""Execution-only P7/P9 cold-path resource and publication contracts."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterable

from canonical_config import canonical_json_bytes, load_strict_yaml

RUNTIME_SCHEMA_VERSION = "1.0.0"


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def sha256_file(path: str | Path) -> str:
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def load_runtime_config(path: str | Path) -> dict[str, Any]:
    value = load_strict_yaml(path)
    if value.get("schema_version") != RUNTIME_SCHEMA_VERSION:
        raise ValueError("unsupported cold-path runtime contract version")
    workers = value["cpu_preparation"]["worker_tiers"]
    if workers != [32, 24, 16] or value["cpu_preparation"]["start_method"] != "spawn":
        raise ValueError("cold-path worker tiers/start method mismatch")
    gpu = value["gpu_producers"]
    if (gpu["producer_count"] != 2 or gpu["batch_size"] != 1
            or gpu["assignment"] != "canonical_index_modulo_2"):
        raise ValueError("cold-path GPU producer contract mismatch")
    if float(value["memory_admission"]["safety_margin_fraction"]) < 0.25:
        raise ValueError("cold-path memory safety margin is below 25 percent")
    if value["scientific_invariants"]["geometry_layout_version"] != "3.0.0":
        raise ValueError("cold-path runtime requires P6 geometry layout 3.0.0")
    return value


def required_memory_bytes(config: dict[str, Any], workers: int) -> int:
    memory = config["memory_admission"]
    fixed = int(memory["fixed_overhead_bytes"])
    per_worker = int(memory["per_worker_peak_bytes"])
    margin = 1.0 + float(memory["safety_margin_fraction"])
    return int((fixed + per_worker * int(workers)) * margin)


def select_worker_tier(config: dict[str, Any], available_bytes: int, current_rss_bytes: int = 0,
                       requested_workers: int | None = None, swap_in_delta_bytes: int = 0) -> dict[str, Any]:
    tiers = list(config["cpu_preparation"]["worker_tiers"])
    requested = int(requested_workers or tiers[0])
    if requested not in tiers:
        raise ValueError("worker override is outside the admitted tiers")
    if swap_in_delta_bytes > int(config["memory_admission"]["maximum_swap_in_delta_bytes"]):
        raise RuntimeError("swap-in admission limit exceeded")
    candidates = tiers[tiers.index(requested):]
    usable = max(0, int(available_bytes) - int(current_rss_bytes))
    for tier in candidates:
        required = required_memory_bytes(config, tier)
        if usable >= required:
            return {"requested_workers": requested, "selected_workers": tier,
                    "available_bytes": int(available_bytes), "current_rss_bytes": int(current_rss_bytes),
                    "usable_bytes": usable, "required_bytes": required,
                    "fallback": tier != requested, "safety_margin_fraction":
                    float(config["memory_admission"]["safety_margin_fraction"])}
    raise MemoryError("insufficient memory for the minimum 16-worker cold-path tier")


def memory_snapshot() -> dict[str, int]:
    import psutil
    memory = psutil.virtual_memory(); swap = psutil.swap_memory()
    return {"mem_available_bytes": int(memory.available), "current_process_rss_bytes":
            int(psutil.Process(os.getpid()).memory_info().rss), "swap_used_bytes": int(swap.used),
            "swap_sin_bytes": int(getattr(swap, "sin", 0))}


def required_staging_bytes(config: dict[str, Any]) -> int:
    disk = config["disk_staging"]
    return int((int(disk["measured_prepared_bytes"]) + int(disk["measured_final_cache_bytes"])
                + int(disk["validation_temporary_bytes"])) * (1.0 + float(disk["safety_margin_fraction"])))


def validate_staging_root(root: str | Path, config: dict[str, Any]) -> dict[str, int | str]:
    root = Path(root).resolve()
    prohibited = [Path(path).resolve() for path in config["disk_staging"]["prohibited_roots"]]
    if any(root == path or path in root.parents for path in prohibited):
        raise ValueError("staging root overlaps an accepted publication or targets-store root")
    root.parent.mkdir(parents=True, exist_ok=True)
    stat = os.statvfs(root.parent)
    free = int(stat.f_bavail * stat.f_frsize); required = required_staging_bytes(config)
    if free < required:
        raise OSError("insufficient free space for cold-path staging")
    return {"root": str(root), "free_bytes": free, "required_bytes": required}


def validate_fixed_indices(rows: Iterable[dict[str, Any]], expected: int) -> list[dict[str, Any]]:
    ordered = sorted(rows, key=lambda row: int(row["global_index"]))
    if [int(row["global_index"]) for row in ordered] != list(range(int(expected))):
        raise ValueError("missing or duplicate fixed-index result")
    return ordered


def prepared_manifest(plan: dict[str, Any], rows: Iterable[dict[str, Any]], layout: str) -> dict[str, Any]:
    ordered = validate_fixed_indices(rows, int(plan["entry_count"]))
    keys = ("global_index", "lookup_key", "cache_key", "sample_digest",
            "payload_size_bytes", "payload_sha256")
    value = {"schema_version": RUNTIME_SCHEMA_VERSION, "status": "PASS",
             "geometry_layout_version": layout, "plan_sha256": plan["plan_sha256"],
             "entry_count": len(ordered), "entries": [{key: row[key] for key in keys} for row in ordered]}
    value["content_sha256"] = digest(value)
    return value


def validate_prepared_manifest(value: dict[str, Any], plan: dict[str, Any], layout: str) -> None:
    scientific = {key: item for key, item in value.items() if key != "content_sha256"}
    if (value.get("status") != "PASS" or value.get("schema_version") != RUNTIME_SCHEMA_VERSION
            or value.get("geometry_layout_version") != layout or value.get("plan_sha256") != plan["plan_sha256"]
            or value.get("content_sha256") != digest(scientific)):
        raise ValueError("incomplete or incompatible prepared-view manifest")
    validate_fixed_indices(value["entries"], int(plan["entry_count"]))


def safe_cleanup_candidate(path: str | Path, expected_parent: str | Path, expected_namespace: str) -> Path:
    candidate = Path(path).resolve(); parent = Path(expected_parent).resolve()
    if candidate.parent != parent or candidate.name != expected_namespace or not expected_namespace:
        raise ValueError("unsafe staging cleanup target")
    if (candidate / "COMPLETE.json").exists():
        raise ValueError("completed cache cannot be handled as stale staging")
    return candidate
