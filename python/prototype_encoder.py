"""Thesis-exact prototype scene encoder used by the I18 GPU smoke."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import torch
from shapely import Polygon
from torch import nn
import triangle


_FREQUENCY_CACHE: dict[tuple[str, float, float, int, int], torch.Tensor] = {}


def mlp(*layers: Any) -> nn.Sequential:
    return nn.Sequential(*layers)


def projected_block(input_dim: int, hidden_dim: int, output_dim: int, dropout: float, final_ln: bool) -> nn.Sequential:
    layers: list[nn.Module] = [
        nn.Linear(input_dim, hidden_dim), nn.LayerNorm(hidden_dim), nn.GELU(), nn.Dropout(dropout),
        nn.Linear(hidden_dim, output_dim),
    ]
    if final_ln:
        layers.append(nn.LayerNorm(output_dim))
    return nn.Sequential(*layers)


def sinusoidal_position_features(position_m: torch.Tensor, wavelengths: torch.Tensor) -> torch.Tensor:
    phase = 2.0 * torch.pi * position_m[:, :, None] / wavelengths[None, None, :]
    return torch.stack((phase[:, 0].sin(), phase[:, 0].cos(), phase[:, 1].sin(), phase[:, 1].cos()), dim=2).flatten(1)


def relation_set_embedding(relation_mask: torch.Tensor, embedding: nn.Embedding) -> torch.Tensor:
    bits = torch.arange(5, device=relation_mask.device, dtype=torch.uint8)
    active = ((relation_mask[:, None] >> bits[None, :]) & 1).to(embedding.weight.dtype)
    return active @ embedding.weight


def segment_fourier(points: torch.Tensor, frequencies: torch.Tensor) -> torch.Tensor:
    if points.shape[0] < 2:
        return torch.zeros(frequencies.shape[0], dtype=torch.complex64, device=frequencies.device)
    start, end = points[:-1], points[1:]
    delta = end - start
    length = torch.linalg.vector_norm(delta, dim=1)
    midpoint = (start + end) * 0.5
    dot_delta = delta @ frequencies.T
    dot_midpoint = midpoint @ frequencies.T
    response = length[:, None] * torch.exp(-2j * torch.pi * dot_midpoint) * torch.sinc(dot_delta)
    return response.sum(dim=0).to(torch.complex64)


def _triangle_fourier(triangles: np.ndarray, frequencies: torch.Tensor) -> torch.Tensor:
    total = torch.zeros(frequencies.shape[0], dtype=torch.complex64, device=frequencies.device)
    u, v = frequencies[:, 0], frequencies[:, 1]
    for triangle_vertices in triangles:
        tri = torch.as_tensor(triangle_vertices, dtype=torch.float32, device=frequencies.device)
        canonical = torch.tensor([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]], device=frequencies.device)
        source = torch.cat((tri.T, torch.ones((1, 3), device=frequencies.device)), dim=0)
        target = torch.cat((canonical.T, torch.ones((1, 3), device=frequencies.device)), dim=0)
        transform = target @ torch.linalg.inv(source)
        a, b, x0 = transform[0]
        c, d, y0 = transform[1]
        determinant = a * d - b * c
        area = 1.0 / (2.0 * determinant.abs())
        x = (b * y0 - d * x0) / determinant
        y = (c * x0 - a * y0) / determinant
        phase = torch.exp(-2j * torch.pi * (u * x + v * y))
        transformed_u = (u * d - v * c) / determinant
        transformed_v = (v * a - u * b) / determinant
        uv = transformed_u + transformed_v
        epsilon = torch.finfo(torch.float32).eps * 16
        zero_u = transformed_u.abs() <= epsilon
        zero_v = transformed_v.abs() <= epsilon
        zero_uv = uv.abs() <= epsilon
        both_zero = zero_u & zero_v
        safe_u = torch.where(zero_u, torch.ones_like(transformed_u), transformed_u)
        safe_v = torch.where(zero_v, torch.ones_like(transformed_v), transformed_v)
        safe_uv = torch.where(zero_uv, torch.ones_like(uv), uv)
        base_u = torch.exp(-2j * torch.pi * transformed_u)
        base_v = torch.exp(-2j * torch.pi * transformed_v)
        base_uv = torch.exp(-2j * torch.pi * uv)
        response = (
            (transformed_u * (-base_uv) + uv * base_u - transformed_v)
            / (4 * torch.pi**2 * safe_u * safe_v * safe_uv)
        )
        response_uv = -(base_u + 2j * torch.pi * transformed_u - 1) / (4 * torch.pi**2 * safe_u**2)
        response_v = ((2j * torch.pi * transformed_u + 1) * base_u - 1) / (4 * torch.pi**2 * safe_u**2)
        response_u = -(base_v + 2j * torch.pi * transformed_v - 1) / (4 * torch.pi**2 * safe_v**2)
        response = torch.where(zero_uv, response_uv, response)
        response = torch.where(zero_v, response_v, response)
        response = torch.where(zero_u, response_u, response)
        response = torch.where(both_zero, area.to(torch.complex64), response / determinant.abs() * phase)
        total += response.to(torch.complex64)
    return total


def _geometry_frequencies(config: dict[str, Any], device: torch.device) -> torch.Tensor:
    key = (
        str(device),
        float(config["geometry"]["minimum_radial_frequency"]),
        float(config["geometry"]["maximum_radial_frequency"]),
        int(config["geometry"]["radial_frequencies"]),
        int(config["geometry"]["angular_orientations"]),
    )
    cached = _FREQUENCY_CACHE.get(key)
    if cached is not None:
        return cached
    radial = torch.logspace(math.log10(key[1]), math.log10(key[2]), key[3], device=device)
    theta = torch.arange(key[4], device=device) * torch.pi / key[4]
    cached = torch.stack(((radial[:, None] * theta.cos()).flatten(), (radial[:, None] * theta.sin()).flatten()), dim=1)
    _FREQUENCY_CACHE[key] = cached
    return cached


def _triangle_fourier_batched(triangles: np.ndarray, frequencies: torch.Tensor) -> torch.Tensor:
    """Evaluate all triangles together while retaining the accepted analytic response."""
    if len(triangles) == 0:
        return torch.zeros(frequencies.shape[0], dtype=torch.complex64, device=frequencies.device)
    canonical = torch.tensor([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]], device=frequencies.device)
    target = torch.cat((canonical.T, torch.ones((1, 3), device=frequencies.device)), dim=0)
    transforms=[]
    for triangle_vertices in triangles:
        tri=torch.as_tensor(triangle_vertices,dtype=torch.float32,device=frequencies.device)
        source=torch.cat((tri.T,torch.ones((1,3),device=frequencies.device)),dim=0)
        transforms.append(target @ torch.linalg.inv(source))
    transform=torch.stack(transforms)
    a, b, x0 = transform[:, 0, 0], transform[:, 0, 1], transform[:, 0, 2]
    c, d, y0 = transform[:, 1, 0], transform[:, 1, 1], transform[:, 1, 2]
    determinant = a * d - b * c
    area = 1.0 / (2.0 * determinant.abs())
    x = (b * y0 - d * x0) / determinant
    y = (c * x0 - a * y0) / determinant
    u, v = frequencies[:, 0].unsqueeze(0), frequencies[:, 1].unsqueeze(0)
    determinant = determinant.unsqueeze(1)
    phase = torch.exp(-2j * torch.pi * (u * x.unsqueeze(1) + v * y.unsqueeze(1)))
    transformed_u = (u * d.unsqueeze(1) - v * c.unsqueeze(1)) / determinant
    transformed_v = (v * a.unsqueeze(1) - u * b.unsqueeze(1)) / determinant
    uv = transformed_u + transformed_v
    epsilon = torch.finfo(torch.float32).eps * 16
    zero_u, zero_v, zero_uv = transformed_u.abs() <= epsilon, transformed_v.abs() <= epsilon, uv.abs() <= epsilon
    both_zero = zero_u & zero_v
    safe_u = torch.where(zero_u, torch.ones_like(transformed_u), transformed_u)
    safe_v = torch.where(zero_v, torch.ones_like(transformed_v), transformed_v)
    safe_uv = torch.where(zero_uv, torch.ones_like(uv), uv)
    base_u = torch.exp(-2j * torch.pi * transformed_u)
    base_v = torch.exp(-2j * torch.pi * transformed_v)
    base_uv = torch.exp(-2j * torch.pi * uv)
    response = (transformed_u * (-base_uv) + uv * base_u - transformed_v) / (4 * torch.pi**2 * safe_u * safe_v * safe_uv)
    response_uv = -(base_u + 2j * torch.pi * transformed_u - 1) / (4 * torch.pi**2 * safe_u**2)
    response_v = ((2j * torch.pi * transformed_u + 1) * base_u - 1) / (4 * torch.pi**2 * safe_u**2)
    response_u = -(base_v + 2j * torch.pi * transformed_v - 1) / (4 * torch.pi**2 * safe_v**2)
    response = torch.where(zero_uv, response_uv, response)
    response = torch.where(zero_v, response_v, response)
    response = torch.where(zero_u, response_u, response)
    response = torch.where(both_zero, area[:, None].to(torch.complex64), response / determinant.abs() * phase)
    total=torch.zeros(frequencies.shape[0],dtype=torch.complex64,device=frequencies.device)
    for triangle_response in response:
        total+=triangle_response.to(torch.complex64)
    return total


def _ring_coordinates(geometry: dict[str, torch.Tensor], ring_index: int) -> np.ndarray:
    start = int(geometry["ring_coordinate_start"][ring_index])
    end = int(geometry["ring_coordinate_end"][ring_index])
    coordinates = geometry["ring_coordinates_xy_m"][start:end].detach().cpu().numpy().astype(np.float64, copy=False)
    if len(coordinates) > 1 and np.array_equal(coordinates[0], coordinates[-1]):
        coordinates = coordinates[:-1]
    return coordinates


def _triangulate_component(exterior: np.ndarray, holes: list[np.ndarray], normalization_length_m: float) -> np.ndarray:
    rings = [exterior, *holes]
    vertices = np.concatenate(rings, axis=0) / normalization_length_m
    segments: list[tuple[int, int]] = []
    offset = 0
    for ring in rings:
        count = len(ring)
        segments.extend((offset + index, offset + (index + 1) % count) for index in range(count))
        offset += count
    specification: dict[str, Any] = {"vertices": vertices, "segments": np.asarray(segments, dtype=np.int32)}
    if holes:
        hole_points = [Polygon(hole).representative_point().coords[0] for hole in holes]
        specification["holes"] = np.asarray(hole_points, dtype=np.float64) / normalization_length_m
    result = triangle.triangulate(specification, "pYQ")
    if "triangles" not in result:
        raise ValueError("constrained polygon triangulation produced no triangles")
    return result["vertices"][result["triangles"]]


@torch.no_grad()
def geometry_fourier_features(batch: dict[str, Any], config: dict[str, Any], device: torch.device,
                              implementation: str = "vectorized") -> tuple[torch.Tensor, torch.Tensor]:
    geometry = batch["geometry"]
    entity_type = batch["entities"]["entity_type"]
    if implementation not in {"legacy", "vectorized"}:
        raise ValueError(f"unknown geometry Fourier implementation: {implementation}")
    frequencies = _geometry_frequencies(config, device)
    count = entity_type.numel()
    magnitude = torch.zeros((count, frequencies.shape[0]), dtype=torch.float32, device=device)
    phase = torch.zeros((count, frequencies.shape[0] * 2), dtype=torch.float32, device=device)
    scale = float(config["geometry"]["normalization_length_m"])
    entity_parts = geometry["entity_part_offsets"]
    part_coordinates = geometry["part_coordinate_offsets"]
    entity_rings = geometry["entity_ring_offsets"]
    ring_components = geometry["ring_component_index"]
    coordinates = geometry["part_coordinates_xy_m"]
    for entity_index in range(count):
        kind = int(entity_type[entity_index])
        if kind == 2:
            continue
        response = torch.zeros(frequencies.shape[0], dtype=torch.complex64, device=device)
        part_start, part_end = int(entity_parts[entity_index]), int(entity_parts[entity_index + 1])
        if kind == 1:
            for part_index in range(part_start, part_end):
                start, end = int(part_coordinates[part_index]), int(part_coordinates[part_index + 1])
                response += segment_fourier(coordinates[start:end].to(device) / scale, frequencies)
        else:
            ring_start, ring_end = int(entity_rings[entity_index]), int(entity_rings[entity_index + 1])
            for component_index in range(part_start, part_end):
                component_rings = [index for index in range(ring_start, ring_end) if int(ring_components[index]) == component_index]
                exteriors = [index for index in component_rings if int(geometry["ring_is_hole"][index]) == 0]
                holes = [index for index in component_rings if int(geometry["ring_is_hole"][index]) == 1]
                if len(exteriors) != 1:
                    raise ValueError("polygon component does not have exactly one exterior ring")
                triangles = _triangulate_component(
                    _ring_coordinates(geometry, exteriors[0]),
                    [_ring_coordinates(geometry, index) for index in holes], scale,
                )
                response += (_triangle_fourier_batched if implementation == "vectorized" else _triangle_fourier)(triangles, frequencies)
        values = response.abs()
        angles = torch.angle(response)
        magnitude[entity_index] = torch.log1p(values)
        phase[entity_index] = torch.cat((angles.cos(), angles.sin()))
    return magnitude, phase


class RelationAwareLayer(nn.Module):
    def __init__(self, dimension: int, heads: int, relation_dimension: int, dropout: float) -> None:
        super().__init__()
        self.heads = heads
        self.head_dimension = dimension // heads
        self.query = nn.Linear(dimension, dimension)
        self.key = nn.Linear(dimension, dimension)
        self.value = nn.Linear(dimension, dimension)
        self.relation_bias = nn.Parameter(torch.empty(heads, relation_dimension))
        self.relation_value = nn.Parameter(torch.empty(heads, self.head_dimension, relation_dimension))
        self.output = nn.Linear(dimension, dimension)
        self.norm_attention = nn.LayerNorm(dimension)
        self.ffn = nn.Sequential(nn.Linear(dimension, 256), nn.GELU(), nn.Dropout(dropout), nn.Linear(256, dimension))
        self.norm_ffn = nn.LayerNorm(dimension)
        self.dropout = nn.Dropout(dropout)
        nn.init.xavier_uniform_(self.relation_bias)
        nn.init.xavier_uniform_(self.relation_value.flatten(1))

    def forward(self, values: torch.Tensor, edge_index: torch.Tensor, relation: torch.Tensor) -> torch.Tensor:
        node_count = values.shape[0]
        if edge_index.shape[1] == 0:
            message = torch.zeros_like(values)
        else:
            source, destination = edge_index[0], edge_index[1]
            query = self.query(values).view(node_count, self.heads, self.head_dimension)
            key = self.key(values).view(node_count, self.heads, self.head_dimension)
            value = self.value(values).view(node_count, self.heads, self.head_dimension)
            score = (query[source] * key[destination]).sum(-1) / math.sqrt(self.head_dimension)
            score = score + torch.einsum("er,hr->eh", relation, self.relation_bias)
            index = source[:, None].expand(-1, self.heads)
            maxima = torch.full((node_count, self.heads), -torch.inf, device=values.device, dtype=values.dtype)
            maxima.scatter_reduce_(0, index, score, reduce="amax", include_self=True)
            exponential = torch.exp(score - maxima[source])
            denominator = torch.zeros((node_count, self.heads), device=values.device, dtype=values.dtype)
            denominator.scatter_add_(0, index, exponential)
            weight = exponential / denominator[source]
            relation_message = torch.einsum("ehrd,er->ehd", self.relation_value[None].expand(relation.shape[0], -1, -1, -1), relation)
            edge_message = weight[:, :, None] * (value[destination] + relation_message)
            aggregated = torch.zeros((node_count, self.heads, self.head_dimension), device=values.device, dtype=values.dtype)
            aggregated.index_add_(0, source, edge_message)
            message = self.output(aggregated.flatten(1))
        intermediate = self.norm_attention(values + self.dropout(message))
        return self.norm_ffn(intermediate + self.dropout(self.ffn(intermediate)))


class RasterCNN(nn.Module):
    def __init__(self, input_channels: int) -> None:
        super().__init__()
        layers: list[nn.Module] = []
        for source, destination in ((input_channels, 64), (64, 128), (128, 128)):
            layers.extend((nn.Conv2d(source, destination, 3, stride=2, padding=1), nn.GroupNorm(8, destination), nn.GELU()))
        self.network = nn.Sequential(*layers)

    def forward(self, values: torch.Tensor) -> torch.Tensor:
        return self.network(values).mean(dim=(-2, -1))


class PrototypeSceneEncoder(nn.Module):
    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__()
        dimension = int(config["dimensions"]["latent"])
        dropout = float(config["architecture"]["dropout"])
        vocabulary = config["architecture"]["vocabulary_sizes"]
        self.register_buffer("wavelengths", torch.logspace(math.log10(10.0), math.log10(1000.0), 16))
        self.position_encoder = projected_block(64, 128, dimension, dropout, True)
        self.magnitude_encoder = projected_block(128, 256, dimension, dropout, False)
        self.phase_encoder = projected_block(256, 256, dimension, dropout, False)
        self.geometry_fusion = projected_block(256, 256, dimension, dropout, True)
        self.category_embeddings = nn.ModuleDict({name: nn.Embedding(int(size), 32) for name, size in vocabulary.items() if not name.startswith("CLASS_")})
        self.building_numerical = projected_block(4, 64, 32, dropout, False)
        self.building_fusion = projected_block(96, 256, dimension, dropout, True)
        self.road_numerical = nn.Sequential(nn.Linear(2, 32), nn.LayerNorm(32), nn.GELU(), nn.Linear(32, 32))
        self.road_fusion = projected_block(96, 256, dimension, dropout, True)
        poi_names = [f"CLASS_L{index}" for index in range(1, 7)]
        poi_dimensions = [int(value) for value in config["dimensions"]["poi_hierarchy_embeddings"]]
        self.poi_embeddings = nn.ModuleList([nn.Embedding(int(vocabulary[name]), size) for name, size in zip(poi_names, poi_dimensions)])
        self.poi_projections = nn.ModuleList([nn.Linear(size, 32) for size in poi_dimensions])
        self.poi_score = nn.Sequential(nn.Linear(32, 64), nn.Tanh(), nn.Linear(64, 1))
        self.poi_fusion = projected_block(sum(poi_dimensions) + 32, 256, dimension, dropout, True)
        self.object_raster_encoder = projected_block(26, 128, dimension, dropout, True)
        self.type_embedding = nn.Embedding(3, 16)
        self.gates = nn.ModuleList([nn.Sequential(nn.Linear(144, 128), nn.GELU(), nn.Dropout(dropout), nn.Linear(128, 128)) for _ in range(4)])
        self.entity_norm = nn.LayerNorm(dimension)
        self.relation_embedding = nn.Embedding(5, 32)
        self.relation_layers = nn.ModuleList([RelationAwareLayer(dimension, 4, 32, dropout) for _ in range(3)])
        self.pool = nn.Sequential(nn.Linear(128, 64), nn.Tanh(), nn.Linear(64, 1))
        self.landcover_embedding = nn.Embedding(24, 16)
        self.landcover_cnn = RasterCNN(16)
        self.dem_cnn = RasterCNN(1)
        self.landcover_projection = projected_block(128, 256, dimension, dropout, True)
        self.dem_projection = projected_block(128, 256, dimension, dropout, True)
        self.scene_fusion = projected_block(640, 256, dimension, dropout, True)
        self.projection_head = nn.Sequential(nn.Linear(128, 256), nn.LayerNorm(256), nn.GELU(), nn.Linear(256, 128))

    def _semantic(self, entities: dict[str, torch.Tensor]) -> torch.Tensor:
        count = entities["local_entity_id"].numel()
        output = torch.zeros((count, 128), device=entities["local_entity_id"].device)
        building_rows = entities["building_row_index"]
        if building_rows.numel():
            category = entities["building_category"]
            categorical = torch.cat((self.category_embeddings["A9"](category[:, 0].long()), self.category_embeddings["A11"](category[:, 1].long())), dim=1)
            numerical = self.building_numerical(torch.cat((entities["building_numerical"], entities["building_missing"].float()), dim=1))
            output[building_rows] = self.building_fusion(torch.cat((categorical, numerical), dim=1))
        road_rows = entities["road_row_index"]
        if road_rows.numel():
            category = entities["road_category"]
            categorical = torch.cat((self.category_embeddings["ROAD_RANK"](category[:, 0].long()), self.category_embeddings["ROAD_TYPE"](category[:, 1].long())), dim=1)
            numerical = self.road_numerical(torch.cat((entities["road_numerical"], entities["road_missing"].float()), dim=1))
            output[road_rows] = self.road_fusion(torch.cat((categorical, numerical), dim=1))
        poi_rows = entities["poi_row_index"]
        if poi_rows.numel():
            category = entities["poi_category"]
            raw = [embedding(category[:, index].long()) for index, embedding in enumerate(self.poi_embeddings)]
            projected = torch.stack([projection(value) for projection, value in zip(self.poi_projections, raw)], dim=1)
            weights = torch.softmax(self.poi_score(projected).squeeze(-1), dim=1)
            weighted = (weights[:, :, None] * projected).sum(dim=1)
            output[poi_rows] = self.poi_fusion(torch.cat((*raw, weighted), dim=1))
        return output

    def _type_pool(self, values: torch.Tensor, entity_types: torch.Tensor, entity_scenes: torch.Tensor, scenes: int) -> torch.Tensor:
        summaries = torch.zeros((scenes, 3, 128), device=values.device, dtype=values.dtype)
        scores = self.pool(values).squeeze(-1)
        for scene in range(scenes):
            for entity_type in range(3):
                indices = torch.nonzero((entity_scenes == scene) & (entity_types == entity_type)).flatten()
                if indices.numel():
                    summaries[scene, entity_type] = (torch.softmax(scores[indices], dim=0)[:, None] * values[indices]).sum(dim=0)
        return summaries

    def forward(self, batch: dict[str, Any], geometry_features: tuple[torch.Tensor, torch.Tensor]) -> dict[str, torch.Tensor]:
        entities, geometry, edges, rasters = batch["entities"], batch["geometry"], batch["edges"], batch["rasters"]
        position = self.position_encoder(sinusoidal_position_features(entities["relative_position_m"], self.wavelengths))
        magnitude, phase = geometry_features
        geometry_embedding = self.geometry_fusion(torch.cat((self.magnitude_encoder(magnitude), self.phase_encoder(phase)), dim=1))
        semantic = self._semantic(entities)
        object_raster = self.object_raster_encoder(entities["object_raster"])
        modality = torch.stack((position, geometry_embedding, semantic, object_raster), dim=1)
        type_embedding = self.type_embedding(entities["entity_type"].long())
        logits = torch.stack([gate(torch.cat((modality[:, index], type_embedding), dim=1)) for index, gate in enumerate(self.gates)], dim=1)
        availability = torch.ones((entities["entity_type"].numel(), 4, 1), dtype=torch.bool, device=logits.device)
        availability[:, 1, 0] = entities["entity_type"] != 2
        weights = torch.softmax(logits.masked_fill(~availability, -torch.inf), dim=1)
        initial = self.entity_norm((weights * modality).sum(dim=1))
        relation = relation_set_embedding(edges["relation_mask"], self.relation_embedding)
        contextual = initial
        for layer in self.relation_layers:
            contextual = layer(contextual, edges["edge_index"], relation)
        scene_count = len(batch["scene_ids"])
        type_summary = self._type_pool(contextual, entities["entity_type"], batch["entity_scene_index"], scene_count)
        fraction = rasters["landcover_class_fraction"]
        landcover = torch.einsum("bchw,cd->bdhw", fraction, self.landcover_embedding.weight[:22])
        invalid = rasters["landcover_valid_mask"] == 0
        landcover = torch.where(invalid[:, None], self.landcover_embedding.weight[22][None, :, None, None], landcover)
        landcover_scene = self.landcover_projection(self.landcover_cnn(landcover))
        dem_scene = self.dem_projection(self.dem_cnn(rasters["dem_standardized_mean"][:, None]))
        raw_scene = self.scene_fusion(torch.cat((type_summary.flatten(1), landcover_scene, dem_scene), dim=1))
        scene = torch.nn.functional.normalize(raw_scene, dim=1)
        projection = torch.nn.functional.normalize(self.projection_head(raw_scene), dim=1)
        return {
            "position": position, "geometry": geometry_embedding, "semantic": semantic,
            "object_raster": object_raster, "modality_weights": weights, "initial_entity": initial,
            "contextual_entity": contextual, "type_summary": type_summary,
            "landcover_scene": landcover_scene, "dem_scene": dem_scene,
            "scene_raw": raw_scene, "scene_embedding": scene, "projection": projection,
        }
