#!/usr/bin/env python3
"""Reusable indexed Dataset, deterministic sampler, and ragged collate for I17."""

from __future__ import annotations

import hashlib
import json
import math
import os
import tarfile
import time
from collections import OrderedDict
from functools import partial
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow.parquet as pq
import torch
import yaml
from safetensors.numpy import load as load_safetensors
from torch.utils.data import DataLoader, Dataset, Sampler


MEMBER_SUFFIXES = (
    "meta.json", "entities.safetensors", "geometry.safetensors",
    "edges.safetensors", "topology.safetensors", "rasters.safetensors",
)
RESOURCE_COLUMNS = {
    "scenes": None,
    "nodes": "node_count",
    "ordered_edges": "ordered_edge_count",
    "coordinates": "coordinate_count",
    "actual_payload_bytes": "actual_payload_bytes",
}


def initialize_loader_worker(_: int) -> None:
    for name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        os.environ[name] = "1"
    torch.set_num_threads(1)


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def validate_index_rows(rows: list[dict[str, Any]], dataset_index: dict[str, Any], accepted_id: str) -> None:
    if not rows or any(row["training_dataset_id"] != accepted_id for row in rows):
        raise ValueError("accepted dataset identity mismatch in global index")
    scene_ids = [row["scene_id"] for row in rows]
    if len(scene_ids) != len(set(scene_ids)):
        raise ValueError("duplicate scene in accepted global index")
    if [int(row["global_order"]) for row in rows] != list(range(len(rows))):
        raise ValueError("global scene order is not contiguous")
    covered: set[str] = set()
    for split, contract in dataset_index["splits"].items():
        split_rows = [row for row in rows if row["split"] == split]
        if len(split_rows) != int(contract["scene_count"]):
            raise ValueError(f"wrong split count/index: {split}")
        if [int(row["split_local_order"]) for row in split_rows] != list(range(len(split_rows))):
            raise ValueError(f"split-local order is not contiguous: {split}")
        start, end = int(contract["global_order_start"]), int(contract["global_order_end_exclusive"])
        if [int(row["global_order"]) for row in split_rows] != list(range(start, end)):
            raise ValueError(f"split/global index mismatch: {split}")
        covered.update(row["scene_id"] for row in split_rows)
    if covered != set(scene_ids):
        raise ValueError("global index contains unknown split or split leakage")


def read_indexed_member(stream: Any, record: dict[str, Any], expected_name: str) -> bytes:
    stream.seek(int(record["offset"]))
    header = stream.read(512)
    if len(header) != 512:
        raise ValueError(f"truncated tar header: {expected_name}")
    try:
        info = tarfile.TarInfo.frombuf(header, encoding="utf-8", errors="surrogateescape")
    except tarfile.HeaderError as error:
        raise ValueError(f"corrupted tar header: {expected_name}") from error
    size = int(record["payload_bytes"])
    expected_length = 512 + math.ceil(size / 512) * 512
    if info.name != expected_name or info.size != size or int(record["length"]) != expected_length:
        raise ValueError(f"indexed member offset/size/name mismatch: {expected_name}")
    payload = stream.read(size)
    if len(payload) != size or hashlib.sha256(payload).hexdigest() != record["sha256"]:
        raise ValueError(f"indexed member checksum mismatch: {expected_name}")
    return payload


def numpy_group_to_torch(group: dict[str, np.ndarray]) -> dict[str, torch.Tensor]:
    return {key: torch.from_numpy(np.asarray(value).copy()) for key, value in group.items()}


def restore_geometry_coordinates(coordinates: torch.Tensor, scale_to_m: float) -> torch.Tensor:
    if scale_to_m <= 0:
        raise ValueError("invalid geometry coordinate scale")
    return coordinates * float(scale_to_m)


