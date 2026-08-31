from __future__ import annotations

import copy
import json
import shutil
import sys
from dataclasses import replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from p9_v2_acceptance import AcceptanceError, publish_acceptance, validate_acceptance  # noqa: E402
from p9_v2_bundle import validate_run_bundle  # noqa: E402
from p9_v2_canonical import canonical_sha256, parse_canonical_json  # noqa: E402
from p9_v2_downstream import CONSUMERS, load_acceptance_eligibility  # noqa: E402
from p9_v2_finalization import finalize_run_bundle, validate_finalization_result  # noqa: E402
from p9_v2_historical_acceptance import (  # noqa: E402
    PERMITTED_ACTIONS,
    PROHIBITED_ACTIONS,
    HistoricalAcceptanceError,
    audit_historical_prepublication,
    make_migration_publication_authority,
    promote_inspection_for_canonical_import,
    publish_historical_acceptance,
    validate_migration_publication_authority,
)
from p9_v2_legacy_import import (  # noqa: E402
    EXPECTED_SELECTED_CHECKPOINT,
    build_legacy_dry_run_bundle,
    validate_legacy_import,
)


@pytest.fixture(scope="module")
def preflight():
    return audit_historical_prepublication()


@pytest.fixture(scope="module")
def canonical_chain(tmp_path_factory):
    return publish_historical_acceptance(tmp_path_factory.mktemp("p9-v2-g-canonical"))


def _mutated_pair(inspection, index: int, **changes):
    pairs = [copy.deepcopy(pair) for pair in inspection.pairs]
    pairs[index].update(changes)
    return replace(inspection, pairs=tuple(pairs))


def test_prepublication_reaudit_is_exact(preflight):
    inspection = preflight.inspection
    validation = validate_legacy_import(inspection)
    selected = next(pair for pair in inspection.pairs if pair["checkpoint_id"] == EXPECTED_SELECTED_CHECKPOINT)
    assert validation.valid and validation.pair_count == 25 and validation.missing_blocking == 0
    assert inspection.source_inventory_digest == "282e8eb48ac5ae9efeabb5d535707e1e9273d3bfd803ec3b8c03f9b74063065c"
    assert len(inspection.source_inventory) == 58
    assert selected["completed_epoch"] == 105
    assert selected["validation"]["validation_retrieval_loss"] == pytest.approx(0.3806893528, abs=5e-11)
    assert selected["validation"]["mean_source_separation_margin"] == pytest.approx(0.2876026034, abs=5e-11)
    assert (inspection.pairs[-1]["completed_epoch"], inspection.pairs[-1]["optimizer_update"]) == (125, 9500)
    assert preflight.dry_run_bundle_id == "p9rb_65fc954ba2b95475aaf38ad7"


def test_authority_is_minimal_deterministic_and_scope_bounded(preflight):
    authority = make_migration_publication_authority(preflight.inspection)
    validate_migration_publication_authority(authority, preflight.inspection)
    assert authority == make_migration_publication_authority(preflight.inspection)
    assert authority["identity"] == f"p9authv2_{authority['content_sha256'][:24]}"
    assert authority["content"]["permitted_actions"] == list(PERMITTED_ACTIONS)
    assert authority["content"]["prohibited_actions"] == list(PROHIBITED_ACTIONS)
    assert not any(token in authority["content"] for token in ("reservation", "attempt", "operation", "recovery_authority"))


def test_dry_run_bundle_remains_acceptance_ineligible(preflight, tmp_path):
    dry = build_legacy_dry_run_bundle(preflight.inspection, tmp_path)
    authority = dry.mapping.inputs.authority
    with pytest.raises(AcceptanceError, match="LEGACY_IMPORT_INELIGIBLE"):
        publish_acceptance(
            dry.finalization_result, dry.bundle_path, dry.mapping.locator_roots,
            tmp_path / "acceptances", authority_id=authority["identity"],
            authority_hash=authority["content_sha256"],
        )


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        (lambda value: replace(value, source_inventory=tuple([{**value.source_inventory[0], "content_sha256": "f" * 64}, *value.source_inventory[1:]])), "SOURCE_INVENTORY_MISMATCH"),
        (lambda value: _mutated_pair(value, 0, checkpoint_payload_sha256="f" * 64), "PAYLOAD_HASH_MISMATCH"),
        (lambda value: _mutated_pair(value, 0, checkpoint_manifest_sha256="f" * 64), "MANIFEST_HASH_MISMATCH"),
        (lambda value: _mutated_pair(value, 0, completed_epoch=6), "EPOCH_MISMATCH"),
        (lambda value: _mutated_pair(value, 0, queue={"count": 1, "pointer": 0, "enqueue_count": 1}), "QUEUE_ARITHMETIC_MISMATCH"),
        (lambda value: _mutated_pair(value, 0, sampler={"epoch": 6, "cursor": 1}), "SAMPLER_MISMATCH"),
        (lambda value: _mutated_pair(value, 0, early_stopping_count=9), "SELECTOR_TRACE_MISMATCH"),
        (lambda value: _mutated_pair(value, 24, optimizer_update=9499), "STOPPING_BOUNDARY_MISMATCH"),
        (lambda value: _mutated_pair(value, 0, validation={**value.pairs[0]["validation"], "evaluation_queries_consumed": 1}), "EVALUATION_CONSUMPTION_NONZERO"),
    ],
)
def test_prepublication_historical_corruption_gates(preflight, mutation, expected):
    result = validate_legacy_import(mutation(preflight.inspection))
    assert not result.valid and expected in result.errors


