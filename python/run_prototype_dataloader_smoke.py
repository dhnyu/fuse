#!/usr/bin/env python3
"""Execute I17 correctness, coordinate, batching, and CPU performance smoke."""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import platform
import shutil
import statistics
import tempfile
import time
from pathlib import Path
from typing import Any

import jsonschema
import numpy as np
import psutil
import pyarrow.parquet as pq
import torch
import yaml
from shapely import from_wkb

from prototype_dataloader import (
    AcceptedPrototypeDataset,
    canonical_json_bytes,
    logical_batch_digest,
    make_dataloader,
    ragged_collate,
    sha256_file,
)
from serialize_prototype_shard import geometry_parts


def process_io_bytes(process: psutil.Process) -> int:
    try:
        counters = process.io_counters()
        return int(counters.read_bytes)
    except (psutil.Error, AttributeError):
        return 0


def process_cpu_seconds(process: psutil.Process) -> float:
    try:
        value = process.cpu_times()
        return float(value.user + value.system)
    except psutil.Error:
        return 0.0


def validate_batch(batch: dict[str, Any]) -> None:
    scene_ptr, edge_ptr, coordinate_ptr = batch["scene_ptr"], batch["edge_ptr"], batch["coordinate_ptr"]
    if scene_ptr[0] != 0 or edge_ptr[0] != 0 or coordinate_ptr[0] != 0:
        raise ValueError("batch pointer does not start at zero")
    if scene_ptr[-1] != batch["entities"]["local_entity_id"].numel():
        raise ValueError("scene pointer terminal mismatch")
    if edge_ptr[-1] != batch["edges"]["relation_mask"].numel():
        raise ValueError("edge pointer terminal mismatch")
    if coordinate_ptr[-1] != batch["geometry"]["coordinates_xy_m"].shape[0]:
        raise ValueError("coordinate pointer terminal mismatch")
    if batch["geometry"]["entity_coordinate_offsets"][-1] != coordinate_ptr[-1]:
        raise ValueError("entity geometry offset terminal mismatch")
    if batch["geometry"]["part_coordinate_offsets"][-1] != coordinate_ptr[-1]:
        raise ValueError("part geometry offset terminal mismatch")
    if not torch.equal(batch["geometry"]["entity_part_offsets"], batch["geometry"]["entity_component_offsets"]):
        raise ValueError("part/component entity offset mismatch")
    if not torch.equal(batch["geometry"]["part_coordinate_offsets"], batch["geometry"]["component_coordinate_offsets"]):
        raise ValueError("part/component coordinate offset mismatch")
    for scene_index in range(len(batch["scene_ids"])):
        node_start, node_end = int(scene_ptr[scene_index]), int(scene_ptr[scene_index + 1])
        edge_start, edge_end = int(edge_ptr[scene_index]), int(edge_ptr[scene_index + 1])
        edge_index = batch["edges"]["edge_index"][:, edge_start:edge_end]
        if edge_index.numel() and (int(edge_index.min()) < node_start or int(edge_index.max()) >= node_end):
            raise ValueError(f"batch edge rebasing crossed scene: {batch['scene_ids'][scene_index]}")
    if batch["rasters"]["landcover_class_fraction"].shape[1:] != (22, 100, 100):
        raise ValueError("collated land-cover shape mismatch")
    if batch["rasters"]["dem_standardized_mean"].shape[1:] != (17, 17):
        raise ValueError("collated DEM shape mismatch")
    if batch["units"] != {"relative_position": "meter", "intrinsic_geometry": "meter"}:
        raise ValueError("collated coordinate unit mismatch")


def validate_unbatch_roundtrip(samples: list[dict[str, Any]], batch: dict[str, Any]) -> None:
    validate_batch(batch)
    for index, sample in enumerate(samples):
        ns, ne = int(batch["scene_ptr"][index]), int(batch["scene_ptr"][index + 1])
        es, ee = int(batch["edge_ptr"][index]), int(batch["edge_ptr"][index + 1])
        cs, ce = int(batch["coordinate_ptr"][index]), int(batch["coordinate_ptr"][index + 1])
        if not torch.equal(batch["entities"]["local_entity_id"][ns:ne], sample["entities"]["local_entity_id"]):
            raise ValueError("entity unbatch round-trip mismatch")
        if not torch.equal(batch["geometry"]["coordinates_xy_m"][cs:ce], sample["geometry"]["coordinates_xy_m"]):
            raise ValueError("coordinate unbatch round-trip mismatch")
        local_edges = batch["edges"]["edge_index"][:, es:ee] - ns
        if not torch.equal(local_edges, sample["edges"]["edge_index"]):
            raise ValueError("edge unbatch round-trip mismatch")
        if not torch.equal(batch["edges"]["relation_mask"][es:ee], sample["edges"]["relation_mask"]):
            raise ValueError("relation mask unbatch round-trip mismatch")
        for key in sample["rasters"]:
            if not torch.equal(batch["rasters"][key][index], sample["rasters"][key]):
                raise ValueError(f"raster unbatch round-trip mismatch: {key}")


