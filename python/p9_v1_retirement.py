"""Fail-closed P9 v1 retirement guard and immutable evidence inventory."""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from typing import Any, NoReturn

from artifact_protocol import canonical_json_bytes, canonical_sha256, parse_canonical_json
from training_ledger import fsync_directory, write_all
from training_schema import validate_instance


RETIREMENT_ERROR_CODE = "P9_V1_EXECUTION_RETIRED"
RETIREMENT_MESSAGE = (
    "P9 v1 is historical/read-only; execution is retired; "
    "use a canonical p9accv2 acceptance through resolve_accepted_checkpoint()."
)
RETIREMENT_IMPLEMENTATION_VERSION = "p9-v1-retirement-v2"
CANONICAL_ACCEPTANCE_ID = "p9accv2_d93b01ef13c3f26a22287ce7"
CANONICAL_CHECKPOINT_ID = "p9ck_42f7957d2ea998ac9e8ff705"

FORMAL_AUTHORITY_ROOT = Path("/mnt/hdd002/dhnyu/fusedata/models/reduced/formal_training/authorization")
RECOVERY_AUTHORITY_ROOT = Path("/mnt/hdd002/dhnyu/fusedata/models/reduced/formal_training/recovery_authorization")
TARGETS_ROOT = Path("/mnt/hdd002/dhnyu/fusedata/targets")
CANONICAL_RETIREMENT_ROOT = Path("/mnt/hdd002/dhnyu/fusedata/models/reduced/p9_v2/canonical/retirement")

FORMAL_AUTHORITY_IDS = (
    "p9a_2c67a3971b785f7049cb3d65", "p9a_3699e8b11a062cebe82148ae",
    "p9a_3ca9d116cc20b41213f37412", "p9a_6a4cbc93682d3110e3cd93b6",
    "p9a_7846ee1db3ec9f05cecdbff8", "p9a_9d6f0554553ac43371b47efd",
    "p9a_b0c50c956d84a1c3664d7934", "p9a_b295be97717efbd2305dd5a6",
    "p9a_c16721ffbce259df3f723cdd",
)
RECOVERY_AUTHORITY_IDS = (
    "p9ra_2b5e0dc9eebb81c028fefedf", "p9ra_7de9e3bb263c254eb070c8ef",
    "p9ra_8e32bacc3917acd1a91921c4",
)
HISTORICAL_STORE_NAMES = (
    "fuse-p9-formal", "fuse-p9-formal-p9gen_acb72f05336e09451b4ac458",
    "fuse-p9-formal-p9gen_batchuniq_20260831", "fuse-p9-recovery-20260831",
    "fuse-p9-recovery-complete-20260831", "fuse-p9-recovery-lockstate-20260831",
)
RETIRED_ENTRY_POINTS = (
    "_targets_p9_formal.R",
    "_targets_p9_recovery.R",
    "scripts/p9_checkpoint_recovery_authorization.py",
    "scripts/p9_formal_authorization.py",
    "retired:p9_formal_training",
    "retired:p9_recovery_execution",
    "retired:p9_campaign_execution",
)
PRESERVED_READ_ONLY_INTERFACES = (
    "checkpoint_resolution.resolve_accepted_checkpoint",
)
PROHIBITED_INTERFACES = (
    "create_v1_acceptance", "create_v1_attempt", "create_v1_authority",
    "create_v1_operation", "create_v1_reservation", "latest_checkpoint",
    "manual_checkpoint_path", "publish_v1_cache", "recover_v1_training",
    "resolve_v1_checkpoint", "resume_v1_training", "train_v1",
)


class P9V1RetiredError(RuntimeError):
    """Stable rejection for every retired P9 v1 execution interface."""


def reject_v1_execution(interface: str) -> NoReturn:
    raise P9V1RetiredError(f"{RETIREMENT_ERROR_CODE}: {interface}: {RETIREMENT_MESSAGE}")


def retire_v1_cli(interface: str) -> NoReturn:
    import sys
    sys.stderr.write(f"{RETIREMENT_ERROR_CODE}: {interface}: {RETIREMENT_MESSAGE}\n")
    raise SystemExit(78)


def _file_sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _tree_inventory(root: Path) -> tuple[list[dict[str, Any]], str]:
    if not root.is_dir():
        raise FileNotFoundError(root)
    entries: list[dict[str, Any]] = []
    for directory, names, filenames in os.walk(root, followlinks=False):
        base = Path(directory)
        names.sort(); filenames.sort()
        for name in [*names, *filenames]:
            path = base / name
            if path.is_symlink():
                entries.append({
                    "path": path.relative_to(root).as_posix(), "kind": "symlink",
                    "target": os.readlink(path),
                })
            elif path.is_file():
                entries.append({
                    "path": path.relative_to(root).as_posix(), "kind": "file",
                    "size_bytes": path.stat().st_size, "sha256": _file_sha256(path),
                })
    entries.sort(key=lambda item: item["path"])
    return entries, canonical_sha256(entries)


