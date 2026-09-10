"""Fail-closed runtime projection of accepted S09 input identities."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Mapping

import pyarrow.parquet as pq
import torch

from artifact_protocol import sha256_file


PROFILE_BY_INTENSITY = {
    0.5: "weak_0.5x",
    1.0: "main_1.0x",
    2.0: "strong_2.0x",
}


class TrainingRuntimeInputError(RuntimeError):
    """A current accepted input cannot satisfy the formal runtime contract."""


def physical_profile_id(intensity: Any) -> str:
    """Resolve a logical S08 intensity to its immutable P4 physical profile."""
    if isinstance(intensity, bool):
        raise TrainingRuntimeInputError("S09_AUGMENTATION_INTENSITY_UNSUPPORTED")
    try:
        return PROFILE_BY_INTENSITY[float(intensity)]
    except (KeyError, TypeError, ValueError) as error:
        raise TrainingRuntimeInputError("S09_AUGMENTATION_INTENSITY_UNSUPPORTED") from error


def _read_json(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise TrainingRuntimeInputError(f"S09_{label}_MISSING")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise TrainingRuntimeInputError(f"S09_{label}_INVALID") from error
    if not isinstance(value, dict):
        raise TrainingRuntimeInputError(f"S09_{label}_INVALID")
    return value


def _artifact_record(records: Any, role: str) -> Mapping[str, Any]:
    matches = [row for row in records or []
               if isinstance(row, Mapping) and row.get("role") == role]
    if len(matches) != 1:
        raise TrainingRuntimeInputError(f"S09_{role.upper()}_RECORD_AMBIGUOUS")
    return matches[0]


class SceneCenterIndex:
    """Exact current-P1 scene centers, bound through current P3/P6/cache lineage."""

    def __init__(self, centers: Mapping[str, tuple[float, float, str]], *,
                 scene_index_id: str, scene_acceptance_id: str, p3_cache_id: str):
        self.centers = dict(centers)
        self.scene_index_id = scene_index_id
        self.scene_acceptance_id = scene_acceptance_id
        self.p3_cache_id = p3_cache_id

    @classmethod
    def from_current_contract(cls, training: Mapping[str, Any], cache_root: str | Path) -> "SceneCenterIndex":
        parents = training.get("parents") or {}
        parent_roots = training.get("parent_roots") or {}
        scene_data = Path(str(parent_roots.get("scene_data", "")))
        scene_index_id = str(parents.get("scene_index_id", ""))
        authority_id = str(parents.get("methodology_authority_id", ""))
        p3_cache_id = str(parents.get("p3_cache_id", ""))
        p3_acceptance_id = str(parents.get("p3_acceptance_id", ""))
        p6_acceptance_id = str(parents.get("p6_aggregate_acceptance_id", ""))
        if (not scene_data.is_absolute() or not scene_index_id.startswith("rsi_")
                or not authority_id.startswith("mta_") or not p3_cache_id.startswith("oscache_")
                or not p3_acceptance_id.startswith("osca_") or not p6_acceptance_id.startswith("mda_")):
            raise TrainingRuntimeInputError("S09_SCENE_CENTER_PARENT_CONTRACT_INCOMPLETE")

        cache_root = Path(cache_root)
        cache_acceptance = _read_json(cache_root / "acceptance.json", "PREPARED_CACHE_ACCEPTANCE")
        cache_parents = cache_acceptance.get("parents") or {}
        if (cache_acceptance.get("status") != "PASS"
                or cache_acceptance.get("cache_id") != cache_root.name
                or cache_parents.get("dataset_acceptance_id") != p6_acceptance_id
                or cache_parents.get("scene_cache_id") != p3_cache_id
                or cache_parents.get("scene_cache_acceptance_id") != p3_acceptance_id
                or cache_parents.get("methodology_authority_id") != authority_id):
            raise TrainingRuntimeInputError("S09_SCENE_CENTER_CACHE_LINEAGE_MISMATCH")

        p6_path = scene_data / "model_data" / "acceptance" / p6_acceptance_id / "model_data_acceptance.json"
        p6 = _read_json(p6_path, "P6_ACCEPTANCE")
        p6_parents = p6.get("parents") or {}
        scene_acceptance_id = str(p6_parents.get("scene_acceptance_id", ""))
        if (p6.get("status") != "PASS" or p6.get("model_data_acceptance_id") != p6_acceptance_id
                or p6_parents.get("authority_id") != authority_id
                or p6_parents.get("scene_index_id") != scene_index_id
                or p6_parents.get("p3_cache_id") != p3_cache_id
                or p6_parents.get("p3_acceptance_id") != p3_acceptance_id
                or not scene_acceptance_id.startswith("sia_")):
            raise TrainingRuntimeInputError("S09_SCENE_CENTER_P6_LINEAGE_MISMATCH")

        root = scene_data / "index" / scene_index_id
        parquet_path = root / "spatial_scene_index.parquet"
        manifest_path = root / "spatial_scene_index_manifest.json"
        acceptance_path = root / "acceptance" / scene_acceptance_id / "scene_index_acceptance.json"
        manifest = _read_json(manifest_path, "SCENE_INDEX_MANIFEST")
        acceptance = _read_json(acceptance_path, "SCENE_INDEX_ACCEPTANCE")
        if (manifest.get("status") != "PASS" or manifest.get("scene_index_id") != scene_index_id
                or manifest.get("authority_id") != authority_id or manifest.get("row_count") != 12_421
                or acceptance.get("status") != "PASS" or acceptance.get("acceptance_id") != scene_acceptance_id
                or acceptance.get("scene_index_id") != scene_index_id
                or acceptance.get("authority_id") != authority_id
                or acceptance.get("split_counts") != {"evaluation": 9000, "training": 2421, "validation": 1000}
                or not (acceptance.get("invariants") or {}).get("epsg_5186")
                or not (acceptance.get("invariants") or {}).get("centers_finite")):
            raise TrainingRuntimeInputError("S09_SCENE_INDEX_ACCEPTANCE_MISMATCH")
        parquet_record = _artifact_record(acceptance.get("artifact_checksums"), "spatial_scene_index")
        manifest_record = _artifact_record(acceptance.get("artifact_checksums"), "spatial_scene_index_manifest")
        if (parquet_path.is_symlink() or not parquet_path.is_file()
                or parquet_record.get("basename") != parquet_path.name
                or manifest_record.get("basename") != manifest_path.name
                or parquet_record.get("sha256") != sha256_file(parquet_path)
                or manifest_record.get("sha256") != sha256_file(manifest_path)):
            raise TrainingRuntimeInputError("S09_SCENE_INDEX_ARTIFACT_MISMATCH")

        try:
            rows = pq.read_table(parquet_path, columns=[
                "scene_id", "split", "center_x", "center_y", "epsg",
                "methodology_authority_id", "scene_index_id",
            ]).to_pylist()
        except Exception as error:
            raise TrainingRuntimeInputError("S09_SCENE_INDEX_UNREADABLE") from error
        centers: dict[str, tuple[float, float, str]] = {}
        counts = {"training": 0, "validation": 0, "evaluation": 0}
        for row in rows:
            scene_id = row.get("scene_id")
            split = row.get("split")
            x, y = row.get("center_x"), row.get("center_y")
            if (not isinstance(scene_id, str) or not scene_id or scene_id in centers
                    or split not in counts or row.get("epsg") != 5186
                    or row.get("methodology_authority_id") != authority_id
                    or row.get("scene_index_id") != scene_index_id
                    or isinstance(x, bool) or isinstance(y, bool)
                    or not isinstance(x, (int, float)) or not isinstance(y, (int, float))
                    or not math.isfinite(float(x)) or not math.isfinite(float(y))):
                raise TrainingRuntimeInputError("S09_SCENE_CENTER_ROW_INVALID")
            centers[scene_id] = (float(x), float(y), split)
            counts[split] += 1
        if len(centers) != 12_421 or counts != {"training": 2421, "validation": 1000, "evaluation": 9000}:
            raise TrainingRuntimeInputError("S09_SCENE_CENTER_POPULATION_MISMATCH")
        return cls(centers, scene_index_id=scene_index_id,
                   scene_acceptance_id=scene_acceptance_id, p3_cache_id=p3_cache_id)

    def attach(self, sample: Mapping[str, Any], expected_split: str) -> dict[str, Any]:
        scene_id = sample.get("scene_id")
        if not isinstance(scene_id, str) or scene_id not in self.centers:
            raise TrainingRuntimeInputError("S09_SCENE_CENTER_MISSING")
        x, y, split = self.centers[scene_id]
        lineage = sample.get("lineage") or {}
        parent = lineage.get("parent") or {}
        if (split != expected_split or sample.get("split") != expected_split
                or parent.get("scene_id") != scene_id or parent.get("cache_id") != self.p3_cache_id):
            raise TrainingRuntimeInputError("S09_SCENE_CENTER_SAMPLE_LINEAGE_MISMATCH")
        result = dict(sample)
        result["scene_center_5186"] = torch.tensor((x, y), dtype=torch.float64)
        return result
