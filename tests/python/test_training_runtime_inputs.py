from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from artifact_protocol import sha256_file  # noqa: E402
from training_runtime_inputs import SceneCenterIndex, TrainingRuntimeInputError  # noqa: E402


AUTHORITY = "mta_" + "a" * 24
SCENE_INDEX = "rsi_" + "b" * 24
SCENE_ACCEPTANCE = "sia_" + "c" * 24
P3_CACHE = "oscache_" + "d" * 24
P3_ACCEPTANCE = "osca_" + "e" * 24
P6_ACCEPTANCE = "mda_" + "f" * 24
CACHE = "s09cache_" + "1" * 24


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def runtime_fixture(tmp_path: Path, *, duplicate: bool = False, epsg: int = 5186,
                    invalid_coordinate: bool = False):
    scene_data = tmp_path / "scene_data"
    index_root = scene_data / "index" / SCENE_INDEX
    index_root.mkdir(parents=True)
    splits = ["training"] * 2421 + ["validation"] * 1000 + ["evaluation"] * 9000
    ids = [f"scene-{index:05d}" for index in range(12421)]
    if duplicate:
        ids[-1] = ids[0]
    centers_x = [float(index) for index in range(12421)]
    if invalid_coordinate:
        centers_x[-1] = math.nan
    table = pa.table({
        "scene_id": ids, "split": splits, "center_x": centers_x,
        "center_y": [float(index + 1) for index in range(12421)],
        "epsg": [epsg] * 12421,
        "methodology_authority_id": [AUTHORITY] * 12421,
        "scene_index_id": [SCENE_INDEX] * 12421,
    })
    parquet = index_root / "spatial_scene_index.parquet"
    pq.write_table(table, parquet)
    manifest = index_root / "spatial_scene_index_manifest.json"
    _write_json(manifest, {
        "status": "PASS", "scene_index_id": SCENE_INDEX, "authority_id": AUTHORITY,
        "row_count": 12421,
    })
    acceptance = index_root / "acceptance" / SCENE_ACCEPTANCE / "scene_index_acceptance.json"
    _write_json(acceptance, {
        "status": "PASS", "acceptance_id": SCENE_ACCEPTANCE,
        "scene_index_id": SCENE_INDEX, "authority_id": AUTHORITY,
        "split_counts": {"evaluation": 9000, "training": 2421, "validation": 1000},
        "invariants": {"epsg_5186": True, "centers_finite": True},
        "artifact_checksums": [
            {"role": "spatial_scene_index", "basename": parquet.name, "sha256": sha256_file(parquet)},
            {"role": "spatial_scene_index_manifest", "basename": manifest.name, "sha256": sha256_file(manifest)},
        ],
    })
    _write_json(scene_data / "model_data" / "acceptance" / P6_ACCEPTANCE / "model_data_acceptance.json", {
        "status": "PASS", "model_data_acceptance_id": P6_ACCEPTANCE,
        "parents": {"authority_id": AUTHORITY, "scene_index_id": SCENE_INDEX,
                    "scene_acceptance_id": SCENE_ACCEPTANCE, "p3_cache_id": P3_CACHE,
                    "p3_acceptance_id": P3_ACCEPTANCE},
    })
    cache_root = tmp_path / CACHE
    _write_json(cache_root / "acceptance.json", {
        "status": "PASS", "cache_id": CACHE,
        "parents": {"methodology_authority_id": AUTHORITY,
                    "dataset_acceptance_id": P6_ACCEPTANCE,
                    "scene_cache_id": P3_CACHE, "scene_cache_acceptance_id": P3_ACCEPTANCE},
    })
    training = {
        "parent_roots": {"scene_data": str(scene_data)},
        "parents": {"methodology_authority_id": AUTHORITY, "scene_index_id": SCENE_INDEX,
                    "p3_cache_id": P3_CACHE, "p3_acceptance_id": P3_ACCEPTANCE,
                    "p6_aggregate_acceptance_id": P6_ACCEPTANCE},
    }
    return training, cache_root


def test_current_scene_center_resolution_and_historical_sibling_is_ignored(tmp_path):
    training, cache = runtime_fixture(tmp_path)
    sibling = Path(training["parent_roots"]["scene_data"]) / "index" / ("rsi_" + "9" * 24)
    sibling.mkdir(parents=True)
    (sibling / "spatial_scene_index.parquet").write_bytes(b"historical")
    index = SceneCenterIndex.from_current_contract(training, cache)
    assert len(index.centers) == 12421
    sample = {"scene_id": "scene-00000", "split": "training",
              "lineage": {"parent": {"scene_id": "scene-00000", "cache_id": P3_CACHE}}}
    resolved = index.attach(sample, "training")
    assert torch.equal(resolved["scene_center_5186"], torch.tensor([0.0, 1.0], dtype=torch.float64))
    assert "scene_center_5186" not in sample


@pytest.mark.parametrize("kwargs", [
    {"duplicate": True}, {"epsg": 4326}, {"invalid_coordinate": True},
])
def test_scene_center_rows_fail_closed(tmp_path, kwargs):
    training, cache = runtime_fixture(tmp_path, **kwargs)
    with pytest.raises(TrainingRuntimeInputError, match="SCENE_CENTER_ROW_INVALID"):
        SceneCenterIndex.from_current_contract(training, cache)


def test_missing_and_mismatched_scene_center_fail_closed():
    index = SceneCenterIndex({"scene": (1.0, 2.0, "training")},
                             scene_index_id=SCENE_INDEX,
                             scene_acceptance_id=SCENE_ACCEPTANCE, p3_cache_id=P3_CACHE)
    with pytest.raises(TrainingRuntimeInputError, match="SCENE_CENTER_MISSING"):
        index.attach({"scene_id": "missing"}, "training")
    bad = {"scene_id": "scene", "split": "training",
           "lineage": {"parent": {"scene_id": "scene", "cache_id": "historical"}}}
    with pytest.raises(TrainingRuntimeInputError, match="SAMPLE_LINEAGE_MISMATCH"):
        index.attach(bad, "training")


def test_wrong_current_parent_fails_without_directory_fallback(tmp_path):
    training, cache = runtime_fixture(tmp_path)
    training["parents"]["scene_index_id"] = "rsi_" + "8" * 24
    with pytest.raises(TrainingRuntimeInputError, match="P6_LINEAGE_MISMATCH"):
        SceneCenterIndex.from_current_contract(training, cache)
