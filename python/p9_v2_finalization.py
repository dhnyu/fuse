"""Pure deterministic P9 v2 checkpoint selection and finalization."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, Sequence

from p9_v2_bundle import COMMIT_PATH, validate_run_bundle
from p9_v2_canonical import (
    CanonicalJSONError,
    canonical_sha256,
    parse_canonical_json,
)
from p9_v2_ledger import LedgerError, read_ledger
from p9_v2_schema import P9V2SchemaError, SCHEMA_VERSION, validate_instance


FINALIZER_IMPLEMENTATION_VERSION = "p9-v2-finalizer-v1"
SELECTION_CONTRACT_VERSION = "p9-selection-v2.0.0"
FINALIZATION_FAILURE_CODES = frozenset({
    "BUNDLE_INVALID",
    "BUNDLE_NOT_FOUND",
    "SCIENTIFICALLY_INCOMPLETE",
    "SELECTION_CONTRACT_MISMATCH",
    "NO_ELIGIBLE_CANDIDATE",
    "SELECTOR_REPLAY_MISMATCH",
    "STOPPING_SUMMARY_MISMATCH",
    "CHECKPOINT_INVENTORY_MISMATCH",
    "SOURCE_PROVENANCE_MISMATCH",
    "UNSUPPORTED_SCHEMA_VERSION",
})


class FinalizationEvidenceError(ValueError):
    """A deterministic scientific-evidence rejection."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def selection_contract_content() -> dict[str, Any]:
    """Return the one immutable dissertation selection contract used by V2-C."""

    return {
        "contract_version": SELECTION_CONTRACT_VERSION,
        "validation_interval_epochs": 5,
        "primary_metric": "validation_retrieval_loss",
        "primary_direction": "minimize",
        "equivalence_tolerance": 0.0001,
        "equivalence_comparison": "absolute_difference_strictly_less_than_tolerance",
        "margin_metric": "mean_source_separation_margin",
        "margin_direction": "maximize",
        "final_tiebreaker": "earlier_completed_epoch",
        "early_stopping_patience": 4,
        "patience_reset": "selected_best_event_only",
        "candidate_eligibility": "VALIDATION_CHECKPOINT_COMMITTED_ONLY",
    }


def make_selection_contract() -> dict[str, Any]:
    content = selection_contract_content()
    content_hash = canonical_sha256(content)
    contract = {
        "schema_version": SCHEMA_VERSION,
        "identity": f"p9selc_{content_hash[:24]}",
        "content_sha256": content_hash,
        "content": content,
    }
    validate_instance("selection_contract", contract)
    return contract


def _read_canonical(path: Path) -> Any:
    return parse_canonical_json(path.read_bytes())


def _implementation_hash(version: str) -> str:
    return canonical_sha256({"component": "p9_v2_finalizer", "version": version})


def _seal_result(preimage: dict[str, Any]) -> dict[str, Any]:
    result_hash = canonical_sha256(preimage)
    result = {
        **preimage,
        "finalization_id": f"p9fin_{result_hash[:24]}",
        "finalization_result_hash": result_hash,
    }
    validate_instance("finalization_result", result)
    return result


def _failure_result(
    code: str,
    *,
    bundle_id: str | None,
    bundle_hash: str | None,
    selection_id: str | None,
    selection_hash: str | None,
    finalizer_version: str,
    scientific_state: str | None = None,
) -> dict[str, Any]:
    if code not in FINALIZATION_FAILURE_CODES:
        code = "BUNDLE_INVALID"
    return _seal_result({
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "p9_v2_finalization_result",
        "status": "FAILED",
        "failure_code": code,
        "evidence_class": "INVALID_SCIENTIFIC_EVIDENCE",
        "run_bundle_id": bundle_id,
        "run_bundle_hash": bundle_hash,
        "selection_contract_id": selection_id,
        "selection_contract_hash": selection_hash,
        "finalizer_implementation_version": finalizer_version,
        "finalizer_implementation_hash": _implementation_hash(finalizer_version),
        "candidate_set_hash": None,
        "selected_checkpoint": None,
        "selector_replay_summary": None,
        "stopping_summary": None,
        "scientific_state": scientific_state,
        "provenance": None,
        "evaluation_consumption_count": 0,
    })


