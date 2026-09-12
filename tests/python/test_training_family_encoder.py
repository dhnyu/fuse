import copy, json
from pathlib import Path
import pytest, torch
from test_training_family_projection import fixture, CONFIG
from training_family_inputs import *
from model_families import build_scene_encoder
from training_support import state_content_digest


def config():
    return {
        "model": {
            "d": 64,
            "d_c": 64,
            "d_t": 16,
            "d_r": 32,
            "attention_heads": 4,
            "head_dimension": 16,
            "ffn_dimension": 128,
            "dropout": 0.2,
            "wavelengths": {"minimum_m": 10, "maximum_m": 1000, "count": 16},
            "poi_hierarchy_dimensions": [8, 12, 16, 16, 24, 32],
        }
    }


def vocabulary():
    return {
        k: 8
        for k in (
            "A9",
            "A11",
            "ROAD_RANK",
            "ROAD_TYPE",
            *[f"CLASS_L{i}" for i in range(1, 7)],
        )
    }


def batch(family, types=(0, 1, 2, 0)):
    s = fixture(types)
    order = torch.argsort(s["edges"]["edge_index"][0], stable=True)
    s["edges"]["edge_index"] = s["edges"]["edge_index"][:, order]
    s["edges"]["relation_mask"] = s["edges"]["relation_mask"][order]
    s["rasters"] = {
        "landcover_class_fraction": torch.zeros(22, 100, 100),
        "landcover_valid_mask": torch.ones(100, 100, dtype=torch.uint8),
        "landcover_intentional_mask": torch.zeros(100, 100, dtype=torch.uint8),
        "landcover_valid_support": torch.ones(100, 100),
        "dem_standardized_mean": torch.zeros(17, 17),
        "dem_valid_mask": torch.ones(17, 17, dtype=torch.uint8),
        "dem_valid_support": torch.ones(17, 17),
    }
    p = project_family_sample(s, family_contract(family))
    b = projected_collate([(p.sample, p.metadata)], {})
    b["family_name"] = family
    b["environment"] = {}
    offset = 0
    for source, width in [("LC", 23), ("DEM", 3)]:
        if (
            "environmental" in family_contract(family).modalities
            and source in family_contract(family).retained_sources
        ):
            b["environment"][source] = b["entities"]["object_raster"][
                :, offset : offset + width
            ]
            offset += width
    n = len(p.original_entity_ids)
    g = (
        (torch.zeros(n, 128), torch.zeros(n, 256))
        if "geometry" in family_contract(family).modalities
        else None
    )
    return b, g, p


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
    ],
)
@pytest.mark.parametrize("empty", [False, True])
def test_actual_encoder(family, empty):
    b, g, p = batch(family, () if empty else (0, 1, 2, 0))
    m = build_scene_encoder(config(), vocabulary(), family).eval()
    _, a = family_modality_assignments(b, CONFIG, 1, 0)
    with torch.no_grad():
        out = m(family_encoder_batch(b), g, None, a)
    assert out["scene_embedding"].shape == (1, 64) and bool(
        torch.isfinite(out["scene_embedding"]).all()
    )
    if family == "B2":
        assert not hasattr(m, "poi_embeddings")
    if family in ("B6", "B7"):
        assert not hasattr(m, "building_fusion")


class Reads(dict):
    def __init__(self, *args):
        super().__init__(*args)
        self.read = []

    def __getitem__(self, k):
        self.read.append(k)
        return super().__getitem__(k)


@pytest.mark.parametrize(
    "family,allowed,forbidden", [("B8", "LC", "dem"), ("B9", "DEM", "landcover")]
)
def test_physical_source_reads(family, allowed, forbidden):
    b, g, _ = batch(family)
    b = family_encoder_batch(b)
    b["rasters"] = Reads(b["rasters"])
    b["environment"] = Reads(b["environment"])
    m = build_scene_encoder(config(), vocabulary(), family).eval()
    with torch.no_grad():
        m(b, g)
    assert b["environment"].read == [allowed]
    assert not any(k.startswith(forbidden) for k in b["rasters"].read)


@pytest.mark.parametrize(
    "fault", ["family", "assignment", "availability", "geometry", "environment", "edge"]
)
def test_encoder_fail_closed(fault):
    b, g, _ = batch("B2")
    b = family_encoder_batch(b)
    a = torch.full((len(b["entities"]["entity_type"]),), -1, dtype=torch.int64)
    if fault == "family":
        b["family_name"] = "FM"
    if fault == "assignment":
        a[:] = 3
    if fault == "availability":
        b["entities"]["modality_available"][:, 3] = 1
    if fault == "geometry":
        g = (g[0][:-1], g[1])
    if fault == "environment":
        b["environment"]["LC"] = torch.zeros(len(a), 23)
    if fault == "edge":
        b["edges"]["edge_index"][0, 0] = 100
    with pytest.raises(ValueError):
        build_scene_encoder(config(), vocabulary(), "B2")(b, g, None, a)


