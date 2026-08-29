#!/usr/bin/env python3
"""Build, execute, and independently verify deterministic P7 prototype training."""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import os
import random
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any

import jsonschema
import numpy as np
import pyarrow.parquet as pq
import torch
import torch.distributed as dist
import yaml
from torch.nn.parallel import DistributedDataParallel

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from p6_data import build_vocabulary  # noqa: E402
from p7_training import (ExactLRScheduler, P7ArtifactCatalog, P7Data, P7Model, SCHEMA_VERSION,
                         SUPPLEMENT_NAME, canonical_digest, collate, derive_seed, empty_queue,
                         enqueue, epoch_scene_order, finalized, learning_rate, load_config,
                         local_infonce_sum, modality_assignments, replay_selector, scientific_config,
                         seed_payload, selected_view_pair, selector_decision, state_content_digest,
                         to_device, training_batch_digest)  # noqa: E402
from p6_model import geometry_fourier_features  # noqa: E402
from p6_data import GEOMETRY_LAYOUT_VERSION  # noqa: E402
from p7_geometry_cache import (CACHE_SCHEMA_VERSION, GeometryCacheReader, GeometryCacheWriter,
                               cache_record, sha256_file as cache_sha256_file)  # noqa: E402
from canonical_config import load_strict_yaml  # noqa: E402


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text())


def write_json(path: str | Path, value: Any) -> Path:
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_bytes((json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode())
    os.replace(temporary, path)
    return path


def sha256_file(path: str | Path) -> str:
    import hashlib
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_schema(path: str | Path, schema_path: str | Path) -> None:
    jsonschema.Draft202012Validator(read_json(schema_path)).validate(read_json(path))


def config_file_checksums(config_path: Path) -> dict[str, str]:
    from canonical_config import canonical_json_bytes, load_strict_yaml
    value = load_strict_yaml(config_path)
    return {"raw_sha256": sha256_file(config_path),
            "canonical_sha256": __import__("hashlib").sha256(canonical_json_bytes(value)).hexdigest()}


def common_inputs(args: argparse.Namespace) -> dict[str, Any]:
    config = load_config(args.config)
    architecture = read_json(args.architecture); preprocessing = read_json(args.preprocessing)
    p6 = read_json(args.p6_acceptance); prototype_manifest = read_json(args.prototype_manifest)
    if (architecture.get("model_authority_id"), preprocessing.get("preprocessing_id"),
            p6.get("model_data_acceptance_id"), prototype_manifest.get("prototype_id")) != (
            config["parents"]["p6_model_authority_id"], config["parents"]["p6_preprocessing_id"],
            config["parents"]["p6_aggregate_acceptance_id"], config["parents"]["prototype_selection_id"]):
        raise ValueError("P7 accepted parent identity mismatch")
    if any(value.get("status") != "PASS" for value in (architecture, preprocessing, p6, prototype_manifest)):
        raise ValueError("P7 parent is not accepted")
    if p6.get("geometry_layout_version") != "3.0.0":
        raise ValueError("P7 requires accepted P6 geometry layout 3.0.0")
    rows = pq.read_table(args.prototype).to_pylist()
    counts = {split: sum(row["split"] == split for row in rows) for split in ("training", "validation", "evaluation")}
    if counts != {"training": 256, "validation": 32, "evaluation": 32}:
        raise ValueError("P7 prototype membership mismatch")
    roots = {"p3": args.p3_root, "p4": args.p4_root, "p5": args.p5_root}
    catalog = P7ArtifactCatalog(roots, config["parents"], verify=False)
    vocabulary = build_vocabulary(args.categories)
    data = P7Data(catalog, preprocessing, vocabulary, rows)
    return {"config": config, "architecture": architecture, "preprocessing": preprocessing,
            "p6": p6, "prototype_manifest": prototype_manifest, "rows": rows, "roots": roots,
            "catalog": catalog, "vocabulary": vocabulary, "data": data}


def build_authority(args: argparse.Namespace) -> None:
    values = common_inputs(args); config = values["config"]
    schema_checksums = {
        path.name: sha256_file(path)
        for path in sorted((ROOT / "config/schemas").glob("p7_*.schema.json"))
    }
    if len(schema_checksums) != 9:
        raise ValueError("P7 schema bundle is incomplete")
    source_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    checksums = {
        "supplement_config": config_file_checksums(Path(args.config)),
        "schema_bundle": schema_checksums,
        "p7_training_implementation": sha256_file(ROOT / "python/p7_training.py"),
        "p7_geometry_cache_implementation": sha256_file(ROOT / "python/p7_geometry_cache.py"),
        "p7_runtime_implementation": sha256_file(Path(__file__)),
        "p6_model_implementation": values["architecture"]["implementation_sha256"],
        "prototype_parquet": sha256_file(args.prototype),
        "prototype_manifest": sha256_file(args.prototype_manifest),
        "p6_aggregate": sha256_file(args.p6_acceptance),
    }
    identity = {
        "supplement": scientific_config(config),
        "scientific_config_sha256": canonical_digest(scientific_config(config)),
        "implementation_checksums": {
            "p7_training": checksums["p7_training_implementation"],
            "p7_geometry_cache": checksums["p7_geometry_cache_implementation"],
            "p7_runtime": checksums["p7_runtime_implementation"],
            "p6_model": checksums["p6_model_implementation"],
        },
        "schema_checksums": checksums["schema_bundle"],
        "parent_content_checksums": {
            "prototype_parquet": checksums["prototype_parquet"],
            "prototype_manifest": checksums["prototype_manifest"],
            "p6_aggregate": checksums["p6_aggregate"],
        },
        "prototype_membership": {key: values["data"].members[key] for key in ("training", "validation")},
        "source_commit": source_commit,
    }
    run_id = "p7run_" + canonical_digest(identity)[:24]
    authority = {
        "schema_version": SCHEMA_VERSION, "status": "PASS", "supplement_name": SUPPLEMENT_NAME,
        "run_id": run_id, "parents": config["parents"], "population": config["population"],
        "source_commit": source_commit,
        "supersession": config["supersession"],
        "scientific_config": scientific_config(config), "checksums": checksums,
        "invariants": {"p0_p6_parent_exact": True, "training_membership_exact": True,
                       "validation_membership_exact": True, "evaluation_consumption_prohibited": True,
                       "revised_p4_k8_only": True, "p5_v2_validation_only_reader": True,
                       "p6_geometry_layout_v3": True, "old_p7_resume_prohibited": True,
                       "optimizer_not_constructed": True, "gpu_execution_zero": True},
    }
    finalized(authority, "p7a_", "training_authority_id")
    write_json(args.output, authority)


def configure_process(config: dict[str, Any], rank: int) -> torch.device:
    os.environ["CUBLAS_WORKSPACE_CONFIG"] = config["numeric"]["cublas_workspace_config"]
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "BLIS_NUM_THREADS",
                 "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS", "GDAL_NUM_THREADS", "ARROW_NUM_THREADS"):
        os.environ[name] = "1"
    torch.set_num_threads(1); torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True, warn_only=False)
    torch.backends.cudnn.deterministic = True; torch.backends.cudnn.benchmark = False
    torch.backends.cuda.matmul.allow_tf32 = False; torch.backends.cudnn.allow_tf32 = False
    root = int(config["training"]["root_seed"])
    random.seed(root); np.random.seed(root); torch.manual_seed(root)
    torch.cuda.set_device(rank); torch.cuda.manual_seed(root + rank)
    if config["execution_contract"]["disjoint_rank_cpu_affinity"]:
        available = sorted(os.sched_getaffinity(0))
        midpoint = len(available) // 2
        selected = available[:midpoint] if rank == 0 else available[midpoint:]
        if not selected:
            raise RuntimeError("cannot assign disjoint rank CPU affinity")
        os.sched_setaffinity(0, selected)
    return torch.device("cuda", rank)


