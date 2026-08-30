#!/usr/bin/env python3
"""Temporary-only two-rank cfg_main pilot, capped at 40 updates."""

from __future__ import annotations

import argparse
import concurrent.futures
import contextlib
import fcntl
import json
import os
import random
import multiprocessing as mp
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import torch
import torch.distributed as dist
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "python"), str(ROOT / "scripts")]

from canonical_config import canonical_json_bytes, load_strict_yaml  # noqa: E402
from p6_data import build_vocabulary  # noqa: E402
from p7_training import (P7ArtifactCatalog, canonical_digest, collate, empty_queue, selected_view_pair,
                         state_content_digest, to_device)  # noqa: E402
from p9_data import P9Data  # noqa: E402
from p9_infrastructure import P9ExactScheduler, bounded_groups, configuration_seed, load_contract  # noqa: E402
from p7_prototype_training import (activate_rank_stochastic_seed, checkpoint_state, configure_process,
                                   geometry, model_and_state, restore_checkpoint, save_checkpoint, train_update,
                                   wrap_ddp)  # noqa: E402
from p7_geometry_cache import GeometryCacheReader, GeometryCacheWriter, cache_record, sha256_file  # noqa: E402


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_bytes(canonical_json_bytes(value)); os.replace(temporary, path)


def runtime_inputs() -> dict[str, Any]:
    return yaml.safe_load((ROOT / "config/p7_cold_path_runtime.yml").read_text())["inputs"]


def values_and_authority() -> dict[str, Any]:
    p9 = load_contract(ROOT / "config/p9_infrastructure.yml")
    config = yaml.safe_load((ROOT / "config/p7_deterministic_training.yml").read_text())
    seed = configuration_seed(int(config["training"]["root_seed"]), "cfg_main")
    config["training"].update({"root_seed": seed, "maximum_updates": 15200,
                               "updates_per_epoch": 76, "maximum_epochs": 200})
    config["scheduler"].update({"warmup_updates": 760, "decay_updates": 14440})
    config["population"] = {"training_scenes": 2421, "validation_scenes": 400,
                            "validation_queries": 800, "validation_gallery": 400,
                            "evaluation_scenes_declared_but_prohibited": 1600}
    paths = runtime_inputs()
    catalog = P7ArtifactCatalog({"p3": paths["p3_root"], "p4": paths["p4_root"], "p5": paths["p5_root"]},
                                config["parents"], verify=False)
    preprocessing = json.loads(Path(paths["preprocessing"]).read_text())
    vocabulary = build_vocabulary(paths["categories"]); data = P9Data(catalog, preprocessing, vocabulary)
    architecture = json.loads(Path(paths["architecture"]).read_text())
    authority = {"run_id": "p9pilot_cfg_main_" + str(seed),
                 "training_authority_id": "p9pilot_authority_cfg_main",
                 "parents": {"p8_acceptance_id": p9["parents"]["p8_acceptance_id"],
                             "p7_runtime_acceptance_id": p9["parents"]["p7_runtime_acceptance_id"]},
                 "formal_attempt": False, "maximum_updates": 40}
    return {"config": config, "catalog": catalog, "preprocessing": preprocessing,
            "vocabulary": vocabulary, "data": data, "architecture": architecture,
            "model_config": load_strict_yaml(ROOT / "config/p6_model_dataloader.yml"),
            "authority": authority}


class P9Lookahead:
    def __init__(self, values: dict[str, Any], rank: int) -> None:
        self.values, self.rank = values, rank
        self.groups = bounded_groups(values["data"].members["training"],
                                     int(values["config"]["training"]["root_seed"]), 40)

    def consume(self, epoch: int, batch_index: int):
        if epoch != 1 or not 0 <= batch_index < 40: raise ValueError("bounded pilot batch outside epoch-1 prefix")
        global_scenes = list(self.groups[batch_index]); local = global_scenes[self.rank * 16:(self.rank + 1) * 16]
        pairs = [selected_view_pair(scene, [row["master_view_id"] for row in self.values["catalog"].k8[scene]],
                                    self.values["config"], epoch) for scene in local]
        batches = [collate([self.values["data"].training_view(scene, pair[role])
                            for scene, pair in zip(local, pairs, strict=True)], self.values["vocabulary"])
                   for role in range(2)]
        return batches, global_scenes, pairs

    def close(self) -> None: pass


