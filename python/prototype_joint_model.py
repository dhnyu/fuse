"""Dissertation-exact joint contrastive and information-preservation model."""

from __future__ import annotations

import copy
import hashlib
from dataclasses import dataclass
from typing import Any

import numpy as np
import torch
import torch.nn.functional as F
from torch import nn

from prototype_encoder import (
    PrototypeSceneEncoder,
    relation_set_embedding,
    sinusoidal_position_features,
)


MODALITIES = ("relative", "geometry", "semantic", "environmental")
RECONSTRUCTION_FIELDS = (
    "relative.position_xy", "geometry.magnitude", "geometry.phase",
    "semantic.building.A9", "semantic.building.A11",
    "semantic.building.building_observed_area_m2", "semantic.building.building_observed_gross_floor_area_m2",
    "semantic.road.ROAD_RANK", "semantic.road.ROAD_TYPE", "semantic.road.road_lanes",
    *(f"semantic.poi.CLASS_L{i}" for i in range(1, 7)),
    "environmental.composition", *(f"environmental.continuous_{i}" for i in range(4)),
)


def stable_rng(seed: int, epoch: int, scene_id: str, view_id: int, operation: str, local_entity_id: int) -> np.random.Generator:
    payload = f"{seed}|{epoch}|{scene_id}|{view_id}|{operation}|{local_entity_id}".encode()
    value = int.from_bytes(hashlib.sha256(payload).digest()[:16], "big")
    return np.random.Generator(np.random.PCG64(value))


def modality_mask_assignments(batch: dict[str, Any], seed: int, epoch: int, view_id: int, probability: float) -> torch.Tensor:
    entity_types = batch["entities"]["entity_type"].cpu().numpy()
    assignments = np.full(len(entity_types), -1, dtype=np.int64)
    scene_ptr = batch["scene_ptr"].cpu().numpy()
    local_ids = batch["entity_local_index"].cpu().numpy()
    for scene_index, scene_id in enumerate(batch["scene_ids"]):
        for row in range(int(scene_ptr[scene_index]), int(scene_ptr[scene_index + 1])):
            rng = stable_rng(seed, epoch, scene_id, view_id, "modality_mask", int(local_ids[row]))
            if rng.random() >= probability:
                continue
            available = [0, 2, 3]
            if int(entity_types[row]) != 2:
                available.insert(1, 1)
            assignments[row] = available[int(rng.integers(len(available)))]
    return torch.from_numpy(assignments)


