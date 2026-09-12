"""Prepared family projection for dissertation component/source ablations.

The training methodology masks one active available modality per selected entity.
Immutable prepared payloads retain full sources; this boundary precedes all encoders.
"""

import copy
from dataclasses import dataclass
from typing import Any
import torch
from model_families import FamilyContract, family_contract
from model_data import validate_geometry_layout
from training_support import collate, derive_seed, uniform01

MODALITIES = ("relative", "geometry", "semantic", "environmental")
SOURCES = ("B", "R", "P")


def index_tensor(value):
    if value.numel() == 0:
        return value.to(torch.int64)
    if value.dtype != torch.int64:
        raise ValueError("nonempty index must be int64")
    return value


def ptr(lengths):
    return torch.tensor(
        [0, *torch.tensor(lengths, dtype=torch.int64).cumsum(0).tolist()],
        dtype=torch.int64,
    )


def segments(offsets, rows):
    selected = [
        torch.arange(int(offsets[i]), int(offsets[i + 1]), dtype=torch.int64)
        for i in rows
    ]
    return (
        torch.cat(selected) if selected else torch.empty(0, dtype=torch.int64),
        ptr([len(x) for x in selected]),
    )


def check_sample(s):
    validate_geometry_layout(s)
    e = s["entities"]
    n = e["local_entity_id"].numel()
    for key in (
        "local_entity_id",
        "entity_type",
        "building_row_index",
        "road_row_index",
        "poi_row_index",
    ):
        index_tensor(e[key])
    expected = {
        "local_entity_id",
        "entity_type",
        "relative_position_m",
        "object_raster",
        "modality_available",
    }
    for prefix in ("building", "road", "poi"):
        expected.add(prefix + "_row_index")
        expected.update(
            prefix + "_" + suffix
            for suffix in (
                ("category",)
                if prefix == "poi"
                else ("category", "numerical", "missing")
            )
        )
    if set(e) != expected:
        raise ValueError("unregistered entity field")
    if set(s["edges"]) != {"edge_index", "relation_mask"}:
        raise ValueError("unregistered edge attribute")
    if e["entity_type"].shape != (n,) or e["modality_available"].shape != (n, 4):
        raise ValueError("entity/availability shape mismatch")
    if e["local_entity_id"].unique().numel() != n or not bool(
        ((e["entity_type"] >= 0) & (e["entity_type"] < 3)).all()
    ):
        raise ValueError("invalid entity identity/type")
    for k in ("relative_position_m", "object_raster"):
        if e[k].shape[0] != n:
            raise ValueError("entity aligned field mismatch: " + k)
    for code, prefix in enumerate(("building", "road", "poi")):
        ix = e[prefix + "_row_index"]
        if not torch.equal(ix, torch.where(e["entity_type"] == code)[0]):
            raise ValueError("semantic row mapping mismatch")
        for suffix in (
            ("category",) if prefix == "poi" else ("category", "numerical", "missing")
        ):
            if e[prefix + "_" + suffix].shape[0] != len(ix):
                raise ValueError("semantic alignment mismatch")
    edge = s["edges"]["edge_index"]
    if (
        edge.ndim != 2
        or edge.shape[0] != 2
        or len(s["edges"]["relation_mask"]) != edge.shape[1]
    ):
        raise ValueError("edge shape mismatch")
    if edge.numel() and not bool(((edge >= 0) & (edge < n)).all()):
        raise ValueError("edge endpoint out of range")
    g = s["geometry"]
    for key in (
        "entity_coordinate_offsets",
        "entity_part_offsets",
        "part_coordinate_offsets",
        "entity_component_offsets",
        "component_coordinate_offsets",
        "entity_ring_offsets",
        "ring_coordinate_start",
        "ring_coordinate_end",
        "ring_component_index",
    ):
        index_tensor(g[key])
    if not torch.equal(
        g["entity_component_offsets"], g["entity_part_offsets"]
    ) or not torch.equal(
        g["component_coordinate_offsets"], g["part_coordinate_offsets"]
    ):
        raise ValueError("unsupported component/part layout disagreement")
    expected_g = {
        "part_coordinates_xy_m",
        "part_coordinates_xy_m_scientific",
        "ring_coordinates_xy_m",
        "ring_coordinates_xy_m_scientific",
        "geometry_type",
        "geometry_available",
        "entity_coordinate_offsets",
        "entity_part_offsets",
        "part_coordinate_offsets",
        "entity_component_offsets",
        "component_coordinate_offsets",
        "entity_ring_offsets",
        "ring_coordinate_start",
        "ring_coordinate_end",
        "ring_is_hole",
        "ring_component_index",
    }
    if set(g) != expected_g:
        raise ValueError("unregistered geometry field")
    for k in (
        "entity_part_offsets",
        "entity_component_offsets",
        "entity_coordinate_offsets",
        "entity_ring_offsets",
    ):
        if len(g[k]) != n + 1:
            raise ValueError("geometry entity offsets mismatch")
    for k in ("geometry_type", "geometry_available"):
        if len(g[k]) != n:
            raise ValueError("geometry row mismatch")
    if not torch.equal(
        g["entity_coordinate_offsets"],
        g["part_coordinate_offsets"][g["entity_part_offsets"]],
    ):
        raise ValueError("entity coordinate/part disagreement")
    for key, terminal in (
        ("entity_part_offsets", len(g["part_coordinate_offsets"]) - 1),
        ("entity_ring_offsets", len(g["ring_is_hole"])),
    ):
        v = g[key]
        if int(v[0]) != 0 or int(v[-1]) != terminal or bool((v[1:] < v[:-1]).any()):
            raise ValueError("geometry offsets invalid")
    for entity in range(n):
        comps = g["ring_component_index"][
            int(g["entity_ring_offsets"][entity]) : int(
                g["entity_ring_offsets"][entity + 1]
            )
        ]
        if comps.numel() and not bool(
            (
                (comps >= g["entity_part_offsets"][entity])
                & (comps < g["entity_part_offsets"][entity + 1])
            ).all()
        ):
            raise ValueError("ring owner mismatch")
    t = s["topology"]
    roads = index_tensor(t["source_chain_road_index"])
    index_tensor(t["source_chain_offsets"])
    if set(t) != {
        "source_chain_road_index",
        "source_chain_offsets",
        "source_node_xy_5186",
        "source_node_ids",
    }:
        raise ValueError("unregistered topology field")
    if roads.numel() and (
        not bool(((roads >= 0) & (roads < n)).all())
        or not bool((e["entity_type"][roads] == 1).all())
    ):
        raise ValueError("topology must reference retained roads")
    if len(t["source_chain_offsets"]) != len(roads) + 1 or int(
        t["source_chain_offsets"][-1]
    ) != len(t["source_node_ids"]):
        raise ValueError("topology offsets mismatch")
    if (
        int(t["source_chain_offsets"][0]) != 0
        or bool((t["source_chain_offsets"][1:] < t["source_chain_offsets"][:-1]).any())
        or t["source_node_xy_5186"].shape != (len(t["source_node_ids"]), 2)
    ):
        raise ValueError("topology nodes mismatch")


