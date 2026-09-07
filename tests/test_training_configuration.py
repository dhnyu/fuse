from pathlib import Path
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from current_methodology import build_ofat, load_current_methodology
from training_configuration import (
    cache_requirements,
    expected_geometry_cache_entries,
    materialize_hyperparameter_configuration,
    reject_duplicate_formal_run,
    training_learning_rate,
    validate_terminal_outcome,
)


def test_all_current_ofat_rows_route_without_removed_objective():
    method = load_current_methodology(ROOT / "config/current_methodology.yml")
    rows = build_ofat(method)
    training = yaml.safe_load((ROOT / "config/training.yml").read_text())
    model = yaml.safe_load((ROOT / "config/model_inputs.yml").read_text())
    routed = [materialize_hyperparameter_configuration(row, training, model) for row in rows]
    assert len(routed) == 11
    assert len({item["scientific_hash"] for item in routed}) == 11
    assert all(not item["formal_authorized"] for item in routed)
    for item in routed:
        objective = item["training"]["objective"]
        assert not ({"lambda_IP", "lambda_ip", "information_preservation_weight", "reconstruction_loss"} & set(objective))
    by_id = {item["configuration_id"]: item for item in routed}
    assert by_id["ofat_d_64"]["model"]["model"]["d"] == 64
    assert by_id["ofat_d_256"]["training"]["queue"]["embedding_dimension"] == 256
    assert by_id["ofat_K_aug_16"]["training"]["training"]["logical_k"] == 16
    assert by_id["ofat_augmentation_intensity_2.0"]["training"]["training"]["profile_id"] == "strong_2.0x"
    assert by_id["ofat_ema_momentum_0.99"]["training"]["ema"]["coefficient"] == .990
    assert by_id["ofat_peak_learning_rate_0.005"]["training"]["optimizer"]["peak_learning_rate"] == .005


def test_current_row_validation_is_fail_closed():
    method = load_current_methodology(ROOT / "config/current_methodology.yml")
    row = build_ofat(method)[0]
    training = yaml.safe_load((ROOT / "config/training.yml").read_text())
    model = yaml.safe_load((ROOT / "config/model_inputs.yml").read_text())
    with pytest.raises(ValueError, match="incomplete"):
        materialize_hyperparameter_configuration({key: value for key, value in row.items() if key != "K_aug"}, training, model)
    legacy = {"configuration_id": "legacy", "scientific": {"lambda_ip": 1.0}}
    with pytest.raises(ValueError, match="incomplete"):
        materialize_hyperparameter_configuration(legacy, training, model)


def test_training_schedule_boundaries():
    assert training_learning_rate(1, 1e-3) == pytest.approx(1e-3 / 760)
    assert training_learning_rate(760, 1e-3) == 1e-3
    assert training_learning_rate(15200, 1e-3) == 0.0


def test_terminal_outcomes_and_duplicate_attempts_fail_closed():
    validate_terminal_outcome({"terminal_outcome": "SCIENTIFIC_DIVERGENCE", "last_valid_update": 10,
                               "detector": "finite_gate", "reason": "non_finite_loss",
                               "complete_trace_sha256": "a" * 64, "winner_eligible": False})
    with pytest.raises(ValueError, match="masquerade"):
        validate_terminal_outcome({"terminal_outcome": "SCIENTIFIC_DIVERGENCE", "infrastructure_failure": True})
    with pytest.raises(FileExistsError, match="duplicate formal"):
        reject_duplicate_formal_run([{"formal_attempt": True, "scientific_hash": "a", "seed": 3}], "a", 3)


def test_cache_requirements_follow_current_component_and_source_contracts():
    bank = {"profile_id": "main_1.0x", "effective_k": 8}
    assert cache_requirements("FM", bank)["relation_label_materialization"] == "heterogeneous"
    assert cache_requirements("A4", bank)["relation_label_materialization"] == "generic"
    assert cache_requirements("A5", bank)["relation_label_materialization"] == "heterogeneous"
    assert cache_requirements("B5", bank)["retained_sources"] == ("B",)
    assert cache_requirements("DS", bank)["ds_raster_cache"] is True
    assert expected_geometry_cache_entries(8) == 22368
