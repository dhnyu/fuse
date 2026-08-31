"""Deterministic full-training logical groups for the official-grid population."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np


def _stable_order(scene_ids: list[str], seed: int, operation: str) -> list[str]:
    return sorted(
        scene_ids,
        key=lambda scene_id: (
            hashlib.sha256(f"{seed}|{operation}|{scene_id}".encode()).hexdigest(),
            scene_id,
        ),
    )


@dataclass(frozen=True)
class RotatingPaddingState:
    epoch: int
    permutation: tuple[str, ...]
    padding_scene_ids: tuple[str, ...]
    logical_group_position: int = 0


def rotating_padding_state(
    scene_ids: list[str], seed: int, epoch: int, global_batch: int = 32
) -> RotatingPaddingState:
    if epoch < 0 or global_batch < 1 or len(scene_ids) < 1:
        raise ValueError("invalid sampler arguments")
    if len(set(scene_ids)) != len(scene_ids):
        raise ValueError("scene IDs must be unique")
    canonical = sorted(scene_ids)
    rng_seed = int.from_bytes(
        hashlib.sha256(f"{seed}|epoch-permutation|{epoch}".encode()).digest()[:8], "big"
    )
    permutation = tuple(np.random.Generator(np.random.PCG64(rng_seed)).permutation(canonical).tolist())
    padding_count = (-len(canonical)) % global_batch
    rotation = _stable_order(canonical, seed, "rotating-padding")
    # Padding completes the final collective. Excluding its remainder is
    # required because current-batch positive lookup permits exactly one copy
    # of each base scene in a global batch.
    remainder = set(permutation[-(len(canonical) % global_batch):]) if padding_count else set()
    candidates = tuple(scene_id for scene_id in rotation if scene_id not in remainder)
    if len(candidates) < padding_count:
        raise ValueError("insufficient collision-free padding candidates")
    start = (epoch * padding_count) % len(candidates) if padding_count else 0
    padding = tuple(candidates[(start + offset) % len(candidates)] for offset in range(padding_count))
    return RotatingPaddingState(epoch, permutation, padding)


def logical_groups(state: RotatingPaddingState, global_batch: int = 32) -> list[tuple[str, ...]]:
    consumed = state.permutation + state.padding_scene_ids
    if len(consumed) % global_batch:
        raise ValueError("padded epoch is not divisible by the global batch")
    return [tuple(consumed[start : start + global_batch]) for start in range(0, len(consumed), global_batch)]


def negative_candidate_mask(scene_ids: list[str]) -> np.ndarray:
    values = np.asarray(scene_ids, dtype=object)
    return values[:, None] != values[None, :]