class P9EagerData:
    """Rank-local immutable prepared-view working set for the bounded trajectory."""

    def __init__(self, base: P9Data, values: dict[str, Any], rank: int, plan_path: Path,
                 prepared: Path) -> None:
        self.members, self.catalog = base.members, base.catalog
        required: set[tuple[str, str, int | None]] = set()
        groups = bounded_groups(base.members["training"], int(values["config"]["training"]["root_seed"]), 40)
        for group in groups:
            for scene in group[rank * 16:(rank + 1) * 16]:
                views = [row["master_view_id"] for row in base.catalog.k8[scene]]
                pair = selected_view_pair(scene, views, values["config"], 1)
                required.update(("training", scene, int(view)) for view in pair)
        records = [("validation_query", scene, index) for scene in base.members["validation"] for index in (0, 1)]
        records += [("validation_gallery", scene, None) for scene in base.members["validation"]]
        for batch_index, start in enumerate(range(0, len(records), 8)):
            if batch_index % 2 == rank:
                required.update(records[start:start + 8])
        plan = json.loads(plan_path.read_text()); self.samples = {}
        implementation = sha256_file(ROOT / "python/prototype_encoder.py")
        for row in plan["entries"]:
            spec = tuple(row["spec"])
            if spec not in required:
                continue
            path = prepared / f"{int(row['index']):06d}.pt"
            payload = torch.load(path, map_location="cpu", weights_only=False)
            if int(payload["index"]) != int(row["index"]):
                raise ValueError("P9 eager fixed-index mismatch")
            sample = payload["sample"]
            expected = cache_record(sample, values["config"]["parents"],
                                    values["model_config"]["model"]["geometry"], implementation, spec[0])
            if canonical_json_bytes(expected) != canonical_json_bytes(payload["record"]):
                raise ValueError("P9 eager prepared-view identity mismatch")
            self.samples[spec] = sample
        if set(self.samples) != required:
            raise ValueError("P9 eager prepared-view coverage mismatch")
        self.required_entry_count = len(required)

    def training_view(self, scene: str, master: int):
        return self.samples[("training", scene, int(master))]

    def validation_query(self, scene: str, index: int):
        return self.samples[("validation_query", scene, int(index))]

    def validation_gallery(self, scene: str):
        return self.samples[("validation_gallery", scene, None)]


def prepare() -> tuple[dict[str, Any], int, torch.device, Any, Any, Any, Any]:
    values = values_and_authority(); rank = int(os.environ["RANK"])
    device = configure_process(values["config"], rank); dist.init_process_group("nccl")
    model, optimizer, _, queue = model_and_state(values, device)
    scheduler = P9ExactScheduler(optimizer, peak=0.001)
    cache_path = os.environ.get("P9_PILOT_CACHE", "")
    if cache_path:
        reader = GeometryCacheReader(cache_path, maximum_memory_bytes=4 * 1024**3)
        if reader.manifest["training_authority_id"] != values["authority"]["training_authority_id"]:
            raise ValueError("foreign P9 pilot cache authority")
        values["geometry_cache"] = reader
    prepared = os.environ.get("P9_PILOT_PREPARED", "")
    plan = os.environ.get("P9_PILOT_PLAN", "")
    if prepared or plan:
        if not prepared or not plan:
            raise ValueError("P9 eager preload requires both plan and prepared root")
        before = state_content_digest({"python": random.getstate(), "numpy": np.random.get_state(),
                                       "torch": torch.get_rng_state()})
        started = time.monotonic()
        values["data"] = P9EagerData(values["data"], values, rank, Path(plan), Path(prepared))
        after = state_content_digest({"python": random.getstate(), "numpy": np.random.get_state(),
                                      "torch": torch.get_rng_state()})
        if before != after:
            raise ValueError("P9 eager preload consumed scientific RNG")
        values["preload"] = {"entry_count": values["data"].required_entry_count,
                             "wall_seconds": time.monotonic() - started,
                             "rng_before": before, "rng_after": after, "rng_unchanged": True}
        dist.barrier()
    return values, rank, device, model, optimizer, scheduler, queue


