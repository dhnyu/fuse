"""Read-only logical projection of the accepted P9 prepared-view cache."""

from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from pathlib import Path
from typing import Any, Iterable, Mapping

import torch

from canonical_config import canonical_json_bytes
from p9_v2_canonical import sha256_file


DS_CACHE_SCHEMA_VERSION = "1.0.0"
DS_RASTER_CONTRACT_ID = "p8ds_73137985bd6b172f6711a062"
DS_RASTER_SHAPE = (26, 100, 100)
DS_RASTER_DTYPE = "torch.float32"


def _legacy_cache_sha256(value: Any) -> str:
    """Reproduce the accepted production-cache identity byte contract."""
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


class PreparedCacheError(RuntimeError):
    """The immutable prepared cache cannot satisfy the requested profile."""


class DSRasterCacheError(PreparedCacheError):
    """The accepted deterministic DS raster cache is absent or inconsistent."""


def logical_training_role(row: Mapping[str, Any], selected_profile: str) -> str | None:
    """Project one selected physical training profile to the logical training role."""
    role = row.get("role")
    if not isinstance(role, str):
        raise PreparedCacheError("PREPARED_ROLE_INVALID")
    if role == "training" or role.startswith("training:"):
        return "training" if row.get("profile") == selected_profile else None
    return role


def build_logical_index(
    entries: Iterable[Mapping[str, Any]], selected_profile: str,
) -> dict[tuple[str, str, int | None], dict[str, Any]]:
    """Build a logical index while retaining every physical cache row unchanged."""
    index: dict[tuple[str, str, int | None], dict[str, Any]] = {}
    for source in entries:
        role = logical_training_role(source, selected_profile)
        if role is None:
            continue
        row = dict(source)
        key = (role, row["scene_id"], row["view"])
        if key in index:
            raise PreparedCacheError("DUPLICATE_PREPARED_VIEW")
        index[key] = row
    return index


class ProductionPreparedData:
    """Read accepted immutable prepared views by logical scientific identity."""

    def __init__(self, root: str | Path, profile: str, logical_k: int):
        self.root = Path(root)
        plan = json.loads((self.root / "canonical_cache_plan.json").read_text(encoding="utf-8"))
        if int(plan["entry_count"]) != 78_672 or len(plan["entries"]) != 78_672:
            raise PreparedCacheError("PRODUCTION_CACHE_ENTRY_COUNT_MISMATCH")
        self.profile = profile
        self.index = build_logical_index(plan["entries"], profile)
        physical_roles = {
            row["role"] for (role, _, _), row in self.index.items() if role == "training"
        }
        if len(physical_roles) != 1:
            raise PreparedCacheError("PHYSICAL_TRAINING_ROLE_AMBIGUOUS")
        self.physical_training_role = next(iter(physical_roles))
        by_scene: dict[str, list[int]] = {}
        for role, scene, view in self.index:
            if role == "training":
                by_scene.setdefault(scene, []).append(int(view))
        self.physical_views = {scene: tuple(sorted(values)) for scene, values in by_scene.items()}
        self.views = {scene: values[:logical_k] for scene, values in self.physical_views.items()}
        if len(self.views) != 2_421 or any(len(values) != logical_k for values in self.views.values()):
            raise PreparedCacheError("PRODUCTION_TRAINING_POPULATION_MISMATCH")
        self.training_scenes = sorted(self.views)
        self.validation_scenes = sorted({
            scene for role, scene, _ in self.index if role == "validation_gallery"
        })
        if len(self.validation_scenes) != 400:
            raise PreparedCacheError("FIXED_VALIDATION_IDENTITY_MISMATCH")

    def sample(self, role: str, scene: str, view: int | None) -> dict[str, Any]:
        spec = self.index.get((role, scene, view))
        if spec is None:
            raise PreparedCacheError("PREPARED_VIEW_MISSING")
        index = int(spec["global_index"])
        payload = torch.load(
            self.root / "prepared" / f"{index:06d}.pt", map_location="cpu", weights_only=False)
        if payload.get("spec") != spec or int(payload.get("global_index", -1)) != index:
            raise PreparedCacheError("PREPARED_PAYLOAD_IDENTITY_MISMATCH")
        return payload["sample"]


def _ds_entry_identity(row: Mapping[str, Any]) -> dict[str, Any]:
    return {key: row[key] for key in (
        "schema_version", "contract_id", "geometry_layout_version", "role",
        "scene_id", "view_id", "source_cache_key", "shape", "dtype", "raw_sha256",
    )}


