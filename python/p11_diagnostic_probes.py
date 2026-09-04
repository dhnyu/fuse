"""P11-G fixed spatial/random and ridge/MLP diagnostic probe matrix."""

from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
import tempfile
import threading
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import yaml
from threadpoolctl import threadpool_limits

from p11_spatial_readiness import apply_target_transform, invert_target_transform
from p11_spatial_ridge import (
    EXPECTED_MODELS,
    EXPECTED_TARGETS,
    P11RidgeError,
    _array_sha256,
    _frame_hash,
    _inputs,
    fit_ridge_fold,
    load_ridge_contract,
    pooled_metrics,
    validate_p11_ridge_acceptance,
)
from p9_v2_canonical import canonical_json_bytes, canonical_sha256, sha256_file


class P11DiagnosticError(RuntimeError):
    """Stable fail-closed diagnostic probe contract or evidence error."""


GLOBAL_SEED = 4824802954555229827
PROBE_CELLS = (
    ("spatial", "ridge"),
    ("random", "ridge"),
    ("spatial", "mlp"),
    ("random", "mlp"),
)


def _gpu_worker_init(device_index: int) -> None:
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    import torch
    torch.cuda.set_device(device_index)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    torch.use_deterministic_algorithms(True)
    torch.empty(1, device=f"cuda:{device_index}")


def _monitor_gpus(stop: threading.Event, samples: list[dict[str, Any]]) -> None:
    while not stop.wait(1.0):
        completed = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,name,utilization.gpu,memory.used,power.draw",
             "--format=csv,noheader,nounits"], capture_output=True, text=True, check=False,
        )
        if completed.returncode != 0:
            continue
        for line in completed.stdout.splitlines():
            fields = [field.strip() for field in line.split(",")]
            if len(fields) == 5 and fields[0] in {"0", "1"}:
                samples.append({
                    "gpu": int(fields[0]), "name": fields[1], "utilization_percent": float(fields[2]),
                    "memory_used_mib": float(fields[3]), "power_watts": float(fields[4]),
                })


def _json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise P11DiagnosticError(f"JSON_OBJECT_REQUIRED:{path}")
    return value


def load_diagnostic_contract(path: str | Path) -> dict[str, Any]:
    value = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    expected_seed_hash = hashlib.sha256(value["seed"]["preimage"].encode("utf-8")).hexdigest()
    derived = int.from_bytes(bytes.fromhex(expected_seed_hash)[:8], "big") & ((1 << 63) - 1)
    required_mlp = {
        "architecture": [128, 64, 1], "activation": "GELU_exact", "dropout": 0.1,
        "optimizer": "AdamW", "learning_rate": 0.001, "weight_decay": 0.0001,
        "betas": [0.9, 0.999], "epsilon": 1.0e-8, "batch_size": 64,
        "maximum_epochs": 200, "inner_validation_fraction": 0.1,
        "inner_validation_count": "floor_10_percent_of_outer_train", "patience": 20,
        "improvement_rule": "strictly_lower_transformed_scale_mse", "restore_best": True,
        "target_standardization": False, "predictor_standardization": "inner_training_partition_only",
        "dtype": "float32", "deterministic_algorithms": True,
    }
    if (
        value.get("contract_name") != "p11-diagnostic-probe-matrix-v1"
        or value.get("status") != "FROZEN_BEFORE_DIAGNOSTIC_FITTING"
        or value["seed"].get("sha256") != expected_seed_hash
        or value["seed"].get("global_seed") != derived
        or derived != GLOBAL_SEED
        or value.get("random_cv") != {
            "folds": 5, "algorithm": "numpy_pcg64_permutation_then_round_robin",
            "target_independent": True, "stratified": False,
        }
        or value.get("mlp") != required_mlp
        or value.get("execution") != {
            "backend": "dual_cuda_task_parallel", "gpu_indices": [0, 1],
            "persistent_workers_per_gpu": 2, "allow_tf32": False, "mixed_precision": False,
            "cpu_gpu_equivalence": {
                "prediction_atol": 0.001, "prediction_rtol": 0.0001,
                "validation_loss_atol": 0.0001, "metric_atol": 0.001,
                "best_epoch_tolerance": 1,
            },
        }
    ):
        raise P11DiagnosticError("P11_G_CONTRACT_INVALID")
    return value


