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
)


def load(path: str):
    return json.loads(Path(path).read_text())


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("mode", choices=("ofat", "winner", "comparison"))
    parser.add_argument("--plan", required=True); parser.add_argument("--contract", required=True)
    parser.add_argument("--cache-acceptance", required=True); parser.add_argument("--output", required=True)
    parser.add_argument("--results", nargs="*"); args = parser.parse_args()
    plan = load(args.plan); contract = yaml.safe_load(Path(args.contract).read_text())
    lineage = current_lineage(plan, contract); cache = load(args.cache_acceptance)
    parents = {**lineage, "production_cache_id": cache["cache_id"],
               "production_cache_acceptance_id": cache["acceptance_id"],
               "retirement_id": contract["parents"]["retirement_id"]}
    training = yaml.safe_load((ROOT / "config/training.yml").read_text())
    model = yaml.safe_load((ROOT / "config/model_inputs.yml").read_text())
    implementation = scientific_implementation_hash(ROOT)
    output = Path(args.output)
    if args.mode == "ofat":
        paths = publish_documents(ofat_authorities(plan, training, model, parents, implementation), output)
        print(json.dumps({"status": "PASS", "paths": paths}, sort_keys=True)); return
    if args.mode == "winner":
        winner = select_ofat_winner(plan, [load(path) for path in args.results or []])
        output.parent.mkdir(parents=True, exist_ok=True)
        payload = canonical_json_bytes(winner)
        if output.exists() and output.read_bytes() != payload: raise FileExistsError("S09_WINNER_COLLISION")
        if not output.exists(): output.write_bytes(payload)
        print(json.dumps({"status": "PASS", "path": str(output)}, sort_keys=True)); return
    winner = load((args.results or [""])[0])
    paths = publish_documents(comparison_authorities(plan, winner, training, model, parents, implementation), output)
    print(json.dumps({"status": "PASS", "paths": paths}, sort_keys=True))


if __name__ == "__main__": main()
