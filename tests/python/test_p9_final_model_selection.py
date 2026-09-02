from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from p9_final_model_selection import (  # noqa: E402
    FINAL_ACCEPTANCE_ID, FINAL_CHECKPOINT_ID, FinalModelSelectionError,
    build_final_model_decision, materialize_p9_b_plan,
)
from p9_selected_fm_campaign import _resolver  # noqa: E402
from p9_v2_schema import P9V2SchemaError, validate_instance  # noqa: E402


def evidence():
    contract = yaml.safe_load((ROOT / "config/p9_v2_training_controller.yml").read_text())
    canonical = Path(contract["roots"]["canonical_publication"])
    acceptance = json.loads((canonical / "acceptances" / FINAL_ACCEPTANCE_ID / "acceptance.json").read_text())
    bundle = Path(contract["roots"]["lifecycle_records"]) / acceptance["authority_id"] / "bundle.json"
    eligibility = canonical / "eligibility/p9elig_8d017288b37c7c7a08734fa7.json"
    resolved = _resolver(canonical, eligibility, [{"bundle_record": str(bundle)}]).resolve_accepted_checkpoint(FINAL_ACCEPTANCE_ID)
    templates = json.loads((Path(contract["roots"]["p8_bundle"]) / "comparison_variant_template_matrix.json").read_text())["templates"]
    decision = build_final_model_decision(
        resolved, p9_a_eligibility_id="p9elig_8d017288b37c7c7a08734fa7",
        interaction_decision_id="p9sfm_dca5569ef50bd9bfb1940032",
        interaction_acceptance_ids=("p9accv2_71cd4dbad4335da2389cf1d7", "p9accv2_1e1e842ee66f169f189725aa"),
    )
    return resolved, decision, materialize_p9_b_plan(decision, resolved, templates)


def test_overall_decision_selects_best_observed_cfg_d128():
    resolved, decision, _ = evidence()
    assert decision["decision_id"] == "p9fms_389a0ce89992eee507d7c846"
    assert decision["selected_acceptance_id"] == FINAL_ACCEPTANCE_ID
    assert decision["selected_checkpoint_id"] == FINAL_CHECKPOINT_ID
    assert decision["validation_retrieval_loss"] == 0.17650695145130157
    assert decision["mean_source_separation_margin"] == 0.3754689395427704
    assert decision["factor_wise_additivity_supported"] is False
    assert resolved.stopping_summary["completed_epoch"] == 105


def test_joint_confirmations_are_retained_as_scoped_interaction_evidence():
    _, decision, _ = evidence()
    assert decision["interaction_confirmation"]["interpretation"].endswith("_only")
    assert decision["interaction_confirmation"]["acceptance_ids"] == [
        "p9accv2_71cd4dbad4335da2389cf1d7", "p9accv2_1e1e842ee66f169f189725aa"]


def test_seven_comparisons_bind_only_cfg_d128_and_unique_transforms():
    _, _, plan = evidence()
    assert plan["plan_id"] == "p9bplan_e36f7c9c5069a504eb31a9ef"
    assert plan["full_model_acceptance_id"] == FINAL_ACCEPTANCE_ID
    assert len({item["final_scientific_hash"] for item in plan["comparisons"]}) == 7
    serialized = json.dumps(plan, sort_keys=True)
    assert "cfg_selected_fm_ip0" not in serialized
    assert "cfg_selected_fm_ip1" not in serialized
    assert "cfg_d64" not in serialized
    assert all(item.get("full_model_dependency") == FINAL_ACCEPTANCE_ID for item in plan["comparisons"])
    assert all(item.get("selected_fm_dependency") is None for item in plan["comparisons"])
    # Any cfg_main token inherited from P8 is a prohibition, never a dependency.
    for item in plan["comparisons"]:
        if "cfg_main" in json.dumps(item, sort_keys=True):
            assert "cfg_main_substitution" in item.get("unsupported_fallbacks", [])


def test_mismatched_final_resolution_fails_closed():
    resolved, _, _ = evidence()
    object.__setattr__(resolved, "checkpoint_id", "p9ck_" + "0" * 24)
    with pytest.raises(FinalModelSelectionError, match="CANONICAL_EVIDENCE_MISMATCH"):
        build_final_model_decision(
            resolved, p9_a_eligibility_id="p9elig_8d017288b37c7c7a08734fa7",
            interaction_decision_id="p9sfm_dca5569ef50bd9bfb1940032",
            interaction_acceptance_ids=("p9accv2_71cd4dbad4335da2389cf1d7", "p9accv2_1e1e842ee66f169f189725aa"),
        )


def test_active_plan_schema_rejects_stale_selected_fm_fields():
    _, _, plan = evidence()
    plan["selected_fm_acceptance_id"] = "p9accv2_1e1e842ee66f169f189725aa"
    with pytest.raises(P9V2SchemaError):
        validate_instance("p9_b_selected_model_plan", plan)