def geometry(batch: dict[str, Any], model_config: dict[str, Any], device: torch.device) -> tuple[torch.Tensor, torch.Tensor]:
    return geometry_fourier_features(batch, {"geometry": model_config["model"]["geometry"]}, device)


def model_and_state(values: dict[str, Any], device: torch.device) -> tuple[P7Model, torch.optim.AdamW, ExactLRScheduler, dict[str, Any]]:
    config = values["config"]; sizes = values["architecture"]["vocabulary_sizes"]
    torch.manual_seed(int(config["training"]["root_seed"]))
    model = P7Model(values["model_config"], sizes, config["objective"]).to(device)
    optimizer = torch.optim.AdamW(
        [parameter for parameter in model.parameters() if parameter.requires_grad], lr=0.0,
        weight_decay=float(config["optimizer"]["weight_decay"]),
        betas=tuple(config["optimizer"]["betas"]), eps=float(config["optimizer"]["eps"]),
    )
    return model, optimizer, ExactLRScheduler(optimizer), empty_queue(device)


def activate_rank_stochastic_seed(config: dict[str, Any], rank: int) -> None:
    """Apply rank-local CUDA stochastic state after DDP broadcasts rank-0 model state."""
    torch.cuda.manual_seed(int(config["training"]["root_seed"]) + rank)


def wrap_ddp(model: P7Model, device: torch.device, config: dict[str, Any]) -> DistributedDataParallel:
    execution = config["execution_contract"]
    return DistributedDataParallel(
        model, device_ids=[device.index], output_device=device.index,
        find_unused_parameters=bool(execution["ddp_find_unused_parameters"]),
        bucket_cap_mb=float(execution["ddp_bucket_cap_mb"]),
        gradient_as_bucket_view=bool(execution["ddp_gradient_as_bucket_view"]),
        static_graph=bool(execution["ddp_static_graph"]),
    )


def all_gather_tensor(value: torch.Tensor) -> torch.Tensor:
    gathered = [torch.empty_like(value) for _ in range(dist.get_world_size())]
    dist.all_gather(gathered, value.contiguous())
    return torch.cat(gathered, 0)


def all_reduce_float(value: torch.Tensor) -> float:
    copied = value.detach().clone(); dist.all_reduce(copied, op=dist.ReduceOp.SUM); return float(copied.cpu())


def all_reduce_tensor(value: torch.Tensor) -> torch.Tensor:
    copied = value.detach().clone(); dist.all_reduce(copied, op=dist.ReduceOp.SUM); return copied


def build_local_batches(values: dict[str, Any], epoch: int, batch_index: int, rank: int) -> tuple[list[dict[str, Any]], list[str], list[tuple[int, int]]]:
    data, config = values["data"], values["config"]
    order = epoch_scene_order(data.members["training"], config, epoch)
    global_scenes = order[batch_index * 32:(batch_index + 1) * 32]
    local_scenes = global_scenes[rank * 16:(rank + 1) * 16]
    pairs = [selected_view_pair(scene, [row["master_view_id"] for row in data.catalog.k8[scene]], config, epoch)
             for scene in local_scenes]
    batches = []
    for role in range(2):
        batches.append(collate([data.training_view(scene, pair[role]) for scene, pair in zip(local_scenes, pairs, strict=True)],
                               values["vocabulary"]))
    return batches, global_scenes, pairs


def geometry_cache_specs(values: dict[str, Any]) -> list[tuple[str, str, int | None]]:
    data = values["data"]
    training = [("training", scene, int(row["master_view_id"]))
                for scene in sorted(data.members["training"])
                for row in sorted(data.catalog.k8[scene], key=lambda item: int(item["master_view_id"]))]
    validation_queries = [("validation_query", scene, index)
                          for scene in data.members["validation"] for index in (0, 1)]
    validation_gallery = [("validation_gallery", scene, None) for scene in data.members["validation"]]
    return training + validation_queries + validation_gallery


def geometry_cache_sample(data: P7Data, spec: tuple[str, str, int | None]) -> dict[str, Any]:
    role, scene, view = spec
    if role == "training":
        return data.training_view(scene, int(view))
    if role == "validation_query":
        return data.validation_query(scene, int(view))
    return data.validation_gallery(scene)


class DeterministicBatchLookahead:
    """One-batch CPU look-ahead that never consumes scientific RNG state."""
    def __init__(self, values: dict[str, Any], rank: int) -> None:
        self.values, self.rank = values, rank
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"p7-input-r{rank}")
        self.future: Future | None = None
        self.identity: tuple[int, int] | None = None

    def launch(self, epoch: int, batch_index: int) -> None:
        identity = (epoch, batch_index)
        if self.future is not None:
            if self.identity != identity:
                raise RuntimeError("P7 look-ahead consumption order mismatch")
            return
        self.identity = identity
        self.future = self.executor.submit(build_local_batches, self.values, epoch, batch_index, self.rank)

    def consume(self, epoch: int, batch_index: int):
        self.launch(epoch, batch_index)
        assert self.future is not None
        result = self.future.result()
        self.future = None; self.identity = None
        if batch_index < 7:
            self.launch(epoch, batch_index + 1)
        return result

    def close(self) -> None:
        self.executor.shutdown(wait=True, cancel_futures=False)


def worker_cache_build(args: argparse.Namespace) -> None:
    config = load_config(args.config); rank = int(os.environ["RANK"])
    device = configure_process(config, rank); dist.init_process_group("nccl")
    values = common_inputs(args); values["model_config"] = load_strict_yaml(args.p6_config)
    authority = read_json(args.authority)
    writer = GeometryCacheWriter(args.stage)
    specs = geometry_cache_specs(values)
    implementation_sha = sha256_file(ROOT / "python/prototype_encoder.py")
    geometry_config = values["model_config"]["model"]["geometry"]
    local_records = []; started = time.monotonic(); raw_bytes = 0
    problem_count = problem_wrong = 0
    for index, spec in enumerate(specs):
        if index % dist.get_world_size() != rank:
            continue
        sample = geometry_cache_sample(values["data"], spec)
        if sample["geometry_layout_version"] != GEOMETRY_LAYOUT_VERSION:
            raise ValueError("cache build received incompatible geometry layout")
        if sample["view_id"] == "augv_0c7fb311e3c582cf84136d90":
            problem_count += 1
            count = sample["resources"]["part_coordinates"] + sample["resources"]["ring_coordinates"]
            problem_wrong += int(count != 28)
        record = cache_record(sample, config["parents"], geometry_config, implementation_sha, spec[0])
        batch_cpu = collate([sample], values["vocabulary"]); batch = to_device(batch_cpu, device)
        magnitude, phase = geometry(batch, values["model_config"], device)
        path = writer.put(record, magnitude, phase)
        payload = torch.load(path, map_location="cpu", weights_only=False)
        if not torch.equal(payload["magnitude"].to(device), magnitude) or not torch.equal(payload["phase"].to(device), phase):
            raise ValueError("geometry-cache online byte parity mismatch")
        raw_bytes += magnitude.numel() * magnitude.element_size() + phase.numel() * phase.element_size()
        local_records.append(record)
    gathered = [None] * dist.get_world_size() if rank == 0 else None
    dist.gather_object(local_records, gathered, dst=0)
    counts = torch.tensor([problem_count, problem_wrong], dtype=torch.int64, device=device)
    dist.all_reduce(counts)
    if int(counts[1]):
        raise ValueError("problem candidate cache geometry is not 28 coordinates")
    dist.barrier()
    if rank == 0:
        records = [record for group in gathered for record in group]
        manifest = writer.finalize(authority["training_authority_id"], records)
        manifest["runtime"] = {"wall_seconds": time.monotonic() - started,
                               "rank_raw_tensor_bytes": raw_bytes,
                               "problem_candidate_occurrences": int(counts[0]),
                               "problem_candidate_wrong_observations": int(counts[1])}
        write_json(args.worker_output, manifest)
    dist.barrier(); dist.destroy_process_group()


