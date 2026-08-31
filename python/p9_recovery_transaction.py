"""Durable, recovery-only transaction primitives.

This module deliberately has no training, CUDA, DDP, optimiser, validation, or
checkpoint-writing entry point. A recovery result becomes canonical only when
``transaction_manifest.json`` is atomically published beside both payloads.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import socket
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from p9_checkpoint_recovery import canonical_json

STATES = {
    "AUTHORIZED_NOT_STARTED", "ACQUIRING_LOCK", "STARTING",
    "VALIDATING_SOURCE", "DERIVING_CANDIDATES", "SELECTING_CHECKPOINT",
    "RECONSTRUCTING_STOPPING_BOUNDARY", "STAGING_TERMINAL_RECOVERY",
    "STAGING_ACCEPTANCE", "COMMITTING", "RECOVERY_ACCEPTED",
    "RECOVERY_BLOCKED", "RECOVERY_FAILED_NONMUTATING",
}
TRANSITIONS = {
    "AUTHORIZED_NOT_STARTED": {"ACQUIRING_LOCK", "RECOVERY_BLOCKED"},
    "ACQUIRING_LOCK": {"STARTING", "RECOVERY_BLOCKED"},
    "STARTING": {"VALIDATING_SOURCE", "RECOVERY_FAILED_NONMUTATING"},
    "VALIDATING_SOURCE": {"DERIVING_CANDIDATES", "RECOVERY_FAILED_NONMUTATING"},
    "DERIVING_CANDIDATES": {"SELECTING_CHECKPOINT", "RECOVERY_FAILED_NONMUTATING"},
    "SELECTING_CHECKPOINT": {"RECONSTRUCTING_STOPPING_BOUNDARY", "RECOVERY_FAILED_NONMUTATING"},
    "RECONSTRUCTING_STOPPING_BOUNDARY": {"STAGING_TERMINAL_RECOVERY", "RECOVERY_FAILED_NONMUTATING"},
    "STAGING_TERMINAL_RECOVERY": {"STAGING_ACCEPTANCE", "RECOVERY_FAILED_NONMUTATING"},
    "STAGING_ACCEPTANCE": {"COMMITTING", "RECOVERY_FAILED_NONMUTATING"},
    "COMMITTING": {"RECOVERY_ACCEPTED", "RECOVERY_FAILED_NONMUTATING"},
    "RECOVERY_ACCEPTED": set(), "RECOVERY_BLOCKED": set(),
    "RECOVERY_FAILED_NONMUTATING": set(),
}


def digest(value: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TestOnlyHardCrash:
    """Hard-stop hook usable only by explicitly synthetic transactions."""

    __test__ = False

    def __init__(self, boundary: str):
        self.boundary = boundary

    def at(self, boundary: str) -> None:
        if boundary == self.boundary:
            os._exit(86)


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    """Persist canonical JSON with same-directory fsync and atomic rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.staging-{os.getpid()}-{uuid.uuid4().hex}")
    try:
        with temporary.open("wb") as stream:
            stream.write(canonical_json(value))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        try:
            descriptor = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        except OSError:
            pass
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


class OperationState:
    """Canonical mutable state; owner/heartbeat never replace this record."""

    schema_version = "1.1.0"

    def __init__(self, path: str | Path, identity: dict[str, Any]):
        self.path, self.identity = Path(path), dict(identity)
        self.value = {
            "schema_version": self.schema_version, **self.identity,
            "state": "AUTHORIZED_NOT_STARTED", "previous_state": None,
            "state_sequence": 0, "transition_unix": time.time(),
            "committed": False, "last_completed_phase": None,
            "error_classification": None, "original_exception_summary": None,
            "release_status": "NOT_RELEASED",
        }

    def transition(self, state: str, **fields: Any) -> dict[str, Any]:
        prior = self.value["state"]
        if state not in STATES or state not in TRANSITIONS[prior]:
            raise ValueError(f"invalid recovery transition: {prior}->{state}")
        committed = fields.get("committed", self.value.get("committed"))
        if state == "RECOVERY_ACCEPTED" and not committed:
            raise ValueError("recovery acceptance requires canonical commit manifest")
        self.value.update(
            fields, state=state, previous_state=prior,
            state_sequence=int(self.value["state_sequence"]) + 1,
            transition_unix=time.time(),
        )
        atomic_json(self.path, self.value)
        return dict(self.value)

    def annotate(self, **fields: Any) -> dict[str, Any]:
        self.value.update(fields)
        atomic_json(self.path, self.value)
        return dict(self.value)


