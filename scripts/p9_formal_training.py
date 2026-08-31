#!/usr/bin/env python3
"""Dedicated, authority-gated P9 formal DDP runner.

Unlike ``p9_bounded_main_pilot.py``, this entry point cannot run without an
immutable formal authority, reservation, execution-tree verification, and the
single-owner formal-attempt lock.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.distributed as dist
import yaml
from torch.nn.parallel import DistributedDataParallel

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "python"), str(ROOT / "scripts")]

from canonical_config import load_strict_yaml  # noqa: E402
from p6_data import build_vocabulary, validate_vocabulary_contract  # noqa: E402
from p7_geometry_cache import GeometryCacheReader  # noqa: E402
from p7_prototype_training import activate_rank_stochastic_seed, all_gather_tensor, configure_process, geometry  # noqa: E402
from p7_training import (collate, empty_queue, enqueue, local_infonce_sum, modality_assignments,
                         state_content_digest, to_device, training_batch_digest)  # noqa: E402
from p9_formal_execution import (FormalAttemptLock, SelectionState, atomic_json, digest, failed_state_payload,
                                 load_checkpoint, save_checkpoint_atomic, transition,
                                 terminal_acceptance_payload, validate_terminal_state_consistency,
                                 validate_validation_event, resolve_durable_progress,
                                 verify_execution_tree)  # noqa: E402
from p9_identity_diagnostics import assemble_rank_manifest  # noqa: E402
from p9_infrastructure import P9ExactScheduler, materialize_hyperparameter_configuration  # noqa: E402
from p9_model_families import P9MomentumModel, ds_raster_from_batch, family_contract, p9_reconstruction_terms  # noqa: E402
from rotating_padding_sampler import logical_groups, rotating_padding_state  # noqa: E402


def read_json(path: str | Path) -> dict[str, Any]: return json.loads(Path(path).read_text())


class ProductionPreparedData:
    """Read immutable prepared views by scientific identity, never completion order."""

    def __init__(self, cache_root: str | Path, profile: str, logical_k: int) -> None:
        self.root = Path(cache_root); plan = read_json(self.root / "canonical_cache_plan.json")
        if int(plan["entry_count"]) != 78672: raise ValueError("P9 production cache entry-count mismatch")
        rows = [row for row in plan["entries"] if row["role"] != "training" or row["profile"] == profile]
        self.index = {}
        for row in rows:
            key = (row["role"], row["scene_id"], row["view"])
            if key in self.index: raise ValueError("duplicate P9 prepared-view identity")
            self.index[key] = row
        self.profile, self.logical_k = profile, int(logical_k)
        by_scene: dict[str, list[int]] = {}
        for role, scene, view in self.index:
            if role == "training": by_scene.setdefault(scene, []).append(int(view))
        self.views = {scene: tuple(sorted(values)[:self.logical_k]) for scene, values in by_scene.items()}
        if len(self.views) != 2421 or any(len(value) != self.logical_k for value in self.views.values()):
            raise ValueError("P9 configured K/profile cache subset is incomplete")
        self.training_scenes = sorted(self.views)
        self.validation_scenes = sorted({scene for role, scene, _ in self.index if role == "validation_gallery"})
        if len(self.validation_scenes) != 400: raise ValueError("P9 validation cache population mismatch")

    def sample(self, role: str, scene: str, view: int | None) -> dict[str, Any]:
        key = (role, scene, view); spec = self.index.get(key)
        if spec is None: raise KeyError(f"missing production prepared view: {key}")
        index = int(spec["global_index"])
        payload = torch.load(self.root / "prepared" / f"{index:06d}.pt", map_location="cpu", weights_only=False)
        if int(payload.get("global_index", -1)) != index or payload.get("spec") != spec:
            raise ValueError("P9 fixed-index prepared payload mismatch")
        return payload["sample"]


def selected_pair(scene: str, available: tuple[int, ...], config: dict[str, Any], epoch: int) -> tuple[int, int]:
    from p7_training import derive_seed
    if len(available) < 2 or len(set(available)) != len(available): raise ValueError("invalid P9 logical view subset")
    generator = torch.Generator().manual_seed(derive_seed(config, "training-view-selection", epoch=epoch,
        global_rank=0, operation="two-views-without-replacement", scene_id=scene))
    order = torch.randperm(len(available), generator=generator).tolist()
    return available[order[0]], available[order[1]]


def load_values(args: argparse.Namespace, *, require_acceptance: bool = True) -> dict[str, Any]:
    authority, reservation = read_json(args.authority), read_json(args.reservation)
    if authority.get("status") != "PASS" or reservation.get("status") != "AUTHORIZED_NOT_STARTED":
        raise ValueError("P9 formal authority/reservation is not launchable")
    if reservation["formal_authority_id"] != authority["authority_id"]:
        raise ValueError("P9 reservation authority mismatch")
    tree = verify_execution_tree(ROOT, authority)
    if require_acceptance:
        accepted = read_json(args.authorization_acceptance)
        if (accepted.get("status") != "PASS" or
                accepted.get("authority_id") != authority["authority_id"] or
                accepted.get("reservation_id") != reservation["reservation_id"] or
                accepted.get("runtime_tree_sha256") != tree["runtime_tree_sha256"] or
                accepted.get("startup_gate", {}).get("status") != "PASS" or
                int(accepted.get("startup_gate", {}).get("optimizer_updates", -1)) != 0):
            raise ValueError("P9 startup-gated execution authorization acceptance mismatch")
    matrix = read_json(args.matrix); row = next((value for value in matrix["rows"]
                                                 if value["configuration_id"] == args.configuration_id), None)
    if row is None or row["scientific_hash"] != reservation["configuration_identity"]:
        raise ValueError("P9 reserved configuration does not match accepted matrix")
    base_training = yaml.safe_load((ROOT / "config/p7_deterministic_training.yml").read_text())
    base_model = load_strict_yaml(ROOT / "config/p6_model_dataloader.yml")
    routed = materialize_hyperparameter_configuration(row, base_training, base_model)
    routed["training"]["training"].update(authority["training_contract"]["trajectory"])
    routed["training"]["validation"] = authority["validation_contract"]
    cache = read_json(args.cache_acceptance)
    if cache["acceptance_id"] != authority["parents"]["production_cache_acceptance_id"]:
        raise ValueError("P9 production cache acceptance mismatch")
    family = row.get("model_family", "FM"); family_contract(family)
    data = ProductionPreparedData(args.cache_root, row["scientific"]["intensity"], row["scientific"]["effective_k"])
    vocabulary = build_vocabulary(args.categories)
    vocabulary_sizes = validate_vocabulary_contract(vocabulary)
    vocabulary_masks = {field: int(contract["mask"]) for field, contract in vocabulary.items()}
    return {"authority": authority, "reservation": reservation, "row": row, "tree": tree,
            "config": routed["training"], "model_config": routed["model"], "family": family,
            "data": data, "vocabulary": vocabulary, "vocabulary_sizes": vocabulary_sizes,
            "vocabulary_masks": vocabulary_masks}


def model_state(values: dict[str, Any], device: torch.device):
    sizes = validate_vocabulary_contract(values["vocabulary"])
    if sizes != values["vocabulary_sizes"]:
        raise ValueError("P9 canonical vocabulary size derivation changed after routing")
    model = P9MomentumModel(values["model_config"], sizes, values["family"]).to(device)
    parameters = [parameter for parameter in model.online.parameters() if parameter.requires_grad]
    optimizer = torch.optim.AdamW(parameters, lr=float(values["row"]["scientific"]["peak_learning_rate"]),
                                  weight_decay=float(values["config"]["optimizer"]["weight_decay"]))
    scheduler = P9ExactScheduler(optimizer, float(values["row"]["scientific"]["peak_learning_rate"]))
    queue_contract = values["config"].get("queue")
    if not isinstance(queue_contract, dict):
        raise ValueError("P9 queue contract is missing")
    capacity = queue_contract.get("capacity")
    dimension = queue_contract.get("embedding_dimension")
    if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity <= 0:
        raise ValueError("P9 queue capacity must be a positive integer")
    expected_dimension = int(values["model_config"]["model"]["d"])
    if dimension != expected_dimension:
        raise ValueError("P9 queue embedding dimension does not match the routed model dimension")
    queue = empty_queue(device, capacity=capacity, dimension=dimension)
    return model, optimizer, scheduler, queue


def local_batches(values: dict[str, Any], epoch: int, batch_index: int, rank: int):
    state = rotating_padding_state(values["data"].training_scenes,
                                   int(values["config"]["training"]["root_seed"]), epoch - 1)
    groups = logical_groups(state, 32)
    if len(groups) != 76: raise ValueError("P9 formal epoch does not contain 76 updates")
    global_scenes = list(groups[batch_index]); local = global_scenes[rank * 16:(rank + 1) * 16]
    pairs = [selected_pair(scene, values["data"].views[scene], values["config"], epoch) for scene in local]
    batches = [collate([values["data"].sample("training", scene, pair[role])
                        for scene, pair in zip(local, pairs, strict=True)], values["vocabulary"])
               for role in range(2)]
    return batches, global_scenes, pairs


def formal_update(ddp: DistributedDataParallel, model: P9MomentumModel, optimizer: Any,
                  scheduler: P9ExactScheduler, queue: dict[str, Any], values: dict[str, Any],
                  epoch: int, batch_index: int, rank: int, device: torch.device,
                  *, execute_update: bool = True) -> dict[str, Any]:
    started = time.monotonic(); cpu, scenes, pairs = local_batches(values, epoch, batch_index, rank)
    assignments = [modality_assignments(batch, values["config"], epoch, role, rank) for role, batch in enumerate(cpu)]
    ds_values = [ds_raster_from_batch(batch) if values["family"] == "DS" else None for batch in cpu]
    batches = [to_device(batch, device) for batch in cpu]
    geom_reader = values.get("geometry_cache")
    geometries = [None if "geometry" not in family_contract(values["family"]).modalities else
                  (geom_reader.batch(batch, "training", device) if geom_reader else geometry(batch, values["model_config"], device))
                  for batch in batches]
    ds_values = [value.to(device) if value is not None else None for value in ds_values]
    optimizer.zero_grad(set_to_none=True)
    outputs = [ddp(batch, geom, ds, assignment) for batch, geom, ds, assignment in
               zip(batches, geometries, ds_values, assignments, strict=True)]
    with torch.no_grad(): targets = [model.target(batch, geom, ds, None) for batch, geom, ds in
                                     zip(batches, geometries, ds_values, strict=True)]
    local_keys = torch.stack((targets[0]["contrastive_embedding"], targets[1]["contrastive_embedding"]), 1)
    gathered = all_gather_tensor(local_keys); centers = all_gather_tensor(batches[0]["scene_center_5186"])
    identifiers = all_gather_tensor(batches[0]["scene_numeric_ids"])
    diagnostic = dict(values.get("identity_diagnostic_context", {}))
    diagnostic.update({
        "epoch": epoch, "batch_index": batch_index,
        "intended_global_update": int(scheduler.completed_updates) + 1,
        "sampler": {"epoch": epoch - 1, "cursor": batch_index,
                    "root_seed": int(values["config"]["training"]["root_seed"]),
                    "global_batch_size": 32, "rank_local_indices": list(range(rank * 16, rank * 16 + 16)),
                    "padding_mode": "rotating_padding"},
        "local_scene_ids": scenes,
        "identity_domains": {"local_ids": "base_scene_sha256_63bit_legacy", "global_ids": "base_scene_sha256_63bit_legacy",
                             "queue_ids": "base_scene_sha256_63bit_legacy", "cache_entry": "physical_cache_entry"},
    })
    scene_sum, scene_count = local_infonce_sum(outputs[0]["contrastive_embedding"], outputs[1]["contrastive_embedding"],
        gathered[:, 0], gathered[:, 1], batches[0]["scene_center_5186"], centers,
        batches[0]["scene_numeric_ids"], identifiers, queue,
        float(values["config"]["objective"]["contrastive_temperature"]),
        float(values["config"]["objective"]["negative_exclusion_distance_m"]), diagnostic)
    count = torch.tensor(scene_count, dtype=torch.int64, device=device); dist.all_reduce(count)
    scene_objective = scene_sum * dist.get_world_size() / int(count)
    reconstruction = [p9_reconstruction_terms(ddp.module, batch, geom, output.get("modalities", {}),
                      values["vocabulary_masks"]) for batch, geom, output in zip(batches, geometries, outputs, strict=True)]
    ip = scene_sum * 0.0; ip_rows = {}
    for name in family_contract(values["family"]).ip_terms:
        numerator = reconstruction[0][name]["sum"] + reconstruction[1][name]["sum"]
        denominator = torch.tensor(sum(int(item[name]["count"]) for item in reconstruction), device=device)
        dist.all_reduce(denominator); global_sum = numerator.detach().clone(); dist.all_reduce(global_sum)
        ip = ip + numerator * dist.get_world_size() / int(denominator)
        ip_rows[name] = {"numerator": float(global_sum), "denominator": int(denominator)}
    if ip_rows: ip = ip / len(ip_rows)
    total = scene_objective + float(values["row"]["scientific"]["lambda_ip"]) * ip
    if not torch.isfinite(total): raise FloatingPointError("non-finite P9 formal loss")
    gathered_pairs = [None] * 2; dist.all_gather_object(gathered_pairs, pairs)
    if not execute_update:
        return {"epoch": epoch, "batch_index": batch_index, "global_update": scheduler.completed_updates,
                "learning_rate": float(optimizer.param_groups[0]["lr"]),
                "total_loss": float(total.detach()), "scene_loss": float(scene_objective.detach()),
                "weighted_ip_loss": float((float(values['row']['scientific']['lambda_ip']) * ip).detach()),
                "gradient_norm": None, "queue_pointer": int(queue["pointer"]),
                "queue_count": int(queue["valid_count"]), "batch_identity_digest": training_batch_digest(
                    scenes, [item for group in gathered_pairs for item in group]),
                "wall_seconds": time.monotonic() - started, "optimizer_update_executed": False}
    lr = scheduler.set_for_next_update(); total.backward()
    parameters = [value for value in model.online.parameters() if value.requires_grad]
    if any(value.grad is None for value in parameters): raise RuntimeError("unused active P9 parameter")
    norm = torch.nn.utils.clip_grad_norm_(parameters, 1.0, error_if_nonfinite=True)
    optimizer.step(); scheduler.advance(); model.update_target(float(values["row"]["scientific"]["ema"]))
    enqueue(queue, gathered.reshape(-1, gathered.shape[-1]),
            all_gather_tensor(torch.stack((batches[0]["scene_numeric_ids"], batches[0]["scene_numeric_ids"]), 1)).reshape(-1),
            all_gather_tensor(torch.stack((batches[0]["scene_center_5186"], batches[0]["scene_center_5186"]), 1)).reshape(-1, 2))
    return {"epoch": epoch, "batch_index": batch_index, "global_update": scheduler.completed_updates,
            "learning_rate": lr, "total_loss": float(total.detach()), "scene_loss": float(scene_objective.detach()),
            "weighted_ip_loss": float((float(values['row']['scientific']['lambda_ip']) * ip).detach()),
            "gradient_norm": float(norm), "queue_pointer": int(queue["pointer"]),
            "queue_count": int(queue["valid_count"]), "batch_identity_digest": training_batch_digest(
                scenes, [item for group in gathered_pairs for item in group]), "wall_seconds": time.monotonic() - started,
            "optimizer_update_executed": True}


def validation(model: P9MomentumModel, values: dict[str, Any], device: torch.device, rank: int, epoch: int) -> dict[str, Any]:
    model.online.eval(); records = [("validation_query", scene, index) for scene in values["data"].validation_scenes for index in (0, 1)]
    records += [("validation_gallery", scene, None) for scene in values["data"].validation_scenes]
    local_vectors, local_indices = [], []
    with torch.inference_mode():
        for start in range(0, 1200, 8):
            if (start // 8) % 2 != rank: continue
            selected = records[start:start + 8]; samples = [values["data"].sample(*row) for row in selected]
            cpu = collate(samples, values["vocabulary"]); ds = ds_raster_from_batch(cpu).to(device) if values["family"] == "DS" else None
            batch = to_device(cpu, device); role = selected[0][0]
            geom = None if "geometry" not in family_contract(values["family"]).modalities else values["geometry_cache"].batch(batch, role, device)
            local_vectors.append(torch.nn.functional.normalize(model.online(batch, geom, ds)["scene_embedding"], dim=1))
            local_indices.extend(range(start, start + len(selected)))
    vector = torch.cat(local_vectors); index = torch.tensor(local_indices, device=device, dtype=torch.int64)
    vectors = [torch.empty_like(vector) for _ in range(2)]; indices = [torch.empty_like(index) for _ in range(2)]
    dist.all_gather(vectors, vector); dist.all_gather(indices, index); combined_i = torch.cat(indices).cpu()
    order = torch.argsort(combined_i); combined = torch.cat(vectors).cpu()[order]
    if combined_i[order].tolist() != list(range(1200)): raise ValueError("P9 validation coverage mismatch")
    queries, galleries = combined[:800], combined[800:]; positive = torch.arange(400).repeat_interleave(2)
    similarities = queries @ galleries.T; loss = torch.nn.functional.cross_entropy(
        similarities / float(values["config"]["objective"]["contrastive_temperature"]), positive)
    positive_values = similarities[torch.arange(800), positive]; masked = similarities.clone()
    masked[torch.arange(800), positive] = -torch.inf
    event = {"epoch": epoch, "validation_retrieval_loss": float(loss),
             "mean_source_separation_margin": float((positive_values - masked.max(1).values).mean()),
             "query_count": 800, "gallery_count": 400, "missing_count": 0, "duplicate_count": 0,
             "evaluation_queries_consumed": 0, "embedding_sha256": state_content_digest(combined)}
    validate_validation_event(event); shared = [event if rank == 0 else None]; dist.broadcast_object_list(shared, src=0)
    model.online.train(); return shared[0]


def _training_body(args: argparse.Namespace, values: dict[str, Any], rank: int,
                   device: torch.device) -> None:
    model, optimizer, scheduler, queue = model_state(values, device)
    ddp = DistributedDataParallel(model.online, device_ids=[device.index], output_device=device.index,
                                  find_unused_parameters=False, bucket_cap_mb=50,
                                  gradient_as_bucket_view=False, static_graph=False)
    values["geometry_cache"] = GeometryCacheReader(
        Path(args.cache_root) / "geometry" / "geometry_cache_manifest.json", 4 * 1024**3)
    activate_rank_stochastic_seed(values["config"], rank); selector = SelectionState(4)
    trace, validations, manifests = [], [], []; start_epoch, start_batch = 1, 0
    lineage = {"authority_id": values["authority"]["authority_id"],
               "reservation_id": values["reservation"]["reservation_id"],
               "cache_acceptance_id": values["authority"]["parents"]["production_cache_acceptance_id"],
               "runtime_tree_sha256": values["tree"]["runtime_tree_sha256"]}
    values["identity_diagnostic_context"] = {
        "diagnostic_root": str(Path(args.output_root) / "identity_diagnostics"), "rank": rank,
        "local_rank": rank, "world_size": 2, "hostname": os.uname().nodename,
        "authority_id": lineage["authority_id"], "reservation_id": lineage["reservation_id"],
        "attempt_id": values["reservation"]["attempt_id"],
        "run_id": "p9run_" + digest({"attempt": values["reservation"]["attempt_id"], "launch": values["tree"]["actual_launch_commit"]})[:24],
        "runtime_tree_sha256": lineage["runtime_tree_sha256"], "actual_launch_commit": values["tree"]["actual_launch_commit"],
    }
    if args.resume:
        state = load_checkpoint(args.resume, lineage); model.online.load_state_dict(state["online_model"])
        model.target.load_state_dict(state["ema_model"]); optimizer.load_state_dict(state["optimizer"])
        scheduler.load_state_dict(state["scheduler"])
        for key in ("values", "scene_ids", "centers"): queue[key].copy_(state["queue"][key].to(device))
        for key in ("pointer", "valid_count", "enqueue_count"): queue[key] = int(state["queue"][key])
        trace, validations = state["training_trace"], state["validation_trace"]
        start_epoch, start_batch = state["progress"]["epoch"], state["progress"]["within_epoch_cursor"]
        rank_rng = state["rng_states"][rank]; random.setstate(rank_rng["python"]); np.random.set_state(rank_rng["numpy"])
        torch.set_rng_state(rank_rng["torch_cpu"]); torch.cuda.set_rng_state(rank_rng["torch_cuda"], rank)
    stop = False
    for epoch in range(start_epoch, int(values["config"]["training"]["maximum_epochs"]) + 1):
        for batch_index in range(start_batch if epoch == start_epoch else 0, 76):
            trace.append(formal_update(ddp, model, optimizer, scheduler, queue, values, epoch, batch_index, rank, device))
            if rank == 0:
                atomic_json(Path(args.output_root) / "worker_progress.json", {
                    "last_completed_epoch": epoch - 1 if batch_index < 75 else epoch,
                    "last_completed_update": int(scheduler.completed_updates), "optimizer_updates": int(scheduler.completed_updates),
                    "validation_events": len(validations), "checkpoint_count": len(manifests),
                    "queue_count": int(queue["valid_count"]), "queue_pointer": int(queue["pointer"]),
                    "last_durable_trace_position": trace[-1],
                })
        if epoch % int(values["authority"]["validation_contract"]["interval_epochs"]) == 0:
            event = validation(model, values, device, rank, epoch); decision = selector.update(event); validations.append(event)
            rank_state = {"rank": rank, "python": random.getstate(), "numpy": np.random.get_state(),
                          "torch_cpu": torch.get_rng_state(), "torch_cuda": torch.cuda.get_rng_state(rank)}
            gathered = [None, None] if rank == 0 else None; dist.gather_object(rank_state, gathered, dst=0)
            state = None if rank else {"online_model": model.online.state_dict(), "ema_model": model.target.state_dict(),
                "optimizer": optimizer.state_dict(), "scheduler": scheduler.state_dict(), "scaler": None,
                "progress": {"epoch": epoch + 1, "global_update": scheduler.completed_updates, "within_epoch_cursor": 0},
                "sampler": {"epoch": epoch + 1, "cursor": 0}, "rng_states": gathered, "queue": queue,
                "early_stopping": {"events_without_improvement": selector.events_without_improvement},
                "best_checkpoint": selector.best, "validation_trace": validations, "training_trace": trace,
                "lineage": lineage, "world_size": 2}
            manifest = save_checkpoint_atomic(Path(args.output_root) / "checkpoints" / f"epoch-{epoch:03d}", state) if rank == 0 else None
            shared = [manifest]; dist.broadcast_object_list(shared, src=0); manifests.append(shared[0])
            if decision["stop"]: stop = True; break
        if stop: break
    if rank == 0:
        atomic_json(Path(args.output_root) / "worker_result.json", {"formal_attempt": True,
            "runner_class": "P9_FORMAL", "state": "COMPLETED_PENDING_VALIDATION",
            "trace": trace, "validation_trace": validations, "checkpoint_manifests": manifests,
            "best": selector.best, "optimizer_updates": scheduler.completed_updates,
            "evaluation_queries_consumed": 0})
    dist.barrier()


def worker(args: argparse.Namespace) -> None:
    rank = int(os.environ["RANK"]); initialized = False; failure = None
    try:
        values = load_values(args)
        if int(os.environ["WORLD_SIZE"]) != 2: raise ValueError("P9 formal world size must be two")
        device = configure_process(values["config"], rank)
        dist.init_process_group("nccl", device_id=device); initialized = True
        _training_body(args, values, rank, device)
    except BaseException as error:
        trace = traceback.format_exc()
        failure = {"schema_version": "1.0.0", "rank": rank, "exit_code": 1,
                   "failure_stage": "FORMAL_WORKER_INITIALIZATION_OR_EXECUTION",
                   "failure_class": type(error).__name__,
                   "failure_message": " ".join(str(error).split())[:512],
                   "traceback_sha256": digest(trace), "process_group_cleanup_status": "PENDING"}
        raise
    finally:
        cleanup = "NOT_INITIALIZED"
        if initialized:
            try:
                dist.destroy_process_group(); cleanup = "CONFIRMED"
            except BaseException:
                cleanup = "FAILED"
        if failure is not None:
            failure["process_group_cleanup_status"] = cleanup
            atomic_json(Path(args.output_root) / f"rank_failure_{rank}.json", failure)


def startup_worker(args: argparse.Namespace) -> None:
    rank = int(os.environ["RANK"]); initialized = False; failure = None
    try:
        values = load_values(args, require_acceptance=False)
        if int(os.environ["WORLD_SIZE"]) != 2: raise ValueError("P9 startup gate world size must be two")
        device = configure_process(values["config"], rank)
        dist.init_process_group("nccl", device_id=device); initialized = True
        model, optimizer, scheduler, queue = model_state(values, device)
        ddp = DistributedDataParallel(model.online, device_ids=[device.index], output_device=device.index,
                                      find_unused_parameters=False, bucket_cap_mb=50,
                                      gradient_as_bucket_view=False, static_graph=False)
        values["geometry_cache"] = GeometryCacheReader(
            Path(args.cache_root) / "geometry" / "geometry_cache_manifest.json", 4 * 1024**3)
        activate_rank_stochastic_seed(values["config"], rank)
        before = {
            "online": state_content_digest(model.online.state_dict()),
            "ema": state_content_digest(model.target.state_dict()),
            "optimizer": state_content_digest(optimizer.state_dict()),
            "scheduler": state_content_digest(scheduler.state_dict()),
            "queue": state_content_digest(queue),
        }
        metrics = formal_update(ddp, model, optimizer, scheduler, queue, values, 1, 0, rank, device,
                                execute_update=False)
        after = {
            "online": state_content_digest(model.online.state_dict()),
            "ema": state_content_digest(model.target.state_dict()),
            "optimizer": state_content_digest(optimizer.state_dict()),
            "scheduler": state_content_digest(scheduler.state_dict()),
            "queue": state_content_digest(queue),
        }
        if before != after or scheduler.completed_updates != 0 or metrics["optimizer_update_executed"]:
            raise RuntimeError("P9 startup gate mutated scientific training state")
        result = {"schema_version": "1.0.0", "rank": rank, "status": "PASS",
                  "formal_attempt": False, "production_training_samples": 32,
                  "optimizer_updates": 0, "ema_updates": 0, "scheduler_steps": 0,
                  "checkpoint_publications": 0, "formal_validation_queries": 0,
                  "evaluation_queries_consumed": 0, "backward_passes": 0,
                  "loss": metrics["total_loss"], "batch_identity_digest": metrics["batch_identity_digest"],
                  "vocabulary_sizes": values["vocabulary_sizes"], "state_digests": after,
                  "process_group_cleanup_status": "PENDING"}
        dist.barrier()
    except BaseException as error:
        failure = {"schema_version": "1.0.0", "rank": rank, "status": "FAIL",
                   "failure_class": type(error).__name__, "failure_message": " ".join(str(error).split())[:512],
                   "traceback_sha256": digest(traceback.format_exc()), "optimizer_updates": 0,
                   "process_group_cleanup_status": "PENDING"}
        raise
    finally:
        cleanup = "NOT_INITIALIZED"
        if initialized:
            try:
                dist.destroy_process_group(); cleanup = "CONFIRMED"
            except BaseException:
                cleanup = "FAILED"
        payload = failure if failure is not None else result
        payload["process_group_cleanup_status"] = cleanup
        atomic_json(Path(args.output_root) / f"startup_rank_{rank}.json", payload)


def startup_controller(args: argparse.Namespace) -> None:
    values = load_values(args, require_acceptance=False)
    output = Path(args.output_root)
    output.mkdir(parents=True, exist_ok=False)
    command = [sys.executable, "-m", "torch.distributed.run", "--standalone", "--nproc_per_node=2",
               str(Path(__file__).resolve()), "startup-worker", *forwarded(args, include_acceptance=False)]
    started = time.time(); result = subprocess.run(command, cwd=ROOT, env=formal_launch_environment(values))
    rows = [read_json(output / f"startup_rank_{rank}.json") for rank in range(2)
            if (output / f"startup_rank_{rank}.json").is_file()]
    if result.returncode or len(rows) != 2 or any(row.get("status") != "PASS" for row in rows):
        raise RuntimeError("P9 production-shaped startup gate failed")
    if any(row.get("process_group_cleanup_status") != "CONFIRMED" for row in rows):
        raise RuntimeError("P9 startup gate did not cleanly destroy every process group")
    payload = {"schema_version": "1.0.0", "artifact_type": "p9_production_startup_gate_evidence",
               "status": "PASS", "formal_attempt": False,
               "authority_id": values["authority"]["authority_id"],
               "reservation_id": values["reservation"]["reservation_id"],
               "runtime_tree_sha256": values["tree"]["runtime_tree_sha256"],
               "production_cache_acceptance_id": values["authority"]["parents"]["production_cache_acceptance_id"],
               "configuration_identity": values["reservation"]["configuration_identity"],
               "world_size": 2, "rank_results": rows, "optimizer_updates": 0,
               "parameter_mutations": 0, "ema_updates": 0, "scheduler_steps": 0,
               "checkpoint_publications": 0, "formal_attempt_starts": 0,
               "formal_validation_queries": 0, "evaluation_queries_consumed": 0,
               "backward_passes": 0, "gpu_executions": 1,
               "started_unix": started, "completed_unix": time.time()}
    payload["content_sha256"] = digest(payload)
    payload["startup_gate_id"] = "p9sg_" + payload["content_sha256"][:24]
    atomic_json(output / "startup_gate_evidence.json", payload)


def _rank_failures(output: Path, launcher_exit: int) -> tuple[dict[str, int], str, str, str]:
    rows = [read_json(path) for path in sorted(output.glob("rank_failure_*.json"))]
    codes = {f"rank_{row['rank']}": int(row["exit_code"]) for row in rows}
    if not codes:
        codes = {"launcher": int(launcher_exit)}
    stages = sorted({row.get("failure_stage", "DDP_LAUNCHER") for row in rows})
    classes = sorted({row.get("failure_class", "ChildProcessError") for row in rows})
    messages = sorted({row.get("failure_message", "P9 formal DDP worker failed") for row in rows})
    traces = sorted(row.get("traceback_sha256", "") for row in rows)
    return codes, "+".join(stages), "+".join(classes), "; ".join(messages) + " [" + digest(traces) + "]"


def controller(args: argparse.Namespace) -> None:
    values = load_values(args); reservation = values["reservation"]
    token = os.environ.get("FUSE_P9_FORMAL_RESERVATION_ID", "")
    if token != reservation["reservation_id"]: raise PermissionError("explicit corrected P9 reservation token required")
    identity = {"duplicate_key": reservation["duplicate_key"], "attempt_id": reservation["attempt_id"],
                "reservation_id": reservation["reservation_id"], "authority_id": values["authority"]["authority_id"],
                "run_id": "p9run_" + digest({"attempt": reservation["attempt_id"], "launch": values["tree"]["actual_launch_commit"]})[:24],
                "actual_launch_commit": values["tree"]["actual_launch_commit"],
                "runtime_tree_sha256": values["tree"]["runtime_tree_sha256"], "world_size": 2}
    lock = FormalAttemptLock(Path(args.lock_root), identity); lock.acquire(); lock.heartbeat("STARTING")
    output = Path(args.output_root); output.mkdir(parents=True, exist_ok=False)
    started = time.time()
    atomic_json(output / "attempt_state.json", {"schema_version": "2.0.0", **identity, "state": "STARTING"})
    stop = threading.Event()
    heartbeat = threading.Thread(target=lambda: _heartbeat_loop(lock, stop), daemon=True); heartbeat.start()
    command = [sys.executable, "-m", "torch.distributed.run", "--standalone", "--nproc_per_node=2",
               str(Path(__file__).resolve()), "worker", *forwarded(args)]
    try:
        atomic_json(output / "attempt_state.json", {"schema_version": "2.0.0", **identity, "state": transition("STARTING", "RUNNING")})
        lock.heartbeat("RUNNING"); result = subprocess.run(command, cwd=ROOT,
                                                            env=formal_launch_environment(values))
        if result.returncode: raise RuntimeError("P9 formal DDP worker failed")
        worker_result = read_json(output / "worker_result.json")
        if not worker_result.get("validation_trace") or not worker_result.get("best"):
            raise RuntimeError("P9 formal worker produced no selectable validation evidence")
        selected_epoch = int(worker_result["best"]["epoch"]); candidates = worker_result["checkpoint_manifests"]
        # A checkpoint is written after validation and records the *next* epoch
        # as its resume cursor.  Match the canonical validation event rather
        # than conflating that cursor with the validation epoch.
        matches = [row for row in candidates if int(row["epoch"]) - 1 == selected_epoch]
        if len(matches) > 1:
            raise RuntimeError("P9 best validation maps to multiple checkpoint candidates")
        selected = matches[0] if matches else None
        if selected is None: raise RuntimeError("P9 best validation has no checkpoint candidate")
        run = {"schema_version": "1.0.0", "formal_attempt": True, "runner_class": "P9_FORMAL",
               "run_id": identity["run_id"], "attempt_id": identity["attempt_id"],
               "parents": {"authority_id": identity["authority_id"], "reservation_id": identity["reservation_id"],
                           "production_cache_acceptance_id": values["authority"]["parents"]["production_cache_acceptance_id"]},
               "actual_launch_commit": identity["actual_launch_commit"],
               "runtime_tree_sha256": identity["runtime_tree_sha256"],
               "optimizer_updates": int(worker_result["optimizer_updates"]), "evaluation_queries_consumed": 0}
        execution = {"schema_version": "1.0.0", **identity, "state": "COMPLETED_PENDING_VALIDATION",
                     "checkpoint_ids": [row["checkpoint_id"] for row in candidates],
                     "worker_result": str(output / "worker_result.json")}
        selected_value = {**selected, "selected_from_epoch": selected_epoch,
                          "validation_retrieval_loss": worker_result["best"]["validation_retrieval_loss"],
                          "mean_source_separation_margin": worker_result["best"]["mean_source_separation_margin"]}
        acceptance = terminal_acceptance_payload(run, selected_value, execution)
        atomic_json(output / "formal_run.json", run)
        atomic_json(output / "validation_trace.json", {"schema_version": "1.0.0", "run_id": identity["run_id"],
                    "events": worker_result["validation_trace"], "evaluation_queries_consumed": 0})
        atomic_json(output / "checkpoint_candidate_index.json", {"schema_version": "1.0.0",
                    "run_id": identity["run_id"], "candidates": candidates})
        atomic_json(output / "selected_checkpoint.json", selected_value)
        atomic_json(output / "terminal_execution_record.json", execution)
        atomic_json(output / "cfg_main_attempt_acceptance.json", acceptance)
        lock.release_terminal("ACCEPTED")
    except BaseException as error:
        launcher = result.returncode if "result" in locals() else 1
        codes, stage, failure_class, message = _rank_failures(output, launcher)
        diagnostic_root = output / "identity_diagnostics"
        if diagnostic_root.is_dir():
            try:
                assemble_rank_manifest(diagnostic_root, 2)
            except BaseException:
                pass
        terminal = failed_state_payload(identity, failure_stage=stage, failure_class=failure_class,
            failure_message=message or str(error), traceback_sha256=digest(traceback.format_exc()),
            rank_exit_codes=codes, started_unix=started,
            progress=resolve_durable_progress(output),
            process_group_cleanup="CONFIRMED" if not list(output.glob("rank_failure_*.json")) or all(
                read_json(path).get("process_group_cleanup_status") == "CONFIRMED"
                for path in output.glob("rank_failure_*.json")) else "FAILED")
        atomic_json(output / "attempt_state.json", terminal)
        atomic_json(output / "terminal_failure.json", terminal)
        lock.heartbeat("FAILED_NONRESUMABLE"); lock.release_terminal("FAILED_NONRESUMABLE")
        terminal["lock_release_status"] = "RELEASED"
        atomic_json(output / "attempt_state.json", terminal); atomic_json(output / "terminal_failure.json", terminal)
        validate_terminal_state_consistency(terminal, read_json(lock.owner_path), read_json(lock.heartbeat_path))
        raise
    finally:
        stop.set(); heartbeat.join(timeout=2)


def _heartbeat_loop(lock: FormalAttemptLock, stop: threading.Event) -> None:
    while not stop.wait(30): lock.heartbeat("RUNNING")


def formal_launch_environment(values: dict[str, Any]) -> dict[str, str]:
    """Apply the accepted P7 two-GPU transport and native-thread contract."""
    runtime = values["config"].get("runtime", {})
    gpu_indices = runtime.get("selected_gpu_indices")
    if gpu_indices != [0, 1]:
        raise ValueError("P9 formal runtime requires accepted GPU indices [0, 1]")
    if runtime.get("nccl_p2p_disable") is not True or runtime.get("nccl_ib_disable") is not True:
        raise ValueError("P9 formal runtime requires accepted NCCL transport safeguards")
    environment = os.environ.copy()
    environment.update({
        "CUDA_VISIBLE_DEVICES": "0,1",
        "NCCL_P2P_DISABLE": "1",
        "NCCL_IB_DISABLE": "1",
        "TORCH_NCCL_BLOCKING_WAIT": "1",
        "CUBLAS_WORKSPACE_CONFIG": values["config"]["numeric"]["cublas_workspace_config"],
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "BLIS_NUM_THREADS",
                 "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS", "GDAL_NUM_THREADS", "ARROW_NUM_THREADS"):
        environment[name] = "1"
    return environment


def forwarded(args: argparse.Namespace, *, include_acceptance: bool = True) -> list[str]:
    result = []
    for name in ("authority", "reservation", "matrix", "cache_acceptance", "cache_root", "categories", "output_root"):
        result.extend(["--" + name.replace("_", "-"), str(getattr(args, name))])
    if include_acceptance:
        result.extend(["--authorization-acceptance", str(args.authorization_acceptance)])
    result.extend(["--configuration-id", args.configuration_id])
    if args.resume: result.extend(["--resume", args.resume])
    return result


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(); value.add_argument("mode", choices=(
        "validate", "controller", "worker", "startup-controller", "startup-worker"))
    for name in ("authority", "reservation", "matrix", "cache-acceptance", "cache-root", "categories", "output-root"):
        value.add_argument("--" + name, required=True)
    value.add_argument("--authorization-acceptance", default="")
    value.add_argument("--configuration-id", required=True); value.add_argument("--lock-root", default="")
    value.add_argument("--resume", default=""); return value


def main() -> None:
    args = parser().parse_args()
    if args.mode == "validate":
        values = load_values(args); print(json.dumps({"status": "PASS", "formal_attempt": True,
            "authority_id": values["authority"]["authority_id"], "reservation_id": values["reservation"]["reservation_id"],
            "runtime_tree_sha256": values["tree"]["runtime_tree_sha256"]}, sort_keys=True))
    elif args.mode == "controller": controller(args)
    elif args.mode == "worker": worker(args)
    elif args.mode == "startup-controller": startup_controller(args)
    else: startup_worker(args)


if __name__ == "__main__": main()
