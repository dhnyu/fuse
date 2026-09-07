#!/usr/bin/env python3
"""Fail-closed guard for the retired P9 v1 authorization interface."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from p9_v1_retirement import retire_v1_cli  # noqa: E402


if __name__ == "__main__":
    retire_v1_cli("scripts/p9_formal_authorization.py")
