"""Read-only P9 v1 formal-run inspection and noncanonical V2-D dry-run mapping."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping, Sequence

from p9_v2_bundle import (
    RunBundleInputs,
    build_run_bundle,
    make_bound_document,
    make_filesystem_locator,
    publish_run_bundle,
    validate_run_bundle,
)
from p9_v2_canonical import canonical_sha256
from p9_v2_finalization import (
    evaluate_selection_candidate,
    finalize_run_bundle,
    make_selection_contract,
    qualifies_patience_reset,
)
from p9_v2_ledger import LedgerWriter, read_ledger
from p9_v2_replay import ReplayResult, replay_events
from p9_v2_schema import SCHEMA_VERSION, validate_instance


IMPORTER_VERSION = "p9-v2-legacy-importer-v1"
LEGACY_NAMESPACE = "p9-v1-history"
EXPECTED_PAIR_COUNT = 25
EXPECTED_SELECTED_CHECKPOINT = "p9ck_42f7957d2ea998ac9e8ff705"
EXPECTED_SELECTED_PAYLOAD_SHA256 = "fdac720bff12fb25747f69977bc69c5fb28adbc4a73cabd879b1b57c47cc06b6"
EXPECTED_SELECTED_MANIFEST_SHA256 = "87010ce01ad74fc7b2652bf0e5a7e56baea2bef88400f6f23748d1e39f9227bc"

CLASSIFICATIONS = (
    "DIRECTLY_AVAILABLE",
    "DETERMINISTICALLY_DERIVABLE",
    "AVAILABLE_WITH_LEGACY_ANNOTATION",
    "NOT_APPLICABLE",
    "MISSING_BLOCKING",
)


class LegacyImportError(ValueError):
    """A stable fail-closed historical evidence rejection."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


@dataclass(frozen=True)
class LegacyRunSources:
    attempt_root: Path
    authority_root: Path
    join_audit_path: Path
    authority_id: str = "p9a_9d6f0554553ac43371b47efd"
    reservation_id: str = "p9res_0f5492c80e7c152e6c543012"
    attempt_id: str = "p9attempt_a754afd14ac87287afb04029"
    run_id: str = "p9run_6887930091dd2f2bfedc3c96"


@dataclass(frozen=True)
class LegacyInspection:
    sources: LegacyRunSources
    imported_run_id: str
    pairs: tuple[dict[str, Any], ...]
    source_inventory: tuple[dict[str, Any], ...]
    source_inventory_digest: str
    field_classifications: tuple[dict[str, str], ...]
    classification_counts: dict[str, int]
    legacy_annotation: dict[str, Any]
    documents: dict[str, dict[str, Any]]
    terminal_state: dict[str, Any]


@dataclass(frozen=True)
class LegacyImportValidation:
    valid: bool
    migration_verdict: str
    pair_count: int
    missing_blocking: int
    selected_checkpoint_id: str | None
    selected_epoch: int | None
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class LegacyMapping:
    ledger_root: Path
    replay: ReplayResult
    inputs: RunBundleInputs
    locator_roots: dict[str, Path]


@dataclass(frozen=True)
class LegacyDryRun:
    inspection: LegacyInspection
    mapping: LegacyMapping
    bundle_path: Path
    bundle_id: str
    bundle_hash: str
    bundle_validation: Any
    finalization_result: dict[str, Any]


def historical_p9_sources() -> LegacyRunSources:
    formal_root = Path("/mnt/hdd002/dhnyu/fusedata/models/reduced/formal_training")
    return LegacyRunSources(
        attempt_root=formal_root / "attempts/p9attempt_a754afd14ac87287afb04029",
        authority_root=formal_root / "authorization/p9a_9d6f0554553ac43371b47efd",
        join_audit_path=formal_root / "recovery_authorization/p9ra_2b5e0dc9eebb81c028fefedf/checkpoint_join_audit.json",
    )


def _fail(code: str, message: str) -> None:
    raise LegacyImportError(code, message)


def _immutable_file(path: Path) -> Path:
    if path.is_symlink() or not path.is_file():
        _fail("SOURCE_FILE_INVALID", f"source must be a regular non-symlink file: {path}")
    return path


