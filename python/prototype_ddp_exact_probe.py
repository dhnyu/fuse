#!/usr/bin/env python3
"""Exact single-device accumulation versus two-rank NCCL DDP probe."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import tempfile
from pathlib import Path
from typing import Any

for _name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_name] = "1"

import torch
import torch.distributed as dist
import torch.multiprocessing as mp
import yaml
from torch import nn
from torch.nn.parallel import DistributedDataParallel

from prototype_dataloader import AcceptedPrototypeDataset, ragged_collate
from prototype_encoder import PrototypeSceneEncoder, geometry_fourier_features
from prototype_ddp_joint_model import dropout_keys, install_keyed_dropout, keyed_dropout_context


def move_batch(batch: dict[str, Any], device: torch.device) -> dict[str, Any]:
    allowed = {key: batch[key] for key in (
        "scene_ids", "scene_ptr", "entity_scene_index", "entity_local_index", "entities", "geometry", "edges", "rasters"
    )}
    def move(value: Any) -> Any:
        if isinstance(value, torch.Tensor): return value.to(device)
        if isinstance(value, dict): return {key: move(child) for key, child in value.items()}
        return value
    return move(allowed)


def digest_state(value: Any) -> str:
    digest = hashlib.sha256()
    def update(item: Any) -> None:
        if isinstance(item, torch.Tensor):
            array = item.detach().cpu().contiguous().numpy()
            digest.update(str(array.dtype).encode()); digest.update(str(array.shape).encode()); digest.update(array.tobytes())
        elif isinstance(item, dict):
            for key in sorted(item): digest.update(key.encode()); update(item[key])
        elif isinstance(item, list):
            for child in item: update(child)
        else: digest.update(repr(item).encode())
    update(value)
    return digest.hexdigest()


class ProbeModel(nn.Module):
    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__()
        self.encoder = PrototypeSceneEncoder(config)
        install_keyed_dropout(self.encoder)

    def forward(self, batch: dict[str, Any], geometry: tuple[torch.Tensor, torch.Tensor]) -> dict[str, torch.Tensor]:
        with keyed_dropout_context(dropout_keys(batch, 20260822, 0, 0)):
            return self.encoder(batch, geometry)


def objective(output: dict[str, torch.Tensor], global_scenes: int) -> torch.Tensor:
    return output["scene_raw"].square().sum() / (global_scenes * output["scene_raw"].shape[1]) + output["projection"][:, 0].sum() / global_scenes


def reference(batches: list[dict[str, Any]], config: dict[str, Any], seed: int) -> dict[str, Any]:
    device = torch.device("cuda:0")
    torch.cuda.set_device(device); torch.manual_seed(seed); torch.cuda.manual_seed_all(seed)
    model = ProbeModel(config).to(device).train(); model.zero_grad(set_to_none=True)
    outputs = []
    for cpu_batch in batches:
        batch = move_batch(cpu_batch, device)
        geometry = geometry_fourier_features(batch, config, device)
        output = model(batch, geometry); outputs.append(output["scene_raw"].detach().cpu())
        objective(output, 32).backward()
    gradients = {name: parameter.grad.detach().cpu() for name, parameter in model.named_parameters() if parameter.grad is not None}
    result = {"scene_raw": torch.cat(outputs), "gradients": gradients}
    result["digest"] = digest_state(result)
    del model
    torch.cuda.empty_cache()
    return result


def ddp_worker(rank: int, port: int, batch_paths: list[str], config_path: str, seed: int, result_path: str) -> None:
    os.environ.update(MASTER_ADDR="127.0.0.1", MASTER_PORT=str(port), RANK=str(rank), WORLD_SIZE="2", LOCAL_RANK=str(rank))
    torch.set_num_threads(1); torch.set_num_interop_threads(1); torch.use_deterministic_algorithms(True)
    torch.backends.cuda.matmul.allow_tf32 = False; torch.backends.cudnn.allow_tf32 = False
    torch.cuda.set_device(rank); dist.init_process_group("nccl", rank=rank, world_size=2)
    config = yaml.safe_load(Path(config_path).read_text()); torch.manual_seed(seed); torch.cuda.manual_seed_all(seed)
    model = ProbeModel(config).to(rank).train()
    ddp = DistributedDataParallel(model, device_ids=[rank], output_device=rank, broadcast_buffers=False)
    batch = move_batch(torch.load(batch_paths[rank], weights_only=False), torch.device(f"cuda:{rank}"))
    geometry = geometry_fourier_features(batch, config, torch.device(f"cuda:{rank}"))
    output = ddp(batch, geometry)
    (2.0 * objective(output, 32)).backward()
    gathered = [torch.empty_like(output["scene_raw"]) for _ in range(2)]
    dist.all_gather(gathered, output["scene_raw"].detach())
    gradients = {name.removeprefix("module."): parameter.grad.detach().cpu()
                 for name, parameter in ddp.named_parameters() if parameter.grad is not None}
    payload = {"scene_raw": torch.cat(gathered).cpu(), "gradients": gradients}
    payload["digest"] = digest_state(payload)
    if rank == 0: torch.save(payload, result_path)
    dist.barrier(); dist.destroy_process_group()


def free_port() -> int:
    with socket.socket() as stream:
        stream.bind(("127.0.0.1", 0)); return int(stream.getsockname()[1])


def compare(reference_value: dict[str, Any], distributed: dict[str, Any]) -> dict[str, Any]:
    forward = (reference_value["scene_raw"] - distributed["scene_raw"]).abs()
    rows = []
    for name in sorted(reference_value["gradients"]):
        left, right = reference_value["gradients"][name], distributed["gradients"][name]
        difference = (left - right).abs()
        rows.append({"name": name, "exact": torch.equal(left, right), "different_elements": int(torch.count_nonzero(left != right)),
                     "maximum_absolute_difference": float(difference.max()) if difference.numel() else 0.0})
    return {
        "forward_exact": torch.equal(reference_value["scene_raw"], distributed["scene_raw"]),
        "forward_different_elements": int(torch.count_nonzero(reference_value["scene_raw"] != distributed["scene_raw"])),
        "forward_maximum_absolute_difference": float(forward.max()),
        "gradient_tensor_count": len(rows), "gradient_non_exact_tensor_count": sum(not row["exact"] for row in rows),
        "gradient_different_element_count": sum(row["different_elements"] for row in rows),
        "gradient_maximum_absolute_difference": max(row["maximum_absolute_difference"] for row in rows),
        "first_non_exact_gradients": [row for row in rows if not row["exact"]][:20],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--accepted-manifest", required=True); parser.add_argument("--tensor-contract", required=True)
    parser.add_argument("--encoder-config", required=True); parser.add_argument("--seed", type=int, default=20260822)
    args = parser.parse_args()
    if torch.cuda.device_count() != 2: raise RuntimeError("probe requires exactly two visible GPUs")
    torch.set_num_threads(1); torch.set_num_interop_threads(1); torch.use_deterministic_algorithms(True)
    torch.backends.cuda.matmul.allow_tf32 = False; torch.backends.cudnn.allow_tf32 = False
    config = yaml.safe_load(Path(args.encoder_config).read_text())
    dataset = AcceptedPrototypeDataset(args.accepted_manifest, args.tensor_contract, split="training")
    samples = []
    for index, _ in sorted(enumerate(dataset.rows), key=lambda item: (int(item[1]["node_count"]), item[1]["scene_id"])):
        sample = dataset[index]
        if set(sample["entities"]["entity_type"].tolist()) == {0, 1, 2}:
            samples.append(sample)
        if len(samples) == 32: break
    if len({sample["scene_id"] for sample in samples}) != 32: raise ValueError("probe scene population mismatch")
    batches = [ragged_collate(samples[:16]), ragged_collate(samples[16:])]
    with tempfile.TemporaryDirectory(prefix="fuse-ddp-exact-probe-") as directory:
        paths = [str(Path(directory) / f"rank-{rank}.pt") for rank in range(2)]
        for path, batch in zip(paths, batches, strict=True): torch.save(batch, path)
        single = reference(batches, config, args.seed)
        distributed_runs = []
        for repeat in range(2):
            result_path = str(Path(directory) / f"ddp-{repeat}.pt")
            mp.spawn(ddp_worker, args=(free_port(), paths, str(Path(args.encoder_config).resolve()), args.seed, result_path), nprocs=2, join=True)
            distributed_runs.append(torch.load(result_path, weights_only=False))
        comparison = compare(single, distributed_runs[0])
        result = {
            "status": "PASS" if comparison["forward_exact"] and comparison["gradient_non_exact_tensor_count"] == 0 and distributed_runs[0]["digest"] == distributed_runs[1]["digest"] else "BLOCKED",
            "mode": "stateless_scene_entity_keyed_dropout_training_gradient_collective",
            "scenes": 32, "rank_scenes": 16, "single_digest": single["digest"],
            "ddp_repeat_digests": [value["digest"] for value in distributed_runs],
            "ddp_repeated_exact": distributed_runs[0]["digest"] == distributed_runs[1]["digest"],
            "comparison": comparison,
            "device_names": [torch.cuda.get_device_name(index) for index in range(2)],
        }
        print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
