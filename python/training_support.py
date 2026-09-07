"""Deterministic training primitives for the current reduced model."""

from __future__ import annotations

import copy
import hashlib
import math
from pathlib import Path
from typing import Any, NamedTuple, Sequence

import numpy as np
import torch
import torch.nn.functional as F
from torch import nn

from canonical_config import canonical_json_bytes, load_strict_yaml
from model_data import ragged_collate
from scene_model import ReducedSceneEncoder
from training_identity import validate_current_batch_lookup
from scene_encoder import relation_set_embedding, sinusoidal_position_features


SCHEMA_VERSION = "1.0.0"
SUPPLEMENT_NAME = "current-deterministic-training-v1"
MODALITIES = ("relative", "geometry", "semantic", "environmental")
def canonical_digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def finalized(value: dict[str, Any], prefix: str, id_field: str) -> dict[str, Any]:
    scientific = {key: item for key, item in value.items() if key not in {id_field, "content_sha256"}}
    value["content_sha256"] = canonical_digest(scientific)
    value[id_field] = prefix + value["content_sha256"][:24]
    return value


def load_config(path: str | Path) -> dict[str, Any]:
    value = load_strict_yaml(path)
    if not isinstance(value, dict):
        raise ValueError("training configuration root must be a mapping")
    validate_config(value)
    return value


def validate_config(config: dict[str, Any]) -> None:
    if config.get("schema_version") != SCHEMA_VERSION or config.get("supplement_name") != SUPPLEMENT_NAME:
        raise ValueError("training supplement identity mismatch")
    training, optimizer, scheduler = config["training"], config["optimizer"], config["scheduler"]
    if (training["root_seed"], training["global_batch_size"], training["world_size"],
            training["per_rank_batch_size"], training["maximum_epochs"], training["maximum_updates"]) != (
            20260828, 32, 2, 16, 200, 15200):
        raise ValueError("training population/batch/seed contract mismatch")
    if (optimizer["name"], optimizer["peak_learning_rate"], optimizer["weight_decay"],
            optimizer["betas"], optimizer["eps"]) != ("AdamW", 0.001, 0.0001, [0.9, 0.999], 1e-8):
        raise ValueError("AdamW contract mismatch")
    if scheduler != {
        "indexing": "one_based_optimizer_update", "warmup_updates": 760,
        "decay_updates": 14440, "minimum_learning_rate": 0.0,
        "restart": False, "update_order": "set_before_optimizer_update",
    }:
        raise ValueError("P7 scheduler contract mismatch")
    objective = config["objective"]
    if set(objective) != {"contrastive_temperature", "negative_exclusion_distance_m", "directions"}:
        raise ValueError("current objective must be contrastive-only")
    numeric = config["numeric"]
    if any((numeric["backend"] != "nccl", numeric["precision"] != "float32", numeric["amp"],
            numeric["grad_scaler"], numeric["tf32_matmul"], numeric["tf32_cudnn"],
            not numeric["deterministic_algorithms"], numeric["deterministic_warn_only"],
            not numeric["cudnn_deterministic"], numeric["cudnn_benchmark"])):
        raise ValueError("training numeric determinism contract mismatch")
    execution = config.get("execution_contract", {})
    required_execution = {
        "geometry_layout_version": "3.0.0", "geometry_cache_schema_version": "3.0.0",
        "geometry_cache_memory_limit_gib_per_rank": 4,
        "packed_evidence_materialization": True, "deterministic_cpu_lookahead_batches": 1,
        "ddp_find_unused_parameters": False, "ddp_bucket_cap_mb": 50,
        "ddp_gradient_as_bucket_view": False, "ddp_static_graph": False,
        "disjoint_rank_cpu_affinity": True, "distributed_validation": True,
        "validation_batch_size": 8, "old_p7_checkpoint_resume": "prohibited",
    }
    if execution != required_execution:
        raise ValueError("optimized training execution contract mismatch")


def scientific_config(config: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(config)
    result.pop("publication_root", None)
    result.pop("staging_root", None)
    result.pop("parent_roots", None)
    runtime = result["runtime"]
    for key in ("selected_gpu_indices", "dataloader_workers_per_rank", "native_threads_per_rank",
                "gpu_lock_root", "gpu_lock_timeout_seconds", "nccl_p2p_disable", "nccl_ib_disable"):
        runtime.pop(key, None)
    return result


def seed_payload(config: dict[str, Any], role: str, epoch: int = 0, global_rank: int = 0,
                 worker_id: int = 0, operation: str = "default", **extra: Any) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "supplement_name": SUPPLEMENT_NAME,
        "root_run_seed": int(config["training"]["root_seed"]),
        "p6_aggregate_acceptance_id": config["parents"]["p6_aggregate_acceptance_id"],
        "scene_index_id": config["parents"]["scene_index_id"],
        "role": role, "epoch": int(epoch), "global_rank": int(global_rank),
        "worker_id": int(worker_id), "stochastic_operation": operation,
        **extra,
    }


