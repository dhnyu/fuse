from __future__ import annotations

import random
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from p9_v2_bundle import (  # noqa: E402
    COMMIT_PATH,
    INVENTORY_PATH,
    BundleError,
    build_run_bundle,
    publish_run_bundle,
    validate_run_bundle,
)
from p9_v2_bundle_test_support import (  # noqa: E402
    read_json,
    make_bundle_fixture,
    reseal_bundle,
)
from p9_v2_canonical import canonical_json_bytes, canonical_sha256, sha256_bytes  # noqa: E402


def _published(tmp_path: Path):
    fixture = make_bundle_fixture(tmp_path / "fixture")
    candidate = build_run_bundle(fixture.ledger_root, fixture.inputs, fixture.locator_roots)
    publication = publish_run_bundle(candidate, tmp_path / "published", fixture.locator_roots)
    return fixture, candidate, publication


def _copy_case(source: Path, cases: Path, name: str) -> Path:
    destination = cases / name / source.name
    destination.parent.mkdir(parents=True)
    shutil.copytree(source, destination)
    return destination


def _rewrite_internal(root: Path, relative: str, value) -> Path:
    (root / relative).write_bytes(canonical_json_bytes(value))
    return reseal_bundle(root, relative)


def _reseal_manifest_only(root: Path, manifest: dict) -> Path:
    preimage = {key: value for key, value in manifest.items() if key not in {"bundle_id", "bundle_content_sha256"}}
    content_hash = canonical_sha256(preimage)
    manifest["bundle_content_sha256"] = content_hash
    manifest["bundle_id"] = f"p9rb_{content_hash[:24]}"
    (root / COMMIT_PATH).write_bytes(canonical_json_bytes(manifest))
    destination = root.with_name(manifest["bundle_id"])
    root.rename(destination)
    return destination


def test_sequential_publication_is_idempotent(tmp_path):
    fixture = make_bundle_fixture(tmp_path / "fixture")
    candidate = build_run_bundle(fixture.ledger_root, fixture.inputs, fixture.locator_roots)
    first = publish_run_bundle(candidate, tmp_path / "published", fixture.locator_roots)
    second = publish_run_bundle(candidate, tmp_path / "published", fixture.locator_roots)
    assert first.created is True
    assert second.created is False
    assert first.path == second.path
    assert first.validation == second.validation


def test_concurrent_identical_publication_creates_once(tmp_path):
    fixture = make_bundle_fixture(tmp_path / "fixture")
    candidate = build_run_bundle(fixture.ledger_root, fixture.inputs, fixture.locator_roots)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(
            lambda _: publish_run_bundle(candidate, tmp_path / "published", fixture.locator_roots),
            range(2),
        ))
    assert sorted(result.created for result in results) == [False, True]
    assert len({result.path for result in results}) == 1
    assert all(result.validation.valid for result in results)


def test_existing_valid_directory_is_create_or_validate(tmp_path):
    fixture, candidate, publication = _published(tmp_path)
    repeated = publish_run_bundle(candidate, publication.path.parent, fixture.locator_roots)
    assert not repeated.created
    assert repeated.validation.bundle_content_sha256 == candidate.bundle_content_sha256


def test_existing_inconsistent_identity_path_fails_closed(tmp_path):
    fixture = make_bundle_fixture(tmp_path / "fixture")
    candidate = build_run_bundle(fixture.ledger_root, fixture.inputs, fixture.locator_roots)
    collision = tmp_path / "published" / candidate.bundle_id
    collision.mkdir(parents=True)
    (collision / "corrupt").write_bytes(b"not a bundle")
    with pytest.raises(BundleError, match="PUBLICATION_COLLISION"):
        publish_run_bundle(candidate, collision.parent, fixture.locator_roots)
    assert (collision / "corrupt").read_bytes() == b"not a bundle"


def test_partial_staging_bundle_is_non_authoritative(tmp_path):
    fixture, candidate, publication = _published(tmp_path)
    partial = publication.path.parent / ".staging" / f"{candidate.bundle_id}.partial.incomplete"
    partial.mkdir()
    (partial / INVENTORY_PATH).write_bytes(b"{}")
    result = validate_run_bundle(partial, fixture.locator_roots)
    assert not result.valid
    assert "MISSING_REQUIRED_BUNDLE_FILE" in result.error_codes
    assert validate_run_bundle(publication.path, fixture.locator_roots).valid


