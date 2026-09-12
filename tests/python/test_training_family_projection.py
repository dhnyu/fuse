import copy
from pathlib import Path
import pytest
import torch
import yaml
from training_family_inputs import *
from training_support import modality_assignments, state_content_digest


def fixture(types=(0, 1, 2, 0)):
    n = len(types)
    ids = torch.arange(10, 10 + n)
    types = torch.tensor(types, dtype=torch.int64)
    e = {
        "local_entity_id": ids,
        "entity_type": types,
        "relative_position_m": torch.arange(n * 2, dtype=torch.float32).reshape(n, 2),
        "object_raster": torch.arange(n * 26, dtype=torch.float32).reshape(n, 26),
        "modality_available": torch.tensor(
            [[1, int(t != 2), 1, 1] for t in types], dtype=torch.uint8
        ).reshape(n, 4),
    }
    for i, prefix in enumerate(("building", "road", "poi")):
        rows = torch.where(types == i)[0]
        e[prefix + "_row_index"] = rows
        e[prefix + "_category"] = torch.zeros(
            (len(rows), 6 if prefix == "poi" else 2), dtype=torch.int64
        )
        if prefix != "poi":
            e[prefix + "_numerical"] = torch.zeros(
                (len(rows), 2 if prefix == "building" else 1)
            )
            e[prefix + "_missing"] = torch.zeros_like(
                e[prefix + "_numerical"], dtype=torch.uint8
            )
    g = {
        k: torch.arange(n * 2, dtype=torch.float64).reshape(n, 2)
        for k in (
            "part_coordinates_xy_m",
            "part_coordinates_xy_m_scientific",
            "ring_coordinates_xy_m",
            "ring_coordinates_xy_m_scientific",
        )
    }
    g.update(
        {
            k: torch.arange(n + 1)
            for k in (
                "entity_coordinate_offsets",
                "entity_part_offsets",
                "part_coordinate_offsets",
                "entity_component_offsets",
                "component_coordinate_offsets",
                "entity_ring_offsets",
            )
        }
    )
    g.update(
        geometry_type=types.clone(),
        geometry_available=(types != 2).to(torch.uint8),
        ring_coordinate_start=torch.arange(n),
        ring_coordinate_end=torch.arange(1, n + 1),
        ring_is_hole=torch.zeros(n, dtype=torch.uint8),
        ring_component_index=torch.arange(n),
    )
    edges = (
        torch.tensor([[0, 1, 0, 2, 1, 0], [1, 0, 2, 0, 3, 1]], dtype=torch.int64)
        if n == 4
        else torch.empty((2, 0), dtype=torch.int64)
    )
    roads = torch.where(types == 1)[0]
    return {
        "scene_id": "scene_a",
        "split": "training",
        "view_id": 0,
        "profile": "main_1.0x",
        "positive_scene_id": "scene_a",
        "lineage": {},
        "geometry_layout_version": "3.0.0",
        "scene_center_5186": torch.tensor([0.0, 0.0]),
        "entities": e,
        "geometry": g,
        "edges": {
            "edge_index": edges,
            "relation_mask": (
                torch.tensor([1, 2, 4, 8, 16, 3], dtype=torch.uint8)
                if n == 4
                else torch.empty(0, dtype=torch.uint8)
            ),
        },
        "topology": {
            "source_chain_offsets": torch.arange(len(roads) + 1),
            "source_chain_road_index": roads,
            "source_node_xy_5186": torch.zeros((len(roads), 2)),
            "source_node_ids": [str(i) for i in roads.tolist()],
        },
        "rasters": {
            "landcover_class_fraction": torch.ones(22, 2, 2),
            "landcover_valid_mask": torch.ones(2, 2),
            "dem_standardized_mean": torch.ones(2, 2),
            "dem_valid_mask": torch.ones(2, 2),
        },
        "resources": {
            "nodes": n,
            "ordered_edges": edges.shape[1],
            "part_coordinates": n,
            "ring_coordinates": n,
            "coordinates": 2 * n,
            "source_nodes": len(roads),
        },
    }


CONFIG = yaml.safe_load(
    (Path(__file__).resolve().parents[2] / "config/training.yml").read_text()
)


@pytest.mark.parametrize(
    "family,expected,width",
    [
        (f"B{i}", x, w)
        for i, x, w in [
            (1, {0, 1, 2}, 0),
            (2, {0, 1}, 0),
            (3, {0, 2}, 0),
            (4, {1, 2}, 0),
            (5, {0}, 0),
            (6, {1}, 0),
            (7, {2}, 0),
            (8, {0, 1, 2}, 23),
            (9, {0, 1, 2}, 3),
        ]
    ],
)
def test_source_projection(family, expected, width):
    s = fixture()
    before = state_content_digest(s)
    p, m = project(s, family)
    assert set(p["entities"]["entity_type"].tolist()) == expected
    assert p["entities"]["object_raster"].shape[1] == width
    assert state_content_digest(s) == before
    old = s["edges"]
    rows = m["retained_rows"]
    rev = {int(x): i for i, x in enumerate(rows)}
    edges = [
        (rev[int(u)], rev[int(v)], int(mask))
        for (u, v), mask in zip(old["edge_index"].T, old["relation_mask"])
        if int(u) in rev and int(v) in rev
    ]
    assert [
        (int(u), int(v), int(mask))
        for (u, v), mask in zip(p["edges"]["edge_index"].T, p["edges"]["relation_mask"])
    ] == edges
    fourier = (torch.arange(12).reshape(4, 3), torch.arange(20).reshape(4, 5))
    got = project_fourier(fourier, m, p["entities"]["local_entity_id"])
    assert all(torch.equal(x, y[rows]) for x, y in zip(got, fourier))
    assert torch.equal(
        p["geometry"]["part_coordinates_xy_m"],
        s["geometry"]["part_coordinates_xy_m"][rows],
    )


