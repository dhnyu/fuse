from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from p9_v2_ledger import LedgerTransitionError  # noqa: E402
from p9_v2_replay import replay_events  # noqa: E402
from p9_v2_test_support import CHECKPOINT_ID, make_chain, payload  # noqa: E402


START = [("RUN_AUTHORIZED", None), ("RUN_STARTING", None), ("RUN_STARTED", None)]
CHECKPOINT = [
    *START,
    ("EPOCH_STARTED", None),
    ("PROGRESS_SUMMARY_COMMITTED", None),
    ("VALIDATION_CHECKPOINT_COMMITTED", None),
]


@pytest.mark.parametrize(
    ("length", "scientific", "operational"),
    [(1, "NOT_STARTED", "AUTHORIZED"), (2, "NOT_STARTED", "STARTING"), (3, "IN_PROGRESS", "RUNNING")],
)
def test_normal_start_state_matrix(length, scientific, operational):
    result = replay_events(make_chain(START[:length]))
    assert result.scientific_state == scientific
    assert result.operational_state == operational


def test_progress_and_checkpoint_remain_scientifically_in_progress():
    result = replay_events(make_chain(CHECKPOINT))
    assert result.scientific_state == "IN_PROGRESS"
    assert result.operational_state == "RUNNING"
    assert result.latest_completed_epoch == 5
    assert result.latest_resume_epoch == 6
    assert result.latest_optimizer_update == 380
    assert result.best_checkpoint_state["best_checkpoint_id"] == CHECKPOINT_ID
    assert result.last_durable_scientific_boundary["event_type"] == "VALIDATION_CHECKPOINT_COMMITTED"


def test_clean_training_completion_is_complete_but_not_accepted():
    result = replay_events(make_chain([*CHECKPOINT, ("TRAINING_COMPLETED", None)]))
    assert result.scientific_state == "COMPLETE"
    assert result.operational_state == "RUNNING"
    assert result.resumability_state == "NOT_APPLICABLE_SCIENTIFICALLY_COMPLETE"
    assert result.acceptance_status == "NOT_PUBLISHED"


def test_interruption_with_exact_checkpoint_is_independently_resumable():
    result = replay_events(make_chain([*CHECKPOINT, ("TRAINING_INTERRUPTED", None)]))
    assert result.scientific_state == "IN_PROGRESS"
    assert result.operational_state == "INTERRUPTED_RESUMABLE"
    assert result.resumability_state == "EXACT_RESUME_ALLOWED"


def test_training_failure_without_checkpoint_is_incomplete():
    result = replay_events(make_chain([*START, ("TRAINING_FAILED", None)]))
    assert result.scientific_state == "INCOMPLETE"
    assert result.operational_state == "TRAINING_FAILED"
    assert result.resumability_state == "RESTART_REQUIRED"


def test_resume_can_be_forbidden_by_explicit_policy_without_losing_science():
    interrupted = payload("TRAINING_INTERRUPTED", resume_policy="FORBIDDEN")
    result = replay_events(make_chain([*CHECKPOINT, ("TRAINING_INTERRUPTED", interrupted)]))
    assert result.scientific_state == "IN_PROGRESS"
    assert result.operational_state == "BLOCKED"
    assert result.resumability_state == "FORBIDDEN_POLICY"


def test_scientific_completion_survives_operational_finalization_failure():
    events = make_chain([
        *CHECKPOINT,
        ("TRAINING_COMPLETED", None),
        ("FINALIZATION_STARTED", None),
        ("FINALIZATION_FAILED", None),
    ])
    result = replay_events(events)
    assert result.scientific_state == "COMPLETE"
    assert result.operational_state == "FINALIZATION_FAILED"
    assert result.resumability_state == "NOT_APPLICABLE_SCIENTIFICALLY_COMPLETE"
    assert result.finalization_status == "FAILED"


