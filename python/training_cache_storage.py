"""Verified physical replicas of immutable S09 inputs; no scientific publication.

Dissertation chapter 4: fixed prepared views remain byte-identical. Placement is
operational only and never changes the accepted cache/plan/authority payload.
"""
from __future__ import annotations

import fcntl
import json
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Mapping

from artifact_protocol import canonical_json_bytes, canonical_sha256, sha256_file

READ_ROOT_ENV = "FUSE_S09_CACHE_READ_ROOT"
RECEIPT = "replica_verified.json"


class CacheStorageError(RuntimeError):
    pass


def plain_root(path: str | Path) -> Path:
    root = Path(path).expanduser().absolute()
    if root.resolve() != root or any(p.is_symlink() for p in (root, *root.parents)):
        raise CacheStorageError("CACHE_REPLICA_SYMLINK_FORBIDDEN")
    return root


def member(root: Path, relative: str) -> Path:
    p = PurePosixPath(relative)
    if p.is_absolute() or not p.parts or any(x in {"..", "."} for x in p.parts) or str(p) != relative:
        raise CacheStorageError("CACHE_REPLICA_PATH_INVALID")
    return plain_root(root / relative)


@dataclass(frozen=True)
class CacheInventory:
    cache_id: str
    acceptance_id: str
    files: dict[str, dict]

    def binding(self) -> dict:
        return {"schema_version": "1.0.0", "cache_id": self.cache_id,
                "acceptance_id": self.acceptance_id, "file_count": len(self.files),
                "total_bytes": sum(row["size"] for row in self.files.values()),
                "inventory_sha256": canonical_sha256(self.files)}


def cache_inventory(canonical_root: str | Path) -> CacheInventory:
    """Only accepted manifests are read from HDD, never enumerate generations."""
    root = plain_root(canonical_root)
    def document(name):
        return json.loads(member(root, name).read_text())
    acceptance = document("acceptance.json")
    production = document("production_cache_manifest.json")
    ah = canonical_sha256({k: v for k, v in acceptance.items() if k not in {"acceptance_id", "content_sha256"}})
    ph = canonical_sha256({k: v for k, v in production.items() if k not in {"cache_id", "content_sha256"}})
    if (acceptance.get("status") != "PASS" or production.get("status") != "PASS"
            or acceptance.get("cache_id") != root.name or production.get("cache_id") != root.name
            or acceptance.get("content_sha256") != ah or acceptance.get("acceptance_id") != "s09ca_" + ah[:24]
            or production.get("content_sha256") != ph
            or acceptance.get("manifest_sha256") != sha256_file(root / "production_cache_manifest.json")
            or acceptance.get("parents") != production.get("parents")
            or acceptance.get("entry_count") != production.get("entry_count")
            or production.get("entry_count") != len(production["entries"])
            or production.get("plan_sha256") != sha256_file(root / "canonical_cache_plan.json")):
        raise CacheStorageError("CACHE_REPLICA_ACCEPTANCE_INVALID")
    files = {}
    def add(name, size, digest):
        member(root, name)
        if name in files or type(size) is not int or size < 0 or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise CacheStorageError("CACHE_REPLICA_INVENTORY_INVALID")
        files[name] = {"size": size, "sha256": digest}
    for name in ("acceptance.json", "production_cache_manifest.json", "canonical_cache_plan.json",
                 "geometry/geometry_cache_manifest.json", "geometry/COMPLETE.json", "ds/ds_cache_manifest.json"):
        path = member(root, name)
        add(name, path.stat().st_size, sha256_file(path))
    indices = []
    for row in production["entries"]:
        index = row["global_index"]
        if type(index) is not int or index < 0:
            raise CacheStorageError("CACHE_REPLICA_INDEX_INVALID")
        indices.append(index)
        add(f"prepared/{index:06d}.pt", row["prepared_size"], row["prepared_sha256"])
    if sorted(indices) != list(range(len(indices))):
        raise CacheStorageError("CACHE_REPLICA_INDEX_INVALID")
    for kind, name in (("geometry", "geometry_cache_manifest.json"), ("ds", "ds_cache_manifest.json")):
        manifest = document(f"{kind}/{name}")
        binding = production[kind]
        if (manifest.get("status") != "PASS" or binding["cache_id"] != manifest["cache_id"]
                or binding["manifest_sha256"] != files[f"{kind}/{name}"]["sha256"]
                or manifest["entry_count"] != len(manifest["entries"])):
            raise CacheStorageError("CACHE_REPLICA_CHILD_BINDING_INVALID")
        for row in manifest["entries"]:
            add(f"{kind}/{row['relative_path']}", row["payload_size_bytes"], row["payload_sha256"])
    return CacheInventory(root.name, acceptance["acceptance_id"], files)


