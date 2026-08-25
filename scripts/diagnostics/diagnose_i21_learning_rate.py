#!/usr/bin/env python3
"""Isolated two-GPU LR diagnostic with no checkpoint or artifact publication."""

from __future__ import annotations

import argparse
import copy
import gc
import json
import os
import random
import sys
import time
from pathlib import Path
from typing import Any

for _name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_name] = "1"

import numpy as np
import psutil
import torch
import torch.distributed as dist
import torch.multiprocessing as mp
import yaml
from torch.nn.parallel import DistributedDataParallel
from torch.utils.data import DataLoader

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from prototype_ddp_joint_model import DistributedJointPrototypeModel
from run_prototype_training import (
    AugmentedPairDataset, collate_pairs, make_optimizer, optimizer_steps_per_epoch, state_digest, worker_init,
)
from run_prototype_training_ddp import (
    RankLogicalGroupSampler, RankSceneSampler, distributed_validation, empty_queue,
    identity_collate, iter_rank_microbatches, sampled_system_metrics, sync_digest, train_group,
)


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    for name in ("run-spec", "training-config", "training-plan-config", "joint-config", "encoder-config",
                 "augmentation-config", "tensor-contract", "i19-manifest", "output"):
        parser.add_argument(f"--{name}", required=True)
    parser.add_argument("--learning-rate", action="append", type=float, required=True)
    parser.add_argument("--epochs", type=int, default=30)
    return parser.parse_args()


def initialize(seed: int, spec: dict[str, Any], encoder: dict[str, Any], joint: dict[str, Any], device: torch.device):
    random.seed(seed);np.random.seed(seed);torch.manual_seed(seed);torch.cuda.manual_seed_all(seed)
    model=DistributedJointPrototypeModel(encoder,joint).to(device).train();model.target.eval()
    ddp=DistributedDataParallel(model,device_ids=[device.index],broadcast_buffers=False,find_unused_parameters=False)
    optimizer,scheduler=make_optimizer(model,spec)
    return model,ddp,optimizer,scheduler,empty_queue(device)


def groups(loader:DataLoader,sampler:RankLogicalGroupSampler):
    batches=[];current=0
    for item in iter_rank_microbatches(loader,sampler):
        group=int(item["group"])
        if batches and group!=current:raise RuntimeError("diagnostic loader crossed logical group")
        batches.append(item)
        count=sum(len(value["positions"]) for value in batches)
        if count<16:continue
        if count!=16:raise RuntimeError("diagnostic rank group is not 16 scenes")
        yield group,batches
        batches=[];current=group+1
    if batches:raise RuntimeError("diagnostic epoch ended with partial group")


def parameter_vector(model:torch.nn.Module)->torch.Tensor:
    return torch.cat([parameter.detach().reshape(-1) for parameter in model.parameters() if parameter.requires_grad])


def release_candidate(*values:Any)->None:
    del values
    gc.collect()
    torch.cuda.empty_cache()
    gc.collect()
    if torch.cuda.memory_allocated()>64*1024**2:
        raise RuntimeError(f"diagnostic GPU state was not released: {torch.cuda.memory_allocated()} bytes")


def safety_replay(rank:int,seed:int,spec:dict[str,Any],joint:dict[str,Any],encoder:dict[str,Any],masks:dict[str,int],
                  device:torch.device,loader:DataLoader,sampler:RankLogicalGroupSampler)->dict[str,Any]:
    repetitions=[]
    for _ in range(2):
        model,ddp,optimizer,scheduler,queue=initialize(seed,spec,encoder,joint,device)
        sampler.set_epoch(0);rows=[]
        for group,batches in groups(loader,sampler):
            before=parameter_vector(model)
            result=train_group(ddp,model,batches,optimizer,scheduler,queue,spec,joint,encoder,masks,device,0)
            update=float(torch.linalg.vector_norm(parameter_vector(model)-before))
            rows.append({**result,"parameter_update_norm":update})
            if group==1:break
        digest=sync_digest(model,optimizer,scheduler,queue,device)
        repetitions.append({"rows":rows,"state_digest":digest})
        del ddp,model,optimizer,scheduler,queue
        release_candidate();dist.barrier()
    if repetitions[0]!=repetitions[1]:raise RuntimeError("LR safety phase is not exactly deterministic")
    rows=repetitions[0]["rows"]
    if len(rows)!=2 or any(not np.isfinite(value[key]) for value in rows for key in (
        "total_loss","scene_loss","information_preservation_loss","gradient_norm","parameter_update_norm")):
        raise RuntimeError("LR safety phase produced non-finite values")
    if rows[1]["total_loss"]>max(rows[0]["total_loss"]*5.0,rows[0]["total_loss"]+10.0):
        raise RuntimeError("LR safety phase loss-spike guard failed")
    return {"status":"PASS","steps":2,"exact_repeat":True,"state_digest":repetitions[0]["state_digest"],"rows":rows}


