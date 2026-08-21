import io
import json
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

import numpy as np
from shapely.geometry import MultiPolygon, Polygon

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from serialize_prototype_shard import (  # noqa: E402
    MEMBER_SUFFIXES,
    add_tar_member,
    build_edge_tensors,
    category_index,
    compare_directories,
    geometry_parts,
    sha256_file,
    standardized,
    tensor_bytes,
    validate_tar_member_names,
    validate_tensor_roundtrip,
    verify_record,
)


class SerializationShardFixtureTest(unittest.TestCase):
    def test_zero_node_and_empty_edge_shapes(self):
        edges = build_edge_tensors([], {}, "zero")
        self.assertEqual(edges["edge_index"].shape, (2, 0))
        self.assertEqual(edges["relation_mask"].shape, (0,))
        payload = tensor_bytes(edges)
        validate_tensor_roundtrip(payload, edges, 1e-5)

    def test_multipart_polygon_hole_offsets_inputs(self):
        with_hole = Polygon(
            [(0, 0), (4, 0), (4, 4), (0, 4), (0, 0)],
            holes=[[(1, 1), (2, 1), (2, 2), (1, 2), (1, 1)]],
        )
        multi = MultiPolygon([with_hole, Polygon([(10, 0), (11, 0), (11, 1), (10, 0)])])
        parts, rings, ring_parts = geometry_parts(multi)
        self.assertEqual(len(parts), 2)
        self.assertEqual(len(rings), 3)
        self.assertEqual([hole for _, hole in rings], [False, True, False])
        self.assertEqual(ring_parts, [0, 0, 1])
        self.assertEqual(sum(map(len, parts)), sum(len(ring) for ring, _ in rings))

    def test_missing_alias_invalid_and_raw_mask_categories(self):
        vocab = {"A11": {"12": 2, "MISSING": 20, "MASK": 21}}
        missing = {"A11": 20}
        self.assertEqual(category_index("A11", None, vocab, missing), 20)
        self.assertEqual(category_index("A11", "12", vocab, missing), 2)
        with self.assertRaisesRegex(ValueError, "invalid category"):
            category_index("A11", "999", vocab, missing)
        with self.assertRaisesRegex(ValueError, "raw MASK"):
            category_index("A11", "MASK", vocab, missing)

    def test_numerical_missing_and_valid_zero_standardized(self):
        stats = {"x": {"transform": "identity", "mean": 5.0, "applied_scale": 2.0}}
        value, indicator = standardized(5.0, "x", stats)
        self.assertEqual(float(value), 0.0)
        self.assertEqual(int(indicator), 0)
        value, indicator = standardized(None, "x", stats)
        self.assertEqual(float(value), 0.0)
        self.assertEqual(int(indicator), 1)

    def test_multi_relation_mask_and_dangling_edge(self):
        edge = {
            "source_local_entity_id": 10, "destination_local_entity_id": 20,
            "relation_mask": 5, "has_sn": True, "has_cnt": False,
            "has_wit": True, "has_int": False, "has_con": False,
        }
        tensors = build_edge_tensors([edge], {10: 0, 20: 1}, "scene")
        self.assertEqual(tensors["edge_index"].tolist(), [[0], [1]])
        self.assertEqual(tensors["relation_mask"].tolist(), [5])
        with self.assertRaisesRegex(ValueError, "dangling"):
            build_edge_tensors([edge], {10: 0}, "scene")
        reverse = dict(edge, source_local_entity_id=20, destination_local_entity_id=10)
        shuffled = build_edge_tensors([reverse, edge], {10: 0, 20: 1}, "scene")
        ordered = build_edge_tensors([edge, reverse], {10: 0, 20: 1}, "scene")
        self.assertTrue(np.array_equal(shuffled["edge_index"], ordered["edge_index"]))
        self.assertTrue(np.array_equal(shuffled["relation_mask"], ordered["relation_mask"]))

    def test_deterministic_tar_and_corrupted_member_order(self):
        metadata = {"mtime": 0, "uid": 0, "gid": 0, "uname": "", "gname": "", "mode": 420}
        def archive_bytes():
            output = io.BytesIO()
            with tarfile.open(fileobj=output, mode="w", format=tarfile.USTAR_FORMAT) as archive:
                for suffix in MEMBER_SUFFIXES:
                    add_tar_member(archive, f"scene.{suffix}", suffix.encode(), metadata)
            return output.getvalue()
        self.assertEqual(archive_bytes(), archive_bytes())
        validate_tar_member_names([f"scene.{suffix}" for suffix in MEMBER_SUFFIXES], ["scene"])
        with self.assertRaisesRegex(ValueError, "tar member"):
            validate_tar_member_names(["scene.meta.json"] * 2, ["scene"])

    def test_checksum_mismatch_and_immutable_conflict(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "source"
            path.write_bytes(b"one")
            record = {"path": str(path), "size_bytes": 3, "sha256": sha256_file(path)}
            verify_record(record, "source")
            path.write_bytes(b"two")
            with self.assertRaisesRegex(ValueError, "checksum"):
                verify_record(record, "source")
            left, right = root / "left", root / "right"
            left.mkdir(); right.mkdir()
            (left / "x").write_bytes(b"a"); (right / "x").write_bytes(b"b")
            with self.assertRaisesRegex(FileExistsError, "different immutable"):
                compare_directories(left, right)

    def test_shuffled_tensor_keys_and_corrupted_safetensors(self):
        first = {"b": np.asarray([2], dtype=np.int32), "a": np.asarray([1], dtype=np.int32)}
        second = {"a": first["a"], "b": first["b"]}
        self.assertEqual(tensor_bytes(first), tensor_bytes(second))
        with self.assertRaises(Exception):
            validate_tensor_roundtrip(tensor_bytes(first)[:-1], first, 1e-5)


if __name__ == "__main__":
    unittest.main()
