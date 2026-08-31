from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from p8_experiment_plan import build_comparison_templates, load_config, materialize_comparison as materialize_p8  # noqa: E402
from p9_infrastructure import materialize_comparison as materialize_p9  # noqa: E402
from p9_v2_downstream import (  # noqa: E402
    CONSUMERS,
    AcceptedCheckpointResolver,
    DownstreamResolutionError,
    make_acceptance_eligibility,
    resolve_consumer_checkpoint,
    resolve_held_out_evaluation_checkpoint,
    resolve_p10_checkpoint,
    resolve_p11_checkpoint,
    resolve_p9_b_checkpoint,
    resolve_selected_fm_checkpoint,
    validate_acceptance_eligibility,
)
from p9_v2_ef_test_support import make_synthetic_chain  # noqa: E402


ADAPTERS = {
    "p9_b": resolve_p9_b_checkpoint,
    "selected_fm": resolve_selected_fm_checkpoint,
    "held_out_evaluation": resolve_held_out_evaluation_checkpoint,
    "p10": resolve_p10_checkpoint,
    "p11": resolve_p11_checkpoint,
}


def test_all_five_consumers_receive_identical_canonical_resolution(tmp_path):
    chain = make_synthetic_chain(tmp_path)
    assert chain.acceptance is not None and chain.resolver is not None
    values = [ADAPTERS[name](chain.acceptance.acceptance_id, chain.resolver) for name in CONSUMERS]
    assert len(ADAPTERS) == len(CONSUMERS) == 5
    assert all(value == values[0] for value in values)
    resolved = values[0]
    assert resolved.checkpoint_id == chain.finalization["selected_checkpoint"]["checkpoint_id"]
    assert resolved.payload_sha256 == chain.finalization["selected_checkpoint"]["payload_sha256"]
    assert resolved.manifest_sha256 == chain.finalization["selected_checkpoint"]["manifest_sha256"]
    assert resolved.stopping_summary == chain.finalization["stopping_summary"]
    assert resolved.scientific_configuration["content"]["configuration"] == "synthetic"
    assert resolved.provenance["source_inventory_entries"] == 2


@pytest.mark.parametrize("consumer", CONSUMERS)
@pytest.mark.parametrize(
    "invalid_identity",
    [
        "/tmp/checkpoint.pt",
        "latest",
        "manual-checkpoint-override",
        "p9ck_" + "a" * 24,
        "p9recovery_" + "a" * 24,
        "/tmp/p9rb_" + "a" * 24,
        "/tmp/p9fin_" + "a" * 24,
        "p9accv2_noncanonical",
    ],
)
def test_complete_five_consumer_fallback_rejection_matrix(tmp_path, consumer, invalid_identity):
    chain = make_synthetic_chain(tmp_path)
    assert chain.resolver is not None
    with pytest.raises(DownstreamResolutionError, match="INVALID_ACCEPTANCE_ID"):
        ADAPTERS[consumer](invalid_identity, chain.resolver)


@pytest.mark.parametrize("consumer", CONSUMERS)
def test_unresolved_uncommitted_superseded_and_revoked_rejected(tmp_path, consumer):
    chain = make_synthetic_chain(tmp_path)
    assert chain.acceptance is not None and chain.resolver is not None
    authority = chain.fixture.inputs.authority
    fake = "p9accv2_" + "f" * 24
    unresolved = AcceptedCheckpointResolver(
        chain.resolver.acceptance_root,
        chain.resolver.bundle_root,
        chain.resolver.locator_roots,
        make_acceptance_eligibility([{
            "acceptance_id": fake,
            "eligibility": "ELIGIBLE",
            "authority_id": authority["identity"],
            "authority_hash": authority["content_sha256"],
        }], namespace="synthetic-v2-ef"),
    )
    with pytest.raises(DownstreamResolutionError, match="ACCEPTANCE_UNCOMMITTED"):
        ADAPTERS[consumer](fake, unresolved)
    for status in ("SUPERSEDED", "REVOKED"):
        ineligible = AcceptedCheckpointResolver(
            chain.resolver.acceptance_root,
            chain.resolver.bundle_root,
            chain.resolver.locator_roots,
            make_acceptance_eligibility([{
                "acceptance_id": chain.acceptance.acceptance_id,
                "eligibility": status,
                "authority_id": authority["identity"],
                "authority_hash": authority["content_sha256"],
            }], namespace="synthetic-v2-ef"),
        )
        with pytest.raises(DownstreamResolutionError, match="ACCEPTANCE_INELIGIBLE"):
            ADAPTERS[consumer](chain.acceptance.acceptance_id, ineligible)


