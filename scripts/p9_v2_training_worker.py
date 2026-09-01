#!/usr/bin/env python3
"""Independent P9 v2 production science-worker entry point."""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from p9_v2_training_worker import ControllerClient, run_worker, utc_now  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authority", required=True); parser.add_argument("--matrix", required=True)
    parser.add_argument("--configuration-id", required=True); parser.add_argument("--cache-root", required=True)
    parser.add_argument("--categories", required=True); parser.add_argument("--training-config", required=True)
    parser.add_argument("--model-config", required=True); parser.add_argument("--mode", choices=("formal", "bounded-pilot"), required=True)
    parser.add_argument("--stop-after-schedule-index", type=int)
    args = parser.parse_args()
    authority = json.loads(Path(args.authority).read_text(encoding="utf-8"))
    spec = {"matrix": args.matrix, "configuration_id": args.configuration_id,
            "cache_root": args.cache_root, "categories": args.categories,
            "training_config": args.training_config, "model_config": args.model_config}
    try:
        result = run_worker(spec, authority, mode=args.mode,
                            stop_after_schedule_index=args.stop_after_schedule_index)
        if result["status"] != "COMPLETE":
            raise RuntimeError(result["status"])
    except FloatingPointError:
        if int(os.environ.get("RANK", "0")) == 0:
            client = ControllerClient()
            client.request("FAILURE_REPORT", {"failure_class": "SCIENTIFIC_DIVERGENCE",
                "failure_stage": "TRAINING_UPDATE", "last_durable_boundary": None,
                "resumable_checkpoint_committed": False, "resume_policy": "FORBIDDEN",
                "occurred_at": utc_now()})
        raise
    except BaseException:
        traceback.print_exc(file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