def p9_validation_metrics(model: Any, values: dict[str, Any], device: torch.device, rank: int) -> dict[str, Any]:
    """Distributed fixed validation for the full 800-query/400-gallery population."""
    data = values["data"]; model.eval()
    records = [("query", scene, index) for scene in data.members["validation"] for index in (0, 1)]
    records += [("gallery", scene, None) for scene in data.members["validation"]]
    if len(records) != 1200:
        raise ValueError("P9 validation population mismatch")
    local_embeddings = []; local_indices = []; cache = values.get("geometry_cache")
    with torch.inference_mode():
        for batch_index, start in enumerate(range(0, len(records), 8)):
            if batch_index % dist.get_world_size() != rank:
                continue
            selected = records[start:start + 8]
            samples = [(data.validation_query(scene, int(index)) if kind == "query"
                        else data.validation_gallery(scene)) for kind, scene, index in selected]
            batch = to_device(collate(samples, values["vocabulary"]), device)
            role = "validation_query" if selected[0][0] == "query" else "validation_gallery"
            geom = cache.batch(batch, role, device) if cache else geometry(batch, values["model_config"], device)
            modalities = model._modalities(model.online, batch, geom)
            output = model._finish(model.online, batch, torch.stack(tuple(
                modalities[name] for name in ("relative", "geometry", "semantic", "environmental")), 1))
            local_embeddings.append(torch.nn.functional.normalize(output["scene_embedding"], dim=1))
            local_indices.extend(range(start, start + len(selected)))
    local = torch.cat(local_embeddings).contiguous()
    indices = torch.tensor(local_indices, dtype=torch.int64, device=device)
    gathered_embeddings = [torch.empty_like(local) for _ in range(dist.get_world_size())]
    gathered_indices = [torch.empty_like(indices) for _ in range(dist.get_world_size())]
    dist.all_gather(gathered_embeddings, local); dist.all_gather(gathered_indices, indices)
    combined_indices = torch.cat(gathered_indices).cpu(); combined = torch.cat(gathered_embeddings).cpu()
    permutation = torch.argsort(combined_indices)
    if combined_indices[permutation].tolist() != list(range(1200)):
        raise ValueError("P9 distributed validation coverage/order mismatch")
    ordered = combined[permutation]; queries, galleries = ordered[:800], ordered[800:]
    positive = torch.arange(400).repeat_interleave(2)
    similarities = queries @ galleries.T
    loss = torch.nn.functional.cross_entropy(
        similarities / float(values["config"]["objective"]["contrastive_temperature"]), positive)
    positive_values = similarities[torch.arange(800), positive]
    masked = similarities.clone(); masked[torch.arange(800), positive] = -torch.inf
    hardest = masked.max(1).values; ranks = 1 + (similarities > positive_values[:, None]).sum(1)
    event = {
        "validation_retrieval_loss": float(loss),
        "mean_source_separation_margin": float((positive_values - hardest).mean()),
        "MRR": float((1.0 / ranks.float()).mean()), "HIT@1": float((ranks <= 1).float().mean()),
        "HIT@5": float((ranks <= 5).float().mean()), "HIT@10": float((ranks <= 10).float().mean()),
        "query_count": 800, "gallery_count": 400,
        "validation_scene_digest": canonical_digest(data.members["validation"]),
        "embedding_digest": state_content_digest({"queries": queries, "galleries": galleries}),
        "distributed_coverage_count": 1200, "distributed_duplicate_count": 0,
        "distributed_missing_count": 0,
    }
    objects = [event if rank == 0 else None]; dist.broadcast_object_list(objects, src=0)
    model.train(); return objects[0]


