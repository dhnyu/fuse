from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from downstream_diagnostics import P11DiagnosticError, load_diagnostic_contract
from downstream_readiness import P11ReadinessError, load_readiness_contract
from spatial_ridge import P11RidgeError, load_ridge_contract


@pytest.mark.parametrize(
    ("path", "loader", "error"),
    [
        ("config/p11_diagnostic_probe_matrix.yml", load_diagnostic_contract, P11DiagnosticError),
        ("config/p11_spatial_readiness.yml", load_readiness_contract, P11ReadinessError),
        ("config/p11_ridge_evaluation.yml", load_ridge_contract, P11RidgeError),
    ],
)
def test_downstream_execution_is_closed_until_current_inputs_exist(path, loader, error):
    config = yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))
    assert config["migration_status"] == "RECOMPUTE_REQUIRED"
    with pytest.raises(error, match="CURRENT_INPUTS_PENDING_RECOMPUTATION"):
        loader(ROOT / path)


def test_downstream_contracts_use_current_population_and_comparison_count():
    dataset = yaml.safe_load((ROOT / "config/p11_downstream_dataset.yml").read_text(encoding="utf-8"))
    assert dataset["scene_universe_count"] == 9_000
    for path in ("python/downstream_readiness.py", "python/downstream_diagnostics.py", "python/spatial_ridge.py"):
        source = (ROOT / path).read_text(encoding="utf-8")
        assert "9000" in source
        assert "model_count\": 17" in source or "len(bindings) != 17" in source
