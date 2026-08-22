import io
import json
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from accept_prototype_training_dataset import (  # noqa: E402
    MemoryArchive,
    compare_directories,
    read_indexed_member,
    validate_branch_sets,
    validate_category_arrays,
    validate_scene_assignments,
)
from serialize_prototype_shard import add_tar_member, sha256_file, tensor_bytes  # noqa: E402
from validate_prototype_serialization_shards import validate_scene_tensors  # noqa: E402


class TrainingDatasetAcceptanceFixtureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = yaml.safe_load((ROOT / "config/serialization_shard.yml").read_text())

    def zero_scene_payloads(self, edge_shape=(2, 0), raster_shape=(22, 100, 100)):
        arrays = {
            "entities": {
                "local_entity_id": np.empty((0,), np.int64), "entity_type": np.empty((0,), np.uint8),
                "relative_position_m": np.empty((0, 2), np.float32), "object_raster": np.empty((0, 26), np.float32),
                "object_dem_missing": np.empty((0, 2), np.uint8), "building_row_index": np.empty((0,), np.int64),
                "building_category": np.empty((0, 2), np.int32), "building_numerical": np.empty((0, 2), np.float32),
                "building_missing": np.empty((0, 2), np.uint8), "road_row_index": np.empty((0,), np.int64),
                "road_category": np.empty((0, 2), np.int32), "road_numerical": np.empty((0, 1), np.float32),
                "road_missing": np.empty((0, 1), np.uint8), "poi_row_index": np.empty((0,), np.int64),
                "poi_category": np.empty((0, 6), np.int32),
            },
            "geometry": {
                "coordinates_xy": np.empty((0, 2), np.float32),
                "coordinates_absolute_xy_5186": np.empty((0, 2), np.float64),
                "reference_center_absolute_xy_5186": np.empty((0, 2), np.float64),
                "building_observed_area_m2_reference": np.empty((0,), np.float64),
                "geometry_type": np.empty((0,), np.uint8),
                "geometry_available": np.empty((0,), np.uint8), "entity_coordinate_offsets": np.asarray([0], np.int64),
                "entity_component_offsets": np.asarray([0], np.int64), "component_coordinate_offsets": np.asarray([0], np.int64),
                "entity_part_offsets": np.asarray([0], np.int64), "part_coordinate_offsets": np.asarray([0], np.int64),
                "entity_ring_offsets": np.asarray([0], np.int64), "ring_component_index": np.empty((0,), np.int64),
                "ring_coordinate_start": np.empty((0,), np.int64), "ring_coordinate_end": np.empty((0,), np.int64),
                "ring_is_hole": np.empty((0,), np.uint8),
            },
            "edges": {"edge_index": np.empty(edge_shape, np.int64), "relation_mask": np.empty((0,), np.uint8)},
            "topology": {
                "road_endpoint_node_index": np.empty((0, 2), np.int64),
                "road_endpoint_retained": np.empty((0, 2), np.uint8),
                "node_incident_road_count": np.empty((0,), np.int32),
                "node_state": np.empty((0,), np.uint8),
                "node_xy_5186": np.empty((0, 2), np.float64),
            },
            "rasters": {
                "landcover_class_fraction": np.zeros(raster_shape, np.float32),
                "landcover_valid_support": np.zeros((100, 100), np.float32),
                "landcover_valid_mask": np.ones((100, 100), np.uint8),
                "dem_standardized_mean": np.zeros((17, 17), np.float32),
                "dem_valid_support": np.zeros((17, 17), np.float32),
                "dem_valid_mask": np.ones((17, 17), np.uint8),
            },
        }
        meta = {
            "scene_id": "scene", "split": "training", "crs": "EPSG:5186",
            "local_entity_ids": [], "empty_edge": True,
            "counts": {"nodes": 0, "edges": 0, "coordinates": 0},
            "road_topology": {"road_local_entity_ids": [], "original_node_ids": []},
        }
        payloads = {"scene.meta.json": json.dumps(meta).encode()}
        payloads.update({f"scene.{group}.safetensors": tensor_bytes(value) for group, value in arrays.items()})
        return payloads

    def test_missing_duplicate_extra_shard_and_scene(self):
        validate_branch_sets(["a", "b"], ["b", "a"])
        for observed in (["a"], ["a", "a"], ["a", "b", "c"]):
            with self.assertRaises(ValueError):
                validate_branch_sets(["a", "b"], observed)
        expected = {"s1": "training", "s2": "validation"}
        validate_scene_assignments([{"scene_id": "s2", "split": "validation"}, {"scene_id": "s1", "split": "training"}], expected)
        for rows in (
            [{"scene_id": "s1", "split": "training"}],
            [{"scene_id": "s1", "split": "training"}] * 2,
            [{"scene_id": "s1", "split": "validation"}, {"scene_id": "s2", "split": "validation"}],
        ):
            with self.assertRaises(ValueError):
                validate_scene_assignments(rows, expected)

    def test_direct_seek_offset_size_member_and_checksum(self):
        metadata = {"mtime": 0, "uid": 0, "gid": 0, "uname": "", "gname": "", "mode": 420}
        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode="w", format=tarfile.USTAR_FORMAT) as archive:
            offset, length = add_tar_member(archive, "scene.meta.json", b"payload", metadata)
        record = {"offset": offset, "length": length, "payload_bytes": 7,
                  "sha256": __import__("hashlib").sha256(b"payload").hexdigest()}
        self.assertEqual(read_indexed_member(io.BytesIO(output.getvalue()), record, "scene.meta.json"), b"payload")
        for change in ({"offset": 512}, {"payload_bytes": 8}, {"sha256": "0" * 64}):
            corrupted = dict(record, **change)
            with self.assertRaises(ValueError):
                read_indexed_member(io.BytesIO(output.getvalue()), corrupted, "scene.meta.json")
        bad_tar = bytearray(output.getvalue()); bad_tar[0] ^= 1
        with self.assertRaises(ValueError):
            read_indexed_member(io.BytesIO(bad_tar), record, "scene.meta.json")
        with self.assertRaises(ValueError):
            read_indexed_member(io.BytesIO(output.getvalue()), record, "scene.edges.safetensors")

    def test_zero_node_empty_edge_tensor_schema_and_corruption(self):
        payloads = self.zero_scene_payloads()
        metrics = validate_scene_tensors(MemoryArchive(payloads), "scene", "training", self.config)
        self.assertEqual(metrics, {"node_count": 0, "ordered_edge_count": 0, "coordinate_count": 0, "empty_edge_scene_count": 1})
        for payload_set in (
            self.zero_scene_payloads(edge_shape=(0, 2)),
            self.zero_scene_payloads(raster_shape=(21, 100, 100)),
        ):
            with self.assertRaises(ValueError):
                validate_scene_tensors(MemoryArchive(payload_set), "scene", "training", self.config)
        corrupted = dict(payloads); corrupted["scene.edges.safetensors"] = corrupted["scene.edges.safetensors"][:-1]
        with self.assertRaises(Exception):
            validate_scene_tensors(MemoryArchive(corrupted), "scene", "training", self.config)

    def test_category_missing_alias_invalid_and_raw_mask(self):
        entities = {
            "building_category": np.asarray([[0, 2], [1, 20]], np.int32),
            "road_category": np.empty((0, 2), np.int32), "poi_category": np.empty((0, 6), np.int32),
        }
        limits = {name: 30 for group in self.config["tensor"]["categorical_attributes"].values() for name in group}
        masks = {name: 21 for name in limits}
        validate_category_arrays(entities, self.config, limits, masks)
        entities["building_category"][0, 0] = 31
        with self.assertRaisesRegex(ValueError, "range"):
            validate_category_arrays(entities, self.config, limits, masks)
        entities["building_category"][0, 0] = 21
        with self.assertRaisesRegex(ValueError, "MASK"):
            validate_category_arrays(entities, self.config, limits, masks)

    def test_checksum_identity_shuffle_and_immutable_reuse_conflict(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"; source.write_bytes(b"I13")
            expected = sha256_file(source); self.assertEqual(expected, sha256_file(source))
            source.write_bytes(b"mismatch"); self.assertNotEqual(expected, sha256_file(source))
            first, same, conflict = root / "first", root / "same", root / "conflict"
            first.mkdir(); same.mkdir(); conflict.mkdir()
            (first / "x").write_bytes(b"a"); (same / "x").write_bytes(b"a"); (conflict / "x").write_bytes(b"b")
            compare_directories(first, same)
            with self.assertRaises(FileExistsError):
                compare_directories(first, conflict)
        values = [{"branch_id": "b", "sha256": "2"}, {"branch_id": "a", "sha256": "1"}]
        self.assertEqual(sorted(values, key=lambda x: x["branch_id"]), sorted(reversed(values), key=lambda x: x["branch_id"]))


if __name__ == "__main__":
    unittest.main()
