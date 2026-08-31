#!/usr/bin/env python3
"""Resolve one canonical P9 v2 acceptance into a hash-validated record."""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from p9_v2_canonical import canonical_json_bytes  # noqa: E402
from p9_v2_downstream import AcceptedCheckpointResolver, load_acceptance_eligibility  # noqa: E402
from p9_v2_ledger import fsync_directory, write_all  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--acceptance-id", required=True); parser.add_argument("--eligibility", required=True)
    parser.add_argument("--locator-roots", required=True); parser.add_argument("--output", required=True)
    args = parser.parse_args()
    canonical = Path("/mnt/hdd002/dhnyu/fusedata/models/reduced/p9_v2/canonical")
    locator_roots = json.loads(Path(args.locator_roots).read_text(encoding="utf-8"))
    resolver = AcceptedCheckpointResolver(
        canonical / "acceptances", canonical / "bundles", locator_roots,
        load_acceptance_eligibility(args.eligibility))
    value = dataclasses.asdict(resolver.resolve_accepted_checkpoint(args.acceptance_id))
    output = Path(args.output); output.parent.mkdir(parents=True, exist_ok=True)
    stage = output.with_name(f".{output.name}.{os.getpid()}.incomplete")
    descriptor = os.open(stage, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o640)
    try: write_all(descriptor, canonical_json_bytes(value)); os.fsync(descriptor)
    finally: os.close(descriptor)
    os.replace(stage, output); fsync_directory(output.parent)
    print(json.dumps({"status": "PASS", "acceptance_id": value["acceptance_id"]}, sort_keys=True))


if __name__ == "__main__": main()
