"""Canonical source registry and digest for formal S09 runtime provenance."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from artifact_protocol import canonical_sha256, sha256_file


REGISTRY = "config/s09_runtime_provenance.yml"


class RuntimeProvenanceError(RuntimeError):
    """The registered formal runtime implementation is incomplete or ambiguous."""


def _registered_paths(root: Path, value: dict[str, Any], key: str) -> tuple[Path, ...]:
    relative = value.get(key)
    if (not isinstance(relative, list) or not relative
            or any(not isinstance(path, str) or not path for path in relative)
            or len(relative) != len(set(relative))):
        raise RuntimeProvenanceError("S09_RUNTIME_SOURCE_REGISTRY_INVALID")
    paths = tuple((root / path).resolve() for path in relative)
    if any(root not in path.parents or not path.is_file() for path in paths):
        raise RuntimeProvenanceError("S09_RUNTIME_SOURCE_MISSING")
    return paths


def runtime_source_paths(root: str | Path) -> tuple[Path, ...]:
    root = Path(root).resolve()
    value = yaml.safe_load((root / REGISTRY).read_text(encoding="utf-8"))
    if value.get("schema_version") != "1.0.0":
        raise RuntimeProvenanceError("S09_RUNTIME_PROVENANCE_SCHEMA_INVALID")
    return _registered_paths(root, value, "runtime_sources")


def runtime_implementation_provenance(root: str | Path) -> dict[str, Any]:
    root = Path(root).resolve()
    paths = runtime_source_paths(root)
    hashes = {path.relative_to(root).as_posix(): sha256_file(path) for path in paths}
    registry = yaml.safe_load((root / REGISTRY).read_text(encoding="utf-8"))
    authority_paths = _registered_paths(root, registry, "authority_publication_sources")
    authority_hashes = {
        path.relative_to(root).as_posix(): sha256_file(path) for path in authority_paths
    }
    return {
        "schema_version": "1.0.0",
        "registry": REGISTRY,
        "runtime_sources": list(hashes),
        "source_hashes": hashes,
        "implementation_sha256": canonical_sha256(hashes),
        "authority_source_hashes": authority_hashes,
        "authority_provenance_sha256": canonical_sha256(authority_hashes),
    }
