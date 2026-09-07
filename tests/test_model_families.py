from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from current_methodology import COMPARISON_NAMES, source_contracts
from model_families import SceneEncoder, family_contract


def model_config(d=128):
    return {"model": {"d": d, "d_c": d, "d_t": 16, "d_r": 32,
        "attention_heads": 4, "head_dimension": d // 4, "ffn_dimension": 2 * d,
        "dropout": 0.2, "wavelengths": {"minimum_m": 10, "maximum_m": 1000, "count": 16},
        "poi_hierarchy_dimensions": [8, 12, 16, 16, 24, 32]}}


def vocabulary():
    return {name: 8 for name in ("A9", "A11", "ROAD_RANK", "ROAD_TYPE",
                                  *(f"CLASS_L{i}" for i in range(1, 7)))}


def test_registry_is_current_seventeen_model_set():
    assert tuple(family_contract(name).name for name in COMPARISON_NAMES) == COMPARISON_NAMES


@pytest.mark.parametrize("dimension", (64, 128, 256))
def test_current_dimensions_construct_without_decoders(dimension):
    model = SceneEncoder(model_config(dimension), vocabulary(), "FM")
    assert model.dimension == dimension
    assert not any("decoder" in name or "reconstruction" in name for name, _ in model.named_parameters())


def test_component_family_contracts_match_nested_sequence():
    assert family_contract("A1").modalities == ("relative",)
    assert not hasattr(SceneEncoder(model_config(), vocabulary(), "A1"), "gates")
    assert family_contract("A2").modalities == ("relative", "geometry")
    assert family_contract("A3").relation == "none"
    assert family_contract("A4").relation == "generic"
    assert family_contract("A5").relation == "heterogeneous" and not family_contract("A5").scene_raster
    assert family_contract("FM").scene_raster


def test_b_series_retained_sources_and_raster_pathways():
    for name, sources in source_contracts().items():
        assert family_contract(name).retained_sources == sources
    assert SceneEncoder(model_config(), vocabulary(), "B8").raster_sources == ("LC",)
    assert SceneEncoder(model_config(), vocabulary(), "B9").raster_sources == ("DEM",)
    assert SceneEncoder(model_config(), vocabulary(), "B8").object_raster_encoder[0].in_features == 23
    assert SceneEncoder(model_config(), vocabulary(), "B9").object_raster_encoder[0].in_features == 3


def test_a4_and_a5_relation_embedding_identity():
    a4 = SceneEncoder(model_config(), vocabulary(), "A4")
    a5 = SceneEncoder(model_config(), vocabulary(), "A5")
    assert a4.relation_embedding.num_embeddings == 1
    assert a5.relation_embedding.num_embeddings == 5