def derive_seed(config: dict[str, Any], role: str, epoch: int = 0, global_rank: int = 0,
                worker_id: int = 0, operation: str = "default", **extra: Any) -> int:
    digest = hashlib.sha256(canonical_json_bytes(seed_payload(
        config, role, epoch, global_rank, worker_id, operation, **extra))).digest()
    return int.from_bytes(digest[:8], "big", signed=False) & ((1 << 63) - 1)


def uniform01(config: dict[str, Any], role: str, **fields: Any) -> float:
    value = derive_seed(config, role, **fields)
    return (value >> 10) * (2.0 ** -53)


def learning_rate(update: int, peak: float = 1e-3) -> float:
    if not 1 <= update <= 15200:
        raise ValueError("optimizer update is outside [1,15200]")
    if update <= 760:
        return peak * update / 760.0
    return 0.5 * peak * (1.0 + math.cos(math.pi * (update - 760) / 14440.0))


class ExactLRScheduler:
    def __init__(self, optimizer: torch.optim.Optimizer, completed_updates: int = 0) -> None:
        self.optimizer = optimizer
        self.completed_updates = int(completed_updates)

    def set_for_next_update(self) -> float:
        value = learning_rate(self.completed_updates + 1)
        for group in self.optimizer.param_groups:
            group["lr"] = value
        return value

    def advance(self) -> None:
        self.completed_updates += 1

    def state_dict(self) -> dict[str, int]:
        return {"completed_updates": self.completed_updates, "next_update": self.completed_updates + 1}

    def load_state_dict(self, state: dict[str, int]) -> None:
        if int(state["next_update"]) != int(state["completed_updates"]) + 1:
            raise ValueError("scheduler next-update state mismatch")
        self.completed_updates = int(state["completed_updates"])


def epoch_scene_order(scene_ids: Sequence[str], config: dict[str, Any], epoch: int) -> list[str]:
    canonical = sorted(scene_ids)
    generator = torch.Generator().manual_seed(derive_seed(
        config, "training-sampler", epoch=epoch, global_rank=0, operation="global-scene-permutation"))
    return [canonical[index] for index in torch.randperm(len(canonical), generator=generator).tolist()]


def selected_view_pair(scene_id: str, available: Sequence[int], config: dict[str, Any], epoch: int) -> tuple[int, int]:
    values = sorted(int(value) for value in available)
    if len(values) != 8 or len(set(values)) != 8:
        raise ValueError("current training requires the accepted main logical K8")
    generator = torch.Generator().manual_seed(derive_seed(
        config, "training-view-selection", epoch=epoch, global_rank=0,
        operation="two-views-without-replacement", scene_id=scene_id))
    order = torch.randperm(len(values), generator=generator).tolist()
    return values[order[0]], values[order[1]]


def scene_numeric_id(scene_id: str) -> int:
    return int.from_bytes(hashlib.sha256(scene_id.encode("utf-8")).digest()[:8], "big") & ((1 << 63) - 1)



def collate(samples: Sequence[dict[str, Any]], vocabulary: dict[str, Any]) -> dict[str, Any]:
    result = ragged_collate(samples)
    result["scene_center_5186"] = torch.stack([sample["scene_center_5186"] for sample in samples]).to(torch.float32)
    result["scene_numeric_ids"] = torch.tensor([scene_numeric_id(value) for value in result["scene_ids"]], dtype=torch.int64)
    result["category_mask_indices"] = {key: int(value["mask"]) for key, value in vocabulary.items()}
    return result


def to_device(value: Any, device: torch.device, key: str = "") -> Any:
    if isinstance(value, torch.Tensor):
        if key in {"part_coordinates_xy_m_scientific", "ring_coordinates_xy_m_scientific"}:
            return value
        return value.to(device, non_blocking=False)
    if isinstance(value, dict):
        return {name: to_device(item, device, name) for name, item in value.items()}
    if isinstance(value, list):
        return value
    return value