def project(s, family):
    """Retain source rows and induced edges, with original local IDs as RNG identity."""
    c = family_contract(family)
    check_sample(s)
    e = s["entities"]
    n = len(e["local_entity_id"])
    allowed = [i for i, x in enumerate(SOURCES) if x in c.retained_sources]
    keep = torch.tensor([int(x) in allowed for x in e["entity_type"]], dtype=torch.bool)
    rows = torch.where(keep)[0]
    reverse = torch.full((n,), -1, dtype=torch.int64)
    reverse[rows] = torch.arange(len(rows))
    out = copy.deepcopy(s)
    for key in (
        "local_entity_id",
        "entity_type",
        "relative_position_m",
        "object_raster",
        "modality_available",
    ):
        out["entities"][key] = e[key][rows].clone()
    for prefix in ("building", "road", "poi"):
        ix = e[prefix + "_row_index"]
        selected = keep[ix]
        out["entities"][prefix + "_row_index"] = reverse[ix[selected]]
        for suffix in (
            ("category",) if prefix == "poi" else ("category", "numerical", "missing")
        ):
            out["entities"][prefix + "_" + suffix] = e[prefix + "_" + suffix][
                selected
            ].clone()
    active = [MODALITIES.index(m) for m in c.modalities]
    eligible = torch.zeros((len(rows), 4), dtype=e["modality_available"].dtype)
    eligible[:, active] = out["entities"]["modality_available"][:, active]
    out["entities"]["modality_available"] = eligible
    columns = []
    if "environmental" in c.modalities:
        if "LC" in c.retained_sources:
            columns += list(range(23))
        if "DEM" in c.retained_sources:
            columns += list(range(23, 26))
    out["entities"]["object_raster"] = out["entities"]["object_raster"][:, columns]
    # Keep geometry's compact storage internally for existing ragged collation.
    # Model input routing must omit Fourier/geometry modality when inactive.
    g = s["geometry"]
    ng = out["geometry"]
    parts, ep = segments(g["entity_part_offsets"], rows)
    coords, pc = segments(g["part_coordinate_offsets"], parts)
    rings, er = segments(g["entity_ring_offsets"], rows)
    ringpieces = [
        torch.arange(
            int(g["ring_coordinate_start"][i]), int(g["ring_coordinate_end"][i])
        )
        for i in rings
    ]
    rcoords = torch.cat(ringpieces) if ringpieces else torch.empty(0, dtype=torch.int64)
    rp = ptr([len(x) for x in ringpieces])
    partmap = torch.full(
        (len(g["part_coordinate_offsets"]) - 1,), -1, dtype=torch.int64
    )
    partmap[parts] = torch.arange(len(parts))
    for k in ("part_coordinates_xy_m", "part_coordinates_xy_m_scientific"):
        ng[k] = g[k][coords]
    for k in ("ring_coordinates_xy_m", "ring_coordinates_xy_m_scientific"):
        ng[k] = g[k][rcoords]
    for k in ("geometry_type", "geometry_available"):
        ng[k] = g[k][rows]
    ng["entity_part_offsets"] = ep
    ng["entity_component_offsets"] = ep.clone()
    ng["part_coordinate_offsets"] = pc
    ng["component_coordinate_offsets"] = pc.clone()
    ng["entity_coordinate_offsets"] = pc[ep]
    ng["entity_ring_offsets"] = er
    ng["ring_coordinate_start"] = rp[:-1]
    ng["ring_coordinate_end"] = rp[1:]
    ng["ring_is_hole"] = g["ring_is_hole"][rings]
    ng["ring_component_index"] = partmap[index_tensor(g["ring_component_index"][rings])]
    edge = s["edges"]["edge_index"]
    emask = keep[edge[0]] & keep[edge[1]]
    if c.relation == "none":
        emask = torch.zeros_like(emask)
    out["edges"] = {
        "edge_index": reverse[edge[:, emask]],
        "relation_mask": s["edges"]["relation_mask"][emask].clone(),
    }
    t = s["topology"]
    road_indices = index_tensor(t["source_chain_road_index"])
    chains = torch.where(keep[road_indices])[0]
    nodes, offset = segments(t["source_chain_offsets"], chains)
    out["topology"] = {
        "source_chain_offsets": offset,
        "source_chain_road_index": reverse[road_indices[chains]],
        "source_node_xy_5186": t["source_node_xy_5186"][nodes],
        "source_node_ids": [t["source_node_ids"][i] for i in nodes.tolist()],
    }
    scene_sources = (
        [x for x in ("LC", "DEM") if x in c.retained_sources] if c.scene_raster else []
    )
    if family == "DS":
        scene_sources = ["LC", "DEM"]
    out["rasters"] = {
        k: v.clone()
        for k, v in s["rasters"].items()
        if ("LC" if k.startswith("landcover") else "DEM") in scene_sources
    }
    out["resources"] = {
        "nodes": len(rows),
        "ordered_edges": int(emask.sum()),
        "part_coordinates": len(coords),
        "ring_coordinates": len(rcoords),
        "coordinates": len(coords) + len(rcoords),
        "source_nodes": len(nodes),
    }
    metadata = {
        "version": "s09-family-projection-v1",
        "family": family,
        "source_entity_count": n,
        "source_local_ids": e["local_entity_id"].clone(),
        "retained_rows": rows,
        "retained_local_ids": e["local_entity_id"][rows].clone(),
        "active_global_ids": active,
        "environment_columns": columns,
        "scene_sources": scene_sources,
        "geometry_enabled": "geometry" in c.modalities,
        "ds_only": family == "DS",
    }
    check_sample(out)
    return out, metadata


