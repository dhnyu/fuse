#!/usr/bin/env python3
"""Validate a completed prepared-input P10 attempt without scientific execution."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from p10_completion_audit import ATTEMPT_ID, audit_completed_p10  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", default=str(ROOT / "config/p10_evaluation.yml"))
    parser.add_argument("--attempt-id", default=ATTEMPT_ID)
    parser.add_argument("--output")
    args = parser.parse_args()
    result = audit_completed_p10(args.contract, args.attempt_id)
    raw = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        Path(args.output).write_text(raw, encoding="utf-8")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
