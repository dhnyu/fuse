#!/usr/bin/env python3
"""Generate or validate the local P10 retrieval inspector."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "tools"))

from retrieval_inspector.inspector import generate_inspector, validate_output  # noqa: E402


def supplemental_output(pointer: Path) -> Path:
    metadata = json.loads(pointer.read_text())
    acceptance_path = Path(metadata["acceptance_path"])
    raw = acceptance_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != metadata["acceptance_sha256"]:
        raise ValueError("Supplemental acceptance checksum mismatch")
    acceptance = json.loads(raw)
    if (acceptance["acceptance_id"] != metadata["acceptance_id"] or acceptance["status"] != "PASS"
            or acceptance["union_count"] != 10000 or not acceptance["supplementary_retrieval_only"]
            or not acceptance["canonical_p10_unchanged"] or not acceptance["canonical_p11_unchanged"]):
        raise ValueError("Supplemental acceptance contract mismatch")
    output = acceptance_path.parent.parent / "inspector"
    if hashlib.sha256((output / "manifest.json").read_bytes()).hexdigest() != acceptance["parents_sha256"]["inspector"]:
        raise ValueError("Supplemental inspector binding mismatch")
    validate_output(output)
    return output / "index.html"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=ROOT / "artifacts/retrieval-inspector")
    parser.add_argument("--validate", type=Path, help="validate an existing generated directory only")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--supplemental", action="store_true", help="validate and locate the accepted dual-gallery inspector")
    args = parser.parse_args()
    if args.supplemental:
        if args.validate or args.overwrite:
            parser.error("--supplemental cannot be combined with --validate or --overwrite")
        pointer = ROOT / "tools/retrieval_inspector/supplemental_output.json"
        if not pointer.exists():
            parser.error("No accepted supplemental inspector has been registered")
        print(supplemental_output(pointer))
        return 0
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
