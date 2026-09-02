#!/usr/bin/env python3
"""Launch the selected-model sequential P9-B comparison campaign."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"python"))
from p9_b_campaign import execute  # noqa: E402
from p9_selected_fm_campaign import SelectedFMCampaignPaths  # noqa: E402


def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument("--campaign-root",required=True)
    parser.add_argument("--plan",default="/mnt/hdd002/dhnyu/fusedata/models/reduced/p9_v2/canonical/p9_b_plans/p9bplan_747bbf5e1e12f831ea5fb101.json")
    parser.add_argument("--contract",default="config/p9_v2_training_controller.yml"); args=parser.parse_args()
    root=Path(args.campaign_root).resolve()
    execute(SelectedFMCampaignPaths(root,ROOT,Path(args.contract).resolve(),root/"p9_b_training_matrix.json"),Path(args.plan).resolve())


if __name__=="__main__": main()
