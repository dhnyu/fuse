from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT/"python"))
from p9_b_campaign import CONFIGURATIONS,FAMILIES,build_authority,build_training_matrix,campaign_contract  # noqa:E402
from p9_infrastructure import materialize_hyperparameter_configuration  # noqa:E402
from p9_v2_canonical import canonical_sha256  # noqa:E402
from p9_v2_training_lifecycle import scientific_configuration_content  # noqa:E402

PLAN=Path("/mnt/hdd002/dhnyu/fusedata/models/reduced/p9_v2/canonical/p9_b_plans/p9bplan_747bbf5e1e12f831ea5fb101.json")


def matrix(): return build_training_matrix(json.loads(PLAN.read_text()))


def test_matrix_is_exact_winner_bound_seven_family_plan():
    value=matrix(); assert tuple(row["configuration_id"] for row in value["rows"])==CONFIGURATIONS
    assert tuple(row["model_family"] for row in value["rows"])==tuple(FAMILIES[name] for name in CONFIGURATIONS)
    assert {row["selected_fm_acceptance_id"] for row in value["rows"]}=={"p9accv2_1e1e842ee66f169f189725aa"}
    assert all(row["evaluation_ancestry"] is False and row["evaluation_query_identity"] is None for row in value["rows"])


def test_comparisons_inherit_winner_hyperparameters_with_ds_ip_exception():
    rows=matrix()["rows"]
    expected={"d":128,"d_c":128,"effective_k":4,"intensity":"weak_0.5x","ema":0.999,"peak_learning_rate":0.003}
    for row in rows:
        assert all(row["scientific"][key]==value for key,value in expected.items())
        assert row["scientific"]["lambda_ip"]==(0.0 if row["model_family"]=="DS" else 1.0)


def test_materializer_routes_each_declared_family_without_changing_bank():
    training=yaml.safe_load((ROOT/"config/p7_deterministic_training.yml").read_text())
    model=yaml.safe_load((ROOT/"config/p6_model_dataloader.yml").read_text())
    for row in matrix()["rows"]:
        routed=materialize_hyperparameter_configuration(row,training,model)
        assert routed["model_family"]==row["model_family"]
        assert routed["bank_binding"]==row["bank_binding"]


def test_authorities_bind_winner_parent_and_full_transformation():
    contract=yaml.safe_load((ROOT/"config/p9_v2_training_controller.yml").read_text())
    contract["parents"]["selected_fm_acceptance_id"]="p9accv2_1e1e842ee66f169f189725aa"
    for row in matrix()["rows"]:
        authority=build_authority(row,contract,ROOT)
        assert authority["content"]["parents"]["selected_fm_acceptance_id"]==row["selected_fm_acceptance_id"]
        assert authority["content"]["scientific"]["configuration_hash"]==canonical_sha256(scientific_configuration_content(row))


def test_dynamic_contract_changes_only_matrix_eligibility_and_selected_parent(tmp_path):
    base=yaml.safe_load((ROOT/"config/p9_v2_training_controller.yml").read_text())
    value=campaign_contract(base,tmp_path/"matrix.json",tmp_path/"eligibility.json","p9accv2_1e1e842ee66f169f189725aa")
    assert value["roots"]["configuration_matrix"]==str((tmp_path/"matrix.json").resolve())
    assert value["roots"]["eligibility_snapshot"]==str((tmp_path/"eligibility.json").resolve())
    assert value["parents"]["selected_fm_acceptance_id"]=="p9accv2_1e1e842ee66f169f189725aa"
    assert "selected_fm_acceptance_id" not in base["parents"]
