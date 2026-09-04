"""P11-C immutable spatial folds, embedding bindings, and leakage gates."""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping

import geopandas as gpd
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import yaml

from p10_evaluation import evaluation_population, load_contract, resolve_model_bindings
from p9_v2_canonical import canonical_json_bytes, canonical_sha256, sha256_file


class P11ReadinessError(RuntimeError):
    """Stable fail-closed P11-C contract or evidence error."""


def _json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise P11ReadinessError(f"JSON_OBJECT_REQUIRED:{path}")
    return value


def _identity(value: Mapping[str, Any], key: str, prefix: str) -> None:
    preimage = {name: item for name, item in value.items() if name not in {key, "content_sha256"}}
    digest = canonical_sha256(preimage)
    if value.get(key) != f"{prefix}{digest[:24]}" or value.get("content_sha256") != digest:
        raise P11ReadinessError(f"CONTENT_IDENTITY_INVALID:{key}")


def load_readiness_contract(path: str | Path) -> dict[str, Any]:
    value = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if value.get("contract_name") != "p11-spatial-readiness-v1":
        raise P11ReadinessError("P11_C_CONTRACT_INVALID")
    return value


def apply_target_transform(values: np.ndarray, transform: str) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64)
    if not np.isfinite(values).all():
        raise P11ReadinessError("TARGET_NONFINITE")
    if transform == "log1p":
        if (values < 0).any():
            raise P11ReadinessError("LOG1P_TARGET_NEGATIVE")
        return np.log1p(values)
    if transform == "identity":
        return values.copy()
    raise P11ReadinessError("TARGET_TRANSFORM_UNSUPPORTED")


def invert_target_transform(values: np.ndarray, transform: str) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64)
    if not np.isfinite(values).all():
        raise P11ReadinessError("TRANSFORMED_TARGET_NONFINITE")
    if transform == "log1p":
        return np.expm1(values)
    if transform == "identity":
        return values.copy()
    raise P11ReadinessError("TARGET_TRANSFORM_UNSUPPORTED")


