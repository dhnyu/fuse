import hashlib
import gc
import io
import json
import os
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

import numpy as np
import psutil
import torch
from safetensors.numpy import load as load_safetensors
from torch.utils.data import DataLoader, Dataset

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from prototype_dataloader import (  # noqa: E402
    DeterministicBudgetBatchSampler,
    logical_batch_digest,
    make_dataloader,
    ragged_collate,
    read_indexed_member,
    restore_geometry_coordinates,
    validate_index_rows,
)
from serialize_prototype_shard import add_tar_member, tensor_bytes  # noqa: E402


BUDGETS = {"scenes": 2, "nodes": 4, "ordered_edges": 4, "coordinates": 8, "actual_payload_bytes": 100}


def sample(scene_id, n, edges, coordinates, empty=False, split="training", global_index=0):
    entity_type = torch.zeros(n, dtype=torch.uint8)
    entities = {
        "local_entity_id": torch.arange(n, dtype=torch.int64), "entity_type": entity_type,
        "relative_position_m": torch.arange(n * 2, dtype=torch.float32).reshape(n, 2),
        "object_raster": torch.zeros((n, 26), dtype=torch.float32),
        "object_dem_missing": torch.zeros((n, 2), dtype=torch.uint8),
        "building_row_index": torch.arange(n, dtype=torch.int64),
        "building_category": torch.zeros((n, 2), dtype=torch.int32),
        "building_numerical": torch.zeros((n, 2), dtype=torch.float32),
        "building_missing": torch.zeros((n, 2), dtype=torch.uint8),
        "road_row_index": torch.empty((0,), dtype=torch.int64),
        "road_category": torch.empty((0, 2), dtype=torch.int32),
        "road_numerical": torch.empty((0, 1), dtype=torch.float32),
        "road_missing": torch.empty((0, 1), dtype=torch.uint8),
        "poi_row_index": torch.empty((0,), dtype=torch.int64),
        "poi_category": torch.empty((0, 6), dtype=torch.int32),
    }
    c = len(coordinates)
    if n:
        entity_coordinates = torch.tensor([0, *([c] * n)], dtype=torch.int64)
        entity_parts = torch.tensor([0, *([1] * n)], dtype=torch.int64)
        entity_rings = torch.tensor([0, *([1] * n)], dtype=torch.int64)
        part_coordinates = torch.tensor([0, c], dtype=torch.int64)
        ring_component = torch.tensor([0], dtype=torch.int64)
        ring_start, ring_end, ring_hole = torch.tensor([0]), torch.tensor([c]), torch.tensor([1], dtype=torch.uint8)
    else:
        entity_coordinates = entity_parts = entity_rings = part_coordinates = torch.tensor([0], dtype=torch.int64)
        ring_component = ring_start = ring_end = torch.empty((0,), dtype=torch.int64)
        ring_hole = torch.empty((0,), dtype=torch.uint8)
    geometry = {
        "coordinates_xy_m": torch.tensor(coordinates, dtype=torch.float32).reshape(c, 2),
        "geometry_type": torch.zeros(n, dtype=torch.uint8), "geometry_available": torch.ones(n, dtype=torch.uint8),
        "entity_coordinate_offsets": entity_coordinates, "entity_part_offsets": entity_parts,
        "entity_component_offsets": entity_parts.clone(), "part_coordinate_offsets": part_coordinates,
        "component_coordinate_offsets": part_coordinates.clone(), "entity_ring_offsets": entity_rings,
        "ring_component_index": ring_component, "ring_coordinate_start": ring_start,
        "ring_coordinate_end": ring_end, "ring_is_hole": ring_hole,
    }
    edge_index = torch.tensor(edges, dtype=torch.int64).reshape(2, -1)
    edge_count = edge_index.shape[1]
    rasters = {
        "landcover_class_fraction": torch.zeros((22, 100, 100)),
        "landcover_valid_support": torch.zeros((100, 100)),
        "landcover_valid_mask": torch.zeros((100, 100), dtype=torch.uint8),
        "dem_standardized_mean": torch.zeros((17, 17)), "dem_valid_support": torch.zeros((17, 17)),
        "dem_valid_mask": torch.zeros((17, 17), dtype=torch.uint8),
    }
    return {
        "scene_id": scene_id, "split": split, "global_index": global_index, "split_local_index": global_index,
        "meta": {"scene_id": scene_id}, "entities": entities, "geometry": geometry,
        "edges": {"edge_index": edge_index, "relation_mask": torch.full((edge_count,), 5, dtype=torch.uint8)},
        "rasters": rasters,
        "resources": {"nodes": n, "ordered_edges": edge_count, "coordinates": c, "actual_payload_bytes": 10},
        "units": {"relative_position": "meter", "intrinsic_geometry": "meter", "crs": "EPSG:5186", "geometry_storage_scale_to_m": 500.0},
    }


class MemoryDataset(Dataset):
    def __init__(self, samples):
        self.samples = samples
        self.rows = [
            {"node_count": value["resources"]["nodes"], "ordered_edge_count": value["resources"]["ordered_edges"],
             "coordinate_count": value["resources"]["coordinates"], "actual_payload_bytes": 10}
            for value in samples
        ]

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, index):
        return self.samples[index]


class ErrorDataset(Dataset):
    def __len__(self):
        return 2

    def __getitem__(self, index):
        if index == 1:
            raise RuntimeError("fixture worker failure")
        return index


