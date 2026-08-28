from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest
import torch
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from p6_data import DeterministicSceneSampler, _poi_category_key, ragged_collate
from p6_model import ReducedSceneEncoder, RelationAwareLayer, parameter_counts


VOCABULARY = {
    "A9": 511, "A11": 24, "ROAD_RANK": 9, "ROAD_TYPE": 7,
    "CLASS_L1": 6, "CLASS_L2": 19, "CLASS_L3": 360,
    "CLASS_L4": 1001, "CLASS_L5": 1400, "CLASS_L6": 150,
}


def config():
    return yaml.safe_load((ROOT / "config" / "p6_model_dataloader.yml").read_text())


def sample(scene: str, entity_types=(0,), edges=(), relation_masks=(), source_nodes=0):
    count = len(entity_types)
    rows = {kind: [index for index, value in enumerate(entity_types) if value == kind]
            for kind in range(3)}
    coordinates = count * 2
    edge_index = (torch.tensor(edges, dtype=torch.int64).reshape((-1, 2)).T
                  if edges else torch.empty((2, 0), dtype=torch.int64))
    return {
        "scene_id": scene, "split": "training", "view_id": "original", "profile": None,
        "positive_scene_id": scene, "lineage": {"parent": "fixture"},
        "entities": {
            "local_entity_id": torch.arange(count), "entity_type": torch.tensor(entity_types),
            "relative_position_m": torch.zeros((count, 2)), "object_raster": torch.zeros((count, 26)),
            "modality_available": torch.ones((count, 4), dtype=torch.uint8),
            "building_row_index": torch.tensor(rows[0], dtype=torch.int64),
            "building_category": torch.zeros((len(rows[0]), 2), dtype=torch.int64),
            "building_numerical": torch.zeros((len(rows[0]), 2)),
            "building_missing": torch.zeros((len(rows[0]), 2), dtype=torch.uint8),
            "road_row_index": torch.tensor(rows[1], dtype=torch.int64),
            "road_category": torch.zeros((len(rows[1]), 2), dtype=torch.int64),
            "road_numerical": torch.zeros((len(rows[1]), 1)),
            "road_missing": torch.zeros((len(rows[1]), 1), dtype=torch.uint8),
            "poi_row_index": torch.tensor(rows[2], dtype=torch.int64),
            "poi_category": torch.zeros((len(rows[2]), 6), dtype=torch.int64),
        },
        "geometry": {
            "coordinates_xy_m": torch.zeros((coordinates, 2)),
            "coordinates_xy_m_scientific": torch.zeros((coordinates, 2), dtype=torch.float64),
            "geometry_type": torch.zeros(count, dtype=torch.int64),
            "geometry_available": torch.ones(count, dtype=torch.uint8),
            "entity_coordinate_offsets": torch.arange(0, coordinates + 1, 2),
            "entity_part_offsets": torch.arange(count + 1),
            "part_coordinate_offsets": torch.arange(0, coordinates + 1, 2),
            "entity_component_offsets": torch.arange(count + 1),
            "component_coordinate_offsets": torch.arange(0, coordinates + 1, 2),
            "entity_ring_offsets": torch.zeros(count + 1, dtype=torch.int64),
            "ring_coordinate_start": torch.empty(0, dtype=torch.int64),
            "ring_coordinate_end": torch.empty(0, dtype=torch.int64),
            "ring_is_hole": torch.empty(0, dtype=torch.uint8),
            "ring_component_index": torch.empty(0, dtype=torch.int64),
        },
        "edges": {
            "edge_index": edge_index,
            "relation_mask": torch.tensor(relation_masks, dtype=torch.uint8),
        },
        "topology": {
            "source_chain_offsets": torch.tensor([0, source_nodes], dtype=torch.int64) if source_nodes else torch.tensor([0]),
            "source_chain_road_index": torch.tensor([rows[1][0]], dtype=torch.int64) if source_nodes else torch.empty(0, dtype=torch.int64),
            "source_node_xy_5186": torch.zeros((source_nodes, 2), dtype=torch.float64),
            "source_node_ids": [f"n{x}" for x in range(source_nodes)],
        },
        "rasters": {
            "landcover_class_fraction": torch.zeros((22, 100, 100)),
            "landcover_valid_mask": torch.ones((100, 100), dtype=torch.uint8),
            "landcover_valid_support": torch.ones((100, 100)),
            "dem_standardized_mean": torch.zeros((17, 17)),
            "dem_valid_mask": torch.ones((17, 17), dtype=torch.uint8),
            "dem_valid_support": torch.ones((17, 17)),
        },
        "resources": {"nodes": count, "ordered_edges": len(relation_masks),
                      "coordinates": coordinates, "source_nodes": source_nodes},
    }


