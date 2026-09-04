"""Deterministic, content-addressed prepared inputs for canonical P10 evaluation.

The cache is an execution acceleration artifact. Its identity binds the accepted
P3/P5 sources and tensorization contract, while scientific authority remains the
closed P10 authority. Formal P10 evaluation never falls back to dynamic source
reconstruction when this cache is required.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import multiprocessing as mp
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

import torch
import numpy as np
from torch.utils.data import DataLoader, Dataset

from p6_data import (
    ArtifactCatalog,
    _delta_tables,
    apply_delta,
    build_vocabulary,
    read_original_scene,
    tensorize_scene,
)
from canonical_config import load_strict_yaml
from p6_model import geometry_fourier_features
from p7_training import collate
from p9_model_families import ds_raster_from_batch
from p9_v2_canonical import canonical_json_bytes, canonical_sha256, sha256_file
from p9_v2_ledger import fsync_directory, write_all
from p9_v2_prepared_cache import ProductionPreparedData


SCHEMA_VERSION = "1.0.0"
CONTRACT_VERSION = "p10-prepared-input-v1"
TENSOR_LAYOUT_VERSION = "p6-ragged-collate-v3+p10-center-v1"


class P10PreparedInputError(RuntimeError):
    """The immutable P10 prepared-input cache is missing or inconsistent."""


def _read_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise P10PreparedInputError(f"PREPARED_JSON_OBJECT_REQUIRED:{path}")
    return value


def _atomic_bytes(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    stage = Path(name)
    try:
        write_all(descriptor, raw)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    try:
        os.link(stage, path)
    except FileExistsError:
        if path.read_bytes() != raw:
            raise P10PreparedInputError(f"PREPARED_IMMUTABLE_COLLISION:{path}")
    finally:
        stage.unlink(missing_ok=True)
    fsync_directory(path.parent)


def _atomic_torch(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.incomplete-{os.getpid()}")
    with temporary.open("wb") as stream:
        torch.save(dict(value), stream)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        os.link(temporary, path)
    except FileExistsError as error:
        raise P10PreparedInputError(f"PREPARED_PAYLOAD_COLLISION:{path}") from error
    finally:
        temporary.unlink(missing_ok=True)
    fsync_directory(path.parent)


def _catalog_inputs(contract: Mapping[str, Any]) -> tuple[dict[str, str], dict[str, str]]:
    root = Path(contract["inputs"]["p5_acceptance_root"])
    p5 = _read_json(root / "fixed_query_acceptance.json")
    p4_paths = sorted((Path(contract["inputs"]["p4_root"]) / "acceptance").glob(
        "*/augmentation_bank_acceptance.json"
    ))
    if len(p4_paths) != 1:
        raise P10PreparedInputError("PREPARED_P4_ACCEPTANCE_AMBIGUOUS")
    p4 = _read_json(p4_paths[0])
    roots = {key: str(contract["inputs"][f"{key}_root"]) for key in ("p3", "p4", "p5")}
    expected = {
        "p3_cache_id": p5["parent_cache_id"],
        "p4_master_bank_id": p4["bank_id"],
        "p5_query_authority_id": p5["query_authority_id"],
    }
    return roots, expected


def _catalog(contract: Mapping[str, Any], verify: bool) -> ArtifactCatalog:
    roots, expected = _catalog_inputs(contract)
    return ArtifactCatalog(roots, expected, verify=verify)


def _source_inventory(contract: Mapping[str, Any], catalog: ArtifactCatalog) -> dict[str, Any]:
    p5 = Path(contract["inputs"]["p5_acceptance_root"])
    p3_indices = sorted((Path(contract["inputs"]["p3_root"]) / "index").glob("*/scene_to_shard.parquet"))
    if len(p3_indices) != 1:
        raise P10PreparedInputError("PREPARED_P3_INDEX_AMBIGUOUS")
    evaluation_scenes = sorted(str(row["scene_id"]) for row in catalog.gallery_rows["evaluation"])
    validation_data = ProductionPreparedData(contract["inputs"]["p9_production_cache"], "main_1.0x", 8)
    validation_scenes = list(validation_data.validation_scenes)
    selected = set(evaluation_scenes) | set(validation_scenes)
    p3 = [{"scene_id": scene, "branch_id": catalog.p3_by_scene[scene]["branch_id"],
           "payload_sha256": catalog.p3_by_scene[scene]["payload_sha256"]} for scene in sorted(selected)]
    p5_queries = []
    for split in ("evaluation",):
        for row in catalog.query_rows[split]:
            p5_queries.append({
                "split": split,
                "scene_id": str(row["scene_id"]),
                "query_index": int(row["query_index"]),
                "query_id": str(row["query_id"]),
                "query_branch_id": str(row["query_branch_id"]),
                "query_payload_sha256": str(row["query_payload_sha256"]),
            })
    files = {}
    for name, path in {
        "p3_scene_index": p3_indices[0],
        "p5_fixed_query_acceptance": p5 / "fixed_query_acceptance.json",
        "p5_evaluation_acceptance": p5 / "evaluation_acceptance.json",
        "validation_query_index": p5 / "validation_query_index.parquet",
        "validation_gallery": p5 / "validation_gallery.parquet",
        "evaluation_query_index": p5 / "evaluation_query_index.parquet",
        "evaluation_gallery": p5 / "evaluation_gallery.parquet",
        "preprocessing": Path(contract["inputs"]["preprocessing"]),
        "categories": Path(contract["inputs"]["categories"]),
        "p9_prepared_cache_plan": Path(contract["inputs"]["p9_production_cache"]) / "canonical_cache_plan.json",
        "p9_production_cache_manifest": Path(contract["inputs"]["p9_production_cache"]) / "production_cache_manifest.json",
    }.items():
        if not path.is_file():
            raise P10PreparedInputError(f"PREPARED_SOURCE_MISSING:{name}")
        files[name] = {"sha256": sha256_file(path), "size_bytes": path.stat().st_size}
    return {
        "accepted_evaluation": dict(contract["accepted_evaluation"]),
        "files": files,
        "p3_scene_sources": p3,
        "p5_query_sources": p5_queries,
        "validation_scene_ids": validation_scenes,
        "evaluation_scene_ids": evaluation_scenes,
    }


def _ordered_records(source: Mapping[str, Any]) -> list[dict[str, Any]]:
    records = []
    for split, scenes in (("validation", source["validation_scene_ids"]),
                          ("evaluation", source["evaluation_scene_ids"])):
        for scene in scenes:
            for view in (0, 1):
                records.append({"split": split, "role": f"{split}_query", "scene_id": scene, "view": view})
        for scene in scenes:
            records.append({"split": split, "role": f"{split}_gallery", "scene_id": scene, "view": None})
    expected = 1200 + 4800
    if len(records) != expected:
        raise P10PreparedInputError("PREPARED_RECORD_POPULATION_INVALID")
    return records


def make_cache_plan(contract: Mapping[str, Any]) -> dict[str, Any]:
    catalog = _catalog(contract, verify=False)
    source = _source_inventory(contract, catalog)
    records = _ordered_records(source)
    batch_size = int(contract["prepared_input"]["batch_size"])
    if batch_size != int(contract["execution"]["batch_size"]) or batch_size <= 0:
        raise P10PreparedInputError("PREPARED_BATCH_SIZE_MISMATCH")
    preimage = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "p10_prepared_input_plan",
        "contract_version": CONTRACT_VERSION,
        "tensor_layout_version": TENSOR_LAYOUT_VERSION,
        "source_inventory": source,
        "ordered_records": records,
        "batch_size": batch_size,
        "tensor_dtypes": "p6_tensorize_scene_and_p7_collate_exact",
        "ds_raster": {"included": True, "shape": [26, 100, 100], "dtype": "torch.float32"},
        "geometry_fourier": {"included": False, "reason": "device-sensitive; computed by accepted model path"},
        "nonlocal_exclusion": {"included": True, "distance_m": 2000.0},
    }
    digest = canonical_sha256(preimage)
    return {**preimage, "cache_id": f"p10pi_{digest[:24]}", "content_sha256": digest}


_WORKER_CONTRACT: dict[str, Any] | None = None
_WORKER_CATALOG: ArtifactCatalog | None = None
_WORKER_PREPROCESSING: dict[str, Any] | None = None
_WORKER_VOCABULARY: dict[str, Any] | None = None
_WORKER_QUERY_INDEX: dict[tuple[str, str, int], dict[str, Any]] | None = None
_WORKER_VALIDATION: ProductionPreparedData | None = None


def _worker_init(contract: Mapping[str, Any]) -> None:
    global _WORKER_CONTRACT, _WORKER_CATALOG, _WORKER_PREPROCESSING, _WORKER_VOCABULARY, _WORKER_QUERY_INDEX, _WORKER_VALIDATION
    for name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        os.environ[name] = "1"
    torch.set_num_threads(1)
    _WORKER_CONTRACT = dict(contract)
    _WORKER_CATALOG = _catalog(contract, verify=False)
    _WORKER_PREPROCESSING = _read_json(contract["inputs"]["preprocessing"])
    _WORKER_VOCABULARY = build_vocabulary(contract["inputs"]["categories"])
    _WORKER_QUERY_INDEX = {
        ("evaluation", str(row["scene_id"]), int(row["query_index"])): row
        for row in _WORKER_CATALOG.query_rows["evaluation"]
    }
    _WORKER_VALIDATION = ProductionPreparedData(contract["inputs"]["p9_production_cache"], "main_1.0x", 8)


def _finish_sample(scene: dict[str, Any]) -> dict[str, Any]:
    assert _WORKER_PREPROCESSING is not None and _WORKER_VOCABULARY is not None
    sample = tensorize_scene(scene, _WORKER_PREPROCESSING, _WORKER_VOCABULARY)
    sample["scene_center_5186"] = torch.tensor(scene["center"], dtype=torch.float64)
    return sample


def _scene_bundle(task: tuple[str, str, str]) -> dict[str, Any]:
    split, scene_id, output_name = task
    assert (_WORKER_CATALOG is not None and _WORKER_QUERY_INDEX is not None
            and _WORKER_VOCABULARY is not None and _WORKER_VALIDATION is not None)
    if split == "validation":
        queries = [_WORKER_VALIDATION.sample("validation_query", scene_id, view) for view in (0, 1)]
        gallery = _WORKER_VALIDATION.sample("validation_gallery", scene_id, None)
    else:
        original = read_original_scene(_WORKER_CATALOG, scene_id)
        gallery = _finish_sample(original)
        queries = []
        for view in (0, 1):
            row = _WORKER_QUERY_INDEX[(split, scene_id, view)]
            delta = _delta_tables(_WORKER_CATALOG.p5_tar(row), "query_id", row["query_id"])
            scene = apply_delta(original, delta, row["query_id"], row["profile_id"], view)
            scene["positive_scene_id"] = row["positive_scene_id"]
            queries.append(_finish_sample(scene))
    samples = {"query_0": queries[0], "query_1": queries[1], "gallery": gallery}
    ds = {key: ds_raster_from_batch(collate([sample], _WORKER_VOCABULARY))[0].contiguous()
          for key, sample in samples.items()}
    path = Path(output_name)
    payload = {"schema_version": SCHEMA_VERSION, "split": split, "scene_id": scene_id,
               "samples": samples, "ds_rasters": ds}
    _atomic_torch(path, payload)
    return {"split": split, "scene_id": scene_id, "relative_path": path.name,
            "payload_sha256": sha256_file(path), "size_bytes": path.stat().st_size}


def _verify_unique_sources(plan: Mapping[str, Any], contract: Mapping[str, Any]) -> None:
    catalog = _catalog(contract, verify=False)
    seen: dict[Path, str] = {}
    for row in plan["source_inventory"]["p3_scene_sources"]:
        source = catalog.p3_by_scene[row["scene_id"]]
        path = Path(contract["inputs"]["p3_root"]) / "shards" / source["branch_id"] / source["payload_filename"]
        seen[path] = source["payload_sha256"]
    for split in ("evaluation",):
        for row in catalog.query_rows[split]:
            path = catalog.p5_tar(row)
            seen[path] = row["query_payload_sha256"]
    for path, expected in sorted(seen.items(), key=lambda item: str(item[0])):
        if not path.is_file() or sha256_file(path) != expected:
            raise P10PreparedInputError(f"PREPARED_SOURCE_HASH_MISMATCH:{path}")


def _batch_specs(plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    size = int(plan["batch_size"])
    result = []
    for split, count in (("validation", 400), ("evaluation", 1600)):
        scenes = list(plan["source_inventory"][f"{split}_scene_ids"])
        if len(scenes) != count:
            raise P10PreparedInputError("PREPARED_SPLIT_POPULATION_INVALID")
        query_records = [(scene, view) for scene in scenes for view in (0, 1)]
        gallery_records = [(scene, None) for scene in scenes]
        for kind, records in (("query", query_records), ("gallery", gallery_records)):
            for start in range(0, len(records), size):
                selected = records[start:start + size]
                result.append({"split": split, "kind": kind, "batch_index": start // size,
                               "records": [{"scene_id": scene, "view": view} for scene, view in selected]})
    return result


def _materialize_batches(stage: Path, plan: Mapping[str, Any], scene_rows: Sequence[Mapping[str, Any]],
                         contract: Mapping[str, Any]) -> list[dict[str, Any]]:
    vocabulary = build_vocabulary(contract["inputs"]["categories"])
    scene_index = {(row["split"], row["scene_id"]): stage / "scenes" / row["relative_path"] for row in scene_rows}
    rows = []
    for identity in _batch_specs(plan):
        samples, ds = [], []
        loaded: dict[Path, dict[str, Any]] = {}
        for record in identity["records"]:
            source = scene_index[(identity["split"], record["scene_id"])]
            if source not in loaded:
                loaded[source] = torch.load(source, map_location="cpu", weights_only=False)
            payload = loaded[source]
            if payload.get("split") != identity["split"] or payload.get("scene_id") != record["scene_id"]:
                raise P10PreparedInputError("PREPARED_SCENE_BUNDLE_IDENTITY_MISMATCH")
            key = "gallery" if identity["kind"] == "gallery" else f"query_{record['view']}"
            samples.append(payload["samples"][key])
            ds.append(payload["ds_rasters"][key])
        batch = collate(samples, vocabulary)
        raster = torch.stack(ds).contiguous()
        filename = f"{identity['split']}-{identity['kind']}-{identity['batch_index']:04d}.pt"
        path = stage / "batches" / filename
        _atomic_torch(path, {"schema_version": SCHEMA_VERSION, "cache_id": plan["cache_id"],
                             "identity": identity, "batch": batch, "ds_raster": raster})
        rows.append({**identity, "relative_path": f"batches/{filename}",
                     "payload_sha256": sha256_file(path), "size_bytes": path.stat().st_size})
    return rows


def _nonlocal_masks(stage: Path, plan: Mapping[str, Any], batch_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    centers, scenes = [], []
    for row in batch_rows:
        if row["split"] != "evaluation" or row["kind"] != "gallery":
            continue
        payload = torch.load(stage / row["relative_path"], map_location="cpu", weights_only=False)
        centers.extend(payload["batch"]["scene_center_5186"].numpy().astype("float64", copy=False))
        scenes.extend(payload["batch"]["scene_ids"])
    center_array = np.asarray(centers, dtype=np.float64)
    if len(scenes) != 1600 or scenes != list(plan["source_inventory"]["evaluation_scene_ids"]):
        raise P10PreparedInputError("PREPARED_GALLERY_CENTER_IDENTITY_MISMATCH")
    distances = ((center_array[:, None, :] - center_array[None, :, :]) ** 2).sum(2) ** 0.5
    masks = distances >= 2000.0
    path = stage / "nonlocal_masks.pt"
    identity = {"scene_ids": scenes, "distance_m": 2000.0,
                "raw_sha256": hashlib.sha256(masks.tobytes()).hexdigest()}
    _atomic_torch(path, {"schema_version": SCHEMA_VERSION, "cache_id": plan["cache_id"],
                         "identity": identity, "masks": torch.from_numpy(masks)})
    return {**identity, "relative_path": path.name, "payload_sha256": sha256_file(path),
            "size_bytes": path.stat().st_size}


def validate_prepared_cache(manifest_path: str | Path, verify_payloads: bool = True) -> dict[str, Any]:
    path = Path(manifest_path)
    manifest = _read_json(path)
    plan = manifest.get("plan")
    if not isinstance(plan, dict):
        raise P10PreparedInputError("PREPARED_PLAN_MISSING")
    preimage = {key: value for key, value in plan.items() if key not in {"cache_id", "content_sha256"}}
    digest = canonical_sha256(preimage)
    if (plan.get("schema_version") != SCHEMA_VERSION or plan.get("contract_version") != CONTRACT_VERSION
            or plan.get("content_sha256") != digest or plan.get("cache_id") != f"p10pi_{digest[:24]}"
            or manifest.get("cache_id") != plan.get("cache_id") or manifest.get("status") != "PASS"):
        raise P10PreparedInputError("PREPARED_MANIFEST_IDENTITY_INVALID")
    rows = manifest.get("batches")
    expected = _batch_specs(plan)
    if not isinstance(rows, list) or [{key: row[key] for key in ("split", "kind", "batch_index", "records")}
                                      for row in rows] != expected:
        raise P10PreparedInputError("PREPARED_BATCH_INVENTORY_INVALID")
    root = path.parent.resolve()
    for row in [*rows, manifest.get("nonlocal_masks", {})]:
        try:
            payload = (root / row["relative_path"]).resolve()
            relative = payload.relative_to(root)
        except (KeyError, ValueError) as error:
            raise P10PreparedInputError("PREPARED_PAYLOAD_PATH_INVALID") from error
        if relative.parts[0].startswith(".") or payload.is_symlink() or not payload.is_file():
            raise P10PreparedInputError("PREPARED_PAYLOAD_MISSING")
        if payload.stat().st_size != int(row["size_bytes"]):
            raise P10PreparedInputError("PREPARED_PAYLOAD_SIZE_MISMATCH")
        if verify_payloads and sha256_file(payload) != row["payload_sha256"]:
            raise P10PreparedInputError("PREPARED_PAYLOAD_HASH_MISMATCH")
    scientific = {key: value for key, value in manifest.items() if key not in {"manifest_sha256"}}
    if manifest.get("manifest_sha256") != canonical_sha256(scientific):
        raise P10PreparedInputError("PREPARED_MANIFEST_HASH_MISMATCH")
    return manifest


def build_prepared_cache(contract: Mapping[str, Any]) -> Path:
    plan = make_cache_plan(contract)
    root = Path(contract["prepared_input"]["root"])
    destination = root / plan["cache_id"]
    committed = destination / "prepared_input_manifest.json"
    if committed.is_file():
        validate_prepared_cache(committed)
        return committed
    if destination.exists():
        raise P10PreparedInputError("PREPARED_INCOMPLETE_DESTINATION_EXISTS")
    root.mkdir(parents=True, exist_ok=True)
    _verify_unique_sources(plan, contract)
    stage = root / f".staging-{plan['cache_id']}-{os.getpid()}"
    stage.mkdir(mode=0o755)
    (stage / "scenes").mkdir()
    started = time.monotonic()
    tasks = []
    for split in ("validation", "evaluation"):
        for scene in plan["source_inventory"][f"{split}_scene_ids"]:
            tasks.append((split, scene, str(stage / "scenes" / f"{split}-{scene}.pt")))
    workers = int(contract["prepared_input"]["build_workers"])
    with concurrent.futures.ProcessPoolExecutor(
        max_workers=workers, mp_context=mp.get_context("spawn"),
        initializer=_worker_init, initargs=(dict(contract),),
    ) as pool:
        scene_rows = list(pool.map(_scene_bundle, tasks, chunksize=1))
    scene_rows.sort(key=lambda row: (row["split"], row["scene_id"]))
    batches = _materialize_batches(stage, plan, scene_rows, contract)
    masks = _nonlocal_masks(stage, plan, batches)
    for row in scene_rows:
        (stage / "scenes" / row["relative_path"]).unlink()
    (stage / "scenes").rmdir()
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "p10_prepared_input_cache",
        "cache_id": plan["cache_id"],
        "plan": plan,
        "batches": batches,
        "batch_count": len(batches),
        "record_count": 6000,
        "nonlocal_masks": masks,
        "build": {"workers": workers, "wall_seconds": time.monotonic() - started},
        "status": "PASS",
    }
    manifest["manifest_sha256"] = canonical_sha256(manifest)
    _atomic_bytes(stage / "prepared_input_manifest.json", canonical_json_bytes(manifest))
    validate_prepared_cache(stage / "prepared_input_manifest.json")
    try:
        os.rename(stage, destination)
    except FileExistsError:
        validate_prepared_cache(destination / "prepared_input_manifest.json")
    fsync_directory(root)
    validate_prepared_cache(committed)
    return committed


def _device_batch(value: Any, device: torch.device, key: str = "") -> Any:
    if isinstance(value, torch.Tensor):
        if key in {"part_coordinates_xy_m_scientific", "ring_coordinates_xy_m_scientific"}:
            return value
        return value.to(device)
    if isinstance(value, dict):
        return {name: _device_batch(item, device, name) for name, item in value.items()}
    return value


def make_geometry_plan(contract: Mapping[str, Any], inputs: "P10PreparedInputCache") -> dict[str, Any]:
    model = load_strict_yaml(contract["inputs"]["model_config"])
    preimage = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "p10_prepared_geometry_plan",
        "contract_version": "p10-prepared-geometry-v1",
        "prepared_input_cache_id": inputs.cache_id,
        "prepared_input_plan_sha256": inputs.manifest["plan"]["content_sha256"],
        "geometry_config": model["model"]["geometry"],
        "geometry_layout_version": "3.0.0",
        "implementation": "prototype_encoder.geometry_fourier_features:vectorized",
        "implementation_sha256": sha256_file(Path(__file__).with_name("prototype_encoder.py")),
        "device_contract": "CUDA deterministic algorithms; RTX A6000 equivalent outputs required",
        "batches": [{key: row[key] for key in ("split", "kind", "batch_index", "records")}
                    for row in inputs.manifest["batches"] if row["split"] == "evaluation"],
    }
    digest = canonical_sha256(preimage)
    return {**preimage, "cache_id": f"p10geo_{digest[:24]}", "content_sha256": digest}


def _geometry_worker(gpu: int, rows: Sequence[Mapping[str, Any]], input_root: str,
                     output_root: str, input_cache_id: str, geometry_cache_id: str,
                     geometry_config: Mapping[str, Any]) -> None:
    os.environ["CUDA_VISIBLE_DEVICES"] = str(gpu)
    os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
    torch.cuda.set_device(0)
    torch.use_deterministic_algorithms(True, warn_only=False)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    torch.set_num_threads(1)
    device = torch.device("cuda:0")
    for row in rows:
        source = Path(input_root) / row["relative_path"]
        payload = torch.load(source, map_location="cpu", weights_only=False)
        if payload.get("cache_id") != input_cache_id:
            raise P10PreparedInputError("PREPARED_GEOMETRY_PARENT_MISMATCH")
        batch = _device_batch(payload["batch"], device)
        magnitude, phase = geometry_fourier_features(
            batch, {"geometry": dict(geometry_config)}, device, implementation="vectorized"
        )
        identity = {key: row[key] for key in ("split", "kind", "batch_index", "records")}
        filename = f"{row['split']}-{row['kind']}-{row['batch_index']:04d}.pt"
        _atomic_torch(Path(output_root) / filename, {
            "schema_version": SCHEMA_VERSION, "cache_id": geometry_cache_id,
            "parent_cache_id": input_cache_id, "identity": identity,
            "magnitude": magnitude.cpu(), "phase": phase.cpu(),
        })


def validate_geometry_cache(manifest_path: str | Path, verify_payloads: bool = True) -> dict[str, Any]:
    path = Path(manifest_path)
    manifest = _read_json(path)
    plan = manifest.get("plan", {})
    preimage = {key: value for key, value in plan.items() if key not in {"cache_id", "content_sha256"}}
    digest = canonical_sha256(preimage)
    if (plan.get("contract_version") != "p10-prepared-geometry-v1"
            or plan.get("content_sha256") != digest or plan.get("cache_id") != f"p10geo_{digest[:24]}"
            or manifest.get("cache_id") != plan.get("cache_id") or manifest.get("status") != "PASS"):
        raise P10PreparedInputError("PREPARED_GEOMETRY_MANIFEST_INVALID")
    expected = plan.get("batches")
    rows = manifest.get("entries")
    if not isinstance(rows, list) or [{key: row[key] for key in ("split", "kind", "batch_index", "records")}
                                      for row in rows] != expected:
        raise P10PreparedInputError("PREPARED_GEOMETRY_INVENTORY_INVALID")
    root = path.parent.resolve()
    for row in rows:
        payload = (root / row["relative_path"]).resolve()
        try:
            payload.relative_to(root)
        except ValueError as error:
            raise P10PreparedInputError("PREPARED_GEOMETRY_PATH_INVALID") from error
        if payload.is_symlink() or not payload.is_file():
            raise P10PreparedInputError("PREPARED_GEOMETRY_PAYLOAD_MISSING")
        if payload.stat().st_size != int(row["size_bytes"]):
            raise P10PreparedInputError("PREPARED_GEOMETRY_SIZE_MISMATCH")
        if verify_payloads and sha256_file(payload) != row["payload_sha256"]:
            raise P10PreparedInputError("PREPARED_GEOMETRY_HASH_MISMATCH")
    scientific = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    if manifest.get("manifest_sha256") != canonical_sha256(scientific):
        raise P10PreparedInputError("PREPARED_GEOMETRY_MANIFEST_HASH_MISMATCH")
    return manifest


def build_geometry_cache(contract: Mapping[str, Any], input_manifest: str | Path) -> Path:
    inputs = P10PreparedInputCache.open(input_manifest)
    plan = make_geometry_plan(contract, inputs)
    root = Path(contract["prepared_input"]["geometry_root"])
    destination = root / plan["cache_id"]
    committed = destination / "prepared_geometry_manifest.json"
    if committed.is_file():
        validate_geometry_cache(committed)
        return committed
    if destination.exists():
        raise P10PreparedInputError("PREPARED_GEOMETRY_INCOMPLETE_DESTINATION")
    root.mkdir(parents=True, exist_ok=True)
    stage = root / f".staging-{plan['cache_id']}-{os.getpid()}"
    entries = stage / "entries"
    entries.mkdir(parents=True)
    rows = [row for row in inputs.manifest["batches"] if row["split"] == "evaluation"]
    started = time.monotonic()
    context = mp.get_context("spawn")
    processes = []
    for gpu in (0, 1):
        selected = [row for index, row in enumerate(rows) if index % 2 == gpu]
        process = context.Process(target=_geometry_worker, args=(
            gpu, selected, str(inputs.manifest_path.parent), str(entries), inputs.cache_id,
            plan["cache_id"], plan["geometry_config"],
        ))
        process.start()
        processes.append(process)
    for process in processes:
        process.join()
        if process.exitcode != 0:
            raise P10PreparedInputError(f"PREPARED_GEOMETRY_WORKER_FAILED:{process.pid}:{process.exitcode}")
    output_rows = []
    for row in rows:
        filename = f"{row['split']}-{row['kind']}-{row['batch_index']:04d}.pt"
        path = entries / filename
        if not path.is_file():
            raise P10PreparedInputError("PREPARED_GEOMETRY_COVERAGE_INCOMPLETE")
        output_rows.append({**{key: row[key] for key in ("split", "kind", "batch_index", "records")},
                            "relative_path": f"entries/{filename}", "size_bytes": path.stat().st_size,
                            "payload_sha256": sha256_file(path)})
    manifest = {"schema_version": SCHEMA_VERSION, "artifact_type": "p10_prepared_geometry_cache",
                "cache_id": plan["cache_id"], "plan": plan, "entries": output_rows,
                "entry_count": len(output_rows), "build": {"gpu_count": 2,
                "wall_seconds": time.monotonic() - started}, "status": "PASS"}
    manifest["manifest_sha256"] = canonical_sha256(manifest)
    _atomic_bytes(stage / "prepared_geometry_manifest.json", canonical_json_bytes(manifest))
    validate_geometry_cache(stage / "prepared_geometry_manifest.json")
    try:
        os.rename(stage, destination)
    except FileExistsError:
        validate_geometry_cache(destination / "prepared_geometry_manifest.json")
    fsync_directory(root)
    validate_geometry_cache(committed)
    return committed


@dataclass(frozen=True)
class P10PreparedGeometryCache:
    manifest_path: Path
    manifest: dict[str, Any]

    @classmethod
    def open(cls, manifest_path: str | Path, verify_payloads: bool = True) -> "P10PreparedGeometryCache":
        path = Path(manifest_path)
        return cls(path, validate_geometry_cache(path, verify_payloads))

    @property
    def cache_id(self) -> str:
        return str(self.manifest["cache_id"])

    def batch(self, split: str, kind: str, index: int, device: torch.device) -> tuple[torch.Tensor, torch.Tensor]:
        rows = [row for row in self.manifest["entries"]
                if row["split"] == split and row["kind"] == kind and int(row["batch_index"]) == index]
        if len(rows) != 1:
            raise P10PreparedInputError("PREPARED_GEOMETRY_LOOKUP_MISSING")
        row = rows[0]
        payload = torch.load(self.manifest_path.parent / row["relative_path"], map_location="cpu", weights_only=False)
        identity = {key: row[key] for key in ("split", "kind", "batch_index", "records")}
        if (payload.get("cache_id") != self.cache_id
                or payload.get("parent_cache_id") != self.manifest["plan"]["prepared_input_cache_id"]
                or payload.get("identity") != identity):
            raise P10PreparedInputError("PREPARED_GEOMETRY_PAYLOAD_IDENTITY_MISMATCH")
        magnitude, phase = payload.get("magnitude"), payload.get("phase")
        if not isinstance(magnitude, torch.Tensor) or not isinstance(phase, torch.Tensor):
            raise P10PreparedInputError("PREPARED_GEOMETRY_PAYLOAD_INVALID")
        return magnitude.to(device, non_blocking=True), phase.to(device, non_blocking=True)


class _PreparedBatchDataset(Dataset):
    def __init__(self, root: Path, rows: Sequence[Mapping[str, Any]], cache_id: str) -> None:
        self.root = root
        self.rows = [dict(row) for row in rows]
        self.cache_id = cache_id

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, index: int) -> dict[str, Any]:
        row = self.rows[index]
        payload = torch.load(self.root / row["relative_path"], map_location="cpu", weights_only=False)
        identity = {key: row[key] for key in ("split", "kind", "batch_index", "records")}
        if (payload.get("schema_version") != SCHEMA_VERSION or payload.get("cache_id") != self.cache_id
                or payload.get("identity") != identity):
            raise P10PreparedInputError("PREPARED_BATCH_PAYLOAD_IDENTITY_MISMATCH")
        batch, ds = payload.get("batch"), payload.get("ds_raster")
        if not isinstance(batch, dict) or not isinstance(ds, torch.Tensor) or tuple(ds.shape[1:]) != (26, 100, 100):
            raise P10PreparedInputError("PREPARED_BATCH_PAYLOAD_INVALID")
        return {"batch": batch, "ds_raster": ds, "record_count": len(row["records"])}


@dataclass(frozen=True)
class P10PreparedInputCache:
    manifest_path: Path
    manifest: dict[str, Any]

    @classmethod
    def open(cls, manifest_path: str | Path, verify_payloads: bool = True) -> "P10PreparedInputCache":
        path = Path(manifest_path)
        return cls(path, validate_prepared_cache(path, verify_payloads=verify_payloads))

    @property
    def cache_id(self) -> str:
        return str(self.manifest["cache_id"])

    def batches(self, split: str, kind: str, *, workers: int, prefetch: int,
                pin_memory: bool) -> Iterator[dict[str, Any]]:
        rows = [row for row in self.manifest["batches"] if row["split"] == split and row["kind"] == kind]
        dataset = _PreparedBatchDataset(self.manifest_path.parent, rows, self.cache_id)
        options: dict[str, Any] = {
            "batch_size": None,
            "shuffle": False,
            "num_workers": workers,
            "pin_memory": pin_memory,
        }
        if workers:
            options.update({"prefetch_factor": prefetch, "persistent_workers": True})
        yield from DataLoader(dataset, **options)

    def nonlocal_masks(self) -> tuple[list[str], torch.Tensor]:
        row = self.manifest["nonlocal_masks"]
        payload = torch.load(self.manifest_path.parent / row["relative_path"], map_location="cpu", weights_only=False)
        identity, masks = payload.get("identity"), payload.get("masks")
        if identity != {key: row[key] for key in ("scene_ids", "distance_m", "raw_sha256")}:
            raise P10PreparedInputError("PREPARED_NONLOCAL_IDENTITY_MISMATCH")
        if not isinstance(masks, torch.Tensor) or tuple(masks.shape) != (1600, 1600) or masks.dtype != torch.bool:
            raise P10PreparedInputError("PREPARED_NONLOCAL_PAYLOAD_INVALID")
        if hashlib.sha256(masks.numpy().tobytes()).hexdigest() != row["raw_sha256"]:
            raise P10PreparedInputError("PREPARED_NONLOCAL_HASH_MISMATCH")
        return list(identity["scene_ids"]), masks
