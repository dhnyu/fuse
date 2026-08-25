#!/usr/bin/env python3
"""Apply the predeclared I21 learning-rate selection contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml


def mean(values:list[float])->float:
    return sum(values)/len(values)


def summarize(candidate:dict[str,Any], baseline_final:float|None=None)->dict[str,Any]:
    steps=candidate["steps"];validations=candidate["validation"]
    final_epoch=max(int(row["epoch"]) for row in steps)
    final_steps=[row for row in steps if int(row["epoch"])==final_epoch]
    losses=[float(row["validation_retrieval_loss"]) for row in validations]
    target_step=None if baseline_final is None else next((int(row["optimizer_step"]) for row in validations
        if float(row["validation_retrieval_loss"])<=baseline_final),None)
    return {"learning_rate":float(candidate["learning_rate"]),"status":candidate["status"],
        "initial_parameter_digest":candidate["initial_parameter_digest"],
        "safety_exact_repeat":candidate["safety"]["exact_repeat"],
        "optimizer_steps":len(steps),"final_training_loss":mean([float(row["total_loss"]) for row in final_steps]),
        "final_scene_loss":mean([float(row["scene_loss"]) for row in final_steps]),
        "final_information_preservation_loss":mean([float(row["information_preservation_loss"]) for row in final_steps]),
        "validation_loss_mean_auc":mean(losses),"final_validation_retrieval_loss":losses[-1],
        "validation_losses":losses,"reference_final_loss_reach_step":target_step,
        "gradient_norm_mean":mean([float(row["gradient_norm"]) for row in steps]),
        "parameter_update_norm_mean":mean([float(row["parameter_update_norm"]) for row in steps]),
        "parameter_update_norm_max":max(float(row["parameter_update_norm"]) for row in steps),
        "clipping_ratio":float(candidate["clipping_ratio"]),"queue_occupancy":int(candidate["queue_occupancy"]),
        "elapsed_seconds":float(candidate["elapsed_seconds"]),"resources":candidate["resources"],
        "validation":validations}


def main()->None:
    parser=argparse.ArgumentParser();parser.add_argument("--diagnostic",required=True);parser.add_argument("--contract",required=True)
    parser.add_argument("--output",required=True);args=parser.parse_args()
    diagnostic=json.loads(Path(args.diagnostic).read_text());contract=yaml.safe_load(Path(args.contract).read_text())
    candidates=sorted(diagnostic["candidates"],key=lambda value:float(value["learning_rate"]))
    if [float(value["learning_rate"]) for value in candidates]!=[float(value) for value in contract["candidates"]]:
        raise ValueError("diagnostic candidate set differs from predeclared contract")
    if any(value["status"]!="PASS" for value in candidates):raise ValueError("one or more LR candidates failed")
    baseline_raw=candidates[0];baseline_loss=float(baseline_raw["validation"][-1]["validation_retrieval_loss"])
    rows=[summarize(value,baseline_loss) for value in candidates]
    if len({row["initial_parameter_digest"] for row in rows})!=1:raise ValueError("candidate initial parameter states differ")
    selection=contract["selection"];selected=rows[0];decisions=[]
    for candidate in rows[1:]:
        final_gain=(selected["final_validation_retrieval_loss"]-candidate["final_validation_retrieval_loss"])/selected["final_validation_retrieval_loss"]
        auc_gain=(selected["validation_loss_mean_auc"]-candidate["validation_loss_mean_auc"])/selected["validation_loss_mean_auc"]
        late=candidate["validation_losses"][-int(selection["late_validation_window_evaluations"]):]
        late_regression=any(after>before+float(selection["maximum_late_loss_increase"]) for before,after in zip(late,late[1:]))
        matched_ratios=[float(c["parameter_update_norm"])/max(float(b["parameter_update_norm"]),1e-30)
            for b,c in zip(baseline_raw["steps"],candidates[rows.index(candidate)]["steps"],strict=True)]
        accepted=bool(final_gain>=float(selection["minimum_relative_final_validation_retrieval_loss_improvement"])
            and auc_gain>=float(selection["minimum_relative_validation_retrieval_loss_auc_improvement"])
            and candidate["reference_final_loss_reach_step"] is not None
            and candidate["reference_final_loss_reach_step"]<rows[0]["optimizer_steps"]
            and not late_regression
            and max(matched_ratios)<=float(selection["maximum_matched_step_update_norm_ratio_to_reference"]))
        decisions.append({"candidate_learning_rate":candidate["learning_rate"],"compared_with":selected["learning_rate"],
            "relative_final_loss_improvement":final_gain,"relative_auc_improvement":auc_gain,
            "late_validation_regression":late_regression,"maximum_matched_step_update_norm_ratio":max(matched_ratios),
            "accepted":accepted})
        if accepted:selected=candidate
    output={"status":"PASS","selected_learning_rate":selected["learning_rate"],"candidate_summaries":rows,"decisions":decisions}
    Path(args.output).write_text(json.dumps(output,sort_keys=True,indent=2)+"\n")


if __name__=="__main__":main()
