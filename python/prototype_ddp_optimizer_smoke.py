#!/usr/bin/env python3
"""Controlled optimizer, deterministic repeat, and resume gates for two-rank DDP."""

from __future__ import annotations

import argparse
import copy
import json
import math
import os
import socket
import tempfile
import time
from pathlib import Path
from typing import Any

import torch
import torch.distributed as dist
import torch.multiprocessing as mp
import yaml
from torch.nn.parallel import DistributedDataParallel

from prototype_dataloader import AcceptedPrototypeDataset, ragged_collate
from prototype_ddp_joint_model import DistributedJointPrototypeModel
from prototype_ddp_joint_objective_smoke import counts, local_backward, prepare_model, target_keys
from prototype_joint_model import enqueue
from run_prototype_training import make_optimizer, state_digest as digest_state


def free_port() -> int:
    with socket.socket() as stream:
        stream.bind(("127.0.0.1", 0))
        return int(stream.getsockname()[1])


def optimizer_spec() -> dict[str, Any]:
    return {"optimizer": {"learning_rate": 1e-4, "weight_decay": 1e-4,
                          "warmup_epochs": 10, "maximum_epochs": 200}}


def empty_queue(device: torch.device) -> dict[str, Any]:
    return {"values": torch.zeros((8192, 128), device=device),
            "scene_ids": torch.full((8192,), -1, dtype=torch.int64, device=device),
            "centers": torch.zeros((8192, 2), device=device), "pointer": 0, "occupancy": 0}


def scene_numbers(scene_ids: list[str], device: torch.device) -> torch.Tensor:
    import hashlib
    return torch.tensor([int.from_bytes(hashlib.sha256(value.encode()).digest()[:8], "big") & ((1 << 63) - 1)
                         for value in scene_ids], dtype=torch.int64, device=device)


def queue_insert(queue: dict[str, Any], keys: list[torch.Tensor], centers: torch.Tensor,
                 scene_ids: list[str]) -> None:
    values = torch.stack(keys, dim=1).reshape(-1, 128)
    ids = scene_numbers(scene_ids, centers.device).repeat_interleave(2)
    inserted_centers = centers.repeat_interleave(2, 0)
    queue["pointer"], queue["occupancy"] = enqueue(
        queue["values"], queue["scene_ids"], queue["centers"], queue["pointer"], queue["occupancy"],
        values, ids, inserted_centers)


def canonical_state(model: DistributedJointPrototypeModel, optimizer: Any, scheduler: Any,
                    queue: dict[str, Any], step: int, losses: list[float]) -> dict[str, Any]:
    return {"model": model.state_dict(), "optimizer": optimizer.state_dict(), "scheduler": scheduler.state_dict(),
            "queue": queue, "step": step, "losses": losses,
            "python_rng": __import__("random").getstate(), "numpy_rng": __import__("numpy").random.get_state(),
            "torch_rng": torch.get_rng_state(), "cuda_rng": torch.cuda.get_rng_state()}


def restore(state: dict[str, Any], model: DistributedJointPrototypeModel, optimizer: Any,
            scheduler: Any, queue: dict[str, Any], device: torch.device) -> tuple[int, list[float]]:
    model.load_state_dict(state["model"]); optimizer.load_state_dict(state["optimizer"]); scheduler.load_state_dict(state["scheduler"])
    for name in ("values", "scene_ids", "centers"): queue[name].copy_(state["queue"][name].to(device))
    queue["pointer"], queue["occupancy"] = int(state["queue"]["pointer"]), int(state["queue"]["occupancy"])
    __import__("random").setstate(state["python_rng"]); __import__("numpy").random.set_state(state["numpy_rng"])
    torch.set_rng_state(state["torch_rng"]); torch.cuda.set_rng_state(state["cuda_rng"], device)
    return int(state["step"]), list(state["losses"])


def one_step(callable_model: Any, model: DistributedJointPrototypeModel, optimizer: Any, scheduler: Any,
             queue: dict[str, Any], packages: list[dict[str, Any]], config: dict[str, Any], joint: dict[str, Any],
             masks: dict[str, int], device: torch.device, seed: int, epoch: int, ddp: bool) -> tuple[float, list[torch.Tensor]]:
    batches = [batch for package in packages for batch in package["batches"]]
    keys = target_keys(model, batches, config, masks, device)
    scene_ids = [scene for package in packages for scene in package["scene_ids"]]
    centers = torch.tensor([center for package in packages for center in package["centers"]], device=device, dtype=torch.float32)
    index = {scene: offset for offset, scene in enumerate(scene_ids)}
    global_counts = counts(batches, masks)
    optimizer.zero_grad(set_to_none=True); loss = 0.0
    for package in packages:
        value, _ = local_backward(callable_model, model, package["batches"], config, joint, masks, device,
                                  keys, centers, index, global_counts, ddp, seed, epoch)
        loss += value
    torch.nn.utils.clip_grad_norm_([parameter for parameter in model.parameters() if parameter.requires_grad], 1.0)
    optimizer.step(); scheduler.step(); model.update_target(0.999); queue_insert(queue, keys, centers, scene_ids)
    return loss, keys


