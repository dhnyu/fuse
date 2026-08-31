from __future__ import annotations

import copy
import hashlib
import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from p9_v2_bundle import validate_run_bundle  # noqa: E402
from p9_v2_legacy_import import (  # noqa: E402
    EXPECTED_SELECTED_CHECKPOINT,
    EXPECTED_SELECTED_MANIFEST_SHA256,
    EXPECTED_SELECTED_PAYLOAD_SHA256,
    LegacyImportError,
    _safe_load_checkpoint,
    build_legacy_dry_run_bundle,
    historical_p9_sources,
    inspect_legacy_run,
    map_legacy_run_to_v2,
    validate_legacy_import,
)
from p9_v2_schema import validate_instance  # noqa: E402


@pytest.fixture(scope="module")
def historical_inspection():
    return inspect_legacy_run()


def _sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _mutated(inspection, index: int, **changes):
    pairs = [copy.deepcopy(pair) for pair in inspection.pairs]
    pairs[index].update(changes)
    return replace(inspection, pairs=tuple(pairs))


def _canonical_bundle_files(path: Path) -> dict[str, bytes]:
    return {
        item.relative_to(path).as_posix(): item.read_bytes()
        for item in sorted(path.rglob("*"))
        if item.is_file()
    }


def test_real_history_maps_all_25_pairs_and_selected_hashes(historical_inspection):
    inspection = historical_inspection
    result = validate_legacy_import(inspection)
    selected = next(pair for pair in inspection.pairs if pair["checkpoint_id"] == EXPECTED_SELECTED_CHECKPOINT)
    assert result.valid and result.migration_verdict == "MIGRATION_DRY_RUN_ELIGIBLE"
    assert result.pair_count == 25 and result.missing_blocking == 0
    assert selected["completed_epoch"] == 105
    assert selected["checkpoint_payload_sha256"] == EXPECTED_SELECTED_PAYLOAD_SHA256
    assert selected["checkpoint_manifest_sha256"] == EXPECTED_SELECTED_MANIFEST_SHA256
    assert selected["validation"]["validation_retrieval_loss"] == pytest.approx(0.3806893528, abs=5e-11)
    assert selected["validation"]["mean_source_separation_margin"] == pytest.approx(0.2876026034, abs=5e-11)


def test_all_checkpoint_state_epoch_queue_sampler_and_evaluation_evidence(historical_inspection):
    for ordinal, pair in enumerate(historical_inspection.pairs, 1):
        epoch = ordinal * 5
        update = epoch * 76
        enqueue = update * 64
        assert (pair["completed_epoch"], pair["resume_epoch"], pair["optimizer_update"]) == (epoch, epoch + 1, update)
        assert pair["sampler"] == {"epoch": epoch + 1, "cursor": 0}
        assert pair["queue"] == {
            "count": min(8192, enqueue), "pointer": enqueue % 8192, "enqueue_count": enqueue
        }
        assert pair["rng_rank_count"] == pair["world_size"] == 2
        assert pair["scaler_status"] == "NOT_APPLICABLE"
        assert all(pair["state_presence"].values())
        assert pair["validation"]["evaluation_queries_consumed"] == 0
    assert historical_inspection.pairs[-1]["optimizer_update"] == 9500
    assert historical_inspection.pairs[-1]["early_stopping_count"] == 4


def test_field_classification_and_legacy_annotation_are_explicit(historical_inspection):
    assert historical_inspection.classification_counts == {
        "DIRECTLY_AVAILABLE": 21,
        "DETERMINISTICALLY_DERIVABLE": 6,
        "AVAILABLE_WITH_LEGACY_ANNOTATION": 2,
        "NOT_APPLICABLE": 2,
        "MISSING_BLOCKING": 0,
    }
    annotation = historical_inspection.legacy_annotation
    validate_instance("legacy_import", annotation)
    assert annotation["status"] == "NONCANONICAL_DRY_RUN"
    assert annotation["canonical_publication_eligible"] is False
    assert annotation["acceptance_eligible"] is False
    assert annotation["atomic_completion"]["classification"] == "AVAILABLE_WITH_LEGACY_ANNOTATION"


def test_dry_run_ledger_bundle_and_pure_finalizer(historical_inspection, tmp_path):
    result = build_legacy_dry_run_bundle(historical_inspection, tmp_path)
    selected = result.finalization_result["selected_checkpoint"]
    assert result.mapping.replay.scientific_state == "COMPLETE"
    assert result.mapping.replay.operational_state == "FINALIZATION_FAILED"
    assert result.mapping.replay.resumability_state == "NOT_APPLICABLE_SCIENTIFICALLY_COMPLETE"
    assert result.mapping.replay.last_committed_sequence == 106
    assert result.bundle_validation.valid
    assert result.bundle_validation.completeness == "SCIENTIFICALLY_COMPLETE"
    assert result.finalization_result["status"] == "SUCCEEDED"
    assert selected["checkpoint_id"] == EXPECTED_SELECTED_CHECKPOINT
    assert selected["completed_epoch"] == 105
    assert selected["validation_retrieval_loss"] == pytest.approx(0.3806893528, abs=5e-11)
    assert selected["mean_source_separation_margin"] == pytest.approx(0.2876026034, abs=5e-11)
    assert "v2_d_noncanonical_dry_run/ineligible_for_acceptance" in result.bundle_path.as_posix()
    assert not list(tmp_path.rglob("p9accv2_*"))


