from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from p9_v2_acceptance import AcceptanceError, publish_acceptance, validate_acceptance  # noqa: E402
from p9_v2_bundle import build_run_bundle, publish_run_bundle  # noqa: E402
from p9_v2_bundle_test_support import make_bundle_fixture  # noqa: E402
from p9_v2_finalization import finalize_run_bundle  # noqa: E402


PRECOMMIT_POINTS = (
    "before_lock_acquisition",
    "after_lock_acquisition_before_staging",
    "after_staging_creation_before_write",
    "during_acceptance_metadata_write",
    "after_file_fsync_before_verification",
    "after_verification_before_commit_manifest_rename",
)
POSTCOMMIT_POINTS = (
    "after_commit_manifest_rename_before_directory_fsync",
    "after_directory_fsync_before_lock_release",
)


class InjectedCrash(RuntimeError):
    pass


def _inputs(tmp_path: Path):
    fixture = make_bundle_fixture(tmp_path / "fixture")
    candidate = build_run_bundle(fixture.ledger_root, fixture.inputs, fixture.locator_roots)
    bundle = publish_run_bundle(candidate, tmp_path / "bundles", fixture.locator_roots)
    result = finalize_run_bundle(bundle.path, fixture.locator_roots)
    return fixture, bundle, result


def _hook(point: str):
    def inject(observed: str) -> None:
        if observed == point:
            raise InjectedCrash(point)
    return inject


@pytest.mark.parametrize("point", PRECOMMIT_POINTS)
def test_precommit_crash_leaves_no_canonical_acceptance_and_retry_commits(tmp_path, point):
    fixture, bundle, result = _inputs(tmp_path)
    authority = fixture.inputs.authority
    root = tmp_path / "acceptances"
    with pytest.raises(InjectedCrash, match=point):
        publish_acceptance(
            result, bundle.path, fixture.locator_roots, root,
            authority_id=authority["identity"], authority_hash=authority["content_sha256"],
            fault_hook=_hook(point),
        )
    assert not any(path.name.startswith("p9accv2_") for path in root.iterdir())
    retry = publish_acceptance(
        result, bundle.path, fixture.locator_roots, root,
        authority_id=authority["identity"], authority_hash=authority["content_sha256"],
    )
    assert retry.created
    assert validate_acceptance(retry.acceptance_id, root, bundle.path.parent, fixture.locator_roots).valid


@pytest.mark.parametrize("point", POSTCOMMIT_POINTS)
def test_postcommit_crash_leaves_exactly_one_valid_acceptance_and_retry_validates(tmp_path, point):
    fixture, bundle, result = _inputs(tmp_path)
    authority = fixture.inputs.authority
    root = tmp_path / "acceptances"
    with pytest.raises(InjectedCrash, match=point):
        publish_acceptance(
            result, bundle.path, fixture.locator_roots, root,
            authority_id=authority["identity"], authority_hash=authority["content_sha256"],
            fault_hook=_hook(point),
        )
    canonical = [path for path in root.iterdir() if path.name.startswith("p9accv2_")]
    assert len(canonical) == 1
    identity = canonical[0].name
    assert validate_acceptance(identity, root, bundle.path.parent, fixture.locator_roots).valid
    retry = publish_acceptance(
        result, bundle.path, fixture.locator_roots, root,
        authority_id=authority["identity"], authority_hash=authority["content_sha256"],
    )
    assert retry.acceptance_id == identity
    assert retry.created is False
    assert len([path for path in root.iterdir() if path.name.startswith("p9accv2_")]) == 1


def test_publication_retry_uses_same_finalization_result_without_rerun(tmp_path):
    fixture, bundle, result = _inputs(tmp_path)
    authority = fixture.inputs.authority
    root = tmp_path / "acceptances"
    with pytest.raises(InjectedCrash):
        publish_acceptance(
            result, bundle.path, fixture.locator_roots, root,
            authority_id=authority["identity"], authority_hash=authority["content_sha256"],
            fault_hook=_hook("after_verification_before_commit_manifest_rename"),
        )
    result_identity = result["finalization_id"], result["finalization_result_hash"]
    publication = publish_acceptance(
        result, bundle.path, fixture.locator_roots, root,
        authority_id=authority["identity"], authority_hash=authority["content_sha256"],
    )
    assert result_identity == (result["finalization_id"], result["finalization_result_hash"])
    assert validate_acceptance(publication.acceptance_id, root, bundle.path.parent, fixture.locator_roots).valid


def test_inconsistent_committed_destination_survives_retry_attempt(tmp_path):
    fixture, bundle, result = _inputs(tmp_path)
    authority = fixture.inputs.authority
    root = tmp_path / "acceptances"
    first = publish_acceptance(
        result, bundle.path, fixture.locator_roots, root,
        authority_id=authority["identity"], authority_hash=authority["content_sha256"],
    )
    commit = first.path / "commit/acceptance_commit_manifest.json"
    commit.unlink()
    marker = first.path / "corruption-marker"
    marker.write_bytes(b"preserve")
    with pytest.raises(AcceptanceError, match="INCONSISTENT_EXISTING_ACCEPTANCE"):
        publish_acceptance(
            result, bundle.path, fixture.locator_roots, root,
            authority_id=authority["identity"], authority_hash=authority["content_sha256"],
        )
    assert marker.read_bytes() == b"preserve"
