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
from p7_training import DECODER_PREFIXES, P7Model, deterministic_relation_layer
from prototype_encoder import geometry_fourier_features, relation_set_embedding, sinusoidal_position_features

FAMILY_NAMES = ("FM", "A1", "A2", "A3", "A4", "A5", "SSV", "DS")


@dataclass(frozen=True)
class FamilyContract:
    name: str
    modalities: tuple[str, ...]
    ip_terms: tuple[str, ...]
    scene_raster: bool
    relation: str
    lambda_ip: float | None = None


FAMILY_REGISTRY = {
    "FM": FamilyContract("FM", ("relative", "geometry", "semantic", "environmental"),
                         ("relative", "geometry", "semantic", "environmental"), True, "heterogeneous"),
    "A1": FamilyContract("A1", ("relative", "geometry"), ("relative", "geometry"), False, "none"),
    "A2": FamilyContract("A2", ("relative", "geometry", "semantic"),
                         ("relative", "geometry", "semantic"), False, "none"),
    "A3": FamilyContract("A3", ("relative", "geometry", "semantic", "environmental"),
                         ("relative", "geometry", "semantic", "environmental"), False, "none"),
    "A4": FamilyContract("A4", ("relative", "geometry", "semantic", "environmental"),
                         ("relative", "geometry", "semantic", "environmental"), True, "none"),
    "A5": FamilyContract("A5", ("relative", "geometry", "semantic", "environmental"),
                         ("relative", "geometry", "semantic", "environmental"), True, "generic"),
    "SSV": FamilyContract("SSV", ("relative", "semantic"), ("relative", "semantic"), False, "none"),
    "DS": FamilyContract("DS", (), (), True, "none", 0.0),
}


def family_contract(name: str) -> FamilyContract:
    if name not in FAMILY_REGISTRY:
        raise ValueError(f"unknown P9 model family: {name}")
    return FAMILY_REGISTRY[name]


def _dimension_contract(config: dict[str, Any]) -> tuple[int, int, float]:
    model = config["model"]
    d = int(model["d"]); heads = int(model["attention_heads"]); dropout = float(model["dropout"])
    if d not in (48, 64, 128) or int(model["d_c"]) != d or heads != 4 or d % heads:
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
            self.object_raster_encoder = projected_block(26, d, d, dropout, True)
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
            self.landcover_embedding = nn.Embedding(24, 16)
            self.landcover_cnn = RasterCNN(16); self.dem_cnn = RasterCNN(1)
            self.landcover_projection = projected_block(64, 2 * d, d, dropout, True)
            self.dem_projection = projected_block(64, 2 * d, d, dropout, True)
        scene_inputs = 3 * d + (2 * d if self.contract.scene_raster else 0)
        self.scene_fusion = projected_block(scene_inputs, 2 * d, d, dropout, True)
        self.mask_embeddings = nn.Parameter(torch.empty(len(self.contract.modalities), d))
        nn.init.normal_(self.mask_embeddings, std=0.02)
        self.contrastive_projection = nn.Sequential(nn.Linear(d, 2 * d), nn.LayerNorm(2 * d), nn.GELU(), nn.Linear(2 * d, d))
        if "relative" in self.contract.ip_terms:
            self.relative_position_decoder = nn.Sequential(nn.Linear(d, d), nn.GELU(), nn.Linear(d, 2))
        if "geometry" in self.contract.ip_terms:
            self.geometry_decoder_shared = nn.Sequential(nn.Linear(d, 2 * d), nn.GELU())
            self.geometry_magnitude_head = nn.Linear(2 * d, 128); self.geometry_phase_head = nn.Linear(2 * d, 256)
        if "semantic" in self.contract.ip_terms:
            self.attribute_decoder_shared = nn.ModuleDict({name: nn.Sequential(nn.Linear(d, d), nn.GELU()) for name in ("B","R","P")})
            self.building_decoder_heads = nn.ModuleDict({"A9":nn.Linear(d,vocabulary_sizes["A9"]),"A11":nn.Linear(d,vocabulary_sizes["A11"]),"numerical":nn.Linear(d,2)})
            self.road_decoder_heads = nn.ModuleDict({"ROAD_RANK":nn.Linear(d,vocabulary_sizes["ROAD_RANK"]),"ROAD_TYPE":nn.Linear(d,vocabulary_sizes["ROAD_TYPE"]),"numerical":nn.Linear(d,1)})
            self.poi_decoder_heads = nn.ModuleList([nn.Linear(d,vocabulary_sizes[f"CLASS_L{x}"]) for x in range(1,7)])
        if "environmental" in self.contract.ip_terms:
            self.environment_decoder_shared = nn.Sequential(nn.Linear(d,d),nn.GELU())
            self.environment_composition_head = nn.Linear(d,22); self.environment_continuous_head = nn.Linear(d,4)

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
        values["relative"] = self.position_encoder(sinusoidal_position_features(entities["relative_position_m"], self.wavelengths))
        if "geometry" in self.contract.modalities:
            if geometry is None: raise ValueError("active geometry modality requires Fourier features")
            values["geometry"] = self.geometry_fusion(torch.cat((self.magnitude_encoder(geometry[0]), self.phase_encoder(geometry[1])), 1))
        if "semantic" in self.contract.modalities: values["semantic"] = self._semantic(entities)
        if "environmental" in self.contract.modalities: values["environmental"] = self.object_raster_encoder(entities["object_raster"])
        stacked = torch.stack([values[name] for name in self.contract.modalities], 1)
        if assignments is not None:
            if assignments.shape != (stacked.shape[0],): raise ValueError("P9 modality assignment shape mismatch")
            for modality in range(len(self.contract.modalities)):
                selected = assignments == modality
                if selected.any(): stacked[selected, modality] = self.mask_embeddings[modality]
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
            landcover = torch.einsum("bchw,cd->bdhw", fraction, self.landcover_embedding.weight[:22])
            valid = rasters["landcover_valid_mask"].bool(); intentional = rasters["landcover_intentional_mask"].bool()
            if torch.any(intentional & valid): raise ValueError("intentional land-cover mask overlaps valid support")
            landcover = torch.where(valid[:, None], landcover, self.landcover_embedding.weight[22][None, :, None, None])
            landcover = torch.where(intentional[:, None], self.landcover_embedding.weight[23][None, :, None, None], landcover)
            scene_parts.extend((self.landcover_projection(self.landcover_cnn(landcover)),
                                self.dem_projection(self.dem_cnn(rasters["dem_standardized_mean"][:, None]))))
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
            if name.startswith(DECODER_PREFIXES):
                continue
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
    if contract.name == "FM" and d == 64:
        return P9FM64Encoder(config, vocabulary_sizes)
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


