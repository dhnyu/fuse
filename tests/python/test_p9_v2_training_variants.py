from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from canonical_config import load_strict_yaml  # noqa: E402
from p9_infrastructure import cache_requirements, materialize_hyperparameter_configuration  # noqa: E402
from p9_v2_finalization import make_selection_contract  # noqa: E402
from p9_v2_schema import validate_instance  # noqa: E402

P8 = Path("/mnt/hdd002/dhnyu/fusedata/models/reduced/formal_plan/p8a_3cb1c49084529987f0244a93/p8acc_c9f16a07275aadfae928d329")


def test_all_thirteen_hyperparameter_rows_construct_without_execution():
    matrix = json.loads((P8 / "hyperparameter_configuration_matrix.json").read_text())
    training = yaml.safe_load((ROOT / "config/p7_deterministic_training.yml").read_text())
    model = load_strict_yaml(ROOT / "config/p6_model_dataloader.yml")
    routed = [materialize_hyperparameter_configuration(row, training, model) for row in matrix["rows"]]
    assert len(routed) == 13
    assert {item["configuration_id"] for item in routed} == {
        "cfg_main", "cfg_d48", "cfg_d128", "cfg_k2", "cfg_k4", "cfg_k16", "cfg_intensity_05",
        "cfg_intensity_20", "cfg_ema_990", "cfg_ip_0", "cfg_lr_2", "cfg_lr_3", "cfg_lr_10",
    }
    assert all(item["formal_authorized"] is False and item["evaluation_ancestry"] is False for item in routed)


def test_all_seven_authoritative_nested_comparisons_construct_without_execution():
    matrix = json.loads((P8 / "comparison_variant_template_matrix.json").read_text())
    expected = {
        "cmp_a1_geometric_core", "cmp_a2_semantic_enriched", "cmp_a3_object_context_enriched",
        "cmp_a4_raster_complete_non_relational", "cmp_a5_relation_type_agnostic", "cmp_ssv_like", "cmp_ds_like",
    }
    assert {row["template_id"] for row in matrix["templates"]} == expected
    for row in matrix["templates"]:
        family = {"cmp_ssv_like": "SSV", "cmp_ds_like": "DS"}.get(row["template_id"],
                 row["template_id"].split("_")[1].upper())
        cache_requirements(family, {"physical_bank_id": "bank", "profile_id": "main_1.0x",
                           "nested_subset_identity": "subset"})


def test_selection_v210_is_the_only_controller_selection_contract():
    contract = make_selection_contract()
    validate_instance("selection_contract", contract)
    assert contract["content"]["contract_version"] == "p9-selection-v2.1.0"
    assert contract["content"]["patience_reset"] == "retrieval_loss_decrease_at_least_tolerance_only"
