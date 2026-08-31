from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from p9_v2_ledger import GENESIS_HASH, LedgerWriter, make_event  # noqa: E402


RUN_ID = "p9runv2_" + "a" * 24
CHECKPOINT_ID = "p9ck_" + "b" * 24
HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64
HASH_D = "d" * 64

ROLES = {
    "RUN_AUTHORIZED": "controller",
    "RUN_STARTING": "controller",
    "RUN_STARTED": "controller",
    "EPOCH_STARTED": "rank0",
    "PROGRESS_SUMMARY_COMMITTED": "rank0",
    "UPDATE_COMMITTED": "rank0",
    "VALIDATION_CHECKPOINT_COMMITTED": "rank0",
    "EARLY_STOPPING_UPDATED": "rank0",
    "TRAINING_COMPLETED": "controller",
    "TRAINING_INTERRUPTED": "controller",
    "TRAINING_FAILED": "controller",
    "FINALIZATION_STARTED": "finalizer",
    "FINALIZATION_COMPLETED": "finalizer",
    "FINALIZATION_FAILED": "finalizer",
    "ACCEPTANCE_PUBLISHED": "publisher",
}


def timestamp(sequence: int) -> str:
    return f"2026-08-31T00:{sequence // 60:02d}:{sequence % 60:02d}Z"


def payload(event_type: str, **overrides: Any) -> dict[str, Any]:
    values: dict[str, dict[str, Any]] = {
        "RUN_AUTHORIZED": {
            "authority_hash": HASH_A,
            "scientific_configuration_hash": HASH_B,
            "parent_identities": {"p8_acceptance": "p8acc_synthetic"},
            "duplicate_run_key": HASH_C,
        },
        "RUN_STARTING": {
            "owner_id": "synthetic-controller",
            "execution_environment_digest": HASH_A,
            "training_lock_key": HASH_B,
        },
        "RUN_STARTED": {"process_id": "synthetic-process", "world_size": 2, "runtime_digest": HASH_C},
        "EPOCH_STARTED": {"epoch": 1, "starting_optimizer_update": 0, "sampler_cursor": 0},
        "PROGRESS_SUMMARY_COMMITTED": {
            "first_update": 1,
            "last_update": 380,
            "ending_epoch": 6,
            "ending_sampler_cursor": 0,
            "trace_block_sha256": HASH_A,
            "sampler_state_sha256": HASH_B,
            "rng_state_sha256": HASH_C,
            "queue_state_sha256": HASH_D,
        },
        "UPDATE_COMMITTED": {"optimizer_update": 1, "epoch": 1, "sampler_cursor": 1, "durable_boundary": True},
        "VALIDATION_CHECKPOINT_COMMITTED": {
            "completed_epoch": 5,
            "resume_epoch": 6,
            "optimizer_update": 380,
            "validation_id": "p9val_" + "c" * 24,
            "checkpoint_id": CHECKPOINT_ID,
            "checkpoint_payload_sha256": HASH_A,
            "checkpoint_manifest_sha256": HASH_B,
            "validation_retrieval_loss": 0.3806893528,
            "mean_source_separation_margin": 0.2876026034,
            "selector_state": {"best_checkpoint_id": CHECKPOINT_ID, "events_without_improvement": 0},
            "queue": {"count": 8192, "pointer": 7936, "enqueue_count": 24320, "state_sha256": HASH_C},
            "sampler": {"epoch": 6, "cursor": 0, "state_sha256": HASH_D},
            "state_presence": {
                "online_model": True, "ema_model": True, "optimizer": True, "scheduler": True,
                "rng_states": True, "queue": True, "sampler": True, "early_stopping": True,
                "best_checkpoint": True, "validation_trace": True,
            },
            "atomic_completion_marker": {"protocol": "native_v2_atomic_commit", "status": "COMPLETE"},
            "source_run_id": RUN_ID,
        },
        "EARLY_STOPPING_UPDATED": {
            "selector_state": {"primary": "validation_retrieval_loss"},
            "best_checkpoint_id": CHECKPOINT_ID,
            "events_without_improvement": 0,
            "decision_basis": "retrieval_loss_improved",
        },
        "TRAINING_COMPLETED": {
            "completed_epoch": 5,
            "resume_epoch": 6,
            "optimizer_update": 380,
            "reason": "SYNTHETIC_COMPLETION",
        },
        "TRAINING_INTERRUPTED": {
            "last_durable_boundary": {"completed_epoch": 5, "resume_epoch": 6, "optimizer_update": 380},
            "resumable_checkpoint_committed": True,
            "resume_policy": "EXACT_RESUME",
            "interruption_reason": "SYNTHETIC_SIGNAL",
        },
        "TRAINING_FAILED": {
            "failure_class": "SyntheticFailure",
            "failure_stage": "synthetic_stage",
            "last_durable_boundary": None,
            "resumable_checkpoint_committed": False,
            "resume_policy": "RESTART",
        },
        "FINALIZATION_STARTED": {"run_bundle_hash": HASH_A, "selection_contract_hash": HASH_B},
        "FINALIZATION_COMPLETED": {"finalization_result_hash": HASH_C, "selected_checkpoint_id": CHECKPOINT_ID},
        "FINALIZATION_FAILED": {"failure_code": "SYNTHETIC_IO", "evidence_class": "OPERATIONAL_FAILURE"},
        "ACCEPTANCE_PUBLISHED": {
            "acceptance_id": "p9accv2_" + "d" * 24,
            "finalization_result_hash": HASH_C,
            "run_bundle_hash": HASH_A,
            "acceptance_commit_manifest_hash": HASH_D,
        },
    }
    return {**values[event_type], **overrides}


def make_chain(specs: Iterable[tuple[str, dict[str, Any] | None]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    previous = GENESIS_HASH
    for sequence, (event_type, event_payload) in enumerate(specs, 1):
        event = make_event(
            event_type=event_type,
            event_sequence=sequence,
            run_id=RUN_ID,
            occurred_at=timestamp(sequence),
            writer_id=f"synthetic-{ROLES[event_type]}",
            writer_role=ROLES[event_type],
            previous_event_hash=previous,
            payload=event_payload or payload(event_type),
        )
        events.append(event)
        previous = event["event_hash"]
    return events


def initialized_writer(root: Path) -> LedgerWriter:
    return LedgerWriter.initialize(root, run_id=RUN_ID, created_at="2026-08-31T00:00:00Z")


def append_event(writer: LedgerWriter, event_type: str, event_payload: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
    current_count = len(list((writer.root / "segments").glob("*.jsonl")))
    return writer.append(
        event_type=event_type,
        occurred_at=timestamp(current_count + 1),
        writer_id=f"synthetic-{ROLES[event_type]}",
        writer_role=ROLES[event_type],
        payload=event_payload or payload(event_type),
        **kwargs,
    )


def append_start(writer: LedgerWriter) -> None:
    for event_type in ("RUN_AUTHORIZED", "RUN_STARTING", "RUN_STARTED"):
        append_event(writer, event_type)


def append_through_checkpoint(writer: LedgerWriter) -> None:
    append_start(writer)
    append_event(writer, "EPOCH_STARTED")
    append_event(writer, "PROGRESS_SUMMARY_COMMITTED")
    append_event(writer, "VALIDATION_CHECKPOINT_COMMITTED")