def test_external_payload_mutation_is_detected_and_restoration_recovers(tmp_path):
    fixture, _, publication = _published(tmp_path)
    payload_path = next(path for path in fixture.external_paths if path.name == "checkpoint.pt")
    original = payload_path.read_bytes()
    payload_path.write_bytes(original + b"mutated")
    invalid = validate_run_bundle(publication.path, fixture.locator_roots)
    assert not invalid.valid
    assert invalid.error_codes[0] in {"ARTIFACT_SIZE_MISMATCH", "ARTIFACT_HASH_MISMATCH"}
    payload_path.write_bytes(original)
    assert validate_run_bundle(publication.path, fixture.locator_roots).valid


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_file", "malformed_json", "wrong_bundle_id", "wrong_content_hash",
        "duplicate_inventory", "reordered_inventory", "unexpected_member",
        "missing_ledger_manifest", "corrupt_ledger_manifest", "ledger_hash",
        "run_id", "authority", "scientific_config", "source_inventory",
        "missing_checkpoint", "checkpoint_payload_hash", "checkpoint_manifest_hash",
        "checkpoint_size", "validation_id", "completed_epoch", "resume_epoch",
        "optimizer_update", "duplicate_checkpoint", "invalid_backend", "raw_path",
        "evaluation_contamination", "targets_contamination",
    ],
)
def test_corruption_and_rejection_matrix(tmp_path, mutation):
    fixture, _, publication = _published(tmp_path / "base")
    root = _copy_case(publication.path, tmp_path / "cases", mutation)
    roots = fixture.locator_roots
    if mutation == "missing_file":
        (root / "summary/training_summary.json").unlink()
    elif mutation == "malformed_json":
        (root / "summary/training_summary.json").write_bytes(b'{"torn":')
    elif mutation in {"wrong_bundle_id", "wrong_content_hash", "ledger_hash", "run_id"}:
        manifest = read_json(root / COMMIT_PATH)
        if mutation == "wrong_bundle_id":
            manifest["bundle_id"] = "p9rb_" + "0" * 24
            (root / COMMIT_PATH).write_bytes(canonical_json_bytes(manifest))
        elif mutation == "wrong_content_hash":
            manifest["bundle_content_sha256"] = "0" * 64
            (root / COMMIT_PATH).write_bytes(canonical_json_bytes(manifest))
        elif mutation == "ledger_hash":
            manifest["bindings"]["ledger_manifest_sha256"] = "0" * 64
            root = _reseal_manifest_only(root, manifest)
        else:
            manifest["run_id"] = "p9runv2_" + "f" * 24
            root = _reseal_manifest_only(root, manifest)
    elif mutation in {"duplicate_inventory", "reordered_inventory"}:
        inventory = read_json(root / INVENTORY_PATH)
        if mutation == "duplicate_inventory":
            inventory["entries"].append(dict(inventory["entries"][-1]))
        else:
            inventory["entries"][0], inventory["entries"][1] = inventory["entries"][1], inventory["entries"][0]
        (root / INVENTORY_PATH).write_bytes(canonical_json_bytes(inventory))
        root = reseal_bundle(root)
    elif mutation == "unexpected_member":
        path = root / "unexpected.json"
        path.write_bytes(b"{}")
        inventory = read_json(root / INVENTORY_PATH)
        inventory["entries"].append({
            "path": "unexpected.json", "required": True, "media_type": "application/json",
            "size_bytes": 2, "sha256": sha256_bytes(b"{}"), "provenance_role": "unexpected",
        })
        inventory["entries"].sort(key=lambda item: item["path"])
        (root / INVENTORY_PATH).write_bytes(canonical_json_bytes(inventory))
        root = reseal_bundle(root)
    elif mutation == "missing_ledger_manifest":
        (root / "ledger/commit/ledger_manifest.json").unlink()
    elif mutation == "corrupt_ledger_manifest":
        path = root / "ledger/commit/ledger_manifest.json"
        path.write_bytes(path.read_bytes()[:-5])
    elif mutation in {"authority", "scientific_config"}:
        relative = "authority/authority_manifest.json" if mutation == "authority" else "config/scientific_configuration.json"
        document = read_json(root / relative)
        document["content"]["mutated"] = True
        document["content_sha256"] = canonical_sha256(document["content"])
        root = _rewrite_internal(root, relative, document)
        manifest = read_json(root / COMMIT_PATH)
        key = "authority_hash" if mutation == "authority" else "scientific_configuration_hash"
        manifest["bindings"][key] = document["content_sha256"]
        root = _reseal_manifest_only(root, manifest)
    elif mutation == "source_inventory":
        relative = "provenance/source_inventory.json"
        document = read_json(root / relative)
        document["entries"][0]["content_sha256"] = "f" * 64
        root = _rewrite_internal(root, relative, document)
    elif mutation == "missing_checkpoint":
        next(path for path in fixture.external_paths if path.name == "checkpoint.pt").unlink()
    elif mutation == "checkpoint_size":
        relative = "checkpoints/checkpoint_inventory.json"
        document = read_json(root / relative)
        document["checkpoints"][0]["payload_locator"]["byte_size"] += 1
        root = _rewrite_internal(root, relative, document)
    elif mutation in {
        "checkpoint_payload_hash", "checkpoint_manifest_hash", "validation_id", "completed_epoch",
        "resume_epoch", "optimizer_update", "duplicate_checkpoint", "invalid_backend", "raw_path",
    }:
        relative = "checkpoints/checkpoint_inventory.json"
        document = read_json(root / relative)
        first = document["checkpoints"][0]
        if mutation == "checkpoint_payload_hash":
            first["payload_locator"]["content_sha256"] = "f" * 64
        elif mutation == "checkpoint_manifest_hash":
            first["manifest_locator"]["content_sha256"] = "f" * 64
        elif mutation == "validation_id":
            first["validation_id"] = "p9val_" + "f" * 24
        elif mutation == "completed_epoch":
            first["completed_epoch"] += 1
        elif mutation == "resume_epoch":
            first["resume_epoch"] += 1
        elif mutation == "optimizer_update":
            first["optimizer_update"] += 1
        elif mutation == "duplicate_checkpoint":
            document["checkpoints"][1]["checkpoint_id"] = first["checkpoint_id"]
        elif mutation == "invalid_backend":
            first["payload_locator"]["backend"] = "mutable-http"
        else:
            first["payload_locator"] = "/tmp/manual-checkpoint.pt"
        root = _rewrite_internal(root, relative, document)
    elif mutation in {"evaluation_contamination", "targets_contamination"}:
        relative = "contracts/selection_contract.json"
        document = read_json(root / relative)
        key = "held_out_evaluation" if mutation == "evaluation_contamination" else "targets_metadata"
        document["content"][key] = {"forbidden": True}
        document["content_sha256"] = canonical_sha256(document["content"])
        root = _rewrite_internal(root, relative, document)
    else:
        raise AssertionError(mutation)
    result = validate_run_bundle(root, roots)
    assert not result.valid, mutation
    assert result.completeness == "EVIDENCE_INVALID"


