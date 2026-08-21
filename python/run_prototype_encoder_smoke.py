#!/usr/bin/env python3
"""Acquire the blueprint POSIX GPU locks before importing PyTorch."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def available_gpu_indices() -> list[int]:
    result = subprocess.run(
        ["nvidia-smi", "--query-gpu=index", "--format=csv,noheader,nounits"],
        check=True, capture_output=True, text=True,
    )
    return [int(value.strip()) for value in result.stdout.splitlines() if value.strip()]


def acquire_gpu(lock_root: Path, timeout: float) -> tuple[int, object, object, float]:
    lock_root.mkdir(parents=True, exist_ok=True)
    pair_stream = (lock_root / "gpu_pair.lock").open("a+")
    fcntl.flock(pair_stream.fileno(), fcntl.LOCK_SH)
    started = time.monotonic()
    while time.monotonic() - started <= timeout:
        for gpu_index in available_gpu_indices():
            gpu_stream = (lock_root / f"gpu{gpu_index}.lock").open("a+")
            try:
                fcntl.flock(gpu_stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return gpu_index, pair_stream, gpu_stream, time.monotonic() - started
            except BlockingIOError:
                gpu_stream.close()
        time.sleep(0.25)
    pair_stream.close()
    raise TimeoutError(f"no GPU lock acquired within {timeout} seconds")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--accepted-manifest", required=True, type=Path)
    parser.add_argument("--dataloader-smoke", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--schema", required=True, type=Path)
    parser.add_argument("--tensor-contract", required=True, type=Path)
    args = parser.parse_args()
    import yaml
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    gpu_index, pair_stream, gpu_stream, wait_seconds = acquire_gpu(
        Path(config["execution"]["lock_root"]), float(config["execution"]["lock_timeout_seconds"])
    )
    try:
        os.environ["CUDA_VISIBLE_DEVICES"] = str(gpu_index)
        os.environ["FUSE_GPU_PHYSICAL_INDEX"] = str(gpu_index)
        os.environ["FUSE_GPU_LOCK_WAIT_SECONDS"] = repr(wait_seconds)
        os.environ["FUSE_GPU_PAIR_LOCK"] = str(Path(config["execution"]["lock_root"]) / "gpu_pair.lock")
        os.environ["FUSE_GPU_DEVICE_LOCK"] = str(Path(config["execution"]["lock_root"]) / f"gpu{gpu_index}.lock")
        from prototype_encoder_smoke_impl import run_smoke
        result = run_smoke(
            args.accepted_manifest.resolve(), args.dataloader_smoke.resolve(), args.config.resolve(),
            args.schema.resolve(), args.tensor_contract.resolve(),
        )
        sys.stdout.write(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    finally:
        fcntl.flock(gpu_stream.fileno(), fcntl.LOCK_UN)
        gpu_stream.close()
        fcntl.flock(pair_stream.fileno(), fcntl.LOCK_UN)
        pair_stream.close()


if __name__ == "__main__":
    raise SystemExit(main())
