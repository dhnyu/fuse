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
from p6_data import build_vocabulary  # noqa: E402
from p7_geometry_cache import GeometryCacheReader  # noqa: E402
from p7_prototype_training import activate_rank_stochastic_seed, all_gather_tensor, configure_process, geometry  # noqa: E402
from p7_training import (collate, empty_queue, enqueue, local_infonce_sum, modality_assignments,
                         state_content_digest, to_device, training_batch_digest)  # noqa: E402
from p9_formal_execution import (FormalAttemptLock, SelectionState, atomic_json, digest,
                                 load_checkpoint, save_checkpoint_atomic, transition,
                                 terminal_acceptance_payload, validate_validation_event,
                                 verify_execution_tree)  # noqa: E402
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
            self.index[key] = int(row["global_index"])
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
        key = (role, scene, view); index = self.index.get(key)
        if index is None: raise KeyError(f"missing production prepared view: {key}")
        payload = torch.load(self.root / "prepared" / f"{index:06d}.pt", map_location="cpu", weights_only=False)
        if int(payload["index"]) != index: raise ValueError("P9 fixed-index prepared payload mismatch")
        return payload["sample"]


def selected_pair(scene: str, available: tuple[int, ...], config: dict[str, Any], epoch: int) -> tuple[int, int]:
    from p7_training import derive_seed
    if len(available) < 2 or len(set(available)) != len(available): raise ValueError("invalid P9 logical view subset")
    generator = torch.Generator().manual_seed(derive_seed(config, "training-view-selection", epoch=epoch,
        global_rank=0, operation="two-views-without-replacement", scene_id=scene))
    order = torch.randperm(len(available), generator=generator).tolist()
    return available[order[0]], available[order[1]]


def load_values(args: argparse.Namespace) -> dict[str, Any]:
    authority, reservation = read_json(args.authority), read_json(args.reservation)
    if authority.get("status") != "PASS" or reservation.get("status") != "AUTHORIZED_NOT_STARTED":
        raise ValueError("P9 formal authority/reservation is not launchable")
    if reservation["formal_authority_id"] != authority["authority_id"]:
        raise ValueError("P9 reservation authority mismatch")
    tree = verify_execution_tree(ROOT, authority)
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
    return {"authority": authority, "reservation": reservation, "row": row, "tree": tree,
            "config": routed["training"], "model_config": routed["model"], "family": family,
            "data": data, "vocabulary": build_vocabulary(args.categories)}


def model_state(values: dict[str, Any], device: torch.device):
    sizes = {key: len(value["values"]) + 1 for key, value in values["vocabulary"]["fields"].items()}
    model = P9MomentumModel(values["model_config"], sizes, values["family"]).to(device)
    parameters = [parameter for parameter in model.online.parameters() if parameter.requires_grad]
    optimizer = torch.optim.AdamW(parameters, lr=float(values["row"]["scientific"]["peak_learning_rate"]),
                                  weight_decay=float(values["config"]["optimizer"]["weight_decay"]))
    scheduler = P9ExactScheduler(optimizer, float(values["row"]["scientific"]["peak_learning_rate"]))
    queue = empty_queue(values["config"], device)
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
                  epoch: int, batch_index: int, rank: int, device: torch.device) -> dict[str, Any]:
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
    scene_sum, scene_count = local_infonce_sum(outputs[0]["contrastive_embedding"], outputs[1]["contrastive_embedding"],
        gathered[:, 0], gathered[:, 1], batches[0]["scene_center_5186"], centers,
        batches[0]["scene_numeric_ids"], identifiers, queue,
        float(values["config"]["objective"]["contrastive_temperature"]),
        float(values["config"]["objective"]["negative_exclusion_distance_m"]))
    count = torch.tensor(scene_count, dtype=torch.int64, device=device); dist.all_reduce(count)
    scene_objective = scene_sum * dist.get_world_size() / int(count)
    reconstruction = [p9_reconstruction_terms(ddp.module, batch, geom, output.get("modalities", {}),
                      values["vocabulary"]["masks"]) for batch, geom, output in zip(batches, geometries, outputs, strict=True)]
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
    lr = scheduler.set_for_next_update(); total.backward()
    parameters = [value for value in model.online.parameters() if value.requires_grad]
    if any(value.grad is None for value in parameters): raise RuntimeError("unused active P9 parameter")
    norm = torch.nn.utils.clip_grad_norm_(parameters, 1.0, error_if_nonfinite=True)
    optimizer.step(); scheduler.advance(); model.update_target(float(values["row"]["scientific"]["ema"]))
    enqueue(queue, gathered.reshape(-1, gathered.shape[-1]),
            all_gather_tensor(torch.stack((batches[0]["scene_numeric_ids"], batches[0]["scene_numeric_ids"]), 1)).reshape(-1),
            all_gather_tensor(torch.stack((batches[0]["scene_center_5186"], batches[0]["scene_center_5186"]), 1)).reshape(-1, 2))
    gathered_pairs = [None] * 2; dist.all_gather_object(gathered_pairs, pairs)
    return {"epoch": epoch, "batch_index": batch_index, "global_update": scheduler.completed_updates,
            "learning_rate": lr, "total_loss": float(total.detach()), "scene_loss": float(scene_objective.detach()),
            "weighted_ip_loss": float((float(values['row']['scientific']['lambda_ip']) * ip).detach()),
            "gradient_norm": float(norm), "queue_pointer": int(queue["pointer"]),
            "queue_count": int(queue["valid_count"]), "batch_identity_digest": training_batch_digest(
                scenes, [item for group in gathered_pairs for item in group]), "wall_seconds": time.monotonic() - started}


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


