from __future__ import annotations

import multiprocessing
import json
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from p9_v2_canonical import canonical_json_bytes, sha256_file  # noqa: E402
from p9_v2_ledger import read_ledger  # noqa: E402
from p9_v2_training_controller import (  # noqa: E402
    DuplicateRunError, StartupInputs, TrainingController, TrainingControllerError, TrainingRunLock,
    build_training_authority, publish_checkpoint, training_run_id, validate_checkpoint,
    accepted_scientific_configurations, validate_training_authority, validate_startup,
)


PARENTS = {
    "methodology_commit": "a" * 40,
    "p8_acceptance_id": "p8acc_fixture",
    "p7_runtime_acceptance_id": "p7rta_fixture",
    "p7_acceptance_id": "p7acc_fixture",
    "p6_acceptance_id": "mda_fixture",
    "p5_validation_acceptance_id": "fqsa_fixture",
    "p4_bank_id": "augbank_fixture",
    "p4_bank_acceptance_id": "aba_fixture",
    "p3_cache_acceptance_id": "osca_fixture",
    "production_cache_id": "p9cache_fixture",
    "production_cache_acceptance_id": "p9ca_fixture",
    "v1_retirement_id": "p9ret_" + "b" * 24,
}


def authority():
    return build_training_authority(configuration_id="cfg_d48", configuration_hash="c" * 64,
                                    scientific_implementation_hash="d" * 64, root_seed=17, parents=PARENTS)


def state_presence():
    return {key: True for key in (
        "online_model", "ema_model", "optimizer", "scheduler", "queue", "sampler", "rng_states",
        "validation_trace", "training_trace", "early_stopping", "best_checkpoint") } | {"amp_scaler": None}


def stamp(index): return f"2026-09-01T01:00:{index:02d}Z"


def start(controller):
    auth = controller.authority
    controller.append("RUN_AUTHORIZED", {
        "authority_hash": auth["content_sha256"], "scientific_configuration_hash": auth["content"]["scientific"]["configuration_hash"],
        "parent_identities": auth["content"]["parents"], "duplicate_run_key": auth["content"]["scientific_run_key"],
    }, occurred_at=stamp(1))
    controller.append("RUN_STARTING", {"owner_id": "fixture", "execution_environment_digest": "d" * 64,
                                        "training_lock_key": auth["content"]["scientific_run_key"]}, occurred_at=stamp(2))
    controller.append("RUN_STARTED", {"process_id": "fixture", "world_size": 2, "runtime_digest": "e" * 64}, occurred_at=stamp(3))


def checkpoint_event(controller):
    checkpoint_id = "p9ck_" + "f" * 24
    controller.append("VALIDATION_CHECKPOINT_COMMITTED", {
        "completed_epoch": 5, "resume_epoch": 6, "optimizer_update": 380,
        "validation_id": "p9val_" + "a" * 24, "checkpoint_id": checkpoint_id,
        "checkpoint_payload_sha256": "1" * 64, "checkpoint_manifest_sha256": "2" * 64,
        "validation_retrieval_loss": 1.0, "mean_source_separation_margin": 0.1,
        "selector_state": {"best_checkpoint_id": checkpoint_id, "events_without_improvement": 0},
        "queue": {"count": 8192, "pointer": 0, "enqueue_count": 24320, "state_sha256": "3" * 64},
        "sampler": {"epoch": 6, "cursor": 0, "state_sha256": "4" * 64},
        "state_presence": {key: True for key in ("online_model", "ema_model", "optimizer", "scheduler",
                           "rng_states", "queue", "sampler", "early_stopping", "best_checkpoint", "validation_trace")},
        "atomic_completion_marker": {"protocol": "native_v2_atomic_commit", "status": "COMPLETE"},
        "source_run_id": controller.run_id,
    }, occurred_at=stamp(4), writer_role="rank0", writer_id="science-rank0")


def test_authority_and_run_identity_are_exact_and_cfg_main_is_blocked():
    first = authority(); second = authority()
    assert canonical_json_bytes(first) == canonical_json_bytes(second)
    assert training_run_id(first) == training_run_id(second)
    validate_training_authority(first)
    with pytest.raises(TrainingControllerError, match="CFG_MAIN"):
        build_training_authority(configuration_id="cfg_main", configuration_hash="c" * 64,
                                 scientific_implementation_hash="d" * 64, root_seed=17, parents=PARENTS)


