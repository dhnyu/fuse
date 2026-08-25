#!/usr/bin/env python3
"""Execute the accepted single-GPU I21 prototype run."""

from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import math
import os
import platform
import random
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Iterator

for _name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_name] = "1"

import jsonschema
import numpy as np
import psutil
import torch
import yaml
from torch.utils.data import DataLoader, Dataset, Sampler

from prototype_dataloader import AcceptedPrototypeDataset, canonical_json_bytes, ragged_collate, sha256_file
from prototype_encoder import geometry_fourier_features
from prototype_joint_model import JointPrototypeModel, enqueue, information_preservation_loss, modality_mask_assignments, reconstruction_losses
from prototype_training_runtime import terminal_checkpoint_decision
from prototype_validation import NEW_METRIC_KEYS, replay_early_stopping, retrieval_metrics
from prototype_training_data import augment_and_materialize, initialize_native_worker, prepare_augmentation_sample
from run_prototype_augmentation_benchmark import load_resources


def stable_integer(*values: Any) -> int:
    return int.from_bytes(hashlib.sha256("|".join(map(str, values)).encode()).digest()[:8], "big")


def state_digest(value: Any) -> str:
    digest = hashlib.sha256()
    def update(item: Any) -> None:
        if isinstance(item, torch.Tensor):
            array = item.detach().cpu().contiguous().numpy()
            digest.update(str(array.dtype).encode()); digest.update(str(array.shape).encode()); digest.update(array.tobytes())
        elif isinstance(item, np.ndarray):
            digest.update(str(item.dtype).encode()); digest.update(str(item.shape).encode()); digest.update(item.tobytes())
        elif isinstance(item, dict):
            for key in sorted(item, key=str): digest.update(str(key).encode()); update(item[key])
        elif isinstance(item, (list, tuple)):
            for child in item: update(child)
        else:
            digest.update(repr(item).encode())
    update(value)
    return digest.hexdigest()


class AugmentedPairDataset(Dataset):
    def __init__(self, accepted: str, tensor_contract: str, split: str, config: dict[str, Any],
                 thresholds: dict[int, float], validation: bool = False,
                 archive_source_root: str | None = None, archive_runtime_root: str | None = None,
                 persistent_archive_handles: bool = False, diagnostic_timing: bool = False,
                 diagnostic_steps: set[int] | None = None, diagnostic_steps_per_epoch: int = 8) -> None:
        self.base = AcceptedPrototypeDataset(
            accepted, tensor_contract, split=split, verify_checksums=True,
            archive_source_root=archive_source_root, archive_runtime_root=archive_runtime_root,
            persistent_archive_handles=persistent_archive_handles, diagnostic_timing=diagnostic_timing,
        )
        self.config = config
        self.resources = load_resources(self.base.manifest)
        self.thresholds = thresholds
        self.validation = validation
        self.diagnostic_timing = diagnostic_timing
        self.diagnostic_steps = diagnostic_steps
        self.diagnostic_steps_per_epoch = int(diagnostic_steps_per_epoch)

    def __len__(self) -> int:
        return len(self.base)

    def __getitem__(self, task: tuple[int, int, int]) -> dict[str, Any]:
        started = time.perf_counter()
        position, epoch, group = map(int, task)
        step = epoch * self.diagnostic_steps_per_epoch + group + 1
        profile_sample = self.diagnostic_timing and (self.diagnostic_steps is None or step in self.diagnostic_steps)
        previous_timing = self.base.diagnostic_timing; self.base.diagnostic_timing = profile_sample
        try: sample = self.base[position]
        finally: self.base.diagnostic_timing = previous_timing
        base_finished = time.perf_counter()
        prepared = prepare_augmentation_sample(sample)
        views = [
            augment_and_materialize(
                sample, self.config, self.resources, self.thresholds, epoch, view, prepared=prepared
            )
            for view in (0, 1)
        ]
        if self.validation:
            views.append(augment_and_materialize(
                sample, self.config, self.resources, self.thresholds, 0, 0, intensity=0.0, prepared=prepared
            ))
        result = {"views": views, "group": group, "position": position}
        if profile_sample:
            result["_diagnostic_timing"] = {
                **sample["_diagnostic_timing"],
                "base_observed_seconds": base_finished - started,
                "augmentation_seconds": time.perf_counter() - base_finished,
                "worker_total_seconds": time.perf_counter() - started,
            }
        return result


