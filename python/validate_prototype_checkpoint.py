#!/usr/bin/env python3
"""Reproduce the selected I21 validation result in a fresh process."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
import yaml
from torch.utils.data import DataLoader

from prototype_joint_model import JointPrototypeModel
from run_prototype_training import (
    AugmentedPairDataset, LogicalGroupSampler, collate_pairs, validation, worker_init,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ("checkpoint", "run-spec", "joint-config", "encoder-config", "augmentation-config", "tensor-contract", "i19-manifest"):
        parser.add_argument(f"--{name}", required=True)
    args = parser.parse_args()
    torch.set_num_threads(1); torch.set_num_interop_threads(1); torch.use_deterministic_algorithms(True)
    torch.backends.cuda.matmul.allow_tf32 = False; torch.backends.cudnn.allow_tf32 = False
    device = torch.device("cuda:0")
    spec = json.loads(Path(args.run_spec).read_text()); joint = yaml.safe_load(Path(args.joint_config).read_text())
    encoder = yaml.safe_load(Path(args.encoder_config).read_text()); augmentation = yaml.safe_load(Path(args.augmentation_config).read_text())
    i19 = json.loads(Path(args.i19_manifest).read_text()); threshold = i19["logical_results"]["thresholds"]
    data = AugmentedPairDataset(spec["dataset_manifest"]["path"], args.tensor_contract, "validation", augmentation,
                                {0: float(threshold["building"]), 1: float(threshold["road"])}, validation=True)
    mask_indices = {name: next(iter(values)) for name, values in data.base.category_mask_index.items()}
    sampler = LogicalGroupSampler(data.base.rows, spec["hard_budgets"], int(spec["seed"])); sampler.permutation = lambda: list(range(32))
    loader = DataLoader(data, batch_sampler=sampler, num_workers=40, collate_fn=collate_pairs,
                        persistent_workers=True, pin_memory=True, prefetch_factor=2,
                        worker_init_fn=worker_init, multiprocessing_context="spawn")
    model = JointPrototypeModel(encoder, joint).to(device=device, dtype=torch.float32)
    state = torch.load(args.checkpoint, map_location="cpu", weights_only=False)
    model.online.load_state_dict(state["online_model"]); model.target.load_state_dict(state["target_model"])
    model.modality_mask_embeddings.data.copy_(state["projection_and_decoders"]["mask"])
    model.decoders.load_state_dict(state["projection_and_decoders"]["decoders"])
    result = validation(model, loader, encoder, mask_indices, device)
    if loader._iterator is not None: loader._iterator._shutdown_workers()
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