def test_acceptance_event_is_representable_without_implementing_publisher():
    result = replay_events(make_chain([
        *CHECKPOINT,
        ("TRAINING_COMPLETED", None),
        ("FINALIZATION_STARTED", None),
        ("FINALIZATION_COMPLETED", None),
        ("ACCEPTANCE_PUBLISHED", None),
    ]))
    assert result.scientific_state == "COMPLETE"
    assert result.operational_state == "ACCEPTED"
    assert result.acceptance_status == "PUBLISHED"


def test_invalid_scientific_evidence_blocks_failed_finalization():
    failure = payload("FINALIZATION_FAILED", evidence_class="INVALID_SCIENTIFIC_EVIDENCE")
    result = replay_events(make_chain([
        *CHECKPOINT,
        ("TRAINING_COMPLETED", None),
        ("FINALIZATION_STARTED", None),
        ("FINALIZATION_FAILED", failure),
    ]))
    assert result.scientific_state == "INCOMPLETE"
    assert result.operational_state == "BLOCKED"
    assert result.resumability_state == "EVIDENCE_INVALID"


def test_illegal_transition_fails_closed_or_returns_invalid_result():
    events = make_chain([("RUN_AUTHORIZED", None), ("RUN_STARTED", None)])
    with pytest.raises(LedgerTransitionError, match="STARTING"):
        replay_events(events)
    invalid = replay_events(events, strict=False)
    assert invalid.scientific_state == "INCOMPLETE"
    assert invalid.operational_state == "BLOCKED"
    assert invalid.resumability_state == "EVIDENCE_INVALID"
    assert invalid.validation_errors


def test_resume_after_exact_interruption_returns_to_running():
    result = replay_events(make_chain([
        *CHECKPOINT,
        ("TRAINING_INTERRUPTED", None),
        ("RUN_STARTING", None),
        ("RUN_STARTED", None),
    ]))
    assert result.scientific_state == "IN_PROGRESS"
    assert result.operational_state == "RUNNING"
    assert result.resumability_state == "NOT_APPLICABLE"


def test_replay_is_deterministic_and_idempotent():
    events = make_chain([*CHECKPOINT, ("TRAINING_COMPLETED", None)])
    expected = replay_events(events).as_dict()
    assert [replay_events(events).as_dict() for _ in range(100)] == [expected] * 100


def test_fixed_seed_random_valid_sequences_are_replayable_and_deterministic():
    randomizer = random.Random(20260831)
    for _ in range(100):
        update_count = randomizer.randint(1, 20)
        specs = list(START)
        for update in range(1, update_count + 1):
            specs.append(("UPDATE_COMMITTED", payload(
                "UPDATE_COMMITTED", optimizer_update=update, epoch=1 + update // 10, sampler_cursor=update,
            )))
        has_checkpoint = randomizer.choice([False, True])
        if has_checkpoint:
            specs.append(("VALIDATION_CHECKPOINT_COMMITTED", payload(
                "VALIDATION_CHECKPOINT_COMMITTED", optimizer_update=update_count,
            )))
        terminal = randomizer.choice(["running", "failure", "interruption", "completion"])
        if terminal == "failure":
            specs.append(("TRAINING_FAILED", None))
        elif terminal == "interruption":
            if has_checkpoint:
                specs.append(("TRAINING_INTERRUPTED", payload(
                    "TRAINING_INTERRUPTED",
                    last_durable_boundary={"completed_epoch": 5, "resume_epoch": 6, "optimizer_update": update_count},
                )))
            else:
                specs.append(("TRAINING_INTERRUPTED", payload(
                    "TRAINING_INTERRUPTED",
                    last_durable_boundary={"completed_epoch": 0, "resume_epoch": 1, "optimizer_update": update_count},
                    resumable_checkpoint_committed=False,
                    resume_policy="RESTART",
                )))
        elif terminal == "completion":
            specs.append(("TRAINING_COMPLETED", payload("TRAINING_COMPLETED", optimizer_update=update_count)))
        events = make_chain(specs)
        assert replay_events(events).as_dict() == replay_events(events).as_dict()