def test_multipart_hole_and_road_topology():
    s = fixture()
    g = s["geometry"]
    # entity0 two polygon parts (shell+hole, shell); entity1 road; entity2 no geometry; entity3 polygon.
    ep = torch.tensor([0, 2, 3, 3, 4])
    pc = torch.tensor([0, 4, 8, 10, 14])
    er = torch.tensor([0, 3, 3, 3, 4])
    for k in ("entity_part_offsets", "entity_component_offsets"):
        g[k] = ep.clone()
    for k in ("part_coordinate_offsets", "component_coordinate_offsets"):
        g[k] = pc.clone()
    g["entity_coordinate_offsets"] = pc[ep]
    g["entity_ring_offsets"] = er
    for k in ("part_coordinates_xy_m", "part_coordinates_xy_m_scientific"):
        g[k] = torch.arange(28, dtype=torch.float64).reshape(14, 2)
    for k in ("ring_coordinates_xy_m", "ring_coordinates_xy_m_scientific"):
        g[k] = torch.arange(32, dtype=torch.float64).reshape(16, 2)
    g["ring_coordinate_start"] = torch.tensor([0, 4, 8, 12])
    g["ring_coordinate_end"] = torch.tensor([4, 8, 12, 16])
    g["ring_component_index"] = torch.tensor([0, 0, 1, 3])
    g["ring_is_hole"] = torch.tensor([0, 1, 0, 0], dtype=torch.uint8)
    p = project_family_sample(s, family_contract("B3"))
    assert p.old_to_new.tolist() == [0, -1, 1, 2]
    assert p.sample["geometry"]["ring_component_index"].tolist() == [0, 0, 1, 2]
    assert p.sample["geometry"]["entity_part_offsets"].tolist() == [0, 2, 2, 3]
    assert p.sample["topology"]["source_node_ids"] == []
    assert p.edge_rows.tolist() == [2, 3]


@pytest.mark.parametrize("field", ["entity_part_offsets", "ring_component_index"])
def test_nonempty_float_indices(field):
    s = fixture()
    s["geometry"][field] = s["geometry"][field].float()
    with pytest.raises(ValueError):
        project_family_sample(s, family_contract("B2"))


def test_shared_training_validation_assembly():
    import ast

    t = ast.parse(
        (Path(__file__).resolve().parents[2] / "python/training_worker.py").read_text()
    )
    for name in ("_local_batches", "full_validation"):
        node = next(
            n for n in t.body if isinstance(n, ast.FunctionDef) and n.name == name
        )
        assert any(
            isinstance(c, ast.Call)
            and isinstance(c.func, ast.Name)
            and c.func.id == "assemble_family_batch"
            for c in ast.walk(node)
        )


def test_ds_no_entity_input():
    b, _, _ = batch("DS")
    b = family_encoder_batch(b)
    assert "entities" not in b
    m = build_scene_encoder(config(), vocabulary(), "DS").eval()
    with torch.no_grad():
        o = m(b, None, torch.zeros(1, 26, 100, 100))
    assert bool(torch.isfinite(o["scene_embedding"]).all())
    b["entities"] = {}
    with pytest.raises(ValueError, match="forbids"):
        m(b, None, torch.zeros(1, 26, 100, 100))


def test_geometry_tuple_is_complete_and_not_duplicated():
    b, g, _ = batch("FM")
    b["_family_geometry"] = g
    model_batch = family_encoder_batch(b)
    assert "_family_geometry" not in model_batch
    with pytest.raises(ValueError, match="Fourier"):
        build_scene_encoder(config(), vocabulary(), "FM")(model_batch, g[:1])


@pytest.mark.parametrize("family", ["FM", "A3", "A4", "A5"])
@pytest.mark.parametrize("d", [64, 128, 256])
def test_legacy_initialization_dropout_and_rng_bytes(family, d, single_thread_reference):
    evidence = json.loads((Path(__file__).parents[1] / "fixtures/s09_full_family_legacy_forward.json").read_text())
    expected = next(r for r in evidence["rows"] if r["family"] == family and r["d"] == d)
    cfg = config()
    cfg["model"].update(d=d, d_c=d, head_dimension=d // 4, ffn_dimension=d * 2)
    torch.manual_seed(934)
    model = build_scene_encoder(cfg, vocabulary(), family)
    assert state_content_digest(model.state_dict()) == expected["state_sha256"]
    b, g, _ = batch(family)
    _, assignments = family_modality_assignments(b, CONFIG, 2, 1, 0)
    with torch.no_grad():
        torch.manual_seed(283)
        output = model(family_encoder_batch(b), g, None, assignments)["scene_embedding"]
    assert state_content_digest(output) == expected["output_sha256"]
    assert state_content_digest(torch.get_rng_state()) == expected["rng_sha256"]


@pytest.fixture
def single_thread_reference():
    previous = torch.get_num_threads()
    torch.set_num_threads(1)
    try:
        yield
    finally:
        torch.set_num_threads(previous)