def _file_sha256(path: Path) -> str:
    with _immutable_file(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(_immutable_file(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        _fail("SOURCE_JSON_INVALID", f"cannot parse {path}: {error}")
    if not isinstance(value, dict):
        _fail("SOURCE_JSON_INVALID", f"JSON root is not an object: {path}")
    return value


def _logical_source(path: Path, sources: LegacyRunSources) -> str:
    roots = (
        (sources.attempt_root, "attempt"),
        (sources.authority_root, "authority"),
        (sources.join_audit_path.parent, "recovery_audit"),
    )
    resolved = path.resolve()
    for root, prefix in roots:
        try:
            relative = resolved.relative_to(root.resolve())
            return f"{prefix}/{relative.as_posix()}"
        except ValueError:
            continue
    _fail("SOURCE_PATH_INVALID", f"source lies outside explicit historical roots: {path}")


def _source_entry(path: Path, role: str, sources: LegacyRunSources) -> dict[str, str]:
    return {
        "logical_path": _logical_source(path, sources),
        "role": role,
        "content_sha256": _file_sha256(path),
    }


def _safe_load_checkpoint(payload_path: Path, expected_sha256: str) -> dict[str, Any]:
    """Restricted historical loader; never exposed as a general checkpoint API."""

    actual = _file_sha256(payload_path)
    if actual != expected_sha256:
        _fail("PAYLOAD_HASH_MISMATCH", f"checkpoint payload hash differs: {payload_path}")
    import numpy as np
    import torch

    allowed = (
        np._core.multiarray._reconstruct,
        np.ndarray,
        np.dtype,
        np._core.multiarray.scalar,
        np.dtypes.UInt32DType,
    )
    try:
        with torch.serialization.safe_globals(allowed):
            state = torch.load(payload_path, map_location="cpu", weights_only=True)
    except Exception as error:
        _fail("RESTRICTED_DESERIALIZATION_FAILED", f"weights-only load failed: {error}")
    if not isinstance(state, dict):
        _fail("CHECKPOINT_STATE_INVALID", "checkpoint root is not a mapping")
    return state


def _field_classifications() -> tuple[dict[str, str], ...]:
    values = {
        "authority_manifest": ("DIRECTLY_AVAILABLE", "formal_training_authority.json"),
        "scientific_configuration": ("DIRECTLY_AVAILABLE", "v1 authority training and validation contracts"),
        "runtime_digest": ("DIRECTLY_AVAILABLE", "checkpoint lineage and authority runtime manifest"),
        "source_parents_and_cache": ("DIRECTLY_AVAILABLE", "immutable_root_inventory.json"),
        "sampler_contract": ("DIRECTLY_AVAILABLE", "authority sampler contract"),
        "run_identity": ("DIRECTLY_AVAILABLE", "attempt_state.json"),
        "native_contemporaneous_v2_ledger": ("NOT_APPLICABLE", "legacy import creates explicitly marked events"),
        "event_sequence_and_hash_chain": ("DETERMINISTICALLY_DERIVABLE", "p9-v1-formal-to-v2-events-v1"),
        "completed_epochs": ("DIRECTLY_AVAILABLE", "checkpoint join validation epochs"),
        "resume_epochs": ("DETERMINISTICALLY_DERIVABLE", "completed_epoch + 1, checked against manifests"),
        "optimizer_updates": ("DIRECTLY_AVAILABLE", "join audit and checkpoint progress"),
        "validation_ids": ("DETERMINISTICALLY_DERIVABLE", "canonical source run/epoch/metric/embedding hash"),
        "checkpoint_ids_and_payload_hashes": ("DIRECTLY_AVAILABLE", "checkpoint manifests and join audit"),
        "checkpoint_manifest_hashes": ("DIRECTLY_AVAILABLE", "checkpoint join audit and file bytes"),
        "atomic_completion_marker": ("AVAILABLE_WITH_LEGACY_ANNOTATION", "hash-verified legacy payload-manifest publication pair"),
        "online_model_state": ("DIRECTLY_AVAILABLE", "restricted checkpoint inspection"),
        "ema_model_state": ("DIRECTLY_AVAILABLE", "restricted checkpoint inspection"),
        "optimizer_state": ("DIRECTLY_AVAILABLE", "restricted checkpoint inspection"),
        "scheduler_state": ("DIRECTLY_AVAILABLE", "restricted checkpoint inspection"),
        "amp_scaler_state": ("NOT_APPLICABLE", "authority amp=false and checkpoint scaler=null"),
        "queue_state": ("DIRECTLY_AVAILABLE", "restricted checkpoint inspection and arithmetic"),
        "sampler_state": ("DIRECTLY_AVAILABLE", "restricted checkpoint inspection"),
        "per_rank_rng_state": ("DIRECTLY_AVAILABLE", "two checkpoint RNG records for world size two"),
        "early_stopping_and_selector_state": ("DIRECTLY_AVAILABLE", "checkpoint trace and best state"),
        "training_and_validation_trace": ("DIRECTLY_AVAILABLE", "checkpoint payload traces"),
        "training_completed_event": ("DETERMINISTICALLY_DERIVABLE", "patience four at epoch 125/update 9500"),
        "stopping_boundary": ("DETERMINISTICALLY_DERIVABLE", "ledger replay over immutable trace"),
        "diagnostic_incident": ("AVAILABLE_WITH_LEGACY_ANNOTATION", "unchanged FAILED_NONRESUMABLE finalization incident"),
        "evaluation_consumption_count": ("DIRECTLY_AVAILABLE", "all validations and terminal evidence record zero"),
        "source_inventory_digest": ("DETERMINISTICALLY_DERIVABLE", "ordered logical source paths and hashes"),
        "v1_terminal_state": ("DIRECTLY_AVAILABLE", "attempt_state and terminal_failure"),
    }
    return tuple(
        {"field": field, "classification": classification, "source_or_rule": source}
        for field, (classification, source) in sorted(values.items())
    )


def _inspect_pair(
    row: dict[str, Any], ordinal: int, validation_trace: Sequence[dict[str, Any]],
    worker_manifests: Mapping[str, dict[str, Any]], authority: dict[str, Any], sources: LegacyRunSources,
) -> dict[str, Any]:
    if set(row) != {
        "checkpoint_id", "checkpoint_manifest_path", "checkpoint_manifest_sha256",
        "checkpoint_payload_path", "checkpoint_payload_sha256", "classification",
        "global_update", "resume_epoch", "validation", "validation_epoch",
    }:
        _fail("AMBIGUOUS_SOURCE_MAPPING", f"join row {ordinal} has an unsupported shape")
    if row["classification"] != "EXACT_MATCH":
        _fail("AMBIGUOUS_SOURCE_MAPPING", f"join row {ordinal} is not EXACT_MATCH")
    completed_epoch = ordinal * 5
    update = completed_epoch * int(authority["training_contract"]["trajectory"]["updates_per_epoch"])
    if row["validation_epoch"] != completed_epoch or row["validation"]["epoch"] != completed_epoch:
        _fail("EPOCH_MISMATCH", f"join row {ordinal} completed epoch differs")
    if row["resume_epoch"] != completed_epoch + 1:
        _fail("RESUME_EPOCH_MISMATCH", f"join row {ordinal} resume epoch differs")
    if row["global_update"] != update:
        _fail("OPTIMIZER_UPDATE_MISMATCH", f"join row {ordinal} optimizer update differs")
    if row["validation"] != validation_trace[ordinal - 1]:
        _fail("VALIDATION_COUNTERPART_MISMATCH", f"join row {ordinal} validation counterpart differs")
    manifest_path = Path(row["checkpoint_manifest_path"])
    payload_path = Path(row["checkpoint_payload_path"])
    expected_root = sources.attempt_root / "checkpoints" / f"epoch-{completed_epoch:03d}"
    if manifest_path != expected_root / "checkpoint_manifest.json" or payload_path != expected_root / "checkpoint.pt":
        _fail("SOURCE_PATH_INVALID", f"join row {ordinal} paths are not canonical historical paths")
    manifest_hash = _file_sha256(manifest_path)
    if manifest_hash != row["checkpoint_manifest_sha256"]:
        _fail("MANIFEST_HASH_MISMATCH", f"join row {ordinal} manifest hash differs")
    manifest = _read_json(manifest_path)
    if manifest.get("schema_version") != "1.0.0" or manifest.get("artifact_type") != "p9_resume_checkpoint_manifest":
        _fail("UNSUPPORTED_HISTORICAL_SCHEMA", f"checkpoint manifest {ordinal} schema is unsupported")
    if manifest.get("checkpoint_id") != row["checkpoint_id"] or manifest.get("epoch") != row["resume_epoch"]:
        _fail("CHECKPOINT_IDENTITY_MISMATCH", f"checkpoint manifest {ordinal} identity/epoch differs")
    if manifest.get("global_update") != update or manifest.get("payload", {}).get("filename") != "checkpoint.pt":
        _fail("OPTIMIZER_UPDATE_MISMATCH", f"checkpoint manifest {ordinal} progress differs")
    if manifest["payload"]["sha256"] != row["checkpoint_payload_sha256"]:
        _fail("PAYLOAD_HASH_MISMATCH", f"join row {ordinal} payload binding differs")
    if manifest["payload"]["size_bytes"] != payload_path.stat().st_size:
        _fail("PAYLOAD_SIZE_MISMATCH", f"checkpoint payload {ordinal} size differs")
    worker_manifest = worker_manifests.get(row["checkpoint_id"])
    if worker_manifest != manifest:
        _fail("CHECKPOINT_COUNTERPART_MISMATCH", f"worker manifest {ordinal} differs")
    state = _safe_load_checkpoint(payload_path, row["checkpoint_payload_sha256"])
    from p7_training import state_content_digest

    required = {
        "online_model", "ema_model", "optimizer", "scheduler", "progress", "sampler",
        "rng_states", "queue", "early_stopping", "best_checkpoint", "validation_trace",
        "training_trace", "lineage", "world_size", "scaler",
    }
    if not required.issubset(state):
        _fail("MISSING_BLOCKING", f"checkpoint {ordinal} lacks required state: {sorted(required - set(state))}")
    if state_content_digest(state) != manifest["state_content_sha256"]:
        _fail("CHECKPOINT_STATE_HASH_MISMATCH", f"checkpoint {ordinal} state digest differs")
    if row["checkpoint_id"] != f"p9ck_{manifest['state_content_sha256'][:24]}":
        _fail("CHECKPOINT_IDENTITY_MISMATCH", f"checkpoint {ordinal} ID differs from state digest")
    progress = state["progress"]
    sampler = state["sampler"]
    queue = state["queue"]
    if progress != {"epoch": completed_epoch + 1, "global_update": update, "within_epoch_cursor": 0}:
        _fail("PROGRESS_STATE_MISMATCH", f"checkpoint {ordinal} progress differs")
    if sampler != {"epoch": completed_epoch + 1, "cursor": 0}:
        _fail("SAMPLER_MISMATCH", f"checkpoint {ordinal} sampler differs")
    if int(state["world_size"]) != 2 or len(state["rng_states"]) != 2:
        _fail("RNG_STATE_MISMATCH", f"checkpoint {ordinal} rank RNG/world-size differs")
    if state["scaler"] is not None or authority["training_contract"]["amp"] is not False:
        _fail("SCALER_STATE_MISMATCH", f"checkpoint {ordinal} AMP non-applicability differs")
    expected_enqueue = update * int(authority["training_contract"]["global_batch_size"]) * 2
    expected_count = min(8192, expected_enqueue)
    expected_pointer = expected_enqueue % 8192
    if (int(queue["enqueue_count"]), int(queue["valid_count"]), int(queue["pointer"])) != (
        expected_enqueue, expected_count, expected_pointer
    ):
        _fail("QUEUE_ARITHMETIC_MISMATCH", f"checkpoint {ordinal} queue arithmetic differs")
    if len(state["training_trace"]) != update or len(state["validation_trace"]) != ordinal:
        _fail("TRACE_LENGTH_MISMATCH", f"checkpoint {ordinal} trace lengths differ")
    if state["validation_trace"] != list(validation_trace[:ordinal]):
        _fail("VALIDATION_TRACE_MISMATCH", f"checkpoint {ordinal} validation trace differs")
    if state["lineage"] != manifest["lineage"]:
        _fail("LINEAGE_MISMATCH", f"checkpoint {ordinal} lineage differs")
    if manifest["lineage"] != {
        "authority_id": sources.authority_id,
        "cache_acceptance_id": authority["parents"]["production_cache_acceptance_id"],
        "reservation_id": sources.reservation_id,
        "runtime_tree_sha256": authority["execution_contract"]["runtime_tree_sha256"],
    }:
        _fail("LINEAGE_MISMATCH", f"checkpoint {ordinal} expected lineage differs")
    validation = row["validation"]
    if any(validation[key] != 0 for key in ("duplicate_count", "missing_count", "evaluation_queries_consumed")):
        _fail("VALIDATION_EVIDENCE_INVALID", f"checkpoint {ordinal} validation counters differ")
    if (validation["query_count"], validation["gallery_count"]) != (800, 400):
        _fail("VALIDATION_EVIDENCE_INVALID", f"checkpoint {ordinal} validation population differs")
    return {
        "ordinal": ordinal,
        "completed_epoch": completed_epoch,
        "resume_epoch": completed_epoch + 1,
        "optimizer_update": update,
        "validation": dict(validation),
        "validation_id": f"p9val_{canonical_sha256({'run_id': sources.run_id, 'validation': validation})[:24]}",
        "checkpoint_id": row["checkpoint_id"],
        "checkpoint_payload_sha256": row["checkpoint_payload_sha256"],
        "checkpoint_manifest_sha256": row["checkpoint_manifest_sha256"],
        "payload_relative_path": payload_path.relative_to(sources.attempt_root).as_posix(),
        "manifest_relative_path": manifest_path.relative_to(sources.attempt_root).as_posix(),
        "state_content_sha256": manifest["state_content_sha256"],
        "state_presence": {
            "online_model": bool(state["online_model"]),
            "ema_model": bool(state["ema_model"]),
            "optimizer": bool(state["optimizer"]),
            "scheduler": bool(state["scheduler"]),
            "rng_states": len(state["rng_states"]) == 2,
            "queue": all(key in queue for key in ("values", "centers", "scene_ids", "valid_count", "pointer", "enqueue_count")),
            "sampler": True,
            "early_stopping": "events_without_improvement" in state["early_stopping"],
            "best_checkpoint": bool(state["best_checkpoint"]),
            "validation_trace": len(state["validation_trace"]) == ordinal,
        },
        "queue": {
            "count": int(queue["valid_count"]),
            "pointer": int(queue["pointer"]),
            "enqueue_count": int(queue["enqueue_count"]),
        },
        "sampler": {"epoch": int(sampler["epoch"]), "cursor": int(sampler["cursor"])},
        "rng_rank_count": len(state["rng_states"]),
        "scaler_status": "NOT_APPLICABLE",
        "early_stopping_count": int(state["early_stopping"]["events_without_improvement"]),
        "stored_best": dict(state["best_checkpoint"]),
        "validation_trace_count": len(state["validation_trace"]),
        "training_trace_count": len(state["training_trace"]),
        "world_size": int(state["world_size"]),
    }


def inspect_legacy_run(
    sources: LegacyRunSources | None = None, *, reverse_discovery: bool = False
) -> LegacyInspection:
    """Hash-gate and inspect all immutable historical pairs without mutation."""

    sources = historical_p9_sources() if sources is None else sources
    authority_path = sources.authority_root / "formal_training_authority.json"
    reservation_path = sources.authority_root / "cfg_main_attempt_reservation.json"
    root_inventory_path = sources.authority_root / "immutable_root_inventory.json"
    attempt_state_path = sources.attempt_root / "attempt_state.json"
    terminal_path = sources.attempt_root / "terminal_failure.json"
    worker_result_path = sources.attempt_root / "worker_result.json"
    worker_progress_path = sources.attempt_root / "worker_progress.json"
    authority = _read_json(authority_path)
    reservation = _read_json(reservation_path)
    root_inventory = _read_json(root_inventory_path)
    terminal = _read_json(terminal_path)
    attempt_state = _read_json(attempt_state_path)
    worker_result = _read_json(worker_result_path)
    join_audit = _read_json(sources.join_audit_path)
    if authority.get("schema_version") != "1.0.0" or join_audit.get("schema_version") != "1.0.0":
        _fail("UNSUPPORTED_HISTORICAL_SCHEMA", "authority or join-audit schema is unsupported")
    expected_identity = (sources.authority_id, sources.reservation_id, sources.attempt_id, sources.run_id)
    observed_identity = (authority.get("authority_id"), reservation.get("reservation_id"), terminal.get("attempt_id"), terminal.get("run_id"))
    if observed_identity != expected_identity:
        _fail("HISTORICAL_IDENTITY_MISMATCH", "explicit historical identities differ")
    if attempt_state != terminal or terminal.get("state") != "FAILED_NONRESUMABLE":
        _fail("TERMINAL_STATE_MISMATCH", "historical terminal evidence differs")
    if terminal.get("evaluation_queries_consumed") != 0 or worker_result.get("evaluation_queries_consumed") != 0:
        _fail("EVALUATION_CONSUMPTION_NONZERO", "historical evaluation consumption is nonzero")
    rows = list(join_audit.get("rows", []))
    validations = list(worker_result.get("validation_trace", []))
    worker_manifest_list = list(worker_result.get("checkpoint_manifests", []))
    if reverse_discovery:
        rows.reverse()
        validations.reverse()
        worker_manifest_list.reverse()
    rows.sort(key=lambda row: (row.get("validation_epoch", -1), row.get("checkpoint_id", "")))
    validations.sort(key=lambda row: row.get("epoch", -1))
    worker_manifest_list.sort(key=lambda row: (row.get("global_update", -1), row.get("checkpoint_id", "")))
    if len(rows) != EXPECTED_PAIR_COUNT or len(validations) != EXPECTED_PAIR_COUNT or len(worker_manifest_list) != EXPECTED_PAIR_COUNT:
        _fail("PAIR_COUNT_MISMATCH", "historical source does not contain 25/25/25 records")
    checkpoint_ids = [row.get("checkpoint_id") for row in rows]
    validation_epochs = [row.get("validation_epoch") for row in rows]
    if len(set(checkpoint_ids)) != EXPECTED_PAIR_COUNT:
        _fail("DUPLICATE_CHECKPOINT_ID", "checkpoint identities are duplicated")
    if len(set(validation_epochs)) != EXPECTED_PAIR_COUNT:
        _fail("DUPLICATE_VALIDATION_COUNTERPART", "validation epochs are duplicated")
    worker_manifests = {item.get("checkpoint_id"): item for item in worker_manifest_list}
    if len(worker_manifests) != EXPECTED_PAIR_COUNT:
        _fail("DUPLICATE_CHECKPOINT_ID", "worker checkpoint identities are duplicated")
    pairs = tuple(
        _inspect_pair(row, ordinal, validations, worker_manifests, authority, sources)
        for ordinal, row in enumerate(rows, 1)
    )
    selected = next((pair for pair in pairs if pair["checkpoint_id"] == EXPECTED_SELECTED_CHECKPOINT), None)
    if selected is None or selected["completed_epoch"] != 105:
        _fail("SELECTED_CHECKPOINT_MISMATCH", "audited epoch-105 checkpoint is absent")
    if selected["checkpoint_payload_sha256"] != EXPECTED_SELECTED_PAYLOAD_SHA256 or selected["checkpoint_manifest_sha256"] != EXPECTED_SELECTED_MANIFEST_SHA256:
        _fail("SELECTED_CHECKPOINT_MISMATCH", "selected checkpoint hashes differ")
    source_paths: list[tuple[Path, str]] = [
        (authority_path, "legacy_authority"),
        (reservation_path, "legacy_reservation_provenance"),
        (root_inventory_path, "accepted_parent_inventory"),
        (attempt_state_path, "legacy_terminal_state"),
        (terminal_path, "legacy_terminal_state"),
        (worker_result_path, "legacy_training_and_validation_trace"),
        (worker_progress_path, "legacy_progress_diagnostic"),
        (sources.join_audit_path, "legacy_validation_checkpoint_join"),
    ]
    for pair in pairs:
        source_paths.extend((
            (sources.attempt_root / pair["payload_relative_path"], "legacy_checkpoint_payload"),
            (sources.attempt_root / pair["manifest_relative_path"], "legacy_checkpoint_manifest"),
        ))
    entries = [_source_entry(path, role, sources) for path, role in source_paths]
    entries.sort(key=lambda entry: entry["logical_path"])
    if len({entry["logical_path"] for entry in entries}) != len(entries):
        _fail("AMBIGUOUS_SOURCE_MAPPING", "logical source paths are duplicated")
    source_inventory = tuple(entries)
    source_digest = canonical_sha256(list(source_inventory))
    imported_run_id = f"p9runv2_{canonical_sha256({'importer': IMPORTER_VERSION, 'v1_run_id': sources.run_id, 'source_inventory_digest': source_digest})[:24]}"
    classifications = _field_classifications()
    counts = Counter(item["classification"] for item in classifications)
    classification_counts = {name: counts.get(name, 0) for name in CLASSIFICATIONS}
    roots = {item["name"]: item for item in root_inventory["roots"]}
    parent_identities = {
        name: item["expected_identity"] or f"sha256:{item['sha256']}"
        for name, item in sorted(roots.items())
    }
    parent_hashes = {name: item["sha256"] for name, item in sorted(roots.items())}
    configuration = make_bound_document(
        f"p9cfglegacy_{canonical_sha256({'training': authority['training_contract'], 'validation': authority['validation_contract']})[:24]}",
        {"training_contract": authority["training_contract"], "validation_contract": authority["validation_contract"], "configuration_id": "cfg_main"},
    )
    runtime = make_bound_document(
        f"p9runtimelegacy_{authority['execution_contract']['runtime_tree_sha256'][:24]}",
        {"runtime_tree_sha256": authority["execution_contract"]["runtime_tree_sha256"], "actual_launch_commit": terminal["actual_launch_commit"]},
    )
    parents = make_bound_document(
        f"p9parentslegacy_{canonical_sha256(parent_hashes)[:24]}",
        {"identities": parent_identities, "hashes": parent_hashes},
    )
    cache = make_bound_document(
        authority["parents"]["production_cache_acceptance_id"],
        {"cache_id": authority["parents"]["production_cache_id"], "root_inventory_id": f"p9root_{root_inventory['content_sha256'][:24]}", "inventory_sha256": root_inventory["content_sha256"]},
    )
    sampler = make_bound_document(
        f"p9samplerlegacy_{authority['sampler_contract']['sha256'][:24]}",
        {**authority["sampler_contract"], "global_batch": 32, "per_rank_batch": 16, "world_size": 2, "uniqueness": "strict_corrected_global_batch"},
    )
    selection = make_selection_contract()
    authority_content = {
        "run_id": imported_run_id,
        "scientific_configuration_id": configuration["identity"],
        "scientific_configuration_hash": configuration["content_sha256"],
        "source_parents_id": parents["identity"],
        "source_parents_hash": parents["content_sha256"],
        "cache_acceptance_id": cache["identity"],
        "cache_acceptance_hash": cache["content_sha256"],
        "sampler_contract_id": sampler["identity"],
        "sampler_contract_hash": sampler["content_sha256"],
        "selection_contract_id": selection["identity"],
        "selection_contract_hash": selection["content_sha256"],
    }
    dry_authority = make_bound_document(
        f"p9authdry_{canonical_sha256({'source_authority': sources.authority_id, 'run_id': imported_run_id, 'source_inventory_digest': source_digest})[:24]}",
        authority_content,
    )
    annotation = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "p9_v2_legacy_import_annotation",
        "status": "NONCANONICAL_DRY_RUN",
        "canonical_publication_eligible": False,
        "acceptance_eligible": False,
        "importer_version": IMPORTER_VERSION,
        "imported_run_id": imported_run_id,
        "source_inventory_digest": source_digest,
        "source": {
            "v1_run_id": sources.run_id,
            "v1_authority_id": sources.authority_id,
            "v1_reservation_id": sources.reservation_id,
            "v1_attempt_id": sources.attempt_id,
            "v1_terminal_state": terminal["state"],
            "join_audit_sha256": _file_sha256(sources.join_audit_path),
        },
        "event_mapping": {
            "rule_id": "p9-v1-formal-to-v2-events-v1",
            "source_order": "completed_epoch_ascending",
            "timestamp_rule": "source_started_unix_plus_event_sequence_microseconds",
            "legacy_import": True,
        },
        "atomic_completion": {
            "classification": "AVAILABLE_WITH_LEGACY_ANNOTATION",
            "protocol": "legacy_atomic_payload_manifest_pair",
            "evidence": "hash_verified_payload_then_manifest_pairs",
        },
        "field_classifications": list(classifications),
        "classification_counts": classification_counts,
    }
    validate_instance("legacy_import", annotation)
    inspection = LegacyInspection(
        sources=sources, imported_run_id=imported_run_id, pairs=pairs,
        source_inventory=source_inventory, source_inventory_digest=source_digest,
        field_classifications=classifications, classification_counts=classification_counts,
        legacy_annotation=annotation,
        documents={
            "authority": dry_authority, "scientific_configuration": configuration,
            "runtime": runtime, "source_parents": parents, "cache_acceptance": cache,
            "sampler_contract": sampler, "selection_contract": selection,
        },
        terminal_state=terminal,
    )
    validation = validate_legacy_import(inspection)
    if not validation.valid:
        _fail("LEGACY_IMPORT_INVALID", "; ".join(validation.errors))
    return inspection


def validate_legacy_import(inspection: LegacyInspection) -> LegacyImportValidation:
    errors: list[str] = []
    pairs = list(inspection.pairs)
    source_hashes = {
        item.get("logical_path"): item.get("content_sha256")
        for item in inspection.source_inventory
    }
    if len(source_hashes) != len(inspection.source_inventory):
        errors.append("AMBIGUOUS_SOURCE_MAPPING")
    if list(inspection.source_inventory) != sorted(
        inspection.source_inventory, key=lambda item: item.get("logical_path", "")
    ):
        errors.append("SOURCE_INVENTORY_MISMATCH")
    if canonical_sha256(list(inspection.source_inventory)) != inspection.source_inventory_digest:
        errors.append("SOURCE_INVENTORY_MISMATCH")
    expected_run_id = "p9runv2_" + canonical_sha256({
        "importer": IMPORTER_VERSION,
        "v1_run_id": inspection.sources.run_id,
        "source_inventory_digest": inspection.source_inventory_digest,
    })[:24]
    if inspection.imported_run_id != expected_run_id:
        errors.append("HISTORICAL_IDENTITY_MISMATCH")
    if inspection.legacy_annotation.get("source_inventory_digest") != inspection.source_inventory_digest:
        errors.append("LEGACY_ANNOTATION_INVALID")
    if len(pairs) != EXPECTED_PAIR_COUNT:
        errors.append("PAIR_COUNT_MISMATCH")
    if len({pair.get("checkpoint_id") for pair in pairs}) != len(pairs):
        errors.append("DUPLICATE_CHECKPOINT_ID")
    if len({pair.get("validation_id") for pair in pairs}) != len(pairs):
        errors.append("DUPLICATE_VALIDATION_COUNTERPART")
    best: dict[str, Any] | None = None
    count = 0
    selected_id: str | None = None
    selected_epoch: int | None = None
    for ordinal, pair in enumerate(pairs, 1):
        expected_epoch = ordinal * 5
        expected_update = expected_epoch * 76
        if pair.get("completed_epoch") != expected_epoch:
            errors.append("EPOCH_MISMATCH")
        if pair.get("resume_epoch") != expected_epoch + 1:
            errors.append("RESUME_EPOCH_MISMATCH")
        if pair.get("optimizer_update") != expected_update:
            errors.append("OPTIMIZER_UPDATE_MISMATCH")
        payload_hash = pair.get("checkpoint_payload_sha256")
        manifest_hash = pair.get("checkpoint_manifest_sha256")
        if not isinstance(payload_hash, str) or re.fullmatch(r"[0-9a-f]{64}", payload_hash) is None:
            errors.append("PAYLOAD_HASH_MISMATCH")
        if not isinstance(manifest_hash, str) or re.fullmatch(r"[0-9a-f]{64}", manifest_hash) is None:
            errors.append("MANIFEST_HASH_MISMATCH")
        if source_hashes.get(f"attempt/{pair.get('payload_relative_path')}") != payload_hash:
            errors.append("PAYLOAD_HASH_MISMATCH")
        if source_hashes.get(f"attempt/{pair.get('manifest_relative_path')}") != manifest_hash:
            errors.append("MANIFEST_HASH_MISMATCH")
        validation = pair.get("validation", {})
        expected_validation_id = f"p9val_{canonical_sha256({'run_id': inspection.sources.run_id, 'validation': validation})[:24]}"
        if pair.get("validation_id") != expected_validation_id:
            errors.append("VALIDATION_COUNTERPART_MISMATCH")
        queue = pair.get("queue", {})
        expected_enqueue = expected_update * 64
        if (queue.get("enqueue_count"), queue.get("count"), queue.get("pointer")) != (
            expected_enqueue, min(8192, expected_enqueue), expected_enqueue % 8192
        ):
            errors.append("QUEUE_ARITHMETIC_MISMATCH")
        if pair.get("sampler") != {"epoch": expected_epoch + 1, "cursor": 0}:
            errors.append("SAMPLER_MISMATCH")
        if pair.get("rng_rank_count") != 2 or pair.get("world_size") != 2:
            errors.append("RNG_STATE_MISMATCH")
        if not all(pair.get("state_presence", {}).values()):
            errors.append("MISSING_BLOCKING")
        candidate = {
            "checkpoint_id": pair.get("checkpoint_id"),
            "completed_epoch": pair.get("completed_epoch"),
            "validation_retrieval_loss": validation.get("validation_retrieval_loss"),
            "mean_source_separation_margin": validation.get("mean_source_separation_margin"),
        }
        try:
            previous_best = best
            selected, _ = evaluate_selection_candidate(candidate, previous_best, 0.0001)
            resets_patience = qualifies_patience_reset(candidate, previous_best, 0.0001)
        except (KeyError, TypeError, ValueError):
            errors.append("SELECTOR_TRACE_MISMATCH")
            continue
        if selected:
            best = candidate
        if resets_patience:
            count = 0
        else:
            count += 1
        stored_best = pair.get("stored_best", {})
        if best is None or (
            stored_best.get("epoch") != best["completed_epoch"]
            or stored_best.get("validation_retrieval_loss") != best["validation_retrieval_loss"]
            or stored_best.get("mean_source_separation_margin") != best["mean_source_separation_margin"]
        ):
            errors.append("SELECTOR_TRACE_MISMATCH")
        if pair.get("early_stopping_count") != count:
            errors.append("SELECTOR_TRACE_MISMATCH")
    if best is not None:
        selected_id = best["checkpoint_id"]
        selected_epoch = best["completed_epoch"]
    if selected_id != EXPECTED_SELECTED_CHECKPOINT or selected_epoch != 105:
        errors.append("SELECTED_CHECKPOINT_MISMATCH")
    if not pairs or pairs[-1].get("optimizer_update") != 9500 or pairs[-1].get("early_stopping_count") != 4:
        errors.append("STOPPING_BOUNDARY_MISMATCH")
    if any(pair.get("validation", {}).get("evaluation_queries_consumed") != 0 for pair in pairs):
        errors.append("EVALUATION_CONSUMPTION_NONZERO")
    if inspection.terminal_state.get("state") != "FAILED_NONRESUMABLE":
        errors.append("TERMINAL_STATE_MISMATCH")
    missing = inspection.classification_counts.get("MISSING_BLOCKING", -1)
    if missing != 0:
        errors.append("MISSING_BLOCKING")
    classification_fields = [item.get("field") for item in inspection.field_classifications]
    observed_counts = Counter(item.get("classification") for item in inspection.field_classifications)
    normalized_counts = {name: observed_counts.get(name, 0) for name in CLASSIFICATIONS}
    if len(classification_fields) != len(set(classification_fields)):
        errors.append("AMBIGUOUS_SOURCE_MAPPING")
    if normalized_counts != inspection.classification_counts:
        errors.append("LEGACY_ANNOTATION_INVALID")
    if inspection.legacy_annotation.get("classification_counts") != inspection.classification_counts:
        errors.append("LEGACY_ANNOTATION_INVALID")
    if inspection.terminal_state.get("evaluation_queries_consumed") != 0:
        errors.append("EVALUATION_CONSUMPTION_NONZERO")
    try:
        validate_instance("legacy_import", inspection.legacy_annotation)
    except Exception:
        errors.append("LEGACY_ANNOTATION_INVALID")
    errors = sorted(set(errors))
    return LegacyImportValidation(
        valid=not errors,
        migration_verdict="MIGRATION_DRY_RUN_ELIGIBLE" if not errors else "MIGRATION_DRY_RUN_BLOCKED",
        pair_count=len(pairs), missing_blocking=max(missing, 0),
        selected_checkpoint_id=selected_id, selected_epoch=selected_epoch,
        errors=tuple(errors),
    )


def _event_time(base: datetime, sequence: int) -> str:
    value = base + timedelta(microseconds=sequence)
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def map_legacy_run_to_v2(inspection: LegacyInspection, ledger_root: str | Path) -> LegacyMapping:
    """Map inspected evidence through the canonical V2-A writer and replay."""

    validation = validate_legacy_import(inspection)
    if not validation.valid:
        _fail("LEGACY_IMPORT_INVALID", "; ".join(validation.errors))
    root = Path(ledger_root)
    base = datetime.fromtimestamp(float(inspection.terminal_state["started_unix"]), tz=UTC)
    writer = LedgerWriter.initialize(root, run_id=inspection.imported_run_id, created_at=_event_time(base, 0))
    sequence = 0
    def append(event_type: str, payload: dict[str, Any]) -> None:
        nonlocal sequence
        sequence += 1
        writer.append(
            event_type=event_type, occurred_at=_event_time(base, sequence),
            writer_id=f"{IMPORTER_VERSION}:{inspection.sources.run_id}",
            writer_role="legacy_importer", payload=payload, legacy_import=True,
        )
    docs = inspection.documents
    append("RUN_AUTHORIZED", {
        "authority_hash": docs["authority"]["content_sha256"],
        "scientific_configuration_hash": docs["scientific_configuration"]["content_sha256"],
        "parent_identities": docs["source_parents"]["content"]["identities"],
        "duplicate_run_key": inspection.terminal_state["duplicate_key"],
    })
    append("RUN_STARTING", {
        "owner_id": f"noncanonical-dry-run:{inspection.sources.attempt_id}",
        "execution_environment_digest": docs["runtime"]["content_sha256"],
        "training_lock_key": canonical_sha256({"noncanonical": True, "v1_run_id": inspection.sources.run_id}),
    })
    append("RUN_STARTED", {
        "process_id": f"legacy-evidence:{inspection.sources.attempt_id}",
        "world_size": 2,
        "runtime_digest": docs["runtime"]["content_sha256"],
    })
    best: dict[str, Any] | None = None
    non_improvements = 0
    previous_update = 0
    locator_map: dict[str, dict[str, dict[str, Any]]] = {}
    for pair in inspection.pairs:
        candidate = {
            "checkpoint_id": pair["checkpoint_id"],
            "completed_epoch": pair["completed_epoch"],
            "validation_retrieval_loss": pair["validation"]["validation_retrieval_loss"],
            "mean_source_separation_margin": pair["validation"]["mean_source_separation_margin"],
        }
        previous_best = best
        selected, basis = evaluate_selection_candidate(candidate, previous_best, 0.0001)
        resets_patience = qualifies_patience_reset(candidate, previous_best, 0.0001)
        if selected:
            best = candidate
        if resets_patience:
            non_improvements = 0
        else:
            non_improvements += 1
        assert best is not None
        append("EPOCH_STARTED", {
            "epoch": 1 if pair["ordinal"] == 1 else inspection.pairs[pair["ordinal"] - 2]["completed_epoch"] + 1,
            "starting_optimizer_update": previous_update,
            "sampler_cursor": 0,
        })
        append("PROGRESS_SUMMARY_COMMITTED", {
            "first_update": previous_update + 1,
            "last_update": pair["optimizer_update"],
            "ending_epoch": pair["completed_epoch"],
            "ending_sampler_cursor": 0,
            "trace_block_sha256": canonical_sha256({"state_content_sha256": pair["state_content_sha256"], "trace": "training"}),
            "sampler_state_sha256": canonical_sha256({"state_content_sha256": pair["state_content_sha256"], "sampler": pair["sampler"]}),
            "rng_state_sha256": canonical_sha256({"state_content_sha256": pair["state_content_sha256"], "rng_rank_count": 2}),
            "queue_state_sha256": canonical_sha256({"state_content_sha256": pair["state_content_sha256"], "queue": pair["queue"]}),
        })
        append("VALIDATION_CHECKPOINT_COMMITTED", {
            "completed_epoch": pair["completed_epoch"],
            "resume_epoch": pair["resume_epoch"],
            "optimizer_update": pair["optimizer_update"],
            "validation_id": pair["validation_id"],
            "checkpoint_id": pair["checkpoint_id"],
            "checkpoint_payload_sha256": pair["checkpoint_payload_sha256"],
            "checkpoint_manifest_sha256": pair["checkpoint_manifest_sha256"],
            "validation_retrieval_loss": pair["validation"]["validation_retrieval_loss"],
            "mean_source_separation_margin": pair["validation"]["mean_source_separation_margin"],
            "selector_state": {"best_checkpoint_id": best["checkpoint_id"], "events_without_improvement": non_improvements},
            "queue": {
                **pair["queue"],
                "state_sha256": canonical_sha256({"state_content_sha256": pair["state_content_sha256"], "queue": pair["queue"]}),
            },
            "sampler": {
                **pair["sampler"],
                "state_sha256": canonical_sha256({"state_content_sha256": pair["state_content_sha256"], "sampler": pair["sampler"]}),
            },
            "state_presence": pair["state_presence"],
            "atomic_completion_marker": {"protocol": "legacy_atomic_payload_manifest_pair", "status": "COMPLETE"},
            "source_run_id": inspection.sources.run_id,
        })
        append("EARLY_STOPPING_UPDATED", {
            "selector_state": {"primary": "validation_retrieval_loss", "legacy_source_checkpoint_id": pair["checkpoint_id"]},
            "best_checkpoint_id": best["checkpoint_id"],
            "events_without_improvement": non_improvements,
            "decision_basis": basis,
        })
        payload_path = inspection.sources.attempt_root / pair["payload_relative_path"]
        manifest_path = inspection.sources.attempt_root / pair["manifest_relative_path"]
        payload_locator = make_filesystem_locator(
            namespace=LEGACY_NAMESPACE, relative_path=pair["payload_relative_path"],
            physical_path=payload_path, role="checkpoint_payload", media_type="application/x-pytorch",
            associated_manifest_sha256=pair["checkpoint_manifest_sha256"],
        )
        manifest_locator = make_filesystem_locator(
            namespace=LEGACY_NAMESPACE, relative_path=pair["manifest_relative_path"],
            physical_path=manifest_path, role="checkpoint_manifest", media_type="application/json",
        )
        locator_map[pair["checkpoint_id"]] = {"payload": payload_locator, "manifest": manifest_locator}
        previous_update = pair["optimizer_update"]
    final = inspection.pairs[-1]
    append("TRAINING_COMPLETED", {
        "completed_epoch": final["completed_epoch"], "resume_epoch": final["resume_epoch"],
        "optimizer_update": final["optimizer_update"], "reason": "LEGACY_EARLY_STOPPING_PATIENCE_RECONSTRUCTED",
    })
    append("FINALIZATION_STARTED", {
        "run_bundle_hash": inspection.legacy_annotation["source"]["join_audit_sha256"],
        "selection_contract_hash": docs["selection_contract"]["content_sha256"],
    })
    append("FINALIZATION_FAILED", {
        "failure_code": "V1_POST_TRAINING_VALIDATION_CHECKPOINT_LINKAGE",
        "evidence_class": "OPERATIONAL_FAILURE",
    })
    writer.close()
    committed = read_ledger(root)
    replay = replay_events(committed.events)
    inputs = RunBundleInputs(
        authority=docs["authority"], scientific_configuration=docs["scientific_configuration"],
        runtime=docs["runtime"], source_parents=docs["source_parents"],
        cache_acceptance=docs["cache_acceptance"], sampler_contract=docs["sampler_contract"],
        selection_contract=docs["selection_contract"], source_inventory=inspection.source_inventory,
        checkpoint_locators=locator_map,
        diagnostic_incidents=({
            "incident_id": f"legacy-v1-terminal-{inspection.sources.run_id}",
            "incident_type": "LEGACY_V1_TERMINAL_STATE",
            "evidence": {"state": "FAILED_NONRESUMABLE", "interpretation": "FINALIZATION_FAILED"},
        },),
        evaluation_consumption_count=0, legacy_import=inspection.legacy_annotation,
    )
    return LegacyMapping(root, replay, inputs, {LEGACY_NAMESPACE: inspection.sources.attempt_root})


def build_legacy_dry_run_bundle(
    inspection: LegacyInspection, output_root: str | Path
) -> LegacyDryRun:
    """Build only below a visibly noncanonical V2-D root and finalize in memory."""

    root = Path(output_root) / "v2_d_noncanonical_dry_run" / "ineligible_for_acceptance"
    mapping = map_legacy_run_to_v2(inspection, root / "ledger")
    candidate = build_run_bundle(mapping.ledger_root, mapping.inputs, mapping.locator_roots)
    publication = publish_run_bundle(candidate, root / "bundles", mapping.locator_roots)
    validation = validate_run_bundle(publication.path, mapping.locator_roots)
    finalization = finalize_run_bundle(publication.path, mapping.locator_roots)
    return LegacyDryRun(
        inspection=inspection, mapping=mapping, bundle_path=publication.path,
        bundle_id=candidate.bundle_id, bundle_hash=candidate.bundle_content_sha256,
        bundle_validation=validation, finalization_result=finalization,
    )