def worker(args: argparse.Namespace) -> None:
    values = load_values(args); rank = int(os.environ["RANK"])
    if int(os.environ["WORLD_SIZE"]) != 2: raise ValueError("P9 formal world size must be two")
    device = configure_process(values["config"], rank); dist.init_process_group("nccl")
    model, optimizer, scheduler, queue = model_state(values, device)
    ddp = DistributedDataParallel(model.online, device_ids=[device.index], output_device=device.index,
                                  find_unused_parameters=False, bucket_cap_mb=50,
                                  gradient_as_bucket_view=False, static_graph=False)
    values["geometry_cache"] = GeometryCacheReader(Path(args.cache_root) / "geometry", 4 * 1024**3)
    activate_rank_stochastic_seed(values["config"], rank); selector = SelectionState(4)
    trace, validations, manifests = [], [], []; start_epoch, start_batch = 1, 0
    lineage = {"authority_id": values["authority"]["authority_id"],
               "reservation_id": values["reservation"]["reservation_id"],
               "cache_acceptance_id": values["authority"]["parents"]["production_cache_acceptance_id"],
               "runtime_tree_sha256": values["tree"]["runtime_tree_sha256"]}
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
    dist.barrier(); dist.destroy_process_group()


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
    atomic_json(output / "running_state.json", {"schema_version": "1.0.0", **identity, "state": "STARTING"})
    stop = threading.Event()
    heartbeat = threading.Thread(target=lambda: _heartbeat_loop(lock, stop), daemon=True); heartbeat.start()
    command = [sys.executable, "-m", "torch.distributed.run", "--standalone", "--nproc_per_node=2",
               str(Path(__file__).resolve()), "worker", *forwarded(args)]
    try:
        atomic_json(output / "running_state.json", {"schema_version": "1.0.0", **identity, "state": transition("STARTING", "RUNNING")})
        lock.heartbeat("RUNNING"); result = subprocess.run(command, cwd=ROOT)
        if result.returncode: raise RuntimeError("P9 formal DDP worker failed")
        worker_result = read_json(output / "worker_result.json")
        if not worker_result.get("validation_trace") or not worker_result.get("best"):
            raise RuntimeError("P9 formal worker produced no selectable validation evidence")
        selected_epoch = int(worker_result["best"]["epoch"]); candidates = worker_result["checkpoint_manifests"]
        selected = next((row for row in candidates if int(row["epoch"]) == selected_epoch), None)
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
    except BaseException:
        lock.heartbeat("FAILED_NONRESUMABLE"); lock.release_terminal("FAILED_NONRESUMABLE"); raise
    finally:
        stop.set(); heartbeat.join(timeout=2)


def _heartbeat_loop(lock: FormalAttemptLock, stop: threading.Event) -> None:
    while not stop.wait(30): lock.heartbeat("RUNNING")


def forwarded(args: argparse.Namespace) -> list[str]:
    result = []
    for name in ("authority", "reservation", "matrix", "cache_acceptance", "cache_root", "categories", "output_root"):
        result.extend(["--" + name.replace("_", "-"), str(getattr(args, name))])
    result.extend(["--configuration-id", args.configuration_id])
    if args.resume: result.extend(["--resume", args.resume])
    return result


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(); value.add_argument("mode", choices=("validate", "controller", "worker"))
    for name in ("authority", "reservation", "matrix", "cache-acceptance", "cache-root", "categories", "output-root"):
        value.add_argument("--" + name, required=True)
    value.add_argument("--configuration-id", required=True); value.add_argument("--lock-root", default="")
    value.add_argument("--resume", default=""); return value


def main() -> None:
    args = parser().parse_args()
    if args.mode == "validate":
        values = load_values(args); print(json.dumps({"status": "PASS", "formal_attempt": True,
            "authority_id": values["authority"]["authority_id"], "reservation_id": values["reservation"]["reservation_id"],
            "runtime_tree_sha256": values["tree"]["runtime_tree_sha256"]}, sort_keys=True))
    elif args.mode == "controller": controller(args)
    else: worker(args)


if __name__ == "__main__": main()
