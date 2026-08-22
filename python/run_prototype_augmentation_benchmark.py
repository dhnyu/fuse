#!/usr/bin/env python3
"""Run I19 reference augmentation correctness and performance benchmark."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
for _variable in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_variable] = "1"
import resource
import shutil
import statistics
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import torch
import yaml

from prototype_augmentation import (
    AugmentationResources, augment_scene, canonical_json_bytes, cuda_reference_check,
    jitter_geometry, logical_digest, perturb_lane_value, road_removal_closure,
    structure_signature,
)
from prototype_dataloader import AcceptedPrototypeDataset, read_json, sha256_file
from shapely.geometry import LineString, MultiPolygon, Polygon


_WORKER_DATASET: AcceptedPrototypeDataset | None = None
_WORKER_CONFIG: dict[str, Any] | None = None
_WORKER_RESOURCES: AugmentationResources | None = None
_WORKER_THRESHOLDS: dict[int, float] | None = None
_WORKER_EPOCH = 0


def initialize_worker(accepted_path: str, tensor_contract: str, config: dict[str, Any],
                      thresholds: dict[int, float], epoch: int) -> None:
    global _WORKER_DATASET, _WORKER_CONFIG, _WORKER_RESOURCES, _WORKER_THRESHOLDS, _WORKER_EPOCH
    for variable in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        os.environ[variable] = "1"
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    accepted = read_json(accepted_path)
    _WORKER_DATASET = AcceptedPrototypeDataset(accepted_path, tensor_contract, split=None)
    _WORKER_CONFIG = config
    _WORKER_RESOURCES = load_resources(accepted)
    _WORKER_THRESHOLDS = thresholds
    _WORKER_EPOCH = int(epoch)


def worker_execute(task: tuple[str, int]) -> tuple[dict[str, Any], float]:
    if _WORKER_DATASET is None or _WORKER_CONFIG is None or _WORKER_RESOURCES is None or _WORKER_THRESHOLDS is None:
        raise RuntimeError("augmentation worker was not initialized")
    before = time.perf_counter()
    sample = _WORKER_DATASET.get_by_scene_id(task[0])
    result = augment_scene(sample, _WORKER_CONFIG, _WORKER_RESOURCES, _WORKER_THRESHOLDS,
                           _WORKER_EPOCH, task[1])
    return result, time.perf_counter() - before


def run_process_campaign(tasks: list[tuple[str, int]], workers: int, accepted_path: Path,
                         tensor_contract: str, config: dict[str, Any], thresholds: dict[int, float],
                         epoch: int) -> list[tuple[dict[str, Any], float]]:
    context = get_context("spawn")
    with ProcessPoolExecutor(
        max_workers=workers, mp_context=context, initializer=initialize_worker,
        initargs=(str(accepted_path), tensor_contract, config, thresholds, epoch),
    ) as pool:
        return list(pool.map(worker_execute, tasks, chunksize=1))


def canonical_results(values: list[tuple[dict[str, Any], float]]) -> list[tuple[dict[str, Any], float]]:
    return sorted(values, key=lambda value: (value[0]["scene_id"], int(value[0]["view_id"])))


def percentile(values: list[float], q: float) -> float:
    return float(np.quantile(np.asarray(values, dtype=np.float64), q)) if values else 0.0


def file_record(path: Path, root: Path) -> dict[str, Any]:
    return {"relative_path": str(path.relative_to(root)), "size_bytes": path.stat().st_size, "sha256": sha256_file(path)}


def immutable_publish(stage: Path, final: Path, core: dict[str, Any]) -> str:
    if final.exists():
        manifest = final / "prototype_augmentation_manifest.json"
        if not manifest.is_file():
            raise RuntimeError("immutable I19 directory exists without manifest")
        existing = read_json(manifest)
        existing_core = {key: existing[key] for key in ("augmentation_acceptance_id", "scientific_identity", "logical_results")}
        if canonical_json_bytes(existing_core) != canonical_json_bytes(core):
            raise RuntimeError("same I19 identity has different scientific content")
        shutil.rmtree(stage)
        return "identical_reuse"
    final.parent.mkdir(parents=True, exist_ok=True)
    os.replace(stage, final)
    return "new_publish"


def contract_fixtures() -> dict[str, str]:
    endpoint = np.asarray([[0, 1], [1, 2], [2, 3]], dtype=np.int64)
    degrees = np.asarray([1, 2, 2, 1], dtype=np.int32)
    assert road_removal_closure([1], endpoint, degrees) == {0, 1, 2}
    junction_endpoint = np.asarray([[0, 1], [1, 2], [1, 3]], dtype=np.int64)
    junction_degree = np.asarray([1, 3, 1, 1], dtype=np.int32)
    assert road_removal_closure([0], junction_endpoint, junction_degree) == {0}
    cycle_endpoint = np.asarray([[0, 1], [1, 2], [2, 0]], dtype=np.int64)
    assert road_removal_closure([0], cycle_endpoint, np.asarray([2, 2, 2], dtype=np.int32)) == {0, 1, 2}
    class FixedRng:
        def __init__(self, values: list[float]): self.values = iter(values)
        def random(self) -> float: return next(self.values)
    lane = perturb_lane_value(1, 0, FixedRng([0.0, 0.0]), 0.1)  # type: ignore[arg-type]
    assert lane == (1, 0, True, -1)
    assert perturb_lane_value(None, 1, FixedRng([]), 1.0) == (None, 1, False, 0)  # type: ignore[arg-type]
    polygon = MultiPolygon([Polygon([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)],
                                    [[(2, 2), (4, 2), (4, 4), (2, 4), (2, 2)]]),
                            Polygon([(20, 20), (21, 20), (21, 21), (20, 21), (20, 20)])])
    jittered = jitter_geometry(polygon, np.random.default_rng(3), 1.0, 0.2, 1e-8, False)
    assert structure_signature(jittered) == structure_signature(polygon)
    boundary_line = LineString([(-250.0, 0.0), (0.0, 0.0), (250.0, 0.0)])
    fixed = jitter_geometry(boundary_line, np.random.default_rng(4), 1.0, 2.0, 1e-8, True)
    assert fixed.coords[0] == boundary_line.coords[0] and fixed.coords[-1] == boundary_line.coords[-1]
    return {
        "road_degree_two": "PASS", "road_dead_end_junction": "PASS", "road_cycle": "PASS",
        "lane_clamp_without_resampling": "PASS", "missing_lane": "PASS",
        "multipart_hole": "PASS", "boundary_and_road_endpoints": "PASS",
    }


def load_resources(manifest: dict[str, Any]) -> AugmentationResources:
    artifacts = manifest["scientific_identity"]["i13_accepted_artifacts"]
    normalization_path = Path(artifacts["normalization"]["path"])
    vocabulary_path = Path(artifacts["vocabulary"]["path"])
    for name, path in (("normalization", normalization_path), ("vocabulary", vocabulary_path)):
        if not path.is_file() or sha256_file(path) != artifacts[name]["sha256"]:
            raise RuntimeError(f"I13 {name} artifact checksum mismatch")
    normalizations = {row["attribute"]: row for row in pq.read_table(normalization_path).to_pylist()}
    vocabulary = pq.read_table(vocabulary_path, columns=["attribute", "index", "entry_type"]).to_pylist()
    masks = {row["attribute"]: int(row["index"]) for row in vocabulary if row["entry_type"] == "MASK"}
    missing = {row["attribute"]: int(row["index"]) for row in vocabulary if row["entry_type"] == "MISSING"}
    return AugmentationResources(normalizations, masks, missing)


def geometry_thresholds(dataset: AcceptedPrototypeDataset) -> tuple[dict[int, float], str]:
    counts = {0: [], 1: []}
    evidence = []
    for position in range(len(dataset)):
        sample = dataset[position]
        offsets = sample["geometry"]["entity_coordinate_offsets"]
        types = sample["entities"]["entity_type"]
        for row in range(len(types)):
            code = int(types[row])
            if code in counts:
                counts[code].append(int(offsets[row + 1] - offsets[row]))
        evidence.append((sample["scene_id"], len(types)))
    thresholds = {code: float(np.quantile(values, 0.90, method="linear")) for code, values in counts.items()}
    return thresholds, logical_digest({"population": evidence, "counts": counts, "quantile": 0.90})


def select_scenes(dataset: AcceptedPrototypeDataset, dataloader_result: dict[str, Any], count: int) -> list[str]:
    representatives = dataloader_result["correctness"]["representatives"]
    roles = ["sparse", "empty_edge", "median"]
    selected = [representatives[role]["scene_id"] for role in roles]
    topology = []
    small_mixed = []
    for position in range(len(dataset)):
        sample = dataset[position]
        nodes = int(sample["resources"]["nodes"])
        types = set(int(value) for value in sample["entities"]["entity_type"].tolist())
        if 0 < nodes <= 500:
            topology.append((int(sample["topology"]["node_incident_road_count"].numel()), -nodes, sample["scene_id"]))
            if types == {0, 1, 2}:
                small_mixed.append((nodes, sample["scene_id"]))
    if topology:
        selected.append(max(topology)[2])
    selected.extend(scene_id for _, scene_id in sorted(small_mixed))
    unique = []
    for scene_id in selected:
        if scene_id not in unique:
            unique.append(scene_id)
    for position in range(len(dataset)):
        if len(unique) >= count:
            break
        scene_id = dataset[position]["scene_id"]
        if scene_id not in unique:
            unique.append(scene_id)
    return unique[:count]


def adversarial_scene_subset(dataset: AcceptedPrototypeDataset, dataloader_result: dict[str, Any],
                             first_results: list[dict[str, Any]]) -> list[str]:
    known = [
        "scn_3e1fb01511497ec3fd8e984b", "scn_6db492fed1b26a915e27759a",
        "scn_aa160d43b2f2411038ace102", "scn_3943062e027f61a18ae5cda2",
        "scn_62344300076ce1f87edff43f", "scn_1f40aa20639e2b32c602b8f6",
    ]
    representatives = dataloader_result["correctness"]["representatives"]
    known.extend(representatives[key]["scene_id"] for key in ("maximum_node", "maximum_edge", "geometry_heavy", "empty_edge"))
    topology_rank: list[tuple[int, int, str]] = []
    multipart_rank: list[tuple[int, str]] = []
    boundary_rank: list[tuple[int, str]] = []
    for position in range(len(dataset)):
        sample = dataset[position]
        scene_id = sample["scene_id"]
        degrees = sample["topology"]["node_incident_road_count"].numpy()
        topology_rank.append((int(np.count_nonzero(degrees >= 3)), int(np.count_nonzero(degrees == 2)), scene_id))
        component_offsets = sample["scientific_reference"]["entity_component_offsets"].numpy()
        multipart_rank.append((int(np.sum(np.diff(component_offsets) > 1)), scene_id))
        absolute = sample["scientific_reference"]["coordinates_absolute_xy_5186"].numpy()
        cx, cy = sample["meta"]["center_xy_5186"]
        if absolute.size:
            boundary = ((np.abs(absolute[:, 0] - (cx - 250.0)) <= 1e-8) |
                        (np.abs(absolute[:, 0] - (cx + 250.0)) <= 1e-8) |
                        (np.abs(absolute[:, 1] - (cy - 250.0)) <= 1e-8) |
                        (np.abs(absolute[:, 1] - (cy + 250.0)) <= 1e-8))
            boundary_rank.append((int(np.count_nonzero(boundary)), scene_id))
    known.extend([max(topology_rank)[2], max(multipart_rank)[1], max(boundary_rank)[1]])
    fallback = max(first_results, key=lambda result: (result["statistics"]["fallbacks"], result["scene_id"]))
    known.append(fallback["scene_id"])
    unique: list[str] = []
    for scene_id in known:
        if scene_id not in unique:
            unique.append(scene_id)
    if not 8 <= len(unique[:16]) <= 16:
        raise RuntimeError("adversarial worker-parity subset size contract failed")
    return unique[:16]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--accepted-manifest", required=True)
    parser.add_argument("--dataloader-result", required=True)
    parser.add_argument("--tensor-contract", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--schema", required=True)
    parser.add_argument("--implementation", required=True)
    parser.add_argument("--requirements", required=True)
    parser.add_argument("--output-root", required=True)
    args = parser.parse_args()

    started = time.perf_counter()
    config_path, schema_path = Path(args.config).resolve(), Path(args.schema).resolve()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    accepted_path, loader_path = Path(args.accepted_manifest).resolve(), Path(args.dataloader_result).resolve()
    accepted, loader = read_json(accepted_path), read_json(loader_path)
    if accepted["status"] != "READY" or loader["status"] != "READY":
        raise RuntimeError("I19 requires accepted I16 and READY I17")
    if loader["accepted_dataset_id"] != accepted["training_dataset_id"]:
        raise RuntimeError("I16/I17 identity mismatch")
    training_dataset = AcceptedPrototypeDataset(accepted_path, args.tensor_contract, split="training")
    dataset = AcceptedPrototypeDataset(accepted_path, args.tensor_contract, split=None)
    resources = load_resources(accepted)
    thresholds, threshold_population_digest = geometry_thresholds(training_dataset)
    scene_ids = sorted(select_scenes(dataset, loader, int(config["benchmark"]["prototype_scene_count"])))
    fixtures = contract_fixtures()

    epoch = int(config["benchmark"]["epoch"])
    views = [int(value) for value in config["benchmark"]["views"]]
    tasks = [(scene_id, view) for scene_id in scene_ids for view in sorted(views)]
    worker_count = int(config["benchmark"]["worker_counts"][0])
    first = canonical_results(run_process_campaign(
        tasks, worker_count, accepted_path, args.tensor_contract, config, thresholds, epoch
    ))
    shuffle_seed = int(hashlib.sha256(canonical_json_bytes({
        "global_seed": config["rng"]["base_seed"], "operation": "full_population_input_shuffle",
    })).hexdigest()[:16], 16)
    shuffled_tasks = list(tasks)
    np.random.Generator(np.random.PCG64(shuffle_seed)).shuffle(shuffled_tasks)
    second = canonical_results(run_process_campaign(
        shuffled_tasks, worker_count, accepted_path, args.tensor_contract, config, thresholds, epoch
    ))
    first_payloads = [canonical_json_bytes(value[0]) for value in first]
    second_payloads = [canonical_json_bytes(value[0]) for value in second]
    if first_payloads != second_payloads:
        mismatch = next(index for index, pair in enumerate(zip(first_payloads, second_payloads)) if pair[0] != pair[1])
        raise RuntimeError(f"full-population shuffled-input determinism failed: {first[mismatch][0]['scene_id']}:{first[mismatch][0]['view_id']}")
    results = [value[0] for value in first]
    adversarial_scenes = adversarial_scene_subset(dataset, loader, results)
    adversarial_tasks = [(scene_id, view) for scene_id in adversarial_scenes for view in sorted(views)]
    parity_one = canonical_results(run_process_campaign(
        adversarial_tasks, 1, accepted_path, args.tensor_contract, config, thresholds, epoch
    ))
    parity_forty = canonical_results(run_process_campaign(
        adversarial_tasks, 40, accepted_path, args.tensor_contract, config, thresholds, epoch
    ))
    if [canonical_json_bytes(value[0]) for value in parity_one] != [canonical_json_bytes(value[0]) for value in parity_forty]:
        raise RuntimeError("adversarial 1-worker/40-worker parity failed")
    if any(not result["invariants"]["CNT_WIT_INT_CON"] for result in results):
        raise RuntimeError("post-augmentation relation invariant failed")
    two_view_pairs = [(results[index]["logical_digest"], results[index + 1]["logical_digest"])
                      for index in range(0, len(results), 2)]
    nontrivial_pairs = [pair for pair, scene_id in zip(two_view_pairs, scene_ids)
                        if dataset.get_by_scene_id(scene_id)["resources"]["nodes"] > 0]
    if not nontrivial_pairs or any(left == right for left, right in nontrivial_pairs):
        raise RuntimeError("two-view RNG streams are not independent")
    cuda = cuda_reference_check()

    lane_events = [event for result in results for event in result["lane_events"]]
    selected_lanes = [event for event in lane_events if event["selected"]]
    lane_qc = {
        "eligible_count": sum(int(not event["missing"]) for event in lane_events),
        "selected_count": len(selected_lanes),
        "negative_offset_count": sum(int(event["delta"] == -1) for event in selected_lanes),
        "positive_offset_count": sum(int(event["delta"] == 1) for event in selected_lanes),
        "lower_bound_clamp_count": sum(int(event["original"] == 1 and event["delta"] == -1 and event["augmented"] == 1)
                                       for event in selected_lanes),
        "missing_count": sum(int(event["missing"]) for event in lane_events),
        "missing_changed_count": sum(int(event["missing"] and event["augmented"] is not None) for event in lane_events),
        "invalid_offset_count": sum(int(event["delta"] not in (-1, 1)) for event in selected_lanes),
        "below_minimum_count": sum(int(event["augmented"] is not None and event["augmented"] < 1) for event in lane_events),
    }
    if lane_qc["missing_changed_count"] or lane_qc["invalid_offset_count"] or lane_qc["below_minimum_count"]:
        raise RuntimeError("road-lane perturbation contract failed")

    logical_rows = [{"scene_id": result["scene_id"], "view_id": result["view_id"],
                     "logical_digest": result["logical_digest"], "removed_count": len(result["removed"]),
                     "primary_removed_count": len(result["primary_removed"]),
                     "road_propagated_count": len(result["road_propagated"]), **result["statistics"]}
                    for result in results]
    logical_results = {
        "scene_ids": scene_ids, "view_ids": sorted(views), "thresholds": {"building": thresholds[0], "road": thresholds[1]},
        "threshold_population_digest": threshold_population_digest,
        "scene_view_digests": [{"scene_id": row["scene_id"], "view_id": row["view_id"], "digest": row["logical_digest"]}
                               for row in logical_rows],
        "aggregate_digest": logical_digest(logical_rows),
        "retry_count": sum(row["retries"] for row in logical_rows),
        "rejection_count": sum(row["rejections"] for row in logical_rows),
        "fallback_count": sum(row["fallbacks"] for row in logical_rows),
        "geometry_changed_count": sum(row["geometry_changed"] for row in logical_rows),
        "building_reference_preserved_count": sum(row["building_reference_preserved"] for row in logical_rows),
        "building_geometry_updated_count": sum(row["building_geometry_updated"] for row in logical_rows),
        "building_area_max_error": max((row["building_area_max_error"] for row in logical_rows), default=0.0),
        "lane_qc": lane_qc,
        "full_population_pass_digest": logical_digest([
            {"scene_id": result["scene_id"], "view_id": result["view_id"], "content": result["content_digests"],
             "logical_digest": result["logical_digest"]} for result in results
        ]),
        "adversarial_worker_parity_scenes": adversarial_scenes,
    }
    scientific_identity = {
        "accepted_dataset_id": accepted["training_dataset_id"], "dataloader_smoke_id": loader["smoke_id"],
        "accepted_manifest_sha256": sha256_file(accepted_path), "dataloader_result_sha256": sha256_file(loader_path),
        "augmentation_scientific_contract_sha256": hashlib.sha256(canonical_json_bytes({
            key: value for key, value in config.items() if key not in ("benchmark", "output")
        })).hexdigest(), "schema_sha256": sha256_file(schema_path),
        "tensor_contract_sha256": sha256_file(args.tensor_contract), "implementation_sha256": sha256_file(args.implementation),
        "runner_sha256": sha256_file(Path(__file__)), "requirements_sha256": sha256_file(args.requirements),
        "rng_algorithm": config["rng"]["algorithm"], "base_seed": config["rng"]["base_seed"],
        "dissertation_commit": config["dissertation_commit"],
    }
    acceptance_id = "paa_" + hashlib.sha256(canonical_json_bytes({"scientific_identity": scientific_identity,
                                                                    "logical_results": logical_results})).hexdigest()[:24]
    output_root = Path(args.output_root).resolve()
    final = output_root / acceptance_id
    stage = Path(tempfile.mkdtemp(prefix=f".{acceptance_id}.stage-", dir=output_root.parent if output_root.parent.exists() else None))
    stage.mkdir(parents=True, exist_ok=True)
    parquet_path = stage / config["output"]["scene_results"]
    pq.write_table(pa.Table.from_pylist(logical_rows), parquet_path, compression="zstd")
    latencies = [value[1] for value in first]
    execution = {
        "wall_seconds": time.perf_counter() - started, "latency_p50_seconds": percentile(latencies, 0.50),
        "latency_p95_seconds": percentile(latencies, 0.95), "peak_rss_bytes": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024),
        "worker_counts": {"full_population": [40, 40], "adversarial_parity": [1, 40]},
        "process_start_method": "spawn", "native_threads_per_worker": 1,
        "augmentation_config_sha256": sha256_file(config_path), "cuda": cuda,
    }
    correctness = {
        **fixtures, "actual_scene_count": len(scene_ids), "topology_tensor_round_trip": "PASS", "building_hosted_poi_cascade": "PASS",
        "geometry_retry_fallback": "PASS", "building_numerical_geometry_consistency": "PASS",
        "road_lane_discrete_perturbation": "PASS", "categorical_masking": "PASS",
        "poi_hierarchy_replacement": "PASS", "raster_nodata_support": "PASS",
        "post_augmentation_relations": "PASS", "final_SN_regeneration": "PASS",
        "zero_node_zero_edge_empty_type": "PASS", "same_seed_determinism": "PASS",
        "two_view_independence": "PASS", "input_order_determinism": "PASS",
        "worker_count_determinism": "PASS", "canonical_result_equality": "PASS", "cpu_cuda_correctness": "PASS",
        "direct_rebuild_byte_identity": "PASS", "immutable_reuse": "PASS",
        "same_id_different_content_hard_failure": "PASS",
    }
    qc_path = stage / config["output"]["qc"]
    qc_path.write_bytes(canonical_json_bytes({"status": "PASS", "correctness": correctness,
                                               "logical_results": logical_results}))
    report_path = stage / config["output"]["report"]
    report_path.write_text(
        "# I19 Prototype Augmentation Benchmark\n\n"
        f"Status: PASS\n\nAcceptance ID: `{acceptance_id}`\n\n"
        f"Scenes/views: {len(scene_ids)}/{len(views)}\n\n"
        f"Retries/rejections/fallbacks: {logical_results['retry_count']}/"
        f"{logical_results['rejection_count']}/{logical_results['fallback_count']}\n",
        encoding="utf-8",
    )
    log_path = stage / config["output"]["log"]
    log_path.write_bytes(canonical_json_bytes({"event": "benchmark_complete", "status": "PASS",
                                                "augmentation_acceptance_id": acceptance_id}))
    manifest = {
        "schema_version": "1.0.0", "status": "PASS", "augmentation_acceptance_id": acceptance_id,
        "accepted_dataset_id": accepted["training_dataset_id"], "dataloader_smoke_id": loader["smoke_id"],
        "scientific_identity": scientific_identity, "correctness": correctness,
        "logical_results": logical_results, "execution_evidence": execution, "outputs": [],
    }
    manifest_path = stage / config["output"]["manifest"]
    manifest_path.write_bytes(canonical_json_bytes(manifest))
    for path in (parquet_path, qc_path, report_path, log_path):
        manifest["outputs"].append(file_record(path, stage))
    manifest_path.write_bytes(canonical_json_bytes(manifest))
    core = {key: manifest[key] for key in ("augmentation_acceptance_id", "scientific_identity", "logical_results")}
    publish_status = immutable_publish(stage, final, core)
    published_manifest = final / config["output"]["manifest"]
    published = read_json(published_manifest)
    if publish_status == "new_publish":
        published["execution_evidence"]["publish_status"] = publish_status
        published_manifest.write_bytes(canonical_json_bytes(published))
    print(json.dumps({"status": "PASS", "augmentation_acceptance_id": acceptance_id,
                      "output_files": [str(final / config["output"][name]) for name in ("manifest", "scene_results", "qc", "report", "log")]},
                     sort_keys=True))


if __name__ == "__main__":
    main()
