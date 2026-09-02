#!/usr/bin/env python3
"""Run validation-free, one-update pilots for weak and strong P9 profiles."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from p9_v2_canonical import canonical_json_bytes  # noqa: E402
from p9_v2_training_pilot import run_bounded_update_pilot  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    contract = yaml.safe_load((ROOT / "config/p9_v2_training_controller.yml").read_text(encoding="utf-8"))
    common = {
        "matrix": str(Path(contract["roots"]["p8_bundle"]) / "hyperparameter_configuration_matrix.json"),
        "cache_root": contract["roots"]["production_cache"],
        "categories": contract["roots"]["categories"],
        "training_config": str(ROOT / "config/p7_deterministic_training.yml"),
        "model_config": str(ROOT / "config/p6_model_dataloader.yml"),
    }
    results = [
        run_bounded_update_pilot({**common, "configuration_id": configuration_id}, output / configuration_id)
        for configuration_id in ("cfg_intensity_05", "cfg_intensity_20")
    ]
    summary = {
        "status": "PASS", "pilot_kind": "NONCANONICAL_INTENSITY_ROLE_UPDATE_MATRIX",
        "formal_authorities": 0, "formal_runs": 0,
        "global_optimizer_updates": sum(row["global_optimizer_updates"] for row in results),
        "validation_executions": 0, "evaluation_executions": 0,
        "formal_checkpoint_publications": 0, "formal_acceptance_publications": 0,
        "results": results,
    }
    path = output / "pilot_result.json"
    path.write_bytes(canonical_json_bytes(summary))
    print(json.dumps({"status": "PASS", "result": str(path)}, sort_keys=True))


if __name__ == "__main__":
    main()
