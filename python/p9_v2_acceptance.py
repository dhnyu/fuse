"""Atomic P9 v2 acceptance publication and accepted-checkpoint resolution."""

from __future__ import annotations

import fcntl
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from p9_v2_bundle import COMMIT_PATH as BUNDLE_COMMIT_PATH
from p9_v2_bundle import validate_run_bundle
from p9_v2_canonical import (
    CanonicalJSONError,
    canonical_json_bytes,
    canonical_sha256,
    parse_canonical_json,
    sha256_bytes,
)
from p9_v2_finalization import validate_finalization_result
from p9_v2_ledger import fsync_directory, write_all
from p9_v2_schema import P9V2SchemaError, SCHEMA_VERSION, validate_instance


ACCEPTANCE_ID_PATTERN = re.compile(r"^p9accv2_[0-9a-f]{24}$")
ACCEPTANCE_PATH = "acceptance.json"
FINALIZATION_PATH = "finalization_result.json"
ACCEPTANCE_COMMIT_PATH = "commit/acceptance_commit_manifest.json"


class AcceptanceError(ValueError):
    """A stable acceptance publication or resolution rejection."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


@dataclass(frozen=True)
class AcceptancePublication:
    acceptance_id: str
    path: Path
    created: bool


@dataclass(frozen=True)
class AcceptanceValidationResult:
    valid: bool
    acceptance_id: str | None
    error_code: str | None = None
    message: str | None = None


@dataclass(frozen=True)
class AcceptedCheckpoint:
    acceptance_id: str
    run_bundle_id: str
    run_bundle_hash: str
    finalization_id: str
    finalization_result_hash: str
    checkpoint_id: str
    payload_locator: dict[str, Any]
    payload_sha256: str
    manifest_sha256: str
    completed_epoch: int
    resume_epoch: int
    optimizer_update: int
    validation_retrieval_loss: float
    mean_source_separation_margin: float
    stopping_summary: dict[str, Any]
    scientific_configuration: dict[str, Any]
    authority_id: str
    authority_hash: str
    provenance: dict[str, Any]


def _fail(code: str, message: str) -> None:
    raise AcceptanceError(code, message)


def _read_canonical(path: Path) -> Any:
    try:
        return parse_canonical_json(path.read_bytes())
    except (OSError, CanonicalJSONError) as error:
        _fail("MALFORMED_CANONICAL_JSON", f"cannot read {path.name}: {error}")


def _acceptance_preimage(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value for key, value in record.items()
        if key not in {"acceptance_id", "acceptance_content_sha256"}
    }


def _make_acceptance(
    finalization: Mapping[str, Any], manifest: Mapping[str, Any], authority_id: str, authority_hash: str
) -> dict[str, Any]:
    if manifest["bindings"]["authority_id"] != authority_id or manifest["bindings"]["authority_hash"] != authority_hash:
        _fail("AUTHORITY_MISMATCH", "publication authority differs from bundle")
    selected = finalization["selected_checkpoint"]
    preimage = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "p9_v2_acceptance",
        "authority_id": authority_id,
        "authority_hash": authority_hash,
        "run_bundle_id": finalization["run_bundle_id"],
        "run_bundle_hash": finalization["run_bundle_hash"],
        "finalization_id": finalization["finalization_id"],
        "finalization_result_hash": finalization["finalization_result_hash"],
        "checkpoint_id": selected["checkpoint_id"],
        "payload_sha256": selected["payload_sha256"],
        "manifest_sha256": selected["manifest_sha256"],
        "evaluation_consumption_count": 0,
    }
    content_hash = canonical_sha256(preimage)
    record = {
        **preimage,
        "acceptance_id": f"p9accv2_{content_hash[:24]}",
        "acceptance_content_sha256": content_hash,
    }
    validate_instance("acceptance", record)
    return record


def _write_file(path: Path, raw: bytes, fault_hook: Callable[[str], None] | None, *, partial_fault: bool = False) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
    try:
        if partial_fault:
            split = max(1, len(raw) // 2)
            write_all(fd, raw[:split])
            if fault_hook is not None:
                fault_hook("during_acceptance_metadata_write")
            write_all(fd, raw[split:])
        else:
            write_all(fd, raw)
        os.fsync(fd)
    finally:
        os.close(fd)


def _commit_manifest(acceptance_id: str, acceptance_raw: bytes, finalization_raw: bytes) -> dict[str, Any]:
    commit = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "p9_v2_acceptance_commit_manifest",
        "acceptance_id": acceptance_id,
        "status": "COMMITTED",
        "acceptance_path": ACCEPTANCE_PATH,
        "acceptance_sha256": sha256_bytes(acceptance_raw),
        "acceptance_size_bytes": len(acceptance_raw),
        "finalization_result_path": FINALIZATION_PATH,
        "finalization_result_sha256": sha256_bytes(finalization_raw),
        "finalization_result_size_bytes": len(finalization_raw),
    }
    validate_instance("acceptance", commit)
    return commit


def validate_acceptance(
    acceptance_id: str,
    acceptance_root: str | Path,
    bundle_root: str | Path,
    locator_roots: Mapping[str, str | Path],
) -> AcceptanceValidationResult:
    """Validate the committed acceptance through its bundle and external artifacts."""

    try:
        if not isinstance(acceptance_id, str) or not ACCEPTANCE_ID_PATTERN.fullmatch(acceptance_id):
            _fail("INVALID_ACCEPTANCE_ID", "resolver requires a canonical acceptance identity")
        root = Path(acceptance_root) / acceptance_id
        commit_path = root / ACCEPTANCE_COMMIT_PATH
        if not commit_path.is_file():
            _fail("ACCEPTANCE_UNCOMMITTED", "acceptance commit manifest is absent")
        commit = _read_canonical(commit_path)
        record = _read_canonical(root / ACCEPTANCE_PATH)
        finalization = _read_canonical(root / FINALIZATION_PATH)
        actual_files = sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file())
        if actual_files != sorted((ACCEPTANCE_PATH, FINALIZATION_PATH, ACCEPTANCE_COMMIT_PATH)):
            _fail("UNEXPECTED_ACCEPTANCE_MEMBER", "acceptance directory members differ from contract")
        validate_instance("acceptance", commit)
        validate_instance("acceptance", record)
        if root.name != acceptance_id or commit["acceptance_id"] != acceptance_id or record["acceptance_id"] != acceptance_id:
            _fail("ACCEPTANCE_ID_MISMATCH", "acceptance identity chain differs")
        content_hash = canonical_sha256(_acceptance_preimage(record))
        if record["acceptance_content_sha256"] != content_hash or acceptance_id != f"p9accv2_{content_hash[:24]}":
            _fail("ACCEPTANCE_HASH_MISMATCH", "acceptance hash or identity differs")
        acceptance_raw = (root / ACCEPTANCE_PATH).read_bytes()
        finalization_raw = (root / FINALIZATION_PATH).read_bytes()
        if commit != _commit_manifest(acceptance_id, acceptance_raw, finalization_raw):
            _fail("ACCEPTANCE_COMMIT_MISMATCH", "commit manifest does not bind published bytes")
        bundle_path = Path(bundle_root) / record["run_bundle_id"]
        bundle = validate_run_bundle(bundle_path, locator_roots)
        if not bundle.valid:
            _fail("BUNDLE_INVALID", "accepted bundle is invalid")
        if bundle.completeness != "SCIENTIFICALLY_COMPLETE":
            _fail("SCIENTIFICALLY_INCOMPLETE", "accepted bundle is incomplete")
        if bundle.bundle_content_sha256 != record["run_bundle_hash"]:
            _fail("BUNDLE_MISMATCH", "acceptance bundle hash differs")
        valid_finalization, reason = validate_finalization_result(finalization, bundle_path, locator_roots)
        if not valid_finalization:
            _fail(reason or "FINALIZATION_RESULT_INVALID", "accepted finalization is invalid")
        if record["finalization_id"] != finalization["finalization_id"] or record["finalization_result_hash"] != finalization["finalization_result_hash"]:
            _fail("FINALIZATION_MISMATCH", "acceptance finalization binding differs")
        selected = finalization["selected_checkpoint"]
        selected_bindings = {
            "checkpoint_id": selected["checkpoint_id"],
            "payload_sha256": selected["payload_sha256"],
            "manifest_sha256": selected["manifest_sha256"],
        }
        if any(record[key] != value for key, value in selected_bindings.items()):
            _fail("SELECTED_CHECKPOINT_MISMATCH", "acceptance checkpoint binding differs")
        bundle_manifest = _read_canonical(bundle_path / BUNDLE_COMMIT_PATH)
        if record["authority_id"] != bundle_manifest["bindings"]["authority_id"] or record["authority_hash"] != bundle_manifest["bindings"]["authority_hash"]:
            _fail("AUTHORITY_MISMATCH", "acceptance authority differs from bundle")
        return AcceptanceValidationResult(True, acceptance_id)
    except AcceptanceError as error:
        return AcceptanceValidationResult(False, acceptance_id if isinstance(acceptance_id, str) else None, error.code, error.message)
    except (OSError, CanonicalJSONError, P9V2SchemaError, KeyError, TypeError) as error:
        return AcceptanceValidationResult(False, acceptance_id if isinstance(acceptance_id, str) else None, "ACCEPTANCE_INVALID", str(error))


def publish_acceptance(
    finalization_result: Mapping[str, Any],
    bundle_path: str | Path,
    locator_roots: Mapping[str, str | Path],
    acceptance_root: str | Path,
    *,
    authority_id: str,
    authority_hash: str,
    fault_hook: Callable[[str], None] | None = None,
) -> AcceptancePublication:
    """Publish once under a short acceptance-identity-scoped kernel lock."""

    bundle_path = Path(bundle_path)
    bundle_validation = validate_run_bundle(bundle_path, locator_roots)
    if not bundle_validation.valid:
        _fail("BUNDLE_INVALID", "cannot accept invalid bundle")
    if bundle_validation.completeness != "SCIENTIFICALLY_COMPLETE":
        _fail("SCIENTIFICALLY_INCOMPLETE", "cannot accept incomplete bundle")
    valid_result, reason = validate_finalization_result(finalization_result, bundle_path, locator_roots)
    if not valid_result:
        _fail(reason or "FINALIZATION_RESULT_INVALID", "cannot accept invalid finalization")
    manifest = _read_canonical(bundle_path / BUNDLE_COMMIT_PATH)
    record = _make_acceptance(finalization_result, manifest, authority_id, authority_hash)
    acceptance_id = record["acceptance_id"]
    publication_root = Path(acceptance_root)
    publication_root.mkdir(parents=True, exist_ok=True)
    locks = publication_root / ".locks"
    staging = publication_root / ".staging"
    locks.mkdir(exist_ok=True)
    staging.mkdir(exist_ok=True)
    final_path = publication_root / acceptance_id
    bundle_store = bundle_path.parent
    acceptance_raw = canonical_json_bytes(record)
    finalization_raw = canonical_json_bytes(dict(finalization_result))
    commit_raw = canonical_json_bytes(_commit_manifest(acceptance_id, acceptance_raw, finalization_raw))
    if fault_hook is not None:
        fault_hook("before_lock_acquisition")
    lock_path = locks / f"{acceptance_id}.lock"
    lock_fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    stage_path: Path | None = None
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        if fault_hook is not None:
            fault_hook("after_lock_acquisition_before_staging")
        existing = validate_acceptance(acceptance_id, publication_root, bundle_store, locator_roots)
        if final_path.exists():
            if not existing.valid:
                _fail("INCONSISTENT_EXISTING_ACCEPTANCE", existing.error_code or "invalid existing acceptance")
            return AcceptancePublication(acceptance_id, final_path, False)
        stage_path = Path(tempfile.mkdtemp(prefix=f".{acceptance_id}.", dir=staging))
        if fault_hook is not None:
            fault_hook("after_staging_creation_before_write")
        _write_file(stage_path / ACCEPTANCE_PATH, acceptance_raw, fault_hook, partial_fault=True)
        _write_file(stage_path / FINALIZATION_PATH, finalization_raw, None)
        if fault_hook is not None:
            fault_hook("after_file_fsync_before_verification")
        if _read_canonical(stage_path / ACCEPTANCE_PATH) != record or _read_canonical(stage_path / FINALIZATION_PATH) != dict(finalization_result):
            _fail("STAGING_VERIFICATION_FAILED", "staged publication bytes differ")
        commit_dir = stage_path / "commit"
        commit_dir.mkdir()
        _write_file(commit_dir / "acceptance_commit_manifest.json", commit_raw, None)
        fsync_directory(commit_dir)
        fsync_directory(stage_path)
        if fault_hook is not None:
            fault_hook("after_verification_before_commit_manifest_rename")
        os.rename(stage_path, final_path)
        stage_path = None
        if fault_hook is not None:
            fault_hook("after_commit_manifest_rename_before_directory_fsync")
        fsync_directory(publication_root)
        if fault_hook is not None:
            fault_hook("after_directory_fsync_before_lock_release")
        validated = validate_acceptance(acceptance_id, publication_root, bundle_store, locator_roots)
        if not validated.valid:
            _fail("PUBLICATION_VERIFICATION_FAILED", validated.error_code or "published acceptance invalid")
        return AcceptancePublication(acceptance_id, final_path, True)
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)


def resolve_accepted_checkpoint(
    acceptance_identity: str,
    acceptance_root: str | Path,
    bundle_root: str | Path,
    locator_roots: Mapping[str, str | Path],
) -> AcceptedCheckpoint:
    """Resolve only a canonical acceptance identity through the complete evidence chain."""

    if not isinstance(acceptance_identity, str) or not ACCEPTANCE_ID_PATTERN.fullmatch(acceptance_identity):
        _fail("INVALID_ACCEPTANCE_ID", "raw paths, latest tokens, and legacy identities are forbidden")
    validation = validate_acceptance(acceptance_identity, acceptance_root, bundle_root, locator_roots)
    if not validation.valid:
        _fail(validation.error_code or "ACCEPTANCE_INVALID", validation.message or "acceptance is invalid")
    acceptance_path = Path(acceptance_root) / acceptance_identity
    record = _read_canonical(acceptance_path / ACCEPTANCE_PATH)
    finalization = _read_canonical(acceptance_path / FINALIZATION_PATH)
    bundle_path = Path(bundle_root) / record["run_bundle_id"]
    selected = finalization["selected_checkpoint"]
    configuration = _read_canonical(bundle_path / "config/scientific_configuration.json")
    source_inventory = _read_canonical(bundle_path / "provenance/source_inventory.json")
    return AcceptedCheckpoint(
        acceptance_id=acceptance_identity,
        run_bundle_id=record["run_bundle_id"],
        run_bundle_hash=record["run_bundle_hash"],
        finalization_id=record["finalization_id"],
        finalization_result_hash=record["finalization_result_hash"],
        checkpoint_id=record["checkpoint_id"],
        payload_locator=dict(selected["payload_locator"]),
        payload_sha256=record["payload_sha256"],
        manifest_sha256=record["manifest_sha256"],
        completed_epoch=selected["completed_epoch"],
        resume_epoch=selected["resume_epoch"],
        optimizer_update=selected["optimizer_update"],
        validation_retrieval_loss=selected["validation_retrieval_loss"],
        mean_source_separation_margin=selected["mean_source_separation_margin"],
        stopping_summary=dict(finalization["stopping_summary"]),
        scientific_configuration=configuration,
        authority_id=record["authority_id"],
        authority_hash=record["authority_hash"],
        provenance={
            **finalization["provenance"],
            "source_inventory_digest": source_inventory["inventory_digest"],
            "source_inventory_entries": len(source_inventory["entries"]),
        },
    )