@pytest.mark.parametrize(
    "family",
    [
        "FM",
        "A1",
        "A2",
        "A3",
        "A4",
        "A5",
        "B1",
        "B2",
        "B3",
        "B4",
        "B5",
        "B6",
        "B7",
        "B8",
        "B9",
        "SSV",
        "DS",
    ],
)
def test_masking_and_ragged(family):
    first = fixture()
    second = fixture((2,))
    second["scene_id"] = "scene_b"
    projected = [project(s, family) for s in (first, second)]
    b = projected_collate(projected, {})
    cfg = copy.deepcopy(CONFIG)
    cfg["training"]["modality_mask_probability"] = 1.0
    global_ids, local_ids = family_modality_assignments(b, cfg, 1, 0)
    active = [MODALITIES.index(m) for m in family_contract(family).modalities]
    for i, g in enumerate(global_ids.tolist()):
        eligible = torch.where(b["entities"]["modality_available"][i])[0].tolist()
        if eligible:
            assert g in eligible and int(local_ids[i]) == active.index(g)
        else:
            assert g == -1 and int(local_ids[i]) == -1
    assert torch.equal(global_ids, family_modality_assignments(b, cfg, 1, 0)[0])
    if active == [0, 1, 2, 3]:
        assert torch.equal(global_ids, modality_assignments(b, cfg, 1, 0))
    edge = b["edges"]["edge_index"]
    if edge.numel():
        assert torch.equal(
            b["entity_scene_index"][edge[0]], b["entity_scene_index"][edge[1]]
        )


def test_ssv_global_to_local():
    p = project(fixture(), "SSV")
    b = projected_collate([p], {})
    b["entities"]["modality_available"][:] = 0
    b["entities"]["modality_available"][:, 2] = 1
    cfg = copy.deepcopy(CONFIG)
    cfg["training"]["modality_mask_probability"] = 1.0
    g, l = family_modality_assignments(b, cfg, 1, 0)
    assert bool((g == 2).all()) and bool((l == 1).all())


@pytest.mark.parametrize("family", ["B2", "B5", "B6", "B7", "A1", "DS"])
def test_empty(family):
    p, m = project(fixture(()), family)
    b = projected_collate([(p, m)], {})
    assert b["edges"]["edge_index"].shape == (2, 0)
    assert family_modality_assignments(b, CONFIG, 1, 0)[0].shape == (0,)


@pytest.mark.parametrize(
    "defect", ["semantic", "availability", "edge", "topology", "fourier"]
)
def test_reject_misalignment(defect):
    s = fixture()
    if defect == "semantic":
        s["entities"]["road_row_index"] = torch.tensor([0])
    if defect == "availability":
        s["entities"]["modality_available"] = torch.ones(3, 4)
    if defect == "edge":
        s["edges"]["edge_index"][0, 0] = 99
    if defect == "topology":
        s["topology"]["source_chain_road_index"] = torch.tensor([0])
    with pytest.raises(ValueError):
        p, m = project(s, "B2")
        if defect == "fourier":
            project_fourier(
                (torch.zeros(3, 2), torch.zeros(3, 3)),
                m,
                p["entities"]["local_entity_id"],
            )


def test_unknown_family_and_ineligible():
    with pytest.raises(ValueError):
        project(fixture(), "UNKNOWN")
    p = project(fixture(), "B1")
    b = projected_collate([p], {})
    b["entities"]["modality_available"][:, 3] = 1
    with pytest.raises(ValueError):
        family_modality_assignments(b, CONFIG, 1, 0)


def test_empty_float_topology_index():
    s = fixture((2,))
    s["topology"]["source_chain_road_index"] = torch.tensor([])
    p, m = project(s, "FM")
    assert p["topology"]["source_chain_road_index"].dtype == torch.int64
    s = fixture()
    s["topology"]["source_chain_road_index"] = torch.tensor([1.0])
    with pytest.raises((ValueError, IndexError)):
        project(s, "B1")


@pytest.mark.parametrize("area", ["entities", "edges", "geometry"])
def test_unregistered_aligned_field(area):
    s = fixture()
    s[area]["future_field"] = torch.zeros(4)
    with pytest.raises(ValueError):
        project(s, "B2")


@pytest.mark.parametrize("family", ["FM", "A3", "A4", "A5"])
def test_full_modality_seed_equivalence(family):
    b = projected_collate([project(fixture(), family)], {})
    for epoch in (1, 5, 95, 200):
        for rank in (0, 1):
            for view in (0, 1):
                new, local = family_modality_assignments(b, CONFIG, epoch, view, rank)
                assert torch.equal(
                    new, modality_assignments(b, CONFIG, epoch, view, rank)
                )
                assert torch.equal(new, local)
