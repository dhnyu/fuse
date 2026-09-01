"""P9 v2 control plane for future formal runs; no scientific computation lives here."""

from __future__ import annotations

import fcntl
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from p9_v2_canonical import canonical_json_bytes, canonical_sha256, deterministic_id, sha256_file
from p9_v2_ledger import LedgerWriter, fsync_directory, read_ledger, write_all
from p9_v2_replay import ReplayResult, replay_ledger
from p9_v2_schema import SCHEMA_VERSION, validate_instance


class TrainingControllerError(RuntimeError):
    """A production controller contract or durable evidence check failed."""


class DuplicateRunError(TrainingControllerError):
    """Another controller currently owns this scientific run key."""


def _without(value: dict[str, Any], *keys: str) -> dict[str, Any]:
    return {key: item for key, item in value.items() if key not in keys}


def make_worker_request(message_type: str, body: dict[str, Any]) -> dict[str, Any]:
    """Create one deterministic rank-zero request for the sole controller."""
    if message_type not in {"EVENT_PROPOSAL", "CHECKPOINT_COMMIT_REQUEST", "FAILURE_REPORT"}:
        raise TrainingControllerError("WORKER_IPC_MESSAGE_TYPE_INVALID")
    request_id = deterministic_id("p9req_", {"message_type": message_type, "body": body})
    value = {"schema_version": SCHEMA_VERSION, "message_type": message_type,
             "request_id": request_id, "body": body}
    validate_instance("worker_ipc", value)
    return value


def validate_worker_message(value: dict[str, Any]) -> None:
    validate_instance("worker_ipc", value)
    if value["message_type"] in {"EVENT_PROPOSAL", "CHECKPOINT_COMMIT_REQUEST", "FAILURE_REPORT"}:
        expected = deterministic_id("p9req_", {"message_type": value["message_type"], "body": value["body"]})
        if value["request_id"] != expected:
            raise TrainingControllerError("WORKER_IPC_REQUEST_ID_MISMATCH")


def worker_response(request_id: str, *, status: str, **body: Any) -> dict[str, Any]:
    value = {"schema_version": SCHEMA_VERSION, "message_type": "ACK" if status == "COMMITTED" else "NACK",
             "request_id": request_id, "body": {"status": status, **body}}
    validate_instance("worker_ipc", value)
    return value


def build_training_authority(*, configuration_id: str, configuration_hash: str,
                             scientific_implementation_hash: str, root_seed: int,
                             parents: dict[str, str],
                             parent_hashes: dict[str, str] | None = None,
                             p8_configuration_hash: str | None = None) -> dict[str, Any]:
    """Build, but do not publish, one content-addressed formal-run authority."""
    if configuration_id == "cfg_main":
        raise TrainingControllerError("CFG_MAIN_ALREADY_CANONICALLY_ACCEPTED")
    scientific = {
        "configuration_id": configuration_id,
        "configuration_hash": configuration_hash,
        "p8_configuration_hash": p8_configuration_hash or configuration_hash,
        "scientific_implementation_hash": scientific_implementation_hash,
        "selection_contract_id": "p9-selection-v2.1.0",
        "root_seed": int(root_seed),
        "evaluation_ancestry": False,
    }
    hashes = dict(sorted((parent_hashes or {
        key: canonical_sha256({"identity": value}) for key, value in parents.items()
    }).items()))
    if set(hashes) != set(parents):
        raise TrainingControllerError("PARENT_HASH_KEYS_MISMATCH")
    run_key = canonical_sha256({"scientific": scientific, "parents": parents, "parent_hashes": hashes})
    content = {
        "authority_kind": "FUTURE_FORMAL_TRAINING",
        "scope": "ONE_NEW_FORMAL_CONFIGURATION",
        "scientific_run_key": run_key,
        "scientific": scientific,
        "parents": dict(sorted(parents.items())),
        "parent_hashes": hashes,
        "execution_policy": {
            "world_size": 2,
            "backend": "nccl",
            "training_allowed": True,
            "resume_policy": "EXACT_COMMITTED_CHECKPOINT_ONLY",
            "validation_only_selection": True,
            "canonical_acceptance_handoff": "V2_B_V2_C_EXISTING_APIS",
        },
    }
    authority_hash = canonical_sha256(content)
    authority = {"schema_version": SCHEMA_VERSION, "identity": "p9authv2_" + authority_hash[:24],
                 "content_sha256": authority_hash, "content": content}
    validate_instance("training_authority", authority)
    return authority


