from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from p9_formal_execution import (FormalAttemptLock, REQUIRED_DUPLICATE_FIELDS, SelectionState,
    candidate_is_better, duplicate_key, load_checkpoint, runtime_tree_manifest, save_checkpoint_atomic,
    terminal_acceptance_payload, transition, validate_validation_event)


def duplicate_fields() -> dict:
    return {key: (2 if key == "world_size" else f"value-{key}") for key in REQUIRED_DUPLICATE_FIELDS}


def checkpoint_state() -> dict:
    generator = torch.Generator().manual_seed(19)
    return {"online_model": {"weight": torch.rand(2, 3, generator=generator)},
            "ema_model": {"weight": torch.rand(2, 3, generator=generator)},
            "optimizer": {"state": {}, "param_groups": []}, "scheduler": {"completed_updates": 4},
            "scaler": None, "progress": {"epoch": 2, "global_update": 4, "within_epoch_cursor": 0},
            "sampler": {"epoch": 2, "cursor": 0}, "rng_states": [{"rank": 0}, {"rank": 1}],
            "queue": {"values": torch.rand(4, 2, generator=generator), "pointer": 1},
            "early_stopping": {"events_without_improvement": 0}, "best_checkpoint": None,
            "validation_trace": [], "training_trace": [], "lineage": {"authority": "p9a_test"},
            "world_size": 2}


def event(epoch=5, loss=1.0, margin=0.1) -> dict:
    return {"epoch": epoch, "validation_retrieval_loss": loss,
            "mean_source_separation_margin": margin, "query_count": 800, "gallery_count": 400,
            "missing_count": 0, "duplicate_count": 0, "evaluation_queries_consumed": 0}


def test_duplicate_key_is_complete_and_sensitive():
    fields = duplicate_fields(); baseline = duplicate_key(fields)
    for key in REQUIRED_DUPLICATE_FIELDS:
        changed = copy.deepcopy(fields); changed[key] = 3 if key == "world_size" else changed[key] + "-changed"
        if key == "world_size":
            with pytest.raises(ValueError, match="world_size"): duplicate_key(changed)
        else:
            assert duplicate_key(changed) != baseline
    for key in REQUIRED_DUPLICATE_FIELDS:
        incomplete = dict(fields); incomplete.pop(key)
        with pytest.raises(ValueError, match="incomplete"): duplicate_key(incomplete)


def test_state_machine_allows_only_declared_transitions():
    assert transition("AUTHORIZED_NOT_STARTED", "STARTING") == "STARTING"
    assert transition("RUNNING", "INTERRUPTED_RESUMABLE") == "INTERRUPTED_RESUMABLE"
    assert transition("COMPLETED_PENDING_VALIDATION", "ACCEPTED") == "ACCEPTED"
    with pytest.raises(ValueError): transition("AUTHORIZED_NOT_STARTED", "RUNNING")
    with pytest.raises(ValueError): transition("ACCEPTED", "RUNNING")


def test_kernel_and_durable_lock_reject_duplicate_and_stale(tmp_path):
    identity = {"duplicate_key": duplicate_key(duplicate_fields()), "attempt_id": "attempt",
                "run_id": "run", "reservation_id": "reservation", "authority_id": "authority"}
    first = FormalAttemptLock(tmp_path, identity); owner = first.acquire()
    assert owner["state"] == "STARTING" and first.owner_path.is_file()
    with pytest.raises(RuntimeError, match="already owned"): FormalAttemptLock(tmp_path, identity).acquire()
    first.release_terminal("REJECTED")
    # A terminal durable owner record is retained as provenance; it is never silently deleted.
    second = FormalAttemptLock(tmp_path, identity); second.acquire(); second.release_terminal("REJECTED")
    stale = json.loads(second.owner_path.read_text()); stale["terminal_state"] = None
    second.owner_path.write_text(json.dumps(stale))
    with pytest.raises(RuntimeError, match="stale recovery"): FormalAttemptLock(tmp_path, identity).acquire()


def test_atomic_checkpoint_roundtrip_and_corruption(tmp_path):
    state = checkpoint_state(); manifest = save_checkpoint_atomic(tmp_path, state)
    assert manifest["checkpoint_id"].startswith("p9ck_")
    restored = load_checkpoint(tmp_path, state["lineage"])
    assert torch.equal(restored["online_model"]["weight"], state["online_model"]["weight"])
    with pytest.raises(ValueError, match="lineage"): load_checkpoint(tmp_path, {"authority": "wrong"})
    with (tmp_path / "checkpoint.pt").open("ab") as stream: stream.write(b"corrupt")
    with pytest.raises(ValueError, match="corruption"): load_checkpoint(tmp_path, state["lineage"])


def test_validation_accounting_selection_and_early_stop():
    validate_validation_event(event())
    with pytest.raises(ValueError): validate_validation_event({**event(), "query_count": 799})
    assert candidate_is_better(event(10, 0.9, 0.0), event(5, 1.0, 9.0))
    assert candidate_is_better(event(10, 1.00005, 0.2), event(5, 1.0, 0.1))
    assert candidate_is_better(event(5, 1.0, 0.1), event(10, 1.0, 0.1))
    selector = SelectionState(4); assert selector.update(event())["improved"]
    for index in range(3): assert not selector.update(event(10 + index, 2.0, 0.0))["stop"]
    assert selector.update(event(20, 2.0, 0.0))["stop"]


def test_bounded_output_cannot_produce_formal_acceptance():
    selected = {"checkpoint_id": "p9ck_x"}; execution = {"state": "COMPLETED_PENDING_VALIDATION",
        "checkpoint_ids": ["p9ck_x"]}
    with pytest.raises(ValueError, match="bounded"):
        terminal_acceptance_payload({"formal_attempt": False}, selected, execution)
    run = {"formal_attempt": True, "runner_class": "P9_FORMAL", "run_id": "p9run_x",
           "attempt_id": "p9attempt_x", "parents": {}}
    assert terminal_acceptance_payload(run, selected, execution)["acceptance_id"].startswith("p9acc_")


def test_runtime_tree_is_order_independent_and_byte_sensitive(tmp_path):
    (tmp_path / "a").write_text("a"); (tmp_path / "b").write_text("b")
    left = runtime_tree_manifest(tmp_path, ["b", "a"]); right = runtime_tree_manifest(tmp_path, ["a", "b"])
    assert left == right
    (tmp_path / "a").write_text("changed")
    assert runtime_tree_manifest(tmp_path, ["a", "b"])["runtime_tree_sha256"] != left["runtime_tree_sha256"]


def test_formal_runner_is_not_the_bounded_runner():
    source = (ROOT / "scripts/p9_formal_training.py").read_text()
    assert "from p9_bounded_main_pilot" not in source
    assert "import p9_bounded_main_pilot" not in source
    assert "FUSE_P9_FORMAL_RESERVATION_ID" in source
    assert "maximum_updates: 40" not in source
    bounded = (ROOT / "scripts/p9_bounded_main_pilot.py").read_text()
    assert '"formal_attempt": False' in bounded
