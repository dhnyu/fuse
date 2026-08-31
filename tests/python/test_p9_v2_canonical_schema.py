from __future__ import annotations

import json
import math
import sys
import unicodedata
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from p9_v2_canonical import (  # noqa: E402
    MAX_SAFE_INTEGER,
    CanonicalJSONError,
    canonical_json_bytes,
    canonical_json_line,
    canonical_sha256,
)
from p9_v2_ledger import LedgerCorruptionError, LedgerTransitionError, make_event, verify_event  # noqa: E402
from p9_v2_schema import SCHEMA_FILES, load_schema, validate_instance  # noqa: E402
from p9_v2_test_support import GENESIS_HASH, ROLES, RUN_ID, make_chain, payload, timestamp  # noqa: E402


def test_canonical_json_primitives_and_key_order():
    assert canonical_json_bytes(None) == b"null"
    assert canonical_json_bytes(True) == b"true"
    assert canonical_json_bytes(False) == b"false"
    assert canonical_json_bytes({"z": [1, "x"], "a": 2}) == b'{"a":2,"z":[1,"x"]}'
    assert canonical_json_line({"a": 1}) == b'{"a":1}\n'


def test_float_encoding_is_exact_exponent_free_binary64_decimal():
    assert canonical_json_bytes(0.1) == (
        b"0.1000000000000000055511151231257827021181583404541015625"
    )
    assert b"e" not in canonical_json_bytes(1.25e-10).lower()
    assert canonical_json_bytes(1.0) == b"1"


@pytest.mark.parametrize("value", [0.0, -0.0])
def test_zero_sign_is_normalized(value):
    assert canonical_json_bytes(value) == b"0"


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_nonfinite_numbers_are_rejected(value):
    with pytest.raises(CanonicalJSONError, match="NaN and infinite"):
        canonical_json_bytes(value)


@pytest.mark.parametrize("value", [MAX_SAFE_INTEGER + 1, -MAX_SAFE_INTEGER - 1])
def test_noninteroperable_integers_are_rejected(value):
    with pytest.raises(CanonicalJSONError, match="safe range"):
        canonical_json_bytes(value)


@pytest.mark.parametrize("value", [float(MAX_SAFE_INTEGER + 1), -float(MAX_SAFE_INTEGER + 1)])
def test_noninteroperable_floats_are_rejected(value):
    with pytest.raises(CanonicalJSONError, match="safe range"):
        canonical_json_bytes(value)


@pytest.mark.parametrize("value", [{1: "bad"}, (1, 2), {"x": object()}])
def test_unsupported_native_values_are_rejected(value):
    with pytest.raises(CanonicalJSONError):
        canonical_json_bytes(value)


def test_unicode_contract_requires_nfc_and_rejects_surrogates():
    composed = "\u00e9"
    decomposed = unicodedata.normalize("NFD", composed)
    assert canonical_json_bytes(composed) == b'"\xc3\xa9"'
    with pytest.raises(CanonicalJSONError, match="NFC"):
        canonical_json_bytes(decomposed)
    with pytest.raises(CanonicalJSONError, match="surrogate"):
        canonical_json_bytes("\ud800")


def test_string_escaping_is_minimal_and_deterministic():
    assert canonical_json_bytes('a\n"\\\u0001') == b'"a\\n\\"\\\\\\u0001"'


def test_repeated_serialization_and_mapping_order_are_identical():
    left = {"b": 0.1, "a": [True, None, "Seoul"]}
    right = {"a": [True, None, "Seoul"], "b": 0.1}
    expected = canonical_json_bytes(left)
    assert expected == canonical_json_bytes(right)
    assert {canonical_json_bytes(left) for _ in range(100)} == {expected}
    assert canonical_sha256(left) == canonical_sha256(right)


def test_runtime_schemas_parse_and_pass_draft_2020_12():
    v2_a_schemas = {"event", "ledger_header", "ledger_manifest", "tail_cache"}
    assert v2_a_schemas <= set(SCHEMA_FILES)
    for name in v2_a_schemas:
        schema = load_schema(name)
        jsonschema.Draft202012Validator.check_schema(schema)
        assert schema["$id"].endswith("2.0.0")


def test_every_event_type_has_a_valid_runtime_schema_example():
    specs = [(event_type, payload(event_type)) for event_type in ROLES]
    events = make_chain(specs)
    for event in events:
        validate_instance("event", event)


def test_event_identity_hash_and_chain_are_deterministic():
    kwargs = dict(
        event_type="RUN_AUTHORIZED",
        event_sequence=1,
        run_id=RUN_ID,
        occurred_at=timestamp(1),
        writer_id="synthetic-controller",
        writer_role="controller",
        previous_event_hash=GENESIS_HASH,
        payload=payload("RUN_AUTHORIZED"),
    )
    first = make_event(**kwargs)
    second = make_event(**kwargs)
    assert first == second
    verify_event(first, expected_run_id=RUN_ID, expected_sequence=1, expected_previous_hash=GENESIS_HASH)


def test_schema_rejects_malformed_payload():
    event = make_chain([("RUN_AUTHORIZED", None)])[0]
    event["payload"].pop("authority_hash")
    with pytest.raises(LedgerCorruptionError, match="schema violation"):
        verify_event(event)


def test_semantics_reject_validation_resume_epoch_mismatch():
    bad = payload("VALIDATION_CHECKPOINT_COMMITTED", resume_epoch=7)
    with pytest.raises(LedgerTransitionError, match="completed_epoch"):
        make_event(
            event_type="VALIDATION_CHECKPOINT_COMMITTED", event_sequence=1, run_id=RUN_ID,
            occurred_at=timestamp(1), writer_id="rank0", writer_role="rank0",
            previous_event_hash=GENESIS_HASH, payload=bad,
        )


def test_schema_rejects_invalid_checkpoint_hash():
    bad = payload("VALIDATION_CHECKPOINT_COMMITTED", checkpoint_payload_sha256="bad")
    with pytest.raises(LedgerCorruptionError, match="schema violation"):
        make_event(
            event_type="VALIDATION_CHECKPOINT_COMMITTED", event_sequence=1, run_id=RUN_ID,
            occurred_at=timestamp(1), writer_id="rank0", writer_role="rank0",
            previous_event_hash=GENESIS_HASH, payload=bad,
        )


@pytest.mark.parametrize("event_type", ["TRAINING_INTERRUPTED", "TRAINING_FAILED"])
def test_semantics_reject_exact_resume_without_checkpoint(event_type):
    bad = payload(
        event_type,
        resumable_checkpoint_committed=False,
        resume_policy="EXACT_RESUME",
    )
    with pytest.raises(LedgerTransitionError, match="requires a committed checkpoint"):
        make_event(
            event_type=event_type, event_sequence=1, run_id=RUN_ID,
            occurred_at=timestamp(1), writer_id="controller", writer_role="controller",
            previous_event_hash=GENESIS_HASH, payload=bad,
        )
