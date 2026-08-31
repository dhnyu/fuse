#!/usr/bin/env python3
"""Publish plan-only P9 infrastructure readiness; never start training."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from p9_v1_retirement import retire_v1_cli  # noqa: E402

if __name__ == "__main__":
    retire_v1_cli("scripts/p9_infrastructure.py")

from canonical_config import canonical_json_bytes  # noqa: E402
from p9_infrastructure import build_readiness, load_contract  # noqa: E402


def main() -> int:
    retire_v1_cli("scripts/p9_infrastructure.py")
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True); parser.add_argument("--schema", required=True)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()
    config = load_contract(args.config)
    value = build_readiness(args.config, config["p8_bundle_root"], args.source_commit)
    jsonschema.Draft202012Validator(json.loads(Path(args.schema).read_text())).validate(value)
    root = Path(config["publication_root"]) / value["readiness_id"]
    path = root / "p9_infrastructure_readiness.json"
    payload = canonical_json_bytes(value)
    if root.exists():
        if not path.is_file() or path.read_bytes() != payload:
            raise FileExistsError("P9 readiness immutable collision")
    else:
        stage = root.with_name(f".{root.name}.tmp-{os.getpid()}"); stage.mkdir(parents=True)
        (stage / path.name).write_bytes(payload); root.parent.mkdir(parents=True, exist_ok=True); os.replace(stage, root)
    print(f"P9_OUTPUT={path}")
    return 0


if __name__ == "__main__": raise SystemExit(main())
