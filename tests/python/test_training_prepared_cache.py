from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from training_prepared_cache import (  # noqa: E402
    ProductionPreparedData, build_logical_index, logical_training_role,
)
from training_worker import ProductionPreparedData as WorkerPreparedData  # noqa: E402


def test_worker_uses_the_canonical_prepared_cache_adapter() -> None:
    assert WorkerPreparedData is ProductionPreparedData


def test_only_selected_profile_projects_to_training_and_other_roles_do_not_leak() -> None:
    entries = [
        {"role": "training", "profile": "main_1.0x", "scene_id": "main", "view": 0},
        {"role": "training:weak_0.5x", "profile": "weak_0.5x", "scene_id": "weak", "view": 0},
        {"role": "training:strong_2.0x", "profile": "strong_2.0x", "scene_id": "strong", "view": 0},
        {"role": "validation_gallery", "profile": "original", "scene_id": "validation", "view": None},
        {"role": "unrelated", "profile": "weak_0.5x", "scene_id": "other", "view": None},
    ]
    index = build_logical_index(entries, "weak_0.5x")
    assert ("training", "weak", 0) in index
    assert not any(key[0] == "training" and key[1] in {"main", "strong", "other"} for key in index)
    assert ("validation_gallery", "validation", None) in index
    assert logical_training_role(entries[0], "main_1.0x") == "training"


def test_current_population_constants_are_not_historical() -> None:
    source = (ROOT / "python/training_prepared_cache.py").read_text(encoding="utf-8")
    assert "80_472" in source
    assert "1_000" in source
    assert "78_672" not in source
    assert "!= 400" not in source
