#!/usr/bin/env python3
"""Emit the shared R/Python selected-host fixture as ordered relation masks."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from shapely.geometry import Point, Polygon

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from prototype_augmentation import RELATION_BITS, selected_host_relations  # noqa: E402


def square(xmin: float, ymin: float, xmax: float, ymax: float) -> Polygon:
    return Polygon([(xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax), (xmin, ymin)])


geometries = [
    square(0, 0, 20, 20), square(2, 2, 12, 12), square(2, 2, 12, 12),
    Point(5, 5), Point(0, 10),
]
types = np.asarray([0, 0, 0, 2, 2], dtype=np.uint8)
source_ids = ["large", "small-z", "small-a", "inside", "boundary"]
relations = selected_host_relations(geometries, types, set(range(5)), source_ids, list(range(5)))
rows = [
    {"source_local_entity_id": source, "destination_local_entity_id": destination,
     "relation_mask": RELATION_BITS[name]}
    for name in ("CNT", "WIT") for source, destination in sorted(relations[name])
]
print(json.dumps(rows, sort_keys=True, separators=(",", ":")))