def modality_assignments(batch: dict[str, Any], config: dict[str, Any], epoch: int, view_role: int,
                         global_rank: int = 0) -> torch.Tensor:
    assignments = torch.full((batch["entities"]["entity_type"].numel(),), -1, dtype=torch.int64)
    scene_ptr = batch["scene_ptr"].tolist()
    local_ids = batch["entities"]["local_entity_id"].tolist()
    available = batch["entities"]["modality_available"].bool()
    probability = float(config["training"]["modality_mask_probability"])
    for scene_index, scene_id in enumerate(batch["scene_ids"]):
        for row in range(scene_ptr[scene_index], scene_ptr[scene_index + 1]):
            fields = dict(epoch=epoch, global_rank=global_rank, worker_id=0, operation="entity-gate",
                          scene_id=scene_id, local_entity_id=int(local_ids[row]), view_role=view_role)
            if uniform01(config, "modality-mask", **fields) >= probability:
                continue
            choices = torch.nonzero(available[row]).flatten().tolist()
            pick = derive_seed(config, "modality-mask", epoch=epoch, global_rank=global_rank, worker_id=0,
                               operation="available-modality", scene_id=scene_id,
                               local_entity_id=int(local_ids[row]), view_role=view_role) % len(choices)
            assignments[row] = int(choices[pick])
    return assignments


def deterministic_relation_layer(layer: nn.Module, values: torch.Tensor, edge_index: torch.Tensor,
                                 relation: torch.Tensor) -> torch.Tensor:
    count = values.shape[0]
    if edge_index.shape[1] == 0:
        message = torch.zeros_like(values)
    else:
        source, destination = edge_index
        if source.numel() > 1 and not torch.all(source[1:] >= source[:-1]):
            raise ValueError("relation edges must be source-sorted for deterministic segment reduction")
        query = layer.query(values).view(count, layer.heads, layer.head_dimension)
        key = layer.key(values).view(count, layer.heads, layer.head_dimension)
        val = layer.value(values).view(count, layer.heads, layer.head_dimension)
        score = (query[source] * key[destination]).sum(-1) / math.sqrt(layer.head_dimension)
        score = score + torch.einsum("er,hr->eh", relation, layer.relation_bias)
        lengths = torch.bincount(source, minlength=count)
        maxima = torch.segment_reduce(score, "max", lengths=lengths)
        exponent = torch.exp(score - maxima[source])
        denominator = torch.segment_reduce(exponent, "sum", lengths=lengths)
        weight = exponent / denominator[source]
        relation_message = torch.einsum("hdr,er->ehd", layer.relation_value, relation)
        edge_message = weight[:, :, None] * (val[destination] + relation_message)
        aggregate = torch.segment_reduce(edge_message, "sum", lengths=lengths)
        message = layer.output(aggregate.flatten(1))
    intermediate = layer.norm_attention(values + layer.dropout(message))
    return layer.norm_ffn(intermediate + layer.dropout(layer.ffn(intermediate)))


class ForwardResult(NamedTuple):
    output: dict[str, torch.Tensor]
    modalities: dict[str, torch.Tensor]


