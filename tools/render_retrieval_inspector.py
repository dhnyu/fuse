#!/usr/bin/env python3
"""Generate or validate the local P10 retrieval inspector."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "tools"))

from retrieval_inspector.inspector import generate_inspector, validate_output  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=ROOT / "artifacts/retrieval-inspector")
    parser.add_argument("--validate", type=Path, help="validate an existing generated directory only")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    if args.validate:
        result = validate_output(args.validate.resolve())
        print(json.dumps(result, sort_keys=True))
        return 0
    args.output_root.mkdir(parents=True, exist_ok=True)
    output = generate_inspector(ROOT, args.output_root, overwrite=args.overwrite)
    print(output / "index.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
