from __future__ import annotations

import json
import hashlib
from copy import deepcopy
from pathlib import Path

import jsonschema
import yaml

from p9_v2_canonical import canonical_sha256


ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads(
    (ROOT / "config/schemas/p11_downstream_source_contract.schema.json").read_text()
)
METHODOLOGY_SCHEMA = json.loads(
    (ROOT / "config/schemas/p11_methodology_decision.schema.json").read_text()
)
DATASET_SCHEMA = json.loads(
    (ROOT / "config/schemas/p11_downstream_dataset_acceptance.schema.json").read_text()
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
    jsonschema.Draft202012Validator.check_schema(METHODOLOGY_SCHEMA)
    jsonschema.Draft202012Validator.check_schema(DATASET_SCHEMA)


def test_sgis_closed_contract_is_hash_bound_and_preserves_omissions() -> None:
    contract = _load("p11_sgis_source_contract.json")
    jsonschema.Draft202012Validator(SCHEMA).validate(contract)
    _assert_content_identity(contract)

    assert contract["status"] == "CLOSED"
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
    assert omission["preprocessing_action"] == "unavailable for that statistic, never zero"
    assert contract["unresolved_fields"] == []


def test_ecostress_closed_contract_freezes_qa_and_coverage() -> None:
    contract = _load("p11_ecostress_source_contract.json")
    jsonschema.Draft202012Validator(SCHEMA).validate(contract)
    _assert_content_identity(contract)

    assert contract["status"] == "CLOSED"
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
    assert mapping["minimum_valid_area_fraction_per_acquisition"] == 0.5
    assert mapping["minimum_accepted_acquisitions_per_scene"] == 12
    assert contract["unresolved_fields"] == []


def test_source_contracts_cannot_authorize_scientific_work() -> None:
    for name in (
        "p11_sgis_source_contract.json",
        "p11_living_population_source_contract.json",
        "p11_land_value_source_contract.json",
        "p11_ecostress_source_contract.json",
    ):
        contract = _load(name)
        assert contract["preprocessing_authorized"] is False
        assert "fold_generation" in contract["prohibited"]
        assert "ridge_fitting" in contract["prohibited"]


def test_all_four_source_contracts_are_closed_and_hash_bound() -> None:
    names = (
        "p11_sgis_source_contract.json",
        "p11_living_population_source_contract.json",
        "p11_land_value_source_contract.json",
        "p11_ecostress_source_contract.json",
    )
    for name in names:
        contract = _load(name)
        jsonschema.Draft202012Validator(SCHEMA).validate(contract)
        _assert_content_identity(contract)
        assert contract["status"] == "CLOSED"
        assert contract["unresolved_fields"] == []


def test_methodology_decision_closes_scope_and_forbids_model_work() -> None:
    decision = _load("p11_methodology_decision.json")
    jsonschema.Draft202012Validator(METHODOLOGY_SCHEMA).validate(decision)
    preimage = {k: v for k, v in decision.items() if k not in {"decision_id", "content_sha256"}}
    digest = canonical_sha256(preimage)
    assert decision["decision_id"] == f"p11meth_{digest[:24]}"
    assert decision["content_sha256"] == digest
    assert decision["status"] == "CLOSED"
    assert decision["unspecified_scientific_decision_count"] == 0
    assert len(decision["active_targets"]) == 11
    assert decision["flickr"]["status"] == "EXCLUDED_STALE_TABLE_EVIDENCE"
    assert {"new_embedding_inference", "fold_generation", "ridge_fitting"} <= set(decision["prohibited"])


def test_source_contract_schema_rejects_preprocessing_authority() -> None:
    contract = deepcopy(_load("p11_sgis_source_contract.json"))
    contract["preprocessing_authorized"] = True
    errors = list(jsonschema.Draft202012Validator(SCHEMA).iter_errors(contract))
    assert len(errors) == 1
    assert list(errors[0].absolute_path) == ["preprocessing_authorized"]


def test_accepted_downstream_dataset_reference_and_schema() -> None:
    reference = yaml.safe_load((ROOT / "config/p11_downstream_dataset.yml").read_text())
    assert reference["status"] == "ACCEPTED"
    assert reference["dataset_id"] == "p11ds_39607da2de792ad6b3c9bb30"
    assert reference["supersedes"] == "p11ds_fdb1f34c6daeda259e803e37"
    assert reference["dissertation_authority_id"] == "disauth_60a514578f57b9397ce71ee6"
    assert reference["methodology_decision_id"] == "p11meth_42070c9b832c232a6e989d25"
    assert (
        reference["living_population_source_contract_id"]
        == "p11src_ff2f5bb24376968aedfdfecc"
    )
    assert reference["target_count"] == 11
    assert reference["scene_universe_count"] == 1600
    assert reference["next_work_unit"] == "P11_F_FINAL_DOWNSTREAM_COMPARISON_AND_ACCEPTANCE"
    assert reference["p11_c_readiness_id"] == "p11c_e78d7c740edc49f1f646ebc3"
    assert reference["p11_e_acceptance_id"] == "p11e_047e764ed7467b72ebe846df"
    acceptance_path = Path(reference["acceptance_path"])
    payload = acceptance_path.read_bytes()
    assert hashlib.sha256(payload).hexdigest() == reference["acceptance_sha256"]
    acceptance = json.loads(payload)
    v2_schema = json.loads(
        (ROOT / "config/schemas/p11_downstream_dataset_acceptance_v2.schema.json").read_text()
    )
    jsonschema.Draft202012Validator(v2_schema).validate(acceptance)
    assert acceptance["dataset_id"] == reference["dataset_id"]
    assert acceptance["content_sha256"] == reference["content_sha256"]
    assert (
        acceptance["living_population_shard"]["shard_id"]
        == reference["living_population_shard_id"]
    )
    dataset_root = acceptance_path.parent
    for artifact in acceptance["artifacts"]:
        artifact_path = dataset_root / artifact["basename"]
        assert artifact_path.stat().st_size == artifact["byte_size"]
        assert hashlib.sha256(artifact_path.read_bytes()).hexdigest() == artifact["sha256"]