def test_wrong_checkpoint_manifest_bytes_are_detected(tmp_path):
    fixture, _, publication = _published(tmp_path)
    manifest_path = next(path for path in fixture.external_paths if path.name == "checkpoint_manifest.json")
    raw = manifest_path.read_bytes()
    manifest_path.write_bytes(raw + b" ")
    result = validate_run_bundle(publication.path, fixture.locator_roots)
    assert not result.valid
    assert result.error_codes[0] in {"ARTIFACT_SIZE_MISMATCH", "ARTIFACT_HASH_MISMATCH"}


def test_standalone_validation_record_cannot_enter_candidate_inventory(tmp_path):
    fixture, _, publication = _published(tmp_path)
    root = _copy_case(publication.path, tmp_path / "cases", "standalone-validation")
    relative = "events/validation_checkpoint_events.json"
    document = read_json(root / relative)
    document["events"].append(dict(document["events"][-1]))
    root = _rewrite_internal(root, relative, document)
    result = validate_run_bundle(root, fixture.locator_roots)
    assert not result.valid
    assert "VALIDATION_CHECKPOINT_MISMATCH" in result.error_codes


def test_fixed_seed_random_single_field_manifest_corruption_is_rejected(tmp_path):
    fixture, _, publication = _published(tmp_path / "base")
    randomizer = random.Random(20260831)
    mutations = (
        "scientific_state", "operational_state", "resumability_state", "bundle_status",
        "validation_checkpoint_count", "source_inventory_digest", "ledger_tail",
        "authority_hash", "selection_hash", "external_hash",
    )
    for case in range(50):
        root = _copy_case(publication.path, tmp_path / "random", f"case-{case:03d}")
        manifest = read_json(root / COMMIT_PATH)
        mutation = randomizer.choice(mutations)
        if mutation == "scientific_state":
            manifest["scientific_state"] = "INCOMPLETE"
        elif mutation == "operational_state":
            manifest["operational_state"] = "BLOCKED"
        elif mutation == "resumability_state":
            manifest["resumability_state"] = "EVIDENCE_INVALID"
        elif mutation == "bundle_status":
            manifest["bundle_status"] = "SCIENTIFICALLY_INCOMPLETE"
        elif mutation == "validation_checkpoint_count":
            manifest["validation_checkpoint_count"] += 1
        elif mutation == "source_inventory_digest":
            manifest["source_inventory_digest"] = "f" * 64
        elif mutation == "ledger_tail":
            manifest["ledger"]["tail_event_hash"] = "f" * 64
        elif mutation == "authority_hash":
            manifest["bindings"]["authority_hash"] = "f" * 64
        elif mutation == "selection_hash":
            manifest["bindings"]["selection_contract_hash"] = "f" * 64
        else:
            manifest["external_objects"][0]["content_sha256"] = "f" * 64
        root = _reseal_manifest_only(root, manifest)
        result = validate_run_bundle(root, fixture.locator_roots)
        assert not result.valid, (case, mutation)