def test_migration_authority_corruption_is_rejected(preflight):
    authority = make_migration_publication_authority(preflight.inspection)
    corrupt = copy.deepcopy(authority)
    corrupt["content"]["permitted_actions"].append("training")
    with pytest.raises(HistoricalAcceptanceError, match="MIGRATION_AUTHORITY_INVALID"):
        validate_migration_publication_authority(corrupt, preflight.inspection)
    with pytest.raises(HistoricalAcceptanceError):
        promote_inspection_for_canonical_import(preflight.inspection, corrupt)


def test_canonical_chain_is_valid_and_all_consumers_are_identical(canonical_chain):
    chain = canonical_chain
    bundle = validate_run_bundle(chain.bundle_path, {"p9-v1-history": chain.resolved.payload_locator and Path("/mnt/hdd002/dhnyu/fusedata/models/reduced/formal_training/attempts/p9attempt_a754afd14ac87287afb04029")})
    assert bundle.valid and bundle.completeness == "SCIENTIFICALLY_COMPLETE"
    assert chain.resolved.checkpoint_id == EXPECTED_SELECTED_CHECKPOINT
    assert chain.resolved.completed_epoch == 105
    assert chain.resolved.optimizer_update == 7980
    assert chain.resolved.stopping_summary["completed_epoch"] == 125
    assert chain.resolved.stopping_summary["optimizer_update"] == 9500
    assert len(chain.consumer_results) == len(CONSUMERS) == 5
    assert all(value == chain.resolved for value in chain.consumer_results)
    assert load_acceptance_eligibility(chain.eligibility_path) == chain.eligibility


def test_duplicate_canonical_publication_is_idempotent(canonical_chain):
    second = publish_historical_acceptance(canonical_chain.authority_path.parents[1])
    assert second.authority == canonical_chain.authority
    assert second.bundle_id == canonical_chain.bundle_id
    assert second.finalization_result == canonical_chain.finalization_result
    assert second.acceptance_id == canonical_chain.acceptance_id
    assert second.eligibility == canonical_chain.eligibility
    assert second.acceptance_created is False
    acceptances = list((canonical_chain.acceptance_path.parent).glob("p9accv2_*"))
    assert acceptances == [canonical_chain.acceptance_path]


def test_bundle_and_finalization_identity_corruption_fail_closed(canonical_chain, tmp_path):
    bundle_copy = tmp_path / canonical_chain.bundle_id
    shutil.copytree(canonical_chain.bundle_path, bundle_copy)
    manifest_path = bundle_copy / "commit/run_bundle_manifest.json"
    manifest = parse_canonical_json(manifest_path.read_bytes())
    manifest["bundle_content_sha256"] = "f" * 64
    manifest_path.write_text(json.dumps(manifest, separators=(",", ":"), sort_keys=True), encoding="utf-8")
    assert not validate_run_bundle(bundle_copy, {"p9-v1-history": Path("/mnt/hdd002/dhnyu/fusedata/models/reduced/formal_training/attempts/p9attempt_a754afd14ac87287afb04029")}).valid

    corrupt_finalization = copy.deepcopy(canonical_chain.finalization_result)
    corrupt_finalization["finalization_id"] = "p9fin_" + "f" * 24
    valid, _ = validate_finalization_result(
        corrupt_finalization,
        canonical_chain.bundle_path,
        {"p9-v1-history": Path("/mnt/hdd002/dhnyu/fusedata/models/reduced/formal_training/attempts/p9attempt_a754afd14ac87287afb04029")},
    )
    assert not valid


def test_acceptance_readback_and_identity_are_valid(canonical_chain):
    result = validate_acceptance(
        canonical_chain.acceptance_id,
        canonical_chain.acceptance_path.parent,
        canonical_chain.bundle_path.parent,
        {"p9-v1-history": Path("/mnt/hdd002/dhnyu/fusedata/models/reduced/formal_training/attempts/p9attempt_a754afd14ac87287afb04029")},
    )
    assert result.valid
    assert canonical_chain.acceptance_id.startswith("p9accv2_")
    assert canonical_sha256(canonical_chain.authority["content"]) == canonical_chain.authority["content_sha256"]