class TrainingModel(nn.Module):
    def __init__(self, model_config: dict[str, Any], vocabulary_sizes: dict[str, int], objective: dict[str, Any]) -> None:
        super().__init__()
        self.online = ReducedSceneEncoder(model_config, vocabulary_sizes)
        self.target = copy.deepcopy(self.online)
        self.target.requires_grad_(False)
        self.target.eval()
        self.objective = objective

    def train(self, mode: bool = True):
        super().train(mode)
        self.target.eval()
        return self

    @staticmethod
    def _modalities(model: ReducedSceneEncoder, batch: dict[str, Any], geometry: tuple[torch.Tensor, torch.Tensor]) -> dict[str, torch.Tensor]:
        entities = batch["entities"]
        magnitude, phase = geometry
        return {
            "relative": model.position_encoder(sinusoidal_position_features(entities["relative_position_m"], model.wavelengths)),
            "geometry": model.geometry_fusion(torch.cat((model.magnitude_encoder(magnitude), model.phase_encoder(phase)), 1)),
            "semantic": model._semantic(entities),
            "environmental": model.object_raster_encoder(entities["object_raster"]),
        }

    @staticmethod
    def _finish(model: ReducedSceneEncoder, batch: dict[str, Any], modalities: torch.Tensor) -> dict[str, torch.Tensor]:
        entities, edges, rasters = batch["entities"], batch["edges"], batch["rasters"]
        type_embedding = model.type_embedding(entities["entity_type"])
        logits = torch.stack([gate(torch.cat((modalities[:, index], type_embedding), 1))
                              for index, gate in enumerate(model.gates)], 1)
        available = entities["modality_available"].bool()[:, :, None]
        weights = torch.softmax(logits.masked_fill(~available, -torch.inf), 1)
        contextual = model.entity_norm((weights * modalities).sum(1))
        relation = relation_set_embedding(edges["relation_mask"].to(torch.uint8), model.relation_embedding)
        for layer in model.relation_layers:
            contextual = deterministic_relation_layer(layer, contextual, edges["edge_index"], relation)
        scene_count = len(batch["scene_ids"])
        type_summary = model._type_pool(contextual, entities["entity_type"], batch["entity_scene_index"], scene_count)
        fraction = rasters["landcover_class_fraction"]
        landcover = torch.einsum("bchw,cd->bdhw", fraction, model.landcover_embedding.weight[:22])
        valid = rasters["landcover_valid_mask"].bool()
        landcover = torch.where(valid[:, None], landcover, model.landcover_embedding.weight[22][None, :, None, None])
        intentional = rasters["landcover_intentional_mask"].bool()
        if torch.any(intentional & valid):
            raise ValueError("intentional land-cover mask overlaps valid support")
        landcover = torch.where(intentional[:, None], model.landcover_embedding.weight[23][None, :, None, None], landcover)
        landcover_scene = model.landcover_projection(model.landcover_cnn(landcover))
        dem_scene = model.dem_projection(model.dem_cnn(rasters["dem_standardized_mean"][:, None]))
        scene = model.scene_fusion(torch.cat((type_summary.flatten(1), landcover_scene, dem_scene), 1))
        return {"scene_embedding": scene, "contrastive_embedding": F.normalize(model.contrastive_projection(scene), dim=1)}

    def _online_one(self, batch: dict[str, Any], geometry: tuple[torch.Tensor, torch.Tensor], assignments: torch.Tensor) -> ForwardResult:
        modalities = self._modalities(self.online, batch, geometry)
        stacked = torch.stack(tuple(modalities[name] for name in MODALITIES), 1)
        assignments = assignments.to(stacked.device)
        for index in range(4):
            selected = assignments == index
            if selected.any():
                stacked[selected, index] = self.online.mask_embeddings[index]
        output = self._finish(self.online, batch, stacked)
        return ForwardResult(output, modalities)

    def forward(self, batches: Sequence[dict[str, Any]], geometries: Sequence[tuple[torch.Tensor, torch.Tensor]],
                assignments: Sequence[torch.Tensor]) -> list[ForwardResult]:
        return [self._online_one(batch, geometry, assignment)
                for batch, geometry, assignment in zip(batches, geometries, assignments, strict=True)]

    @torch.no_grad()
    def target_forward(self, batch: dict[str, Any], geometry: tuple[torch.Tensor, torch.Tensor]) -> dict[str, torch.Tensor]:
        modalities = self._modalities(self.target, batch, geometry)
        return self._finish(self.target, batch, torch.stack(tuple(modalities[name] for name in MODALITIES), 1))

    @torch.no_grad()
    def update_target(self, coefficient: float) -> None:
        online = dict(self.online.named_parameters())
        for name, target in self.target.named_parameters():
            target.mul_(coefficient).add_(online[name], alpha=1.0 - coefficient)
        online_buffers = dict(self.online.named_buffers())
        for name, target in self.target.named_buffers():
            target.copy_(online_buffers[name])


def local_infonce_sum(q1: torch.Tensor, q2: torch.Tensor, global_k1: torch.Tensor, global_k2: torch.Tensor,
                      local_centers: torch.Tensor, global_centers: torch.Tensor, local_ids: torch.Tensor,
                      global_ids: torch.Tensor, queue: dict[str, Any], temperature: float,
                      exclusion_m: float, identity_diagnostic_context: dict[str, Any] | None = None) -> tuple[torch.Tensor, int]:
    validate_current_batch_lookup(
        local_ids, global_ids, global_embedding_rows=global_k1.shape[0], queue=queue,
        context=identity_diagnostic_context,
    )
    keys = torch.cat((global_k1, global_k2), 0)
    key_centers = torch.cat((global_centers, global_centers), 0)
    key_ids = torch.cat((global_ids, global_ids), 0)
    losses = []
    for queries, positives in ((q1, global_k2), (q2, global_k1)):
        for local_index in range(queries.shape[0]):
            query = queries[local_index]
            scene_id = local_ids[local_index]
            global_index = torch.nonzero(global_ids == scene_id).flatten()
            positive = positives[int(global_index[0])]
            distance = torch.linalg.vector_norm(key_centers - local_centers[local_index], dim=1)
            valid = (key_ids != scene_id) & (distance >= exclusion_m)
            negatives = [keys[valid]] if valid.any() else []
            valid_count = int(queue["valid_count"])
            if valid_count:
                qdistance = torch.linalg.vector_norm(queue["centers"][:valid_count] - local_centers[local_index], dim=1)
                qvalid = (queue["scene_ids"][:valid_count] != scene_id) & (qdistance >= exclusion_m)
                if qvalid.any(): negatives.append(queue["values"][:valid_count][qvalid])
            positive_logit = (query * positive).sum().reshape(1) / temperature
            negative_logits = (torch.cat([query @ item.T for item in negatives]) / temperature
                               if negatives else positive_logit.new_empty(0))
            losses.append(-positive_logit[0] + torch.logsumexp(torch.cat((positive_logit, negative_logits)), 0))
    return torch.stack(losses).sum(), len(losses)