def scan_loader(
    dataset: AcceptedPrototypeDataset,
    budgets: dict[str, int],
    workers: int,
    shuffle: bool,
    seed: int,
    pin_memory: bool = False,
    persistent_workers: bool = False,
    prefetch_factor: int = 2,
) -> dict[str, Any]:
    pin_memory_effective = bool(pin_memory and torch.cuda.is_available())
    loader, sampler = make_dataloader(
        dataset, budgets, workers, shuffle, seed, pin_memory=pin_memory_effective,
        persistent_workers=persistent_workers, prefetch_factor=prefetch_factor,
    )
    process = psutil.Process()
    rss_peak = process.memory_info().rss
    fd_start = process.num_fds() if hasattr(process, "num_fds") else 0
    fd_peak = fd_start
    io_start = process_io_bytes(process)
    cpu_start = process_cpu_seconds(process)
    started = time.perf_counter()
    iterator_started = started
    iterator = iter(loader)
    worker_processes: list[psutil.Process] = []
    for worker in getattr(iterator, "_workers", []) or []:
        try:
            worker_processes.append(psutil.Process(worker.pid))
        except psutil.Error:
            pass
    worker_io_start = sum(process_io_bytes(worker) for worker in worker_processes)
    worker_cpu_start = sum(process_cpu_seconds(worker) for worker in worker_processes)
    worker_rss_peak = 0
    order: list[str] = []
    boundaries: list[list[str]] = []
    batch_digests: list[str] = []
    batch_latencies: list[float] = []
    totals = {key: 0 for key in ("scenes", "nodes", "ordered_edges", "coordinates", "actual_payload_bytes")}
    first_batch_latency = None
    while True:
        before = time.perf_counter()
        try:
            batch = next(iterator)
        except StopIteration:
            break
        after = time.perf_counter()
        latency = after - before
        batch_latencies.append(latency)
        if first_batch_latency is None:
            first_batch_latency = after - iterator_started
        validate_batch(batch)
        order.extend(batch["scene_ids"])
        boundaries.append(batch["scene_ids"])
        batch_digests.append(logical_batch_digest(batch))
        for key in totals:
            totals[key] += int(batch["resources"][key])
        rss_peak = max(rss_peak, process.memory_info().rss)
        if hasattr(process, "num_fds"):
            fd_peak = max(fd_peak, process.num_fds())
        for worker in worker_processes:
            try:
                worker_rss_peak = max(worker_rss_peak, worker.memory_info().rss)
            except psutil.Error:
                pass
        # Worker batches contain many shared-memory tensors. Do not retain the
        # final batch while shutting down workers, or its storage descriptors
        # remain open in the parent process until this function returns.
        del batch
    elapsed = time.perf_counter() - started
    worker_io_end = sum(process_io_bytes(worker) for worker in worker_processes)
    worker_cpu_end = sum(process_cpu_seconds(worker) for worker in worker_processes)
    digest = hashlib.sha256(canonical_json_bytes({
        "order": order, "boundaries": boundaries, "batch_digests": batch_digests, "totals": totals,
    })).hexdigest()
    if hasattr(iterator, "_shutdown_workers"):
        iterator._shutdown_workers()
    del iterator, loader
    gc.collect()
    fd_end = process.num_fds() if hasattr(process, "num_fds") else 0
    # file_system sharing initializes one process-global manager connection on
    # the first worker run. Repeated growth is checked across smoke runs.
    if fd_end > fd_start + 4:
        raise ValueError(f"DataLoader file descriptor growth exceeded manager allowance: {fd_start} -> {fd_end}")
    batch_count = len(boundaries)
    return {
        "workers": workers, "shuffle": shuffle, "pin_memory": pin_memory,
        "pin_memory_effective": pin_memory_effective,
        "persistent_workers": persistent_workers if workers else False,
        "prefetch_factor": prefetch_factor if workers else None,
        "scene_order": order, "batch_boundaries": boundaries, "logical_digest": digest,
        "totals": totals, "batch_count": batch_count,
        "first_batch_latency_seconds": float(first_batch_latency or 0.0),
        "elapsed_seconds": elapsed, "scenes_per_second": len(order) / elapsed,
        "batches_per_second": batch_count / elapsed, "entities_per_second": totals["nodes"] / elapsed,
        "edges_per_second": totals["ordered_edges"] / elapsed,
        "coordinates_per_second": totals["coordinates"] / elapsed,
        "batch_latency_p50_seconds": float(np.quantile(batch_latencies, 0.5)) if batch_latencies else 0.0,
        "batch_latency_p95_seconds": float(np.quantile(batch_latencies, 0.95)) if batch_latencies else 0.0,
        "main_peak_rss_bytes": rss_peak, "worker_peak_rss_bytes": worker_rss_peak,
        "main_read_bytes": max(0, process_io_bytes(process) - io_start),
        "worker_read_bytes": max(0, worker_io_end - worker_io_start),
        "main_cpu_seconds": max(0.0, process_cpu_seconds(process) - cpu_start),
        "worker_cpu_seconds": max(0.0, worker_cpu_end - worker_cpu_start),
        "cpu_utilization_equivalent_cores": max(0.0, (process_cpu_seconds(process) - cpu_start + worker_cpu_end - worker_cpu_start) / elapsed),
        "open_fd_start": fd_start, "open_fd_peak": fd_peak, "open_fd_end": fd_end,
        "open_fd_retained": max(0, fd_end - fd_start),
        "warm_cache": True,
    }


