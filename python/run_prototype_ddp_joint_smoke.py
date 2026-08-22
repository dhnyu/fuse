#!/usr/bin/env python3
"""Publish the immutable two-rank joint-model acceptance after all DDP gates."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import jsonschema
import yaml

from prototype_dataloader import canonical_json_bytes, sha256_file


def acquire(path: Path, timeout: float) -> Any:
    path.parent.mkdir(parents=True, exist_ok=True); stream=path.open("a+"); deadline=time.monotonic()+timeout
    while True:
        try: fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB); return stream
        except BlockingIOError:
            if time.monotonic()>=deadline: stream.close(); raise TimeoutError(f"GPU lock timeout: {path}")
            time.sleep(0.25)


def invoke(script: Path, common: list[str], env: dict[str, str]) -> dict[str, Any]:
    result=subprocess.run([sys.executable,str(script),*common],capture_output=True,text=True,env=env,check=False)
    if result.returncode: raise RuntimeError(f"{script.name} failed:\n{result.stdout}\n{result.stderr}")
    lines=[line for line in result.stdout.splitlines() if line.lstrip().startswith("{")]
    if not lines: raise RuntimeError(f"{script.name} emitted no result")
    value=json.loads(lines[-1])
    if value.get("status")!="PASS": raise RuntimeError(f"{script.name} gate blocked: {value}")
    return value


def main() -> int:
    parser=argparse.ArgumentParser()
    for name in ("accepted-manifest","tensor-contract","encoder-config","joint-config","distributed-config",
                 "parent-joint-manifest","schema"):parser.add_argument(f"--{name}",required=True,type=Path)
    args=parser.parse_args();config=yaml.safe_load(args.distributed_config.read_text());execution=config["execution"]
    streams=[]
    try:
        for name in ("gpu_pair.lock","gpu0.lock","gpu1.lock"):
            streams.append(acquire(Path(execution["lock_root"])/name,float(execution["lock_timeout_seconds"])))
        env=os.environ.copy();env.update({"CUDA_VISIBLE_DEVICES":"0,1","OMP_NUM_THREADS":"1","MKL_NUM_THREADS":"1",
            "OPENBLAS_NUM_THREADS":"1","NUMEXPR_NUM_THREADS":"1","NCCL_P2P_DISABLE":"1","NCCL_IB_DISABLE":"1",
            "TORCH_NCCL_BLOCKING_WAIT":"1","PYTHONPATH":str(Path(__file__).parent)})
        common=["--accepted-manifest",str(args.accepted_manifest.resolve()),"--tensor-contract",str(args.tensor_contract.resolve()),
                "--encoder-config",str(args.encoder_config.resolve()),"--joint-config",str(args.joint_config.resolve())]
        root=Path(__file__).parent;forward=invoke(root/"prototype_ddp_joint_objective_smoke.py",common,env)
        optimizer=invoke(root/"prototype_ddp_optimizer_smoke.py",common,env)
        sparse=invoke(root/"prototype_sparse_reconstruction_smoke.py",[],env)
        parent=json.loads(args.parent_joint_manifest.read_text())
        scientific={"parent_joint_model_identity":parent["joint_model_acceptance_id"],"parent_manifest_sha256":sha256_file(args.parent_joint_manifest),
                    "distributed_contract":config["strategy"],"numerical_equivalence":config["numerical_equivalence"],
                    "config_sha256":sha256_file(args.distributed_config),"encoder_config_sha256":sha256_file(args.encoder_config),
                    "joint_config_sha256":sha256_file(args.joint_config),"tensor_contract_sha256":sha256_file(args.tensor_contract),
                    "implementation_sha256":{name:sha256_file(root/name) for name in ("prototype_ddp_joint_model.py",
                        "prototype_ddp_joint_objective_smoke.py","prototype_ddp_optimizer_smoke.py",
                        "prototype_joint_model.py","prototype_sparse_reconstruction_smoke.py",
                        "run_prototype_training_ddp.py","run_prototype_ddp_joint_smoke.py")}}
        identity="pjd_"+hashlib.sha256(canonical_json_bytes(scientific)).hexdigest()[:24]
        final=args.accepted_manifest.parent/config["output"]["subdirectory"]/identity;final.parent.mkdir(parents=True,exist_ok=True)
        stage=Path(tempfile.mkdtemp(prefix=f".{identity}.stage-",dir=final.parent))
        qc={"status":"PASS","forward_gradient_parity":forward,"optimizer_resume_parity":optimizer,
            "sparse_reconstruction_parity":sparse,
            "measured_speedup":optimizer["speedup"],"execution_contract":execution}
        qc_path=stage/config["output"]["qc"];qc_path.write_bytes(canonical_json_bytes(qc))
        outputs=[{"relative_path":qc_path.name,"size_bytes":qc_path.stat().st_size,"sha256":sha256_file(qc_path)}]
        manifest={"schema_version":"1.0.0","status":"PASS","distributed_joint_acceptance_id":identity,
                  "parent_joint_model_identity":parent["joint_model_acceptance_id"],"scientific_identity":scientific,
                  "parity":{"forward_gradient":forward,"optimizer_resume":optimizer,
                            "sparse_reconstruction":sparse},
                  "execution":{"world_size":2,"backend":"nccl","measured_speedup":optimizer["speedup"],
                               "single_elapsed_seconds":optimizer["single_elapsed_seconds"],"ddp_elapsed_seconds":optimizer["ddp_elapsed_seconds"],
                               "workers_planned":execution["total_dataloader_workers"],"workers_per_rank":execution["workers_per_rank"]},
                  "outputs":outputs}
        jsonschema.validate(manifest,json.loads(args.schema.read_text()))
        manifest_path=stage/config["output"]["manifest"];manifest_path.write_bytes(canonical_json_bytes(manifest))
        names=[qc_path.name,manifest_path.name]
        if final.exists():
            if any(not (final/name).is_file() or sha256_file(final/name)!=sha256_file(stage/name) for name in names):
                raise FileExistsError(f"same distributed joint ID has different content: {final}")
            shutil.rmtree(stage);publish="identical_reuse"
        else:os.replace(stage,final);publish="new_publish"
        print(json.dumps({"status":"PASS","distributed_joint_acceptance_id":identity,"publish_status":publish,
                          "output_files":[str(final/name) for name in names]},sort_keys=True));return 0
    finally:
        for stream in reversed(streams):fcntl.flock(stream.fileno(),fcntl.LOCK_UN);stream.close()


if __name__=="__main__":raise SystemExit(main())