def verify_file(path: Path, expected: dict, *, full: bool) -> None:
    if not path.is_file() or path.stat().st_size != expected["size"]:
        raise CacheStorageError(f"CACHE_REPLICA_FILE_INVALID:{path}")
    if full and sha256_file(path) != expected["sha256"]:
        raise CacheStorageError(f"CACHE_REPLICA_CHECKSUM_INVALID:{path}")


def verify_replica(canonical_root: str | Path, replica_root: str | Path, *, full: bool = False) -> dict:
    inventory = cache_inventory(canonical_root)
    root = plain_root(replica_root)
    if root.name != inventory.cache_id or root == plain_root(canonical_root):
        raise CacheStorageError("CACHE_REPLICA_ROOT_INVALID")
    receipt = json.loads(member(root, RECEIPT).read_text())
    expected = {**inventory.binding(), "status": "VERIFIED", "verification": "ALL_FILE_SHA256"}
    if receipt != expected:
        raise CacheStorageError("CACHE_REPLICA_RECEIPT_INVALID")
    for name, row in inventory.files.items():
        verify_file(member(root, name), row, full=full or name.endswith(".json"))
    return {**expected, "canonical_root": str(plain_root(canonical_root)), "read_root": str(root)}


def resolve_cache_read_root(canonical_root: str | Path, environment: Mapping[str, str] | None = None) -> Path:
    environment = os.environ if environment is None else environment
    canonical = plain_root(canonical_root)
    if READ_ROOT_ENV not in environment:
        return canonical
    if not environment[READ_ROOT_ENV].strip():
        raise CacheStorageError("CACHE_REPLICA_ROOT_EMPTY")
    evidence = verify_replica(canonical, environment[READ_ROOT_ENV])
    return Path(evidence["read_root"])


def copy_replica(canonical_root: str | Path, replica_root: str | Path, progress=print) -> dict:
    """Sequential resumable copy. Existing files are verified, never overwritten."""
    source, destination = plain_root(canonical_root), plain_root(replica_root)
    inventory = cache_inventory(source)
    if (destination.name != source.name or destination == source
            or source in destination.parents or destination in source.parents):
        raise CacheStorageError("CACHE_REPLICA_ROOT_INVALID")
    destination.mkdir(parents=True, exist_ok=True)
    with member(destination, ".replica_copy.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if member(destination, RECEIPT).exists():
            return verify_replica(source, destination, full=True)
        remaining = sum(v["size"] for k, v in inventory.files.items() if not member(destination, k).exists())
        if shutil.disk_usage(destination).free < remaining + 1024**3:
            raise CacheStorageError("CACHE_REPLICA_INSUFFICIENT_SPACE")
        for number, (name, row) in enumerate(inventory.files.items(), 1):
            src, dst = member(source, name), member(destination, name)
            dst.parent.mkdir(parents=True, exist_ok=True)
            if not dst.exists():
                temporary = member(destination, name + ".copying")
                # A previous interrupted partial is evidence, not safe to replace.
                with src.open("rb") as incoming, temporary.open("xb") as outgoing:
                    shutil.copyfileobj(incoming, outgoing, 4 * 1024**2)
                    outgoing.flush(); os.fsync(outgoing.fileno())
                verify_file(temporary, row, full=True)
                shutil.copystat(src, temporary)
                os.link(temporary, dst)
                temporary.unlink()
            else:
                verify_file(dst, row, full=True)
            if number % 1000 == 0:
                progress(json.dumps({"verified_files": number, "total_files": len(inventory.files)}))
        if cache_inventory(source).binding() != inventory.binding():
            raise CacheStorageError("CACHE_REPLICA_SOURCE_CHANGED")
        evidence = {**inventory.binding(), "status": "VERIFIED", "verification": "ALL_FILE_SHA256"}
        with member(destination, RECEIPT).open("xb") as stream:
            stream.write(canonical_json_bytes(evidence)); stream.flush(); os.fsync(stream.fileno())
        return evidence
