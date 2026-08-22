#!/usr/bin/env python3
"""Hold both GPU locks while running I23 independent inference shards."""

from __future__ import annotations

import fcntl
import os
import subprocess
import sys
import time
from pathlib import Path


def acquire(path: Path, timeout: float):
    path.parent.mkdir(parents=True, exist_ok=True)
    stream = path.open("a+")
    deadline = time.monotonic() + timeout
    while True:
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return stream
        except BlockingIOError:
            if time.monotonic() >= deadline:
                raise TimeoutError(path)
            time.sleep(0.25)


def main() -> int:
    root = Path("/mnt/hdd002/dhnyu/fusedata/runtime/gpu_locks")
    streams = []
    try:
        for name in ("gpu_pair.lock", "gpu0.lock", "gpu1.lock"):
            streams.append(acquire(root / name, 120))
        environment = os.environ.copy()
        environment.update({
            "CUDA_VISIBLE_DEVICES": "0,1", "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1",
        })
        script = Path(__file__).with_name("run_prototype_model_validation.py")
        return subprocess.call([sys.executable, str(script), *sys.argv[1:]], env=environment)
    finally:
        for stream in reversed(streams):
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
            stream.close()


if __name__ == "__main__":
    raise SystemExit(main())
