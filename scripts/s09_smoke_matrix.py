#!/usr/bin/env python3
"""Checkpoint-free S09 qualification only. Never invokes targets or a controller."""
import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))


def main():
    from s09_smoke import CASES, run_matrix, worker
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("one-step",), default="one-step")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--case", choices=CASES)
    group.add_argument("--all", action="store_true")
    group.add_argument("--worker-case", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--output", type=Path, help="New directory below logs/s09/smoke only")
    args = parser.parse_args()
    if args.worker_case:
        if args.output or "LOCAL_RANK" not in os.environ:
            parser.error("worker mode is internal to the guarded launcher")
        worker(args.worker_case)
    else:
        print(run_matrix(CASES if args.all else [args.case], args.output))


if __name__ == "__main__":
    main()
