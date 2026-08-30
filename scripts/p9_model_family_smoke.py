#!/usr/bin/env python3
"""Bounded actual-data P9 family/DDP smoke; performs no optimizer update."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import torch
import torch.distributed as dist
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "python"), str(ROOT / "scripts")]

from canonical_config import canonical_json_bytes  # noqa: E402
from p7_training import collate, selected_view_pair, to_device  # noqa: E402
from p7_prototype_training import configure_process, geometry  # noqa: E402
from p9_model_families import (FAMILY_NAMES, P9SceneEncoder, ds_raster_from_batch,
                               family_contract, p9_reconstruction_terms)  # noqa: E402
from p9_bounded_main_pilot import values_and_authority  # noqa: E402


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(value))


def worker(args: argparse.Namespace) -> None:
    values = values_and_authority(); rank = int(os.environ["RANK"])
    device = configure_process(values["config"], rank); dist.init_process_group("nccl")
    scenes = []; samples = []; entity_types: set[int] = set()
    for scene in values["data"].members["training"][rank::2]:
        views = [row["master_view_id"] for row in values["catalog"].k8[scene]]
        view = selected_view_pair(scene, views, values["config"], 1)[0]
        sample = values["data"].training_view(scene, view)
        samples.append(sample); scenes.append(scene)
        entity_types.update(int(value) for value in sample["entities"]["entity_type"].tolist())
        if len(samples) >= 4 and entity_types == {0, 1, 2}:
            break
    if entity_types != {0, 1, 2}:
        raise RuntimeError("P9 actual-data family smoke could not cover all entity types")
    batch_cpu = collate(samples, values["vocabulary"])
    ds_raster = ds_raster_from_batch(batch_cpu) if args.family == "DS" else None
    batch = to_device(batch_cpu, device)
    geometry_value = None
    if "geometry" in family_contract(args.family).modalities:
        geometry_value = geometry(batch, values["model_config"], device)
    config = yaml.safe_load((ROOT / "config/p6_model_dataloader.yml").read_text())
    config["model"].update({"d": args.dimension, "d_c": args.dimension,
                            "head_dimension": args.dimension // 4,
                            "ffn_dimension": 2 * args.dimension})
    sizes = {name: int(value["size"]) for name, value in values["vocabulary"].items()}
    model = P9SceneEncoder(config, sizes, args.family).to(device)
    ddp = torch.nn.parallel.DistributedDataParallel(
        model, device_ids=[device.index], output_device=device.index,
        find_unused_parameters=False, bucket_cap_mb=50,
        gradient_as_bucket_view=False, static_graph=False)
    assignments = None
    if args.family != "DS":
        assignments = torch.arange(batch["entities"]["local_entity_id"].numel(), device=device)
        assignments = assignments.remainder(len(family_contract(args.family).modalities))
    before_edges = batch["edges"]["edge_index"].clone()
    output = ddp(batch, geometry=geometry_value,
                 ds_raster=ds_raster.to(device) if ds_raster is not None else None,
                 assignments=assignments)
    reconstruction = {} if args.family == "DS" else p9_reconstruction_terms(
        model, batch, geometry_value, output["modalities"], batch["category_mask_indices"])
    loss = output["scene_embedding"].square().sum() + output["contrastive_embedding"].square().sum()
    for value in reconstruction.values():
        loss = loss + value["sum"]
    loss.backward()
    missing = [name for name, value in model.named_parameters() if value.requires_grad and value.grad is None]
    local = {
        "rank": rank, "family": args.family, "dimension": args.dimension,
        "scene_ids": scenes, "loss": float(loss.detach().cpu()),
        "missing_gradients": missing, "active_ip_terms": list(reconstruction),
        "edge_instances_preserved": bool(torch.equal(before_edges, batch["edges"]["edge_index"])),
        "ds_shape": list(ds_raster.shape) if ds_raster is not None else None,
        "peak_vram_bytes": int(torch.cuda.max_memory_allocated(device)),
        "optimizer_updates": 0, "evaluation_queries_consumed": 0,
    }
    write_json(Path(args.output) / f"rank-{rank}.json", local)
    gathered: list[object] = [None] * dist.get_world_size()
    dist.all_gather_object(gathered, missing)
    passed = not any(gathered)
    if rank == 0:
        rows = [json.loads((Path(args.output) / f"rank-{value}.json").read_text()) for value in range(2)]
        write_json(Path(args.output) / "summary.json", {"status": "PASS" if passed else "FAIL", "ranks": rows})
    dist.barrier(); dist.destroy_process_group()
    if not passed:
        raise RuntimeError("P9 family smoke found unused trainable parameters")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--family", choices=FAMILY_NAMES, required=True)
    parser.add_argument("--dimension", choices=(48, 64, 128), type=int, required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(); worker(args)


if __name__ == "__main__":
    main()
