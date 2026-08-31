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


def digest(value: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.staging-{os.getpid()}")
    with temporary.open("wb") as stream:
        stream.write(canonical_json(value)); stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, path)


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
