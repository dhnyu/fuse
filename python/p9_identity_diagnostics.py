"""Fail-closed evidence capture for formal scene-identity invariants.

This module deliberately records only identity metadata, checksums, and the
minimum failing rows. It never serializes embeddings or changes loss semantics.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

import torch


class SceneIdentityLookupError(ValueError):
    """A classified failure of the current-batch identity invariant."""

    def __init__(self, classification: str, message: str, bundle_path: str | None = None) -> None:
        super().__init__(f"{classification}: {message}")
        self.classification = classification
        self.bundle_path = bundle_path


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"not JSON serializable: {type(value)!r}")


def _digest_tensor(value: torch.Tensor) -> str:
    materialized = value.detach().cpu().contiguous()
    return hashlib.sha256(materialized.numpy().tobytes()).hexdigest()


def _tensor_metadata(value: torch.Tensor) -> dict[str, Any]:
    return {
        "shape": list(value.shape), "dtype": str(value.dtype), "device": str(value.device),
        "sha256": _digest_tensor(value),
    }


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_name(f".{path.name}.{os.getpid()}.staging")
    staging.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=_json_default))
    os.replace(staging, path)


def _rng_digests() -> dict[str, str]:
    import numpy as np
    import random

    result = {
        "python": hashlib.sha256(repr(random.getstate()).encode()).hexdigest(),
        "numpy": hashlib.sha256(repr(np.random.get_state()).encode()).hexdigest(),
        "torch_cpu": _digest_tensor(torch.get_rng_state()),
    }
    if torch.cuda.is_available():
        result["torch_cuda"] = [
            _digest_tensor(torch.cuda.get_rng_state(index)) for index in range(torch.cuda.device_count())
        ]
    return result


def _identity_rows(ids: torch.Tensor) -> list[int]:
    return [int(item) for item in ids.detach().cpu().tolist()]


def capture_lookup_failure(
    *,
    context: dict[str, Any] | None,
    classification: str,
    local_ids: torch.Tensor,
    global_ids: torch.Tensor,
    global_embedding_rows: int,
    first_failing_id: int | None,
    lookup_positions: list[int],
    lookup_multiplicity: int,
    queue: dict[str, Any],
) -> str | None:
    """Write one atomic rank record without replacing the scientific error."""
    if not context or not context.get("diagnostic_root"):
        return None
    try:
        rank = int(context.get("rank", -1))
        payload = {
            "schema_version": "1.0.0", "artifact_type": "p9_scene_identity_failure_rank_record",
            "classification": classification, "captured_unix": time.time(),
            "authority_id": context.get("authority_id"), "reservation_id": context.get("reservation_id"),
            "attempt_id": context.get("attempt_id"), "run_id": context.get("run_id"),
            "runtime_tree_sha256": context.get("runtime_tree_sha256"),
            "actual_launch_commit": context.get("actual_launch_commit"),
            "hostname": context.get("hostname"), "world_size": context.get("world_size"),
            "rank": rank, "local_rank": context.get("local_rank", rank),
            "epoch": context.get("epoch"), "batch_index": context.get("batch_index"),
            "intended_global_update": context.get("intended_global_update"),
            "sampler": context.get("sampler", {}),
            "identity_domains": context.get("identity_domains", {}),
            "local_scene_ids": context.get("local_scene_ids", []),
            "gathered_scene_ids": _identity_rows(global_ids),
            "requested_lookup_ids": _identity_rows(local_ids),
            "first_failing_id": first_failing_id,
            "lookup_multiplicity": int(lookup_multiplicity),
            "matching_positions": [int(value) for value in lookup_positions],
            "global_embedding_rows": int(global_embedding_rows),
            "local_ids": _tensor_metadata(local_ids), "global_ids": _tensor_metadata(global_ids),
            "queue": {
                "count": int(queue.get("valid_count", 0)), "pointer": int(queue.get("pointer", 0)),
                "enqueue_count": int(queue.get("enqueue_count", 0)),
                "scene_ids": _tensor_metadata(queue["scene_ids"][:int(queue.get("valid_count", 0))]),
                "values": _tensor_metadata(queue["values"][:int(queue.get("valid_count", 0))]),
            },
            "rng_sha256": _rng_digests(),
            "collective_sequence": context.get("collective_sequence"),
        }
        destination = Path(context["diagnostic_root"]) / f"rank-{rank}.json"
        _atomic_json(destination, payload)
        return str(destination)
    except BaseException as error:
        # The invariant exception remains primary. The caller receives this note
        # through the classified message rather than losing the original failure.
        return f"DIAGNOSTIC_PERSISTENCE_FAILED:{type(error).__name__}"


def validate_current_batch_lookup(
    local_ids: torch.Tensor,
    global_ids: torch.Tensor,
    *,
    global_embedding_rows: int,
    queue: dict[str, Any],
    context: dict[str, Any] | None = None,
) -> None:
    """Preserve the one-positive-per-current-batch invariant with evidence."""
    classification: str | None = None
    first: int | None = None
    positions: list[int] = []
    multiplicity = 0
    if global_ids.ndim != 1 or local_ids.ndim != 1:
        classification = "ID_DOMAIN_MISMATCH"
    elif global_ids.shape[0] != int(global_embedding_rows):
        classification = "GATHER_LENGTH_MISMATCH"
    elif queue["values"].shape[0] != queue["scene_ids"].shape[0] or queue["scene_ids"].shape[0] != queue["centers"].shape[0]:
        classification = "QUEUE_ALIGNMENT_MISMATCH"
    else:
        for value in local_ids:
            found = torch.nonzero(global_ids == value).flatten()
            if found.numel() != 1:
                first, positions, multiplicity = int(value), found.detach().cpu().tolist(), int(found.numel())
                classification = "CURRENT_BATCH_ID_MISSING" if multiplicity == 0 else "CURRENT_BATCH_ID_DUPLICATE"
                break
    if classification is None:
        return
    bundle = capture_lookup_failure(
        context=context, classification=classification, local_ids=local_ids, global_ids=global_ids,
        global_embedding_rows=global_embedding_rows, first_failing_id=first,
        lookup_positions=positions, lookup_multiplicity=multiplicity, queue=queue,
    )
    suffix = "" if not bundle else f" diagnostic={bundle}"
    raise SceneIdentityLookupError(classification, "global scene identity lookup mismatch" + suffix, bundle)


def assemble_rank_manifest(root: str | Path, world_size: int) -> dict[str, Any]:
    """Assemble a manifest after rank records have been atomically persisted."""
    root = Path(root)
    rows = []
    for rank in range(world_size):
        path = root / f"rank-{rank}.json"
        if path.is_file():
            rows.append(json.loads(path.read_text()))
    payload = {
        "schema_version": "1.0.0", "artifact_type": "p9_scene_identity_failure_manifest",
        "expected_world_size": int(world_size), "available_rank_count": len(rows),
        "completeness": "COMPLETE" if len(rows) == world_size else "PARTIAL",
        "rank_records": [{"rank": row["rank"], "classification": row["classification"]} for row in rows],
    }
    _atomic_json(root / "manifest.json", payload)
    return payload