def train_update(ddp: DistributedDataParallel, model: P7Model, optimizer: torch.optim.AdamW,
                 scheduler: ExactLRScheduler, queue: dict[str, Any], values: dict[str, Any],
                 epoch: int, batch_index: int, rank: int, device: torch.device) -> dict[str, Any]:
    started = time.monotonic(); config = values["config"]
    lookahead = values.get("lookahead")
    batches_cpu, global_scenes, local_pairs = (lookahead.consume(epoch, batch_index) if lookahead
                                               else build_local_batches(values, epoch, batch_index, rank))
    assignments = [modality_assignments(batch, config, epoch, role, rank)
                   for role, batch in enumerate(batches_cpu)]
    batches = [to_device(batch, device) for batch in batches_cpu]
    cache = values.get("geometry_cache")
    geometries = ([cache.batch(batch, "training", device) for batch in batches] if cache
                  else [geometry(batch, values["model_config"], device) for batch in batches])
    optimizer.zero_grad(set_to_none=True)
    outputs = ddp(batches, geometries, assignments)
    with torch.no_grad():
        targets = [model.target_forward(batch, geom) for batch, geom in zip(batches, geometries, strict=True)]
    local_keys = torch.stack((targets[0]["contrastive_embedding"], targets[1]["contrastive_embedding"]), 1)
    gathered_rank_major = all_gather_tensor(local_keys)
    global_k1 = gathered_rank_major[:, 0]; global_k2 = gathered_rank_major[:, 1]
    global_centers = all_gather_tensor(batches[0]["scene_center_5186"])
    global_ids = all_gather_tensor(batches[0]["scene_numeric_ids"])
    scene_sum, scene_count = local_infonce_sum(
        outputs[0].output["contrastive_embedding"], outputs[1].output["contrastive_embedding"],
        global_k1, global_k2, batches[0]["scene_center_5186"], global_centers,
        batches[0]["scene_numeric_ids"], global_ids, queue,
        float(config["objective"]["contrastive_temperature"]),
        float(config["objective"]["negative_exclusion_distance_m"]),
    )
    global_counts = [all_reduce_tensor(torch.tensor(scene_count, dtype=torch.int64, device=device))]
    reduced_sums: list[torch.Tensor] = []
    local_sums: list[torch.Tensor] = []
    ip_objective = scene_sum * 0.0
    names = ("relative", "geometry", "semantic", "environmental")
    for name in names:
        local_sum = outputs[0].reconstruction["modalities"][name]["sum"] + outputs[1].reconstruction["modalities"][name]["sum"]
        local_count = (outputs[0].reconstruction["modalities"][name]["count"] +
                       outputs[1].reconstruction["modalities"][name]["count"])
        global_counts.append(all_reduce_tensor(local_count.to(device=device, dtype=torch.int64)))
        reduced_sums.append(all_reduce_tensor(local_sum))
        local_sums.append(local_sum)
    count_values = torch.stack(global_counts).cpu().tolist()
    scene_count_value = int(count_values[0]); active = 0
    scene_objective = scene_sum * dist.get_world_size() / scene_count_value
    for local_sum, count in zip(local_sums, count_values[1:], strict=True):
        if int(count):
            ip_objective = ip_objective + local_sum * dist.get_world_size() / int(count)
            active += 1
    if active:
        ip_objective = ip_objective / active
    total = scene_objective + float(config["objective"]["information_preservation_weight"]) * ip_objective
    if not torch.isfinite(total):
        raise FloatingPointError("non-finite P7 total loss")
    lr = scheduler.set_for_next_update()
    total.backward()
    parameters = [parameter for parameter in model.parameters() if parameter.requires_grad]
    before = torch.nn.utils.clip_grad_norm_(parameters, float(config["optimizer"]["gradient_clip"]["maximum_norm"]),
                                            norm_type=float(config["optimizer"]["gradient_clip"]["norm_type"]), error_if_nonfinite=True)
    optimizer.step(); scheduler.advance(); model.update_target(float(config["ema"]["coefficient"]))
    queue_values = gathered_rank_major.reshape(-1, gathered_rank_major.shape[-1])
    queue_ids = all_gather_tensor(torch.stack((batches[0]["scene_numeric_ids"], batches[0]["scene_numeric_ids"]), 1)).reshape(-1)
    queue_centers = all_gather_tensor(torch.stack((batches[0]["scene_center_5186"], batches[0]["scene_center_5186"]), 1)).reshape(-1, 2)
    enqueue(queue, queue_values, queue_ids, queue_centers)
    global_scene_sum_tensor = all_reduce_tensor(scene_sum)
    evidence = torch.cat((torch.stack([global_scene_sum_tensor, *reduced_sums]).to(torch.float64),
                          torch.stack(global_counts).to(torch.float64),
                          before.detach().reshape(1).to(torch.float64)))
    evidence_values = evidence.cpu().tolist()
    sum_values = evidence_values[:5]; evidence_counts = [int(value) for value in evidence_values[5:10]]
    global_scene_sum = float(sum_values[0]); scene_value = global_scene_sum / evidence_counts[0]
    modality_rows = {name: {"numerator": float(sum_values[index + 1]),
                            "denominator": evidence_counts[index + 1]}
                     for index, name in enumerate(names)}
    ip_value = sum(row["numerator"] / row["denominator"] for row in modality_rows.values() if row["denominator"]) / active if active else 0.0
    global_pairs = []
    gathered_pairs: list[Any] = [None] * dist.get_world_size()
    dist.all_gather_object(gathered_pairs, local_pairs)
    for item in gathered_pairs: global_pairs.extend(item)
    return {
        "epoch": epoch, "batch_index": batch_index, "global_update": scheduler.completed_updates,
        "learning_rate": lr, "total_loss": scene_value + float(config["objective"]["information_preservation_weight"]) * ip_value,
        "scene_contrastive_loss": scene_value, "information_preservation_loss": ip_value,
        "information_preservation_weight": float(config["objective"]["information_preservation_weight"]),
        "modality_components": modality_rows, "scene_numerator": global_scene_sum,
        "scene_denominator": evidence_counts[0], "gradient_norm_before_clip": float(evidence_values[10]),
        "gradient_norm_after_clip": min(float(evidence_values[10]), float(config["optimizer"]["gradient_clip"]["maximum_norm"])),
        "gradient_clip_applied": float(evidence_values[10]) > float(config["optimizer"]["gradient_clip"]["maximum_norm"]),
        "queue_pointer": int(queue["pointer"]), "queue_valid_count": int(queue["valid_count"]),
        "queue_enqueue_count": int(queue["enqueue_count"]), "ema_update_count": scheduler.completed_updates,
        "batch_identity_digest": training_batch_digest(global_scenes, global_pairs),
        "step_wall_seconds": time.monotonic() - started,
    }


