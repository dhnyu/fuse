"""P8-bound P9 model-family registry and deterministic DS materialization."""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import shapely
import torch
import torch.nn.functional as F
from torch import nn

from p6_model import RasterCNN, ReducedSceneEncoder, RelationAwareLayer, projected_block
from p7_training import P7Model, deterministic_relation_layer
from current_methodology import COMPARISON_NAMES, component_contracts, source_contracts
from prototype_encoder import geometry_fourier_features, relation_set_embedding, sinusoidal_position_features

FAMILY_NAMES = COMPARISON_NAMES


@dataclass(frozen=True)
class FamilyContract:
    name: str
    modalities: tuple[str, ...]
    scene_raster: bool
    relation: str
    retained_sources: tuple[str, ...]


def _family_registry() -> dict[str, FamilyContract]:
    components = component_contracts(); sources = source_contracts(); output = {}
    for name in FAMILY_NAMES:
        component = components.get(name, components["FM"])
        retained = sources.get(name, sources["FM"])
        modalities = tuple(component["modalities"])
        if name.startswith("B") and not ({"LC", "DEM"} & set(retained)):
            modalities = tuple(value for value in modalities if value != "environmental")
        output[name] = FamilyContract(name, modalities, bool(component["scene_raster"]),
                                      str(component["relation"]), tuple(retained))
    return output


FAMILY_REGISTRY = _family_registry()


def family_contract(name: str) -> FamilyContract:
    if name not in FAMILY_REGISTRY:
        raise ValueError(f"unknown P9 model family: {name}")
    return FAMILY_REGISTRY[name]


def _dimension_contract(config: dict[str, Any]) -> tuple[int, int, float]:
    model = config["model"]
    d = int(model["d"]); heads = int(model["attention_heads"]); dropout = float(model["dropout"])
    if d not in (64, 128, 256) or int(model["d_c"]) != d or heads != 4 or d % heads:
        raise ValueError("P9 d/d_c/head contract mismatch")
    if int(model["head_dimension"]) != d // heads or int(model["ffn_dimension"]) != 2 * d:
        raise ValueError("P9 relative-to-d architecture mismatch")
    if (int(model["d_t"]), int(model["d_r"]), dropout) != (16, 32, 0.2):
        raise ValueError("P9 fixed auxiliary dimension/dropout mismatch")
    return d, heads, dropout