class LogicalGroupSampler(Sampler[list[tuple[int, int, int]]]):
    def __init__(self, rows: list[dict[str, Any]], budgets: dict[str, int], seed: int) -> None:
        self.rows, self.budgets, self.seed, self.epoch = rows, budgets, int(seed), 0

    def set_epoch(self, epoch: int) -> None:
        self.epoch = int(epoch)

    def permutation(self) -> list[int]:
        rng = np.random.Generator(np.random.PCG64(stable_integer(self.seed, self.epoch, "sampler")))
        return rng.permutation(len(self.rows)).tolist()

    def batches(self) -> list[list[tuple[int, int, int]]]:
        order = self.permutation()
        if len(order) % 32:
            raise ValueError("training population is not divisible by effective batch 32")
        output: list[list[tuple[int, int, int]]] = []
        for group, start in enumerate(range(0, len(order), 32)):
            current: list[tuple[int, int, int]] = []
            load = {name: 0 for name in self.budgets}
            for position in order[start:start + 32]:
                row = self.rows[position]
                cost = {"scenes": 1, "nodes": int(row["node_count"]), "ordered_edges": int(row["ordered_edge_count"]),
                        "coordinates": int(row["coordinate_count"]), "actual_payload_bytes": int(row["actual_payload_bytes"])}
                if current and any(load[key] + cost[key] > int(self.budgets[key]) for key in self.budgets):
                    output.append(current); current = []; load = {name: 0 for name in self.budgets}
                current.append((position, self.epoch, group))
                for key in load: load[key] += cost[key]
            if current: output.append(current)
        return output

    def __iter__(self) -> Iterator[list[tuple[int, int, int]]]:
        return iter(self.batches())

    def __len__(self) -> int:
        return len(self.batches())


def collate_pairs(items: list[dict[str, Any]]) -> dict[str, Any]:
    started = time.perf_counter()
    view_count = len(items[0]["views"])
    result = {
        "views": [ragged_collate([item["views"][view] for item in items]) for view in range(view_count)],
        "group": items[0]["group"], "positions": [item["position"] for item in items],
        "i19_digests": [[item["views"][view]["i19_logical_digest"] for item in items] for view in range(2)],
        "tensor_digests": [[item["views"][view]["training_tensor_digest"] for item in items] for view in range(2)],
        "centers": [item["views"][0]["meta"]["center_xy_5186"] for item in items],
        "augmentation_statistics": [[item["views"][view]["augmentation_result"]["statistics"] for item in items] for view in range(2)],
    }
    if "_diagnostic_timing" in items[0]:
        result["_diagnostic_timing"] = {
            "samples": [item["_diagnostic_timing"] for item in items],
            "collate_seconds": time.perf_counter() - started,
        }
    return result


def worker_init(_: int) -> None:
    initialize_native_worker()


def device_batch(batch: dict[str, Any], device: torch.device, mask_indices: dict[str, int]) -> dict[str, Any]:
    # Scientific float64 reference and original topology deliberately never enter the device/encoder namespace.
    allowed = {key: batch[key] for key in (
        "scene_ids", "scene_ptr", "entity_scene_index", "entity_local_index", "entities", "geometry", "edges", "rasters"
    )}
    def move(value: Any) -> Any:
        if isinstance(value, torch.Tensor): return value.to(device, non_blocking=True)
        if isinstance(value, dict): return {key: move(child) for key, child in value.items()}
        return value
    result = move(allowed)
    result["category_mask_indices"] = mask_indices
    return result


def modality_counts(batch: dict[str, Any], mask_indices: dict[str, int]) -> dict[str, int]:
    entities = batch["entities"]
    semantic = 0
    for prefix, names in (("building", ("A9", "A11")), ("road", ("ROAD_RANK", "ROAD_TYPE")),
                          ("poi", tuple(f"CLASS_L{i}" for i in range(1, 7)))):
        categories = entities[f"{prefix}_category"]
        if categories.numel():
            valid = torch.zeros(categories.shape[0], dtype=torch.bool)
            for column, name in enumerate(names): valid |= categories[:, column] != mask_indices[name]
            if prefix != "poi": valid |= (~entities[f"{prefix}_missing"].bool()).any(dim=1)
            semantic += int(valid.sum())
    n = int(entities["entity_type"].numel())
    return {"relative": n, "geometry": int((entities["entity_type"] != 2).sum()), "semantic": semantic, "environmental": n}


def query_loss(query: torch.Tensor, global_indices: list[int], positive: torch.Tensor, keys: torch.Tensor,
               centers: torch.Tensor, queue_values: torch.Tensor, queue_centers: torch.Tensor,
               occupancy: int, temperature: float, exclusion: float) -> torch.Tensor:
    scene_count = centers.shape[0]
    key_centers = torch.cat((centers, centers))
    key_scene = torch.arange(scene_count, device=centers.device).repeat(2)
    losses = []
    for local, index in enumerate(global_indices):
        distance = torch.linalg.vector_norm(key_centers - centers[index], dim=1)
        valid = (key_scene != index) & (distance >= exclusion)
        candidates = [keys[valid]] if valid.any() else []
        if occupancy:
            qdistance = torch.linalg.vector_norm(queue_centers[:occupancy] - centers[index], dim=1)
            qvalid = qdistance >= exclusion
            if qvalid.any(): candidates.append(queue_values[:occupancy][qvalid])
        pos = (query[local] * positive[index]).sum().reshape(1) / temperature
        neg = torch.cat([query[local] @ values.T for values in candidates]) / temperature if candidates else pos.new_empty(0)
        losses.append(-pos[0] + torch.logsumexp(torch.cat((pos, neg)), dim=0))
    return torch.stack(losses).sum()


