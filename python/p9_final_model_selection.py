"""Validation-only overall P9 final-model decision and P9-B materialization."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from p9_selected_fm_campaign import _publish_file
from p9_v2_canonical import canonical_sha256
from p9_v2_schema import validate_instance


FINAL_CONFIGURATION_ID = "cfg_d128"
FINAL_ACCEPTANCE_ID = "p9accv2_a1c00e32a882ddc4b7e2677b"
FINAL_CHECKPOINT_ID = "p9ck_56195e9ea3cd45d80cf5e23c"
EXPECTED_LOSS = 0.17650695145130157
EXPECTED_MARGIN = 0.3754689395427704
EXPECTED_SELECTED_EPOCH = 85
EXPECTED_STOPPING_EPOCH = 105


class FinalModelSelectionError(ValueError):
    """Canonical evidence cannot support the requested overall decision."""


def validate_final_model_resolution(resolved: Any) -> None:
    content = resolved.scientific_configuration["content"]
    observed = (
        content.get("configuration_id"), resolved.acceptance_id, resolved.checkpoint_id,
        resolved.completed_epoch, resolved.validation_retrieval_loss,
        resolved.mean_source_separation_margin,
    )
    expected = (
        FINAL_CONFIGURATION_ID, FINAL_ACCEPTANCE_ID, FINAL_CHECKPOINT_ID,
        EXPECTED_SELECTED_EPOCH, EXPECTED_LOSS, EXPECTED_MARGIN,
    )
    if observed != expected:
        raise FinalModelSelectionError("CFG_D128_CANONICAL_EVIDENCE_MISMATCH")
    if resolved.stopping_summary.get("completed_epoch") != EXPECTED_STOPPING_EPOCH:
        raise FinalModelSelectionError("CFG_D128_STOPPING_BOUNDARY_MISMATCH")
    scientific = content["scientific"]
    expected_scientific = {
        "d": 128, "d_c": 128, "effective_k": 8, "intensity": "main_1.0x",
        "ema": 0.999, "lambda_ip": 1.0, "peak_learning_rate": 0.001,
    }
    if any(scientific.get(key) != value for key, value in expected_scientific.items()):
        raise FinalModelSelectionError("CFG_D128_SCIENTIFIC_CONFIGURATION_MISMATCH")


def build_final_model_decision(
    resolved: Any, *, p9_a_eligibility_id: str,
    interaction_decision_id: str, interaction_acceptance_ids: Sequence[str],
) -> dict[str, Any]:
    validate_final_model_resolution(resolved)
    if tuple(interaction_acceptance_ids) != (
        "p9accv2_71cd4dbad4335da2389cf1d7",
        "p9accv2_1e1e842ee66f169f189725aa",
    ):
        raise FinalModelSelectionError("SELECTED_FM_INTERACTION_EVIDENCE_MISMATCH")
    preimage = {
        "schema_version": "2.0.0",
        "artifact_type": "p9_final_model_decision",
        "status": "SELECTED",
        "selection_contract_id": "p9-selection-v2.1.0",
        "selection_scope": "all_executed_p9_a_and_joint_confirmation_candidates",
        "p9_a_eligibility_id": p9_a_eligibility_id,
        "executed_candidate_count": 15,
        "selected_configuration_id": FINAL_CONFIGURATION_ID,
        "selected_acceptance_id": resolved.acceptance_id,
        "selected_checkpoint_id": resolved.checkpoint_id,
        "selected_epoch": resolved.completed_epoch,
        "stopping_epoch": resolved.stopping_summary["completed_epoch"],
        "validation_retrieval_loss": resolved.validation_retrieval_loss,
        "mean_source_separation_margin": resolved.mean_source_separation_margin,
        "factor_wise_preferred_values": {
            "d": 128, "effective_k": 4, "intensity": "weak_0.5x",
            "ema": 0.999, "lambda_ip": 0.0, "peak_learning_rate": 0.003,
        },
        "factor_wise_additivity_supported": False,
        "interaction_confirmation": {
            "decision_id": interaction_decision_id,
            "acceptance_ids": list(interaction_acceptance_ids),
            "interpretation": "lambda_ip_comparison_within_joint_factor_wise_configuration_only",
        },
        "evaluation_consumption_count": 0,
    }
    digest = canonical_sha256(preimage)
    result = {**preimage, "decision_id": "p9fms_" + digest[:24], "content_sha256": digest}
    validate_instance("final_model_decision", result)
    return result


def materialize_p9_b_plan(
    decision: Mapping[str, Any], resolved: Any, templates: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    validate_instance("final_model_decision", dict(decision))
    validate_final_model_resolution(resolved)
    if decision["selected_acceptance_id"] != resolved.acceptance_id:
        raise FinalModelSelectionError("FINAL_DECISION_RESOLUTION_MISMATCH")
    expected_ids = (
        "cmp_a1_geometric_core", "cmp_a2_semantic_enriched",
        "cmp_a3_object_context_enriched", "cmp_a4_raster_complete_non_relational",
        "cmp_a5_relation_type_agnostic", "cmp_ssv_like", "cmp_ds_like",
    )
    if tuple(item.get("template_id") for item in templates) != expected_ids:
        raise FinalModelSelectionError("P9_B_TEMPLATE_ORDER_INVALID")
    comparisons = []
    for source in templates:
        item = dict(source)
        item.pop("selected_fm_dependency", None)
        hash_preimage = {
            "full_model_acceptance_id": resolved.acceptance_id,
            "full_model_checkpoint_id": resolved.checkpoint_id,
            "full_model_scientific_configuration": resolved.scientific_configuration,
            "template_hash": source["template_hash"],
            "transformation_contract": source["transformation_contract"],
        }
        comparisons.append({
            **item,
            "full_model_dependency": resolved.acceptance_id,
            "full_model_checkpoint_id": resolved.checkpoint_id,
            "final_config_hash_status": "RESOLVED",
            "final_scientific_hash": canonical_sha256(hash_preimage),
        })
    preimage = {
        "schema_version": "2.0.0",
        "artifact_type": "p9_b_selected_model_plan",
        "status": "MATERIALIZED_NOT_EXECUTED",
        "final_model_decision_id": decision["decision_id"],
        "full_model_configuration_id": FINAL_CONFIGURATION_ID,
        "full_model_acceptance_id": resolved.acceptance_id,
        "full_model_checkpoint_id": resolved.checkpoint_id,
        "full_model_scientific_configuration": resolved.scientific_configuration,
        "comparisons": comparisons,
        "count": 7,
        "evaluation_consumption_count": 0,
    }
    digest = canonical_sha256(preimage)
    result = {**preimage, "plan_id": "p9bplan_" + digest[:24], "content_sha256": digest}
    validate_instance("p9_b_selected_model_plan", result)
    return result


def publish_final_model_materialization(
    decision: Mapping[str, Any], plan: Mapping[str, Any], canonical_root: str | Path,
) -> tuple[Path, Path]:
    validate_instance("final_model_decision", dict(decision))
    validate_instance("p9_b_selected_model_plan", dict(plan))
    root = Path(canonical_root)
    decision_path = _publish_file(root / "final_model" / f"{decision['decision_id']}.json", decision)
    plan_path = _publish_file(root / "p9_b_plans" / f"{plan['plan_id']}.json", plan)
    return decision_path, plan_path
