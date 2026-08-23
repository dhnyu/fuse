#!/usr/bin/env python3
"""Exact 32-scene joint-objective parity for two-rank DDP."""

from __future__ import annotations

import argparse, io, json, math, os, socket, tempfile
from pathlib import Path
from typing import Any

import torch, torch.distributed as dist, torch.multiprocessing as mp, yaml
from torch.nn.parallel import DistributedDataParallel

from prototype_dataloader import AcceptedPrototypeDataset, ragged_collate
from prototype_encoder import geometry_fourier_features
from prototype_joint_model import enqueue, information_preservation_loss, modality_mask_assignments, reconstruction_losses
from prototype_ddp_joint_model import DistributedJointPrototypeModel
from prototype_ddp_exact_probe import digest_state
from run_prototype_training import device_batch, modality_counts, query_loss


def port() -> int:
    with socket.socket() as stream: stream.bind(("127.0.0.1", 0)); return int(stream.getsockname()[1])


def prepare_model(config: dict[str, Any], joint: dict[str, Any], device: torch.device, seed: int) -> DistributedJointPrototypeModel:
    torch.manual_seed(seed); torch.cuda.manual_seed_all(seed)
    model = DistributedJointPrototypeModel(config, joint).to(device).train(); model.target.eval(); return model


def counts(batches: list[dict[str, Any]], masks: dict[str, int]) -> dict[str, int]:
    names = ("relative", "geometry", "semantic", "environmental")
    return {name: sum(modality_counts(batch, masks)[name] for batch in batches) for name in names}


def target_keys(model: DistributedJointPrototypeModel, batches: list[dict[str, Any]], config: dict[str, Any],
                masks: dict[str, int], device: torch.device) -> list[torch.Tensor]:
    result = [[], []]
    with torch.no_grad():
        for batch in batches:
            for view in (0, 1):
                value = device_batch(batch, device, masks); geometry = geometry_fourier_features(value, config, device)
                result[view].append(model.forward_target(value, geometry)["projection"])
    return [torch.cat(value) for value in result]


def local_backward(callable_model: Any, raw: DistributedJointPrototypeModel, batches: list[dict[str, Any]],
                   config: dict[str, Any], joint: dict[str, Any], masks: dict[str, int], device: torch.device,
                   global_keys: list[torch.Tensor], centers: torch.Tensor, index: dict[str, int], global_counts: dict[str, int],
                   ddp: bool, seed: int = 20260822, epoch: int = 0) -> tuple[float, list[dict[str, Any]]]:
    queue_values = torch.zeros((8192, 128), device=device); queue_centers = torch.zeros((8192, 2), device=device)
    active = sum(value > 0 for value in global_counts.values()); records = []; total_value = 0.0
    calls = len(batches) * 2; call_index = 0
    for batch in batches:
        for view in (0, 1):
            value = device_batch(batch, device, masks); geometry = geometry_fourier_features(value, config, device)
            assignments = modality_mask_assignments(value, seed, epoch, view, 0.30)
            context = callable_model.no_sync() if ddp and call_index < calls - 1 else __import__("contextlib").nullcontext()
            with context:
                output = callable_model(value, geometry, assignments, seed, epoch, view)
                indices = [index[scene] for scene in value["scene_ids"]]
                scene = query_loss(output.outputs["projection"], indices, global_keys[1 - view],
                                   torch.cat(global_keys), centers, queue_values, queue_centers, 0, 0.1, 750.0) / 64.0
                losses = reconstruction_losses(raw, value, geometry, output.modalities, joint)
                local = modality_counts(batch, masks)
                if any(losses["modalities"][name]["local_valid_count"] != local[name] for name in global_counts):
                    raise RuntimeError("reconstruction count contract mismatch")
                ip = information_preservation_loss(losses, global_counts)
                contribution = scene + 0.5 * ip
                (contribution * (2.0 if ddp else 1.0)).backward()
            total_value += float(contribution.detach()); records.extend(
                {"scene_id": scene_id, "view_id": view, "projection": projection.detach().cpu()}
                for scene_id, projection in zip(value["scene_ids"], output.outputs["projection"], strict=True))
            call_index += 1
    return total_value, records


