from __future__ import annotations

import shutil
import sys
from dataclasses import replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from p9_v2_bundle import (  # noqa: E402
    BundleError,
    build_run_bundle,
    load_run_bundle,
    publish_run_bundle,
    validate_run_bundle,
)
from p9_v2_bundle_test_support import make_bundle_fixture  # noqa: E402


def _published(tmp_path: Path, *, terminal: str = "complete"):
    fixture = make_bundle_fixture(tmp_path / "fixture", terminal=terminal)
    candidate = build_run_bundle(fixture.ledger_root, fixture.inputs, fixture.locator_roots)
    publication = publish_run_bundle(candidate, tmp_path / "published", fixture.locator_roots)
    return fixture, candidate, publication


@pytest.mark.parametrize(
    ("terminal", "completeness", "scientific", "operational", "resumability"),
    [
        ("complete", "SCIENTIFICALLY_COMPLETE", "COMPLETE", "RUNNING", "NOT_APPLICABLE_SCIENTIFICALLY_COMPLETE"),
        ("finalization_failed", "SCIENTIFICALLY_COMPLETE", "COMPLETE", "FINALIZATION_FAILED", "NOT_APPLICABLE_SCIENTIFICALLY_COMPLETE"),
        ("interrupted", "SCIENTIFICALLY_INCOMPLETE", "IN_PROGRESS", "INTERRUPTED_RESUMABLE", "EXACT_RESUME_ALLOWED"),
        ("training_failed", "SCIENTIFICALLY_INCOMPLETE", "INCOMPLETE", "TRAINING_FAILED", "RESTART_REQUIRED"),
    ],
)
def test_scientific_completeness_is_independent_of_operational_state(
    tmp_path, terminal, completeness, scientific, operational, resumability
):
    fixture, _, publication = _published(tmp_path, terminal=terminal)
    result = validate_run_bundle(publication.path, fixture.locator_roots)
    assert result.valid
    assert result.completeness == completeness
    assert result.scientific_state == scientific
    assert result.operational_state == operational
    assert result.resumability_state == resumability


def test_same_evidence_has_identical_bytes_hash_and_id(tmp_path):
    fixture = make_bundle_fixture(tmp_path / "fixture")
    first = build_run_bundle(fixture.ledger_root, fixture.inputs, fixture.locator_roots)
    second = build_run_bundle(fixture.ledger_root, fixture.inputs, fixture.locator_roots)
    assert first == second
    assert first.file_map() == second.file_map()


def test_reordered_input_collections_are_canonicalized(tmp_path):
    first_fixture = make_bundle_fixture(tmp_path / "left")
    second_fixture = make_bundle_fixture(tmp_path / "right", reverse_inputs=True)
    first = build_run_bundle(first_fixture.ledger_root, first_fixture.inputs, first_fixture.locator_roots)
    second = build_run_bundle(second_fixture.ledger_root, second_fixture.inputs, second_fixture.locator_roots)
    assert first.bundle_id == second.bundle_id
    assert first.bundle_content_sha256 == second.bundle_content_sha256
    assert first.file_map() == second.file_map()


def test_physical_root_relocation_does_not_change_bundle_identity(tmp_path):
    left = make_bundle_fixture(tmp_path / "left")
    right = make_bundle_fixture(tmp_path / "right")
    first = build_run_bundle(left.ledger_root, left.inputs, left.locator_roots)
    second = build_run_bundle(right.ledger_root, right.inputs, right.locator_roots)
    assert first.bundle_id == second.bundle_id
    assert str(left.external_root) not in b"".join(first.file_map().values()).decode("utf-8", errors="ignore")
    assert str(right.external_root) not in b"".join(second.file_map().values()).decode("utf-8", errors="ignore")


def test_published_bundle_validates_after_external_root_relocation(tmp_path):
    fixture, candidate, publication = _published(tmp_path)
    relocated = tmp_path / "relocated-external"
    shutil.copytree(fixture.external_root, relocated)
    result = validate_run_bundle(publication.path, {next(iter(fixture.locator_roots)): relocated})
    assert result.valid
    assert result.bundle_id == candidate.bundle_id