def _validate_selection_contract(contract: Any) -> dict[str, Any]:
    try:
        validate_instance("selection_contract", contract)
    except P9V2SchemaError as error:
        raise FinalizationEvidenceError("SELECTION_CONTRACT_MISMATCH", str(error)) from error
    if canonical_sha256(contract["content"]) != contract["content_sha256"]:
        raise FinalizationEvidenceError("SELECTION_CONTRACT_MISMATCH", "content hash differs")
    if contract["identity"] != f"p9selc_{contract['content_sha256'][:24]}":
        raise FinalizationEvidenceError("SELECTION_CONTRACT_MISMATCH", "identity differs from content")
    if contract != make_selection_contract():
        raise FinalizationEvidenceError("SELECTION_CONTRACT_MISMATCH", "contract is not the active dissertation rule")
    return contract


def _binary64_decimal(value: float) -> Decimal:
    return Decimal.from_float(value)


def evaluate_selection_candidate(
    candidate: Mapping[str, Any], best: Mapping[str, Any] | None, tolerance: float
) -> tuple[bool, str]:
    """Apply the canonical V2-C candidate ordering for replay/import adapters."""
    if best is None:
        return True, "retrieval_loss_improved"
    loss = _binary64_decimal(candidate["validation_retrieval_loss"])
    best_loss = _binary64_decimal(best["validation_retrieval_loss"])
    equivalent = abs(loss - best_loss) < _binary64_decimal(tolerance)
    if not equivalent:
        return (loss < best_loss, "retrieval_loss_improved" if loss < best_loss else "retrieval_loss_not_improved")
    margin = _binary64_decimal(candidate["mean_source_separation_margin"])
    best_margin = _binary64_decimal(best["mean_source_separation_margin"])
    if margin > best_margin:
        return True, "equivalent_loss_margin_improved"
    if margin < best_margin:
        return False, "equivalent_loss_margin_not_improved"
    earlier = candidate["completed_epoch"] < best["completed_epoch"]
    return earlier, (
        "equivalent_loss_earlier_epoch_improved"
        if earlier else "equivalent_loss_earlier_epoch_retained"
    )


