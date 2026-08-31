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
from p9_v2_schema import validate_instance
from rotating_padding_sampler import logical_groups, rotating_padding_state


class PilotContractError(RuntimeError):
    pass


class ProductionPreparedData:
    """Read accepted immutable prepared views by logical scientific identity."""
    def __init__(self, root: str | Path, profile: str, logical_k: int):
        self.root = Path(root)
        plan = json.loads((self.root / "canonical_cache_plan.json").read_text(encoding="utf-8"))
        if int(plan["entry_count"]) != 78_672: raise PilotContractError("PRODUCTION_CACHE_ENTRY_COUNT_MISMATCH")
        index: dict[tuple[str, str, int | None], dict[str, Any]] = {}
        for row in plan["entries"]:
            if row["role"] == "training" and row["profile"] != profile: continue
            key = (row["role"], row["scene_id"], row["view"])
            if key in index: raise PilotContractError("DUPLICATE_PREPARED_VIEW")
            index[key] = row
        self.index = index
        by_scene: dict[str, list[int]] = {}
        for role, scene, view in index:
            if role == "training": by_scene.setdefault(scene, []).append(int(view))
        self.views = {scene: tuple(sorted(values)[:logical_k]) for scene, values in by_scene.items()}
        if len(self.views) != 2_421 or any(len(value) != logical_k for value in self.views.values()):
            raise PilotContractError("PRODUCTION_TRAINING_POPULATION_MISMATCH")
        self.training_scenes = sorted(self.views)
        self.validation_scenes = sorted({scene for role, scene, _ in index if role == "validation_gallery"})
        if len(self.validation_scenes) != 400: raise PilotContractError("FIXED_VALIDATION_IDENTITY_MISMATCH")

    def sample(self, scene: str, view: int) -> dict[str, Any]:
        spec = self.index[("training", scene, view)]; index = int(spec["global_index"])
        payload = torch.load(self.root / "prepared" / f"{index:06d}.pt", map_location="cpu", weights_only=False)
        if payload.get("spec") != spec or int(payload.get("global_index", -1)) != index:
            raise PilotContractError("PREPARED_PAYLOAD_IDENTITY_MISMATCH")
        return payload["sample"]


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
        cpu = [collate([data.sample(scene, pair[role]) for scene, pair in zip(local, pairs, strict=True)], vocabulary)
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
        geometries = [geometry_reader.batch(batch, "training", device) for batch in batches]
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
