"""Reduced-dissertation d64 scene encoder and reconstruction heads for P6."""

from __future__ import annotations

import math
from typing import Any

import torch
from torch import nn

from prototype_encoder import geometry_fourier_features, relation_set_embedding, sinusoidal_position_features


def projected_block(input_dim: int, hidden_dim: int, output_dim: int, dropout: float, final_ln: bool) -> nn.Sequential:
    layers: list[nn.Module] = [
        nn.Linear(input_dim, hidden_dim), nn.LayerNorm(hidden_dim), nn.GELU(),
        nn.Dropout(dropout), nn.Linear(hidden_dim, output_dim),
    ]
    if final_ln:
        layers.append(nn.LayerNorm(output_dim))
    return nn.Sequential(*layers)


class RelationAwareLayer(nn.Module):
    """Post-norm relation-aware attention from methodology Eq. 19-22."""

    def __init__(self, dimension: int = 64, heads: int = 4, relation_dimension: int = 32,
                 ffn_dimension: int = 128, dropout: float = 0.2) -> None:
        super().__init__()
        if dimension != heads * (dimension // heads):
            raise ValueError("attention head dimensions do not divide d")
        self.heads = heads
        self.head_dimension = dimension // heads
        self.query = nn.Linear(dimension, dimension)
        self.key = nn.Linear(dimension, dimension)
        self.value = nn.Linear(dimension, dimension)
        self.relation_bias = nn.Parameter(torch.empty(heads, relation_dimension))
        self.relation_value = nn.Parameter(torch.empty(heads, self.head_dimension, relation_dimension))
        self.output = nn.Linear(dimension, dimension)
        self.norm_attention = nn.LayerNorm(dimension)
        self.ffn = nn.Sequential(
            nn.Linear(dimension, ffn_dimension), nn.GELU(), nn.Dropout(dropout),
            nn.Linear(ffn_dimension, dimension),
        )
        self.norm_ffn = nn.LayerNorm(dimension)
        self.dropout = nn.Dropout(dropout)
        nn.init.xavier_uniform_(self.relation_bias)
        nn.init.xavier_uniform_(self.relation_value.flatten(1))

    def forward(self, values: torch.Tensor, edge_index: torch.Tensor, relation: torch.Tensor) -> torch.Tensor:
        count = values.shape[0]
        if edge_index.shape[1] == 0:
            message = torch.zeros_like(values)
        else:
            source, destination = edge_index
            query = self.query(values).view(count, self.heads, self.head_dimension)
            key = self.key(values).view(count, self.heads, self.head_dimension)
            val = self.value(values).view(count, self.heads, self.head_dimension)
            score = (query[source] * key[destination]).sum(-1) / math.sqrt(self.head_dimension)
            score = score + torch.einsum("er,hr->eh", relation, self.relation_bias)
            scatter_index = source[:, None].expand(-1, self.heads)
            maxima = torch.full((count, self.heads), -torch.inf, dtype=values.dtype, device=values.device)
            maxima.scatter_reduce_(0, scatter_index, score, reduce="amax", include_self=True)
            exponent = torch.exp(score - maxima[source])
            denominator = torch.zeros((count, self.heads), dtype=values.dtype, device=values.device)
            denominator.scatter_add_(0, scatter_index, exponent)
            weight = exponent / denominator[source]
            relation_message = torch.einsum("hdr,er->ehd", self.relation_value, relation)
            edge_message = weight[:, :, None] * (val[destination] + relation_message)
            aggregate = torch.zeros((count, self.heads, self.head_dimension), dtype=values.dtype, device=values.device)
            aggregate.index_add_(0, source, edge_message)
            message = self.output(aggregate.flatten(1))
        intermediate = self.norm_attention(values + self.dropout(message))
        return self.norm_ffn(intermediate + self.dropout(self.ffn(intermediate)))


class RasterCNN(nn.Module):
    def __init__(self, input_channels: int) -> None:
        super().__init__()
        layers: list[nn.Module] = []
        for source, destination in ((input_channels, 32), (32, 64), (64, 64)):
            layers.extend((
                nn.Conv2d(source, destination, 3, stride=2, padding=1),
                nn.GroupNorm(8, destination), nn.GELU(),
            ))
        self.network = nn.Sequential(*layers)

    def forward(self, values: torch.Tensor) -> torch.Tensor:
        return self.network(values).mean(dim=(-2, -1))


class ReducedSceneEncoder(nn.Module):
    """Complete d64 encoder plus architecture-table projection/decoder modules."""

    def __init__(self, config: dict[str, Any], vocabulary_sizes: dict[str, int]) -> None:
        super().__init__()
        model = config["model"]
        d, dropout = int(model["d"]), float(model["dropout"])
        if (d, int(model["d_c"]), int(model["d_t"]), int(model["d_r"])) != (64, 64, 16, 32):
            raise ValueError("reduced model dimension contract mismatch")
        if (int(model["attention_heads"]), int(model["head_dimension"]), int(model["ffn_dimension"])) != (4, 16, 128):
            raise ValueError("reduced attention/FFN contract mismatch")
        if dropout != 0.2:
            raise ValueError("reduced dropout contract mismatch")
        wavelength = model["wavelengths"]
        self.register_buffer("wavelengths", torch.logspace(
            math.log10(float(wavelength["minimum_m"])), math.log10(float(wavelength["maximum_m"])),
            int(wavelength["count"]),
        ))
        self.position_encoder = projected_block(64, 64, 64, dropout, True)
        self.magnitude_encoder = projected_block(128, 128, 64, dropout, False)
        self.phase_encoder = projected_block(256, 128, 64, dropout, False)
        self.geometry_fusion = projected_block(128, 128, 64, dropout, True)
        non_poi = ("A9", "A11", "ROAD_RANK", "ROAD_TYPE")
        self.category_embeddings = nn.ModuleDict({name: nn.Embedding(vocabulary_sizes[name], 32) for name in non_poi})
        self.building_numerical = projected_block(4, 64, 32, dropout, False)
        self.building_fusion = projected_block(96, 128, 64, dropout, True)
        self.road_numerical = nn.Sequential(nn.Linear(2, 32), nn.LayerNorm(32), nn.GELU(), nn.Linear(32, 32))
        self.road_fusion = projected_block(96, 128, 64, dropout, True)
        poi_names = [f"CLASS_L{index}" for index in range(1, 7)]
        poi_dimensions = [int(value) for value in model["poi_hierarchy_dimensions"]]
        self.poi_embeddings = nn.ModuleList([
            nn.Embedding(vocabulary_sizes[name], dimension) for name, dimension in zip(poi_names, poi_dimensions, strict=True)
        ])
        self.poi_projections = nn.ModuleList([nn.Linear(dimension, 32) for dimension in poi_dimensions])
        self.poi_score = nn.Sequential(nn.Linear(32, 64), nn.Tanh(), nn.Linear(64, 1))
        self.poi_fusion = projected_block(140, 128, 64, dropout, True)
        self.object_raster_encoder = projected_block(26, 64, 64, dropout, True)
        self.type_embedding = nn.Embedding(3, 16)
        self.gates = nn.ModuleList([
            nn.Sequential(nn.Linear(80, 64), nn.GELU(), nn.Dropout(dropout), nn.Linear(64, 64))
            for _ in range(4)
        ])
        self.entity_norm = nn.LayerNorm(64)
        self.relation_embedding = nn.Embedding(5, 32)
        self.relation_layers = nn.ModuleList([
            RelationAwareLayer(64, 4, 32, 128, dropout) for _ in range(3)
        ])
        self.pool = nn.Sequential(nn.Linear(64, 32), nn.Tanh(), nn.Linear(32, 1))
        self.landcover_embedding = nn.Embedding(24, 16)
        self.landcover_cnn = RasterCNN(16)
        self.dem_cnn = RasterCNN(1)
        self.landcover_projection = projected_block(64, 128, 64, dropout, True)
        self.dem_projection = projected_block(64, 128, 64, dropout, True)
        self.scene_fusion = projected_block(320, 128, 64, dropout, True)
        self.mask_embeddings = nn.Parameter(torch.empty(4, 64))
        nn.init.normal_(self.mask_embeddings, std=0.02)
        self.contrastive_projection = nn.Sequential(nn.Linear(64, 128), nn.LayerNorm(128), nn.GELU(), nn.Linear(128, 64))
        self.relative_position_decoder = nn.Sequential(nn.Linear(64, 64), nn.GELU(), nn.Linear(64, 2))
        self.geometry_decoder_shared = nn.Sequential(nn.Linear(64, 128), nn.GELU())
        self.geometry_magnitude_head = nn.Linear(128, 128)
        self.geometry_phase_head = nn.Linear(128, 256)
        self.attribute_decoder_shared = nn.ModuleDict({name: nn.Sequential(nn.Linear(64, 64), nn.GELU()) for name in ("B", "R", "P")})
        self.building_decoder_heads = nn.ModuleDict({
            "A9": nn.Linear(64, vocabulary_sizes["A9"]), "A11": nn.Linear(64, vocabulary_sizes["A11"]),
            "numerical": nn.Linear(64, 2),
        })
        self.road_decoder_heads = nn.ModuleDict({
            "ROAD_RANK": nn.Linear(64, vocabulary_sizes["ROAD_RANK"]),
            "ROAD_TYPE": nn.Linear(64, vocabulary_sizes["ROAD_TYPE"]), "numerical": nn.Linear(64, 1),
        })
        self.poi_decoder_heads = nn.ModuleList([nn.Linear(64, vocabulary_sizes[name]) for name in poi_names])
        self.environment_decoder_shared = nn.Sequential(nn.Linear(64, 64), nn.GELU())
        self.environment_composition_head = nn.Linear(64, 22)
        self.environment_continuous_head = nn.Linear(64, 4)

    def _semantic(self, entities: dict[str, torch.Tensor]) -> torch.Tensor:
        output = torch.zeros((entities["local_entity_id"].numel(), 64), device=entities["local_entity_id"].device)
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
            category = entities["poi_category"]
            raw = [embedding(category[:, index]) for index, embedding in enumerate(self.poi_embeddings)]
            projected = torch.stack([projection(value) for projection, value in zip(self.poi_projections, raw, strict=True)], 1)
            weights = torch.softmax(self.poi_score(projected).squeeze(-1), 1)
            output[poi] = self.poi_fusion(torch.cat((*raw, (weights[:, :, None] * projected).sum(1)), 1))
        return output

    def _type_pool(self, values: torch.Tensor, types: torch.Tensor, scenes: torch.Tensor, scene_count: int) -> torch.Tensor:
        result = torch.zeros((scene_count, 3, 64), device=values.device, dtype=values.dtype)
        scores = self.pool(values).squeeze(-1)
        for scene in range(scene_count):
            for entity_type in range(3):
                index = torch.nonzero((scenes == scene) & (types == entity_type)).flatten()
                if index.numel():
                    result[scene, entity_type] = (torch.softmax(scores[index], 0)[:, None] * values[index]).sum(0)
        return result

    def forward(self, batch: dict[str, Any], precomputed_geometry: tuple[torch.Tensor, torch.Tensor] | None = None) -> dict[str, torch.Tensor]:
        entities, edges, rasters = batch["entities"], batch["edges"], batch["rasters"]
        position = self.position_encoder(sinusoidal_position_features(entities["relative_position_m"], self.wavelengths))
        magnitude, phase = precomputed_geometry or geometry_fourier_features(batch, {"geometry": {
            "minimum_radial_frequency": 0.5, "maximum_radial_frequency": 50.0,
            "radial_frequencies": 8, "angular_orientations": 16, "normalization_length_m": 500.0,
        }}, position.device)
        geometry = self.geometry_fusion(torch.cat((self.magnitude_encoder(magnitude), self.phase_encoder(phase)), 1))
        semantic = self._semantic(entities)
        background = self.object_raster_encoder(entities["object_raster"])
        modalities = torch.stack((position, geometry, semantic, background), 1)
        type_embedding = self.type_embedding(entities["entity_type"])
        logits = torch.stack([gate(torch.cat((modalities[:, index], type_embedding), 1)) for index, gate in enumerate(self.gates)], 1)
        available = entities["modality_available"].bool()[:, :, None]
        weights = torch.softmax(logits.masked_fill(~available, -torch.inf), 1)
        initial = self.entity_norm((weights * modalities).sum(1))
        relation = relation_set_embedding(edges["relation_mask"].to(torch.uint8), self.relation_embedding)
        contextual = initial
        for layer in self.relation_layers:
            contextual = layer(contextual, edges["edge_index"], relation)
        type_summary = self._type_pool(contextual, entities["entity_type"], batch["entity_scene_index"], len(batch["scene_ids"]))
        fraction = rasters["landcover_class_fraction"]
        landcover = torch.einsum("bchw,cd->bdhw", fraction, self.landcover_embedding.weight[:22])
        valid = rasters["landcover_valid_mask"].bool()
        landcover = torch.where(valid[:, None], landcover, self.landcover_embedding.weight[22][None, :, None, None])
        landcover_scene = self.landcover_projection(self.landcover_cnn(landcover))
        dem_scene = self.dem_projection(self.dem_cnn(rasters["dem_standardized_mean"][:, None]))
        scene = self.scene_fusion(torch.cat((type_summary.flatten(1), landcover_scene, dem_scene), 1))
        contrastive = torch.nn.functional.normalize(self.contrastive_projection(scene), dim=1)
        return {
            "relative_position": position, "geometry": geometry, "semantic": semantic,
            "object_raster": background, "modality_weights": weights, "entity": contextual,
            "type_summary": type_summary, "landcover_scene": landcover_scene, "dem_scene": dem_scene,
            "scene_embedding": scene, "contrastive_embedding": contrastive,
        }


def parameter_counts(model: nn.Module) -> dict[str, Any]:
    by_module = {name: sum(value.numel() for value in module.parameters(recurse=False)) for name, module in model.named_modules() if name}
    trainable = sum(value.numel() for value in model.parameters() if value.requires_grad)
    non_trainable = sum(value.numel() for value in model.parameters() if not value.requires_grad)
    return {"trainable": trainable, "non_trainable": non_trainable, "total": trainable + non_trainable,
            "by_module": {key: value for key, value in sorted(by_module.items()) if value}}
