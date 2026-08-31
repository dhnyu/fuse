import hashlib
import json
from pathlib import Path

from p9_checkpoint_recovery import validation_epoch_from_manifest


def test_validation_epoch_is_resume_epoch_minus_one():
    assert validation_epoch_from_manifest({"epoch": 106}) == 105


def test_validation_epoch_rejects_invalid_resume_epoch():
    try:
        validation_epoch_from_manifest({"epoch": 1})
    except ValueError as error:
        assert "resume epoch" in str(error)
    else:
        raise AssertionError("invalid resume epoch must fail closed")