def ema_queue_state(model: DistributedJointPrototypeModel, keys: list[torch.Tensor], centers: torch.Tensor,
                    scene_ids: list[str]) -> dict[str, Any]:
    with torch.no_grad():
        for parameter in model.online.parameters(): parameter.add_(1e-6)
    model.update_target(0.999)
    values = torch.stack(keys, dim=1).reshape(64, 128)
    ids = torch.tensor([int.from_bytes(__import__("hashlib").sha256(scene.encode()).digest()[:8], "big") & ((1 << 63) - 1)
                        for scene in scene_ids], device=centers.device, dtype=torch.int64).repeat_interleave(2)
    queue_values = torch.zeros((8192, 128), device=centers.device); queue_ids = torch.full((8192,), -1, device=centers.device, dtype=torch.int64)
    queue_centers = torch.zeros((8192, 2), device=centers.device)
    pointer, occupancy = enqueue(queue_values, queue_ids, queue_centers, 0, 0, values, ids, centers.repeat_interleave(2, 0))
    return {"target": model.target.state_dict(), "queue_values": queue_values[:occupancy], "queue_ids": queue_ids[:occupancy],
            "queue_centers": queue_centers[:occupancy], "pointer": pointer, "occupancy": occupancy}


def reference(packages: list[dict[str, Any]], config: dict[str, Any], joint: dict[str, Any], masks: dict[str, int], seed: int) -> dict[str, Any]:
    device = torch.device("cuda:0"); model = prepare_model(config, joint, device, seed); model.zero_grad(set_to_none=True)
    batches = [batch for package in packages for batch in package["batches"]]
    keys = target_keys(model, batches, config, masks, device)
    scene_ids = [scene for package in packages for scene in package["scene_ids"]]
    centers = torch.tensor([center for package in packages for center in package["centers"]], device=device, dtype=torch.float32)
    index = {scene: offset for offset, scene in enumerate(scene_ids)}; global_counts = {name: 2 * value for name, value in counts(batches, masks).items()}
    loss = 0.0; records = []
    for package in packages:
        value, output = local_backward(model, model, package["batches"], config, joint, masks, device, keys, centers, index, global_counts, False)
        loss += value; records.extend(output)
    gradients = {name: parameter.grad.cpu() for name, parameter in model.named_parameters() if parameter.requires_grad}
    state = ema_queue_state(model, keys, centers, scene_ids)
    result = {"loss": loss, "records": sorted(records, key=lambda x: (x["scene_id"], x["view_id"])), "gradients": gradients, "ema_queue": state}
    result["digest"] = digest_state(result); del model; torch.cuda.empty_cache(); return result