class AcceptedPrototypeDataset(Dataset):
    """Map-style dataset whose only data entry points are the I16 manifest/indexes."""

    def __init__(
        self,
        accepted_manifest: str | Path,
        tensor_contract: str | Path,
        split: str | None = None,
        verify_checksums: bool = True,
        archive_source_root: str | Path | None = None,
        archive_runtime_root: str | Path | None = None,
        persistent_archive_handles: bool = False,
        archive_handle_limit: int = 8,
        diagnostic_timing: bool = False,
    ) -> None:
        self.manifest_path = Path(accepted_manifest).resolve()
        self.root = self.manifest_path.parent
        self.manifest = read_json(self.manifest_path)
        self.accepted_id = self.manifest["training_dataset_id"]
        self.tensor_contract_path = Path(tensor_contract).resolve()
        self.tensor_contract = yaml.safe_load(self.tensor_contract_path.read_text(encoding="utf-8"))
        expected_contract_hash = self.manifest["scientific_identity"]["tensor_contract_sha256"]
        if sha256_file(self.tensor_contract_path) != expected_contract_hash:
            raise ValueError("I15 tensor scale metadata checksum mismatch")
        self.geometry_scale_to_m = float(self.tensor_contract["tensor"]["geometry_normalization_length_m"])
        if self.geometry_scale_to_m <= 0:
            raise ValueError("invalid or missing intrinsic geometry scale metadata")
        if self.tensor_contract["tensor"]["safetensors"]["entities"]["relative_position_m"]["dtype"] != "float32":
            raise ValueError("relative-position meter contract mismatch")
        vocabulary_record = self.manifest["scientific_identity"]["i13_accepted_artifacts"]["vocabulary"]
        vocabulary_path = Path(vocabulary_record["path"])
        if not vocabulary_path.is_file() or sha256_file(vocabulary_path) != vocabulary_record["sha256"]:
            raise ValueError("I13 vocabulary checksum mismatch")
        vocabulary_rows = pq.read_table(vocabulary_path, columns=["attribute", "index", "entry_type"]).to_pylist()
        self.category_max_index: dict[str, int] = {}
        self.category_mask_index: dict[str, set[int]] = {}
        for vocabulary_row in vocabulary_rows:
            attribute = vocabulary_row["attribute"]
            index = int(vocabulary_row["index"])
            self.category_max_index[attribute] = max(index, self.category_max_index.get(attribute, -1))
            if vocabulary_row["entry_type"] == "MASK":
                self.category_mask_index.setdefault(attribute, set()).add(index)

        output_records = {record["relative_path"]: record for record in self.manifest["outputs"]}
        dataset_index_path = self.root / "dataset_index.json"
        global_index_path = self.root / "global_scene_index.parquet"
        for path in (dataset_index_path, global_index_path):
            record = output_records.get(path.name)
            if record is None or not path.is_file():
                raise ValueError(f"I16 accepted index missing: {path.name}")
            if verify_checksums and (path.stat().st_size != int(record["size_bytes"]) or sha256_file(path) != record["sha256"]):
                raise ValueError(f"I16 accepted index checksum mismatch: {path.name}")
        self.dataset_index = read_json(dataset_index_path)
        all_rows = pq.read_table(global_index_path).to_pylist()
        validate_index_rows(all_rows, self.dataset_index, self.accepted_id)
        if split is not None and split not in self.dataset_index["splits"]:
            raise ValueError(f"unknown split: {split}")
        self.split = split
        if (archive_source_root is None) != (archive_runtime_root is None):
            raise ValueError("archive source/runtime roots must be supplied together")
        self.archive_source_root = Path(archive_source_root).resolve() if archive_source_root is not None else None
        self.archive_runtime_root = Path(archive_runtime_root).resolve() if archive_runtime_root is not None else None
        self.persistent_archive_handles = bool(persistent_archive_handles)
        self.archive_handle_limit = int(archive_handle_limit)
        if self.archive_handle_limit < 1:
            raise ValueError("archive_handle_limit must be positive")
        self.diagnostic_timing = bool(diagnostic_timing)
        self._archive_handles: OrderedDict[str, Any] = OrderedDict()
        self._validated_tensor_payloads: set[tuple[tuple[str, str, int], ...]] = set()
        self.rows = [row for row in all_rows if split is None or row["split"] == split]
        self.scene_to_position = {row["scene_id"]: index for index, row in enumerate(self.rows)}
        self._index_entries: dict[tuple[str, str], dict[str, Any]] = {}
        self._load_archive_indexes(verify_checksums)

    def __getstate__(self) -> dict[str, Any]:
        state = self.__dict__.copy()
        state["_archive_handles"] = OrderedDict()
        state["_validated_tensor_payloads"] = set()
        return state

    def __del__(self) -> None:
        for stream in getattr(self, "_archive_handles", {}).values():
            try:
                stream.close()
            except Exception:
                pass

    def _runtime_archive_path(self, authoritative_path: str | Path) -> Path:
        path = Path(authoritative_path).resolve()
        if self.archive_source_root is None:
            return path
        try:
            relative = path.relative_to(self.archive_source_root)
        except ValueError as error:
            raise ValueError(f"archive is outside the authoritative serialization root: {path}") from error
        runtime_path = self.archive_runtime_root / relative
        if not runtime_path.is_file():
            raise ValueError(f"runtime archive mirror is incomplete: {runtime_path}")
        return runtime_path

    def _archive_stream(self, path: Path) -> tuple[Any, bool]:
        key = str(path)
        stream = self._archive_handles.pop(key, None)
        if stream is not None:
            self._archive_handles[key] = stream
            return stream, True
        stream = path.open("rb", buffering=0)
        self._archive_handles[key] = stream
        while len(self._archive_handles) > self.archive_handle_limit:
            _, expired = self._archive_handles.popitem(last=False)
            expired.close()
        return stream, False

    def _load_archive_indexes(self, verify_checksums: bool) -> None:
        by_index: dict[str, list[dict[str, Any]]] = {}
        for row in self.rows:
            by_index.setdefault(row["idx_path"], []).append(row)
        verified_tar: set[str] = set()
        for idx_value, rows in sorted(by_index.items()):
            idx_path = self._runtime_archive_path(idx_value)
            first = rows[0]
            if not idx_path.is_file():
                raise ValueError(f"missing .idx: {idx_path}")
            if verify_checksums and sha256_file(idx_path) != first["idx_sha256"]:
                raise ValueError(f"corrupted .idx checksum: {idx_path}")
            index = read_json(idx_path)
            entries = index.get("scenes", [])
            by_scene = {entry["scene_id"]: entry for entry in entries}
            if len(by_scene) != len(entries):
                raise ValueError(f"duplicate scene in .idx: {idx_path}")
            for row in rows:
                entry = by_scene.get(row["scene_id"])
                if entry is None:
                    raise ValueError(f"scene missing from .idx: {row['scene_id']}")
                if int(entry["offset"]) != int(row["sample_offset"]) or int(entry["length"]) != int(row["sample_length"]):
                    raise ValueError(f"global/.idx offset mismatch: {row['scene_id']}")
                self._index_entries[(row["idx_path"], row["scene_id"])] = entry
                tar_path = row["tar_path"]
                if verify_checksums and tar_path not in verified_tar:
                    path = self._runtime_archive_path(tar_path)
                    if not path.is_file() or sha256_file(path) != row["tar_sha256"]:
                        raise ValueError(f"corrupted tar checksum: {path}")
                    verified_tar.add(tar_path)

    def __len__(self) -> int:
        return len(self.rows)

    def position_for_scene(self, scene_id: str) -> int:
        if scene_id not in self.scene_to_position:
            raise KeyError(f"scene ID is absent from requested split: {scene_id}")
        return self.scene_to_position[scene_id]

    def get_by_scene_id(self, scene_id: str) -> dict[str, Any]:
        return self[self.position_for_scene(scene_id)]

    def _validate_tensor_contract(
        self, scene_id: str, groups: dict[str, dict[str, torch.Tensor]], n: int, e: int, c: int
    ) -> None:
        dtype_map = {
            "float32": torch.float32, "float64": torch.float64, "int64": torch.int64,
            "int32": torch.int32, "uint8": torch.uint8,
        }
        entities = groups["entities"]
        dimensions = {
            "N": n, "E": e, "C": c,
            "NB": entities["building_row_index"].numel(),
            "NR": entities["road_row_index"].numel(),
            "NP": entities["poi_row_index"].numel(), "N_plus_1": n + 1,
            "TN": groups["topology"]["node_incident_road_count"].numel(),
        }
        for group_name, tensor_specs in self.tensor_contract["tensor"]["safetensors"].items():
            tensors = groups[group_name]
            if set(tensors) != set(tensor_specs):
                raise ValueError(f"tensor key mismatch: {scene_id}:{group_name}")
            for key, spec in tensor_specs.items():
                tensor = tensors[key]
                if tensor.dtype != dtype_map[spec["dtype"]] or tensor.ndim != len(spec["shape"]):
                    raise ValueError(f"tensor dtype/rank mismatch: {scene_id}:{group_name}:{key}")
                for axis, expected in enumerate(spec["shape"]):
                    if isinstance(expected, int) and tensor.shape[axis] != expected:
                        raise ValueError(f"tensor shape mismatch: {scene_id}:{group_name}:{key}")
                    if expected in dimensions and tensor.shape[axis] != dimensions[expected]:
                        raise ValueError(f"tensor shape mismatch: {scene_id}:{group_name}:{key}")
                if tensor.is_floating_point() and not torch.isfinite(tensor).all():
                    raise ValueError(f"non-finite tensor: {scene_id}:{group_name}:{key}")

        if not torch.equal(entities["local_entity_id"], torch.arange(n, dtype=torch.int64)):
            raise ValueError(f"local entity order mismatch: {scene_id}")
        for prefix, entity_code, attribute_group in (("building", 0, "B"), ("road", 1, "R"), ("poi", 2, "P")):
            row_index = entities[f"{prefix}_row_index"]
            expected_rows = torch.nonzero(entities["entity_type"] == entity_code).flatten()
            if not torch.equal(row_index, expected_rows):
                raise ValueError(f"type row index mismatch: {scene_id}:{prefix}")
            category = entities[f"{prefix}_category"]
            attributes = self.tensor_contract["tensor"]["categorical_attributes"][attribute_group]
            for column, attribute in enumerate(attributes):
                values = category[:, column]
                if values.numel() and (int(values.min()) < 0 or int(values.max()) > self.category_max_index[attribute]):
                    raise ValueError(f"categorical index out of range: {scene_id}:{attribute}")
                forbidden = self.category_mask_index.get(attribute, set())
                if forbidden and any(torch.any(values == value).item() for value in forbidden):
                    raise ValueError(f"raw MASK category is forbidden: {scene_id}:{attribute}")

        binary_keys = (
            ("entities", "object_dem_missing"), ("entities", "building_missing"),
            ("entities", "road_missing"), ("geometry", "geometry_available"),
            ("geometry", "ring_is_hole"), ("rasters", "landcover_valid_mask"),
            ("rasters", "dem_valid_mask"),
        )
        for group_name, key in binary_keys:
            values = groups[group_name][key]
            if values.numel() and not torch.all((values == 0) | (values == 1)):
                raise ValueError(f"non-binary mask: {scene_id}:{group_name}:{key}")
        relation_mask = groups["edges"]["relation_mask"]
        if relation_mask.numel() and (int(relation_mask.min()) < 1 or int(relation_mask.max()) > 31):
            raise ValueError(f"unknown/empty relation mask: {scene_id}")
        for key in ("entity_coordinate_offsets", "entity_component_offsets", "component_coordinate_offsets",
                    "entity_part_offsets", "part_coordinate_offsets", "entity_ring_offsets"):
            offsets = groups["geometry"][key]
            if offsets.numel() == 0 or int(offsets[0]) != 0 or torch.any(offsets[1:] < offsets[:-1]):
                raise ValueError(f"invalid geometry offsets: {scene_id}:{key}")
        if int(groups["geometry"]["entity_coordinate_offsets"][-1]) != c:
            raise ValueError(f"geometry coordinate offset terminal mismatch: {scene_id}")

    def _validate_tensor_contract_once(
        self, payload_identity: tuple[tuple[str, str, int], ...], scene_id: str,
        groups: dict[str, dict[str, torch.Tensor]], n: int, e: int, c: int,
    ) -> bool:
        if payload_identity in self._validated_tensor_payloads:
            return True
        self._validate_tensor_contract(scene_id, groups, n, e, c)
        self._validated_tensor_payloads.add(payload_identity)
        return False

    def __getitem__(self, position: int) -> dict[str, Any]:
        started = time.perf_counter()
        row = self.rows[position]
        scene_id = row["scene_id"]
        entry = self._index_entries[(row["idx_path"], scene_id)]
        members = entry.get("members", [])
        expected_names = [f"{scene_id}.{suffix}" for suffix in MEMBER_SUFFIXES]
        if [member.get("name") for member in members] != expected_names:
            raise ValueError(f"missing/duplicate/unexpected member: {scene_id}")
        payloads: dict[str, bytes] = {}
        archive_path = self._runtime_archive_path(row["tar_path"])
        opened = time.perf_counter()
        cache_hit = False
        if self.persistent_archive_handles:
            stream, cache_hit = self._archive_stream(archive_path)
            open_finished = time.perf_counter()
            for member, expected_name in zip(members, expected_names):
                payloads[expected_name] = read_indexed_member(stream, member, expected_name)
        else:
            with archive_path.open("rb") as stream:
                open_finished = time.perf_counter()
                for member, expected_name in zip(members, expected_names):
                    payloads[expected_name] = read_indexed_member(stream, member, expected_name)
        read_finished = time.perf_counter()
        try:
            meta = json.loads(payloads[f"{scene_id}.meta.json"])
            if self.diagnostic_timing:
                groups = {}; safetensors_decode_seconds = 0.0; numpy_copy_seconds = 0.0
                for group in ("entities", "geometry", "edges", "topology", "rasters"):
                    phase_started = time.perf_counter()
                    decoded_group = load_safetensors(payloads[f"{scene_id}.{group}.safetensors"])
                    safetensors_decode_seconds += time.perf_counter() - phase_started
                    phase_started = time.perf_counter()
                    groups[group] = numpy_group_to_torch(decoded_group)
                    numpy_copy_seconds += time.perf_counter() - phase_started
            else:
                groups = {
                    group: numpy_group_to_torch(load_safetensors(payloads[f"{scene_id}.{group}.safetensors"]))
                    for group in ("entities", "geometry", "edges", "topology", "rasters")
                }
        except Exception as error:
            raise ValueError(f"corrupted scene payload: {scene_id}") from error
        decoded = time.perf_counter()
        if meta["scene_id"] != scene_id or meta["split"] != row["split"]:
            raise ValueError(f"scene metadata split/index mismatch: {scene_id}")
        entities, geometry, edges, topology, rasters = (groups[key] for key in ("entities", "geometry", "edges", "topology", "rasters"))
        n, e, c = int(row["node_count"]), int(row["ordered_edge_count"]), int(row["coordinate_count"])
        payload_identity = tuple(
            (str(member["name"]), str(member["sha256"]), int(member["payload_bytes"]))
            for member in members if str(member["name"]).endswith(".safetensors")
        )
        tensor_contract_cache_hit = self._validate_tensor_contract_once(
            payload_identity, scene_id, groups, n, e, c
        )
        if entities["local_entity_id"].shape != (n,) or edges["edge_index"].shape != (2, e) or geometry["coordinates_xy"].shape != (c, 2):
            raise ValueError(f"tensor count/shape mismatch: {scene_id}")
        if e and (int(edges["edge_index"].min()) < 0 or int(edges["edge_index"].max()) >= n):
            raise ValueError(f"dangling scene-local edge: {scene_id}")
        topology_node_count = topology["node_incident_road_count"].numel()
        endpoint_index = topology["road_endpoint_node_index"]
        if endpoint_index.numel() and (int(endpoint_index.min()) < 0 or int(endpoint_index.max()) >= topology_node_count):
            raise ValueError(f"road topology endpoint index out of range: {scene_id}")
        if topology["road_endpoint_retained"].numel() and int(topology["road_endpoint_retained"].max()) > 1:
            raise ValueError(f"road topology endpoint-retained range mismatch: {scene_id}")
        if bool(row["empty_edge"]) != (e == 0 and edges["relation_mask"].shape == (0,)):
            raise ValueError(f"empty-edge shape mismatch: {scene_id}")
        scientific_reference = {
            "coordinates_absolute_xy_5186": geometry.pop("coordinates_absolute_xy_5186"),
            "reference_center_absolute_xy_5186": geometry.pop("reference_center_absolute_xy_5186"),
            "building_observed_area_m2_reference": geometry.pop("building_observed_area_m2_reference"),
            "geometry_type": geometry["geometry_type"],
            **{key: geometry[key] for key in (
                "entity_coordinate_offsets", "entity_component_offsets", "component_coordinate_offsets",
                "entity_part_offsets", "part_coordinate_offsets", "entity_ring_offsets",
                "ring_component_index", "ring_coordinate_start", "ring_coordinate_end", "ring_is_hole",
            )},
        }
        geometry["coordinates_xy_m"] = restore_geometry_coordinates(
            geometry.pop("coordinates_xy"), self.geometry_scale_to_m
        )
        result = {
            "scene_id": scene_id, "split": row["split"], "global_index": int(row["global_order"]),
            "split_local_index": int(row["split_local_order"]), "meta": meta,
            "entities": entities, "geometry": geometry, "scientific_reference": scientific_reference,
            "edges": edges, "topology": topology, "rasters": rasters,
            "resources": {
                "nodes": n, "ordered_edges": e, "coordinates": c,
                "actual_payload_bytes": int(row["actual_payload_bytes"]),
            },
            "units": {
                "relative_position": "meter", "intrinsic_geometry": "meter",
                "scientific_reference": "absolute_float64_EPSG:5186",
                "crs": meta["crs"], "geometry_storage_scale_to_m": self.geometry_scale_to_m,
            },
        }
        if self.diagnostic_timing:
            result["_diagnostic_timing"] = {
                "archive_open_seconds": open_finished - opened if not cache_hit else 0.0,
                "archive_read_seconds": read_finished - open_finished,
                "decode_seconds": decoded - read_finished,
                "safetensors_decode_seconds": safetensors_decode_seconds,
                "numpy_torch_copy_seconds": numpy_copy_seconds,
                "validation_seconds": time.perf_counter() - decoded,
                "base_total_seconds": time.perf_counter() - started,
                "archive_handle_cache_hit": int(cache_hit),
                "tensor_contract_cache_hit": int(tensor_contract_cache_hit),
                "archive_path": str(archive_path),
            }
        return result


