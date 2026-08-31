"""Kernel-locked, non-mutating recovery publication transaction."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import socket
import time
from pathlib import Path
from typing import Any

from p9_checkpoint_recovery import canonical_json

STATES = {"AUTHORIZED_NOT_STARTED", "ACQUIRING_LOCK", "STARTING", "VALIDATING_SOURCE", "DERIVING_CANDIDATES", "SELECTING_CHECKPOINT", "RECONSTRUCTING_STOPPING_BOUNDARY", "STAGING_TERMINAL_RECOVERY", "STAGING_ACCEPTANCE", "COMMITTING", "RECOVERY_ACCEPTED", "RECOVERY_BLOCKED", "RECOVERY_FAILED_NONMUTATING"}
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
    "RECOVERY_ACCEPTED": set(), "RECOVERY_BLOCKED": set(), "RECOVERY_FAILED_NONMUTATING": set(),
}


def digest(value: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.staging-{os.getpid()}")
    with temporary.open("wb") as stream:
        stream.write(canonical_json(value)); stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, path)
    try:
        directory = os.open(path.parent, os.O_RDONLY); os.fsync(directory); os.close(directory)
    except OSError:
        pass


class OperationState:
    """Canonical mutable state; owner/heartbeat never replace this record."""
    schema_version = "1.0.0"
    def __init__(self, path: str | Path, identity: dict[str, Any]):
        self.path, self.identity = Path(path), identity
        self.value = {"schema_version": self.schema_version, **identity, "state": "AUTHORIZED_NOT_STARTED", "previous_state": None, "state_sequence": 0, "committed": False, "last_completed_phase": None, "error_classification": None, "original_exception_summary": None, "release_status": "NOT_RELEASED"}
    def transition(self, state: str, **fields: Any) -> dict[str, Any]:
        prior = self.value["state"]
        if state not in STATES or state not in TRANSITIONS[prior]:
            raise ValueError(f"invalid recovery transition: {prior}->{state}")
        if state == "RECOVERY_ACCEPTED" and not fields.get("committed", self.value.get("committed")):
            raise ValueError("recovery acceptance requires canonical commit manifest")
        self.value.update(fields, state=state, previous_state=prior, state_sequence=int(self.value["state_sequence"]) + 1, transition_unix=time.time())
        atomic_json(self.path, self.value); return dict(self.value)


def resolve_committed(root: str | Path) -> dict[str, Any]:
    """The only downstream resolver: commit manifest is the sole commit point."""
    root = Path(root); manifest_path = root / "transaction_manifest.json"
    if not manifest_path.exists(): raise ValueError("no canonical recovery commit manifest")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("state") != "COMMITTED": raise ValueError("recovery transaction is not committed")
    terminal, acceptance = root / "terminal_recovery.json", root / "recovery_acceptance.json"
    if not terminal.exists() or not acceptance.exists(): raise ValueError("committed recovery payload incomplete")
    if manifest.get("terminal_sha256") != hashlib.sha256(terminal.read_bytes()).hexdigest() or manifest.get("acceptance_sha256") != hashlib.sha256(acceptance.read_bytes()).hexdigest(): raise ValueError("recovery committed hash mismatch")
    value = json.loads(acceptance.read_text())
    if value.get("status") != "PASS": raise ValueError("recovery acceptance is not accepted")
    return value


class RecoveryLock:
    """A descriptor-backed lock; records are evidence, never ownership."""
    def __init__(self, root: str | Path, duplicate_key: str, owner: dict[str, Any]):
        self.root, self.key, self.owner = Path(root), duplicate_key, owner
        self.path = self.root / f"{duplicate_key}.lock"; self.fd: int | None = None; self.sequence = 0

    def acquire(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(self.fd); self.fd = None
            raise RuntimeError("DUPLICATE_OPERATION_ACTIVE")
        atomic_json(self.root / f"{self.key}.owner.json", {"schema_version": "1.0.0", **self.owner, "kernel_lock_status": "HELD", "lock_path": str(self.path), "state": "ACQUIRING_LOCK"})
        self.heartbeat("ACQUIRING_LOCK", "kernel_lock_acquired")

    def heartbeat(self, state: str, phase: str) -> None:
        if self.fd is None: raise RuntimeError("recovery heartbeat without kernel lock")
        self.sequence += 1
        atomic_json(self.root / f"{self.key}.heartbeat.json", {"schema_version": "1.0.0", "duplicate_operation_key": self.key, "owner_pid": os.getpid(), "hostname": socket.gethostname(), "sequence": self.sequence, "wall_unix": time.time(), "state": state, "last_completed_phase": phase})

    def release(self, state: str) -> None:
        if self.fd is not None:
            self.heartbeat(state, "lock_release")
            fcntl.flock(self.fd, fcntl.LOCK_UN); os.close(self.fd); self.fd = None


def duplicate_key(authority: dict[str, Any], reservation: dict[str, Any], operation: dict[str, Any], contract: dict[str, Any]) -> str:
    value = {"authority": authority["recovery_authority_id"], "reservation": reservation["recovery_reservation_id"], "operation": operation["recovery_operation_id"], "source": contract["failed_lineage"], "candidate_set": contract["join_audit_sha256"], "selected": contract["expected_selected_checkpoint"], "stopping": contract["stopping"], "runtime": authority["runtime_tree_sha256"], "dag": authority["dag_sha256"], "terminal_target": authority["terminal_target"]}
    return digest(value)