def test_rerun_and_source_order_are_byte_deterministic(historical_inspection, tmp_path):
    reversed_inspection = inspect_legacy_run(reverse_discovery=True)
    assert reversed_inspection.imported_run_id == historical_inspection.imported_run_id
    assert reversed_inspection.pairs == historical_inspection.pairs
    left = build_legacy_dry_run_bundle(historical_inspection, tmp_path / "left")
    right = build_legacy_dry_run_bundle(reversed_inspection, tmp_path / "right")
    assert left.bundle_id == right.bundle_id
    assert left.bundle_hash == right.bundle_hash
    assert left.finalization_result == right.finalization_result
    assert _canonical_bundle_files(left.bundle_path) == _canonical_bundle_files(right.bundle_path)
    left_committed = left.mapping.ledger_root / "commit/ledger_manifest.json"
    right_committed = right.mapping.ledger_root / "commit/ledger_manifest.json"
    assert left_committed.read_bytes() == right_committed.read_bytes()


def test_bundle_is_targets_independent(historical_inspection, tmp_path):
    result = build_legacy_dry_run_bundle(historical_inspection, tmp_path)
    targets = tmp_path / "_targets" / "meta"
    targets.parent.mkdir(parents=True)
    targets.write_text("corrupt and irrelevant", encoding="utf-8")
    again = validate_run_bundle(result.bundle_path, result.mapping.locator_roots)
    assert again == result.bundle_validation


def test_restricted_loader_hash_gate_precedes_deserialization(historical_inspection, monkeypatch):
    selected = next(pair for pair in historical_inspection.pairs if pair["checkpoint_id"] == EXPECTED_SELECTED_CHECKPOINT)
    path = historical_inspection.sources.attempt_root / selected["payload_relative_path"]
    import torch

    monkeypatch.setattr(torch, "load", lambda *args, **kwargs: pytest.fail("deserialization was reached"))
    with pytest.raises(LegacyImportError, match="PAYLOAD_HASH_MISMATCH"):
        _safe_load_checkpoint(path, "f" * 64)


def test_restricted_loader_uses_weights_only_and_local_safe_globals(historical_inspection, monkeypatch):
    selected = next(pair for pair in historical_inspection.pairs if pair["checkpoint_id"] == EXPECTED_SELECTED_CHECKPOINT)
    path = historical_inspection.sources.attempt_root / selected["payload_relative_path"]
    observed = {}
    import torch

    def capture(*args, **kwargs):
        observed.update(kwargs)
        return {}

    monkeypatch.setattr(torch, "load", capture)
    assert _safe_load_checkpoint(path, EXPECTED_SELECTED_PAYLOAD_SHA256) == {}
    assert observed["weights_only"] is True
    assert observed["map_location"] == "cpu"


@pytest.mark.parametrize(
    ("change", "error"),
    [
        (lambda data: data.__setitem__("schema_version", "9.0.0"), "UNSUPPORTED_HISTORICAL_SCHEMA"),
        (lambda data: data["rows"][0].__setitem__("checkpoint_manifest_sha256", "f" * 64), "MANIFEST_HASH_MISMATCH"),
        (lambda data: data["rows"][0].__setitem__("checkpoint_payload_sha256", "f" * 64), "PAYLOAD_HASH_MISMATCH"),
        (lambda data: data["rows"][0].__setitem__("validation_epoch", 6), "EPOCH_MISMATCH"),
        (lambda data: data["rows"][0].__setitem__("resume_epoch", 7), "RESUME_EPOCH_MISMATCH"),
        (lambda data: data["rows"][0].__setitem__("global_update", 381), "OPTIMIZER_UPDATE_MISMATCH"),
        (lambda data: data["rows"][0]["validation"].__setitem__("validation_retrieval_loss", 9.0), "VALIDATION_COUNTERPART_MISMATCH"),
    ],
)
def test_copied_join_audit_corruption_fails_before_checkpoint_load(tmp_path, monkeypatch, change, error):
    sources = historical_p9_sources()
    copied = json.loads(sources.join_audit_path.read_text(encoding="utf-8"))
    change(copied)
    copied_path = tmp_path / "checkpoint_join_audit.json"
    copied_path.write_text(json.dumps(copied), encoding="utf-8")
    monkeypatch.setattr("p9_v2_legacy_import._safe_load_checkpoint", lambda *args, **kwargs: pytest.fail("checkpoint load reached"))
    with pytest.raises(LegacyImportError, match=error):
        inspect_legacy_run(replace(sources, join_audit_path=copied_path))