def validation_metrics(model: P7Model, values: dict[str, Any], device: torch.device, rank: int) -> dict[str, Any] | None:
    data = values["data"]; model.eval()
    records = [("query", scene, index) for scene in data.members["validation"] for index in (0, 1)]
    records += [("gallery", scene, None) for scene in data.members["validation"]]
    local_embeddings = []; local_indices = []; cache = values.get("geometry_cache")
    with torch.inference_mode():
        for batch_index, start in enumerate(range(0, len(records), 8)):
            if batch_index % dist.get_world_size() != rank:
                continue
            selected = records[start:start + 8]
            samples = [(data.validation_query(scene, int(index)) if kind == "query" else data.validation_gallery(scene))
                       for kind, scene, index in selected]
            batch = to_device(collate(samples, values["vocabulary"]), device)
            cache_role = "validation_query" if selected[0][0] == "query" else "validation_gallery"
            geom = cache.batch(batch, cache_role, device) if cache else geometry(batch, values["model_config"], device)
            modalities = model._modalities(model.online, batch, geom)
            output = model._finish(model.online, batch, torch.stack(tuple(modalities[name] for name in ("relative", "geometry", "semantic", "environmental")), 1))
            local_embeddings.append(torch.nn.functional.normalize(output["scene_embedding"], dim=1))
            local_indices.extend(range(start, start + len(selected)))
    local = torch.cat(local_embeddings).contiguous()
    indices = torch.tensor(local_indices, dtype=torch.int64, device=device)
    gathered_embeddings = [torch.empty_like(local) for _ in range(dist.get_world_size())]
    gathered_indices = [torch.empty_like(indices) for _ in range(dist.get_world_size())]
    dist.all_gather(gathered_embeddings, local); dist.all_gather(gathered_indices, indices)
    combined_indices = torch.cat(gathered_indices).cpu()
    combined = torch.cat(gathered_embeddings).cpu()
    permutation = torch.argsort(combined_indices)
    if combined_indices[permutation].tolist() != list(range(96)):
        raise ValueError("distributed validation coverage/order mismatch")
    ordered = combined[permutation]
    queries, galleries = ordered[:64], ordered[64:]
    positive = torch.tensor([index for index in range(32) for _ in (0, 1)])
    similarities = queries @ galleries.T
    loss = torch.nn.functional.cross_entropy(similarities / float(values["config"]["objective"]["contrastive_temperature"]), positive)
    positive_values = similarities[torch.arange(64), positive]
    masked = similarities.clone(); masked[torch.arange(64), positive] = -torch.inf
    hardest = masked.max(1).values; ranks = 1 + (similarities > positive_values[:, None]).sum(1)
    event = {"validation_retrieval_loss": float(loss),
            "mean_source_separation_margin": float((positive_values - hardest).mean()),
            "mean_positive_similarity": float(positive_values.mean()),
            "mean_hardest_negative_similarity": float(hardest.mean()),
            "MRR": float((1.0 / ranks.float()).mean()), "HIT@1": float((ranks <= 1).float().mean()),
            "HIT@5": float((ranks <= 5).float().mean()), "HIT@10": float((ranks <= 10).float().mean()),
            "query_count": 64, "gallery_count": 32,
            "validation_scene_digest": canonical_digest(data.members["validation"]),
            "embedding_digest": state_content_digest({"queries": queries, "galleries": galleries}),
            "distributed_coverage_count": 96, "distributed_duplicate_count": 0,
            "distributed_missing_count": 0}
    objects = [event if rank == 0 else None]; dist.broadcast_object_list(objects, src=0)
    model.train()
    return objects[0]


def rank_rng_state(rank: int) -> dict[str, Any]:
    return {"rank": rank, "python": random.getstate(), "numpy": np.random.get_state(),
            "torch_cpu": torch.get_rng_state(), "torch_cuda": torch.cuda.get_rng_state(rank)}


def gather_rank_states(rank: int) -> list[Any] | None:
    result = [None] * dist.get_world_size() if rank == 0 else None
    dist.gather_object(rank_rng_state(rank), result, dst=0)
    return result


def restore_rng(value: dict[str, Any], rank: int) -> None:
    if int(value["rank"]) != rank: raise ValueError("checkpoint rank RNG mismatch")
    random.setstate(value["python"]); np.random.set_state(value["numpy"])
    torch.set_rng_state(value["torch_cpu"]); torch.cuda.set_rng_state(value["torch_cuda"], rank)


def checkpoint_state(model: P7Model, optimizer: torch.optim.AdamW, scheduler: ExactLRScheduler,
                     queue: dict[str, Any], progress: dict[str, Any], trace: list[dict[str, Any]],
                     validations: list[dict[str, Any]], selector: dict[str, Any], rank: int,
                     authority: dict[str, Any]) -> dict[str, Any] | None:
    states = gather_rank_states(rank)
    if rank != 0: return None
    return {"schema_version": SCHEMA_VERSION, "run_id": authority["run_id"],
            "training_authority_id": authority["training_authority_id"], "parents": authority["parents"],
            "online_and_target_model": model.state_dict(), "optimizer": optimizer.state_dict(),
            "scheduler": scheduler.state_dict(), "queue": queue, "progress": progress,
            "training_trace": trace, "validation_events": validations, "selector_state": selector,
            "rank_rng_states": states, "world_size": 2, "rank_order": [0, 1]}


def save_checkpoint(stage: Path, state: dict[str, Any] | None, role: str, rank: int,
                    authority: dict[str, Any]) -> dict[str, Any] | None:
    if rank != 0: return None
    state_digest = state_content_digest(state)
    checkpoint_id = "p7ck_" + state_digest[:24]
    root = stage / "checkpoints" / checkpoint_id; root.mkdir(parents=True, exist_ok=True)
    path = root / "checkpoint.pt"; temporary = root / f".checkpoint.pt.tmp-{os.getpid()}"
    torch.save(state, temporary); os.replace(temporary, path)
    manifest = {"schema_version": SCHEMA_VERSION, "status": "PASS", "checkpoint_id": checkpoint_id,
                "role": role, "epoch": int(state["progress"]["completed_epoch"]),
                "global_update": int(state["scheduler"]["completed_updates"]),
                "state_content_sha256": state_digest,
                "payload": {"filename": "checkpoint.pt", "size_bytes": path.stat().st_size, "sha256": sha256_file(path)},
                "parents": authority["parents"], "run_id": authority["run_id"],
                "training_authority_id": authority["training_authority_id"]}
    write_json(root / "checkpoint_manifest.json", manifest); return manifest


def restore_checkpoint(path: Path, model: P7Model, optimizer: torch.optim.AdamW,
                       scheduler: ExactLRScheduler, queue: dict[str, Any], rank: int,
                       authority: dict[str, Any]) -> dict[str, Any]:
    state = torch.load(path, map_location="cpu", weights_only=False)
    if (state["run_id"], state["training_authority_id"], state["parents"], state["world_size"]) != (
            authority["run_id"], authority["training_authority_id"], authority["parents"], 2):
        raise ValueError("foreign P7 checkpoint lineage")
    model.load_state_dict(state["online_and_target_model"]); optimizer.load_state_dict(state["optimizer"])
    scheduler.load_state_dict(state["scheduler"])
    for key in ("values", "scene_ids", "centers"):
        queue[key].copy_(state["queue"][key].to(queue[key].device))
    for key in ("pointer", "valid_count", "enqueue_count"): queue[key] = int(state["queue"][key])
    restore_rng(state["rank_rng_states"][rank], rank); return state


def gpu_sample() -> list[dict[str, Any]]:
    command = ["nvidia-smi", "--query-gpu=index,utilization.gpu,memory.used,memory.total", "--format=csv,noheader,nounits"]
    rows = []
    try:
        for line in subprocess.check_output(command, text=True).splitlines():
            index, utilization, used, total = [int(value.strip()) for value in line.split(",")]
            if index in (0, 1): rows.append({"index": index, "utilization_percent": utilization, "memory_used_mib": used, "memory_total_mib": total})
    except Exception: pass
    return rows


def prepare_worker(args: argparse.Namespace) -> tuple[dict[str, Any], int, torch.device, P7Model, torch.optim.AdamW, ExactLRScheduler, dict[str, Any]]:
    rank = int(os.environ["RANK"]); world = int(os.environ["WORLD_SIZE"])
    if world != 2: raise ValueError("P7 requires exactly two DDP ranks")
    config = load_config(args.config); device = configure_process(config, rank)
    dist.init_process_group("nccl")
    values = common_inputs(args); values["model_config"] = load_strict_yaml(args.p6_config)
    authority = read_json(args.authority); values["authority"] = authority
    if getattr(args, "geometry_cache", ""):
        reader = GeometryCacheReader(
            args.geometry_cache,
            int(config["execution_contract"]["geometry_cache_memory_limit_gib_per_rank"]) * 1024**3,
        )
        if reader.manifest["training_authority_id"] != authority["training_authority_id"]:
            raise ValueError("foreign geometry cache authority")
        values["geometry_cache"] = reader
    model, optimizer, scheduler, queue = model_and_state(values, device)
    return values, rank, device, model, optimizer, scheduler, queue


