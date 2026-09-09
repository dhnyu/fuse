from __future__ import annotations

import csv
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from training_progress import (  # noqa: E402
    CampaignProgress, RunProgress, TrainingProgressError, campaign_snapshot, configured_log_root,
    validation_progress,
)
from training_worker import make_worker_request  # noqa: E402
from training_controller import TrainingControllerError  # noqa: E402


def logger(root: Path, *, phase: str = "OFAT", config: str = "ofat_d_64",
           authority: str = "s09auth_fixture", run: str = "p9runv2_fixture",
           require_existing: bool = False) -> RunProgress:
    return RunProgress(root, phase=phase, config_or_model=config, authority_id=authority,
                       run_id=run, patience_limit=4, epoch_limit=200, update_limit=15_200,
                       create=True, require_existing=require_existing)


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def test_epoch_and_validation_rows_append_without_truncation(tmp_path):
    progress = logger(tmp_path / "logs")
    progress.append("AUTHORITY_READY")
    progress.append("TRAINING", epoch=1, update=76, training_loss=1.8421,
                    learning_rate=0.0001)
    values = validation_progress({
        "completed_epoch": 5, "optimizer_update": 380,
        "validation_retrieval_loss": 0.2143,
        "mean_source_separation_margin": 0.3187,
        "current_candidate_selected": True,
    }, {
        "checkpoint_id": "p9ck_" + "a" * 24,
        "selector_state": {"events_without_improvement": 0},
    }, tmp_path / "checkpoints")
    progress.append("CHECKPOINT_COMMITTED", **values)
    history = rows(progress.run_path)
    assert len(history) == 3
    assert history[1]["training_loss"] == "1.8421000000000001"
    assert float(history[2]["validation_loss"]) == 0.2143
    assert float(history[2]["validation_margin"]) == 0.3187
    assert history[2]["best_epoch"] == "5"
    assert history[2]["latest_checkpoint_id"] == "p9ck_" + "a" * 24
    assert history[2]["best_checkpoint_id"] == "p9ck_" + "a" * 24


def test_current_status_is_atomic_and_human_readable(tmp_path):
    progress = logger(tmp_path / "logs")
    progress.append("TRAINING", epoch=35, update=2660, training_loss=1.8421,
                    validation_loss=0.2143, validation_margin=0.3187,
                    best_epoch=30, best_validation_loss=0.2078,
                    best_validation_margin=0.3152, patience_used=1)
    current = (tmp_path / "logs/current_status.txt").read_text()
    assert "phase=OFAT" in current
    assert "epoch=35/200" in current
    assert "patience=1/4" in current
    assert "training_loss=1.8421000000000001" in current
    assert not list((tmp_path / "logs").glob(".current_status.*.tmp"))


def test_interruption_and_resume_append_to_existing_run(tmp_path):
    root = tmp_path / "logs"
    first = logger(root)
    first.append("TRAINING", epoch=5, update=380)
    first.append("INTERRUPTED", latest_checkpoint_id="p9ck_" + "b" * 24)
    before = first.run_path.read_bytes()
    resumed = logger(root, require_existing=True)
    resumed.append("RESUMING", epoch=5, update=380,
                   latest_checkpoint_id="p9ck_" + "b" * 24)
    after = resumed.run_path.read_bytes()
    assert after.startswith(before)
    assert [row["status"] for row in rows(resumed.run_path)] == ["TRAINING", "INTERRUPTED", "RESUMING"]


def test_required_run_lifecycle_transitions_are_appendable(tmp_path):
    progress = logger(tmp_path / "logs")
    statuses = [
        "AUTHORITY_READY", "WAITING_FOR_GPU", "PREPARING", "TRAINING", "VALIDATING",
        "CHECKPOINT_COMMITTED", "EARLY_STOPPED", "COMPLETED", "ACCEPTED", "FAILED",
        "INTERRUPTED", "RESUMING",
    ]
    for status in statuses:
        progress.append(status)
    assert [row["status"] for row in rows(progress.run_path)] == statuses


def test_run_identity_is_separated_and_existing_identity_is_validated(tmp_path):
    root = tmp_path / "logs"
    first = logger(root, run="p9runv2_first")
    second = logger(root, run="p9runv2_second")
    first.append("AUTHORITY_READY"); second.append("AUTHORITY_READY")
    assert first.run_path != second.run_path
    with pytest.raises(TrainingProgressError, match="IDENTITY"):
        logger(root, authority="s09auth_wrong", run="p9runv2_first")


def test_missing_log_directory_fails_when_creation_is_not_authorized(tmp_path):
    with pytest.raises(TrainingProgressError, match="DIRECTORY_MISSING"):
        CampaignProgress(tmp_path / "missing", create=False)
    assert configured_log_root(tmp_path, {"execution": {"progress_log_root": "logs/s09"}}) == (
        tmp_path / "logs/s09").resolve()
    with pytest.raises(TrainingProgressError, match="MUST_BE_LOGS_S09"):
        configured_log_root(tmp_path, {"execution": {"progress_log_root": "other"}})


