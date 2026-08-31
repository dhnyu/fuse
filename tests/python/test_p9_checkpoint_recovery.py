import hashlib
import json
from argparse import Namespace
from pathlib import Path

import pytest

from p9_checkpoint_recovery import validation_epoch_from_manifest
from p9_recovery_transaction import (
    OperationState,
    RecoveryLock,
    RecoveryTransactionController,
    TransactionContext,
    atomic_json,
    resolve_committed,
)
from scripts import p9_checkpoint_recovery_authorization as recovery_entry


def test_validation_epoch_is_resume_epoch_minus_one():
    assert validation_epoch_from_manifest({"epoch": 106}) == 105


def test_validation_epoch_rejects_invalid_resume_epoch():
    try:
        validation_epoch_from_manifest({"epoch": 1})
    except ValueError as error:
        assert "resume epoch" in str(error)
    else:
        raise AssertionError("invalid resume epoch must fail closed")


def test_recovery_kernel_lock_rejects_second_owner(tmp_path):
    first = RecoveryLock(tmp_path, "same", {"owner": "one"})
    second = RecoveryLock(tmp_path, "same", {"owner": "two"})
    first.acquire()
    try:
        with pytest.raises(RuntimeError, match="DUPLICATE_OPERATION_ACTIVE"):
            second.acquire()
    finally:
        first.release("RECOVERY_BLOCKED")


def test_state_machine_and_commit_resolver(tmp_path):
    state = OperationState(tmp_path / "state.json", {"synthetic": True})
    for step in ("ACQUIRING_LOCK", "STARTING", "VALIDATING_SOURCE", "DERIVING_CANDIDATES", "SELECTING_CHECKPOINT", "RECONSTRUCTING_STOPPING_BOUNDARY", "STAGING_TERMINAL_RECOVERY", "STAGING_ACCEPTANCE", "COMMITTING"):
        state.transition(step)
    terminal = {"terminal_recovery_id": "p9rt_synthetic", "state": "RECOVERY_ACCEPTED"}
    acceptance = {"status": "PASS", "terminal_recovery_id": "p9rt_synthetic"}
    atomic_json(tmp_path / "terminal_recovery.json", terminal); atomic_json(tmp_path / "recovery_acceptance.json", acceptance)
    atomic_json(tmp_path / "transaction_manifest.json", {"state": "COMMITTED", "terminal_sha256": hashlib.sha256((tmp_path / "terminal_recovery.json").read_bytes()).hexdigest(), "acceptance_sha256": hashlib.sha256((tmp_path / "recovery_acceptance.json").read_bytes()).hexdigest()})
    state.transition("RECOVERY_ACCEPTED", committed=True)
    assert resolve_committed(tmp_path)["status"] == "PASS"


def _synthetic_context(tmp_path):
    contract = {
        "failed_lineage": {"authority_id": "p9a_source", "reservation_id": "p9res_source", "attempt_id": "p9attempt_source", "run_id": "p9run_source", "runtime_tree_sha256": "source-runtime"},
        "join_audit_sha256": "a" * 64,
        "expected_selected_checkpoint": {"checkpoint_id": "p9ck_42f7957d2ea998ac9e8ff705"},
        "stopping": {"reason": "EARLY_STOPPING_PATIENCE_EXHAUSTED", "stopping_epoch": 125, "stopping_update": 9500, "validation_events": 25, "patience": 4},
    }
    authority = {"recovery_authority_id": "p9ra_synthetic", "runtime_tree_sha256": "runtime", "dag_sha256": "dag", "terminal_target": "p9_cfg_main_recovery_acceptance"}
    reservation = {"recovery_reservation_id": "p9rres_synthetic"}
    operation = {"recovery_operation_id": "p9rop_synthetic"}
    return TransactionContext.create(
        authority=authority, reservation=reservation, operation=operation, contract=contract,
        lock_root=tmp_path / "locks", output_root=tmp_path / "output", store="synthetic-store",
        launch_commit="synthetic", synthetic=True,
    )


