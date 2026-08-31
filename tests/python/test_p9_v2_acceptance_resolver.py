from __future__ import annotations

import copy
import os
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from p9_v2_acceptance import (  # noqa: E402
    ACCEPTANCE_COMMIT_PATH,
    ACCEPTANCE_PATH,
    FINALIZATION_PATH,
    AcceptanceError,
    publish_acceptance,
    resolve_accepted_checkpoint,
    validate_acceptance,
)
from p9_v2_bundle import build_run_bundle, publish_run_bundle  # noqa: E402
from p9_v2_bundle_test_support import make_bundle_fixture  # noqa: E402
from p9_v2_canonical import canonical_json_bytes, canonical_sha256, parse_canonical_json, sha256_bytes  # noqa: E402
from p9_v2_finalization import finalize_run_bundle  # noqa: E402
from p9_v2_schema import P9V2SchemaError, validate_instance  # noqa: E402


def _case(tmp_path: Path, terminal: str = "complete"):
    fixture = make_bundle_fixture(tmp_path / "fixture", terminal=terminal)
    candidate = build_run_bundle(fixture.ledger_root, fixture.inputs, fixture.locator_roots)
    bundle_publication = publish_run_bundle(candidate, tmp_path / "bundles", fixture.locator_roots)
    result = finalize_run_bundle(bundle_publication.path, fixture.locator_roots)
    authority = fixture.inputs.authority
    publication = publish_acceptance(
        result, bundle_publication.path, fixture.locator_roots, tmp_path / "acceptances",
        authority_id=authority["identity"], authority_hash=authority["content_sha256"],
    )
    return fixture, bundle_publication, result, publication


def _read(path: Path):
    return parse_canonical_json(path.read_bytes())


def _reseal_record(path: Path, mutate) -> tuple[Path, str]:
    record = _read(path / ACCEPTANCE_PATH)
    mutate(record)
    preimage = {key: value for key, value in record.items() if key not in {"acceptance_id", "acceptance_content_sha256"}}
    content_hash = canonical_sha256(preimage)
    record["acceptance_content_sha256"] = content_hash
    record["acceptance_id"] = f"p9accv2_{content_hash[:24]}"
    acceptance_raw = canonical_json_bytes(record)
    finalization_raw = (path / FINALIZATION_PATH).read_bytes()
    os.chmod(path / ACCEPTANCE_PATH, 0o644)
    os.chmod(path / ACCEPTANCE_COMMIT_PATH, 0o644)
    (path / ACCEPTANCE_PATH).write_bytes(acceptance_raw)
    commit = {
        "schema_version": "2.0.0",
        "artifact_type": "p9_v2_acceptance_commit_manifest",
        "acceptance_id": record["acceptance_id"],
        "status": "COMMITTED",
        "acceptance_path": ACCEPTANCE_PATH,
        "acceptance_sha256": sha256_bytes(acceptance_raw),
        "acceptance_size_bytes": len(acceptance_raw),
        "finalization_result_path": FINALIZATION_PATH,
        "finalization_result_sha256": sha256_bytes(finalization_raw),
        "finalization_result_size_bytes": len(finalization_raw),
    }
    (path / ACCEPTANCE_COMMIT_PATH).write_bytes(canonical_json_bytes(commit))
    destination = path.with_name(record["acceptance_id"])
    path.rename(destination)
    return destination, record["acceptance_id"]


def test_publish_and_resolve_full_chain(tmp_path):
    fixture, bundle, result, publication = _case(tmp_path)
    resolved = resolve_accepted_checkpoint(
        publication.acceptance_id, publication.path.parent, bundle.path.parent, fixture.locator_roots
    )
    assert resolved.checkpoint_id == result["selected_checkpoint"]["checkpoint_id"]
    assert resolved.run_bundle_id == bundle.bundle_id
    assert resolved.completed_epoch == 10
    assert resolved.scientific_configuration["content"]["configuration"] == "synthetic"
    assert resolved.provenance["source_inventory_entries"] == 2


def test_historical_style_finalization_failure_retries_without_training_or_recovery(tmp_path):
    fixture, bundle, result, publication = _case(tmp_path, terminal="finalization_failed")
    assert result["status"] == "SUCCEEDED"
    resolved = resolve_accepted_checkpoint(
        publication.acceptance_id, publication.path.parent, bundle.path.parent, fixture.locator_roots
    )
    assert resolved.checkpoint_id == result["selected_checkpoint"]["checkpoint_id"]
    assert resolved.completed_epoch == 10