def worker(rank: int, master_port: int, package_paths: list[str], config_path: str, joint_path: str,
           masks: dict[str, int], seed: int, result_path: str) -> None:
    os.environ.update(MASTER_ADDR="127.0.0.1", MASTER_PORT=str(master_port), RANK=str(rank), WORLD_SIZE="2", LOCAL_RANK=str(rank))
    torch.cuda.set_device(rank); torch.use_deterministic_algorithms(True); torch.backends.cuda.matmul.allow_tf32=False; torch.backends.cudnn.allow_tf32=False
    dist.init_process_group("nccl", rank=rank, world_size=2)
    config=yaml.safe_load(Path(config_path).read_text()); joint=yaml.safe_load(Path(joint_path).read_text()); package=torch.load(package_paths[rank],weights_only=False)
    device=torch.device(f"cuda:{rank}"); model=prepare_model(config,joint,device,seed); ddp=DistributedDataParallel(model,device_ids=[rank],broadcast_buffers=False,find_unused_parameters=False)
    local_keys=target_keys(model,package["batches"],config,masks,device); keys=[]
    for value in local_keys:
        gathered=[torch.empty_like(value) for _ in range(2)];dist.all_gather(gathered,value);keys.append(torch.cat(gathered))
    objects=[None,None];dist.all_gather_object(objects,(package["scene_ids"],package["centers"]));scene_ids=[x for obj in objects for x in obj[0]]
    centers=torch.tensor([x for obj in objects for x in obj[1]],device=device,dtype=torch.float32);index={scene:i for i,scene in enumerate(scene_ids)}
    local_counts=counts(package["batches"],masks); names=list(local_counts); tensor=torch.tensor([local_counts[n] for n in names],device=device,dtype=torch.int64);dist.all_reduce(tensor)
    global_counts={name:2*int(tensor[i]) for i,name in enumerate(names)};ddp.zero_grad(set_to_none=True)
    loss,records=local_backward(ddp,model,package["batches"],config,joint,masks,device,keys,centers,index,global_counts,True)
    loss_tensor=torch.tensor([loss],device=device,dtype=torch.float64);dist.all_reduce(loss_tensor)
    gradients={name.removeprefix("module."):p.grad.cpu() for name,p in ddp.named_parameters() if p.requires_grad}; all_records=[None,None];dist.all_gather_object(all_records,records)
    state=ema_queue_state(model,keys,centers,scene_ids);state_digest=digest_state(state);state_digests=[None,None];dist.all_gather_object(state_digests,state_digest)
    result={"loss":float(loss_tensor),"records":sorted([x for rows in all_records for x in rows],key=lambda x:(x["scene_id"],x["view_id"])),"gradients":gradients,"ema_queue":state,"rank_state_digests":state_digests}
    result["digest"]=digest_state(result)
    if rank==0:torch.save(result,result_path)
    dist.barrier();dist.destroy_process_group()


