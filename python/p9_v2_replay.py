"""Pure state replay for committed P9 v2 ledger events."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

from p9_v2_ledger import (
    GENESIS_HASH,
    LedgerCorruptionError,
    LedgerError,
    LedgerTransitionError,
    read_ledger,
    verify_event,
)


SCIENTIFIC_STATES = frozenset({"NOT_STARTED", "IN_PROGRESS", "COMPLETE", "INCOMPLETE"})
OPERATIONAL_STATES = frozenset({
    "AUTHORIZED", "STARTING", "RUNNING", "FINALIZING", "ACCEPTED",
    "INTERRUPTED_RESUMABLE", "TRAINING_FAILED", "FINALIZATION_FAILED", "BLOCKED",
})
RESUMABILITY_STATES = frozenset({
    "NOT_APPLICABLE", "EXACT_RESUME_ALLOWED", "RESTART_REQUIRED",
    "NOT_APPLICABLE_SCIENTIFICALLY_COMPLETE", "FORBIDDEN_POLICY", "EVIDENCE_INVALID",
})


@dataclass(frozen=True)
class ReplayResult:
    scientific_state: str
    operational_state: str | None
    resumability_state: str
    run_id: str | None
    last_committed_sequence: int
    last_committed_event_hash: str
    last_durable_scientific_boundary: dict[str, Any] | None
    latest_completed_epoch: int | None
    latest_resume_epoch: int | None
    latest_optimizer_update: int | None
    best_checkpoint_state: dict[str, Any] | None
    training_completion_evidence: dict[str, Any] | None
    training_interruption_evidence: dict[str, Any] | None
    training_failure_evidence: dict[str, Any] | None
    finalization_status: str
    acceptance_status: str
    validation_errors: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class _ReplayAccumulator:
    scientific_state: str = "NOT_STARTED"
    operational_state: str | None = None
    resumability_state: str = "NOT_APPLICABLE"
    run_id: str | None = None
    last_sequence: int = 0
    last_hash: str = GENESIS_HASH
    last_boundary: dict[str, Any] | None = None
    completed_epoch: int | None = None
    resume_epoch: int | None = None
    optimizer_update: int | None = None
    best_checkpoint: dict[str, Any] | None = None
    training_completion: dict[str, Any] | None = None
    training_interruption: dict[str, Any] | None = None
    training_failure: dict[str, Any] | None = None
    finalization_status: str = "NOT_STARTED"
    acceptance_status: str = "NOT_PUBLISHED"
    checkpoint_ids: set[str] = field(default_factory=set)
    latest_checkpoint_boundary: dict[str, Any] | None = None

    def result(self, errors: tuple[str, ...] = ()) -> ReplayResult:
        scientific = self.scientific_state
        operational = self.operational_state
        resumability = self.resumability_state
        if errors:
            scientific = "INCOMPLETE"
            operational = "BLOCKED"
            resumability = "EVIDENCE_INVALID"
        assert scientific in SCIENTIFIC_STATES
        assert operational is None or operational in OPERATIONAL_STATES
        assert resumability in RESUMABILITY_STATES
        return ReplayResult(
            scientific_state=scientific,
            operational_state=operational,
            resumability_state=resumability,
            run_id=self.run_id,
            last_committed_sequence=self.last_sequence,
            last_committed_event_hash=self.last_hash,
            last_durable_scientific_boundary=self.last_boundary,
            latest_completed_epoch=self.completed_epoch,
            latest_resume_epoch=self.resume_epoch,
            latest_optimizer_update=self.optimizer_update,
            best_checkpoint_state=self.best_checkpoint,
            training_completion_evidence=self.training_completion,
            training_interruption_evidence=self.training_interruption,
            training_failure_evidence=self.training_failure,
            finalization_status=self.finalization_status,
            acceptance_status=self.acceptance_status,
            validation_errors=errors,
        )


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise LedgerTransitionError(message)


def _boundary(payload: dict[str, Any]) -> dict[str, int]:
    return {
        "completed_epoch": payload["completed_epoch"],
        "resume_epoch": payload["resume_epoch"],
        "optimizer_update": payload["optimizer_update"],
    }


def _apply(acc: _ReplayAccumulator, event: dict[str, Any]) -> None:
    event_type = event["event_type"]
    payload = event["payload"]
    operational = acc.operational_state

    if event_type == "RUN_AUTHORIZED":
        _require(acc.last_sequence == 0 and operational is None, "RUN_AUTHORIZED must be the first event")
        acc.run_id = event["run_id"]
        acc.scientific_state = "NOT_STARTED"
        acc.operational_state = "AUTHORIZED"
        acc.resumability_state = "NOT_APPLICABLE"
    elif event_type == "RUN_STARTING":
        _require(operational in {"AUTHORIZED", "INTERRUPTED_RESUMABLE"}, "RUN_STARTING requires authorization or exact-resume interruption")
        acc.operational_state = "STARTING"
        if acc.scientific_state == "IN_PROGRESS":
            acc.resumability_state = "NOT_APPLICABLE"
    elif event_type == "RUN_STARTED":
        _require(operational == "STARTING", "RUN_STARTED requires STARTING")
        _require(acc.scientific_state in {"NOT_STARTED", "IN_PROGRESS"}, "completed or failed science cannot restart")
        acc.scientific_state = "IN_PROGRESS"
        acc.operational_state = "RUNNING"
        acc.resumability_state = "NOT_APPLICABLE"
    elif event_type == "EPOCH_STARTED":
        _require(operational == "RUNNING" and acc.scientific_state == "IN_PROGRESS", "EPOCH_STARTED requires active training")
        if acc.optimizer_update is not None:
            _require(payload["starting_optimizer_update"] >= acc.optimizer_update, "epoch start regresses optimizer update")
    elif event_type == "PROGRESS_SUMMARY_COMMITTED":
        _require(operational == "RUNNING" and acc.scientific_state == "IN_PROGRESS", "progress requires active training")
        if acc.optimizer_update is not None:
            _require(payload["first_update"] == acc.optimizer_update + 1, "progress range must continue exactly")
        _require(payload["last_update"] >= payload["first_update"], "progress range is invalid")
        acc.optimizer_update = payload["last_update"]
        acc.last_boundary = {
            "event_type": event_type,
            "epoch": payload["ending_epoch"],
            "optimizer_update": payload["last_update"],
            "sampler_cursor": payload["ending_sampler_cursor"],
        }
    elif event_type == "UPDATE_COMMITTED":
        _require(operational == "RUNNING" and acc.scientific_state == "IN_PROGRESS", "update requires active training")
        if acc.optimizer_update is not None:
            _require(payload["optimizer_update"] == acc.optimizer_update + 1, "update sequence must continue exactly")
        acc.optimizer_update = payload["optimizer_update"]
        acc.last_boundary = {
            "event_type": event_type,
            "epoch": payload["epoch"],
            "optimizer_update": payload["optimizer_update"],
            "sampler_cursor": payload["sampler_cursor"],
        }
    elif event_type == "VALIDATION_CHECKPOINT_COMMITTED":
        _require(operational == "RUNNING" and acc.scientific_state == "IN_PROGRESS", "validation checkpoint requires active training")
        if acc.optimizer_update is not None:
            _require(payload["optimizer_update"] >= acc.optimizer_update, "checkpoint regresses optimizer update")
        if acc.completed_epoch is not None:
            _require(payload["completed_epoch"] > acc.completed_epoch, "validation epochs must increase")
        checkpoint_id = payload["checkpoint_id"]
        _require(checkpoint_id not in acc.checkpoint_ids, "checkpoint identity is duplicated")
        acc.checkpoint_ids.add(checkpoint_id)
        best_id = payload["selector_state"].get("best_checkpoint_id")
        _require(best_id is None or best_id in acc.checkpoint_ids, "selector references an uncommitted checkpoint")
        acc.completed_epoch = payload["completed_epoch"]
        acc.resume_epoch = payload["resume_epoch"]
        acc.optimizer_update = payload["optimizer_update"]
        acc.latest_checkpoint_boundary = _boundary(payload)
        acc.last_boundary = {"event_type": event_type, **acc.latest_checkpoint_boundary}
        acc.best_checkpoint = dict(payload["selector_state"])
    elif event_type == "EARLY_STOPPING_UPDATED":
        _require(operational == "RUNNING" and acc.scientific_state == "IN_PROGRESS", "early stopping requires active training")
        best_id = payload["best_checkpoint_id"]
        _require(best_id is None or best_id in acc.checkpoint_ids, "early stopping references an uncommitted checkpoint")
        acc.best_checkpoint = {
            **payload["selector_state"],
            "best_checkpoint_id": best_id,
            "events_without_improvement": payload["events_without_improvement"],
            "decision_basis": payload["decision_basis"],
        }
    elif event_type == "TRAINING_COMPLETED":
        _require(operational == "RUNNING" and acc.scientific_state == "IN_PROGRESS", "training completion requires active training")
        if acc.optimizer_update is not None:
            _require(payload["optimizer_update"] >= acc.optimizer_update, "completion regresses optimizer update")
        acc.scientific_state = "COMPLETE"
        acc.resumability_state = "NOT_APPLICABLE_SCIENTIFICALLY_COMPLETE"
        acc.completed_epoch = payload["completed_epoch"]
        acc.resume_epoch = payload["resume_epoch"]
        acc.optimizer_update = payload["optimizer_update"]
        acc.last_boundary = {"event_type": event_type, **_boundary(payload)}
        acc.training_completion = dict(payload)
    elif event_type == "TRAINING_INTERRUPTED":
        _require(operational == "RUNNING" and acc.scientific_state == "IN_PROGRESS", "interruption requires active training")
        acc.training_interruption = dict(payload)
        acc.last_boundary = {"event_type": event_type, **payload["last_durable_boundary"]}
        if payload["resumable_checkpoint_committed"]:
            _require(acc.latest_checkpoint_boundary == payload["last_durable_boundary"], "resumability requires the latest committed checkpoint boundary")
            if payload["resume_policy"] == "EXACT_RESUME":
                acc.operational_state = "INTERRUPTED_RESUMABLE"
                acc.resumability_state = "EXACT_RESUME_ALLOWED"
            else:
                _require(payload["resume_policy"] == "FORBIDDEN", "invalid interruption resume policy")
                acc.operational_state = "BLOCKED"
                acc.resumability_state = "FORBIDDEN_POLICY"
        else:
            acc.scientific_state = "INCOMPLETE"
            acc.operational_state = "BLOCKED"
            acc.resumability_state = "RESTART_REQUIRED"
    elif event_type == "TRAINING_FAILED":
        _require(operational == "RUNNING" and acc.scientific_state == "IN_PROGRESS", "training failure requires active training")
        acc.scientific_state = "INCOMPLETE"
        acc.operational_state = "TRAINING_FAILED"
        acc.training_failure = dict(payload)
        if payload["last_durable_boundary"] is not None:
            acc.last_boundary = {"event_type": event_type, **payload["last_durable_boundary"]}
        if payload["resumable_checkpoint_committed"]:
            _require(acc.latest_checkpoint_boundary == payload["last_durable_boundary"], "failed-run resume requires the latest committed checkpoint")
            acc.resumability_state = (
                "EXACT_RESUME_ALLOWED"
                if payload["resume_policy"] == "EXACT_RESUME"
                else "FORBIDDEN_POLICY"
            )
        else:
            acc.resumability_state = (
                "FORBIDDEN_POLICY" if payload["resume_policy"] == "FORBIDDEN"
                else "RESTART_REQUIRED"
            )
    elif event_type == "FINALIZATION_STARTED":
        _require(acc.scientific_state == "COMPLETE", "finalization requires complete science")
        _require(operational in {"RUNNING", "FINALIZATION_FAILED"}, "finalization start has invalid operational predecessor")
        acc.operational_state = "FINALIZING"
        acc.finalization_status = "IN_PROGRESS"
        acc.resumability_state = "NOT_APPLICABLE_SCIENTIFICALLY_COMPLETE"
    elif event_type == "FINALIZATION_COMPLETED":
        _require(operational == "FINALIZING" and acc.finalization_status == "IN_PROGRESS", "finalization completion requires FINALIZING")
        _require(payload["selected_checkpoint_id"] in acc.checkpoint_ids, "finalization selected checkpoint is not committed")
        acc.finalization_status = "COMPLETED"
    elif event_type == "FINALIZATION_FAILED":
        _require(operational == "FINALIZING" and acc.finalization_status == "IN_PROGRESS", "finalization failure requires FINALIZING")
        acc.finalization_status = "FAILED"
        if payload["evidence_class"] == "INVALID_SCIENTIFIC_EVIDENCE":
            acc.scientific_state = "INCOMPLETE"
            acc.operational_state = "BLOCKED"
            acc.resumability_state = "EVIDENCE_INVALID"
        else:
            acc.operational_state = "FINALIZATION_FAILED"
            acc.resumability_state = "NOT_APPLICABLE_SCIENTIFICALLY_COMPLETE"
    elif event_type == "ACCEPTANCE_PUBLISHED":
        _require(acc.scientific_state == "COMPLETE", "acceptance requires complete science")
        _require(operational == "FINALIZING" and acc.finalization_status == "COMPLETED", "acceptance requires completed finalization")
        acc.operational_state = "ACCEPTED"
        acc.acceptance_status = "PUBLISHED"
    else:
        raise LedgerTransitionError(f"unsupported event type: {event_type}")


def replay_events(events: Iterable[dict[str, Any]], *, strict: bool = True) -> ReplayResult:
    acc = _ReplayAccumulator()
    try:
        for expected_sequence, event in enumerate(events, 1):
            expected_run = acc.run_id if acc.run_id is not None else event.get("run_id")
            verify_event(
                event,
                expected_run_id=expected_run,
                expected_sequence=expected_sequence,
                expected_previous_hash=acc.last_hash,
            )
            _apply(acc, event)
            acc.last_sequence = event["event_sequence"]
            acc.last_hash = event["event_hash"]
        return acc.result()
    except LedgerError as error:
        if strict:
            raise
        return acc.result((str(error),))


def replay_ledger(root: str | Path, *, strict: bool = True) -> ReplayResult:
    try:
        committed = read_ledger(root)
        return replay_events(committed.events, strict=strict)
    except LedgerError as error:
        if strict:
            raise
        run_id = None
        try:
            run_id = read_ledger(root, verify_manifest=False).header["run_id"]
        except LedgerError:
            pass
        acc = _ReplayAccumulator(run_id=run_id)
        return acc.result((str(error),))