def test_missing_checkpoint_manifest_is_rejected(tmp_path):
    from p9_v2_legacy_import import _immutable_file

    with pytest.raises(LegacyImportError, match="SOURCE_FILE_INVALID"):
        _immutable_file(tmp_path / "missing-checkpoint-manifest.json")


@pytest.mark.parametrize(
    ("mutation", "error"),
    [
        (lambda value: _mutated(value, 0, completed_epoch=6), "EPOCH_MISMATCH"),
        (lambda value: _mutated(value, 0, resume_epoch=7), "RESUME_EPOCH_MISMATCH"),
        (lambda value: _mutated(value, 0, optimizer_update=381), "OPTIMIZER_UPDATE_MISMATCH"),
        (lambda value: _mutated(value, 0, checkpoint_payload_sha256="f" * 64), "PAYLOAD_HASH_MISMATCH"),
        (lambda value: _mutated(value, 0, checkpoint_manifest_sha256="f" * 64), "MANIFEST_HASH_MISMATCH"),
        (lambda value: _mutated(value, 0, queue={"count": 1, "pointer": 0, "enqueue_count": 1}), "QUEUE_ARITHMETIC_MISMATCH"),
        (lambda value: _mutated(value, 0, sampler={"epoch": 1, "cursor": 1}), "SAMPLER_MISMATCH"),
        (lambda value: _mutated(value, 0, rng_rank_count=1), "RNG_STATE_MISMATCH"),
        (lambda value: _mutated(value, 0, early_stopping_count=3), "SELECTOR_TRACE_MISMATCH"),
        (lambda value: _mutated(value, 24, optimizer_update=9499), "STOPPING_BOUNDARY_MISMATCH"),
    ],
)
def test_import_validation_corruption_matrix(historical_inspection, mutation, error):
    result = validate_legacy_import(mutation(historical_inspection))
    assert not result.valid and result.migration_verdict == "MIGRATION_DRY_RUN_BLOCKED"
    assert error in result.errors


def test_duplicate_missing_and_evaluation_contamination_are_rejected(historical_inspection):
    missing = replace(historical_inspection, pairs=historical_inspection.pairs[:-1])
    assert "PAIR_COUNT_MISMATCH" in validate_legacy_import(missing).errors
    duplicate = _mutated(historical_inspection, 1, checkpoint_id=historical_inspection.pairs[0]["checkpoint_id"])
    assert "DUPLICATE_CHECKPOINT_ID" in validate_legacy_import(duplicate).errors
    validation = copy.deepcopy(historical_inspection.pairs[0]["validation"])
    validation["evaluation_queries_consumed"] = 1
    contaminated = _mutated(historical_inspection, 0, validation=validation)
    assert "EVALUATION_CONSUMPTION_NONZERO" in validate_legacy_import(contaminated).errors


def test_source_inventory_and_missing_blocking_corruption_are_rejected(historical_inspection):
    inventory = [dict(item) for item in historical_inspection.source_inventory]
    inventory[0]["content_sha256"] = "f" * 64
    changed = replace(historical_inspection, source_inventory=tuple(inventory))
    assert "SOURCE_INVENTORY_MISMATCH" in validate_legacy_import(changed).errors
    presence = dict(historical_inspection.pairs[0]["state_presence"])
    presence["rng_states"] = False
    missing = _mutated(historical_inspection, 0, state_presence=presence)
    assert "MISSING_BLOCKING" in validate_legacy_import(missing).errors


def test_unsupported_annotation_and_terminal_state_are_rejected(historical_inspection):
    annotation = copy.deepcopy(historical_inspection.legacy_annotation)
    annotation["schema_version"] = "9.0.0"
    assert "LEGACY_ANNOTATION_INVALID" in validate_legacy_import(
        replace(historical_inspection, legacy_annotation=annotation)
    ).errors
    assert "TERMINAL_STATE_MISMATCH" in validate_legacy_import(
        replace(historical_inspection, terminal_state={**historical_inspection.terminal_state, "state": "COMPLETE"})
    ).errors


def test_real_selected_artifacts_remain_byte_identical(historical_inspection):
    selected = next(pair for pair in historical_inspection.pairs if pair["checkpoint_id"] == EXPECTED_SELECTED_CHECKPOINT)
    payload = historical_inspection.sources.attempt_root / selected["payload_relative_path"]
    manifest = historical_inspection.sources.attempt_root / selected["manifest_relative_path"]
    assert _sha256(payload) == EXPECTED_SELECTED_PAYLOAD_SHA256
    assert _sha256(manifest) == EXPECTED_SELECTED_MANIFEST_SHA256
