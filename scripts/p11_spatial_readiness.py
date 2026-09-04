#!/usr/bin/env python3
"""Materialize P11-C district folds and immutable readiness evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from p11_spatial_readiness import materialize_p11_spatial_readiness


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/p11_spatial_readiness.yml")
    parser.add_argument("--output")
    args = parser.parse_args()
    result = materialize_p11_spatial_readiness(args.config)
    raw = json.dumps(result, sort_keys=True, separators=(",", ":"))
    if args.output:
        Path(args.output).write_text(raw + "\n", encoding="utf-8")
    else:
        print(raw)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