def training_run_id(authority: dict[str, Any]) -> str:
    validate_instance("training_authority", authority)
    return deterministic_id("p9runv2_", {
        "authority_hash": authority["content_sha256"],
        "scientific_run_key": authority["content"]["scientific_run_key"],
    })


def validate_training_authority(authority: dict[str, Any]) -> None:
    validate_instance("training_authority", authority)
    observed = canonical_sha256(authority["content"])
    if observed != authority["content_sha256"] or authority["identity"] != "p9authv2_" + observed[:24]:
        raise TrainingControllerError("TRAINING_AUTHORITY_IDENTITY_MISMATCH")


@dataclass(frozen=True)
class StartupInputs:
    fuse_root: Path
    dissertation_root: Path
    retirement_manifest: Path
    p8_acceptance: Path
    p8_matrix: Path
    production_cache_root: Path
    production_cache_acceptance: Path
    writable_root: Path
    immutable_root: Path
    expected_dissertation_commit: str
    expected_retirement_id: str
    expected_p8_acceptance_id: str
    expected_cache_id: str
    expected_cache_acceptance_id: str
    expected_cache_manifest_sha256: str
    expected_parents: dict[str, str]
    minimum_free_bytes: int = 1_000_000_000


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def validate_startup(authority: dict[str, Any], inputs: StartupInputs, *, accepted_hashes: set[str],
                     accepted_configuration_ids: set[str] | None = None,
                     require_clean: bool = True, cuda_devices: int | None = None) -> dict[str, Any]:
    """Fail-closed production startup checks. This function creates no authority or run."""
    validate_training_authority(authority)
    failures: list[str] = []
    if _git(inputs.fuse_root, "branch", "--show-current") != "reduced": failures.append("FUSE_BRANCH_NOT_REDUCED")
    if require_clean and _git(inputs.fuse_root, "status", "--porcelain"): failures.append("FUSE_TREE_DIRTY")
    if _git(inputs.dissertation_root, "branch", "--show-current") != "reduced": failures.append("DISSERTATION_BRANCH_NOT_REDUCED")
    if _git(inputs.dissertation_root, "rev-parse", "HEAD") != inputs.expected_dissertation_commit: failures.append("METHODOLOGY_COMMIT_MISMATCH")
    if _git(inputs.dissertation_root, "status", "--porcelain"): failures.append("DISSERTATION_TREE_DIRTY")
    retirement = json.loads(inputs.retirement_manifest.read_text(encoding="utf-8"))
    try:
        validate_instance("v1_retirement_manifest", retirement)
    except Exception:
        failures.append("V1_RETIREMENT_INVALID")
    if retirement.get("retirement_id") != inputs.expected_retirement_id: failures.append("V1_RETIREMENT_INVALID")
    p8 = json.loads(inputs.p8_acceptance.read_text(encoding="utf-8"))
    if p8.get("acceptance_id") != inputs.expected_p8_acceptance_id or p8.get("evaluation_ancestry_count") != 0:
        failures.append("P8_ACCEPTANCE_INVALID")
    matrix = json.loads(inputs.p8_matrix.read_text(encoding="utf-8"))
    content = authority["content"]
    row = next((item for item in matrix.get("rows", [])
                if item.get("configuration_id") == content["scientific"]["configuration_id"]), None)
    if row is None or row.get("scientific_hash") != content["scientific"]["p8_configuration_hash"] or row.get("evaluation_ancestry") is not False:
        failures.append("P8_CONFIGURATION_INVALID")
    if content["parents"] != inputs.expected_parents: failures.append("SCIENTIFIC_PARENT_MISMATCH")
    if content["scientific"]["configuration_hash"] in accepted_hashes: failures.append("SCIENTIFIC_CONFIGURATION_ALREADY_ACCEPTED")
    if content["scientific"]["configuration_id"] in (accepted_configuration_ids or set()): failures.append("SCIENTIFIC_CONFIGURATION_ALREADY_ACCEPTED")
    if not inputs.production_cache_root.is_dir():
        failures.append("PRODUCTION_CACHE_MISSING")
    else:
        cache_manifest = inputs.production_cache_root / "production_cache_manifest.json"
        cache = json.loads(cache_manifest.read_text(encoding="utf-8"))
        if cache.get("cache_id") != inputs.expected_cache_id or sha256_file(cache_manifest) != inputs.expected_cache_manifest_sha256:
            failures.append("PRODUCTION_CACHE_IDENTITY_MISMATCH")
    cache_acceptance = json.loads(inputs.production_cache_acceptance.read_text(encoding="utf-8"))
    if cache_acceptance.get("acceptance_id") != inputs.expected_cache_acceptance_id or cache_acceptance.get("status") != "PASS":
        failures.append("PRODUCTION_CACHE_ACCEPTANCE_INVALID")
    guards = tuple(inputs.fuse_root / path for path in (
        "scripts/p9_formal_training.py", "scripts/p9_formal_authorization.py",
        "scripts/p9_formal_isolated_authorization.py", "scripts/p9_formal_reauthorization.py",
        "scripts/p9_checkpoint_recovery_authorization.py"))
    if any("retire_v1_cli" not in path.read_text(encoding="utf-8") for path in guards): failures.append("V1_EXECUTION_GUARD_INACTIVE")
    if inputs.writable_root.resolve() == inputs.immutable_root.resolve(): failures.append("WRITABLE_IMMUTABLE_ROOT_ALIAS")
    inputs.writable_root.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(inputs.writable_root).free < inputs.minimum_free_bytes: failures.append("INSUFFICIENT_DISK")
    if not os.access(inputs.production_cache_root, os.R_OK): failures.append("PRODUCTION_CACHE_UNREADABLE")
    if cuda_devices is not None and cuda_devices != 2: failures.append("TWO_GPU_PREFLIGHT_FAILED")
    if failures:
        raise TrainingControllerError(";".join(failures))
    return {"status": "PASS", "scientific_run_key": content["scientific_run_key"], "evaluation_ancestry": 0}


