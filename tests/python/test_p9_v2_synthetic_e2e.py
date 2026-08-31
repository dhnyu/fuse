from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from p9_v2_acceptance import ACCEPTANCE_COMMIT_PATH, AcceptanceError, publish_acceptance  # noqa: E402
from p9_v2_bundle import validate_run_bundle  # noqa: E402
from p9_v2_downstream import CONSUMERS, DownstreamResolutionError, resolve_consumer_checkpoint  # noqa: E402
from p9_v2_ef_test_support import make_synthetic_chain  # noqa: E402


def test_normal_success_runs_actual_v2_chain_to_every_consumer(tmp_path):
    chain = make_synthetic_chain(tmp_path)
    assert chain.acceptance is not None and chain.resolver is not None
    resolved = [
        resolve_consumer_checkpoint(name, chain.acceptance.acceptance_id, chain.resolver)
        for name in CONSUMERS
    ]
    assert chain.finalization["status"] == "SUCCEEDED"
    assert all(item == resolved[0] for item in resolved)


def test_interruption_with_exact_checkpoint_is_resumable_but_not_finalizable(tmp_path):
    chain = make_synthetic_chain(tmp_path, terminal="interrupted", publish=False)
    validation = validate_run_bundle(chain.bundle.path, chain.fixture.locator_roots)
    assert validation.scientific_state == "IN_PROGRESS"
    assert validation.operational_state == "INTERRUPTED_RESUMABLE"
    assert validation.resumability_state == "EXACT_RESUME_ALLOWED"
    assert chain.finalization["status"] == "FAILED"
    assert chain.finalization["failure_code"] == "SCIENTIFICALLY_INCOMPLETE"


def test_training_failure_is_incomplete_and_cannot_finalize(tmp_path):
    chain = make_synthetic_chain(tmp_path, terminal="training_failed", publish=False)
    validation = validate_run_bundle(chain.bundle.path, chain.fixture.locator_roots)
    assert validation.scientific_state == "INCOMPLETE"
    assert validation.operational_state == "TRAINING_FAILED"
    assert chain.finalization["status"] == "FAILED"
    assert chain.finalization["failure_code"] == "SCIENTIFICALLY_INCOMPLETE"


def test_complete_finalization_failure_pure_retry_requires_no_retraining(tmp_path):
    chain = make_synthetic_chain(tmp_path, terminal="finalization_failed")
    assert chain.acceptance is not None and chain.resolver is not None
    validation = validate_run_bundle(chain.bundle.path, chain.fixture.locator_roots)
    assert validation.scientific_state == "COMPLETE"
    assert validation.operational_state == "FINALIZATION_FAILED"
    assert chain.finalization["status"] == "SUCCEEDED"
    assert chain.resolver.resolve_accepted_checkpoint(chain.acceptance.acceptance_id).checkpoint_id


def test_acceptance_publication_failure_retries_same_result_idempotently(tmp_path):
    chain = make_synthetic_chain(tmp_path, publish=False)
    authority = chain.fixture.inputs.authority
    acceptance_root = tmp_path / "acceptances"

    def crash(point):
        if point == "after_verification_before_commit_manifest_rename":
            raise RuntimeError("synthetic publication crash")

    with pytest.raises(RuntimeError, match="synthetic publication crash"):
        publish_acceptance(
            chain.finalization, chain.bundle.path, chain.fixture.locator_roots,
            acceptance_root, authority_id=authority["identity"],
            authority_hash=authority["content_sha256"], fault_hook=crash,
        )
    assert not list(acceptance_root.glob("p9accv2_*"))
    first = publish_acceptance(
        chain.finalization, chain.bundle.path, chain.fixture.locator_roots,
        acceptance_root, authority_id=authority["identity"],
        authority_hash=authority["content_sha256"],
    )
    second = publish_acceptance(
        chain.finalization, chain.bundle.path, chain.fixture.locator_roots,
        acceptance_root, authority_id=authority["identity"],
        authority_hash=authority["content_sha256"],
    )
    assert first.created is True and second.created is False
    assert first.acceptance_id == second.acceptance_id


def test_committed_acceptance_survives_later_bookkeeping_failure(tmp_path):
    chain = make_synthetic_chain(tmp_path)
    assert chain.acceptance is not None and chain.resolver is not None
    try:
        raise RuntimeError("synthetic target bookkeeping failure")
    except RuntimeError:
        pass
    resolved = chain.resolver.resolve_accepted_checkpoint(chain.acceptance.acceptance_id)
    assert resolved.acceptance_id == chain.acceptance.acceptance_id


def test_corrupted_bundle_is_rejected_by_full_resolution(tmp_path):
    chain = make_synthetic_chain(tmp_path)
    assert chain.acceptance is not None and chain.resolver is not None
    manifest = chain.bundle.path / "commit/run_bundle_manifest.json"
    os.chmod(manifest, 0o644)
    manifest.write_bytes(manifest.read_bytes() + b" ")
    with pytest.raises(DownstreamResolutionError, match="BUNDLE_INVALID"):
        chain.resolver.resolve_accepted_checkpoint(chain.acceptance.acceptance_id)


def test_corrupted_acceptance_is_rejected_by_full_resolution(tmp_path):
    chain = make_synthetic_chain(tmp_path)
    assert chain.acceptance is not None and chain.resolver is not None
    commit = chain.acceptance.path / ACCEPTANCE_COMMIT_PATH
    os.chmod(commit, 0o644)
    commit.write_bytes(b'{"torn":')
    with pytest.raises(DownstreamResolutionError, match="MALFORMED_CANONICAL_JSON"):
        chain.resolver.resolve_accepted_checkpoint(chain.acceptance.acceptance_id)


def test_mutated_external_checkpoint_is_rejected(tmp_path):
    chain = make_synthetic_chain(tmp_path)
    assert chain.acceptance is not None and chain.resolver is not None
    payload = chain.fixture.external_paths[0]
    payload.write_bytes(payload.read_bytes() + b"changed")
    with pytest.raises(DownstreamResolutionError, match="BUNDLE_INVALID"):
        chain.resolver.resolve_accepted_checkpoint(chain.acceptance.acceptance_id)


@pytest.mark.parametrize("identity", ["latest", "/tmp/checkpoint.pt", "p9ck_" + "a" * 24, "p9recovery_legacy"])
def test_no_manual_latest_or_v1_fallback_in_end_to_end_chain(tmp_path, identity):
    chain = make_synthetic_chain(tmp_path)
    assert chain.resolver is not None
    with pytest.raises(DownstreamResolutionError, match="INVALID_ACCEPTANCE_ID"):
        chain.resolver.resolve_accepted_checkpoint(identity)