class RelativeDecoder(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.network = nn.Sequential(nn.Linear(128, 128), nn.GELU(), nn.Linear(128, 2))

    def forward(self, value: torch.Tensor) -> torch.Tensor:
        return self.network(value)


class GeometryDecoder(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.hidden = nn.Sequential(nn.Linear(128, 256), nn.GELU())
        self.magnitude = nn.Linear(256, 128)
        self.phase = nn.Linear(256, 256)

    def forward(self, value: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        hidden = self.hidden(value)
        return self.magnitude(hidden), self.phase(hidden)


class AttributeDecoder(nn.Module):
    def __init__(self, categorical: dict[str, int], numerical: list[str]) -> None:
        super().__init__()
        self.hidden = nn.Sequential(nn.Linear(128, 128), nn.GELU())
        self.categorical = nn.ModuleDict({name: nn.Linear(128, size) for name, size in categorical.items()})
        self.numerical = nn.ModuleDict({name: nn.Linear(128, 1) for name in numerical})

    def forward(self, value: torch.Tensor) -> dict[str, torch.Tensor]:
        hidden = self.hidden(value)
        return {
            **{name: head(hidden) for name, head in self.categorical.items()},
            **{name: head(hidden).squeeze(-1) for name, head in self.numerical.items()},
        }


class EnvironmentalDecoder(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.hidden = nn.Sequential(nn.Linear(128, 128), nn.GELU())
        self.composition = nn.Linear(128, 22)
        self.continuous = nn.Linear(128, 4)

    def forward(self, value: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        hidden = self.hidden(value)
        return self.composition(hidden), self.continuous(hidden)


class ReconstructionDecoders(nn.Module):
    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__()
        decoder = config["decoders"]
        self.relative = RelativeDecoder()
        self.geometry = GeometryDecoder()
        self.building = AttributeDecoder(decoder["building"]["categorical_heads"], decoder["building"]["numerical_heads"])
        self.road = AttributeDecoder(decoder["road"]["categorical_heads"], decoder["road"]["numerical_heads"])
        self.poi = AttributeDecoder(decoder["poi"]["categorical_heads"], [])
        self.environmental = EnvironmentalDecoder()


@dataclass
class JointForward:
    outputs: dict[str, torch.Tensor]
    modalities: dict[str, torch.Tensor]


class JointPrototypeModel(nn.Module):
    """Accepted encoder plus training-only masks, decoders, and momentum encoder."""

    def __init__(self, encoder_config: dict[str, Any], joint_config: dict[str, Any]) -> None:
        super().__init__()
        self.online = PrototypeSceneEncoder(encoder_config)
        self.target = copy.deepcopy(self.online)
        self.target.requires_grad_(False)
        self.target.eval()
        self.modality_mask_embeddings = nn.Parameter(torch.empty(4, 128))
        nn.init.normal_(self.modality_mask_embeddings, mean=0.0, std=0.02)
        self.decoders = ReconstructionDecoders(joint_config)

    @staticmethod
    def _modalities(model: PrototypeSceneEncoder, batch: dict[str, Any], geometry_features: tuple[torch.Tensor, torch.Tensor]) -> dict[str, torch.Tensor]:
        entities = batch["entities"]
        magnitude, phase = geometry_features
        return {
            "relative": model.position_encoder(sinusoidal_position_features(entities["relative_position_m"], model.wavelengths)),
            "geometry": model.geometry_fusion(torch.cat((model.magnitude_encoder(magnitude), model.phase_encoder(phase)), dim=1)),
            "semantic": model._semantic(entities),
            "environmental": model.object_raster_encoder(entities["object_raster"]),
        }

    @staticmethod
    def _finish(model: PrototypeSceneEncoder, batch: dict[str, Any], modality: torch.Tensor) -> dict[str, torch.Tensor]:
        entities, edges, rasters = batch["entities"], batch["edges"], batch["rasters"]
        type_embedding = model.type_embedding(entities["entity_type"].long())
        logits = torch.stack([
            gate(torch.cat((modality[:, index], type_embedding), dim=1))
            for index, gate in enumerate(model.gates)
        ], dim=1)
        availability = torch.ones((entities["entity_type"].numel(), 4, 1), dtype=torch.bool, device=logits.device)
        availability[:, 1, 0] = entities["entity_type"] != 2
        weights = torch.softmax(logits.masked_fill(~availability, -torch.inf), dim=1)
        initial = model.entity_norm((weights * modality).sum(dim=1))
        relation = relation_set_embedding(edges["relation_mask"], model.relation_embedding)
        contextual = initial
        for layer in model.relation_layers:
            contextual = layer(contextual, edges["edge_index"], relation)
        scene_count = len(batch["scene_ids"])
        type_summary = model._type_pool(contextual, entities["entity_type"], batch["entity_scene_index"], scene_count)
        fraction = rasters["landcover_class_fraction"]
        landcover = torch.einsum("bchw,cd->bdhw", fraction, model.landcover_embedding.weight[:22])
        invalid = rasters["landcover_valid_mask"] == 0
        landcover = torch.where(invalid[:, None], model.landcover_embedding.weight[22][None, :, None, None], landcover)
        landcover_scene = model.landcover_projection(model.landcover_cnn(landcover))
        dem_scene = model.dem_projection(model.dem_cnn(rasters["dem_standardized_mean"][:, None]))
        raw_scene = model.scene_fusion(torch.cat((type_summary.flatten(1), landcover_scene, dem_scene), dim=1))
        return {
            "modality_weights": weights,
            "initial_entity": initial,
            "contextual_entity": contextual,
            "type_summary": type_summary,
            "landcover_scene": landcover_scene,
            "dem_scene": dem_scene,
            "scene_raw": raw_scene,
            "scene_embedding": F.normalize(raw_scene, dim=1),
            "projection": F.normalize(model.projection_head(raw_scene), dim=1),
        }

    def forward_online(self, batch: dict[str, Any], geometry_features: tuple[torch.Tensor, torch.Tensor], assignments: torch.Tensor) -> JointForward:
        modalities = self._modalities(self.online, batch, geometry_features)
        stacked = torch.stack(tuple(modalities[name] for name in MODALITIES), dim=1)
        assignments = assignments.to(stacked.device)
        for modality_index in range(4):
            selected = assignments == modality_index
            if selected.any():
                stacked[selected, modality_index] = self.modality_mask_embeddings[modality_index]
        return JointForward(self._finish(self.online, batch, stacked), modalities)

    @torch.no_grad()
    def forward_target(self, batch: dict[str, Any], geometry_features: tuple[torch.Tensor, torch.Tensor]) -> dict[str, torch.Tensor]:
        modalities = self._modalities(self.target, batch, geometry_features)
        return self._finish(self.target, batch, torch.stack(tuple(modalities[name] for name in MODALITIES), dim=1))

    @torch.no_grad()
    def update_target(self, momentum: float) -> None:
        for target, online in zip(self.target.parameters(), self.online.parameters(), strict=True):
            target.mul_(momentum).add_(online, alpha=1.0 - momentum)


def _valid_entity_losses(field_losses: list[tuple[torch.Tensor, torch.Tensor]], entity_count: int) -> torch.Tensor:
    if entity_count == 0:
        device = field_losses[0][0].device if field_losses else torch.device("cpu")
        return torch.empty(0, device=device)
    numerator = torch.zeros(entity_count, device=field_losses[0][0].device)
    denominator = torch.zeros(entity_count, device=numerator.device)
    for values, valid in field_losses:
        numerator = numerator + torch.where(valid, values, torch.zeros_like(values))
        denominator = denominator + valid.float()
    entity_valid = denominator > 0
    if not entity_valid.any():
        return numerator.new_empty(0)
    return numerator[entity_valid] / denominator[entity_valid]


def _differentiable_zero(module: nn.Module, representation: torch.Tensor) -> torch.Tensor:
    zero = representation.sum() * 0.0
    for parameter in module.parameters():
        zero = zero + parameter.reshape(-1)[0] * 0.0
    return zero


def _loss_term(loss_sum: torch.Tensor, valid_count: int) -> dict[str, Any]:
    return {"loss_sum": loss_sum, "local_valid_count": int(valid_count),
            "globally_reduced_valid_count": None, "active": bool(valid_count)}


def information_preservation_loss(terms: dict[str, Any], global_counts: dict[str, int] | None = None) -> torch.Tensor:
    counts = global_counts or {name: int(term["local_valid_count"]) for name, term in terms["modalities"].items()}
    active = [name for name in MODALITIES if int(counts[name]) > 0]
    if not active:
        return sum((term["loss_sum"] for term in terms["modalities"].values()))
    for name, term in terms["modalities"].items():
        term["globally_reduced_valid_count"] = int(counts[name])
        term["active"] = name in active
    return sum(terms["modalities"][name]["loss_sum"] / int(counts[name]) for name in active) / len(active)


def reconstruction_valid_counts(batch: dict[str, Any], geometry_features: tuple[torch.Tensor, torch.Tensor],
                                config: dict[str, Any]) -> dict[str, dict[str, int]]:
    entities, masks = batch["entities"], batch["category_mask_indices"]
    entity_type = entities["entity_type"]
    fields = {name: 0 for name in RECONSTRUCTION_FIELDS}
    fields["relative.position_xy"] = int(entity_type.numel())
    geometry_rows = entity_type != 2
    fields["geometry.magnitude"] = int(geometry_rows.sum())
    if geometry_rows.any():
        raw_magnitude = torch.expm1(geometry_features[0][geometry_rows]).clamp_min(0)
        maximum = raw_magnitude.amax(dim=1, keepdim=True)
        phase_valid = (maximum > 0) & (raw_magnitude / maximum.clamp_min(torch.finfo(raw_magnitude.dtype).tiny) >=
                                      float(config["loss"]["phase"]["relative_magnitude_threshold"]))
        fields["geometry.phase"] = int(phase_valid.any(dim=1).sum())
    semantic_count = 0
    for prefix, names, numerical_names in (
        ("building", ("A9", "A11"), ("building_observed_area_m2", "building_observed_gross_floor_area_m2")),
        ("road", ("ROAD_RANK", "ROAD_TYPE"), ("road_lanes",)),
        ("poi", tuple(f"CLASS_L{i}" for i in range(1, 7)), ()),
    ):
        category = entities[f"{prefix}_category"]
        if category.numel() == 0: category = category.reshape(0, len(names))
        valid_entity = torch.zeros(category.shape[0], dtype=torch.bool, device=category.device)
        for column, name in enumerate(names):
            valid = category[:, column] != int(masks[name]); fields[f"semantic.{prefix}.{name}"] = int(valid.sum()); valid_entity |= valid
        if numerical_names:
            missing = entities[f"{prefix}_missing"].bool()
            if missing.numel() == 0: missing = missing.reshape(0, len(numerical_names))
            for column, name in enumerate(numerical_names):
                valid = ~missing[:, column]; fields[f"semantic.{prefix}.{name}"] = int(valid.sum()); valid_entity |= valid
        semantic_count += int(valid_entity.sum())
    context = entities["object_raster"]; dem_missing = entities["object_dem_missing"].bool()
    fields["environmental.composition"] = int((context[:, 22] > 0).sum())
    fields["environmental.continuous_0"] = int(context.shape[0])
    fields["environmental.continuous_1"] = int((~dem_missing[:, 0]).sum())
    fields["environmental.continuous_2"] = int((~dem_missing[:, 1]).sum())
    fields["environmental.continuous_3"] = int(context.shape[0])
    modalities = {"relative": int(entity_type.numel()), "geometry": int(geometry_rows.sum()),
                  "semantic": semantic_count, "environmental": int(context.shape[0])}
    return {"modalities": modalities, "fields": fields}


def apply_global_reconstruction_counts(terms: dict[str, Any], counts: dict[str, dict[str, int]]) -> None:
    for namespace in ("modalities", "fields"):
        for name, term in terms[namespace].items():
            term["globally_reduced_valid_count"] = int(counts[namespace][name])
            term["active"] = int(counts[namespace][name]) > 0


def reconstruction_losses(model: JointPrototypeModel, batch: dict[str, Any], geometry_features: tuple[torch.Tensor, torch.Tensor], modalities: dict[str, torch.Tensor], config: dict[str, Any]) -> dict[str, Any]:
    entities = batch["entities"]
    delta = float(config["loss"]["continuous"]["delta"])
    mask_indices = batch["category_mask_indices"]
    result: dict[str, Any] = {"modalities": {}, "fields": {}}

    relative_prediction = model.decoders.relative(modalities["relative"])
    relative_target = entities["relative_position_m"] / 500.0
    relative_count = int(relative_target.shape[0])
    relative_sum = (F.huber_loss(relative_prediction, relative_target, delta=delta, reduction="none").mean(dim=1).sum()
                    if relative_count else _differentiable_zero(model.decoders.relative, modalities["relative"]))
    result["fields"]["relative.position_xy"] = _loss_term(relative_sum, relative_count)
    result["modalities"]["relative"] = _loss_term(relative_sum, relative_count)

    geometry_rows = entities["entity_type"] != 2
    geometry_count = int(geometry_rows.sum())
    if geometry_rows.any():
        predicted_magnitude, predicted_phase = model.decoders.geometry(modalities["geometry"][geometry_rows])
        target_magnitude = geometry_features[0][geometry_rows]
        target_phase = geometry_features[1][geometry_rows].reshape(-1, 128, 2)
        magnitude_loss = F.huber_loss(predicted_magnitude, target_magnitude, delta=delta, reduction="none").mean(dim=1)
        raw_magnitude = torch.expm1(target_magnitude).clamp_min(0)
        maximum = raw_magnitude.amax(dim=1, keepdim=True)
        phase_valid = (maximum > 0) & (raw_magnitude / maximum.clamp_min(torch.finfo(raw_magnitude.dtype).tiny) >= float(config["loss"]["phase"]["relative_magnitude_threshold"]))
        phase_prediction = predicted_phase.reshape(-1, 128, 2)
        phase_component = 1.0 - F.cosine_similarity(phase_prediction, target_phase, dim=2)
        phase_entity_valid = phase_valid.any(dim=1)
        phase_loss = torch.zeros_like(magnitude_loss)
        phase_loss[phase_entity_valid] = (phase_component[phase_entity_valid] * phase_valid[phase_entity_valid]).sum(dim=1) / phase_valid[phase_entity_valid].sum(dim=1)
        geometry_entity = torch.where(phase_entity_valid, 0.5 * (magnitude_loss + phase_loss), magnitude_loss)
        geometry_sum = geometry_entity.sum()
        result["fields"]["geometry.magnitude"] = _loss_term(magnitude_loss.sum(), geometry_count)
        result["fields"]["geometry.phase"] = _loss_term(phase_loss[phase_entity_valid].sum(), int(phase_entity_valid.sum()))
    else:
        geometry_sum = _differentiable_zero(model.decoders.geometry, modalities["geometry"])
        result["fields"]["geometry.magnitude"] = _loss_term(geometry_sum, 0)
        result["fields"]["geometry.phase"] = _loss_term(geometry_sum, 0)
    result["modalities"]["geometry"] = _loss_term(geometry_sum, geometry_count)

    semantic_entity_losses: list[torch.Tensor] = []
    for prefix, decoder, categorical_names, numerical_names in (
        ("building", model.decoders.building, ("A9", "A11"), ("building_observed_area_m2", "building_observed_gross_floor_area_m2")),
        ("road", model.decoders.road, ("ROAD_RANK", "ROAD_TYPE"), ("road_lanes",)),
        ("poi", model.decoders.poi, tuple(f"CLASS_L{i}" for i in range(1, 7)), ()),
    ):
        rows = entities[f"{prefix}_row_index"]
        predictions = decoder(modalities["semantic"][rows])
        category = entities[f"{prefix}_category"]
        if category.numel() == 0: category = category.reshape(0, len(categorical_names))
        fields: list[tuple[torch.Tensor, torch.Tensor]] = []
        for column, name in enumerate(categorical_names):
            target = category[:, column].long()
            valid = target != int(mask_indices[name])
            values = F.cross_entropy(predictions[name], target, reduction="none") if target.numel() else predictions[name].sum(dim=1)
            fields.append((values, valid))
            field_sum = values[valid].sum() if valid.any() else _differentiable_zero(decoder.categorical[name], modalities["semantic"][rows])
            result["fields"][f"semantic.{prefix}.{name}"] = _loss_term(field_sum, int(valid.sum()))
        if numerical_names:
            numerical = entities[f"{prefix}_numerical"]
            missing = entities[f"{prefix}_missing"].bool()
            if numerical.numel() == 0: numerical = numerical.reshape(0, len(numerical_names))
            if missing.numel() == 0: missing = missing.reshape(0, len(numerical_names))
            for column, name in enumerate(numerical_names):
                values = F.huber_loss(predictions[name], numerical[:, column], delta=delta, reduction="none")
                valid = ~missing[:, column]
                fields.append((values, valid))
                field_sum = values[valid].sum() if valid.any() else _differentiable_zero(decoder.numerical[name], modalities["semantic"][rows])
                result["fields"][f"semantic.{prefix}.{name}"] = _loss_term(field_sum, int(valid.sum()))
        semantic = _valid_entity_losses(fields, rows.numel())
        if semantic.numel():
            semantic_entity_losses.append(semantic)
    if semantic_entity_losses:
        semantic_values = torch.cat(semantic_entity_losses)
        semantic_sum, semantic_count = semantic_values.sum(), int(semantic_values.numel())
    else:
        semantic_sum = sum((_differentiable_zero(decoder, modalities["semantic"])
                            for decoder in (model.decoders.building, model.decoders.road, model.decoders.poi)))
        semantic_count = 0
    result["modalities"]["semantic"] = _loss_term(semantic_sum, semantic_count)

    composition_logits, continuous_prediction = model.decoders.environmental(modalities["environmental"])
    context = entities["object_raster"]
    composition_target = context[:, :22]
    composition_valid = context[:, 22] > 0
    composition_loss = -(composition_target * F.log_softmax(composition_logits, dim=1)).sum(dim=1)
    continuous_target = context[:, 22:26]
    continuous_loss = F.huber_loss(continuous_prediction, continuous_target, delta=delta, reduction="none")
    dem_missing = entities["object_dem_missing"].bool()
    continuous_valid = torch.ones_like(continuous_target, dtype=torch.bool)
    continuous_valid[:, 1] = ~dem_missing[:, 0]
    continuous_valid[:, 2] = ~dem_missing[:, 1]
    composition_sum = composition_loss[composition_valid].sum() if composition_valid.any() else _differentiable_zero(model.decoders.environmental.composition, modalities["environmental"])
    result["fields"]["environmental.composition"] = _loss_term(composition_sum, int(composition_valid.sum()))
    for index in range(4):
        valid = continuous_valid[:, index]
        field_sum = continuous_loss[:, index][valid].sum() if valid.any() else _differentiable_zero(model.decoders.environmental.continuous, modalities["environmental"])
        result["fields"][f"environmental.continuous_{index}"] = _loss_term(field_sum, int(valid.sum()))
    environmental_fields = [(composition_loss, composition_valid)] + [
        (continuous_loss[:, index], continuous_valid[:, index]) for index in range(4)
    ]
    environmental_entity = _valid_entity_losses(environmental_fields, context.shape[0])
    if environmental_entity.numel():
        environmental_sum, environmental_count = environmental_entity.sum(), int(environmental_entity.numel())
    else:
        environmental_sum = _differentiable_zero(model.decoders.environmental, modalities["environmental"])
        environmental_count = 0
    result["modalities"]["environmental"] = _loss_term(environmental_sum, environmental_count)
    apply_global_reconstruction_counts(result, {
        "modalities": {name: term["local_valid_count"] for name, term in result["modalities"].items()},
        "fields": {name: term["local_valid_count"] for name, term in result["fields"].items()},
    })
    result["information_preservation"] = information_preservation_loss(result)
    return result


def symmetric_infonce_components(q1: torch.Tensor, q2: torch.Tensor, k1: torch.Tensor, k2: torch.Tensor,
                                 centers: torch.Tensor, queue_values: torch.Tensor, queue_centers: torch.Tensor,
                                 queue_occupancy: int, temperature: float, exclusion_m: float) -> torch.Tensor:
    keys = torch.cat((k1, k2), dim=0)
    key_centers = torch.cat((centers, centers), dim=0)
    scene_count = q1.shape[0]
    losses: list[torch.Tensor] = []
    for queries, positives in ((q1, k2), (q2, k1)):
        for index in range(scene_count):
            candidates = []
            current_distance = torch.linalg.vector_norm(key_centers - centers[index], dim=1)
            current_scene = torch.cat((torch.arange(scene_count, device=centers.device), torch.arange(scene_count, device=centers.device)))
            valid_current = (current_scene != index) & (current_distance >= exclusion_m)
            if valid_current.any():
                candidates.append(keys[valid_current])
            if queue_occupancy:
                queued_distance = torch.linalg.vector_norm(queue_centers[:queue_occupancy] - centers[index], dim=1)
                valid_queue = queued_distance >= exclusion_m
                if valid_queue.any():
                    candidates.append(queue_values[:queue_occupancy][valid_queue])
            positive = (queries[index] * positives[index]).sum().reshape(1) / temperature
            negative = torch.cat([queries[index] @ value.T for value in candidates]) / temperature if candidates else positive.new_empty(0)
            logits = torch.cat((positive, negative))
            losses.append(-positive[0] + torch.logsumexp(logits, dim=0))
    return torch.stack(losses)


def symmetric_infonce(q1: torch.Tensor, q2: torch.Tensor, k1: torch.Tensor, k2: torch.Tensor,
                      centers: torch.Tensor, queue_values: torch.Tensor, queue_centers: torch.Tensor,
                      queue_occupancy: int, temperature: float, exclusion_m: float) -> torch.Tensor:
    return symmetric_infonce_components(
        q1, q2, k1, k2, centers, queue_values, queue_centers,
        queue_occupancy, temperature, exclusion_m,
    ).mean()


@torch.no_grad()
def enqueue(queue_values: torch.Tensor, queue_scene_ids: torch.Tensor, queue_centers: torch.Tensor,
            pointer: int, occupancy: int, values: torch.Tensor, scene_ids: torch.Tensor,
            centers: torch.Tensor) -> tuple[int, int]:
    capacity = queue_values.shape[0]
    for value, scene_id, center in zip(values, scene_ids, centers, strict=True):
        queue_values[pointer].copy_(value)
        queue_scene_ids[pointer].copy_(scene_id)
        queue_centers[pointer].copy_(center)
        pointer = (pointer + 1) % capacity
        occupancy = min(capacity, occupancy + 1)
    return pointer, occupancy
