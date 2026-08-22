#!/usr/bin/env python3
"""Hold the approved single-GPU lock for the complete I21 subprocess."""

from __future__ import annotations

import argparse
import fcntl
import os
import subprocess
import sys
from pathlib import Path

import yaml

from run_prototype_encoder_smoke import acquire_gpu


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--training-config", required=True, type=Path)
    known, remainder = parser.parse_known_args()
    config = yaml.safe_load(known.training_config.read_text())
    gpu, pair_stream, gpu_stream, wait = acquire_gpu(
        Path(config["execution"]["gpu_lock_root"]), float(config["execution"]["gpu_lock_timeout_seconds"])
    )
    try:
        environment = os.environ.copy()
        environment.update({"CUDA_VISIBLE_DEVICES": str(gpu), "FUSE_GPU_PHYSICAL_INDEX": str(gpu),
                            "FUSE_GPU_LOCK_WAIT_SECONDS": repr(wait)})
        command = [sys.executable, str(Path(__file__).with_name("run_prototype_training.py")),
                   "--training-config", str(known.training_config), *remainder]
        return subprocess.run(command, env=environment).returncode
    finally:
        fcntl.flock(gpu_stream.fileno(), fcntl.LOCK_UN); gpu_stream.close()
        fcntl.flock(pair_stream.fileno(), fcntl.LOCK_UN); pair_stream.close()


if __name__ == "__main__":
    raise SystemExit(main())
