"""Materialize accepted I19 decisions as compact I21 tensor samples."""

from __future__ import annotations

import hashlib
import math
import os
from typing import Any

import numpy as np
import torch
from shapely import from_wkb
from shapely.geometry import LineString, MultiLineString, MultiPoint, MultiPolygon, Point, Polygon

from prototype_augmentation import (
    AugmentationResources,
    RELATION_BITS,
    augment_scene,
    geometry_bbox_center,
    keyed_rng,
    recompute_object_context,
    standardize,
    unstandardize,
    unpack_geometries,
)
from prototype_dataloader import logical_batch_digest, ragged_collate


THREAD_VARIABLES = ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS")


def initialize_native_worker() -> None:
    for name in THREAD_VARIABLES:
        os.environ[name] = "1"
    torch.set_num_threads(1)


def _parts(geometry: Any) -> tuple[int, list[Any]]:
    if isinstance(geometry, Point):
        return 0, [geometry]
    if isinstance(geometry, MultiPoint):
        return 1, list(geometry.geoms)
    if isinstance(geometry, LineString):
        return 2, [geometry]
    if isinstance(geometry, MultiLineString):
        return 3, list(geometry.geoms)
    if isinstance(geometry, Polygon):
        return 4, [geometry]
    if isinstance(geometry, MultiPolygon):
        return 5, list(geometry.geoms)
    raise ValueError(f"unsupported augmented geometry: {geometry.geom_type}")


def _geometry_tensors(geometries: list[Any]) -> tuple[dict[str, torch.Tensor], dict[str, torch.Tensor]]:
    absolute: list[tuple[float, float]] = []
    intrinsic: list[tuple[float, float]] = []
    centers: list[tuple[float, float]] = []
    geometry_type: list[int] = []
    entity_coordinate = [0]
    entity_part = [0]
    part_coordinate = [0]
    entity_ring = [0]
    ring_component: list[int] = []
    ring_start: list[int] = []
    ring_end: list[int] = []
    ring_hole: list[int] = []
    for geometry in geometries:
        code, parts = _parts(geometry)
        geometry_type.append(code)
        center = geometry_bbox_center(geometry)
        centers.append(center)
        for part in parts:
            component = len(part_coordinate) - 1
            if isinstance(part, Point):
                rings = [(np.asarray(part.coords, dtype=np.float64), False)]
            elif isinstance(part, LineString):
                rings = [(np.asarray(part.coords, dtype=np.float64), False)]
            else:
                rings = [(np.asarray(part.exterior.coords, dtype=np.float64), False)]
                rings.extend((np.asarray(ring.coords, dtype=np.float64), True) for ring in part.interiors)
            part_begin = len(absolute)
            for coordinates, is_hole in rings:
                start = len(absolute)
                absolute.extend(map(tuple, coordinates.tolist()))
                intrinsic.extend(map(tuple, (coordinates - np.asarray(center)).tolist()))
                if isinstance(part, Polygon):
                    ring_component.append(component)
                    ring_start.append(start)
                    ring_end.append(len(absolute))
                    ring_hole.append(int(is_hole))
            part_coordinate.append(len(absolute))
            if len(absolute) == part_begin:
                raise ValueError("empty geometry part")
        entity_coordinate.append(len(absolute))
        entity_part.append(len(part_coordinate) - 1)
        entity_ring.append(len(ring_component))
    absolute_array = np.asarray(absolute, dtype=np.float64).reshape(-1, 2)
    intrinsic_array = np.asarray(intrinsic, dtype=np.float32).reshape(-1, 2)
    common = {
        "geometry_type": torch.tensor(geometry_type, dtype=torch.int64),
        "entity_coordinate_offsets": torch.tensor(entity_coordinate, dtype=torch.int64),
        "entity_component_offsets": torch.tensor(entity_part, dtype=torch.int64),
        "component_coordinate_offsets": torch.tensor(part_coordinate, dtype=torch.int64),
        "entity_part_offsets": torch.tensor(entity_part, dtype=torch.int64),
        "part_coordinate_offsets": torch.tensor(part_coordinate, dtype=torch.int64),
        "entity_ring_offsets": torch.tensor(entity_ring, dtype=torch.int64),
        "ring_component_index": torch.tensor(ring_component, dtype=torch.int64),
        "ring_coordinate_start": torch.tensor(ring_start, dtype=torch.int64),
        "ring_coordinate_end": torch.tensor(ring_end, dtype=torch.int64),
        "ring_is_hole": torch.tensor(ring_hole, dtype=torch.uint8),
    }
    model = {**common, "coordinates_xy_m": torch.from_numpy(intrinsic_array),
             "geometry_available": torch.ones(len(geometries), dtype=torch.uint8)}
    reference = {**common, "coordinates_absolute_xy_5186": torch.from_numpy(absolute_array),
                 "reference_center_absolute_xy_5186": torch.tensor(centers, dtype=torch.float64).reshape(-1, 2)}
    return model, reference


