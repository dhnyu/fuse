#!/usr/bin/env python3
import unittest
import sys
from pathlib import Path

import numpy as np
from shapely.geometry import LineString, MultiPolygon, Point, Polygon

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from prototype_augmentation import (  # noqa: E402
    float32_ulp_distance, jitter_geometry, keyed_rng, perturb_lane_value,
    road_removal_closure, selected_host_relations, structure_signature,
)


class AugmentationFixtureTest(unittest.TestCase):
    def test_selected_host_strict_within_ties_shuffle_and_multipart(self):
        large = Polygon([(0, 0), (20, 0), (20, 20), (0, 20), (0, 0)])
        small_z = Polygon([(2, 2), (12, 2), (12, 12), (2, 12), (2, 2)])
        small_a = Polygon([(2, 2), (12, 2), (12, 12), (2, 12), (2, 2)])
        multipart = MultiPolygon([
            Polygon([(30, 30), (35, 30), (35, 35), (30, 35), (30, 30)]),
            Polygon([(40, 40), (45, 40), (45, 45), (40, 45), (40, 40)]),
        ])
        geometries = [large, small_z, small_a, multipart, Point(5, 5), Point(0, 10), Point(32, 32), Point(60, 60)]
        types = np.asarray([0, 0, 0, 0, 2, 2, 2, 2], dtype=np.uint8)
        source_ids = ["large", "small-z", "small-a", "multi", "inside", "boundary", "multi-poi", "outside"]
        local_ids = [10, 11, 12, 13, 20, 21, 22, 23]
        result = selected_host_relations(geometries, types, set(range(len(geometries))), source_ids, local_ids)
        self.assertEqual(result["CNT"], {(2, 4), (3, 6)})
        self.assertEqual(result["WIT"], {(4, 2), (6, 3)})
        self.assertNotIn((0, 4), result["CNT"])
        self.assertNotIn((1, 4), result["CNT"])
        self.assertFalse(any(21 in pair or 23 in pair for pairs in result.values() for pair in pairs))

        equal_source_ids = list(source_ids); equal_source_ids[1] = equal_source_ids[2] = "same"
        equal_local_ids = list(local_ids); equal_local_ids[1], equal_local_ids[2] = 9, 8
        tied = selected_host_relations(geometries, types, set(range(len(geometries))), equal_source_ids, equal_local_ids)
        self.assertIn((2, 4), tied["CNT"])

        order = [7, 4, 2, 0, 6, 3, 1, 5]
        shuffled = selected_host_relations(
            [geometries[index] for index in order], types[order], set(range(len(order))),
            [source_ids[index] for index in order], [local_ids[index] for index in order],
        )
        stable_pairs = {
            name: {(local_ids[order[source]], local_ids[order[destination]]) for source, destination in pairs}
            for name, pairs in shuffled.items()
        }
        expected_stable = {
            name: {(local_ids[source], local_ids[destination]) for source, destination in pairs}
            for name, pairs in result.items()
        }
        self.assertEqual(stable_pairs, expected_stable)

    def test_float32_ulp_distance_is_sign_safe(self):
        one = np.float32(1.0)
        next_one = np.nextafter(one, np.float32(np.inf), dtype=np.float32)
        two_away = np.nextafter(next_one, np.float32(np.inf), dtype=np.float32)
        self.assertEqual(float32_ulp_distance(one, one), 0)
        self.assertEqual(float32_ulp_distance(one, next_one), 1)
        self.assertEqual(float32_ulp_distance(one, two_away), 2)
        negative = np.float32(-1.0)
        next_negative = np.nextafter(negative, np.float32(-np.inf), dtype=np.float32)
        self.assertEqual(float32_ulp_distance(negative, next_negative), 1)
        self.assertEqual(float32_ulp_distance(np.float32(-0.0), np.float32(0.0)), 1)
        with self.assertRaises(ValueError):
            float32_ulp_distance(np.float32(np.inf), one)

    def test_seed_is_repeatable_and_view_specific(self):
        left = keyed_rng(7, 2, "scene", 0, "lane", 3).integers(0, 2**31, size=8)
        repeat = keyed_rng(7, 2, "scene", 0, "lane", 3).integers(0, 2**31, size=8)
        right = keyed_rng(7, 2, "scene", 1, "lane", 3).integers(0, 2**31, size=8)
        np.testing.assert_array_equal(left, repeat)
        self.assertFalse(np.array_equal(left, right))

    def test_lane_clamp_and_missing(self):
        class Fixed:
            def __init__(self, values): self.values = iter(values)
            def random(self): return next(self.values)
        self.assertEqual(perturb_lane_value(1, 0, Fixed([0.0, 0.0]), 0.1), (1, 0, True, -1))
        self.assertEqual(perturb_lane_value(None, 1, Fixed([]), 1.0), (None, 1, False, 0))

    def test_degree_two_and_cycle_propagation(self):
        endpoints = np.asarray([[0, 1], [1, 2], [2, 3]], dtype=np.int64)
        self.assertEqual(road_removal_closure([1], endpoints, np.asarray([1, 2, 2, 1])), {0, 1, 2})
        cycle = np.asarray([[0, 1], [1, 2], [2, 0]], dtype=np.int64)
        self.assertEqual(road_removal_closure([0], cycle, np.asarray([2, 2, 2])), {0, 1, 2})

    def test_boundary_endpoints_multipart_and_hole(self):
        line = LineString([(-250.0, 0.0), (0.0, 0.0), (250.0, 0.0)])
        changed = jitter_geometry(line, np.random.default_rng(1), 1.0, 2.0, 1e-8, True)
        self.assertEqual(changed.coords[0], line.coords[0])
        self.assertEqual(changed.coords[-1], line.coords[-1])
        polygon = MultiPolygon([
            Polygon([(0, 0), (5, 0), (5, 5), (0, 5), (0, 0)],
                    [[(1, 1), (2, 1), (2, 2), (1, 2), (1, 1)]]),
            Polygon([(10, 10), (11, 10), (11, 11), (10, 11), (10, 10)]),
        ])
        changed = jitter_geometry(polygon, np.random.default_rng(2), 1.0, 0.1, 1e-8, False)
        self.assertEqual(structure_signature(changed), structure_signature(polygon))


if __name__ == "__main__":
    unittest.main()