class P9SceneEncoder(nn.Module):
    """Instantiate only modules active in one P8 comparison family."""

    def __init__(self, config: dict[str, Any], vocabulary_sizes: dict[str, int], family: str = "FM") -> None:
        super().__init__(); self.contract = family_contract(family)
        d, heads, dropout = _dimension_contract(config); self.dimension = d
        self.raster_sources = (tuple(source for source in ("LC", "DEM") if source in self.contract.retained_sources)
                               if self.contract.scene_raster else ())
        self.environment_sources = tuple(source for source in ("LC", "DEM")
                                         if source in self.contract.retained_sources)
        if family == "DS":
            self.ds_cnn = RasterCNN(26)
            self.ds_projection = projected_block(64, 2 * d, d, dropout, True)
            self.contrastive_projection = nn.Sequential(nn.Linear(d, 2 * d), nn.LayerNorm(2 * d), nn.GELU(), nn.Linear(2 * d, d))
            return
        model = config["model"]
        wavelength = model["wavelengths"]
        self.register_buffer("wavelengths", torch.logspace(
            math.log10(float(wavelength["minimum_m"])), math.log10(float(wavelength["maximum_m"])),
            int(wavelength["count"])))
        self.position_encoder = projected_block(64, d, d, dropout, True)
        if "geometry" in self.contract.modalities:
            self.magnitude_encoder = projected_block(128, 2 * d, d, dropout, False)
            self.phase_encoder = projected_block(256, 2 * d, d, dropout, False)
            self.geometry_fusion = projected_block(2 * d, 2 * d, d, dropout, True)
        if "semantic" in self.contract.modalities:
            fixed = 32
            self.category_embeddings = nn.ModuleDict({name: nn.Embedding(vocabulary_sizes[name], fixed)
                                                      for name in ("A9", "A11", "ROAD_RANK", "ROAD_TYPE")})
            self.building_numerical = projected_block(4, d, fixed, dropout, False)
            self.building_fusion = projected_block(3 * fixed, 2 * d, d, dropout, True)
            self.road_numerical = nn.Sequential(nn.Linear(2, fixed), nn.LayerNorm(fixed), nn.GELU(), nn.Linear(fixed, fixed))
            self.road_fusion = projected_block(3 * fixed, 2 * d, d, dropout, True)
            poi_names = [f"CLASS_L{x}" for x in range(1, 7)]
            poi_dims = [int(value) for value in model["poi_hierarchy_dimensions"]]
            self.poi_embeddings = nn.ModuleList([nn.Embedding(vocabulary_sizes[name], width)
                                                  for name, width in zip(poi_names, poi_dims, strict=True)])
            self.poi_projections = nn.ModuleList([nn.Linear(width, fixed) for width in poi_dims])
            self.poi_score = nn.Sequential(nn.Linear(fixed, d), nn.Tanh(), nn.Linear(d, 1))
            self.poi_fusion = projected_block(sum(poi_dims) + fixed, 2 * d, d, dropout, True)
        if "environmental" in self.contract.modalities:
            environmental_width = (23 if "LC" in self.environment_sources else 0) + (3 if "DEM" in self.environment_sources else 0)
            if environmental_width == 0:
                raise ValueError("environmental modality requires at least one retained raster source")
            self.object_raster_encoder = projected_block(environmental_width, d, d, dropout, True)
        if len(self.contract.modalities) > 1:
            self.type_embedding = nn.Embedding(3, 16)
            self.gates = nn.ModuleDict({name: nn.Sequential(nn.Linear(d + 16, d), nn.GELU(), nn.Dropout(dropout), nn.Linear(d, d))
                                        for name in self.contract.modalities})
        self.entity_norm = nn.LayerNorm(d)
        if self.contract.relation != "none":
            relation_count = 5 if self.contract.relation == "heterogeneous" else 1
            self.relation_embedding = nn.Embedding(relation_count, 32)
            self.relation_layers = nn.ModuleList([RelationAwareLayer(d, heads, 32, 2 * d, dropout) for _ in range(3)])
        self.pool = nn.Sequential(nn.Linear(d, 32), nn.Tanh(), nn.Linear(32, 1))
        if self.contract.scene_raster:
            if "LC" in self.raster_sources:
                self.landcover_embedding = nn.Embedding(24, 16)
                self.landcover_cnn = RasterCNN(16)
                self.landcover_projection = projected_block(64, 2 * d, d, dropout, True)
            if "DEM" in self.raster_sources:
                self.dem_cnn = RasterCNN(1)
                self.dem_projection = projected_block(64, 2 * d, d, dropout, True)
        scene_inputs = 3 * d + len(self.raster_sources) * d
        self.scene_fusion = projected_block(scene_inputs, 2 * d, d, dropout, True)
        self.mask_embeddings = nn.Parameter(torch.empty(len(self.contract.modalities), d))
        nn.init.normal_(self.mask_embeddings, std=0.02)
        self.contrastive_projection = nn.Sequential(nn.Linear(d, 2 * d), nn.LayerNorm(2 * d), nn.GELU(), nn.Linear(2 * d, d))

    def _semantic(self, entities: dict[str, torch.Tensor]) -> torch.Tensor:
        d = self.dimension; output = torch.zeros((entities["local_entity_id"].numel(), d), device=entities["local_entity_id"].device)
        building = entities["building_row_index"]
        if building.numel():
            category = entities["building_category"]
            categorical = torch.cat((self.category_embeddings["A9"](category[:, 0]), self.category_embeddings["A11"](category[:, 1])), 1)
            numerical = self.building_numerical(torch.cat((entities["building_numerical"], entities["building_missing"].float()), 1))
            output[building] = self.building_fusion(torch.cat((categorical, numerical), 1))
        road = entities["road_row_index"]
        if road.numel():
            category = entities["road_category"]
            categorical = torch.cat((self.category_embeddings["ROAD_RANK"](category[:, 0]), self.category_embeddings["ROAD_TYPE"](category[:, 1])), 1)
            numerical = self.road_numerical(torch.cat((entities["road_numerical"], entities["road_missing"].float()), 1))
            output[road] = self.road_fusion(torch.cat((categorical, numerical), 1))
        poi = entities["poi_row_index"]
        if poi.numel():
            category = entities["poi_category"]; raw = [embedding(category[:, i]) for i, embedding in enumerate(self.poi_embeddings)]
            projected = torch.stack([projection(value) for projection, value in zip(self.poi_projections, raw, strict=True)], 1)
            weights = torch.softmax(self.poi_score(projected).squeeze(-1), 1)
            output[poi] = self.poi_fusion(torch.cat((*raw, (weights[:, :, None] * projected).sum(1)), 1))
        return output

    def _pool(self, values: torch.Tensor, types: torch.Tensor, scenes: torch.Tensor, count: int) -> torch.Tensor:
        result = values.new_zeros((count, 3, self.dimension)); scores = self.pool(values).squeeze(-1)
        for scene in range(count):
            for kind in range(3):
                rows = torch.nonzero((scenes == scene) & (types == kind)).flatten()
                if rows.numel(): result[scene, kind] = (torch.softmax(scores[rows], 0)[:, None] * values[rows]).sum(0)
        return result

    def forward(self, batch: dict[str, Any], geometry: tuple[torch.Tensor, torch.Tensor] | None = None,
                ds_raster: torch.Tensor | None = None, assignments: torch.Tensor | None = None) -> dict[str, torch.Tensor]:
        if self.contract.name == "DS":
            if ds_raster is None or ds_raster.ndim != 4 or ds_raster.shape[1:] != (26, 100, 100):
                raise ValueError("DS requires C_cat+4 (26) channels on the 100x100 grid")
            scene = self.ds_projection(self.ds_cnn(ds_raster)); contrastive = F.normalize(self.contrastive_projection(scene), dim=1)
            return {"scene_embedding": scene, "contrastive_embedding": contrastive, "ds_raster": ds_raster}
        entities = batch["entities"]; values: dict[str, torch.Tensor] = {}
        if self.contract.name.startswith("B"):
            allowed = {index for index, source in enumerate(("B", "R", "P"))
                       if source in self.contract.retained_sources}
            observed = set(int(value) for value in entities["entity_type"].unique().tolist())
            if not observed <= allowed:
                raise ValueError("B-series input contains an excluded entity source")
        values["relative"] = self.position_encoder(sinusoidal_position_features(entities["relative_position_m"], self.wavelengths))
        if "geometry" in self.contract.modalities:
            if geometry is None: raise ValueError("active geometry modality requires Fourier features")
            values["geometry"] = self.geometry_fusion(torch.cat((self.magnitude_encoder(geometry[0]), self.phase_encoder(geometry[1])), 1))
        if "semantic" in self.contract.modalities: values["semantic"] = self._semantic(entities)
        if "environmental" in self.contract.modalities:
            columns = []
            if "LC" in self.environment_sources:
                columns.append(entities["object_raster"][:, :23])
            if "DEM" in self.environment_sources:
                columns.append(entities["object_raster"][:, 23:26])
            values["environmental"] = self.object_raster_encoder(torch.cat(columns, dim=1))
        stacked = torch.stack([values[name] for name in self.contract.modalities], 1)
        if assignments is not None:
            if assignments.shape != (stacked.shape[0],): raise ValueError("P9 modality assignment shape mismatch")
            for modality in range(len(self.contract.modalities)):
                selected = assignments == modality
                if selected.any(): stacked[selected, modality] = self.mask_embeddings[modality]
        if len(self.contract.modalities) == 1:
            weights = torch.ones_like(stacked)
            contextual = self.entity_norm(stacked[:, 0])
        else:
            type_embedding = self.type_embedding(entities["entity_type"])
            logits = torch.stack([self.gates[name](torch.cat((values[name], type_embedding), 1)) for name in self.contract.modalities], 1)
            availability_map = {"relative": 0, "geometry": 1, "semantic": 2, "environmental": 3}
            available = torch.stack([entities["modality_available"][:, availability_map[name]].bool() for name in self.contract.modalities], 1)[:, :, None]
            weights = torch.softmax(logits.masked_fill(~available, -torch.inf), 1)
            contextual = self.entity_norm((weights * stacked).sum(1))
        if self.contract.relation != "none":
            if self.contract.relation == "generic":
                relation = self.relation_embedding(torch.zeros_like(batch["edges"]["relation_mask"], dtype=torch.long))
            else:
                relation = relation_set_embedding(batch["edges"]["relation_mask"].to(torch.uint8), self.relation_embedding)
            for layer in self.relation_layers:
                contextual = deterministic_relation_layer(layer, contextual, batch["edges"]["edge_index"], relation)
        type_summary = self._pool(contextual, entities["entity_type"], batch["entity_scene_index"], len(batch["scene_ids"]))
        scene_parts = [type_summary.flatten(1)]
        if self.contract.scene_raster:
            rasters = batch["rasters"]; fraction = rasters["landcover_class_fraction"]
            if "LC" in self.raster_sources:
                landcover = torch.einsum("bchw,cd->bdhw", fraction, self.landcover_embedding.weight[:22])
                valid = rasters["landcover_valid_mask"].bool(); intentional = rasters["landcover_intentional_mask"].bool()
                if torch.any(intentional & valid): raise ValueError("intentional land-cover mask overlaps valid support")
                landcover = torch.where(valid[:, None], landcover, self.landcover_embedding.weight[22][None, :, None, None])
                landcover = torch.where(intentional[:, None], self.landcover_embedding.weight[23][None, :, None, None], landcover)
                scene_parts.append(self.landcover_projection(self.landcover_cnn(landcover)))
            if "DEM" in self.raster_sources:
                scene_parts.append(self.dem_projection(self.dem_cnn(rasters["dem_standardized_mean"][:, None])))
        scene = self.scene_fusion(torch.cat(scene_parts, 1)); contrastive = F.normalize(self.contrastive_projection(scene), dim=1)
        return {"modalities": values, "modality_weights": weights, "entity": contextual,
                "scene_embedding": scene, "contrastive_embedding": contrastive}