@pytest.mark.parametrize("consumer", CONSUMERS)
def test_external_hash_mismatch_has_no_consumer_fallback(tmp_path, consumer):
    chain = make_synthetic_chain(tmp_path)
    assert chain.acceptance is not None and chain.resolver is not None
    payload = chain.fixture.external_paths[0]
    payload.write_bytes(payload.read_bytes() + b"mutated")
    with pytest.raises(DownstreamResolutionError, match="BUNDLE_INVALID"):
        ADAPTERS[consumer](chain.acceptance.acceptance_id, chain.resolver)


def test_eligibility_snapshot_is_canonical_ordered_and_fail_closed(tmp_path):
    chain = make_synthetic_chain(tmp_path)
    assert chain.resolver is not None
    validate_acceptance_eligibility(chain.resolver.eligibility)
    corrupt = copy.deepcopy(chain.resolver.eligibility)
    corrupt["content_sha256"] = "f" * 64
    with pytest.raises(DownstreamResolutionError, match="INVALID_ACCEPTANCE_ELIGIBILITY"):
        validate_acceptance_eligibility(corrupt)


def test_p9_b_plan_interfaces_require_and_use_acceptance_resolver(tmp_path):
    chain = make_synthetic_chain(tmp_path)
    assert chain.acceptance is not None and chain.resolver is not None
    template = {"template_id": "cmp_a1_geometric_core", "template_hash": "a" * 64}
    p9 = materialize_p9(template, chain.acceptance.acceptance_id, chain.resolver)
    assert p9["selected_configuration_identity"] == chain.acceptance.acceptance_id
    assert p9["checkpoint_id"] == chain.finalization["selected_checkpoint"]["checkpoint_id"]
    templates = build_comparison_templates(load_config(ROOT / "config/p8_formal_experiment_plan.yml"))
    p8 = materialize_p8(templates[0], chain.acceptance.acceptance_id, chain.resolver)
    assert p8["selected_fm_dependency"] == chain.acceptance.acceptance_id
    assert p8["selected_checkpoint_id"] == p9["checkpoint_id"]
    with pytest.raises((ValueError, DownstreamResolutionError)):
        materialize_p9(template, "/tmp/checkpoint.pt", chain.resolver)
    with pytest.raises((ValueError, DownstreamResolutionError)):
        materialize_p8(templates[0], "latest", chain.resolver)


def test_unknown_consumer_and_noncanonical_resolver_are_rejected(tmp_path):
    chain = make_synthetic_chain(tmp_path)
    assert chain.acceptance is not None and chain.resolver is not None
    with pytest.raises(DownstreamResolutionError, match="UNKNOWN_CONSUMER"):
        resolve_consumer_checkpoint("other", chain.acceptance.acceptance_id, chain.resolver)
    with pytest.raises(DownstreamResolutionError, match="INVALID_RESOLVER"):
        resolve_consumer_checkpoint("p10", chain.acceptance.acceptance_id, object())


def test_downstream_resolver_import_boundary_has_no_scientific_execution_stack():
    source = (ROOT / "python/p9_v2_downstream.py").read_text(encoding="utf-8")
    prohibited = ("import torch", "cuda", "DataLoader", "optimizer", "train_update", "held_out_evaluation(")
    assert all(token not in source for token in prohibited)
