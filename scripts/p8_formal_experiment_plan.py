#!/usr/bin/env python3
"""Build and validate plan-only P8 artifacts without training."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from p8_experiment_plan import (build_bundle, canonical_bytes, load_config,
                                materialize_comparison, validate_schema, write_bundle)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("build", "validate", "reject-early-materialization"))
    parser.add_argument("--config", type=Path, default=ROOT / "config/p8_formal_experiment_plan.yml")
    parser.add_argument("--dissertation-root", type=Path, default=Path.home() / "dhnyu-masters-dissertation")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--artifact", type=Path)
    parser.add_argument("--schema", type=Path)
    args = parser.parse_args()
    if args.command == "build":
        if args.output is None:
            parser.error("--output is required")
        write_bundle(build_bundle(load_config(args.config), ROOT, args.dissertation_root), args.output, ROOT / "config/schemas")
    elif args.command == "validate":
        if args.artifact is None or args.schema is None:
            parser.error("--artifact and --schema are required")
        value = json.loads(args.artifact.read_text())
        validate_schema(value, args.schema)
        sys.stdout.buffer.write(canonical_bytes({"status": "PASS"}))
    else:
        bundle = build_bundle(load_config(args.config), ROOT, args.dissertation_root)
        try:
            materialize_comparison(bundle["comparison_variant_template_matrix"]["templates"][0], None)
        except ValueError:
            sys.stdout.buffer.write(canonical_bytes({"status": "PASS", "early_materialization_rejected": True}))
            return
        raise RuntimeError("comparison template materialized without selected FM")


if __name__ == "__main__":
    main()
