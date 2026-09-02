"""Read-only logical projection of the accepted P9 prepared-view cache."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

import torch


class PreparedCacheError(RuntimeError):
    """The immutable prepared cache cannot satisfy the requested profile."""


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