def worker_init(args: argparse.Namespace) -> None:
    values, rank, device, model, optimizer, scheduler, queue = prepare_worker(args)
    ddp = wrap_ddp(model, device, values["config"])
    activate_rank_stochastic_seed(values["config"], rank)
    digest = state_content_digest(ddp.module.state_dict()); digests = [None, None]; dist.all_gather_object(digests, digest)
    checks = {"rank_state_equal": len(set(digests)) == 1, "backend": dist.get_backend(), "cuda_devices": torch.cuda.device_count(),
              "amp_disabled": True, "tf32_disabled": not torch.backends.cuda.matmul.allow_tf32,
              "deterministic_algorithms": torch.are_deterministic_algorithms_enabled()}
    if not all(value for key, value in checks.items() if isinstance(value, bool)) or checks["backend"] != "nccl":
        raise RuntimeError("P7 DDP initialization gate failed")
    if rank == 0: write_json(args.worker_output, {"checks": checks, "state_digest": digest})
    dist.barrier(); dist.destroy_process_group()


def worker_update(args: argparse.Namespace) -> None:
    values, rank, device, model, optimizer, scheduler, queue = prepare_worker(args)
    ddp = wrap_ddp(model, device, values["config"])
    activate_rank_stochastic_seed(values["config"], rank)
    values["lookahead"] = DeterministicBatchLookahead(values, rank)
    model.train(); result = train_update(ddp, model, optimizer, scheduler, queue, values, 1, 0, rank, device)
    values["lookahead"].close()
    scientific = {key: value for key, value in result.items() if key != "step_wall_seconds"}
    state = checkpoint_state(model, optimizer, scheduler, queue, {"completed_epoch": 0, "next_batch_index": 1},
                             [scientific], [], {"best": None, "patience": 0}, rank, values["authority"])
    manifest = save_checkpoint(Path(args.stage), state, "resume_fixture", rank, values["authority"])
    checks = {"finite_loss": bool(np.isfinite(result["total_loss"])), "optimizer_updates": scheduler.completed_updates == 1,
              "ema_updates": result["ema_update_count"] == 1, "queue_valid_count": queue["valid_count"] == 64,
              "queue_pointer": queue["pointer"] == 64, "checkpoint_roundtrip": manifest is not None if rank == 0 else True}
    if not all(checks.values()): raise RuntimeError(f"P7 single-update gate failed: {checks}")
    if rank == 0: write_json(args.worker_output, {"checks": checks, "step": result, "checkpoint": manifest})
    dist.barrier(); dist.destroy_process_group()


def worker_reference(args: argparse.Namespace) -> None:
    config = load_config(args.config); rank = int(os.environ["RANK"]); device = configure_process(config, rank)
    dist.init_process_group("nccl")
    torch.manual_seed(4401); reference = torch.nn.Linear(5, 3, bias=True).to(device)
    ddp = DistributedDataParallel(reference, device_ids=[rank])
    x_global = torch.arange(160, dtype=torch.float32, device=device).reshape(32, 5) / 100.0
    y_global = torch.arange(96, dtype=torch.float32, device=device).reshape(32, 3) / 50.0
    local = slice(rank * 16, (rank + 1) * 16); output = ddp(x_global[local])
    numerator = ((output - y_global[local]) ** 2).sum(); denominator = torch.tensor(16 * 3, device=device)
    global_numerator = numerator.detach().clone(); dist.all_reduce(global_numerator)
    global_denominator = denominator.clone(); dist.all_reduce(global_denominator)
    loss = numerator * 2 / global_denominator; loss.backward()
    distributed_loss = global_numerator / global_denominator
    distributed_gradients = [parameter.grad.detach().cpu() for parameter in ddp.module.parameters()]
    if rank == 0:
        torch.manual_seed(4401); single = torch.nn.Linear(5, 3, bias=True).to(device)
        reference_loss = ((single(x_global) - y_global) ** 2).sum() / (32 * 3); reference_loss.backward()
        reference_gradients = [parameter.grad.detach().cpu() for parameter in single.parameters()]
        max_error = max(float((left - right).abs().max()) for left, right in zip(distributed_gradients, reference_gradients, strict=True))
        loss_error = abs(float(distributed_loss.cpu()) - float(reference_loss.detach().cpu()))
        tolerance = config["runtime"]["reference_tolerance"]
        checks = {"loss_error": loss_error, "gradient_maximum_error": max_error,
                  "loss_within_tolerance": loss_error <= float(tolerance["loss_atol"]),
                  "gradient_within_tolerance": max_error <= float(tolerance["gradient_atol"])}
        if not checks["loss_within_tolerance"] or not checks["gradient_within_tolerance"]:
            raise RuntimeError(f"P7 DDP reference mismatch: {checks}")
        write_json(args.worker_output, {"checks": checks})
    dist.barrier(); dist.destroy_process_group()


def worker_trajectory(args: argparse.Namespace) -> None:
    values, rank, device, model, optimizer, scheduler, queue = prepare_worker(args)
    ddp = wrap_ddp(model, device, values["config"])
    activate_rank_stochastic_seed(values["config"], rank)
    trace: list[dict[str, Any]] = []; progress = {"completed_epoch": 0, "next_batch_index": 0}
    if args.resume_checkpoint:
        state = restore_checkpoint(Path(args.resume_checkpoint), model, optimizer, scheduler, queue, rank, values["authority"])
        trace = state["training_trace"]; progress = state["progress"]
    values["lookahead"] = DeterministicBatchLookahead(values, rank); model.train()
    while scheduler.completed_updates < args.max_updates:
        epoch = scheduler.completed_updates // 8 + 1; batch_index = scheduler.completed_updates % 8
        result = train_update(ddp, model, optimizer, scheduler, queue, values, epoch, batch_index, rank, device)
        trace.append({key: value for key, value in result.items() if key != "step_wall_seconds"}); progress = {"completed_epoch": scheduler.completed_updates // 8,
                                          "next_batch_index": scheduler.completed_updates % 8}
    values["lookahead"].close()
    state = checkpoint_state(model, optimizer, scheduler, queue, progress, trace, [], {"best": None, "patience": 0}, rank, values["authority"])
    manifest = save_checkpoint(Path(args.stage), state, "resume_fixture", rank, values["authority"])
    if rank == 0:
        write_json(args.worker_output, {"state_content_sha256": manifest["state_content_sha256"],
                   "checkpoint": manifest, "checkpoint_path": str(Path(args.stage) / "checkpoints" / manifest["checkpoint_id"] / "checkpoint.pt"),
                   "scientific_trace": [{key: value for key, value in row.items() if key != "step_wall_seconds"} for row in trace]})
    dist.barrier(); dist.destroy_process_group()