def _early_updates(events: Sequence[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    updates: dict[str, dict[str, Any]] = {}
    pending: str | None = None
    for event in events:
        if event["event_type"] == "VALIDATION_CHECKPOINT_COMMITTED":
            if pending is not None:
                raise FinalizationEvidenceError("SELECTOR_REPLAY_MISMATCH", "checkpoint lacks one early-stopping update")
            pending = event["payload"]["checkpoint_id"]
        elif event["event_type"] == "EARLY_STOPPING_UPDATED":
            if pending is None or pending in updates:
                raise FinalizationEvidenceError("SELECTOR_REPLAY_MISMATCH", "orphan or duplicate early-stopping update")
            updates[pending] = event["payload"]
            pending = None
        elif event["event_type"] in {"TRAINING_COMPLETED", "TRAINING_INTERRUPTED", "TRAINING_FAILED"} and pending is not None:
            raise FinalizationEvidenceError("SELECTOR_REPLAY_MISMATCH", "terminal event precedes early-stopping update")
    if pending is not None:
        raise FinalizationEvidenceError("SELECTOR_REPLAY_MISMATCH", "final checkpoint lacks early-stopping update")
    return updates


def _selector_candidates(root: Path) -> list[dict[str, Any]]:
    candidates_document = _read_canonical(root / "events/validation_checkpoint_events.json")
    checkpoint_document = _read_canonical(root / "checkpoints/checkpoint_inventory.json")
    candidates = candidates_document["events"]
    records = checkpoint_document["checkpoints"]
    by_id = {record["checkpoint_id"]: record for record in records}
    if len(by_id) != len(records) or len(records) != len(candidates):
        raise FinalizationEvidenceError("CHECKPOINT_INVENTORY_MISMATCH", "candidate/checkpoint cardinality differs")
    selector_candidates: list[dict[str, Any]] = []
    for event in candidates:
        payload = event["payload"]
        record = by_id.get(payload["checkpoint_id"])
        if record is None:
            raise FinalizationEvidenceError("CHECKPOINT_INVENTORY_MISMATCH", "candidate checkpoint is absent")
        selector_candidates.append({
            "event_sequence": event["event_sequence"],
            **payload,
            "payload_locator": record["payload_locator"],
            "manifest_locator": record["manifest_locator"],
        })
    selector_candidates.sort(key=lambda item: item["event_sequence"])
    return selector_candidates


def _replay_selector(
    candidates: Sequence[dict[str, Any]],
    early_updates: Mapping[str, dict[str, Any]],
    contract: dict[str, Any],
    final_selector_evidence: dict[str, Any],
    completion_boundary: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if not candidates:
        raise FinalizationEvidenceError("NO_ELIGIBLE_CANDIDATE", "no committed validation-checkpoint candidate")
    content = contract["content"]
    interval = content["validation_interval_epochs"]
    tolerance = content["equivalence_tolerance"]
    patience = content["early_stopping_patience"]
    best: dict[str, Any] | None = None
    non_improvements = 0
    stopped_at: dict[str, Any] | None = None
    steps: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates):
        if stopped_at is not None:
            raise FinalizationEvidenceError("STOPPING_SUMMARY_MISMATCH", "candidate occurs after patience boundary")
        if candidate["completed_epoch"] % interval != 0:
            raise FinalizationEvidenceError("SELECTOR_REPLAY_MISMATCH", "candidate violates validation interval")
        if index and candidate["completed_epoch"] - candidates[index - 1]["completed_epoch"] != interval:
            raise FinalizationEvidenceError("SELECTOR_REPLAY_MISMATCH", "validation cadence is not exactly five epochs")
        selected, basis = evaluate_selection_candidate(candidate, best, tolerance)
        if selected:
            best = candidate
            non_improvements = 0
        else:
            non_improvements += 1
        checkpoint_id = candidate["checkpoint_id"]
        stored_selector = candidate["selector_state"]
        stored_early = early_updates.get(checkpoint_id)
        if stored_early is None:
            raise FinalizationEvidenceError("SELECTOR_REPLAY_MISMATCH", "candidate has no early-stopping evidence")
        expected_best = best["checkpoint_id"]
        expected = {"best_checkpoint_id": expected_best, "events_without_improvement": non_improvements}
        if any(stored_selector.get(key) != value for key, value in expected.items()):
            raise FinalizationEvidenceError("SELECTOR_REPLAY_MISMATCH", "checkpoint selector state differs from replay")
        if any(stored_early.get(key) != value for key, value in expected.items()) or stored_early.get("decision_basis") != basis:
            raise FinalizationEvidenceError("SELECTOR_REPLAY_MISMATCH", "early-stopping state differs from replay")
        step = {
            "event_sequence": candidate["event_sequence"],
            "checkpoint_id": checkpoint_id,
            "completed_epoch": candidate["completed_epoch"],
            "selected_as_best": selected,
            "decision_basis": basis,
            "best_checkpoint_id": expected_best,
            "events_without_improvement": non_improvements,
        }
        steps.append(step)
        if non_improvements == patience:
            stopped_at = candidate
    assert best is not None
    selector_state = final_selector_evidence.get("selector_state")
    if not final_selector_evidence.get("present") or not isinstance(selector_state, dict):
        raise FinalizationEvidenceError("SELECTOR_REPLAY_MISMATCH", "final selector evidence is absent")
    final_expected = {
        "best_checkpoint_id": best["checkpoint_id"],
        "events_without_improvement": non_improvements,
        "decision_basis": steps[-1]["decision_basis"],
    }
    if any(selector_state.get(key) != value for key, value in final_expected.items()):
        raise FinalizationEvidenceError("SELECTOR_REPLAY_MISMATCH", "final selector evidence differs from replay")
    final_candidate = candidates[-1]
    expected_boundary = {
        "completed_epoch": final_candidate["completed_epoch"],
        "resume_epoch": final_candidate["resume_epoch"],
        "optimizer_update": final_candidate["optimizer_update"],
    }
    if any(completion_boundary.get(key) != value for key, value in expected_boundary.items()):
        raise FinalizationEvidenceError("STOPPING_SUMMARY_MISMATCH", "completion differs from final candidate boundary")
    if stopped_at is not None and any(stopped_at[key] != expected_boundary[key] for key in expected_boundary):
        raise FinalizationEvidenceError("STOPPING_SUMMARY_MISMATCH", "completion is not the patience boundary")
    replay_summary = {
        "candidate_count": len(candidates),
        "ordered_candidate_event_sequences": [item["event_sequence"] for item in candidates],
        "steps": steps,
        "final_best_checkpoint_id": best["checkpoint_id"],
        "final_events_without_improvement": non_improvements,
    }
    stopping_summary = {
        "patience": patience,
        "patience_reached": stopped_at is not None,
        "trigger_checkpoint_id": None if stopped_at is None else stopped_at["checkpoint_id"],
        "completed_epoch": completion_boundary["completed_epoch"],
        "resume_epoch": completion_boundary["resume_epoch"],
        "optimizer_update": completion_boundary["optimizer_update"],
        "completion_reason": completion_boundary["reason"],
    }
    return best, replay_summary, stopping_summary


def finalize_run_bundle(
    bundle_root: str | Path,
    locator_roots: Mapping[str, str | Path],
    *,
    selection_contract_hash: str | None = None,
    finalizer_version: str = FINALIZER_IMPLEMENTATION_VERSION,
) -> dict[str, Any]:
    """Return a deterministic result without mutating the bundle or filesystem."""

    root = Path(bundle_root)
    validation = validate_run_bundle(root, locator_roots)
    bundle_id = validation.bundle_id
    bundle_hash = validation.bundle_content_sha256
    if not validation.valid:
        code = "BUNDLE_NOT_FOUND" if not root.exists() else "BUNDLE_INVALID"
        if validation.error_codes and validation.error_codes[0] == "BUNDLE_SCHEMA_INVALID":
            code = "UNSUPPORTED_SCHEMA_VERSION"
        return _failure_result(
            code, bundle_id=bundle_id, bundle_hash=bundle_hash, selection_id=None,
            selection_hash=selection_contract_hash, finalizer_version=finalizer_version,
        )
    manifest: dict[str, Any] | None = None
    contract: dict[str, Any] | None = None
    try:
        manifest = _read_canonical(root / COMMIT_PATH)
        contract = _validate_selection_contract(_read_canonical(root / "contracts/selection_contract.json"))
        if manifest["bindings"]["selection_contract_id"] != contract["identity"] or manifest["bindings"]["selection_contract_hash"] != contract["content_sha256"]:
            raise FinalizationEvidenceError("SELECTION_CONTRACT_MISMATCH", "bundle binding differs from contract")
        if selection_contract_hash is not None and selection_contract_hash != contract["content_sha256"]:
            raise FinalizationEvidenceError("SELECTION_CONTRACT_MISMATCH", "requested contract hash differs")
        if validation.completeness != "SCIENTIFICALLY_COMPLETE":
            raise FinalizationEvidenceError("SCIENTIFICALLY_INCOMPLETE", "bundle is not scientifically complete")
        selector_candidates = _selector_candidates(root)
        committed = read_ledger(root / "ledger")
        early = _early_updates(committed.events)
        final_selector = _read_canonical(root / "summary/final_selector_state.json")
        stopping = _read_canonical(root / "summary/stopping_boundary.json")
        if not stopping.get("present") or not isinstance(stopping.get("boundary"), dict):
            raise FinalizationEvidenceError("STOPPING_SUMMARY_MISMATCH", "completion boundary is absent")
        best, replay_summary, stopping_summary = _replay_selector(
            selector_candidates, early, contract, final_selector, stopping["boundary"]
        )
        source_inventory = _read_canonical(root / "provenance/source_inventory.json")
        if source_inventory.get("inventory_digest") != manifest["source_inventory_digest"]:
            raise FinalizationEvidenceError("SOURCE_PROVENANCE_MISMATCH", "source inventory digest differs")
        selected = {
            "checkpoint_id": best["checkpoint_id"],
            "validation_id": best["validation_id"],
            "completed_epoch": best["completed_epoch"],
            "resume_epoch": best["resume_epoch"],
            "optimizer_update": best["optimizer_update"],
            "validation_retrieval_loss": best["validation_retrieval_loss"],
            "mean_source_separation_margin": best["mean_source_separation_margin"],
            "payload_sha256": best["checkpoint_payload_sha256"],
            "manifest_sha256": best["checkpoint_manifest_sha256"],
            "payload_locator": best["payload_locator"],
        }
        candidate_set_hash = canonical_sha256(selector_candidates)
        provenance = {
            "run_id": manifest["run_id"],
            "authority_id": manifest["bindings"]["authority_id"],
            "authority_hash": manifest["bindings"]["authority_hash"],
            "scientific_configuration_id": manifest["bindings"]["scientific_configuration_id"],
            "scientific_configuration_hash": manifest["bindings"]["scientific_configuration_hash"],
            "source_inventory_digest": manifest["source_inventory_digest"],
            "ledger_manifest_sha256": manifest["bindings"]["ledger_manifest_sha256"],
        }
        return _seal_result({
            "schema_version": SCHEMA_VERSION,
            "artifact_type": "p9_v2_finalization_result",
            "status": "SUCCEEDED",
            "failure_code": None,
            "evidence_class": "VALID_SCIENTIFIC_EVIDENCE",
            "run_bundle_id": manifest["bundle_id"],
            "run_bundle_hash": manifest["bundle_content_sha256"],
            "selection_contract_id": contract["identity"],
            "selection_contract_hash": contract["content_sha256"],
            "finalizer_implementation_version": finalizer_version,
            "finalizer_implementation_hash": _implementation_hash(finalizer_version),
            "candidate_set_hash": candidate_set_hash,
            "selected_checkpoint": selected,
            "selector_replay_summary": replay_summary,
            "stopping_summary": stopping_summary,
            "scientific_state": "COMPLETE",
            "provenance": provenance,
            "evaluation_consumption_count": 0,
        })
    except FinalizationEvidenceError as error:
        return _failure_result(
            error.code, bundle_id=bundle_id, bundle_hash=bundle_hash,
            selection_id=None if contract is None else contract.get("identity"),
            selection_hash=(selection_contract_hash if contract is None else contract.get("content_sha256")),
            finalizer_version=finalizer_version, scientific_state=validation.scientific_state,
        )
    except (OSError, CanonicalJSONError, LedgerError, KeyError, TypeError, P9V2SchemaError):
        return _failure_result(
            "BUNDLE_INVALID", bundle_id=bundle_id, bundle_hash=bundle_hash,
            selection_id=None if contract is None else contract.get("identity"),
            selection_hash=(selection_contract_hash if contract is None else contract.get("content_sha256")),
            finalizer_version=finalizer_version, scientific_state=validation.scientific_state,
        )


def validate_finalization_result(
    result: Mapping[str, Any],
    bundle_root: str | Path,
    locator_roots: Mapping[str, str | Path],
) -> tuple[bool, str | None]:
    """Validate result structure and chain bindings without rerunning selection."""

    try:
        value = dict(result)
        validate_instance("finalization_result", value)
        preimage = {key: item for key, item in value.items() if key not in {"finalization_id", "finalization_result_hash"}}
        result_hash = canonical_sha256(preimage)
        if value["finalization_result_hash"] != result_hash or value["finalization_id"] != f"p9fin_{result_hash[:24]}":
            return False, "FINALIZATION_HASH_MISMATCH"
        if value["finalizer_implementation_hash"] != _implementation_hash(value["finalizer_implementation_version"]):
            return False, "FINALIZER_IMPLEMENTATION_MISMATCH"
        bundle = validate_run_bundle(bundle_root, locator_roots)
        if not bundle.valid:
            return False, "BUNDLE_INVALID"
        if value["run_bundle_id"] != bundle.bundle_id or value["run_bundle_hash"] != bundle.bundle_content_sha256:
            return False, "BUNDLE_MISMATCH"
        manifest = _read_canonical(Path(bundle_root) / COMMIT_PATH)
        if value["selection_contract_id"] != manifest["bindings"]["selection_contract_id"] or value["selection_contract_hash"] != manifest["bindings"]["selection_contract_hash"]:
            return False, "SELECTION_CONTRACT_MISMATCH"
        if value["status"] != "SUCCEEDED":
            return False, "FINALIZATION_UNSUCCESSFUL"
        candidates = _selector_candidates(Path(bundle_root))
        if value["candidate_set_hash"] != canonical_sha256(candidates):
            return False, "CANDIDATE_SET_MISMATCH"
        replay_summary = value["selector_replay_summary"]
        sequences = [item["event_sequence"] for item in candidates]
        if replay_summary.get("candidate_count") != len(candidates) or replay_summary.get("ordered_candidate_event_sequences") != sequences:
            return False, "SELECTOR_SUMMARY_MISMATCH"
        selected = value["selected_checkpoint"]
        inventory = _read_canonical(Path(bundle_root) / "checkpoints/checkpoint_inventory.json")
        record = next((item for item in inventory["checkpoints"] if item["checkpoint_id"] == selected["checkpoint_id"]), None)
        if record is None:
            return False, "CHECKPOINT_INVENTORY_MISMATCH"
        expected = {
            "checkpoint_id": record["checkpoint_id"],
            "validation_id": record["validation_id"],
            "completed_epoch": record["completed_epoch"],
            "resume_epoch": record["resume_epoch"],
            "optimizer_update": record["optimizer_update"],
            "validation_retrieval_loss": record["validation_retrieval_loss"],
            "mean_source_separation_margin": record["mean_source_separation_margin"],
            "payload_sha256": record["payload_locator"]["content_sha256"],
            "manifest_sha256": record["manifest_locator"]["content_sha256"],
            "payload_locator": record["payload_locator"],
        }
        if selected != expected:
            return False, "CHECKPOINT_INVENTORY_MISMATCH"
        if replay_summary.get("final_best_checkpoint_id") != selected["checkpoint_id"]:
            return False, "SELECTOR_SUMMARY_MISMATCH"
        stopping = _read_canonical(Path(bundle_root) / "summary/stopping_boundary.json")["boundary"]
        expected_stopping = {
            "patience": 4,
            "completed_epoch": stopping["completed_epoch"],
            "resume_epoch": stopping["resume_epoch"],
            "optimizer_update": stopping["optimizer_update"],
            "completion_reason": stopping["reason"],
        }
        if any(value["stopping_summary"].get(key) != item for key, item in expected_stopping.items()):
            return False, "STOPPING_SUMMARY_MISMATCH"
        expected_provenance = {
            "run_id": manifest["run_id"],
            "authority_id": manifest["bindings"]["authority_id"],
            "authority_hash": manifest["bindings"]["authority_hash"],
            "scientific_configuration_id": manifest["bindings"]["scientific_configuration_id"],
            "scientific_configuration_hash": manifest["bindings"]["scientific_configuration_hash"],
            "source_inventory_digest": manifest["source_inventory_digest"],
            "ledger_manifest_sha256": manifest["bindings"]["ledger_manifest_sha256"],
        }
        if value["provenance"] != expected_provenance:
            return False, "SOURCE_PROVENANCE_MISMATCH"
        return True, None
    except (OSError, CanonicalJSONError, P9V2SchemaError, FinalizationEvidenceError, KeyError, TypeError, StopIteration):
        return False, "FINALIZATION_RESULT_INVALID"
