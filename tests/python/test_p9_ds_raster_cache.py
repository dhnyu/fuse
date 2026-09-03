from __future__ import annotations

import copy
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

import pytest
import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from canonical_config import canonical_json_bytes  # noqa: E402
from p7_training import collate, enqueue  # noqa: E402
from p9_model_families import ds_raster_from_batch  # noqa: E402
from p9_v2_canonical import sha256_file  # noqa: E402
from p9_v2_prepared_cache import (  # noqa: E402
    DSRasterCacheError, DSRasterCacheReader, DS_RASTER_CONTRACT_ID,
)
from p9_v2_training_controller import latest_checkpoint_boundary  # noqa: E402
from p9_v2_training_worker import create_state, load_worker_values  # noqa: E402


PRODUCTION_CACHE = Path(
    "/mnt/hdd002/dhnyu/fusedata/models/reduced/formal_training/production_cache/"
    "p9cba_5c472951ac896e82a0a0f555"
)
P9_B_MATRIX = Path(
    "/mnt/hdd002/dhnyu/fusedata/runtime/p9_b_campaigns/"
    "20260903_0539_cfgd128/p9_b_training_matrix.json"
)
CATEGORIES = Path(
    "/mnt/hdd002/dhnyu/fusedata/scene_data/reduced/observations/"
    "obs_cd00016f6b5bfd960b0a6842/production/acceptance/"
    "bsa_e617ee0280a6edfa722994d3/spatial_categories.json"
)


