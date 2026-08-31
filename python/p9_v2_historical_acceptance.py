"""V2-G canonical publication of the audited immutable P9 v1 trajectory."""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping

from p9_v2_acceptance import publish_acceptance, validate_acceptance
from p9_v2_bundle import build_run_bundle, publish_run_bundle, validate_run_bundle
from p9_v2_canonical import canonical_json_bytes, canonical_sha256, parse_canonical_json
from p9_v2_downstream import (
    CONSUMERS,
    AcceptedCheckpointResolver,
    load_acceptance_eligibility,
    make_acceptance_eligibility,
    publish_acceptance_eligibility,
    resolve_consumer_checkpoint,
)
from p9_v2_finalization import (
    FINALIZER_IMPLEMENTATION_VERSION,
    SELECTION_CONTRACT_VERSION,
    finalize_run_bundle,
    validate_finalization_result,
)
from p9_v2_ledger import fsync_directory, read_ledger, write_all
from p9_v2_legacy_import import (
    EXPECTED_SELECTED_CHECKPOINT,
    EXPECTED_SELECTED_MANIFEST_SHA256,
    EXPECTED_SELECTED_PAYLOAD_SHA256,
    LegacyInspection,
    LegacyMapping,
    build_legacy_dry_run_bundle,
    inspect_legacy_run,
    map_legacy_run_to_v2,
    validate_legacy_import,
)
from p9_v2_schema import SCHEMA_VERSION, validate_instance


DEFAULT_CANONICAL_ROOT = Path("/mnt/hdd002/dhnyu/fusedata/models/reduced/p9_v2/canonical")
ELIGIBILITY_NAMESPACE = "p9-v2-canonical-historical"
PERMITTED_ACTIONS = (
    "canonical_bundle_publication",
    "canonical_historical_import",
    "eligibility_snapshot_publication",
    "pure_finalization",
    "resolver_verification",
    "acceptance_publication",
)
PROHIBITED_ACTIONS = (
    "cache_modification",
    "checkpoint_modification",
    "downstream_scientific_execution",
    "evaluation",
    "recovery",
    "resume",
    "training",
    "validation",
)


class HistoricalAcceptanceError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


@dataclass(frozen=True)
class HistoricalPreflight:
    inspection: LegacyInspection
    dry_run_bundle_id: str
    dry_run_bundle_hash: str
    dry_run_finalization_id: str


@dataclass(frozen=True)
class HistoricalAcceptancePublication:
    authority: dict[str, Any]
    authority_path: Path
    imported_run_id: str
    ledger_root: Path
    bundle_id: str
    bundle_hash: str
    bundle_path: Path
    finalization_result: dict[str, Any]
    acceptance_id: str
    acceptance_path: Path
    acceptance_created: bool
    eligibility: dict[str, Any]
    eligibility_path: Path
    resolved: Any
    consumer_results: tuple[Any, ...]
    source_inventory_digest: str


def _fail(code: str, message: str) -> None:
    raise HistoricalAcceptanceError(code, message)


def make_migration_publication_authority(inspection: LegacyInspection) -> dict[str, Any]:
    """Create the sole deterministic V2-G authority from audited evidence."""

    docs = inspection.documents
    base = dict(docs["authority"]["content"])
    content = {
        **base,
        "authority_kind": "HISTORICAL_MIGRATION_PUBLICATION",
        "status": "AUTHORIZED",
        "source_v1_run_id": inspection.sources.run_id,
        "source_inventory_digest": inspection.source_inventory_digest,
        "permitted_actions": list(PERMITTED_ACTIONS),
        "prohibited_actions": list(PROHIBITED_ACTIONS),
    }
    digest = canonical_sha256(content)
    authority = {
        "schema_version": SCHEMA_VERSION,
        "identity": f"p9authv2_{digest[:24]}",
        "content_sha256": digest,
        "content": content,
    }
    validate_instance("migration_authority", authority)
    return authority


def validate_migration_publication_authority(
    authority: Mapping[str, Any], inspection: LegacyInspection
) -> None:
    try:
        validate_instance("migration_authority", authority)
    except Exception as error:
        _fail("MIGRATION_AUTHORITY_INVALID", str(error))
    content = authority["content"]
    digest = canonical_sha256(content)
    if authority["content_sha256"] != digest or authority["identity"] != f"p9authv2_{digest[:24]}":
        _fail("MIGRATION_AUTHORITY_INVALID", "identity/hash differs")
    if (
        content["run_id"] != inspection.imported_run_id
        or content["source_v1_run_id"] != inspection.sources.run_id
        or content["source_inventory_digest"] != inspection.source_inventory_digest
        or content["selection_contract_id"] != inspection.documents["selection_contract"]["identity"]
        or content["selection_contract_hash"] != inspection.documents["selection_contract"]["content_sha256"]
    ):
        _fail("MIGRATION_AUTHORITY_MISMATCH", "authority does not bind audited evidence")


