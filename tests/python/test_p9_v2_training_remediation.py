from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from p9_v2_canonical import canonical_json_bytes, canonical_sha256  # noqa: E402
from p9_v2_finalization import make_selection_contract  # noqa: E402
from p9_v2_training_controller import (  # noqa: E402
    TrainingController, TrainingControllerError, build_training_authority,
    make_worker_request, training_run_id, validate_worker_message,
)
from p9_v2_training_lifecycle import (  # noqa: E402
    publish_native_lifecycle, scientific_configuration_content,
)


PARENTS = {
    "methodology_commit": "a" * 40, "p8_acceptance_id": "p8acc_fixture",
    "p7_runtime_acceptance_id": "p7rta_fixture", "p7_acceptance_id": "p7acc_fixture",
    "p6_acceptance_id": "mda_fixture", "p5_validation_acceptance_id": "fqsa_fixture",
    "p4_bank_id": "augbank_fixture", "p4_bank_acceptance_id": "aba_fixture",
    "p3_cache_acceptance_id": "osca_fixture", "production_cache_id": "p9cache_fixture",
    "production_cache_acceptance_id": "p9ca_fixture", "v1_retirement_id": "p9ret_" + "b" * 24,
}


def stamp(index: int) -> str: return f"2026-09-01T08:00:{index:02d}Z"


def row() -> dict:
    return {
        "configuration_family": "hyperparameter", "configuration_id": "cfg_d48",
        "scientific": {"d": 48}, "bank_binding": {"effective_k": 8},
        "validation_acceptance_id": "fqsa_fixture", "run_seed_namespace": "p9-a/cfg_d48",
        "run_seed_formula": "fixture", "parent_p7_acceptance_id": "p7acc_fixture",
        "runtime_acceptance_id": "p7rta_fixture", "scientific_hash": "9" * 64,
    }


def authority() -> dict:
    content_hash = canonical_sha256(scientific_configuration_content(row()))
    return build_training_authority(
        configuration_id="cfg_d48", configuration_hash=content_hash,
        p8_configuration_hash="9" * 64, scientific_implementation_hash="8" * 64,
        root_seed=7, parents=PARENTS,
        parent_hashes={key: canonical_sha256({"identity": value}) for key, value in PARENTS.items()})


def start(controller: TrainingController) -> None:
    auth = controller.authority
    controller.append("RUN_AUTHORIZED", {
        "authority_hash": auth["content_sha256"],
        "scientific_configuration_hash": auth["content"]["scientific"]["configuration_hash"],
        "parent_identities": auth["content"]["parents"],
        "duplicate_run_key": auth["content"]["scientific_run_key"],
    }, occurred_at=stamp(1))
    controller.append("RUN_STARTING", {"owner_id": "fixture",
        "execution_environment_digest": auth["content_sha256"],
        "training_lock_key": auth["content"]["scientific_run_key"]}, occurred_at=stamp(2))
    controller.append("RUN_STARTED", {"process_id": "fixture", "world_size": 2,
        "runtime_digest": auth["content_sha256"]}, occurred_at=stamp(3))


def checkpoint_body(controller: TrainingController, staged: str) -> dict:
    return {
        "staged_payload": staged, "completed_epoch": 5, "resume_epoch": 6,
        "optimizer_update": 2, "validation_id": "p9val_" + "a" * 24,
        "validation_retrieval_loss": 0.5, "mean_source_separation_margin": 0.2,
        "selector_state": {"best_checkpoint_id": None, "events_without_improvement": 0},
        "current_candidate_selected": True,
        "queue": {"count": 128, "pointer": 128, "enqueue_count": 128, "state_sha256": "3" * 64},
        "sampler": {"epoch": 6, "cursor": 0, "state_sha256": "4" * 64},
        "state_presence": {key: True for key in ("online_model", "ema_model", "optimizer", "scheduler",
            "queue", "sampler", "rng_states", "validation_trace", "training_trace", "early_stopping",
            "best_checkpoint")} | {"amp_scaler": None},
        "source_run_id": controller.run_id, "occurred_at": stamp(5),
    }


def staged_payload(tmp_path: Path, controller: TrainingController) -> tuple[Path, str]:
    stage_id = "p9stage_" + "c" * 24
    relative = f"requests/{stage_id}/checkpoint.pt"
    path = tmp_path / "staging" / relative; path.parent.mkdir(parents=True); path.write_bytes(b"opaque-science-state")
    return path, relative


def test_ipc_request_identity_is_deterministic_and_corruption_is_rejected():
    body = {"event_type": "EPOCH_STARTED", "occurred_at": stamp(1),
            "payload": {"epoch": 1, "starting_optimizer_update": 0, "sampler_cursor": 0},
            "writer_id": "science-rank0", "writer_role": "rank0"}
    first = make_worker_request("EVENT_PROPOSAL", body); second = make_worker_request("EVENT_PROPOSAL", dict(reversed(list(body.items()))))
    assert canonical_json_bytes(first) == canonical_json_bytes(second)
    validate_worker_message(first)
    first["request_id"] = "p9req_" + "0" * 24
    with pytest.raises(TrainingControllerError, match="REQUEST_ID_MISMATCH"):
        validate_worker_message(first)


def test_checkpoint_request_is_controller_committed_acknowledged_and_idempotent(tmp_path):
    controller = TrainingController(authority(), tmp_path / "ledger", created_at=stamp(0)); start(controller)
    _, relative = staged_payload(tmp_path, controller)
    request = make_worker_request("CHECKPOINT_COMMIT_REQUEST", checkpoint_body(controller, relative))
    first = controller.handle_worker_request(request, staging_root=tmp_path / "staging",
                                             checkpoint_root=tmp_path / "checkpoints")
    second = controller.handle_worker_request(request, staging_root=tmp_path / "staging",
                                              checkpoint_root=tmp_path / "checkpoints")
    assert first == second and first["body"]["status"] == "COMMITTED"
    assert first["body"]["checkpoint_id"].startswith("p9ck_")
    assert controller.replay().latest_optimizer_update == 2


