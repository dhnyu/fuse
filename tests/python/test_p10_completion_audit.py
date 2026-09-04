from __future__ import annotations

from pathlib import Path

import pytest

from p10_completion_audit import ATTEMPT_ID, audit_completed_p10


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def result():
    return audit_completed_p10(ROOT / "config/p10_evaluation.yml", ATTEMPT_ID)


def test_completed_prepared_p10_attempt_and_acceptance_are_valid(result):
    assert result["status"] == "PASS"
    assert result["model_count"] == 8
    assert result["acceptance_id"] == "p10acc_6e5071beee7616750dec7907"
    assert result["consumption_transition"] == {"before": 0, "after": 1}
    assert result["acceptance_idempotent"] is True
    assert result["selection_reopened"] is False
    assert result["training_count"] == result["optimizer_update_count"] == 0


def test_all_eight_validation_revalidations_are_exact(result):
    assert len(result["validation_revalidation"]) == 8
    assert all(
        row["loss_delta"] == row["margin_delta"] == 0
        for row in result["validation_revalidation"]
    )


def test_all_models_share_qualitative_and_prepared_contracts(result):
    assert len(result["qualitative_contract"]["selected_scene_ids"]) == 10
    assert result["qualitative_contract"]["nonlocal_exclusion_distance_m"] == 2000.0
    assert result["prepared_input_cache_id"] == "p10pi_da45b59753b561948fea78f5"
    assert result["prepared_geometry_cache_id"] == "p10geo_8cdab54a6886cb8217c0088b"
    assert {row["configuration_id"] for row in result["heldout_comparison"]} == {
        "cfg_d128",
        "cmp_a1_geometric_core",
        "cmp_a2_semantic_enriched",
        "cmp_a3_object_context_enriched",
        "cmp_a4_raster_complete_non_relational",
        "cmp_a5_relation_type_agnostic",
        "cmp_ssv_like",
        "cmp_ds_like",
    }
