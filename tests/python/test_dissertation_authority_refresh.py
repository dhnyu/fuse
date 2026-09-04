from __future__ import annotations

import hashlib
import json
from pathlib import Path

import jsonschema
import yaml

from p9_v2_canonical import canonical_sha256


ROOT = Path(__file__).resolve().parents[2]
DISSERTATION = ROOT.parent / "dhnyu-masters-dissertation"


def _load(name: str) -> dict:
    return json.loads((ROOT / "config" / name).read_text())


def _validate(document: str, schema: str) -> dict:
    value = _load(document)
    definition = json.loads((ROOT / "config/schemas" / schema).read_text())
    jsonschema.Draft202012Validator.check_schema(definition)
    jsonschema.Draft202012Validator(definition).validate(value)
    return value


def _assert_identity(value: dict, identity_key: str, prefix: str) -> None:
    preimage = {
        key: item
        for key, item in value.items()
        if key not in {identity_key, "content_sha256"}
    }
    digest = canonical_sha256(preimage)
    assert value["content_sha256"] == digest
    assert value[identity_key] == f"{prefix}{digest[:24]}"


def test_latest_dissertation_authority_is_hash_bound_and_readable() -> None:
    authority = _validate(
        "dissertation_authority_refresh.json",
        "dissertation_authority_refresh.schema.json",
    )
    _assert_identity(authority, "authority_id", "disauth_")
    assert authority["dissertation"]["commit"] == "4adbd49b6dacab589d2fa99d88ec5be83aceb287"
    if DISSERTATION.exists():
        for document in authority["dissertation"]["documents"]:
            path = DISSERTATION / document["logical_path"]
            assert hashlib.sha256(path.read_bytes()).hexdigest() == document["sha256"]


def test_selected_full_model_matches_latest_dissertation_dimensions() -> None:
    selected = _load("dissertation_authority_refresh.json")["selected_full_model"]
    assert selected["configuration_id"] == "cfg_d128"
    assert selected["acceptance_id"] == "p9accv2_a1c00e32a882ddc4b7e2677b"
    assert selected["checkpoint_id"] == "p9ck_56195e9ea3cd45d80cf5e23c"
    assert selected["dimensions"] == {
        "d": 128,
        "d_c": 128,
        "d_t": 16,
        "d_r": 32,
        "d_a": 32,
        "poi_hierarchy": [8, 12, 16, 16, 24, 32],
        "poi_common_projection": 32,
        "land_cover_embedding": 16,
        "attention_heads": 4,
        "per_head": 32,
        "relation_ffn": [128, 256, 128],
        "fusion_input": 640,
        "final_scene_representation": 128,
        "mask_embedding": 128,
        "contrastive_head": [128, 256, 128],
        "land_cover_cnn_channels": [64, 128, 128],
        "dem_cnn_channels": [64, 128, 128],
    }


def test_existing_model_shape_contract_matches_selected_architecture() -> None:
    model = yaml.safe_load((ROOT / "config/model_architecture.yml").read_text())
    dims = model["dimensions"]
    architecture = model["architecture"]
    assert dims == {
        "latent": 128,
        "type_embedding": 16,
        "relation_embedding": 32,
        "categorical_embedding": 32,
        "poi_hierarchy_embeddings": [8, 12, 16, 16, 24, 32],
        "poi_common_projection": 32,
        "landcover_embedding": 16,
        "contrastive": 128,
    }
    assert architecture["attention_heads"] == 4
    assert architecture["head_dimension"] == 32
    assert architecture["final_fusion_input"] == 640
    assert architecture["raster"]["conv_channels"] == [64, 128, 128]


def test_historical_cfg_main_is_not_relabelled_or_rewritten() -> None:
    reference = _load("dissertation_authority_refresh.json")["historical_reference"]
    assert reference["configuration_id"] == "cfg_main"
    assert reference["reporting_alias"] == "cfg_d64"
    assert reference["d"] == 64
    assert reference["identity_rewrite"] is False


def test_active_v2_controller_binds_latest_authority_without_rewriting_history() -> None:
    active = yaml.safe_load((ROOT / "config/p9_v2_training_controller.yml").read_text())
    authority = _load("dissertation_authority_refresh.json")
    assert active["source"]["dissertation_commit"] == authority["dissertation"]["commit"]
    assert active["source"]["dissertation_authority_id"] == authority["authority_id"]
    historical = yaml.safe_load((ROOT / "config/p8_formal_experiment_plan.yml").read_text())
    assert historical["methodology"]["dissertation_commit"] == (
        "ad8c8b5c17c5ca72dce7f30c2eb283f6041dbc9a"
    )


def test_living_population_v2_contract_closes_latest_partial_support_rule() -> None:
    authority = _load("dissertation_authority_refresh.json")
    decision = _validate(
        "p11_methodology_decision_v2.json",
        "p11_methodology_decision_v2.schema.json",
    )
    _assert_identity(decision, "decision_id", "p11meth_")
    contract = _validate(
        "p11_living_population_source_contract_v2.json",
        "p11_downstream_source_contract_v2.schema.json",
    )
    _assert_identity(contract, "contract_id", "p11src_")
    assert decision["dissertation_authority_id"] == authority["authority_id"]
    assert contract["methodology_authority"]["methodology_decision_id"] == decision["decision_id"]
    semantics = contract["semantic_contract"]
    assert "without extrapolation" in semantics["scene_hour_mapping"]
    assert semantics["eligibility_rule"] == (
        "at least one valid hourly scene-level observation in the temporal class"
    )
    assert decision["unspecified_scientific_decision_count"] == 0


def test_rematerialization_contract_preserves_superseded_dataset() -> None:
    future = yaml.safe_load(
        (ROOT / "config/p11_downstream_preprocessing_v2.yml").read_text()
    )
    current = yaml.safe_load((ROOT / "config/p11_downstream_dataset.yml").read_text())
    assert future["status"] == "AUTHORIZED_FOR_LIVING_REMATERIALIZATION"
    assert future["current_immutable_dataset"] == current["supersedes"]
    assert future["accepted_output"] == current["dataset_id"]
    assert (
        future["accepted_living_population_shard"]
        == current["living_population_shard_id"]
    )
    assert future["living_population"]["minimum_valid_scene_hours"] == 1
    assert future["living_population"]["extrapolate_missing_spatial_support"] is False
    assert current["dataset_id"] == "p11ds_39607da2de792ad6b3c9bb30"
    assert current["supersedes"] == "p11ds_fdb1f34c6daeda259e803e37"
