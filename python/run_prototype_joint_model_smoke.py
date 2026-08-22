#!/usr/bin/env python3
"""Acquire one GPU lock and launch the joint-model smoke."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import sys
from pathlib import Path

import yaml

from run_prototype_encoder_smoke import acquire_gpu


def main() -> int:
    parser = argparse.ArgumentParser()
    for name in ("accepted-manifest", "dataloader-smoke", "encoder-manifest", "augmentation-manifest",
                 "gate-manifest", "joint-config", "encoder-config", "tensor-contract", "schema"):
        parser.add_argument(f"--{name}", required=True, type=Path)
    args = parser.parse_args()
    config = yaml.safe_load(args.joint_config.read_text())
    gpu, pair_stream, gpu_stream, wait = acquire_gpu(Path(config["execution"]["lock_root"]), float(config["execution"]["lock_timeout_seconds"]))
    try:
        os.environ.update({
            "CUDA_VISIBLE_DEVICES": str(gpu), "FUSE_GPU_PHYSICAL_INDEX": str(gpu),
            "FUSE_GPU_LOCK_WAIT_SECONDS": repr(wait),
            "FUSE_GPU_PAIR_LOCK": str(Path(config["execution"]["lock_root"]) / "gpu_pair.lock"),
            "FUSE_GPU_DEVICE_LOCK": str(Path(config["execution"]["lock_root"]) / f"gpu{gpu}.lock"),
        })
        from prototype_joint_model_smoke_impl import run_smoke
        result = run_smoke(args.accepted_manifest.resolve(), args.dataloader_smoke.resolve(),
                           args.encoder_manifest.resolve(), args.augmentation_manifest.resolve(),
                           args.gate_manifest.resolve(), args.joint_config.resolve(), args.encoder_config.resolve(),
                           args.tensor_contract.resolve(), args.schema.resolve())
        sys.stdout.write(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    finally:
        fcntl.flock(gpu_stream.fileno(), fcntl.LOCK_UN); gpu_stream.close()
        fcntl.flock(pair_stream.fileno(), fcntl.LOCK_UN); pair_stream.close()


if __name__ == "__main__":
    raise SystemExit(main())