def prepare_augmentation_sample(sample: dict[str, Any]) -> dict[str, Any]:
    """Prepare immutable geometry and row lookups shared by a sample's views."""
    geometries = tuple(unpack_geometries(sample))
    entities = sample["entities"]
    row_lists = {
        prefix: tuple(map(int, entities[f"{prefix}_row_index"].tolist()))
        for prefix in ("building", "road", "poi")
    }
    return {
        "geometries": geometries,
        "geometry_wkb": tuple(geometry.wkb for geometry in geometries),
        "entity_types": entities["entity_type"].numpy(),
        "local_entity_ids": tuple(map(int, entities["local_entity_id"].tolist())),
        "row_lists": row_lists,
        "row_offsets": {prefix: {row: offset for offset, row in enumerate(rows)} for prefix, rows in row_lists.items()},
    }


def materialize_augmented_sample(sample: dict[str, Any], result: dict[str, Any], config: dict[str, Any],
                                 resources: AugmentationResources, epoch: int, view_id: int,
                                 intensity: float = 1.0,
                                 prepared: dict[str, Any] | None = None,
                                 runtime_cache: dict[str, Any] | None = None) -> dict[str, Any]:
    prepared = prepare_augmentation_sample(sample) if prepared is None else prepared
    retained = list(map(int, result["retained"]))
    old_to_new = {old: new for new, old in enumerate(retained)}
    original_entities = sample["entities"]
    original_types = prepared["entity_types"]
    types = original_types[retained]
    geometries = (
        list(runtime_cache["geometries"]) if runtime_cache is not None else
        [from_wkb(bytes.fromhex(result["geometry_wkb"][str(row)])) for row in retained]
    )
    if runtime_cache is not None:
        geometries = [geometries[row] for row in retained]
    geometry, reference = _geometry_tensors(geometries)
    center = np.asarray(sample["meta"]["center_xy_5186"], dtype=np.float64)
    centers = reference["reference_center_absolute_xy_5186"].numpy()
    relative = np.asarray(centers - center, dtype=np.float32)

    type_offsets: dict[str, list[int]] = {}
    for prefix, code in (("building", 0), ("road", 1), ("poi", 2)):
        row_to_offset = prepared["row_offsets"][prefix]
        type_offsets[prefix] = [row_to_offset[row] for row in retained if original_types[row] == code]
    entities: dict[str, torch.Tensor] = {
        "local_entity_id": torch.arange(len(retained), dtype=torch.int64),
        "entity_type": torch.from_numpy(np.asarray(types, dtype=np.int64)),
        "relative_position_m": torch.from_numpy(relative),
    }
    categories = result["categories"]
    for prefix in ("building", "road", "poi"):
        selected = type_offsets[prefix]
        entities[f"{prefix}_row_index"] = torch.tensor(
            [new for new, old in enumerate(retained) if original_types[old] == {"building": 0, "road": 1, "poi": 2}[prefix]],
            dtype=torch.int64,
        )
        values = np.asarray(categories[f"{prefix}_category"], dtype=np.int64)
        entities[f"{prefix}_category"] = torch.from_numpy(values[selected].copy())

    building_values = original_entities["building_numerical"].numpy().copy()
    building_missing = original_entities["building_missing"].numpy().copy()
    area_references = sample["scientific_reference"]["building_observed_area_m2_reference"].numpy()
    area_stat = resources.normalizations["building_observed_area_m2"]
    gfa_stat = resources.normalizations["building_observed_gross_floor_area_m2"]
    updated_references: list[float] = []
    changed = set(int(value) for value in result["statistics"].get("geometry_changed_rows", []))
    # Older accepted I19 records expose only the count; WKB equality supplies the exact state transition.
    original_wkb = prepared["geometry_wkb"]
    for offset, row in enumerate(prepared["row_lists"]["building"]):
        if row not in old_to_new:
            continue
        new_geometry = geometries[old_to_new[row]]
        geometry_changed = new_geometry.wkb != original_wkb[row]
        area = float(new_geometry.area) if geometry_changed else float(area_references[offset])
        updated_references.append(area)
        if not int(building_missing[offset, 0]):
            building_values[offset, 0] = np.float32(standardize(area, area_stat["mean"], area_stat["applied_scale"], area_stat["transform"]))
        if not int(building_missing[offset, 1]):
            original_gfa = unstandardize(float(original_entities["building_numerical"][offset, 1]), gfa_stat["mean"], gfa_stat["applied_scale"], gfa_stat["transform"])
            ratio = original_gfa / float(area_references[offset])
            building_values[offset, 1] = np.float32(standardize(area * ratio, gfa_stat["mean"], gfa_stat["applied_scale"], gfa_stat["transform"]))
    selected_b = type_offsets["building"]
    entities["building_numerical"] = torch.from_numpy(building_values[selected_b].copy())
    entities["building_missing"] = torch.from_numpy(building_missing[selected_b].copy())
    reference["building_observed_area_m2_reference"] = torch.tensor(updated_references, dtype=torch.float64)

    lane_values = original_entities["road_numerical"].numpy().copy()
    lane_missing = original_entities["road_missing"].numpy().copy()
    lane_stat = resources.normalizations["road_lanes"]
    event_by_row = {int(event["row"]): event for event in result["lane_events"]}
    for offset, row in enumerate(original_entities["road_row_index"].tolist()):
        event = event_by_row.get(int(row))
        if event is not None and event["augmented"] is not None:
            lane_values[offset, 0] = np.float32(standardize(event["augmented"], lane_stat["mean"], lane_stat["applied_scale"], lane_stat["transform"]))
    selected_r = type_offsets["road"]
    entities["road_numerical"] = torch.from_numpy(lane_values[selected_r].copy())
    entities["road_missing"] = torch.from_numpy(lane_missing[selected_r].copy())

    if runtime_cache is not None:
        rasters = runtime_cache["rasters"]
        object_context = runtime_cache["object_context"][retained]
    else:
        rasters = {key: value.numpy().copy() for key, value in sample["rasters"].items()}
        valid_lc = np.argwhere(rasters["landcover_valid_mask"] == 1)
        fraction = min(1.0, intensity * float(config["raster"]["landcover"]["valid_cell_mask_fraction"]))
        count = int(math.floor(fraction * len(valid_lc)))
        if count:
            rng = keyed_rng(int(config["rng"]["base_seed"]), epoch, sample["scene_id"], view_id, "landcover")
            for row, column in valid_lc[rng.choice(len(valid_lc), size=count, replace=False)]:
                rasters["landcover_class_fraction"][:, row, column] = 0
                rasters["landcover_valid_support"][row, column] = 0
        dem_stat = resources.normalizations["scene_dem_mean_m"]
        valid_dem = rasters["dem_valid_mask"] == 1
        rng = keyed_rng(int(config["rng"]["base_seed"]), epoch, sample["scene_id"], view_id, "dem")
        sigma = intensity * float(config["raster"]["dem"]["valid_cell_gaussian_sd_m"]) / float(dem_stat["applied_scale"])
        rasters["dem_standardized_mean"][valid_dem] += rng.normal(0, sigma, int(valid_dem.sum())).astype(np.float32)
        object_context = recompute_object_context(
            geometries, set(range(len(geometries))), rasters["landcover_class_fraction"],
            rasters["landcover_valid_support"], rasters["dem_standardized_mean"], rasters["dem_valid_support"], tuple(center),
        )
    entities["object_raster"] = torch.from_numpy(object_context)
    entities["object_dem_missing"] = torch.from_numpy(np.stack((object_context[:, 25] == 0, object_context[:, 25] == 0), axis=1).astype(np.uint8))

    relation_masks: dict[tuple[int, int], int] = {}
    for relation, pairs in result["relations"].items():
        bit = RELATION_BITS[relation]
        for source, destination in pairs:
            pair = (old_to_new[int(source)], old_to_new[int(destination)])
            relation_masks[pair] = relation_masks.get(pair, 0) | bit
    pairs = sorted(relation_masks)
    edges = {
        "edge_index": torch.tensor(pairs, dtype=torch.int64).T.contiguous() if pairs else torch.empty((2, 0), dtype=torch.int64),
        "relation_mask": torch.tensor([relation_masks[pair] for pair in pairs], dtype=torch.int64),
    }
    road_offsets = type_offsets["road"]
    topology = {key: value.clone() for key, value in sample["topology"].items()}
    topology["road_endpoint_node_index"] = topology["road_endpoint_node_index"][road_offsets]
    topology["road_endpoint_retained"] = topology["road_endpoint_retained"][road_offsets]
    raster_tensors = {key: torch.from_numpy(value.copy()) for key, value in rasters.items()}
    output = {
        "scene_id": sample["scene_id"], "split": sample["split"], "global_index": sample["global_index"],
        "split_local_index": sample["split_local_index"],
        "meta": {**sample["meta"], "source_entity_ids": [sample["meta"]["source_entity_ids"][row] for row in retained]},
        "entities": entities, "geometry": geometry, "scientific_reference": reference,
        "edges": edges, "topology": topology, "rasters": raster_tensors,
        "resources": {"nodes": len(retained), "ordered_edges": len(pairs),
                      "coordinates": int(geometry["coordinates_xy_m"].shape[0]),
                      "actual_payload_bytes": sum(value.numel() * value.element_size() for group in (entities, geometry, reference, edges, topology, raster_tensors) for value in group.values())},
        "units": sample["units"], "augmentation_result": result,
    }
    return output


def augment_and_materialize(sample: dict[str, Any], config: dict[str, Any], resources: AugmentationResources,
                            thresholds: dict[int, float], epoch: int, view_id: int,
                            intensity: float = 1.0,
                            prepared: dict[str, Any] | None = None) -> dict[str, Any]:
    prepared = prepare_augmentation_sample(sample) if prepared is None else prepared
    runtime_cache: dict[str, Any] = {}
    result = augment_scene(
        sample, config, resources, thresholds, epoch, view_id, intensity=intensity,
        prepared=prepared, runtime_cache=runtime_cache,
    )
    output = materialize_augmented_sample(
        sample, result, config, resources, epoch, view_id, intensity=intensity,
        prepared=prepared, runtime_cache=runtime_cache,
    )
    output["training_tensor_digest"] = logical_batch_digest(ragged_collate([output]))
    output["i19_logical_digest"] = result["logical_digest"]
    return output