def test_lost_checkpoint_ack_reconciles_from_ledger_after_controller_reopen(tmp_path):
    auth = authority(); controller = TrainingController(auth, tmp_path / "ledger", created_at=stamp(0)); start(controller)
    _, relative = staged_payload(tmp_path, controller)
    request = make_worker_request("CHECKPOINT_COMMIT_REQUEST", checkpoint_body(controller, relative))
    committed = controller.handle_worker_request(request, staging_root=tmp_path / "staging",
                                                 checkpoint_root=tmp_path / "checkpoints")
    reopened = TrainingController(auth, tmp_path / "ledger", created_at=stamp(9))
    reconciled = reopened.handle_worker_request(request, staging_root=tmp_path / "staging",
                                                checkpoint_root=tmp_path / "checkpoints")
    assert reconciled == committed
    assert reopened.replay().last_committed_sequence == 4


def test_worker_staging_without_request_is_noncanonical_debris(tmp_path):
    controller = TrainingController(authority(), tmp_path / "ledger", created_at=stamp(0)); start(controller)
    staged_payload(tmp_path, controller)
    assert controller.replay().last_committed_sequence == 3
    assert not (tmp_path / "checkpoints").exists()


def test_checkpoint_request_rejects_staging_escape(tmp_path):
    controller = TrainingController(authority(), tmp_path / "ledger", created_at=stamp(0)); start(controller)
    body = checkpoint_body(controller, "requests/p9stage_" + "c" * 24 + "/checkpoint.pt")
    request = make_worker_request("CHECKPOINT_COMMIT_REQUEST", body)
    with pytest.raises(TrainingControllerError, match="STAGING_PAYLOAD_INVALID"):
        controller.handle_worker_request(request, staging_root=tmp_path / "staging",
                                         checkpoint_root=tmp_path / "checkpoints")


def test_science_worker_has_no_v1_or_canonical_publication_dependency():
    source = (ROOT / "python/p9_v2_training_worker.py").read_text(encoding="utf-8")
    for prohibited in ("p9_formal_training", "p9_formal_execution", "p9_v1", "publish_acceptance",
                       "LedgerWriter", "import targets", "resolve_committed"):
        assert prohibited not in source
    assert "optimizer.step()" in source and "total.backward()" in source


def test_native_training_evidence_executes_bundle_finalization_acceptance_and_resolver(tmp_path):
    auth = authority(); controller = TrainingController(auth, tmp_path / "ledger", created_at=stamp(0)); start(controller)
    controller.append("EPOCH_STARTED", {"epoch": 5, "starting_optimizer_update": 0, "sampler_cursor": 0},
                      occurred_at=stamp(4), writer_role="rank0", writer_id="science-rank0")
    _, relative = staged_payload(tmp_path, controller)
    ack = controller.handle_worker_request(make_worker_request(
        "CHECKPOINT_COMMIT_REQUEST", checkpoint_body(controller, relative)),
        staging_root=tmp_path / "staging", checkpoint_root=tmp_path / "checkpoints")
    checkpoint_id = ack["body"]["checkpoint_id"]
    controller.append("EARLY_STOPPING_UPDATED", {
        "selector_state": ack["body"]["selector_state"], "best_checkpoint_id": checkpoint_id,
        "events_without_improvement": 0, "decision_basis": "retrieval_loss_improved"},
        occurred_at=stamp(6), writer_role="rank0", writer_id="science-rank0")
    controller.append("TRAINING_COMPLETED", {"completed_epoch": 5, "resume_epoch": 6,
        "optimizer_update": 2, "reason": "MAXIMUM_EPOCH"}, occurred_at=stamp(7),
        writer_role="rank0", writer_id="science-rank0")
    controller.close()
    matrix = tmp_path / "matrix.json"; matrix.write_text(json.dumps({"rows": [row()]}))
    cache = tmp_path / "cache.json"; cache.write_text(json.dumps({"acceptance_id": "p9ca_fixture", "status": "PASS"}))
    publication = publish_native_lifecycle(
        auth, controller.ledger_root, tmp_path / "checkpoints", matrix, cache,
        tmp_path / "publication", [matrix, cache, ROOT / "python/p9_v2_training_worker.py"],
        eligibility_namespace="fixture-native")
    assert publication.checkpoint_id == checkpoint_id
    assert publication.bundle_id.startswith("p9rb_") and publication.acceptance_id.startswith("p9accv2_")


def test_p8_and_v2_configuration_hashes_are_independently_bound():
    value = authority()
    assert value["content"]["scientific"]["configuration_hash"] != value["content"]["scientific"]["p8_configuration_hash"]
    assert training_run_id(value).startswith("p9runv2_")


def test_scientific_divergence_without_checkpoint_is_nonresumable(tmp_path):
    controller = TrainingController(authority(), tmp_path / "ledger", created_at=stamp(0)); start(controller)
    controller.append("TRAINING_FAILED", {"failure_class": "SCIENTIFIC_DIVERGENCE",
        "failure_stage": "TRAINING_UPDATE", "last_durable_boundary": None,
        "resumable_checkpoint_committed": False, "resume_policy": "FORBIDDEN"}, occurred_at=stamp(4))
    replay = controller.replay()
    assert (replay.scientific_state, replay.operational_state, replay.resumability_state) == (
        "INCOMPLETE", "TRAINING_FAILED", "FORBIDDEN_POLICY")
