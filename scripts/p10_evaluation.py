#!/usr/bin/env python3
"""Execute the explicitly authorized, closed-model P10 evaluation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from p10_evaluation import run_p10_reexecution  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", default=str(ROOT / "config/p10_evaluation.yml"))
    parser.add_argument("--reexecute", action="store_true")
    args = parser.parse_args()
    if not args.reexecute:
        parser.error("P10 held-out consumption is committed; only the bound --reexecute path is allowed")
    print(json.dumps(run_p10_reexecution(args.contract), sort_keys=True))


if __name__ == "__main__":
    main()
