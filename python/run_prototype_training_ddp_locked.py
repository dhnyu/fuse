#!/usr/bin/env python3
"""Hold the pair and both device locks while executing two-rank I21."""

from __future__ import annotations
import fcntl,os,subprocess,sys,time
from pathlib import Path

def acquire(path:Path,timeout:float):
    path.parent.mkdir(parents=True,exist_ok=True);stream=path.open("a+");deadline=time.monotonic()+timeout
    while True:
        try:fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB);return stream
        except BlockingIOError:
            if time.monotonic()>=deadline:raise TimeoutError(path)
            time.sleep(.25)

def main()->int:
    root=Path("/mnt/hdd002/dhnyu/fusedata/runtime/gpu_locks");streams=[]
    try:
        for name in ("gpu_pair.lock","gpu0.lock","gpu1.lock"):streams.append(acquire(root/name,120))
        env=os.environ.copy();env.update({"CUDA_VISIBLE_DEVICES":"0,1","OMP_NUM_THREADS":"1","MKL_NUM_THREADS":"1",
            "OPENBLAS_NUM_THREADS":"1","NUMEXPR_NUM_THREADS":"1","NCCL_P2P_DISABLE":"1","NCCL_IB_DISABLE":"1","TORCH_NCCL_BLOCKING_WAIT":"1"})
        return subprocess.call([sys.executable,str(Path(__file__).with_name("run_prototype_training_ddp.py")),*sys.argv[1:]],env=env)
    finally:
        for stream in reversed(streams):fcntl.flock(stream.fileno(),fcntl.LOCK_UN);stream.close()

if __name__=="__main__":raise SystemExit(main())