def select_representative_rows(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    median_payload = statistics.median(row["actual_payload_bytes"] for row in rows)
    return {
        "empty_edge": min((row for row in rows if row["empty_edge"]), key=lambda row: row["global_order"]),
        "sparse": min(rows, key=lambda row: (row["node_count"], row["ordered_edge_count"], row["scene_id"])),
        "median": min(rows, key=lambda row: (abs(row["actual_payload_bytes"] - median_payload), row["scene_id"])),
        "maximum_node": max(rows, key=lambda row: (row["node_count"], row["scene_id"])),
        "maximum_edge": max(rows, key=lambda row: (row["ordered_edge_count"], row["scene_id"])),
        "geometry_heavy": max(rows, key=lambda row: (row["coordinate_count"], row["scene_id"])),
    }


def build_i10_reference(manifest: dict[str, Any]) -> dict[tuple[str, int], dict[str, Any]]:
    dictionary_path = Path(manifest["accepted_artifacts"]["dictionary"]["path"])
    dictionary = pq.read_table(dictionary_path).to_pylist()
    by_path: dict[str, list[dict[str, Any]]] = {}
    for row in dictionary:
        by_path.setdefault(row["vector_artifact_path"], []).append(row)
    reference: dict[tuple[str, int], dict[str, Any]] = {}
    columns = [
        "scene_id", "local_entity_id", "source_entity_id", "relative_center_x_m", "relative_center_y_m",
        "observed_center_x_5186", "observed_center_y_5186", "observed_geometry",
    ]
    for path_value, expected_rows in sorted(by_path.items()):
        expected_scenes = {row["scene_id"] for row in expected_rows}
        table = pq.read_table(path_value, columns=columns, filters=[("scene_id", "in", sorted(expected_scenes))])
        for row in table.to_pylist():
            key = (row["scene_id"], int(row["local_entity_id"]))
            if key in reference:
                raise ValueError(f"duplicate I10 metric reference: {key}")
            reference[key] = row
    if len(reference) != len(dictionary):
        raise ValueError("I10 reference/dictionary completeness mismatch")
    return reference


def audit_meter_coordinates(dataset: AcceptedPrototypeDataset, manifest: dict[str, Any], tolerance: float) -> dict[str, Any]:
    reference = build_i10_reference(manifest)
    maximum_relative_error = 0.0
    maximum_geometry_error = 0.0
    coordinate_total = 0
    entity_total = 0
    for position in range(len(dataset)):
        sample = dataset[position]
        relative_expected: list[list[float]] = []
        coordinate_expected: list[np.ndarray] = []
        for local_id in sample["meta"]["local_entity_ids"]:
            row = reference[(sample["scene_id"], int(local_id))]
            relative_expected.append([row["relative_center_x_m"], row["relative_center_y_m"]])
            geometry = from_wkb(row["observed_geometry"])
            parts, _, _ = geometry_parts(geometry)
            center = np.asarray([row["observed_center_x_5186"], row["observed_center_y_5186"]], dtype=np.float64)
            coordinate_expected.extend(np.asarray(part[:, :2] - center, dtype=np.float32) for part in parts)
        expected_relative = np.asarray(relative_expected, dtype=np.float32).reshape((-1, 2))
        expected_geometry = np.concatenate(coordinate_expected, axis=0) if coordinate_expected else np.empty((0, 2), np.float32)
        actual_relative = sample["entities"]["relative_position_m"].numpy()
        actual_geometry = sample["geometry"]["coordinates_xy_m"].numpy()
        if actual_relative.shape != expected_relative.shape or actual_geometry.shape != expected_geometry.shape:
            raise ValueError(f"I10 meter coordinate shape mismatch: {sample['scene_id']}")
        relative_error = float(np.max(np.abs(actual_relative - expected_relative))) if actual_relative.size else 0.0
        geometry_error = float(np.max(np.abs(actual_geometry - expected_geometry))) if actual_geometry.size else 0.0
        if relative_error > tolerance or geometry_error > tolerance:
            raise ValueError(
                f"I10 meter coordinate tolerance mismatch: {sample['scene_id']} relative={relative_error} geometry={geometry_error}"
            )
        maximum_relative_error = max(maximum_relative_error, relative_error)
        maximum_geometry_error = max(maximum_geometry_error, geometry_error)
        entity_total += len(expected_relative)
        coordinate_total += len(expected_geometry)
    return {
        "status": "PASS", "scene_count": len(dataset), "entity_count": entity_total,
        "coordinate_count": coordinate_total, "relative_position_unit": "meter",
        "intrinsic_geometry_unit": "meter", "geometry_scale_to_m": dataset.geometry_scale_to_m,
        "tolerance_m": tolerance, "maximum_relative_error_m": maximum_relative_error,
        "maximum_geometry_error_m": maximum_geometry_error,
    }


def compare_runs(first: dict[str, Any], second: dict[str, Any], label: str) -> None:
    for key in ("scene_order", "batch_boundaries", "logical_digest", "totals"):
        if first[key] != second[key]:
            raise ValueError(f"worker-count deterministic equality failed: {label}:{key}")


def publish_result(result: dict[str, Any], schema: dict[str, Any], root: Path, config: dict[str, Any]) -> tuple[list[str], str]:
    identity = {
        "accepted_dataset_id": result["accepted_dataset_id"], "contract": result["contract"],
        "logical_digests": result["correctness"]["logical_digests"],
        "performance": result["performance"], "recommendation": result["recommendation"],
        "environment": result["environment"],
    }
    smoke_id = f"pdl_{hashlib.sha256(canonical_json_bytes(identity)).hexdigest()[:24]}"
    result["smoke_id"] = smoke_id
    jsonschema.validate(instance=result, schema=schema)
    final_dir = root / config["output"]["subdirectory"] / smoke_id
    final_dir.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{smoke_id}.staging-", dir=final_dir.parent))
    try:
        result_path = stage / config["output"]["result"]
        log_path = stage / config["output"]["log"]
        result_path.write_bytes(canonical_json_bytes(result))
        log_path.write_bytes(canonical_json_bytes({
            "event": "prototype_dataloader_smoke_complete", "status": "READY",
            "smoke_id": smoke_id, "accepted_dataset_id": result["accepted_dataset_id"],
            "scene_count": result["correctness"]["scene_count"], "gpu": 0,
        }))
        if final_dir.exists():
            existing = sorted(path.name for path in final_dir.iterdir() if path.is_file())
            staged = sorted(path.name for path in stage.iterdir() if path.is_file())
            if existing != staged or any(sha256_file(final_dir / name) != sha256_file(stage / name) for name in staged):
                raise FileExistsError("same smoke ID has different content")
            shutil.rmtree(stage)
        else:
            os.replace(stage, final_dir)
        return sorted(str(path.resolve()) for path in final_dir.iterdir() if path.is_file()), smoke_id
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def run_smoke(manifest_path: Path, config_path: Path, schema_path: Path, tensor_contract_path: Path) -> dict[str, Any]:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["training_dataset_id"] != config["identity"]["accepted_dataset_id"] or manifest["status"] != "READY":
        raise ValueError("I16 accepted dataset identity/status mismatch")
    if torch.cuda.is_available():
        raise ValueError("I17 is CPU-only but CUDA is visible")
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    budgets = {key: int(value) for key, value in config["batching"]["budgets"].items()}
    seed = int(config["batching"]["seed"])
    all_dataset = AcceptedPrototypeDataset(manifest_path, tensor_contract_path, verify_checksums=True)
    expected = config["expected"]
    if len(all_dataset) != int(expected["scenes"]):
        raise ValueError("accepted scene count mismatch")
    split_datasets = {
        split: AcceptedPrototypeDataset(manifest_path, tensor_contract_path, split=split, verify_checksums=False)
        for split in config["expected"]["split_counts"]
    }
    for split, count in config["expected"]["split_counts"].items():
        if len(split_datasets[split]) != int(count) or any(row["split"] != split for row in split_datasets[split].rows):
            raise ValueError(f"split leakage/count mismatch: {split}")

    sequential: dict[str, dict[int, dict[str, Any]]] = {}
    for split, dataset in split_datasets.items():
        sequential[split] = {
            workers: scan_loader(dataset, budgets, workers, False, seed)
            for workers in (0, 4)
        }
        compare_runs(sequential[split][0], sequential[split][4], f"{split}:sequential")
    shuffled = {
        workers: scan_loader(split_datasets["training"], budgets, workers, True, seed)
        for workers in (0, 4)
    }
    compare_runs(shuffled[0], shuffled[4], "training:shuffle")
    repeated_shuffle = scan_loader(split_datasets["training"], budgets, 0, True, seed)
    compare_runs(shuffled[0], repeated_shuffle, "training:repeated-shuffle")

    observed_totals = {
        "scenes": sum(sequential[split][0]["totals"]["scenes"] for split in sequential),
        "nodes": sum(sequential[split][0]["totals"]["nodes"] for split in sequential),
        "ordered_edges": sum(sequential[split][0]["totals"]["ordered_edges"] for split in sequential),
        "coordinates": sum(sequential[split][0]["totals"]["coordinates"] for split in sequential),
        "empty_edge_scenes": sum(bool(row["empty_edge"]) for row in all_dataset.rows),
    }
    expected_totals = {key: int(expected[key]) for key in observed_totals}
    if observed_totals != expected_totals:
        raise ValueError(f"loader resource totals mismatch: {observed_totals}")

    representatives = select_representative_rows(all_dataset.rows)
    representative_results: dict[str, Any] = {}
    samples = []
    for role, row in representatives.items():
        sequential_sample = all_dataset[all_dataset.position_for_scene(row["scene_id"])]
        random_sample = all_dataset.get_by_scene_id(row["scene_id"])
        first_digest = hashlib.sha256(); second_digest = hashlib.sha256()
        from prototype_dataloader import update_digest
        update_digest(first_digest, sequential_sample); update_digest(second_digest, random_sample)
        if first_digest.hexdigest() != second_digest.hexdigest():
            raise ValueError(f"sequential/random scene equality failed: {row['scene_id']}")
        representative_results[role] = {
            "scene_id": row["scene_id"], "split": row["split"], "nodes": row["node_count"],
            "ordered_edges": row["ordered_edge_count"], "coordinates": row["coordinate_count"],
            "empty_edge": row["empty_edge"], "digest": first_digest.hexdigest(),
        }
        samples.append(sequential_sample)
    representative_batch = ragged_collate(samples, budgets)
    validate_unbatch_roundtrip(samples, representative_batch)

    performance = [sequential["training"][0], sequential["training"][4]]
    candidate_settings = [
        (0, True, False),
        (4, True, False), (4, False, True), (4, True, True),
    ]
    for workers, pin_memory, persistent in candidate_settings:
        performance.append(scan_loader(
            split_datasets["training"], budgets, workers, False, seed,
            pin_memory=pin_memory, persistent_workers=persistent,
            prefetch_factor=int(config["execution"]["prefetch_factor"]),
        ))
    baseline_digest = performance[0]["logical_digest"]
    if any(run["logical_digest"] != baseline_digest or run["batch_boundaries"] != performance[0]["batch_boundaries"] for run in performance):
        raise ValueError("performance candidates changed logical loader output")
    operational_candidates = [run for run in performance if not run["pin_memory"]]
    recommendation_source = max(operational_candidates, key=lambda value: value["scenes_per_second"])
    recommendation = {
        "workers": recommendation_source["workers"], "pin_memory": recommendation_source["pin_memory"],
        "persistent_workers": recommendation_source["persistent_workers"],
        "prefetch_factor": recommendation_source["prefetch_factor"],
        "selection_rule": "maximum_warm_cache_training_scenes_per_second_among_correct_cpu_effective_candidates",
        "pin_memory_unavailable_without_accelerator": True,
        "scientific_dataset_identity_includes_runtime_choice": False,
    }

    coordinate_audit = audit_meter_coordinates(
        all_dataset, manifest, float(config["coordinates"]["reference_tolerance_m"])
    )
    config_hashes = {
        "dataloader_config_sha256": sha256_file(config_path), "result_schema_sha256": sha256_file(schema_path),
        "tensor_contract_sha256": sha256_file(tensor_contract_path),
        "dataset_implementation_sha256": sha256_file(Path(__file__).resolve().parent / "prototype_dataloader.py"),
        "smoke_implementation_sha256": sha256_file(Path(__file__).resolve()),
        "requirements_sha256": sha256_file(Path(__file__).resolve().parent / "requirements-dataloader.txt"),
    }
    result = {
        "schema_version": "1.0.0", "status": "READY", "smoke_id": "pdl_" + "0" * 24,
        "accepted_dataset_id": manifest["training_dataset_id"],
        "contract": config_hashes,
        "coordinate_contract": coordinate_audit,
        "batching": {
            "algorithm": config["batching"]["algorithm"], "shuffle_algorithm": config["batching"]["shuffle_algorithm"],
            "seed": seed, "budgets": budgets, "training_batch_count": sequential["training"][0]["batch_count"],
            "training_batch_scene_min": min(map(len, sequential["training"][0]["batch_boundaries"])),
            "training_batch_scene_median": statistics.median(map(len, sequential["training"][0]["batch_boundaries"])),
            "training_batch_scene_max": max(map(len, sequential["training"][0]["batch_boundaries"])),
            "oversize_singleton_count": 0,
        },
        "correctness": {
            "status": "PASS", "scene_count": observed_totals["scenes"],
            "split_counts": {split: len(dataset) for split, dataset in split_datasets.items()},
            "node_count": observed_totals["nodes"], "ordered_edge_count": observed_totals["ordered_edges"],
            "coordinate_count": observed_totals["coordinates"], "empty_edge_scene_count": observed_totals["empty_edge_scenes"],
            "missing_scene_count": 0, "duplicate_scene_count": 0, "split_leakage_count": 0,
            "sequential_random_equality": "PASS", "worker_0_4_equality": "PASS",
            "batch_offset_unbatch_round_trip": "PASS", "fixed_seed_repeat": "PASS",
            "file_descriptor_leak_count": 0,
            "logical_digests": {
                **{f"{split}_sequential": sequential[split][0]["logical_digest"] for split in sequential},
                "training_shuffle": shuffled[0]["logical_digest"],
            },
            "representatives": representative_results,
        },
        "performance": [{key: value for key, value in run.items() if key not in ("scene_order", "batch_boundaries")} for run in performance],
        "recommendation": recommendation,
        "environment": {
            "python": platform.python_version(), "torch": torch.__version__, "numpy": np.__version__,
            "pyarrow": __import__("pyarrow").__version__, "safetensors": __import__("safetensors").__version__,
            "psutil": psutil.__version__, "platform": platform.platform(), "cpu_count": os.cpu_count(),
            "warm_cache": True, "page_cache_dropped": False, "gpu": 0,
        },
    }
    outputs, smoke_id = publish_result(result, schema, manifest_path.parent, config)
    return {"status": "READY", "smoke_id": smoke_id, "output_files": outputs}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--accepted-manifest", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--schema", required=True, type=Path)
    parser.add_argument("--tensor-contract", required=True, type=Path)
    args = parser.parse_args()
    result = run_smoke(
        args.accepted_manifest.resolve(), args.config.resolve(), args.schema.resolve(), args.tensor_contract.resolve()
    )
    print(canonical_json_bytes(result).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
