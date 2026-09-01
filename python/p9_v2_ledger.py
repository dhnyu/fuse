"""Append-only, hash-chained P9 v2 run ledger storage."""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from p9_v2_canonical import (
    CanonicalJSONError,
    canonical_json_bytes,
    canonical_json_line,
    canonical_sha256,
    deterministic_id,
    parse_canonical_json,
    sha256_bytes,
)
from p9_v2_schema import SCHEMA_VERSION, P9V2SchemaError, validate_instance


GENESIS_HASH = "GENESIS"
MAXIMUM_EVENT_BYTES = 1_048_576
EVENTS_PER_SEGMENT = 1
SEGMENT_PATTERN = re.compile(r"^(\d{12})-(\d{12})\.jsonl$")
FaultHook = Callable[[str], None]

WRITER_PERMISSIONS: dict[str, frozenset[str]] = {
    "RUN_AUTHORIZED": frozenset({"controller", "legacy_importer"}),
    "RUN_STARTING": frozenset({"controller", "legacy_importer"}),
    "RUN_STARTED": frozenset({"controller", "legacy_importer"}),
    "EPOCH_STARTED": frozenset({"rank0", "legacy_importer"}),
    "PROGRESS_SUMMARY_COMMITTED": frozenset({"rank0", "legacy_importer"}),
    "UPDATE_COMMITTED": frozenset({"rank0", "legacy_importer"}),
    "VALIDATION_CHECKPOINT_COMMITTED": frozenset({"rank0", "legacy_importer"}),
    "EARLY_STOPPING_UPDATED": frozenset({"rank0", "legacy_importer"}),
    "TRAINING_COMPLETED": frozenset({"controller", "rank0", "legacy_importer"}),
    "TRAINING_INTERRUPTED": frozenset({"controller", "legacy_importer"}),
    "TRAINING_FAILED": frozenset({"controller", "legacy_importer"}),
    "FINALIZATION_STARTED": frozenset({"finalizer", "legacy_importer"}),
    "FINALIZATION_COMPLETED": frozenset({"finalizer", "legacy_importer"}),
    "FINALIZATION_FAILED": frozenset({"finalizer", "legacy_importer"}),
    "ACCEPTANCE_PUBLISHED": frozenset({"publisher", "legacy_importer"}),
}


class LedgerError(ValueError):
    """Base error for invalid or unsafe ledger operations."""


class LedgerCorruptionError(LedgerError):
    """Committed canonical evidence is malformed or inconsistent."""


class LedgerTransitionError(LedgerError):
    """An event violates semantic or writer constraints."""


class LedgerClosedError(LedgerError):
    """A caller attempted to append to a closed ledger."""


class UncommittedStagingError(LedgerError):
    """A prior writer left non-authoritative staging debris."""


@dataclass(frozen=True)
class LedgerRead:
    header: dict[str, Any]
    events: tuple[dict[str, Any], ...]
    segment_inventory: tuple[dict[str, Any], ...]
    closed: bool

    @property
    def last_sequence(self) -> int:
        return self.events[-1]["event_sequence"] if self.events else 0

    @property
    def last_event_hash(self) -> str:
        return self.events[-1]["event_hash"] if self.events else GENESIS_HASH


def _no_fault(_: str) -> None:
    return None


def _parse_canonical_json(raw: bytes, *, line: bool) -> Any:
    try:
        return parse_canonical_json(raw, json_line=line)
    except CanonicalJSONError as error:
        raise LedgerCorruptionError("JSON value is outside the canonical contract") from error


def fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def write_all(descriptor: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        written = os.write(descriptor, payload[offset:])
        if written <= 0:
            raise OSError("short write while persisting ledger artifact")
        offset += written


def _segment_name(sequence: int) -> str:
    return f"{sequence:012d}-{sequence:012d}.jsonl"


def _semantic_event_validation(event: dict[str, Any]) -> None:
    event_type = event["event_type"]
    role = event["writer"]["role"]
    if role not in WRITER_PERMISSIONS[event_type]:
        raise LedgerTransitionError(f"writer role {role} cannot write {event_type}")
    if event["legacy_import"] != (role == "legacy_importer"):
        raise LedgerTransitionError("legacy_import must be true exactly for legacy_importer events")
    payload = event["payload"]
    if event_type in {"VALIDATION_CHECKPOINT_COMMITTED", "TRAINING_COMPLETED"}:
        if payload["resume_epoch"] != payload["completed_epoch"] + 1:
            raise LedgerTransitionError("resume_epoch must equal completed_epoch + 1")
    if event_type == "VALIDATION_CHECKPOINT_COMMITTED":
        if payload["sampler"]["epoch"] != payload["resume_epoch"]:
            raise LedgerTransitionError("sampler epoch must equal explicit resume_epoch")
        if not event["legacy_import"] and payload["source_run_id"] != event["run_id"]:
            raise LedgerTransitionError("native checkpoint source run must equal event run")
    if event_type == "PROGRESS_SUMMARY_COMMITTED":
        if payload["first_update"] > payload["last_update"]:
            raise LedgerTransitionError("progress update range is reversed")
    if event_type in {"TRAINING_INTERRUPTED", "TRAINING_FAILED"}:
        has_checkpoint = payload["resumable_checkpoint_committed"]
        policy = payload["resume_policy"]
        if policy == "EXACT_RESUME" and not has_checkpoint:
            raise LedgerTransitionError("exact resume policy requires a committed checkpoint")
        if policy == "RESTART" and has_checkpoint:
            raise LedgerTransitionError("restart policy cannot mark a checkpoint resumable")


def make_event(
    *,
    event_type: str,
    event_sequence: int,
    run_id: str,
    occurred_at: str,
    writer_id: str,
    writer_role: str,
    previous_event_hash: str,
    payload: dict[str, Any],
    legacy_import: bool = False,
) -> dict[str, Any]:
    envelope = {
        "schema_version": SCHEMA_VERSION,
        "event_type": event_type,
        "event_sequence": event_sequence,
        "run_id": run_id,
        "occurred_at": occurred_at,
        "writer": {"writer_id": writer_id, "role": writer_role},
        "legacy_import": legacy_import,
        "previous_event_hash": previous_event_hash,
        "payload": payload,
    }
    event = {**envelope, "event_id": deterministic_id("p9evt_", envelope)}
    event["event_hash"] = canonical_sha256(event)
    verify_event(event)
    return event


def verify_event(
    event: dict[str, Any],
    *,
    expected_run_id: str | None = None,
    expected_sequence: int | None = None,
    expected_previous_hash: str | None = None,
) -> None:
    try:
        validate_instance("event", event)
    except P9V2SchemaError as error:
        raise LedgerCorruptionError(str(error)) from error
    envelope = {key: value for key, value in event.items() if key not in {"event_id", "event_hash"}}
    if event["event_id"] != deterministic_id("p9evt_", envelope):
        raise LedgerCorruptionError("event_id mismatch")
    unhashed = {key: value for key, value in event.items() if key != "event_hash"}
    if event["event_hash"] != canonical_sha256(unhashed):
        raise LedgerCorruptionError("event_hash mismatch")
    if expected_run_id is not None and event["run_id"] != expected_run_id:
        raise LedgerCorruptionError("event run identity mismatch")
    if expected_sequence is not None and event["event_sequence"] != expected_sequence:
        raise LedgerCorruptionError("event sequence discontinuity")
    if expected_previous_hash is not None and event["previous_event_hash"] != expected_previous_hash:
        raise LedgerCorruptionError("previous-event hash mismatch")
    _semantic_event_validation(event)


def _read_header(root: Path) -> dict[str, Any]:
    path = root / "header.json"
    if not path.is_file():
        raise LedgerCorruptionError("ledger header is missing")
    value = _parse_canonical_json(path.read_bytes(), line=False)
    try:
        validate_instance("ledger_header", value)
    except P9V2SchemaError as error:
        raise LedgerCorruptionError(str(error)) from error
    return value


def _expected_manifest(read: LedgerRead) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "p9_v2_ledger_manifest",
        "run_id": read.header["run_id"],
        "event_count": len(read.events),
        "first_sequence": 1,
        "last_sequence": read.last_sequence,
        "tail_event_hash": read.last_event_hash,
        "segment_policy": {
            "events_per_segment": EVENTS_PER_SEGMENT,
            "maximum_event_bytes": MAXIMUM_EVENT_BYTES,
        },
        "segments": list(read.segment_inventory),
    }


