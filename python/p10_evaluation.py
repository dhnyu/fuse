"""Canonical P10 revalidation, held-out evaluation, and representation analysis.

P10 is read-only with respect to P9.  It resolves checkpoints through V2 acceptance,
replays the fixed validation retrieval once, then consumes the closed evaluation set.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
import os
import shutil
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import torch
import yaml

from canonical_config import load_strict_yaml
from p6_data import (
    ArtifactCatalog, build_vocabulary, read_fixed_query, read_original_scene,
    tensorize_scene, validate_vocabulary_contract,
)
from p6_model import geometry_fourier_features
from p7_geometry_cache import GeometryCacheReader
from p7_training import collate, to_device
from p9_infrastructure import materialize_hyperparameter_configuration
from p9_model_families import P9MomentumModel, ds_raster_from_batch, family_contract
from p9_selected_fm_campaign import _resolver
from p9_v2_canonical import canonical_json_bytes, canonical_sha256, sha256_file
from p9_v2_downstream import resolve_p10_checkpoint
from p9_v2_ledger import fsync_directory, write_all
from p9_v2_prepared_cache import DSRasterCacheReader, ProductionPreparedData
from p10_prepared_input import (
    P10PreparedGeometryCache, P10PreparedInputCache, build_geometry_cache, build_prepared_cache,
)


SCHEMA_VERSION = "1.0.0"
MODEL_IDS = (
    "cfg_d128", "cmp_a1_geometric_core", "cmp_a2_semantic_enriched",
    "cmp_a3_object_context_enriched", "cmp_a4_raster_complete_non_relational",
    "cmp_a5_relation_type_agnostic", "cmp_ssv_like", "cmp_ds_like",
)


class P10Error(RuntimeError):
    """A stable fail-closed P10 contract or evidence error."""


@dataclass(frozen=True)
class ModelBinding:
    configuration_id: str
    acceptance_id: str
    family: str
    checkpoint_id: str
    checkpoint_path: str
    payload_sha256: str
    manifest_sha256: str
    selected_epoch: int
    expected_retrieval_loss: float
    expected_margin: float
    authority_id: str
    bundle_id: str
    finalization_id: str
    scientific_configuration: dict[str, Any]


def _read_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise P10Error(f"JSON_OBJECT_REQUIRED:{path}")
    return value


def _atomic_file(path: Path, raw: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != raw:
            raise P10Error(f"IMMUTABLE_PUBLICATION_COLLISION:{path}")
        return path
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
            raise P10Error(f"IMMUTABLE_PUBLICATION_COLLISION:{path}")
    finally:
        stage.unlink(missing_ok=True)
    fsync_directory(path.parent)
    return path


def publish_json(path: Path, value: Mapping[str, Any]) -> Path:
    return _atomic_file(path, canonical_json_bytes(dict(value)))


def load_contract(path: str | Path) -> dict[str, Any]:
    value = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if value.get("schema_version") != SCHEMA_VERSION or value.get("contract_name") != "p10-full-evaluation-v1":
        raise P10Error("P10_CONTRACT_VERSION_INVALID")
    if tuple(item.get("configuration_id") for item in value.get("model_set", ())) != MODEL_IDS:
        raise P10Error("P10_MODEL_SET_NOT_CLOSED_EIGHT")
    if len({item["acceptance_id"] for item in value["model_set"]}) != 8:
        raise P10Error("P10_ACCEPTANCE_SET_AMBIGUOUS")
    expected = value["accepted_evaluation"]
    if (expected["split_acceptance_id"], expected["query_index_id"], expected["gallery_id"], expected["mapping_id"]) != (
        "fqsa_3a2581d57c735d2e5ebc91fd", "fqi_55aa7d01752b5f3b1bdbd6c2",
        "fgg_2fa46178130bfc397a9e722c", "fqpm_1534ab2bf81f24a6a94c0cae",
    ):
        raise P10Error("P10_EVALUATION_IDENTITY_MISMATCH")
    return value


def _resolver_inputs(contract: Mapping[str, Any]) -> tuple[Any, list[dict[str, Any]]]:
    status = _read_json(contract["inputs"]["p9b_status"])
    completed = [{
        "configuration_id": "cfg_d128",
        "acceptance_id": contract["model_set"][0]["acceptance_id"],
        "bundle_record": contract["inputs"]["cfg_d128_bundle_record"],
    }, *status["completed"]]
    resolver = _resolver(
        Path(contract["inputs"]["p9_canonical_root"]),
        Path(contract["inputs"]["eligibility"]), completed,
    )
    return resolver, completed


def resolve_model_bindings(contract: Mapping[str, Any]) -> list[ModelBinding]:
    resolver, _ = _resolver_inputs(contract)
    bindings: list[ModelBinding] = []
    for item in contract["model_set"]:
        resolved = resolve_p10_checkpoint(item["acceptance_id"], resolver)
        locator = resolved.payload_locator
        location = locator.get("location", {})
        if locator.get("backend") != "filesystem" or location.get("namespace") not in resolver.locator_roots:
            raise P10Error("P10_CHECKPOINT_LOCATOR_INVALID")
        payload = Path(resolver.locator_roots[location["namespace"]]) / location["relative_path"]
        if not payload.is_file() or sha256_file(payload) != resolved.payload_sha256:
            raise P10Error("P10_CHECKPOINT_HASH_MISMATCH")
        scientific_content = resolved.scientific_configuration.get("content", {})
        if scientific_content.get("configuration_id") != item["configuration_id"]:
            raise P10Error("P10_CONFIGURATION_BINDING_MISMATCH")
        bindings.append(ModelBinding(
            configuration_id=item["configuration_id"], acceptance_id=item["acceptance_id"], family=item["family"],
            checkpoint_id=resolved.checkpoint_id, checkpoint_path=str(payload),
            payload_sha256=resolved.payload_sha256, manifest_sha256=resolved.manifest_sha256,
            selected_epoch=resolved.completed_epoch,
            expected_retrieval_loss=resolved.validation_retrieval_loss,
            expected_margin=resolved.mean_source_separation_margin,
            authority_id=resolved.authority_id, bundle_id=resolved.run_bundle_id,
            finalization_id=resolved.finalization_id,
            scientific_configuration=resolved.scientific_configuration,
        ))
    return bindings


def evaluation_population(contract: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    root = Path(contract["inputs"]["p5_acceptance_root"])
    acceptance = _read_json(root / "fixed_query_acceptance.json")
    evaluation = _read_json(root / "evaluation_acceptance.json")
    if acceptance.get("evaluation_acceptance_id") != contract["accepted_evaluation"]["split_acceptance_id"]:
        raise P10Error("P10_EVALUATION_ACCEPTANCE_MISMATCH")
    if (evaluation.get("query_index_id"), evaluation.get("gallery_id"), evaluation.get("mapping_id")) != (
        contract["accepted_evaluation"]["query_index_id"], contract["accepted_evaluation"]["gallery_id"],
        contract["accepted_evaluation"]["mapping_id"],
    ):
        raise P10Error("P10_EVALUATION_COMPONENT_MISMATCH")
    queries = pq.read_table(root / "evaluation_query_index.parquet").to_pylist()
    galleries = pq.read_table(root / "evaluation_gallery.parquet").to_pylist()
    queries = sorted(queries, key=lambda row: (row["scene_id"], int(row["query_index"])))
    galleries = sorted(galleries, key=lambda row: row["scene_id"])
    if len(queries) != 3200 or len(galleries) != 1600:
        raise P10Error("P10_EVALUATION_POPULATION_INVALID")
    if [row["positive_scene_id"] for row in queries] != [row["scene_id"] for row in galleries for _ in range(2)]:
        raise P10Error("P10_EVALUATION_MAPPING_INVALID")
    return queries, galleries


def make_qualitative_contract(contract: Mapping[str, Any], galleries: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    scene_ids = [str(row["scene_id"]) for row in galleries]
    if scene_ids != sorted(scene_ids) or len(scene_ids) != 1600 or len(set(scene_ids)) != 1600:
        raise P10Error("P10_QUALITATIVE_POPULATION_INVALID")
    population_hash = canonical_sha256(scene_ids)
    version = contract["qualitative"]["contract_version"]
    seed_digest = hashlib.sha256(
        (version + contract["accepted_evaluation"]["split_acceptance_id"] + population_hash).encode("utf-8")
    ).hexdigest()
    seed = int.from_bytes(bytes.fromhex(seed_digest)[:8], "big", signed=False)
    generator = np.random.Generator(np.random.PCG64(seed))
    positions = generator.choice(len(scene_ids), size=10, replace=False).tolist()
    selected = [scene_ids[index] for index in positions]
    preimage = {
        "schema_version": SCHEMA_VERSION, "artifact_type": "p10_qualitative_query_contract",
        "contract_version": version, "evaluation_split_acceptance_id": contract["accepted_evaluation"]["split_acceptance_id"],
        "ordered_population_sha256": population_hash, "population_count": 1600,
        "seed_derivation": "sha256_utf8(contract_version||evaluation_split_acceptance_id||ordered_population_sha256)",
        "seed_digest": seed_digest, "seed_unsigned_big_endian_u64_decimal": str(seed),
        "prng": "numpy.random.PCG64", "numpy_version": contract["qualitative"]["numpy_version"],
        "sampling": "choice_without_replacement_preserve_draw_order", "selected_indices": positions,
        "selected_scene_ids": selected, "standard_candidate_count": 1599,
        "nonlocal_exclusion_distance_m": 2000.0,
        "reported_rank_positions": ["top", "one_third", "two_thirds", "bottom"],
    }
    digest = canonical_sha256(preimage)
    return {**preimage, "contract_id": f"p10qq_{digest[:24]}", "content_sha256": digest, "status": "COMMITTED"}


def make_analysis_contract(contract: Mapping[str, Any]) -> dict[str, Any]:
    preimage = {"schema_version": SCHEMA_VERSION, "artifact_type": "p10_representation_analysis_contract", **contract["analysis"]}
    digest = canonical_sha256(preimage)
    return {**preimage, "contract_id": f"p10ana_{digest[:24]}", "content_sha256": digest, "status": "COMMITTED"}


def make_authority(contract: Mapping[str, Any], bindings: Sequence[ModelBinding], qualitative: Mapping[str, Any], analysis: Mapping[str, Any]) -> dict[str, Any]:
    implementation = {
        "p10_evaluation.py": sha256_file(Path(__file__)),
        "p9_model_families.py": sha256_file(Path(__file__).with_name("p9_model_families.py")),
        "p6_data.py": sha256_file(Path(__file__).with_name("p6_data.py")),
        "config": canonical_sha256(contract),
    }
    preimage = {
        "schema_version": SCHEMA_VERSION, "artifact_type": "p10_evaluation_authority",
        "scope": "CLOSED_EIGHT_MODEL_FULL_P10", "models": [asdict(item) for item in bindings],
        "evaluation": contract["accepted_evaluation"], "validation_revalidation": contract["validation_revalidation"],
        "qualitative_contract_id": qualitative["contract_id"], "analysis_contract_id": analysis["contract_id"],
        "implementation": implementation,
        "permissions": {"validation_revalidations": 8, "heldout_campaigns": 1, "training": 0,
                        "optimizer_updates": 0, "checkpoint_writes": 0, "p11": 0},
    }
    digest = canonical_sha256(preimage)
    return {**preimage, "authority_id": f"p10auth_{digest[:24]}", "content_sha256": digest, "status": "AUTHORIZED"}


def _rows(contract: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    hyper = _read_json(contract["inputs"]["hyperparameter_matrix"])["rows"]
    comparison = _read_json(contract["inputs"]["comparison_matrix"])["rows"]
    return {row["configuration_id"]: row for row in [*hyper, *comparison]}


def _model_values(contract: Mapping[str, Any], binding: ModelBinding, row: Mapping[str, Any]) -> dict[str, Any]:
    training = yaml.safe_load(Path(contract["inputs"]["training_config"]).read_text(encoding="utf-8"))
    model = load_strict_yaml(contract["inputs"]["model_config"])
    routed = materialize_hyperparameter_configuration(row, training, model)
    vocabulary = build_vocabulary(contract["inputs"]["categories"])
    return {"model_config": routed["model"], "vocabulary": vocabulary,
            "vocabulary_sizes": validate_vocabulary_contract(vocabulary), "family": binding.family}


def _device(contract: Mapping[str, Any]) -> torch.device:
    if not torch.cuda.is_available():
        raise P10Error("P10_CUDA_UNAVAILABLE")
    os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
    torch.use_deterministic_algorithms(True, warn_only=False)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    torch.set_num_threads(1)
    device = torch.device(contract["execution"]["device"])
    torch.cuda.set_device(device)
    return device


def _load_model(binding: ModelBinding, values: Mapping[str, Any], device: torch.device) -> P9MomentumModel:
    checkpoint = torch.load(binding.checkpoint_path, map_location="cpu", weights_only=False)
    if checkpoint.get("configuration_identity") != binding.scientific_configuration.get("content_sha256"):
        raise P10Error("P10_CHECKPOINT_INTERNAL_CONFIGURATION_MISMATCH")
    model = P9MomentumModel(values["model_config"], values["vocabulary_sizes"], binding.family).to(device)
    model.online.load_state_dict(checkpoint["online_model"], strict=True)
    model.online.eval()
    return model


def _metric(queries: torch.Tensor, galleries: torch.Tensor, temperature: float) -> tuple[dict[str, Any], np.ndarray]:
    similarities = queries @ galleries.T
    positive = torch.arange(galleries.shape[0]).repeat_interleave(2)
    order = torch.argsort(similarities, dim=1, descending=True, stable=True)
    ranks = torch.nonzero(order == positive[:, None], as_tuple=False)[:, 1] + 1
    positive_values = similarities[torch.arange(len(queries)), positive]
    masked = similarities.clone(); masked[torch.arange(len(queries)), positive] = -torch.inf
    result = {
        "retrieval_loss": float(torch.nn.functional.cross_entropy(similarities / temperature, positive)),
        "mean_source_separation_margin": float((positive_values - masked.max(1).values).mean()),
        "MRR": float((1.0 / ranks.float()).mean()), "HIT@1": float((ranks <= 1).float().mean()),
        "HIT@5": float((ranks <= 5).float().mean()), "HIT@10": float((ranks <= 10).float().mean()),
        "query_count": int(len(queries)), "gallery_count": int(len(galleries)),
    }
    return result, order.numpy().astype(np.int32, copy=False)


def _dynamic_catalog(contract: Mapping[str, Any]) -> ArtifactCatalog:
    p5 = _read_json(Path(contract["inputs"]["p5_acceptance_root"]) / "fixed_query_acceptance.json")
    p4_paths = list((Path(contract["inputs"]["p4_root"]) / "acceptance").glob("*/augmentation_bank_acceptance.json"))
    if len(p4_paths) != 1:
        raise P10Error("P10_P4_ACCEPTANCE_AMBIGUOUS")
    p4 = _read_json(p4_paths[0])
    return ArtifactCatalog(
        {key: contract["inputs"][f"{key}_root"] for key in ("p3", "p4", "p5")},
        {"p3_cache_id": p5["parent_cache_id"], "p4_master_bank_id": p4["bank_id"],
         "p5_query_authority_id": p5["query_authority_id"]}, verify=True,
    )


def _embed(
    model: P9MomentumModel, values: Mapping[str, Any], records: Sequence[tuple[str, str, int | None]],
    contract: Mapping[str, Any], device: torch.device, prepared: ProductionPreparedData | None,
    catalog: ArtifactCatalog | None,
) -> tuple[torch.Tensor, np.ndarray]:
    preprocessing = _read_json(contract["inputs"]["preprocessing"])
    geometry_cache = None
    ds_cache = None
    if prepared is not None:
        cache_root = Path(yaml.safe_load(Path("config/p9_v2_training_controller.yml").read_text())["roots"]["production_cache"])
        geometry_cache = GeometryCacheReader(cache_root / "geometry/geometry_cache_manifest.json", 4 * 1024**3)
        ds_cache = DSRasterCacheReader(cache_root)
    vectors: list[torch.Tensor] = []
    centers: list[np.ndarray] = []
    batch_size = int(contract["execution"]["batch_size"])
    with torch.inference_mode():
        for start in range(0, len(records), batch_size):
            selected = records[start:start + batch_size]
            if prepared is not None:
                samples = [prepared.sample(role, scene, view) for role, scene, view in selected]
            else:
                assert catalog is not None
                scenes = [read_fixed_query(catalog, "evaluation", scene, int(view)) if role == "evaluation_query"
                          else read_original_scene(catalog, scene) for role, scene, view in selected]
                samples = []
                for scene in scenes:
                    sample = tensorize_scene(scene, preprocessing, values["vocabulary"])
                    sample["scene_center_5186"] = torch.tensor(scene["center"], dtype=torch.float64)
                    samples.append(sample)
            cpu = collate(samples, values["vocabulary"])
            centers.extend(cpu["scene_center_5186"].numpy())
            role = selected[0][0]
            ds = ((ds_cache.batch(cpu, role, device) if ds_cache is not None else ds_raster_from_batch(cpu).to(device))
                  if values["family"] == "DS" else None)
            batch = to_device(cpu, device)
            geometry = None
            if "geometry" in family_contract(values["family"]).modalities:
                geometry = (geometry_cache.batch(batch, role, device) if geometry_cache is not None else
                            geometry_fourier_features(batch, {"geometry": values["model_config"]["model"]["geometry"]}, device))
            output = model.online(batch, geometry, ds)["scene_embedding"]
            vectors.append(torch.nn.functional.normalize(output, dim=1).cpu())
    return torch.cat(vectors), np.asarray(centers, dtype=np.float64)


def _to_device_nonblocking(value: Any, device: torch.device, key: str = "") -> Any:
    if isinstance(value, torch.Tensor):
        if key in {"part_coordinates_xy_m_scientific", "ring_coordinates_xy_m_scientific"}:
            return value
        return value.to(device, non_blocking=True)
    if isinstance(value, dict):
        return {name: _to_device_nonblocking(item, device, name) for name, item in value.items()}
    return value


def _embed_prepared(
    model: P9MomentumModel,
    values: Mapping[str, Any],
    contract: Mapping[str, Any],
    device: torch.device,
    cache: P10PreparedInputCache,
    split: str,
    prepared_geometry: P10PreparedGeometryCache | None = None,
) -> tuple[torch.Tensor, np.ndarray]:
    """Embed fixed prepared batches; no dynamic source fallback is permitted."""
    vectors: list[torch.Tensor] = []
    centers: list[np.ndarray] = []
    options = contract["prepared_input"]["loader"]
    accepted_geometry = None
    if split == "validation":
        accepted_geometry = GeometryCacheReader(
            Path(contract["inputs"]["p9_production_cache"]) / "geometry" / "geometry_cache_manifest.json",
            4 * 1024**3,
        )
    with torch.inference_mode():
        for kind in ("query", "gallery"):
            batch_count = sum(
                row["split"] == split and row["kind"] == kind
                for row in cache.manifest["batches"]
            )
            print(
                f"P10_PREPARED_INPUT_ACTIVE split={split} kind={kind} "
                f"batches={batch_count} cache={cache.cache_id}",
                file=sys.stderr, flush=True,
            )
            iterator = cache.batches(
                split,
                kind,
                workers=int(options["workers"]),
                prefetch=int(options["prefetch"]),
                pin_memory=bool(options["pin_memory"]),
            )
            for batch_index, payload in enumerate(iterator):
                cpu = payload["batch"]
                centers.extend(cpu["scene_center_5186"].numpy())
                ds = payload["ds_raster"].to(device, non_blocking=True) if values["family"] == "DS" else None
                batch = _to_device_nonblocking(cpu, device)
                geometry = None
                if "geometry" in family_contract(values["family"]).modalities:
                    if split == "validation":
                        assert accepted_geometry is not None
                        geometry = accepted_geometry.batch(batch, f"validation_{kind}", device)
                    else:
                        if prepared_geometry is None:
                            raise P10Error("P10_PREPARED_GEOMETRY_REQUIRED_NO_FALLBACK")
                        geometry = prepared_geometry.batch(split, kind, batch_index, device)
                output = model.online(batch, geometry, ds)["scene_embedding"]
                vectors.append(torch.nn.functional.normalize(output, dim=1).cpu())
                completed = batch_index + 1
                if completed % 50 == 0 or completed == batch_count:
                    print(
                        f"P10_PREPARED_PROGRESS split={split} kind={kind} "
                        f"completed={completed}/{batch_count}",
                        file=sys.stderr, flush=True,
                    )
    return torch.cat(vectors), np.asarray(centers, dtype=np.float64)


def _save_arrays(path: Path, **arrays: np.ndarray) -> None:
    if path.exists():
        with np.load(path) as existing:
            if set(existing.files) != set(arrays) or any(not np.array_equal(existing[key], value) for key, value in arrays.items()):
                raise P10Error(f"IMMUTABLE_ARRAY_PUBLICATION_COLLISION:{path}")
        return
    temporary = path.with_name(f".{path.name}.incomplete-{os.getpid()}")
    with temporary.open("wb") as stream:
        np.savez_compressed(stream, **arrays)
        stream.flush(); os.fsync(stream.fileno())
    try:
        os.link(temporary, path)
    except FileExistsError:
        with np.load(path) as existing:
            if set(existing.files) != set(arrays) or any(not np.array_equal(existing[key], value) for key, value in arrays.items()):
                raise P10Error(f"IMMUTABLE_ARRAY_PUBLICATION_COLLISION:{path}")
    finally:
        temporary.unlink(missing_ok=True)
    fsync_directory(path.parent)


def _load_committed_model_evaluation(
    root: Path, authority: Mapping[str, Any], binding: ModelBinding,
    prepared_cache: P10PreparedInputCache, prepared_geometry: P10PreparedGeometryCache,
) -> dict[str, Any] | None:
    committed = root / "evaluation.json"
    if not committed.is_file():
        return None
    result = _read_json(committed)
    if (result.get("status") != "PASS"
            or result.get("authority_id") != authority["authority_id"]
            or result.get("configuration_id") != binding.configuration_id
            or result.get("acceptance_id") != binding.acceptance_id
            or result.get("checkpoint_id") != binding.checkpoint_id
            or result.get("prepared_input_cache_id") != prepared_cache.cache_id
            or result.get("prepared_geometry_cache_id") != prepared_geometry.cache_id):
        raise P10Error(f"P10_COMMITTED_MODEL_EVALUATION_MISMATCH:{binding.configuration_id}")
    arrays_path = root / "evaluation_embeddings_ranks_analysis.npz"
    qualitative_path = root / "qualitative_retrieval.json"
    if not arrays_path.is_file() or not qualitative_path.is_file():
        raise P10Error(f"P10_COMMITTED_MODEL_EVALUATION_INCOMPLETE:{binding.configuration_id}")
    with np.load(arrays_path) as arrays:
        expected = {
            "embedding_sha256": hashlib.sha256(arrays["embeddings"].tobytes()).hexdigest(),
            "rank_sha256": hashlib.sha256(arrays["ranks"].tobytes()).hexdigest(),
            "umap_sha256": hashlib.sha256(arrays["umap"].astype(np.float32).tobytes()).hexdigest(),
            "hdbscan_labels_sha256": hashlib.sha256(arrays["hdbscan_labels"].astype(np.int32).tobytes()).hexdigest(),
            "hdbscan_probabilities_sha256": hashlib.sha256(
                arrays["hdbscan_probabilities"].astype(np.float32).tobytes()
            ).hexdigest(),
        }
    if any(result.get(key) != value for key, value in expected.items()):
        raise P10Error(f"P10_COMMITTED_MODEL_ARRAY_HASH_MISMATCH:{binding.configuration_id}")
    if result.get("qualitative_sha256") != canonical_sha256(_read_json(qualitative_path)):
        raise P10Error(f"P10_COMMITTED_MODEL_QUALITATIVE_HASH_MISMATCH:{binding.configuration_id}")
    return result


def revalidate_model(contract: Mapping[str, Any], authority: Mapping[str, Any], binding: ModelBinding,
                     row: Mapping[str, Any], output: Path) -> dict[str, Any]:
    values = _model_values(contract, binding, row); device = _device(contract)
    model = _load_model(binding, values, device)
    cache_root = yaml.safe_load(Path("config/p9_v2_training_controller.yml").read_text())["roots"]["production_cache"]
    prepared = ProductionPreparedData(cache_root, row["scientific"]["intensity"], int(row["scientific"]["effective_k"]))
    scenes = prepared.validation_scenes
    records = [("validation_query", scene, view) for scene in scenes for view in (0, 1)]
    records += [("validation_gallery", scene, None) for scene in scenes]
    started = time.monotonic(); embeddings, centers = _embed(model, values, records, contract, device, prepared, None)
    metrics, ranks = _metric(embeddings[:800], embeddings[800:], float(contract["execution"]["temperature"]))
    loss_delta = metrics["retrieval_loss"] - binding.expected_retrieval_loss
    margin_delta = metrics["mean_source_separation_margin"] - binding.expected_margin
    gate = contract["validation_revalidation"]
    if abs(loss_delta) > float(gate["retrieval_loss_atol"]) or abs(margin_delta) > float(gate["margin_atol"]):
        raise P10Error(f"P10_VALIDATION_REVALIDATION_MISMATCH:{binding.configuration_id}:{loss_delta}:{margin_delta}")
    result = {
        "schema_version": SCHEMA_VERSION, "artifact_type": "p10_validation_revalidation",
        "authority_id": authority["authority_id"], "configuration_id": binding.configuration_id,
        "acceptance_id": binding.acceptance_id, "checkpoint_id": binding.checkpoint_id,
        "expected": {"retrieval_loss": binding.expected_retrieval_loss, "mean_source_separation_margin": binding.expected_margin},
        "reproduced": metrics, "delta": {"retrieval_loss": loss_delta, "mean_source_separation_margin": margin_delta},
        "tolerance": {"retrieval_loss_atol": gate["retrieval_loss_atol"], "margin_atol": gate["margin_atol"]},
        "embedding_sha256": hashlib.sha256(embeddings.numpy().tobytes()).hexdigest(),
        "rank_sha256": hashlib.sha256(ranks.tobytes()).hexdigest(),
        "status": "PASS", "heldout_consumption_count": 0,
    }
    root = output / binding.configuration_id; root.mkdir(parents=True, exist_ok=True)
    _save_arrays(root / "validation_embeddings_and_ranks.npz", embeddings=embeddings.numpy(), centers=centers, ranks=ranks)
    publish_json(root / "validation_revalidation.json", result)
    del model, embeddings
    torch.cuda.empty_cache()
    return result


def make_consumption(authority: Mapping[str, Any], validations: Sequence[Mapping[str, Any]], contract: Mapping[str, Any]) -> dict[str, Any]:
    if len(validations) != 8 or any(item.get("status") != "PASS" for item in validations):
        raise P10Error("P10_PREHELDOUT_GATE_INCOMPLETE")
    preimage = {
        "schema_version": SCHEMA_VERSION, "artifact_type": "p10_heldout_consumption",
        "authority_id": authority["authority_id"], "evaluation_split_acceptance_id": contract["accepted_evaluation"]["split_acceptance_id"],
        "closed_model_acceptance_ids": [item["acceptance_id"] for item in authority["models"]],
        "validation_gate_sha256": canonical_sha256(list(validations)), "transition": {"before": 0, "after": 1},
    }
    digest = canonical_sha256(preimage)
    return {**preimage, "consumption_id": f"p10cons_{digest[:24]}", "content_sha256": digest, "status": "COMMITTED"}


def _qualitative(binding: ModelBinding, gallery_embeddings: torch.Tensor, centers: np.ndarray,
                 scene_ids: Sequence[str], qualitative: Mapping[str, Any],
                 nonlocal_masks: torch.Tensor | None = None) -> dict[str, Any]:
    index = {scene: position for position, scene in enumerate(scene_ids)}
    output = []
    for scene in qualitative["selected_scene_ids"]:
        position = index[scene]
        similarity = gallery_embeddings[position] @ gallery_embeddings.T
        standard = [i for i in range(len(scene_ids)) if i != position]
        standard.sort(key=lambda i: (-float(similarity[i]), scene_ids[i]))
        if nonlocal_masks is None:
            distances = np.sqrt(((centers - centers[position]) ** 2).sum(1))
            mask = distances >= 2000.0
        else:
            mask = nonlocal_masks[position].numpy()
        nonlocal_indices = [i for i in standard if bool(mask[i])]
        def selected(indices: list[int]) -> list[dict[str, Any]]:
            positions = [0, math.ceil(len(indices) / 3) - 1, math.ceil(2 * len(indices) / 3) - 1, len(indices) - 1]
            return [{"rank": rank + 1, "scene_id": scene_ids[indices[rank]], "similarity": float(similarity[indices[rank]])} for rank in positions]
        output.append({"query_scene_id": scene, "standard_candidate_count": len(standard),
                       "standard_rank_positions": selected(standard), "nonlocal_candidate_count": len(nonlocal_indices),
                       "nonlocal_rank_positions": selected(nonlocal_indices)})
    return {"configuration_id": binding.configuration_id, "checkpoint_id": binding.checkpoint_id,
            "qualitative_contract_id": qualitative["contract_id"], "queries": output}


def evaluate_model(contract: Mapping[str, Any], authority: Mapping[str, Any], binding: ModelBinding,
                   row: Mapping[str, Any], qualitative: Mapping[str, Any], output: Path,
                   prepared_cache: P10PreparedInputCache,
                   prepared_geometry: P10PreparedGeometryCache) -> dict[str, Any]:
    root = output / binding.configuration_id
    existing = _load_committed_model_evaluation(
        root, authority, binding, prepared_cache, prepared_geometry
    )
    if existing is not None:
        return existing
    values = _model_values(contract, binding, row); device = _device(contract); model = _load_model(binding, values, device)
    queries, galleries = evaluation_population(contract)
    started = time.monotonic()
    embeddings, centers = _embed_prepared(
        model, values, contract, device, prepared_cache, "evaluation", prepared_geometry
    )
    metrics, ranks = _metric(embeddings[:3200], embeddings[3200:], float(contract["execution"]["temperature"]))
    gallery_embeddings = embeddings[3200:]
    mask_scenes, masks = prepared_cache.nonlocal_masks()
    gallery_scenes = [row["scene_id"] for row in galleries]
    if mask_scenes != gallery_scenes:
        raise P10Error("P10_PREPARED_NONLOCAL_SCENE_MISMATCH")
    qualitative_result = _qualitative(
        binding, gallery_embeddings, centers[3200:], gallery_scenes, qualitative, masks
    )
    # Fixed descriptive analyses. HDBSCAN is fitted in original representation space.
    import hdbscan
    import umap
    analysis = contract["analysis"]
    umap_args = {key: value for key, value in analysis["umap"].items() if key not in {"package", "version"}}
    coordinates = umap.UMAP(**umap_args).fit_transform(gallery_embeddings.numpy())
    cluster_args = {key: value for key, value in analysis["hdbscan"].items() if key not in {"package", "version"}}
    clusterer = hdbscan.HDBSCAN(**cluster_args).fit(gallery_embeddings.numpy())
    norms = torch.linalg.vector_norm(gallery_embeddings, dim=1)
    result = {
        "schema_version": SCHEMA_VERSION, "artifact_type": "p10_model_evaluation",
        "authority_id": authority["authority_id"], "configuration_id": binding.configuration_id,
        "acceptance_id": binding.acceptance_id, "checkpoint_id": binding.checkpoint_id,
        "evaluation_split_acceptance_id": contract["accepted_evaluation"]["split_acceptance_id"],
        "metrics": metrics, "embedding_dimension": int(embeddings.shape[1]),
        "embedding_sha256": hashlib.sha256(embeddings.numpy().tobytes()).hexdigest(),
        "rank_sha256": hashlib.sha256(ranks.tobytes()).hexdigest(),
        "representation_summary": {"gallery_mean_norm": float(norms.mean()), "gallery_norm_sd": float(norms.std(unbiased=False)),
                                   "hdbscan_cluster_count": len(set(clusterer.labels_)) - (1 if -1 in clusterer.labels_ else 0),
                                   "hdbscan_noise_count": int((clusterer.labels_ == -1).sum())},
        "qualitative_sha256": canonical_sha256(qualitative_result),
        "umap_sha256": hashlib.sha256(coordinates.astype(np.float32).tobytes()).hexdigest(),
        "hdbscan_labels_sha256": hashlib.sha256(clusterer.labels_.astype(np.int32).tobytes()).hexdigest(),
        "hdbscan_probabilities_sha256": hashlib.sha256(clusterer.probabilities_.astype(np.float32).tobytes()).hexdigest(),
        "prepared_input_cache_id": prepared_cache.cache_id,
        "prepared_geometry_cache_id": prepared_geometry.cache_id,
        "timing": {"evaluation_wall_seconds": time.monotonic() - started},
        "status": "PASS", "training_count": 0, "optimizer_update_count": 0, "checkpoint_write_count": 0,
    }
    root.mkdir(parents=True, exist_ok=True)
    _save_arrays(root / "evaluation_embeddings_ranks_analysis.npz", embeddings=embeddings.numpy(), centers=centers,
                 ranks=ranks, umap=coordinates.astype(np.float32), hdbscan_labels=clusterer.labels_.astype(np.int32),
                 hdbscan_probabilities=clusterer.probabilities_.astype(np.float32))
    publish_json(root / "qualitative_retrieval.json", qualitative_result)
    publish_json(root / "evaluation.json", result)
    del model, embeddings
    torch.cuda.empty_cache()
    return result


def _installed_versions() -> dict[str, str]:
    return {name: importlib.metadata.version(name) for name in (
        "torch", "numpy", "scikit-learn", "umap-learn", "hdbscan", "pyarrow"
    )}


def make_execution_attempt(
    contract: Mapping[str, Any], authority: Mapping[str, Any], consumption: Mapping[str, Any],
    cache: P10PreparedInputCache,
    geometry: P10PreparedGeometryCache,
) -> dict[str, Any]:
    expected_versions = dict(contract["prepared_input"]["environment"])
    observed_versions = _installed_versions()
    if observed_versions != expected_versions:
        raise P10Error(f"P10_EXECUTION_ENVIRONMENT_MISMATCH:{observed_versions}")
    preimage = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "p10_execution_attempt",
        "base_authority_id": authority["authority_id"],
        "base_authority_sha256": authority["content_sha256"],
        "consumption_id": consumption["consumption_id"],
        "consumption_sha256": consumption["content_sha256"],
        "reason": "OPERATOR_REQUESTED_PERFORMANCE_REMEDIATION_P10_INPUT_PIPELINE",
        "closed_model_acceptance_ids": [item["acceptance_id"] for item in authority["models"]],
        "qualitative_contract_id": authority["qualitative_contract_id"],
        "analysis_contract_id": authority["analysis_contract_id"],
        "prepared_input_cache_id": cache.cache_id,
        "prepared_input_plan_sha256": cache.manifest["plan"]["content_sha256"],
        "prepared_geometry_cache_id": geometry.cache_id,
        "prepared_geometry_plan_sha256": geometry.manifest["plan"]["content_sha256"],
        "implementation": {
            "p10_evaluation.py": sha256_file(Path(__file__)),
            "p10_prepared_input.py": sha256_file(Path(__file__).with_name("p10_prepared_input.py")),
        },
        "environment": observed_versions,
        "permissions": {"heldout_reexecution_same_contract": 1, "training": 0, "optimizer_updates": 0,
                        "checkpoint_writes": 0, "model_set_changes": 0, "p11": 0},
    }
    digest = canonical_sha256(preimage)
    return {**preimage, "attempt_id": f"p10exec_{digest[:24]}", "content_sha256": digest,
            "status": "AUTHORIZED_SAME_CLOSED_CONTRACT_REEXECUTION"}


def record_interrupted_execution(contract: Mapping[str, Any]) -> dict[str, Any]:
    publication = Path(contract["publication_root"])
    reexecution = contract["reexecution"]
    authority = _read_json(publication / "authorities" / f"{reexecution['authority_id']}.json")
    consumption = _read_json(publication / "consumption" / f"{reexecution['consumption_id']}.json")
    completed = []
    for configuration_id in MODEL_IDS:
        path = publication / "evaluations" / authority["authority_id"] / configuration_id / "evaluation.json"
        if path.is_file():
            completed.append({"configuration_id": configuration_id, "sha256": sha256_file(path)})
    expected_completed = list(reexecution["interrupted_completed_models"])
    if [item["configuration_id"] for item in completed] != expected_completed:
        raise P10Error("P10_INTERRUPTED_COMPLETION_SET_MISMATCH")
    preimage = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "p10_execution_interruption",
        "authority_id": authority["authority_id"],
        "authority_sha256": authority["content_sha256"],
        "consumption_id": consumption["consumption_id"],
        "consumption_sha256": consumption["content_sha256"],
        "tmux_session": reexecution["interrupted_tmux_session"],
        "reason": reexecution["interruption_reason"],
        "completed_model_evaluations": completed,
        "incomplete_models": [name for name in MODEL_IDS if name not in expected_completed],
        "training_count": 0,
        "optimizer_update_count": 0,
        "checkpoint_write_count": 0,
        "status": "INTERRUPTED_PRESERVED",
    }
    digest = canonical_sha256(preimage)
    result = {**preimage, "interruption_id": f"p10int_{digest[:24]}", "content_sha256": digest}
    publish_json(publication / "interruptions" / f"{result['interruption_id']}.json", result)
    return result


def _load_base_evidence(contract: Mapping[str, Any], bindings: Sequence[ModelBinding],
                        qualitative: Mapping[str, Any], analysis: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    publication = Path(contract["publication_root"])
    base = contract["reexecution"]
    authority = _read_json(publication / "authorities" / f"{base['authority_id']}.json")
    consumption = _read_json(publication / "consumption" / f"{base['consumption_id']}.json")
    if (authority.get("authority_id") != base["authority_id"]
            or authority.get("models") != [asdict(item) for item in bindings]
            or authority.get("qualitative_contract_id") != qualitative["contract_id"]
            or authority.get("analysis_contract_id") != analysis["contract_id"]):
        raise P10Error("P10_BASE_AUTHORITY_CONTRACT_MISMATCH")
    if (consumption.get("authority_id") != authority["authority_id"]
            or consumption.get("transition") != {"before": 0, "after": 1}
            or consumption.get("status") != "COMMITTED"):
        raise P10Error("P10_BASE_CONSUMPTION_INVALID")
    validation_root = publication / "validation_revalidation" / authority["authority_id"]
    validations = [_read_json(validation_root / item.configuration_id / "validation_revalidation.json")
                   for item in bindings]
    if len(validations) != 8 or any(item.get("status") != "PASS" for item in validations):
        raise P10Error("P10_BASE_VALIDATION_GATE_INVALID")
    return authority, consumption, validations


def finalize_p10_attempt(authority: Mapping[str, Any], attempt: Mapping[str, Any],
                         consumption: Mapping[str, Any], validations: Sequence[Mapping[str, Any]],
                         evaluations: Sequence[Mapping[str, Any]], qualitative: Mapping[str, Any],
                         analysis: Mapping[str, Any], output: Path) -> dict[str, Any]:
    if len(evaluations) != 8 or any(item.get("status") != "PASS" for item in evaluations):
        raise P10Error("P10_MODEL_EVALUATION_INCOMPLETE")
    comparison = [{"configuration_id": item["configuration_id"], **item["metrics"]} for item in evaluations]
    preimage = {
        "schema_version": SCHEMA_VERSION, "artifact_type": "p10_evaluation_acceptance",
        "authority_id": authority["authority_id"], "execution_attempt_id": attempt["attempt_id"],
        "consumption_id": consumption["consumption_id"],
        "qualitative_contract_id": qualitative["contract_id"], "analysis_contract_id": analysis["contract_id"],
        "validation_revalidation_sha256": canonical_sha256(list(validations)),
        "model_evaluation_sha256": canonical_sha256(list(evaluations)), "comparison": comparison,
        "fixed_full_model": "cfg_d128", "selection_reopened": False, "p11_execution_count": 0,
    }
    digest = canonical_sha256(preimage)
    acceptance = {**preimage, "acceptance_id": f"p10acc_{digest[:24]}",
                  "content_sha256": digest, "status": "PASS"}
    publish_json(output / "final_comparison.json", {"models": comparison, "reference": "cfg_d128"})
    publish_json(output / "commit" / "evaluation_acceptance.json", acceptance)
    return acceptance


def run_p10_reexecution(contract_path: str | Path) -> dict[str, Any]:
    contract = load_contract(contract_path)
    interruption = record_interrupted_execution(contract)
    bindings = resolve_model_bindings(contract)
    _, galleries = evaluation_population(contract)
    qualitative = make_qualitative_contract(contract, galleries)
    analysis = make_analysis_contract(contract)
    authority, consumption, validations = _load_base_evidence(contract, bindings, qualitative, analysis)
    cache_manifest = build_prepared_cache(contract)
    cache = P10PreparedInputCache.open(cache_manifest)
    geometry_manifest = build_geometry_cache(contract, cache_manifest)
    geometry = P10PreparedGeometryCache.open(geometry_manifest)
    attempt = make_execution_attempt(contract, authority, consumption, cache, geometry)
    publication = Path(contract["publication_root"])
    attempt_root = publication / "execution_attempts" / attempt["attempt_id"]
    publish_json(attempt_root / "attempt.json", attempt)
    committed = attempt_root / "commit" / "evaluation_acceptance.json"
    if committed.is_file():
        evaluations = [_read_json(attempt_root / "evaluations" / item.configuration_id / "evaluation.json")
                       for item in bindings]
        return {"authority": authority, "interruption": interruption,
                "execution_attempt": attempt, "consumption": consumption,
                "evaluations": evaluations, "acceptance": _read_json(committed),
                "prepared_input_manifest": str(cache_manifest), "prepared_geometry_manifest": str(geometry_manifest),
                "result_root": str(attempt_root),
                "idempotent_reuse": True}
    rows = _rows(contract)
    evaluations = []
    for binding in bindings:
        print(f"P10 prepared held-out evaluation: {binding.configuration_id}", file=sys.stderr, flush=True)
        evaluations.append(evaluate_model(
            contract, authority, binding, rows[binding.configuration_id], qualitative,
            attempt_root / "evaluations", cache, geometry,
        ))
    acceptance = finalize_p10_attempt(
        authority, attempt, consumption, validations, evaluations, qualitative, analysis, attempt_root
    )
    return {"authority": authority, "interruption": interruption,
            "execution_attempt": attempt, "consumption": consumption,
            "evaluations": evaluations, "acceptance": acceptance,
            "prepared_input_manifest": str(cache_manifest), "prepared_geometry_manifest": str(geometry_manifest),
            "result_root": str(attempt_root)}


def finalize_p10(authority: Mapping[str, Any], consumption: Mapping[str, Any], validations: Sequence[Mapping[str, Any]],
                 evaluations: Sequence[Mapping[str, Any]], qualitative: Mapping[str, Any], analysis: Mapping[str, Any],
                 output: Path) -> dict[str, Any]:
    if len(evaluations) != 8 or any(item.get("status") != "PASS" for item in evaluations):
        raise P10Error("P10_MODEL_EVALUATION_INCOMPLETE")
    comparison = [{"configuration_id": item["configuration_id"], **item["metrics"]} for item in evaluations]
    preimage = {
        "schema_version": SCHEMA_VERSION, "artifact_type": "p10_evaluation_acceptance",
        "authority_id": authority["authority_id"], "consumption_id": consumption["consumption_id"],
        "qualitative_contract_id": qualitative["contract_id"], "analysis_contract_id": analysis["contract_id"],
        "validation_revalidation_sha256": canonical_sha256(list(validations)),
        "model_evaluation_sha256": canonical_sha256(list(evaluations)), "comparison": comparison,
        "fixed_full_model": "cfg_d128", "selection_reopened": False, "p11_execution_count": 0,
    }
    digest = canonical_sha256(preimage)
    acceptance = {**preimage, "acceptance_id": f"p10acc_{digest[:24]}", "content_sha256": digest, "status": "PASS"}
    publish_json(output / "final_comparison.json", {"models": comparison, "reference": "cfg_d128"})
    publish_json(output / "commit" / "evaluation_acceptance.json", acceptance)
    return acceptance


def run_p10(contract_path: str | Path) -> dict[str, Any]:
    contract = load_contract(contract_path)
    bindings = resolve_model_bindings(contract)
    _, galleries = evaluation_population(contract)  # IDs/metadata only; no held-out payload is opened.
    qualitative = make_qualitative_contract(contract, galleries)
    analysis = make_analysis_contract(contract)
    authority = make_authority(contract, bindings, qualitative, analysis)
    publication = Path(contract["publication_root"])
    publish_json(publication / "qualitative" / f"{qualitative['contract_id']}.json", qualitative)
    publish_json(publication / "analysis" / f"{analysis['contract_id']}.json", analysis)
    publish_json(publication / "authorities" / f"{authority['authority_id']}.json", authority)
    result_root = publication / "evaluations" / authority["authority_id"]
    committed = result_root / "commit" / "evaluation_acceptance.json"
    if committed.is_file():
        validations = [_read_json(publication / "validation_revalidation" / authority["authority_id"] /
                                  binding.configuration_id / "validation_revalidation.json") for binding in bindings]
        evaluations = [_read_json(result_root / binding.configuration_id / "evaluation.json") for binding in bindings]
        consumption_id = _read_json(committed)["consumption_id"]
        consumption = _read_json(publication / "consumption" / f"{consumption_id}.json")
        return {"authority": authority, "qualitative": qualitative, "analysis": analysis, "consumption": consumption,
                "validation_revalidations": validations, "evaluations": evaluations, "acceptance": _read_json(committed),
                "result_root": str(result_root), "idempotent_reuse": True}
    rows = _rows(contract)
    validation_root = publication / "validation_revalidation" / authority["authority_id"]
    validations = []
    for binding in bindings:
        print(f"P10 validation revalidation: {binding.configuration_id}", file=sys.stderr, flush=True)
        validations.append(revalidate_model(contract, authority, binding, rows[binding.configuration_id], validation_root))
    consumption = make_consumption(authority, validations, contract)
    publish_json(publication / "consumption" / f"{consumption['consumption_id']}.json", consumption)
    evaluations = []
    for binding in bindings:
        print(f"P10 held-out evaluation: {binding.configuration_id}", file=sys.stderr, flush=True)
        cache_manifest = build_prepared_cache(contract)
        cache = P10PreparedInputCache.open(cache_manifest)
        geometry = P10PreparedGeometryCache.open(build_geometry_cache(contract, cache_manifest))
        evaluations.append(evaluate_model(contract, authority, binding, rows[binding.configuration_id], qualitative, result_root, cache, geometry))
    acceptance = finalize_p10(authority, consumption, validations, evaluations, qualitative, analysis, result_root)
    return {"authority": authority, "qualitative": qualitative, "analysis": analysis, "consumption": consumption,
            "validation_revalidations": validations, "evaluations": evaluations, "acceptance": acceptance,
            "result_root": str(result_root)}
