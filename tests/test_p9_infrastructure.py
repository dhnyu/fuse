from pathlib import Path
import json
import sys

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from p9_infrastructure import (bounded_groups, cache_requirements, expected_geometry_cache_entries,
                               load_contract, materialize_comparison, materialize_hyperparameter_configuration,
                               p9_learning_rate, reject_duplicate_formal_run,
                               validate_p8_bundle, validate_terminal_outcome)

P8 = Path("/mnt/hdd002/dhnyu/fusedata/models/reduced/formal_plan/p8a_3cb1c49084529987f0244a93/p8acc_c9f16a07275aadfae928d329")


def test_contract_and_canonical_p8_bundle():
    contract = load_contract(ROOT / "config/p9_infrastructure.yml")
    bundle = validate_p8_bundle(P8, contract)
    assert bundle["hyper"]["count"] == 13
    assert bundle["comparisons"]["count"] == 7
    assert bundle["comparisons"]["materialized_count"] == 0


def test_full_sampler_and_pilot_limit():
    scenes = [f"scn_{value:04d}" for value in range(2421)]
    groups = bounded_groups(scenes, 20260828, 40)
    assert len(groups) == 40 and all(len(group) == 32 for group in groups)
    with pytest.raises(ValueError, match="limited to 40"):
        bounded_groups(scenes, 20260828, 41)


def test_p9_b_materialization_is_fail_closed():
    template = {"template_id": "cmp_a1_geometric_core", "template_hash": "a" * 64}
    with pytest.raises(ValueError, match="selected FM"):
        materialize_comparison(template, None)
    with pytest.raises(ValueError, match="evaluation identity"):
        materialize_comparison(template, "p9accv2_" + "a" * 24, evaluation_identity="evaluation")
    with pytest.raises(ValueError, match="resolver"):
        materialize_comparison(template, "p9accv2_" + "a" * 24)


def test_p9_full_schedule_boundaries():
    assert p9_learning_rate(1, 1e-3) == pytest.approx(1e-3 / 760)
    assert p9_learning_rate(760, 1e-3) == 1e-3
    assert p9_learning_rate(15200, 1e-3) == 0.0


def test_terminal_outcomes_and_duplicate_attempts_fail_closed():
    validate_terminal_outcome({"terminal_outcome": "SCIENTIFIC_DIVERGENCE", "last_valid_update": 10,
                               "detector": "finite_gate", "reason": "non_finite_loss",
                               "complete_trace_sha256": "a" * 64, "winner_eligible": False})
    with pytest.raises(ValueError, match="masquerade"):
        validate_terminal_outcome({"terminal_outcome": "SCIENTIFIC_DIVERGENCE", "infrastructure_failure": True})
    with pytest.raises(FileExistsError, match="duplicate formal"):
        reject_duplicate_formal_run([{"formal_attempt": True, "scientific_hash": "a", "seed": 3}], "a", 3)


def test_all_p9_schemas_are_fail_closed():
    for path in sorted((ROOT / "config/schemas").glob("p9_*.schema.json")):
        schema = json.loads(path.read_text())
        jsonschema.Draft202012Validator.check_schema(schema)
        assert schema["additionalProperties"] is False

    schema = json.loads((ROOT / "config/schemas/p9_training_configuration.schema.json").read_text())
    valid = {
        "schema_version": "1.0.0", "configuration_id": "cfg_main",
        "scientific_hash": "a" * 64, "scientific": {"d": 64},
        "execution": {"world_size": 2},
        "parents": {"p8_acceptance_id": "p8acc_c9f16a07275aadfae928d329",
                    "p7_runtime_acceptance_id": "p7rta_c780441a553abe26772827d0"},
        "evaluation_ancestry": False, "formal_authorized": False,
    }
    jsonschema.validate(valid, schema)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({**valid, "evaluation_identity": "forbidden"}, schema)


def test_all_hyperparameter_rows_route_exactly_and_without_authorization():
    import yaml
    contract = load_contract(ROOT / "config/p9_infrastructure.yml")
    rows = validate_p8_bundle(P8, contract)["hyper"]["rows"]
    training = yaml.safe_load((ROOT / "config/p7_deterministic_training.yml").read_text())
    model = yaml.safe_load((ROOT / "config/p6_model_dataloader.yml").read_text())
    routed = [materialize_hyperparameter_configuration(row, training, model) for row in rows]
    assert len(routed) == 13 and all(not item["formal_authorized"] for item in routed)
    by_id = {item["configuration_id"]: item for item in routed}
    assert by_id["cfg_d48"]["model"]["model"]["d"] == 48
    assert by_id["cfg_d128"]["training"]["queue"]["embedding_dimension"] == 128
    assert by_id["cfg_k16"]["training"]["training"]["logical_k"] == 16
    assert by_id["cfg_intensity_20"]["training"]["training"]["profile_id"] == "strong_2.0x"
    assert by_id["cfg_ema_990"]["training"]["ema"]["coefficient"] == .990
    assert by_id["cfg_ip_0"]["training"]["objective"]["information_preservation_weight"] == 0
    assert by_id["cfg_lr_10"]["training"]["optimizer"]["peak_learning_rate"] == .01


def test_cache_reuse_matrix_is_family_and_view_explicit():
    contract = load_contract(ROOT / "config/p9_infrastructure.yml")
    main = validate_p8_bundle(P8, contract)["hyper"]["rows"][0]["bank_binding"]
    assert cache_requirements("FM", main)["geometry_feature_cache"]
    assert cache_requirements("A5", main)["relation_label_materialization"] == "generic_runtime_map"
    assert cache_requirements("SSV", main)["geometry_feature_cache"] is False
    assert cache_requirements("DS", main)["ds_raster_cache"] is True
    assert expected_geometry_cache_entries(8) == 20568