def accepted_scientific_configurations(canonical_root: str | Path, eligibility_path: str | Path) -> tuple[set[str], set[str]]:
    """Resolve explicitly eligible bundle configs; never enumerate a latest acceptance."""
    canonical = Path(canonical_root); eligibility = json.loads(Path(eligibility_path).read_text(encoding="utf-8"))
    validate_instance("acceptance_eligibility", eligibility)
    identifiers: set[str] = set(); hashes: set[str] = set()
    for entry in eligibility["entries"]:
        if entry["eligibility"] != "ELIGIBLE": continue
        acceptance = json.loads((canonical / "acceptances" / entry["acceptance_id"] / "acceptance.json").read_text(encoding="utf-8"))
        configuration = json.loads((canonical / "bundles" / acceptance["run_bundle_id"] /
                                    "config/scientific_configuration.json").read_text(encoding="utf-8"))
        if configuration.get("content_sha256") != canonical_sha256(configuration.get("content")):
            raise TrainingControllerError("ACCEPTED_CONFIGURATION_HASH_MISMATCH")
        value = configuration["content"].get("configuration_id")
        if not isinstance(value, str): raise TrainingControllerError("ACCEPTED_CONFIGURATION_ID_MISSING")
        identifiers.add(value); hashes.add(configuration["content_sha256"])
    return identifiers, hashes


