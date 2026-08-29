from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from p7_geometry_cache import GeometryCacheReader, GeometryCacheWriter, CACHE_SCHEMA_VERSION


def record(index: int = 0) -> dict:
    return {
        "cache_schema_version": CACHE_SCHEMA_VERSION,
        "geometry_layout_version": "3.0.0",
        "cache_key": f"{index:064x}",
        "lookup_key": f"training\0scene-{index}\0view-{index}",
        "identity": {"scene_id": f"scene-{index}", "view_id": f"view-{index}",
                     "geometry_layout_version": "3.0.0"},
    }


def build(root: Path) -> Path:
    writer = GeometryCacheWriter(root)
    item = record()
    writer.put(item, torch.arange(12, dtype=torch.float32).reshape(3, 4),
               torch.arange(6, dtype=torch.float32).reshape(3, 2))
    writer.finalize("p7a_" + "1" * 24, [item])
    return root / "geometry_cache_manifest.json"


def test_cache_manifest_complete_and_exact_read(tmp_path):
    manifest = build(tmp_path / "cache")
    reader = GeometryCacheReader(manifest, maximum_memory_bytes=1024)
    magnitude, phase = reader._get("training", "scene-0", "view-0")
    assert torch.equal(magnitude, torch.arange(12, dtype=torch.float32).reshape(3, 4))
    assert torch.equal(phase, torch.arange(6, dtype=torch.float32).reshape(3, 2))
    assert reader.stats()["misses"] == 1
    reader._get("training", "scene-0", "view-0")
    assert reader.stats()["hits"] == 1


def test_cache_rejects_incomplete_old_layout_and_corruption(tmp_path):
    manifest = build(tmp_path / "cache")
    complete = manifest.parent / "COMPLETE.json"
    complete.unlink()
    with pytest.raises((FileNotFoundError, ValueError)):
        GeometryCacheReader(manifest)

    manifest = build(tmp_path / "old")
    value = json.loads(manifest.read_text()); value["geometry_layout_version"] = "2.0.0"
    manifest.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="incomplete or incompatible"):
        GeometryCacheReader(manifest)

    manifest = build(tmp_path / "corrupt")
    reader = GeometryCacheReader(manifest)
    payload = manifest.parent / reader.manifest["entries"][0]["relative_path"]
    with payload.open("ab") as stream:
        stream.write(b"corrupt")
    with pytest.raises(ValueError, match="checksum"):
        reader._get("training", "scene-0", "view-0")


def test_cache_same_id_different_bytes_collision(tmp_path):
    writer = GeometryCacheWriter(tmp_path / "cache"); item = record()
    writer.put(item, torch.ones((1, 2)), torch.ones((1, 2)))
    with pytest.raises(FileExistsError, match="different-bytes"):
        writer.put(item, torch.zeros((1, 2)), torch.ones((1, 2)))
