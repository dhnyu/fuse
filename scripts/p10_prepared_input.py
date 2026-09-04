#!/usr/bin/env python3
"""Build or validate the deterministic P10 prepared-input cache."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from p10_prepared_input import (  # noqa: E402
    build_geometry_cache, build_prepared_cache, validate_geometry_cache, validate_prepared_cache,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build")
    build.add_argument("--contract", default=str(ROOT / "config/p10_evaluation.yml"))
    validate = subparsers.add_parser("validate")
    validate.add_argument("--manifest", required=True)
    geometry = subparsers.add_parser("build-geometry")
    geometry.add_argument("--contract", default=str(ROOT / "config/p10_evaluation.yml"))
    geometry.add_argument("--input-manifest", required=True)
    geometry_validate = subparsers.add_parser("validate-geometry")
    geometry_validate.add_argument("--manifest", required=True)
    args = parser.parse_args()
    if args.command == "build":
        contract = yaml.safe_load(Path(args.contract).read_text(encoding="utf-8"))
        print(build_prepared_cache(contract))
    elif args.command == "validate":
        print(validate_prepared_cache(args.manifest)["cache_id"])
    elif args.command == "build-geometry":
        contract = yaml.safe_load(Path(args.contract).read_text(encoding="utf-8"))
        print(build_geometry_cache(contract, args.input_manifest))
    else:
        print(validate_geometry_cache(args.manifest)["cache_id"])


if __name__ == "__main__":
    main()