def worker(args: argparse.Namespace) -> None:
    if args.max_updates < 1 or args.max_updates > 40: raise ValueError("P9 pilot cannot exceed 40 updates")
    values, rank, device, model, optimizer, scheduler, queue = prepare()
    ddp = wrap_ddp(model, device, values["config"]); activate_rank_stochastic_seed(values["config"], rank)
    trace: list[dict[str, Any]] = []; progress = {"completed_epoch": 0, "next_batch_index": 0}
    if args.resume_checkpoint:
        state = restore_checkpoint(Path(args.resume_checkpoint), model, optimizer, scheduler, queue, rank, values["authority"])
        trace = state["training_trace"]; progress = state["progress"]
    values["lookahead"] = P9Lookahead(values, rank); model.train(); started = time.monotonic(); walls = []
    while scheduler.completed_updates < args.max_updates:
        batch_index = scheduler.completed_updates
        result = train_update(ddp, model, optimizer, scheduler, queue, values, 1, batch_index, rank, device)
        walls.append(result["step_wall_seconds"])
        trace.append({key: value for key, value in result.items() if key != "step_wall_seconds"})
        progress = {"completed_epoch": 0, "next_batch_index": scheduler.completed_updates}
    validation = None
    if args.validation:
        model.eval(); validation = p9_validation_metrics(model, values, device, rank); model.train()
    state = checkpoint_state(model, optimizer, scheduler, queue, progress, trace,
                             [validation] if validation else [], {"best": validation, "patience": 0},
                             rank, values["authority"])
    manifest = save_checkpoint(Path(args.stage), state, "bounded_pilot", rank, values["authority"])
    if rank == 0:
        ordered = sorted(walls)
        summary = {"status": "PASS", "formal_attempt": False, "optimizer_updates": scheduler.completed_updates,
                   "state_content_sha256": manifest["state_content_sha256"], "checkpoint": manifest,
                   "checkpoint_path": str(Path(args.stage) / "checkpoints" / manifest["checkpoint_id"] / "checkpoint.pt"),
                   "trace": trace, "validation": validation, "wall_seconds": time.monotonic() - started,
                   "update_median_seconds": ordered[len(ordered)//2] if ordered else None,
                   "update_p95_seconds": ordered[min(len(ordered)-1, int(.95*(len(ordered)-1)))] if ordered else None,
                   "peak_vram_allocated_bytes": int(torch.cuda.max_memory_allocated(device)),
                   "root_seed": int(values["config"]["training"]["root_seed"]),
                   "preload": values.get("preload"),
                   "evaluation_queries_consumed": 0}
        write_json(Path(args.output), summary)
    dist.barrier(); dist.destroy_process_group()


@contextlib.contextmanager
def locks():
    root = Path(yaml.safe_load((ROOT / "config/p7_cold_path_runtime.yml").read_text())["gpu_lock_root"]); streams=[]
    try:
        for name in ("gpu_pair.lock","gpu0.lock","gpu1.lock"):
            stream=(root/name).open("a+"); fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB); streams.append(stream)
        yield
    finally:
        for stream in reversed(streams): fcntl.flock(stream.fileno(),fcntl.LOCK_UN); stream.close()


