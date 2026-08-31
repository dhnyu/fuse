"""Resolver-only checkpoint inputs for P9-B, selected-FM, evaluation, P10, and P11."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from p9_v2_acceptance import (
    ACCEPTANCE_ID_PATTERN,
    AcceptedCheckpoint,
    AcceptanceError,
    resolve_accepted_checkpoint as resolve_acceptance_chain,
)
from p9_v2_canonical import canonical_sha256
from p9_v2_schema import P9V2SchemaError, SCHEMA_VERSION, validate_instance


CONSUMERS = ("p9_b", "selected_fm", "held_out_evaluation", "p10", "p11")


class DownstreamResolutionError(ValueError):
    """Stable failure for consumer-bound acceptance resolution."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def _fail(code: str, message: str) -> None:
    raise DownstreamResolutionError(code, message)


def _eligibility_preimage(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: item for key, item in value.items()
        if key not in {"eligibility_id", "content_sha256"}
    }


def make_acceptance_eligibility(
    entries: list[Mapping[str, Any]], *, namespace: str
) -> dict[str, Any]:
    """Create a deterministic immutable eligibility snapshot, not an authority."""

    normalized = sorted((dict(entry) for entry in entries), key=lambda item: item["acceptance_id"])
    if len({item["acceptance_id"] for item in normalized}) != len(normalized):
        _fail("AMBIGUOUS_ACCEPTANCE_ELIGIBILITY", "acceptance identity is duplicated")
    preimage = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "p9_v2_acceptance_eligibility",
        "namespace": namespace,
        "status": "COMMITTED",
        "entries": normalized,
    }
    digest = canonical_sha256(preimage)
    result = {
        **preimage,
        "eligibility_id": f"p9elig_{digest[:24]}",
        "content_sha256": digest,
    }
    try:
        validate_instance("acceptance_eligibility", result)
    except P9V2SchemaError as error:
        _fail("INVALID_ACCEPTANCE_ELIGIBILITY", str(error))
    return result


def validate_acceptance_eligibility(value: Mapping[str, Any]) -> None:
    try:
        validate_instance("acceptance_eligibility", value)
    except P9V2SchemaError as error:
        _fail("INVALID_ACCEPTANCE_ELIGIBILITY", str(error))
    digest = canonical_sha256(_eligibility_preimage(value))
    if value["content_sha256"] != digest or value["eligibility_id"] != f"p9elig_{digest[:24]}":
        _fail("INVALID_ACCEPTANCE_ELIGIBILITY", "snapshot identity/hash differs")
    identities = [entry["acceptance_id"] for entry in value["entries"]]
    if identities != sorted(identities) or len(identities) != len(set(identities)):
        _fail("AMBIGUOUS_ACCEPTANCE_ELIGIBILITY", "entries are duplicated or unordered")


@dataclass(frozen=True)
class AcceptedCheckpointResolver:
    """Configured canonical resolver whose public resolution method takes only an ID."""

    acceptance_root: Path
    bundle_root: Path
    locator_roots: Mapping[str, str | Path]
    eligibility: Mapping[str, Any]

    def resolve_accepted_checkpoint(self, acceptance_identity: str) -> AcceptedCheckpoint:
        validate_acceptance_eligibility(self.eligibility)
        if (
            not isinstance(acceptance_identity, str)
            or ACCEPTANCE_ID_PATTERN.fullmatch(acceptance_identity) is None
        ):
            _fail("INVALID_ACCEPTANCE_ID", "only canonical p9accv2 identities are accepted")
        entries = [
            entry for entry in self.eligibility["entries"]
            if entry["acceptance_id"] == acceptance_identity
        ]
        if len(entries) != 1:
            _fail("ACCEPTANCE_ELIGIBILITY_UNRESOLVED", "acceptance is absent or ambiguous")
        entry = entries[0]
        if entry["eligibility"] != "ELIGIBLE":
            _fail("ACCEPTANCE_INELIGIBLE", f"acceptance is {entry['eligibility'].lower()}")
        try:
            resolved = resolve_acceptance_chain(
                acceptance_identity,
                self.acceptance_root,
                self.bundle_root,
                self.locator_roots,
            )
        except AcceptanceError as error:
            _fail(error.code, error.message)
        if (
            resolved.authority_id != entry["authority_id"]
            or resolved.authority_hash != entry["authority_hash"]
        ):
            _fail("AUTHORITY_MISMATCH", "eligibility authority differs from acceptance chain")
        return resolved


def resolve_consumer_checkpoint(
    consumer: str,
    acceptance_identity: str,
    resolver: AcceptedCheckpointResolver,
) -> AcceptedCheckpoint:
    """Resolve the sole checkpoint input shared by every downstream consumer."""

    if consumer not in CONSUMERS:
        _fail("UNKNOWN_CONSUMER", "consumer is outside the V2-E contract")
    if not isinstance(resolver, AcceptedCheckpointResolver):
        _fail("INVALID_RESOLVER", "a configured canonical resolver is required")
    return resolver.resolve_accepted_checkpoint(acceptance_identity)


def resolve_p9_b_checkpoint(identity: str, resolver: AcceptedCheckpointResolver) -> AcceptedCheckpoint:
    return resolve_consumer_checkpoint("p9_b", identity, resolver)


def resolve_selected_fm_checkpoint(identity: str, resolver: AcceptedCheckpointResolver) -> AcceptedCheckpoint:
    return resolve_consumer_checkpoint("selected_fm", identity, resolver)


def resolve_held_out_evaluation_checkpoint(identity: str, resolver: AcceptedCheckpointResolver) -> AcceptedCheckpoint:
    return resolve_consumer_checkpoint("held_out_evaluation", identity, resolver)


def resolve_p10_checkpoint(identity: str, resolver: AcceptedCheckpointResolver) -> AcceptedCheckpoint:
    return resolve_consumer_checkpoint("p10", identity, resolver)


def resolve_p11_checkpoint(identity: str, resolver: AcceptedCheckpointResolver) -> AcceptedCheckpoint:
    return resolve_consumer_checkpoint("p11", identity, resolver)