def projected_collate(projected, vocabulary):
    samples, meta = zip(*projected)
    if len({m["family"] for m in meta}) != 1:
        raise ValueError("mixed family batch")
    batch = collate(samples, vocabulary)
    batch["family_projection"] = list(meta)
    return batch


def project_fourier(values, metadata, retained_ids):
    n = metadata["source_entity_count"]
    rows = metadata["retained_rows"]
    if any(x.ndim != 2 or len(x) != n for x in values):
        raise ValueError("geometry cache original row count mismatch")
    if not torch.equal(metadata["source_local_ids"][rows], retained_ids):
        raise ValueError("geometry retained identity mismatch")
    result = tuple(x[rows].clone() for x in values)
    if any(len(x) != len(retained_ids) for x in result):
        raise ValueError("projected geometry mismatch")
    return result


def family_modality_assignments(batch, config, epoch, view_role, global_rank=0):
    """Same seed/gate as legacy; sample only eligible GLOBAL IDs then map to local."""
    meta = batch["family_projection"]
    c = family_contract(meta[0]["family"])
    active = [MODALITIES.index(m) for m in c.modalities]
    available = batch["entities"]["modality_available"].bool()
    if available.ndim != 2 or available.shape[1] != 4:
        raise ValueError("availability shape")
    forbidden = [i for i in range(4) if i not in active]
    if forbidden and bool(available[:, forbidden].any()):
        raise ValueError("inactive modality remains eligible")
    assignments = torch.full((len(available),), -1, dtype=torch.int64)
    local = assignments.clone()
    ptrs = batch["scene_ptr"].tolist()
    ids = batch["entities"]["local_entity_id"].tolist()
    for si, scene in enumerate(batch["scene_ids"]):
        for row in range(ptrs[si], ptrs[si + 1]):
            fields = dict(
                epoch=epoch,
                global_rank=global_rank,
                worker_id=0,
                operation="entity-gate",
                scene_id=scene,
                local_entity_id=int(ids[row]),
                view_role=view_role,
            )
            if uniform01(config, "modality-mask", **fields) >= float(
                config["training"]["modality_mask_probability"]
            ):
                continue
            choices = torch.where(available[row])[0].tolist()
            if not choices:
                continue  # Explicit NOT_MASKABLE (-1), including DS.
            pick = derive_seed(
                config,
                "modality-mask",
                epoch=epoch,
                global_rank=global_rank,
                worker_id=0,
                operation="available-modality",
                scene_id=scene,
                local_entity_id=int(ids[row]),
                view_role=view_role,
            ) % len(choices)
            selected = choices[pick]
            assignments[row] = selected
            local[row] = active.index(selected)
    return assignments, local