def test_campaign_progress_aggregation_tracks_cache_and_accepted_runs(tmp_path):
    root = tmp_path / "logs"
    campaign = CampaignProgress(root, create=True)
    campaign.append_campaign("PREPARED_CACHE_READY", phase="CACHE", config_or_model="s09cache_fixture")
    logger(root, config="ofat_d_64", run="run-a").append("ACCEPTED")
    logger(root, config="ofat_d_256", run="run-b").append("ACCEPTED")
    logger(root, phase="COMPARISON", config="A1", run="run-c").append("ACCEPTED")
    campaign.append_campaign("WINNER_SELECTED", config_or_model="ofat_d_64",
                             winner_configuration="ofat_d_64")
    snapshot = campaign_snapshot(rows(root / "campaign_status.tsv"))
    assert snapshot == {
        "ofat_completed": "2", "ofat_total": "11",
        "comparison_completed": "1", "comparison_total": "17",
        "winner_configuration": "ofat_d_64",
        "prepared_cache_status": "PREPARED_CACHE_READY", "campaign_status": "IN_PROGRESS",
    }
    accepted_rows = [row for row in rows(root / "campaign_status.tsv") if row["status"] == "ACCEPTED"]
    assert [row["phase_completed"] for row in accepted_rows] == ["1", "2", "1"]


def test_validation_progress_propagates_formal_metrics_exactly(tmp_path):
    body = {"completed_epoch": 10, "optimizer_update": 760,
            "validation_retrieval_loss": 0.123456789,
            "mean_source_separation_margin": -0.0042,
            "current_candidate_selected": False}
    response = {"checkpoint_id": "p9ck_" + "c" * 24,
                "selector_state": {"events_without_improvement": 2}}
    value = validation_progress(body, response, tmp_path)
    assert value["validation_loss"] == body["validation_retrieval_loss"]
    assert value["validation_margin"] == body["mean_source_separation_margin"]
    assert value["selection_eligible"] is True
    assert value["patience_used"] == 2
    assert "best_epoch" not in value


def test_worker_epoch_adapter_uses_existing_update_metrics():
    spec = importlib.util.spec_from_file_location("s09_worker_entry", ROOT / "scripts/training_worker.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    value = module.epoch_progress_payload({}, [
        {"total_loss": 2.0, "learning_rate": 0.001},
        {"total_loss": 1.0, "learning_rate": 0.0009},
    ], 12.5)
    assert value == {"mean_training_loss": 1.5, "ending_learning_rate": 0.0009,
                     "epoch_wall_seconds": 12.5}
    request = make_worker_request("EVENT_PROPOSAL", {
        "event_type": "PROGRESS_SUMMARY_COMMITTED", "occurred_at": "2026-09-09T00:00:00Z",
        "writer_id": "science-rank0", "writer_role": "rank0",
        "payload": {"first_update": 1, "last_update": 76, "ending_epoch": 1,
                    "ending_sampler_cursor": 76, "trace_block_sha256": "a" * 64,
                    "sampler_state_sha256": "b" * 64, "rng_state_sha256": "c" * 64,
                    "queue_state_sha256": "d" * 64, **value},
    })
    assert request["body"]["payload"]["mean_training_loss"] == 1.5
    with pytest.raises(RuntimeError, match="METRICS_MISSING"):
        module.epoch_progress_payload({}, [], 1.0)


def test_controller_requires_and_propagates_formal_epoch_metrics():
    spec = importlib.util.spec_from_file_location("s09_controller_entry", ROOT / "scripts/training_controller.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)

    class Capture:
        def __init__(self): self.values = None
        def append(self, status, **values): self.values = (status, values)

    payload = {"ending_epoch": 3, "last_update": 228, "mean_training_loss": 1.25,
               "ending_learning_rate": 0.0008, "epoch_wall_seconds": 20.0}
    capture = Capture()
    module.log_committed_worker_event(capture, {
        "message_type": "EVENT_PROPOSAL",
        "body": {"event_type": "PROGRESS_SUMMARY_COMMITTED", "payload": payload},
    })
    assert capture.values == ("TRAINING", {"epoch": 3, "update": 228,
                                            "training_loss": 1.25,
                                            "learning_rate": 0.0008})
    del payload["mean_training_loss"]
    with pytest.raises(TrainingControllerError, match="METRICS_MISSING"):
        module.log_committed_worker_event(capture, {
            "message_type": "EVENT_PROPOSAL",
            "body": {"event_type": "PROGRESS_SUMMARY_COMMITTED", "payload": payload},
        })