def test_reduced_dimensions_and_parameter_manifest():
    model = ReducedSceneEncoder(config(), VOCABULARY)
    assert model.relation_layers[0].heads == 4
    assert model.relation_layers[0].head_dimension == 16
    assert model.relation_layers[0].dropout.p == 0.2
    assert parameter_counts(model)["total"] == 934420


def test_wrong_reduced_dimensions_are_blocked():
    changed = config(); changed["model"]["d"] = 128
    with pytest.raises(ValueError, match="dimension contract"):
        ReducedSceneEncoder(changed, VOCABULARY)


def test_relation_projection_accepts_d32_and_empty_edges():
    layer = RelationAwareLayer(); layer.eval()
    values = torch.zeros((2, 64))
    empty = layer(values, torch.empty((2, 0), dtype=torch.int64), torch.empty((0, 32)))
    linked = layer(values, torch.tensor([[0], [1]]), torch.zeros((1, 32)))
    assert empty.shape == linked.shape == (2, 64)
    assert torch.isfinite(empty).all() and torch.isfinite(linked).all()


def test_ragged_collation_rebases_edges_and_variable_topology():
    first = sample("a", (0, 1), ((0, 1),), (17,), source_nodes=3)
    second = sample("b", (2, 1), ((0, 1),), (3,), source_nodes=2)
    batch = ragged_collate([first, second])
    assert batch["scene_ptr"].tolist() == [0, 2, 4]
    assert batch["edges"]["edge_index"].tolist() == [[0, 2], [1, 3]]
    assert batch["edges"]["relation_mask"].tolist() == [17, 3]
    assert batch["topology"]["source_chain_offsets"].tolist() == [0, 3, 5]
    assert batch["topology"]["source_chain_road_index"].tolist() == [1, 3]


def test_empty_types_and_relations_do_not_create_dummy_rows():
    batch = ragged_collate([sample("poi", (2,))])
    assert batch["entities"]["building_row_index"].numel() == 0
    assert batch["entities"]["road_row_index"].numel() == 0
    assert batch["edges"]["edge_index"].shape == (2, 0)
    assert batch["topology"]["source_node_ids"] == []


def test_relation_multi_mask_is_preserved():
    mask = 1 | 4 | 16
    batch = ragged_collate([sample("multi", (0, 1), ((0, 1),), (mask,))])
    assert batch["edges"]["relation_mask"].item() == mask


def test_deterministic_sampler_membership_and_seed():
    left = list(DeterministicSceneSampler(50, 7))
    assert left == list(DeterministicSceneSampler(50, 7))
    assert left != list(DeterministicSceneSampler(50, 8))
    assert sorted(left) == list(range(50))
    assert list(DeterministicSceneSampler(5, 7, shuffle=False)) == list(range(5))


def test_poi_terminal_dash_is_missing_after_augmentation_delta():
    vocabulary = {f"CLASS_L{x}": {"missing_codes": []} for x in range(1, 7)}
    vocabulary["CLASS_L5"]["missing_codes"] = ["F00"]
    row = {f"CLASS_L{x}_CODE": value for x, value in enumerate(
        ("A02", "A03", "A169", "D04", "F00", "G00"), start=1)}
    assert _poi_category_key(row, 4, vocabulary) == "A02/A03/A169/D04"
    assert _poi_category_key(row, 5, vocabulary) is None
    assert _poi_category_key(row, 6, vocabulary) is None


def test_collator_rejects_empty_batch():
    with pytest.raises(ValueError, match="empty batch"):
        ragged_collate([])


def test_batch_input_is_not_mutated():
    fixture = sample("stable", (0, 1), ((0, 1),), (1,))
    original = copy.deepcopy(fixture)
    ragged_collate([fixture])
    assert torch.equal(fixture["edges"]["edge_index"], original["edges"]["edge_index"])