def test_sequential_duplicate_publication_is_idempotent(tmp_path):
    fixture, bundle, result, first = _case(tmp_path)
    authority = fixture.inputs.authority
    second = publish_acceptance(
        result, bundle.path, fixture.locator_roots, first.path.parent,
        authority_id=authority["identity"], authority_hash=authority["content_sha256"],
    )
    assert first.created is True
    assert second.created is False
    assert first.acceptance_id == second.acceptance_id
    assert len([path for path in first.path.parent.iterdir() if path.name.startswith("p9accv2_")]) == 1


def test_concurrent_duplicate_publication_creates_once(tmp_path):
    fixture = make_bundle_fixture(tmp_path / "fixture")
    candidate = build_run_bundle(fixture.ledger_root, fixture.inputs, fixture.locator_roots)
    bundle = publish_run_bundle(candidate, tmp_path / "bundles", fixture.locator_roots)
    result = finalize_run_bundle(bundle.path, fixture.locator_roots)
    authority = fixture.inputs.authority
    def publish(_):
        return publish_acceptance(
            result, bundle.path, fixture.locator_roots, tmp_path / "acceptances",
            authority_id=authority["identity"], authority_hash=authority["content_sha256"],
        )
    with ThreadPoolExecutor(max_workers=2) as executor:
        publications = list(executor.map(publish, range(2)))
    assert sorted(item.created for item in publications) == [False, True]
    assert len({item.acceptance_id for item in publications}) == 1


def test_relocated_physical_root_keeps_acceptance_identity(tmp_path):
    fixture, bundle, result, first = _case(tmp_path)
    relocated = tmp_path / "relocated"
    shutil.copytree(fixture.external_root, relocated)
    authority = fixture.inputs.authority
    second = publish_acceptance(
        result, bundle.path, {next(iter(fixture.locator_roots)): relocated}, tmp_path / "second-acceptances",
        authority_id=authority["identity"], authority_hash=authority["content_sha256"],
    )
    assert first.acceptance_id == second.acceptance_id


def test_inconsistent_existing_acceptance_fails_closed(tmp_path):
    fixture = make_bundle_fixture(tmp_path / "fixture")
    candidate = build_run_bundle(fixture.ledger_root, fixture.inputs, fixture.locator_roots)
    bundle = publish_run_bundle(candidate, tmp_path / "bundles", fixture.locator_roots)
    result = finalize_run_bundle(bundle.path, fixture.locator_roots)
    authority = fixture.inputs.authority
    from p9_v2_acceptance import _make_acceptance
    record = _make_acceptance(result, _read(bundle.path / "commit/run_bundle_manifest.json"), authority["identity"], authority["content_sha256"])
    collision = tmp_path / "acceptances" / record["acceptance_id"]
    collision.mkdir(parents=True)
    (collision / "corrupt").write_bytes(b"preserve")
    with pytest.raises(AcceptanceError, match="INCONSISTENT_EXISTING_ACCEPTANCE"):
        publish_acceptance(
            result, bundle.path, fixture.locator_roots, collision.parent,
            authority_id=authority["identity"], authority_hash=authority["content_sha256"],
        )
    assert (collision / "corrupt").read_bytes() == b"preserve"


def test_external_payload_mutation_is_detected_and_restore_recovers(tmp_path):
    fixture, bundle, _, publication = _case(tmp_path)
    payload_path = fixture.external_paths[0]
    original = payload_path.read_bytes()
    payload_path.write_bytes(original + b"changed")
    invalid = validate_acceptance(publication.acceptance_id, publication.path.parent, bundle.path.parent, fixture.locator_roots)
    assert not invalid.valid and invalid.error_code == "BUNDLE_INVALID"
    payload_path.write_bytes(original)
    assert validate_acceptance(publication.acceptance_id, publication.path.parent, bundle.path.parent, fixture.locator_roots).valid


def test_external_manifest_mutation_is_detected(tmp_path):
    fixture, bundle, _, publication = _case(tmp_path)
    manifest_path = fixture.external_paths[1]
    manifest_path.write_bytes(manifest_path.read_bytes() + b" ")
    with pytest.raises(AcceptanceError, match="BUNDLE_INVALID"):
        resolve_accepted_checkpoint(publication.acceptance_id, publication.path.parent, bundle.path.parent, fixture.locator_roots)