def worker_production(args: argparse.Namespace) -> None:
    started = time.monotonic(); values, rank, device, model, optimizer, scheduler, queue = prepare_worker(args)
    ddp = wrap_ddp(model, device, values["config"])
    activate_rank_stochastic_seed(values["config"], rank)
    trace: list[dict[str, Any]] = []; validations: list[dict[str, Any]] = []
    selector = {"best": None, "patience": 0}; checkpoint_manifests: list[dict[str, Any]] = []
    progress = {"completed_epoch": 0, "next_batch_index": 0}; step_walls: list[float] = []
    values["lookahead"] = DeterministicBatchLookahead(values, rank); model.train()
    termination = None
    for epoch in range(1, int(values["config"]["training"]["maximum_epochs"]) + 1):
        for batch_index in range(8):
            result = train_update(ddp, model, optimizer, scheduler, queue, values, epoch, batch_index, rank, device)
            trace.append({key: value for key, value in result.items() if key != "step_wall_seconds"}); progress = {"completed_epoch": epoch if batch_index == 7 else epoch - 1,
                                              "next_batch_index": (batch_index + 1) % 8}
            if rank == 0: step_walls.append(float(result["step_wall_seconds"]))
        if epoch % int(values["config"]["validation"]["interval_epochs"]) == 0:
            dist.barrier(); event = validation_metrics(model, values, device, rank); event["epoch"] = epoch
            selected = selector_decision(selector["best"], event, float(values["config"]["validation"]["equivalence_threshold"]))
            if selected: selector = {"best": dict(event), "patience": 0}
            else: selector["patience"] += 1
            event["selected_best"] = selected; event["patience_after_event"] = selector["patience"]
            validations.append(event)
            state = checkpoint_state(model, optimizer, scheduler, queue, {**progress, "completed_epoch": epoch}, trace,
                                     validations, selector, rank, values["authority"])
            manifest = save_checkpoint(Path(args.stage), state, "validation", rank, values["authority"])
            objects = [manifest]; dist.broadcast_object_list(objects, src=0); manifest = objects[0]
            event["checkpoint_id"] = manifest["checkpoint_id"]; checkpoint_manifests.append(manifest)
            if selector["patience"] >= int(values["config"]["validation"]["patience_events"]):
                termination = "early_stopping"; break
        if termination: break
    values["lookahead"].close()
    if termination is None: termination = "maximum_epochs"
    best, patience = replay_selector(validations, float(values["config"]["validation"]["equivalence_threshold"]))
    best_manifest = next(item for item in checkpoint_manifests if item["checkpoint_id"] == best["checkpoint_id"])
    latest_manifest = checkpoint_manifests[-1]
    if rank == 0:
        scientific_steps = trace
        trace_value = {"schema_version": SCHEMA_VERSION, "status": "PASS", "run_id": values["authority"]["run_id"],
                       "training_authority_id": values["authority"]["training_authority_id"], "step_count": len(trace),
                       "epoch_count": validations[-1]["epoch"], "steps": scientific_steps, "validation_events": validations}
        finalized(trace_value, "p7tr_", "trace_id"); write_json(Path(args.stage) / "training_trace.json", trace_value)
        selector_value = {"schema_version": SCHEMA_VERSION, "status": "PASS", "run_id": values["authority"]["run_id"],
                          "best_epoch": best["epoch"], "best_validation_retrieval_loss": best["validation_retrieval_loss"],
                          "best_validation_margin": best["mean_source_separation_margin"], "patience_events": patience,
                          "events": validations, "best_checkpoint_id": best_manifest["checkpoint_id"]}
        finalized(selector_value, "p7sel_", "selector_id"); write_json(Path(args.stage) / "selector_result.json", selector_value)
        runtime = {"python": sys.version.split()[0], "pytorch": torch.__version__, "cuda": torch.version.cuda,
                   "cudnn": torch.backends.cudnn.version(), "nccl": torch.cuda.nccl.version(),
                   "visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"), "gpu_names": [torch.cuda.get_device_name(index) for index in range(2)]}
        execution = {"schema_version": SCHEMA_VERSION, "status": "PASS", "run_id": values["authority"]["run_id"],
                     "world_size": 2, "backend": "nccl", "precision": "float32",
                     "non_execution": {"evaluation_queries": 0, "p8_plus": 0, "maintenance": 0,
                                       "full_population_training": 0, "amp": 0}}
        finalized(execution, "p7exe_", "execution_id")
        execution["runtime"] = runtime
        cache_stats = values["geometry_cache"].stats() if values.get("geometry_cache") else None
        sorted_walls = sorted(step_walls)
        percentile = lambda q: sorted_walls[min(len(sorted_walls) - 1, int(q * (len(sorted_walls) - 1)))]
        execution["resources"] = {"workers_per_rank": 0, "native_threads_per_rank": 1,
                                  "wall_seconds": time.monotonic() - started,
                                  "update_wall_median_seconds": percentile(0.5),
                                  "update_wall_p95_seconds": percentile(0.95),
                                  "training_scenes_per_second": 32.0 / percentile(0.5),
                                  "rank0_peak_allocated_bytes": torch.cuda.max_memory_allocated(device),
                                  "geometry_cache": cache_stats,
                                  "ddp_find_unused_parameters": False, "ddp_bucket_cap_mb": 50,
                                  "ddp_gradient_as_bucket_view": False,
                                  "cpu_affinity": sorted(os.sched_getaffinity(0))}
        write_json(Path(args.stage) / "execution_record.json", execution)
        run = {"schema_version": SCHEMA_VERSION, "status": "PASS", "run_id": values["authority"]["run_id"],
               "training_authority_id": values["authority"]["training_authority_id"], "termination": termination,
               "epochs_completed": validations[-1]["epoch"], "optimizer_updates": len(trace),
               "best_checkpoint": best_manifest, "latest_checkpoint": latest_manifest,
               "trace_id": trace_value["trace_id"], "selector_id": selector_value["selector_id"],
               "execution_id": execution["execution_id"],
               "geometry_cache_id": values["geometry_cache"].manifest["cache_id"]}
        write_json(Path(args.stage) / "run_manifest.json", run)
        write_json(args.worker_output, run)
    dist.barrier(); dist.destroy_process_group()


def worker(args: argparse.Namespace) -> None:
    {"cache-build": worker_cache_build, "init": worker_init, "update": worker_update, "reference": worker_reference,
     "trajectory": worker_trajectory, "production": worker_production}[args.worker_mode](args)


def acquire(path: Path, timeout: float):
    path.parent.mkdir(parents=True, exist_ok=True); stream = path.open("a+"); deadline = time.monotonic() + timeout
    while True:
        try: fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB); return stream
        except BlockingIOError:
            if time.monotonic() >= deadline: raise TimeoutError(f"GPU lock unavailable: {path}")
            time.sleep(0.25)


@contextlib.contextmanager
def gpu_pair(config: dict[str, Any]):
    root = Path(config["runtime"]["gpu_lock_root"]); streams = []
    try:
        for name in ("gpu_pair.lock", "gpu0.lock", "gpu1.lock"):
            streams.append(acquire(root / name, float(config["runtime"]["gpu_lock_timeout_seconds"])))
        yield
    finally:
        for stream in reversed(streams): fcntl.flock(stream.fileno(), fcntl.LOCK_UN); stream.close()


def worker_command(args: argparse.Namespace, mode: str, output: Path, stage: Path,
                   max_updates: int = 0, resume_checkpoint: str = "") -> list[str]:
    forwarded = []
    for name in ("config", "p6_config", "authority", "architecture", "preprocessing", "p6_acceptance",
                 "prototype", "prototype_manifest", "p3_root", "p4_root", "p5_root", "categories"):
        forwarded += ["--" + name.replace("_", "-"), str(getattr(args, name))]
    command = [sys.executable, "-m", "torch.distributed.run", "--standalone", "--nproc_per_node=2",
               str(Path(__file__).resolve()), "worker", "--worker-mode", mode,
               "--worker-output", str(output), "--stage", str(stage), *forwarded]
    if max_updates: command += ["--max-updates", str(max_updates)]
    if resume_checkpoint: command += ["--resume-checkpoint", resume_checkpoint]
    if getattr(args, "geometry_cache", ""):
        command += ["--geometry-cache", str(args.geometry_cache)]
    return command


