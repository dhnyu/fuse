"""Resolver-only checkpoint inputs for P9-B, selected-FM, evaluation, P10, and P11."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from p9_v2_acceptance import (
    ACCEPTANCE_ID_PATTERN,
    AcceptedCheckpoint,
    AcceptanceError,
    resolve_accepted_checkpoint as resolve_acceptance_chain,
)
from p9_v2_canonical import canonical_json_bytes, canonical_sha256, parse_canonical_json
from p9_v2_ledger import fsync_directory, write_all
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


def publish_acceptance_eligibility(
    value: Mapping[str, Any], publication_root: str | Path
) -> Path:
    """Atomically publish or validate one immutable eligibility snapshot."""

    validate_acceptance_eligibility(value)
    root = Path(publication_root)
    root.mkdir(parents=True, exist_ok=True)
    staging = root / ".staging"
    staging.mkdir(exist_ok=True)
    final = root / f"{value['eligibility_id']}.json"
    raw = canonical_json_bytes(dict(value))
    if final.exists():
        try:
            existing = parse_canonical_json(final.read_bytes())
        except Exception as error:
            _fail("INCONSISTENT_EXISTING_ELIGIBILITY", str(error))
        if existing != dict(value):
            _fail("INCONSISTENT_EXISTING_ELIGIBILITY", "existing snapshot differs")
        validate_acceptance_eligibility(existing)
        return final
    descriptor, stage_name = tempfile.mkstemp(prefix=f".{value['eligibility_id']}.", dir=staging)
    stage = Path(stage_name)
    try:
        write_all(descriptor, raw)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    try:
        if parse_canonical_json(stage.read_bytes()) != dict(value):
            _fail("ELIGIBILITY_STAGING_INVALID", "staged snapshot differs")
        try:
            os.link(stage, final)
            stage.unlink()
        except FileExistsError:
            existing = parse_canonical_json(final.read_bytes())
            if existing != dict(value):
                _fail("INCONSISTENT_EXISTING_ELIGIBILITY", "concurrent snapshot differs")
            stage.unlink(missing_ok=True)
        fsync_directory(root)
    finally:
        stage.unlink(missing_ok=True)
    loaded = parse_canonical_json(final.read_bytes())
    validate_acceptance_eligibility(loaded)
    if loaded != dict(value):
        _fail("ELIGIBILITY_PUBLICATION_INVALID", "published snapshot differs")
    return final


def load_acceptance_eligibility(path: str | Path) -> dict[str, Any]:
    try:
        value = parse_canonical_json(Path(path).read_bytes())
    except Exception as error:
        _fail("INVALID_ACCEPTANCE_ELIGIBILITY", str(error))
    if not isinstance(value, dict):
        _fail("INVALID_ACCEPTANCE_ELIGIBILITY", "snapshot root is not an object")
    validate_acceptance_eligibility(value)
    return value


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