def promote_inspection_for_canonical_import(
    inspection: LegacyInspection, authority: Mapping[str, Any]
) -> LegacyInspection:
    """Bind unchanged V2-D evidence to the explicit V2-G publication authority."""

    validate_migration_publication_authority(authority, inspection)
    annotation = {
        **inspection.legacy_annotation,
        "status": "CANONICAL_MIGRATION",
        "canonical_publication_eligible": True,
        "acceptance_eligible": True,
        "migration_authority_id": authority["identity"],
        "migration_authority_hash": authority["content_sha256"],
        "dry_run_annotation_sha256": canonical_sha256(inspection.legacy_annotation),
    }
    validate_instance("legacy_import", annotation)
    documents = {**inspection.documents, "authority": dict(authority)}
    promoted = replace(inspection, legacy_annotation=annotation, documents=documents)
    validation = validate_legacy_import(promoted)
    if not validation.valid:
        _fail("CANONICAL_IMPORT_INVALID", "; ".join(validation.errors))
    return promoted


def audit_historical_prepublication() -> HistoricalPreflight:
    """Reinspect real sources and run V2-A/B/C only in a temporary dry-run root."""

    inspection = inspect_legacy_run()
    validation = validate_legacy_import(inspection)
    if not validation.valid or validation.pair_count != 25 or validation.missing_blocking != 0:
        _fail("HISTORICAL_PREFLIGHT_FAILED", "; ".join(validation.errors))
    if SELECTION_CONTRACT_VERSION != "p9-selection-v2.1.0":
        _fail("SELECTION_CONTRACT_MISMATCH", SELECTION_CONTRACT_VERSION)
    with tempfile.TemporaryDirectory(prefix="p9-v2-g-preflight-") as temporary:
        dry = build_legacy_dry_run_bundle(inspection, temporary)
    selected = dry.finalization_result.get("selected_checkpoint") or {}
    last = inspection.pairs[-1]
    if (
        dry.mapping.replay.scientific_state != "COMPLETE"
        or dry.mapping.replay.operational_state != "FINALIZATION_FAILED"
        or dry.mapping.replay.resumability_state != "NOT_APPLICABLE_SCIENTIFICALLY_COMPLETE"
        or selected.get("checkpoint_id") != EXPECTED_SELECTED_CHECKPOINT
        or selected.get("completed_epoch") != 105
        or selected.get("checkpoint_payload_sha256", selected.get("payload_sha256")) != EXPECTED_SELECTED_PAYLOAD_SHA256
        or selected.get("checkpoint_manifest_sha256", selected.get("manifest_sha256")) != EXPECTED_SELECTED_MANIFEST_SHA256
        or last["completed_epoch"] != 125
        or last["optimizer_update"] != 9500
        or any(pair["validation"]["evaluation_queries_consumed"] != 0 for pair in inspection.pairs)
    ):
        _fail("HISTORICAL_PREFLIGHT_FAILED", "historical replay differs from approved evidence")
    return HistoricalPreflight(
        inspection=inspection,
        dry_run_bundle_id=dry.bundle_id,
        dry_run_bundle_hash=dry.bundle_hash,
        dry_run_finalization_id=dry.finalization_result["finalization_id"],
    )


def _publish_canonical_document(
    value: Mapping[str, Any], identity: str, publication_root: Path
) -> Path:
    publication_root.mkdir(parents=True, exist_ok=True)
    staging = publication_root / ".staging"
    staging.mkdir(exist_ok=True)
    final = publication_root / f"{identity}.json"
    raw = canonical_json_bytes(dict(value))
    if final.exists():
        if parse_canonical_json(final.read_bytes()) != dict(value):
            _fail("PUBLICATION_COLLISION", f"existing {identity} differs")
        return final
    descriptor, stage_name = tempfile.mkstemp(prefix=f".{identity}.", dir=staging)
    stage = Path(stage_name)
    try:
        write_all(descriptor, raw)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    try:
        if parse_canonical_json(stage.read_bytes()) != dict(value):
            _fail("STAGING_VERIFICATION_FAILED", identity)
        try:
            os.link(stage, final)
            stage.unlink()
        except FileExistsError:
            if parse_canonical_json(final.read_bytes()) != dict(value):
                _fail("PUBLICATION_COLLISION", f"concurrent {identity} differs")
            stage.unlink(missing_ok=True)
        fsync_directory(publication_root)
    finally:
        stage.unlink(missing_ok=True)
    if parse_canonical_json(final.read_bytes()) != dict(value):
        _fail("PUBLICATION_VERIFICATION_FAILED", identity)
    return final


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*")) if path.is_file()
    }