class DeterministicBudgetBatchSampler(Sampler[list[int]]):
    def __init__(
        self,
        rows: Sequence[dict[str, Any]],
        budgets: dict[str, int],
        shuffle: bool = False,
        seed: int = 0,
        epoch: int = 0,
    ) -> None:
        self.rows = rows
        self.budgets = {key: int(value) for key, value in budgets.items()}
        if set(self.budgets) != set(RESOURCE_COLUMNS) or any(value <= 0 for value in self.budgets.values()):
            raise ValueError("all five positive hard budgets are required")
        self.shuffle, self.seed, self.epoch = bool(shuffle), int(seed), int(epoch)

    def set_epoch(self, epoch: int) -> None:
        self.epoch = int(epoch)

    def ordered_indices(self) -> list[int]:
        if not self.shuffle:
            return list(range(len(self.rows)))
        rng = np.random.Generator(np.random.PCG64(self.seed + self.epoch))
        return rng.permutation(len(self.rows)).tolist()

    def _cost(self, row: dict[str, Any]) -> dict[str, int]:
        return {key: 1 if column is None else int(row[column]) for key, column in RESOURCE_COLUMNS.items()}

    def batches(self) -> list[list[int]]:
        result: list[list[int]] = []
        current: list[int] = []
        load = {key: 0 for key in self.budgets}
        for index in self.ordered_indices():
            cost = self._cost(self.rows[index])
            exceeds = any(load[key] + cost[key] > self.budgets[key] for key in self.budgets)
            if current and exceeds:
                result.append(current)
                current, load = [], {key: 0 for key in self.budgets}
            current.append(index)
            for key in load:
                load[key] += cost[key]
            if any(cost[key] > self.budgets[key] for key in self.budgets):
                result.append(current)
                current, load = [], {key: 0 for key in self.budgets}
        if current:
            result.append(current)
        return result

    def __iter__(self) -> Iterator[list[int]]:
        return iter(self.batches())

    def __len__(self) -> int:
        return len(self.batches())


