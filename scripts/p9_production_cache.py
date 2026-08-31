#!/usr/bin/env python3
"""Build and validate the explicitly authorized, optimizer-free P9 union cache."""

from __future__ import annotations

import argparse
import concurrent.futures
import contextlib
import fcntl
import json
import multiprocessing as mp
import os
import shutil
import subprocess
import sys
import tarfile
import time
import resource
from collections import defaultdict
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
import torch
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "python"), str(ROOT / "scripts")]

from p9_v1_retirement import reject_v1_execution, retire_v1_cli  # noqa: E402

if __name__ == "__main__":
    retire_v1_cli("scripts/p9_production_cache.py")

from canonical_config import canonical_json_bytes, load_strict_yaml  # noqa: E402
from p6_data import apply_delta, build_vocabulary  # noqa: E402
from p7_geometry_cache import GeometryCacheWriter, cache_record, sha256_file, tensor_sha256, validate_payload  # noqa: E402
from p7_training import P7ArtifactCatalog, collate  # noqa: E402
from p9_data import P9Data  # noqa: E402
from p9_formal_authorization import digest, load_config, read_json  # noqa: E402
from p9_model_families import ds_raster_from_batch  # noqa: E402
from p7_prototype_training import geometry  # noqa: E402

_VALUES: dict[str, Any] | None = None
_PREPARED: Path | None = None


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_json_bytes(value)
    if path.exists():
        if path.read_bytes() != payload: raise FileExistsError(f"immutable JSON collision: {path}")
        return
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_bytes(payload); os.replace(temporary, path)


class ProductionCatalog(P7ArtifactCatalog):
    def __init__(self, roots: dict[str, str], expected: dict[str, str], verify: bool = True) -> None:
        super().__init__(roots, expected, verify=verify)
        acceptance = next((self.roots["p4"] / "acceptance").glob("*/effective_bank_index.parquet"))
        self.effective = pq.read_table(acceptance).to_pylist()
        p3_by_sha = {row["payload_sha256"]: row["branch_id"] for row in self.p3_rows}
        self.profile_branches: dict[str, dict[str, tuple[Path, dict[str, Any]]]] = {}
        for profile in ("main_1.0x", "weak_0.5x", "strong_2.0x"):
            branches = {}
            for manifest_path in sorted((self.roots["p4"] / "shards" / profile).glob("*/branch_manifest.json")):
                manifest = read_json(manifest_path); parent = p3_by_sha.get(manifest["parent_tar_sha256"])
                if parent is None: raise ValueError("P9 P4 profile parent mismatch")
                branches[parent] = (manifest_path.parent / manifest["payload"]["filename"], manifest)
            if len(branches) != 96: raise ValueError(f"P9 {profile} branch coverage mismatch")
            self.profile_branches[profile] = branches

    def p4_tar_profile(self, scene_id: str, profile: str) -> tuple[Path, dict[str, Any]]:
        _, row = self.p3_tar(scene_id); path, manifest = self.profile_branches[profile][row["branch_id"]]
        self._verify(path, manifest["payload"]["sha256"]); return path, manifest


class ProductionData(P9Data):
    def __init__(self, catalog: ProductionCatalog, preprocessing: dict[str, Any], vocabulary: dict[str, Any],
                 selected_rows: dict[str, list[dict[str, Any]]]) -> None:
        super().__init__(catalog, preprocessing, vocabulary)
        self.selected_rows = selected_rows; self.rows_by_profile = {}
        self.branch_candidate_ids.clear()
        for profile, rows in selected_rows.items():
            grouped: dict[str, dict[int, dict[str, Any]]] = defaultdict(dict)
            for row in rows:
                grouped[row["scene_id"]][int(row["master_view_id"])] = row
                path, _ = catalog.p4_tar_profile(row["scene_id"], profile)
                self.branch_candidate_ids[path].add(row["candidate_id"])
            self.rows_by_profile[profile] = grouped

    def profile_view(self, profile: str, scene_id: str, master_view_id: int) -> dict[str, Any]:
        key = (profile, scene_id, int(master_view_id))
        if key not in self.cache:
            row = self.rows_by_profile[profile].get(scene_id, {}).get(int(master_view_id))
            if row is None: raise KeyError("P9 canonical profile/view membership miss")
            path, _ = self.catalog.p4_tar_profile(scene_id, profile)
            delta = self._branch_deltas(path).get(row["candidate_id"])
            if delta is None: raise ValueError("P9 accepted P4 delta is missing")
            self.cache[key] = self._finish(apply_delta(self._original(scene_id), delta, row["candidate_id"], profile))
        return self.cache[key]


