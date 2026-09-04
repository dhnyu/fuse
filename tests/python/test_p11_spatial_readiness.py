from __future__ import annotations

import json
import hashlib
import shutil
from pathlib import Path

import jsonschema
import numpy as np
import pyarrow.parquet as pq
import pytest
import yaml

from p11_spatial_readiness import (
    P11ReadinessError,
    apply_target_transform,
    invert_target_transform,
    materialize_p11_spatial_readiness,
    validate_p11_spatial_readiness,
)
from p9_v2_canonical import canonical_sha256


ROOT = Path(__file__).resolve().parents[2]


def _pointer() -> dict:
    return yaml.safe_load((ROOT / "config/p11_spatial_readiness_acceptance.yml").read_text())


def test_transformations_are_exact_and_round_trip() -> None:
    values = np.array([0.0, 1.0, 100.5, 50_034_680.0])
    transformed = apply_target_transform(values, "log1p")
    np.testing.assert_allclose(invert_target_transform(transformed, "log1p"), values, rtol=1e-14)
    assert np.array_equal(invert_target_transform(values, "identity"), values)
    with pytest.raises(P11ReadinessError, match="LOG1P_TARGET_NEGATIVE"):
        apply_target_transform(np.array([-0.1]), "log1p")


def test_methodology_identity_schema_and_map() -> None:
    authority = json.loads((ROOT / "config/dissertation_authority_p11_transformation.json").read_text())
    authority_schema = json.loads(
        (ROOT / "config/schemas/dissertation_authority_p11_transformation.schema.json").read_text()
    )
    jsonschema.Draft202012Validator(authority_schema).validate(authority)
    authority_preimage = {
        k: v for k, v in authority.items() if k not in {"authority_id", "content_sha256"}
    }
    authority_digest = canonical_sha256(authority_preimage)
    assert authority["authority_id"] == f"disauth_{authority_digest[:24]}"
    assert authority["content_sha256"] == authority_digest
    dissertation = ROOT.parent / "dhnyu-masters-dissertation"
    if dissertation.exists():
        for document in authority["dissertation"]["documents"]:
            path = dissertation / document["logical_path"]
            assert hashlib.sha256(path.read_bytes()).hexdigest() == document["sha256"]

    value = json.loads((ROOT / "config/p11_target_transformation_methodology.json").read_text())
    schema = json.loads((ROOT / "config/schemas/p11_target_transformation_methodology.schema.json").read_text())
    jsonschema.Draft202012Validator(schema).validate(value)
    preimage = {k: v for k, v in value.items() if k not in {"methodology_id", "content_sha256"}}
    digest = canonical_sha256(preimage)
    assert value["methodology_id"] == f"p11meth_{digest[:24]}"
    assert value["content_sha256"] == digest
    transforms = {row["target"]: row["transform"] for row in value["transforms"]}
    assert len(transforms) == 11
    assert transforms["ecostress_lst"] == "identity"
    assert set(transforms.values()) == {"identity", "log1p"}


def test_acceptance_folds_embeddings_leakage_and_oof() -> None:
    pointer = _pointer()
    root = Path(pointer["acceptance_path"]).parent
    assert hashlib.sha256(Path(pointer["acceptance_path"]).read_bytes()).hexdigest() == pointer[
        "acceptance_sha256"
    ]
    acceptance = validate_p11_spatial_readiness(root)
    schema = json.loads((ROOT / "config/schemas/p11_spatial_readiness_acceptance.schema.json").read_text())
    jsonschema.Draft202012Validator(schema).validate(acceptance)
    master = pq.read_table(root / "master_district_folds.parquet").to_pandas()
    folds = pq.read_table(root / "target_fold_readiness.parquet").to_pandas()
    bindings = json.loads((root / "embedding_bindings.json").read_text())
    gates = json.loads((root / "leakage_gates.json").read_text())
    oof = json.loads((root / "oof_readiness.json").read_text())
    assert len(master) == master.scene_id.nunique() == 1600
    assert master.district_id.nunique() == 25
    assert len(folds) == 275 and folds.evaluable.all()
    assert len(bindings) == 8
    assert all(row["stored_shape"] == [4800, 128] for row in bindings)
    assert all(row["predictor_shape"] == [1600, 128] for row in bindings)
    assert len({row["gallery_scene_ids_sha256"] for row in bindings}) == 1
    assert gates["gates"]["train_test_scene_disjoint"] is True
    assert gates["gates"]["ridge_lambda_exactly_one"] is True
    assert gates["gates"]["alpha_tuning_or_inner_cv"] is False
    assert gates["gates"]["random_cv"] is False
    assert gates["gates"]["manual_latest_v1_fallback"] is False
    assert oof["predictions_generated"] == 0
    assert oof["nonevaluable_folds"] == []
    assert oof["excluded_eligible_scenes"] == []


def test_idempotent_rerun_and_corruption_rejection(tmp_path: Path) -> None:
    pointer = _pointer()
    acceptance_path = Path(pointer["acceptance_path"])
    before = acceptance_path.stat().st_mtime_ns
    result = materialize_p11_spatial_readiness(ROOT / "config/p11_spatial_readiness.yml")
    assert result["readiness_id"] == pointer["readiness_id"]
    assert acceptance_path.stat().st_mtime_ns == before
    copied = tmp_path / "corrupt"
    shutil.copytree(acceptance_path.parent, copied)
    path = copied / "leakage_gates.json"
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(P11ReadinessError, match="P11_C_ARTIFACT_CORRUPTION"):
        validate_p11_spatial_readiness(copied)
