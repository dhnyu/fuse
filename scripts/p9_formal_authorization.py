#!/usr/bin/env python3
"""Publish P9 cache plans and formal authorization without running an optimizer."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from p9_formal_authorization import (build_plan_bundle, cache_acceptance_payload, cfg_main_reservation_payload,
                                     formal_authority_payload, load_config, publish_final_bundle,
                                     publish_plan_bundle, read_json)  # noqa: E402


def validate(schema: Path, value: dict) -> None:
    jsonschema.Draft202012Validator(json.loads(schema.read_text())).validate(value)


def main() -> int:
    parser = argparse.ArgumentParser(); sub = parser.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan"); plan.add_argument("--config", required=True); plan.add_argument("--schema-dir", required=True)
    plan.add_argument("--scientific-commit", required=True); plan.add_argument("--execution-commit", required=True)
    final = sub.add_parser("finalize"); final.add_argument("--config", required=True); final.add_argument("--schema-dir", required=True)
    final.add_argument("--build-authority", required=True); final.add_argument("--validation", required=True)
    final.add_argument("--execution-commit", required=True)
    args = parser.parse_args(); config = load_config(args.config); schemas = Path(args.schema_dir)
    if args.command == "plan":
        bundle = build_plan_bundle(args.config, args.scientific_commit, args.execution_commit)
        for name, value in bundle.items(): validate(schemas / f"p9_{name}.schema.json", value)
        paths = publish_plan_bundle(config, bundle)
    else:
        build_authority = read_json(args.build_authority); validation = read_json(args.validation)
        acceptance = cache_acceptance_payload(config, build_authority, validation, args.execution_commit)
        authority = formal_authority_payload(config, acceptance, args.execution_commit)
        reservation = cfg_main_reservation_payload(config, authority, acceptance)
        for name, value in (("production_cache_acceptance", acceptance), ("formal_training_authority", authority),
                            ("cfg_main_attempt_reservation", reservation)):
            validate(schemas / f"p9_{name}.schema.json", value)
        paths = publish_final_bundle(config, acceptance, authority, reservation)
    print("P9_OUTPUTS=" + json.dumps([str(path) for path in paths], separators=(",", ":")))
    return 0


if __name__ == "__main__": raise SystemExit(main())
