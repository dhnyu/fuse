"""Production-shaped P9 v2 science-plane pilot with a hard zero-update contract."""

from __future__ import annotations

import json
import os
import socket
from pathlib import Path
from typing import Any

import torch
import torch.distributed as dist
import torch.multiprocessing as mp
import yaml
from torch.nn.parallel import DistributedDataParallel

from canonical_config import load_strict_yaml
from p6_data import build_vocabulary, validate_vocabulary_contract
from p7_geometry_cache import GeometryCacheReader
from p7_training import collate, empty_queue, local_infonce_sum, state_content_digest, to_device
from p9_infrastructure import P9ExactScheduler, materialize_hyperparameter_configuration
from p9_model_families import P9MomentumModel
from p9_v2_prepared_cache import ProductionPreparedData
from p9_v2_schema import validate_instance
from rotating_padding_sampler import logical_groups, rotating_padding_state


class PilotContractError(RuntimeError):
    pass


def selected_pair(scene: str, available: tuple[int, ...], config: dict[str, Any]) -> tuple[int, int]:
    from p7_training import derive_seed
    generator = torch.Generator().manual_seed(derive_seed(
        config, "training-view-selection", epoch=1, global_rank=0,
        operation="two-views-without-replacement", scene_id=scene))
    order = torch.randperm(len(available), generator=generator).tolist()
    return available[order[0]], available[order[1]]


def _gather(value: torch.Tensor) -> torch.Tensor:
    values = [torch.empty_like(value) for _ in range(dist.get_world_size())]
    dist.all_gather(values, value)
    return torch.cat(values)


def _state_digest(model: P9MomentumModel, optimizer: torch.optim.Optimizer,
                  scheduler: P9ExactScheduler, queue: dict[str, Any]) -> str:
    return state_content_digest({
        "online": model.online.state_dict(), "ema": model.target.state_dict(),
        "optimizer": optimizer.state_dict(), "scheduler": scheduler.state_dict(), "queue": queue,
    })