def legacy_hash(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def make_cache(root: Path) -> tuple[Path, dict]:
    ds = root / "ds"
    entries = ds / "entries"
    entries.mkdir(parents=True)
    tensor = torch.arange(26 * 100 * 100, dtype=torch.float32).reshape(26, 100, 100)
    identity = {
        "schema_version": "1.0.0", "contract_id": DS_RASTER_CONTRACT_ID,
        "geometry_layout_version": "3.0.0", "role": "training",
        "scene_id": "scene-a", "view_id": "view-a", "source_cache_key": "a" * 64,
        "shape": [26, 100, 100], "dtype": "torch.float32",
        "raw_sha256": hashlib.sha256(tensor.numpy().tobytes()).hexdigest(),
    }
    cache_key = legacy_hash(identity)
    payload_path = entries / f"{cache_key}.pt"
    torch.save({"manifest": {**identity, "cache_key": cache_key}, "raster": tensor}, payload_path)
    row = {**identity, "cache_key": cache_key, "global_index": 0,
           "relative_path": f"entries/{cache_key}.pt",
           "payload_size_bytes": payload_path.stat().st_size,
           "payload_sha256": sha256_file(payload_path)}
    manifest = {"schema_version": "1.0.0", "status": "PASS",
                "contract_id": DS_RASTER_CONTRACT_ID, "entry_count": 1, "entries": [row]}
    manifest["content_sha256"] = legacy_hash(manifest)
    manifest["cache_id"] = "p9ds_" + manifest["content_sha256"][:24]
    manifest_path = ds / "ds_cache_manifest.json"
    manifest_path.write_bytes(canonical_json_bytes(manifest))
    production = {"ds": {"cache_id": manifest["cache_id"],
        "manifest_relative_path": "ds/ds_cache_manifest.json",
        "manifest_sha256": sha256_file(manifest_path)}}
    (root / "production_cache_manifest.json").write_bytes(canonical_json_bytes(production))
    return payload_path, row


def rewrite_manifests(root: Path, mutate) -> None:
    path = root / "ds/ds_cache_manifest.json"
    manifest = json.loads(path.read_text())
    mutate(manifest)
    scientific = {key: value for key, value in manifest.items()
                  if key not in {"content_sha256", "cache_id"}}
    manifest["content_sha256"] = legacy_hash(scientific)
    manifest["cache_id"] = "p9ds_" + manifest["content_sha256"][:24]
    path.write_bytes(canonical_json_bytes(manifest))
    production_path = root / "production_cache_manifest.json"
    production = json.loads(production_path.read_text())
    production["ds"]["cache_id"] = manifest["cache_id"]
    production["ds"]["manifest_sha256"] = sha256_file(path)
    production_path.write_bytes(canonical_json_bytes(production))


def production_spec() -> dict[str, str]:
    return {"configuration_id": "cmp_ds_like", "matrix": str(P9_B_MATRIX),
            "cache_root": str(PRODUCTION_CACHE), "categories": str(CATEGORIES),
            "training_config": str(ROOT / "config/p7_deterministic_training.yml"),
            "model_config": str(ROOT / "config/p6_model_dataloader.yml")}


def test_reader_validates_identity_and_has_no_online_fallback(tmp_path: Path) -> None:
    _, row = make_cache(tmp_path)
    reader = DSRasterCacheReader(tmp_path, maximum_memory_bytes=2 * 1024**2)
    batch = {"scene_ids": [row["scene_id"]], "view_ids": [row["view_id"]]}
    first = reader.batch(batch, row["role"], torch.device("cpu"))
    second = reader.batch(batch, row["role"], torch.device("cpu"))
    assert torch.equal(first, second)
    assert reader.stats()["misses"] == 1 and reader.stats()["hits"] == 1
    with pytest.raises(DSRasterCacheError, match="LOOKUP_MISSING"):
        reader.batch(batch, "validation_gallery", torch.device("cpu"))


def test_accepted_cache_covers_every_physical_view_and_fixed_validation_input() -> None:
    reader = DSRasterCacheReader(PRODUCTION_CACHE, maximum_memory_bytes=0)
    assert Counter(row["role"] for row in reader.manifest["entries"]) == {
        "training": 2_421 * 16,
        "training:weak_0.5x": 2_421 * 8,
        "training:strong_2.0x": 2_421 * 8,
        "validation_query": 800,
        "validation_gallery": 400,
    }
    assert len(reader.index) == 78_672


@pytest.mark.parametrize("corruption", ["payload", "contract", "source", "shape", "duplicate"])
def test_reader_rejects_corruption_and_staleness(tmp_path: Path, corruption: str) -> None:
    payload, _ = make_cache(tmp_path)
    if corruption == "payload":
        payload.write_bytes(payload.read_bytes()[:-17])
        reader = DSRasterCacheReader(tmp_path)
        with pytest.raises(DSRasterCacheError, match="PAYLOAD_HASH_MISMATCH"):
            reader._get("training", "scene-a", "view-a")
        return
    def mutate(manifest):
        row = manifest["entries"][0]
        if corruption == "contract": manifest["contract_id"] = "stale-contract"
        elif corruption == "source": row["source_cache_key"] = "b" * 64
        elif corruption == "shape": row["shape"] = [25, 100, 100]
        elif corruption == "duplicate":
            manifest["entries"].append(copy.deepcopy(row)); manifest["entry_count"] = 2
    rewrite_manifests(tmp_path, mutate)
    with pytest.raises(DSRasterCacheError):
        DSRasterCacheReader(tmp_path)


@pytest.mark.parametrize("global_index", [
    pytest.param(0, id="main-mixed"),
    pytest.param(144, id="main-no-roads"),
    pytest.param(432, id="main-buildings-only"),
    pytest.param(576, id="main-poi-only"),
    pytest.param(704, id="main-empty-vector-channels"),
    pytest.param(1_280, id="main-roads-and-poi"),
    pytest.param(2_560, id="main-roads-only"),
    pytest.param(38_736, id="strong-view"),
    pytest.param(58_104, id="weak-view"),
    pytest.param(77_472, id="validation-gallery"),
    pytest.param(77_872, id="validation-query"),
])
def test_accepted_cache_is_bitwise_equal_to_online_raster(global_index: int) -> None:
    prepared = torch.load(PRODUCTION_CACHE / "prepared" / f"{global_index:06d}.pt",
                          map_location="cpu", weights_only=False)
    batch = collate([prepared["sample"]], {name: {"mask": 0} for name in ()})
    online = ds_raster_from_batch(batch)
    reader = DSRasterCacheReader(PRODUCTION_CACHE, maximum_memory_bytes=2 * 1024**2)
    cached = reader.batch(batch, prepared["spec"]["role"], torch.device("cpu"))
    assert torch.equal(online, cached)


def test_cache_lookup_preserves_requested_batch_order() -> None:
    prepared = [torch.load(PRODUCTION_CACHE / "prepared" / f"{index:06d}.pt",
                           map_location="cpu", weights_only=False)
                for index in (0, 16)]
    batches = [collate([row["sample"]], {}) for row in prepared]
    reader = DSRasterCacheReader(PRODUCTION_CACHE, maximum_memory_bytes=4 * 1024**2)
    forward = reader.batch(collate([row["sample"] for row in prepared], {}),
                           "training", torch.device("cpu"))
    reverse = reader.batch(collate([row["sample"] for row in reversed(prepared)], {}),
                           "training", torch.device("cpu"))
    assert torch.equal(forward[0], ds_raster_from_batch(batches[0])[0])
    assert torch.equal(forward[1], ds_raster_from_batch(batches[1])[0])
    assert torch.equal(reverse, forward.flip(0))


def test_cached_and_online_paths_preserve_forward_gradient_update_queue_and_sampler() -> None:
    values = load_worker_values(production_spec())
    samples = [values["data"].sample("training", scene, values["data"].views[scene][0])
               for scene in values["data"].training_scenes[:2]]
    batch = collate(samples, values["vocabulary"])
    online = ds_raster_from_batch(batch)
    cached = values["ds_raster_cache"].batch(
        batch, values["data"].physical_training_role, torch.device("cpu"))
    assert torch.equal(online, cached)
    torch.manual_seed(17)
    left = create_state(values, torch.device("cpu"))
    right = copy.deepcopy(left)
    torch.manual_seed(29)
    left_output = left.model.online(batch, None, online)["contrastive_embedding"]
    torch.manual_seed(29)
    right_output = right.model.online(batch, None, cached)["contrastive_embedding"]
    assert torch.equal(left_output, right_output)
    left_loss = left_output.square().mean(); right_loss = right_output.square().mean()
    assert torch.equal(left_loss, right_loss)
    left_loss.backward(); right_loss.backward()
    for lhs, rhs in zip(left.model.online.parameters(), right.model.online.parameters(), strict=True):
        assert torch.equal(lhs.grad, rhs.grad)
    left.optimizer.step(); right.optimizer.step()
    for lhs, rhs in zip(left.model.online.parameters(), right.model.online.parameters(), strict=True):
        assert torch.equal(lhs, rhs)
    enqueue(left.queue, left_output.detach(), batch["scene_numeric_ids"], batch["scene_center_5186"])
    enqueue(right.queue, right_output.detach(), batch["scene_numeric_ids"], batch["scene_center_5186"])
    assert left.queue["pointer"] == right.queue["pointer"] == 2
    for key in ("values", "scene_ids", "centers"):
        assert torch.equal(left.queue[key], right.queue[key])
    assert left.queue["valid_count"] == right.queue["valid_count"]
    assert left.queue["enqueue_count"] == right.queue["enqueue_count"]


def test_interruption_boundary_ignores_newer_uncheckpointed_progress() -> None:
    checkpoint = {"event_type": "VALIDATION_CHECKPOINT_COMMITTED", "payload": {
        "completed_epoch": 75, "resume_epoch": 76, "optimizer_update": 5700}}
    progress = {"event_type": "PROGRESS_SUMMARY_COMMITTED", "payload": {
        "ending_epoch": 76, "last_update": 5776}}
    epoch = {"event_type": "EPOCH_STARTED", "payload": {
        "epoch": 77, "starting_optimizer_update": 5776}}
    assert latest_checkpoint_boundary([checkpoint, progress, epoch]) == {
        "completed_epoch": 75, "resume_epoch": 76, "optimizer_update": 5700}


def test_production_worker_requires_cache_and_never_calls_online_ds_rasterization() -> None:
    source = (ROOT / "python/p9_v2_training_worker.py").read_text(encoding="utf-8")
    assert "DSRasterCacheReader" in source
    assert "ds_raster_from_batch" not in source
