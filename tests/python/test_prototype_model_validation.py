#!/usr/bin/env python3

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import jsonschema
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from run_prototype_model_validation import (  # noqa: E402
    cosine_rankings,
    immutable_publish,
    source_ranks,
    tensor_digest,
)


class PrototypeModelValidationTest(unittest.TestCase):
    def test_original_self_exclusion_has_full_deterministic_ranking_without_labels(self):
        scene_ids = ["scn_a", "scn_b", "scn_c"]
        embeddings = np.asarray([[1, 0], [0.8, 0.6], [0, 1]], dtype=np.float32)
        rows, digest = cosine_rankings(scene_ids, embeddings, embeddings, exclude_self=True)
        self.assertEqual(len(rows), 6)
        self.assertTrue(all(row["candidate_count"] == 2 for row in rows))
        self.assertTrue(all(row["query_scene_id"] != row["candidate_scene_id"] for row in rows))
        shuffled = [2, 0, 1]
        shuffled_ids = [scene_ids[index] for index in shuffled]
        shuffled_rows, _ = cosine_rankings(shuffled_ids, embeddings[shuffled], embeddings[shuffled], exclude_self=True)
        canonical = sorted(rows, key=lambda row: (row["query_scene_id"], row["rank"]))
        reordered = sorted(shuffled_rows, key=lambda row: (row["query_scene_id"], row["rank"]))
        self.assertEqual(canonical, reordered)
        self.assertEqual(len(digest), 64)

    def test_augmented_source_metrics_use_only_matching_original_scene(self):
        scene_ids = ["scn_a", "scn_b", "scn_c"]
        candidates = np.eye(3, dtype=np.float32)
        queries = candidates.copy()
        rows, metrics, digest = source_ranks(scene_ids, queries, candidates)
        self.assertEqual([row["candidate_scene_id"] for row in rows], scene_ids)
        self.assertEqual([row["rank"] for row in rows], [1, 1, 1])
        self.assertEqual(metrics, {"MRR": 1.0, "HIT@1": 1.0, "HIT@5": 1.0, "HIT@10": 1.0})
        self.assertEqual(len(digest), 64)

    def test_embedding_digest_is_canonical_order_sensitive(self):
        values = np.asarray([[1, 0], [0, 1]], dtype=np.float32)
        first = tensor_digest(["a", "b"], values)
        second = tensor_digest(["b", "a"], values[[1, 0]])
        self.assertNotEqual(first, second)
        self.assertEqual(first, tensor_digest(["a", "b"], values.copy()))

    def test_immutable_reuse_and_collision(self):
        with tempfile.TemporaryDirectory(prefix="fuse-i23-test-") as directory:
            root = Path(directory); final = root / "final"; names = ["manifest.json", "data.parquet"]
            first = root / "first"; first.mkdir()
            for name in names:
                (first / name).write_text(name)
            self.assertEqual(immutable_publish(first, final, names), "new_publish")
            repeat = root / "repeat"; shutil.copytree(final, repeat)
            self.assertEqual(immutable_publish(repeat, final, names), "identical_reuse")
            collision = root / "collision"; shutil.copytree(final, collision)
            (collision / names[1]).write_text("different")
            with self.assertRaises(FileExistsError):
                immutable_publish(collision, final, names)

    def test_schema_rejects_original_relevance_metrics(self):
        schema = json.loads((ROOT / "config/schemas/prototype_model_validation.schema.json").read_text())
        original = schema["properties"]["original_retrieval"]
        self.assertFalse(original.get("additionalProperties", True))
        self.assertNotIn("MRR", original["properties"])
        jsonschema.Draft202012Validator.check_schema(schema)


if __name__ == "__main__":
    unittest.main()