def _build_and_publish_ledger(
    inspection: LegacyInspection, canonical_root: Path
) -> LegacyMapping:
    ledgers = canonical_root / "ledgers"
    ledgers.mkdir(parents=True, exist_ok=True)
    staging = ledgers / ".staging"
    staging.mkdir(exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{inspection.imported_run_id}.", dir=staging))
    try:
        mapping = map_legacy_run_to_v2(inspection, stage / "ledger")
        read_ledger(mapping.ledger_root)
        final = ledgers / inspection.imported_run_id
        if final.exists():
            read_ledger(final)
            if _tree_bytes(final) != _tree_bytes(mapping.ledger_root):
                _fail("LEDGER_PUBLICATION_COLLISION", "existing canonical ledger differs")
            shutil.rmtree(stage)
            return replace(mapping, ledger_root=final)
        os.rename(mapping.ledger_root, final)
        fsync_directory(ledgers)
        shutil.rmtree(stage)
        read_ledger(final)
        return replace(mapping, ledger_root=final)
    except Exception:
        if stage.exists():
            shutil.rmtree(stage)
        raise


def _verify_finalization(result: Mapping[str, Any], bundle_path: Path, locator_roots: Mapping[str, Path]) -> None:
    valid, reason = validate_finalization_result(result, bundle_path, locator_roots)
    selected = result.get("selected_checkpoint") or {}
    stopping = result.get("stopping_summary") or {}
    if not valid:
        _fail(reason or "FINALIZATION_INVALID", "pure finalization failed")
    if (
        result.get("status") != "SUCCEEDED"
        or result.get("finalizer_implementation_version") != FINALIZER_IMPLEMENTATION_VERSION
        or selected.get("checkpoint_id") != EXPECTED_SELECTED_CHECKPOINT
        or selected.get("completed_epoch") != 105
        or selected.get("payload_sha256") != EXPECTED_SELECTED_PAYLOAD_SHA256
        or selected.get("manifest_sha256") != EXPECTED_SELECTED_MANIFEST_SHA256
        or stopping.get("completed_epoch") != 125
        or stopping.get("optimizer_update") != 9500
    ):
        _fail("FINALIZATION_MISMATCH", "result differs from V2-D historical audit")


def publish_historical_acceptance(
    canonical_root: str | Path = DEFAULT_CANONICAL_ROOT,
) -> HistoricalAcceptancePublication:
    """Perform the one authorized, idempotent V2-G canonical publication."""

    preflight = audit_historical_prepublication()
    inspection = preflight.inspection
    root = Path(canonical_root)
    authority = make_migration_publication_authority(inspection)
    validate_migration_publication_authority(authority, inspection)

    # This authority file is the first canonical artifact written by V2-G.
    authority_path = _publish_canonical_document(
        authority, authority["identity"], root / "authorities"
    )
    promoted = promote_inspection_for_canonical_import(inspection, authority)
    mapping = _build_and_publish_ledger(promoted, root)
    candidate = build_run_bundle(mapping.ledger_root, mapping.inputs, mapping.locator_roots)
    bundle = publish_run_bundle(candidate, root / "bundles", mapping.locator_roots)
    independent = validate_run_bundle(bundle.path, mapping.locator_roots)
    if not independent.valid or independent.completeness != "SCIENTIFICALLY_COMPLETE":
        _fail("BUNDLE_INVALID", "; ".join(independent.errors))

    finalization = finalize_run_bundle(
        bundle.path,
        mapping.locator_roots,
        selection_contract_hash=promoted.documents["selection_contract"]["content_sha256"],
    )
    _verify_finalization(finalization, bundle.path, mapping.locator_roots)
    acceptance = publish_acceptance(
        finalization,
        bundle.path,
        mapping.locator_roots,
        root / "acceptances",
        authority_id=authority["identity"],
        authority_hash=authority["content_sha256"],
    )
    acceptance_validation = validate_acceptance(
        acceptance.acceptance_id,
        root / "acceptances",
        root / "bundles",
        mapping.locator_roots,
    )
    if not acceptance_validation.valid:
        _fail("ACCEPTANCE_INVALID", acceptance_validation.error_code or "readback failed")
    eligibility = make_acceptance_eligibility([{
        "acceptance_id": acceptance.acceptance_id,
        "eligibility": "ELIGIBLE",
        "authority_id": authority["identity"],
        "authority_hash": authority["content_sha256"],
    }], namespace=ELIGIBILITY_NAMESPACE)
    eligibility_path = publish_acceptance_eligibility(eligibility, root / "eligibility")
    loaded_eligibility = load_acceptance_eligibility(eligibility_path)
    resolver = AcceptedCheckpointResolver(
        root / "acceptances", root / "bundles", mapping.locator_roots, loaded_eligibility
    )
    resolved = resolver.resolve_accepted_checkpoint(acceptance.acceptance_id)
    consumer_results = tuple(
        resolve_consumer_checkpoint(consumer, acceptance.acceptance_id, resolver)
        for consumer in CONSUMERS
    )
    if any(value != resolved for value in consumer_results):
        _fail("CONSUMER_RESOLUTION_MISMATCH", "downstream interfaces differ")
    return HistoricalAcceptancePublication(
        authority=dict(authority), authority_path=authority_path,
        imported_run_id=inspection.imported_run_id, ledger_root=mapping.ledger_root,
        bundle_id=bundle.bundle_id, bundle_hash=candidate.bundle_content_sha256,
        bundle_path=bundle.path, finalization_result=dict(finalization),
        acceptance_id=acceptance.acceptance_id, acceptance_path=acceptance.path,
        acceptance_created=acceptance.created, eligibility=eligibility,
        eligibility_path=eligibility_path, resolved=resolved,
        consumer_results=consumer_results,
        source_inventory_digest=inspection.source_inventory_digest,
    )
