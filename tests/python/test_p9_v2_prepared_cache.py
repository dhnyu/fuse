from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from p9_v2_prepared_cache import (  # noqa: E402
    ProductionPreparedData, build_logical_index, logical_training_role,
)
from p9_v2_training_pilot import ProductionPreparedData as PilotPreparedData  # noqa: E402
from p9_v2_training_worker import ProductionPreparedData as WorkerPreparedData  # noqa: E402


CACHE = Path("/mnt/hdd002/dhnyu/fusedata/models/reduced/formal_training/production_cache/p9cba_5c472951ac896e82a0a0f555")


@pytest.fixture(scope="module")
def prepared_profiles() -> dict[str, ProductionPreparedData]:
    if not (CACHE / "canonical_cache_plan.json").is_file():
        pytest.skip("accepted production cache unavailable")
    return {
        profile: ProductionPreparedData(CACHE, profile, 8)
        for profile in ("main_1.0x", "weak_0.5x", "strong_2.0x")
    }


def test_worker_and_pilot_share_one_prepared_cache_adapter() -> None:
    assert WorkerPreparedData is ProductionPreparedData
    assert PilotPreparedData is ProductionPreparedData


def test_physical_profile_populations_and_logical_k(prepared_profiles) -> None:
    main = prepared_profiles["main_1.0x"]
    weak = prepared_profiles["weak_0.5x"]
    strong = prepared_profiles["strong_2.0x"]
    assert len(main.training_scenes) == len(weak.training_scenes) == len(strong.training_scenes) == 2_421
    assert sum(map(len, main.physical_views.values())) == 2_421 * 16
    assert sum(map(len, weak.physical_views.values())) == 2_421 * 8
    assert sum(map(len, strong.physical_views.values())) == 2_421 * 8
    assert all(sum(map(len, item.views.values())) == 2_421 * 8 for item in (main, weak, strong))
    assert main.physical_training_role == "training"
    assert weak.physical_training_role == "training:weak_0.5x"
    assert strong.physical_training_role == "training:strong_2.0x"


@pytest.mark.parametrize("profile", ("main_1.0x", "weak_0.5x", "strong_2.0x"))
def test_payload_lookup_preserves_physical_spec(profile, prepared_profiles) -> None:
    prepared = prepared_profiles[profile]
    scene = prepared.training_scenes[0]
    view = prepared.views[scene][0]
    spec = prepared.index[("training", scene, view)]
    assert spec["profile"] == profile
    assert spec["role"] == ("training" if profile == "main_1.0x" else f"training:{profile}")
    assert isinstance(prepared.sample("training", scene, view), dict)


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


def test_cache_plan_roles_remain_byte_unchanged(prepared_profiles) -> None:
    plan_path = CACHE / "canonical_cache_plan.json"
    before = plan_path.read_bytes()
    plan = json.loads(before)
    assert any(row["role"] == "training:weak_0.5x" for row in plan["entries"])
    assert any(row["role"] == "training:strong_2.0x" for row in plan["entries"])
    assert plan_path.read_bytes() == before
