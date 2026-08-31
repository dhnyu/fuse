from __future__ import annotations

import json
import sys
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from p9_v2_bundle import (  # noqa: E402
    BundleError,
    make_bound_document,
    make_filesystem_locator,
)
from p9_v2_canonical import CanonicalJSONError, canonical_json_bytes, parse_canonical_json  # noqa: E402
from p9_v2_schema import P9V2SchemaError, SCHEMA_FILES, load_schema, validate_instance  # noqa: E402


def test_v2_b_runtime_schemas_parse_and_pass_draft_2020_12():
    assert {"immutable_locator", "bundle_inventory", "run_bundle_manifest"} <= set(SCHEMA_FILES)
    for name in ("immutable_locator", "bundle_inventory", "run_bundle_manifest"):
        schema = load_schema(name)
        jsonschema.Draft202012Validator.check_schema(schema)
        assert schema["$id"].endswith("2.0.0")


def test_canonical_parser_reuses_unique_v2_a_bytes():
    value = {"b": 0.1, "a": [True, None]}
    raw = canonical_json_bytes(value)
    assert parse_canonical_json(raw) == value
    with pytest.raises(CanonicalJSONError, match="not canonical"):
        parse_canonical_json(json.dumps(value, indent=2).encode("utf-8"))


def test_filesystem_locator_separates_logical_location_and_physical_root(tmp_path):
    physical = tmp_path / "physical" / "checkpoint.pt"
    physical.parent.mkdir()
    physical.write_bytes(b"checkpoint")
    locator = make_filesystem_locator(
        namespace="checkpoint-store",
        relative_path="objects/a/checkpoint.pt",
        physical_path=physical,
        role="checkpoint_payload",
        media_type="application/x-pytorch",
        associated_manifest_sha256="a" * 64,
    )
    validate_instance("immutable_locator", locator)
    assert str(tmp_path) not in canonical_json_bytes(locator).decode("utf-8")
    assert locator["immutable_object_id"] == f"sha256:{locator['content_sha256']}"


@pytest.mark.parametrize(
    "bad",
    [
        "/absolute/checkpoint.pt",
        "../escape/checkpoint.pt",
        "objects/../checkpoint.pt",
        r"objects\checkpoint.pt",
    ],
)
def test_locator_rejects_absolute_traversal_or_platform_paths(tmp_path, bad):
    physical = tmp_path / "payload"
    physical.write_bytes(b"x")
    with pytest.raises(BundleError):
        make_filesystem_locator(
            namespace="checkpoint-store", relative_path=bad, physical_path=physical,
            role="checkpoint_payload", media_type="application/octet-stream",
            associated_manifest_sha256="a" * 64,
        )


def test_locator_schema_rejects_raw_manual_path():
    with pytest.raises(P9V2SchemaError):
        validate_instance("immutable_locator", {"path": "/tmp/checkpoint.pt"})


def test_locator_schema_rejects_unknown_backend(tmp_path):
    physical = tmp_path / "payload"
    physical.write_bytes(b"x")
    locator = make_filesystem_locator(
        namespace="checkpoint-store", relative_path="objects/x", physical_path=physical,
        role="checkpoint_payload", media_type="application/octet-stream",
        associated_manifest_sha256="a" * 64,
    )
    locator["backend"] = "mutable-http"
    with pytest.raises(P9V2SchemaError):
        validate_instance("immutable_locator", locator)


def test_bound_document_rejects_targets_or_evaluation_evidence():
    with pytest.raises(BundleError, match="PROHIBITED_EVIDENCE"):
        make_bound_document("bad", {"targets_metadata": {"current": True}})
    with pytest.raises(BundleError, match="PROHIBITED_EVIDENCE"):
        make_bound_document("bad", {"held_out_evaluation": {"metric": 1.0}})