def _synthetic_payloads(context):
    selected = context.contract["expected_selected_checkpoint"]
    terminal = {
        "terminal_recovery_id": "p9rt_synthetic", "state": "RECOVERY_ACCEPTED",
        "source_failed_lineage": context.contract["failed_lineage"],
        "selected_checkpoint": selected, "stopping": context.contract["stopping"],
        "candidate_set_sha256": context.contract["join_audit_sha256"],
        "prohibited_operation_counters": {"optimizer_updates": 0},
    }
    acceptance = {
        "recovery_acceptance_id": "p9racc_synthetic", "status": "PASS",
        "terminal_recovery_id": "p9rt_synthetic", "selected_checkpoint": selected,
        "prohibited_operation_counters": {"optimizer_updates": 0},
    }
    return terminal, acceptance


def test_controller_commits_only_after_all_durable_phases(tmp_path):
    context = _synthetic_context(tmp_path)
    controller = RecoveryTransactionController(context)
    controller.acquire_and_start()
    controller.phase("VALIDATING_SOURCE", "source_validated")
    controller.phase("DERIVING_CANDIDATES", "25_exact_matches", candidate_count=25)
    controller.phase("SELECTING_CHECKPOINT", "epoch_105_selected")
    controller.phase("RECONSTRUCTING_STOPPING_BOUNDARY", "epoch_125_reconstructed")
    terminal, acceptance = _synthetic_payloads(context)
    hashes = controller.stage_pair(terminal, acceptance)
    resolved = controller.commit(hashes, candidate_set_sha256="a" * 64, selection_sha256="b" * 64, stopping_sha256="c" * 64)
    assert resolved["recovery_acceptance_id"] == "p9racc_synthetic"
    assert controller.release() == "RELEASED"
    state = json.loads(context.state_path.read_text())
    assert state["state"] == "RECOVERY_ACCEPTED"
    assert state["state_sequence"] == 10
    assert state["previous_state"] == "COMMITTING"
    assert state["release_status"] == "RELEASED"
    assert resolve_committed(context.final_root, context=context)["status"] == "PASS"


def test_controller_precommit_exception_never_becomes_accepted(tmp_path):
    context = _synthetic_context(tmp_path)
    controller = RecoveryTransactionController(context)
    controller.acquire_and_start()
    controller.phase("VALIDATING_SOURCE", "source_validated")
    error = RuntimeError("synthetic source mismatch")
    controller.fail(error)
    assert controller.release() == "RELEASED"
    state = json.loads(context.state_path.read_text())
    assert state["state"] == "RECOVERY_FAILED_NONMUTATING"
    assert state["original_exception_summary"] == "synthetic source mismatch"
    assert not context.final_root.exists()
    with pytest.raises(ValueError, match="canonical"):
        resolve_committed(context.final_root, context=context)


