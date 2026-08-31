#!/usr/bin/env python3
"""CLI for isolated P9 formal-execution authorization publication."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from p9_formal_isolated_authorization import publish, publish_candidate


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["publish", "candidate"])
    parser.add_argument("--runtime-config", required=True)
    parser.add_argument("--publication-config", required=True)
    parser.add_argument("--output-root")
    args = parser.parse_args()
    if args.command == "candidate":
        if not args.output_root:
            parser.error("candidate publication requires --output-root")
        paths = publish_candidate(args.runtime_config, args.publication_config, Path.cwd(), args.output_root)
    else:
        paths = publish(args.runtime_config, args.publication_config, Path.cwd())
    print("P9_ISOLATED_OUTPUTS=" + json.dumps([str(path.resolve()) for path in paths], separators=(",", ":")))


if __name__ == "__main__":
    main()
