import hashlib
import json
from pathlib import Path

import pytest

from p9_checkpoint_recovery import validation_epoch_from_manifest
from p9_recovery_transaction import RecoveryLock


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