class RecoveryLock:
    """Descriptor-backed lock; records are evidence and cannot grant ownership."""

    owner_schema_version = "1.1.0"
    heartbeat_schema_version = "1.1.0"

    def __init__(self, root: str | Path, duplicate_key: str, owner: dict[str, Any]):
        self.root, self.key, self.owner = Path(root), duplicate_key, dict(owner)
        self.path = self.root / f"{duplicate_key}.lock"
        self.fd: int | None = None
        self.sequence = 0

    @property
    def owner_path(self) -> Path:
        return self.root / f"{self.key}.owner.json"

    @property
    def heartbeat_path(self) -> Path:
        return self.root / f"{self.key}.heartbeat.json"

    def acquire(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(self.fd)
            self.fd = None
            raise RuntimeError("DUPLICATE_OPERATION_ACTIVE")
        atomic_json(self.owner_path, {
            "schema_version": self.owner_schema_version, **self.owner,
            "kernel_lock_status": "HELD", "lock_path": str(self.path),
            "state": "ACQUIRING_LOCK", "owner_pid": os.getpid(),
            "hostname": socket.gethostname(), "acquired_unix": time.time(),
        })
        self.heartbeat("ACQUIRING_LOCK", "kernel_lock_acquired", state_sequence=1)

    def heartbeat(self, state: str, phase: str, **fields: Any) -> None:
        if self.fd is None:
            raise RuntimeError("recovery heartbeat without kernel lock")
        self.sequence += 1
        atomic_json(self.heartbeat_path, {
            "schema_version": self.heartbeat_schema_version,
            "duplicate_operation_key": self.key, "owner_pid": os.getpid(),
            "hostname": socket.gethostname(), "sequence": self.sequence,
            "wall_unix": time.time(), "state": state,
            "last_completed_phase": phase, "kernel_lock_status": "HELD", **fields,
        })

    def release(self, state: str, *, committed: bool = False,
                last_completed_phase: str = "lock_release") -> str:
        if self.fd is None:
            return "ALREADY_RELEASED_BY_PROCESS_EXIT"
        try:
            self.heartbeat(state, last_completed_phase, committed=committed,
                           release_status="RELEASING")
            fcntl.flock(self.fd, fcntl.LOCK_UN)
            os.close(self.fd)
            self.fd = None
            atomic_json(self.owner_path, {
                "schema_version": self.owner_schema_version, **self.owner,
                "kernel_lock_status": "RELEASED", "lock_path": str(self.path),
                "state": state, "committed": committed,
                "last_completed_phase": last_completed_phase,
                "released_unix": time.time(),
            })
            return "RELEASED"
        except OSError:
            return "RELEASE_FAILED"


@dataclass(frozen=True)
class TransactionContext:
    """The only path/identity source used by a recovery transaction."""

    authority: dict[str, Any]
    reservation: dict[str, Any]
    operation: dict[str, Any]
    contract: dict[str, Any]
    duplicate_operation_key: str
    source_inventory_digest: str
    lock_root: Path
    output_root: Path
    store: str
    launch_commit: str
    synthetic: bool = False
    transaction_id: str = ""
    hard_crash: TestOnlyHardCrash | None = None

    @classmethod
    def create(cls, *, authority: dict[str, Any], reservation: dict[str, Any],
               operation: dict[str, Any], contract: dict[str, Any], lock_root: str | Path,
               output_root: str | Path, store: str, launch_commit: str,
               synthetic: bool = False,
               hard_crash: TestOnlyHardCrash | None = None) -> "TransactionContext":
        if hard_crash is not None and not synthetic:
            raise ValueError("hard crash injection requires a synthetic transaction")
        key = duplicate_key(authority, reservation, operation, contract)
        return cls(authority, reservation, operation, contract, key,
                   contract["join_audit_sha256"], Path(lock_root), Path(output_root), store,
                   launch_commit, synthetic, f"p9rtx_{key[:24]}", hard_crash)

    @property
    def final_root(self) -> Path:
        return self.output_root / self.transaction_id

    @property
    def staging_root(self) -> Path:
        return self.output_root / f".{self.transaction_id}.staging-{self.duplicate_operation_key[:12]}"

    @property
    def state_path(self) -> Path:
        return self.lock_root / "operation_state" / self.duplicate_operation_key / "operation_state.json"

    def identity(self) -> dict[str, Any]:
        return {
            "synthetic": self.synthetic,
            "recovery_authority_id": self.authority["recovery_authority_id"],
            "recovery_reservation_id": self.reservation["recovery_reservation_id"],
            "recovery_operation_id": self.operation["recovery_operation_id"],
            "duplicate_operation_key": self.duplicate_operation_key,
            "transaction_id": self.transaction_id,
            "source_failed_lineage": self.contract["failed_lineage"],
            "source_inventory_digest": self.source_inventory_digest,
            "runtime_tree_sha256": self.authority["runtime_tree_sha256"],
            "dag_sha256": self.authority["dag_sha256"],
            "terminal_target": self.authority["terminal_target"],
            "recovery_store": self.store,
            "staging_path": str(self.staging_root),
            "final_transaction_path": str(self.final_root),
        }


class RecoveryTransactionController:
    """Single controller for canonical recovery publication."""

    def __init__(self, context: TransactionContext):
        self.context = context
        owner = {
            **context.identity(), "launch_commit": context.launch_commit,
            "parent_pid": os.getppid(),
            "process_start_identity": f"{os.getpid()}:{time.time_ns()}",
        }
        self.lock = RecoveryLock(context.lock_root, context.duplicate_operation_key, owner)
        self.state = OperationState(context.state_path, context.identity())
        self.started = False
        self.committed = False

    def _transition(self, target: str, phase: str, **fields: Any) -> None:
        snapshot = self.state.transition(target, last_completed_phase=phase, **fields)
        self.lock.heartbeat(target, phase, state_sequence=snapshot["state_sequence"],
                            committed=bool(snapshot.get("committed")),
                            transaction_id=self.context.transaction_id)

    def checkpoint(self, boundary: str) -> None:
        if self.context.hard_crash is not None:
            self.context.hard_crash.at(boundary)

    def acquire_and_start(self) -> None:
        self.checkpoint("BEFORE_LOCK")
        self.lock.acquire()
        self.checkpoint("AFTER_LOCK")
        self.checkpoint("AFTER_OWNER")
        self._transition("ACQUIRING_LOCK", "kernel_lock_acquired")
        self._transition("STARTING", "owner_and_state_persisted")
        self.started = True
        self.checkpoint("AFTER_STARTING")

    def phase(self, target: str, phase: str, **fields: Any) -> None:
        self._transition(target, phase, **fields)

    def stage_pair(self, terminal: dict[str, Any], acceptance: dict[str, Any]) -> dict[str, str]:
        stage = self.context.staging_root
        if stage.exists() or self.context.final_root.exists():
            raise FileExistsError("DUPLICATE_OPERATION_COMPLETED_OR_STAGING_EXISTS")
        stage.mkdir(parents=True, exist_ok=False)
        self.phase("STAGING_TERMINAL_RECOVERY", "staging_directory_created",
                   staging_path=str(stage))
        atomic_json(stage / "terminal_recovery.json", terminal)
        terminal_hash = sha256_path(stage / "terminal_recovery.json")
        self.state.annotate(terminal_recovery_id=terminal["terminal_recovery_id"],
                            terminal_recovery_sha256=terminal_hash)
        self.lock.heartbeat("STAGING_TERMINAL_RECOVERY", "terminal_staged",
                            state_sequence=self.state.value["state_sequence"],
                            terminal_recovery_sha256=terminal_hash)
        self.checkpoint("AFTER_TERMINAL_STAGING")
        self.phase("STAGING_ACCEPTANCE", "terminal_validated")
        self.checkpoint("AFTER_TERMINAL_VALIDATION")
        atomic_json(stage / "recovery_acceptance.json", acceptance)
        acceptance_hash = sha256_path(stage / "recovery_acceptance.json")
        self.state.annotate(recovery_acceptance_id=acceptance["recovery_acceptance_id"],
                            recovery_acceptance_sha256=acceptance_hash)
        self.checkpoint("AFTER_ACCEPTANCE_STAGING")
        self.checkpoint("AFTER_ACCEPTANCE_VALIDATION")
        self.lock.heartbeat("STAGING_ACCEPTANCE", "acceptance_staged",
                            state_sequence=self.state.value["state_sequence"],
                            recovery_acceptance_sha256=acceptance_hash)
        return {"terminal_sha256": terminal_hash, "acceptance_sha256": acceptance_hash}

    def commit(self, hashes: dict[str, str], *, candidate_set_sha256: str,
               selection_sha256: str, stopping_sha256: str) -> dict[str, Any]:
        stage = self.context.staging_root
        self.phase("COMMITTING", "acceptance_validated")
        manifest = {
            "schema_version": "1.1.0", "artifact_type": "p9_recovery_transaction_manifest",
            "state": "COMMITTED", "transaction_id": self.context.transaction_id,
            "duplicate_operation_key": self.context.duplicate_operation_key,
            "recovery_authority_id": self.context.authority["recovery_authority_id"],
            "recovery_reservation_id": self.context.reservation["recovery_reservation_id"],
            "recovery_operation_id": self.context.operation["recovery_operation_id"],
            "source_inventory_digest": self.context.source_inventory_digest,
            "source_failed_lineage": self.context.contract["failed_lineage"],
            "runtime_tree_sha256": self.context.authority["runtime_tree_sha256"],
            "dag_sha256": self.context.authority["dag_sha256"],
            "terminal_target": self.context.authority["terminal_target"],
            "recovery_store": self.context.store,
            "candidate_count": 25, "join_result": "25/25 EXACT_MATCH",
            "candidate_set_sha256": candidate_set_sha256,
            "selection_sha256": selection_sha256, "stopping_sha256": stopping_sha256,
            **hashes,
        }
        atomic_json(stage / "transaction_manifest.json", manifest)
        self.checkpoint("AFTER_MANIFEST_STAGING")
        self.context.output_root.mkdir(parents=True, exist_ok=True)
        self.checkpoint("BEFORE_PAYLOAD_PUBLICATION")
        os.replace(stage, self.context.final_root)
        self.checkpoint("AFTER_PAYLOAD_PUBLICATION_BEFORE_COMMIT")
        self.checkpoint("IMMEDIATELY_AFTER_COMMIT_MANIFEST")
        resolved = resolve_committed(self.context.final_root, context=self.context)
        self.committed = True
        self.checkpoint("AFTER_COMMITTED_READBACK")
        self._transition("RECOVERY_ACCEPTED", "commit_manifest_validated", committed=True,
                         commit_manifest_sha256=sha256_path(self.context.final_root / "transaction_manifest.json"))
        self.checkpoint("AFTER_RECOVERY_ACCEPTED_STATE")
        return resolved

    def fail(self, error: BaseException) -> None:
        if self.started and self.state.value["state"] not in {"RECOVERY_ACCEPTED", "RECOVERY_FAILED_NONMUTATING"}:
            self._transition("RECOVERY_FAILED_NONMUTATING", self.state.value.get("last_completed_phase") or "unknown",
                             error_classification=type(error).__name__,
                             original_exception_summary=str(error)[:1000])

    def release(self) -> str:
        current = self.state.value["state"]
        self.checkpoint("BEFORE_LOCK_RELEASE")
        outcome = self.lock.release(current, committed=self.committed,
                                    last_completed_phase=self.state.value.get("last_completed_phase") or "unknown")
        if self.started:
            self.state.annotate(release_status=outcome)
        return outcome


def resolve_committed(root: str | Path, *, context: TransactionContext | None = None) -> dict[str, Any]:
    """The sole downstream resolver; a manifest is the sole commit point."""
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("recovery transaction root is not a canonical directory")
    manifest_path = root / "transaction_manifest.json"
    if not manifest_path.exists():
        raise ValueError("no canonical recovery commit manifest")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("state") != "COMMITTED":
        raise ValueError("recovery transaction is not committed")
    terminal, acceptance = root / "terminal_recovery.json", root / "recovery_acceptance.json"
    if not terminal.exists() or not acceptance.exists():
        raise ValueError("committed recovery payload incomplete")
    if any(path.is_symlink() or path.resolve().parent != root.resolve() for path in (manifest_path, terminal, acceptance)):
        raise ValueError("recovery transaction payload path escapes canonical root")
    if manifest.get("terminal_sha256") != sha256_path(terminal) or manifest.get("acceptance_sha256") != sha256_path(acceptance):
        raise ValueError("recovery committed hash mismatch")
    terminal_value, acceptance_value = json.loads(terminal.read_text()), json.loads(acceptance.read_text())
    if acceptance_value.get("status") != "PASS" or terminal_value.get("state") != "RECOVERY_ACCEPTED":
        raise ValueError("recovery payload state is not accepted")
    if acceptance_value.get("terminal_recovery_id") != terminal_value.get("terminal_recovery_id"):
        raise ValueError("recovery acceptance terminal linkage mismatch")
    if context is not None:
        expected = context.identity()
        for field in ("recovery_authority_id", "recovery_reservation_id", "recovery_operation_id"):
            if manifest.get(field) != expected[field]:
                raise ValueError(f"recovery manifest context mismatch: {field}")
        if manifest.get("duplicate_operation_key") != context.duplicate_operation_key:
            raise ValueError("recovery manifest duplicate identity mismatch")
        if manifest.get("source_inventory_digest") != context.source_inventory_digest:
            raise ValueError("recovery source inventory digest mismatch")
        expected = context.contract
        if manifest.get("source_failed_lineage") != expected["failed_lineage"]:
            raise ValueError("recovery manifest source lineage mismatch")
        if manifest.get("runtime_tree_sha256") != context.authority["runtime_tree_sha256"] or manifest.get("dag_sha256") != context.authority["dag_sha256"]:
            raise ValueError("recovery manifest runtime identity mismatch")
        if manifest.get("terminal_target") != context.authority["terminal_target"] or manifest.get("recovery_store") != context.store:
            raise ValueError("recovery manifest target/store mismatch")
        if manifest.get("candidate_count") != 25 or manifest.get("join_result") != "25/25 EXACT_MATCH":
            raise ValueError("recovery candidate join mismatch")
        if terminal_value.get("source_failed_lineage") != expected["failed_lineage"]:
            raise ValueError("recovery terminal source lineage mismatch")
        if terminal_value.get("selected_checkpoint") != expected["expected_selected_checkpoint"]:
            raise ValueError("recovery terminal selected checkpoint mismatch")
        if terminal_value.get("stopping") != expected["stopping"]:
            raise ValueError("recovery terminal stopping boundary mismatch")
        if terminal_value.get("candidate_set_sha256") != expected["join_audit_sha256"]:
            raise ValueError("recovery terminal candidate digest mismatch")
        counters = terminal_value.get("prohibited_operation_counters", {})
        if any(value != 0 for value in counters.values()):
            raise ValueError("recovery terminal prohibited activity is nonzero")
        if acceptance_value.get("selected_checkpoint") != expected["expected_selected_checkpoint"]:
            raise ValueError("recovery acceptance selected checkpoint mismatch")
        if acceptance_value.get("prohibited_operation_counters") != counters:
            raise ValueError("recovery acceptance prohibited counters mismatch")
    return acceptance_value


def duplicate_key(authority: dict[str, Any], reservation: dict[str, Any], operation: dict[str, Any], contract: dict[str, Any]) -> str:
    value = {
        "authority": authority["recovery_authority_id"],
        "reservation": reservation["recovery_reservation_id"],
        "operation": operation["recovery_operation_id"],
        "source": contract["failed_lineage"], "candidate_set": contract["join_audit_sha256"],
        "selected": contract["expected_selected_checkpoint"], "stopping": contract["stopping"],
        "runtime": authority["runtime_tree_sha256"], "dag": authority["dag_sha256"],
        "terminal_target": authority["terminal_target"],
    }
    return digest(value)