def derive_fit_seed(model: str, target: str, fold_id: str, cv_regime: str) -> int:
    preimage = f"{GLOBAL_SEED}|{model}|{target}|{fold_id}|{cv_regime}"
    digest = hashlib.sha256(preimage.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") & ((1 << 63) - 1)


def random_fold_assignment(scene_ids: list[str]) -> pd.DataFrame:
    if len(scene_ids) != 1600 or len(set(scene_ids)) != 1600:
        raise P11DiagnosticError("P11_G_RANDOM_SCENE_UNIVERSE_INVALID")
    generator = np.random.Generator(np.random.PCG64(GLOBAL_SEED))
    permutation = generator.permutation(len(scene_ids))
    assignment = np.empty(len(scene_ids), dtype=np.int8)
    assignment[permutation] = np.arange(len(scene_ids), dtype=np.int64) % 5
    result = pd.DataFrame({"scene_id": scene_ids, "random_fold": assignment})
    result["fold_id"] = result.random_fold.map(lambda value: f"random_{value}")
    if sorted(result.groupby("random_fold").size().tolist()) != [320] * 5:
        raise P11DiagnosticError("P11_G_RANDOM_FOLD_BALANCE_INVALID")
    return result


def _validate_inputs(contract: Mapping[str, Any]) -> dict[str, Any]:
    inputs = _inputs(load_ridge_contract(contract["input_contract"]))
    pointer = yaml.safe_load(Path(contract["p11_e_acceptance_pointer"]).read_text(encoding="utf-8"))
    path = Path(pointer["acceptance_path"])
    if sha256_file(path) != pointer["acceptance_sha256"]:
        raise P11DiagnosticError("P11_E_ACCEPTANCE_HASH_MISMATCH")
    p11e = validate_p11_ridge_acceptance(path.parent)
    expected = {
        "dissertation_authority_id": "disauth_febd90b8475a5e9caa9f7d2f",
        "transformation_methodology_id": "p11meth_6cc844b7f5d1fc896d9e7be2",
        "p11_c_acceptance_id": "p11c_e78d7c740edc49f1f646ebc3",
        "downstream_dataset_id": "p11ds_39607da2de792ad6b3c9bb30",
        "embedding_binding_id": "p11emb_0fe61f9e1dc0faf640084abb",
    }
    if any(contract.get(key) != value for key, value in expected.items()):
        raise P11DiagnosticError("P11_G_AUTHORITY_INPUT_MISMATCH")
    if p11e.get("acceptance_id") != "p11e_047e764ed7467b72ebe846df":
        raise P11DiagnosticError("P11_G_BASELINE_ACCEPTANCE_INVALID")
    inputs["p11e"] = p11e
    inputs["p11e_root"] = path.parent
    inputs["random_folds"] = random_fold_assignment(inputs["gallery_ids"])
    for target, rows in inputs["targets"].items():
        test = rows.merge(inputs["random_folds"], on="scene_id", validate="one_to_one")
        if test.groupby("random_fold").size().min() <= 0:
            raise P11DiagnosticError(f"P11_G_RANDOM_TARGET_FOLD_EMPTY:{target}")
    return inputs


def _ridge_random_model_target(
    model: str, target: str, embeddings: np.ndarray, target_rows: pd.DataFrame,
    transforms: Mapping[str, str], random_folds: pd.DataFrame,
) -> dict[str, list[dict[str, Any]]]:
    rows = target_rows.merge(random_folds, on="scene_id", validate="one_to_one")
    transformed = apply_target_transform(rows.response.to_numpy(dtype=np.float64), transforms[target])
    y_by_scene = dict(zip(rows.scene_id, transformed))
    predictions = []
    diagnostics = []
    for fold in range(5):
        train = rows[rows.random_fold != fold]
        test = rows[rows.random_fold == fold]
        train_y = np.asarray([y_by_scene[scene] for scene in train.scene_id], dtype=np.float64)
        started = time.perf_counter()
        result = fit_ridge_fold(
            embeddings[train.embedding_row.to_numpy(dtype=np.int64)], train_y,
            embeddings[test.embedding_row.to_numpy(dtype=np.int64)],
        )
        elapsed = time.perf_counter() - started
        fit_preimage = {
            "model": model, "target": target, "cv_regime": "random", "probe": "ridge",
            "fold_id": f"random_{fold}", "seed": str(GLOBAL_SEED),
            "train_scene_ids_sha256": canonical_sha256(sorted(train.scene_id.tolist())),
            "test_scene_ids_sha256": canonical_sha256(sorted(test.scene_id.tolist())),
            "mean_sha256": _array_sha256(result["mean"]), "scale_sha256": _array_sha256(result["scale"]),
            "coefficient_sha256": _array_sha256(result["coefficient"]), "intercept": result["intercept"],
            "lambda": 1.0,
        }
        fit_hash = canonical_sha256(fit_preimage)
        fit_id = f"p11gfit_{fit_hash[:24]}"
        prediction = invert_target_transform(result["prediction"], transforms[target])
        observed = test.response.to_numpy(dtype=np.float64)
        residual = observed - prediction
        diagnostics.append({
            "fit_id": fit_id, "model": model, "target": target, "cv_regime": "random", "probe": "ridge",
            "fold_id": f"random_{fold}", "train_n": len(train), "test_n": len(test),
            "zero_variance_dimension_count": len(result["zero_variance_indices"]),
            "coefficient_norm": float(np.linalg.norm(result["coefficient"])),
            "intercept": result["intercept"], "residual_mean": float(residual.mean()),
            "residual_sd": float(residual.std(ddof=0)), "runtime_seconds": elapsed,
            "numerical_status": "PASS",
        })
        test_y_t = np.asarray([y_by_scene[scene] for scene in test.scene_id], dtype=np.float64)
        for row, observed_t, predicted_t, predicted in zip(
            test.itertuples(index=False), test_y_t, result["prediction"], prediction
        ):
            predictions.append({
                "scene_id": row.scene_id, "model": model, "target": target,
                "probe": "ridge", "cv_regime": "random", "fold_id": f"random_{fold}",
                "observed": float(row.response), "transformed_response": float(observed_t),
                "transformed_prediction": float(predicted_t), "prediction": float(predicted),
                "fit_id": fit_id,
            })
    return {"predictions": predictions, "diagnostics": diagnostics}


def _mlp_fold(
    model: str, target: str, regime: str, fold_id: str,
    train_x: np.ndarray, train_y: np.ndarray, train_scene_ids: list[str],
    test_x: np.ndarray, test_scene_ids: list[str],
    contract: Mapping[str, Any], device_name: str = "cpu",
) -> dict[str, Any]:
    import torch

    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    if device_name.startswith("cuda"):
        if not torch.cuda.is_available():
            raise P11DiagnosticError("P11_G_CUDA_UNAVAILABLE")
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False
    device = torch.device(device_name)
    seed = derive_fit_seed(model, target, fold_id, regime)
    split_seed = derive_fit_seed(model, target, fold_id, f"{regime}:inner_validation")
    generator = np.random.Generator(np.random.PCG64(split_seed))
    permutation = generator.permutation(len(train_x))
    validation_n = max(1, int(math.floor(len(train_x) * 0.10)))
    validation_index = permutation[:validation_n]
    inner_train_index = permutation[validation_n:]
    inner_x = np.asarray(train_x[inner_train_index], dtype=np.float64)
    validation_x = np.asarray(train_x[validation_index], dtype=np.float64)
    mean = inner_x.mean(axis=0)
    scale = inner_x.std(axis=0, ddof=0)
    zero = scale == 0
    scale[zero] = 1.0
    inner_x = ((inner_x - mean) / scale).astype(np.float32)
    validation_x = ((validation_x - mean) / scale).astype(np.float32)
    standardized_test = ((np.asarray(test_x, dtype=np.float64) - mean) / scale).astype(np.float32)
    inner_y = np.asarray(train_y[inner_train_index], dtype=np.float32)
    validation_y = np.asarray(train_y[validation_index], dtype=np.float32)
    torch.manual_seed(seed)
    if device.type == "cuda":
        torch.cuda.manual_seed_all(seed)
    network = torch.nn.Sequential(
        torch.nn.Linear(128, 64), torch.nn.GELU(approximate="none"),
        torch.nn.Dropout(0.1), torch.nn.Linear(64, 1),
    ).to(device)
    optimizer = torch.optim.AdamW(
        network.parameters(), lr=0.001, weight_decay=0.0001,
        betas=(0.9, 0.999), eps=1.0e-8,
    )
    x_tensor = torch.from_numpy(inner_x).to(device)
    y_tensor = torch.from_numpy(inner_y).to(device)
    validation_x_tensor = torch.from_numpy(validation_x).to(device)
    validation_y_tensor = torch.from_numpy(validation_y).to(device)
    batch_generator = torch.Generator(device="cpu")
    batch_generator.manual_seed(seed ^ 0x5DEECE66D)
    cuda_dropout_masks = None
    cuda_dropout_offset = 0
    if device.type == "cuda":
        # Freeze the CPU native-dropout realization once, then transfer it once.
        # This keeps the scientific seed trajectory backend-independent without
        # epoch-by-epoch host/device traffic.
        masks = []
        for _ in range(200):
            for offset in range(0, len(x_tensor), 64):
                count = min(64, len(x_tensor) - offset)
                masks.append(torch.ops.aten.native_dropout(
                    torch.ones((count, 64), dtype=torch.float32), 0.1, True
                )[1])
        cuda_dropout_masks = torch.cat(masks, dim=0).to(device)
    best_loss = math.inf
    best_epoch = 0
    best_state = None
    patience = 0
    final_training_loss = math.nan
    stopped_early = False
    started = time.perf_counter()
    for epoch in range(1, 201):
        network.train()
        order = torch.randperm(len(x_tensor), generator=batch_generator)
        total_loss = 0.0
        seen = 0
        for offset in range(0, len(order), 64):
            index = order[offset:offset + 64]
            if cuda_dropout_masks is None:
                prediction = network(x_tensor[index]).squeeze(1)
            else:
                hidden = network[1](network[0](x_tensor[index]))
                mask = cuda_dropout_masks[cuda_dropout_offset:cuda_dropout_offset + len(index)]
                cuda_dropout_offset += len(index)
                prediction = network[3](hidden * mask / 0.9).squeeze(1)
            loss = torch.nn.functional.mse_loss(prediction, y_tensor[index], reduction="mean")
            if not torch.isfinite(loss):
                raise P11DiagnosticError(f"P11_G_MLP_NONFINITE_LOSS:{model}:{target}:{regime}:{fold_id}")
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
            total_loss += float(loss.detach()) * len(index)
            seen += len(index)
        final_training_loss = total_loss / seen
        network.eval()
        with torch.no_grad():
            validation_prediction = network(validation_x_tensor).squeeze(1)
            validation_loss = float(torch.nn.functional.mse_loss(
                validation_prediction, validation_y_tensor, reduction="mean"
            ))
        if not math.isfinite(validation_loss):
            raise P11DiagnosticError(f"P11_G_MLP_NONFINITE_VALIDATION:{model}:{target}:{regime}:{fold_id}")
        if validation_loss < best_loss:
            best_loss = validation_loss
            best_epoch = epoch
            best_state = {name: value.detach().clone() for name, value in network.state_dict().items()}
            patience = 0
        else:
            patience += 1
        if patience >= 20:
            stopped_early = True
            break
    if best_state is None:
        raise P11DiagnosticError("P11_G_MLP_NO_BEST_STATE")
    network.load_state_dict(best_state)
    network.eval()
    with torch.no_grad():
        prediction = network(torch.from_numpy(standardized_test).to(device)).squeeze(1).cpu().numpy().astype(np.float64)
    if device.type == "cuda":
        torch.cuda.synchronize(device)
    runtime = time.perf_counter() - started
    if not np.isfinite(prediction).all():
        raise P11DiagnosticError(f"P11_G_MLP_NONFINITE_PREDICTION:{model}:{target}:{regime}:{fold_id}")
    parameter_hash = hashlib.sha256()
    for name, value in sorted(best_state.items()):
        parameter_hash.update(name.encode("utf-8")); parameter_hash.update(value.cpu().numpy().tobytes())
    fit_preimage = {
        "model": model, "target": target, "cv_regime": regime, "probe": "mlp", "fold_id": fold_id,
        "seed": str(seed),
        "outer_train_scene_ids_sha256": canonical_sha256(sorted(train_scene_ids)),
        "inner_train_scene_ids_sha256": canonical_sha256(sorted(train_scene_ids[index] for index in inner_train_index)),
        "inner_validation_scene_ids_sha256": canonical_sha256(sorted(train_scene_ids[index] for index in validation_index)),
        "outer_test_scene_ids_sha256": canonical_sha256(sorted(test_scene_ids)),
        "mean_sha256": _array_sha256(mean), "scale_sha256": _array_sha256(scale),
        "mlp_contract_sha256": canonical_sha256(dict(contract)),
    }
    fit_hash = canonical_sha256(fit_preimage)
    return {
        "fit_id": f"p11gfit_{fit_hash[:24]}", "prediction": prediction,
        "diagnostic": {
            "fit_id": f"p11gfit_{fit_hash[:24]}", "model": model, "target": target,
            "cv_regime": regime, "probe": "mlp", "fold_id": fold_id,
            "outer_train_n": len(train_x), "inner_train_n": len(inner_train_index),
            "inner_validation_n": validation_n, "test_n": len(test_x), "seed": str(seed),
            "best_epoch": best_epoch, "epochs_executed": epoch,
            "best_inner_validation_loss": best_loss, "final_training_loss": final_training_loss,
            "best_parameter_sha256": parameter_hash.hexdigest(),
            "parameter_count": sum(value.numel() for value in network.parameters()),
            "stopped_early": stopped_early, "reached_maximum_epoch": epoch == 200,
            "zero_variance_dimension_count": int(zero.sum()), "runtime_seconds": runtime,
            "numerical_status": "PASS", "execution_device": device_name,
        },
    }


def _mlp_model_target_task(task: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    model = task["model"]; target = task["target"]; regime = task["regime"]
    embeddings = task["embeddings"]; rows = task["rows"]; transform = task["transform"]
    fold_column = "district_id" if regime == "spatial" else "random_fold"
    folds = sorted(rows[fold_column].unique())
    transformed = apply_target_transform(rows.response.to_numpy(dtype=np.float64), transform)
    y_by_scene = dict(zip(rows.scene_id, transformed))
    predictions = []
    diagnostics = []
    for fold in folds:
        train = rows[rows[fold_column] != fold]
        test = rows[rows[fold_column] == fold]
        fold_id = f"district_{fold}" if regime == "spatial" else f"random_{fold}"
        result = _mlp_fold(
            model, target, regime, fold_id,
            embeddings[train.embedding_row.to_numpy(dtype=np.int64)],
            np.asarray([y_by_scene[scene] for scene in train.scene_id], dtype=np.float64),
            train.scene_id.tolist(),
            embeddings[test.embedding_row.to_numpy(dtype=np.int64)], test.scene_id.tolist(),
            task["mlp_contract"], task.get("device_name", "cpu"),
        )
        predicted = invert_target_transform(result["prediction"], transform)
        if not np.isfinite(predicted).all():
            raise P11DiagnosticError(f"P11_G_MLP_INVERSE_NONFINITE:{model}:{target}:{regime}:{fold_id}")
        test_y_t = np.asarray([y_by_scene[scene] for scene in test.scene_id], dtype=np.float64)
        for row, observed_t, predicted_t, original_prediction in zip(
            test.itertuples(index=False), test_y_t, result["prediction"], predicted
        ):
            predictions.append({
                "scene_id": row.scene_id, "model": model, "target": target,
                "probe": "mlp", "cv_regime": regime, "fold_id": fold_id,
                "observed": float(row.response), "transformed_response": float(observed_t),
                "transformed_prediction": float(predicted_t), "prediction": float(original_prediction),
                "fit_id": result["fit_id"],
            })
        diagnostics.append(result["diagnostic"])
    return {"predictions": predictions, "diagnostics": diagnostics}


def _metric_table(predictions: pd.DataFrame) -> pd.DataFrame:
    renamed = predictions.copy()
    renamed["model_probe"] = (
        renamed.model + "|" + renamed.cv_regime + "|" + renamed.probe
    )
    raw = pooled_metrics(renamed.rename(columns={"model": "source_model"}).rename(columns={"model_probe": "model"}))
    split = raw.model.str.split("|", expand=True)
    raw["model"] = split[0]; raw["cv_regime"] = split[1]; raw["probe"] = split[2]
    return raw[["model", "target", "cv_regime", "probe", "eligible_n", "r2", "rmse", "mae", "sse", "sst"]].sort_values(
        ["model", "target", "cv_regime", "probe"], kind="mergesort"
    ).reset_index(drop=True)


def _diagnostic_deltas(metrics: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    indexed = metrics.set_index(["model", "target", "cv_regime", "probe"])
    spatial = []
    nonlinear = []
    for model in EXPECTED_MODELS:
        for target in EXPECTED_TARGETS:
            for probe in ("ridge", "mlp"):
                s = indexed.loc[(model, target, "spatial", probe)]
                r = indexed.loc[(model, target, "random", probe)]
                spatial.append({
                    "model": model, "target": target, "probe": probe,
                    "delta_spatial_r2": s.r2 - r.r2,
                    "delta_spatial_rmse": s.rmse - r.rmse,
                    "delta_spatial_mae": s.mae - r.mae,
                })
            for regime in ("spatial", "random"):
                mlp = indexed.loc[(model, target, regime, "mlp")]
                ridge = indexed.loc[(model, target, regime, "ridge")]
                nonlinear.append({
                    "model": model, "target": target, "cv_regime": regime,
                    "delta_mlp_r2": mlp.r2 - ridge.r2,
                    "delta_mlp_rmse": mlp.rmse - ridge.rmse,
                    "delta_mlp_mae": mlp.mae - ridge.mae,
                })
    fm = metrics[metrics.model == "cfg_d128"].pivot(index="target", columns=["cv_regime", "probe"], values="r2")
    fm_rows = []
    for target, row in fm.iterrows():
        fm_rows.append({
            "target": target,
            "spatial_ridge_r2": row[("spatial", "ridge")],
            "random_ridge_r2": row[("random", "ridge")],
            "spatial_mlp_r2": row[("spatial", "mlp")],
            "random_mlp_r2": row[("random", "mlp")],
            "ridge_spatial_penalty": row[("spatial", "ridge")] - row[("random", "ridge")],
            "mlp_spatial_penalty": row[("spatial", "mlp")] - row[("random", "mlp")],
            "spatial_nonlinear_gain": row[("spatial", "mlp")] - row[("spatial", "ridge")],
            "random_nonlinear_gain": row[("random", "mlp")] - row[("random", "ridge")],
        })
    summary = metrics.pivot_table(index="model", columns=["cv_regime", "probe"], values="r2", aggfunc="median")
    spatial_frame = pd.DataFrame(spatial)
    nonlinear_frame = pd.DataFrame(nonlinear)
    summary_rows = []
    for model, row in summary.iterrows():
        model_spatial = spatial_frame[spatial_frame.model == model]
        model_nonlinear = nonlinear_frame[nonlinear_frame.model == model]
        summary_rows.append({
            "model": model,
            "median_spatial_ridge_r2": row[("spatial", "ridge")],
            "median_random_ridge_r2": row[("random", "ridge")],
            "median_spatial_mlp_r2": row[("spatial", "mlp")],
            "median_random_mlp_r2": row[("random", "mlp")],
            "median_ridge_spatial_penalty": float(model_spatial[model_spatial.probe == "ridge"].delta_spatial_r2.median()),
            "median_mlp_spatial_penalty": float(model_spatial[model_spatial.probe == "mlp"].delta_spatial_r2.median()),
            "median_spatial_nonlinear_gain": float(model_nonlinear[model_nonlinear.cv_regime == "spatial"].delta_mlp_r2.median()),
            "median_random_nonlinear_gain": float(model_nonlinear[model_nonlinear.cv_regime == "random"].delta_mlp_r2.median()),
        })
    return spatial_frame, nonlinear_frame, pd.DataFrame(fm_rows), pd.DataFrame(summary_rows)


def _write_parquet(frame: pd.DataFrame, path: Path) -> None:
    pq.write_table(pa.Table.from_pandas(frame, preserve_index=False), path, compression="zstd", version="2.6", write_statistics=True)


def run_mlp_determinism_pilot(path: str | Path = "config/p11_diagnostic_probe_matrix.yml") -> dict[str, Any]:
    contract = load_diagnostic_contract(path)
    inputs = _validate_inputs(contract)
    model = "cfg_d128"; target = "ecostress_lst"
    rows = inputs["targets"][target]
    fold = sorted(rows.district_id.unique())[0]
    train = rows[rows.district_id != fold]; test = rows[rows.district_id == fold]
    train_y = apply_target_transform(train.response.to_numpy(dtype=np.float64), inputs["transforms"][target])
    outputs = []
    for _ in range(2):
        result = _mlp_fold(
            model, target, "spatial", f"district_{fold}",
            inputs["embeddings"][model][train.embedding_row.to_numpy(dtype=np.int64)],
            train_y, train.scene_id.tolist(),
            inputs["embeddings"][model][test.embedding_row.to_numpy(dtype=np.int64)],
            test.scene_id.tolist(), contract["mlp"],
        )
        diagnostic = {key: value for key, value in result["diagnostic"].items() if key != "runtime_seconds"}
        outputs.append(canonical_sha256({"prediction_sha256": _array_sha256(result["prediction"]), "diagnostic": diagnostic}))
    if outputs[0] != outputs[1]:
        raise P11DiagnosticError("P11_G_MLP_DETERMINISM_PILOT_FAILED")
    return {"status": "PASS", "fit_count": 2, "digest": outputs[0]}


def run_cpu_gpu_equivalence_pilot(path: str | Path = "config/p11_diagnostic_probe_matrix.yml") -> dict[str, Any]:
    contract = load_diagnostic_contract(path)
    inputs = _validate_inputs(contract)
    model = "cfg_d128"; target = "ecostress_lst"
    rows = inputs["targets"][target]
    fold = sorted(rows.district_id.unique())[0]
    train = rows[rows.district_id != fold]; test = rows[rows.district_id == fold]
    train_y = apply_target_transform(train.response.to_numpy(dtype=np.float64), inputs["transforms"][target])
    arguments = (
        model, target, "spatial", f"district_{fold}",
        inputs["embeddings"][model][train.embedding_row.to_numpy(dtype=np.int64)],
        train_y, train.scene_id.tolist(),
        inputs["embeddings"][model][test.embedding_row.to_numpy(dtype=np.int64)],
        test.scene_id.tolist(), contract["mlp"],
    )
    cpu = _mlp_fold(*arguments, "cpu")
    gpu_results = []
    for gpu in contract["execution"]["gpu_indices"]:
        with ProcessPoolExecutor(max_workers=1, initializer=_gpu_worker_init, initargs=(gpu,)) as executor:
            gpu_results.append(executor.submit(_mlp_fold, *arguments, f"cuda:{gpu}").result())
    tolerance = contract["execution"]["cpu_gpu_equivalence"]
    comparisons = []
    for gpu, result in zip(contract["execution"]["gpu_indices"], gpu_results):
        maximum = float(np.max(np.abs(cpu["prediction"] - result["prediction"])))
        relative = float(np.max(np.abs(cpu["prediction"] - result["prediction"]) / np.maximum(np.abs(cpu["prediction"]), 1.0)))
        loss_difference = abs(cpu["diagnostic"]["best_inner_validation_loss"] - result["diagnostic"]["best_inner_validation_loss"])
        epoch_difference = abs(cpu["diagnostic"]["best_epoch"] - result["diagnostic"]["best_epoch"])
        if (maximum > tolerance["prediction_atol"] + tolerance["prediction_rtol"] * float(np.max(np.abs(cpu["prediction"])))
                or loss_difference > tolerance["validation_loss_atol"]
                or epoch_difference > tolerance["best_epoch_tolerance"]):
            raise P11DiagnosticError(
                f"P11_G_CPU_GPU_EQUIVALENCE_FAILED:cuda:{gpu}:max={maximum}:relative={relative}:"
                f"loss={loss_difference}:epoch={epoch_difference}:cpu_epoch={cpu['diagnostic']['best_epoch']}:"
                f"gpu_epoch={result['diagnostic']['best_epoch']}"
            )
        comparisons.append({
            "gpu": gpu, "maximum_prediction_absolute_difference": maximum,
            "maximum_prediction_relative_difference": relative,
            "validation_loss_absolute_difference": loss_difference,
            "best_epoch_difference": epoch_difference,
            "cpu_runtime_seconds": cpu["diagnostic"]["runtime_seconds"],
            "gpu_runtime_seconds": result["diagnostic"]["runtime_seconds"],
        })
    if not np.array_equal(gpu_results[0]["prediction"], gpu_results[1]["prediction"]):
        raise P11DiagnosticError("P11_G_CROSS_GPU_DETERMINISM_FAILED")
    return {"status": "PASS", "fit_identity": cpu["fit_id"], "comparisons": comparisons}


def run_gpu_throughput_pilot(
    path: str | Path = "config/p11_diagnostic_probe_matrix.yml", workers_per_gpu: int = 1,
) -> dict[str, Any]:
    contract = load_diagnostic_contract(path)
    inputs = _validate_inputs(contract)
    model = "cfg_d128"; target = "ecostress_lst"
    rows = inputs["targets"][target]
    fold = sorted(rows.district_id.unique())[0]
    train = rows[rows.district_id != fold]; test = rows[rows.district_id == fold]
    train_y = apply_target_transform(train.response.to_numpy(dtype=np.float64), inputs["transforms"][target])
    arguments = (
        model, target, "spatial", f"district_{fold}",
        inputs["embeddings"][model][train.embedding_row.to_numpy(dtype=np.int64)], train_y,
        train.scene_id.tolist(), inputs["embeddings"][model][test.embedding_row.to_numpy(dtype=np.int64)],
        test.scene_id.tolist(), contract["mlp"],
    )
    samples: list[dict[str, Any]] = []
    stop = threading.Event(); monitor = threading.Thread(target=_monitor_gpus, args=(stop, samples), daemon=True); monitor.start()
    started = time.perf_counter()
    executors = [ProcessPoolExecutor(max_workers=workers_per_gpu, initializer=_gpu_worker_init, initargs=(gpu,)) for gpu in (0, 1)]
    try:
        futures = []
        for gpu, executor in enumerate(executors):
            for _ in range(8):
                futures.append((gpu, executor.submit(_mlp_fold, *arguments, f"cuda:{gpu}")))
        results = [(gpu, future.result()) for gpu, future in futures]
    finally:
        for executor in executors:
            executor.shutdown(wait=True, cancel_futures=True)
        stop.set(); monitor.join(timeout=5)
    wall = time.perf_counter() - started
    digests = {_array_sha256(result["prediction"]) for _, result in results}
    if len(digests) != 1:
        raise P11DiagnosticError("P11_G_GPU_THROUGHPUT_PILOT_NONDETERMINISTIC")
    return {
        "status": "PASS", "workers_per_gpu": workers_per_gpu, "fit_count": len(results),
        "wall_seconds": wall, "aggregate_fits_per_second": len(results) / wall,
        "per_gpu_fits_per_second": {
            str(gpu): sum(device == gpu for device, _ in results) / wall for gpu in (0, 1)
        },
        "utilization_percent_mean": {
            str(gpu): float(np.mean([row["utilization_percent"] for row in samples if row["gpu"] == gpu])) for gpu in (0, 1)
        },
        "peak_memory_mib": {
            str(gpu): float(np.max([row["memory_used_mib"] for row in samples if row["gpu"] == gpu])) for gpu in (0, 1)
        },
        "prediction_sha256": next(iter(digests)),
    }


def _baseline_predictions(inputs: Mapping[str, Any]) -> pd.DataFrame:
    frame = pq.read_table(inputs["p11e_root"] / "oof_predictions.parquet").to_pandas()
    frame = frame[["scene_id", "model", "target", "observed", "transformed_response",
                   "transformed_prediction", "prediction", "fit_id"]].copy()
    frame["probe"] = "ridge"
    frame["cv_regime"] = "spatial"
    frame["fold_id"] = pq.read_table(
        inputs["p11e_root"] / "oof_predictions.parquet", columns=["fold_id"]
    ).to_pandas().fold_id
    return frame


def _all_predictions(root: Path, inputs: Mapping[str, Any]) -> pd.DataFrame:
    frames = [_baseline_predictions(inputs)]
    for name in ("random_ridge_oof.parquet", "spatial_mlp_oof.parquet", "random_mlp_oof.parquet"):
        frames.append(pq.read_table(root / name).to_pandas())
    return pd.concat(frames, ignore_index=True).sort_values(
        ["model", "target", "cv_regime", "probe", "scene_id"], kind="mergesort"
    ).reset_index(drop=True)


def _validate_matrix_predictions(predictions: pd.DataFrame, inputs: Mapping[str, Any]) -> int:
    expected_one_cell = sum(len(inputs["targets"][target]) for target in EXPECTED_TARGETS) * 8
    expected = expected_one_cell * 4
    if len(predictions) != expected:
        raise P11DiagnosticError(f"P11_G_OOF_CARDINALITY_INVALID:{len(predictions)}:{expected}")
    keys = ["scene_id", "model", "target", "cv_regime", "probe"]
    if predictions.duplicated(keys).any():
        raise P11DiagnosticError("P11_G_OOF_DUPLICATE")
    if not np.isfinite(predictions[["observed", "transformed_response", "transformed_prediction", "prediction"]]).all().all():
        raise P11DiagnosticError("P11_G_OOF_NONFINITE")
    for model in EXPECTED_MODELS:
        for target in EXPECTED_TARGETS:
            required = set(inputs["targets"][target].scene_id)
            for regime, probe in PROBE_CELLS:
                actual = set(predictions[
                    (predictions.model == model) & (predictions.target == target)
                    & (predictions.cv_regime == regime) & (predictions.probe == probe)
                ].scene_id)
                if actual != required:
                    raise P11DiagnosticError(f"P11_G_OOF_COVERAGE_MISMATCH:{model}:{target}:{regime}:{probe}")
    return expected


def _assert_spatial_ridge_equivalence(metrics: pd.DataFrame, inputs: Mapping[str, Any]) -> None:
    expected = pq.read_table(inputs["p11e_root"] / "pooled_metrics.parquet").to_pandas().sort_values(
        ["model", "target"], kind="mergesort"
    ).reset_index(drop=True)
    actual = metrics[(metrics.cv_regime == "spatial") & (metrics.probe == "ridge")].sort_values(
        ["model", "target"], kind="mergesort"
    ).reset_index(drop=True)
    keys = ["model", "target", "eligible_n"]
    numeric = ["r2", "rmse", "mae", "sse", "sst"]
    if not np.array_equal(actual[keys].to_numpy(), expected[keys].to_numpy()):
        raise P11DiagnosticError("P11_G_SPATIAL_RIDGE_KEYS_MISMATCH")
    if not np.array_equal(actual[numeric].to_numpy(dtype=np.float64), expected[numeric].to_numpy(dtype=np.float64)):
        raise P11DiagnosticError("P11_G_SPATIAL_RIDGE_BASELINE_MISMATCH")


def validate_p11_diagnostic_acceptance(
    root: str | Path, config_path: str | Path = "config/p11_diagnostic_probe_matrix.yml",
    recompute_metrics: bool = True,
) -> dict[str, Any]:
    root = Path(root)
    acceptance = _json(root / "p11_g_acceptance.json")
    preimage = {key: value for key, value in acceptance.items() if key not in {"acceptance_id", "content_sha256", "status", "artifacts"}}
    digest = canonical_sha256(preimage)
    if acceptance.get("acceptance_id") != f"p11g_{digest[:24]}" or acceptance.get("content_sha256") != digest or acceptance.get("status") != "PASS":
        raise P11DiagnosticError("P11_G_ACCEPTANCE_IDENTITY_INVALID")
    for artifact in acceptance.get("artifacts", []):
        artifact_path = root / artifact["basename"]
        if not artifact_path.is_file() or artifact_path.stat().st_size != artifact["byte_size"] or sha256_file(artifact_path) != artifact["sha256"]:
            raise P11DiagnosticError(f"P11_G_ARTIFACT_CORRUPTION:{artifact['basename']}")
    if recompute_metrics:
        contract = load_diagnostic_contract(config_path)
        inputs = _validate_inputs(contract)
        predictions = _all_predictions(root, inputs)
        _validate_matrix_predictions(predictions, inputs)
        reproduced = _metric_table(predictions)
        stored = pq.read_table(root / "diagnostic_metrics.parquet").to_pandas()
        if _frame_hash(reproduced) != _frame_hash(stored):
            raise P11DiagnosticError("P11_G_METRIC_RECOMPUTATION_MISMATCH")
        _assert_spatial_ridge_equivalence(stored, inputs)
    return acceptance


def materialize_p11_diagnostic_matrix(
    path: str | Path = "config/p11_diagnostic_probe_matrix.yml",
) -> dict[str, Any]:
    pointer_path = Path("config/p11_diagnostic_probe_acceptance.yml")
    if Path(path).resolve() == Path("config/p11_diagnostic_probe_matrix.yml").resolve() and pointer_path.is_file():
        pointer = yaml.safe_load(pointer_path.read_text(encoding="utf-8"))
        accepted_path = Path(pointer["acceptance_path"])
        if not accepted_path.is_file() or sha256_file(accepted_path) != pointer["acceptance_sha256"]:
            raise P11DiagnosticError("P11_G_ACCEPTANCE_POINTER_INVALID")
        return validate_p11_diagnostic_acceptance(accepted_path.parent, path)
    contract = load_diagnostic_contract(path)
    inputs = _validate_inputs(contract)
    equivalence = run_cpu_gpu_equivalence_pilot(path)
    started = time.perf_counter()
    random_folds = inputs["random_folds"].sort_values("scene_id", kind="mergesort").reset_index(drop=True)

    ridge_tasks = [(model, target) for model in EXPECTED_MODELS for target in EXPECTED_TARGETS]
    def run_ridge(task: tuple[str, str]) -> dict[str, list[dict[str, Any]]]:
        model, target = task
        return _ridge_random_model_target(
            model, target, inputs["embeddings"][model], inputs["targets"][target],
            inputs["transforms"], random_folds[["scene_id", "random_fold"]],
        )
    ridge_started = time.perf_counter()
    with threadpool_limits(limits=1), ThreadPoolExecutor(max_workers=8) as executor:
        ridge_results = list(executor.map(run_ridge, ridge_tasks))
    ridge_wall = time.perf_counter() - ridge_started
    ridge_predictions = pd.DataFrame([
        row for result in ridge_results for row in result["predictions"]
    ]).sort_values(["model", "target", "scene_id"], kind="mergesort").reset_index(drop=True)
    ridge_diagnostics = pd.DataFrame([
        row for result in ridge_results for row in result["diagnostics"]
    ]).sort_values(["model", "target", "fold_id"], kind="mergesort").reset_index(drop=True)

    mlp_tasks = []
    for regime in ("spatial", "random"):
        for model in EXPECTED_MODELS:
            for target in EXPECTED_TARGETS:
                rows = inputs["targets"][target]
                if regime == "random":
                    rows = rows.merge(random_folds[["scene_id", "random_fold"]], on="scene_id", validate="one_to_one")
                mlp_tasks.append({
                    "model": model, "target": target, "regime": regime,
                    "embeddings": np.asarray(inputs["embeddings"][model], dtype=np.float32),
                    "rows": rows, "transform": inputs["transforms"][target],
                    "mlp_contract": contract["mlp"],
                })
    gpu_indices = contract["execution"]["gpu_indices"]
    gpu_samples: list[dict[str, Any]] = []
    monitor_stop = threading.Event()
    monitor = threading.Thread(target=_monitor_gpus, args=(monitor_stop, gpu_samples), daemon=True)
    monitor.start()
    mlp_started = time.perf_counter()
    workers_per_gpu = int(contract["execution"]["persistent_workers_per_gpu"])
    executors = [ProcessPoolExecutor(max_workers=workers_per_gpu, initializer=_gpu_worker_init, initargs=(gpu,)) for gpu in gpu_indices]
    try:
        futures = []
        for index, task in enumerate(mlp_tasks):
            gpu = gpu_indices[index % len(gpu_indices)]
            task["device_name"] = f"cuda:{gpu}"
            futures.append(executors[index % len(executors)].submit(_mlp_model_target_task, task))
        mlp_results = [future.result() for future in futures]
    finally:
        for executor in executors:
            executor.shutdown(wait=True, cancel_futures=True)
        monitor_stop.set()
        monitor.join(timeout=5)
    mlp_wall = time.perf_counter() - mlp_started
    mlp_predictions = pd.DataFrame([
        row for result in mlp_results for row in result["predictions"]
    ]).sort_values(["cv_regime", "model", "target", "scene_id"], kind="mergesort").reset_index(drop=True)
    mlp_diagnostics = pd.DataFrame([
        row for result in mlp_results for row in result["diagnostics"]
    ]).sort_values(["cv_regime", "model", "target", "fold_id"], kind="mergesort").reset_index(drop=True)
    spatial_mlp = mlp_predictions[mlp_predictions.cv_regime == "spatial"].reset_index(drop=True)
    random_mlp = mlp_predictions[mlp_predictions.cv_regime == "random"].reset_index(drop=True)
    if len(ridge_diagnostics) != 440 or len(mlp_diagnostics) != 2640:
        raise P11DiagnosticError("P11_G_FIT_CARDINALITY_INVALID")
    if not (ridge_diagnostics.numerical_status.eq("PASS").all() and mlp_diagnostics.numerical_status.eq("PASS").all()):
        raise P11DiagnosticError("P11_G_FIT_FAILURE")

    predictions = pd.concat([_baseline_predictions(inputs), ridge_predictions, spatial_mlp, random_mlp], ignore_index=True)
    expected_oof = _validate_matrix_predictions(predictions, inputs)
    metrics = _metric_table(predictions)
    if len(metrics) != 352:
        raise P11DiagnosticError("P11_G_METRIC_CARDINALITY_INVALID")
    _assert_spatial_ridge_equivalence(metrics, inputs)
    spatial_delta, nonlinear_delta, fm_summary, model_summary = _diagnostic_deltas(metrics)
    mlp_contract_artifact = {
        "schema_version": "1.0.0", "artifact_type": "p11_g_mlp_training_contract",
        "global_seed": str(GLOBAL_SEED), "fit_seed_derivation": "sha256(global_seed|model|target|fold_id|cv_regime)_first_8_bytes_big_endian_mask63",
        **contract["mlp"],
    }
    runtime = {
        "execution_strategy": "one persistent task worker per RTX A6000 GPU; deterministic alternating model-target tasks; 8 thread random-ridge tasks",
        "backend": contract["execution"]["backend"], "gpu_indices": gpu_indices,
        "persistent_workers_per_gpu": workers_per_gpu,
        "wall_seconds": time.perf_counter() - started,
        "random_ridge_wall_seconds": ridge_wall, "total_mlp_wall_seconds": mlp_wall,
        "spatial_mlp_sum_fit_seconds": float(mlp_diagnostics[mlp_diagnostics.cv_regime == "spatial"].runtime_seconds.sum()),
        "random_mlp_sum_fit_seconds": float(mlp_diagnostics[mlp_diagnostics.cv_regime == "random"].runtime_seconds.sum()),
        "cpu_gpu_equivalence": equivalence,
        "random_ridge_fit_seconds": {"median": float(ridge_diagnostics.runtime_seconds.median()), "p95": float(ridge_diagnostics.runtime_seconds.quantile(.95))},
        "mlp_fit_seconds": {"median": float(mlp_diagnostics.runtime_seconds.median()), "p95": float(mlp_diagnostics.runtime_seconds.quantile(.95))},
        "mlp_convergence": {
            "fit_count": len(mlp_diagnostics), "early_stopped": int(mlp_diagnostics.stopped_early.sum()),
            "maximum_epoch": int(mlp_diagnostics.reached_maximum_epoch.sum()),
            "nonfinite": int((mlp_diagnostics.numerical_status != "PASS").sum()),
            "best_epoch_min": int(mlp_diagnostics.best_epoch.min()),
            "best_epoch_median": float(mlp_diagnostics.best_epoch.median()),
            "best_epoch_max": int(mlp_diagnostics.best_epoch.max()),
        },
        "per_gpu": {
            str(gpu): {
                "fit_count": int((mlp_diagnostics.execution_device == f"cuda:{gpu}").sum()),
                "fits_per_fit_runtime_second": float(
                    (mlp_diagnostics.execution_device == f"cuda:{gpu}").sum()
                    / mlp_diagnostics[mlp_diagnostics.execution_device == f"cuda:{gpu}"].runtime_seconds.sum()
                ),
                "utilization_percent_mean": float(np.mean([row["utilization_percent"] for row in gpu_samples if row["gpu"] == gpu])),
                "utilization_percent_max": float(np.max([row["utilization_percent"] for row in gpu_samples if row["gpu"] == gpu])),
                "peak_memory_mib": float(np.max([row["memory_used_mib"] for row in gpu_samples if row["gpu"] == gpu])),
                "power_watts_mean": float(np.mean([row["power_watts"] for row in gpu_samples if row["gpu"] == gpu])),
            } for gpu in gpu_indices
        },
        "gpu_sample_count": len(gpu_samples), "failures": 0, "retries": 0,
    }
    frames = {
        "random_fold_assignments.parquet": random_folds,
        "random_ridge_oof.parquet": ridge_predictions,
        "spatial_mlp_oof.parquet": spatial_mlp,
        "random_mlp_oof.parquet": random_mlp,
        "random_ridge_diagnostics.parquet": ridge_diagnostics,
        "mlp_fit_diagnostics.parquet": mlp_diagnostics,
        "diagnostic_metrics.parquet": metrics,
        "spatial_generalization_deltas.parquet": spatial_delta,
        "nonlinear_accessibility_deltas.parquet": nonlinear_delta,
        "fm_diagnostic_summary.parquet": fm_summary,
        "cross_model_summary.parquet": model_summary,
    }
    scientific_hashes = {
        name: _frame_hash(frame, ("runtime_seconds",)) for name, frame in frames.items()
    }
    preimage = {
        "schema_version": "1.0.0", "artifact_type": "p11_g_diagnostic_probe_matrix_acceptance",
        "implementation_version": "p11-g-diagnostic-probe-matrix-v1",
        "implementation_sha256": sha256_file(Path(__file__)),
        "contract_sha256": sha256_file(path),
        "dissertation_authority_id": contract["dissertation_authority_id"],
        "transformation_methodology_id": contract["transformation_methodology_id"],
        "p11_c_acceptance_id": contract["p11_c_acceptance_id"],
        "p11_e_acceptance_id": inputs["p11e"]["acceptance_id"],
        "downstream_dataset_id": contract["downstream_dataset_id"],
        "embedding_binding_id": contract["embedding_binding_id"],
        "global_seed": str(GLOBAL_SEED), "random_fold_count": 5,
        "model_count": 8, "target_count": 11, "probe_cell_count": 4,
        "reused_spatial_ridge_fit_count": 2200, "new_fit_count": 3080,
        "random_ridge_fit_count": 440, "spatial_mlp_fit_count": 2200, "random_mlp_fit_count": 440,
        "oof_row_count": expected_oof, "metric_row_count": 352,
        "scientific_output_sha256": scientific_hashes,
        "p11_e_mutated": False, "model_selection_reopened": False,
        "next_work_unit": contract["next_work_unit"],
    }
    digest = canonical_sha256(preimage)
    acceptance_id = f"p11g_{digest[:24]}"
    final = Path(contract["publication_root"]) / acceptance_id
    if final.exists():
        return validate_p11_diagnostic_acceptance(final, path)
    final.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{acceptance_id}.", dir=final.parent))
    for name, frame in frames.items():
        _write_parquet(frame, stage / name)
    (stage / "mlp_training_contract.json").write_bytes(canonical_json_bytes(mlp_contract_artifact))
    (stage / "runtime_summary.json").write_bytes(canonical_json_bytes(runtime))
    artifacts = [{"basename": item.name, "byte_size": item.stat().st_size, "sha256": sha256_file(item)} for item in sorted(stage.iterdir(), key=lambda item: item.name)]
    acceptance = {**preimage, "acceptance_id": acceptance_id, "content_sha256": digest, "status": "PASS", "artifacts": artifacts}
    (stage / "p11_g_acceptance.json").write_bytes(canonical_json_bytes(acceptance))
    os.rename(stage, final)
    return validate_p11_diagnostic_acceptance(final, path)
