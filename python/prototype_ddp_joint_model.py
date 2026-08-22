"""Rank-independent keyed dropout wrapper for the accepted joint model."""

from __future__ import annotations

import contextlib
import contextvars
import hashlib
from typing import Any, Iterator

import torch
from torch import nn

from prototype_joint_model import JointForward, JointPrototypeModel


_KEY_CONTEXT: contextvars.ContextVar[dict[str, torch.Tensor] | None] = contextvars.ContextVar("fuse_dropout_keys", default=None)


def stable_seed(*values: Any) -> int:
    return int.from_bytes(hashlib.sha256("|".join(map(str, values)).encode()).digest()[:8], "big") & ((1 << 63) - 1)


class KeyedDropout(nn.Module):
    def __init__(self, probability: float, module_path: str, scope: str) -> None:
        super().__init__()
        self.probability = float(probability)
        self.module_path = module_path
        self.scope = scope
        self.module_seed = stable_seed("dropout_module", module_path)

    def forward(self, value: torch.Tensor) -> torch.Tensor:
        if not self.training or self.probability == 0.0 or value.numel() == 0:
            return value
        context = _KEY_CONTEXT.get()
        if context is None or self.scope not in context:
            raise RuntimeError(f"keyed dropout context missing: {self.module_path}:{self.scope}")
        seeds = context[self.scope]
        if value.shape[0] != seeds.numel():
            raise RuntimeError(f"keyed dropout row mismatch: {self.module_path}:{value.shape[0]}!={seeds.numel()}")
        flat = value.reshape(value.shape[0], -1)
        row = seeds.to(device=value.device, dtype=torch.int64)[:, None]
        column = torch.arange(flat.shape[1], device=value.device, dtype=torch.int64)[None, :]
        mixed = row ^ torch.tensor(self.module_seed, device=value.device, dtype=torch.int64)
        mixed = mixed + column * 6364136223846793005 + 1442695040888963407
        mixed = mixed ^ (mixed >> 21); mixed = mixed ^ (mixed << 37); mixed = mixed ^ (mixed >> 4)
        positive = torch.bitwise_and(mixed, torch.tensor((1 << 63) - 1, device=value.device, dtype=torch.int64))
        uniform = positive.to(torch.float64) / float(1 << 63)
        mask = (uniform >= self.probability).to(value.dtype)
        return (flat * mask / (1.0 - self.probability)).reshape_as(value)


def dropout_scope(module_path: str) -> str:
    if module_path.startswith(("building_numerical", "building_fusion")): return "building"
    if module_path.startswith("road_fusion"): return "road"
    if module_path.startswith("poi_fusion"): return "poi"
    if module_path.startswith(("landcover_projection", "dem_projection", "scene_fusion")): return "scene"
    return "entity"


def install_keyed_dropout(module: nn.Module) -> None:
    replacements = [(name, child) for name, child in module.named_modules() if isinstance(child, nn.Dropout)]
    for path, child in replacements:
        parent_path, _, leaf = path.rpartition(".")
        parent = module.get_submodule(parent_path) if parent_path else module
        replacement = KeyedDropout(float(child.p), path, dropout_scope(path))
        if isinstance(parent, nn.Sequential) and leaf.isdigit(): parent[int(leaf)] = replacement
        else: setattr(parent, leaf, replacement)


def dropout_keys(batch: dict[str, Any], seed: int, epoch: int, view_id: int) -> dict[str, torch.Tensor]:
    entity_type = batch["entities"]["entity_type"].detach().cpu()
    scene_ptr = batch["scene_ptr"].detach().cpu().tolist()
    local = batch["entity_local_index"].detach().cpu().tolist()
    entity_values = []
    for scene_index, scene_id in enumerate(batch["scene_ids"]):
        entity_values.extend(stable_seed(seed, epoch, scene_id, view_id, "dropout", local[row])
                             for row in range(scene_ptr[scene_index], scene_ptr[scene_index + 1]))
    entity = torch.tensor(entity_values, dtype=torch.int64)
    return {
        "entity": entity,
        "building": entity[entity_type == 0],
        "road": entity[entity_type == 1],
        "poi": entity[entity_type == 2],
        "scene": torch.tensor([stable_seed(seed, epoch, scene_id, view_id, "dropout_scene") for scene_id in batch["scene_ids"]], dtype=torch.int64),
    }


@contextlib.contextmanager
def keyed_dropout_context(keys: dict[str, torch.Tensor]) -> Iterator[None]:
    token = _KEY_CONTEXT.set(keys)
    try: yield
    finally: _KEY_CONTEXT.reset(token)


class DistributedJointPrototypeModel(JointPrototypeModel):
    def __init__(self, encoder_config: dict[str, Any], joint_config: dict[str, Any]) -> None:
        super().__init__(encoder_config, joint_config)
        install_keyed_dropout(self.online)
        install_keyed_dropout(self.target)

    def forward(self, batch: dict[str, Any], geometry_features: tuple[torch.Tensor, torch.Tensor],
                assignments: torch.Tensor, seed: int, epoch: int, view_id: int) -> JointForward:
        with keyed_dropout_context(dropout_keys(batch, seed, epoch, view_id)):
            return super().forward_online(batch, geometry_features, assignments)