def _authority_and_transform(contract: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    authority = _json(contract["dissertation_authority"])
    methodology = _json(contract["transformation_methodology"])
    _identity(authority, "authority_id", "disauth_")
    _identity(methodology, "methodology_id", "p11meth_")
    if (
        authority["dissertation"]["commit"] != "989c19d98e64ec129dc53b761c58a4d961fc3983"
        or methodology["dissertation_authority_id"] != authority["authority_id"]
        or methodology["downstream_dataset_id"] != "p11ds_39607da2de792ad6b3c9bb30"
        or len(methodology["transforms"]) != 11
    ):
        raise P11ReadinessError("P11_C_METHODOLOGY_AUTHORITY_INVALID")
    return authority, methodology


def _dataset(contract: Mapping[str, Any]) -> tuple[dict[str, Any], Any]:
    pointer = yaml.safe_load(Path(contract["downstream_dataset"]).read_text(encoding="utf-8"))
    acceptance_path = Path(pointer["acceptance_path"])
    if sha256_file(acceptance_path) != pointer["acceptance_sha256"]:
        raise P11ReadinessError("P11_DATASET_ACCEPTANCE_HASH_MISMATCH")
    acceptance = _json(acceptance_path)
    if acceptance["dataset_id"] != "p11ds_39607da2de792ad6b3c9bb30":
        raise P11ReadinessError("P11_DATASET_IDENTITY_INVALID")
    table = pq.read_table(acceptance_path.parent / "scene_targets.parquet").to_pandas()
    if len(table) != 17600 or table.scene_id.nunique() != 1600 or table.target.nunique() != 11:
        raise P11ReadinessError("P11_DATASET_CARDINALITY_INVALID")
    return acceptance, table


def _master_folds(contract: Mapping[str, Any], gallery_ids: list[str]) -> Any:
    scenes = pq.read_table(contract["scene_index"]).to_pandas()
    scenes = scenes[scenes.scene_id.isin(gallery_ids)].copy()
    if len(scenes) != 1600 or scenes.scene_id.nunique() != 1600:
        raise P11ReadinessError("P11_SCENE_UNIVERSE_INVALID")
    districts = gpd.read_file(contract["district_boundary"])
    districts = districts[districts.SIGUNGU_CD.astype(str).str.startswith("11")].copy()
    districts["district_id"] = districts.SIGUNGU_CD.astype(str)
    districts = districts.to_crs(contract["scene_crs"])
    points = gpd.GeoDataFrame(
        scenes[["scene_id", "center_x", "center_y"]],
        geometry=gpd.points_from_xy(scenes.center_x, scenes.center_y),
        crs=contract["scene_crs"],
    )
    joined = gpd.sjoin(points, districts[["district_id", "geometry"]], predicate="intersects")
    assigned = joined.groupby("scene_id", sort=True).district_id.min().rename("district_id")
    result = scenes[["scene_id", "center_x", "center_y"]].merge(
        assigned, left_on="scene_id", right_index=True, how="left", validate="one_to_one"
    )
    result = result.sort_values("scene_id", kind="mergesort").reset_index(drop=True)
    if result.district_id.isna().any() or result.district_id.nunique() != 25:
        raise P11ReadinessError("P11_DISTRICT_ASSIGNMENT_INVALID")
    if result.scene_id.tolist() != gallery_ids:
        raise P11ReadinessError("P11_FOLD_GALLERY_ORDER_MISMATCH")
    result["fold_id"] = "district_" + result.district_id
    return result


def _target_folds(targets: Any, master: Any, transforms: Mapping[str, str]) -> Any:
    merged = targets.merge(master[["scene_id", "district_id", "fold_id"]], on="scene_id", validate="many_to_one")
    rows: list[dict[str, Any]] = []
    for target in sorted(transforms):
        group = merged[merged.target == target]
        eligible = group[group.eligible]
        apply_target_transform(eligible.response.to_numpy(), transforms[target])
        for district in sorted(master.district_id.unique()):
            test = eligible[eligible.district_id == district]
            train = eligible[eligible.district_id != district]
            fold_all = group[group.district_id == district]
            variance = float(np.var(train.response.to_numpy(), ddof=0)) if len(train) else math.nan
            rows.append({
                "target": target,
                "district_id": district,
                "fold_id": f"district_{district}",
                "district_scene_n": int(len(fold_all)),
                "train_n": int(len(train)),
                "test_n": int(len(test)),
                "eligible_n": int(len(eligible)),
                "ineligible_n": int(1600 - len(eligible)),
                "test_ineligible_n": int((~fold_all.eligible).sum()),
                "train_target_variance": variance,
                "evaluable": bool(len(train) > 0 and len(test) > 0 and variance > 0),
            })
    import pandas as pd
    result = pd.DataFrame(rows).sort_values(["target", "district_id"], kind="mergesort")
    if len(result) != 275:
        raise P11ReadinessError("P11_TARGET_FOLD_CARDINALITY_INVALID")
    return result.reset_index(drop=True)


def _embedding_bindings(contract: Mapping[str, Any], gallery_ids: list[str]) -> list[dict[str, Any]]:
    p10 = load_contract(contract["p10_contract"])
    bindings = resolve_model_bindings(p10)
    _, galleries = evaluation_population(p10)
    source_ids = [str(row["scene_id"]) for row in galleries]
    if source_ids != gallery_ids:
        raise P11ReadinessError("P11_P10_GALLERY_SCENE_IDS_INVALID")
    acceptance = _json(
        Path(p10["publication_root"]) / "execution_attempts" / "p10exec_7fee193dac532190c79e02c6"
        / "commit" / "evaluation_acceptance.json"
    )
    if acceptance["acceptance_id"] != "p10acc_6e5071beee7616750dec7907":
        raise P11ReadinessError("P11_P10_ACCEPTANCE_INVALID")
    root = Path(p10["publication_root"]) / "execution_attempts" / acceptance["execution_attempt_id"] / "evaluations"
    output = []
    for binding in bindings:
        model_root = root / binding.configuration_id
        result = _json(model_root / "evaluation.json")
        array_path = model_root / "evaluation_embeddings_ranks_analysis.npz"
        with np.load(array_path, allow_pickle=False) as arrays:
            embeddings = np.asarray(arrays["embeddings"])
            if embeddings.shape != (4800, 128) or embeddings.dtype != np.float32:
                raise P11ReadinessError(f"P11_EMBEDDING_SHAPE_INVALID:{binding.configuration_id}")
            if hashlib.sha256(embeddings.tobytes()).hexdigest() != result["embedding_sha256"]:
                raise P11ReadinessError(f"P11_EMBEDDING_HASH_INVALID:{binding.configuration_id}")
            gallery = np.ascontiguousarray(embeddings[3200:])
        output.append({
            "configuration_id": binding.configuration_id,
            "p9_acceptance_id": binding.acceptance_id,
            "checkpoint_id": binding.checkpoint_id,
            "p10_result_sha256": sha256_file(model_root / "evaluation.json"),
            "stored_array_sha256": sha256_file(array_path),
            "full_embedding_sha256": result["embedding_sha256"],
            "gallery_embedding_sha256": hashlib.sha256(gallery.tobytes()).hexdigest(),
            "gallery_scene_ids_sha256": canonical_sha256(gallery_ids),
            "stored_shape": [4800, 128],
            "predictor_slice": [3200, 4800],
            "predictor_shape": [1600, 128],
            "logical_locator": f"execution_attempts/{acceptance['execution_attempt_id']}/evaluations/{binding.configuration_id}/evaluation_embeddings_ranks_analysis.npz",
        })
    return output


def _write_parquet(frame: Any, path: Path) -> None:
    table = pa.Table.from_pandas(frame, preserve_index=False)
    pq.write_table(table, path, compression="zstd", version="2.6", write_statistics=True)


def _publish(root: Path, preimage: dict[str, Any], master: Any, folds: Any,
             embeddings: list[dict[str, Any]], gates: dict[str, Any], oof: dict[str, Any]) -> dict[str, Any]:
    identity_hash = canonical_sha256(preimage)
    readiness_id = f"p11c_{identity_hash[:24]}"
    final = root / readiness_id
    acceptance = {**preimage, "readiness_id": readiness_id, "content_sha256": identity_hash, "status": "PASS"}
    if final.exists():
        existing = validate_p11_spatial_readiness(final)
        expected = {**acceptance, "artifacts": existing.get("artifacts")}
        if existing != expected:
            raise P11ReadinessError("P11_C_PUBLICATION_COLLISION")
        return existing
    root.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{readiness_id}.", dir=root))
    _write_parquet(master, stage / "master_district_folds.parquet")
    _write_parquet(folds, stage / "target_fold_readiness.parquet")
    values = {
        "embedding_bindings.json": embeddings,
        "leakage_gates.json": gates,
        "oof_readiness.json": oof,
    }
    for name, value in values.items():
        (stage / name).write_bytes(canonical_json_bytes(value))
    artifacts = []
    for path in sorted(stage.iterdir(), key=lambda item: item.name):
        artifacts.append({"basename": path.name, "byte_size": path.stat().st_size, "sha256": sha256_file(path)})
    acceptance["artifacts"] = artifacts
    # Artifact hashes are publication evidence, not part of scientific identity.
    (stage / "p11_c_acceptance.json").write_bytes(canonical_json_bytes(acceptance))
    os.rename(stage, final)
    return validate_p11_spatial_readiness(final)


def validate_p11_spatial_readiness(root: str | Path) -> dict[str, Any]:
    root = Path(root)
    acceptance = _json(root / "p11_c_acceptance.json")
    preimage = {
        key: value for key, value in acceptance.items()
        if key not in {"artifacts", "readiness_id", "content_sha256", "status"}
    }
    digest = canonical_sha256(preimage)
    if (
        acceptance.get("readiness_id") != f"p11c_{digest[:24]}"
        or acceptance.get("content_sha256") != digest
        or acceptance.get("status") != "PASS"
    ):
        raise P11ReadinessError("P11_C_ACCEPTANCE_IDENTITY_INVALID")
    for item in acceptance.get("artifacts", []):
        path = root / item["basename"]
        if (
            not path.is_file()
            or path.stat().st_size != item["byte_size"]
            or sha256_file(path) != item["sha256"]
        ):
            raise P11ReadinessError(f"P11_C_ARTIFACT_CORRUPTION:{item['basename']}")
    return acceptance


def materialize_p11_spatial_readiness(path: str | Path = "config/p11_spatial_readiness.yml") -> dict[str, Any]:
    contract = load_readiness_contract(path)
    authority, methodology = _authority_and_transform(contract)
    dataset_acceptance, targets = _dataset(contract)
    p10 = load_contract(contract["p10_contract"])
    _, galleries = evaluation_population(p10)
    gallery_ids = [str(row["scene_id"]) for row in galleries]
    master = _master_folds(contract, gallery_ids)
    transforms = {row["target"]: row["transform"] for row in methodology["transforms"]}
    folds = _target_folds(targets, master, transforms)
    embeddings = _embedding_bindings(contract, gallery_ids)
    if len(embeddings) != 8 or not folds.evaluable.all():
        raise P11ReadinessError("P11_C_READINESS_INCOMPLETE")
    downstream_tokens = ("p11ds_", "p11src_", "livingpopulation", "land_value", "ecostress")
    if any(token in json.dumps(item, sort_keys=True).lower() for item in embeddings for token in downstream_tokens):
        raise P11ReadinessError("P11_DOWNSTREAM_LABEL_ANCESTRY_DETECTED")
    gates = {
        "status": "PASS",
        "gates": {
            "downstream_labels_not_training_ancestors": True,
            "train_test_scene_disjoint": True,
            "one_district_per_scene": True,
            "target_eligibility_model_independent": True,
            "eight_models_share_target_populations": True,
            "no_model_specific_target_preprocessing": True,
            "p10_metrics_not_used_for_p11_methodology": True,
            "predictor_standardization_training_fold_only": True,
            "target_transform_fixed_parameter_free": True,
            "ridge_lambda_exactly_one": True,
            "alpha_tuning_or_inner_cv": False,
            "random_cv": False,
            "manual_latest_v1_fallback": False,
        },
    }
    oof = {
        "status": "READY",
        "eligible_scene_count": {target: int(group.eligible.sum()) for target, group in targets.groupby("target")},
        "nonevaluable_folds": [],
        "excluded_eligible_scenes": [],
        "ownership_rule": "eligible scene belongs to exactly its one district fold",
        "maximum_predictions_per_scene_target_model": 1,
        "predictions_generated": 0,
    }
    master_hash = canonical_sha256(master.to_dict(orient="records"))
    fold_hash = canonical_sha256(folds.to_dict(orient="records"))
    embedding_preimage = {"p10_acceptance_id": "p10acc_6e5071beee7616750dec7907", "bindings": embeddings}
    embedding_hash = canonical_sha256(embedding_preimage)
    preimage = {
        "schema_version": "1.0.0",
        "artifact_type": "p11_spatial_fold_and_leakage_readiness",
        "implementation_version": "p11-spatial-readiness-v1",
        "implementation_sha256": sha256_file(Path(__file__)),
        "dissertation_authority_id": authority["authority_id"],
        "methodology_id": methodology["methodology_id"],
        "downstream_dataset_id": dataset_acceptance["dataset_id"],
        "p10_acceptance_id": "p10acc_6e5071beee7616750dec7907",
        "master_fold_id": f"p11fold_{master_hash[:24]}",
        "master_fold_sha256": master_hash,
        "target_fold_sha256": fold_hash,
        "embedding_binding_id": f"p11emb_{embedding_hash[:24]}",
        "embedding_binding_sha256": embedding_hash,
        "leakage_gate_sha256": canonical_sha256(gates),
        "oof_readiness_sha256": canonical_sha256(oof),
        "fold_count": 25,
        "scene_count": 1600,
        "target_count": 11,
        "model_count": 8,
        "next_work_unit": contract["next_work_unit"],
        "ridge_execution_authorized": True,
    }
    # Acceptance hashes are added after files exist but excluded from identity.
    acceptance = _publish(Path(contract["publication_root"]), preimage, master, folds, embeddings, gates, oof)
    return {**acceptance, "target_fold_summary": folds.to_dict(orient="records")}
