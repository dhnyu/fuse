#!/usr/bin/env python3
"""Run the V2-H production-shaped, non-training P9 pilot."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from p9_v2_training_pilot import run_non_training_pilot  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--configuration-id", default="cfg_d48")
    args = parser.parse_args()
    p8 = "/mnt/hdd002/dhnyu/fusedata/models/reduced/formal_plan/p8a_3cb1c49084529987f0244a93/p8acc_c9f16a07275aadfae928d329"
    result = run_non_training_pilot({
        "configuration_id": args.configuration_id,
        "matrix": f"{p8}/hyperparameter_configuration_matrix.json",
        "cache_root": "/mnt/hdd002/dhnyu/fusedata/models/reduced/formal_training/production_cache/p9cba_5c472951ac896e82a0a0f555",
        "categories": "/mnt/hdd002/dhnyu/fusedata/scene_data/reduced/observations/obs_cd00016f6b5bfd960b0a6842/production/acceptance/bsa_e617ee0280a6edfa722994d3/spatial_categories.json",
        "training_config": str(ROOT / "config/p7_deterministic_training.yml"),
        "model_config": str(ROOT / "config/p6_model_dataloader.yml"),
    }, args.output)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__": main()
