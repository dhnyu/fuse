#!/usr/bin/env python3
"""Publish a recovery-only authorization from immutable failed-run evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from p9_checkpoint_recovery import audit_pairs, canonical_json, sha256_file

RUNTIME_FILES = ["_targets_p9_recovery.R", "R/research_p9_checkpoint_recovery.R", "targets/research_p9_checkpoint_recovery.R", "python/p9_checkpoint_recovery.py", "scripts/p9_checkpoint_recovery_authorization.py"]


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
    authority = {"schema_version": "1.0.0", "artifact_type": "p9_posttraining_recovery_authority", "recovery_contract_id": contract["recovery_contract_id"], "runtime_tree_sha256": manifest["runtime_tree_sha256"], "failed_run_id": failed["run_id"], "allowed_operations": ["immutable_evidence_validation", "candidate_derivation", "selection", "terminal_recovery", "recovery_acceptance"], "prohibited_operations": contract["prohibited_operations"]}
    authority["recovery_authority_id"] = "p9ra_" + _digest(authority)[:24]
    reservation = {"schema_version": "1.0.0", "artifact_type": "p9_posttraining_recovery_reservation", "recovery_authority_id": authority["recovery_authority_id"], "recovery_contract_id": contract["recovery_contract_id"], "status": "AUTHORIZED_NOT_STARTED", "operation": "READ_ONLY_TERMINAL_RECOVERY"}
    reservation["recovery_reservation_id"] = "p9rres_" + _digest(reservation)[:24]
    operation = {"schema_version": "1.0.0", "artifact_type": "p9_posttraining_recovery_operation", "recovery_reservation_id": reservation["recovery_reservation_id"], "failed_run_id": failed["run_id"], "expected_selected_checkpoint_id": selected["checkpoint_id"]}
    operation["recovery_operation_id"] = "p9rop_" + _digest(operation)[:24]
    acceptance = {"schema_version": "1.0.0", "status": "PASS", "recovery_authority_id": authority["recovery_authority_id"], "recovery_reservation_id": reservation["recovery_reservation_id"], "recovery_operation_id": operation["recovery_operation_id"], "runtime_tree_sha256": manifest["runtime_tree_sha256"], "expected_selected_checkpoint_id": selected["checkpoint_id"]}
    acceptance["recovery_authorization_acceptance_id"] = "p9rxacc_" + _digest(acceptance)[:24]
    out = Path(args.output) / authority["recovery_authority_id"]
    for name, value in (("runtime_manifest.json", manifest), ("checkpoint_join_audit.json", audit), ("recovery_contract.json", contract), ("recovery_authority.json", authority), ("recovery_reservation.json", reservation), ("recovery_operation.json", operation), ("recovery_authorization_acceptance.json", acceptance)):
        _atomic_json(out / name, value)
    print("P9_RECOVERY_OUTPUT=" + str(out))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("command", choices=["publish"]); parser.add_argument("--failed-run", required=True); parser.add_argument("--output", required=True)
    publish(parser.parse_args())