def read_ledger(root: str | Path, *, verify_manifest: bool = True) -> LedgerRead:
    root = Path(root)
    header = _read_header(root)
    segments_root = root / "segments"
    if not segments_root.is_dir():
        raise LedgerCorruptionError("segments directory is missing")
    paths = sorted(segments_root.iterdir())
    events: list[dict[str, Any]] = []
    inventory: list[dict[str, Any]] = []
    previous_hash = GENESIS_HASH
    for expected_sequence, path in enumerate(paths, 1):
        match = SEGMENT_PATTERN.fullmatch(path.name)
        if not path.is_file() or match is None:
            raise LedgerCorruptionError(f"unexpected committed segment entry: {path.name}")
        first, last = (int(value) for value in match.groups())
        if first != last or first != expected_sequence:
            raise LedgerCorruptionError("segment filename sequence is missing, duplicate, or reordered")
        raw = path.read_bytes()
        if not raw or len(raw) > MAXIMUM_EVENT_BYTES:
            raise LedgerCorruptionError("segment size is outside the configured bound")
        event = _parse_canonical_json(raw, line=True)
        verify_event(
            event,
            expected_run_id=header["run_id"],
            expected_sequence=expected_sequence,
            expected_previous_hash=previous_hash,
        )
        previous_hash = event["event_hash"]
        events.append(event)
        inventory.append({
            "path": f"segments/{path.name}",
            "first_sequence": first,
            "last_sequence": last,
            "event_count": 1,
            "size_bytes": len(raw),
            "sha256": sha256_bytes(raw),
        })
    manifest_path = root / "commit" / "ledger_manifest.json"
    result = LedgerRead(header, tuple(events), tuple(inventory), manifest_path.is_file())
    if result.closed and verify_manifest:
        if not result.events:
            raise LedgerCorruptionError("closed ledger cannot be empty")
        manifest = _parse_canonical_json(manifest_path.read_bytes(), line=False)
        try:
            validate_instance("ledger_manifest", manifest)
        except P9V2SchemaError as error:
            raise LedgerCorruptionError(str(error)) from error
        if manifest != _expected_manifest(result):
            raise LedgerCorruptionError("manifest does not match committed segments")
    return result


def read_tail_hint(root: str | Path, canonical: LedgerRead | None = None) -> dict[str, Any] | None:
    """Return a valid current hint, or None. Tail bytes never affect canonical replay."""

    root = Path(root)
    path = root / "tail.json"
    if not path.is_file():
        return None
    try:
        value = _parse_canonical_json(path.read_bytes(), line=False)
        validate_instance("tail_cache", value)
        current = canonical or read_ledger(root)
        if value["run_id"] != current.header["run_id"]:
            return None
        if value["last_sequence"] != current.last_sequence:
            return None
        if value["last_event_hash"] != current.last_event_hash:
            return None
        return value
    except (LedgerError, P9V2SchemaError, OSError):
        return None


