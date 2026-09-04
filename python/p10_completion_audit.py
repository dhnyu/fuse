"""Read-only integrity audit for one completed prepared-input P10 attempt."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import torch

from p10_evaluation import (
    MODEL_IDS,
    P10Error,
    _load_base_evidence,
    _load_committed_model_evaluation,
    _metric,
    _qualitative,
    _read_json,
    evaluation_population,
    finalize_p10_attempt,
    load_contract,
    make_analysis_contract,
    make_execution_attempt,
    make_qualitative_contract,
    resolve_model_bindings,
)
from p10_prepared_input import (
    P10PreparedGeometryCache,
    P10PreparedInputCache,
)
from p9_v2_canonical import canonical_sha256, sha256_file


ATTEMPT_ID = "p10exec_7fee193dac532190c79e02c6"


def _same_numbers(observed: Mapping[str, Any], expected: Mapping[str, Any]) -> bool:
    return all(observed.get(key) == value for key, value in expected.items())


def _validate_validation(
    value: Mapping[str, Any], binding: Any, arrays_path: Path, contract: Mapping[str, Any]
) -> dict[str, Any]:
    if (
        value.get("status") != "PASS"
        or value.get("configuration_id") != binding.configuration_id
        or value.get("acceptance_id") != binding.acceptance_id
        or value.get("checkpoint_id") != binding.checkpoint_id
        or value.get("heldout_consumption_count") != 0
    ):
        raise P10Error(f"P10_AUDIT_VALIDATION_BINDING_INVALID:{binding.configuration_id}")
    expected = {
        "retrieval_loss": binding.expected_retrieval_loss,
        "mean_source_separation_margin": binding.expected_margin,
    }
    if not _same_numbers(value.get("expected", {}), expected):
        raise P10Error(f"P10_AUDIT_VALIDATION_EXPECTED_MISMATCH:{binding.configuration_id}")
    reproduced = value.get("reproduced", {})
    gate = contract["validation_revalidation"]
    if (
        int(reproduced.get("query_count", -1)) != 800
        or int(reproduced.get("gallery_count", -1)) != 400
        or abs(float(reproduced["retrieval_loss"]) - binding.expected_retrieval_loss)
        > float(gate["retrieval_loss_atol"])
        or abs(float(reproduced["mean_source_separation_margin"]) - binding.expected_margin)
        > float(gate["margin_atol"])
    ):
        raise P10Error(f"P10_AUDIT_VALIDATION_TOLERANCE_FAILURE:{binding.configuration_id}")
    with np.load(arrays_path) as arrays:
        embeddings = np.asarray(arrays["embeddings"])
        ranks = np.asarray(arrays["ranks"])
        if embeddings.shape != (1200, int(embeddings.shape[1])) or ranks.shape != (800, 400):
            raise P10Error(f"P10_AUDIT_VALIDATION_ARRAY_SHAPE:{binding.configuration_id}")
        metrics, recomputed_ranks = _metric(
            torch.from_numpy(embeddings[:800]),
            torch.from_numpy(embeddings[800:]),
            float(contract["execution"]["temperature"]),
        )
        if (
            metrics != reproduced
            or not np.array_equal(ranks, recomputed_ranks)
            or value.get("embedding_sha256") != hashlib.sha256(embeddings.tobytes()).hexdigest()
            or value.get("rank_sha256") != hashlib.sha256(ranks.tobytes()).hexdigest()
        ):
            raise P10Error(f"P10_AUDIT_VALIDATION_RECOMPUTE_MISMATCH:{binding.configuration_id}")
    return {
        "configuration_id": binding.configuration_id,
        "expected_retrieval_loss": binding.expected_retrieval_loss,
        "reproduced_retrieval_loss": float(reproduced["retrieval_loss"]),
        "expected_margin": binding.expected_margin,
        "reproduced_margin": float(reproduced["mean_source_separation_margin"]),
        "loss_delta": float(reproduced["retrieval_loss"]) - binding.expected_retrieval_loss,
        "margin_delta": (
            float(reproduced["mean_source_separation_margin"]) - binding.expected_margin
        ),
    }


def _validate_evaluation(
    root: Path,
    authority: Mapping[str, Any],
    binding: Any,
    cache: P10PreparedInputCache,
    geometry: P10PreparedGeometryCache,
    qualitative: Mapping[str, Any],
    gallery_scene_ids: list[str],
    masks: torch.Tensor,
    contract: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    value = _load_committed_model_evaluation(root, authority, binding, cache, geometry)
    if value is None:
        raise P10Error(f"P10_AUDIT_MODEL_RESULT_MISSING:{binding.configuration_id}")
    arrays_path = root / "evaluation_embeddings_ranks_analysis.npz"
    with np.load(arrays_path) as arrays:
        embeddings = np.asarray(arrays["embeddings"])
        centers = np.asarray(arrays["centers"])
        ranks = np.asarray(arrays["ranks"])
        umap = np.asarray(arrays["umap"])
        labels = np.asarray(arrays["hdbscan_labels"])
        probabilities = np.asarray(arrays["hdbscan_probabilities"])
        dimension = int(value["embedding_dimension"])
        if (
            embeddings.shape != (4800, dimension)
            or centers.shape != (4800, 2)
            or ranks.shape != (3200, 1600)
            or umap.shape != (1600, 2)
            or labels.shape != (1600,)
            or probabilities.shape != (1600,)
        ):
            raise P10Error(f"P10_AUDIT_MODEL_ARRAY_SHAPE:{binding.configuration_id}")
        metrics, recomputed_ranks = _metric(
            torch.from_numpy(embeddings[:3200]),
            torch.from_numpy(embeddings[3200:]),
            float(contract["execution"]["temperature"]),
        )
        if metrics != value.get("metrics") or not np.array_equal(ranks, recomputed_ranks):
            raise P10Error(f"P10_AUDIT_MODEL_METRIC_RECOMPUTE:{binding.configuration_id}")
        reproduced_qualitative = _qualitative(
            binding,
            torch.from_numpy(embeddings[3200:]),
            centers[3200:],
            gallery_scene_ids,
            qualitative,
            masks,
        )
    committed_qualitative = _read_json(root / "qualitative_retrieval.json")
    if reproduced_qualitative != committed_qualitative:
        raise P10Error(f"P10_AUDIT_QUALITATIVE_RECOMPUTE:{binding.configuration_id}")
    if len(committed_qualitative.get("queries", [])) != 10:
        raise P10Error(f"P10_AUDIT_QUALITATIVE_COUNT:{binding.configuration_id}")
    for row in committed_qualitative["queries"]:
        if (
            row.get("standard_candidate_count") != 1599
            or len(row.get("standard_rank_positions", [])) != 4
            or len(row.get("nonlocal_rank_positions", [])) != 4
            or int(row.get("nonlocal_candidate_count", 0)) <= 0
        ):
            raise P10Error(f"P10_AUDIT_QUALITATIVE_CONTRACT:{binding.configuration_id}")
    return value, {
        "configuration_id": binding.configuration_id,
        **dict(value["metrics"]),
        "retrieval_loss_delta_from_cfg_d128": 0.0,
        "margin_delta_from_cfg_d128": 0.0,
        "evaluation_wall_seconds": float(value["timing"]["evaluation_wall_seconds"]),
        "hdbscan_cluster_count": int(value["representation_summary"]["hdbscan_cluster_count"]),
        "hdbscan_noise_count": int(value["representation_summary"]["hdbscan_noise_count"]),
        "embedding_sha256": value["embedding_sha256"],
        "umap_sha256": value["umap_sha256"],
        "hdbscan_labels_sha256": value["hdbscan_labels_sha256"],
        "hdbscan_probabilities_sha256": value["hdbscan_probabilities_sha256"],
        "qualitative_sha256": value["qualitative_sha256"],
    }


def audit_completed_p10(contract_path: str | Path, attempt_id: str = ATTEMPT_ID) -> dict[str, Any]:
    contract = load_contract(contract_path)
    bindings = resolve_model_bindings(contract)
    if tuple(item.configuration_id for item in bindings) != MODEL_IDS:
        raise P10Error("P10_AUDIT_MODEL_ORDER_INVALID")
    _, galleries = evaluation_population(contract)
    gallery_scene_ids = [str(row["scene_id"]) for row in galleries]
    qualitative = make_qualitative_contract(contract, galleries)
    analysis = make_analysis_contract(contract)
    authority, consumption, validations = _load_base_evidence(
        contract, bindings, qualitative, analysis
    )
    publication = Path(contract["publication_root"])
    attempt_root = publication / "execution_attempts" / attempt_id
    attempt = _read_json(attempt_root / "attempt.json")
    input_manifest = (
        Path(contract["prepared_input"]["root"])
        / attempt["prepared_input_cache_id"]
        / "prepared_input_manifest.json"
    )
    geometry_manifest = (
        Path(contract["prepared_input"]["geometry_root"])
        / attempt["prepared_geometry_cache_id"]
        / "prepared_geometry_manifest.json"
    )
    cache = P10PreparedInputCache.open(input_manifest, verify_payloads=True)
    geometry = P10PreparedGeometryCache.open(geometry_manifest, verify_payloads=True)
    expected_attempt = make_execution_attempt(contract, authority, consumption, cache, geometry)
    if attempt != expected_attempt or attempt_id != expected_attempt["attempt_id"]:
        raise P10Error("P10_AUDIT_ATTEMPT_IDENTITY_INVALID")
    if attempt.get("environment") != {
        name: importlib.metadata.version(name)
        for name in ("torch", "numpy", "scikit-learn", "umap-learn", "hdbscan", "pyarrow")
    }:
        raise P10Error("P10_AUDIT_ENVIRONMENT_MISMATCH")
    mask_scenes, masks = cache.nonlocal_masks()
    if mask_scenes != gallery_scene_ids or cache.cache_id != "p10pi_da45b59753b561948fea78f5":
        raise P10Error("P10_AUDIT_PREPARED_INPUT_INVALID")
    if geometry.cache_id != "p10geo_8cdab54a6886cb8217c0088b":
        raise P10Error("P10_AUDIT_PREPARED_GEOMETRY_INVALID")

    validation_rows = []
    validation_root = publication / "validation_revalidation" / authority["authority_id"]
    expected_model_names = {item.configuration_id for item in bindings}
    if {path.name for path in validation_root.iterdir() if path.is_dir()} != expected_model_names:
        raise P10Error("P10_AUDIT_VALIDATION_MODEL_SET_INVALID")
    for binding, value in zip(bindings, validations, strict=True):
        validation_rows.append(_validate_validation(
            value,
            binding,
            validation_root / binding.configuration_id / "validation_embeddings_and_ranks.npz",
            contract,
        ))

    evaluations = []
    comparison = []
    evaluation_root = attempt_root / "evaluations"
    if {path.name for path in evaluation_root.iterdir() if path.is_dir()} != expected_model_names:
        raise P10Error("P10_AUDIT_EVALUATION_MODEL_SET_INVALID")
    for binding in bindings:
        value, summary = _validate_evaluation(
            attempt_root / "evaluations" / binding.configuration_id,
            authority,
            binding,
            cache,
            geometry,
            qualitative,
            gallery_scene_ids,
            masks,
            contract,
        )
        evaluations.append(value)
        comparison.append(summary)
    reference = comparison[0]
    for row in comparison:
        row["retrieval_loss_delta_from_cfg_d128"] = (
            row["retrieval_loss"] - reference["retrieval_loss"]
        )
        row["margin_delta_from_cfg_d128"] = row["mean_source_separation_margin"] - reference[
            "mean_source_separation_margin"
        ]

    acceptance_path = attempt_root / "commit" / "evaluation_acceptance.json"
    before_sha = sha256_file(acceptance_path)
    before_mtime = acceptance_path.stat().st_mtime_ns
    acceptance = _read_json(acceptance_path)
    expected_acceptance = finalize_p10_attempt(
        authority,
        attempt,
        consumption,
        validations,
        evaluations,
        qualitative,
        analysis,
        attempt_root,
    )
    if acceptance != expected_acceptance:
        raise P10Error("P10_AUDIT_ACCEPTANCE_CONTENT_INVALID")
    if (
        sha256_file(acceptance_path) != before_sha
        or acceptance_path.stat().st_mtime_ns != before_mtime
    ):
        raise P10Error("P10_AUDIT_ACCEPTANCE_IDEMPOTENCY_FAILURE")
    if acceptance.get("acceptance_id") != "p10acc_6e5071beee7616750dec7907":
        raise P10Error("P10_AUDIT_ACCEPTANCE_ID_UNEXPECTED")
    if (
        acceptance.get("model_evaluation_sha256") != canonical_sha256(evaluations)
        or acceptance.get("validation_revalidation_sha256") != canonical_sha256(validations)
        or acceptance.get("consumption_id") != consumption["consumption_id"]
    ):
        raise P10Error("P10_AUDIT_ACCEPTANCE_BINDING_INVALID")

    return {
        "status": "PASS",
        "authority_id": authority["authority_id"],
        "attempt_id": attempt["attempt_id"],
        "acceptance_id": acceptance["acceptance_id"],
        "acceptance_sha256": before_sha,
        "consumption_id": consumption["consumption_id"],
        "consumption_transition": consumption["transition"],
        "prepared_input_cache_id": cache.cache_id,
        "prepared_geometry_cache_id": geometry.cache_id,
        "qualitative_contract": qualitative,
        "analysis_contract": analysis,
        "model_bindings": [asdict(item) for item in bindings],
        "validation_revalidation": validation_rows,
        "heldout_comparison": comparison,
        "model_count": len(evaluations),
        "acceptance_idempotent": True,
        "selection_reopened": False,
        "training_count": 0,
        "optimizer_update_count": 0,
        "checkpoint_write_count": 0,
        "p11_execution_count": 0,
    }