def p9_reconstruction_terms(model: P9SceneEncoder, batch: dict[str, Any], geometry: tuple[torch.Tensor, torch.Tensor] | None,
                            modalities: dict[str, torch.Tensor], masks: dict[str, int], delta: float = 1.0,
                            phase_threshold: float = 0.05) -> dict[str, dict[str, torch.Tensor | int]]:
    """P7 reconstruction semantics restricted exactly to the family's retained IP terms."""
    entities=batch["entities"]; result={}; active=model.contract.ip_terms
    if "relative" in active:
        values=F.huber_loss(model.relative_position_decoder(modalities["relative"]),entities["relative_position_m"]/500.0,
                            delta=delta,reduction="none").mean(1)
        result["relative"]={"sum":values.sum(),"count":values.numel()}
    if "geometry" in active:
        assert geometry is not None; rows=entities["entity_type"]!=2; hidden=model.geometry_decoder_shared(modalities["geometry"][rows])
        if hidden.shape[0]:
            magnitude=F.huber_loss(model.geometry_magnitude_head(hidden),geometry[0][rows],delta=delta,reduction="none").mean(1)
            target=geometry[1][rows].reshape(-1,128,2); prediction=model.geometry_phase_head(hidden).reshape(-1,128,2)
            raw=torch.expm1(geometry[0][rows]).clamp_min(0); maximum=raw.amax(1,keepdim=True)
            valid=(maximum>0)&(raw/maximum.clamp_min(torch.finfo(raw.dtype).tiny)>=phase_threshold)
            phase_components=1.0-F.cosine_similarity(prediction,target,dim=2); has=valid.any(1)
            phase=torch.zeros_like(magnitude); phase[has]=(phase_components[has]*valid[has]).sum(1)/valid[has].sum(1)
            values=torch.where(has,0.5*(magnitude+phase),magnitude)
        else: values=modalities["geometry"].sum().reshape(1)*0.0
        result["geometry"]={"sum":values.sum(),"count":int(rows.sum())}
    if "semantic" in active:
        collected=[]
        for prefix,names,numerical in (("building",("A9","A11"),2),("road",("ROAD_RANK","ROAD_TYPE"),1),("poi",tuple(f"CLASS_L{x}" for x in range(1,7)),0)):
            rows=entities[f"{prefix}_row_index"]; hidden=model.attribute_decoder_shared[{"building":"B","road":"R","poi":"P"}[prefix]](modalities["semantic"][rows])
            numerator=hidden.new_zeros(rows.numel()); denominator=hidden.new_zeros(rows.numel()); category=entities[f"{prefix}_category"]
            for column,name in enumerate(names):
                logits=model.poi_decoder_heads[column](hidden) if prefix=="poi" else getattr(model,f"{prefix}_decoder_heads")[name](hidden)
                values=F.cross_entropy(logits,category[:,column],reduction="none") if rows.numel() else hidden.new_empty(0)
                valid=category[:,column]!=int(masks[name]); numerator+=torch.where(valid,values,torch.zeros_like(values)); denominator+=valid
            if numerical:
                prediction=getattr(model,f"{prefix}_decoder_heads")["numerical"](hidden); target=entities[f"{prefix}_numerical"]; missing=entities[f"{prefix}_missing"].bool()
                for column in range(numerical):
                    values=F.huber_loss(prediction[:,column],target[:,column],delta=delta,reduction="none"); valid=~missing[:,column]
                    numerator+=torch.where(valid,values,torch.zeros_like(values)); denominator+=valid
            if rows.numel(): collected.append(numerator[denominator>0]/denominator[denominator>0])
        values=torch.cat(collected) if collected else modalities["semantic"].new_empty(0)
        result["semantic"]={"sum":values.sum(),"count":values.numel()}
    if "environmental" in active:
        hidden=model.environment_decoder_shared(modalities["environmental"]); context=entities["object_raster"]
        composition=-(context[:,:22]*F.log_softmax(model.environment_composition_head(hidden),1)).sum(1); composition_valid=context[:,22]>0
        continuous=F.huber_loss(model.environment_continuous_head(hidden),context[:,22:26],delta=delta,reduction="none")
        valid=torch.ones_like(continuous,dtype=torch.bool); valid[:,1]=context[:,25]>0; valid[:,2]=context[:,25]>0
        numerator=torch.where(composition_valid,composition,torch.zeros_like(composition)); denominator=composition_valid.float()
        for index in range(4): numerator+=torch.where(valid[:,index],continuous[:,index],torch.zeros_like(numerator)); denominator+=valid[:,index]
        values=numerator[denominator>0]/denominator[denominator>0]
        result["environmental"]={"sum":values.sum(),"count":values.numel()}
    if set(result)!=set(active): raise ValueError("P9 active IP loss composition mismatch")
    return result
