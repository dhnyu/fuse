"""Immutable P9 v2 run-bundle construction, publication, and validation."""

from __future__ import annotations

import errno
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

from p9_v2_canonical import (
    CanonicalJSONError,
    canonical_json_bytes,
    canonical_sha256,
    deterministic_id,
    parse_canonical_json,
    sha256_bytes,
)
from p9_v2_ledger import LedgerError, fsync_directory, read_ledger, write_all
from p9_v2_replay import ReplayResult, replay_events
from p9_v2_schema import P9V2SchemaError, SCHEMA_VERSION, validate_instance


BUNDLE_FORMAT_VERSION = "p9-v2-run-bundle-v1"
BUNDLE_ID_PATTERN = re.compile(r"^p9rb_[0-9a-f]{24}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
COMMIT_PATH = "commit/run_bundle_manifest.json"
INVENTORY_PATH = "inventory.json"

BOUND_DOCUMENT_PATHS = {
    "authority": "authority/authority_manifest.json",
    "scientific_configuration": "config/scientific_configuration.json",
    "runtime": "runtime/runtime_digest.json",
    "source_parents": "parents/source_parents.json",
    "cache_acceptance": "parents/cache_acceptance.json",
    "sampler_contract": "contracts/sampler_contract.json",
    "selection_contract": "contracts/selection_contract.json",
}

REQUIRED_FIXED_PATHS = frozenset({
    *BOUND_DOCUMENT_PATHS.values(),
    "ledger/header.json",
    "ledger/commit/ledger_manifest.json",
    "summary/training_summary.json",
    "summary/final_selector_state.json",
    "summary/stopping_boundary.json",
    "events/validation_checkpoint_events.json",
    "checkpoints/checkpoint_inventory.json",
    "diagnostics/incidents.json",
    "provenance/source_inventory.json",
})

PROHIBITED_EVIDENCE_KEYS = frozenset({
    "held_out_evaluation", "heldout_evaluation", "evaluation_identity",
    "evaluation_metrics", "evaluation_path", "evaluation_results",
    "targets_metadata", "target_store", "target_currentness", "tar_meta",
})


class BundleError(ValueError):
    """A stable run-bundle construction or validation failure."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


@dataclass(frozen=True)
class RunBundleInputs:
    authority: dict[str, Any]
    scientific_configuration: dict[str, Any]
    runtime: dict[str, Any]
    source_parents: dict[str, Any]
    cache_acceptance: dict[str, Any]
    sampler_contract: dict[str, Any]
    selection_contract: dict[str, Any]
    source_inventory: tuple[dict[str, Any], ...]
    checkpoint_locators: Mapping[str, dict[str, dict[str, Any]]]
    diagnostic_incidents: tuple[dict[str, Any], ...] = ()
    evaluation_consumption_count: int = 0
    legacy_import: dict[str, Any] | None = None


@dataclass(frozen=True)
class RunBundleCandidate:
    bundle_id: str
    bundle_content_sha256: str
    files: tuple[tuple[str, bytes], ...]

    def file_map(self) -> dict[str, bytes]:
        return dict(self.files)


@dataclass(frozen=True)
class BundleValidationResult:
    valid: bool
    validation_status: str
    completeness: str
    bundle_id: str | None
    bundle_content_sha256: str | None
    run_id: str | None
    scientific_state: str | None
    operational_state: str | None
    resumability_state: str | None
    ledger_tail_hash: str | None
    validation_checkpoint_count: int
    source_inventory_digest: str | None
    error_codes: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    validation_implementation: str = BUNDLE_FORMAT_VERSION


@dataclass(frozen=True)
class BundlePublication:
    path: Path
    bundle_id: str
    created: bool
    validation: BundleValidationResult


def _fail(code: str, message: str) -> None:
    raise BundleError(code, message)


def make_bound_document(identity: str, content: dict[str, Any]) -> dict[str, Any]:
    """Bind a logical evidence identity to canonical content bytes."""

    if not isinstance(identity, str) or not identity:
        _fail("CONTRACT_MISMATCH", "bound document identity must be a nonempty string")
    _reject_prohibited_evidence(content)
    return {
        "schema_version": SCHEMA_VERSION,
        "identity": identity,
        "content_sha256": canonical_sha256(content),
        "content": content,
    }


def _validate_bound_document(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "schema_version", "identity", "content_sha256", "content"
    }:
        _fail("CONTRACT_MISMATCH", f"{label} is not a bound evidence document")
    if value["schema_version"] != SCHEMA_VERSION:
        _fail("CONTRACT_MISMATCH", f"{label} schema version is unsupported")
    if not isinstance(value["identity"], str) or not value["identity"]:
        _fail("CONTRACT_MISMATCH", f"{label} identity is invalid")
    if not isinstance(value["content"], dict):
        _fail("CONTRACT_MISMATCH", f"{label} content must be an object")
    _reject_prohibited_evidence(value["content"])
    if value["content_sha256"] != canonical_sha256(value["content"]):
        _fail("CONTRACT_MISMATCH", f"{label} content hash mismatch")
    return value


def _safe_relative_path(value: str) -> PurePosixPath:
    if not isinstance(value, str) or "\\" in value:
        _fail("MALFORMED_LOCATOR", "locator relative_path must use POSIX separators")
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        _fail("MALFORMED_LOCATOR", "locator relative_path must be normalized and relative")
    return path


def make_filesystem_locator(
    *,
    namespace: str,
    relative_path: str,
    physical_path: str | Path,
    role: str,
    media_type: str,
    associated_manifest_sha256: str | None = None,
) -> dict[str, Any]:
    """Create a portable logical locator from verified local synthetic evidence."""

    raw = Path(physical_path).read_bytes()
    content_hash = sha256_bytes(raw)
    locator: dict[str, Any] = {
        "backend": "filesystem",
        "location": {"namespace": namespace, "relative_path": relative_path},
        "immutable_object_id": f"sha256:{content_hash}",
        "content_sha256": content_hash,
        "byte_size": len(raw),
        "role": role,
        "media_type": media_type,
    }
    if associated_manifest_sha256 is not None:
        locator["associated_manifest_sha256"] = associated_manifest_sha256
    _validate_locator_shape(locator)
    return locator


def _validate_locator_shape(locator: Any) -> dict[str, Any]:
    try:
        validate_instance("immutable_locator", locator)
    except P9V2SchemaError as error:
        _fail("MALFORMED_LOCATOR", str(error))
    _safe_relative_path(locator["location"]["relative_path"])
    if locator["immutable_object_id"] != f"sha256:{locator['content_sha256']}":
        _fail("MALFORMED_LOCATOR", "immutable object identity must equal the content hash")
    if locator["role"] == "checkpoint_payload" and "associated_manifest_sha256" not in locator:
        _fail("MALFORMED_LOCATOR", "checkpoint payload locator must bind its manifest hash")
    if locator["role"] == "checkpoint_manifest" and "associated_manifest_sha256" in locator:
        _fail("MALFORMED_LOCATOR", "manifest locator cannot associate another manifest")
    return locator


def _resolve_locator(locator: dict[str, Any], roots: Mapping[str, str | Path]) -> Path:
    namespace = locator["location"]["namespace"]
    if namespace not in roots:
        _fail("MISSING_IMMUTABLE_ARTIFACT", f"no physical root for locator namespace {namespace}")
    root = Path(roots[namespace]).resolve()
    relative = _safe_relative_path(locator["location"]["relative_path"])
    path = root.joinpath(*relative.parts).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        _fail("MALFORMED_LOCATOR", "resolved locator escapes its namespace root")
    return path


def _verify_locator(locator: Any, roots: Mapping[str, str | Path]) -> Path:
    value = _validate_locator_shape(locator)
    path = _resolve_locator(value, roots)
    if not path.is_file():
        _fail("MISSING_IMMUTABLE_ARTIFACT", f"external artifact is missing: {value['immutable_object_id']}")
    raw = path.read_bytes()
    if len(raw) != value["byte_size"]:
        _fail("ARTIFACT_SIZE_MISMATCH", f"external artifact size differs: {value['immutable_object_id']}")
    if sha256_bytes(raw) != value["content_sha256"]:
        _fail("ARTIFACT_HASH_MISMATCH", f"external artifact hash differs: {value['immutable_object_id']}")
    return path


def _reject_prohibited_evidence(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = key.lower()
            if normalized in PROHIBITED_EVIDENCE_KEYS or normalized.startswith("held_out_"):
                _fail("PROHIBITED_EVIDENCE", f"prohibited evidence key: {key}")
            _reject_prohibited_evidence(child)
    elif isinstance(value, list) or isinstance(value, tuple):
        for child in value:
            _reject_prohibited_evidence(child)


def _canonical_source_inventory(entries: Sequence[dict[str, Any]]) -> dict[str, Any]:
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"logical_path", "role", "content_sha256"}:
            _fail("SOURCE_INVENTORY_MISMATCH", "source inventory entry has an invalid shape")
        logical_path = entry["logical_path"]
        _safe_relative_path(logical_path)
        if logical_path in seen:
            _fail("SOURCE_INVENTORY_MISMATCH", f"duplicate source path: {logical_path}")
        if not isinstance(entry["role"], str) or not entry["role"]:
            _fail("SOURCE_INVENTORY_MISMATCH", "source role must be nonempty")
        if not isinstance(entry["content_sha256"], str) or not SHA256_PATTERN.fullmatch(entry["content_sha256"]):
            _fail("SOURCE_INVENTORY_MISMATCH", "source hash is invalid")
        seen.add(logical_path)
        normalized.append(dict(entry))
    normalized.sort(key=lambda item: item["logical_path"])
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "p9_v2_source_inventory",
        "entries": normalized,
        "inventory_digest": canonical_sha256(normalized),
    }


def _canonical_incidents(
    events: Sequence[dict[str, Any]], additional: Sequence[dict[str, Any]]
) -> dict[str, Any]:
    incidents = [
        {
            "incident_id": event["event_id"],
            "event_sequence": event["event_sequence"],
            "incident_type": event["event_type"],
            "evidence": event["payload"],
        }
        for event in events
        if event["event_type"] in {"TRAINING_INTERRUPTED", "TRAINING_FAILED", "FINALIZATION_FAILED"}
    ]
    for item in additional:
        if not isinstance(item, dict) or not isinstance(item.get("incident_id"), str):
            _fail("CONTRACT_MISMATCH", "diagnostic incident requires incident_id")
        _reject_prohibited_evidence(item)
        incidents.append(dict(item))
    incidents.sort(key=lambda item: item["incident_id"])
    if len({item["incident_id"] for item in incidents}) != len(incidents):
        _fail("CONTRACT_MISMATCH", "diagnostic incident identities are duplicated")
    return {"schema_version": SCHEMA_VERSION, "artifact_type": "p9_v2_incidents", "incidents": incidents}


def _checkpoint_records(
    events: Sequence[dict[str, Any]],
    locator_map: Mapping[str, dict[str, dict[str, Any]]],
    roots: Mapping[str, str | Path],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    checkpoint_events = [event for event in events if event["event_type"] == "VALIDATION_CHECKPOINT_COMMITTED"]
    expected_ids = {event["payload"]["checkpoint_id"] for event in checkpoint_events}
    if set(locator_map) != expected_ids:
        _fail("VALIDATION_CHECKPOINT_MISMATCH", "checkpoint locator identities do not match committed events")
    records: list[dict[str, Any]] = []
    external: list[dict[str, Any]] = []
    object_bindings: dict[str, tuple[str, int]] = {}
    for event in checkpoint_events:
        payload = event["payload"]
        checkpoint_id = payload["checkpoint_id"]
        pair = locator_map[checkpoint_id]
        if not isinstance(pair, dict) or set(pair) != {"payload", "manifest"}:
            _fail("MALFORMED_LOCATOR", f"checkpoint {checkpoint_id} requires payload and manifest locators")
        payload_locator = _validate_locator_shape(pair["payload"])
        manifest_locator = _validate_locator_shape(pair["manifest"])
        if payload_locator["role"] != "checkpoint_payload" or manifest_locator["role"] != "checkpoint_manifest":
            _fail("MALFORMED_LOCATOR", f"checkpoint {checkpoint_id} locator roles are invalid")
        if payload_locator["content_sha256"] != payload["checkpoint_payload_sha256"]:
            _fail("VALIDATION_CHECKPOINT_MISMATCH", f"checkpoint {checkpoint_id} payload hash differs from event")
        if manifest_locator["content_sha256"] != payload["checkpoint_manifest_sha256"]:
            _fail("VALIDATION_CHECKPOINT_MISMATCH", f"checkpoint {checkpoint_id} manifest hash differs from event")
        if payload_locator["associated_manifest_sha256"] != manifest_locator["content_sha256"]:
            _fail("VALIDATION_CHECKPOINT_MISMATCH", f"checkpoint {checkpoint_id} payload locator has wrong manifest")
        for locator in (payload_locator, manifest_locator):
            _verify_locator(locator, roots)
            binding = (locator["content_sha256"], locator["byte_size"])
            previous = object_bindings.setdefault(locator["immutable_object_id"], binding)
            if previous != binding:
                _fail("CHECKPOINT_IDENTITY_CONFLICT", "immutable object identity has divergent content")
            external.append(locator)
        records.append({
            "event_id": event["event_id"],
            "event_sequence": event["event_sequence"],
            "completed_epoch": payload["completed_epoch"],
            "resume_epoch": payload["resume_epoch"],
            "optimizer_update": payload["optimizer_update"],
            "validation_id": payload["validation_id"],
            "checkpoint_id": checkpoint_id,
            "source_run_id": payload["source_run_id"],
            "validation_retrieval_loss": payload["validation_retrieval_loss"],
            "mean_source_separation_margin": payload["mean_source_separation_margin"],
            "payload_locator": payload_locator,
            "manifest_locator": manifest_locator,
        })
    records.sort(key=lambda item: (item["completed_epoch"], item["checkpoint_id"]))
    external.sort(key=lambda item: (item["role"], item["immutable_object_id"], canonical_sha256(item)))
    return records, external


def _document_bindings(documents: Mapping[str, dict[str, Any]], ledger_manifest_hash: str) -> dict[str, Any]:
    return {
        "authority_id": documents["authority"]["identity"],
        "authority_hash": documents["authority"]["content_sha256"],
        "scientific_configuration_id": documents["scientific_configuration"]["identity"],
        "scientific_configuration_hash": documents["scientific_configuration"]["content_sha256"],
        "runtime_id": documents["runtime"]["identity"],
        "runtime_digest": documents["runtime"]["content_sha256"],
        "source_parents_id": documents["source_parents"]["identity"],
        "source_parents_hash": documents["source_parents"]["content_sha256"],
        "cache_acceptance_id": documents["cache_acceptance"]["identity"],
        "cache_acceptance_hash": documents["cache_acceptance"]["content_sha256"],
        "sampler_contract_id": documents["sampler_contract"]["identity"],
        "sampler_contract_hash": documents["sampler_contract"]["content_sha256"],
        "selection_contract_id": documents["selection_contract"]["identity"],
        "selection_contract_hash": documents["selection_contract"]["content_sha256"],
        "ledger_manifest_id": f"sha256:{ledger_manifest_hash}",
        "ledger_manifest_sha256": ledger_manifest_hash,
    }


def _verify_document_linkage(
    documents: Mapping[str, dict[str, Any]], events: Sequence[dict[str, Any]], run_id: str,
    legacy_import: Mapping[str, Any] | None = None,
) -> None:
    authorization = events[0]
    if authorization["event_type"] != "RUN_AUTHORIZED":
        _fail("INVALID_LEDGER_BINDING", "ledger does not begin with authorization")
    auth_payload = authorization["payload"]
    if auth_payload["authority_hash"] != documents["authority"]["content_sha256"]:
        _fail("AUTHORITY_MISMATCH", "authorization event does not bind authority evidence")
    if auth_payload["scientific_configuration_hash"] != documents["scientific_configuration"]["content_sha256"]:
        _fail("SCIENTIFIC_CONFIGURATION_MISMATCH", "authorization event does not bind scientific configuration")
    parent_content = documents["source_parents"]["content"]
    if set(parent_content) != {"identities", "hashes"} or auth_payload["parent_identities"] != parent_content["identities"]:
        _fail("SOURCE_PARENT_MISMATCH", "authorization parent identities differ")
    starts = [event for event in events if event["event_type"] == "RUN_STARTED"]
    if not starts or starts[-1]["payload"]["runtime_digest"] != documents["runtime"]["content_sha256"]:
        _fail("RUNTIME_MISMATCH", "run-start event does not bind runtime digest")
    authority = documents["authority"]["content"]
    if authority.get("authority_kind") == "FUTURE_FORMAL_TRAINING":
        try:
            validate_instance("training_authority", documents["authority"])
        except P9V2SchemaError as error:
            _fail("AUTHORITY_MISMATCH", f"native training authority is invalid: {error}")
        expected_run_id = deterministic_id("p9runv2_", {
            "authority_hash": documents["authority"]["content_sha256"],
            "scientific_run_key": authority["scientific_run_key"],
        })
        if (
            run_id != expected_run_id
            or authority["scientific"]["configuration_id"] != documents["scientific_configuration"]["identity"]
            or authority["scientific"]["configuration_hash"] != documents["scientific_configuration"]["content_sha256"]
            or authority["scientific"]["selection_contract_id"] != documents["selection_contract"]["content"].get("contract_version")
            or authority["parents"] != parent_content["identities"]
            or authority["parent_hashes"] != parent_content["hashes"]
            or authority["parents"].get("production_cache_acceptance_id") != documents["cache_acceptance"]["identity"]
        ):
            _fail("AUTHORITY_MISMATCH", "native training authority bindings differ from bundle evidence")
        return
    expected = {
        "run_id": run_id,
        "scientific_configuration_id": documents["scientific_configuration"]["identity"],
        "scientific_configuration_hash": documents["scientific_configuration"]["content_sha256"],
        "source_parents_id": documents["source_parents"]["identity"],
        "source_parents_hash": documents["source_parents"]["content_sha256"],
        "cache_acceptance_id": documents["cache_acceptance"]["identity"],
        "cache_acceptance_hash": documents["cache_acceptance"]["content_sha256"],
        "sampler_contract_id": documents["sampler_contract"]["identity"],
        "sampler_contract_hash": documents["sampler_contract"]["content_sha256"],
        "selection_contract_id": documents["selection_contract"]["identity"],
        "selection_contract_hash": documents["selection_contract"]["content_sha256"],
    }
    if any(authority.get(key) != value for key, value in expected.items()):
        _fail("AUTHORITY_MISMATCH", "authority bindings differ from bundle evidence")
    extras = set(authority) - set(expected)
    if extras:
        if legacy_import is None or legacy_import.get("status") != "CANONICAL_MIGRATION":
            _fail("AUTHORITY_MISMATCH", "unexpected authority scope fields")
        try:
            validate_instance("migration_authority", documents["authority"])
        except P9V2SchemaError as error:
            _fail("AUTHORITY_MISMATCH", f"migration authority is invalid: {error}")
        if (
            legacy_import.get("migration_authority_id") != documents["authority"]["identity"]
            or legacy_import.get("migration_authority_hash") != documents["authority"]["content_sha256"]
            or authority.get("source_inventory_digest") != legacy_import.get("source_inventory_digest")
            or authority.get("source_v1_run_id") != legacy_import.get("source", {}).get("v1_run_id")
        ):
            _fail("AUTHORITY_MISMATCH", "migration authority differs from legacy annotation")


def _inventory_entry(path: str, raw: bytes) -> dict[str, Any]:
    return {
        "path": path,
        "required": True,
        "media_type": "application/x-ndjson" if path.endswith(".jsonl") else "application/json",
        "size_bytes": len(raw),
        "sha256": sha256_bytes(raw),
        "provenance_role": (
            "canonical_ledger_event_segment" if path.endswith(".jsonl") else path.split("/", 1)[0]
        ),
    }


def _external_summary(locator: dict[str, Any]) -> dict[str, Any]:
    return {
        "immutable_object_id": locator["immutable_object_id"],
        "role": locator["role"],
        "content_sha256": locator["content_sha256"],
        "byte_size": locator["byte_size"],
        "locator_digest": canonical_sha256(locator),
    }


def _validate_scientific_completeness(
    events: Sequence[dict[str, Any]], replay: ReplayResult, checkpoint_count: int
) -> None:
    if replay.scientific_state != "COMPLETE":
        if replay.training_completion_evidence is not None:
            _fail("SCIENTIFIC_COMPLETENESS_MISMATCH", "incomplete science carries completion evidence")
        return
    if replay.training_completion_evidence is None:
        _fail("SCIENTIFIC_COMPLETENESS_MISMATCH", "complete science lacks completion evidence")
    checkpoints = [
        event["payload"] for event in events
        if event["event_type"] == "VALIDATION_CHECKPOINT_COMMITTED"
    ]
    if checkpoint_count < 1 or not checkpoints:
        _fail("SCIENTIFIC_COMPLETENESS_MISMATCH", "complete science has no committed checkpoint candidate")
    final_checkpoint = checkpoints[-1]
    completion = replay.training_completion_evidence
    for field in ("completed_epoch", "resume_epoch", "optimizer_update"):
        if final_checkpoint[field] != completion[field]:
            _fail(
                "SCIENTIFIC_COMPLETENESS_MISMATCH",
                f"completion {field} differs from the final validation-checkpoint boundary",
            )


def _manifest_preimage(manifest: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in manifest.items() if key not in {"bundle_id", "bundle_content_sha256"}}


def build_run_bundle(
    ledger_root: str | Path,
    inputs: RunBundleInputs,
    locator_roots: Mapping[str, str | Path],
) -> RunBundleCandidate:
    """Build deterministic canonical bundle bytes from committed V2-A evidence."""

    if inputs.evaluation_consumption_count != 0:
        _fail("PROHIBITED_EVIDENCE", "evaluation consumption must be zero")
    legacy_import = inputs.legacy_import
    if legacy_import is not None:
        try:
            validate_instance("legacy_import", legacy_import)
        except P9V2SchemaError as error:
            _fail("CONTRACT_MISMATCH", f"legacy import annotation is invalid: {error}")
        if legacy_import["source_inventory_digest"] != canonical_sha256(
            sorted(inputs.source_inventory, key=lambda item: item["logical_path"])
        ):
            _fail("SOURCE_INVENTORY_MISMATCH", "legacy annotation source inventory digest differs")
    documents = {
        "authority": _validate_bound_document(inputs.authority, "authority"),
        "scientific_configuration": _validate_bound_document(inputs.scientific_configuration, "scientific configuration"),
        "runtime": _validate_bound_document(inputs.runtime, "runtime"),
        "source_parents": _validate_bound_document(inputs.source_parents, "source parents"),
        "cache_acceptance": _validate_bound_document(inputs.cache_acceptance, "cache acceptance"),
        "sampler_contract": _validate_bound_document(inputs.sampler_contract, "sampler contract"),
        "selection_contract": _validate_bound_document(inputs.selection_contract, "selection contract"),
    }
    committed = read_ledger(ledger_root)
    if not committed.closed:
        _fail("INVALID_LEDGER_BINDING", "run bundle requires a closed ledger")
    replay = replay_events(committed.events)
    if replay.run_id != committed.header["run_id"]:
        _fail("INVALID_LEDGER_BINDING", "ledger replay run identity differs")
    _verify_document_linkage(documents, committed.events, replay.run_id, legacy_import)
    checkpoints, external = _checkpoint_records(
        committed.events, inputs.checkpoint_locators, locator_roots
    )
    _validate_scientific_completeness(committed.events, replay, len(checkpoints))
    source_inventory = _canonical_source_inventory(inputs.source_inventory)
    incidents = _canonical_incidents(committed.events, inputs.diagnostic_incidents)
    validation_events = [
        event for event in committed.events if event["event_type"] == "VALIDATION_CHECKPOINT_COMMITTED"
    ]
    checkpoint_inventory = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "p9_v2_checkpoint_inventory",
        "checkpoints": checkpoints,
    }
    training_summary = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "p9_v2_training_summary",
        "run_id": replay.run_id,
        "scientific_state": replay.scientific_state,
        "operational_state": replay.operational_state,
        "resumability_state": replay.resumability_state,
        "last_committed_sequence": replay.last_committed_sequence,
        "last_committed_event_hash": replay.last_committed_event_hash,
        "validation_checkpoint_count": len(validation_events),
    }
    final_selector = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "p9_v2_final_selector_state_evidence",
        "present": replay.best_checkpoint_state is not None,
        "selector_state": replay.best_checkpoint_state,
    }
    stopping_boundary = replay.training_completion_evidence
    stopping = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "p9_v2_stopping_boundary",
        "present": stopping_boundary is not None,
        "boundary": stopping_boundary,
    }
    event_inventory = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "p9_v2_validation_checkpoint_events",
        "events": validation_events,
    }
    files: dict[str, bytes] = {
        BOUND_DOCUMENT_PATHS[name]: canonical_json_bytes(document)
        for name, document in documents.items()
    }
    ledger_root = Path(ledger_root)
    files["ledger/header.json"] = (ledger_root / "header.json").read_bytes()
    for segment in committed.segment_inventory:
        relative = segment["path"]
        files[f"ledger/{relative}"] = (ledger_root / relative).read_bytes()
    ledger_manifest_path = ledger_root / "commit" / "ledger_manifest.json"
    files["ledger/commit/ledger_manifest.json"] = ledger_manifest_path.read_bytes()
    files.update({
        "summary/training_summary.json": canonical_json_bytes(training_summary),
        "summary/final_selector_state.json": canonical_json_bytes(final_selector),
        "summary/stopping_boundary.json": canonical_json_bytes(stopping),
        "events/validation_checkpoint_events.json": canonical_json_bytes(event_inventory),
        "checkpoints/checkpoint_inventory.json": canonical_json_bytes(checkpoint_inventory),
        "diagnostics/incidents.json": canonical_json_bytes(incidents),
        "provenance/source_inventory.json": canonical_json_bytes(source_inventory),
    })
    entries = [_inventory_entry(path, files[path]) for path in sorted(files)]
    inventory = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "p9_v2_bundle_inventory",
        "entries": entries,
    }
    validate_instance("bundle_inventory", inventory)
    inventory_bytes = canonical_json_bytes(inventory)
    ledger_manifest_hash = sha256_bytes(files["ledger/commit/ledger_manifest.json"])
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "p9_v2_run_bundle_manifest",
        "run_id": replay.run_id,
        "bindings": _document_bindings(documents, ledger_manifest_hash),
        "scientific_state": replay.scientific_state,
        "operational_state": replay.operational_state,
        "resumability_state": replay.resumability_state,
        "bundle_status": (
            "SCIENTIFICALLY_COMPLETE" if replay.scientific_state == "COMPLETE"
            else "SCIENTIFICALLY_INCOMPLETE"
        ),
        "evaluation_consumption_count": 0,
        "ledger": {
            "manifest_path": "ledger/commit/ledger_manifest.json",
            "event_count": len(committed.events),
            "last_sequence": committed.last_sequence,
            "tail_event_hash": committed.last_event_hash,
        },
        "inventory": {
            "path": INVENTORY_PATH,
            "sha256": sha256_bytes(inventory_bytes),
            "size_bytes": len(inventory_bytes),
        },
        "external_objects": [_external_summary(locator) for locator in external],
        "validation_checkpoint_count": len(validation_events),
        "stopping_boundary": stopping_boundary,
        "source_inventory_digest": source_inventory["inventory_digest"],
        "legacy_import": {
            "is_legacy_import": legacy_import is not None,
            "annotation": legacy_import,
        },
    }
    content_hash = canonical_sha256(_manifest_preimage(manifest))
    manifest["bundle_content_sha256"] = content_hash
    manifest["bundle_id"] = f"p9rb_{content_hash[:24]}"
    validate_instance("run_bundle_manifest", manifest)
    files[INVENTORY_PATH] = inventory_bytes
    files[COMMIT_PATH] = canonical_json_bytes(manifest)
    return RunBundleCandidate(
        bundle_id=manifest["bundle_id"],
        bundle_content_sha256=content_hash,
        files=tuple((path, files[path]) for path in sorted(files)),
    )


def _read_canonical(path: Path) -> Any:
    try:
        return parse_canonical_json(path.read_bytes())
    except (OSError, CanonicalJSONError) as error:
        _fail("MALFORMED_CANONICAL_JSON", f"cannot read canonical JSON {path.name}: {error}")


def _required_paths(entries: Sequence[dict[str, Any]]) -> None:
    paths = {entry["path"] for entry in entries}
    missing = REQUIRED_FIXED_PATHS - paths
    if missing:
        _fail("MISSING_REQUIRED_BUNDLE_FILE", f"missing inventory paths: {sorted(missing)}")
    if not any(path.startswith("ledger/segments/") and path.endswith(".jsonl") for path in paths):
        _fail("MISSING_REQUIRED_BUNDLE_FILE", "bundle has no committed ledger segment")
    unexpected = paths - REQUIRED_FIXED_PATHS
    invalid = [
        path for path in unexpected
        if not re.fullmatch(r"ledger/segments/[0-9]{12}-[0-9]{12}\.jsonl", path)
    ]
    if invalid:
        _fail("UNEXPECTED_INVENTORY_MEMBER", f"unexpected inventory paths: {sorted(invalid)}")


def _validate_checkpoint_inventory(
    root: Path,
    events: Sequence[dict[str, Any]],
    roots: Mapping[str, str | Path],
) -> tuple[int, list[dict[str, Any]]]:
    checkpoint_document = _read_canonical(root / "checkpoints/checkpoint_inventory.json")
    if set(checkpoint_document) != {"schema_version", "artifact_type", "checkpoints"}:
        _fail("VALIDATION_CHECKPOINT_MISMATCH", "checkpoint inventory shape is invalid")
    records = checkpoint_document["checkpoints"]
    if not isinstance(records, list):
        _fail("VALIDATION_CHECKPOINT_MISMATCH", "checkpoint inventory must be an array")
    if records != sorted(records, key=lambda item: (item["completed_epoch"], item["checkpoint_id"])):
        _fail("NONCANONICAL_INVENTORY_ORDER", "checkpoint inventory ordering is invalid")
    committed = [event for event in events if event["event_type"] == "VALIDATION_CHECKPOINT_COMMITTED"]
    if len(records) != len(committed):
        _fail("VALIDATION_CHECKPOINT_MISMATCH", "checkpoint inventory count differs from committed events")
    external: list[dict[str, Any]] = []
    checkpoint_ids: dict[str, tuple[str, str]] = {}
    for event, record in zip(committed, records):
        payload = event["payload"]
        expected = {
            "event_id": event["event_id"], "event_sequence": event["event_sequence"],
            "completed_epoch": payload["completed_epoch"], "resume_epoch": payload["resume_epoch"],
            "optimizer_update": payload["optimizer_update"], "validation_id": payload["validation_id"],
            "checkpoint_id": payload["checkpoint_id"], "source_run_id": payload["source_run_id"],
            "validation_retrieval_loss": payload["validation_retrieval_loss"],
            "mean_source_separation_margin": payload["mean_source_separation_margin"],
        }
        if any(record.get(key) != value for key, value in expected.items()):
            _fail("VALIDATION_CHECKPOINT_MISMATCH", f"checkpoint record differs for {payload['checkpoint_id']}")
        payload_locator = _validate_locator_shape(record.get("payload_locator"))
        manifest_locator = _validate_locator_shape(record.get("manifest_locator"))
        if payload_locator["content_sha256"] != payload["checkpoint_payload_sha256"]:
            _fail("VALIDATION_CHECKPOINT_MISMATCH", "checkpoint payload hash differs from event")
        if manifest_locator["content_sha256"] != payload["checkpoint_manifest_sha256"]:
            _fail("VALIDATION_CHECKPOINT_MISMATCH", "checkpoint manifest hash differs from event")
        if payload_locator["associated_manifest_sha256"] != manifest_locator["content_sha256"]:
            _fail("VALIDATION_CHECKPOINT_MISMATCH", "checkpoint locator manifest binding differs")
        _verify_locator(payload_locator, roots)
        _verify_locator(manifest_locator, roots)
        content = (payload_locator["content_sha256"], manifest_locator["content_sha256"])
        prior = checkpoint_ids.setdefault(payload["checkpoint_id"], content)
        if prior != content:
            _fail("CHECKPOINT_IDENTITY_CONFLICT", "checkpoint identity has divergent content")
        external.extend((payload_locator, manifest_locator))
    external.sort(key=lambda item: (item["role"], item["immutable_object_id"], canonical_sha256(item)))
    return len(records), external


def _validate_bundle(root: Path, locator_roots: Mapping[str, str | Path], *, require_name: bool) -> BundleValidationResult:
    if not (root / COMMIT_PATH).is_file():
        _fail("MISSING_REQUIRED_BUNDLE_FILE", "bundle commit manifest is absent")
    if not (root / INVENTORY_PATH).is_file():
        _fail("MISSING_REQUIRED_BUNDLE_FILE", "bundle inventory is absent")
    manifest = _read_canonical(root / COMMIT_PATH)
    inventory = _read_canonical(root / INVENTORY_PATH)
    try:
        validate_instance("run_bundle_manifest", manifest)
        validate_instance("bundle_inventory", inventory)
    except P9V2SchemaError as error:
        _fail("BUNDLE_SCHEMA_INVALID", str(error))
    if require_name and root.name != manifest["bundle_id"]:
        _fail("BUNDLE_ID_MISMATCH", "bundle directory name differs from manifest identity")
    content_hash = canonical_sha256(_manifest_preimage(manifest))
    if manifest["bundle_content_sha256"] != content_hash:
        _fail("BUNDLE_CONTENT_HASH_MISMATCH", "bundle content hash differs from manifest preimage")
    if manifest["bundle_id"] != f"p9rb_{content_hash[:24]}":
        _fail("BUNDLE_ID_MISMATCH", "bundle identity differs from content hash")
    inventory_raw = (root / INVENTORY_PATH).read_bytes()
    if manifest["inventory"] != {
        "path": INVENTORY_PATH, "sha256": sha256_bytes(inventory_raw), "size_bytes": len(inventory_raw)
    }:
        _fail("INVENTORY_HASH_MISMATCH", "manifest does not bind canonical inventory bytes")
    entries = inventory["entries"]
    paths = [entry["path"] for entry in entries]
    if paths != sorted(paths):
        _fail("NONCANONICAL_INVENTORY_ORDER", "bundle inventory is not path sorted")
    if len(paths) != len(set(paths)):
        _fail("DUPLICATE_INVENTORY_ENTRY", "bundle inventory has duplicate paths")
    for path in paths:
        _safe_relative_path(path)
    _required_paths(entries)
    actual = sorted(
        path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()
    )
    expected_actual = sorted([*paths, INVENTORY_PATH, COMMIT_PATH])
    if actual != expected_actual:
        _fail("UNEXPECTED_INVENTORY_MEMBER", "filesystem members differ from canonical inventory")
    for entry in entries:
        raw = (root / entry["path"]).read_bytes()
        if len(raw) != entry["size_bytes"] or sha256_bytes(raw) != entry["sha256"]:
            _fail("INTERNAL_ARTIFACT_HASH_MISMATCH", f"inventory hash/size differs: {entry['path']}")
    documents = {
        name: _validate_bound_document(_read_canonical(root / path), name)
        for name, path in BOUND_DOCUMENT_PATHS.items()
    }
    for path in paths:
        if path.endswith(".json"):
            _reject_prohibited_evidence(_read_canonical(root / path))
    ledger_root = root / "ledger"
    try:
        committed = read_ledger(ledger_root)
        if not committed.closed:
            _fail("INVALID_LEDGER_BINDING", "bound ledger is not closed")
        replay = replay_events(committed.events)
    except LedgerError as error:
        _fail("INVALID_LEDGER_BINDING", str(error))
    if manifest["run_id"] != committed.header["run_id"] or manifest["run_id"] != replay.run_id:
        _fail("RUN_ID_MISMATCH", "bundle, ledger, and replay run identities differ")
    ledger_manifest_raw = (ledger_root / "commit/ledger_manifest.json").read_bytes()
    if manifest["bindings"]["ledger_manifest_sha256"] != sha256_bytes(ledger_manifest_raw):
        _fail("LEDGER_HASH_MISMATCH", "bundle ledger manifest hash differs")
    expected_ledger = {
        "manifest_path": "ledger/commit/ledger_manifest.json",
        "event_count": len(committed.events),
        "last_sequence": committed.last_sequence,
        "tail_event_hash": committed.last_event_hash,
    }
    if manifest["ledger"] != expected_ledger:
        _fail("INVALID_LEDGER_BINDING", "bundle ledger summary differs")
    legacy_annotation = (
        manifest.get("legacy_import", {}).get("annotation")
        if manifest.get("legacy_import", {}).get("is_legacy_import") else None
    )
    _verify_document_linkage(documents, committed.events, replay.run_id, legacy_annotation)
    expected_bindings = _document_bindings(documents, sha256_bytes(ledger_manifest_raw))
    if manifest["bindings"] != expected_bindings:
        _fail("CONTRACT_MISMATCH", "manifest evidence bindings differ")
    validation_document = _read_canonical(root / "events/validation_checkpoint_events.json")
    expected_events = [event for event in committed.events if event["event_type"] == "VALIDATION_CHECKPOINT_COMMITTED"]
    if validation_document != {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "p9_v2_validation_checkpoint_events",
        "events": expected_events,
    }:
        _fail("VALIDATION_CHECKPOINT_MISMATCH", "candidate events are not exact committed checkpoint events")
    checkpoint_count, external = _validate_checkpoint_inventory(root, committed.events, locator_roots)
    _validate_scientific_completeness(committed.events, replay, checkpoint_count)
    if manifest["external_objects"] != [_external_summary(locator) for locator in external]:
        _fail("CONTRACT_MISMATCH", "external object summary differs from checkpoint locators")
    source_inventory = _read_canonical(root / "provenance/source_inventory.json")
    canonical_sources = _canonical_source_inventory(source_inventory.get("entries", []))
    if source_inventory != canonical_sources:
        _fail("SOURCE_INVENTORY_MISMATCH", "source inventory content or order differs")
    if manifest["source_inventory_digest"] != source_inventory["inventory_digest"]:
        _fail("SOURCE_INVENTORY_MISMATCH", "manifest source inventory digest differs")
    training_summary = _read_canonical(root / "summary/training_summary.json")
    expected_summary = {
        "schema_version": SCHEMA_VERSION, "artifact_type": "p9_v2_training_summary",
        "run_id": replay.run_id, "scientific_state": replay.scientific_state,
        "operational_state": replay.operational_state, "resumability_state": replay.resumability_state,
        "last_committed_sequence": replay.last_committed_sequence,
        "last_committed_event_hash": replay.last_committed_event_hash,
        "validation_checkpoint_count": checkpoint_count,
    }
    if training_summary != expected_summary:
        _fail("CONTRACT_MISMATCH", "training summary differs from replay")
    expected_status = "SCIENTIFICALLY_COMPLETE" if replay.scientific_state == "COMPLETE" else "SCIENTIFICALLY_INCOMPLETE"
    state_fields = {
        "scientific_state": replay.scientific_state,
        "operational_state": replay.operational_state,
        "resumability_state": replay.resumability_state,
        "bundle_status": expected_status,
        "validation_checkpoint_count": checkpoint_count,
        "stopping_boundary": replay.training_completion_evidence,
    }
    if any(manifest[key] != value for key, value in state_fields.items()):
        _fail("SCIENTIFIC_COMPLETENESS_MISMATCH", "manifest state differs from canonical replay")
    selector = _read_canonical(root / "summary/final_selector_state.json")
    if selector != {
        "schema_version": SCHEMA_VERSION, "artifact_type": "p9_v2_final_selector_state_evidence",
        "present": replay.best_checkpoint_state is not None, "selector_state": replay.best_checkpoint_state,
    }:
        _fail("CONTRACT_MISMATCH", "selector evidence differs from replay")
    stopping = _read_canonical(root / "summary/stopping_boundary.json")
    if stopping != {
        "schema_version": SCHEMA_VERSION, "artifact_type": "p9_v2_stopping_boundary",
        "present": replay.training_completion_evidence is not None,
        "boundary": replay.training_completion_evidence,
    }:
        _fail("SCIENTIFIC_COMPLETENESS_MISMATCH", "stopping boundary differs from replay")
    if manifest["evaluation_consumption_count"] != 0:
        _fail("PROHIBITED_EVIDENCE", "evaluation consumption is nonzero")
    legacy = manifest["legacy_import"]
    if legacy["is_legacy_import"]:
        try:
            validate_instance("legacy_import", legacy["annotation"])
        except P9V2SchemaError as error:
            _fail("CONTRACT_MISMATCH", f"legacy import annotation is invalid: {error}")
        if legacy["annotation"]["imported_run_id"] != manifest["run_id"]:
            _fail("RUN_ID_MISMATCH", "legacy annotation imported run identity differs")
        if legacy["annotation"]["source_inventory_digest"] != source_inventory["inventory_digest"]:
            _fail("SOURCE_INVENTORY_MISMATCH", "legacy annotation source inventory digest differs")
    elif legacy["annotation"] is not None:
        _fail("CONTRACT_MISMATCH", "native bundle cannot carry a legacy annotation")
    return BundleValidationResult(
        valid=True,
        validation_status="VALID",
        completeness=expected_status,
        bundle_id=manifest["bundle_id"],
        bundle_content_sha256=manifest["bundle_content_sha256"],
        run_id=replay.run_id,
        scientific_state=replay.scientific_state,
        operational_state=replay.operational_state,
        resumability_state=replay.resumability_state,
        ledger_tail_hash=replay.last_committed_event_hash,
        validation_checkpoint_count=checkpoint_count,
        source_inventory_digest=source_inventory["inventory_digest"],
    )


def validate_run_bundle(
    bundle_root: str | Path,
    locator_roots: Mapping[str, str | Path],
) -> BundleValidationResult:
    """Return a deterministic structured result; invalid evidence never raises."""

    root = Path(bundle_root)
    try:
        return _validate_bundle(root, locator_roots, require_name=True)
    except BundleError as error:
        return BundleValidationResult(
            valid=False,
            validation_status="INVALID",
            completeness="EVIDENCE_INVALID",
            bundle_id=root.name if BUNDLE_ID_PATTERN.fullmatch(root.name) else None,
            bundle_content_sha256=None,
            run_id=None,
            scientific_state=None,
            operational_state=None,
            resumability_state="EVIDENCE_INVALID",
            ledger_tail_hash=None,
            validation_checkpoint_count=0,
            source_inventory_digest=None,
            error_codes=(error.code,),
            errors=(error.message,),
        )
    except (OSError, CanonicalJSONError, P9V2SchemaError, LedgerError, KeyError, TypeError) as error:
        return BundleValidationResult(
            valid=False,
            validation_status="INVALID",
            completeness="EVIDENCE_INVALID",
            bundle_id=root.name if BUNDLE_ID_PATTERN.fullmatch(root.name) else None,
            bundle_content_sha256=None,
            run_id=None,
            scientific_state=None,
            operational_state=None,
            resumability_state="EVIDENCE_INVALID",
            ledger_tail_hash=None,
            validation_checkpoint_count=0,
            source_inventory_digest=None,
            error_codes=("INVALID_EVIDENCE",),
            errors=(str(error),),
        )


def load_run_bundle(bundle_root: str | Path, locator_roots: Mapping[str, str | Path]) -> dict[str, Any]:
    result = validate_run_bundle(bundle_root, locator_roots)
    if not result.valid:
        _fail(result.error_codes[0], result.errors[0])
    return _read_canonical(Path(bundle_root) / COMMIT_PATH)


def _write_candidate(root: Path, candidate: RunBundleCandidate) -> None:
    for relative, raw in candidate.files:
        path = root.joinpath(*PurePosixPath(relative).parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o640)
        try:
            write_all(descriptor, raw)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    directories = sorted(
        (path for path in root.rglob("*") if path.is_dir()),
        key=lambda path: len(path.parts),
        reverse=True,
    )
    for directory in directories:
        fsync_directory(directory)
    fsync_directory(root)


def publish_run_bundle(
    candidate: RunBundleCandidate,
    publication_root: str | Path,
    locator_roots: Mapping[str, str | Path],
) -> BundlePublication:
    """Publish by atomic directory rename or validate an existing identical bundle."""

    publication_root = Path(publication_root)
    publication_root.mkdir(parents=True, exist_ok=True)
    staging_root = publication_root / ".staging"
    staging_root.mkdir(exist_ok=True)
    final = publication_root / candidate.bundle_id
    if final.exists():
        result = validate_run_bundle(final, locator_roots)
        if not result.valid or result.bundle_content_sha256 != candidate.bundle_content_sha256:
            _fail("PUBLICATION_COLLISION", "existing bundle identity path is inconsistent")
        return BundlePublication(final, candidate.bundle_id, False, result)
    stage = Path(tempfile.mkdtemp(prefix=f"{candidate.bundle_id}.", suffix=".incomplete", dir=staging_root))
    try:
        _write_candidate(stage, candidate)
        staged = _validate_bundle(stage, locator_roots, require_name=False)
        if staged.bundle_id != candidate.bundle_id or staged.bundle_content_sha256 != candidate.bundle_content_sha256:
            _fail("CONTRACT_MISMATCH", "staged bundle differs from candidate")
        try:
            os.rename(stage, final)
            created = True
        except OSError as error:
            if error.errno not in {errno.EEXIST, errno.ENOTEMPTY} or not final.exists():
                raise
            existing = validate_run_bundle(final, locator_roots)
            if not existing.valid or existing.bundle_content_sha256 != candidate.bundle_content_sha256:
                _fail("PUBLICATION_COLLISION", "concurrent bundle publication is inconsistent")
            shutil.rmtree(stage)
            return BundlePublication(final, candidate.bundle_id, False, existing)
        fsync_directory(publication_root)
        result = validate_run_bundle(final, locator_roots)
        if not result.valid:
            _fail(result.error_codes[0], result.errors[0])
        return BundlePublication(final, candidate.bundle_id, created, result)
    except Exception:
        if stage.exists():
            shutil.rmtree(stage)
        raise