def _rank(rank: int, world_size: int, port: int, spec: dict[str, str], output: str) -> None:
    os.environ.update({
        "MASTER_ADDR": "127.0.0.1", "MASTER_PORT": str(port), "NCCL_P2P_DISABLE": "1",
        "NCCL_IB_DISABLE": "1", "TORCH_NCCL_BLOCKING_WAIT": "1", "CUBLAS_WORKSPACE_CONFIG": ":4096:8",
    })
    torch.set_num_threads(1); torch.cuda.set_device(rank)
    torch.manual_seed(20260828); torch.cuda.manual_seed(20260828)
    torch.backends.cuda.matmul.allow_tf32 = False; torch.backends.cudnn.allow_tf32 = False
    torch.backends.cudnn.benchmark = False; torch.backends.cudnn.deterministic = True
    torch.use_deterministic_algorithms(True)
    dist.init_process_group("nccl", rank=rank, world_size=world_size)
    try:
        matrix = json.loads(Path(spec["matrix"]).read_text(encoding="utf-8"))
        row = next(item for item in matrix["rows"] if item["configuration_id"] == spec["configuration_id"])
        base_training = yaml.safe_load(Path(spec["training_config"]).read_text(encoding="utf-8"))
        base_model = load_strict_yaml(spec["model_config"])
        routed = materialize_hyperparameter_configuration(row, base_training, base_model)
        routed["training"]["training"].update({"maximum_epochs": 200, "updates_per_epoch": 76, "maximum_updates": 15_200})
        config, model_config = routed["training"], routed["model"]
        data = ProductionPreparedData(spec["cache_root"], row["scientific"]["intensity"], row["scientific"]["effective_k"])
        vocabulary = build_vocabulary(spec["categories"]); vocabulary_sizes = validate_vocabulary_contract(vocabulary)
        sampler = rotating_padding_state(data.training_scenes, int(config["training"]["root_seed"]), 0)
        groups = logical_groups(sampler, 32)
        if len(groups) != 76: raise PilotContractError("SAMPLER_UPDATE_COUNT_MISMATCH")
        scenes = list(groups[0]); local = scenes[rank * 16:(rank + 1) * 16]
        pairs = [selected_pair(scene, data.views[scene], config) for scene in local]
        cpu = [collate([data.sample("training", scene, pair[role]) for scene, pair in zip(local, pairs, strict=True)], vocabulary)
               for role in range(2)]
        device = torch.device("cuda", rank)
        model = P9MomentumModel(model_config, vocabulary_sizes, "FM").to(device)
        model.online.eval(); model.target.eval()
        optimizer = torch.optim.AdamW([p for p in model.online.parameters() if p.requires_grad],
                                      lr=float(row["scientific"]["peak_learning_rate"]),
                                      weight_decay=float(config["optimizer"]["weight_decay"]))
        scheduler = P9ExactScheduler(optimizer, float(row["scientific"]["peak_learning_rate"]))
        queue = empty_queue(device, capacity=int(config["queue"]["capacity"]), dimension=int(model_config["model"]["d"]))
        geometry_reader = GeometryCacheReader(Path(spec["cache_root"]) / "geometry/geometry_cache_manifest.json", 4 * 1024**3)
        batches = [to_device(value, device) for value in cpu]
        geometries = [geometry_reader.batch(batch, data.physical_training_role, device) for batch in batches]
        ddp = DistributedDataParallel(model.online, device_ids=[rank], output_device=rank,
                                      find_unused_parameters=False, bucket_cap_mb=50,
                                      gradient_as_bucket_view=False, static_graph=False)
        before = _state_digest(model, optimizer, scheduler, queue)
        with torch.no_grad():
            outputs = [ddp(batch, geometry) for batch, geometry in zip(batches, geometries, strict=True)]
            targets = [model.target(batch, geometry)["contrastive_embedding"]
                       for batch, geometry in zip(batches, geometries, strict=True)]
            keys = torch.stack(targets, 1); gathered = _gather(keys)
            centers = _gather(batches[0]["scene_center_5186"]); identifiers = _gather(batches[0]["scene_numeric_ids"])
            numerator, count = local_infonce_sum(
                outputs[0]["contrastive_embedding"], outputs[1]["contrastive_embedding"],
                gathered[:, 0], gathered[:, 1], batches[0]["scene_center_5186"], centers,
                batches[0]["scene_numeric_ids"], identifiers, queue,
                float(config["objective"]["contrastive_temperature"]),
                float(config["objective"]["negative_exclusion_distance_m"]))
            loss = numerator / count
        after = _state_digest(model, optimizer, scheduler, queue)
        result = {
            "rank": rank, "loss": float(loss), "finite": bool(torch.isfinite(loss)), "state_unchanged": before == after,
            "local_batch": len(local), "validation_identity_count": len(data.validation_scenes),
            "optimizer_updates": scheduler.completed_updates, "queue_count": int(queue["valid_count"]),
        }
        Path(output, f"rank-{rank}.json").write_text(json.dumps(result, sort_keys=True), encoding="utf-8")
    finally:
        dist.destroy_process_group()


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0)); return int(sock.getsockname()[1])


def run_non_training_pilot(spec: dict[str, str], output: str | Path) -> dict[str, Any]:
    """Run one actual production-cache batch on two GPUs and return non-authorizing evidence."""
    if spec["configuration_id"] == "cfg_main": raise PilotContractError("CFG_MAIN_PILOT_PROHIBITED")
    if torch.cuda.device_count() != 2: raise PilotContractError("PILOT_REQUIRES_EXACTLY_TWO_VISIBLE_GPUS")
    output = Path(output); output.mkdir(parents=True, exist_ok=False)
    mp.spawn(_rank, args=(2, _free_port(), spec, str(output)), nprocs=2, join=True)
    ranks = [json.loads((output / f"rank-{rank}.json").read_text(encoding="utf-8")) for rank in range(2)]
    if not all(row["finite"] and row["state_unchanged"] and row["optimizer_updates"] == 0 and row["queue_count"] == 0 for row in ranks):
        raise PilotContractError("NON_TRAINING_INVARIANT_FAILED")
    result = {
        "schema_version": "2.0.0", "artifact_type": "p9_v2_non_training_pilot", "status": "PASS",
        "configuration_id": spec["configuration_id"], "world_size": 2,
        "production_batch_loaded": True, "finite_forward_loss": True,
        "construction": {name: True for name in ("production_dataset", "ddp", "model", "ema", "optimizer", "scheduler", "queue", "sampler", "fixed_validation_identity")},
        "mutation_counts": {name: 0 for name in ("backward_passes", "optimizer_updates", "ema_updates", "queue_mutations", "checkpoint_publications", "acceptance_publications")},
        "evaluation_counts": {name: 0 for name in ("query_loads", "gallery_loads", "embeddings", "metric_computations")},
    }
    validate_instance("training_pilot", result)
    return result


