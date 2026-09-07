from __future__ import annotations

import sys
from pathlib import Path

import pytest
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from current_methodology import (COMPARISON_NAMES, active_raster_sources, build_ofat,
                                 build_plan, comparison_contracts, component_contracts,
                                 induced_subgraph, load_current_methodology,
                                 retained_entity_mask, source_contracts, validate_plan)
from model_families import SceneEncoder, family_contract
from model_data import filter_scene_sources


@pytest.fixture(scope="module")
def methodology():
    return load_current_methodology(ROOT / "config/current_methodology.yml")


def test_scene_split_and_contrastive_only_contract(methodology):
    assert methodology["scene_split"] == {"total_off_grid": 10_000, "validation": 1_000,
                                           "evaluation": 9_000, "minimum_training_center_distance_m": 50}
    assert methodology["model"]["d"] == methodology["model"]["d_c"] == 128
    assert methodology["model"]["information_preservation"] is False
    assert methodology["model"]["reconstruction_decoders"] is False
    assert methodology["training"]["objective"] == "symmetric_scene_contrastive"


def test_ofat_is_exactly_eleven_unique_configurations(methodology):
    rows = build_ofat(methodology)
    assert len(rows) == len({tuple(sorted(row.items())) for row in rows}) == 11
    assert {row["d"] for row in rows} == {64, 128, 256}
    assert {row["K_aug"] for row in rows} == {4, 8, 16}
    assert {row["augmentation_intensity"] for row in rows} == {0.5, 1.0, 2.0}
    assert {row["ema_momentum"] for row in rows} == {0.990, 0.999}
    assert {row["peak_learning_rate"] for row in rows} == {0.001, 0.002, 0.003, 0.005}
    assert all(row["d"] == row["d_c"] for row in rows)


def test_current_plan_has_content_addressed_identity(methodology):
    plan = build_plan(ROOT / "config/current_methodology.yml")
    validate_plan(plan, methodology)
    assert plan["plan_id"].startswith("s08plan_")
    changed = dict(plan, content_sha256="0" * 64)
    with pytest.raises(ValueError, match="identity"):
        validate_plan(changed, methodology)


def test_component_ablation_sequence_is_exact(methodology):
    rows = component_contracts()
    assert rows["A1"] == {"modalities": ("relative",), "fusion": False, "relation": "none", "scene_raster": False}
    assert rows["A2"]["modalities"] == ("relative", "geometry")
    assert rows["A3"]["modalities"] == ("relative", "geometry", "semantic", "environmental")
    assert rows["A4"]["relation"] == "generic"
    assert rows["A4"]["edge_policy"] == "exact_FM_directed_edges_preserve_direction_and_multiplicity"
    assert rows["A5"]["relation"] == "heterogeneous" and rows["A5"]["scene_raster"] is False
    assert rows["FM"]["scene_raster"] is True


def test_seventeen_comparison_contracts_and_b_source_sets(methodology):
    rows = comparison_contracts(methodology)
    assert tuple(row["name"] for row in rows) == COMPARISON_NAMES
    assert len(rows) == 17
    assert source_contracts() == {
        "FM": ("B", "R", "P", "LC", "DEM"), "B1": ("B", "R", "P"),
        "B2": ("B", "R"), "B3": ("B", "P"), "B4": ("R", "P"),
        "B5": ("B",), "B6": ("R",), "B7": ("P",),
        "B8": ("B", "R", "P", "LC"), "B9": ("B", "R", "P", "DEM"),
    }


def test_input_level_entity_removal_and_induced_subgraph():
    keep = retained_entity_mask(["B", "R", "P", "B"], ("B", "P"))
    assert keep == [True, False, True, True]
    edges = [(0, 1), (0, 2), (2, 3), (3, 0)]
    assert induced_subgraph(edges, keep) == [(0, 2), (2, 3), (3, 0)]

    scene = {
        "entities": [
            {"local_entity_id": 0, "entity_type": "B"},
            {"local_entity_id": 1, "entity_type": "R"},
            {"local_entity_id": 2, "entity_type": "P"},
        ],
        "contexts": {0: {"value": "B"}, 1: {"value": "R"}, 2: {"value": "P"}},
        "relations": [
            {"source_local_entity_id": 0, "destination_local_entity_id": 1, "relation": "SN"},
            {"source_local_entity_id": 0, "destination_local_entity_id": 2, "relation": "WIT"},
        ],
        "topology": [{"road_local_entity_id": 1}],
    }
    filtered = filter_scene_sources(scene, ("B", "P", "DEM"))
    assert [row["entity_type"] for row in filtered["entities"]] == ["B", "P"]
    assert filtered["relations"] == [scene["relations"][1]]
    assert filtered["topology"] == []
    assert filtered["active_raster_sources"] == ("DEM",)


def test_lc_only_and_dem_only_pathways_are_distinct():
    assert active_raster_sources(source_contracts()["B8"]) == ("LC",)
    assert active_raster_sources(source_contracts()["B9"]) == ("DEM",)
    assert family_contract("B8").retained_sources[-1] == "LC"
    assert family_contract("B9").retained_sources[-1] == "DEM"


def test_current_model_has_no_reconstruction_parameters(methodology):
    config = {"model": {"d": 128, "d_c": 128, "d_t": 16, "d_r": 32,
                         "attention_heads": 4, "head_dimension": 32, "ffn_dimension": 256,
                         "dropout": 0.2, "wavelengths": {"minimum_m": 10, "maximum_m": 1000, "count": 16},
                         "poi_hierarchy_dimensions": [8, 12, 16, 16, 24, 32]}}
    vocab = {name: 4 for name in ("A9", "A11", "ROAD_RANK", "ROAD_TYPE", *(f"CLASS_L{i}" for i in range(1, 7)))}
    model = SceneEncoder(config, vocab, "FM")
    forbidden = ("decoder", "reconstruction")
    assert not any(any(token in name for token in forbidden) for name, _ in model.named_parameters())
    assert model.dimension == 128