class P9MomentumModel(nn.Module):
    def __init__(self, config: dict[str, Any], vocabulary_sizes: dict[str, int], family: str) -> None:
        super().__init__(); self.family = family; self.online = build_scene_encoder(config, vocabulary_sizes, family)
        self.target = copy.deepcopy(self.online); self.target.requires_grad_(False); self.target.eval()

    @torch.no_grad()
    def update_target(self, coefficient: float) -> None:
        online = dict(self.online.named_parameters())
        for name, target in self.target.named_parameters():
            target.mul_(coefficient).add_(online[name], alpha=1.0 - coefficient)
        online_buffers = dict(self.online.named_buffers())
        for name, target in self.target.named_buffers():
            target.copy_(online_buffers[name])


class P9FM64Encoder(ReducedSceneEncoder):
    """Expose P7's byte-identical FM encoder through the common P9 call contract."""

    def __init__(self, config: dict[str, Any], vocabulary_sizes: dict[str, int]) -> None:
        super().__init__(config, vocabulary_sizes)
        self.contract = family_contract("FM")

    def forward(self, batch: dict[str, Any], geometry: tuple[torch.Tensor, torch.Tensor] | None = None,
                ds_raster: torch.Tensor | None = None, assignments: torch.Tensor | None = None) -> dict[str, torch.Tensor]:
        if geometry is None or ds_raster is not None:
            raise ValueError("P9 FM d64 requires geometry and prohibits a DS raster")
        modalities = P7Model._modalities(self, batch, geometry)
        stacked = torch.stack(tuple(modalities[name] for name in ("relative", "geometry", "semantic", "environmental")), 1)
        if assignments is not None:
            assignments = assignments.to(stacked.device)
            if assignments.shape != (stacked.shape[0],):
                raise ValueError("P9 FM d64 modality assignment shape mismatch")
            for index in range(4):
                selected = assignments == index
                if selected.any():
                    stacked[selected, index] = self.mask_embeddings[index]
        return {**P7Model._finish(self, batch, stacked), "modalities": modalities}


