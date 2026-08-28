from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from p4_deterministic_rng import base_digest, counter_block
from p5_fixed_queries import (
    PROFILE_ID,
    canonical_json,
    operation_digest_provider,
    p4_seed_regression_vector,
    query_seed_digest,
    query_seed_payload,
    stable_id,
    validate_query_gallery_records,
)


CONFIG = {
    "augmentation_contract_id": "mmc_065f894aea3f8475",
    "p4_accepted_augmenter_sha256": "79f429652e329e347a5ac849be96e0bb9a7f1ab396466a4dd60a20d5411c73b8",
    "p3_cache_id": "oscache_c89fa07e3d6cb1819a7994a6",
}


def test_seed_payload_is_canonical_and_namespace_separated():
    validation = query_seed_payload(CONFIG, "validation-query", "scn_x", 0)
    evaluation = query_seed_payload(CONFIG, "evaluation-query", "scn_x", 0)
    encoded = canonical_json(validation, newline=False)
    assert b" " not in encoded and b"\n" not in encoded
    assert list(json.loads(encoded)) == sorted(validation)
    assert query_seed_digest(validation) != query_seed_digest(evaluation)


def test_query_indices_are_exact_and_distinct():
    zero = query_seed_payload(CONFIG, "validation-query", "scn_x", 0)
    one = query_seed_payload(CONFIG, "validation-query", "scn_x", 1)
    assert query_seed_digest(zero) != query_seed_digest(one)
    with pytest.raises(ValueError):
        query_seed_payload(CONFIG, "validation-query", "scn_x", 2)


def test_wrong_namespace_is_blocked():
    with pytest.raises(ValueError):
        query_seed_payload(CONFIG, "training-bank", "scn_x", 0)


def test_operation_stream_separates_entity_attempt_and_operation():
    root = query_seed_digest(query_seed_payload(CONFIG, "validation-query", "scn_x", 0))
    provider = operation_digest_provider(root, PROFILE_ID, "scn_x", 0)
    values = {
        provider(PROFILE_ID, "scn_x", 0, "geometry", "road-1", 1),
        provider(PROFILE_ID, "scn_x", 0, "geometry", "road-1", 2),
        provider(PROFILE_ID, "scn_x", 0, "geometry", "road-2", 1),
        provider(PROFILE_ID, "scn_x", 0, "entity_removal", None, None),
    }
    assert len(values) == 4
    with pytest.raises(ValueError):
        provider(PROFILE_ID, "scn_x", 1, "geometry", "road-1", 1)


def test_environment_fields_do_not_change_scientific_seed():
    left = query_seed_payload(CONFIG, "validation-query", "scn_x", 0)
    expanded = {**CONFIG, "worker_count": 40, "timestamp": "now", "path": "/tmp/x"}
    right = query_seed_payload(expanded, "validation-query", "scn_x", 0)
    assert left == right
    assert query_seed_digest(left) == query_seed_digest(right)


def test_seed_field_change_changes_identity():
    left = query_seed_payload(CONFIG, "validation-query", "scn_x", 0)
    changed = copy.deepcopy(CONFIG)
    changed["augmentation_contract_id"] = "mmc_changed"
    right = query_seed_payload(changed, "validation-query", "scn_x", 0)
    assert query_seed_digest(left) != query_seed_digest(right)
    assert stable_id("fq_", left) != stable_id("fq_", right)


def test_p4_v2_training_seed_regression_vector_is_stable():
    expected = base_digest("main_1.0x", "scene-regression", 7, "geometry", "road-12", 3)
    vector = p4_seed_regression_vector()
    assert vector["payload_sha256"] == expected.hex()
    assert vector["uniform_block_sha256"] == counter_block(expected, "geometry_jitter_value", 4).hex()


def test_repeat_generation_is_byte_identical():
    payload = query_seed_payload(CONFIG, "evaluation-query", "scn_repeat", 1)
    assert canonical_json(payload, newline=False) == canonical_json(payload, newline=False)
    assert query_seed_digest(payload) == query_seed_digest(payload)


def test_supplement_does_not_reference_p4_membership():
    config = (ROOT / "config" / "p5_deterministic_queries.yml").read_text()
    assert "training_bank_membership: prohibited" in config
    assert "master_view_id" not in config
    assert "logical K8" not in config


def _records():
    galleries = [
        {"gallery_id": "g0", "scene_id": "s0"},
        {"gallery_id": "g1", "scene_id": "s1"},
    ]
    queries = []
    for scene in ("s0", "s1"):
        for index in (0, 1):
            queries.append({"query_id": f"q-{scene}-{index}", "namespace": "validation-query",
                            "split": "validation", "scene_id": scene, "query_index": index,
                            "profile_id": "main_1.0x", "positive_scene_id": scene,
                            "seed_digest": f"seed-{scene}-{index}"})
    return queries, galleries


def test_query_gallery_acceptance_contract():
    queries, galleries = _records()
    validate_query_gallery_records(queries, galleries, "validation", 2, {"s0", "s1"})


@pytest.mark.parametrize("mutation", ["population", "query_count", "same_seed", "positive",
                                      "training", "cross_split", "p4_reference", "missing_p3",
                                      "duplicate", "ordering"])
def test_query_gallery_adversarial_failures(mutation):
    queries, galleries = _records()
    valid = {"s0", "s1"}
    if mutation == "population":
        galleries.pop()
    elif mutation == "query_count":
        queries.pop()
    elif mutation == "same_seed":
        queries[1]["seed_digest"] = queries[0]["seed_digest"]
    elif mutation == "positive":
        queries[0]["positive_scene_id"] = "s1"
    elif mutation == "training":
        queries[0]["split"] = "training"
    elif mutation == "cross_split":
        queries[0]["namespace"] = "evaluation-query"
    elif mutation == "p4_reference":
        queries[0]["master_view_id"] = 0
    elif mutation == "missing_p3":
        valid.remove("s1")
    elif mutation == "duplicate":
        queries[1]["query_id"] = queries[0]["query_id"]
    elif mutation == "ordering":
        queries[0], queries[1] = queries[1], queries[0]
    with pytest.raises(ValueError):
        validate_query_gallery_records(queries, galleries, "validation", 2, valid)