def inspect_retirement_sources(repository_root: str | Path | None = None) -> dict[str, Any]:
    """Read immutable historical evidence without depending on executable source files."""
    formal = []
    for identity in FORMAL_AUTHORITY_IDS:
        entries, digest = _tree_inventory(FORMAL_AUTHORITY_ROOT / identity)
        formal.append({"identity": identity, "status": "RETIRED_INELIGIBLE", "inventory_sha256": digest, "file_count": len(entries)})
    recovery = []
    for identity in RECOVERY_AUTHORITY_IDS:
        entries, digest = _tree_inventory(RECOVERY_AUTHORITY_ROOT / identity)
        recovery.append({"identity": identity, "status": "RETIRED_INELIGIBLE", "inventory_sha256": digest, "file_count": len(entries)})
    stores = []
    for name in HISTORICAL_STORE_NAMES:
        entries, digest = _tree_inventory(TARGETS_ROOT / name)
        stores.append({"name": name, "status": "HISTORICAL_READ_ONLY", "inventory_sha256": digest, "entry_count": len(entries)})
    return {
        "formal_authorities": formal, "recovery_authorities": recovery,
        "historical_stores": stores,
    }


def build_retirement_manifest(repository_root: str | Path) -> dict[str, Any]:
    evidence = inspect_retirement_sources(repository_root)
    preimage = {
        "schema_version": "1.0.0", "artifact_type": "p9_v1_retirement_manifest",
        "implementation_version": RETIREMENT_IMPLEMENTATION_VERSION,
        "status": "V1_RETIRED_READ_ONLY",
        "authorization_basis": "CURRENT_LINEAGE_SOURCE_CLEANUP",
        **evidence,
        "retired_entry_points": list(RETIRED_ENTRY_POINTS),
        "prohibited_interfaces": list(PROHIBITED_INTERFACES),
        "preserved_read_only_interfaces": list(PRESERVED_READ_ONLY_INTERFACES),
        "replacement": {
            "acceptance_id": CANONICAL_ACCEPTANCE_ID,
            "checkpoint_id": CANONICAL_CHECKPOINT_ID,
            "resolver_contract": "resolve_accepted_checkpoint(acceptance_identity)",
        },
        "retirement_publication_identity": "current-lineage-p9-v1-retirement-v2",
    }
    digest = canonical_sha256(preimage)
    manifest = {**preimage, "retirement_id": f"p9ret_{digest[:24]}", "content_sha256": digest}
    validate_instance("v1_retirement_manifest", manifest)
    return manifest


def publish_retirement_manifest(manifest: dict[str, Any], root: str | Path = CANONICAL_RETIREMENT_ROOT) -> Path:
    """Atomically create or validate the sole immutable V2-I manifest."""

    validate_instance("v1_retirement_manifest", manifest)
    preimage = {key: value for key, value in manifest.items() if key not in {"retirement_id", "content_sha256"}}
    digest = canonical_sha256(preimage)
    if manifest["content_sha256"] != digest or manifest["retirement_id"] != f"p9ret_{digest[:24]}":
        raise ValueError("retirement manifest identity/hash mismatch")
    publication_root = Path(root); publication_root.mkdir(parents=True, exist_ok=True)
    staging = publication_root / ".staging"; staging.mkdir(exist_ok=True)
    final = publication_root / manifest["retirement_id"] / "retirement_manifest.json"
    raw = canonical_json_bytes(manifest)
    if final.exists():
        if parse_canonical_json(final.read_bytes()) != manifest:
            raise FileExistsError("retirement manifest collision")
        return final
    stage = Path(tempfile.mkdtemp(prefix=f".{manifest['retirement_id']}.", dir=staging))
    try:
        target = stage / "retirement_manifest.json"
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o640)
        try:
            write_all(descriptor, raw); os.fsync(descriptor)
        finally:
            os.close(descriptor)
        if parse_canonical_json(target.read_bytes()) != manifest:
            raise ValueError("staged retirement manifest differs")
        try:
            os.rename(stage, final.parent)
        except FileExistsError:
            if not final.is_file() or parse_canonical_json(final.read_bytes()) != manifest:
                raise FileExistsError("retirement manifest collision")
        fsync_directory(publication_root)
    finally:
        if stage.exists():
            import shutil
            shutil.rmtree(stage)
    if parse_canonical_json(final.read_bytes()) != manifest:
        raise ValueError("published retirement manifest differs")
    return final
