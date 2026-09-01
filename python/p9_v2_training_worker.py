"""P9 v2 scientific worker: DDP updates, validation, staging, and exact restore.

This module contains no authority publication, ledger writer, acceptance, target,
or v1 control-plane dependency. Rank zero communicates with the sole controller.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import random
import resource
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import torch
import torch.distributed as dist
import yaml
from torch.nn.parallel import DistributedDataParallel

from canonical_config import load_strict_yaml
from p6_data import build_vocabulary, validate_vocabulary_contract
from p7_geometry_cache import GeometryCacheReader
from p7_training import (
    collate, derive_seed, empty_queue, enqueue, local_infonce_sum,
    modality_assignments, state_content_digest, to_device, training_batch_digest,
)
from p9_infrastructure import P9ExactScheduler, materialize_hyperparameter_configuration
from p9_model_families import (
    P9MomentumModel, ds_raster_from_batch, family_contract, p9_reconstruction_terms,
)
from p9_v2_canonical import (
    canonical_json_line, canonical_sha256, deterministic_id, parse_canonical_json,
)
from p9_v2_finalization import (
    evaluate_selection_candidate, make_selection_contract, qualifies_patience_reset,
)
from p9_v2_schema import SCHEMA_VERSION, validate_instance
from rotating_padding_sampler import logical_groups, rotating_padding_state


class ScienceWorkerError(RuntimeError):
    """Scientific execution or controller-protocol failure."""


def make_worker_request(message_type: str, body: dict[str, Any]) -> dict[str, Any]:
    """Create a protocol request without importing the control plane."""
    value = {"schema_version": SCHEMA_VERSION, "message_type": message_type,
             "request_id": deterministic_id("p9req_", {"message_type": message_type, "body": body}),
             "body": body}
    validate_instance("worker_ipc", value)
    return value


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


class ControllerClient:
    """Blocking rank-zero canonical line protocol; every request requires ACK."""

    def __init__(self, input_stream: Any = None, output_stream: Any = None):
        self.input = input_stream or sys.stdin.buffer
        self.output = output_stream or sys.stdout.buffer

    def request(self, message_type: str, body: dict[str, Any]) -> dict[str, Any]:
        request = make_worker_request(message_type, body)
        self.output.write(canonical_json_line(request)); self.output.flush()
        raw = self.input.readline()
        if not raw:
            raise ScienceWorkerError("CONTROLLER_ACK_EOF")
        response = parse_canonical_json(raw, json_line=True)
        validate_instance("worker_ipc", response)
        if response["request_id"] != request["request_id"]:
            raise ScienceWorkerError("CONTROLLER_ACK_REQUEST_MISMATCH")
        if response["message_type"] != "ACK" or response["body"]["status"] != "COMMITTED":
            raise ScienceWorkerError(f"CONTROLLER_NACK: {response['body']}")
        return response["body"]


class ProductionPreparedData:
    """Read the accepted fixed-index cache without directory discovery."""

    def __init__(self, root: str | Path, profile: str, logical_k: int):
        self.root = Path(root)
        plan = json.loads((self.root / "canonical_cache_plan.json").read_text(encoding="utf-8"))
        if int(plan["entry_count"]) != 78_672:
            raise ScienceWorkerError("PRODUCTION_CACHE_ENTRY_COUNT_MISMATCH")
        self.index: dict[tuple[str, str, int | None], dict[str, Any]] = {}
        for row in plan["entries"]:
            if row["role"] == "training" and row["profile"] != profile:
                continue
            key = (row["role"], row["scene_id"], row["view"])
            if key in self.index:
                raise ScienceWorkerError("DUPLICATE_PREPARED_VIEW")
            self.index[key] = row
        by_scene: dict[str, list[int]] = {}
        for role, scene, view in self.index:
            if role == "training":
                by_scene.setdefault(scene, []).append(int(view))
        self.views = {scene: tuple(sorted(values)[:logical_k]) for scene, values in by_scene.items()}
        if len(self.views) != 2_421 or any(len(values) != logical_k for values in self.views.values()):
            raise ScienceWorkerError("PRODUCTION_TRAINING_POPULATION_MISMATCH")
        self.training_scenes = sorted(self.views)
        self.validation_scenes = sorted({scene for role, scene, _ in self.index if role == "validation_gallery"})
        if len(self.validation_scenes) != 400:
            raise ScienceWorkerError("FIXED_VALIDATION_IDENTITY_MISMATCH")

    def sample(self, role: str, scene: str, view: int | None) -> dict[str, Any]:
        spec = self.index.get((role, scene, view))
        if spec is None:
            raise ScienceWorkerError("PREPARED_VIEW_MISSING")
        index = int(spec["global_index"])
        payload = torch.load(self.root / "prepared" / f"{index:06d}.pt", map_location="cpu", weights_only=False)
        if payload.get("spec") != spec or int(payload.get("global_index", -1)) != index:
            raise ScienceWorkerError("PREPARED_PAYLOAD_IDENTITY_MISMATCH")
        return payload["sample"]


@dataclass
class WorkerState:
    model: P9MomentumModel
    optimizer: torch.optim.Optimizer
    scheduler: P9ExactScheduler
    queue: dict[str, Any]
    training_trace: list[dict[str, Any]]
    validation_trace: list[dict[str, Any]]
    best: dict[str, Any] | None
    events_without_improvement: int
    next_schedule_index: int


def configure_process(config: dict[str, Any], rank: int) -> torch.device:
    os.environ["CUBLAS_WORKSPACE_CONFIG"] = config["numeric"]["cublas_workspace_config"]
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        os.environ[name] = "1"
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True, warn_only=False)
    torch.backends.cudnn.deterministic = True; torch.backends.cudnn.benchmark = False
    torch.backends.cuda.matmul.allow_tf32 = False; torch.backends.cudnn.allow_tf32 = False
    seed = int(config["training"]["root_seed"])
    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)
    torch.cuda.set_device(rank); torch.cuda.manual_seed(seed + rank)
    return torch.device("cuda", rank)


def all_gather_tensor(value: torch.Tensor) -> torch.Tensor:
    values = [torch.empty_like(value) for _ in range(dist.get_world_size())]
    dist.all_gather(values, value)
    return torch.cat(values)


def selected_pair(scene: str, available: tuple[int, ...], config: dict[str, Any], epoch: int) -> tuple[int, int]:
    generator = torch.Generator().manual_seed(derive_seed(
        config, "training-view-selection", epoch=epoch, global_rank=0,
        operation="two-views-without-replacement", scene_id=scene))
    order = torch.randperm(len(available), generator=generator).tolist()
    return available[order[0]], available[order[1]]


def load_worker_values(spec: Mapping[str, str]) -> dict[str, Any]:
    matrix = json.loads(Path(spec["matrix"]).read_text(encoding="utf-8"))
    row = next((item for item in matrix["rows"] if item["configuration_id"] == spec["configuration_id"]), None)
    if row is None or row.get("evaluation_ancestry") is not False:
        raise ScienceWorkerError("P8_CONFIGURATION_INVALID")
    base_training = yaml.safe_load(Path(spec["training_config"]).read_text(encoding="utf-8"))
    base_model = load_strict_yaml(spec["model_config"])
    routed = materialize_hyperparameter_configuration(row, base_training, base_model)
    routed["training"]["training"].update({"maximum_epochs": 200, "updates_per_epoch": 76, "maximum_updates": 15_200})
    config, model_config = routed["training"], routed["model"]
    data = ProductionPreparedData(spec["cache_root"], row["scientific"]["intensity"], row["scientific"]["effective_k"])
    vocabulary = build_vocabulary(spec["categories"])
    vocabulary_sizes = validate_vocabulary_contract(vocabulary)
    return {
        "row": row, "config": config, "model_config": model_config,
        "family": row.get("model_family", "FM"), "data": data,
        "vocabulary": vocabulary, "vocabulary_sizes": vocabulary_sizes,
        "vocabulary_masks": {field: int(contract["mask"]) for field, contract in vocabulary.items()},
        "geometry_cache": GeometryCacheReader(Path(spec["cache_root"]) / "geometry/geometry_cache_manifest.json", 4 * 1024**3),
    }


def create_state(values: dict[str, Any], device: torch.device) -> WorkerState:
    model = P9MomentumModel(values["model_config"], values["vocabulary_sizes"], values["family"]).to(device)
    optimizer = torch.optim.AdamW(
        [parameter for parameter in model.online.parameters() if parameter.requires_grad],
        lr=float(values["row"]["scientific"]["peak_learning_rate"]),
        weight_decay=float(values["config"]["optimizer"]["weight_decay"]),
        betas=tuple(values["config"]["optimizer"]["betas"]), eps=float(values["config"]["optimizer"]["eps"]),
    )
    scheduler = P9ExactScheduler(optimizer, float(values["row"]["scientific"]["peak_learning_rate"]))
    queue = empty_queue(device, capacity=int(values["config"]["queue"]["capacity"]),
                        dimension=int(values["model_config"]["model"]["d"]))
    return WorkerState(model, optimizer, scheduler, queue, [], [], None, 0, 0)


def _local_batches(values: dict[str, Any], epoch: int, batch_index: int, rank: int):
    sampler = rotating_padding_state(values["data"].training_scenes, int(values["config"]["training"]["root_seed"]), epoch - 1)
    groups = logical_groups(sampler, 32)
    if len(groups) != 76:
        raise ScienceWorkerError("SAMPLER_UPDATE_COUNT_MISMATCH")
    scenes = list(groups[batch_index]); local = scenes[rank * 16:(rank + 1) * 16]
    pairs = [selected_pair(scene, values["data"].views[scene], values["config"], epoch) for scene in local]
    batches = [collate([values["data"].sample("training", scene, pair[role])
                        for scene, pair in zip(local, pairs, strict=True)], values["vocabulary"])
               for role in range(2)]
    return batches, scenes, pairs


def training_update(ddp: DistributedDataParallel, state: WorkerState, values: dict[str, Any],
                    epoch: int, batch_index: int, rank: int, device: torch.device) -> dict[str, Any]:
    cpu, scenes, pairs = _local_batches(values, epoch, batch_index, rank)
    assignments = [modality_assignments(batch, values["config"], epoch, role, rank) for role, batch in enumerate(cpu)]
    ds_inputs = [ds_raster_from_batch(batch) if values["family"] == "DS" else None for batch in cpu]
    batches = [to_device(batch, device) for batch in cpu]
    geometries = [None if "geometry" not in family_contract(values["family"]).modalities else
                  values["geometry_cache"].batch(batch, "training", device) for batch in batches]
    ds_inputs = [item.to(device) if item is not None else None for item in ds_inputs]
    state.optimizer.zero_grad(set_to_none=True)
    outputs = [ddp(batch, geometry, ds, assignment) for batch, geometry, ds, assignment in
               zip(batches, geometries, ds_inputs, assignments, strict=True)]
    with torch.no_grad():
        targets = [state.model.target(batch, geometry, ds, None) for batch, geometry, ds in
                   zip(batches, geometries, ds_inputs, strict=True)]
    local_keys = torch.stack((targets[0]["contrastive_embedding"], targets[1]["contrastive_embedding"]), 1)
    gathered = all_gather_tensor(local_keys)
    centers = all_gather_tensor(batches[0]["scene_center_5186"])
    identifiers = all_gather_tensor(batches[0]["scene_numeric_ids"])
    scene_sum, scene_count = local_infonce_sum(
        outputs[0]["contrastive_embedding"], outputs[1]["contrastive_embedding"],
        gathered[:, 0], gathered[:, 1], batches[0]["scene_center_5186"], centers,
        batches[0]["scene_numeric_ids"], identifiers, state.queue,
        float(values["config"]["objective"]["contrastive_temperature"]),
        float(values["config"]["objective"]["negative_exclusion_distance_m"]))
    count = torch.tensor(scene_count, dtype=torch.int64, device=device); dist.all_reduce(count)
    scene_objective = scene_sum * dist.get_world_size() / int(count)
    reconstruction = [p9_reconstruction_terms(ddp.module, batch, geometry, output.get("modalities", {}),
                      values["vocabulary_masks"]) for batch, geometry, output in zip(batches, geometries, outputs, strict=True)]
    information = scene_sum * 0.0
    active = family_contract(values["family"]).ip_terms
    for name in active:
        numerator = reconstruction[0][name]["sum"] + reconstruction[1][name]["sum"]
        denominator = torch.tensor(sum(int(item[name]["count"]) for item in reconstruction), device=device)
        dist.all_reduce(denominator)
        information = information + numerator * dist.get_world_size() / int(denominator)
    if active:
        information = information / len(active)
    total = scene_objective + float(values["row"]["scientific"]["lambda_ip"]) * information
    if not torch.isfinite(total):
        raise FloatingPointError("SCIENTIFIC_DIVERGENCE")
    pairs_by_rank: list[Any] = [None] * dist.get_world_size(); dist.all_gather_object(pairs_by_rank, pairs)
    learning_rate = state.scheduler.set_for_next_update(); total.backward()
    parameters = [parameter for parameter in state.model.online.parameters() if parameter.requires_grad]
    if any(parameter.grad is None for parameter in parameters):
        raise ScienceWorkerError("UNUSED_ACTIVE_PARAMETER")
    norm = torch.nn.utils.clip_grad_norm_(parameters, 1.0, error_if_nonfinite=True)
    state.optimizer.step(); state.scheduler.advance()
    state.model.update_target(float(values["row"]["scientific"]["ema"]))
    enqueue(state.queue, gathered.reshape(-1, gathered.shape[-1]),
            all_gather_tensor(torch.stack((batches[0]["scene_numeric_ids"], batches[0]["scene_numeric_ids"]), 1)).reshape(-1),
            all_gather_tensor(torch.stack((batches[0]["scene_center_5186"], batches[0]["scene_center_5186"]), 1)).reshape(-1, 2))
    return {
        "epoch": epoch, "batch_index": batch_index, "global_update": state.scheduler.completed_updates,
        "learning_rate": learning_rate, "total_loss": float(total.detach()),
        "scene_loss": float(scene_objective.detach()), "gradient_norm": float(norm),
        "queue_pointer": int(state.queue["pointer"]), "queue_count": int(state.queue["valid_count"]),
        "batch_identity_digest": training_batch_digest(scenes, [item for group in pairs_by_rank for item in group]),
    }


def full_validation(state: WorkerState, values: dict[str, Any], device: torch.device,
                    rank: int, epoch: int) -> dict[str, Any]:
    state.model.online.eval()
    records = [("validation_query", scene, index) for scene in values["data"].validation_scenes for index in (0, 1)]
    records += [("validation_gallery", scene, None) for scene in values["data"].validation_scenes]
    vectors, indices = [], []
    with torch.inference_mode():
        for start in range(0, 1200, 8):
            if (start // 8) % 2 != rank: continue
            selected = records[start:start + 8]
            cpu = collate([values["data"].sample(*row) for row in selected], values["vocabulary"])
            ds = ds_raster_from_batch(cpu).to(device) if values["family"] == "DS" else None
            batch = to_device(cpu, device); role = selected[0][0]
            geometry = None if "geometry" not in family_contract(values["family"]).modalities else values["geometry_cache"].batch(batch, role, device)
            vectors.append(torch.nn.functional.normalize(state.model.online(batch, geometry, ds)["scene_embedding"], dim=1))
            indices.extend(range(start, start + len(selected)))
    vector = torch.cat(vectors); index = torch.tensor(indices, device=device, dtype=torch.int64)
    all_vectors = [torch.empty_like(vector) for _ in range(2)]; all_indices = [torch.empty_like(index) for _ in range(2)]
    dist.all_gather(all_vectors, vector); dist.all_gather(all_indices, index)
    combined_i = torch.cat(all_indices).cpu(); order = torch.argsort(combined_i)
    combined = torch.cat(all_vectors).cpu()[order]
    if combined_i[order].tolist() != list(range(1200)):
        raise ScienceWorkerError("VALIDATION_COVERAGE_MISMATCH")
    queries, galleries = combined[:800], combined[800:]; positive = torch.arange(400).repeat_interleave(2)
    similarities = queries @ galleries.T
    loss = torch.nn.functional.cross_entropy(similarities / float(values["config"]["objective"]["contrastive_temperature"]), positive)
    positive_values = similarities[torch.arange(800), positive]; masked = similarities.clone()
    masked[torch.arange(800), positive] = -torch.inf
    diagnostics = retrieval_rank_diagnostics(similarities, positive)
    result = {"completed_epoch": epoch, "validation_retrieval_loss": float(loss),
              "mean_source_separation_margin": float((positive_values - masked.max(1).values).mean()),
              **diagnostics,
              "query_count": 800, "gallery_count": 400, "evaluation_consumption_count": 0}
    shared = [result if rank == 0 else None]; dist.broadcast_object_list(shared, src=0)
    state.model.online.train(); return shared[0]


def retrieval_rank_diagnostics(similarities: torch.Tensor, positive: torch.Tensor) -> dict[str, float]:
    """Compute dissertation supplementary ranks without affecting selection."""
    order = torch.argsort(similarities, dim=1, descending=True, stable=True)
    ranks = torch.nonzero(order == positive[:, None], as_tuple=False)[:, 1] + 1
    if ranks.numel() != similarities.shape[0]:
        raise ScienceWorkerError("VALIDATION_RANK_COVERAGE_MISMATCH")
    rank_values = ranks.float()
    return {
        "MRR": float((1.0 / rank_values).mean()),
        "HIT@1": float((ranks <= 1).float().mean()),
        "HIT@5": float((ranks <= 5).float().mean()),
        "HIT@10": float((ranks <= 10).float().mean()),
    }


def bounded_validation(state: WorkerState, epoch: int) -> dict[str, Any]:
    """Noncanonical pilot metric from the latest bounded training observation."""
    latest = state.training_trace[-1]
    return {"completed_epoch": epoch, "validation_retrieval_loss": max(0.0, latest["total_loss"]),
            "mean_source_separation_margin": -latest["scene_loss"], "query_count": 0,
            "gallery_count": 0, "evaluation_consumption_count": 0}


def capture_rng(rank: int) -> dict[str, Any]:
    return {"rank": rank, "python": random.getstate(), "numpy": np.random.get_state(),
            "torch_cpu": torch.get_rng_state(), "torch_cuda": torch.cuda.get_rng_state(rank)}


def restore_rng(value: Mapping[str, Any], rank: int) -> None:
    random.setstate(value["python"]); np.random.set_state(value["numpy"])
    torch.set_rng_state(value["torch_cpu"].cpu()); torch.cuda.set_rng_state(value["torch_cuda"].cpu(), rank)


def scientific_state_digest(state: Mapping[str, Any]) -> str:
    keys = ("online_model", "ema_model", "optimizer", "scheduler", "queue", "sampler",
            "rng_states", "training_trace", "validation_trace", "early_stopping", "best_checkpoint",
            "progress", "world_size", "configuration_identity", "run_identity", "parent_identities")
    return state_content_digest({key: state[key] for key in keys})


def restore_checkpoint(path: str | Path, worker: WorkerState, rank: int, expected: Mapping[str, Any]) -> dict[str, Any]:
    checkpoint = torch.load(path, map_location=torch.device("cuda", rank), weights_only=False)
    for key, value in expected.items():
        if checkpoint.get(key) != value:
            raise ScienceWorkerError(f"RESUME_{key.upper()}_MISMATCH")
    worker.model.online.load_state_dict(checkpoint["online_model"])
    worker.model.target.load_state_dict(checkpoint["ema_model"])
    worker.optimizer.load_state_dict(checkpoint["optimizer"]); worker.scheduler.load_state_dict(checkpoint["scheduler"])
    for key in ("values", "scene_ids", "centers"):
        worker.queue[key].copy_(checkpoint["queue"][key].to(worker.queue[key].device))
    for key in ("pointer", "valid_count", "enqueue_count"):
        worker.queue[key] = int(checkpoint["queue"][key])
    worker.training_trace = checkpoint["training_trace"]
    worker.validation_trace = checkpoint["validation_trace"]
    worker.best = checkpoint["best_checkpoint"]
    worker.events_without_improvement = int(checkpoint["early_stopping"]["events_without_improvement"])
    worker.next_schedule_index = int(checkpoint["progress"]["next_schedule_index"])
    restore_rng(checkpoint["rng_states"][rank], rank)
    return checkpoint


def _broadcast_ack(rank: int, client: ControllerClient | None, message_type: str,
                   body: dict[str, Any]) -> dict[str, Any]:
    shared = [client.request(message_type, body) if rank == 0 else None]
    dist.broadcast_object_list(shared, src=0)
    if not isinstance(shared[0], dict): raise ScienceWorkerError("CONTROLLER_ACK_BROADCAST_INVALID")
    return shared[0]


def _event(rank: int, client: ControllerClient | None, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    return _broadcast_ack(rank, client, "EVENT_PROPOSAL", {
        "event_type": event_type, "occurred_at": utc_now(), "payload": payload,
        "writer_id": "science-rank0", "writer_role": "rank0",
    })


def _stage_checkpoint(state: WorkerState, values: dict[str, Any], rank: int, run_id: str,
                      authority: Mapping[str, Any], epoch: int, next_index: int,
                      staging_root: Path) -> tuple[Path | None, dict[str, Any] | None]:
    rank_rng = capture_rng(rank); gathered = [None, None] if rank == 0 else None
    dist.gather_object(rank_rng, gathered, dst=0)
    checkpoint = None; path = None
    if rank == 0:
        checkpoint = {
            "online_model": state.model.online.state_dict(), "ema_model": state.model.target.state_dict(),
            "optimizer": state.optimizer.state_dict(), "scheduler": state.scheduler.state_dict(), "scaler": None,
            "queue": state.queue, "sampler": {"epoch": epoch + 1, "cursor": 0}, "rng_states": gathered,
            "training_trace": state.training_trace, "validation_trace": state.validation_trace,
            "early_stopping": {"events_without_improvement": state.events_without_improvement},
            "best_checkpoint": state.best, "progress": {"completed_epoch": epoch, "resume_epoch": epoch + 1,
                "global_update": state.scheduler.completed_updates, "within_epoch_cursor": 0,
                "next_schedule_index": next_index},
            "world_size": 2, "configuration_identity": authority["content"]["scientific"]["configuration_hash"],
            "run_identity": run_id, "parent_identities": authority["content"]["parents"],
        }
        stage_id = "p9stage_" + canonical_sha256({"run_id": run_id, "completed_epoch": epoch,
                                                   "optimizer_update": state.scheduler.completed_updates})[:24]
        directory = staging_root / "requests" / stage_id; directory.mkdir(parents=True, exist_ok=True)
        path = directory / "checkpoint.pt"
        if path.exists():
            existing = torch.load(path, map_location="cpu", weights_only=False)
            if scientific_state_digest(existing) != scientific_state_digest(checkpoint):
                raise ScienceWorkerError("STAGING_CHECKPOINT_COLLISION")
        else:
            temporary = directory / "checkpoint.pt.incomplete"
            with temporary.open("xb") as stream:
                torch.save(checkpoint, stream); stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, path)
            descriptor = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try: os.fsync(descriptor)
            finally: os.close(descriptor)
    return path, checkpoint


def run_worker(spec: Mapping[str, str], authority: Mapping[str, Any], *, mode: str,
               pilot_schedule: tuple[tuple[int, int], ...] = ((5, 2), (10, 2)),
               stop_after_schedule_index: int | None = None) -> dict[str, Any]:
    rank = int(os.environ["RANK"]); world = int(os.environ["WORLD_SIZE"])
    if world != 2 or torch.cuda.device_count() != 2:
        raise ScienceWorkerError("WORKER_REQUIRES_TWO_GPUS")
    run_id = os.environ["P9_V2_RUN_ID"]
    staging_root = Path(os.environ["P9_V2_STAGING_ROOT"])
    client = ControllerClient() if rank == 0 else None
    values = load_worker_values(spec); device = configure_process(values["config"], rank)
    if (authority["content"]["scientific"]["configuration_id"] != spec["configuration_id"]
            or authority["content"]["scientific"]["p8_configuration_hash"] != values["row"]["scientific_hash"]):
        raise ScienceWorkerError("AUTHORITY_P8_CONFIGURATION_MISMATCH")
    dist.init_process_group("nccl", device_id=device)
    try:
        worker = create_state(values, device)
        ddp = DistributedDataParallel(worker.model.online, device_ids=[rank], output_device=rank,
                                      find_unused_parameters=False, bucket_cap_mb=50,
                                      gradient_as_bucket_view=False, static_graph=False)
        torch.cuda.manual_seed(int(values["config"]["training"]["root_seed"]) + rank)
        resume = os.environ.get("P9_V2_RESUME_CHECKPOINT", "")
        if resume:
            checkpoint = restore_checkpoint(resume, worker, rank, {
                "run_identity": run_id, "configuration_identity": authority["content"]["scientific"]["configuration_hash"],
                "parent_identities": authority["content"]["parents"], "world_size": 2})
            checkpoint_id = os.environ["P9_V2_RESUME_CHECKPOINT_ID"]
            if (worker.best is not None
                    and worker.best.get("completed_epoch") == checkpoint["progress"]["completed_epoch"]):
                worker.best["checkpoint_id"] = checkpoint_id
        schedule = (tuple((epoch, 76) for epoch in range(1, 201)) if mode == "formal" else pilot_schedule)
        selection = make_selection_contract()["content"]
        final_digest = None
        for schedule_index in range(worker.next_schedule_index, len(schedule)):
            epoch, updates = schedule[schedule_index]
            _event(rank, client, "EPOCH_STARTED", {"epoch": epoch,
                   "starting_optimizer_update": worker.scheduler.completed_updates, "sampler_cursor": 0})
            torch.cuda.reset_peak_memory_stats(device)
            first_update = worker.scheduler.completed_updates + 1; started = time.monotonic()
            update_walls: list[float] = []
            for batch_index in range(updates):
                update_started = time.monotonic()
                worker.training_trace.append(training_update(ddp, worker, values, epoch, batch_index, rank, device))
                torch.cuda.synchronize(device)
                update_walls.append(time.monotonic() - update_started)
            update_wall = time.monotonic() - started
            local_performance = {"rank": rank, "update_wall_seconds": update_wall,
                                 "update_wall_samples": update_walls,
                                 "peak_vram_bytes": int(torch.cuda.max_memory_allocated(device)),
                                 "peak_rss_bytes": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) * 1024}
            rank_performance = [None, None] if rank == 0 else None
            dist.gather_object(local_performance, rank_performance, dst=0)
            _event(rank, client, "PROGRESS_SUMMARY_COMMITTED", {
                "first_update": first_update, "last_update": worker.scheduler.completed_updates,
                "ending_epoch": epoch, "ending_sampler_cursor": updates,
                "trace_block_sha256": state_content_digest(worker.training_trace[first_update - 1:]),
                "sampler_state_sha256": canonical_sha256({"epoch": epoch, "cursor": updates}),
                "rng_state_sha256": state_content_digest(capture_rng(rank)),
                "queue_state_sha256": state_content_digest(worker.queue),
            })
            validation_due = mode != "formal" or epoch % int(selection["validation_interval_epochs"]) == 0
            if not validation_due:
                continue
            validation_started = time.monotonic()
            metric = full_validation(worker, values, device, rank, epoch) if mode == "formal" else bounded_validation(worker, epoch)
            torch.cuda.synchronize(device)
            validation_wall = time.monotonic() - validation_started
            previous = worker.best
            selected, basis = evaluate_selection_candidate(metric, previous, float(selection["equivalence_tolerance"]))
            reset = qualifies_patience_reset(metric, previous, float(selection["equivalence_tolerance"]))
            worker.events_without_improvement = 0 if reset else worker.events_without_improvement + 1
            candidate = {**metric, "selected_at_boundary": selected}
            if selected: worker.best = candidate
            worker.validation_trace.append(metric)
            path, checkpoint = _stage_checkpoint(worker, values, rank, run_id, authority, epoch,
                                                  schedule_index + 1, staging_root)
            stage_rel = None if path is None else path.relative_to(staging_root).as_posix()
            validation_id = "p9val_" + canonical_sha256({"run_id": run_id, **metric})[:24]
            request = {
                "staged_payload": stage_rel, "completed_epoch": epoch, "resume_epoch": epoch + 1,
                "optimizer_update": worker.scheduler.completed_updates, "validation_id": validation_id,
                "validation_retrieval_loss": metric["validation_retrieval_loss"],
                "mean_source_separation_margin": metric["mean_source_separation_margin"],
                "selector_state": {"best_checkpoint_id": None if previous is None else previous.get("checkpoint_id"),
                                   "events_without_improvement": worker.events_without_improvement},
                "current_candidate_selected": selected,
                "queue": {"count": int(worker.queue["valid_count"]), "pointer": int(worker.queue["pointer"]),
                          "enqueue_count": int(worker.queue["enqueue_count"]),
                          "state_sha256": state_content_digest(worker.queue)},
                "sampler": {"epoch": epoch + 1, "cursor": 0,
                            "state_sha256": canonical_sha256({"epoch": epoch + 1, "cursor": 0})},
                "state_presence": {"online_model": True, "ema_model": True, "optimizer": True,
                    "scheduler": True, "queue": True, "sampler": True, "rng_states": True,
                    "validation_trace": True, "training_trace": True, "early_stopping": True,
                    "best_checkpoint": True, "amp_scaler": None},
                "source_run_id": run_id, "occurred_at": utc_now(),
            }
            commit_started = time.monotonic()
            ack = _broadcast_ack(rank, client, "CHECKPOINT_COMMIT_REQUEST", request)
            checkpoint_wall = time.monotonic() - commit_started
            if selected:
                assert worker.best is not None; worker.best["checkpoint_id"] = ack["checkpoint_id"]
            _event(rank, client, "EARLY_STOPPING_UPDATED", {
                "selector_state": ack["selector_state"],
                "best_checkpoint_id": ack["selector_state"]["best_checkpoint_id"],
                "events_without_improvement": worker.events_without_improvement,
                "decision_basis": basis,
            })
            final_digest = scientific_state_digest(checkpoint) if checkpoint is not None else None
            if rank == 0:
                assert rank_performance is not None
                walls = [item["update_wall_seconds"] for item in rank_performance]
                update_samples = [value for item in rank_performance for value in item["update_wall_samples"]]
                diagnostic = {"schedule_index": schedule_index, "epoch": epoch, "optimizer_update": worker.scheduler.completed_updates,
                              "update_wall_seconds": max(walls),
                              "median_update_wall_seconds": statistics.median(update_samples),
                              "p95_update_wall_seconds": sorted(update_samples)[max(0, int(0.95 * len(update_samples)) - 1)],
                              "throughput_scenes_per_second": 32 * updates / max(walls),
                              "rank_wall_skew_seconds": max(walls) - min(walls),
                              "peak_vram_bytes": max(item["peak_vram_bytes"] for item in rank_performance),
                              "peak_rank_rss_bytes": max(item["peak_rss_bytes"] for item in rank_performance),
                              "validation_wall_seconds": validation_wall,
                              "checkpoint_commit_wall_seconds": checkpoint_wall,
                              "scientific_state_digest": final_digest,
                              "checkpoint_id": ack["checkpoint_id"], "evaluation_consumption_count": 0}
                diagnostics = staging_root / "diagnostics"; diagnostics.mkdir(exist_ok=True)
                (diagnostics / f"boundary-{epoch:04d}.json").write_text(json.dumps(diagnostic, sort_keys=True), encoding="utf-8")
            if stop_after_schedule_index == schedule_index:
                dist.barrier()
                return {"status": "INTERRUPT_AFTER_COMMITTED_CHECKPOINT", "optimizer_updates": worker.scheduler.completed_updates}
            if worker.events_without_improvement == int(selection["early_stopping_patience"]):
                reason = "EARLY_STOPPING_PATIENCE"
                break
        else:
            reason = "MAXIMUM_EPOCH"
        last = worker.validation_trace[-1]
        _event(rank, client, "TRAINING_COMPLETED", {
            "completed_epoch": last["completed_epoch"], "resume_epoch": last["completed_epoch"] + 1,
            "optimizer_update": worker.scheduler.completed_updates, "reason": reason})
        dist.barrier()
        return {"status": "COMPLETE", "optimizer_updates": worker.scheduler.completed_updates,
                "scientific_state_digest": final_digest}
    finally:
        dist.destroy_process_group()
