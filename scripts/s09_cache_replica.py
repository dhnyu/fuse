#!/usr/bin/env python3
"""Copy or verify an S09 physical read replica, without running targets/training."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
from training_cache_storage import cache_inventory, copy_replica, verify_replica


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("plan", "copy", "verify"))
    parser.add_argument("--canonical-root", required=True)
    parser.add_argument("--read-root")
    args = parser.parse_args()
    if args.mode == "plan":
        result = cache_inventory(args.canonical_root).binding()
    else:
        if not args.read_root:
            parser.error("--read-root is required")
        result = (copy_replica(args.canonical_root, args.read_root) if args.mode == "copy"
                  else verify_replica(args.canonical_root, args.read_root, full=True))
    print(json.dumps(result, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
