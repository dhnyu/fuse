#!/usr/bin/env python3
"""Two-GPU NCCL transport preflight without model or data dependencies."""

from __future__ import annotations

import json
import os
import argparse
import datetime as dt

import torch
import torch.distributed as dist
from torch.nn.parallel import DistributedDataParallel


def run(timeout_seconds: float) -> None:
    rank = int(os.environ.get("RANK", "-1"))
    local_rank = int(os.environ.get("LOCAL_RANK", "-1"))
    world_size = int(os.environ.get("WORLD_SIZE", "-1"))
    if (os.getenv("CUDA_VISIBLE_DEVICES") != "0,1" or os.getenv("NCCL_P2P_DISABLE") != "1"
            or os.getenv("NCCL_IB_DISABLE") != "1" or torch.cuda.device_count() != 2
            or rank not in (0, 1) or local_rank not in (0, 1) or world_size != 2):
        raise RuntimeError("S09_NCCL_PREFLIGHT_ENVIRONMENT_MISMATCH")
    torch.cuda.set_device(local_rank)
    dist.init_process_group("nccl",
                            timeout=dt.timedelta(seconds=float(timeout_seconds)))
    if dist.get_rank() != rank or dist.get_world_size() != 2 or torch.cuda.current_device() != local_rank:
        raise RuntimeError("S09_NCCL_PREFLIGHT_RANK_DEVICE_MISMATCH")
    value = torch.tensor([rank + 1.0], dtype=torch.float32, device=local_rank)
    dist.all_reduce(value, op=dist.ReduceOp.SUM)
    if not torch.equal(value.cpu(), torch.tensor([3.0])): raise RuntimeError("NCCL all-reduce value mismatch")
    gathered = [torch.empty_like(value) for _ in range(2)]
    dist.all_gather(gathered, value)
    if any(not torch.equal(item.cpu(), torch.tensor([3.0])) for item in gathered): raise RuntimeError("NCCL all-gather mismatch")
    probe_model = torch.nn.Sequential(torch.nn.Linear(4, 8), torch.nn.GELU(), torch.nn.Linear(8, 2)).to(local_rank)
    ddp = DistributedDataParallel(
        probe_model, device_ids=[local_rank], output_device=local_rank,
        find_unused_parameters=False, bucket_cap_mb=50,
        gradient_as_bucket_view=False, static_graph=False,
    )
    if not isinstance(ddp, DistributedDataParallel):
        raise RuntimeError("S09_NCCL_PREFLIGHT_DDP_CONSTRUCTION_FAILED")
    dist.barrier()
    dist.destroy_process_group()
    if rank == 0:
        print(json.dumps({
            "status": "PASS", "backend": "nccl", "world_size": 2,
            "environment": {
                "CUDA_VISIBLE_DEVICES": os.getenv("CUDA_VISIBLE_DEVICES"),
                "NCCL_P2P_DISABLE": os.getenv("NCCL_P2P_DISABLE"),
                "NCCL_IB_DISABLE": os.getenv("NCCL_IB_DISABLE"),
            },
            "stages": {
                "process_group_initialization": "PASS",
                "rank_device_assignment": "PASS",
                "allreduce": "PASS",
                "allgather": "PASS",
                "ddp_construction": "PASS",
                "process_group_destruction": "PASS",
            },
        }, sort_keys=True), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout-seconds", type=float, required=True)
    args = parser.parse_args()
    if not 5 <= args.timeout_seconds <= 120:
        raise ValueError("S09_NCCL_PREFLIGHT_TIMEOUT_INVALID")
    run(args.timeout_seconds)
