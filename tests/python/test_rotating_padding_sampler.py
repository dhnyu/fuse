import unittest

import numpy as np

from rotating_padding_sampler import logical_groups, negative_candidate_mask, rotating_padding_state


class RotatingPaddingSamplerTest(unittest.TestCase):
    def test_full_population_contract(self):
        scenes = [f"scn_{index:04d}" for index in range(2421)]
        first = rotating_padding_state(scenes, 20260822, 0)
        second = rotating_padding_state(list(reversed(scenes)), 20260822, 0)
        self.assertEqual(first, second)
        self.assertEqual(len(first.permutation), 2421)
        self.assertEqual(len(first.padding_scene_ids), 11)
        self.assertEqual(len(logical_groups(first)), 76)
        self.assertEqual(set(first.permutation), set(scenes))
        self.assertNotEqual(first.padding_scene_ids, rotating_padding_state(scenes, 20260822, 1).padding_scene_ids)

    def test_prototype_has_no_padding(self):
        state = rotating_padding_state([f"scn_{index:03d}" for index in range(256)], 20260822, 0)
        self.assertEqual(state.padding_scene_ids, ())
        self.assertEqual(len(logical_groups(state)), 8)

    def test_duplicate_ids_are_not_negatives(self):
        mask = negative_candidate_mask(["a", "b", "a"])
        np.testing.assert_array_equal(mask, [[False, True, False], [True, False, True], [False, True, False]])

    def test_duplicate_population_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unique"):
            rotating_padding_state(["a", "a"], 1, 0)


if __name__ == "__main__":
    unittest.main()
