from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import jsonschema
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import pytest
import yaml

from p11_spatial_ridge import (
    P11RidgeError,
    _frame_hash,
    fit_ridge_fold,
    load_ridge_contract,
    materialize_p11_ridge_evaluation,
    pooled_metrics,
    run_determinism_pilot,
    validate_p11_ridge_acceptance,
)


ROOT = Path(__file__).resolve().parents[2]


def test_ridge_objective_and_train_only_standardization() -> None:
    train_x = np.array([[1.0, 5.0], [2.0, 5.0], [4.0, 5.0], [8.0, 5.0]])
    train_y = np.array([2.0, 3.0, 5.0, 9.0])
    test_x = np.array([[1000.0, 5.0]])
    result = fit_ridge_fold(train_x, train_y, test_x)
    np.testing.assert_array_equal(result["mean"], train_x.mean(axis=0))
    assert result["scale"][1] == 1.0
    assert result["zero_variance_indices"] == [1]
    assert result["coefficient"][1] == 0.0
    standardized = (train_x - result["mean"]) / result["scale"]
    gradient = (
        standardized.T
        @ (standardized @ result["coefficient"] + result["intercept"] - train_y)
        + result["coefficient"]
    )
    np.testing.assert_allclose(gradient, np.zeros(2), atol=1e-12)


def test_pooled_r2_is_sse_over_sst_not_squared_correlation() -> None:
    frame = pd.DataFrame(
        {
            "model": ["m"] * 3,
            "target": ["t"] * 3,
            "scene_id": ["a", "b", "c"],
            "observed": [1.0, 2.0, 4.0],
            "prediction": [1.5, 2.0, 3.0],
        }
    )
    result = pooled_metrics(frame).iloc[0]
    observed = np.array([1.0, 2.0, 4.0])
    predicted = np.array([1.5, 2.0, 3.0])
    expected = 1 - np.square(observed - predicted).sum() / np.square(observed - observed.mean()).sum()
    np.testing.assert_allclose(result.r2, expected, rtol=1e-15)
    np.testing.assert_allclose(result.rmse, np.sqrt(np.square(observed - predicted).mean()), rtol=1e-15)
    np.testing.assert_allclose(result.mae, np.abs(observed - predicted).mean(), rtol=1e-15)


def test_contract_and_bounded_determinism_pilot() -> None:
    contract = load_ridge_contract("config/p11_ridge_evaluation.yml")
    assert contract["ridge"]["lambda"] == 1.0
    assert contract["parallel_workers"] == 8
    result = run_determinism_pilot()
    assert result == {
        "status": "PASS",
        "fit_count": 100,
        "digest": "1493d031a3394d9f3a2e16549d215f7bd1329a0fe0b85d95f2bc66d000d19f86",
    }


def test_scientific_frame_hash_preserves_large_float64_values() -> None:
    frame = pd.DataFrame({"value": [2.0e13, 2.0e18], "runtime": [1.0, 2.0]})
    first = _frame_hash(frame, ("runtime",))
    second = _frame_hash(frame.assign(runtime=[99.0, 100.0]), ("runtime",))
    assert first == second


def test_canonical_acceptance_oof_metrics_and_equal_populations() -> None:
    pointer = yaml.safe_load((ROOT / "config/p11_ridge_evaluation_acceptance.yml").read_text())
    path = Path(pointer["acceptance_path"])
    assert hashlib.sha256(path.read_bytes()).hexdigest() == pointer["acceptance_sha256"]
    acceptance = validate_p11_ridge_acceptance(path.parent)
    schema = json.loads((ROOT / "config/schemas/p11_spatial_ridge_acceptance.schema.json").read_text())
    jsonschema.Draft202012Validator(schema).validate(acceptance)
    fits = pq.read_table(path.parent / "fold_fit_manifest.parquet").to_pandas()
    predictions = pq.read_table(path.parent / "oof_predictions.parquet").to_pandas()
    metrics = pq.read_table(path.parent / "pooled_metrics.parquet").to_pandas()
    readiness_root = Path(
        "/mnt/hdd002/dhnyu/fusedata/downstream_data/p11_readiness/"
        "p11c_e78d7c740edc49f1f646ebc3"
    )
    readiness_folds = pq.read_table(readiness_root / "target_fold_readiness.parquet").to_pandas()
    master = pq.read_table(readiness_root / "master_district_folds.parquet").to_pandas()
    assert len(fits) == fits.fit_id.nunique() == 2200
    assert fits.fit_success.all()
    assert len(predictions) == 128432
    assert not predictions.duplicated(["scene_id", "model", "target"]).any()
    assert np.isfinite(
        predictions[["observed", "transformed_response", "transformed_prediction", "prediction"]]
    ).all().all()
    assert len(metrics) == 88
    population = predictions.groupby(["model", "target"]).size().unstack("model")
    assert (population.nunique(axis=1) == 1).all()
    ownership = predictions.merge(
        master[["scene_id", "fold_id"]], on="scene_id", suffixes=("", "_master"), validate="many_to_one"
    )
    assert (ownership.fold_id == ownership.fold_id_master).all()
    expected_counts = fits.merge(
        readiness_folds[["target", "fold_id", "train_n", "test_n"]],
        on=["target", "fold_id"], suffixes=("", "_expected"), validate="many_to_one"
    )
    assert (expected_counts.train_n == expected_counts.train_n_expected).all()
    assert (expected_counts.test_n == expected_counts.test_n_expected).all()
    log_rows = predictions[predictions["transform"] == "log1p"]
    np.testing.assert_array_equal(
        log_rows.transformed_response.to_numpy(), np.log1p(log_rows.observed.to_numpy())
    )
    np.testing.assert_array_equal(
        log_rows.prediction.to_numpy(), np.expm1(log_rows.transformed_prediction.to_numpy())
    )


def test_complete_rerun_is_idempotent_and_corruption_is_rejected(tmp_path: Path) -> None:
    pointer = yaml.safe_load((ROOT / "config/p11_ridge_evaluation_acceptance.yml").read_text())
    acceptance_path = Path(pointer["acceptance_path"])
    before = acceptance_path.stat().st_mtime_ns
    result = materialize_p11_ridge_evaluation()
    assert result["acceptance_id"] == pointer["acceptance_id"]
    assert acceptance_path.stat().st_mtime_ns == before
    copied = tmp_path / "corrupt"
    shutil.copytree(acceptance_path.parent, copied)
    artifact = copied / "pooled_metrics.parquet"
    artifact.write_bytes(artifact.read_bytes() + b"\n")
    with pytest.raises(P11RidgeError, match="P11_E_ARTIFACT_CORRUPTION"):
        validate_p11_ridge_acceptance(copied, recompute_metrics=False)
