"""P11-E deterministic district-held-out ridge probes and OOF evidence."""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import yaml
from threadpoolctl import threadpool_limits

from p10_evaluation import load_contract
from p11_spatial_readiness import (
    P11ReadinessError,
    apply_target_transform,
    invert_target_transform,
    validate_p11_spatial_readiness,
)
from p9_v2_canonical import canonical_json_bytes, canonical_sha256, sha256_file


class P11RidgeError(RuntimeError):
    """Stable fail-closed P11-E evidence or numerical contract error."""


EXPECTED_MODELS = (
    "cfg_d128",
    "cmp_a1_geometric_core",
    "cmp_a2_semantic_enriched",
    "cmp_a3_object_context_enriched",
    "cmp_a4_raster_complete_non_relational",
    "cmp_a5_relation_type_agnostic",
    "cmp_ssv_like",
    "cmp_ds_like",
)
EXPECTED_TARGETS = (
    "total_population",
    "households",
    "housing_units",
    "establishments",
    "workers",
    "weekday_daytime",
    "weekday_nighttime",
    "weekend_daytime",
    "weekend_nighttime",
    "official_land_value",
    "ecostress_lst",
)
NESTED_COMPARISONS = (
    ("entity_semantics", "cmp_a2_semantic_enriched", "cmp_a1_geometric_core"),
    ("object_environmental_context", "cmp_a3_object_context_enriched", "cmp_a2_semantic_enriched"),
    ("scene_raster_context", "cmp_a4_raster_complete_non_relational", "cmp_a3_object_context_enriched"),
    ("generic_relational_contextualization", "cmp_a5_relation_type_agnostic", "cmp_a4_raster_complete_non_relational"),
    ("heterogeneous_relation_identity", "cfg_d128", "cmp_a5_relation_type_agnostic"),
    ("intrinsic_geometry", "cmp_a2_semantic_enriched", "cmp_ssv_like"),
    ("full_model_vs_ds", "cfg_d128", "cmp_ds_like"),
)


def _json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise P11RidgeError(f"JSON_OBJECT_REQUIRED:{path}")
    return value


def load_ridge_contract(path: str | Path) -> dict[str, Any]:
    value = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if (
        value.get("contract_name") != "p11-spatial-ridge-v1"
        or tuple(value.get("models", ())) != EXPECTED_MODELS
        or tuple(value.get("targets", ())) != EXPECTED_TARGETS
        or value.get("ridge") != {
            "intercept": True,
            "lambda": 1.0,
            "solver": "float64_normal_equation_solve",
            "predictor_standard_deviation_ddof": 0,
            "zero_variance_scale": 1.0,
        }
    ):
        raise P11RidgeError("P11_E_CONTRACT_INVALID")
    return value


def _array_sha256(value: np.ndarray) -> str:
    array = np.ascontiguousarray(value)
    header = f"{array.dtype.str}|{','.join(map(str, array.shape))}|".encode("ascii")
    return hashlib.sha256(header + array.tobytes()).hexdigest()


def _readiness(contract: Mapping[str, Any]) -> tuple[Path, dict[str, Any]]:
    pointer = yaml.safe_load(Path(contract["readiness_pointer"]).read_text(encoding="utf-8"))
    path = Path(pointer["acceptance_path"])
    if sha256_file(path) != pointer["acceptance_sha256"]:
        raise P11RidgeError("P11_C_ACCEPTANCE_HASH_MISMATCH")
    acceptance = validate_p11_spatial_readiness(path.parent)
    required = {
        "readiness_id": "p11c_e78d7c740edc49f1f646ebc3",
        "master_fold_id": "p11fold_48a03eba108b799379891e4c",
        "embedding_binding_id": "p11emb_0fe61f9e1dc0faf640084abb",
        "dissertation_authority_id": "disauth_febd90b8475a5e9caa9f7d2f",
        "methodology_id": "p11meth_6cc844b7f5d1fc896d9e7be2",
        "downstream_dataset_id": "p11ds_39607da2de792ad6b3c9bb30",
        "p10_acceptance_id": "p10acc_6e5071beee7616750dec7907",
        "ridge_execution_authorized": True,
    }
    if any(acceptance.get(key) != expected for key, expected in required.items()):
        raise P11RidgeError("P11_C_AUTHORITY_MISMATCH")
    folds = pq.read_table(path.parent / "target_fold_readiness.parquet").to_pandas()
    if len(folds) != 2200 // 8 or not folds.evaluable.all():
        raise P11RidgeError("P11_C_FOLD_READINESS_INVALID")
    return path.parent, acceptance