class LedgerWriter:
    """Single-writer append API; callers must already own the run writer boundary."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.header = _read_header(self.root)

    @classmethod
    def initialize(cls, root: str | Path, *, run_id: str, created_at: str) -> "LedgerWriter":
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        for directory in ("segments", ".staging", ".debris", "commit"):
            (root / directory).mkdir(exist_ok=True)
        header = {
            "schema_version": SCHEMA_VERSION,
            "artifact_type": "p9_v2_ledger_header",
            "run_id": run_id,
            "created_at": created_at,
            "canonical_json_contract": "p9-v2-exact-binary64-decimal-v1",
            "segment_policy": {
                "events_per_segment": EVENTS_PER_SEGMENT,
                "maximum_event_bytes": MAXIMUM_EVENT_BYTES,
                "filename_format": "%012d-%012d.jsonl",
            },
        }
        validate_instance("ledger_header", header)
        path = root / "header.json"
        if path.exists():
            existing = _parse_canonical_json(path.read_bytes(), line=False)
            if existing != header:
                raise LedgerCorruptionError("existing ledger header differs")
        else:
            stage = root / ".staging" / "header.json.incomplete"
            descriptor = os.open(stage, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o640)
            try:
                write_all(descriptor, canonical_json_bytes(header))
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            os.replace(stage, path)
            fsync_directory(root)
        return cls(root)

    @classmethod
    def reopen_after_crash(cls, root: str | Path) -> "LedgerWriter":
        writer = cls(root)
        writer.quarantine_staging_debris()
        return writer

    def quarantine_staging_debris(self) -> tuple[Path, ...]:
        """Preserve ignored staging bytes before a new append under single-writer ownership."""

        staging = self.root / ".staging"
        debris = self.root / ".debris"
        moved: list[Path] = []
        for source in sorted(staging.iterdir()):
            if not source.is_file():
                raise UncommittedStagingError("unexpected staging directory entry")
            index = 1
            while True:
                destination = debris / f"{source.name}.{index:06d}"
                if not destination.exists():
                    break
                index += 1
            os.replace(source, destination)
            moved.append(destination)
        if moved:
            fsync_directory(staging)
            fsync_directory(debris)
        return tuple(moved)

    def append(
        self,
        *,
        event_type: str,
        occurred_at: str,
        writer_id: str,
        writer_role: str,
        payload: dict[str, Any],
        legacy_import: bool = False,
        fault: FaultHook = _no_fault,
    ) -> dict[str, Any]:
        current = read_ledger(self.root)
        if current.closed:
            raise LedgerClosedError("cannot append to a closed ledger")
        sequence = current.last_sequence + 1
        event = make_event(
            event_type=event_type,
            event_sequence=sequence,
            run_id=self.header["run_id"],
            occurred_at=occurred_at,
            writer_id=writer_id,
            writer_role=writer_role,
            previous_event_hash=current.last_event_hash,
            payload=payload,
            legacy_import=legacy_import,
        )
        raw = canonical_json_line(event)
        if len(raw) > MAXIMUM_EVENT_BYTES:
            raise LedgerError("event exceeds the one-segment byte bound")
        name = _segment_name(sequence)
        stage = self.root / ".staging" / f"{name}.incomplete"
        final = self.root / "segments" / name
        fault("before_staging_file_creation")
        try:
            descriptor = os.open(stage, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o640)
        except FileExistsError as error:
            raise UncommittedStagingError(f"staging debris blocks sequence {sequence}") from error
        try:
            fault("after_staging_creation_before_write")
            midpoint = max(1, len(raw) // 2)
            write_all(descriptor, raw[:midpoint])
            fault("during_stage_write")
            write_all(descriptor, raw[midpoint:])
            fault("after_write_before_file_fsync")
            os.fsync(descriptor)
            fault("after_file_fsync_before_verification")
        finally:
            os.close(descriptor)
        candidate = stage.read_bytes()
        parsed = _parse_canonical_json(candidate, line=True)
        verify_event(
            parsed,
            expected_run_id=self.header["run_id"],
            expected_sequence=sequence,
            expected_previous_hash=current.last_event_hash,
        )
        if candidate != raw:
            raise LedgerCorruptionError("staged event differs from proposed canonical bytes")
        fault("after_verification_before_rename")
        if final.exists():
            raise LedgerCorruptionError("committed segment collision")
        os.replace(stage, final)
        fault("after_rename_before_directory_fsync")
        fsync_directory(final.parent)
        fault("after_directory_fsync_before_tail_cache")
        self._update_tail(event, fault=fault)
        return event

    def _update_tail(self, event: dict[str, Any], *, fault: FaultHook) -> None:
        value = {
            "schema_version": SCHEMA_VERSION,
            "artifact_type": "p9_v2_tail_cache",
            "non_authoritative": True,
            "run_id": self.header["run_id"],
            "last_sequence": event["event_sequence"],
            "last_event_hash": event["event_hash"],
        }
        validate_instance("tail_cache", value)
        stage = self.root / ".staging" / f"tail.{os.getpid()}.{time.time_ns()}.incomplete"
        descriptor = os.open(stage, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o640)
        try:
            write_all(descriptor, canonical_json_bytes(value))
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        fault("during_tail_cache_replacement")
        os.replace(stage, self.root / "tail.json")
        fsync_directory(self.root)

    def close(self, *, fault: FaultHook = _no_fault) -> Path:
        current = read_ledger(self.root, verify_manifest=False)
        if not current.events:
            raise LedgerError("cannot close an empty ledger")
        expected = _expected_manifest(current)
        validate_instance("ledger_manifest", expected)
        final = self.root / "commit" / "ledger_manifest.json"
        if final.exists():
            existing = _parse_canonical_json(final.read_bytes(), line=False)
            if existing != expected:
                raise LedgerCorruptionError("existing closed-ledger manifest differs")
            return final
        raw = canonical_json_bytes(expected)
        stage = self.root / ".staging" / "ledger_manifest.json.incomplete"
        descriptor = os.open(stage, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o640)
        try:
            midpoint = max(1, len(raw) // 2)
            write_all(descriptor, raw[:midpoint])
            fault("during_closed_manifest_publication")
            write_all(descriptor, raw[midpoint:])
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        if _parse_canonical_json(stage.read_bytes(), line=False) != expected:
            raise LedgerCorruptionError("staged ledger manifest differs")
        os.replace(stage, final)
        fault("after_manifest_rename_before_directory_fsync")
        fsync_directory(final.parent)
        read_ledger(self.root)
        return final
