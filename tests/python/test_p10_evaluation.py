from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from current_methodology import COMPARISON_NAMES
from p10_evaluation import CURRENT_MODEL_IDS, P10Error, load_contract


def test_current_evaluation_contract_is_closed_and_pending_recomputation():
    path = ROOT / "config/p10_evaluation.yml"
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert tuple(item["configuration_id"] for item in value["model_set"]) == COMPARISON_NAMES == CURRENT_MODEL_IDS
    assert value["accepted_evaluation"]["original_count"] == 9000
    assert value["validation_revalidation"]["original_count"] == 1000
    assert {item["acceptance_id"] for item in value["model_set"]} == {"PENDING_RECOMPUTATION"}
    with pytest.raises(P10Error, match="PENDING_RECOMPUTATION"):
        load_contract(path)


def test_evaluation_contract_prohibits_training_side_effects():
    value = yaml.safe_load((ROOT / "config/p10_evaluation.yml").read_text(encoding="utf-8"))
    assert value["execution"]["optimizer_updates"] == 0
    assert value["execution"]["checkpoint_writes"] == 0