def launch(stage: Path, name: str, updates: int, resume: str = "", validation: bool = False) -> dict[str, Any]:
    target=stage/name; target.mkdir(parents=True); output=target/"summary.json"
    command=[sys.executable,"-m","torch.distributed.run","--standalone","--nproc_per_node=2",str(Path(__file__).resolve()),
             "worker","--stage",str(target),"--output",str(output),"--max-updates",str(updates)]
    if resume: command += ["--resume-checkpoint",resume]
    if validation: command += ["--validation"]
    env=os.environ.copy(); env.update({"CUDA_VISIBLE_DEVICES":"0,1","NCCL_P2P_DISABLE":"1","NCCL_IB_DISABLE":"1",
        "CUBLAS_WORKSPACE_CONFIG":":4096:8","OMP_NUM_THREADS":"1","MKL_NUM_THREADS":"1","OPENBLAS_NUM_THREADS":"1",
        "NUMEXPR_NUM_THREADS":"1","PYTHONDONTWRITEBYTECODE":"1"})
    for name in ("P9_PILOT_CACHE", "P9_PILOT_PLAN", "P9_PILOT_PREPARED"):
        if os.environ.get(name):
            env[name] = os.environ[name]
    with (target/"torchrun.log").open("w") as log:
        process=subprocess.run(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=7200)
    if process.returncode: raise RuntimeError(f"P9 bounded worker failed: {target/'torchrun.log'}")
    return json.loads(output.read_text())


_CPU_VALUES: dict[str, Any] | None = None
_CPU_STAGE = Path("/")


def cache_specs(values: dict[str, Any]) -> list[tuple[str, str, int | None]]:
    groups = bounded_groups(values["data"].members["training"], int(values["config"]["training"]["root_seed"]), 40)
    selected: set[tuple[str, str, int | None]] = set()
    for group in groups:
        for scene in group:
            pair = selected_view_pair(scene, [row["master_view_id"] for row in values["catalog"].k8[scene]],
                                      values["config"], 1)
            selected.update(("training", scene, int(view)) for view in pair)
    selected.update(("validation_query", scene, index) for scene in values["data"].members["validation"] for index in (0, 1))
    selected.update(("validation_gallery", scene, None) for scene in values["data"].members["validation"])
    return sorted(selected, key=lambda item: (item[0], item[1], -1 if item[2] is None else int(item[2])))


def sample_for(values: dict[str, Any], spec: tuple[str, str, int | None]) -> dict[str, Any]:
    role, scene, view = spec
    if role == "training": return values["data"].training_view(scene, int(view))
    if role == "validation_query": return values["data"].validation_query(scene, int(view))
    return values["data"].validation_gallery(scene)


def cpu_init(stage: str) -> None:
    global _CPU_VALUES, _CPU_STAGE
    for name in ("OMP_NUM_THREADS","MKL_NUM_THREADS","OPENBLAS_NUM_THREADS","NUMEXPR_NUM_THREADS"): os.environ[name]="1"
    torch.set_num_threads(1)
    if torch.cuda.is_initialized(): raise RuntimeError("P9 CPU preparation worker initialized CUDA")
    _CPU_VALUES=values_and_authority(); _CPU_STAGE=Path(stage)


def cpu_prepare(task: tuple[int, tuple[str, str, int | None]]) -> dict[str, Any]:
    index,spec=task; assert _CPU_VALUES is not None
    sample=sample_for(_CPU_VALUES,spec)
    record=cache_record(sample,_CPU_VALUES["config"]["parents"],_CPU_VALUES["model_config"]["model"]["geometry"],
                        sha256_file(ROOT/"python/prototype_encoder.py"),spec[0])
    path=_CPU_STAGE/f"{index:06d}.pt"; temporary=path.with_name(f".{path.name}.tmp-{os.getpid()}")
    torch.save({"index":index,"record":record,"sample":sample},temporary); os.replace(temporary,path)
    result={"index":index,"record":record,"path":str(path),"sha256":sha256_file(path)}
    # P9 has 20,568 possible cache entries. Worker-local scientific objects are
    # execution-only and must not accumulate across fixed-index tasks.
    _CPU_VALUES["data"].cache.clear(); _CPU_VALUES["data"].original_cache.clear()
    _CPU_VALUES["data"].branch_delta_cache.clear()
    return result


