#!/usr/bin/env python3
"""Materialize current S09 campaign evidence without launching DDP."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from artifact_protocol import canonical_json_bytes  # noqa: E402
from training_campaign import (  # noqa: E402
    comparison_authorities, current_lineage, ofat_authorities, publish_documents,
    scientific_implementation_hash, select_ofat_winner,
    validate_current_results, validate_current_winner, ordered_comparisons,
)
from training_progress import CampaignProgress, configured_log_root  # noqa: E402


def load(path: str):
    return json.loads(Path(path).read_text())


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument(
        "mode", choices=("ofat", "winner", "comparison", "campaign-validate", "campaign-accepted"))
    parser.add_argument("--plan", required=True); parser.add_argument("--contract", required=True)
    parser.add_argument("--cache-acceptance", required=True); parser.add_argument("--output", required=True)
    parser.add_argument("--implementation-hash")
    parser.add_argument("--results", nargs="*"); args = parser.parse_args()
    plan = load(args.plan); contract = yaml.safe_load(Path(args.contract).read_text())
    progress = CampaignProgress(configured_log_root(ROOT, contract), create=True)
    lineage = current_lineage(plan, contract); cache = load(args.cache_acceptance)
    parents = {**lineage, "production_cache_id": cache["cache_id"],
               "production_cache_acceptance_id": cache["acceptance_id"],
               "retirement_id": contract["parents"]["retirement_id"]}
    training = yaml.safe_load((ROOT / "config/training.yml").read_text())
    model = yaml.safe_load((ROOT / "config/model_inputs.yml").read_text())
    implementation = scientific_implementation_hash(ROOT)
    if args.implementation_hash != implementation:
        raise RuntimeError("S09_RUNTIME_IMPLEMENTATION_HASH_MISMATCH")
    output = Path(args.output)
    if args.mode == "ofat":
        progress.ensure_generation(implementation)
        paths = publish_documents(ofat_authorities(plan, training, model, parents, implementation), output)
        progress.append_campaign("OFAT_AUTHORITIES_READY", phase="OFAT",
                                 config_or_model="all_ofat_authorities")
        print(json.dumps({"status": "PASS", "paths": paths}, sort_keys=True)); return
    if args.mode == "winner":
        rows = [load(path) for path in args.results or []]
        validate_current_results(rows, ofat_authorities(plan, training, model, parents, implementation))
        winner = select_ofat_winner(plan, rows)
        output.parent.mkdir(parents=True, exist_ok=True)
        payload = canonical_json_bytes(winner)
        if output.exists() and output.read_bytes() != payload: raise FileExistsError("S09_WINNER_COLLISION")
        if not output.exists(): output.write_bytes(payload)
        progress.append_campaign("WINNER_SELECTED", config_or_model=winner["selected_configuration_id"],
                                 winner_configuration=winner["selected_configuration_id"])
        print(json.dumps({"status": "PASS", "path": str(output)}, sort_keys=True)); return
    winner = load((args.results or [""])[0])
    validate_current_winner(plan, winner, ofat_authorities(plan, training, model, parents, implementation))
    if args.mode in {"campaign-validate", "campaign-accepted"}:
        rows = [load(path) for path in (args.results or [])[1:]]
        validate_current_results(rows, comparison_authorities(plan, winner, training, model, parents, implementation))
        if args.mode == "campaign-validate":
            ordered = ordered_comparisons(rows, key="model_id")
            paths = {row["model_id"]: path for row, path in zip(rows, args.results[1:])}
            print(json.dumps({"status": "PASS", "comparison_result_paths": [
                paths[row["model_id"]] for row in ordered]})); return
        acceptance = load(output)
        progress.append_campaign(
            "CAMPAIGN_ACCEPTED", config_or_model=acceptance["campaign_acceptance_id"],
            winner_configuration=winner["selected_configuration_id"],
            prepared_cache_status="PREPARED_CACHE_READY", campaign_status="CAMPAIGN_ACCEPTED")
        print(json.dumps({"status": "PASS", "path": str(output)}, sort_keys=True)); return
    paths = publish_documents(comparison_authorities(plan, winner, training, model, parents, implementation), output)
    progress.append_campaign("COMPARISON_AUTHORITIES_READY", phase="COMPARISON",
                             config_or_model="all_comparison_authorities",
                             winner_configuration=winner["selected_configuration_id"])
    print(json.dumps({"status": "PASS", "paths": paths}, sort_keys=True))


if __name__ == "__main__": main()
