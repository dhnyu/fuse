#!/usr/bin/env python3
"""Independent current training production science-worker entry point."""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

import training_worker as training_worker_module  # noqa: E402
from training_campaign import s08_selection_document  # noqa: E402
from training_worker import ControllerClient, run_worker, utc_now  # noqa: E402


def epoch_progress_payload(payload: dict, updates: list[dict], elapsed_seconds: float) -> dict:
    if not updates:
        raise RuntimeError("S09_EPOCH_PROGRESS_METRICS_MISSING")
    return {**payload,
            "mean_training_loss": statistics.fmean(float(item["total_loss"]) for item in updates),
            "ending_learning_rate": float(updates[-1]["learning_rate"]),
            "epoch_wall_seconds": float(elapsed_seconds)}


def install_progress_event_adapter() -> None:
    """Expose existing scientific epoch metrics to the operational controller."""
    original_update = training_worker_module.training_update
    original_event = training_worker_module._event
    epoch_updates: list[dict] = []
    epoch_started = time.monotonic()

    def tracked_update(*args, **kwargs):
        result = original_update(*args, **kwargs)
        epoch_updates.append(result)
        return result

    def enriched_event(rank, client, event_type, payload):
        nonlocal epoch_started
        if event_type == "EPOCH_STARTED":
            epoch_updates.clear()
            epoch_started = time.monotonic()
        elif event_type == "PROGRESS_SUMMARY_COMMITTED":
            payload = epoch_progress_payload(payload, epoch_updates, time.monotonic() - epoch_started)
        return original_event(rank, client, event_type, payload)

    training_worker_module.training_update = tracked_update
    training_worker_module._event = enriched_event


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authority", required=True); parser.add_argument("--matrix", required=True)
    parser.add_argument("--configuration-id", required=True); parser.add_argument("--cache-root", required=True)
    parser.add_argument("--categories", required=True); parser.add_argument("--training-config", required=True)
    parser.add_argument("--model-config", required=True); parser.add_argument("--mode", choices=("formal", "bounded-pilot"), required=True)
    parser.add_argument("--stop-after-schedule-index", type=int)
    args = parser.parse_args()
    authority = json.loads(Path(args.authority).read_text(encoding="utf-8"))
    matrix = json.loads(Path(args.matrix).read_text(encoding="utf-8"))
    selection = s08_selection_document(matrix)
    training_worker_module.make_selection_contract = lambda: selection
    install_progress_event_adapter()
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