def cache_gpu(args: argparse.Namespace) -> None:
    gpu=int(args.gpu); torch.cuda.set_device(gpu); torch.use_deterministic_algorithms(True)
    torch.backends.cuda.matmul.allow_tf32=False; torch.backends.cudnn.allow_tf32=False
    values=values_and_authority(); device=torch.device("cuda",gpu); writer=GeometryCacheWriter(args.cache_stage)
    plan=json.loads(Path(args.plan).read_text()); rows=[]
    for row in plan["entries"]:
        if int(row["index"])%2 != gpu: continue
        path=Path(args.prepared)/f"{int(row['index']):06d}.pt"; deadline=time.monotonic()+3600
        while not path.is_file():
            if time.monotonic()>deadline: raise TimeoutError("P9 prepared sample timeout")
            time.sleep(.02)
        payload=torch.load(path,map_location="cpu",weights_only=False)
        if payload["index"]!=row["index"]: raise ValueError("P9 fixed-index handoff mismatch")
        batch_cpu=collate([payload["sample"]],values["vocabulary"]); batch=to_device(batch_cpu,device)
        magnitude,phase=geometry(batch,values["model_config"],device); writer.put(payload["record"],magnitude,phase)
        rows.append(payload["record"])
    write_json(Path(args.output),{"gpu":gpu,"records":rows,"entries":len(rows)})


def build_cache(root: Path, workers: int=32, limit: int=0) -> Path:
    root.mkdir(parents=True,exist_ok=False)
    values=values_and_authority(); specs=cache_specs(values)
    if limit: specs=specs[:int(limit)]
    prepared=root/"prepared"; prepared.mkdir()
    cache_stage=root/"geometry_cache"; cache_stage.mkdir(); entries=[{"index":i,"spec":list(spec)} for i,spec in enumerate(specs)]
    plan={"entry_count":len(entries),"entries":entries}; write_json(root/"cache_plan.json",plan)
    processes=[]; env=os.environ.copy(); env.update({"CUDA_VISIBLE_DEVICES":"0,1","CUBLAS_WORKSPACE_CONFIG":":4096:8"})
    for gpu in (0,1):
        output=root/f"cache-gpu-{gpu}.json"; command=[sys.executable,str(Path(__file__).resolve()),"cache-gpu","--gpu",str(gpu),
            "--plan",str(root/"cache_plan.json"),"--prepared",str(prepared),"--cache-stage",str(cache_stage),"--output",str(output)]
        processes.append((subprocess.Popen(command,cwd=ROOT,env=env),output))
    rows=[]
    try:
        with concurrent.futures.ProcessPoolExecutor(max_workers=workers,mp_context=mp.get_context("spawn"),initializer=cpu_init,
                                                    initargs=(str(prepared),)) as pool:
            for row in pool.map(cpu_prepare,[(i,spec) for i,spec in enumerate(specs)],chunksize=1): rows.append(row)
        for process,_ in processes:
            if process.wait(timeout=3600): raise RuntimeError("P9 cache GPU producer failed")
    except Exception:
        for process,_ in processes:
            if process.poll() is None: process.terminate()
        raise
    if len(rows)!=len(specs) or sorted(row["index"] for row in rows)!=list(range(len(specs))): raise ValueError("P9 cache CPU coverage mismatch")
    gpu_rows=[json.loads(path.read_text()) for _,path in processes]; records=[record for item in gpu_rows for record in item["records"]]
    if len(records)!=len(specs): raise ValueError("P9 cache GPU coverage mismatch")
    manifest=GeometryCacheWriter(cache_stage).finalize(values["authority"]["training_authority_id"],records)
    if manifest["entry_count"]!=len(specs): raise ValueError("P9 cache manifest coverage mismatch")
    return cache_stage/"geometry_cache_manifest.json"


