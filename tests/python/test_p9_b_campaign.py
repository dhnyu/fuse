from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT/"python"))
from p9_b_campaign import CONFIGURATIONS,FAMILIES,_restore,build_authority,build_training_matrix,campaign_contract  # noqa:E402
from p9_infrastructure import materialize_hyperparameter_configuration  # noqa:E402
from p9_selected_fm_campaign import SelectedFMCampaignPaths  # noqa:E402
from p9_v2_canonical import canonical_sha256  # noqa:E402
from p9_v2_training_lifecycle import scientific_configuration_content  # noqa:E402

PLAN=Path("/mnt/hdd002/dhnyu/fusedata/models/reduced/p9_v2/canonical/p9_b_plans/p9bplan_e36f7c9c5069a504eb31a9ef.json")
CAMPAIGN=Path("/mnt/hdd002/dhnyu/fusedata/runtime/p9_b_campaigns/20260903_0539_cfgd128")


def matrix(): return build_training_matrix(json.loads(PLAN.read_text()))


def test_matrix_is_exact_cfg_d128_bound_seven_family_plan():
    value=matrix(); assert tuple(row["configuration_id"] for row in value["rows"])==CONFIGURATIONS
    assert tuple(row["model_family"] for row in value["rows"])==tuple(FAMILIES[name] for name in CONFIGURATIONS)
    assert {row["full_model_acceptance_id"] for row in value["rows"]}=={"p9accv2_a1c00e32a882ddc4b7e2677b"}
    assert all(row["evaluation_ancestry"] is False and row["evaluation_query_identity"] is None for row in value["rows"])


def test_comparisons_inherit_cfg_d128_hyperparameters_with_ds_ip_exception():
    rows=matrix()["rows"]
    expected={"d":128,"d_c":128,"effective_k":8,"intensity":"main_1.0x","ema":0.999,"peak_learning_rate":0.001}
    for row in rows:
        assert all(row["scientific"][key]==value for key,value in expected.items())
        assert row["scientific"]["lambda_ip"]==(0.0 if row["model_family"]=="DS" else 1)


def test_materializer_routes_each_declared_family_without_changing_bank():
    training=yaml.safe_load((ROOT/"config/p7_deterministic_training.yml").read_text())
    model=yaml.safe_load((ROOT/"config/p6_model_dataloader.yml").read_text())
    for row in matrix()["rows"]:
        routed=materialize_hyperparameter_configuration(row,training,model)
        assert routed["model_family"]==row["model_family"]
        assert routed["bank_binding"]==row["bank_binding"]


def test_authorities_bind_cfg_d128_parent_and_full_transformation():
    contract=yaml.safe_load((ROOT/"config/p9_v2_training_controller.yml").read_text())
    contract["parents"]["full_model_acceptance_id"]="p9accv2_a1c00e32a882ddc4b7e2677b"
    for row in matrix()["rows"]:
        authority=build_authority(row,contract,ROOT)
        assert authority["content"]["parents"]["full_model_acceptance_id"]==row["full_model_acceptance_id"]
        assert authority["content"]["scientific"]["configuration_hash"]==canonical_sha256(scientific_configuration_content(row))


def test_dynamic_contract_changes_only_matrix_eligibility_and_full_model_parent(tmp_path):
    base=yaml.safe_load((ROOT/"config/p9_v2_training_controller.yml").read_text())
    value=campaign_contract(base,tmp_path/"matrix.json",tmp_path/"eligibility.json","p9accv2_a1c00e32a882ddc4b7e2677b")
    assert value["roots"]["configuration_matrix"]==str((tmp_path/"matrix.json").resolve())
    assert value["roots"]["eligibility_snapshot"]==str((tmp_path/"eligibility.json").resolve())
    assert value["parents"]["full_model_acceptance_id"]=="p9accv2_a1c00e32a882ddc4b7e2677b"
    assert "full_model_acceptance_id" not in base["parents"]


def test_final_decision_eligibility_contains_cfg_d128():
    plan=json.loads(PLAN.read_text()); canonical=PLAN.parents[1]
    decision=json.loads((canonical/"final_model"/f"{plan['final_model_decision_id']}.json").read_text())
    eligibility=json.loads((canonical/"eligibility"/f"{decision['p9_a_eligibility_id']}.json").read_text())
    assert decision["selected_acceptance_id"]==plan["full_model_acceptance_id"]
    assert sum(entry["acceptance_id"]==plan["full_model_acceptance_id"] for entry in eligibility["entries"])==1


def test_completed_campaign_restores_all_seven_canonical_resolver_chains():
    contract=yaml.safe_load((ROOT/"config/p9_v2_training_controller.yml").read_text())
    paths=SelectedFMCampaignPaths(CAMPAIGN,ROOT,ROOT/"config/p9_v2_training_controller.yml",CAMPAIGN/"p9_b_training_matrix.json")
    completed,eligibility=_restore(paths,matrix()["rows"],contract)
    assert [item["configuration_id"] for item in completed]==list(CONFIGURATIONS)
    assert all(item["evaluation_consumption_count"]==0 for item in completed)
    assert eligibility.name=="p9elig_250e0140d593f360f1368ef1.json"
