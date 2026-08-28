#!/usr/bin/env python3
"""Plan resources or build one immutable P4 augmentation-bank branch."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from p4_fixed_augmentation import build_branch, scan_resources


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("resources")
    plan.add_argument("--spec", required=True)
    plan.add_argument("--output", required=True)
    branch = sub.add_parser("branch")
    branch.add_argument("--spec", required=True)
    branch.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    spec = json.loads(Path(args.spec).read_text())
    if args.command == "resources":
        value = scan_resources([Path(x) for x in spec["parent_tars"]], Path(args.output), spec["cache_id"], spec["implementation_hash"])
        summary = {
            "status": "PASS",
            "branch_count": len(value["branch_training_scenes"]),
            "training_scene_count": value["training_scene_count"],
        }
    else:
        value = build_branch(spec, Path(args.output_dir))
        summary = {
            "status": value["status"],
            "branch_id": value["branch_id"],
            "candidate_count": value["candidate_count"],
            "writer_validation": value["validation"]["writer"],
        }
    print(json.dumps({"status": "PASS", "result": summary}, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
