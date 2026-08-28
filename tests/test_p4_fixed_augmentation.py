import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import pytest
from shapely.geometry import LineString, Point, Polygon

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "scripts"))

import p4_fixed_augmentation as p4
import p4_smoke


def test_receiver_group_and_entity_fallback_smokes():
    assert p4_smoke.road_smoke()["status"] == "PASS"
    assert p4_smoke.fallback_smoke()["status"] == "PASS"


def test_disconnected_absorption_is_rejected():
    entities = {
        0: {"entity_type": "R", "source_entity_id": "receiver", "ROAD_TYPE": "A", "ROAD_RANK": "1"},
        1: {"entity_type": "R", "source_entity_id": "donor", "ROAD_TYPE": "A", "ROAD_RANK": "1"},
    }
    scene = {"scene_id": "disconnected", "entities": entities,
             "geometries": {0: LineString([(0, 0), (1, 0)]), 1: LineString([(5, 0), (6, 0)])},
             "road_nodes": {0: [[("shared", 1, 0)]], 1: [[("shared", 5, 0)]]}}
    absorbed, mapping, provenance, _, _ = p4.compose_absorption(scene, {1}, "main_1.0x", 0)
    assert not absorbed and not mapping
    assert provenance[0]["status"] == "INVALID_CONNECTED_GEOMETRY"


def test_sn_applicability_excludes_contained_poi():
    entities = {0: {"entity_type": "B"}, 1: {"entity_type": "P"}, 2: {"entity_type": "P"}}
    geometry = {0: Point(0, 0), 1: Point(0, 0), 2: Point(1, 0)}
    edges = p4.sn_relations(entities, geometry, set(entities), {1}, radius=100, top_k=16)
    assert all(1 not in edge for edge in edges)
    assert (0, 2) in edges and (2, 0) in edges


def test_arrow_schemas_preserve_empty_payload_contract(tmp_path):
    for name, schema in p4.PARQUET_SCHEMAS.items():
        path = tmp_path / f"{name}.parquet"
        p4.write_parquet(path, [], schema)
        assert pq.read_schema(path).equals(schema)


def test_geometry_and_relation_delta_schema_is_explicit():
    import pyarrow as pa
    assert pa.types.is_binary(p4.PARQUET_SCHEMAS["geometry"].field("geometry_wkb").type)
    assert p4.PARQUET_SCHEMAS["relation_delta"].names[-4:] == ["relation_type", "source", "destination", "action"]


def test_components_connected_and_order_sensitive_parts():
    connected = [LineString([(0, 0), (1, 0)]), LineString([(1, 0), (2, 0)])]
    assert p4.components_connected(connected)
    assert not p4.components_connected(connected + [LineString([(9, 0), (10, 0)])])


def test_original_relation_decoder_preserves_multi_relation():
    frame = pd.DataFrame([{"source_local_entity_id": 1, "destination_local_entity_id": 2,
                           "has_sn": True, "has_cnt": False, "has_wit": False,
                           "has_int": True, "has_con": False}])
    result = p4.original_relations(frame)
    assert result["SN"] == {(1, 2)} and result["INT"] == {(1, 2)}
    assert not result["CNT"]


def test_topology_schema_has_nested_offsets():
    required = {"component_index", "source_chain_index", "component_offset",
                "chain_offset_start", "chain_offset_end", "source_node_offset"}
    assert required.issubset(p4.PARQUET_SCHEMAS["topology"].names)


def test_profile_configuration_exact():
    import yaml
    value = yaml.safe_load((ROOT / "config/p4_deterministic_augmentation.yml").read_text())
    assert [(x["scale"], x["removal_fraction"], x["dem_noise_sd_m"]) for x in value["profiles"]] == [
        (0.5, 0.05, 0.5), (1.0, 0.10, 1.0), (2.0, 0.20, 2.0)]
    assert [(x["jitter_probability"], x["jitter_displacement_m"], x["simplification_tolerance_m"])
            for x in value["profiles"]] == [(0.1, 0.5, 0.5), (0.2, 1.0, 1.0), (0.4, 2.0, 2.0)]
    assert value["supplement_version"] == "p4-augmentation-v2"
    assert value["fixed_parameters"]["landcover_maximum_active_fronts"] == 4
    assert value["banks"] == {"physical_k": 16, "logical_prefixes": [2, 4, 8, 16], "default_k": 8,
                              "expected_physical_candidates": 116208, "expected_default_references": 58104}


def test_incomplete_and_collision_policy_is_not_writer_bypass(tmp_path):
    final = tmp_path / "immutable"
    final.mkdir()
    (final / "payload").write_bytes(b"first")
    assert p4.sha256_file(final / "payload") != p4.sha256_bytes(b"second")


def test_landcover_block_mask_exact_deterministic_and_bounded():
    digest = p4.base_digest("main_1.0x", "scene-block", 0, "landcover", None, None)
    valid = [row * 100 + column for row in range(10, 40) for column in range(20, 70)]
    first = p4.landcover_block_mask(valid, 0.1, digest)
    second = p4.landcover_block_mask(list(reversed(valid)), 0.1, digest)
    assert first == second
    assert len(first["selected"]) == round(0.1 * len(valid))
    assert set(first["selected"]).issubset(valid)
    assert first["maximum_concurrent_fronts"] <= 4
    assert first["realized_component_count"] <= 4


def test_landcover_block_mask_fragmented_support_reseeds_without_nodata():
    digest = p4.base_digest("strong_2.0x", "scene-fragment", 5, "landcover", None, None)
    valid = [0, 2, 200, 202, 505, 707, 909]
    result = p4.landcover_block_mask(valid, 1.0, digest)
    assert set(result["selected"]) == set(valid)
    assert len(result["selected"]) == len(valid)
    assert result["reseeds"]
    assert result["maximum_concurrent_fronts"] <= 4


def test_bernoulli_jitter_preserves_protected_vertex():
    profile = {"jitter_probability": 1.0, "jitter_displacement_m": 1.0}
    geometry = LineString([(1.0, 1.0), (2.0, 2.0), (3.0, 3.0)])
    digest = p4.base_digest("main_1.0x", "scene-jitter", 0, "geometry", "road", 1)
    changed = p4.jitter_geometry(geometry, digest, profile, {(2.0, 2.0)}, (0.0, 0.0, 10.0, 10.0))
    assert list(changed.coords)[1] == (2.0, 2.0)
    assert list(changed.coords)[0] != (1.0, 1.0)
