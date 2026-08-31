#!/usr/bin/env python3
"""Publish a recovery-only authorization from immutable failed-run evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from p9_checkpoint_recovery import audit_pairs, canonical_json, recovery_terminal_payload, sha256_file
from p9_recovery_transaction import (
    RecoveryTransactionController,
    TransactionContext,
    atomic_json as transaction_json,
    digest as transaction_digest,
)

RUNTIME_FILES = ["_targets_p9_recovery.R", "R/research_p9_checkpoint_recovery.R", "targets/research_p9_checkpoint_recovery.R", "python/p9_checkpoint_recovery.py", "python/p9_recovery_transaction.py", "scripts/p9_checkpoint_recovery_authorization.py"]


def _digest(value: dict) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".staging-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(canonical_json(value)); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True); raise


def _runtime_manifest() -> dict:
    files = []
    for name in RUNTIME_FILES:
        path = ROOT / name
        if not path.exists():
            raise FileNotFoundError(f"recovery runtime file missing: {name}")
        files.append({"path": name, "sha256": sha256_file(path), "size_bytes": path.stat().st_size})
    value = {"schema_version": "1.0.0", "runtime_files": files,
             "prohibited_capabilities": ["training", "optimizer", "DDP", "GPU", "validation", "evaluation", "checkpoint_write"]}
    value["runtime_tree_sha256"] = _digest(value)
    return value


def publish(args: argparse.Namespace) -> None:
    failed_root = Path(args.failed_run)
    audit = audit_pairs(failed_root)
    failed = json.loads((failed_root / "attempt_state.json").read_text())
    manifest = _runtime_manifest(); selected = audit["selected_checkpoint"]
    contract = {"schema_version": "1.0.0", "artifact_type": "p9_posttraining_recovery_contract",
                "failed_lineage": {key: failed[key] for key in ("authority_id", "reservation_id", "attempt_id", "run_id", "runtime_tree_sha256")},
                "failed_terminal_state_sha256": sha256_file(failed_root / "terminal_failure.json"),
                "join_audit_sha256": audit["content_sha256"], "checkpoint_candidates": audit["candidates"],
                "expected_selected_checkpoint": selected,
                "stopping": {"reason": "EARLY_STOPPING_PATIENCE_EXHAUSTED", "stopping_epoch": 125, "stopping_update": 9500, "validation_events": 25, "patience": 4},
                "prohibited_operations": {"optimizer_updates": 0, "validation_runs": 0, "evaluation_queries": 0, "checkpoint_writes": 0, "ddp_launches": 0, "gpu_processes": 0}}
    contract["recovery_contract_id"] = "p9rec_" + _digest(contract)[:24]
    authority = {"schema_version": "1.0.0", "artifact_type": "p9_posttraining_recovery_authority", "recovery_contract_id": contract["recovery_contract_id"], "runtime_tree_sha256": manifest["runtime_tree_sha256"], "failed_run_id": failed["run_id"], "terminal_target": "p9_cfg_main_recovery_acceptance", "dag_sha256": sha256_file(ROOT / "targets/research_p9_checkpoint_recovery.R"), "lock_namespace": "/mnt/hdd002/dhnyu/fusedata/runtime/p9_recovery_locks", "supersedes": ["p9ra_8e32bacc3917acd1a91921c4", "p9rres_63586f0a27e1402f54bfa32b", "p9rop_1e1db7e73e8101739a960df9"], "allowed_operations": ["immutable_evidence_validation", "candidate_derivation", "selection", "terminal_recovery", "recovery_acceptance"], "prohibited_operations": contract["prohibited_operations"]}
    authority["recovery_authority_id"] = "p9ra_" + _digest(authority)[:24]
    reservation = {"schema_version": "1.0.0", "artifact_type": "p9_posttraining_recovery_reservation", "recovery_authority_id": authority["recovery_authority_id"], "recovery_contract_id": contract["recovery_contract_id"], "status": "AUTHORIZED_NOT_STARTED", "operation": "READ_ONLY_TERMINAL_RECOVERY"}
    reservation["recovery_reservation_id"] = "p9rres_" + _digest(reservation)[:24]
    operation = {"schema_version": "1.0.0", "artifact_type": "p9_posttraining_recovery_operation", "recovery_reservation_id": reservation["recovery_reservation_id"], "failed_run_id": failed["run_id"], "expected_selected_checkpoint_id": selected["checkpoint_id"]}
    operation["recovery_operation_id"] = "p9rop_" + _digest(operation)[:24]
    acceptance = {"schema_version": "1.0.0", "status": "PASS", "recovery_authority_id": authority["recovery_authority_id"], "recovery_reservation_id": reservation["recovery_reservation_id"], "recovery_operation_id": operation["recovery_operation_id"], "runtime_tree_sha256": manifest["runtime_tree_sha256"], "expected_selected_checkpoint_id": selected["checkpoint_id"]}
    acceptance["recovery_authorization_acceptance_id"] = "p9rxacc_" + _digest(acceptance)[:24]
    supersession = {"schema_version": "1.0.0", "artifact_type": "p9_recovery_supersession_correction", "supersedes": authority["supersedes"], "reason": "previous complete DAG lacked a recovery-operation kernel lock and durable state transaction", "replacement_authority_id": authority["recovery_authority_id"]}
    supersession["recovery_supersession_id"] = "p9rsup_" + _digest(supersession)[:24]
    out = Path(args.output) / authority["recovery_authority_id"]
    for name, value in (("runtime_manifest.json", manifest), ("checkpoint_join_audit.json", audit), ("recovery_contract.json", contract), ("recovery_authority.json", authority), ("recovery_reservation.json", reservation), ("recovery_operation.json", operation), ("recovery_authorization_acceptance.json", acceptance), ("recovery_supersession.json", supersession)):
        _atomic_json(out / name, value)
    print("P9_RECOVERY_OUTPUT=" + str(out))


def execute(args: argparse.Namespace) -> None:
    directory = Path(args.authorization_dir)
    reservation = json.loads((directory / "recovery_reservation.json").read_text())
    if os.environ.get("FUSE_P9_RECOVERY_RESERVATION_ID") != reservation["recovery_reservation_id"]:
        raise PermissionError("exact recovery reservation token required")
    if reservation["status"] != "AUTHORIZED_NOT_STARTED":
        raise ValueError("recovery reservation is not executable")
    contract = json.loads((directory / "recovery_contract.json").read_text())
    authority = json.loads((directory / "recovery_authority.json").read_text())
    operation = json.loads((directory / "recovery_operation.json").read_text())
    _validate_execution_inputs(authority, reservation, operation, contract, args)
    context = TransactionContext.create(
        authority=authority, reservation=reservation, operation=operation, contract=contract,
        lock_root=args.lock_root, output_root=args.output, store=args.store,
        launch_commit=os.popen("git rev-parse HEAD").read().strip(), synthetic=args.synthetic,
    )
    controller = RecoveryTransactionController(context)
    try:
        controller.acquire_and_start()
        controller.phase("VALIDATING_SOURCE", "authorization_and_source_validation_started")
        _validate_failed_source(Path(args.failed_run), contract)
        controller.phase("DERIVING_CANDIDATES", "source_hashes_validated")
        audit = audit_pairs(args.failed_run)
        if len(audit["rows"]) != 25 or any(row["classification"] != "EXACT_MATCH" for row in audit["rows"]):
            raise ValueError("recovery requires 25 EXACT_MATCH checkpoint candidates")
        controller.state.annotate(candidate_set_sha256=audit["content_sha256"], candidate_count=len(audit["candidates"]))
        controller.phase("SELECTING_CHECKPOINT", "candidate_join_validated")
        _require_expected_selection(audit["selected_checkpoint"], contract["expected_selected_checkpoint"])
        selection_sha256 = transaction_digest(audit["selected_checkpoint"])
        controller.phase("RECONSTRUCTING_STOPPING_BOUNDARY", "selection_validated", selection_sha256=selection_sha256)
        _require_stopping_boundary(contract["stopping"])
        stopping_sha256 = transaction_digest(contract["stopping"])
        terminal = recovery_terminal_payload(contract, audit)
        terminal.update({
            "recovery_authority_id": authority["recovery_authority_id"],
            "recovery_reservation_id": reservation["recovery_reservation_id"],
            "recovery_operation_id": operation["recovery_operation_id"],
            "recovery_transaction_id": context.transaction_id,
            "recovery_dag_sha256": authority["dag_sha256"],
        })
        terminal["terminal_recovery_id"] = "p9rt_" + _digest(terminal)[:24]
        acceptance = {
            "schema_version": "1.1.0", "artifact_type": "p9_recovery_acceptance", "status": "PASS",
            "terminal_recovery_id": terminal["terminal_recovery_id"],
            "selected_checkpoint": terminal["selected_checkpoint"],
            "source_failed_lineage": terminal["source_failed_lineage"],
            "historical_formal_run_state": "FAILED_NONRESUMABLE",
            "candidate_set_sha256": audit["content_sha256"],
            "zero_new_training_activity": True,
            "prohibited_operation_counters": contract["prohibited_operations"],
        }
        acceptance["recovery_acceptance_id"] = "p9racc_" + _digest(acceptance)[:24]
        hashes = controller.stage_pair(terminal, acceptance)
        resolved = controller.commit(
            hashes, candidate_set_sha256=audit["content_sha256"],
            selection_sha256=selection_sha256, stopping_sha256=stopping_sha256,
        )
        if resolved["recovery_acceptance_id"] != acceptance["recovery_acceptance_id"]:
            raise ValueError("canonical recovery resolver selection mismatch")
        print("P9_RECOVERY_TERMINAL_OUTPUT=" + str(context.final_root))
    except BaseException as error:
        if controller.committed:
            controller.state.annotate(post_commit_integrity_incident={
                "exception_class": type(error).__name__, "summary": str(error)[:1000],
            })
        else:
            controller.fail(error)
        raise
    finally:
        controller.release()


def _validate_execution_inputs(authority: dict, reservation: dict, operation: dict,
                               contract: dict, args: argparse.Namespace) -> None:
    if authority.get("recovery_contract_id") != contract.get("recovery_contract_id"):
        raise ValueError("recovery authority/contract mismatch")
    if reservation.get("recovery_authority_id") != authority.get("recovery_authority_id"):
        raise ValueError("recovery reservation/authority mismatch")
    if reservation.get("recovery_contract_id") != contract.get("recovery_contract_id"):
        raise ValueError("recovery reservation/contract mismatch")
    if operation.get("recovery_reservation_id") != reservation.get("recovery_reservation_id"):
        raise ValueError("recovery operation/reservation mismatch")
    if authority.get("terminal_target") != "p9_cfg_main_recovery_acceptance":
        raise ValueError("unexpected recovery terminal target")
    if not args.store:
        raise ValueError("recovery store is required")


def _validate_failed_source(failed_root: Path, contract: dict) -> None:
    state = json.loads((failed_root / "attempt_state.json").read_text())
    expected = contract["failed_lineage"]
    for source_key, state_key in (("authority_id", "authority_id"), ("reservation_id", "reservation_id"),
                                  ("attempt_id", "attempt_id"), ("run_id", "run_id"),
                                  ("runtime_tree_sha256", "runtime_tree_sha256")):
        if state.get(state_key) != expected.get(source_key):
            raise ValueError(f"source failed lineage mismatch: {source_key}")
    terminal = json.loads((failed_root / "terminal_failure.json").read_text())
    if terminal.get("state") != "FAILED_NONRESUMABLE":
        raise ValueError("source formal terminal state is not FAILED_NONRESUMABLE")
    if sha256_file(failed_root / "terminal_failure.json") != contract["failed_terminal_state_sha256"]:
        raise ValueError("source terminal failure hash mismatch")


def _require_expected_selection(actual: dict, expected: dict) -> None:
    for key in ("checkpoint_id", "epoch", "validation_retrieval_loss", "mean_source_separation_margin",
                "checkpoint_payload_sha256", "checkpoint_manifest_sha256"):
        if actual.get(key) != expected.get(key):
            raise ValueError(f"deterministic recovery selection mismatch: {key}")


def _require_stopping_boundary(stopping: dict) -> None:
    expected = {"reason": "EARLY_STOPPING_PATIENCE_EXHAUSTED", "stopping_epoch": 125,
                "stopping_update": 9500, "validation_events": 25, "patience": 4}
    if stopping != expected:
        raise ValueError("recovery stopping-boundary contract mismatch")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("command", choices=["publish", "execute"]); parser.add_argument("--failed-run", required=True); parser.add_argument("--output", required=True); parser.add_argument("--authorization-dir"); parser.add_argument("--lock-root", default="/mnt/hdd002/dhnyu/fusedata/runtime/p9_recovery_locks"); parser.add_argument("--store", default=""); parser.add_argument("--synthetic", action="store_true")
    args = parser.parse_args()
    if args.command == "publish": publish(args)
    else:
        if not args.authorization_dir: parser.error("--authorization-dir is required for execute")
        execute(args)
