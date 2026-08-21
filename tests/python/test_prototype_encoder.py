#!/usr/bin/env python3

import sys
import unittest
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from prototype_encoder import relation_set_embedding, segment_fourier, sinusoidal_position_features


class PrototypeEncoderFixtureTest(unittest.TestCase):
    def test_position_features_have_thesis_dimension_and_meter_period(self):
        wavelengths = torch.logspace(1, 3, 16)
        values = sinusoidal_position_features(torch.tensor([[0.0, 0.0], [10.0, 10.0]]), wavelengths)
        self.assertEqual(tuple(values.shape), (2, 64))
        self.assertTrue(torch.allclose(values[0, 0::4], torch.zeros(16)))
        self.assertAlmostEqual(float(values[1, 0]), 0.0, places=5)

    def test_arc_length_fourier_zero_frequency(self):
        points = torch.tensor([[0.0, 0.0], [3.0, 4.0], [6.0, 8.0]])
        response = segment_fourier(points, torch.zeros((1, 2)))
        self.assertAlmostEqual(float(response.real), 10.0, places=5)
        self.assertAlmostEqual(float(response.imag), 0.0, places=5)

    def test_multi_relation_mask_is_embedding_sum(self):
        embedding = torch.nn.Embedding(5, 3)
        with torch.no_grad():
            embedding.weight.copy_(torch.arange(15).reshape(5, 3))
        observed = relation_set_embedding(torch.tensor([1 | 4 | 16], dtype=torch.uint8), embedding)
        expected = embedding.weight[[0, 2, 4]].sum(dim=0, keepdim=True)
        self.assertTrue(torch.equal(observed, expected))


if __name__ == "__main__":
    unittest.main()