def run_candidate(rank:int,lr:float,epochs:int,seed:int,base_spec:dict[str,Any],joint:dict[str,Any],encoder:dict[str,Any],
                  masks:dict[str,int],device:torch.device,loader:DataLoader,valid_loader:DataLoader,
                  sampler:RankLogicalGroupSampler,validation:dict[str,Any])->dict[str,Any]:
    spec=copy.deepcopy(base_spec);spec["optimizer"]["learning_rate"]=float(lr)
    safety=safety_replay(rank,seed,spec,joint,encoder,masks,device,loader,sampler)
    model,ddp,optimizer,scheduler,queue=initialize(seed,spec,encoder,joint,device)
    initial_parameter_digest=state_digest(model.state_dict())
    steps=[];validations=[];epoch_rows=[];started=time.time();clip=float(spec["optimizer"]["gradient_norm_clip"])
    torch.cuda.reset_peak_memory_stats(device)
    for epoch in range(epochs):
        epoch_started=time.time();sampler.set_epoch(epoch)
        for group,batches in groups(loader,sampler):
            before=parameter_vector(model)
            result=train_group(ddp,model,batches,optimizer,scheduler,queue,spec,joint,encoder,masks,device,epoch)
            result["parameter_update_norm"]=float(torch.linalg.vector_norm(parameter_vector(model)-before))
            result["gradient_clipped"]=bool(float(result["gradient_norm"])>clip)
            result["epoch"]=epoch+1;result["logical_group"]=group;steps.append(result)
        system=sampled_system_metrics(rank,device)
        epoch_rows.append({"epoch":epoch+1,"wall_seconds":time.time()-epoch_started,"system":system})
        if (epoch+1)%int(validation["interval_epochs"])==0:
            metric=distributed_validation(model,valid_loader,encoder,masks,device,validation)
            metric["epoch"]=epoch+1;metric["optimizer_step"]=(epoch+1)*optimizer_steps_per_epoch(spec);validations.append(metric)
        if rank==0:
            recent=steps[-optimizer_steps_per_epoch(spec):]
            message={"learning_rate":lr,"epoch":epoch+1,
                "training_loss":sum(float(row["total_loss"]) for row in recent)/len(recent),
                "validation_retrieval_loss":validations[-1]["validation_retrieval_loss"] if validations and validations[-1]["epoch"]==epoch+1 else None}
            print(json.dumps(message,sort_keys=True),flush=True)
    state=sync_digest(model,optimizer,scheduler,queue,device)
    local={"rank":rank,"rss_bytes":psutil.Process().memory_info().rss,
           "peak_vram_bytes":int(torch.cuda.max_memory_allocated(device))}
    resources=[None,None];dist.all_gather_object(resources,local)
    output={"learning_rate":lr,"status":"PASS","safety":safety,"initial_parameter_digest":initial_parameter_digest,
        "steps":steps,"validation":validations,
        "epoch_timings":epoch_rows,"elapsed_seconds":time.time()-started,"final_state_digest":state,
        "clipping_ratio":sum(int(row["gradient_clipped"]) for row in steps)/len(steps),
        "queue_occupancy":int(queue["occupancy"]),"resources":resources}
    del ddp,model,optimizer,scheduler,queue
    release_candidate();dist.barrier()
    return output