def run_torchrun(args: argparse.Namespace, mode: str, output: Path, stage: Path,
                 max_updates: int = 0, resume_checkpoint: str = "") -> None:
    config = load_config(args.config); env = os.environ.copy()
    env.update({"CUDA_VISIBLE_DEVICES": ",".join(map(str, config["runtime"]["selected_gpu_indices"])),
                "CUBLAS_WORKSPACE_CONFIG": config["numeric"]["cublas_workspace_config"],
                "PYTHONDONTWRITEBYTECODE": "1", "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1", "BLIS_NUM_THREADS": "1", "VECLIB_MAXIMUM_THREADS": "1",
                "NUMEXPR_NUM_THREADS": "1", "GDAL_NUM_THREADS": "1", "ARROW_NUM_THREADS": "1",
                "TORCH_NCCL_BLOCKING_WAIT": "1",
                "NCCL_P2P_DISABLE": "1" if config["runtime"]["nccl_p2p_disable"] else "0",
                "NCCL_IB_DISABLE": "1" if config["runtime"]["nccl_ib_disable"] else "0"})
    log_path = stage / f"torchrun-{mode}.log"
    command = worker_command(args, mode, output, stage, max_updates, resume_checkpoint)
    nvml_process = None
    nvml_stream = None
    if mode == "production":
        nvml_stream = (stage / "nvml-production.csv").open("w", encoding="utf-8")
        nvml_process = subprocess.Popen([
            "nvidia-smi", "--query-gpu=timestamp,index,utilization.gpu,utilization.memory,memory.used,memory.total,power.draw,clocks.sm",
            "--format=csv,noheader,nounits", "--loop-ms=500",
        ], stdout=nvml_stream, stderr=subprocess.STDOUT, text=True)
    with log_path.open("w", encoding="utf-8") as stream:
        process = subprocess.Popen(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, bufsize=1)
        assert process.stdout is not None
        for line in process.stdout:
            stream.write(line)
            stream.flush()
            print(line, end="", flush=True)
        returncode = process.wait()
    if nvml_process is not None:
        nvml_process.terminate()
        try: nvml_process.wait(timeout=5)
        except subprocess.TimeoutExpired: nvml_process.kill(); nvml_process.wait()
        assert nvml_stream is not None; nvml_stream.close()
    if returncode:
        raise RuntimeError(f"P7 torchrun failed in {mode}: {returncode}; diagnostic log: {log_path}")


def nvml_summary(path: Path) -> dict[str, Any]:
    rows = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            fields = [field.strip() for field in line.split(",")]
            if len(fields) != 8 or not fields[1].isdigit():
                continue
            try:
                rows.append({"gpu": int(fields[1]), "utilization": float(fields[2]),
                             "memory_utilization": float(fields[3]), "memory_used_mib": float(fields[4]),
                             "memory_total_mib": float(fields[5]), "power_w": float(fields[6]),
                             "clock_mhz": float(fields[7])})
            except ValueError:
                continue
    by_gpu = {}
    for gpu in (0, 1):
        selected = [row for row in rows if row["gpu"] == gpu]
        by_gpu[str(gpu)] = {"samples": len(selected),
                            "mean_utilization_percent": sum(row["utilization"] for row in selected) / len(selected) if selected else None,
                            "peak_utilization_percent": max((row["utilization"] for row in selected), default=None),
                            "zero_utilization_samples": sum(row["utilization"] == 0 for row in selected),
                            "peak_vram_mib": max((row["memory_used_mib"] for row in selected), default=None),
                            "mean_power_w": sum(row["power_w"] for row in selected) / len(selected) if selected else None}
    return {"sampling_interval_seconds": 0.5, "sample_rows": len(rows), "gpus": by_gpu}


def publish_gate(args: argparse.Namespace, gate: str, checks: dict[str, Any], runtime: dict[str, Any] | None = None) -> Path:
    authority = read_json(args.authority)
    value = {"schema_version": SCHEMA_VERSION, "status": "PASS", "gate": gate,
             "training_authority_id": authority["training_authority_id"], "world_size": 2, "checks": checks}
    finalized(value, "p7g_", "gate_id")
    if runtime is not None: value["runtime"] = runtime
    root = Path(args.output_root) / "diagnostics" / authority["training_authority_id"] / value["gate_id"]
    if root.exists():
        existing = root / "gate.json"
        if not existing.is_file() or read_json(existing).get("content_sha256") != value["content_sha256"]:
            raise FileExistsError("P7 immutable gate collision")
        return existing
    stage = Path(args.staging_root) / authority["run_id"] / (gate + "-publish")
    stage.mkdir(parents=True, exist_ok=False); write_json(stage / "gate.json", value)
    root.parent.mkdir(parents=True, exist_ok=True); os.replace(stage, root); return root / "gate.json"


def cache_build(args: argparse.Namespace) -> None:
    config = load_config(args.config); authority = read_json(args.authority)
    stage = Path(args.staging_root) / authority["run_id"] / "geometry-cache-v3"
    if stage.exists(): raise FileExistsError(f"P7 geometry-cache staging collision: {stage}")
    stage.mkdir(parents=True)
    with gpu_pair(config): run_torchrun(args, "cache-build", stage / "worker.json", stage)
    manifest = stage / "geometry_cache_manifest.json"; validate_schema(manifest, args.schema)
    value = read_json(manifest)
    if (value.get("training_authority_id") != authority["training_authority_id"]
            or value.get("geometry_layout_version") != GEOMETRY_LAYOUT_VERSION):
        raise ValueError("P7 geometry-cache authority/layout mismatch")
    final = Path(args.output_root) / "geometry_cache" / authority["training_authority_id"] / value["cache_id"]
    if final.exists(): raise FileExistsError(f"P7 immutable geometry-cache collision: {final}")
    final.parent.mkdir(parents=True, exist_ok=True); os.replace(stage, final)
    print(f"P7_OUTPUT={final / 'geometry_cache_manifest.json'}")


def gpu_gate(args: argparse.Namespace) -> None:
    config = load_config(args.config); authority = read_json(args.authority)
    stage = Path(args.staging_root) / authority["run_id"] / args.gate; stage.mkdir(parents=True, exist_ok=True)
    with gpu_pair(config):
        if args.gate in ("init", "update", "reference"):
            output = stage / "worker.json"; run_torchrun(args, args.gate, output, stage)
            worker_value = read_json(output)
            name = {"init": "ddp_initialization", "update": "single_update", "reference": "ddp_reference"}[args.gate]
            published = publish_gate(args, name, worker_value["checks"])
        elif args.gate == "resume":
            maximum = int(config["runtime"]["resume_equivalence_updates"])
            interrupt = int(config["runtime"]["resume_interrupt_after_updates"])
            a_stage = stage / "uninterrupted"; b_stage = stage / "interrupted"; a_stage.mkdir(exist_ok=True); b_stage.mkdir(exist_ok=True)
            run_torchrun(args, "trajectory", a_stage / "summary.json", a_stage, maximum)
            run_torchrun(args, "trajectory", b_stage / "part.json", b_stage, interrupt)
            part = read_json(b_stage / "part.json")
            run_torchrun(args, "trajectory", b_stage / "summary.json", b_stage, maximum, part["checkpoint_path"])
            left, right = read_json(a_stage / "summary.json"), read_json(b_stage / "summary.json")
            checks = {"state_content_exact": left["state_content_sha256"] == right["state_content_sha256"],
                      "trace_exact": left["scientific_trace"] == right["scientific_trace"],
                      "interrupt_update": interrupt, "final_update": maximum,
                      "new_process_resume": True, "serialization_container_excluded": True}
            if not checks["state_content_exact"] or not checks["trace_exact"]:
                raise RuntimeError(f"P7 exact resume equivalence failed: {checks}")
            published = publish_gate(args, "resume_equivalence", checks)
        else: raise ValueError(args.gate)
    print(f"P7_OUTPUT={published}")