def empty_queue(device: torch.device, capacity: int = 8192, dimension: int = 64) -> dict[str, Any]:
    return {"values": torch.zeros((capacity, dimension), dtype=torch.float32, device=device),
            "scene_ids": torch.zeros(capacity, dtype=torch.int64, device=device),
            "centers": torch.zeros((capacity, 2), dtype=torch.float32, device=device),
            "pointer": 0, "valid_count": 0, "enqueue_count": 0}


@torch.no_grad()
def enqueue(queue: dict[str, Any], values: torch.Tensor, scene_ids: torch.Tensor, centers: torch.Tensor) -> None:
    capacity = queue["values"].shape[0]
    for value, scene_id, center in zip(values, scene_ids, centers, strict=True):
        pointer = int(queue["pointer"])
        queue["values"][pointer].copy_(value)
        queue["scene_ids"][pointer].copy_(scene_id)
        queue["centers"][pointer].copy_(center)
        queue["pointer"] = (pointer + 1) % capacity
        queue["valid_count"] = min(capacity, int(queue["valid_count"]) + 1)
        queue["enqueue_count"] = int(queue["enqueue_count"]) + 1


def selector_decision(best: dict[str, Any] | None, candidate: dict[str, Any], threshold: float = 1e-4) -> bool:
    if best is None:
        return True
    difference = float(candidate["validation_retrieval_loss"]) - float(best["validation_retrieval_loss"])
    if difference < -threshold:
        return True
    if abs(difference) < threshold:
        margin_difference = float(candidate["mean_source_separation_margin"]) - float(best["mean_source_separation_margin"])
        if margin_difference > 0:
            return True
        if margin_difference == 0 and int(candidate["epoch"]) < int(best["epoch"]):
            return True
    return False


def replay_selector(events: Sequence[dict[str, Any]], threshold: float = 1e-4) -> tuple[dict[str, Any], int]:
    best = None; patience = 0
    for event in events:
        if selector_decision(best, event, threshold):
            best = dict(event); patience = 0
        else:
            patience += 1
    if best is None:
        raise ValueError("selector has no validation events")
    return best, patience


def _state_hash_update(digest: Any, value: Any) -> None:
    if isinstance(value, torch.Tensor):
        tensor = value.detach().cpu().contiguous()
        digest.update(b"tensor\0" + str(tensor.dtype).encode() + b"\0" + canonical_json_bytes(list(tensor.shape)))
        digest.update(tensor.numpy().tobytes())
    elif isinstance(value, np.ndarray):
        array = np.ascontiguousarray(value)
        digest.update(b"ndarray\0" + str(array.dtype).encode() + b"\0" + canonical_json_bytes(list(array.shape)))
        digest.update(array.tobytes())
    elif isinstance(value, dict):
        digest.update(b"dict\0")
        for key in sorted(value, key=lambda item: str(item)):
            _state_hash_update(digest, str(key)); _state_hash_update(digest, value[key])
    elif isinstance(value, (list, tuple)):
        digest.update(("tuple" if isinstance(value, tuple) else "list").encode() + b"\0")
        for item in value: _state_hash_update(digest, item)
    elif isinstance(value, bytes):
        digest.update(b"bytes\0" + value)
    else:
        digest.update(b"scalar\0" + canonical_json_bytes(value))


def state_content_digest(value: Any) -> str:
    digest = hashlib.sha256(); _state_hash_update(digest, value); return digest.hexdigest()


def training_batch_digest(scene_ids: Sequence[str], view_pairs: Sequence[tuple[int, int]]) -> str:
    return canonical_digest([{"scene_id": scene, "views": list(views)} for scene, views in zip(scene_ids, view_pairs, strict=True)])
