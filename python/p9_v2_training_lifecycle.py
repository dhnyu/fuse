"""Executable native-training handoff into the existing V2-B/C/E chain."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from p9_v2_acceptance import publish_acceptance, validate_acceptance
from p9_v2_bundle import (
    RunBundleInputs, build_run_bundle, make_bound_document, make_filesystem_locator,
    publish_run_bundle, validate_run_bundle,
)
from p9_v2_canonical import canonical_json_bytes, canonical_sha256, sha256_file
from p9_v2_downstream import (
    AcceptedCheckpointResolver, load_acceptance_eligibility, make_acceptance_eligibility,
    publish_acceptance_eligibility,
)
from p9_v2_finalization import (
    finalize_run_bundle, make_selection_contract, validate_finalization_result,
)
from p9_v2_ledger import fsync_directory, read_ledger, write_all
from p9_v2_training_controller import validate_training_authority


class TrainingLifecycleError(RuntimeError):
    """Native V2 training evidence cannot advance to the next immutable stage."""


SCIENTIFIC_KEYS = (
    "configuration_family", "configuration_id", "scientific", "bank_binding",
    "validation_acceptance_id", "run_seed_namespace", "run_seed_formula",
    "parent_p7_acceptance_id", "runtime_acceptance_id",
)


def scientific_configuration_content(row: Mapping[str, Any]) -> dict[str, Any]:
    return {key: row[key] for key in SCIENTIFIC_KEYS}


def _source_inventory(paths: Sequence[str | Path]) -> tuple[dict[str, Any], ...]:
    root = Path(__file__).resolve().parents[1]
    rows = []
    for value in sorted({Path(path).resolve() for path in paths}, key=str):
        if not value.is_file(): raise TrainingLifecycleError(f"SOURCE_FILE_MISSING: {value}")
        try: logical = value.relative_to(root).as_posix()
        except ValueError: logical = "external/" + canonical_sha256({"path": value.name, "sha256": sha256_file(value)})[:24] + "/" + value.name
        rows.append({"logical_path": logical, "role": "scientific_source", "content_sha256": sha256_file(value)})
    return tuple(rows)


def native_bundle_inputs(
    authority: Mapping[str, Any], matrix_path: str | Path, cache_acceptance_path: str | Path,
    checkpoint_root: str | Path, ledger_root: str | Path, source_paths: Sequence[str | Path],
) -> tuple[RunBundleInputs, dict[str, Path]]:
    """Bind a closed native ledger and controller-published checkpoints to V2-B."""
    authority = dict(authority); validate_training_authority(authority)
    matrix = json.loads(Path(matrix_path).read_text(encoding="utf-8"))
    row = next((item for item in matrix["rows"]
                if item["configuration_id"] == authority["content"]["scientific"]["configuration_id"]), None)
    if row is None: raise TrainingLifecycleError("CONFIGURATION_NOT_IN_P8_MATRIX")
    scientific_content = scientific_configuration_content(row)
    scientific = make_bound_document(row["configuration_id"], scientific_content)
    if scientific["content_sha256"] != authority["content"]["scientific"]["configuration_hash"]:
        raise TrainingLifecycleError("V2_SCIENTIFIC_CONFIGURATION_HASH_MISMATCH")
    if row["scientific_hash"] != authority["content"]["scientific"]["p8_configuration_hash"]:
        raise TrainingLifecycleError("P8_SCIENTIFIC_CONFIGURATION_HASH_MISMATCH")
    cache_raw = json.loads(Path(cache_acceptance_path).read_text(encoding="utf-8"))
    cache = make_bound_document(cache_raw["acceptance_id"], cache_raw)
    source_parents = make_bound_document("p9parents_" + authority["content"]["scientific_run_key"][:24], {
        "identities": authority["content"]["parents"], "hashes": authority["content"]["parent_hashes"]})
    runtime = make_bound_document("p9runtime_" + authority["content_sha256"][:24], authority["content"])
    sampler = make_bound_document("p9sampler_rotating_padding_v2", {
        "policy": "deterministic_epoch_rotating_padding", "training_scenes": 2421,
        "padded_scenes_per_epoch": 2432, "padding_scenes_per_epoch": 11,
        "global_batch": 32, "per_rank_batch": 16, "world_size": 2,
        "updates_per_epoch": 76, "resume_cursor_contract": "completed_validation_epoch_plus_one_cursor_zero"})
    selection = make_selection_contract()
    committed = read_ledger(ledger_root)
    checkpoint_root = Path(checkpoint_root)
    namespace = "p9-v2-native-" + committed.header["run_id"]
    locator_roots = {namespace: checkpoint_root}
    locators: dict[str, dict[str, dict[str, Any]]] = {}
    for event in committed.events:
        if event["event_type"] != "VALIDATION_CHECKPOINT_COMMITTED": continue
        checkpoint_id = event["payload"]["checkpoint_id"]
        root = checkpoint_root / checkpoint_id
        manifest_path = root / "checkpoint_manifest.json"
        manifest_hash = sha256_file(manifest_path)
        locators[checkpoint_id] = {
            "manifest": make_filesystem_locator(namespace=namespace,
                relative_path=f"{checkpoint_id}/checkpoint_manifest.json", physical_path=manifest_path,
                role="checkpoint_manifest", media_type="application/json"),
            "payload": make_filesystem_locator(namespace=namespace,
                relative_path=f"{checkpoint_id}/checkpoint.pt", physical_path=root / "checkpoint.pt",
                role="checkpoint_payload", media_type="application/x-pytorch",
                associated_manifest_sha256=manifest_hash),
        }
    inputs = RunBundleInputs(
        authority=authority, scientific_configuration=scientific, runtime=runtime,
        source_parents=source_parents, cache_acceptance=cache, sampler_contract=sampler,
        selection_contract=selection, source_inventory=_source_inventory(source_paths),
        checkpoint_locators=locators, evaluation_consumption_count=0,
    )
    return inputs, locator_roots


def build_publish_native_bundle(
    authority: Mapping[str, Any], ledger_root: str | Path, checkpoint_root: str | Path,
    matrix_path: str | Path, cache_acceptance_path: str | Path,
    publication_root: str | Path, source_paths: Sequence[str | Path],
) -> tuple[Any, dict[str, Path]]:
    inputs, locator_roots = native_bundle_inputs(
        authority, matrix_path, cache_acceptance_path, checkpoint_root, ledger_root, source_paths)
    candidate = build_run_bundle(ledger_root, inputs, locator_roots)
    publication = publish_run_bundle(candidate, Path(publication_root) / "bundles", locator_roots)
    validated = validate_run_bundle(publication.path, locator_roots)
    if not validated.valid or validated.completeness != "SCIENTIFICALLY_COMPLETE":
        raise TrainingLifecycleError(f"NATIVE_BUNDLE_INVALID: {validated.errors}")
    return publication, locator_roots


def _publish_result(result: Mapping[str, Any], root: str | Path) -> Path:
    root = Path(root) / result["finalization_id"]; root.mkdir(parents=True, exist_ok=True)
    path = root / "finalization_result.json"; raw = canonical_json_bytes(dict(result))
    if path.exists():
        if path.read_bytes() != raw: raise TrainingLifecycleError("FINALIZATION_PUBLICATION_COLLISION")
        return path
    temporary = root / ".finalization_result.json.incomplete"
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o640)
    try: write_all(descriptor, raw); os.fsync(descriptor)
    finally: os.close(descriptor)
    os.replace(temporary, path); fsync_directory(root)
    return path


@dataclass(frozen=True)
class NativeLifecyclePublication:
    bundle_id: str
    bundle_path: Path
    finalization_id: str
    finalization_path: Path
    acceptance_id: str
    acceptance_path: Path
    eligibility_id: str
    eligibility_path: Path
    checkpoint_id: str


def publish_native_lifecycle(
    authority: Mapping[str, Any], ledger_root: str | Path, checkpoint_root: str | Path,
    matrix_path: str | Path, cache_acceptance_path: str | Path,
    publication_root: str | Path, source_paths: Sequence[str | Path], *,
    eligibility_namespace: str, existing_eligibility: str | Path | None = None,
) -> NativeLifecyclePublication:
    """Execute V2-B/C/E in order with no training or selector duplicate."""
    root = Path(publication_root)
    bundle, locator_roots = build_publish_native_bundle(
        authority, ledger_root, checkpoint_root, matrix_path, cache_acceptance_path, root, source_paths)
    finalization = finalize_run_bundle(
        bundle.path, locator_roots,
        selection_contract_hash=make_selection_contract()["content_sha256"])
    valid, reason = validate_finalization_result(finalization, bundle.path, locator_roots)
    if not valid: raise TrainingLifecycleError(f"FINALIZATION_INVALID: {reason}")
    finalization_path = _publish_result(finalization, root / "finalizations")
    acceptance = publish_acceptance(
        finalization, bundle.path, locator_roots, root / "acceptances",
        authority_id=authority["identity"], authority_hash=authority["content_sha256"])
    acceptance_valid = validate_acceptance(
        acceptance.acceptance_id, root / "acceptances", root / "bundles", locator_roots)
    if not acceptance_valid.valid: raise TrainingLifecycleError(f"ACCEPTANCE_INVALID: {acceptance_valid.error_code}")
    entries = [] if existing_eligibility is None else list(load_acceptance_eligibility(existing_eligibility)["entries"])
    entries = [entry for entry in entries if entry["acceptance_id"] != acceptance.acceptance_id]
    entries.append({"acceptance_id": acceptance.acceptance_id, "eligibility": "ELIGIBLE",
                    "authority_id": authority["identity"], "authority_hash": authority["content_sha256"]})
    eligibility = make_acceptance_eligibility(entries, namespace=eligibility_namespace)
    eligibility_path = publish_acceptance_eligibility(eligibility, root / "eligibility")
    resolver = AcceptedCheckpointResolver(root / "acceptances", root / "bundles", locator_roots,
                                          load_acceptance_eligibility(eligibility_path))
    resolved = resolver.resolve_accepted_checkpoint(acceptance.acceptance_id)
    if resolved.checkpoint_id != finalization["selected_checkpoint"]["checkpoint_id"]:
        raise TrainingLifecycleError("RESOLVER_FINALIZATION_MISMATCH")
    return NativeLifecyclePublication(
        bundle.bundle_id, bundle.path, finalization["finalization_id"], finalization_path,
        acceptance.acceptance_id, acceptance.path, eligibility["eligibility_id"], eligibility_path,
        resolved.checkpoint_id)