def _cat(samples: list[dict[str, Any]], group: str, key: str, dimension: int = 0) -> torch.Tensor:
    return torch.cat([sample[group][key] for sample in samples], dim=dimension)


def ragged_collate(samples: list[dict[str, Any]], budgets: dict[str, int] | None = None) -> dict[str, Any]:
    if not samples:
        raise ValueError("cannot collate an empty sample list")
    node_counts = [sample["resources"]["nodes"] for sample in samples]
    edge_counts = [sample["resources"]["ordered_edges"] for sample in samples]
    coordinate_counts = [sample["resources"]["coordinates"] for sample in samples]
    scene_ptr = torch.tensor([0, *np.cumsum(node_counts).tolist()], dtype=torch.int64)
    edge_ptr = torch.tensor([0, *np.cumsum(edge_counts).tolist()], dtype=torch.int64)
    coordinate_ptr = torch.tensor([0, *np.cumsum(coordinate_counts).tolist()], dtype=torch.int64)
    part_counts = [sample["geometry"]["part_coordinate_offsets"].numel() - 1 for sample in samples]
    ring_counts = [sample["geometry"]["ring_is_hole"].numel() for sample in samples]
    part_ptr = torch.tensor([0, *np.cumsum(part_counts).tolist()], dtype=torch.int64)
    ring_ptr = torch.tensor([0, *np.cumsum(ring_counts).tolist()], dtype=torch.int64)
    topology_node_counts = [sample["topology"]["node_incident_road_count"].numel() for sample in samples]
    topology_node_ptr = torch.tensor([0, *np.cumsum(topology_node_counts).tolist()], dtype=torch.int64)

    entities: dict[str, torch.Tensor] = {}
    simple_entity_keys = ("local_entity_id", "entity_type", "relative_position_m", "object_raster", "object_dem_missing")
    for key in simple_entity_keys:
        entities[key] = _cat(samples, "entities", key)
    for prefix in ("building", "road", "poi"):
        row_key = f"{prefix}_row_index"
        entities[row_key] = torch.cat([
            sample["entities"][row_key] + scene_ptr[index] for index, sample in enumerate(samples)
        ])
        suffixes = ("category", "numerical", "missing") if prefix != "poi" else ("category",)
        for suffix in suffixes:
            key = f"{prefix}_{suffix}"
            entities[key] = _cat(samples, "entities", key)

    geometry: dict[str, torch.Tensor] = {
        "coordinates_xy_m": _cat(samples, "geometry", "coordinates_xy_m"),
        "geometry_type": _cat(samples, "geometry", "geometry_type"),
        "geometry_available": _cat(samples, "geometry", "geometry_available"),
    }
    for key in ("entity_coordinate_offsets",):
        geometry[key] = torch.cat([
            samples[0]["geometry"][key][:1],
            *[sample["geometry"][key][1:] + coordinate_ptr[index] for index, sample in enumerate(samples)],
        ])
    for key in ("entity_part_offsets", "entity_component_offsets"):
        geometry[key] = torch.cat([
            samples[0]["geometry"][key][:1],
            *[sample["geometry"][key][1:] + part_ptr[index] for index, sample in enumerate(samples)],
        ])
    for key in ("part_coordinate_offsets", "component_coordinate_offsets"):
        geometry[key] = torch.cat([
            samples[0]["geometry"][key][:1],
            *[sample["geometry"][key][1:] + coordinate_ptr[index] for index, sample in enumerate(samples)],
        ])
    geometry["entity_ring_offsets"] = torch.cat([
        samples[0]["geometry"]["entity_ring_offsets"][:1],
        *[sample["geometry"]["entity_ring_offsets"][1:] + ring_ptr[index] for index, sample in enumerate(samples)],
    ])
    geometry["ring_component_index"] = torch.cat([
        sample["geometry"]["ring_component_index"] + part_ptr[index] for index, sample in enumerate(samples)
    ])
    for key in ("ring_coordinate_start", "ring_coordinate_end"):
        geometry[key] = torch.cat([
            sample["geometry"][key] + coordinate_ptr[index] for index, sample in enumerate(samples)
        ])
    geometry["ring_is_hole"] = _cat(samples, "geometry", "ring_is_hole")

    scientific_reference: dict[str, torch.Tensor] = {
        "coordinates_absolute_xy_5186": _cat(samples, "scientific_reference", "coordinates_absolute_xy_5186"),
        "reference_center_absolute_xy_5186": _cat(samples, "scientific_reference", "reference_center_absolute_xy_5186"),
        "building_observed_area_m2_reference": _cat(samples, "scientific_reference", "building_observed_area_m2_reference"),
        "geometry_type": _cat(samples, "scientific_reference", "geometry_type"),
    }
    scientific_reference["entity_coordinate_offsets"] = torch.cat([
        samples[0]["scientific_reference"]["entity_coordinate_offsets"][:1],
        *[sample["scientific_reference"]["entity_coordinate_offsets"][1:] + coordinate_ptr[index]
          for index, sample in enumerate(samples)],
    ])
    for key in ("entity_part_offsets", "entity_component_offsets"):
        scientific_reference[key] = torch.cat([
            samples[0]["scientific_reference"][key][:1],
            *[sample["scientific_reference"][key][1:] + part_ptr[index]
              for index, sample in enumerate(samples)],
        ])
    for key in ("part_coordinate_offsets", "component_coordinate_offsets"):
        scientific_reference[key] = torch.cat([
            samples[0]["scientific_reference"][key][:1],
            *[sample["scientific_reference"][key][1:] + coordinate_ptr[index]
              for index, sample in enumerate(samples)],
        ])
    scientific_reference["entity_ring_offsets"] = torch.cat([
        samples[0]["scientific_reference"]["entity_ring_offsets"][:1],
        *[sample["scientific_reference"]["entity_ring_offsets"][1:] + ring_ptr[index]
          for index, sample in enumerate(samples)],
    ])
    scientific_reference["ring_component_index"] = torch.cat([
        sample["scientific_reference"]["ring_component_index"] + part_ptr[index]
        for index, sample in enumerate(samples)
    ])
    for key in ("ring_coordinate_start", "ring_coordinate_end"):
        scientific_reference[key] = torch.cat([
            sample["scientific_reference"][key] + coordinate_ptr[index]
            for index, sample in enumerate(samples)
        ])
    scientific_reference["ring_is_hole"] = _cat(samples, "scientific_reference", "ring_is_hole")

    edges = {
        "edge_index": torch.cat([
            sample["edges"]["edge_index"] + scene_ptr[index] for index, sample in enumerate(samples)
        ], dim=1),
        "relation_mask": _cat(samples, "edges", "relation_mask"),
    }
    topology = {
        "road_endpoint_node_index": torch.cat([
            sample["topology"]["road_endpoint_node_index"] + topology_node_ptr[index]
            for index, sample in enumerate(samples)
        ]),
        "road_endpoint_retained": _cat(samples, "topology", "road_endpoint_retained"),
        "node_incident_road_count": _cat(samples, "topology", "node_incident_road_count"),
        "node_state": _cat(samples, "topology", "node_state"),
        "node_xy_5186": _cat(samples, "topology", "node_xy_5186"),
    }
    rasters = {
        key: torch.stack([sample["rasters"][key] for sample in samples])
        for key in samples[0]["rasters"]
    }
    batch_resources = {
        "scenes": len(samples), "nodes": sum(node_counts), "ordered_edges": sum(edge_counts),
        "coordinates": sum(coordinate_counts),
        "actual_payload_bytes": sum(sample["resources"]["actual_payload_bytes"] for sample in samples),
    }
    oversize = bool(
        budgets and len(samples) == 1 and any(batch_resources[key] > int(budgets[key]) for key in budgets)
    )
    return {
        "scene_ids": [sample["scene_id"] for sample in samples], "splits": [sample["split"] for sample in samples],
        "global_indices": torch.tensor([sample["global_index"] for sample in samples], dtype=torch.int64),
        "split_local_indices": torch.tensor([sample["split_local_index"] for sample in samples], dtype=torch.int64),
        "scene_ptr": scene_ptr, "edge_ptr": edge_ptr, "coordinate_ptr": coordinate_ptr,
        "part_ptr": part_ptr, "ring_ptr": ring_ptr, "topology_node_ptr": topology_node_ptr,
        "building_ptr": torch.tensor([0, *np.cumsum([sample["entities"]["building_row_index"].numel() for sample in samples]).tolist()], dtype=torch.int64),
        "entities": entities, "geometry": geometry, "scientific_reference": scientific_reference,
        "edges": edges, "topology": topology,
        "rasters": rasters, "resources": batch_resources,
        "oversize_singleton": oversize,
        "entity_scene_index": torch.repeat_interleave(torch.arange(len(samples), dtype=torch.int64), torch.tensor(node_counts)),
        "entity_local_index": entities["local_entity_id"].clone(),
        "units": {"relative_position": "meter", "intrinsic_geometry": "meter"},
    }