class DSRasterCacheReader:
    """Fail-closed reader for the accepted per-view deterministic DS raster cache."""

    def __init__(self, production_cache_root: str | Path,
                 maximum_memory_bytes: int = 4 * 1024**3) -> None:
        self.production_cache_root = Path(production_cache_root)
        production_path = self.production_cache_root / "production_cache_manifest.json"
        production = json.loads(production_path.read_text(encoding="utf-8"))
        binding = production.get("ds", {})
        manifest_path = self.production_cache_root / str(binding.get("manifest_relative_path", ""))
        if (not manifest_path.is_file()
                or binding.get("manifest_sha256") != sha256_file(manifest_path)):
            raise DSRasterCacheError("DS_CACHE_PRODUCTION_BINDING_MISMATCH")
        self.root = manifest_path.parent
        self.manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        scientific = {key: value for key, value in self.manifest.items()
                      if key not in {"content_sha256", "cache_id"}}
        content_hash = _legacy_cache_sha256(scientific)
        if (self.manifest.get("schema_version") != DS_CACHE_SCHEMA_VERSION
                or self.manifest.get("status") != "PASS"
                or self.manifest.get("contract_id") != DS_RASTER_CONTRACT_ID
                or self.manifest.get("content_sha256") != content_hash
                or self.manifest.get("cache_id") != "p9ds_" + content_hash[:24]
                or binding.get("cache_id") != self.manifest.get("cache_id")):
            raise DSRasterCacheError("DS_CACHE_MANIFEST_INVALID")
        entries = self.manifest.get("entries")
        if not isinstance(entries, list) or len(entries) != int(self.manifest.get("entry_count", -1)):
            raise DSRasterCacheError("DS_CACHE_ENTRY_COUNT_MISMATCH")
        self.index: dict[tuple[str, str, str], dict[str, Any]] = {}
        for source in entries:
            row = dict(source)
            try:
                identity = _ds_entry_identity(row)
                key = (str(row["role"]), str(row["scene_id"]), str(row["view_id"]))
            except (KeyError, TypeError) as error:
                raise DSRasterCacheError("DS_CACHE_ENTRY_MALFORMED") from error
            if (row.get("cache_key") != _legacy_cache_sha256(identity)
                    or row.get("contract_id") != DS_RASTER_CONTRACT_ID
                    or row.get("geometry_layout_version") != "3.0.0"
                    or tuple(row.get("shape", ())) != DS_RASTER_SHAPE
                    or row.get("dtype") != DS_RASTER_DTYPE
                    or key in self.index):
                raise DSRasterCacheError("DS_CACHE_ENTRY_IDENTITY_INVALID")
            self.index[key] = row
        self.maximum_memory_bytes = int(maximum_memory_bytes)
        self.memory: OrderedDict[tuple[str, str, str], tuple[torch.Tensor, int]] = OrderedDict()
        self.memory_bytes = self.hits = self.misses = self.evictions = 0

    @property
    def cache_id(self) -> str:
        return str(self.manifest["cache_id"])

    def _get(self, role: str, scene_id: str, view_id: str) -> torch.Tensor:
        key = (role, scene_id, view_id)
        if key in self.memory:
            value = self.memory.pop(key)
            self.memory[key] = value
            self.hits += 1
            return value[0]
        row = self.index.get(key)
        if row is None:
            raise DSRasterCacheError(f"DS_CACHE_LOOKUP_MISSING:{role}:{scene_id}:{view_id}")
        path = (self.root / row["relative_path"]).resolve()
        if path.parent != (self.root / "entries").resolve() or path.is_symlink() or not path.is_file():
            raise DSRasterCacheError("DS_CACHE_PAYLOAD_PATH_INVALID")
        if path.stat().st_size != int(row["payload_size_bytes"]) or sha256_file(path) != row["payload_sha256"]:
            raise DSRasterCacheError("DS_CACHE_PAYLOAD_HASH_MISMATCH")
        try:
            payload = torch.load(path, map_location="cpu", mmap=True, weights_only=True)
        except Exception as error:
            raise DSRasterCacheError("DS_CACHE_PAYLOAD_UNREADABLE") from error
        if payload.get("manifest") != {**_ds_entry_identity(row), "cache_key": row["cache_key"]}:
            raise DSRasterCacheError("DS_CACHE_PAYLOAD_MANIFEST_MISMATCH")
        tensor = payload.get("raster")
        if (not isinstance(tensor, torch.Tensor) or tuple(tensor.shape) != DS_RASTER_SHAPE
                or str(tensor.dtype) != DS_RASTER_DTYPE or not tensor.is_contiguous()):
            raise DSRasterCacheError("DS_CACHE_PAYLOAD_TENSOR_INVALID")
        observed_raw = hashlib.sha256(tensor.numpy().tobytes()).hexdigest()
        if observed_raw != row["raw_sha256"] or not bool(torch.isfinite(tensor).all()):
            raise DSRasterCacheError("DS_CACHE_PAYLOAD_TENSOR_HASH_MISMATCH")
        size = tensor.numel() * tensor.element_size()
        self.misses += 1
        while self.memory and self.memory_bytes + size > self.maximum_memory_bytes:
            _, (_, removed) = self.memory.popitem(last=False)
            self.memory_bytes -= removed
            self.evictions += 1
        if size <= self.maximum_memory_bytes:
            self.memory[key] = (tensor, size)
            self.memory_bytes += size
        return tensor

    def batch(self, batch: Mapping[str, Any], role: str, device: torch.device) -> torch.Tensor:
        scenes = batch.get("scene_ids")
        views = batch.get("view_ids")
        if not isinstance(scenes, list) or not isinstance(views, list) or len(scenes) != len(views):
            raise DSRasterCacheError("DS_CACHE_BATCH_IDENTITY_INVALID")
        tensors = [self._get(role, str(scene), str(view))
                   for scene, view in zip(scenes, views, strict=True)]
        return torch.stack(tensors).to(device, non_blocking=False)

    def stats(self) -> dict[str, int | str]:
        return {"cache_id": self.cache_id, "hits": self.hits, "misses": self.misses,
                "evictions": self.evictions, "resident_entries": len(self.memory),
                "resident_bytes": self.memory_bytes}