def reference(packages: list[dict[str, Any]], config: dict[str, Any], joint: dict[str, Any],
              masks: dict[str, int], steps: int) -> dict[str, Any]:
    device = torch.device("cuda:0"); model = prepare_model(config, joint, device, 20260822)
    optimizer, scheduler = make_optimizer(model, optimizer_spec()); queue = empty_queue(device); losses = []
    started = time.perf_counter()
    snapshots = {}
    for step in range(steps):
        loss, _ = one_step(model, model, optimizer, scheduler, queue, packages, config, joint, masks,
                           device, 20260822, step, False); losses.append(loss)
        if step in (0, 4): snapshots[step + 1] = {name: value.detach().cpu().clone() for name, value in model.named_parameters()}
    torch.cuda.synchronize(); elapsed = time.perf_counter() - started
    state = canonical_state(model, optimizer, scheduler, queue, steps, losses)
    result = {"snapshots": snapshots, "state_digest": digest_state(state), "losses": losses,
              "elapsed_seconds": elapsed, "steps": steps}
    del model, optimizer, scheduler, queue; torch.cuda.empty_cache(); return result


def ddp_worker(rank: int, port: int, package_paths: list[str], config_path: str, joint_path: str,
               masks: dict[str, int], steps: int, mode: str, checkpoint_path: str, output_path: str) -> None:
    os.environ.update(MASTER_ADDR="127.0.0.1", MASTER_PORT=str(port), RANK=str(rank), WORLD_SIZE="2", LOCAL_RANK=str(rank))
    torch.cuda.set_device(rank); torch.use_deterministic_algorithms(True)
    torch.backends.cuda.matmul.allow_tf32 = False; torch.backends.cudnn.allow_tf32 = False
    dist.init_process_group("nccl", rank=rank, world_size=2, device_id=torch.device(f"cuda:{rank}"))
    device = torch.device(f"cuda:{rank}"); config = yaml.safe_load(Path(config_path).read_text()); joint = yaml.safe_load(Path(joint_path).read_text())
    local_package = torch.load(package_paths[rank], weights_only=False)
    model = prepare_model(config, joint, device, 20260822)
    ddp = DistributedDataParallel(model, device_ids=[rank], broadcast_buffers=False, find_unused_parameters=False)
    optimizer, scheduler = make_optimizer(model, optimizer_spec()); queue = empty_queue(device); losses=[]; start_step=0
    if mode == "resume":
        state = torch.load(f"{checkpoint_path}.rank{rank}.pt", map_location="cpu", weights_only=False)
        start_step, losses = restore(state, model, optimizer, scheduler, queue, device)
    metadata: list[Any] = [None, None]
    dist.all_gather_object(metadata, (local_package["scene_ids"], local_package["centers"]))
    scene_ids=[scene for value in metadata for scene in value[0]]
    centers=torch.tensor([center for value in metadata for center in value[1]],device=device,dtype=torch.float32)
    index={scene:offset for offset,scene in enumerate(scene_ids)}
    local_counts=counts(local_package["batches"],masks); names=list(local_counts)
    count_tensor=torch.tensor([local_counts[name] for name in names],device=device,dtype=torch.int64);dist.all_reduce(count_tensor)
    global_counts={name:int(count_tensor[offset]) for offset,name in enumerate(names)}
    started = time.perf_counter(); snapshots={}
    for step in range(start_step, steps):
        local_keys=target_keys(model,local_package["batches"],config,masks,device);keys=[]
        for local in local_keys:
            gathered=[torch.empty_like(local) for _ in range(2)];dist.all_gather(gathered,local);keys.append(torch.cat(gathered))
        optimizer.zero_grad(set_to_none=True)
        local_loss,_=local_backward(ddp,model,local_package["batches"],config,joint,masks,device,keys,centers,index,
                                    global_counts,True,20260822,step)
        torch.nn.utils.clip_grad_norm_([parameter for parameter in model.parameters() if parameter.requires_grad],1.0)
        optimizer.step();scheduler.step();model.update_target(0.999);queue_insert(queue,keys,centers,scene_ids)
        loss_tensor=torch.tensor([local_loss],device=device,dtype=torch.float64);dist.all_reduce(loss_tensor);losses.append(float(loss_tensor))
        if step in (0,4):snapshots[step+1]={name:value.detach().cpu().clone() for name,value in model.named_parameters()}
        if mode == "straight" and step == 1:
            state=canonical_state(model,optimizer,scheduler,queue,step+1,losses)
            torch.save(state,f"{checkpoint_path}.rank{rank}.pt")
    torch.cuda.synchronize();local_elapsed=time.perf_counter()-started
    elapsed=torch.tensor([local_elapsed],device=device,dtype=torch.float64);dist.all_reduce(elapsed,op=dist.ReduceOp.MAX)
    state=canonical_state(model,optimizer,scheduler,queue,steps,losses)
    synchronized={"model":model.state_dict(),"optimizer":optimizer.state_dict(),"scheduler":scheduler.state_dict(),
                  "queue":queue,"step":steps,"losses":losses}
    sync_digest=digest_state(synchronized);digests=[None,None];dist.all_gather_object(digests,sync_digest)
    full_digest=digest_state(state);full_digests=[None,None];dist.all_gather_object(full_digests,full_digest)
    result={"snapshots":snapshots,"state_digest":sync_digest,"rank_state_digests":digests,
            "rank_checkpoint_digests":full_digests,"losses":losses,"elapsed_seconds":float(elapsed),"steps":steps}
    result["digest"]=sync_digest
    if rank==0:torch.save(result,output_path)
    dist.barrier();dist.destroy_process_group()