def test_control_plane_module_has_no_scientific_runtime_imports():
    source = (ROOT / "python/p9_v2_training_controller.py").read_text(encoding="utf-8")
    for prohibited in ("import torch", "import p9_model", "import p7_training", "DataLoader", "optimizer.step", "backward("):
        assert prohibited not in source


def test_real_read_only_startup_inputs_pass_for_cfg_d48_without_creating_a_run(tmp_path):
    contract = yaml.safe_load((ROOT / "config/p9_v2_training_controller.yml").read_text())
    contract["roots"]["writable_runs"] = str(tmp_path / "writable")
    matrix = json.loads((Path(contract["roots"]["p8_bundle"]) / "hyperparameter_configuration_matrix.json").read_text())
    row = next(item for item in matrix["rows"] if item["configuration_id"] == "cfg_d48")
    parents = dict(contract["parents"]); parents["methodology_commit"] = contract["source"]["dissertation_commit"]
    allowed = {key: parents[key] for key in PARENTS}
    value = build_training_authority(configuration_id="cfg_d48", configuration_hash=row["scientific_hash"],
                                     scientific_implementation_hash="d" * 64, root_seed=17, parents=allowed)
    p8 = Path(contract["roots"]["p8_bundle"])
    inputs = StartupInputs(
        fuse_root=ROOT, dissertation_root=Path.home() / "dhnyu-masters-dissertation",
        retirement_manifest=Path(contract["roots"]["immutable_publication"]) / "canonical/retirement" /
            contract["parents"]["v1_retirement_id"] / "retirement_manifest.json",
        p8_acceptance=p8 / "formal_experiment_plan_acceptance.json",
        p8_matrix=p8 / "hyperparameter_configuration_matrix.json",
        production_cache_root=Path(contract["roots"]["production_cache"]),
        production_cache_acceptance=Path(contract["roots"]["production_cache_acceptance"]),
        writable_root=tmp_path / "writable", immutable_root=Path(contract["roots"]["immutable_publication"]),
        expected_dissertation_commit=contract["source"]["dissertation_commit"],
        expected_retirement_id=contract["parents"]["v1_retirement_id"],
        expected_p8_acceptance_id=contract["parents"]["p8_acceptance_id"],
        expected_cache_id=contract["parents"]["production_cache_id"],
        expected_cache_acceptance_id=contract["parents"]["production_cache_acceptance_id"],
        expected_cache_manifest_sha256=contract["production_cache_manifest_sha256"], expected_parents=allowed,
    )
    result = validate_startup(value, inputs, accepted_hashes=set(),
                              require_clean=False, cuda_devices=2)
    assert result["status"] == "PASS" and not (tmp_path / "writable" / value["content"]["scientific_run_key"]).exists()


def test_explicit_eligibility_snapshot_blocks_all_accepted_p9_a_without_latest_lookup():
    contract = yaml.safe_load((ROOT / "config/p9_v2_training_controller.yml").read_text())
    ids, hashes = accepted_scientific_configurations(
        Path(contract["roots"]["immutable_publication"]) / "canonical", contract["roots"]["eligibility_snapshot"])
    assert ids == {
        "cfg_main", "cfg_d48", "cfg_d128", "cfg_k2", "cfg_k4", "cfg_k16",
        "cfg_intensity_05", "cfg_intensity_20", "cfg_ema_990", "cfg_ip_0",
        "cfg_lr_2", "cfg_lr_3", "cfg_lr_10",
    }
    assert len(hashes) == 13


def test_controller_replays_normal_start_and_clean_shutdown(tmp_path):
    controller = TrainingController(authority(), tmp_path / "ledger", created_at=stamp(0)); start(controller)
    state = controller.replay()
    assert (state.scientific_state, state.operational_state) == ("IN_PROGRESS", "RUNNING")
    controller.append("TRAINING_INTERRUPTED", {
        "last_durable_boundary": {"completed_epoch": 0, "resume_epoch": 1, "optimizer_update": 0}, "resumable_checkpoint_committed": False,
        "resume_policy": "RESTART", "interruption_reason": "CLEAN_NONTRAINING_SHUTDOWN",
    }, occurred_at=stamp(4))
    controller.close()
    assert read_ledger(controller.ledger_root).closed