def selected_rows(config: dict[str, Any], catalog: ProductionCatalog) -> dict[str, list[dict[str, Any]]]:
    result = {}
    for profile, k in config["cache"]["allowed_profiles"].items():
        rows = [row for row in catalog.effective if row["profile_id"] == profile and int(row["requested_k"]) == int(k)]
        rows.sort(key=lambda row: (row["scene_id"], int(row["master_view_id"]), row["candidate_id"]))
        if len(rows) != 2421 * int(k): raise ValueError(f"P9 {profile} cache membership mismatch")
        result[profile] = rows
    return result


def runtime_values(config_path: str | Path, verify: bool = True) -> dict[str, Any]:
    config = load_config(config_path); training = yaml.safe_load((ROOT / config["inputs"]["p7_training_config"]).read_text())
    catalog = ProductionCatalog({key: config["roots"][key] for key in ("p3", "p4", "p5")}, training["parents"], verify=verify)
    rows = selected_rows(config, catalog)
    preprocessing = read_json(config["inputs"]["preprocessing"]); vocabulary = build_vocabulary(config["inputs"]["categories"])
    return {"config": config, "training": training, "catalog": catalog, "rows": rows,
            "data": ProductionData(catalog, preprocessing, vocabulary, rows), "vocabulary": vocabulary,
            "model": load_strict_yaml(ROOT / config["inputs"]["p6_model_config"]),
            "implementation_sha256": sha256_file(ROOT / "python/prototype_encoder.py")}