class PrototypeDataLoaderFixtureTest(unittest.TestCase):
    def test_empty_node_edge_and_multipart_hole_collate(self):
        empty = sample("empty", 0, [[], []], [], empty=True, global_index=0)
        multipart = sample("multipart", 1, [[], []], [[0, 0], [1, 0], [0, 0]], global_index=1)
        batch = ragged_collate([empty, multipart], BUDGETS)
        self.assertEqual(batch["scene_ptr"].tolist(), [0, 0, 1])
        self.assertEqual(tuple(batch["edges"]["edge_index"].shape), (2, 0))
        self.assertEqual(batch["edge_ptr"].tolist(), [0, 0, 0])
        self.assertEqual(batch["geometry"]["ring_is_hole"].tolist(), [1])
        self.assertEqual(batch["coordinate_ptr"].tolist(), [0, 0, 3])

    def test_multiple_scene_edge_rebasing_and_local_mapping(self):
        first = sample("first", 2, [[0], [1]], [[0, 0], [1, 0]], global_index=0)
        second = sample("second", 2, [[1], [0]], [[0, 0], [2, 0]], global_index=1)
        batch = ragged_collate([first, second], BUDGETS)
        self.assertEqual(batch["edges"]["edge_index"].tolist(), [[0, 3], [1, 2]])
        self.assertEqual(batch["entity_scene_index"].tolist(), [0, 0, 1, 1])
        self.assertEqual(batch["entity_local_index"].tolist(), [0, 1, 0, 1])

    def test_coordinate_scale_restoration(self):
        stored = torch.tensor([[0.5, -0.25]], dtype=torch.float32)
        self.assertTrue(torch.equal(restore_geometry_coordinates(stored, 500.0), torch.tensor([[250.0, -125.0]])))
        with self.assertRaises(ValueError):
            restore_geometry_coordinates(stored, 0)

    def test_budget_boundary_oversize_and_fixed_seed_shuffle(self):
        rows = [
            {"node_count": 2, "ordered_edge_count": 2, "coordinate_count": 4, "actual_payload_bytes": 50},
            {"node_count": 2, "ordered_edge_count": 2, "coordinate_count": 4, "actual_payload_bytes": 50},
            {"node_count": 5, "ordered_edge_count": 0, "coordinate_count": 0, "actual_payload_bytes": 10},
        ]
        sampler = DeterministicBudgetBatchSampler(rows, BUDGETS)
        self.assertEqual(sampler.batches(), [[0, 1], [2]])
        shuffled_a = DeterministicBudgetBatchSampler(rows, BUDGETS, True, 7).batches()
        shuffled_b = DeterministicBudgetBatchSampler(rows, BUDGETS, True, 7).batches()
        self.assertEqual(shuffled_a, shuffled_b)
        oversized = ragged_collate([sample("large", 5, [[], []], [], global_index=2)], BUDGETS)
        self.assertTrue(oversized["oversize_singleton"])

    def test_worker_count_determinism_and_fd_cleanup(self):
        values = [sample(f"s{i}", 1, [[], []], [[i, 0]], global_index=i) for i in range(4)]
        dataset = MemoryDataset(values)
        outputs = []
        process = psutil.Process(); before = process.num_fds()
        for workers in (0, 4):
            loader, sampler = make_dataloader(dataset, BUDGETS, workers, True, 9)
            batches = list(loader)
            outputs.append(([x for batch in batches for x in batch["scene_ids"]], [logical_batch_digest(batch) for batch in batches], sampler.batches()))
            del batches, loader
            gc.collect()
        self.assertEqual(outputs[0], outputs[1])
        warmed = process.num_fds()
        loader, _ = make_dataloader(dataset, BUDGETS, 4, True, 9)
        batches = list(loader)
        del batches, loader
        gc.collect()
        self.assertLessEqual(process.num_fds(), warmed)
        self.assertLessEqual(warmed - before, 4)

    def test_corrupted_index_tar_member_and_safetensors(self):
        metadata = {"mtime": 0, "uid": 0, "gid": 0, "uname": "", "gname": "", "mode": 420}
        output = io.BytesIO(); payload = tensor_bytes({"x": np.asarray([1], np.int32)})
        with tarfile.open(fileobj=output, mode="w", format=tarfile.USTAR_FORMAT) as archive:
            offset, length = add_tar_member(archive, "scene.entities.safetensors", payload, metadata)
        record = {"offset": offset, "length": length, "payload_bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}
        self.assertIn("x", load_safetensors(read_indexed_member(io.BytesIO(output.getvalue()), record, "scene.entities.safetensors")))
        for changed in ({"offset": 512}, {"sha256": "0" * 64}):
            with self.assertRaises(ValueError):
                read_indexed_member(io.BytesIO(output.getvalue()), dict(record, **changed), "scene.entities.safetensors")
        with self.assertRaises(ValueError):
            read_indexed_member(io.BytesIO(output.getvalue()), record, "scene.geometry.safetensors")
        with self.assertRaises(Exception):
            load_safetensors(payload[:-1])
        with tempfile.TemporaryDirectory() as temporary:
            bad_index = Path(temporary) / "bad.idx"; bad_index.write_text("{bad")
            with self.assertRaises(json.JSONDecodeError):
                json.loads(bad_index.read_text())

    def test_wrong_split_index_and_worker_exception_propagation(self):
        dataset_index = {"splits": {"training": {"scene_count": 1, "global_order_start": 0, "global_order_end_exclusive": 1}}}
        good = [{"training_dataset_id": "accepted", "scene_id": "s", "split": "training", "global_order": 0, "split_local_order": 0}]
        validate_index_rows(good, dataset_index, "accepted")
        bad = [dict(good[0], split="validation")]
        with self.assertRaises(ValueError):
            validate_index_rows(bad, dataset_index, "accepted")
        loader = DataLoader(ErrorDataset(), num_workers=1)
        with self.assertRaisesRegex(RuntimeError, "fixture worker failure"):
            list(loader)


if __name__ == "__main__":
    unittest.main()
