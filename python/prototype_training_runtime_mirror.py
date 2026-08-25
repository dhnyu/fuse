#!/usr/bin/env python3
"""Prepare the execution-only SSD archive mirror used by formal I21 training."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path


MARKER_NAME = "READY.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def authoritative_archives(source_root: Path) -> list[Path]:
    source_root = source_root.resolve()
    files = sorted(
        path for path in (source_root / "branches").rglob("*")
        if path.is_file() and path.suffix in {".tar", ".idx"}
    )
    if not files:
        raise ValueError(f"authoritative serialization has no archives: {source_root}")
    return files


def _records(source_root: Path) -> list[dict[str, object]]:
    return [
        {
            "relative_path": str(path.relative_to(source_root)),
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for path in authoritative_archives(source_root)
    ]


def validate_runtime_mirror(source_root: Path, runtime_root: Path) -> dict[str, object] | None:
    source_root, runtime_root = source_root.resolve(), runtime_root.resolve()
    marker = runtime_root / MARKER_NAME
    if not marker.is_file():
        return None
    value = json.loads(marker.read_text())
    expected = _records(source_root)
    if value.get("status") != "READY" or value.get("files") != expected:
        return None
    for record in expected:
        mirror = runtime_root / str(record["relative_path"])
        if (
            not mirror.is_file()
            or mirror.stat().st_size != int(record["size_bytes"])
            or sha256_file(mirror) != record["sha256"]
        ):
            return None
    return value


def prepare_runtime_mirror(source_root: Path, runtime_root: Path) -> dict[str, object]:
    source_root, runtime_root = source_root.resolve(), runtime_root.resolve()
    if source_root == runtime_root:
        raise ValueError("runtime mirror must differ from authoritative serialization root")
    existing = validate_runtime_mirror(source_root, runtime_root)
    if existing is not None:
        return {**existing, "reuse": True}
    if runtime_root.exists():
        raise ValueError(f"incomplete or colliding runtime mirror: {runtime_root}")

    records = _records(source_root)
    runtime_root.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{runtime_root.name}.stage-", dir=runtime_root.parent))
    try:
        for record in records:
            source = source_root / str(record["relative_path"])
            destination = stage / str(record["relative_path"])
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            if (
                destination.stat().st_size != int(record["size_bytes"])
                or sha256_file(destination) != record["sha256"]
            ):
                raise ValueError(f"runtime archive copy mismatch: {destination}")
        value = {
            "schema_version": "1.0.0",
            "status": "READY",
            "scientific_identity": "excluded_execution_only",
            "source_root": str(source_root),
            "runtime_root": str(runtime_root),
            "file_count": len(records),
            "total_bytes": sum(int(record["size_bytes"]) for record in records),
            "files": records,
        }
        marker = stage / MARKER_NAME
        marker.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")
        with marker.open("rb") as stream:
            os.fsync(stream.fileno())
        os.rename(stage, runtime_root)
        validated = validate_runtime_mirror(source_root, runtime_root)
        if validated is None:
            raise ValueError("activated runtime mirror failed validation")
        return {**validated, "reuse": False}
    except Exception:
        if stage.exists():
            shutil.rmtree(stage)
        raise
