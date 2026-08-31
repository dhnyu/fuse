import hashlib
import json
from pathlib import Path

import pytest

from p9_checkpoint_recovery import validation_epoch_from_manifest
from p9_recovery_transaction import OperationState, RecoveryLock, resolve_committed, atomic_json


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
    terminal = {"terminal": "synthetic"}; acceptance = {"status": "PASS"}
    atomic_json(tmp_path / "terminal_recovery.json", terminal); atomic_json(tmp_path / "recovery_acceptance.json", acceptance)
    atomic_json(tmp_path / "transaction_manifest.json", {"state": "COMMITTED", "terminal_sha256": hashlib.sha256((tmp_path / "terminal_recovery.json").read_bytes()).hexdigest(), "acceptance_sha256": hashlib.sha256((tmp_path / "recovery_acceptance.json").read_bytes()).hexdigest()})
    state.transition("RECOVERY_ACCEPTED", committed=True)
    assert resolve_committed(tmp_path)["status"] == "PASS"