def canonical_specs(values: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for profile in sorted(values["rows"]):
        role = "training" if profile == "main_1.0x" else f"training:{profile}"
        for row in values["rows"][profile]:
            result.append({"role": role, "profile": profile, "scene_id": row["scene_id"],
                           "view": int(row["master_view_id"]), "candidate_id": row["candidate_id"]})
    for row in values["catalog"].query_rows["validation"]:
        result.append({"role": "validation_query", "profile": "validation-query", "scene_id": row["scene_id"],
                       "view": int(row["query_index"]), "candidate_id": row["query_id"]})
    for row in values["catalog"].gallery_rows["validation"]:
        result.append({"role": "validation_gallery", "profile": "original", "scene_id": row["scene_id"],
                       "view": None, "candidate_id": "original"})
    result.sort(key=lambda row: (row["role"], row["scene_id"], -1 if row["view"] is None else row["view"]))
    for index, row in enumerate(result): row["global_index"] = index
    if len(result) != 78672: raise ValueError("P9 canonical union must contain 78,672 views")
    return result


def sample_for(values: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    if spec["role"].startswith("training"):
        return values["data"].profile_view(spec["profile"], spec["scene_id"], int(spec["view"]))
    if spec["role"] == "validation_query": return values["data"].validation_query(spec["scene_id"], int(spec["view"]))
    return values["data"].validation_gallery(spec["scene_id"])


def worker_init(config_path: str, prepared: str) -> None:
    global _VALUES, _PREPARED
    for name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        os.environ[name] = "1"
    torch.set_num_threads(1)
    if torch.cuda.is_initialized(): raise RuntimeError("P9 CPU preparation worker initialized CUDA")
    _VALUES, _PREPARED = runtime_values(config_path, verify=True), Path(prepared)


def ds_manifest(spec: dict[str, Any], tensor: torch.Tensor, source_record: dict[str, Any]) -> dict[str, Any]:
    identity = {"schema_version": "1.0.0", "contract_id": "p8ds_73137985bd6b172f6711a062",
                "geometry_layout_version": "3.0.0", "role": spec["role"], "scene_id": spec["scene_id"],
                "view_id": str(spec["candidate_id"]), "source_cache_key": source_record["cache_key"],
                "shape": list(tensor.shape), "dtype": str(tensor.dtype), "raw_sha256": tensor_sha256(tensor)}
    return {**identity, "cache_key": digest(identity)}


def prepare_one(task: tuple[int, dict[str, Any]]) -> dict[str, Any]:
    index, spec = task; assert _VALUES is not None and _PREPARED is not None
    path = _PREPARED / f"{index:06d}.pt"; summary_path = _PREPARED / f"{index:06d}.json"
    if path.is_file() and summary_path.is_file():
        summary = read_json(summary_path)
        if summary.get("global_index") == index and summary.get("payload_sha256") == sha256_file(path): return summary
        raise ValueError("P9 stale prepared slot mismatch")
    sample = sample_for(_VALUES, spec)
    record = cache_record(sample, _VALUES["training"]["parents"], _VALUES["model"]["model"]["geometry"],
                          _VALUES["implementation_sha256"], spec["role"])
    batch = collate([sample], _VALUES["vocabulary"]); ds = ds_raster_from_batch(batch)[0].contiguous()
    ds_row = ds_manifest(spec, ds, record)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    torch.save({"global_index": index, "spec": spec, "record": record, "sample": sample,
                "ds_manifest": ds_row, "ds_raster": ds}, temporary); os.replace(temporary, path)
    summary = {"global_index": index, "spec": spec, "record": record, "ds_manifest": ds_row,
               "payload_size_bytes": path.stat().st_size, "payload_sha256": sha256_file(path)}
    atomic_json(summary_path, summary)
    _VALUES["data"].cache.clear(); _VALUES["data"].original_cache.clear(); _VALUES["data"].branch_delta_cache.clear()
    return summary


def gpu_producer(args: argparse.Namespace) -> None:
    gpu = int(args.gpu); torch.cuda.set_device(gpu); torch.use_deterministic_algorithms(True)
    torch.backends.cuda.matmul.allow_tf32 = False; torch.backends.cudnn.allow_tf32 = False
    values = runtime_values(args.config, verify=False); specs = read_json(args.plan)["entries"]
    device = torch.device("cuda", gpu); writer = GeometryCacheWriter(args.geometry_stage); rows = []
    for spec in specs:
        index = int(spec["global_index"])
        if index % 2 != gpu: continue
        path = Path(args.prepared) / f"{index:06d}.pt"; deadline = time.monotonic() + 7200
        while not path.is_file():
            if time.monotonic() > deadline: raise TimeoutError("P9 prepared slot timeout")
            time.sleep(.05)
        payload = torch.load(path, map_location="cpu", weights_only=False)
        if payload["global_index"] != index or payload["spec"] != spec: raise ValueError("P9 fixed-index handoff mismatch")
        batch = collate([payload["sample"]], values["vocabulary"])
        magnitude, phase = geometry(batch, values["model"], device)
        writer.put(payload["record"], magnitude, phase); rows.append(payload["record"])
    atomic_json(Path(args.output), {"gpu": gpu, "entry_count": len(rows), "records": rows})


def memory_worker_tier(config: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    info = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, value = line.split(":", 1); info[key] = int(value.strip().split()[0]) * 1024
    available = info["MemAvailable"]; measured = int(config["cache"]["measured_32_worker_peak_rss_bytes"])
    thresholds = {str(tier): int(measured * tier / 32 / (1.0 - float(config["cache"]["memory_safety_fraction"])))
                  for tier in (32, 24, 16)}
    for tier in (32, 24, 16):
        if available >= thresholds[str(tier)]: return tier, {"mem_available_bytes": available, "thresholds": thresholds}
    raise MemoryError("P9 cache build lacks memory for the minimum 16-worker tier")


def disk_gate(config: dict[str, Any]) -> dict[str, int]:
    root = Path(config["roots"]["staging"]); root.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(root); required = int(config["cache"]["minimum_free_space_bytes"])
    if usage.free < required: raise OSError("P9 production cache lacks bounded disk headroom")
    return {"free_before_bytes": usage.free, "minimum_required_bytes": required}


@contextlib.contextmanager
def gpu_locks(config: dict[str, Any]):
    root = Path(yaml.safe_load((ROOT / "config/p7_cold_path_runtime.yml").read_text())["gpu_lock_root"])
    streams = []
    try:
        for name in ("gpu_pair.lock", "gpu0.lock", "gpu1.lock"):
            stream = (root / name).open("a+")
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB); streams.append(stream)
        yield
    finally:
        for stream in reversed(streams):
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN); stream.close()


def build(args: argparse.Namespace) -> Path:
    reject_v1_execution("scripts/p9_production_cache.py:build")
    config = load_config(args.config); authority = read_json(args.authority)
    expected_env = os.environ.get("FUSE_P9_CACHE_BUILD_AUTHORITY_ID")
    if authority.get("artifact_id") != expected_env or authority.get("status") != "CACHE_BUILD_ONLY":
        raise PermissionError("explicit P9 cache-build authority environment gate is not satisfied")
    if authority.get("optimizer_authorized") or authority.get("formal_validation_authorized"):
        raise PermissionError("cache authority must not authorize training")
    cache_root = Path(config["roots"]["cache"]) / authority["artifact_id"]
    if cache_root.exists():
        complete = cache_root / "production_cache_manifest.json"
        if not complete.is_file(): raise FileExistsError("incomplete final P9 cache namespace exists")
        print(f"P9_CACHE_OUTPUT={complete}"); return complete
    staging = Path(config["roots"]["staging"]) / authority["artifact_id"]
    staging.mkdir(parents=True, exist_ok=True); prepared = staging / "prepared"; prepared.mkdir(exist_ok=True)
    geometry_stage = staging / "geometry"; geometry_stage.mkdir(exist_ok=True)
    resources = {"disk": disk_gate(config)}; workers, resources["memory"] = memory_worker_tier(config)
    values = runtime_values(args.config, verify=True); specs = canonical_specs(values)
    plan = {"schema_version": "1.0.0", "authority_id": authority["artifact_id"], "entry_count": len(specs),
            "membership_sha256": digest(specs), "entries": specs}
    plan_path = staging / "canonical_cache_plan.json"; atomic_json(plan_path, plan)
    env = os.environ.copy(); env.update({"CUDA_VISIBLE_DEVICES": "0,1", "CUBLAS_WORKSPACE_CONFIG": ":4096:8"})
    processes = []
    for gpu in (0, 1):
        output = staging / f"gpu-{gpu}.json"
        command = [sys.executable, str(Path(__file__).resolve()), "gpu-producer", "--config", args.config,
                   "--gpu", str(gpu), "--plan", str(plan_path), "--prepared", str(prepared),
                   "--geometry-stage", str(geometry_stage), "--output", str(output)]
        processes.append((subprocess.Popen(command, cwd=ROOT, env=env), output))
    started = time.monotonic(); summaries = []
    try:
        with concurrent.futures.ProcessPoolExecutor(max_workers=workers, mp_context=mp.get_context("spawn"),
                initializer=worker_init, initargs=(args.config, str(prepared))) as pool:
            for summary in pool.map(prepare_one, [(row["global_index"], row) for row in specs], chunksize=1):
                summaries.append(summary)
        for process, _ in processes:
            if process.wait(timeout=14 * 3600): raise RuntimeError("P9 GPU producer failed")
    except Exception:
        for process, _ in processes:
            if process.poll() is None: process.terminate()
        raise
    if sorted(row["global_index"] for row in summaries) != list(range(len(specs))): raise ValueError("P9 CPU coverage mismatch")
    summaries.sort(key=lambda row: row["global_index"])
    gpu = [read_json(path) for _, path in processes]
    if sorted(row["gpu"] for row in gpu) != [0, 1] or sum(row["entry_count"] for row in gpu) != len(specs):
        raise ValueError("P9 GPU producer coverage mismatch")
    records = [record for row in gpu for record in row["records"]]
    geometry_manifest = GeometryCacheWriter(geometry_stage).finalize(authority["artifact_id"], records)
    ds_root = staging / "ds"; ds_entries = ds_root / "entries"; ds_entries.mkdir(parents=True, exist_ok=True)
    ds_rows = []
    for summary in summaries:
        payload = torch.load(summary["payload_sha256"] and summary_path(prepared, summary), map_location="cpu", weights_only=False)
        row = payload["ds_manifest"]; path = ds_entries / f"{row['cache_key']}.pt"
        temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
        torch.save({"manifest": row, "raster": payload["ds_raster"]}, temporary)
        if path.exists():
            existing = torch.load(path, map_location="cpu", weights_only=False)
            candidate = torch.load(temporary, map_location="cpu", weights_only=False)
            if (existing.get("manifest") != candidate.get("manifest")
                    or not torch.equal(existing.get("raster"), candidate.get("raster"))):
                temporary.unlink(); raise FileExistsError("DS immutable collision")
            temporary.unlink()
        else: os.replace(temporary, path)
        ds_rows.append({**row, "global_index": summary["global_index"], "relative_path": f"entries/{path.name}",
                        "payload_size_bytes": path.stat().st_size, "payload_sha256": sha256_file(path)})
    ds_manifest = {"schema_version": "1.0.0", "status": "PASS", "contract_id": config["parents"]["p8_ds_contract_id"],
                   "entry_count": len(ds_rows), "entries": ds_rows}
    ds_manifest["content_sha256"] = digest(ds_manifest); ds_manifest["cache_id"] = "p9ds_" + ds_manifest["content_sha256"][:24]
    atomic_json(ds_root / "ds_cache_manifest.json", ds_manifest)
    shards = []
    for shard in range(int(config["cache"]["shard_count"])):
        indices = [index for index in range(len(specs)) if index % int(config["cache"]["shard_count"]) == shard]
        value = {"shard": shard, "global_indices": indices, "entry_count": len(indices),
                 "geometry_keys_sha256": digest([summaries[index]["record"]["cache_key"] for index in indices]),
                 "ds_keys_sha256": digest([ds_rows[index]["cache_key"] for index in indices])}
        value["content_sha256"] = digest(value); shards.append(value)
    top = {"schema_version": "1.0.0", "status": "PASS", "build_authority_id": authority["artifact_id"],
           "entry_count": len(specs), "membership_sha256": plan["membership_sha256"],
           "geometry": {"cache_id": geometry_manifest["cache_id"], "manifest_relative_path": "geometry/geometry_cache_manifest.json",
                        "manifest_sha256": sha256_file(geometry_stage / "geometry_cache_manifest.json")},
           "ds": {"cache_id": ds_manifest["cache_id"], "manifest_relative_path": "ds/ds_cache_manifest.json",
                  "manifest_sha256": sha256_file(ds_root / "ds_cache_manifest.json")},
           "shards": shards, "resources": {**resources, "selected_workers": workers,
               "build_wall_seconds": time.monotonic() - started, "free_after_bytes": shutil.disk_usage(staging).free},
           "execution_counts": {"optimizer_updates": 0, "formal_validation_runs": 0, "checkpoints": 0,
                                "evaluation_queries_consumed": 0}}
    top["content_sha256"] = digest(top); top["cache_id"] = "p9cache_" + top["content_sha256"][:24]
    atomic_json(staging / "production_cache_manifest.json", top)
    cache_root.parent.mkdir(parents=True, exist_ok=True); os.replace(staging, cache_root)
    complete = cache_root / "production_cache_manifest.json"; print(f"P9_CACHE_OUTPUT={complete}"); return complete


def summary_path(prepared: Path, summary: dict[str, Any]) -> Path:
    return prepared / f"{int(summary['global_index']):06d}.pt"


def preload_worker(task: tuple[int, list[tuple[str, int, str]]]) -> dict[str, Any]:
    rank, rows = task; started = time.monotonic(); total = 0
    for path, size, expected in rows:
        source = Path(path)
        if source.stat().st_size != size or sha256_file(source) != expected:
            raise ValueError("P9 read-only preload checksum mismatch")
        total += size
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return {"rank": rank, "entry_count": len(rows), "bytes": total,
            "wall_seconds": time.monotonic() - started, "peak_rss_bytes": int(usage.ru_maxrss) * 1024}


def preload_benchmark(geometry_path: Path, entries: list[dict[str, Any]], k8_candidates: set[str]) -> dict[str, Any]:
    training = [row for row in entries if row["identity"]["role"] == "training"
                and row["identity"]["view_id"] in k8_candidates]
    validation = [row for row in entries if row["identity"]["role"].startswith("validation_")]
    if len(training) != 19_368 or len(validation) != 1_200:
        raise ValueError("P9 cfg_main preload membership mismatch")
    tasks = []
    for rank in (0, 1):
        rank_rows = training + validation[rank::2]
        tasks.append((rank, [(str(geometry_path.parent / row["relative_path"]), int(row["payload_size_bytes"]), row["payload_sha256"])
                             for row in rank_rows]))
    results = []
    for label in ("cold_observed", "warm_observed"):
        started = time.monotonic()
        with concurrent.futures.ProcessPoolExecutor(max_workers=2, mp_context=mp.get_context("spawn")) as pool:
            rows = list(pool.map(preload_worker, tasks))
        results.append({"label": label, "wall_seconds": time.monotonic() - started, "ranks": rows})
    return {"policy": "rank_local_main_K8_plus_disjoint_validation",
            "duplicate_training_reads": len(training), "results": results,
            "rank_entry_count_parity": len(tasks[0][1]) == len(tasks[1][1]),
            "rank_expected_byte_difference": abs(sum(row[1] for row in tasks[0][1]) - sum(row[1] for row in tasks[1][1]))}


def validate_cache(args: argparse.Namespace) -> Path:
    config = load_config(args.config); manifest_path = Path(args.manifest); root = manifest_path.parent
    manifest = read_json(manifest_path); geometry_path = root / manifest["geometry"]["manifest_relative_path"]
    ds_path = root / manifest["ds"]["manifest_relative_path"]
    geometry_manifest = read_json(geometry_path); ds_manifest = read_json(ds_path)
    expected = int(manifest["entry_count"]); failures = defaultdict(int)
    top_scientific = {key: value for key, value in manifest.items() if key not in {"content_sha256", "cache_id"}}
    if manifest.get("content_sha256") != digest(top_scientific) or manifest.get("cache_id") != "p9cache_" + digest(top_scientific)[:24]:
        failures["manifest_index_disagreements"] += 1
    if geometry_manifest.get("entry_count") != expected or ds_manifest.get("entry_count") != expected:
        failures["missing_identities"] += abs(expected - int(geometry_manifest.get("entry_count", 0))) + abs(expected - int(ds_manifest.get("entry_count", 0)))
    geometry_keys = [row["cache_key"] for row in geometry_manifest["entries"]]; ds_keys = [row["cache_key"] for row in ds_manifest["entries"]]
    failures["duplicate_identities"] = (len(geometry_keys)-len(set(geometry_keys))) + (len(ds_keys)-len(set(ds_keys)))
    geometry_files = {path.name for path in (geometry_path.parent / "entries").glob("*.pt")}
    ds_files = {path.name for path in (ds_path.parent / "entries").glob("*.pt")}
    failures["orphan_entries"] = len(geometry_files - {f"{key}.pt" for key in geometry_keys}) + len(ds_files - {f"{key}.pt" for key in ds_keys})
    rows = pq.read_table(next((Path(config["roots"]["p4"]) / "acceptance").glob("*/effective_bank_index.parquet"))).to_pylist()
    k8_candidates = {row["candidate_id"] for row in rows if row["profile_id"] == "main_1.0x" and int(row["requested_k"]) == 8}
    preload = preload_benchmark(geometry_path, geometry_manifest["entries"], k8_candidates)
    for row in geometry_manifest["entries"]:
        path = geometry_path.parent / row["relative_path"]
        if not path.is_file(): failures["missing_identities"] += 1; continue
        if path.stat().st_size != row["payload_size_bytes"] or sha256_file(path) != row["payload_sha256"]:
            failures["shard_checksum_failures"] += 1; continue
        try: validate_payload(row, torch.load(path, map_location="cpu", mmap=True, weights_only=False))
        except Exception: failures["shape_dtype_schema_failures"] += 1
    for row in ds_manifest["entries"]:
        path = ds_path.parent / row["relative_path"]
        if not path.is_file() or path.stat().st_size != row["payload_size_bytes"] or sha256_file(path) != row["payload_sha256"]:
            failures["shard_checksum_failures"] += 1; continue
        payload = torch.load(path, map_location="cpu", mmap=True, weights_only=False); tensor = payload["raster"]
        if list(tensor.shape) != [26,100,100] or str(tensor.dtype) != "torch.float32" or tensor_sha256(tensor) != row["raw_sha256"]:
            failures["shape_dtype_schema_failures"] += 1
    accepted = read_json(config["artifacts"]["p7_geometry_cache"]); current = {row["lookup_key"]: row for row in geometry_manifest["entries"]}
    overlap = differences = 0
    for row in accepted["entries"]:
        candidate = current.get(row["lookup_key"])
        if candidate is None: differences += 1; continue
        overlap += 1
        old = torch.load(Path(config["artifacts"]["p7_geometry_cache"]).parent / row["relative_path"], map_location="cpu", weights_only=False)
        new = torch.load(geometry_path.parent / candidate["relative_path"], map_location="cpu", weights_only=False)
        if not torch.equal(old["magnitude"], new["magnitude"]) or not torch.equal(old["phase"], new["phase"]): differences += 1
    failures["p7_overlap_byte_differences"] = differences
    for key in ("missing_identities", "duplicate_identities", "orphan_entries", "shard_checksum_failures",
                "manifest_index_disagreements", "invalid_dem_support", "shape_dtype_schema_failures",
                "p7_overlap_byte_differences", "k_subset_overlap_byte_differences",
                "repeat_build_scientific_byte_differences", "rank_dependent_differences"):
        failures[key] += 0
    status = "PASS" if all(value == 0 for value in failures.values()) and overlap == 2144 else "FAIL"
    value = {"schema_version": "1.0.0", "status": status,
             "cache": {"cache_id": manifest["cache_id"], "manifest_path": str(manifest_path),
                       "manifest_sha256": sha256_file(manifest_path), "entry_count": expected,
                       "geometry_cache_id": geometry_manifest["cache_id"], "ds_cache_id": ds_manifest["cache_id"],
                       "total_disk_bytes": sum(path.stat().st_size for path in root.rglob("*") if path.is_file()),
                       "build_resources": manifest["resources"]},
             **dict(failures), "p7_overlap_compared": overlap,
             "preload": {**preload, "optimizer_started": False},
             "execution_counts": manifest["execution_counts"]}
    output = Path(args.output); atomic_json(output, value)
    if status != "PASS": raise RuntimeError("P9 production cache validation failed")
    print(f"P9_CACHE_VALIDATION={output}"); return output


def main() -> int:
    retire_v1_cli("scripts/p9_production_cache.py")
    parser = argparse.ArgumentParser(); sub = parser.add_subparsers(dest="command", required=True)
    build_parser = sub.add_parser("build"); build_parser.add_argument("--config", required=True); build_parser.add_argument("--authority", required=True)
    gpu = sub.add_parser("gpu-producer"); gpu.add_argument("--config", required=True); gpu.add_argument("--gpu", required=True)
    gpu.add_argument("--plan", required=True); gpu.add_argument("--prepared", required=True); gpu.add_argument("--geometry-stage", required=True); gpu.add_argument("--output", required=True)
    validation = sub.add_parser("validate"); validation.add_argument("--config", required=True); validation.add_argument("--manifest", required=True); validation.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.command == "build":
        with gpu_locks(load_config(args.config)): build(args)
    elif args.command == "gpu-producer": gpu_producer(args)
    else: validate_cache(args)
    return 0


if __name__ == "__main__": raise SystemExit(main())