@pytest.mark.parametrize(
    "variant",
    ["configuration", "selection", "checkpoint"],
)
def test_one_bit_scientific_evidence_changes_bundle_identity(tmp_path, variant):
    base = make_bundle_fixture(tmp_path / "base")
    changed = make_bundle_fixture(
        tmp_path / "changed",
        config_variant="changed" if variant == "configuration" else "base",
        selection_variant="changed" if variant == "selection" else "base",
        payload_variant="changed" if variant == "checkpoint" else "base",
    )
    base_candidate = build_run_bundle(base.ledger_root, base.inputs, base.locator_roots)
    changed_candidate = build_run_bundle(changed.ledger_root, changed.inputs, changed.locator_roots)
    assert base_candidate.bundle_id != changed_candidate.bundle_id
    assert base_candidate.bundle_content_sha256 != changed_candidate.bundle_content_sha256


def test_tail_cache_and_staging_debris_do_not_change_identity(tmp_path):
    fixture = make_bundle_fixture(tmp_path / "fixture")
    before = build_run_bundle(fixture.ledger_root, fixture.inputs, fixture.locator_roots)
    (fixture.ledger_root / "tail.json").write_bytes(b'{"corrupt":')
    (fixture.ledger_root / ".staging" / "uncommitted.incomplete").write_bytes(b"debris")
    after = build_run_bundle(fixture.ledger_root, fixture.inputs, fixture.locator_roots)
    assert before == after


def test_target_metadata_is_absent_and_irrelevant(tmp_path):
    fixture = make_bundle_fixture(tmp_path / "fixture")
    target_metadata = tmp_path / "fixture" / "_targets" / "meta"
    target_metadata.mkdir(parents=True)
    (target_metadata / "meta").write_text("mutable target metadata", encoding="utf-8")
    before = build_run_bundle(fixture.ledger_root, fixture.inputs, fixture.locator_roots)
    shutil.rmtree(target_metadata.parent)
    after = build_run_bundle(fixture.ledger_root, fixture.inputs, fixture.locator_roots)
    assert before == after
    assert b"targets" not in b"".join(before.file_map().values()).lower()


def test_nonzero_evaluation_consumption_is_rejected(tmp_path):
    fixture = make_bundle_fixture(tmp_path / "fixture")
    contaminated = replace(fixture.inputs, evaluation_consumption_count=1)
    with pytest.raises(BundleError, match="PROHIBITED_EVIDENCE"):
        build_run_bundle(fixture.ledger_root, contaminated, fixture.locator_roots)


def test_extra_checkpoint_without_committed_event_is_rejected(tmp_path):
    fixture = make_bundle_fixture(tmp_path / "fixture")
    checkpoint_map = dict(fixture.inputs.checkpoint_locators)
    checkpoint_map["p9ck_" + "f" * 24] = next(iter(checkpoint_map.values()))
    extra = replace(fixture.inputs, checkpoint_locators=checkpoint_map)
    with pytest.raises(BundleError, match="VALIDATION_CHECKPOINT_MISMATCH"):
        build_run_bundle(fixture.ledger_root, extra, fixture.locator_roots)


def test_complete_bundle_requires_exact_final_checkpoint_stopping_boundary(tmp_path):
    fixture = make_bundle_fixture(tmp_path / "fixture", completion_update=761)
    with pytest.raises(BundleError, match="SCIENTIFIC_COMPLETENESS_MISMATCH"):
        build_run_bundle(fixture.ledger_root, fixture.inputs, fixture.locator_roots)


def test_targets_metadata_injected_into_contract_is_rejected(tmp_path):
    fixture = make_bundle_fixture(tmp_path / "fixture")
    bad_selection = dict(fixture.inputs.selection_contract)
    bad_selection["content"] = {**bad_selection["content"], "targets_metadata": {"current": True}}
    contaminated = replace(fixture.inputs, selection_contract=bad_selection)
    with pytest.raises(BundleError, match="PROHIBITED_EVIDENCE"):
        build_run_bundle(fixture.ledger_root, contaminated, fixture.locator_roots)


def test_large_checkpoint_payloads_are_not_copied_into_bundle(tmp_path):
    fixture, candidate, publication = _published(tmp_path)
    bundle_files = {path.relative_to(publication.path).as_posix() for path in publication.path.rglob("*") if path.is_file()}
    assert not any(path.endswith("checkpoint.pt") for path in bundle_files)
    assert all(path.read_bytes() not in candidate.file_map().values() for path in fixture.external_paths if path.name == "checkpoint.pt")


def test_load_returns_only_a_validated_committed_manifest(tmp_path):
    fixture, candidate, publication = _published(tmp_path)
    manifest = load_run_bundle(publication.path, fixture.locator_roots)
    assert manifest["bundle_id"] == candidate.bundle_id
    assert manifest["bundle_status"] == "SCIENTIFICALLY_COMPLETE"
