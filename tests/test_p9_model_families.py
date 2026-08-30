import copy
from pathlib import Path
import sys

import pytest
import torch
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from p6_model import ReducedSceneEncoder
from p7_training import P7Model, reconstruction_terms
from p9_model_families import (FAMILY_NAMES, P9SceneEncoder, active_parameter_names, build_scene_encoder,
                               ds_raster_from_batch, family_contract, p9_reconstruction_terms)


def model_config(d=64):
    value = yaml.safe_load((ROOT / "config/p6_model_dataloader.yml").read_text())
    value["model"].update({"d": d, "d_c": d, "head_dimension": d // 4, "ffn_dimension": 2 * d})
    return value


def vocabulary():
    return {name: 8 for name in ("A9", "A11", "ROAD_RANK", "ROAD_TYPE", *(f"CLASS_L{x}" for x in range(1, 7)))}


def masks(): return {name: 7 for name in vocabulary()}


def batch(valid_dem=True):
    nodes = 4
    entity_type = torch.tensor([0, 1, 2, 0])
    part = torch.tensor([[-1., -1.], [1., -1.], [1., 1.], [-1., 1.], [-1., -1.],
                         [-4., 0.], [4., 0.], [-1., -1.], [1., -1.], [1., 1.], [-1., 1.], [-1., -1.]], dtype=torch.float64)
    ring = torch.tensor([[-1., -1.], [1., -1.], [1., 1.], [-1., 1.], [-1., -1.],
                         [-1., -1.], [1., -1.], [1., 1.], [-1., 1.], [-1., -1.]], dtype=torch.float64)
    return {
        "scene_ids": ["s0"], "entity_scene_index": torch.zeros(nodes, dtype=torch.long),
        "entities": {
            "local_entity_id": torch.arange(nodes), "entity_type": entity_type,
            "relative_position_m": torch.tensor([[0., 0.], [20., 0.], [0., 20.], [-20., 0.]]),
            "object_raster": torch.rand(nodes, 26), "modality_available": torch.tensor([[1,1,1,1],[1,1,1,1],[1,0,1,1],[1,1,1,1]], dtype=torch.uint8),
            "building_row_index": torch.tensor([0,3]), "building_category": torch.tensor([[1,2],[2,1]]),
            "building_numerical": torch.rand(2,2), "building_missing": torch.zeros(2,2,dtype=torch.uint8),
            "road_row_index": torch.tensor([1]), "road_category": torch.tensor([[1,2]]),
            "road_numerical": torch.rand(1,1), "road_missing": torch.zeros(1,1,dtype=torch.uint8),
            "poi_row_index": torch.tensor([2]), "poi_category": torch.ones(1,6,dtype=torch.long),
        },
        "edges": {"edge_index": torch.tensor([[0,1,2],[1,2,3]]), "relation_mask": torch.tensor([1,3,16],dtype=torch.uint8)},
        "geometry": {
            "part_coordinates_xy_m_scientific": part, "entity_coordinate_offsets": torch.tensor([0,5,7,7,12]),
            "entity_part_offsets": torch.tensor([0,1,2,2,3]), "part_coordinate_offsets": torch.tensor([0,5,7,12]),
            "ring_coordinates_xy_m_scientific": ring, "entity_ring_offsets": torch.tensor([0,1,1,1,2]),
            "ring_coordinate_start": torch.tensor([0,5]), "ring_coordinate_end": torch.tensor([5,10]),
            "ring_is_hole": torch.tensor([0,0],dtype=torch.uint8), "ring_component_index": torch.tensor([0,2]),
        },
        "rasters": {
            "landcover_class_fraction": torch.rand(1,22,100,100),
            "landcover_valid_mask": torch.ones(1,100,100,dtype=torch.uint8),
            "landcover_intentional_mask": torch.zeros(1,100,100,dtype=torch.uint8),
            "dem_standardized_mean": torch.rand(1,17,17),
            "dem_valid_mask": torch.full((1,17,17), int(valid_dem), dtype=torch.uint8),
        },
    }


@pytest.mark.parametrize("d", [48, 64, 128])
def test_fm_dimensions_forward_backward(d):
    model = P9SceneEncoder(model_config(d), vocabulary(), "FM")
    value = batch(); geometry = (torch.rand(4,128), torch.rand(4,256))
    output = model(value, geometry, assignments=torch.tensor([0,1,2,3]))
    terms=p9_reconstruction_terms(model,value,geometry,output["modalities"],masks())
    loss=output["scene_embedding"].square().sum()+output["contrastive_embedding"].square().sum()+sum(row["sum"] for row in terms.values())
    loss.backward()
    assert output["scene_embedding"].shape == (1,d)
    assert all(parameter.grad is not None for parameter in model.parameters() if parameter.requires_grad)


@pytest.mark.parametrize("family", FAMILY_NAMES)
def test_family_registry_active_modules_and_backward(family):
    model = P9SceneEncoder(model_config(), vocabulary(), family)
    value = batch(); geometry = (torch.rand(4,128), torch.rand(4,256))
    if family == "DS": output = model(value, ds_raster=ds_raster_from_batch(value)); terms={}
    else:
        assignments = torch.zeros(4,dtype=torch.long)
        output = model(value, geometry if "geometry" in family_contract(family).modalities else None, assignments=assignments)
        terms=p9_reconstruction_terms(model,value,geometry if "geometry" in family_contract(family).modalities else None,output["modalities"],masks())
    (output["scene_embedding"].square().sum()+sum(row["sum"] for row in terms.values())).backward()
    assert tuple(terms)==family_contract(family).ip_terms
    names = active_parameter_names(model)
    if family in ("A1","A2","A3","A4","SSV"): assert not any("relation_" in name for name in names)
    if family == "A5": assert model.relation_embedding.num_embeddings == 1
    if family == "DS": assert not any(token in name for name in names for token in ("gates", "relation", "position_encoder"))


def test_a5_preserves_edge_instances_and_uses_one_label():
    value = batch(); before = value["edges"]["edge_index"].clone()
    model = P9SceneEncoder(model_config(), vocabulary(), "A5")
    model(value, (torch.rand(4,128), torch.rand(4,256)))
    assert torch.equal(before, value["edges"]["edge_index"])
    assert model.relation_embedding.num_embeddings == 1


def test_ds_shape_determinism_mask_and_invalid_support():
    value = batch(); value["rasters"]["landcover_intentional_mask"][:,10,10] = 1
    first = ds_raster_from_batch(value); second = ds_raster_from_batch(copy.deepcopy(value))
    assert first.shape == (1,26,100,100) and torch.equal(first,second)
    assert torch.equal(first[:,3:25,10,10], torch.zeros(1,22))
    with pytest.raises(ValueError, match="complete valid DEM"):
        ds_raster_from_batch(batch(valid_dem=False))


def test_nested_modality_and_ip_contracts():
    assert family_contract("A2").modalities == (*family_contract("A1").modalities, "semantic")
    assert family_contract("A3").modalities == (*family_contract("A2").modalities, "environmental")
    assert set(family_contract("A2").modalities) - set(family_contract("SSV").modalities) == {"geometry"}
    assert family_contract("DS").lambda_ip == 0 and family_contract("DS").ip_terms == ()


def test_cfg_main_factory_reuses_exact_p7_encoder_namespace():
    expected = ReducedSceneEncoder(model_config(), vocabulary())
    observed = build_scene_encoder(model_config(), vocabulary(), "FM")
    assert isinstance(observed, ReducedSceneEncoder)
    assert {name: tuple(value.shape) for name, value in observed.state_dict().items()} == {
        name: tuple(value.shape) for name, value in expected.state_dict().items()
    }
    assert isinstance(build_scene_encoder(model_config(48), vocabulary(), "FM"), P9SceneEncoder)
    assert isinstance(build_scene_encoder(model_config(128), vocabulary(), "FM"), P9SceneEncoder)


def test_production_vocabulary_parameter_counts():
    from p6_data import build_vocabulary
    runtime = yaml.safe_load((ROOT / "config/p7_cold_path_runtime.yml").read_text())["inputs"]
    sizes = {name: int(value["size"]) for name, value in build_vocabulary(runtime["categories"]).items()}
    expected = {"FM": 934420, "A1": 233587, "A2": 638778, "A3": 660180,
                "A4": 827316, "A5": 934292, "SSV": 479930, "DS": 97056}
    observed = {
        family: sum(parameter.numel() for parameter in build_scene_encoder(
            model_config(), sizes, family).parameters() if parameter.requires_grad)
        for family in FAMILY_NAMES
    }
    assert observed == expected


def test_fm_reconstruction_objective_matches_p7_exactly():
    model = ReducedSceneEncoder(model_config(), vocabulary())
    model.contract = family_contract("FM")
    value = batch(); value["category_mask_indices"] = masks()
    geometry = (torch.rand(4, 128), torch.rand(4, 256))
    modalities = P7Model._modalities(model, value, geometry)
    objective = {"huber_delta": 1.0, "phase_relative_magnitude_threshold": 0.05}
    expected = reconstruction_terms(model, value, geometry, modalities, objective)
    observed = p9_reconstruction_terms(model, value, geometry, modalities, masks())
    for name in model.contract.ip_terms:
        assert torch.equal(observed[name]["sum"], expected["modalities"][name]["sum"])
        assert int(observed[name]["count"]) == int(expected["modalities"][name]["count"])