def compare_parameters(expected: dict[str, torch.Tensor], observed: dict[str, torch.Tensor]) -> dict[str, Any]:
    failures=[]; maximum=0.0
    for name, left in expected.items():
        right=observed[name]; maximum=max(maximum,float((left-right).abs().max()))
        if not torch.allclose(left,right,atol=1e-6,rtol=1e-5): failures.append(name)
    return {"atol":1e-6,"rtol":1e-5,"maximum_absolute_difference":maximum,"failures":failures}


def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument("--accepted-manifest",required=True);parser.add_argument("--tensor-contract",required=True)
    parser.add_argument("--encoder-config",required=True);parser.add_argument("--joint-config",required=True);args=parser.parse_args()
    torch.use_deterministic_algorithms(True);torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
    config=yaml.safe_load(Path(args.encoder_config).read_text());joint=yaml.safe_load(Path(args.joint_config).read_text())
    dataset=AcceptedPrototypeDataset(args.accepted_manifest,args.tensor_contract,split="training")
    samples=[]
    for position,row in sorted(enumerate(dataset.rows),key=lambda value:(int(value[1]["node_count"]),value[1]["scene_id"])):
        sample=dataset[position]
        if set(sample["entities"]["entity_type"].tolist())=={0,1,2}:samples.append(sample)
        if len(samples)==32:break
    samples=sorted(samples,key=lambda value:value["scene_id"]);packages=[]
    for rank in range(2):
        local=samples[rank*16:(rank+1)*16]
        packages.append({"scene_ids":[value["scene_id"] for value in local],
                         "centers":[value["meta"]["center_xy_5186"] for value in local],
                         "batches":[ragged_collate(local[:8]),ragged_collate(local[8:])]})
    masks={name:next(iter(values)) for name,values in dataset.category_mask_index.items()}
    single=reference(packages,config,joint,masks,5)
    with tempfile.TemporaryDirectory(prefix="fuse-ddp-optimizer-") as directory:
        root=Path(directory);package_paths=[]
        for rank,package in enumerate(packages):
            path=root/f"package-{rank}.pt";torch.save(package,path);package_paths.append(str(path))
        def launch(label:str,mode:str,checkpoint:str)->dict[str,Any]:
            output=root/f"{label}.pt"
            mp.spawn(ddp_worker,args=(free_port(),package_paths,str(Path(args.encoder_config).resolve()),
                     str(Path(args.joint_config).resolve()),masks,5,mode,checkpoint,str(output)),nprocs=2,join=True)
            return torch.load(output,weights_only=False)
        first=launch("straight-a","straight",str(root/"control"))
        second=launch("straight-b","straight",str(root/"control-b"))
        resumed=launch("resumed","resume",str(root/"control"))
    comparisons={str(step):compare_parameters(single["snapshots"][step],first["snapshots"][step]) for step in (1,5)}
    repeated_exact=first["digest"]==second["digest"]
    resume_exact=first["digest"]==resumed["digest"]
    ranks_exact=len(set(first["rank_state_digests"]))==1
    speedup=single["elapsed_seconds"]/first["elapsed_seconds"]
    passed=all((not comparisons["1"]["failures"],not comparisons["5"]["failures"],repeated_exact,resume_exact,ranks_exact,speedup>1.0))
    print(json.dumps({"status":"PASS" if passed else "BLOCKED","parameter_parity":comparisons,
                      "ddp_repeated_exact":repeated_exact,"ddp_resume_exact":resume_exact,"rank_state_exact":ranks_exact,
                      "single_elapsed_seconds":single["elapsed_seconds"],"ddp_elapsed_seconds":first["elapsed_seconds"],
                      "speedup":speedup,"straight_digest":first["digest"],"repeat_digest":second["digest"],
                      "resume_digest":resumed["digest"],"steps":5},sort_keys=True))


if __name__ == "__main__": main()
