import json
import os
import tempfile
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from canonical_config import canonical_json_bytes  # noqa: E402
from p9_formal_authorization import (FormalAttemptLock, build_plan_bundle, canonical_membership,
                                     cfg_main_reservation_payload, load_config, validate_lineage)  # noqa: E402
sys.path.insert(0, str(ROOT / "scripts"))
import p9_production_cache as production_cache  # noqa: E402

CONFIG = ROOT / "config/p9_formal_authorization.yml"


def test_canonical_lineage_and_cache_union():
    config = load_config(CONFIG); bundle = validate_lineage(config); membership = canonical_membership(config, bundle)
    assert membership["canonical_union_count"] == 78_672
    assert membership["profile_counts"] == {"main_1.0x": 38_736, "weak_0.5x": 19_368, "strong_2.0x": 19_368}
    assert membership["validation_count"] == 1_200
    assert {key: value["entry_count"] for key, value in membership["main_subsets"].items()} == {
        "2": 4_842, "4": 9_684, "8": 19_368, "16": 38_736}
    assert all(value["candidate_differences_from_k16"] == 0 for value in membership["main_subsets"].values())


def test_plan_is_canonical_and_optimizer_free():
    config = load_config(CONFIG)
    assert config["cache_build_execution_commit"] == "2c5b4904449842dea4d6c479067d6d05f952359f"
    first = build_plan_bundle(CONFIG, config["canonical_implementation_commit"], "0" * 40)
    second = build_plan_bundle(CONFIG, config["canonical_implementation_commit"], "0" * 40)
    assert canonical_json_bytes(first) == canonical_json_bytes(second)
    authority = first["production_cache_build_authority"]
    assert authority["expected_entry_count_per_derived_family"] == 78_672
    assert authority["optimizer_authorized"] is False
    assert authority["formal_validation_authorized"] is False
    with pytest.raises(ValueError, match="publication commit"):
        build_plan_bundle(CONFIG, "1" * 40, "0" * 40)
    with pytest.raises(ValueError, match="complete 40-character"):
        build_plan_bundle(CONFIG, config["canonical_implementation_commit"], "8a0dd3f")


def test_atomic_duplicate_lock_and_explicit_recovery():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "attempt.lock.json"; key = "a" * 64
        lock = FormalAttemptLock(path, key); owner = lock.acquire()
        assert owner["state"] == "ACTIVE" and path.is_file()
        with pytest.raises(FileExistsError): FormalAttemptLock(path, key).acquire()
        lock.heartbeat(); terminal = lock.release("FAILED")
        assert terminal.is_file() and not path.exists()
        stale = Path(directory) / "stale.lock.json"
        stale.write_bytes(canonical_json_bytes({"state": "ACTIVE", "duplicate_attempt_key": key}))
        with pytest.raises(PermissionError): FormalAttemptLock.authorize_stale_recovery(stale, {"status": "APPROVED"})
        moved = FormalAttemptLock.authorize_stale_recovery(stale, {"status": "APPROVED", "lock_sha256": __import__(
            "hashlib").sha256(stale.read_bytes()).hexdigest()})
        assert moved.is_file() and not stale.exists()


def test_rank_non_owner_requires_matching_controller_lock():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "attempt.lock.json"; key = "b" * 64
        controller = FormalAttemptLock(path, key); controller.acquire(resume_identity="resume-1")
        assert FormalAttemptLock(path, key, rank=1).acquire(resume_identity="resume-1")["owner"] == "DDP_CONTROLLER"
        with pytest.raises(FileExistsError): FormalAttemptLock(path, key, rank=1).acquire(resume_identity="resume-2")
        controller.release("FAILED")


def test_reservation_is_unstarted_and_complete_duplicate_key():
    config = load_config(CONFIG)
    acceptance = {"status": "PASS", "acceptance_id": "p9ca_" + "1" * 24}
    authority = {"authority_id": "p9a_" + "2" * 24}
    reservation = cfg_main_reservation_payload(config, authority, acceptance)
    assert reservation["status"] == "AUTHORIZED_NOT_STARTED"
    assert reservation["attempt_started"] is False
    assert reservation["optimizer_updates_executed"] == 0
    assert len(reservation["duplicate_attempt_key"]) == 64


def test_memory_thresholds_are_canonical_json_serializable(monkeypatch):
    config = load_config(CONFIG)
    original = Path.read_text

    def read_text(path, *args, **kwargs):
        if str(path) == "/proc/meminfo":
            return "MemAvailable: 999999999 kB\n"
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read_text)
    tier, resources = production_cache.memory_worker_tier(config)
    assert tier == 32
    assert set(resources["thresholds"]) == {"32", "24", "16"}
    canonical_json_bytes(resources)