@dataclass(frozen=True)
class Projection:
    sample: dict[str, Any]
    metadata: dict[str, Any]
    original_entity_ids: torch.Tensor
    old_to_new: torch.Tensor
    geometry_rows: torch.Tensor
    edge_rows: torch.Tensor
    global_to_local: tuple[int, ...]


def project_family_sample(
    sample: dict[str, Any], contract: FamilyContract
) -> Projection:
    if contract != family_contract(contract.name):
        raise ValueError("noncanonical family contract")
    p, m = project(sample, contract.name)
    old_to_new = torch.full((m["source_entity_count"],), -1, dtype=torch.int64)
    old_to_new[m["retained_rows"]] = torch.arange(len(m["retained_rows"]))
    edge = sample["edges"]["edge_index"]
    keep = (old_to_new[edge[0]] >= 0) & (old_to_new[edge[1]] >= 0)
    if contract.relation == "none":
        keep[:] = False
    mapping = tuple(
        contract.modalities.index(x) if x in contract.modalities else -1
        for x in MODALITIES
    )
    return Projection(
        p,
        m,
        m["retained_local_ids"],
        old_to_new,
        m["retained_rows"],
        torch.where(keep)[0],
        mapping,
    )


def assemble_family_batch(values, records):
    """Shared training/query/gallery assembly, including per-record cache role."""
    c = family_contract(values["family"])
    projected = [
        project_family_sample(
            values["scene_centers"].attach(
                values["data"].sample(*row),
                "training" if row[0] == "training" else "validation",
            ),
            c,
        )
        for row in records
    ]
    b = projected_collate(
        [(p.sample, p.metadata) for p in projected], values["vocabulary"]
    )
    b["family_name"] = c.name
    env = b["entities"]["object_raster"]
    offset = 0
    blocks = {}
    for source, width in [("LC", 23), ("DEM", 3)]:
        if "environmental" in c.modalities and source in c.retained_sources:
            blocks[source] = env[:, offset : offset + width]
            offset += width
    if offset != env.shape[1]:
        raise ValueError("environment width mismatch")
    b["environment"] = blocks
    geometry = None
    if "geometry" in c.modalities:
        rows = []
        for p, (role, scene, view) in zip(projected, records, strict=True):
            physical = (
                values["data"].physical_training_role if role == "training" else role
            )
            raw = values["geometry_cache"]._get(
                physical, scene, str(p.sample["view_id"])
            )
            rows.append(project_fourier(raw, p.metadata, p.original_entity_ids))
        geometry = tuple(torch.cat([x[i] for x in rows]) for i in (0, 1))
    return b, geometry, projected


