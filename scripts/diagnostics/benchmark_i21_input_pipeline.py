#!/usr/bin/env python3
"""Temporary I21-path profiler; it never creates a run directory or checkpoint."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "python"))

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
from torch.utils.data import Sampler
from torch.utils.data._utils.pin_memory import pin_memory as pin_batch_memory

from prototype_dataloader import sha256_file
from prototype_ddp_joint_model import DistributedJointPrototypeModel
from run_prototype_training import AugmentedPairDataset, collate_pairs, make_optimizer, stable_integer, state_digest, worker_init
from run_prototype_training_ddp import RankLogicalGroupSampler, empty_queue, sync_digest, train_group


def free_port() -> int:
    with socket.socket() as stream:
        stream.bind(("127.0.0.1", 0))
        return int(stream.getsockname()[1])


def identity_collate(value: Any) -> Any:
    return value


class FlatSceneSampler(Sampler[tuple[int, int, int]]):
    """Preserve I21 order/boundaries while scheduling each scene independently."""
    def __init__(self, grouped: RankLogicalGroupSampler) -> None:
        self.grouped = grouped

    def __iter__(self):
        return iter([task for batch in self.grouped.batches() for task in batch])

    def __len__(self) -> int:
        return sum(map(len, self.grouped.batches()))


def percentile(values: list[float], probability: float) -> float:
    if not values:
        return 0.0
    return float(np.percentile(np.asarray(values, dtype=np.float64), probability))


def summarize(values: list[float]) -> dict[str, float]:
    return {
        "mean": float(statistics.fmean(values)) if values else 0.0,
        "median": float(statistics.median(values)) if values else 0.0,
        "p95": percentile(values, 95),
        "sum": float(sum(values)),
    }


def component_digests(model: Any, optimizer: Any, scheduler: Any, queue: dict[str, Any]) -> dict[str, str]:
    return {
        "model_online": state_digest(model.online.state_dict()),
        "model_target_ema": state_digest(model.target.state_dict()),
        "projection_decoders": state_digest({"mask": model.modality_mask_embeddings, "decoders": model.decoders.state_dict()}),
        "optimizer": state_digest(optimizer.state_dict()),
        "scheduler": state_digest(scheduler.state_dict()),
        "queue": state_digest(queue),
    }


def cpu_clone(value: Any) -> Any:
    if isinstance(value, torch.Tensor): return value.detach().cpu().clone()
    if isinstance(value, dict): return {key: cpu_clone(item) for key, item in value.items()}
    if isinstance(value, list): return [cpu_clone(item) for item in value]
    if isinstance(value, tuple): return tuple(cpu_clone(item) for item in value)
    return value


def rank_worker(rank: int, world_size: int, args: argparse.Namespace, mode: str, result_path: str, port: int) -> None:
    os.environ.update(RANK=str(rank), WORLD_SIZE=str(world_size), LOCAL_RANK=str(rank), MASTER_ADDR="127.0.0.1", MASTER_PORT=str(port))
    torch.cuda.set_device(rank)
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    dist.init_process_group("nccl", rank=rank, world_size=world_size, device_id=torch.device(f"cuda:{rank}"))

    spec = json.loads(Path(args.run_spec).read_text())
    training = yaml.safe_load(Path(args.training_config).read_text())
    joint = yaml.safe_load(Path(args.joint_config).read_text())
    encoder = yaml.safe_load(Path(args.encoder_config).read_text())
    augmentation = yaml.safe_load(Path(args.augmentation_config).read_text())
    i19 = json.loads(Path(args.i19_manifest).read_text())
    workers = int(training["execution"]["workers_per_rank"])
    if world_size != 2 or workers != 20 or int(training["execution"]["workers"]) != 40:
        raise ValueError("diagnostic requires two ranks and exactly 20 DataLoader workers per rank")
    if int(training["execution"]["native_threads_per_worker"]) != 1:
        raise ValueError("diagnostic requires one native thread per DataLoader worker")

    thresholds = {0: float(i19["logical_results"]["thresholds"]["building"]), 1: float(i19["logical_results"]["thresholds"]["road"])}
    optimized = mode != "legacy_input"
    candidate = mode
    dataset = AugmentedPairDataset(
        spec["dataset_manifest"]["path"], args.tensor_contract, "training", augmentation, thresholds,
        archive_source_root=args.archive_source_root, archive_runtime_root=args.archive_runtime_root,
        persistent_archive_handles=optimized, diagnostic_timing=True,
    )
    sampler = RankLogicalGroupSampler(dataset.base.rows, spec["hard_budgets"], int(spec["seed"]), rank)
    prefetch = int(args.optimized_prefetch if optimized else args.baseline_prefetch)
    if optimized:
        loader = DataLoader(
            dataset, sampler=FlatSceneSampler(sampler), batch_size=None, num_workers=workers,
            collate_fn=identity_collate, persistent_workers=True, pin_memory=True,
            prefetch_factor=prefetch, worker_init_fn=worker_init, multiprocessing_context="spawn",
        )
    else:
        loader = DataLoader(
            dataset, batch_sampler=sampler, num_workers=workers, collate_fn=collate_pairs,
            persistent_workers=True, pin_memory=True, prefetch_factor=prefetch,
            worker_init_fn=worker_init, multiprocessing_context="spawn",
        )
    masks = {name: next(iter(values)) for name, values in dataset.base.category_mask_index.items()}
    device = torch.device(f"cuda:{rank}")
    repetitions: list[dict[str, Any]] = []
    captured_gradients: list[Any] = []
    captured_state: dict[str, Any] | None = None

    for repetition in range(args.repetitions):
        seed = int(spec["seed"])
        import random
        random.seed(seed); np.random.seed(seed); torch.manual_seed(seed); torch.cuda.manual_seed_all(seed)
        sampler.set_epoch(0)
        model = DistributedJointPrototypeModel(encoder, joint).to(device).train(); model.target.eval()
        ddp = DistributedDataParallel(model, device_ids=[rank], broadcast_buffers=False, find_unused_parameters=False)
        optimizer, scheduler = make_optimizer(model, spec); queue = empty_queue(device)
        iterator = iter(loader)
        optimized_batch_lengths = ([16] * 8 if candidate == "microbatch16" else [len(batch) for batch in sampler.batches()]) if optimized else []
        optimized_batch_position = 0
        step_records: list[dict[str, Any]] = []
        group_batches: list[dict[str, Any]] = []
        rank_worker_timings: dict[str, float] = {}
        worker_sample_count = 0
        epoch_started = time.perf_counter(); step_started = epoch_started; wait_accumulated = 0.0

        while True:
            if optimized and optimized_batch_position >= len(optimized_batch_lengths):
                break
            wait_started = time.perf_counter()
            try:
                if optimized:
                    raw_items = [next(iterator) for _ in range(optimized_batch_lengths[optimized_batch_position])]
                    optimized_batch_position += 1
                    wait_accumulated += time.perf_counter() - wait_started
                    collate_started = time.perf_counter(); item = collate_pairs(raw_items)
                    rank_worker_timings["parent_collate_seconds"] = rank_worker_timings.get("parent_collate_seconds", 0.0) + time.perf_counter() - collate_started
                    pin_started = time.perf_counter(); item = pin_batch_memory(item)
                    rank_worker_timings["parent_pinning_seconds"] = rank_worker_timings.get("parent_pinning_seconds", 0.0) + time.perf_counter() - pin_started
                else:
                    item = next(iterator)
                    wait_accumulated += time.perf_counter() - wait_started
            except StopIteration:
                break
            profile = item["_diagnostic_timing"]
            rank_worker_timings["collate_seconds"] = rank_worker_timings.get("collate_seconds", 0.0) + float(profile["collate_seconds"])
            for sample_profile in profile["samples"]:
                worker_sample_count += 1
                for key, value in sample_profile.items():
                    if key.endswith("_seconds"):
                        rank_worker_timings[key] = rank_worker_timings.get(key, 0.0) + float(value)
                rank_worker_timings["archive_handle_cache_hits"] = rank_worker_timings.get("archive_handle_cache_hits", 0.0) + int(sample_profile["archive_handle_cache_hit"])
            group_batches.append(item)
            if sum(len(value["positions"]) for value in group_batches) < 16:
                continue
            result = train_group(
                ddp, model, group_batches, optimizer, scheduler, queue, spec, joint, encoder, masks,
                device, 0, True, diagnostic_profile=True,
                geometry_implementation="vectorized" if candidate in {"vectorized_geometry", "combined"} else "legacy",
                async_h2d=candidate in {"async_h2d", "combined"},
                contiguous_packing=candidate in {"contiguous_packing", "combined"},
            )
            if args.capture_state and rank == 0:
                captured_gradients.append({name: parameter.grad for name, parameter in model.named_parameters() if parameter.grad is not None})
                captured_gradients[-1] = cpu_clone(captured_gradients[-1])
            torch.cuda.synchronize(device)
            step_elapsed = time.perf_counter() - step_started
            step_records.append({
                "step": len(step_records) + 1,
                "step_seconds": step_elapsed,
                "dataloader_wait_seconds": wait_accumulated,
                "loss": result["total_loss"],
                "augmentation_digest": result["augmentation_digest"],
                "gradient_digest": result["diagnostic"]["gradient_digest"],
                "scene_ids": result["diagnostic"]["scene_ids"],
                "gpu_phases": result["diagnostic"]["timings"],
            })
            group_batches = []; wait_accumulated = 0.0; step_started = time.perf_counter()
        if group_batches or len(step_records) != 8:
            raise RuntimeError(f"one prototype epoch must contain eight complete optimizer groups, got {len(step_records)}")
        torch.cuda.synchronize(device)
        epoch_seconds = time.perf_counter() - epoch_started
        state = component_digests(model, optimizer, scheduler, queue)
        synchronized_state = sync_digest(model, optimizer, scheduler, queue, device)
        local = {
            "rank": rank, "epoch_seconds": epoch_seconds, "step_records": step_records,
            "worker_service_totals": rank_worker_timings, "worker_sample_count": worker_sample_count,
            "component_digests": state, "synchronized_state_digest": synchronized_state,
            "queue_pointer": int(queue["pointer"]), "queue_occupancy": int(queue["occupancy"]),
        }
        ranks: list[Any] = [None, None]
        dist.all_gather_object(ranks, local)
        if rank == 0:
            repetitions.append({
                "repetition": repetition + 1, "cache_class": "cold_worker_fd_cache" if repetition == 0 else "warm_persistent_workers",
                "epoch_wall_seconds": max(value["epoch_seconds"] for value in ranks),
                "scenes_per_second": 256.0 / max(value["epoch_seconds"] for value in ranks),
                "ranks": ranks,
            })
            if args.capture_state:
                captured_state=cpu_clone({
                    "gradients": captured_gradients,
                    "model_online": model.online.state_dict(), "model_target_ema": model.target.state_dict(),
                    "projection_decoders": {"mask": model.modality_mask_embeddings, "decoders": model.decoders.state_dict()},
                    "optimizer": optimizer.state_dict(), "scheduler": scheduler.state_dict(), "queue": queue,
                })
        del ddp, model, optimizer, scheduler, queue
        torch.cuda.empty_cache(); dist.barrier()

    if loader._iterator is not None:
        loader._iterator._shutdown_workers()
    if rank == 0:
        Path(result_path).write_text(json.dumps({"mode": mode, "prefetch_factor": prefetch, "repetitions": repetitions}, sort_keys=True))
        if args.capture_state:
            torch.save(captured_state, result_path + ".state.pt")
    dist.barrier(); dist.destroy_process_group()


class SystemMonitor:
    def __init__(self) -> None:
        self.stop = threading.Event(); self.samples: list[dict[str, Any]] = []
        self.disk_start = psutil.disk_io_counters(perdisk=True).get("sdb")
        self.started = time.monotonic(); self.peak_rss = 0

    def run(self) -> None:
        root = psutil.Process()
        psutil.cpu_times_percent(interval=None)
        while not self.stop.wait(0.5):
            cpu = psutil.cpu_times_percent(interval=None)
            rss = root.memory_info().rss
            for child in root.children(recursive=True):
                try: rss += child.memory_info().rss
                except (psutil.NoSuchProcess, psutil.AccessDenied): pass
            self.peak_rss = max(self.peak_rss, rss)
            gpu = subprocess.run(
                ["nvidia-smi", "--query-gpu=index,utilization.gpu,memory.used", "--format=csv,noheader,nounits"],
                check=True, text=True, capture_output=True,
            ).stdout.strip().splitlines()
            self.samples.append({
                "cpu_util_percent": 100.0 - float(cpu.idle), "cpu_iowait_percent": float(getattr(cpu, "iowait", 0.0)),
                "gpu": [{"index": int(parts[0]), "util_percent": float(parts[1]), "memory_mib": float(parts[2])}
                        for line in gpu if (parts := [part.strip() for part in line.split(",")])],
            })

    def summary(self) -> dict[str, Any]:
        elapsed = time.monotonic() - self.started
        disk_end = psutil.disk_io_counters(perdisk=True).get("sdb")
        utils = [sample["cpu_util_percent"] for sample in self.samples]
        waits = [sample["cpu_iowait_percent"] for sample in self.samples]
        gpu = {index: [sample["gpu"][index]["util_percent"] for sample in self.samples] for index in range(2)}
        return {
            "samples": len(self.samples), "elapsed_seconds": elapsed, "peak_process_tree_rss_bytes": self.peak_rss,
            "cpu_util_percent": summarize(utils), "cpu_iowait_percent": summarize(waits),
            "gpu_util_percent": {str(index): summarize(values) for index, values in gpu.items()},
            "gpu_idle_fraction_le_5_percent": {str(index): sum(value <= 5 for value in values) / len(values) if values else 0.0 for index, values in gpu.items()},
            "ssd_sdb_read_bytes": int(disk_end.read_bytes - self.disk_start.read_bytes),
            "ssd_sdb_write_bytes": int(disk_end.write_bytes - self.disk_start.write_bytes),
            "ssd_sdb_read_mib_per_second": (disk_end.read_bytes - self.disk_start.read_bytes) / (1024 ** 2) / elapsed,
        }


def validate_inputs(args: argparse.Namespace) -> dict[str, Any]:
    spec = json.loads(Path(args.run_spec).read_text())
    formal_root = Path(spec["output_root"])
    if formal_root.exists():
        raise RuntimeError(f"formal I21 run directory already exists; diagnostic refuses to touch it: {formal_root}")
    for name in ("dataset_manifest", "dataloader_manifest", "no_op_gate_manifest", "encoder_manifest", "augmentation_manifest", "joint_model_manifest", "distributed_joint_model_manifest"):
        record = spec[name]; path = Path(record["path"])
        if not path.is_file() or path.stat().st_size != int(record["size_bytes"]) or sha256_file(path) != record["sha256"]:
            raise RuntimeError(f"authoritative I20 parent mismatch: {name}")
    source_root = Path(args.archive_source_root).resolve(); runtime_root = Path(args.archive_runtime_root).resolve()
    files = []
    for source in sorted(source_root.joinpath("branches").rglob("*")):
        if not source.is_file(): continue
        target = runtime_root / source.relative_to(source_root)
        if not target.is_file() or target.stat().st_size != source.stat().st_size or sha256_file(target) != sha256_file(source):
            raise RuntimeError(f"SSD runtime mirror mismatch: {target}")
        files.append((source, target))
    return {
        "formal_output_root": str(formal_root), "formal_output_root_exists_before": False,
        "authoritative_dataset_manifest": spec["dataset_manifest"], "scientific_training_dataset_id": "ptd_8b3359690ea2d0bef52d63e3",
        "runtime_root": str(runtime_root), "mirror_file_count": len(files),
        "mirror_bytes": sum(source.stat().st_size for source, _ in files), "mirror_size_sha256_equal": True,
    }


def combine_mode(mode_result: dict[str, Any]) -> dict[str, Any]:
    for repetition in mode_result["repetitions"]:
        steps = [step for rank in repetition["ranks"] for step in rank["step_records"]]
        repetition["step_seconds"] = summarize([step["step_seconds"] for step in steps])
        repetition["dataloader_wait_seconds"] = summarize([step["dataloader_wait_seconds"] for step in steps])
        phase_names = sorted(steps[0]["gpu_phases"])
        repetition["gpu_phase_seconds"] = {name: summarize([step["gpu_phases"][name] for step in steps]) for name in phase_names}
        worker_names = sorted(repetition["ranks"][0]["worker_service_totals"])
        repetition["worker_service_totals"] = {name: sum(rank["worker_service_totals"].get(name, 0.0) for rank in repetition["ranks"]) for name in worker_names}
    return mode_result


def equivalence(baseline: dict[str, Any], optimized: dict[str, Any]) -> dict[str, Any]:
    comparisons = []
    references = baseline["repetitions"]
    for index,opt in enumerate(optimized["repetitions"]):
        base=references[min(index,len(references)-1)]
        base_steps = base["ranks"][0]["step_records"]; opt_steps = opt["ranks"][0]["step_records"]
        loss_delta = max(abs(a["loss"] - b["loss"]) for a, b in zip(base_steps, opt_steps, strict=True))
        comparisons.append({
            "repetition": base["repetition"], "scene_order_exact": [x["scene_ids"] for x in base_steps] == [x["scene_ids"] for x in opt_steps],
            "augmentation_digest_exact": [x["augmentation_digest"] for x in base_steps] == [x["augmentation_digest"] for x in opt_steps],
            "gradient_digest_exact": [x["gradient_digest"] for x in base_steps] == [x["gradient_digest"] for x in opt_steps],
            "loss_max_abs_delta": loss_delta,
            "component_states_exact": base["ranks"][0]["component_digests"] == opt["ranks"][0]["component_digests"],
            "combined_state_exact": base["ranks"][0]["synchronized_state_digest"] == opt["ranks"][0]["synchronized_state_digest"],
        })
    passed = all(item["scene_order_exact"] and item["augmentation_digest_exact"] and
                 item["loss_max_abs_delta"] <= 1e-7 + 1e-6 * max(abs(step["loss"]) for step in baseline["repetitions"][0]["ranks"][0]["step_records"])
                 for item in comparisons)
    return {"status": "PASS" if passed else "FAIL", "loss_atol": 1e-7, "loss_rtol": 1e-6, "comparisons": comparisons}


def tensor_equivalence(reference_path: Path, candidate_path: Path) -> dict[str, Any]:
    reference=torch.load(reference_path,map_location="cpu",weights_only=False)
    candidate=torch.load(candidate_path,map_location="cpu",weights_only=False)
    summaries={"gradient":{"atol":1e-7,"rtol":1e-5,"maximum_absolute_difference":0.0,"failures":[]},
               "state":{"atol":1e-6,"rtol":1e-5,"maximum_absolute_difference":0.0,"failures":[]}}
    def compare(left:Any,right:Any,path:str,group:str)->None:
        summary=summaries[group]
        if isinstance(left,torch.Tensor):
            if not isinstance(right,torch.Tensor) or left.shape!=right.shape or left.dtype!=right.dtype:
                summary["failures"].append(path);return
            if left.is_floating_point() or left.is_complex():
                difference=float((left-right).abs().max()) if left.numel() else 0.0
                summary["maximum_absolute_difference"]=max(summary["maximum_absolute_difference"],difference)
                if not torch.allclose(left,right,atol=summary["atol"],rtol=summary["rtol"]):summary["failures"].append(path)
            elif not torch.equal(left,right):summary["failures"].append(path)
        elif isinstance(left,dict) and isinstance(right,dict) and left.keys()==right.keys():
            for key in left:compare(left[key],right[key],f"{path}.{key}",group)
        elif isinstance(left,(list,tuple)) and isinstance(right,type(left)) and len(left)==len(right):
            for index,(a,b) in enumerate(zip(left,right,strict=True)):compare(a,b,f"{path}[{index}]",group)
        elif left!=right:summary["failures"].append(path)
    compare(reference["gradients"],candidate["gradients"],"gradients","gradient")
    compare({k:v for k,v in reference.items() if k!="gradients"},{k:v for k,v in candidate.items() if k!="gradients"},"state","state")
    for value in summaries.values():value["status"]="PASS" if not value["failures"] else "FAIL"
    return {"status":"PASS" if all(x["status"]=="PASS" for x in summaries.values()) else "FAIL",**summaries}


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ("run-spec", "training-config", "joint-config", "encoder-config", "augmentation-config", "tensor-contract", "i19-manifest", "archive-source-root", "archive-runtime-root", "output"):
        parser.add_argument(f"--{name}", required=True)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--baseline-prefetch", type=int, default=2)
    parser.add_argument("--optimized-prefetch", type=int, default=4)
    parser.add_argument("--baseline-result")
    parser.add_argument("--candidate", choices=("current", "microbatch16", "async_h2d", "contiguous_packing", "vectorized_geometry", "combined"), default="current")
    parser.add_argument("--fresh-reference", action="store_true")
    parser.add_argument("--capture-state", action="store_true")
    args = parser.parse_args()
    if args.repetitions < 1: raise ValueError("at least one repetition is required")
    audit = validate_inputs(args); modes = {}
    selected_modes = (("current", args.candidate) if args.fresh_reference else ("legacy_input", args.candidate))
    if args.baseline_result:
        reference = json.loads(Path(args.baseline_result).read_text())
        modes["reference"] = reference["modes"].get("optimized", reference["modes"].get("candidate"))
        selected_modes = (args.candidate,)
    state_paths={}
    for mode in selected_modes:
        result_path = str(Path(args.output).with_suffix(f".{mode}.tmp.json"))
        monitor = SystemMonitor(); thread = threading.Thread(target=monitor.run, daemon=True); thread.start()
        try:
            mp.spawn(rank_worker, args=(2, args, mode, result_path, free_port()), nprocs=2, join=True)
        finally:
            monitor.stop.set(); thread.join()
        modes[mode] = combine_mode(json.loads(Path(result_path).read_text()))
        state_path=Path(result_path+".state.pt")
        if state_path.exists():state_paths[mode]=state_path
        Path(result_path).unlink()
        modes[mode]["system"] = monitor.summary()
    if "reference" not in modes:
        reference_name="current" if args.fresh_reference else "legacy_input"
        modes["reference"] = modes.pop(reference_name)
        if reference_name in state_paths:state_paths["reference"]=state_paths.pop(reference_name)
    modes["candidate"] = modes.pop(args.candidate)
    if args.candidate in state_paths:state_paths["candidate"]=state_paths.pop(args.candidate)
    check = equivalence(modes["reference"], modes["candidate"])
    numeric_check=tensor_equivalence(state_paths["reference"],state_paths["candidate"]) if {"reference","candidate"} <= state_paths.keys() else None
    for path in state_paths.values():path.unlink(missing_ok=True)
    if numeric_check is not None and numeric_check["status"]!="PASS":check["status"]="FAIL"
    reference_values=[x["epoch_wall_seconds"] for x in modes["reference"]["repetitions"]]
    candidate_values=[x["epoch_wall_seconds"] for x in modes["candidate"]["repetitions"]]
    baseline_warm = statistics.median(reference_values[1:] or reference_values)
    optimized_warm = statistics.median(candidate_values[1:] or candidate_values)
    result = {
        "status": "PASS" if check["status"] == "PASS" else "FAIL", "diagnostic_only": True,
        "formal_target_executed": False, "formal_optimizer_steps": 0, "diagnostic_optimizer_steps": args.repetitions * 8 * 2,
        "candidate": args.candidate,
        "workers": {"total_dataloader_workers": 40, "per_rank": 20, "native_threads_per_worker": 1},
        "input_audit": audit, "modes": modes, "equivalence": check, "tensor_equivalence": numeric_check,
        "warm_median": {"baseline_seconds": baseline_warm, "optimized_seconds": optimized_warm,
                        "speedup": baseline_warm / optimized_warm, "time_reduction_percent": (1 - optimized_warm / baseline_warm) * 100},
        "formal_output_root_exists_after": Path(audit["formal_output_root"]).exists(),
    }
    if result["formal_output_root_exists_after"]: raise RuntimeError("diagnostic created the formal I21 run directory")
    Path(args.output).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": result["status"], "output": str(Path(args.output).resolve()), "warm_median": result["warm_median"]}, sort_keys=True))
    if result["status"] != "PASS": raise SystemExit(2)


if __name__ == "__main__":
    main()
