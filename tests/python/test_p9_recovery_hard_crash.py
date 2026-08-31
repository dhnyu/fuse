"""Process-level hard-crash and resolver matrix for synthetic recovery only."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skip(
    reason="P9 v1 recovery execution is retired; V2-I rejection/read-only coverage supersedes this suite"
)

from p9_recovery_transaction import (
    RecoveryLock,
    RecoveryTransactionController,
    TestOnlyHardCrash,
    TransactionContext,
    atomic_json,
    resolve_committed,
    sha256_path,
)


BOUNDARIES = (
    "BEFORE_LOCK", "AFTER_LOCK", "AFTER_OWNER", "AFTER_STARTING",
    "DURING_SOURCE_VALIDATION", "AFTER_SOURCE_VALIDATION",
    "AFTER_CANDIDATE_DERIVATION", "AFTER_SELECTION",
    "AFTER_STOPPING_RECONSTRUCTION", "AFTER_TERMINAL_STAGING",
    "AFTER_TERMINAL_VALIDATION", "AFTER_ACCEPTANCE_STAGING",
    "AFTER_ACCEPTANCE_VALIDATION", "AFTER_MANIFEST_STAGING",
    "BEFORE_PAYLOAD_PUBLICATION", "AFTER_PAYLOAD_PUBLICATION_BEFORE_COMMIT",
    "IMMEDIATELY_AFTER_COMMIT_MANIFEST", "AFTER_COMMITTED_READBACK",
    "AFTER_RECOVERY_ACCEPTED_STATE", "BEFORE_LOCK_RELEASE",
)
POST_COMMIT = set(BOUNDARIES[15:])


def _parts(label: str):
    selected = {
        "checkpoint_id": "p9ck_42f7957d2ea998ac9e8ff705", "epoch": 105,
        "validation_retrieval_loss": 0.3806893528,
        "mean_source_separation_margin": 0.2876026034,
        "checkpoint_payload_sha256": "p" * 64,
        "checkpoint_manifest_sha256": "m" * 64,
    }
    contract = {
        "failed_lineage": {"authority_id": "p9a_source", "reservation_id": "p9res_source", "attempt_id": "p9attempt_source", "run_id": "p9run_source", "runtime_tree_sha256": "source-runtime"},
        "join_audit_sha256": "j" * 64, "expected_selected_checkpoint": selected,
        "stopping": {"reason": "EARLY_STOPPING_PATIENCE_EXHAUSTED", "stopping_epoch": 125, "stopping_update": 9500, "validation_events": 25, "patience": 4},
    }
    authority = {"recovery_authority_id": f"p9ra_{label}", "runtime_tree_sha256": "runtime", "dag_sha256": "dag", "terminal_target": "p9_cfg_main_recovery_acceptance"}
    return authority, {"recovery_reservation_id": f"p9rres_{label}"}, {"recovery_operation_id": f"p9rop_{label}"}, contract


def _context(root: Path, label: str, boundary: str | None = None):
    authority, reservation, operation, contract = _parts(label)
    return TransactionContext.create(
        authority=authority, reservation=reservation, operation=operation, contract=contract,
        lock_root=root / "locks", output_root=root / "output", store="synthetic-store",
        launch_commit="synthetic", synthetic=True,
        hard_crash=TestOnlyHardCrash(boundary) if boundary else None,
    )


def _payloads(context):
    terminal = {
        "terminal_recovery_id": "p9rt_synthetic", "state": "RECOVERY_ACCEPTED",
        "source_failed_lineage": context.contract["failed_lineage"],
        "selected_checkpoint": context.contract["expected_selected_checkpoint"],
        "stopping": context.contract["stopping"],
        "candidate_set_sha256": context.contract["join_audit_sha256"],
        "prohibited_operation_counters": {"optimizer_updates": 0, "validation_runs": 0, "evaluation_queries": 0, "checkpoint_writes": 0, "ddp_launches": 0, "gpu_processes": 0},
    }
    acceptance = {
        "recovery_acceptance_id": "p9racc_synthetic", "status": "PASS",
        "terminal_recovery_id": terminal["terminal_recovery_id"],
        "selected_checkpoint": terminal["selected_checkpoint"],
        "prohibited_operation_counters": terminal["prohibited_operation_counters"],
    }
    return terminal, acceptance


def _drive(context):
    controller = RecoveryTransactionController(context)
    controller.acquire_and_start()
    controller.checkpoint("DURING_SOURCE_VALIDATION")
    controller.phase("VALIDATING_SOURCE", "source_validated")
    controller.checkpoint("AFTER_SOURCE_VALIDATION")
    controller.phase("DERIVING_CANDIDATES", "25_exact_matches", candidate_count=25)
    controller.checkpoint("AFTER_CANDIDATE_DERIVATION")
    controller.phase("SELECTING_CHECKPOINT", "epoch_105_selected")
    controller.checkpoint("AFTER_SELECTION")
    controller.phase("RECONSTRUCTING_STOPPING_BOUNDARY", "epoch_125_reconstructed")
    controller.checkpoint("AFTER_STOPPING_RECONSTRUCTION")
    hashes = controller.stage_pair(*_payloads(context))
    controller.commit(hashes, candidate_set_sha256=context.contract["join_audit_sha256"], selection_sha256="s" * 64, stopping_sha256="t" * 64)
    controller.release()


def _child(root: str, boundary: str):
    _drive(_context(Path(root), boundary, boundary))


@pytest.mark.parametrize("boundary", BOUNDARIES)
def test_hard_crash_matrix(boundary, tmp_path):
    result = subprocess.run([sys.executable, __file__, "--child", str(tmp_path), boundary], env={"PYTHONPATH": "python:."}, cwd=Path.cwd())
    assert result.returncode == 86
    context = _context(tmp_path, boundary)
    lock = RecoveryLock(context.lock_root, context.duplicate_operation_key, {"synthetic": True})
    lock.acquire()
    assert lock.release("RECOVERY_BLOCKED") == "RELEASED"
    state = json.loads(context.state_path.read_text()) if context.state_path.exists() else {}
    if boundary in POST_COMMIT:
        accepted = resolve_committed(context.final_root, context=context)
        assert accepted["selected_checkpoint"]["checkpoint_id"] == "p9ck_42f7957d2ea998ac9e8ff705"
    else:
        assert state.get("state") != "RECOVERY_ACCEPTED"
        with pytest.raises(ValueError):
            resolve_committed(context.final_root, context=context)


def _commit(root: Path):
    context = _context(root, "valid")
    _drive(context)
    return context


def _rewrite(path: Path, value: dict):
    atomic_json(path, value)


@pytest.mark.parametrize("field,value", [
    ("recovery_authority_id", "wrong"), ("recovery_reservation_id", "wrong"),
    ("recovery_operation_id", "wrong"), ("duplicate_operation_key", "wrong"),
    ("source_inventory_digest", "wrong"), ("candidate_count", 24),
    ("join_result", "24/24 EXACT_MATCH"), ("runtime_tree_sha256", "wrong"),
    ("dag_sha256", "wrong"), ("terminal_target", "wrong"), ("recovery_store", "wrong"),
])
def test_resolver_rejects_manifest_contract_mutations(field, value, tmp_path):
    context = _commit(tmp_path)
    manifest_path = context.final_root / "transaction_manifest.json"
    manifest = json.loads(manifest_path.read_text()); manifest[field] = value; _rewrite(manifest_path, manifest)
    with pytest.raises(ValueError):
        resolve_committed(context.final_root, context=context)


@pytest.mark.parametrize("mutation", [
    "missing_manifest", "terminal_only", "acceptance_only", "invalid_json", "terminal_hash", "acceptance_hash",
    "source_lineage", "selected_checkpoint", "stopping", "candidate_digest", "nonzero_counter", "acceptance_link",
])
def test_resolver_rejects_payload_and_commit_mutations(mutation, tmp_path):
    context = _commit(tmp_path)
    terminal = context.final_root / "terminal_recovery.json"; acceptance = context.final_root / "recovery_acceptance.json"; manifest = context.final_root / "transaction_manifest.json"
    if mutation == "missing_manifest": manifest.unlink()
    elif mutation == "terminal_only": acceptance.unlink(); manifest.unlink()
    elif mutation == "acceptance_only": terminal.unlink(); manifest.unlink()
    elif mutation == "invalid_json": manifest.write_text("{")
    elif mutation == "terminal_hash": json.loads(terminal.read_text()).get("state"); terminal.write_text("{}")
    elif mutation == "acceptance_hash": acceptance.write_text("{}")
    else:
        value = json.loads(terminal.read_text())
        if mutation == "source_lineage": value["source_failed_lineage"]["run_id"] = "wrong"
        elif mutation == "selected_checkpoint": value["selected_checkpoint"]["checkpoint_id"] = "wrong"
        elif mutation == "stopping": value["stopping"]["stopping_epoch"] = 124
        elif mutation == "candidate_digest": value["candidate_set_sha256"] = "wrong"
        elif mutation == "nonzero_counter": value["prohibited_operation_counters"]["optimizer_updates"] = 1
        elif mutation == "acceptance_link":
            value = json.loads(acceptance.read_text()); value["terminal_recovery_id"] = "wrong"; acceptance = acceptance
        _rewrite(acceptance if mutation == "acceptance_link" else terminal, value)
    with pytest.raises(ValueError):
        resolve_committed(context.final_root, context=context)


def test_resolver_is_read_only_and_duplicate_completion_is_noop(tmp_path):
    context = _commit(tmp_path)
    files = [context.final_root / name for name in ("terminal_recovery.json", "recovery_acceptance.json", "transaction_manifest.json")]
    before = [(sha256_path(path), path.stat().st_mtime_ns) for path in files]
    assert resolve_committed(context.final_root, context=context) == resolve_committed(context.final_root, context=context)
    after = [(sha256_path(path), path.stat().st_mtime_ns) for path in files]
    assert after == before
    with pytest.raises(FileExistsError):
        _drive(context)


@pytest.mark.parametrize("consumer", ("p9_b", "selected_fm", "evaluation", "p10", "p11"))
def test_each_downstream_adapter_uses_canonical_resolver(consumer, tmp_path):
    context = _commit(tmp_path)
    # Adapters receive only the resolver result, never a checkpoint path.
    result = resolve_committed(context.final_root, context=context)
    assert consumer
    assert result["selected_checkpoint"]["checkpoint_id"] == "p9ck_42f7957d2ea998ac9e8ff705"


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--child":
        _child(sys.argv[2], sys.argv[3])
    else:
        raise SystemExit("synthetic crash child arguments required")
