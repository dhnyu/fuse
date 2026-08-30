from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from p8_experiment_plan import (CONFIG_IDS, TEMPLATE_IDS, build_a5_generic_relation_contract,
                                build_comparison_templates, build_ds_raster_contract,
                                build_hyperparameter_rows, dimension_compatibility,
                                load_config, materialize_comparison,
                                validate_comparison_templates, validate_hyperparameter_rows)


def config():
    return load_config(ROOT / "config/p8_formal_experiment_plan.yml")


def test_hyperparameter_matrix_is_exactly_thirteen_unique_ofat_rows():
    rows = build_hyperparameter_rows(config())
    assert tuple(row["configuration_id"] for row in rows) == CONFIG_IDS
    assert len({row["scientific_hash"] for row in rows}) == 13
    assert sum(row["configuration_id"] == "cfg_main" for row in rows) == 1
    assert {row["scientific"]["d"] for row in rows} == {48, 64, 128}
    assert {row["scientific"]["per_head_dimension"] for row in rows} == {12, 16, 32}
    assert {row["scientific"]["effective_k"] for row in rows} == {2, 4, 8, 16}
    assert {row["scientific"]["peak_learning_rate"] for row in rows} == {0.001, 0.002, 0.003, 0.01}
    assert all(row["evaluation_query_identity"] is None and not row["evaluation_ancestry"] for row in rows)


def test_hyperparameter_matrix_rejects_missing_extra_duplicate_and_two_factor_mutation():
    rows = build_hyperparameter_rows(config())
    with pytest.raises(ValueError): validate_hyperparameter_rows(rows[:-1])
    with pytest.raises(ValueError): validate_hyperparameter_rows(rows + [copy.deepcopy(rows[-1])])
    duplicate = copy.deepcopy(rows); duplicate[-1]["scientific_hash"] = duplicate[0]["scientific_hash"]
    with pytest.raises(ValueError, match="duplicate"): validate_hyperparameter_rows(duplicate)
    mutation = copy.deepcopy(rows); mutation[1]["scientific"]["ema"] = 0.990
    with pytest.raises(ValueError, match="OFAT"): validate_hyperparameter_rows(mutation)


def test_comparison_templates_are_seven_deferred_nonselection_specs():
    rows = build_comparison_templates(config())
    assert tuple(row["template_id"] for row in rows) == TEMPLATE_IDS
    assert sum(row["comparison_class"] == "ablation" for row in rows) == 5
    assert sum(row["comparison_class"] == "controlled_baseline" for row in rows) == 2
    assert all(not row["hyperparameter_selection_eligible"] for row in rows)
    assert all(row["final_config_hash_status"] == "UNRESOLVED_UNTIL_P9_A_SELECTION" for row in rows)
    with pytest.raises(ValueError, match="selected FM"): materialize_comparison(rows[0], None)


def test_comparison_transformation_details_are_authoritative():
    rows = {row["template_id"]: row for row in build_comparison_templates(config())}
    a1 = rows["cmp_a1_geometric_core"]["transformation_contract"]
    assert a1["active_entity_modalities"] == ["relative_position", "intrinsic_geometry"]
    a2 = rows["cmp_a2_semantic_enriched"]["transformation_contract"]
    assert a2["extends"] == "cmp_a1_geometric_core" and "building_semantic" in a2["active_entity_modalities"]
    a3 = rows["cmp_a3_object_context_enriched"]["transformation_contract"]
    assert a3["extends"] == "cmp_a2_semantic_enriched" and "object_environmental_background" in a3["active_entity_modalities"]
    a4 = rows["cmp_a4_raster_complete_non_relational"]["transformation_contract"]
    assert a4["scene_raster_branch"] and "relational_contextualization" in a4["remove"]
    a5 = rows["cmp_a5_relation_type_agnostic"]["transformation_contract"]
    assert a5["edge_instances"] == "exact_FM_directed_edge_instances"
    assert a5["map_relation_labels"] == {name: "GENERIC" for name in ("SN", "CNT", "WIT", "INT", "CON")}
    assert not a5["radius_graph"] and not a5["edge_support_change"]
    assert rows["cmp_ssv_like"]["transformation_contract"]["retain"] == ["relative_position", "semantic", "scene_contrastive", "ip_relative_position", "ip_semantic"]
    assert rows["cmp_ssv_like"]["template_hash"] == "c32c80baae23d14a142555e85e2232daf55d58a3a16ca8b26318211043a6a748"
    ds = rows["cmp_ds_like"]["transformation_contract"]
    assert ds["channels"] == "C_cat_plus_4" and ds["lambda_ip"] == 0.0 and not ds["direct_reproduction"]


def test_a5_generic_relation_contract_preserves_exact_fm_support():
    contract = build_a5_generic_relation_contract(config())
    assert contract["edge_instances"] == "exact_FM_directed_edge_instances"
    assert contract["preserve_direction"] and contract["preserve_multiplicity"] and contract["preserve_edge_support"]
    assert contract["source_relation_labels"] == ["SN", "CNT", "WIT", "INT", "CON"]
    assert "radius_graph_reconstruction" in contract["prohibited"]


def test_ds_contract_is_common_grid_and_fail_closed():
    contract = build_ds_raster_contract(config())
    assert contract["common_grid"]["height"] == contract["common_grid"]["width"] == 100
    assert contract["dem"]["source_grid"] == {"height": 17, "width": 17}
    assert contract["dem"]["target_grid"] == {"height": 100, "width": 100}
    assert contract["dem"]["interpolation"] == "cell_center_based_bilinear"
    assert not contract["dem"]["regenerate_perturbation"]
    assert contract["dem"]["complete_valid_support_required"]
    assert contract["dem"]["invalid_or_nodata_policy"] == "fail_closed"
    assert contract["channel_count_formula"] == "C_cat_plus_4" and contract["lambda_ip"] == 0.0


def test_comparison_rejects_unknown_and_evaluation_injection():
    rows = build_comparison_templates(config())
    unknown = copy.deepcopy(rows); unknown[0]["template_id"] = "unknown"
    with pytest.raises(ValueError): validate_comparison_templates(unknown)
    evaluation = copy.deepcopy(rows); evaluation[0]["evaluation_query_identity"] = "forbidden"
    with pytest.raises(ValueError, match="evaluation"): validate_comparison_templates(evaluation)
    radius = copy.deepcopy(rows); radius[4]["transformation_contract"]["radius_graph"] = True
    with pytest.raises(ValueError, match="radius"): validate_comparison_templates(radius)


def test_d48_d64_d128_construction_uses_fixed_auxiliary_dimensions():
    result = dimension_compatibility()
    assert result["status"] == "PASS" and not result["legacy_d128_artifact_adopted"]
    assert [(row["d"], row["d_c"], row["heads"], row["per_head_dimension"]) for row in result["rows"]] == [(48, 48, 4, 12), (64, 64, 4, 16), (128, 128, 4, 32)]


def test_divergence_policy_cannot_hide_infrastructure_failure_or_replace_lr():
    policy = config()["divergence_policy"]
    assert policy["terminal_status"] == "SCIENTIFIC_DIVERGENCE"
    assert not policy["winner_eligible"]
    assert not policy["replacement_learning_rate_allowed"]
    assert not policy["infrastructure_failure_may_use_status"]
