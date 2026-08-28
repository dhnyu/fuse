#!/usr/bin/env python3
"""Build, independently validate, or aggregate P5 fixed queries."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from p5_fixed_queries import aggregate, build_branch, canonical_json, validate_branch


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    branch = commands.add_parser("branch")
    branch.add_argument("--spec", required=True)
    branch.add_argument("--output-dir", required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("--manifest", required=True)
    validate.add_argument("--config-json", required=True)
    validate.add_argument("--output", required=True)
    aggregation = commands.add_parser("aggregate")
    aggregation.add_argument("--spec", required=True)
    aggregation.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    if args.command == "branch":
        result = build_branch(json.loads(Path(args.spec).read_text()), Path(args.output_dir))
    elif args.command == "validate":
        result = validate_branch(Path(args.manifest), json.loads(Path(args.config_json).read_text()))
        Path(args.output).write_bytes(canonical_json(result))
    else:
        result = aggregate(json.loads(Path(args.spec).read_text()), Path(args.output_dir))
    print(json.dumps({"status": "PASS", "result": result}, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