def controller(args: argparse.Namespace) -> None:
    root=Path(args.root); root.mkdir(parents=True,exist_ok=False)
    with locks():
        started=time.monotonic(); cache=build_cache(root/"cache_build",workers=32); cache_wall=time.monotonic()-started
        os.environ["P9_PILOT_CACHE"]=str(cache)
        os.environ["P9_PILOT_PLAN"] = str(root / "cache_build/cache_plan.json")
        os.environ["P9_PILOT_PREPARED"] = str(root / "cache_build/prepared")
        uninterrupted=launch(root,"uninterrupted",40,validation=True)
        first=launch(root,"interrupted",20)
        resumed=launch(root,"resumed",40,first["checkpoint_path"],validation=True)
    exact=(uninterrupted["state_content_sha256"]==resumed["state_content_sha256"] and
           uninterrupted["trace"]==resumed["trace"])
    if not exact: raise RuntimeError("P9 bounded 20+resume+20 parity mismatch")
    write_json(root/"pilot_result.json",{"status":"PASS","formal_attempt":False,"maximum_updates":40,
        "resume_exact":True,"uninterrupted":uninterrupted,"interrupted":first,"resumed":resumed,
        "cache_manifest":str(cache),"cache_build_wall_seconds":cache_wall,
        "evaluation_queries_consumed":0})
    print(root/"pilot_result.json")


def trajectory_controller(args: argparse.Namespace) -> None:
    root = Path(args.root); root.mkdir(parents=True, exist_ok=False)
    cache = Path(args.cache)
    if not cache.is_file():
        raise FileNotFoundError("P9 temporary cache manifest is missing")
    with locks():
        os.environ["P9_PILOT_CACHE"] = str(cache)
        os.environ["P9_PILOT_PLAN"] = str(Path(args.plan))
        os.environ["P9_PILOT_PREPARED"] = str(Path(args.prepared))
        uninterrupted = launch(root, "uninterrupted", 40, validation=True)
        first = launch(root, "interrupted", 20)
        resumed = launch(root, "resumed", 40, first["checkpoint_path"], validation=True)
    exact = (uninterrupted["state_content_sha256"] == resumed["state_content_sha256"]
             and uninterrupted["trace"] == resumed["trace"]
             and uninterrupted["validation"] == resumed["validation"])
    if not exact:
        raise RuntimeError("P9 bounded 20+resume+20 parity mismatch")
    write_json(root / "pilot_result.json", {
        "status": "PASS", "formal_attempt": False, "maximum_updates": 40,
        "resume_exact": True, "uninterrupted": uninterrupted, "interrupted": first,
        "resumed": resumed, "cache_manifest": str(cache), "evaluation_queries_consumed": 0,
    })
    print(root / "pilot_result.json")


def parser() -> argparse.ArgumentParser:
    result=argparse.ArgumentParser(); sub=result.add_subparsers(dest="command",required=True)
    control=sub.add_parser("run"); control.add_argument("--root",required=True)
    trajectory=sub.add_parser("trajectory"); trajectory.add_argument("--root",required=True); trajectory.add_argument("--cache",required=True)
    trajectory.add_argument("--plan",required=True); trajectory.add_argument("--prepared",required=True)
    work=sub.add_parser("worker"); work.add_argument("--stage",required=True); work.add_argument("--output",required=True)
    work.add_argument("--max-updates",type=int,required=True); work.add_argument("--resume-checkpoint",default="")
    work.add_argument("--validation",action="store_true")
    gpu=sub.add_parser("cache-gpu"); gpu.add_argument("--gpu",required=True); gpu.add_argument("--plan",required=True)
    gpu.add_argument("--prepared",required=True); gpu.add_argument("--cache-stage",required=True); gpu.add_argument("--output",required=True)
    cache=sub.add_parser("cache-test"); cache.add_argument("--root",required=True); cache.add_argument("--limit",type=int,default=4)
    return result


if __name__ == "__main__":
    args=parser().parse_args()
    if args.command=="run": controller(args)
    elif args.command=="trajectory": trajectory_controller(args)
    elif args.command=="cache-gpu": cache_gpu(args)
    elif args.command=="cache-test":
        with locks(): print(build_cache(Path(args.root),workers=min(4,args.limit),limit=args.limit))
    else: worker(args)