class TrainingRunLock:
    """One kernel-backed, duplicate-run lock; owner bytes are non-authoritative."""
    def __init__(self, root: str | Path, scientific_run_key: str):
        self.root = Path(root); self.key = scientific_run_key; self._file = None

    def __enter__(self) -> "TrainingRunLock":
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / f"{self.key}.lock"
        self._file = path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(self._file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            self._file.close(); self._file = None
            raise DuplicateRunError("DUPLICATE_V2_CONTROLLER_START") from error
        self._file.seek(0); self._file.truncate(); self._file.write(f"pid={os.getpid()}\n")
        self._file.flush(); os.fsync(self._file.fileno())
        return self

    def __exit__(self, *_: object) -> None:
        assert self._file is not None
        fcntl.flock(self._file.fileno(), fcntl.LOCK_UN); self._file.close(); self._file = None


class TrainingController:
    """Canonical writer for event proposals produced by one future science worker."""
    def __init__(self, authority: dict[str, Any], ledger_root: str | Path, *, created_at: str):
        validate_training_authority(authority)
        self.authority = authority; self.run_id = training_run_id(authority); self.ledger_root = Path(ledger_root)
        if (self.ledger_root / "header.json").exists():
            self.writer = LedgerWriter.reopen_after_crash(self.ledger_root)
            if self.writer.header["run_id"] != self.run_id: raise TrainingControllerError("RUN_ID_MISMATCH")
        else:
            self.writer = LedgerWriter.initialize(self.ledger_root, run_id=self.run_id, created_at=created_at)

    def append(self, event_type: str, payload: dict[str, Any], *, occurred_at: str,
               writer_role: str = "controller", writer_id: str = "p9-v2-controller",
               fault: Callable[[str], None] | None = None) -> dict[str, Any]:
        kwargs: dict[str, Any] = {}
        if fault is not None: kwargs["fault"] = fault
        return self.writer.append(event_type=event_type, occurred_at=occurred_at, writer_id=writer_id,
                                  writer_role=writer_role, payload=payload, **kwargs)

    def replay(self) -> ReplayResult:
        return replay_ledger(self.ledger_root)

    def resume_allowed(self) -> bool:
        state = self.replay()
        return state.operational_state == "INTERRUPTED_RESUMABLE" and state.resumability_state == "EXACT_RESUME_ALLOWED"

    def close(self) -> Path:
        return self.writer.close()

    def commit_validation_checkpoint(
        self, staged_payload: str | Path, checkpoint_root: str | Path, *, completed_epoch: int,
        optimizer_update: int, validation_id: str, validation_retrieval_loss: float,
        mean_source_separation_margin: float, selector_state: dict[str, Any], queue: dict[str, Any],
        sampler: dict[str, Any], state_presence: dict[str, Any], occurred_at: str,
        fault: Callable[[str], None] = lambda _: None,
    ) -> dict[str, Any]:
        """Commit checkpoint bytes, then atomically bind them to one eligible ledger event."""
        path, manifest = publish_checkpoint(
            staged_payload, checkpoint_root, run_id=self.run_id, completed_epoch=completed_epoch,
            optimizer_update=optimizer_update, state_presence=state_presence, fault=fault)
        manifest_sha = sha256_file(path / "checkpoint_manifest.json")
        event_payload = {
            "completed_epoch": completed_epoch, "resume_epoch": completed_epoch + 1,
            "optimizer_update": optimizer_update, "validation_id": validation_id,
            "checkpoint_id": manifest["checkpoint_id"],
            "checkpoint_payload_sha256": manifest["payload"]["sha256"],
            "checkpoint_manifest_sha256": manifest_sha,
            "validation_retrieval_loss": validation_retrieval_loss,
            "mean_source_separation_margin": mean_source_separation_margin,
            "selector_state": selector_state, "queue": queue, "sampler": sampler,
            "state_presence": {key: bool(state_presence[key]) for key in (
                "online_model", "ema_model", "optimizer", "scheduler", "rng_states", "queue", "sampler",
                "early_stopping", "best_checkpoint", "validation_trace")},
            "atomic_completion_marker": {"protocol": "native_v2_atomic_commit", "status": "COMPLETE"},
            "source_run_id": self.run_id,
        }
        existing = [event for event in read_ledger(self.ledger_root).events
                    if event["event_type"] == "VALIDATION_CHECKPOINT_COMMITTED"
                    and event["payload"]["checkpoint_id"] == manifest["checkpoint_id"]]
        if existing:
            if len(existing) != 1 or existing[0]["payload"] != event_payload:
                raise TrainingControllerError("CHECKPOINT_LEDGER_BINDING_COLLISION")
            return existing[0]
        fault("after_checkpoint_commit_before_ledger_event")
        event = self.append("VALIDATION_CHECKPOINT_COMMITTED", event_payload, occurred_at=occurred_at,
                            writer_role="rank0", writer_id="science-rank0")
        fault("after_checkpoint_ledger_event_commit")
        return event

    def handle_worker_request(
        self, request: dict[str, Any], *, staging_root: str | Path,
        checkpoint_root: str | Path,
    ) -> dict[str, Any]:
        """Validate one request, durably apply it once, and return its ACK."""
        validate_worker_message(request)
        body = request["body"]
        if request["message_type"] == "EVENT_PROPOSAL":
            event = self.append(body["event_type"], body["payload"], occurred_at=body["occurred_at"],
                                writer_role=body["writer_role"], writer_id=body["writer_id"])
            return worker_response(request["request_id"], status="COMMITTED",
                                   event_id=event["event_id"], event_hash=event["event_hash"],
                                   event_sequence=event["event_sequence"])
        if request["message_type"] == "FAILURE_REPORT":
            failure = dict(body); occurred_at = failure.pop("occurred_at")
            event = self.append("TRAINING_FAILED", failure, occurred_at=occurred_at,
                                writer_role="controller", writer_id="p9-v2-controller")
            return worker_response(request["request_id"], status="COMMITTED",
                                   event_id=event["event_id"], event_hash=event["event_hash"],
                                   event_sequence=event["event_sequence"])
        if body["source_run_id"] != self.run_id:
            raise TrainingControllerError("CHECKPOINT_SOURCE_RUN_MISMATCH")
        if body["resume_epoch"] != body["completed_epoch"] + 1:
            raise TrainingControllerError("CHECKPOINT_RESUME_EPOCH_MISMATCH")
        stage_root = Path(staging_root).resolve()
        staged = (stage_root / body["staged_payload"]).resolve()
        if staged.parent.parent != (stage_root / "requests").resolve() or not staged.parent.name.startswith("p9stage_") or staged.name != "checkpoint.pt":
            raise TrainingControllerError("CHECKPOINT_STAGING_PATH_INVALID")
        if staged.is_symlink() or not staged.is_file():
            raise TrainingControllerError("CHECKPOINT_STAGING_PAYLOAD_INVALID")
        provisional = checkpoint_manifest(
            run_id=self.run_id, completed_epoch=body["completed_epoch"],
            optimizer_update=body["optimizer_update"], payload_sha256=sha256_file(staged),
            byte_size=staged.stat().st_size, state_presence=body["state_presence"])
        selector = dict(body["selector_state"])
        if body["current_candidate_selected"]:
            selector["best_checkpoint_id"] = provisional["checkpoint_id"]
        elif selector.get("best_checkpoint_id") is None:
            raise TrainingControllerError("CHECKPOINT_SELECTOR_BEST_MISSING")
        event = self.commit_validation_checkpoint(
            staged, checkpoint_root, completed_epoch=body["completed_epoch"],
            optimizer_update=body["optimizer_update"], validation_id=body["validation_id"],
            validation_retrieval_loss=body["validation_retrieval_loss"],
            mean_source_separation_margin=body["mean_source_separation_margin"],
            selector_state=selector, queue=body["queue"], sampler=body["sampler"],
            state_presence=body["state_presence"], occurred_at=body["occurred_at"])
        return worker_response(
            request["request_id"], status="COMMITTED", event_id=event["event_id"],
            event_hash=event["event_hash"], event_sequence=event["event_sequence"],
            checkpoint_id=event["payload"]["checkpoint_id"],
            checkpoint_payload_sha256=event["payload"]["checkpoint_payload_sha256"],
            checkpoint_manifest_sha256=event["payload"]["checkpoint_manifest_sha256"],
            selector_state=event["payload"]["selector_state"],
        )


def checkpoint_manifest(*, run_id: str, completed_epoch: int, optimizer_update: int,
                        payload_sha256: str, byte_size: int, state_presence: dict[str, Any]) -> dict[str, Any]:
    body = {
        "schema_version": SCHEMA_VERSION, "artifact_type": "p9_v2_checkpoint_commit",
        "run_id": run_id, "completed_epoch": completed_epoch, "resume_epoch": completed_epoch + 1,
        "optimizer_update": optimizer_update,
        "payload": {"relative_path": "checkpoint.pt", "sha256": payload_sha256, "byte_size": byte_size},
        "state_presence": state_presence,
    }
    digest = canonical_sha256(body)
    value = {**body, "checkpoint_id": "p9ck_" + digest[:24], "content_sha256": digest}
    validate_instance("checkpoint_commit", value)
    return value


def publish_checkpoint(staged_payload: str | Path, checkpoint_root: str | Path, *, run_id: str,
                       completed_epoch: int, optimizer_update: int, state_presence: dict[str, Any],
                       fault: Callable[[str], None] = lambda _: None) -> tuple[Path, dict[str, Any]]:
    """Atomically commit opaque worker bytes; the manifest rename is the commit point."""
    source = Path(staged_payload); root = Path(checkpoint_root); root.mkdir(parents=True, exist_ok=True)
    payload_hash = sha256_file(source); manifest = checkpoint_manifest(
        run_id=run_id, completed_epoch=completed_epoch, optimizer_update=optimizer_update,
        payload_sha256=payload_hash, byte_size=source.stat().st_size, state_presence=state_presence)
    destination = root / manifest["checkpoint_id"]
    if destination.exists():
        validate_checkpoint(destination, expected=manifest); return destination, manifest
    staging = root / f".{manifest['checkpoint_id']}.incomplete"
    staging.mkdir(exist_ok=False)
    fault("after_staging_create")
    payload_path = staging / "checkpoint.pt"
    with source.open("rb") as inp, payload_path.open("xb") as out:
        while block := inp.read(1024 * 1024): out.write(block)
        out.flush(); os.fsync(out.fileno())
    fault("after_payload_publish_before_manifest")
    raw = canonical_json_bytes(manifest)
    stage_manifest = staging / "checkpoint_manifest.json.incomplete"
    descriptor = os.open(stage_manifest, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o640)
    try: write_all(descriptor, raw); os.fsync(descriptor)
    finally: os.close(descriptor)
    if sha256_file(payload_path) != payload_hash: raise TrainingControllerError("CHECKPOINT_PAYLOAD_HASH_MISMATCH")
    os.replace(stage_manifest, staging / "checkpoint_manifest.json")
    fault("after_manifest_commit_before_directory_publish")
    fsync_directory(staging)
    os.replace(staging, destination)
    fault("after_checkpoint_directory_publish_before_fsync")
    fsync_directory(root)
    validate_checkpoint(destination, expected=manifest)
    return destination, manifest


def validate_checkpoint(root: str | Path, *, expected: dict[str, Any] | None = None) -> dict[str, Any]:
    root = Path(root); path = root / "checkpoint_manifest.json"
    if not path.is_file(): raise TrainingControllerError("CHECKPOINT_UNCOMMITTED")
    value = json.loads(path.read_text(encoding="utf-8")); validate_instance("checkpoint_commit", value)
    observed = canonical_sha256(_without(value, "checkpoint_id", "content_sha256"))
    if observed != value["content_sha256"] or value["checkpoint_id"] != "p9ck_" + observed[:24]:
        raise TrainingControllerError("CHECKPOINT_MANIFEST_IDENTITY_MISMATCH")
    payload = root / value["payload"]["relative_path"]
    if not payload.is_file() or payload.stat().st_size != value["payload"]["byte_size"] or sha256_file(payload) != value["payload"]["sha256"]:
        raise TrainingControllerError("CHECKPOINT_PAYLOAD_HASH_MISMATCH")
    if expected is not None and value != expected: raise TrainingControllerError("CHECKPOINT_COLLISION")
    return value
