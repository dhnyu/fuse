#!/usr/bin/env python3
"""Execute the accepted two-process DDP I21 prototype run."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import random
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Iterator

for _name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_name] = "1"

import jsonschema
import numpy as np
import psutil
import torch
import torch.distributed as dist
import torch.multiprocessing as mp
import yaml
from torch.nn.parallel import DistributedDataParallel
from torch.utils.data import DataLoader, Sampler

from prototype_dataloader import canonical_json_bytes, sha256_file
from prototype_ddp_joint_model import DistributedJointPrototypeModel
from prototype_encoder import geometry_fourier_features
from prototype_joint_model import (
    MODALITIES, RECONSTRUCTION_FIELDS, apply_global_reconstruction_counts, enqueue,
    information_preservation_loss, modality_mask_assignments, reconstruction_losses,
    reconstruction_valid_counts,
)
from run_prototype_training import (
    AugmentedPairDataset, collate_pairs, device_batch, make_optimizer, modality_counts,
    query_loss, save_checkpoint, stable_integer, state_digest, worker_init,
)


class RankLogicalGroupSampler(Sampler[list[tuple[int, int, int]]]):
    def __init__(self, rows: list[dict[str, Any]], budgets: dict[str, int], seed: int, rank: int) -> None:
        self.rows, self.budgets, self.seed, self.rank, self.epoch = rows, budgets, int(seed), int(rank), 0

    def set_epoch(self, epoch: int) -> None: self.epoch = int(epoch)

    def permutation(self) -> list[int]:
        rng=np.random.Generator(np.random.PCG64(stable_integer(self.seed,self.epoch,"sampler")))
        return rng.permutation(len(self.rows)).tolist()

    def batches(self) -> list[list[tuple[int,int,int]]]:
        order=self.permutation()
        if len(order)%32:raise ValueError("population is not divisible by global effective batch 32")
        output=[]
        for group,start in enumerate(range(0,len(order),32)):
            global_group=order[start:start+32]
            fields={"nodes":"node_count","ordered_edges":"ordered_edge_count","coordinates":"coordinate_count",
                    "actual_payload_bytes":"actual_payload_bytes"}
            ranked=sorted(global_group,key=lambda position:(
                -sum(float(self.rows[position][field])/float(self.budgets[name]) for name,field in fields.items()),
                self.rows[position]["scene_id"]))
            assignments=[[],[]];loads=[0.0,0.0]
            for position in ranked:
                cost=sum(float(self.rows[position][field])/float(self.budgets[name]) for name,field in fields.items())
                eligible=[rank for rank in (0,1) if len(assignments[rank])<16]
                selected=min(eligible,key=lambda rank:(loads[rank],rank))
                assignments[selected].append(position);loads[selected]+=cost
            def pack(rank:int)->list[list[int]]:
                selected_set=set(assignments[rank]);local=[position for position in global_group if position in selected_set]
                if len(local)!=16:raise RuntimeError("deterministic rank balancing did not assign 16 scenes")
                packed=[];current=[];load={name:0 for name in self.budgets}
                for position in local:
                    row=self.rows[position];cost={"scenes":1,"nodes":int(row["node_count"]),
                        "ordered_edges":int(row["ordered_edge_count"]),"coordinates":int(row["coordinate_count"]),
                        "actual_payload_bytes":int(row["actual_payload_bytes"])}
                    if current and any(load[key]+cost[key]>int(self.budgets[key]) for key in self.budgets):
                        packed.append(current);current=[];load={name:0 for name in self.budgets}
                    current.append(position)
                    for key in load:load[key]+=cost[key]
                if current:packed.append(current)
                return packed
            packed=[pack(0),pack(1)];target=max(map(len,packed))
            for rank in (0,1):
                while len(packed[rank])<target:
                    candidates=[(len(batch),-offset,offset) for offset,batch in enumerate(packed[rank]) if len(batch)>1]
                    if not candidates:raise RuntimeError("cannot equalize rank microbatch counts")
                    _,_,offset=max(candidates);batch=packed[rank].pop(offset);split=(len(batch)+1)//2
                    packed[rank][offset:offset]=[batch[:split],batch[split:]]
            output.extend([[(position,self.epoch,group) for position in batch] for batch in packed[self.rank]])
        selected=getattr(self,"selected_group",None)
        return output if selected is None else [batch for batch in output if batch[0][2]==int(selected)]

    def __iter__(self)->Iterator[list[tuple[int,int,int]]]:return iter(self.batches())
    def __len__(self)->int:return len(self.batches())


def take_local_group(loader: DataLoader) -> list[dict[str, Any]]:
    batches=[]
    for item in loader:
        if batches and int(item["group"])!=int(batches[0]["group"]):break
        batches.append(item);count=sum(len(value["positions"]) for value in batches)
        if count==16:return batches
        if count>16:raise ValueError("rank-local logical group exceeds 16 scenes")
    raise ValueError("could not assemble complete rank-local logical group")


def empty_queue(device: torch.device)->dict[str,Any]:
    return {"values":torch.zeros((8192,128),device=device),
            "scene_ids":torch.full((8192,),-1,dtype=torch.int64,device=device),
            "centers":torch.zeros((8192,2),device=device),"pointer":0,"occupancy":0}


def gather_metadata(local_batches:list[dict[str,Any]],device:torch.device)->tuple[list[str],torch.Tensor,dict[str,int],list[int]]:
    local_ids=[scene for item in local_batches for scene in item["views"][0]["scene_ids"]]
    local_centers=[center for item in local_batches for center in item["centers"]]
    values=[None,None];dist.all_gather_object(values,(local_ids,local_centers))
    gathered_ids=[scene for value in values for scene in value[0]]
    gathered_centers=[center for value in values for center in value[1]]
    if len(gathered_ids)!=32 or len(set(gathered_ids))!=32:raise ValueError("global logical group is not 32 unique scenes")
    order=sorted(range(32),key=lambda offset:gathered_ids[offset]);scene_ids=[gathered_ids[offset] for offset in order]
    centers=torch.tensor([gathered_centers[offset] for offset in order],device=device,dtype=torch.float32)
    return scene_ids,centers,{scene:index for index,scene in enumerate(scene_ids)},order


def global_reconstruction_counts(batches:list[list[dict[str,Any]]], geometries:list[list[tuple[torch.Tensor,torch.Tensor]]],
                                 joint:dict[str,Any],device:torch.device)->dict[str,dict[str,int]]:
    names=[*(f"modalities.{name}" for name in MODALITIES),*(f"fields.{name}" for name in RECONSTRUCTION_FIELDS)]
    local={name:0 for name in names}
    for pair,geometry_pair in zip(batches,geometries,strict=True):
        for view in (0,1):
            current=reconstruction_valid_counts(pair[view],geometry_pair[view],joint)
            for namespace in ("modalities","fields"):
                for name,value in current[namespace].items():local[f"{namespace}.{name}"]+=int(value)
    tensor=torch.tensor([local[name] for name in names],device=device,dtype=torch.int64);dist.all_reduce(tensor)
    result={"modalities":{},"fields":{}}
    for index,qualified in enumerate(names):
        namespace,name=qualified.split(".",1);result[namespace][name]=int(tensor[index])
    return result


def train_group(ddp:DistributedDataParallel,model:DistributedJointPrototypeModel,cpu_batches:list[dict[str,Any]],
                optimizer:Any,scheduler:Any,queue:dict[str,Any],spec:dict[str,Any],joint:dict[str,Any],
                encoder:dict[str,Any],masks:dict[str,int],device:torch.device,epoch:int,perform_update:bool=True)->dict[str,Any]:
    scene_ids,centers,index,canonical_order=gather_metadata(cpu_batches,device);batches=[];geometries=[];local_keys=[[],[]];sizes=[]
    for item in cpu_batches:
        pair=[device_batch(item["views"][view],device,masks) for view in (0,1)]
        geometry_pair=[geometry_fourier_features(pair[view],encoder,device) for view in (0,1)]
        batches.append(pair);geometries.append(geometry_pair);sizes.append(len(pair[0]["scene_ids"]))
        with torch.no_grad():
            for view in (0,1):
                local_keys[view].append(model.forward_target(pair[view],geometry_pair[view])["projection"])
    global_counts=global_reconstruction_counts(batches,geometries,joint,device)
    active=sum(value>0 for value in global_counts["modalities"].values())
    keys=[]
    for view in (0,1):
        local=torch.cat(local_keys[view]);gathered=[torch.empty_like(local) for _ in range(2)];dist.all_gather(gathered,local)
        combined=torch.cat(gathered);keys.append(combined[torch.tensor(canonical_order,device=device,dtype=torch.int64)])
    all_keys=torch.cat(keys);optimizer.zero_grad(set_to_none=True);local_scene=0.0;local_ip=0.0
    calls=len(batches)*2;call_index=0
    for batch_index,(pair,geometry_pair,size) in enumerate(zip(batches,geometries,sizes,strict=True)):
        for view in (0,1):
            context=ddp.no_sync() if call_index<calls-1 else __import__("contextlib").nullcontext()
            with context:
                geometry=geometry_pair[view]
                assignments=modality_mask_assignments(pair[view],int(spec["seed"]),epoch,view,float(joint["modality_masking"]["selection_probability"]))
                output=ddp(pair[view],geometry,assignments,int(spec["seed"]),epoch,view)
                indices=[index[scene] for scene in pair[view]["scene_ids"]]
                positive=keys[1-view]
                scene_component=query_loss(output.outputs["projection"],indices,positive,all_keys,centers,
                    queue["values"],queue["centers"],queue["occupancy"],float(spec["optimizer"]["temperature"]),
                    float(spec["optimizer"]["geographic_negative_exclusion_radius_m"]))/64.0
                losses=reconstruction_losses(model,pair[view],geometry,output.modalities,joint)
                local_counts=modality_counts(cpu_batches[batch_index]["views"][view],masks)
                if any(losses["modalities"][name]["local_valid_count"]!=local_counts[name] for name in MODALITIES):
                    raise RuntimeError("reconstruction count contract mismatch")
                apply_global_reconstruction_counts(losses,global_counts)
                ip_component=information_preservation_loss(losses,global_counts["modalities"])
                contribution=scene_component+float(joint["loss"]["information_preservation_weight"])*ip_component
                if call_index==calls-1:
                    reducer_anchor=torch.stack([parameter.reshape(-1)[0]*0.0 for parameter in model.parameters()
                                                if parameter.requires_grad]).sum()
                    contribution=contribution+reducer_anchor
                if not torch.isfinite(contribution):raise ValueError("non-finite distributed training loss")
                (contribution*2.0).backward()
            local_scene+=float(scene_component.detach());local_ip+=float(ip_component.detach());call_index+=1
    invalid=[name for name,p in model.named_parameters() if p.requires_grad and (p.grad is None or not torch.isfinite(p.grad).all())]
    routing=torch.tensor([sum(p.grad is not None and bool(torch.count_nonzero(p.grad)) for p in model.parameters() if p.requires_grad)],device=device)
    routing_values=[torch.empty_like(routing) for _ in range(2)];dist.all_gather(routing_values,routing)
    if invalid or len({int(value) for value in routing_values})!=1 or int(routing)!=280:
        raise ValueError(f"distributed gradient coverage/routing failed invalid={invalid} counts={[int(x) for x in routing_values]}")
    gradient_norm=torch.nn.utils.clip_grad_norm_([p for p in model.parameters() if p.requires_grad],float(spec["optimizer"]["gradient_norm_clip"]))
    applied_lr=float(optimizer.param_groups[0]["lr"])
    if perform_update:
        optimizer.step();scheduler.step();model.update_target(float(spec["optimizer"]["ema_momentum"]))
        numeric=torch.tensor([stable_integer(scene)&((1<<63)-1) for scene in scene_ids],dtype=torch.int64,device=device)
        values=torch.stack(keys,dim=1).reshape(64,128)
        queue["pointer"],queue["occupancy"]=enqueue(queue["values"],queue["scene_ids"],queue["centers"],queue["pointer"],queue["occupancy"],
            values,numeric.repeat_interleave(2),centers.repeat_interleave(2,0))
    totals=torch.tensor([local_scene,local_ip],device=device,dtype=torch.float64);dist.all_reduce(totals)
    digests=[item["i19_digests"] for item in cpu_batches];all_digests=[None,None];dist.all_gather_object(all_digests,digests)
    return {"total_loss":float(totals[0])+float(joint["loss"]["information_preservation_weight"])*float(totals[1]),
            "scene_loss":float(totals[0]),"information_preservation_loss":float(totals[1]),
            "gradient_norm":float(gradient_norm),"learning_rate":applied_lr,"rank_microbatch_sizes":sizes,
            "augmentation_digest":state_digest(all_digests)}


def sync_digest(model:Any,optimizer:Any,scheduler:Any,queue:dict[str,Any],device:torch.device)->str:
    value=state_digest({"model":model.state_dict(),"optimizer":optimizer.state_dict(),"scheduler":scheduler.state_dict(),"queue":queue})
    values=[None,None];dist.all_gather_object(values,value)
    if len(set(values))!=1:raise RuntimeError(f"rank scientific state drift: {values}")
    return value


def local_rng_state(rank:int,progress:dict[str,Any])->dict[str,Any]:
    return {"rank":rank,"python_rng":random.getstate(),"numpy_rng":np.random.get_state(),"torch_cpu_rng":torch.get_rng_state(),
            "torch_cuda_rng":torch.cuda.get_rng_state(),"sampler_epoch":progress["epoch"],
            "sampler_permutation":progress["permutation"],"sampler_position":progress["group_position"],
            "accumulation_scene_count":0,"accumulation_gradient_state":{}}


def checkpoint_payload(model:Any,optimizer:Any,scheduler:Any,queue:dict[str,Any],progress:dict[str,Any],rank:int)->dict[str,Any]|None:
    local=local_rng_state(rank,progress);rank_states=[None,None];dist.all_gather_object(rank_states,local)
    if rank:return None
    return {"online_model":model.online.state_dict(),"target_model":model.target.state_dict(),
        "projection_and_decoders":{"mask":model.modality_mask_embeddings.detach(),"decoders":model.decoders.state_dict()},
        "optimizer":optimizer.state_dict(),"scheduler":scheduler.state_dict(),"ema_update_count":progress["optimizer_step"],
        "queue_values":queue["values"],"queue_scene_ids":queue["scene_ids"],"queue_scene_centers":queue["centers"],
        "queue_pointer":queue["pointer"],"queue_occupancy":queue["occupancy"],"distributed_rank_states":rank_states,
        "best_checkpoint_metric_state":progress["best"],"validation_history":progress["validation"],
        "early_stopping_patience_state":progress["patience"],"optimizer_step":progress["optimizer_step"],
        "scene_consumptions":progress["scene_consumptions"],"scientific_parents":progress["parents"],
        "run_id":progress["run_id"],"seed":progress["seed"],"schema_version":"2.0.0","world_size":2}


def restore(path:Path,model:Any,optimizer:Any,scheduler:Any,queue:dict[str,Any],rank:int)->dict[str,Any]:
    state=torch.load(path,map_location="cpu",weights_only=False)
    if state.get("world_size")!=2:raise ValueError("checkpoint is not an accepted two-rank state")
    model.online.load_state_dict(state["online_model"]);model.target.load_state_dict(state["target_model"])
    model.modality_mask_embeddings.data.copy_(state["projection_and_decoders"]["mask"]);model.decoders.load_state_dict(state["projection_and_decoders"]["decoders"])
    optimizer.load_state_dict(state["optimizer"]);scheduler.load_state_dict(state["scheduler"])
    for key,source in (("values","queue_values"),("scene_ids","queue_scene_ids"),("centers","queue_scene_centers")):queue[key].copy_(state[source].to(queue[key].device))
    queue["pointer"],queue["occupancy"]=int(state["queue_pointer"]),int(state["queue_occupancy"])
    local=state["distributed_rank_states"][rank];random.setstate(local["python_rng"]);np.random.set_state(local["numpy_rng"])
    torch.set_rng_state(local["torch_cpu_rng"]);torch.cuda.set_rng_state(local["torch_cuda_rng"])
    return state


def distributed_validation(model:Any,loader:DataLoader,encoder:dict[str,Any],masks:dict[str,int],device:torch.device)->dict[str,Any]:
    model.eval();local=[]
    with torch.no_grad():
        for item in loader:
            for scene_offset,scene_id in enumerate(item["views"][0]["scene_ids"]):
                record={"scene_id":scene_id,"embeddings":[]}
                for view in range(3):
                    batch=device_batch(item["views"][view],device,masks);geometry=geometry_fourier_features(batch,encoder,device)
                    assignments=torch.full((batch["entities"]["entity_type"].numel(),),-1,dtype=torch.int64,device=device)
                    embedding=model.forward_online(batch,geometry,assignments).outputs["scene_embedding"][scene_offset]
                    record["embeddings"].append(embedding.cpu())
                local.append(record)
    gathered=[None,None];dist.all_gather_object(gathered,local);records=sorted([x for values in gathered for x in values],key=lambda x:x["scene_id"])
    candidates=torch.stack([x["embeddings"][2] for x in records]).to(device)
    queries=torch.cat((torch.stack([x["embeddings"][0] for x in records]),torch.stack([x["embeddings"][1] for x in records]))).to(device)
    similarity=queries@candidates.T;target=torch.arange(32,device=device).repeat(2);order=torch.argsort(similarity,dim=1,descending=True,stable=True)
    ranks=torch.nonzero(order==target[:,None])[:,1]+1
    result={"MRR":float((1.0/ranks.float()).mean()),"HIT@1":float((ranks<=1).float().mean()),
            "HIT@5":float((ranks<=5).float().mean()),"HIT@10":float((ranks<=10).float().mean()),"population":32,
            "embedding_digest":state_digest((queries,candidates)),"retrieval_digest":state_digest((order,ranks)),
            "scene_ids_digest":state_digest([x["scene_id"] for x in records])}
    model.train();model.target.eval();return result


def run(rank:int,world_size:int,args:argparse.Namespace)->None:
    os.environ.update(RANK=str(rank),WORLD_SIZE=str(world_size),LOCAL_RANK=str(rank));torch.cuda.set_device(rank)
    torch.set_num_threads(1);torch.use_deterministic_algorithms(True);torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
    dist.init_process_group("nccl",rank=rank,world_size=world_size,device_id=torch.device(f"cuda:{rank}"))
    spec=json.loads(Path(args.run_spec).read_text());training=yaml.safe_load(Path(args.training_config).read_text());joint=yaml.safe_load(Path(args.joint_config).read_text())
    encoder=yaml.safe_load(Path(args.encoder_config).read_text());augmentation=yaml.safe_load(Path(args.augmentation_config).read_text());i19=json.loads(Path(args.i19_manifest).read_text())
    if spec["execution_mode"]!="two_process_ddp" or int(spec["requested_gpu_count"])!=2:raise ValueError("I20 is not a two-rank DDP run")
    if spec["run_id"]!=training["identity"]["run_id"] or spec["plan_id"]!=training["identity"]["plan_id"]:raise ValueError("I21 plan/run mismatch")
    parents={"dataset":spec["dataset_manifest"],"loader":spec["dataloader_manifest"],"gate":spec["no_op_gate_manifest"],
             "encoder":spec["encoder_manifest"],"augmentation":spec["augmentation_manifest"],"joint":spec["joint_model_manifest"],
             "distributed_joint":spec["distributed_joint_model_manifest"]}
    for name,record in parents.items():
        path=Path(record["path"])
        if not path.is_file() or path.stat().st_size!=int(record["size_bytes"]) or sha256_file(path)!=record["sha256"]:raise ValueError(f"upstream mismatch: {name}")
    thresholds={0:float(i19["logical_results"]["thresholds"]["building"]),1:float(i19["logical_results"]["thresholds"]["road"])}
    seed=int(spec["seed"]);random.seed(seed);np.random.seed(seed);torch.manual_seed(seed);torch.cuda.manual_seed_all(seed)
    train=AugmentedPairDataset(spec["dataset_manifest"]["path"],args.tensor_contract,"training",augmentation,thresholds)
    valid=AugmentedPairDataset(spec["dataset_manifest"]["path"],args.tensor_contract,"validation",augmentation,thresholds,validation=True)
    if len(train)!=256 or len(valid)!=32:raise ValueError("split population mismatch")
    masks={name:next(iter(values)) for name,values in train.base.category_mask_index.items()};workers=int(training["execution"]["workers_per_rank"])
    sampler=RankLogicalGroupSampler(train.base.rows,spec["hard_budgets"],seed,rank)
    if args.preflight_group is not None:sampler.selected_group=int(args.preflight_group)
    loader=DataLoader(train,batch_sampler=sampler,num_workers=workers,collate_fn=collate_pairs,persistent_workers=True,pin_memory=True,
                      prefetch_factor=2,worker_init_fn=worker_init,multiprocessing_context="spawn")
    valid_sampler=RankLogicalGroupSampler(valid.base.rows,spec["hard_budgets"],seed,rank);valid_sampler.permutation=lambda:list(range(32))
    valid_loader=DataLoader(valid,batch_sampler=valid_sampler,num_workers=workers,collate_fn=collate_pairs,persistent_workers=True,pin_memory=True,
                            prefetch_factor=2,worker_init_fn=worker_init,multiprocessing_context="spawn")
    device=torch.device(f"cuda:{rank}");model=DistributedJointPrototypeModel(encoder,joint).to(device).train();model.target.eval()
    if sum(p.numel() for p in model.parameters() if p.requires_grad)!=2665140:raise ValueError("joint parameter count mismatch")
    ddp=DistributedDataParallel(model,device_ids=[rank],broadcast_buffers=False,find_unused_parameters=False)
    optimizer,scheduler=make_optimizer(model,spec);queue=empty_queue(device)
    output_root=Path(spec["output_root"]);mutable=output_root/"mutable-ddp";immutable=output_root/"acceptance";checkpoints=mutable/"checkpoints"
    if rank==0:mutable.mkdir(parents=True,exist_ok=True);checkpoints.mkdir(parents=True,exist_ok=True)
    dist.barrier();step_log=mutable/training["output"]["steps_name"];telemetry_log=mutable/training["output"]["telemetry_name"]
    progress={"epoch":0,"group_position":0,"permutation":[],"optimizer_step":0,"scene_consumptions":0,"best":None,"validation":[],"patience":0,
              "parents":{key:value["sha256"] for key,value in parents.items()},"run_id":spec["run_id"],"seed":seed}
    preflight_epoch=int(args.preflight_epoch or 0)
    sampler.set_epoch(preflight_epoch);progress["permutation"]=sampler.permutation()
    if len(set(progress["permutation"]))!=256:raise ValueError("sampler duplication/omission")
    initial=checkpoint_payload(model,optimizer,scheduler,queue,progress,rank)
    if rank==0:initial_record=save_checkpoint(checkpoints/"initial-step-000000.pt",initial)
    dist.barrier();restore(checkpoints/"initial-step-000000.pt",model,optimizer,scheduler,queue,rank);sync_digest(model,optimizer,scheduler,queue,device)
    first=take_local_group(loader);second=take_local_group(loader)
    local_repeat=state_digest([(x["positions"],x["i19_digests"],x["tensor_digests"]) for x in first])==state_digest([(x["positions"],x["i19_digests"],x["tensor_digests"]) for x in second])
    repeat_tensor=torch.tensor([int(local_repeat)],device=device);dist.all_reduce(repeat_tensor)
    if int(repeat_tensor)!=2:raise RuntimeError("40-worker DDP DataLoader repeat mismatch")
    dry=train_group(ddp,model,first,optimizer,scheduler,queue,spec,joint,encoder,masks,device,preflight_epoch,False)
    if optimizer.state or queue["occupancy"] or scheduler.last_epoch!=0:raise RuntimeError("dry step mutated state")
    restore(checkpoints/"initial-step-000000.pt",model,optimizer,scheduler,queue,rank)
    if args.preflight_through_epoch2_first:
        restore(checkpoints/"initial-step-000000.pt",model,optimizer,scheduler,queue,rank);fixture=[]
        for fixture_epoch in (0,1):
            sampler.selected_group=None;sampler.set_epoch(fixture_epoch);group_batches=[];current_group=0
            for item in loader:
                group=int(item["group"]);group_batches.append(item)
                if sum(len(value["positions"]) for value in group_batches)<16:continue
                result=train_group(ddp,model,group_batches,optimizer,scheduler,queue,spec,joint,encoder,masks,device,fixture_epoch)
                fixture.append({"epoch":fixture_epoch+1,"group":group,"loss":result["total_loss"],"digest":sync_digest(model,optimizer,scheduler,queue,device)})
                group_batches=[];current_group=group+1
                if fixture_epoch==1:break
        if len(fixture)!=9:raise RuntimeError(f"epoch1/epoch2-first regression executed {len(fixture)} groups")
        if rank==0:print(json.dumps({"status":"PASS","preflight":{"workers_total":40,"workers_per_rank":20,
            "dry_loss":dry["total_loss"],"epoch1_and_epoch2_first_groups":fixture}},sort_keys=True))
        if loader._iterator is not None:loader._iterator._shutdown_workers()
        if valid_loader._iterator is not None:valid_loader._iterator._shutdown_workers()
        dist.destroy_process_group();return
    if args.preflight_only:
        if rank==0:print(json.dumps({"status":"PASS","preflight":{"workers_total":40,"workers_per_rank":20,"epoch":preflight_epoch+1,"dry_loss":dry["total_loss"]}},sort_keys=True))
        if loader._iterator is not None:loader._iterator._shutdown_workers()
        if valid_loader._iterator is not None:valid_loader._iterator._shutdown_workers()
        dist.destroy_process_group();return
    started=time.time();checkpoint_records=[];exact_resume=None;termination="maximum_epochs"
    for epoch in range(int(spec["optimizer"]["maximum_epochs"])):
        sampler.set_epoch(epoch);progress.update(epoch=epoch,permutation=sampler.permutation(),group_position=0)
        group_batches=[];current_group=0
        for item in loader:
            group=int(item["group"])
            if group!=current_group and group_batches:raise RuntimeError("loader crossed group")
            group_batches.append(item);count=sum(len(x["positions"]) for x in group_batches)
            if count<16:continue
            if count!=16:raise ValueError("partial/oversized rank group")
            result=train_group(ddp,model,group_batches,optimizer,scheduler,queue,spec,joint,encoder,masks,device,epoch)
            progress["optimizer_step"]+=1;progress["scene_consumptions"]+=32;progress["group_position"]=group+1
            state=sync_digest(model,optimizer,scheduler,queue,device)
            row={"epoch":epoch+1,"logical_group":group,"optimizer_step":progress["optimizer_step"],"scenes_consumed":32,
                 "effective_batch_size":32,"ema_update_count":progress["optimizer_step"],"queue_pointer":queue["pointer"],
                 "queue_occupancy":queue["occupancy"],"rank_state_digest":state,**result}
            if rank==0:
                with step_log.open("ab") as stream:stream.write(canonical_json_bytes(row)+b"\n")
            process=psutil.Process();local_telemetry={"rank":rank,"optimizer_step":progress["optimizer_step"],
                "process_tree_rss_bytes":process.memory_info().rss+sum(child.memory_info().rss for child in process.children(recursive=True) if child.is_running()),
                "gpu_allocated_bytes":torch.cuda.memory_allocated(),"gpu_reserved_bytes":torch.cuda.memory_reserved(),
                "gpu_peak_allocated_bytes":torch.cuda.max_memory_allocated(),"queue_occupancy":queue["occupancy"]}
            telemetry_values=[None,None];dist.all_gather_object(telemetry_values,local_telemetry)
            if rank==0:
                with telemetry_log.open("ab") as stream:stream.write(canonical_json_bytes({"optimizer_step":progress["optimizer_step"],"ranks":telemetry_values})+b"\n")
            if progress["optimizer_step"]==1:
                payload=checkpoint_payload(model,optimizer,scheduler,queue,progress,rank)
                if rank==0:save_checkpoint(checkpoints/"controlled-step-000001.pt",payload)
                dist.barrier()
            elif progress["optimizer_step"]==2 and exact_resume is None:
                direct=state;direct_result=copy.deepcopy(result)
                restore(checkpoints/"controlled-step-000001.pt",model,optimizer,scheduler,queue,rank)
                replay=train_group(ddp,model,group_batches,optimizer,scheduler,queue,spec,joint,encoder,masks,device,epoch)
                replay_state=sync_digest(model,optimizer,scheduler,queue,device)
                if direct!=replay_state or state_digest(direct_result)!=state_digest(replay):raise RuntimeError("controlled DDP resume mismatch")
                exact_resume={"status":"PASS","checkpoint_step":1,"comparison_steps":1,"direct_state_digest":direct,
                              "replay_state_digest":replay_state,"augmentation_digest":replay["augmentation_digest"]}
            group_batches=[];current_group=group+1
        if group_batches:raise ValueError("epoch ended with partial rank group")
        if (epoch+1)%int(spec["validation"]["interval_epochs"])==0:
            metrics=distributed_validation(model,valid_loader,encoder,masks,device);metrics["epoch"]=epoch+1;progress["validation"].append(metrics)
            best=progress["best"];improved=best is None or metrics["MRR"]>best["MRR"]
            selected=best is None or (metrics["MRR"],metrics["HIT@1"],-(epoch+1))>(best["MRR"],best["HIT@1"],-best["epoch"])
            progress["patience"]=0 if improved else progress["patience"]+1
            if selected:progress["best"]=dict(metrics)
            payload=checkpoint_payload(model,optimizer,scheduler,queue,progress,rank)
            if rank==0:
                record=save_checkpoint(checkpoints/f"epoch-{epoch+1:03d}.pt",payload);record["epoch"]=epoch+1;checkpoint_records.append(record)
                if progress["best"]["epoch"]==epoch+1:progress["best"]["checkpoint"]=record
            best_values=[progress["best"] if rank==0 else None];dist.broadcast_object_list(best_values,src=0);progress["best"]=best_values[0]
            if progress["patience"]>=int(spec["validation"]["early_stopping_patience_evaluations"]):termination="early_stopping";break
    if exact_resume is None:raise RuntimeError("controlled resume not completed")
    best_path_values=[progress["best"]["checkpoint"]["path"] if rank==0 else None];dist.broadcast_object_list(best_path_values,src=0)
    peak={"rank":rank,"allocated":int(torch.cuda.max_memory_allocated()),"reserved":int(torch.cuda.max_memory_reserved())}
    peak_values=[None,None];dist.all_gather_object(peak_values,peak)
    if loader._iterator is not None:loader._iterator._shutdown_workers()
    del ddp,model,optimizer,scheduler,queue;torch.cuda.empty_cache()
    reproduced_model=DistributedJointPrototypeModel(encoder,joint).to(device).eval();reproduced_optimizer,reproduced_scheduler=make_optimizer(reproduced_model,spec)
    reproduced_queue=empty_queue(device);restore(Path(best_path_values[0]),reproduced_model,reproduced_optimizer,reproduced_scheduler,reproduced_queue,rank)
    reproduction=distributed_validation(reproduced_model,valid_loader,encoder,masks,device)
    expected_reproduction={key:progress["best"][key] for key in ("MRR","HIT@1","HIT@5","HIT@10","population","embedding_digest","retrieval_digest","scene_ids_digest")}
    if reproduction!=expected_reproduction:raise RuntimeError("reloaded best-checkpoint distributed validation mismatch")
    if valid_loader._iterator is not None:valid_loader._iterator._shutdown_workers()
    if rank==0:
        final_checkpoint=checkpoint_records[-1];best_checkpoint=progress["best"]["checkpoint"]
        scientific={"plan_id":spec["plan_id"],"run_id":spec["run_id"],"parents":progress["parents"],
            "run_spec_sha256":sha256_file(args.run_spec),"training_contract_sha256":sha256_file(args.training_config),
            "training_implementation_sha256":sha256_file(Path(__file__)),"seed":seed,
            "numerical_policy":"two_process_ddp_float32_no_tf32","world_size":2}
        acceptance="pta_"+hashlib.sha256(canonical_json_bytes(scientific)).hexdigest()[:24]
        final_dir=immutable/acceptance;immutable.mkdir(parents=True,exist_ok=True);stage=Path(tempfile.mkdtemp(prefix=f".{acceptance}.stage-",dir=immutable))
        validation_path=stage/training["output"]["validation_name"];validation_path.write_bytes(canonical_json_bytes(progress["validation"]))
        qc={"status":"PASS","optimizer_step_performed":True,"world_size":2,"worker_count":40,"workers_per_rank":20,
            "exact_resume":exact_resume,"peak_vram_by_rank":peak_values,
            "elapsed_seconds":time.time()-started,"checkpoint_count":len(checkpoint_records)}
        qc_path=stage/training["output"]["qc_name"];qc_path.write_bytes(canonical_json_bytes(qc))
        outputs=[{"relative_path":x.name,"size_bytes":x.stat().st_size,"sha256":sha256_file(x)} for x in (qc_path,validation_path)]
        manifest={"schema_version":"1.0.0","status":"PASS","training_acceptance_id":acceptance,"plan_id":spec["plan_id"],"run_id":spec["run_id"],
            "scientific_identity":scientific,"completion":{"epochs_completed":progress["epoch"]+1,"optimizer_steps":progress["optimizer_step"],
            "training_scene_consumptions":progress["scene_consumptions"],"termination":termination},"validation_history":progress["validation"],
            "best_checkpoint":best_checkpoint,"final_checkpoint":final_checkpoint,"exact_resume":exact_resume,"resources":qc,
            "fresh_process_validation":reproduction,"outputs":outputs}
        jsonschema.validate(manifest,json.loads(Path(args.schema).read_text()));manifest_path=stage/training["output"]["manifest_name"];manifest_path.write_bytes(canonical_json_bytes(manifest))
        if final_dir.exists():
            existing=json.loads((final_dir/manifest_path.name).read_text())
            if canonical_json_bytes(existing)!=canonical_json_bytes(manifest):raise RuntimeError("same DDP I21 ID has different content")
            shutil.rmtree(stage);publish="identical_reuse"
        else:os.replace(stage,final_dir);publish="new_publish"
        print(json.dumps({"status":"PASS","training_acceptance_id":acceptance,"publish_status":publish,
                          "output_files":[str(final_dir/name) for name in (qc_path.name,validation_path.name,manifest_path.name)]},sort_keys=True))
    dist.barrier();dist.destroy_process_group()


def main()->None:
    parser=argparse.ArgumentParser()
    for name in ("run-spec","training-config","joint-config","encoder-config","augmentation-config","tensor-contract","i19-manifest","schema"):
        parser.add_argument(f"--{name}",required=True)
    parser.add_argument("--preflight-group",type=int)
    parser.add_argument("--preflight-epoch",type=int)
    parser.add_argument("--preflight-through-epoch2-first",action="store_true")
    parser.add_argument("--preflight-only",action="store_true");args=parser.parse_args()
    os.environ.setdefault("MASTER_ADDR","127.0.0.1");os.environ.setdefault("MASTER_PORT","29621")
    mp.spawn(run,args=(2,args),nprocs=2,join=True)


if __name__=="__main__":main()
