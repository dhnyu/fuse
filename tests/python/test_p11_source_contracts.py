from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import jsonschema

from p9_v2_canonical import canonical_sha256


ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads(
    (ROOT / "config/schemas/p11_downstream_source_contract.schema.json").read_text()
)


def _load(name: str) -> dict:
    return json.loads((ROOT / "config" / name).read_text())


def _assert_content_identity(contract: dict) -> None:
    preimage = {
        key: value
        for key, value in contract.items()
        if key not in {"contract_id", "content_sha256"}
    }
    digest = canonical_sha256(preimage)
    assert contract["content_sha256"] == digest
    assert contract["contract_id"] == f"p11src_{digest[:24]}"


def test_p11_source_contract_schema_is_draft_2020_12() -> None:
    jsonschema.Draft202012Validator.check_schema(SCHEMA)


def test_sgis_partial_contract_is_hash_bound_and_fail_closed() -> None:
    contract = _load("p11_sgis_source_contract.json")
    jsonschema.Draft202012Validator(SCHEMA).validate(contract)
    _assert_content_identity(contract)

    assert contract["status"] == "PARTIALLY_CLOSED"
    assert contract["preprocessing_authorized"] is False
    mapping = {
        item["target"]: item["code"]
        for item in contract["semantic_contract"]["targets"]
    }
    assert mapping == {
        "total_population": "to_in_001",
        "households": "to_ga_001",
        "housing_units": "to_ho_001",
        "establishments": "to_fa_010",
        "workers": "to_em_020",
    }
    assert contract["semantic_contract"]["privacy"]["explicit_zero"] == (
        "retain as observed released zero"
    )
    omission = contract["semantic_contract"]["row_omission"]
    assert omission["distinguishable_per_row"] is False
    assert omission["provisional_ingest_action"] == "missing, never silently zero"
    assert contract["unresolved_fields"] == [
        {
            "field": "row_omission_semantics",
            "classification": "BLOCKED_SOURCE_SEMANTICS",
            "reason": contract["unresolved_fields"][0]["reason"],
        }
    ]


def test_ecostress_partial_contract_closes_qa_without_coverage_guess() -> None:
    contract = _load("p11_ecostress_source_contract.json")
    jsonschema.Draft202012Validator(SCHEMA).validate(contract)
    _assert_content_identity(contract)

    assert contract["status"] == "PARTIALLY_CLOSED"
    assert contract["preprocessing_authorized"] is False
    pixel = contract["semantic_contract"]["pixel_acceptance"]
    assert pixel["qc_mandatory_bits_1_0"].startswith("00")
    assert pixel["accepted_cloud_value"] == "0 (Clear)"
    assert pixel["rejected_cloud_value"] == "1 (Cloudy)"
    assert pixel["official_scaled_valid_range_kelvin"] == [150, 1310.7]
    assert pixel["accepted_observed_audit"] == {
        "pixel_count": 13_753_718,
        "minimum_kelvin": 156.12,
        "maximum_kelvin": 340.5,
    }
    assert contract["semantic_contract"]["unit"]["downstream_response"] == "Kelvin"
    mapping = contract["semantic_contract"]["future_scene_mapping"]
    assert contract["semantic_contract"]["science_acquisitions"][
        "different_timestamps_are_distinct"
    ] is True
    assert mapping["period_aggregation"].startswith("arithmetic mean")
    assert {
        item["classification"] for item in contract["unresolved_fields"]
    } == {"BLOCKED_SCIENTIFIC_DECISION"}


def test_source_contracts_cannot_authorize_scientific_work() -> None:
    for name in (
        "p11_sgis_source_contract.json",
        "p11_ecostress_source_contract.json",
    ):
        contract = _load(name)
        assert contract["preprocessing_authorized"] is False
        assert "downstream_preprocessing" in contract["prohibited"]
        assert "scene_target_materialization" in contract["prohibited"]
        assert "fold_generation" in contract["prohibited"]
        assert "ridge_fitting" in contract["prohibited"]


def test_source_contract_schema_rejects_preprocessing_authority() -> None:
    contract = deepcopy(_load("p11_sgis_source_contract.json"))
    contract["preprocessing_authorized"] = True
    errors = list(jsonschema.Draft202012Validator(SCHEMA).iter_errors(contract))
    assert len(errors) == 1
    assert list(errors[0].absolute_path) == ["preprocessing_authorized"]
