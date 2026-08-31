"""Fail-closed contracts shared by the dedicated P9 formal runner.

This module contains execution mechanics only. It never authorizes or starts a
training attempt on import.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import socket
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import torch

from canonical_config import canonical_json_bytes

SCHEMA_VERSION = "1.0.0"
FORMAL_STATES = (
    "AUTHORIZED_NOT_STARTED", "STARTING", "RUNNING", "INTERRUPTED_RESUMABLE",
    "FAILED_NONRESUMABLE", "COMPLETED_PENDING_VALIDATION", "ACCEPTED", "REJECTED",
)
TERMINAL_STATES = {"FAILED_NONRESUMABLE", "ACCEPTED", "REJECTED"}
TRANSITIONS = {
    "AUTHORIZED_NOT_STARTED": {"STARTING"},
    "STARTING": {"RUNNING", "FAILED_NONRESUMABLE"},
    "RUNNING": {"INTERRUPTED_RESUMABLE", "FAILED_NONRESUMABLE", "COMPLETED_PENDING_VALIDATION"},
    "INTERRUPTED_RESUMABLE": {"STARTING", "FAILED_NONRESUMABLE"},
    "COMPLETED_PENDING_VALIDATION": {"ACCEPTED", "REJECTED"},
    "FAILED_NONRESUMABLE": set(), "ACCEPTED": set(), "REJECTED": set(),
}
REQUIRED_DUPLICATE_FIELDS = (
    "configuration_identity", "seed_identity", "p8_acceptance_id",
    "p7_runtime_acceptance_id", "p9_readiness_id", "production_cache_acceptance_id",
    "p9_formal_authority_id", "authorized_execution_identity",
    "scientific_implementation_commit", "world_size",
)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def sha256_file(path: str | Path) -> str:
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def atomic_json(path: str | Path, payload: Any) -> Path:
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_bytes(canonical_json_bytes(payload)); os.replace(temporary, path)
    return path


def runtime_tree_manifest(root: str | Path, files: Iterable[str]) -> dict[str, Any]:
    root = Path(root).resolve(); names = sorted(set(files))
    if not names:
        raise ValueError("formal runtime file set is empty")
    rows = []
    for name in names:
        path = root / name
        if not path.is_file() or path.resolve().parent == root.parent:
            raise ValueError(f"formal runtime file is missing: {name}")
        rows.append({"path": name, "size_bytes": path.stat().st_size, "sha256": sha256_file(path)})
    value = {"schema_version": SCHEMA_VERSION, "files": rows}
    value["runtime_tree_sha256"] = digest(value)
    return value


def git_head(root: str | Path) -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()


def verify_execution_tree(root: str | Path, authority: dict[str, Any]) -> dict[str, Any]:
    expected = authority["execution_contract"]
    observed = runtime_tree_manifest(root, expected["runtime_files"])
    if observed["runtime_tree_sha256"] != expected["runtime_tree_sha256"]:
        raise ValueError("formal runtime tree differs from the authorized implementation")
    head = git_head(root); implementation = expected["implementation_commit"]
    if head != implementation:
        if not expected.get("allow_byte_identical_descendant", False):
            raise ValueError("formal launch commit is not the authorized implementation commit")
        status = subprocess.run(["git", "merge-base", "--is-ancestor", implementation, head], cwd=root)
        if status.returncode != 0:
            raise ValueError("formal launch commit is not a descendant of the authorized implementation")
    return {**observed, "implementation_commit": implementation, "actual_launch_commit": head}


def duplicate_key(fields: dict[str, Any]) -> str:
    missing = [key for key in REQUIRED_DUPLICATE_FIELDS if key not in fields]
    if missing:
        raise ValueError(f"incomplete formal duplicate key: {', '.join(missing)}")
    payload = {key: fields[key] for key in REQUIRED_DUPLICATE_FIELDS}
    if int(payload["world_size"]) != 2:
        raise ValueError("P9 formal execution requires world_size=2")
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def transition(current: str, requested: str) -> str:
    if current not in TRANSITIONS or requested not in FORMAL_STATES:
        raise ValueError("unknown formal attempt state")
    if requested not in TRANSITIONS[current]:
        raise ValueError(f"invalid formal attempt transition: {current} -> {requested}")
    return requested


@dataclass
class FormalAttemptLock:
    """Kernel lock plus durable, validated ownership and heartbeat records."""

    root: Path
    identity: dict[str, Any]
    stream: Any = field(init=False, default=None)
    owner_path: Path = field(init=False)
    heartbeat_path: Path = field(init=False)

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        key = self.identity["duplicate_key"]
        self.owner_path = self.root / f"{key}.owner.json"
        self.heartbeat_path = self.root / f"{key}.heartbeat.json"

    def acquire(self) -> dict[str, Any]:
        self.root.mkdir(parents=True, exist_ok=True)
        lock_path = self.root / f"{self.identity['duplicate_key']}.lock"
        self.stream = lock_path.open("a+")
        try:
            fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            self.stream.close(); self.stream = None
            raise RuntimeError("formal attempt duplicate lock is already owned") from error
        if self.owner_path.exists():
            owner = json.loads(self.owner_path.read_text())
            if owner.get("terminal_state") not in TERMINAL_STATES:
                self.release_kernel_only()
                raise RuntimeError("durable formal owner record exists; stale recovery requires authorization")
        now = time.time()
        owner = {"schema_version": SCHEMA_VERSION, **self.identity, "owner_pid": os.getpid(),
                 "hostname": socket.gethostname(), "acquired_unix": now,
                 "state": "STARTING", "terminal_state": None}
        atomic_json(self.owner_path, owner); self.heartbeat("STARTING")
        return owner

    def heartbeat(self, state: str) -> None:
        if self.stream is None:
            raise RuntimeError("cannot heartbeat an unowned formal lock")
        atomic_json(self.heartbeat_path, {"schema_version": SCHEMA_VERSION,
                    "duplicate_key": self.identity["duplicate_key"], "owner_pid": os.getpid(),
                    "hostname": socket.gethostname(), "state": state, "heartbeat_unix": time.time()})

    def release_kernel_only(self) -> None:
        if self.stream is not None:
            fcntl.flock(self.stream.fileno(), fcntl.LOCK_UN); self.stream.close(); self.stream = None

    def release_terminal(self, state: str) -> None:
        if state not in TERMINAL_STATES:
            raise ValueError("formal lock can only be released after durable terminal publication")
        owner = json.loads(self.owner_path.read_text()); owner["state"] = state
        owner["terminal_state"] = state; owner["released_unix"] = time.time()
        atomic_json(self.owner_path, owner); self.heartbeat(state); self.release_kernel_only()


def checkpoint_manifest(state: dict[str, Any], payload_path: Path) -> dict[str, Any]:
    from p7_training import state_content_digest
    required = ("online_model", "ema_model", "optimizer", "scheduler", "progress", "sampler",
                "rng_states", "queue", "early_stopping", "best_checkpoint", "validation_trace",
                "lineage", "world_size")
    missing = [key for key in required if key not in state]
    if missing:
        raise ValueError(f"formal checkpoint state is incomplete: {', '.join(missing)}")
    if int(state["world_size"]) != 2:
        raise ValueError("formal checkpoint world size mismatch")
    content = state_content_digest(state)
    return {"schema_version": SCHEMA_VERSION, "artifact_type": "p9_resume_checkpoint_manifest",
            "checkpoint_id": "p9ck_" + content[:24], "state_content_sha256": content,
            "payload": {"filename": payload_path.name, "size_bytes": payload_path.stat().st_size,
                        "sha256": sha256_file(payload_path)}, "lineage": state["lineage"],
            "epoch": int(state["progress"]["epoch"]),
            "global_update": int(state["progress"]["global_update"])}


def save_checkpoint_atomic(root: str | Path, state: dict[str, Any]) -> dict[str, Any]:
    root = Path(root); root.mkdir(parents=True, exist_ok=True)
    temporary = root / f".checkpoint.pt.tmp-{os.getpid()}"; final = root / "checkpoint.pt"
    torch.save(state, temporary); os.replace(temporary, final)
    manifest = checkpoint_manifest(state, final); atomic_json(root / "checkpoint_manifest.json", manifest)
    return manifest


def load_checkpoint(root: str | Path, expected_lineage: dict[str, Any]) -> dict[str, Any]:
    from p7_training import state_content_digest
    root = Path(root); manifest = json.loads((root / "checkpoint_manifest.json").read_text())
    payload = root / manifest["payload"]["filename"]
    if (payload.stat().st_size != int(manifest["payload"]["size_bytes"]) or
            sha256_file(payload) != manifest["payload"]["sha256"]):
        raise ValueError("formal checkpoint payload corruption")
    state = torch.load(payload, map_location="cpu", weights_only=False)
    if state.get("lineage") != expected_lineage or state_content_digest(state) != manifest["state_content_sha256"]:
        raise ValueError("formal checkpoint lineage or content mismatch")
    if int(state.get("world_size", 0)) != 2:
        raise ValueError("formal checkpoint DDP contract mismatch")
    return state


def validate_validation_event(event: dict[str, Any]) -> None:
    if (event.get("query_count"), event.get("gallery_count")) != (800, 400):
        raise ValueError("formal validation population mismatch")
    for key in ("missing_count", "duplicate_count", "evaluation_queries_consumed"):
        if int(event.get(key, -1)) != 0:
            raise ValueError(f"formal validation gate failed: {key}")
    for key in ("validation_retrieval_loss", "mean_source_separation_margin"):
        if not isinstance(event.get(key), (int, float)) or not torch.isfinite(torch.tensor(event[key])):
            raise ValueError(f"non-finite formal validation metric: {key}")


def candidate_is_better(candidate: dict[str, Any], best: dict[str, Any] | None,
                        tie_threshold: float = 1e-4) -> bool:
    validate_validation_event(candidate)
    if best is None:
        return True
    validate_validation_event(best)
    loss_delta = float(candidate["validation_retrieval_loss"]) - float(best["validation_retrieval_loss"])
    if abs(loss_delta) >= tie_threshold:
        return loss_delta < 0
    margin_delta = float(candidate["mean_source_separation_margin"]) - float(best["mean_source_separation_margin"])
    if margin_delta != 0:
        return margin_delta > 0
    return int(candidate["epoch"]) < int(best["epoch"])


@dataclass
class SelectionState:
    patience_limit: int = 4
    best: dict[str, Any] | None = None
    events_without_improvement: int = 0
    history: list[dict[str, Any]] = field(default_factory=list)

    def update(self, event: dict[str, Any]) -> dict[str, Any]:
        improved = candidate_is_better(event, self.best)
        if improved:
            self.best = dict(event); self.events_without_improvement = 0
        else:
            self.events_without_improvement += 1
        row = {**event, "selected_as_best": improved,
               "events_without_improvement": self.events_without_improvement}
        self.history.append(row)
        return {"improved": improved, "stop": self.events_without_improvement >= self.patience_limit,
                "best": self.best}


def terminal_acceptance_payload(run: dict[str, Any], selected: dict[str, Any],
                                execution: dict[str, Any]) -> dict[str, Any]:
    if not run.get("formal_attempt") or run.get("runner_class") != "P9_FORMAL":
        raise ValueError("bounded/non-formal output cannot produce P9 acceptance")
    if execution.get("state") != "COMPLETED_PENDING_VALIDATION":
        raise ValueError("P9 terminal execution is not acceptance-ready")
    if selected.get("checkpoint_id") not in execution.get("checkpoint_ids", []):
        raise ValueError("selected checkpoint is not part of the formal run")
    payload = {"schema_version": SCHEMA_VERSION, "artifact_type": "p9_attempt_acceptance",
               "status": "PASS", "run_id": run["run_id"], "attempt_id": run["attempt_id"],
               "selected_checkpoint_id": selected["checkpoint_id"], "parents": run["parents"],
               "evaluation_queries_consumed": 0}
    payload["content_sha256"] = digest(payload); payload["acceptance_id"] = "p9acc_" + payload["content_sha256"][:24]
    return payload
