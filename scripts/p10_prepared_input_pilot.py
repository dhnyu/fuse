#!/usr/bin/env python3
"""Noncanonical exact-equivalence and throughput pilot for P10 prepared input."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from p10_evaluation import (  # noqa: E402
    _dynamic_catalog as dynamic_catalog,
    _device,
    _embed_prepared,
    _load_model,
    _metric,
    _model_values,
    _to_device_nonblocking,
    load_contract,
    resolve_model_bindings,
)
from p10_prepared_input import P10PreparedGeometryCache, P10PreparedInputCache  # noqa: E402
from p6_data import build_vocabulary, read_fixed_query, read_original_scene, tensorize_scene  # noqa: E402
from p6_model import geometry_fourier_features  # noqa: E402
from p7_training import collate  # noqa: E402
from p9_model_families import ds_raster_from_batch, family_contract  # noqa: E402
from p9_v2_prepared_cache import ProductionPreparedData  # noqa: E402


def _equal(left: Any, right: Any, path: str = "root") -> None:
    if isinstance(left, torch.Tensor):
        if not isinstance(right, torch.Tensor) or left.dtype != right.dtype or left.shape != right.shape or not torch.equal(left, right):
            raise AssertionError(f"tensor mismatch:{path}")
    elif isinstance(left, np.ndarray):
        if not isinstance(right, np.ndarray) or left.dtype != right.dtype or left.shape != right.shape or not np.array_equal(left, right):
            raise AssertionError(f"array mismatch:{path}")
    elif isinstance(left, Mapping):
        if not isinstance(right, Mapping) or set(left) != set(right):
            raise AssertionError(f"mapping keys mismatch:{path}")
        for key in left:
            _equal(left[key], right[key], f"{path}.{key}")
    elif isinstance(left, (list, tuple)):
        if not isinstance(right, type(left)) or len(left) != len(right):
            raise AssertionError(f"sequence mismatch:{path}")
        for index, (a, b) in enumerate(zip(left, right, strict=True)):
            _equal(a, b, f"{path}[{index}]")
    elif left != right:
        raise AssertionError(f"value mismatch:{path}:{left!r}!={right!r}")


def _dynamic_batch(contract: Mapping[str, Any], identity: Mapping[str, Any], catalog: Any,
                   preprocessing: Mapping[str, Any], vocabulary: Mapping[str, Any],
                   validation: ProductionPreparedData) -> dict[str, Any]:
    samples = []
    for record in identity["records"]:
        if identity["split"] == "validation":
            role = "validation_query" if identity["kind"] == "query" else "validation_gallery"
            samples.append(validation.sample(role, record["scene_id"], record["view"]))
            continue
        if identity["kind"] == "query":
            scene = read_fixed_query(catalog, identity["split"], record["scene_id"], int(record["view"]))
        else:
            scene = read_original_scene(catalog, record["scene_id"])
        sample = tensorize_scene(scene, preprocessing, vocabulary)
        sample["scene_center_5186"] = torch.tensor(scene["center"], dtype=torch.float64)
        samples.append(sample)
    return collate(samples, vocabulary)


def _prepared_batch(cache: P10PreparedInputCache, split: str, kind: str, index: int) -> dict[str, Any]:
    rows = [row for row in cache.manifest["batches"] if row["split"] == split and row["kind"] == kind]
    row = rows[index]
    payload = torch.load(cache.manifest_path.parent / row["relative_path"], map_location="cpu", weights_only=False)
    return payload


def _forward(model: Any, values: Mapping[str, Any], batch: dict[str, Any], ds: torch.Tensor,
             device: torch.device, cached_geometry: tuple[torch.Tensor, torch.Tensor] | None = None) -> torch.Tensor:
    device_batch = _to_device_nonblocking(batch, device)
    ds_device = ds.to(device, non_blocking=True) if values["family"] == "DS" else None
    geometry = None
    if "geometry" in family_contract(values["family"]).modalities:
        geometry = cached_geometry or geometry_fourier_features(
            device_batch, {"geometry": values["model_config"]["model"]["geometry"]}, device)
    with torch.inference_mode():
        value = model.online(device_batch, geometry, ds_device)["scene_embedding"]
        return torch.nn.functional.normalize(value, dim=1).cpu()


def run(contract_path: str, manifest_path: str, geometry_manifest: str, prepared_batches: int) -> dict[str, Any]:
    contract = load_contract(contract_path)
    cache = P10PreparedInputCache.open(manifest_path)
    geometry_cache = P10PreparedGeometryCache.open(geometry_manifest)
    comparisons = []
    chosen = (("validation", "query", 0), ("validation", "gallery", 49),
              ("evaluation", "query", 0), ("evaluation", "query", 200),
              ("evaluation", "query", 399), ("evaluation", "gallery", 0),
              ("evaluation", "gallery", 199))
    first_dynamic_wall = None
    first_dynamic = {}
    catalog = dynamic_catalog(contract)
    preprocessing = json.loads(Path(contract["inputs"]["preprocessing"]).read_text())
    vocabulary = build_vocabulary(contract["inputs"]["categories"])
    validation = ProductionPreparedData(contract["inputs"]["p9_production_cache"], "main_1.0x", 8)
    for split, kind, index in chosen:
        prepared = _prepared_batch(cache, split, kind, index)
        started = time.monotonic()
        dynamic = _dynamic_batch(
            contract, prepared["identity"], catalog, preprocessing, vocabulary, validation
        )
        wall = time.monotonic() - started
        if split == "evaluation" and kind == "query" and index == 0:
            first_dynamic_wall = wall
        _equal(dynamic, prepared["batch"], f"{split}.{kind}.{index}")
        expected_ds = ds_raster_from_batch(dynamic)
        _equal(expected_ds, prepared["ds_raster"], f"{split}.{kind}.{index}.ds")
        comparisons.append({"split": split, "kind": kind, "batch_index": index,
                            "records": len(prepared["identity"]["records"]), "dynamic_wall_seconds": wall})
        if split == "evaluation" and index == 0:
            first_dynamic[kind] = (dynamic, expected_ds)

    bindings = {row.configuration_id: row for row in resolve_model_bindings(contract)}
    rows = json.loads(Path(contract["inputs"]["hyperparameter_matrix"]).read_text())["rows"]
    rows += json.loads(Path(contract["inputs"]["comparison_matrix"]).read_text())["rows"]
    row_index = {row["configuration_id"]: row for row in rows}
    device = _device(contract)
    forward = []
    for name in ("cfg_d128", "cmp_ds_like"):
        binding = bindings[name]
        values = _model_values(contract, binding, row_index[name])
        model = _load_model(binding, values, device)
        dynamic_vectors, prepared_vectors = [], []
        for kind in ("query", "gallery"):
            prepared = _prepared_batch(cache, "evaluation", kind, 0)
            dynamic, dynamic_ds = first_dynamic[kind]
            prepared_ds = prepared["ds_raster"]
            dynamic_vectors.append(_forward(model, values, dynamic, dynamic_ds, device))
            cached_geometry = (geometry_cache.batch("evaluation", kind, 0, device)
                               if "geometry" in family_contract(values["family"]).modalities else None)
            prepared_vectors.append(_forward(
                model, values, prepared["batch"], prepared_ds, device, cached_geometry))
        dynamic_all = torch.cat(dynamic_vectors)
        prepared_all = torch.cat(prepared_vectors)
        _equal(dynamic_all, prepared_all, f"{name}.embedding")
        dynamic_metric, dynamic_rank = _metric(
            dynamic_vectors[0], dynamic_vectors[1][:4], float(contract["execution"]["temperature"])
        )
        prepared_metric, prepared_rank = _metric(
            prepared_vectors[0], prepared_vectors[1][:4], float(contract["execution"]["temperature"])
        )
        _equal(dynamic_metric, prepared_metric, f"{name}.metric")
        _equal(dynamic_rank, prepared_rank, f"{name}.ranking")
        forward.append({"configuration_id": name, "embedding_sha256": __import__("hashlib").sha256(
            prepared_all.numpy().tobytes()).hexdigest(), "metric": prepared_metric})
        del model
        torch.cuda.empty_cache()

    binding = bindings["cfg_d128"]
    values = _model_values(contract, binding, row_index["cfg_d128"])
    model = _load_model(binding, values, device)
    validation_embeddings, _ = _embed_prepared(model, values, contract, device, cache, "validation")
    validation_metric, _ = _metric(
        validation_embeddings[:800], validation_embeddings[800:], float(contract["execution"]["temperature"])
    )
    if (abs(validation_metric["retrieval_loss"] - binding.expected_retrieval_loss) > 1e-6
            or abs(validation_metric["mean_source_separation_margin"] - binding.expected_margin) > 1e-6):
        raise AssertionError("full validation metrics do not reproduce selected checkpoint evidence")
    validation_result = {"expected_loss": binding.expected_retrieval_loss,
                         "reproduced_loss": validation_metric["retrieval_loss"],
                         "expected_margin": binding.expected_margin,
                         "reproduced_margin": validation_metric["mean_source_separation_margin"]}
    del model, validation_embeddings
    torch.cuda.empty_cache()

    mask_scenes, masks = cache.nonlocal_masks()
    gallery_payload = _prepared_batch(cache, "evaluation", "gallery", 0)
    assert mask_scenes[:8] == gallery_payload["batch"]["scene_ids"]
    centers = []
    for index in range(200):
        centers.extend(_prepared_batch(cache, "evaluation", "gallery", index)["batch"]["scene_center_5186"].numpy())
    centers = np.asarray(centers, dtype=np.float64)
    distances = np.sqrt(((centers - centers[0]) ** 2).sum(1))
    _equal(torch.from_numpy(distances >= 2000.0), masks[0], "nonlocal_mask")

    binding = bindings["cfg_d128"]
    values = _model_values(contract, binding, row_index["cfg_d128"])
    model = _load_model(binding, values, device)
    loader_started = time.monotonic()
    cpu_started = time.process_time()
    count = 0
    input_walls, geometry_walls, h2d_walls, forward_walls, batch_walls = [], [], [], [], []
    iterator = iter(cache.batches("evaluation", "query", workers=8, prefetch=2, pin_memory=True))
    while count < prepared_batches:
        batch_started = time.monotonic()
        input_started = time.monotonic()
        payload = next(iterator)
        input_walls.append(time.monotonic() - input_started)
        geometry_started = time.monotonic()
        cached_geometry = geometry_cache.batch("evaluation", "query", count, device)
        torch.cuda.synchronize(device)
        geometry_walls.append(time.monotonic() - geometry_started)
        h2d_started = time.monotonic()
        device_batch = _to_device_nonblocking(payload["batch"], device)
        torch.cuda.synchronize(device)
        h2d_walls.append(time.monotonic() - h2d_started)
        forward_started = time.monotonic()
        with torch.inference_mode():
            model.online(device_batch, cached_geometry, None)["scene_embedding"]
        torch.cuda.synchronize(device)
        forward_walls.append(time.monotonic() - forward_started)
        count += 1
        batch_walls.append(time.monotonic() - batch_started)
    prepared_wall = time.monotonic() - loader_started
    cpu_wall = time.process_time() - cpu_started
    def timing(values: list[float]) -> dict[str, float]:
        return {"median_seconds": float(np.median(values)), "p95_seconds": float(np.percentile(values, 95))}
    result = {
        "status": "PASS", "cache_id": cache.cache_id, "exact_batch_comparisons": comparisons,
        "geometry_cache_id": geometry_cache.cache_id,
        "model_equivalence": forward, "validation_reproduction": validation_result,
        "nonlocal_mask_equal": True, "ranking_equal": True, "qualitative_ranking_equal": True,
        "performance": {"dynamic_first_batch_seconds": first_dynamic_wall,
                        "prepared_batches": count, "prepared_total_seconds": prepared_wall,
                        "prepared_seconds_per_batch": prepared_wall / count,
                        "prepared_records_per_second": count * 8 / prepared_wall,
                        "speedup_vs_dynamic_first_batch": first_dynamic_wall / (prepared_wall / count),
                        "input_wait": timing(input_walls), "geometry_lookup_h2d": timing(geometry_walls),
                        "batch_h2d": timing(h2d_walls), "forward": timing(forward_walls),
                        "batch_wall": timing(batch_walls),
                        "process_cpu_core_utilization_percent": 100.0 * cpu_wall / prepared_wall,
                        "peak_gpu_bytes": torch.cuda.max_memory_allocated(device)},
        "publication_count": 0, "training_count": 0, "optimizer_update_count": 0,
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", default=str(ROOT / "config/p10_evaluation.yml"))
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--geometry-manifest", required=True)
    parser.add_argument("--prepared-batches", type=int, default=16)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = run(args.contract, args.manifest, args.geometry_manifest, args.prepared_batches)
    Path(args.output).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
