"""Read-only recovery of P9 checkpoint candidates.

This module deliberately operates on a completed formal-run directory.  It has
no training, DDP, CUDA, optimiser, or checkpoint-writing entry point.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import torch

from p9_formal_execution import candidate_is_better, validate_validation_event


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def validation_epoch_from_manifest(manifest: dict[str, Any]) -> int:
    """Map a resume cursor to the validation event which created its checkpoint."""
    progress = manifest.get("progress", {})
    resume_epoch = progress.get("epoch", manifest.get("epoch"))
    if not isinstance(resume_epoch, int) or resume_epoch < 2:
        raise ValueError("checkpoint manifest lacks a valid post-validation resume epoch")
    return resume_epoch - 1


def _lineage(state: dict[str, Any], expected: dict[str, str]) -> None:
    actual = state.get("lineage", {})
    for key, value in expected.items():
        if actual.get(key) != value:
            raise ValueError(f"LINEAGE_MISMATCH:{key}")


def audit_pairs(run_root: str | Path) -> dict[str, Any]:
    """Join validation events to atomic checkpoints using immutable state facts."""
    root = Path(run_root)
    result_path = root / "worker_result.json"
    if not result_path.exists():
        raise FileNotFoundError("missing immutable worker_result.json")
    result = json.loads(result_path.read_text())
    events = result.get("validation_trace", [])
    expected = {"authority_id": result.get("authority_id"), "reservation_id": result.get("reservation_id")}
    # Older worker results omit lineage; derive it from the immutable attempt state.
    attempt = json.loads((root / "attempt_state.json").read_text())
    expected = {"authority_id": attempt["authority_id"], "reservation_id": attempt["reservation_id"]}
    rows: list[dict[str, Any]] = []
    manifests = sorted((root / "checkpoints").glob("*/checkpoint_manifest.json"))
    by_epoch: dict[int, list[tuple[Path, dict[str, Any]]]] = {}
    for path in manifests:
        manifest = json.loads(path.read_text())
        try:
            epoch = validation_epoch_from_manifest(manifest)
        except ValueError:
            continue
        by_epoch.setdefault(epoch, []).append((path, manifest))
    for event in events:
        validate_validation_event(event)
        epoch = int(event["epoch"])
        matches = by_epoch.get(epoch, [])
        row: dict[str, Any] = {"validation_epoch": epoch, "validation": event, "classification": "EXACT_MATCH"}
        if len(matches) == 0:
            row["classification"] = "MISSING_CHECKPOINT"
        elif len(matches) != 1:
            row["classification"] = "MULTIPLE_CHECKPOINTS"
        else:
            path, manifest = matches[0]
            payload = path.parent / manifest.get("payload", {}).get("filename", "checkpoint.pt")
            if not payload.exists() or sha256_file(payload) != manifest.get("payload", {}).get("sha256"):
                row["classification"] = "CHECKSUM_MISMATCH"
            else:
                state = torch.load(payload, map_location="cpu", weights_only=False)
                try:
                    _lineage(state, expected)
                except ValueError as error:
                    row["classification"] = str(error).split(":", 1)[0]
                else:
                    if int(state.get("progress", {}).get("global_update", -1)) != int(manifest.get("global_update", -2)):
                        row["classification"] = "UPDATE_MISMATCH"
                    elif event not in state.get("validation_trace", []):
                        row["classification"] = "METRIC_MISMATCH"
            row.update({"checkpoint_manifest_path": str(path), "checkpoint_payload_path": str(payload),
                        "checkpoint_manifest_sha256": sha256_file(path),
                        "checkpoint_payload_sha256": sha256_file(payload) if payload.exists() else None,
                        "checkpoint_id": manifest.get("checkpoint_id"),
                        "resume_epoch": manifest.get("epoch"),
                        "global_update": manifest.get("global_update")})
        rows.append(row)
    classifications = [row["classification"] for row in rows]
    if len(rows) != 25 or any(value != "EXACT_MATCH" for value in classifications):
        raise ValueError("checkpoint recovery join is not exactly 25 EXACT_MATCH rows")
    candidates = [{**row["validation"], "checkpoint_id": row["checkpoint_id"],
                   "checkpoint_manifest_sha256": row["checkpoint_manifest_sha256"],
                   "checkpoint_payload_sha256": row["checkpoint_payload_sha256"],
                   "checkpoint_manifest_path": row["checkpoint_manifest_path"]} for row in rows]
    best: dict[str, Any] | None = None
    for candidate in candidates:
        if candidate_is_better(candidate, best):
            best = candidate
    return {"schema_version": "1.0.0", "run_root": str(root), "run_id": attempt["run_id"],
            "attempt_id": attempt["attempt_id"], "rows": rows, "candidates": candidates,
            "selected_checkpoint": best,
            "content_sha256": hashlib.sha256(canonical_json({"rows": rows, "selected_checkpoint": best})).hexdigest()}