def build_scene_encoder(config: dict[str, Any], vocabulary_sizes: dict[str, int], family: str) -> nn.Module:
    """Keep cfg_main byte-compatible with P7 while generalizing dimensions and families."""
    contract = family_contract(family)
    d, _, _ = _dimension_contract(config)
    return P9SceneEncoder(config, vocabulary_sizes, family)


def _bilinear_cell_centers(values: torch.Tensor, size: tuple[int, int] = (100, 100)) -> torch.Tensor:
    if values.shape[-2:] != (17, 17): raise ValueError("DS realized DEM must be 17x17")
    # align_corners=False maps target and source by cell centers.
    return F.interpolate(values[:, None], size=size, mode="bilinear", align_corners=False)[:, 0]


def ds_raster_from_batch(batch: dict[str, Any]) -> torch.Tensor:
    """Materialize the deterministic DS common raster from accepted P6 v3 tensors."""
    rasters = batch["rasters"]
    if not bool(rasters["dem_valid_mask"].bool().all()):
        raise ValueError("DS requires complete valid DEM support")
    landcover = rasters["landcover_class_fraction"].clone()
    masked = ~rasters["landcover_valid_mask"].bool() | rasters["landcover_intentional_mask"].bool()
    landcover = torch.where(masked[:, None], torch.zeros_like(landcover), landcover)
    count = len(batch["scene_ids"]); device = landcover.device
    if device.type != "cpu":
        raise ValueError("DS raster materialization must precede H2D")
    building = torch.zeros((count, 100, 100), dtype=torch.float32)
    road = torch.zeros_like(building); poi = torch.zeros_like(building)
    positions = batch["entities"]["relative_position_m"].double().numpy()
    types = batch["entities"]["entity_type"].numpy(); scenes = batch["entity_scene_index"].numpy()
    geometry = batch["geometry"]
    part_coordinates = geometry["part_coordinates_xy_m_scientific"].numpy()
    entity_coordinate_offsets = geometry["entity_coordinate_offsets"].numpy()
    entity_part_offsets = geometry["entity_part_offsets"].numpy()
    part_offsets = geometry["part_coordinate_offsets"].numpy()
    ring_coordinates = geometry["ring_coordinates_xy_m_scientific"].numpy()
    entity_ring_offsets = geometry["entity_ring_offsets"].numpy()
    ring_start = geometry["ring_coordinate_start"].numpy(); ring_end = geometry["ring_coordinate_end"].numpy()
    ring_hole = geometry["ring_is_hole"].numpy(); ring_component = geometry["ring_component_index"].numpy()

    def bounds(geom):
        xmin, ymin, xmax, ymax = geom.bounds
        c0 = max(0, int(math.floor((xmin + 250.0) / 5.0))); c1 = min(99, int(math.floor((xmax + 250.0) / 5.0)))
        r0 = max(0, int(math.floor((250.0 - ymax) / 5.0))); r1 = min(99, int(math.floor((250.0 - ymin) / 5.0)))
        return r0, r1, c0, c1

    def cell(row: int, column: int):
        xmin = -250.0 + 5.0 * column; xmax = xmin + 5.0
        ymax = 250.0 - 5.0 * row; ymin = ymax - 5.0
        return shapely.box(xmin, ymin, xmax, ymax)

    for index, kind in enumerate(types):
        scene = int(scenes[index]); center = positions[index]
        if int(kind) == 2:
            column = min(99, max(0, int(math.floor((center[0] + 250.0) / 5.0))))
            row = min(99, max(0, int(math.floor((250.0 - center[1]) / 5.0))))
            poi[scene, row, column] += 1.0
            continue
        if int(kind) == 0:
            grouped: dict[int, dict[str, Any]] = {}
            for ring_index in range(int(entity_ring_offsets[index]), int(entity_ring_offsets[index + 1])):
                component = int(ring_component[ring_index] - entity_part_offsets[index])
                values = ring_coordinates[int(ring_start[ring_index]):int(ring_end[ring_index])] + center
                group = grouped.setdefault(component, {"shell": None, "holes": []})
                if bool(ring_hole[ring_index]): group["holes"].append(values)
                else: group["shell"] = values
            polygons = [shapely.Polygon(value["shell"], value["holes"])
                        for _, value in sorted(grouped.items()) if value["shell"] is not None]
            shape = shapely.MultiPolygon(polygons) if len(polygons) > 1 else polygons[0] if polygons else None
            if shape is None or shape.is_empty: continue
            r0, r1, c0, c1 = bounds(shape)
            for row in range(r0, r1 + 1):
                for column in range(c0, c1 + 1):
                    area = float(shape.intersection(cell(row, column)).area)
                    if area: building[scene, row, column] = min(1.0, float(building[scene, row, column]) + area / 25.0)
        else:
            parts = []
            for part in range(int(entity_part_offsets[index]), int(entity_part_offsets[index + 1])):
                values = part_coordinates[int(part_offsets[part]):int(part_offsets[part + 1])] + center
                if len(values) >= 2: parts.append(shapely.LineString(values))
            shape = shapely.MultiLineString(parts) if len(parts) > 1 else parts[0] if parts else None
            if shape is None or shape.is_empty: continue
            r0, r1, c0, c1 = bounds(shape)
            for row in range(r0, r1 + 1):
                for column in range(c0, c1 + 1):
                    if shape.intersects(cell(row, column)): road[scene, row, column] = 1.0
    poi = torch.log1p(poi)
    dem = _bilinear_cell_centers(rasters["dem_standardized_mean"])
    result = torch.cat((building[:, None], road[:, None], poi[:, None], landcover, dem[:, None]), 1)
    if result.shape[1:] != (26, 100, 100) or not torch.isfinite(result).all():
        raise ValueError("invalid DS raster materialization")
    return result


def active_parameter_names(model: nn.Module) -> tuple[str, ...]:
    return tuple(name for name, value in model.named_parameters() if value.requires_grad)
