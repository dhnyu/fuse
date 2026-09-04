from __future__ import annotations

import json
import shutil
from pathlib import Path

import jsonschema
import numpy as np
import pyarrow.parquet as pq
import pytest
import yaml

from p11_diagnostic_probes import (
    GLOBAL_SEED,
    P11DiagnosticError,
    _mlp_fold,
    derive_fit_seed,
    load_diagnostic_contract,
    random_fold_assignment,
    materialize_p11_diagnostic_matrix,
    run_mlp_determinism_pilot,
    validate_p11_diagnostic_acceptance,
)
from p11_spatial_ridge import EXPECTED_MODELS, EXPECTED_TARGETS


ROOT = Path(__file__).resolve().parents[2]


def test_frozen_contract_and_random_fold_determinism() -> None:
    contract = load_diagnostic_contract(ROOT / "config/p11_diagnostic_probe_matrix.yml")
    assert contract["seed"]["global_seed"] == GLOBAL_SEED
    scene_ids = [f"scene_{index:04d}" for index in range(1600)]
    first = random_fold_assignment(scene_ids)
    second = random_fold_assignment(scene_ids)
    assert first.equals(second)
    assert first.groupby("random_fold").size().to_dict() == {0: 320, 1: 320, 2: 320, 3: 320, 4: 320}
    assert derive_fit_seed("m", "t", "f", "random") == derive_fit_seed("m", "t", "f", "random")


def test_mlp_outer_test_does_not_affect_fit_or_early_stopping() -> None:
    rng = np.random.Generator(np.random.PCG64(88))
    train_x = rng.normal(size=(80, 128))
    train_y = rng.normal(size=80)
    test_x = rng.normal(size=(10, 128))
    scene_ids = [f"train_{index}" for index in range(80)]
    test_ids = [f"test_{index}" for index in range(10)]
    contract = load_diagnostic_contract(ROOT / "config/p11_diagnostic_probe_matrix.yml")
    first = _mlp_fold("m", "t", "random", "random_0", train_x, train_y, scene_ids, test_x, test_ids, contract["mlp"])
    second = _mlp_fold("m", "t", "random", "random_0", train_x, train_y, scene_ids, test_x * 1000, test_ids, contract["mlp"])
    assert first["fit_id"] == second["fit_id"]
    for key in ("best_epoch", "epochs_executed", "best_inner_validation_loss", "final_training_loss"):
        assert first["diagnostic"][key] == second["diagnostic"][key]


def test_bounded_mlp_determinism_pilot() -> None:
    result = run_mlp_determinism_pilot()
    assert result == {
        "status": "PASS",
        "fit_count": 2,
        "digest": "5a23a7ec1c2c6a7cfb68ef0c715fa1662358ad3dbcc4307200059f43e40e8690",
    }


def test_published_acceptance_if_pointer_exists() -> None:
    pointer_path = ROOT / "config/p11_diagnostic_probe_acceptance.yml"
    if not pointer_path.exists():
        pytest.skip("P11-G acceptance has not yet been published")
    pointer = yaml.safe_load(pointer_path.read_text())
    root = Path(pointer["acceptance_path"]).parent
    acceptance = validate_p11_diagnostic_acceptance(root)
    schema = json.loads((ROOT / "config/schemas/p11_diagnostic_probe_acceptance.schema.json").read_text())
    jsonschema.Draft202012Validator(schema).validate(acceptance)
    metrics = pq.read_table(root / "diagnostic_metrics.parquet").to_pandas()
    assert len(metrics) == 8 * 11 * 4
    assert set(metrics.model) == set(EXPECTED_MODELS)
    assert set(metrics.target) == set(EXPECTED_TARGETS)
    before = (root / "p11_g_acceptance.json").stat().st_mtime_ns
    assert materialize_p11_diagnostic_matrix()["acceptance_id"] == pointer["acceptance_id"]
    assert (root / "p11_g_acceptance.json").stat().st_mtime_ns == before


def test_published_acceptance_rejects_corruption_if_pointer_exists(tmp_path: Path) -> None:
    pointer_path = ROOT / "config/p11_diagnostic_probe_acceptance.yml"
    if not pointer_path.exists():
        pytest.skip("P11-G acceptance has not yet been published")
    pointer = yaml.safe_load(pointer_path.read_text())
    copied = tmp_path / "corrupt"
    shutil.copytree(Path(pointer["acceptance_path"]).parent, copied)
    artifact = copied / "diagnostic_metrics.parquet"
    artifact.write_bytes(artifact.read_bytes() + b"x")
    with pytest.raises(P11DiagnosticError, match="P11_G_ARTIFACT_CORRUPTION"):
        validate_p11_diagnostic_acceptance(copied, recompute_metrics=False)
