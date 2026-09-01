#!/usr/bin/env python3
"""Launch the bounded, sequential remaining P9-A campaign."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from p9_a_campaign import CampaignPaths, execute  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-root", required=True)
    parser.add_argument("--contract", default="config/p9_v2_training_controller.yml")
    args = parser.parse_args()
    execute(CampaignPaths(Path(args.campaign_root).resolve(), ROOT, Path(args.contract).resolve()))


if __name__ == "__main__":
    main()
