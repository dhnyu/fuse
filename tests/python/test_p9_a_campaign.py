from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from p8_experiment_plan import historical_configuration_id, reporting_configuration_id  # noqa: E402
from p9_a_campaign import (  # noqa: E402
    CAMPAIGN_CONFIGURATIONS, CampaignError, CampaignPaths, build_campaign_authority,
    campaign_contract, campaign_plan, restore_campaign_progress,
)
from p9_v2_canonical import canonical_sha256  # noqa: E402
from p9_v2_training_controller import training_run_id  # noqa: E402
from p9_v2_training_lifecycle import scientific_configuration_content  # noqa: E402


P8 = Path("/mnt/hdd002/dhnyu/fusedata/models/reduced/formal_plan/p8a_3cb1c49084529987f0244a93/p8acc_c9f16a07275aadfae928d329")


def test_cfg_main_reporting_alias_preserves_historical_identity_and_hash():
    matrix = json.loads((P8 / "hyperparameter_configuration_matrix.json").read_text())
    row = matrix["rows"][0]
    before = canonical_sha256(row)
    assert row["configuration_id"] == "cfg_main"
    assert reporting_configuration_id("cfg_main") == "cfg_d64"
    assert historical_configuration_id("cfg_d64") == "cfg_main"
    assert canonical_sha256(row) == before


def test_campaign_is_exact_predeclared_remaining_order():
    matrix = json.loads((P8 / "hyperparameter_configuration_matrix.json").read_text())
    rows = campaign_plan(matrix)
    assert tuple(row["configuration_id"] for row in rows) == CAMPAIGN_CONFIGURATIONS
    assert len(rows) == 11 and "cfg_main" not in CAMPAIGN_CONFIGURATIONS and "cfg_d48" not in CAMPAIGN_CONFIGURATIONS


def test_campaign_authorities_are_deterministic_and_bound_to_p8():
    matrix = json.loads((P8 / "hyperparameter_configuration_matrix.json").read_text())
    row = campaign_plan(matrix)[0]
    contract = yaml.safe_load((ROOT / "config/p9_v2_training_controller.yml").read_text())
    first = build_campaign_authority(row["configuration_id"], row, contract, ROOT)
    second = build_campaign_authority(row["configuration_id"], row, contract, ROOT)
    assert first == second and training_run_id(first) == training_run_id(second)
    assert first["content"]["scientific"]["p8_configuration_hash"] == row["scientific_hash"]
    assert first["content"]["scientific"]["configuration_hash"] == canonical_sha256(scientific_configuration_content(row))
    assert first["content"]["scientific"]["evaluation_ancestry"] is False


def test_dynamic_contract_changes_only_eligibility_pointer(tmp_path):
    base = yaml.safe_load((ROOT / "config/p9_v2_training_controller.yml").read_text())
    value = campaign_contract(base, tmp_path / "eligibility.json")
    expected = json.loads(json.dumps(base))
    expected["roots"]["eligibility_snapshot"] = str((tmp_path / "eligibility.json").resolve())
    assert value == expected and base["roots"]["eligibility_snapshot"] != value["roots"]["eligibility_snapshot"]


def test_blocked_campaign_restores_four_canonical_acceptances_and_latest_eligibility(tmp_path):
    source = Path("/mnt/hdd002/dhnyu/fusedata/runtime/p9_a_campaigns/20260901_1450/campaign_status.json")
    if not source.is_file():
        pytest.skip("campaign audit status unavailable")
    root = tmp_path / "campaign"
    root.mkdir()
    (root / "campaign_status.json").write_bytes(source.read_bytes())
    contract = yaml.safe_load((ROOT / "config/p9_v2_training_controller.yml").read_text())
    matrix = json.loads((P8 / "hyperparameter_configuration_matrix.json").read_text())
    completed, eligibility = restore_campaign_progress(
        CampaignPaths(root, ROOT, ROOT / "config/p9_v2_training_controller.yml"), campaign_plan(matrix), contract)
    assert [item["configuration_id"] for item in completed] == ["cfg_d128", "cfg_k2", "cfg_k4", "cfg_k16"]
    assert eligibility.name == "p9elig_76f891b4a1072237a90a50d7.json"


def test_campaign_restore_rejects_unvalidated_skip(tmp_path):
    source = Path("/mnt/hdd002/dhnyu/fusedata/runtime/p9_a_campaigns/20260901_1450/campaign_status.json")
    if not source.is_file():
        pytest.skip("campaign audit status unavailable")
    status = json.loads(source.read_text())
    status["completed"][0]["checkpoint_id"] = "p9ck_" + "0" * 24
    root = tmp_path / "campaign"
    root.mkdir()
    (root / "campaign_status.json").write_text(json.dumps(status))
    contract = yaml.safe_load((ROOT / "config/p9_v2_training_controller.yml").read_text())
    matrix = json.loads((P8 / "hyperparameter_configuration_matrix.json").read_text())
    with pytest.raises(CampaignError, match="LIFECYCLE_RECORD_MISMATCH"):
        restore_campaign_progress(
            CampaignPaths(root, ROOT, ROOT / "config/p9_v2_training_controller.yml"), campaign_plan(matrix), contract)