def _update_rank(rank: int, world_size: int, port: int, spec: dict[str, str], output: str) -> None:
    """Run one real update with no validation, ledger, checkpoint, or publication."""
    from p9_v2_training_worker import (
        configure_process, create_state, load_worker_values, training_update,
    )

    os.environ.update({
        "MASTER_ADDR": "127.0.0.1", "MASTER_PORT": str(port), "NCCL_P2P_DISABLE": "1",
        "NCCL_IB_DISABLE": "1", "TORCH_NCCL_BLOCKING_WAIT": "1",
    })
    values = load_worker_values(spec)
    device = configure_process(values["config"], rank)
    dist.init_process_group("nccl", rank=rank, world_size=world_size, device_id=device)
    try:
        state = create_state(values, device)
        ddp = DistributedDataParallel(
            state.model.online, device_ids=[rank], output_device=rank,
            find_unused_parameters=False, bucket_cap_mb=50,
            gradient_as_bucket_view=False, static_graph=False,
        )
        observation = training_update(ddp, state, values, 1, 0, rank, device)
        torch.cuda.synchronize(device)
        result = {
            "rank": rank,
            "configuration_id": spec["configuration_id"],
            "selected_profile": values["data"].profile,
            "training_scenes": len(values["data"].training_scenes),
            "physical_training_views": sum(len(value) for value in values["data"].physical_views.values()),
            "logical_training_views": sum(len(value) for value in values["data"].views.values()),
            "optimizer_updates": state.scheduler.completed_updates,
            "queue_count": int(state.queue["valid_count"]),
            "queue_pointer": int(state.queue["pointer"]),
            "sampler_epoch": 1,
            "sampler_cursor": 1,
            "finite": all(torch.isfinite(torch.tensor(observation[key])) for key in
                          ("total_loss", "scene_loss", "ip_loss")),
            "training_observation": observation,
            "validation_executions": 0,
            "evaluation_executions": 0,
            "checkpoint_publications": 0,
            "acceptance_publications": 0,
        }
        Path(output, f"rank-{rank}.json").write_text(
            json.dumps(result, sort_keys=True), encoding="utf-8")
    finally:
        dist.destroy_process_group()


def run_bounded_update_pilot(spec: dict[str, str], output: str | Path) -> dict[str, Any]:
    """Run exactly one noncanonical global update for an intensity profile."""
    if spec["configuration_id"] not in {"cfg_intensity_05", "cfg_intensity_20"}:
        raise PilotContractError("INTENSITY_UPDATE_PILOT_CONFIGURATION_INVALID")
    if torch.cuda.device_count() != 2:
        raise PilotContractError("PILOT_REQUIRES_EXACTLY_TWO_VISIBLE_GPUS")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    mp.spawn(_update_rank, args=(2, _free_port(), spec, str(output)), nprocs=2, join=True)
    ranks = [json.loads((output / f"rank-{rank}.json").read_text(encoding="utf-8")) for rank in range(2)]
    if not all(
        row["training_scenes"] == 2_421
        and row["logical_training_views"] == 2_421 * 8
        and row["optimizer_updates"] == 1
        and row["queue_count"] == 64
        and row["queue_pointer"] == 64
        and row["sampler_cursor"] == 1
        and row["finite"]
        and row["validation_executions"] == 0
        and row["evaluation_executions"] == 0
        and row["checkpoint_publications"] == 0
        and row["acceptance_publications"] == 0
        for row in ranks
    ):
        raise PilotContractError("BOUNDED_INTENSITY_UPDATE_INVARIANT_FAILED")
    return {
        "status": "PASS", "pilot_kind": "NONCANONICAL_INTENSITY_ROLE_UPDATE",
        "configuration_id": spec["configuration_id"], "selected_profile": ranks[0]["selected_profile"],
        "world_size": 2, "global_optimizer_updates": 1,
        "physical_training_views": ranks[0]["physical_training_views"],
        "logical_training_views": ranks[0]["logical_training_views"],
        "queue_count": ranks[0]["queue_count"], "queue_pointer": ranks[0]["queue_pointer"],
        "sampler_epoch": 1, "sampler_cursor": 1,
        "validation_executions": 0, "evaluation_executions": 0,
        "formal_checkpoint_publications": 0, "formal_acceptance_publications": 0,
        "ranks": ranks,
    }