def make_dataloader(
    dataset: AcceptedPrototypeDataset,
    budgets: dict[str, int],
    workers: int,
    shuffle: bool,
    seed: int,
    epoch: int = 0,
    pin_memory: bool = False,
    persistent_workers: bool = False,
    prefetch_factor: int = 2,
) -> tuple[DataLoader, DeterministicBudgetBatchSampler]:
    if workers:
        torch.multiprocessing.set_sharing_strategy("file_system")
    sampler = DeterministicBudgetBatchSampler(dataset.rows, budgets, shuffle=shuffle, seed=seed, epoch=epoch)
    kwargs: dict[str, Any] = {
        "dataset": dataset, "batch_sampler": sampler, "num_workers": int(workers),
        "collate_fn": partial(ragged_collate, budgets=budgets), "pin_memory": bool(pin_memory),
        "worker_init_fn": initialize_loader_worker if workers else None,
    }
    if workers:
        kwargs.update(persistent_workers=bool(persistent_workers), prefetch_factor=int(prefetch_factor))
    loader = DataLoader(**kwargs)
    return loader, sampler


def update_digest(digest: Any, value: Any) -> None:
    if isinstance(value, torch.Tensor):
        array = value.detach().cpu().contiguous().numpy()
        digest.update(str(array.dtype).encode()); digest.update(str(array.shape).encode()); digest.update(array.tobytes())
    elif isinstance(value, dict):
        for key in sorted(value):
            digest.update(key.encode()); update_digest(digest, value[key])
    elif isinstance(value, (list, tuple)):
        for item in value:
            update_digest(digest, item)
    elif isinstance(value, (str, int, float, bool)) or value is None:
        digest.update(repr(value).encode())


def logical_batch_digest(batch: dict[str, Any]) -> str:
    digest = hashlib.sha256()
    update_digest(digest, batch)
    return digest.hexdigest()
