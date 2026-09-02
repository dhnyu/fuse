#!/usr/bin/env python3
"""Launch the bounded sequential selected-FM IP comparison."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from p9_selected_fm_campaign import SelectedFMCampaignPaths, execute  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-root", required=True)
    parser.add_argument("--contract", default="config/p9_v2_training_controller.yml")
    parser.add_argument("--matrix", default="config/p9_selected_fm_confirmation_matrix.json")
    args = parser.parse_args()
    execute(SelectedFMCampaignPaths(
        Path(args.campaign_root).resolve(), ROOT, Path(args.contract).resolve(), Path(args.matrix).resolve()))


if __name__ == "__main__":
    main()
