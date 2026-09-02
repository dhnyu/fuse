#!/usr/bin/env python3
"""Run seven noncanonical two-GPU P9-B family update pilots."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"python"))
from p9_a_campaign import atomic_write  # noqa:E402
from p9_b_campaign import build_authority,build_training_matrix,campaign_contract  # noqa:E402
from p9_v2_canonical import canonical_json_bytes  # noqa:E402
from p9_v2_ledger import read_ledger  # noqa:E402

PLAN=Path("/mnt/hdd002/dhnyu/fusedata/models/reduced/p9_v2/canonical/p9_b_plans/p9bplan_747bbf5e1e12f831ea5fb101.json")


def run(output: Path) -> dict:
    output=output.resolve(); temporary=Path(tempfile.gettempdir()).resolve()
    if temporary not in output.parents: raise RuntimeError("P9-B pilot output must be under system temporary root")
    output.mkdir(parents=True,exist_ok=False)
    base=yaml.safe_load((ROOT/"config/p9_v2_training_controller.yml").read_text())
    plan=json.loads(PLAN.read_text()); matrix=build_training_matrix(plan); matrix_path=output/"p9_b_training_matrix.json"
    atomic_write(matrix_path,canonical_json_bytes(matrix))
    results=[]
    for row in matrix["rows"]:
        family_root=output/row["configuration_id"]; family_root.mkdir()
        contract=campaign_contract(base,matrix_path,Path(base["roots"]["eligibility_snapshot"]),plan["selected_fm_acceptance_id"])
        contract_path=family_root/"contract.yml"; atomic_write(contract_path,yaml.safe_dump(contract,sort_keys=True).encode())
        authority=build_authority(row,contract,ROOT); authority_path=family_root/"noncanonical_authority.json"
        atomic_write(authority_path,canonical_json_bytes(authority))
        worker=shlex.join([sys.executable,"-m","torch.distributed.run","--standalone","--nproc_per_node=2",
            "scripts/p9_v2_training_worker.py","--authority",str(authority_path),"--matrix",str(matrix_path),
            "--configuration-id",row["configuration_id"],"--cache-root",base["roots"]["production_cache"],
            "--categories",base["roots"]["categories"],"--training-config","config/p7_deterministic_training.yml",
            "--model-config","config/p6_model_dataloader.yml","--mode","bounded-pilot"])
        command=[sys.executable,"scripts/p9_v2_training_controller.py","run","--authority",str(authority_path),
                 "--contract",str(contract_path),"--output",str(family_root/"runs"),"--science-worker-command",worker,
                 "--noncanonical-pilot"]
        environment=os.environ.copy(); environment.update({"NCCL_P2P_DISABLE":"1","NCCL_IB_DISABLE":"1","TORCH_NCCL_BLOCKING_WAIT":"1"})
        process=subprocess.run(command,cwd=ROOT,env=environment,text=True,capture_output=True)
        if process.returncode: raise RuntimeError(f"{row['configuration_id']} pilot failed\n{process.stdout}\n{process.stderr[-5000:]}")
        execution=json.loads(process.stdout.splitlines()[-1]); ledger=read_ledger(execution["ledger_root"])
        checkpoints=[event for event in ledger.events if event["event_type"]=="VALIDATION_CHECKPOINT_COMMITTED"]
        completed=[event for event in ledger.events if event["event_type"]=="TRAINING_COMPLETED"]
        if len(checkpoints)!=2 or len(completed)!=1 or completed[0]["payload"]["optimizer_update"]!=4:
            raise RuntimeError(f"{row['configuration_id']} pilot lifecycle mismatch")
        diagnostics=sorted((Path(execution["ledger_root"]).parent/"staging/diagnostics").glob("*.json"))
        performance=[json.loads(path.read_text()) for path in diagnostics]
        if any(item["evaluation_consumption_count"]!=0 for item in performance): raise RuntimeError("evaluation contamination")
        results.append({"configuration_id":row["configuration_id"],"model_family":row["model_family"],
                        "optimizer_updates":4,"checkpoints":2,"evaluation_consumption_count":0,
                        "peak_vram_bytes":max(item["peak_vram_bytes"] for item in performance),
                        "median_update_wall_seconds":sum(item["median_update_wall_seconds"] for item in performance)/len(performance)})
        print(f"PILOT_PASS {row['configuration_id']}",flush=True)
    result={"verdict":"PASS","pilot_kind":"NONCANONICAL_P9_B_SEVEN_FAMILY","results":results,
            "formal_authorities":0,"canonical_checkpoints":0,"canonical_acceptances":0,"evaluation_consumption_count":0}
    atomic_write(output/"pilot_result.json",canonical_json_bytes(result)); return result


def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument("--output",required=True); args=parser.parse_args()
    print(json.dumps(run(Path(args.output)),sort_keys=True))


if __name__=="__main__": main()