def test_exact_resume_and_scientific_divergence_are_distinct(tmp_path):
    c = TrainingController(authority(), tmp_path / "resume", created_at=stamp(0)); start(c)
    checkpoint_event(c)
    c.append("TRAINING_INTERRUPTED", {
        "last_durable_boundary": {"completed_epoch": 5, "resume_epoch": 6, "optimizer_update": 380},
        "resumable_checkpoint_committed": True, "resume_policy": "EXACT_RESUME", "interruption_reason": "NODE_LOSS",
    }, occurred_at=stamp(5))
    assert c.resume_allowed()
    d = TrainingController(authority(), tmp_path / "diverged", created_at=stamp(0)); start(d)
    d.append("TRAINING_FAILED", {"failure_class": "SCIENTIFIC_DIVERGENCE", "failure_stage": "forward_finite_check",
                                  "last_durable_boundary": None, "resumable_checkpoint_committed": False,
                                  "resume_policy": "RESTART"}, occurred_at=stamp(4))
    state = d.replay()
    assert state.operational_state == "TRAINING_FAILED" and not d.resume_allowed()


def _hold_lock(root, key, entered, release):
    with TrainingRunLock(root, key): entered.set(); release.wait(10)


def test_duplicate_controller_start_is_rejected_and_stale_owner_bytes_are_harmless(tmp_path):
    root = tmp_path / "locks"; key = "a" * 64
    entered = multiprocessing.Event(); release = multiprocessing.Event()
    process = multiprocessing.Process(target=_hold_lock, args=(root, key, entered, release)); process.start()
    assert entered.wait(5)
    try:
        with pytest.raises(DuplicateRunError):
            with TrainingRunLock(root, key): pass
    finally:
        release.set(); process.join(5)
    (root / f"{key}.lock").write_text("pid=stale\n", encoding="utf-8")
    with TrainingRunLock(root, key): pass


@pytest.mark.parametrize("point,committed", [
    ("after_staging_create", False), ("after_payload_publish_before_manifest", False),
    ("after_manifest_commit_before_directory_publish", False),
])
def test_checkpoint_crash_before_directory_publication_never_commits(tmp_path, point, committed):
    payload = tmp_path / "worker.pt"; payload.write_bytes(b"opaque-state")
    def crash(observed):
        if observed == point: raise RuntimeError(point)
    with pytest.raises(RuntimeError, match=point):
        publish_checkpoint(payload, tmp_path / "checkpoints", run_id=training_run_id(authority()),
                           completed_epoch=5, optimizer_update=380, state_presence=state_presence(), fault=crash)
    canonical = [path for path in (tmp_path / "checkpoints").iterdir() if not path.name.startswith(".")]
    assert canonical == []


def test_checkpoint_publication_is_content_addressed_and_detects_mutation(tmp_path):
    payload = tmp_path / "worker.pt"; payload.write_bytes(b"opaque-state")
    root, manifest = publish_checkpoint(payload, tmp_path / "checkpoints", run_id=training_run_id(authority()),
                                        completed_epoch=5, optimizer_update=380, state_presence=state_presence())
    again, same = publish_checkpoint(payload, tmp_path / "checkpoints", run_id=training_run_id(authority()),
                                     completed_epoch=5, optimizer_update=380, state_presence=state_presence())
    assert root == again and manifest == same and validate_checkpoint(root) == manifest
    assert sha256_file(root / "checkpoint.pt") == manifest["payload"]["sha256"]
    (root / "checkpoint.pt").write_bytes(b"changed")
    with pytest.raises(TrainingControllerError, match="PAYLOAD_HASH"):
        validate_checkpoint(root)