def _methodology(contract: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    value = _json(contract["transformation_methodology"])
    if (
        value.get("methodology_id") != "p11meth_6cc844b7f5d1fc896d9e7be2"
        or value.get("ridge") != {"intercept": True, "lambda": 1, "alpha_tuning": False, "inner_cv": False}
    ):
        raise P11RidgeError("P11_E_METHODOLOGY_INVALID")
    transforms = {row["target"]: row["transform"] for row in value["transforms"]}
    if tuple(target for target in EXPECTED_TARGETS if target not in transforms) or len(transforms) != 11:
        raise P11RidgeError("P11_E_TRANSFORM_MAP_INVALID")
    return value, transforms


def _dataset(contract: Mapping[str, Any]) -> tuple[dict[str, Any], pd.DataFrame]:
    pointer = yaml.safe_load(Path(contract["downstream_dataset_pointer"]).read_text(encoding="utf-8"))
    path = Path(pointer["acceptance_path"])
    if sha256_file(path) != pointer["acceptance_sha256"]:
        raise P11RidgeError("P11_E_DATASET_ACCEPTANCE_HASH_MISMATCH")
    acceptance = _json(path)
    if acceptance.get("dataset_id") != "p11ds_39607da2de792ad6b3c9bb30":
        raise P11RidgeError("P11_E_DATASET_ID_INVALID")
    targets = pq.read_table(path.parent / "scene_targets.parquet").to_pandas()
    if len(targets) != 17600 or targets.scene_id.nunique() != 1600 or targets.target.nunique() != 11:
        raise P11RidgeError("P11_E_DATASET_CARDINALITY_INVALID")
    return acceptance, targets


def _inputs(contract: Mapping[str, Any]) -> dict[str, Any]:
    readiness_root, readiness = _readiness(contract)
    methodology, transforms = _methodology(contract)
    dataset, targets = _dataset(contract)
    master = pq.read_table(readiness_root / "master_district_folds.parquet").to_pandas()
    fold_rows = pq.read_table(readiness_root / "target_fold_readiness.parquet").to_pandas()
    bindings = json.loads((readiness_root / "embedding_bindings.json").read_text(encoding="utf-8"))
    if len(bindings) != 8 or tuple(row["configuration_id"] for row in bindings) != EXPECTED_MODELS:
        raise P11RidgeError("P11_E_MODEL_BINDINGS_INVALID")
    p10 = load_contract(contract["p10_contract"])
    p10_acceptance_path = (
        Path(p10["publication_root"]) / "execution_attempts" / "p10exec_7fee193dac532190c79e02c6"
        / "commit" / "evaluation_acceptance.json"
    )
    if _json(p10_acceptance_path).get("acceptance_id") != "p10acc_6e5071beee7616750dec7907":
        raise P11RidgeError("P11_E_P10_ACCEPTANCE_INVALID")
    gallery_ids = master.scene_id.astype(str).tolist()
    if len(gallery_ids) != 1600 or len(set(gallery_ids)) != 1600:
        raise P11RidgeError("P11_E_MASTER_SCENES_INVALID")
    embeddings: dict[str, np.ndarray] = {}
    common_scene_hashes = set()
    for binding in bindings:
        path = Path(p10["publication_root"]) / binding["logical_locator"]
        if sha256_file(path) != binding["stored_array_sha256"]:
            raise P11RidgeError(f"P11_E_EMBEDDING_FILE_HASH_MISMATCH:{binding['configuration_id']}")
        with np.load(path, allow_pickle=False) as arrays:
            full = np.asarray(arrays["embeddings"])
            if full.shape != (4800, 128) or full.dtype != np.float32:
                raise P11RidgeError(f"P11_E_EMBEDDING_SHAPE_INVALID:{binding['configuration_id']}")
            if hashlib.sha256(full.tobytes()).hexdigest() != binding["full_embedding_sha256"]:
                raise P11RidgeError(f"P11_E_FULL_EMBEDDING_HASH_MISMATCH:{binding['configuration_id']}")
            gallery = np.ascontiguousarray(full[3200:], dtype=np.float64)
        if hashlib.sha256(gallery.astype(np.float32).tobytes()).hexdigest() != binding["gallery_embedding_sha256"]:
            raise P11RidgeError(f"P11_E_GALLERY_EMBEDDING_HASH_MISMATCH:{binding['configuration_id']}")
        embeddings[binding["configuration_id"]] = gallery
        common_scene_hashes.add(binding["gallery_scene_ids_sha256"])
    if len(common_scene_hashes) != 1:
        raise P11RidgeError("P11_E_MODEL_POPULATION_MISMATCH")
    target_groups: dict[str, pd.DataFrame] = {}
    for target in EXPECTED_TARGETS:
        group = targets[(targets.target == target) & targets.eligible].copy()
        group = master[["scene_id", "district_id", "fold_id"]].merge(
            group[["scene_id", "response"]], on="scene_id", how="inner", validate="one_to_one"
        )
        group["embedding_row"] = group.scene_id.map({scene: index for index, scene in enumerate(gallery_ids)})
        if group.embedding_row.isna().any() or not np.isfinite(group.response.to_numpy(dtype=np.float64)).all():
            raise P11RidgeError(f"P11_E_TARGET_VALUES_INVALID:{target}")
        apply_target_transform(group.response.to_numpy(dtype=np.float64), transforms[target])
        target_groups[target] = group.sort_values("scene_id", kind="mergesort").reset_index(drop=True)
    return {
        "readiness_root": readiness_root,
        "readiness": readiness,
        "methodology": methodology,
        "transforms": transforms,
        "dataset": dataset,
        "targets": target_groups,
        "master": master,
        "fold_rows": fold_rows,
        "bindings": bindings,
        "embeddings": embeddings,
        "gallery_ids": gallery_ids,
        "p10_acceptance_path": p10_acceptance_path,
    }


def fit_ridge_fold(
    train_x: np.ndarray,
    train_y: np.ndarray,
    test_x: np.ndarray,
    ridge_lambda: float = 1.0,
) -> dict[str, Any]:
    train_x = np.asarray(train_x, dtype=np.float64)
    test_x = np.asarray(test_x, dtype=np.float64)
    train_y = np.asarray(train_y, dtype=np.float64)
    if train_x.ndim != 2 or test_x.ndim != 2 or train_x.shape[1] != test_x.shape[1]:
        raise P11RidgeError("RIDGE_PREDICTOR_SHAPE_INVALID")
    if len(train_x) != len(train_y) or len(train_x) == 0 or len(test_x) == 0:
        raise P11RidgeError("RIDGE_FOLD_POPULATION_INVALID")
    if not np.isfinite(train_x).all() or not np.isfinite(test_x).all() or not np.isfinite(train_y).all():
        raise P11RidgeError("RIDGE_INPUT_NONFINITE")
    mean = train_x.mean(axis=0)
    scale = train_x.std(axis=0, ddof=0)
    zero = scale == 0
    scale[zero] = 1.0
    x_train = (train_x - mean) / scale
    x_test = (test_x - mean) / scale
    intercept = float(train_y.mean())
    centered_y = train_y - intercept
    gram = x_train.T @ x_train
    coefficient = np.linalg.solve(
        gram + float(ridge_lambda) * np.eye(train_x.shape[1], dtype=np.float64),
        x_train.T @ centered_y,
    )
    prediction = intercept + x_test @ coefficient
    if not all(np.isfinite(value).all() for value in (mean, scale, coefficient, prediction)):
        raise P11RidgeError("RIDGE_OUTPUT_NONFINITE")
    return {
        "mean": mean,
        "scale": scale,
        "zero_variance_indices": np.flatnonzero(zero).astype(int).tolist(),
        "coefficient": coefficient,
        "intercept": intercept,
        "prediction": prediction,
    }


def _fit_model_target(
    model: str,
    target: str,
    embeddings: np.ndarray,
    target_rows: pd.DataFrame,
    transform: str,
    fold_identity: str,
    embedding_identity: str,
) -> dict[str, list[dict[str, Any]]]:
    manifests: list[dict[str, Any]] = []
    scalings: list[dict[str, Any]] = []
    coefficients: list[dict[str, Any]] = []
    predictions: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    transformed = apply_target_transform(target_rows.response.to_numpy(dtype=np.float64), transform)
    response_by_index = dict(zip(target_rows.index, transformed))
    eligibility_hash = canonical_sha256({
        "dataset_id": "p11ds_39607da2de792ad6b3c9bb30",
        "target": target,
        "eligible_scene_ids": target_rows.scene_id.tolist(),
    })
    for district in sorted(target_rows.district_id.unique()):
        started = time.perf_counter()
        train = target_rows[target_rows.district_id != district]
        test = target_rows[target_rows.district_id == district]
        train_indices = train.embedding_row.to_numpy(dtype=np.int64)
        test_indices = test.embedding_row.to_numpy(dtype=np.int64)
        train_y = np.asarray([response_by_index[index] for index in train.index], dtype=np.float64)
        result = fit_ridge_fold(embeddings[train_indices], train_y, embeddings[test_indices])
        runtime = time.perf_counter() - started
        scale_preimage = {
            "model": model,
            "target": target,
            "fold_id": f"district_{district}",
            "training_scene_ids_sha256": canonical_sha256(train.scene_id.tolist()),
            "mean_sha256": _array_sha256(result["mean"]),
            "scale_sha256": _array_sha256(result["scale"]),
            "zero_variance_indices": result["zero_variance_indices"],
            "ddof": 0,
        }
        scale_hash = canonical_sha256(scale_preimage)
        scaling_id = f"p11scale_{scale_hash[:24]}"
        coefficient_preimage = {
            "scaling_id": scaling_id,
            "training_target_sha256": _array_sha256(train_y),
            "coefficient_sha256": _array_sha256(result["coefficient"]),
            "intercept": result["intercept"],
            "lambda": 1.0,
            "solver": "float64_normal_equation_solve",
        }
        fit_hash = canonical_sha256(coefficient_preimage)
        fit_id = f"p11fit_{fit_hash[:24]}"
        manifests.append({
            "fit_id": fit_id, "model": model, "target": target,
            "fold_id": f"district_{district}", "district_id": str(district),
            "train_n": len(train), "test_n": len(test), "transform": transform,
            "scaling_id": scaling_id, "lambda": 1.0, "intercept_enabled": True,
            "solver": "float64_normal_equation_solve", "fit_success": True,
        })
        scalings.append({
            "scaling_id": scaling_id, "model": model, "target": target,
            "fold_id": f"district_{district}",
            "training_scene_ids_sha256": scale_preimage["training_scene_ids_sha256"],
            "mean": result["mean"].tolist(), "standard_deviation": result["scale"].tolist(),
            "zero_variance_indices": result["zero_variance_indices"], "ddof": 0,
        })
        coefficients.append({
            "fit_id": fit_id, "scaling_id": scaling_id, "model": model, "target": target,
            "fold_id": f"district_{district}", "coefficient": result["coefficient"].tolist(),
            "intercept": result["intercept"], "coefficient_norm": float(np.linalg.norm(result["coefficient"])),
        })
        test_transformed = np.asarray([response_by_index[index] for index in test.index], dtype=np.float64)
        original_prediction = invert_target_transform(result["prediction"], transform)
        residual = test.response.to_numpy(dtype=np.float64) - original_prediction
        diagnostics.append({
            "fit_id": fit_id, "model": model, "target": target,
            "fold_id": f"district_{district}", "train_n": len(train), "test_n": len(test),
            "train_response_variance": float(np.var(train.response.to_numpy(dtype=np.float64), ddof=0)),
            "coefficient_norm": float(np.linalg.norm(result["coefficient"])),
            "intercept": result["intercept"],
            "prediction_min": float(original_prediction.min()),
            "prediction_max": float(original_prediction.max()),
            "residual_mean": float(residual.mean()), "residual_sd": float(residual.std(ddof=0)),
            "fit_runtime_seconds": runtime, "zero_variance_dimension_count": len(result["zero_variance_indices"]),
            "numerical_status": "PASS",
        })
        for row, observed_t, predicted_t, predicted in zip(
            test.itertuples(index=False), test_transformed, result["prediction"], original_prediction
        ):
            predictions.append({
                "scene_id": row.scene_id, "district_id": str(row.district_id), "fold_id": row.fold_id,
                "model": model, "target": target, "observed": float(row.response),
                "transformed_response": float(observed_t), "transformed_prediction": float(predicted_t),
                "prediction": float(predicted), "transform": transform,
                "eligibility_sha256": eligibility_hash, "embedding_binding_id": embedding_identity,
                "master_fold_id": fold_identity, "fit_id": fit_id,
            })
    return {
        "manifests": manifests,
        "scalings": scalings,
        "coefficients": coefficients,
        "predictions": predictions,
        "diagnostics": diagnostics,
    }


def pooled_metrics(predictions: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (model, target), group in predictions.sort_values(
        ["model", "target", "scene_id"], kind="mergesort"
    ).groupby(["model", "target"], sort=True):
        observed = group.observed.to_numpy(dtype=np.float64)
        predicted = group.prediction.to_numpy(dtype=np.float64)
        residual = observed - predicted
        sse = float(residual @ residual)
        centered = observed - observed.mean()
        sst = float(centered @ centered)
        if not math.isfinite(sst) or sst <= 0:
            raise P11RidgeError(f"POOLED_TARGET_VARIANCE_INVALID:{target}")
        rows.append({
            "model": model, "target": target, "eligible_n": len(group),
            "r2": 1.0 - sse / sst,
            "rmse": math.sqrt(sse / len(group)),
            "mae": float(np.abs(residual).mean()),
            "sse": sse, "sst": sst,
        })
    return pd.DataFrame(rows).sort_values(["target", "model"], kind="mergesort").reset_index(drop=True)


def _comparisons(metrics: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    indexed = metrics.set_index(["target", "model"])
    fm_rows = []
    for row in metrics.itertuples(index=False):
        fm = indexed.loc[(row.target, "cfg_d128")]
        fm_rows.append({
            "target": row.target, "model": row.model, "eligible_n": row.eligible_n,
            "delta_r2_model_minus_fm": row.r2 - fm.r2,
            "delta_rmse_model_minus_fm": row.rmse - fm.rmse,
            "delta_mae_model_minus_fm": row.mae - fm.mae,
        })
    nested = []
    for target in EXPECTED_TARGETS:
        for name, left, right in NESTED_COMPARISONS:
            left_row = indexed.loc[(target, left)]
            right_row = indexed.loc[(target, right)]
            nested.append({
                "target": target, "comparison": name, "left_model": left, "right_model": right,
                "delta_r2_left_minus_right": left_row.r2 - right_row.r2,
                "delta_rmse_left_minus_right": left_row.rmse - right_row.rmse,
                "delta_mae_left_minus_right": left_row.mae - right_row.mae,
            })
    return pd.DataFrame(fm_rows), pd.DataFrame(nested)


def _write_parquet(frame: pd.DataFrame, path: Path) -> None:
    table = pa.Table.from_pandas(frame, preserve_index=False)
    pq.write_table(table, path, compression="zstd", version="2.6", write_statistics=True)


def _frame_hash(frame: pd.DataFrame, exclude: tuple[str, ...] = ()) -> str:
    value = frame.drop(columns=list(exclude), errors="ignore")
    sink = pa.BufferOutputStream()
    table = pa.Table.from_pandas(value, preserve_index=False)
    with pa.ipc.new_stream(sink, table.schema) as writer:
        writer.write_table(table)
    return hashlib.sha256(sink.getvalue().to_pybytes()).hexdigest()


def _validate_oof(predictions: pd.DataFrame, inputs: Mapping[str, Any]) -> int:
    expected_per_target = {target: len(group) for target, group in inputs["targets"].items()}
    expected = sum(expected_per_target.values()) * len(EXPECTED_MODELS)
    if len(predictions) != expected:
        raise P11RidgeError(f"OOF_CARDINALITY_INVALID:{len(predictions)}:{expected}")
    keys = ["scene_id", "model", "target"]
    if predictions.duplicated(keys).any():
        raise P11RidgeError("OOF_DUPLICATE_PREDICTION")
    if not np.isfinite(predictions[["observed", "transformed_response", "transformed_prediction", "prediction"]]).all().all():
        raise P11RidgeError("OOF_NONFINITE")
    for model in EXPECTED_MODELS:
        for target in EXPECTED_TARGETS:
            actual = set(predictions[(predictions.model == model) & (predictions.target == target)].scene_id)
            required = set(inputs["targets"][target].scene_id)
            if actual != required:
                raise P11RidgeError(f"OOF_COVERAGE_MISMATCH:{model}:{target}")
    return expected


def run_determinism_pilot(path: str | Path = "config/p11_ridge_evaluation.yml") -> dict[str, Any]:
    contract = load_ridge_contract(path)
    inputs = _inputs(contract)
    digests = []
    for _ in range(2):
        outputs = []
        for model, target in ((EXPECTED_MODELS[0], EXPECTED_TARGETS[0]), (EXPECTED_MODELS[-1], EXPECTED_TARGETS[-1])):
            value = _fit_model_target(
                model, target, inputs["embeddings"][model], inputs["targets"][target],
                inputs["transforms"][target], inputs["readiness"]["master_fold_id"],
                inputs["readiness"]["embedding_binding_id"],
            )
            outputs.extend(value["predictions"])
            for row in value["diagnostics"]:
                row.pop("fit_runtime_seconds", None)
            outputs.extend(value["diagnostics"])
        digests.append(canonical_sha256(outputs))
    if digests[0] != digests[1]:
        raise P11RidgeError("P11_E_DETERMINISM_PILOT_FAILED")
    return {"status": "PASS", "fit_count": 100, "digest": digests[0]}


def validate_p11_ridge_acceptance(root: str | Path, recompute_metrics: bool = True) -> dict[str, Any]:
    root = Path(root)
    acceptance = _json(root / "p11_e_acceptance.json")
    preimage = {key: value for key, value in acceptance.items() if key not in {"acceptance_id", "content_sha256", "status", "artifacts"}}
    digest = canonical_sha256(preimage)
    if (
        acceptance.get("acceptance_id") != f"p11e_{digest[:24]}"
        or acceptance.get("content_sha256") != digest
        or acceptance.get("status") != "PASS"
    ):
        raise P11RidgeError("P11_E_ACCEPTANCE_IDENTITY_INVALID")
    for artifact in acceptance.get("artifacts", []):
        path = root / artifact["basename"]
        if not path.is_file() or path.stat().st_size != artifact["byte_size"] or sha256_file(path) != artifact["sha256"]:
            raise P11RidgeError(f"P11_E_ARTIFACT_CORRUPTION:{artifact['basename']}")
    if recompute_metrics:
        predictions = pq.read_table(root / "oof_predictions.parquet").to_pandas()
        stored = pq.read_table(root / "pooled_metrics.parquet").to_pandas()
        reproduced = pooled_metrics(predictions)
        numeric = ["r2", "rmse", "mae", "sse", "sst"]
        if not np.array_equal(stored[["model", "target", "eligible_n"]].to_numpy(), reproduced[["model", "target", "eligible_n"]].to_numpy()):
            raise P11RidgeError("P11_E_METRIC_KEYS_MISMATCH")
        if not np.array_equal(stored[numeric].to_numpy(dtype=np.float64), reproduced[numeric].to_numpy(dtype=np.float64)):
            raise P11RidgeError("P11_E_METRIC_RECOMPUTATION_MISMATCH")
    return acceptance


def materialize_p11_ridge_evaluation(path: str | Path = "config/p11_ridge_evaluation.yml") -> dict[str, Any]:
    contract = load_ridge_contract(path)
    inputs = _inputs(contract)
    started = time.perf_counter()
    tasks = [(model, target) for model in EXPECTED_MODELS for target in EXPECTED_TARGETS]

    def run(task: tuple[str, str]) -> dict[str, list[dict[str, Any]]]:
        model, target = task
        return _fit_model_target(
            model, target, inputs["embeddings"][model], inputs["targets"][target],
            inputs["transforms"][target], inputs["readiness"]["master_fold_id"],
            inputs["readiness"]["embedding_binding_id"],
        )

    with threadpool_limits(limits=int(contract["blas_threads_per_worker"])), ThreadPoolExecutor(
        max_workers=int(contract["parallel_workers"])
    ) as executor:
        task_results = list(executor.map(run, tasks))
    combined = {key: [] for key in ("manifests", "scalings", "coefficients", "predictions", "diagnostics")}
    for result in task_results:
        for key in combined:
            combined[key].extend(result[key])
    manifests = pd.DataFrame(combined["manifests"]).sort_values(["model", "target", "district_id"], kind="mergesort").reset_index(drop=True)
    scalings = pd.DataFrame(combined["scalings"]).sort_values(["model", "target", "fold_id"], kind="mergesort").reset_index(drop=True)
    coefficients = pd.DataFrame(combined["coefficients"]).sort_values(["model", "target", "fold_id"], kind="mergesort").reset_index(drop=True)
    predictions = pd.DataFrame(combined["predictions"]).sort_values(["model", "target", "scene_id"], kind="mergesort").reset_index(drop=True)
    diagnostics = pd.DataFrame(combined["diagnostics"]).sort_values(["model", "target", "fold_id"], kind="mergesort").reset_index(drop=True)
    expected_oof = _validate_oof(predictions, inputs)
    if len(manifests) != 2200 or not manifests.fit_success.all() or len(scalings) != 2200 or len(coefficients) != 2200 or len(diagnostics) != 2200:
        raise P11RidgeError("P11_E_FIT_CARDINALITY_INVALID")
    metrics = pooled_metrics(predictions)
    if len(metrics) != 88:
        raise P11RidgeError("P11_E_METRIC_CARDINALITY_INVALID")
    fm, nested = _comparisons(metrics)
    runtime = {
        "execution_strategy": "8 model-target thread workers; one BLAS thread; 25 folds sequential per task",
        "parallel_workers": int(contract["parallel_workers"]),
        "blas_threads_per_worker": int(contract["blas_threads_per_worker"]),
        "wall_seconds": time.perf_counter() - started,
        "fit_runtime_seconds": {
            "median": float(diagnostics.fit_runtime_seconds.median()),
            "p95": float(diagnostics.fit_runtime_seconds.quantile(0.95)),
            "maximum": float(diagnostics.fit_runtime_seconds.max()),
        },
    }
    frames = {
        "fold_fit_manifest.parquet": manifests,
        "scaling_parameters.parquet": scalings,
        "ridge_coefficients.parquet": coefficients,
        "oof_predictions.parquet": predictions,
        "fold_diagnostics.parquet": diagnostics,
        "pooled_metrics.parquet": metrics,
        "fm_relative_deltas.parquet": fm,
        "nested_ablation_deltas.parquet": nested,
    }
    scientific_hashes = {
        name: _frame_hash(frame, ("fit_runtime_seconds",)) for name, frame in frames.items()
    }
    preimage = {
        "schema_version": "1.0.0",
        "artifact_type": "p11_spatial_ridge_oof_acceptance",
        "implementation_version": "p11-spatial-ridge-v1",
        "implementation_sha256": sha256_file(Path(__file__)),
        "dissertation_authority_id": "disauth_febd90b8475a5e9caa9f7d2f",
        "transformation_methodology_id": "p11meth_6cc844b7f5d1fc896d9e7be2",
        "p11_c_acceptance_id": inputs["readiness"]["readiness_id"],
        "master_fold_id": inputs["readiness"]["master_fold_id"],
        "embedding_binding_id": inputs["readiness"]["embedding_binding_id"],
        "downstream_dataset_id": inputs["dataset"]["dataset_id"],
        "p10_acceptance_id": "p10acc_6e5071beee7616750dec7907",
        "model_count": 8, "target_count": 11, "fold_count": 25,
        "fit_count": 2200, "oof_row_count": expected_oof, "metric_row_count": 88,
        "ridge_lambda": 1.0, "intercept": True,
        "scientific_output_sha256": scientific_hashes,
        "next_work_unit": contract["next_work_unit"],
    }
    identity_hash = canonical_sha256(preimage)
    acceptance_id = f"p11e_{identity_hash[:24]}"
    final = Path(contract["publication_root"]) / acceptance_id
    if final.exists():
        return validate_p11_ridge_acceptance(final)
    final.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{acceptance_id}.", dir=final.parent))
    for name, frame in frames.items():
        _write_parquet(frame, stage / name)
    (stage / "runtime_summary.json").write_bytes(canonical_json_bytes(runtime))
    artifacts = []
    for artifact_path in sorted(stage.iterdir(), key=lambda item: item.name):
        artifacts.append({"basename": artifact_path.name, "byte_size": artifact_path.stat().st_size, "sha256": sha256_file(artifact_path)})
    acceptance = {**preimage, "acceptance_id": acceptance_id, "content_sha256": identity_hash, "status": "PASS", "artifacts": artifacts}
    (stage / "p11_e_acceptance.json").write_bytes(canonical_json_bytes(acceptance))
    os.rename(stage, final)
    return validate_p11_ridge_acceptance(final)