def make_optimizer(model: JointPrototypeModel, spec: dict[str, Any]) -> tuple[torch.optim.Optimizer, torch.optim.lr_scheduler.LambdaLR]:
    base = float(spec["optimizer"]["learning_rate"])
    optimizer = torch.optim.AdamW((parameter for parameter in model.parameters() if parameter.requires_grad), lr=base,
                                  weight_decay=float(spec["optimizer"]["weight_decay"]))
    steps_per_epoch = optimizer_steps_per_epoch(spec)
    warmup = int(spec["optimizer"]["warmup_epochs"]) * steps_per_epoch
    maximum = int(spec["optimizer"]["maximum_epochs"]) * steps_per_epoch
    def scale(step: int) -> float:
        if step < warmup: return float(step + 1) / warmup
        progress = (step - warmup) / max(1, maximum - warmup)
        return 0.5 * (1 + math.cos(math.pi * min(1.0, progress)))
    return optimizer, torch.optim.lr_scheduler.LambdaLR(optimizer, scale)


def optimizer_steps_per_epoch(spec: dict[str, Any]) -> int:
    training_scenes = int(spec["training_scenes"])
    effective_batch = int(spec["effective_batch_scenes"])
    if training_scenes <= 0 or effective_batch <= 0 or training_scenes % effective_batch:
        raise ValueError("training scenes must be exactly divisible by the effective batch")
    declared = spec.get("optimizer", {}).get("optimizer_steps_per_epoch")
    derived = training_scenes // effective_batch
    if declared is not None and int(declared) != derived:
        raise ValueError(f"optimizer_steps_per_epoch mismatch: declared={declared} derived={derived}")
    return derived


def checkpoint_state(model: JointPrototypeModel, optimizer: torch.optim.Optimizer, scheduler: Any,
                     queue: dict[str, Any], progress: dict[str, Any]) -> dict[str, Any]:
    return {
        "online_model": model.online.state_dict(), "target_model": model.target.state_dict(),
        "projection_and_decoders": {"mask": model.modality_mask_embeddings.detach(), "decoders": model.decoders.state_dict()},
        "optimizer": optimizer.state_dict(), "scheduler": scheduler.state_dict(), "ema_update_count": progress["optimizer_step"],
        "queue_values": queue["values"], "queue_scene_ids": queue["scene_ids"], "queue_scene_centers": queue["centers"],
        "queue_pointer": queue["pointer"], "queue_occupancy": queue["occupancy"],
        "python_rng": random.getstate(), "numpy_rng": np.random.get_state(), "torch_cpu_rng": torch.get_rng_state(),
        "torch_cuda_rng": torch.cuda.get_rng_state(), "sampler_epoch": progress["epoch"],
        "sampler_permutation": progress["permutation"], "sampler_position": progress["group_position"],
        "accumulation_scene_count": 0, "accumulation_gradient_state": {},
        "best_checkpoint_metric_state": progress["best"], "validation_history": progress["validation"],
        "early_stopping_patience_state": progress["patience"],
        "early_stopping_metric_state": progress.get("early_stopping_metric_state"), "optimizer_step": progress["optimizer_step"],
        "scene_consumptions": progress["scene_consumptions"], "scientific_parents": progress["parents"],
        "run_id": progress["run_id"], "seed": progress["seed"], "schema_version": "1.0.0",
    }


def save_checkpoint(path: Path, state: dict[str, Any], diagnostic: dict[str, float] | None = None) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    started = time.perf_counter() if diagnostic is not None else 0.0
    torch.save(state, temporary)
    if diagnostic is not None:
        diagnostic["checkpoint_serialization_seconds"] = time.perf_counter() - started; started = time.perf_counter()
    with temporary.open("rb") as stream: os.fsync(stream.fileno())
    if diagnostic is not None:
        diagnostic["checkpoint_fsync_seconds"] = time.perf_counter() - started; started = time.perf_counter()
    loaded = torch.load(temporary, map_location="cpu", weights_only=False)
    digest = state_digest(loaded)
    if diagnostic is not None:
        diagnostic["checkpoint_reload_validation_seconds"] = time.perf_counter() - started
    if path.exists():
        existing = torch.load(path, map_location="cpu", weights_only=False)
        if state_digest(existing) != digest: raise RuntimeError(f"immutable checkpoint collision: {path}")
        temporary.unlink()
    else: os.replace(temporary, path)
    started = time.perf_counter() if diagnostic is not None else 0.0
    sha256 = sha256_file(path)
    if diagnostic is not None:
        diagnostic["checkpoint_hash_seconds"] = time.perf_counter() - started
    return {"path": str(path), "size_bytes": path.stat().st_size, "sha256": sha256, "state_digest": digest}


def restore_checkpoint(path: Path, model: JointPrototypeModel, optimizer: Any, scheduler: Any,
                       queue: dict[str, Any]) -> dict[str, Any]:
    state = torch.load(path, map_location="cpu", weights_only=False)
    model.online.load_state_dict(state["online_model"]); model.target.load_state_dict(state["target_model"])
    model.modality_mask_embeddings.data.copy_(state["projection_and_decoders"]["mask"])
    model.decoders.load_state_dict(state["projection_and_decoders"]["decoders"])
    optimizer.load_state_dict(state["optimizer"]); scheduler.load_state_dict(state["scheduler"])
    for key, source in (("values", "queue_values"), ("scene_ids", "queue_scene_ids"), ("centers", "queue_scene_centers")):
        queue[key].copy_(state[source].to(queue[key].device))
    queue["pointer"], queue["occupancy"] = int(state["queue_pointer"]), int(state["queue_occupancy"])
    random.setstate(state["python_rng"]); np.random.set_state(state["numpy_rng"]); torch.set_rng_state(state["torch_cpu_rng"])
    torch.cuda.set_rng_state(state["torch_cuda_rng"])
    return state