def compare(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    limits = {"loss_atol": 1e-7, "loss_rtol": 1e-6, "gradient_atol": 1e-7,
              "gradient_rtol": 1e-5, "relative_l2_max": 1e-6, "cosine_min": 0.9999999}
    non=[]; maximum=0.0; maximum_relative_l2=0.0; minimum_cosine=1.0
    allclose_failures=[]; relative_l2_failures=[]; cosine_failures=[]; routing_failures=[]
    for name in left["gradients"]:
        expected, observed = left["gradients"][name], right["gradients"][name]
        if not torch.isfinite(expected).all() or not torch.isfinite(observed).all():
            allclose_failures.append(name); continue
        expected_nonzero, observed_nonzero = bool(torch.count_nonzero(expected)), bool(torch.count_nonzero(observed))
        if expected_nonzero != observed_nonzero: routing_failures.append(name)
        if not torch.equal(expected, observed):
            diff=float((expected-observed).abs().max());non.append(name);maximum=max(maximum,diff)
        if not torch.allclose(expected, observed, atol=limits["gradient_atol"], rtol=limits["gradient_rtol"]):
            allclose_failures.append(name)
        expected64, observed64 = expected.double().flatten(), observed.double().flatten()
        denominator = float(torch.linalg.vector_norm(expected64))
        relative_l2 = float(torch.linalg.vector_norm(expected64 - observed64)) / denominator if denominator else (0.0 if not observed_nonzero else math.inf)
        maximum_relative_l2=max(maximum_relative_l2,relative_l2)
        if relative_l2 > limits["relative_l2_max"]: relative_l2_failures.append(name)
        observed_norm=float(torch.linalg.vector_norm(observed64))
        if denominator and observed_norm:
            cosine=float(torch.dot(expected64,observed64)/(denominator*observed_norm));minimum_cosine=min(minimum_cosine,cosine)
            if cosine < limits["cosine_min"]: cosine_failures.append(name)
    loss_difference=abs(left["loss"]-right["loss"])
    loss_close=math.isclose(left["loss"],right["loss"],abs_tol=limits["loss_atol"],rel_tol=limits["loss_rtol"])
    return {"limits":limits,"loss_exact":left["loss"]==right["loss"],"loss_close":loss_close,"loss_difference":loss_difference,
            "projection_exact":digest_state(left["records"])==digest_state(right["records"]),"gradient_non_exact_tensors":len(non),
            "gradient_maximum_absolute_difference":maximum,"gradient_maximum_relative_l2":maximum_relative_l2,
            "gradient_minimum_cosine_similarity":minimum_cosine,"gradient_allclose_failures":allclose_failures,
            "gradient_relative_l2_failures":relative_l2_failures,"gradient_cosine_failures":cosine_failures,
            "gradient_routing_failures":routing_failures,"first_non_exact":non[:20],"ema_queue_exact":digest_state(left["ema_queue"])==digest_state(right["ema_queue"]),
            "rank_state_exact":len(set(right["rank_state_digests"]))==1}


def main() -> None:
    p=argparse.ArgumentParser();p.add_argument("--accepted-manifest",required=True);p.add_argument("--tensor-contract",required=True);p.add_argument("--encoder-config",required=True);p.add_argument("--joint-config",required=True);a=p.parse_args()
    torch.use_deterministic_algorithms(True);torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
    config=yaml.safe_load(Path(a.encoder_config).read_text());joint=yaml.safe_load(Path(a.joint_config).read_text());dataset=AcceptedPrototypeDataset(a.accepted_manifest,a.tensor_contract,split="training")
    samples=[]
    for i,_ in sorted(enumerate(dataset.rows),key=lambda x:(int(x[1]["node_count"]),x[1]["scene_id"])):
        value=dataset[i]
        if set(value["entities"]["entity_type"].tolist())=={0,1,2}:samples.append(value)
        if len(samples)==32:break
    samples=sorted(samples,key=lambda x:x["scene_id"]);packages=[]
    for rank in range(2):
        local=samples[rank*16:(rank+1)*16];packages.append({"scene_ids":[x["scene_id"] for x in local],"centers":[x["meta"]["center_xy_5186"] for x in local],"batches":[ragged_collate(local[:8]),ragged_collate(local[8:])]})
    masks={name:next(iter(values)) for name,values in dataset.category_mask_index.items()}
    single=reference(packages,config,joint,masks,20260822)
    with tempfile.TemporaryDirectory(prefix="fuse-ddp-joint-") as directory:
        paths=[str(Path(directory)/f"rank-{r}.pt") for r in range(2)]
        for path,package in zip(paths,packages,strict=True):torch.save(package,path)
        runs=[]
        for repeat in range(2):
            out=str(Path(directory)/f"run-{repeat}.pt");mp.spawn(worker,args=(port(),paths,str(Path(a.encoder_config).resolve()),str(Path(a.joint_config).resolve()),masks,20260822,out),nprocs=2,join=True);runs.append(torch.load(out,weights_only=False))
        comparison=compare(single,runs[0]);repeat_exact=runs[0]["digest"]==runs[1]["digest"]
        passed=all((comparison["loss_close"],comparison["projection_exact"],not comparison["gradient_allclose_failures"],
                    not comparison["gradient_relative_l2_failures"],not comparison["gradient_cosine_failures"],
                    not comparison["gradient_routing_failures"],comparison["ema_queue_exact"],comparison["rank_state_exact"],repeat_exact))
        print(json.dumps({"status":"PASS" if passed else "BLOCKED","comparison":comparison,"ddp_repeated_exact":repeat_exact,"single_digest":single["digest"],"ddp_digests":[x["digest"] for x in runs],"scenes":32,"rank_scenes":16,"rank_microbatches":[8,8],"optimizer_step_performed":False,"optimizer_steps":0},sort_keys=True))


if __name__=="__main__":main()
