#!/usr/bin/env python3
"""Render an offline, read-only inspector for accepted P3/P4 artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "tools"))

from augmentation_inspector import InspectorError, generate_inspector, validate_html  # noqa: E402


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description=__doc__,
        epilog="Generated HTML includes dependent profile/entity/operation/attribute filters.",
    )
    result.add_argument("--scene-id")
    result.add_argument("--master-view-id", type=int)
    result.add_argument("--preset", choices=("qc-extremes", "v1-reference"))
    result.add_argument("--max-cases", type=int, default=8)
    result.add_argument("--output", type=Path, required=True)
    result.add_argument("--original-cache-root", type=Path)
    result.add_argument("--augmentation-bank-root", type=Path)
    result.add_argument("--master-bank-id", default="augbank_252ce67e6d74679b02871e57")
    result.add_argument("--logical-index-id", default="abi_66dfe52602ffe442336685e0")
    result.add_argument("--overwrite", action="store_true")
    result.add_argument("--validate-only", action="store_true")
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        if args.validate_only:
            result = validate_html(args.output)
        else:
            result = generate_inspector(
                repository=REPOSITORY,
                output=args.output,
                scene_id=args.scene_id,
                master_view_id=args.master_view_id,
                preset=args.preset,
                max_cases=args.max_cases,
                original_cache_root=args.original_cache_root,
                augmentation_bank_root=args.augmentation_bank_root,
                master_bank_id=args.master_bank_id,
                logical_index_id=args.logical_index_id,
                overwrite=args.overwrite,
            )
    except InspectorError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