def test_target_metadata_absent_or_corrupt_is_irrelevant(tmp_path):
    fixture, bundle, _, publication = _case(tmp_path)
    target_meta = tmp_path / "_targets" / "meta"
    target_meta.mkdir(parents=True)
    (target_meta / "meta").write_bytes(b"corrupt target metadata")
    first = resolve_accepted_checkpoint(publication.acceptance_id, publication.path.parent, bundle.path.parent, fixture.locator_roots)
    shutil.rmtree(target_meta.parent)
    second = resolve_accepted_checkpoint(publication.acceptance_id, publication.path.parent, bundle.path.parent, fixture.locator_roots)
    assert first == second


@pytest.mark.parametrize("identity", ["/tmp/checkpoint.pt", "latest", "p9ck_" + "a" * 24, "p9recovery_legacy"])
def test_manual_latest_and_legacy_fallbacks_are_rejected(tmp_path, identity):
    with pytest.raises(AcceptanceError, match="INVALID_ACCEPTANCE_ID"):
        resolve_accepted_checkpoint(identity, tmp_path, tmp_path, {})


def test_missing_and_corrupt_commit_manifest_are_rejected(tmp_path):
    fixture, bundle, _, publication = _case(tmp_path)
    commit = publication.path / ACCEPTANCE_COMMIT_PATH
    commit.unlink()
    assert validate_acceptance(publication.acceptance_id, publication.path.parent, bundle.path.parent, fixture.locator_roots).error_code == "ACCEPTANCE_UNCOMMITTED"
    commit.parent.mkdir(exist_ok=True)
    commit.write_bytes(b'{"torn":')
    assert validate_acceptance(publication.acceptance_id, publication.path.parent, bundle.path.parent, fixture.locator_roots).error_code == "MALFORMED_CANONICAL_JSON"


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("run_bundle_hash", "f" * 64, "BUNDLE_MISMATCH"),
        ("authority_hash", "f" * 64, "AUTHORITY_MISMATCH"),
        ("checkpoint_id", "p9ck_" + "f" * 24, "SELECTED_CHECKPOINT_MISMATCH"),
        ("finalization_result_hash", "f" * 64, "FINALIZATION_MISMATCH"),
    ],
)
def test_resealed_chain_mismatches_are_rejected(tmp_path, field, value, expected):
    fixture, bundle, _, publication = _case(tmp_path)
    changed_path, changed_id = _reseal_record(publication.path, lambda record: record.__setitem__(field, value))
    result = validate_acceptance(changed_id, changed_path.parent, bundle.path.parent, fixture.locator_roots)
    assert not result.valid and result.error_code == expected


def test_wrong_acceptance_id_and_malformed_record_are_rejected(tmp_path):
    fixture, bundle, _, publication = _case(tmp_path)
    record_path = publication.path / ACCEPTANCE_PATH
    record = _read(record_path)
    record["acceptance_id"] = "p9accv2_" + "f" * 24
    os.chmod(record_path, 0o644)
    record_path.write_bytes(canonical_json_bytes(record))
    result = validate_acceptance(publication.acceptance_id, publication.path.parent, bundle.path.parent, fixture.locator_roots)
    assert not result.valid
    record_path.write_bytes(b'{"malformed":')
    result = validate_acceptance(publication.acceptance_id, publication.path.parent, bundle.path.parent, fixture.locator_roots)
    assert not result.valid


def test_unsuccessful_finalization_result_is_rejected_by_resolver(tmp_path):
    fixture, bundle, _, publication = _case(tmp_path)
    failed = finalize_run_bundle(bundle.path, fixture.locator_roots, selection_contract_hash="f" * 64)
    assert failed["status"] == "FAILED"
    finalization_path = publication.path / FINALIZATION_PATH
    commit_path = publication.path / ACCEPTANCE_COMMIT_PATH
    os.chmod(finalization_path, 0o644)
    os.chmod(commit_path, 0o644)
    finalization_raw = canonical_json_bytes(failed)
    finalization_path.write_bytes(finalization_raw)
    commit = _read(commit_path)
    commit["finalization_result_sha256"] = sha256_bytes(finalization_raw)
    commit["finalization_result_size_bytes"] = len(finalization_raw)
    commit_path.write_bytes(canonical_json_bytes(commit))
    with pytest.raises(AcceptanceError, match="FINALIZATION_UNSUCCESSFUL"):
        resolve_accepted_checkpoint(publication.acceptance_id, publication.path.parent, bundle.path.parent, fixture.locator_roots)