def train_group(model: JointPrototypeModel, cpu_batches: list[dict[str, Any]], optimizer: Any, scheduler: Any,
                queue: dict[str, Any], spec: dict[str, Any], joint: dict[str, Any], encoder_config: dict[str, Any],
                mask_indices: dict[str, int], device: torch.device, epoch: int,
                perform_update: bool = True) -> dict[str, Any]:
    optimizer.zero_grad(set_to_none=True)
    batches = [[device_batch(item["views"][view], device, mask_indices) for view in (0, 1)] for item in cpu_batches]
    counts = {name: sum(modality_counts(item["views"][view], mask_indices)[name]
                        for item in cpu_batches for view in (0, 1))
              for name in ("relative", "geometry", "semantic", "environmental")}
    active = sum(value > 0 for value in counts.values())
    keys = [[], []]; sizes = []
    with torch.no_grad():
        for pair in batches:
            sizes.append(len(pair[0]["scene_ids"]))
            for view in (0, 1):
                geometry = geometry_fourier_features(pair[view], encoder_config, device)
                keys[view].append(model.forward_target(pair[view], geometry)["projection"])
    k1, k2 = torch.cat(keys[0]), torch.cat(keys[1])
    all_keys = torch.cat((k1, k2))
    centers = torch.tensor([center for item in cpu_batches for center in item["centers"]], dtype=torch.float32, device=device)
    if centers.shape[0] != 32: raise ValueError("logical group does not contain exactly 32 scenes")
    cursor = 0; scene_sum = 0.0; ip_sum = 0.0
    for batch_index, (pair, size) in enumerate(zip(batches, sizes, strict=True)):
        indices = list(range(cursor, cursor + size)); cursor += size
        for view in (0, 1):
            geometry = geometry_fourier_features(pair[view], encoder_config, device)
            assignments = modality_mask_assignments(pair[view], int(spec["seed"]), epoch, view, float(joint["modality_masking"]["selection_probability"]))
            forward = model.forward_online(pair[view], geometry, assignments)
            positive = k2 if view == 0 else k1
            scene_component = query_loss(forward.outputs["projection"], indices, positive, all_keys, centers,
                                         queue["values"], queue["centers"], queue["occupancy"],
                                         float(spec["optimizer"]["temperature"]), float(spec["optimizer"]["geographic_negative_exclusion_radius_m"])) / 64.0
            losses = reconstruction_losses(model, pair[view], geometry, forward.modalities, joint)
            local_counts = modality_counts(cpu_batches[batch_index]["views"][view], mask_indices)
            if any(losses["modalities"][name]["local_valid_count"] != local_counts[name] for name in counts):
                raise RuntimeError("reconstruction count contract mismatch")
            ip_component = information_preservation_loss(losses, counts)
            loss = scene_component + float(joint["loss"]["information_preservation_weight"]) * ip_component
            if not torch.isfinite(loss): raise ValueError("non-finite training loss")
            loss.backward()
            scene_sum += float(scene_component.detach()); ip_sum += float(ip_component.detach())
    invalid = [name for name, parameter in model.named_parameters() if parameter.requires_grad and parameter.grad is not None and not torch.isfinite(parameter.grad).all()]
    missing = [name for name, parameter in model.named_parameters() if parameter.requires_grad and parameter.grad is None]
    zero = [name for name, parameter in model.named_parameters() if parameter.requires_grad and parameter.grad is not None and not torch.any(parameter.grad != 0)]
    if invalid or missing or zero: raise ValueError(f"invalid joint gradients missing={missing} invalid={invalid} zero={zero}")
    gradient_norm = torch.nn.utils.clip_grad_norm_([p for p in model.parameters() if p.requires_grad], float(spec["optimizer"]["gradient_norm_clip"]))
    applied_learning_rate = float(optimizer.param_groups[0]["lr"])
    if perform_update:
        optimizer.step(); scheduler.step(); model.update_target(float(spec["optimizer"]["ema_momentum"]))
        numeric_ids = torch.tensor([stable_integer(scene_id) & ((1 << 63) - 1) for item in cpu_batches for scene_id in item["views"][0]["scene_ids"]], dtype=torch.int64, device=device)
        values = torch.stack((k1, k2), dim=1).reshape(64, 128); inserted_centers = centers.repeat_interleave(2, dim=0)
        queue["pointer"], queue["occupancy"] = enqueue(queue["values"], queue["scene_ids"], queue["centers"], queue["pointer"], queue["occupancy"], values, numeric_ids.repeat_interleave(2), inserted_centers)
    return {"total_loss": scene_sum + float(joint["loss"]["information_preservation_weight"]) * ip_sum,
            "scene_loss": scene_sum, "information_preservation_loss": ip_sum, "gradient_norm": float(gradient_norm),
            "learning_rate": applied_learning_rate, "microbatch_sizes": sizes,
            "augmentation_digest": state_digest([item["i19_digests"] for item in cpu_batches])}


