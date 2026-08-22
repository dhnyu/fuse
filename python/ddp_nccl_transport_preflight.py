#!/usr/bin/env python3
"""Two-GPU NCCL transport preflight without model or data dependencies."""

from __future__ import annotations

import json
import os
import socket

import torch
import torch.distributed as dist
import torch.multiprocessing as mp


def port() -> int:
    with socket.socket() as stream:
        stream.bind(("127.0.0.1", 0)); return int(stream.getsockname()[1])


def worker(rank: int, master_port: int) -> None:
    os.environ.update(MASTER_ADDR="127.0.0.1", MASTER_PORT=str(master_port), RANK=str(rank), WORLD_SIZE="2", LOCAL_RANK=str(rank))
    torch.cuda.set_device(rank)
    dist.init_process_group("nccl", rank=rank, world_size=2)
    value = torch.tensor([rank + 1.0], dtype=torch.float32, device=rank)
    dist.all_reduce(value, op=dist.ReduceOp.SUM)
    if not torch.equal(value.cpu(), torch.tensor([3.0])): raise RuntimeError("NCCL all-reduce value mismatch")
    gathered = [torch.empty_like(value) for _ in range(2)]
    dist.all_gather(gathered, value)
    if any(not torch.equal(item.cpu(), torch.tensor([3.0])) for item in gathered): raise RuntimeError("NCCL all-gather mismatch")
    dist.barrier(); dist.destroy_process_group()


if __name__ == "__main__":
    mp.spawn(worker, args=(port(),), nprocs=2, join=True)
    print(json.dumps({"status": "PASS", "backend": "nccl", "world_size": 2,
                      "p2p_disabled": os.getenv("NCCL_P2P_DISABLE"), "ib_disabled": os.getenv("NCCL_IB_DISABLE")}))