def family_encoder_batch(batch):
    """Drop inactive carriers before model entry, retaining scene identities."""
    c = family_contract(batch["family_name"])
    if c.name == "DS":
        return {
            k: batch[k]
            for k in (
                "family_name",
                "scene_ids",
                "scene_center_5186",
                "scene_numeric_ids",
            )
        }
    out = dict(batch)
    # Fourier tensors are supplied separately, never copied into the model twice.
    out.pop("_family_geometry", None)
    e = dict(batch["entities"])
    e.pop("object_raster")
    if "semantic" not in c.modalities:
        for key in list(e):
            if key.startswith(("building_", "road_", "poi_")):
                del e[key]
    out["entities"] = e
    out.pop("geometry", None)
    out.pop("topology", None)
    return out


def validate_family_encoder_input(b, c, geometry, assignments):
    if b.get("family_name") != c.name:
        raise ValueError("family binding mismatch")
    e = b["entities"]
    n = len(e["local_entity_id"])
    types = e["entity_type"]
    a = e["modality_available"]
    allowed = {i for i, s in enumerate(("B", "R", "P")) if s in c.retained_sources}
    if not set(types.tolist()) <= allowed:
        raise ValueError("excluded source")
    if (
        types.shape != (n,)
        or a.shape != (n, 4)
        or b["entity_scene_index"].shape != (n,)
    ):
        raise ValueError("entity shape")
    if n and not bool(
        (
            (b["entity_scene_index"] >= 0)
            & (b["entity_scene_index"] < len(b["scene_ids"]))
        ).all()
    ):
        raise ValueError("scene mapping")
    active = [MODALITIES.index(x) for x in c.modalities]
    if any(bool(a[:, i].any()) for i in range(4) if i not in active):
        raise ValueError("inactive availability")
    if bool(a[types == 2, 1].any()):
        raise ValueError("POI geometry")
    if n and not bool(a[:, active].bool().any(1).all()):
        raise ValueError("no active encoder modality")
    if "geometry" in c.modalities:
        if (
            geometry is None
            or len(geometry) != 2
            or any(x.shape != (n, w) for x, w in zip(geometry, (128, 256)))
        ):
            raise ValueError("Fourier rows")
    elif geometry is not None:
        raise ValueError("inactive Fourier input")
    sources = (
        tuple(s for s in ("LC", "DEM") if s in c.retained_sources)
        if "environmental" in c.modalities
        else ()
    )
    if set(b["environment"]) != set(sources):
        raise ValueError("environment sources")
    for s, x in b["environment"].items():
        if x.shape != (n, 23 if s == "LC" else 3):
            raise ValueError("environment shape")
    expected = set()
    if c.scene_raster:
        if "LC" in c.retained_sources:
            expected.update(
                (
                    "landcover_class_fraction",
                    "landcover_valid_mask",
                    "landcover_intentional_mask",
                    "landcover_valid_support",
                )
            )
        if "DEM" in c.retained_sources:
            expected.update(
                ("dem_standardized_mean", "dem_valid_mask", "dem_valid_support")
            )
    if set(b["rasters"]) != expected:
        raise ValueError("raster source contract: " + str(set(b["rasters"])))
    edges = b["edges"]["edge_index"]
    if edges.numel() and not bool(((edges >= 0) & (edges < n)).all()):
        raise ValueError("edge endpoint")
    if c.relation == "none" and edges.numel():
        raise ValueError("inactive relations")
    if assignments is not None:
        if assignments.dtype != torch.int64 or assignments.shape != (n,):
            raise ValueError("assignment shape/dtype")
        if not bool(((assignments >= -1) & (assignments < len(active))).all()):
            raise ValueError("local assignment range")
        chosen = torch.where(assignments >= 0)[0]
        if len(chosen):
            global_ids = torch.tensor(active, device=a.device)[assignments[chosen]]
            if not bool(a[chosen, global_ids].bool().all()):
                raise ValueError("ineligible assignment")
