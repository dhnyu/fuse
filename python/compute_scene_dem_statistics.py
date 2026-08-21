#!/usr/bin/env python3
"""Compute deterministic population statistics over valid training-scene DEM cells."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
import zarr


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    jobs = json.loads(args.jobs.read_text(encoding="utf-8"))
    count = 0
    total = 0.0
    total_square = 0.0
    minimum = math.inf
    maximum = -math.inf
    for job in sorted(jobs, key=lambda value: value["branch_id"]):
        index = pq.read_table(job["index_path"], columns=["split", "zarr_index"]).to_pydict()
        selected = sorted(int(position) for split, position in zip(index["split"], index["zarr_index"])
                          if split == "training")
        if not selected:
            continue
        group = zarr.open_group(job["dem_zarr_path"], mode="r")
        for position in selected:
            values = np.asarray(group["raw_mean_m"][position], dtype=np.float64).reshape(-1)
            mask = np.asarray(group["valid_mask"][position]).reshape(-1) == 1
            valid = values[mask]
            if not np.all(np.isfinite(valid)):
                raise RuntimeError(f"Non-finite valid DEM value in {job['branch_id']}:{position}")
            count += int(valid.size)
            total += float(np.sum(valid, dtype=np.float64))
            total_square += float(np.sum(valid * valid, dtype=np.float64))
            if valid.size:
                minimum = min(minimum, float(np.min(valid)))
                maximum = max(maximum, float(np.max(valid)))
    if count == 0:
        raise RuntimeError("No valid training-scene DEM pixels")
    mean = total / count
    variance = max(0.0, total_square / count - mean * mean)
    value = {"valid_count": count, "mean": mean, "raw_sd": math.sqrt(variance),
             "minimum": minimum, "maximum": maximum, "sum": total,
             "sum_squares": total_square, "population": "training_valid_pixel_instance"}
    args.output.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