def test_production_entry_uses_controller_for_synthetic_transaction(tmp_path, monkeypatch):
    selected = {
        "checkpoint_id": "p9ck_42f7957d2ea998ac9e8ff705", "epoch": 105,
        "validation_retrieval_loss": 0.3806893528,
        "mean_source_separation_margin": 0.2876026034,
        "checkpoint_payload_sha256": "p" * 64,
        "checkpoint_manifest_sha256": "m" * 64,
    }
    contract = {
        "recovery_contract_id": "p9rec_synthetic",
        "failed_lineage": {"authority_id": "p9a_source", "reservation_id": "p9res_source", "attempt_id": "p9attempt_source", "run_id": "p9run_source", "runtime_tree_sha256": "source-runtime"},
        "join_audit_sha256": "j" * 64,
        "expected_selected_checkpoint": selected,
        "stopping": {"reason": "EARLY_STOPPING_PATIENCE_EXHAUSTED", "stopping_epoch": 125, "stopping_update": 9500, "validation_events": 25, "patience": 4},
        "prohibited_operations": {"optimizer_updates": 0, "validation_runs": 0, "evaluation_queries": 0, "checkpoint_writes": 0, "ddp_launches": 0, "gpu_processes": 0},
    }
    authority = {"recovery_authority_id": "p9ra_synthetic_entry", "recovery_contract_id": "p9rec_synthetic", "runtime_tree_sha256": "runtime", "dag_sha256": "dag", "terminal_target": "p9_cfg_main_recovery_acceptance"}
    reservation = {"recovery_reservation_id": "p9rres_synthetic_entry", "recovery_authority_id": authority["recovery_authority_id"], "recovery_contract_id": "p9rec_synthetic", "status": "AUTHORIZED_NOT_STARTED"}
    operation = {"recovery_operation_id": "p9rop_synthetic_entry", "recovery_reservation_id": reservation["recovery_reservation_id"]}
    authorization = tmp_path / "authorization"
    authorization.mkdir()
    for name, value in (("recovery_contract.json", contract), ("recovery_authority.json", authority), ("recovery_reservation.json", reservation), ("recovery_operation.json", operation)):
        atomic_json(authorization / name, value)
    audit = {"content_sha256": contract["join_audit_sha256"], "selected_checkpoint": selected,
             "rows": [{"classification": "EXACT_MATCH"} for _ in range(25)],
             "candidates": [selected for _ in range(25)]}
    monkeypatch.setattr(recovery_entry, "_validate_failed_source", lambda *_: None)
    monkeypatch.setattr(recovery_entry, "audit_pairs", lambda *_: audit)
    monkeypatch.setenv("FUSE_P9_RECOVERY_RESERVATION_ID", reservation["recovery_reservation_id"])
    args = Namespace(authorization_dir=str(authorization), failed_run=str(tmp_path / "source"),
                     lock_root=str(tmp_path / "locks"), output=str(tmp_path / "output"),
                     store="synthetic-store", synthetic=True)
    recovery_entry.execute(args)
    roots = list((tmp_path / "output").iterdir())
    assert len(roots) == 1
    assert resolve_committed(roots[0])["selected_checkpoint"]["checkpoint_id"] == selected["checkpoint_id"]
    state_files = list((tmp_path / "locks" / "operation_state").rglob("operation_state.json"))
    assert len(state_files) == 1
    assert json.loads(state_files[0].read_text())["state"] == "RECOVERY_ACCEPTED"


def test_production_entry_rejects_wrong_token_before_transaction_artifacts(tmp_path, monkeypatch):
    authorization = tmp_path / "authorization"
    authorization.mkdir()
    atomic_json(authorization / "recovery_reservation.json", {
        "recovery_reservation_id": "p9rres_expected", "status": "AUTHORIZED_NOT_STARTED",
    })
    monkeypatch.setenv("FUSE_P9_RECOVERY_RESERVATION_ID", "p9rres_wrong")
    args = Namespace(authorization_dir=str(authorization), failed_run=str(tmp_path / "source"),
                     lock_root=str(tmp_path / "locks"), output=str(tmp_path / "output"),
                     store="synthetic-store", synthetic=True)
    with pytest.raises(PermissionError, match="exact recovery reservation"):
        recovery_entry.execute(args)
    assert not (tmp_path / "locks").exists()
    assert not (tmp_path / "output").exists()


def test_postcommit_exception_preserves_committed_transaction(tmp_path, monkeypatch):
    context = _synthetic_context(tmp_path)
    controller = RecoveryTransactionController(context)
    controller.acquire_and_start()
    controller.phase("VALIDATING_SOURCE", "source_validated")
    controller.phase("DERIVING_CANDIDATES", "25_exact_matches")
    controller.phase("SELECTING_CHECKPOINT", "epoch_105_selected")
    controller.phase("RECONSTRUCTING_STOPPING_BOUNDARY", "epoch_125_reconstructed")
    terminal, acceptance = _synthetic_payloads(context)
    hashes = controller.stage_pair(terminal, acceptance)
    original_transition = controller._transition

    def fail_after_commit(target, phase, **fields):
        if target == "RECOVERY_ACCEPTED":
            raise RuntimeError("synthetic post-commit bookkeeping failure")
        return original_transition(target, phase, **fields)

    monkeypatch.setattr(controller, "_transition", fail_after_commit)
    with pytest.raises(RuntimeError, match="post-commit"):
        controller.commit(hashes, candidate_set_sha256="a" * 64, selection_sha256="b" * 64, stopping_sha256="c" * 64)
    assert controller.committed is True
    assert resolve_committed(context.final_root, context=context)["status"] == "PASS"
    controller.state.annotate(post_commit_integrity_incident="synthetic post-commit bookkeeping failure")
    assert controller.release() == "RELEASED"
