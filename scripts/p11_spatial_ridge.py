#!/usr/bin/env python3
"""Execute or validate the immutable P11-E spatial ridge evaluation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from p11_spatial_ridge import (
    materialize_p11_ridge_evaluation,
    run_determinism_pilot,
    validate_p11_ridge_acceptance,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/p11_ridge_evaluation.yml")
    parser.add_argument("--pilot", action="store_true")
    parser.add_argument("--validate")
    args = parser.parse_args()
    if args.validate:
        result = validate_p11_ridge_acceptance(Path(args.validate))
    elif args.pilot:
        result = run_determinism_pilot(args.config)
    else:
        result = materialize_p11_ridge_evaluation(args.config)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