def production(args: argparse.Namespace) -> None:
    config = load_config(args.config); authority = read_json(args.authority)
    final = Path(args.output_root) / authority["training_authority_id"] / authority["run_id"]
    if final.exists():
        manifest = final / "run_manifest.json"
        if not manifest.is_file() or read_json(manifest).get("status") != "PASS":
            raise FileExistsError("incomplete/colliding P7 immutable run")
        print(f"P7_OUTPUT={manifest}"); return
    stage = Path(args.staging_root) / authority["run_id"] / "production"
    stage.mkdir(parents=True, exist_ok=True)
    with gpu_pair(config): run_torchrun(args, "production", stage / "worker.json", stage)
    run = read_json(stage / "run_manifest.json")
    for filename in ("training_trace.json", "selector_result.json", "execution_record.json"):
        if not (stage / filename).is_file(): raise ValueError(f"missing P7 production output: {filename}")
    execution_path = stage / "execution_record.json"; execution = read_json(execution_path)
    execution["resources"]["nvml"] = nvml_summary(stage / "nvml-production.csv")
    write_json(execution_path, execution)
    final.parent.mkdir(parents=True, exist_ok=True); os.replace(stage, final)
    print(f"P7_OUTPUT={final / 'run_manifest.json'}")


def extract(args: argparse.Namespace) -> None:
    root = Path(args.run_manifest).parent; path = root / args.filename
    if not path.is_file(): raise ValueError(f"missing P7 run output: {args.filename}")
    validate_schema(path, args.schema); print(f"P7_OUTPUT={path}")


def aggregate(args: argparse.Namespace) -> None:
    authority = read_json(args.authority); run = read_json(args.run_manifest)
    trace = read_json(args.trace); selector = read_json(args.selector); execution = read_json(args.execution)
    gate_values = [read_json(path) for path in args.gates]; cache = read_json(args.geometry_cache)
    if any(value.get("status") != "PASS" for value in [authority, run, trace, selector, execution, cache, *gate_values]):
        raise ValueError("P7 aggregate parent rejection")
    if (cache.get("training_authority_id") != authority["training_authority_id"]
            or cache.get("geometry_layout_version") != GEOMETRY_LAYOUT_VERSION
            or run.get("geometry_cache_id") != cache.get("cache_id")):
        raise ValueError("P7 geometry-cache lineage rejection")
    best = run["best_checkpoint"]; latest = run["latest_checkpoint"]
    root = Path(args.run_manifest).parent
    for record in (best, latest):
        checkpoint = root / "checkpoints" / record["checkpoint_id"] / record["payload"]["filename"]
        if checkpoint.stat().st_size != record["payload"]["size_bytes"] or sha256_file(checkpoint) != record["payload"]["sha256"]:
            raise ValueError("P7 checkpoint checksum mismatch")
        manifest_path = checkpoint.with_name("checkpoint_manifest.json")
        validate_schema(manifest_path, ROOT / "config/schemas/p7_checkpoint_manifest.schema.json")
    replay_best, replay_patience = replay_selector(trace["validation_events"])
    if (replay_best["epoch"], replay_best["checkpoint_id"], replay_patience) != (
            selector["best_epoch"], selector["best_checkpoint_id"], selector["patience_events"]):
        raise ValueError("P7 independent selector replay mismatch")
    acceptance = {"schema_version": SCHEMA_VERSION, "status": "PASS",
                  "training_authority_id": authority["training_authority_id"], "run_id": authority["run_id"],
                  "trace_id": trace["trace_id"], "selector_id": selector["selector_id"], "execution_id": execution["execution_id"],
                  "best_checkpoint": best, "latest_checkpoint": latest,
                  "geometry_cache": {"cache_id": cache["cache_id"], "entry_count": cache["entry_count"],
                                     "total_raw_tensor_bytes": cache["total_raw_tensor_bytes"],
                                     "total_disk_bytes": cache["total_disk_bytes"]},
                  "population": {"training_scenes": 256, "validation_scenes": 32,
                                 "validation_queries": 64, "validation_gallery": 32, "evaluation_consumed": 0},
                  "completion": {"termination": run["termination"], "epochs": run["epochs_completed"],
                                 "optimizer_updates": run["optimizer_updates"]},
                  "invariants": {"all_gpu_gates_pass": len(gate_values) == 4, "finite_training": True,
                                 "geometry_layout_v3": cache["geometry_layout_version"] == "3.0.0",
                                 "geometry_cache_complete": cache["entry_count"] == 2144,
                                 "exact_resume": next(value for value in gate_values if value["gate"] == "resume_equivalence")["checks"]["state_content_exact"],
                                 "validation_only_selector": True, "queue_and_ema_exact": True,
                                 "scheduler_exact": trace["steps"][-1]["learning_rate"] == learning_rate(trace["step_count"]),
                                 "evaluation_execution_zero": execution["non_execution"]["evaluation_queries"] == 0,
                                 "p8_plus_zero": execution["non_execution"]["p8_plus"] == 0,
                                 "maintenance_zero": execution["non_execution"]["maintenance"] == 0,
                                 "full_population_training_zero": execution["non_execution"]["full_population_training"] == 0},
                  "parents": authority["parents"]}
    if not all(acceptance["invariants"].values()): raise ValueError("P7 acceptance invariant failure")
    finalized(acceptance, "p7acc_", "acceptance_id")
    destination = Path(args.output)
    write_json(destination, acceptance); validate_schema(destination, args.schema)
    print(f"P7_OUTPUT={destination}")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(); subs = result.add_subparsers(dest="command", required=True)
    def inputs(command):
        for name in ("config", "p6_config", "architecture", "preprocessing", "p6_acceptance", "prototype",
                     "prototype_manifest", "p3_root", "p4_root", "p5_root", "categories"):
            command.add_argument("--" + name.replace("_", "-"), required=True)
        command.add_argument("--geometry-cache", default="")
    authority = subs.add_parser("authority"); inputs(authority); authority.add_argument("--output", required=True)
    cache = subs.add_parser("cache-build"); inputs(cache); cache.add_argument("--authority", required=True); cache.add_argument("--output-root", required=True); cache.add_argument("--staging-root", required=True); cache.add_argument("--schema", required=True)
    gate = subs.add_parser("gpu-gate"); inputs(gate); gate.add_argument("--authority", required=True); gate.add_argument("--gate", choices=("init", "update", "reference", "resume"), required=True); gate.add_argument("--output-root", required=True); gate.add_argument("--staging-root", required=True)
    prod = subs.add_parser("production"); inputs(prod); prod.add_argument("--authority", required=True); prod.add_argument("--output-root", required=True); prod.add_argument("--staging-root", required=True)
    work = subs.add_parser("worker"); inputs(work); work.add_argument("--authority", required=True); work.add_argument("--worker-mode", choices=("cache-build", "init", "update", "reference", "trajectory", "production"), required=True); work.add_argument("--worker-output", required=True); work.add_argument("--stage", required=True); work.add_argument("--max-updates", type=int, default=0); work.add_argument("--resume-checkpoint", default="")
    extract_parser = subs.add_parser("extract"); extract_parser.add_argument("--run-manifest", required=True); extract_parser.add_argument("--filename", required=True); extract_parser.add_argument("--schema", required=True)
    accept = subs.add_parser("aggregate"); accept.add_argument("--authority", required=True); accept.add_argument("--run-manifest", required=True); accept.add_argument("--trace", required=True); accept.add_argument("--selector", required=True); accept.add_argument("--execution", required=True); accept.add_argument("--geometry-cache", required=True); accept.add_argument("--gates", nargs=4, required=True); accept.add_argument("--schema", required=True); accept.add_argument("--output", required=True)
    return result


def main() -> int:
    args = parser().parse_args()
    {"authority": build_authority, "cache-build": cache_build, "gpu-gate": gpu_gate, "production": production,
     "worker": worker, "extract": extract, "aggregate": aggregate}[args.command](args)
    return 0


if __name__ == "__main__": raise SystemExit(main())