def take_first_logical_group(loader: DataLoader) -> list[dict[str, Any]]:
    batches: list[dict[str, Any]] = []
    for item in loader:
        if batches and int(item["group"]) != int(batches[0]["group"]): break
        batches.append(item)
        count = sum(len(batch["positions"]) for batch in batches)
        if count == 32: return batches
        if count > 32: raise ValueError("preflight group exceeds 32 scenes")
    raise ValueError("preflight could not assemble a complete logical group")


def validation(model: JointPrototypeModel, loader: DataLoader, encoder_config: dict[str, Any], mask_indices: dict[str, int],
               device: torch.device, validation_config: dict[str, Any]) -> dict[str, Any]:
    model.eval(); query = [[], []]; candidates = []; scene_ids = []
    with torch.no_grad():
        for item in loader:
            for view in range(3):
                batch = device_batch(item["views"][view], device, mask_indices)
                geometry = geometry_fourier_features(batch, encoder_config, device)
                assignments = torch.full((batch["entities"]["entity_type"].numel(),), -1, dtype=torch.int64)
                embedding = model.forward_online(batch, geometry, assignments).outputs["scene_embedding"]
                (query[view] if view < 2 else candidates).append(embedding)
            scene_ids.extend(item["views"][0]["scene_ids"])
    candidate = torch.cat(candidates); queries = torch.cat((torch.cat(query[0]), torch.cat(query[1])))
    metrics = retrieval_metrics(queries, candidate, scene_ids, validation_config, state_digest)
    model.train(); model.target.eval()
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ("run-spec", "training-config", "joint-config", "encoder-config", "augmentation-config", "tensor-contract", "i19-manifest", "schema"):
        parser.add_argument(f"--{name}", required=True)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    started = time.time(); run_spec_path = Path(args.run_spec).resolve(); spec = json.loads(run_spec_path.read_text())
    training_config_path = Path(args.training_config).resolve(); training_config = yaml.safe_load(training_config_path.read_text())
    joint_path = Path(args.joint_config).resolve(); joint = yaml.safe_load(joint_path.read_text())
    encoder_path = Path(args.encoder_config).resolve(); encoder_config = yaml.safe_load(encoder_path.read_text())
    augmentation_path = Path(args.augmentation_config).resolve(); augmentation = yaml.safe_load(augmentation_path.read_text())
    i19_path = Path(args.i19_manifest).resolve(); i19 = json.loads(i19_path.read_text())
    if spec["run_id"] != training_config["identity"]["run_id"] or spec["plan_id"] != training_config["identity"]["plan_id"]:
        raise ValueError("I21 plan/run identity mismatch")
    accepted_path = Path(spec["dataset_manifest"]["path"])
    parents = {"dataset": spec["dataset_manifest"], "loader": spec["dataloader_manifest"], "gate": spec["no_op_gate_manifest"],
               "encoder": spec["encoder_manifest"], "augmentation": spec["augmentation_manifest"], "joint": spec["joint_model_manifest"]}
    for name, record in parents.items():
        path = Path(record["path"])
        if not path.is_file() or path.stat().st_size != int(record["size_bytes"]) or sha256_file(path) != record["sha256"]:
            raise ValueError(f"I21 upstream checksum mismatch: {name}")
    if i19["augmentation_acceptance_id"] != spec["augmentation_manifest"]["path"].split("/")[-2]: raise ValueError("I19 path identity mismatch")
    threshold_values = i19["logical_results"]["thresholds"]
    thresholds = {0: float(threshold_values["building"]), 1: float(threshold_values["road"])}
    workers = int(training_config["execution"]["workers"])
    if workers != 40: raise ValueError("approved production worker count is 40")
    single_checkpoints = Path(spec["output_root"]) / "mutable" / "checkpoints"
    terminal_states = []
    parent_hashes = {key: value["sha256"] for key, value in parents.items()}
    for checkpoint_path in single_checkpoints.glob("epoch-*.pt"):
        checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
        if checkpoint.get("run_id") != spec["run_id"] or checkpoint.get("scientific_parents") != parent_hashes:
            raise ValueError(f"foreign single-GPU checkpoint lineage: {checkpoint_path}")
        decision = terminal_checkpoint_decision(checkpoint, spec)
        if decision.terminal: terminal_states.append((decision.completed_epoch, checkpoint_path, decision))
    if terminal_states:
        _, checkpoint_path, decision = min(terminal_states)
        print(json.dumps({"status":"PASS","mode":"terminal_training_blocked","optimizer_steps":0,
                          "cuda_operations":0,"terminal_reason":decision.reason,
                          "terminal_checkpoint":str(checkpoint_path)},sort_keys=True))
        return
    if not torch.cuda.is_available() or torch.cuda.device_count() != 1: raise RuntimeError("I21 requires one lock-selected CUDA GPU")
    torch.set_num_threads(1); torch.set_num_interop_threads(1); torch.use_deterministic_algorithms(True)
    torch.backends.cuda.matmul.allow_tf32 = False; torch.backends.cudnn.allow_tf32 = False
    seed = int(spec["seed"]); random.seed(seed); np.random.seed(seed); torch.manual_seed(seed); torch.cuda.manual_seed_all(seed)
    device = torch.device("cuda:0"); torch.cuda.set_device(device); torch.cuda.reset_peak_memory_stats()
    train_data = AugmentedPairDataset(str(accepted_path), args.tensor_contract, "training", augmentation, thresholds)
    validation_data = AugmentedPairDataset(str(accepted_path), args.tensor_contract, "validation", augmentation, thresholds, validation=True)
    if len(train_data) != 256 or len(validation_data) != 32: raise ValueError("I21 split population mismatch")
    mask_indices = {name: next(iter(values)) for name, values in train_data.base.category_mask_index.items()}
    sampler = LogicalGroupSampler(train_data.base.rows, spec["hard_budgets"], seed)
    loader = DataLoader(train_data, batch_sampler=sampler, num_workers=workers, collate_fn=collate_pairs,
                        persistent_workers=True, pin_memory=True, prefetch_factor=2, worker_init_fn=worker_init,
                        multiprocessing_context="spawn")
    validation_sampler = LogicalGroupSampler(validation_data.base.rows, spec["hard_budgets"], seed)
    validation_sampler.permutation = lambda: list(range(32))  # fixed accepted validation order
    validation_loader = DataLoader(validation_data, batch_sampler=validation_sampler, num_workers=workers, collate_fn=collate_pairs,
                                   persistent_workers=True, pin_memory=True, prefetch_factor=2, worker_init_fn=worker_init,
                                   multiprocessing_context="spawn")
    model = JointPrototypeModel(encoder_config, joint).to(device=device, dtype=torch.float32); model.train(); model.target.eval()
    if sum(p.numel() for p in model.parameters() if p.requires_grad) != 2665140: raise ValueError("I21 joint parameter count mismatch")
    optimizer, scheduler = make_optimizer(model, spec)
    queue = {"values": torch.zeros((8192, 128), device=device), "scene_ids": torch.full((8192,), -1, dtype=torch.int64, device=device),
             "centers": torch.zeros((8192, 2), device=device), "pointer": 0, "occupancy": 0}
    output_root = Path(spec["output_root"]); mutable = output_root / "mutable"; immutable = output_root / "acceptance"; checkpoints = mutable / "checkpoints"
    mutable.mkdir(parents=True, exist_ok=True); checkpoints.mkdir(parents=True, exist_ok=True)
    step_log = mutable / training_config["output"]["steps_name"]
    telemetry_log = mutable / training_config["output"]["telemetry_name"]
    progress = {"epoch": 0, "group_position": 0, "permutation": [], "optimizer_step": 0, "scene_consumptions": 0,
                "best": None, "validation": [], "patience": 0,
                "early_stopping_metric_state": {"best_mrr": None, "saturated_retrieval_loss_reference": None},
                "parents": {k: v["sha256"] for k, v in parents.items()},
                "run_id": spec["run_id"], "seed": seed}
    sampler.set_epoch(0); progress["permutation"] = sampler.permutation()
    if len(set(progress["permutation"])) != 256:
        raise ValueError("I21 sampler preflight has duplicate/omitted training scenes")
    shared_storage = any(online.data_ptr() == target.data_ptr() for online, target in zip(model.online.parameters(), model.target.parameters(), strict=True))
    if shared_storage or any(parameter.requires_grad for parameter in model.target.parameters()):
        raise ValueError("online/target encoder storage or gradient isolation failed")
    initial_record = save_checkpoint(checkpoints / "initial-step-000000.pt", checkpoint_state(model, optimizer, scheduler, queue, progress))
    before_initial = state_digest(checkpoint_state(model, optimizer, scheduler, queue, progress))
    restore_checkpoint(Path(initial_record["path"]), model, optimizer, scheduler, queue)
    if state_digest(checkpoint_state(model, optimizer, scheduler, queue, progress)) != before_initial:
        raise RuntimeError("initialized checkpoint round-trip mismatch")
    first_repeat = take_first_logical_group(loader)
    second_repeat = take_first_logical_group(loader)
    first_digest = state_digest([(item["positions"], item["i19_digests"], item["tensor_digests"]) for item in first_repeat])
    second_digest = state_digest([(item["positions"], item["i19_digests"], item["tensor_digests"]) for item in second_repeat])
    if first_digest != second_digest:
        raise RuntimeError("40-worker fixed-order augmentation/DataLoader repeat mismatch")
    accepted_i19 = {(row["scene_id"], int(row["view_id"])): row["digest"] for row in i19["logical_results"]["scene_view_digests"]}
    observed_i19 = {(scene_id, view): digest for item in first_repeat for view in (0, 1)
                    for scene_id, digest in zip(item["views"][view]["scene_ids"], item["i19_digests"][view], strict=True)}
    if any(accepted_i19.get(key) != digest for key, digest in observed_i19.items()):
        raise RuntimeError("I21 materialization does not reproduce accepted I19 logical digests")
    dry = train_group(model, first_repeat, optimizer, scheduler, queue, spec, joint, encoder_config,
                      mask_indices, device, 0, perform_update=False)
    if optimizer.state or queue["occupancy"] or scheduler.last_epoch != 0:
        raise RuntimeError("step-zero dry backward mutated optimizer/scheduler/queue")
    restore_checkpoint(Path(initial_record["path"]), model, optimizer, scheduler, queue)
    preflight = {"status": "PASS", "workers": workers, "logical_scenes": 32,
                 "repeat_digest": first_digest, "dry_loss": dry["total_loss"],
                 "accepted_i19_parity_scenes": len(observed_i19) // 2,
                 "joint_trainable_parameters": 2665140,
                 "joint_trainable_parameter_tensors": sum(p.requires_grad for p in model.parameters()),
                 "scientific_float64_on_device": False, "optimizer_step": 0}
    if args.preflight_only:
        print(json.dumps({"status": "PASS", "preflight": preflight}, sort_keys=True))
        return
    checkpoint_records = []; exact_resume = None; termination = "maximum_epochs"
    for epoch in range(int(spec["optimizer"]["maximum_epochs"])):
        sampler.set_epoch(epoch); progress["epoch"] = epoch; progress["permutation"] = sampler.permutation(); progress["group_position"] = 0
        group_batches: list[dict[str, Any]] = []; current_group = 0
        for item in loader:
            group = int(item["group"])
            if group != current_group and group_batches:
                raise RuntimeError("DataLoader crossed logical group without execution")
            group_batches.append(item)
            if sum(len(batch["positions"]) for batch in group_batches) < 32: continue
            if sum(len(batch["positions"]) for batch in group_batches) != 32: raise ValueError("partial/oversized logical group")
            before_ids = [scene for batch in group_batches for scene in batch["views"][0]["scene_ids"]]
            if len(set(before_ids)) != 32: raise ValueError("duplicate scene in logical group")
            result = train_group(model, group_batches, optimizer, scheduler, queue, spec, joint, encoder_config, mask_indices, device, epoch)
            progress["optimizer_step"] += 1; progress["scene_consumptions"] += 32; progress["group_position"] = group + 1
            row = {"epoch": epoch + 1, "logical_group": group, "optimizer_step": progress["optimizer_step"],
                   "scenes_consumed": 32, "effective_batch_size": 32, "ema_update_count": progress["optimizer_step"],
                   "queue_pointer": queue["pointer"], "queue_occupancy": queue["occupancy"], **result}
            with step_log.open("ab") as stream: stream.write(canonical_json_bytes(row))
            if progress["optimizer_step"] == 1:
                controlled = save_checkpoint(checkpoints / "controlled-step-000001.pt", checkpoint_state(model, optimizer, scheduler, queue, progress))
            elif progress["optimizer_step"] == 2 and exact_resume is None:
                direct = state_digest(checkpoint_state(model, optimizer, scheduler, queue, progress)); direct_result = copy.deepcopy(result)
                restore_checkpoint(checkpoints / "controlled-step-000001.pt", model, optimizer, scheduler, queue)
                replay = train_group(model, group_batches, optimizer, scheduler, queue, spec, joint, encoder_config, mask_indices, device, epoch)
                replay_state = checkpoint_state(model, optimizer, scheduler, queue, {**progress, "optimizer_step": 2, "scene_consumptions": 64})
                replay_digest = state_digest(replay_state)
                if direct != replay_digest or state_digest(direct_result) != state_digest(replay):
                    raise RuntimeError("controlled exact-resume mismatch")
                exact_resume = {"status": "PASS", "checkpoint_step": 1, "comparison_steps": 1,
                                "direct_state_digest": direct, "replay_state_digest": replay_digest,
                                "augmentation_digest": replay["augmentation_digest"]}
            group_batches = []; current_group = group + 1
            if time.time() - started >= 60:
                process = psutil.Process(); rss = process.memory_info().rss + sum(child.memory_info().rss for child in process.children(recursive=True) if child.is_running())
                telemetry = {"optimizer_step": progress["optimizer_step"], "process_tree_rss_bytes": rss,
                             "gpu_allocated_bytes": torch.cuda.memory_allocated(), "gpu_reserved_bytes": torch.cuda.memory_reserved(),
                             "gpu_peak_allocated_bytes": torch.cuda.max_memory_allocated()}
                with telemetry_log.open("ab") as stream: stream.write(canonical_json_bytes(telemetry))
        if group_batches: raise ValueError("epoch ended with partial logical group")
        if (epoch + 1) % int(spec["validation"]["interval_epochs"]) == 0:
            metrics = validation(model, validation_loader, encoder_config, mask_indices, device, spec["validation"]); metrics["epoch"] = epoch + 1
            progress["validation"].append(metrics)
            patience, selected, metric_state = replay_early_stopping(progress["validation"], spec["validation"])
            progress["patience"] = patience; progress["best"] = selected
            progress["early_stopping_metric_state"] = metric_state
            record = save_checkpoint(checkpoints / f"epoch-{epoch + 1:03d}.pt", checkpoint_state(model, optimizer, scheduler, queue, progress)); record["epoch"] = epoch + 1
            checkpoint_records.append(record)
            if progress["best"]["epoch"] == epoch + 1: progress["best"]["checkpoint"] = record
            if progress["patience"] >= int(spec["validation"]["early_stopping_patience_evaluations"]):
                termination = "early_stopping"; break
    if exact_resume is None: raise RuntimeError("controlled exact-resume gate was not completed")
    final_checkpoint = checkpoint_records[-1]
    best_checkpoint = progress["best"]["checkpoint"]
    if loader._iterator is not None: loader._iterator._shutdown_workers()
    if validation_loader._iterator is not None: validation_loader._iterator._shutdown_workers()
    del loader, validation_loader, model, optimizer, scheduler, queue
    torch.cuda.empty_cache()
    reproduction_command = [
        os.sys.executable, str(Path(__file__).with_name("validate_prototype_checkpoint.py")),
        "--checkpoint", best_checkpoint["path"], "--run-spec", str(run_spec_path),
        "--joint-config", str(joint_path), "--encoder-config", str(encoder_path),
        "--augmentation-config", str(augmentation_path), "--tensor-contract", str(Path(args.tensor_contract).resolve()),
        "--i19-manifest", str(i19_path),
    ]
    reproduction_process = subprocess.run(reproduction_command, check=True, capture_output=True, text=True)
    reproduction = json.loads(reproduction_process.stdout.splitlines()[-1])
    expected_reproduction = {key: progress["best"][key] for key in NEW_METRIC_KEYS}
    if reproduction != expected_reproduction: raise RuntimeError("fresh-process best validation reproduction mismatch")
    scientific_identity = {"plan_id": spec["plan_id"], "run_id": spec["run_id"], "parents": progress["parents"],
                           "run_spec_sha256": sha256_file(run_spec_path), "training_contract_sha256": sha256_file(training_config_path),
                           "joint_config_sha256": sha256_file(joint_path), "encoder_config_sha256": sha256_file(encoder_path),
                           "augmentation_config_sha256": sha256_file(augmentation_path),
                           "training_implementation_sha256": sha256_file(Path(__file__)),
                           "training_launcher_sha256": sha256_file(Path(__file__).with_name("run_prototype_training_locked.py")),
                           "materialization_implementation_sha256": sha256_file(Path(__file__).with_name("prototype_training_data.py")),
                           "seed": seed, "numerical_policy": "single_gpu_float32_no_tf32"}
    acceptance_id = "pta_" + hashlib.sha256(canonical_json_bytes(scientific_identity)).hexdigest()[:24]
    final_dir = immutable / acceptance_id; stage = Path(tempfile.mkdtemp(prefix=f".{acceptance_id}.stage-", dir=immutable.mkdir(parents=True, exist_ok=True) or immutable))
    validation_path = stage / training_config["output"]["validation_name"]; validation_path.write_bytes(canonical_json_bytes(progress["validation"]))
    qc = {"status": "PASS", "optimizer_step_performed": True, "worker_count": workers, "preflight": preflight, "exact_resume": exact_resume,
          "peak_allocated_vram_bytes": torch.cuda.max_memory_allocated(), "peak_reserved_vram_bytes": torch.cuda.max_memory_reserved(),
          "elapsed_seconds": time.time() - started, "checkpoint_count": len(checkpoint_records)}
    qc_path = stage / training_config["output"]["qc_name"]; qc_path.write_bytes(canonical_json_bytes(qc))
    outputs = [{"relative_path": path.name, "size_bytes": path.stat().st_size, "sha256": sha256_file(path)} for path in (qc_path, validation_path)]
    manifest = {"schema_version": "1.0.0", "status": "PASS", "training_acceptance_id": acceptance_id,
                "plan_id": spec["plan_id"], "run_id": spec["run_id"], "scientific_identity": scientific_identity,
                "completion": {"epochs_completed": progress["epoch"] + 1, "optimizer_steps": progress["optimizer_step"],
                               "training_scene_consumptions": progress["scene_consumptions"], "termination": termination},
                "validation_history": progress["validation"], "best_checkpoint": best_checkpoint,
                "final_checkpoint": final_checkpoint, "exact_resume": exact_resume, "resources": qc,
                "fresh_process_validation": reproduction,
                "outputs": outputs}
    jsonschema.validate(manifest, json.loads(Path(args.schema).read_text()))
    manifest_path = stage / training_config["output"]["manifest_name"]; manifest_path.write_bytes(canonical_json_bytes(manifest))
    if final_dir.exists():
        existing = json.loads((final_dir / manifest_path.name).read_text())
        if canonical_json_bytes(existing) != canonical_json_bytes(manifest): raise RuntimeError("same I21 ID has different content")
        shutil.rmtree(stage); publish = "identical_reuse"
    else: os.replace(stage, final_dir); publish = "new_publish"
    print(json.dumps({"status": "PASS", "training_acceptance_id": acceptance_id, "publish_status": publish,
                      "output_files": [str(final_dir / name) for name in (qc_path.name, validation_path.name, manifest_path.name)]}))


if __name__ == "__main__":
    main()
