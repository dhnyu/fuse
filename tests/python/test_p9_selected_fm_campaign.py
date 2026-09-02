from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from p8_experiment_plan import digest  # noqa: E402
from p9_infrastructure import materialize_hyperparameter_configuration  # noqa: E402
from p9_selected_fm_campaign import (  # noqa: E402
    EXPECTED_SOURCE_HASHES, build_authority, compare_results, load_confirmation_rows,
    selected_contract,
)
from p9_v2_canonical import canonical_sha256  # noqa: E402
from p9_v2_training_lifecycle import scientific_configuration_content  # noqa: E402


MATRIX = ROOT / "config/p9_selected_fm_confirmation_matrix.json"


def test_confirmation_rows_are_exact_ip_only_pair():
    left, right = load_confirmation_rows(MATRIX)
    assert (left["scientific_hash"], right["scientific_hash"]) == EXPECTED_SOURCE_HASHES
    assert left["bank_binding"] == right["bank_binding"]
    assert left["run_seed_configuration_id"] == right["run_seed_configuration_id"] == "cfg_selected_fm"
    differences = {key for key in left["scientific"] if left["scientific"][key] != right["scientific"][key]}
    assert differences == {"lambda_ip"}


def test_source_hashes_preserve_ip0_plan_and_derive_ip1_by_lambda_only():
    plan = json.loads((ROOT / "blueprint/p9_v2/p9_a_selection_plan.json").read_text())
    source = plan["selected_fm"]["configuration"]
    ip1 = copy.deepcopy(source)
    ip1["scientific"]["lambda_ip"] = 1.0
    assert digest(source) == EXPECTED_SOURCE_HASHES[0]
    assert digest(ip1) == EXPECTED_SOURCE_HASHES[1]


def test_confirmation_materialization_has_same_seed_and_only_ip_objective_differs():
    left, right = load_confirmation_rows(MATRIX)
    training = yaml.safe_load((ROOT / "config/p7_deterministic_training.yml").read_text())
    model = yaml.safe_load((ROOT / "config/p6_model_dataloader.yml").read_text())
    a = materialize_hyperparameter_configuration(left, training, model)
    b = materialize_hyperparameter_configuration(right, training, model)
    assert a["training"]["training"]["root_seed"] == b["training"]["training"]["root_seed"]
    b_training = copy.deepcopy(b["training"])
    b_training["objective"]["information_preservation_weight"] = 0.0
    assert a["training"] == b_training
    assert a["model"] == b["model"]


def test_confirmation_authorities_are_deterministic_and_bind_distinct_v2_configs():
    rows = load_confirmation_rows(MATRIX)
    contract = yaml.safe_load((ROOT / "config/p9_v2_training_controller.yml").read_text())
    authorities = [build_authority(row, contract, ROOT) for row in rows]
    assert authorities == [build_authority(row, contract, ROOT) for row in rows]
    assert authorities[0]["content"]["scientific"]["root_seed"] == authorities[1]["content"]["scientific"]["root_seed"]
    assert authorities[0]["content"]["scientific"]["configuration_hash"] != authorities[1]["content"]["scientific"]["configuration_hash"]
    assert [item["content"]["scientific"]["p8_configuration_hash"] for item in authorities] == list(EXPECTED_SOURCE_HASHES)
    assert authorities[0]["content"]["scientific"]["configuration_hash"] == canonical_sha256(scientific_configuration_content(rows[0]))


def test_final_comparison_uses_loss_then_margin_then_ip0():
    ip0 = {"validation_retrieval_loss": 0.30, "mean_source_separation_margin": 0.20}
    ip1 = {"validation_retrieval_loss": 0.29, "mean_source_separation_margin": 0.10}
    assert compare_results(ip0, ip1) == "cfg_selected_fm_ip1"
    ip1 = {"validation_retrieval_loss": 0.29995, "mean_source_separation_margin": 0.21}
    assert compare_results(ip0, ip1) == "cfg_selected_fm_ip1"
    ip1 = {"validation_retrieval_loss": 0.2998, "mean_source_separation_margin": 0.10}
    assert compare_results(ip0, ip1) == "cfg_selected_fm_ip1"
    ip1 = dict(ip0)
    assert compare_results(ip0, ip1) == "cfg_selected_fm_ip0"


def test_selected_contract_changes_only_matrix_and_eligibility(tmp_path):
    base = yaml.safe_load((ROOT / "config/p9_v2_training_controller.yml").read_text())
    value = selected_contract(base, MATRIX, tmp_path / "eligibility.json")
    expected = json.loads(json.dumps(base))
    expected["roots"]["configuration_matrix"] = str(MATRIX.resolve())
    expected["roots"]["eligibility_snapshot"] = str((tmp_path / "eligibility.json").resolve())
    assert value == expected
