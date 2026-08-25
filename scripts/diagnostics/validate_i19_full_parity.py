#!/usr/bin/env python3
"""Read-only full-population parity check for the optimized I19 implementation."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import resource
import time
from pathlib import Path

for variable in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

import numpy as np
import pyarrow.parquet as pq
import yaml

from prototype_augmentation import canonical_json_bytes
from prototype_dataloader import AcceptedPrototypeDataset
from run_prototype_augmentation_benchmark import (
    canonical_results,
    geometry_thresholds,
    run_process_campaign,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--accepted-manifest", required=True)
    parser.add_argument("--tensor-contract", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--reference-results", required=True)
    parser.add_argument("--workers", type=int, default=40)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    started = time.perf_counter()
    cpu_started = time.process_time()
    accepted_path = Path(args.accepted_manifest).resolve()
    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    training = AcceptedPrototypeDataset(accepted_path, args.tensor_contract, split="training")
    dataset = AcceptedPrototypeDataset(accepted_path, args.tensor_contract, split=None)
    thresholds, threshold_digest = geometry_thresholds(
        training, accepted_path, args.tensor_contract, config, args.workers
    )
    scene_ids = sorted(row["scene_id"] for row in dataset.rows)
    epoch = int(config["benchmark"]["epoch"])
    views = sorted(int(value) for value in config["benchmark"]["views"])
    tasks = [(scene_id, view) for scene_id in scene_ids for view in views]

    first_started = time.perf_counter()
    first = canonical_results(run_process_campaign(
        tasks, args.workers, accepted_path, args.tensor_contract, config, thresholds, epoch
    ))
    first_wall = time.perf_counter() - first_started

    shuffle_seed = int(hashlib.sha256(canonical_json_bytes({
        "global_seed": config["rng"]["base_seed"],
        "operation": "full_population_input_shuffle",
    })).hexdigest()[:16], 16)
    shuffled = list(tasks)
    np.random.Generator(np.random.PCG64(shuffle_seed)).shuffle(shuffled)
    second_started = time.perf_counter()
    second = canonical_results(run_process_campaign(
        shuffled, args.workers, accepted_path, args.tensor_contract, config, thresholds, epoch
    ))
    second_wall = time.perf_counter() - second_started

    first_payload = [canonical_json_bytes(value[0]) for value in first]
    second_payload = [canonical_json_bytes(value[0]) for value in second]
    determinism_mismatches = sum(left != right for left, right in zip(first_payload, second_payload, strict=True))

    reference = pq.read_table(args.reference_results).to_pylist()
    reference_digest = {
        (row["scene_id"], int(row["view_id"])): row["logical_digest"] for row in reference
    }
    current_digest = {
        (value[0]["scene_id"], int(value[0]["view_id"])): value[0]["logical_digest"] for value in first
    }
    missing = sorted(set(reference_digest) - set(current_digest))
    extra = sorted(set(current_digest) - set(reference_digest))
    digest_mismatches = sorted(
        key for key in set(reference_digest) & set(current_digest)
        if reference_digest[key] != current_digest[key]
    )
    status = "PASS" if not missing and not extra and not digest_mismatches and not determinism_mismatches else "FAIL"
    result = {
        "status": status,
        "scene_count": len(scene_ids),
        "view_count": len(views),
        "comparison_count": len(current_digest),
        "epoch": epoch,
        "workers": args.workers,
        "thresholds": {"building": thresholds[0], "road": thresholds[1]},
        "threshold_population_digest": threshold_digest,
        "missing_count": len(missing),
        "extra_count": len(extra),
        "digest_mismatch_count": len(digest_mismatches),
        "determinism_mismatch_count": determinism_mismatches,
        "mismatches": [f"{scene_id}:{view_id}" for scene_id, view_id in digest_mismatches[:20]],
        "first_wall_seconds": first_wall,
        "shuffled_wall_seconds": second_wall,
        "total_wall_seconds": time.perf_counter() - started,
        "parent_cpu_seconds": time.process_time() - cpu_started,
        "maximum_rss_kb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }
    Path(args.output).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    if status != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
