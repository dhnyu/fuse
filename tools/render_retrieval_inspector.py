#!/usr/bin/env python3
"""Resolve/build the current 10K inspector, or explicitly access legacy evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "tools"))

from retrieval_inspector.inspector import validate_output  # noqa: E402


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
    if (output / "presentation.json").exists():
        from retrieval_inspector.presentation import validate_presentation
        validate_presentation(output)
    return output / "index.html"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=ROOT / "artifacts/retrieval-inspector")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--validate", type=Path, help="validate an explicit current or legacy package")
    mode.add_argument("--legacy-canonical", action="store_true", help="locate the immutable old 1600-only application; never rerank")
    mode.add_argument("--build-current", action="store_true", help="build and browser-validate a current repo-local package from accepted evidence")
    mode.add_argument("--supplemental", action="store_true", help="compatibility alias: locate the external accepted presentation, not the current package")
    mode.add_argument("--refresh-supplemental", action="store_true", help="compatibility: explicitly refresh the external presentation only")
    parser.add_argument("--overwrite", action="store_true", help="deprecated; immutable artifacts cannot be overwritten")
    args = parser.parse_args()
    if args.overwrite:
        parser.error("--overwrite is not supported; use --build-current for a new immutable package")
    if args.supplemental or args.refresh_supplemental:
        if args.validate or args.overwrite:
            parser.error("--supplemental cannot be combined with --validate or --overwrite")
        pointer = ROOT / "tools/retrieval_inspector/supplemental_output.json"
        if not pointer.exists():
            parser.error("No accepted supplemental inspector has been registered")
        entry = supplemental_output(pointer)
        print("Compatibility workflow: external presentation. Omit this flag for the current repo-local inspector.", file=sys.stderr)
        if args.refresh_supplemental:
            from retrieval_inspector.presentation import prepare_update, publish_update
            from retrieval_inspector.browser_validation import validate_browser
            revision = prepare_update(ROOT, entry.parent)
            checked = validate_browser(revision)
            entry = publish_update(entry.parent, revision, checked)
        print(entry)
        return 0
    if args.validate:
        if (args.validate / "artifact.json").exists():
            from retrieval_inspector.artifacts import validate_current
            artifact = validate_current(args.validate.resolve())
            result = {"status":"PASS", "inspector_id":artifact["inspector_id"], "role":"current"}
        else:
            result = validate_output(args.validate.resolve())
        print(json.dumps(result, sort_keys=True))
        return 0
    from retrieval_inspector.artifacts import build_current, legacy_output, resolve_current
    if args.legacy_canonical:
        entry = legacy_output(ROOT, args.output_root)
    elif args.build_current:
        entry = build_current(ROOT, args.output_root)
    else:
        entry = resolve_current(ROOT, args.output_root)
    print(entry)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