def worker(rank:int,args:argparse.Namespace)->None:
    os.environ.update(RANK=str(rank),WORLD_SIZE="2",LOCAL_RANK=str(rank));torch.cuda.set_device(rank)
    torch.set_num_threads(1);torch.use_deterministic_algorithms(True)
    torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
    dist.init_process_group("nccl",rank=rank,world_size=2,device_id=torch.device(f"cuda:{rank}"))
    spec=json.loads(Path(args.run_spec).read_text());execution=yaml.safe_load(Path(args.training_config).read_text())["execution"]
    plan=yaml.safe_load(Path(args.training_plan_config).read_text());joint=yaml.safe_load(Path(args.joint_config).read_text())
    encoder=yaml.safe_load(Path(args.encoder_config).read_text());augmentation=yaml.safe_load(Path(args.augmentation_config).read_text())
    i19=json.loads(Path(args.i19_manifest).read_text());seed=int(spec["seed"])
    spec["training_scenes"]=int(plan["data"]["training_scenes"]);spec["effective_batch_scenes"]=int(plan["data"]["effective_batch_scenes"])
    spec["optimizer"]=copy.deepcopy(plan["optimization"]);validation=copy.deepcopy(plan["validation"])
    archive={"archive_source_root":execution["archive_source_root"],"archive_runtime_root":execution["archive_runtime_root"]}
    thresholds={0:float(i19["logical_results"]["thresholds"]["building"]),1:float(i19["logical_results"]["thresholds"]["road"])}
    train=AugmentedPairDataset(spec["dataset_manifest"]["path"],args.tensor_contract,"training",augmentation,thresholds,**archive)
    valid=AugmentedPairDataset(spec["dataset_manifest"]["path"],args.tensor_contract,"validation",augmentation,thresholds,validation=True,**archive)
    masks={name:next(iter(values)) for name,values in train.base.category_mask_index.items()};workers=int(execution["workers_per_rank"])
    sampler=RankLogicalGroupSampler(train.base.rows,spec["hard_budgets"],seed,rank)
    loader=DataLoader(train,sampler=RankSceneSampler(sampler),batch_size=None,num_workers=workers,collate_fn=identity_collate,
        persistent_workers=True,pin_memory=True,prefetch_factor=int(execution["prefetch_factor"]),worker_init_fn=worker_init,multiprocessing_context="spawn")
    valid_sampler=RankLogicalGroupSampler(valid.base.rows,spec["hard_budgets"],seed,rank);valid_sampler.permutation=lambda:list(range(32))
    valid_loader=DataLoader(valid,batch_sampler=valid_sampler,num_workers=workers,collate_fn=collate_pairs,
        persistent_workers=True,pin_memory=True,prefetch_factor=int(execution["prefetch_factor"]),worker_init_fn=worker_init,multiprocessing_context="spawn")
    device=torch.device(f"cuda:{rank}");results=[]
    for lr in args.learning_rate:
        try:
            results.append(run_candidate(rank,lr,args.epochs,seed,spec,joint,encoder,masks,device,loader,valid_loader,sampler,validation))
        except (RuntimeError,ValueError) as error:
            results.append({"learning_rate":lr,"status":"REJECTED_BY_SAFETY_OR_RUNTIME_GUARD","error":str(error)})
            dist.barrier();torch.cuda.empty_cache()
    if loader._iterator is not None:loader._iterator._shutdown_workers()
    if valid_loader._iterator is not None:valid_loader._iterator._shutdown_workers()
    if rank==0:
        value={"status":"PASS","mode":"isolated_diagnostic_no_checkpoint_ledger_or_publication","world_size":2,
            "workers_total":40,"epochs_per_candidate":args.epochs,"candidates":results,
            "formal_training_invocations":0,"diagnostic_gpu_invocations":1,"publication_count":0}
        output=Path(args.output);temporary=output.with_suffix(output.suffix+".tmp")
        temporary.write_text(json.dumps(value,sort_keys=True,indent=2)+"\n");os.replace(temporary,output)
    dist.barrier();dist.destroy_process_group()


def main()->None:
    args=arguments()
    if torch.cuda.device_count()<2:raise RuntimeError("LR diagnostic requires two visible CUDA devices")
    os.environ.setdefault("MASTER_ADDR","127.0.0.1");os.environ.setdefault("MASTER_PORT","29631")
    mp.spawn(worker,args=(args,),nprocs=2,join=True)


if __name__=="__main__":main()