def test_unresolved_namespace_is_rejected(tmp_path):
    fixture, bundle, _, publication = _case(tmp_path)
    result = validate_acceptance(publication.acceptance_id, publication.path.parent, bundle.path.parent, {})
    assert not result.valid and result.error_code == "BUNDLE_INVALID"


@pytest.mark.parametrize("terminal", ["interrupted", "training_failed"])
def test_incomplete_bundle_cannot_be_accepted(tmp_path, terminal):
    fixture = make_bundle_fixture(tmp_path / "fixture", terminal=terminal)
    candidate = build_run_bundle(fixture.ledger_root, fixture.inputs, fixture.locator_roots)
    bundle = publish_run_bundle(candidate, tmp_path / "bundles", fixture.locator_roots)
    result = finalize_run_bundle(bundle.path, fixture.locator_roots)
    authority = fixture.inputs.authority
    with pytest.raises(AcceptanceError, match="SCIENTIFICALLY_INCOMPLETE|FINALIZATION_UNSUCCESSFUL"):
        publish_acceptance(
            result, bundle.path, fixture.locator_roots, tmp_path / "acceptances",
            authority_id=authority["identity"], authority_hash=authority["content_sha256"],
        )


def test_wrong_authority_cannot_publish(tmp_path):
    fixture = make_bundle_fixture(tmp_path / "fixture")
    candidate = build_run_bundle(fixture.ledger_root, fixture.inputs, fixture.locator_roots)
    bundle = publish_run_bundle(candidate, tmp_path / "bundles", fixture.locator_roots)
    result = finalize_run_bundle(bundle.path, fixture.locator_roots)
    with pytest.raises(AcceptanceError, match="AUTHORITY_MISMATCH"):
        publish_acceptance(
            result, bundle.path, fixture.locator_roots, tmp_path / "acceptances",
            authority_id="wrong", authority_hash="f" * 64,
        )


def test_partial_staging_is_not_an_acceptance(tmp_path):
    fixture, bundle, _, publication = _case(tmp_path)
    debris = publication.path.parent / ".staging" / "p9accv2_debris"
    debris.mkdir()
    (debris / ACCEPTANCE_PATH).write_bytes(b'{"partial":')
    assert validate_acceptance(publication.acceptance_id, publication.path.parent, bundle.path.parent, fixture.locator_roots).valid


def test_unexpected_committed_acceptance_member_is_rejected(tmp_path):
    fixture, bundle, _, publication = _case(tmp_path)
    (publication.path / "unexpected.json").write_bytes(b"{}\n")
    result = validate_acceptance(publication.acceptance_id, publication.path.parent, bundle.path.parent, fixture.locator_roots)
    assert not result.valid and result.error_code == "UNEXPECTED_ACCEPTANCE_MEMBER"


def test_acceptance_schema_accepts_record_and_commit_rejects_extra(tmp_path):
    _, _, _, publication = _case(tmp_path)
    record = _read(publication.path / ACCEPTANCE_PATH)
    commit = _read(publication.path / ACCEPTANCE_COMMIT_PATH)
    validate_instance("acceptance", record)
    validate_instance("acceptance", commit)
    record["evaluation_metrics"] = {"held_out": 1.0}
    with pytest.raises(P9V2SchemaError):
        validate_instance("acceptance", record)


def test_publication_does_not_mutate_bundle_or_result(tmp_path):
    fixture = make_bundle_fixture(tmp_path / "fixture")
    candidate = build_run_bundle(fixture.ledger_root, fixture.inputs, fixture.locator_roots)
    bundle = publish_run_bundle(candidate, tmp_path / "bundles", fixture.locator_roots)
    result = finalize_run_bundle(bundle.path, fixture.locator_roots)
    result_before = copy.deepcopy(result)
    bundle_before = {path.relative_to(bundle.path): path.read_bytes() for path in bundle.path.rglob("*") if path.is_file()}
    authority = fixture.inputs.authority
    publish_acceptance(
        result, bundle.path, fixture.locator_roots, tmp_path / "acceptances",
        authority_id=authority["identity"], authority_hash=authority["content_sha256"],
    )
    assert result == result_before
    assert bundle_before == {path.relative_to(bundle.path): path.read_bytes() for path in bundle.path.rglob("*") if path.is_file()}
