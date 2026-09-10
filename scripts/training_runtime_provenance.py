#!/usr/bin/env python3
"""Print the canonical formal S09 runtime-provenance value."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from training_runtime_provenance import runtime_implementation_provenance  # noqa: E402


if __name__ == "__main__":
    print(json.dumps({"status": "PASS", **runtime_implementation_provenance(ROOT)}, sort_keys=True))
