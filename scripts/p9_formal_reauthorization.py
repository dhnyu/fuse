#!/usr/bin/env python3
"""Publish or verify the corrected P9 authority without starting training."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from p9_v1_retirement import retire_v1_cli  # noqa: E402

if __name__ == "__main__":
    retire_v1_cli("scripts/p9_formal_reauthorization.py")

from p9_formal_reauthorization import build, publish  # noqa: E402


def main() -> None:
    retire_v1_cli("scripts/p9_formal_reauthorization.py")
    parser = argparse.ArgumentParser(); parser.add_argument("command", choices=("validate", "publish"))
    parser.add_argument("--config", required=True); args = parser.parse_args()
    if args.command == "validate":
        values = build(args.config, ROOT); print("P9_REAUTHORIZATION=" + json.dumps(
            {key: next(value[field] for field in ("authority_id", "reservation_id", "supersession_id") if field in value)
             for key, value in values.items()}, sort_keys=True))
    else:
        print("P9_OUTPUTS=" + json.dumps([str(path) for path in publish(args.config, ROOT)], sort_keys=True))


if __name__ == "__main__": main()