def test_checkpoint_crash_after_directory_publish_is_committed_and_retry_validates(tmp_path):
    payload = tmp_path / "worker.pt"; payload.write_bytes(b"opaque-state")
    def crash(point):
        if point == "after_checkpoint_directory_publish_before_fsync": raise RuntimeError(point)
    with pytest.raises(RuntimeError, match="after_checkpoint_directory_publish"):
        publish_checkpoint(payload, tmp_path / "checkpoints", run_id=training_run_id(authority()),
                           completed_epoch=5, optimizer_update=380, state_presence=state_presence(), fault=crash)
    committed = next(path for path in (tmp_path / "checkpoints").iterdir() if not path.name.startswith("."))
    manifest = validate_checkpoint(committed)
    retried, same = publish_checkpoint(payload, tmp_path / "checkpoints", run_id=training_run_id(authority()),
                                       completed_epoch=5, optimizer_update=380, state_presence=state_presence())
    assert retried == committed and same == manifest


@pytest.mark.parametrize("point,expected_events", [
    ("after_checkpoint_commit_before_ledger_event", 0), ("after_checkpoint_ledger_event_commit", 1),
])
def test_validation_checkpoint_binding_crash_is_absent_or_exactly_once(tmp_path, point, expected_events):
    c = TrainingController(authority(), tmp_path / "ledger", created_at=stamp(0)); start(c)
    payload = tmp_path / "worker.pt"; payload.write_bytes(b"opaque-state")
    checkpoint_id = None
    def crash(observed):
        if observed == point: raise RuntimeError(point)
    kwargs = dict(
        completed_epoch=5, optimizer_update=380, validation_id="p9val_" + "a" * 24,
        validation_retrieval_loss=1.0, mean_source_separation_margin=0.1,
        selector_state={"best_checkpoint_id": None, "events_without_improvement": 0},
        queue={"count": 8192, "pointer": 0, "enqueue_count": 24320, "state_sha256": "3" * 64},
        sampler={"epoch": 6, "cursor": 0, "state_sha256": "4" * 64}, state_presence=state_presence(),
        occurred_at=stamp(4), fault=crash)
    with pytest.raises(RuntimeError, match=point):
        c.commit_validation_checkpoint(payload, tmp_path / "checkpoints", **kwargs)
    events = [event for event in read_ledger(c.ledger_root).events if event["event_type"] == "VALIDATION_CHECKPOINT_COMMITTED"]
    assert len(events) == expected_events
    kwargs["fault"] = lambda _: None
    event = c.commit_validation_checkpoint(payload, tmp_path / "checkpoints", **kwargs)
    assert event["payload"]["checkpoint_id"].startswith("p9ck_")
    assert len([item for item in read_ledger(c.ledger_root).events if item["event_type"] == "VALIDATION_CHECKPOINT_COMMITTED"]) == 1


@pytest.mark.parametrize("point", [
    "before_staging_file_creation", "after_staging_creation_before_write", "during_stage_write",
    "after_write_before_file_fsync", "after_file_fsync_before_verification", "after_verification_before_rename",
])
def test_ledger_crash_before_commit_replays_previous_state(tmp_path, point):
    c = TrainingController(authority(), tmp_path / point, created_at=stamp(0))
    def crash(observed):
        if observed == point: raise RuntimeError(point)
    with pytest.raises(RuntimeError, match=point):
        c.append("RUN_AUTHORIZED", {"authority_hash": c.authority["content_sha256"],
                 "scientific_configuration_hash": "c" * 64, "parent_identities": PARENTS,
                 "duplicate_run_key": c.authority["content"]["scientific_run_key"]}, occurred_at=stamp(1), fault=crash)
    assert read_ledger(c.ledger_root).last_sequence == 0


@pytest.mark.parametrize("point", ["after_rename_before_directory_fsync", "after_directory_fsync_before_tail_cache", "during_tail_cache_replacement"])
def test_ledger_crash_after_commit_replays_event_exactly_once(tmp_path, point):
    c = TrainingController(authority(), tmp_path / point, created_at=stamp(0))
    def crash(observed):
        if observed == point: raise RuntimeError(point)
    with pytest.raises(RuntimeError, match=point):
        c.append("RUN_AUTHORIZED", {"authority_hash": c.authority["content_sha256"],
                 "scientific_configuration_hash": "c" * 64, "parent_identities": PARENTS,
                 "duplicate_run_key": c.authority["content"]["scientific_run_key"]}, occurred_at=stamp(1), fault=crash)
    assert read_ledger(c.ledger_root).last_sequence == 1
