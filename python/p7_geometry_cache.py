"""Immutable P6-layout-v3 geometry features for deterministic P7 execution."""

from __future__ import annotations

import hashlib
import json
import os
from collections import OrderedDict
from pathlib import Path
from typing import Any, Iterable, Sequence

import torch

from canonical_config import canonical_json_bytes
from p6_data import GEOMETRY_LAYOUT_VERSION, validate_geometry_layout

CACHE_SCHEMA_VERSION = "3.0.0"


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def tensor_sha256(value: torch.Tensor) -> str:
    return hashlib.sha256(value.detach().cpu().contiguous().numpy().tobytes()).hexdigest()


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def cache_record(sample: dict[str, Any], parents: dict[str, Any], geometry_config: dict[str, Any],
                 implementation_sha256: str, role: str) -> dict[str, Any]:
    validate_geometry_layout(sample)
    geometry = sample["geometry"]
    order = torch.stack((sample["entities"]["local_entity_id"].to(torch.int64),
                         sample["entities"]["entity_type"].to(torch.int64)), 1)
    identity = {
        "cache_schema_version": CACHE_SCHEMA_VERSION,
        "geometry_layout_version": GEOMETRY_LAYOUT_VERSION,
        "role": role,
        "scene_id": sample["scene_id"],
        "view_id": sample["view_id"],
        "profile_id": sample["profile"],
        "positive_scene_id": sample["positive_scene_id"],
        "p4_bank_id": parents["p4_master_bank_id"],
        "p4_logical_index_id": parents["p4_logical_index_id"],
        "p6_model_authority_id": parents["p6_model_authority_id"],
        "p6_preprocessing_id": parents["p6_preprocessing_id"],
        "p6_aggregate_acceptance_id": parents["p6_aggregate_acceptance_id"],
        "lineage_sha256": canonical_digest(sample["lineage"]),
        "part_content_sha256": tensor_sha256(geometry["part_coordinates_xy_m_scientific"]),
        "ring_content_sha256": tensor_sha256(geometry["ring_coordinates_xy_m_scientific"]),
        "entity_order_sha256": tensor_sha256(order),
        "geometry_config_sha256": canonical_digest(geometry_config),
        "feature_implementation_sha256": implementation_sha256,
        "input_dtype": str(geometry["part_coordinates_xy_m"].dtype),
        "output_dtype": "torch.float32",
    }
    return {"cache_schema_version": CACHE_SCHEMA_VERSION,
            "geometry_layout_version": GEOMETRY_LAYOUT_VERSION,
            "cache_key": canonical_digest(identity), "identity": identity,
            "lookup_key": f"{role}\0{sample['scene_id']}\0{sample['view_id']}"}


def feature_manifest(record: dict[str, Any], magnitude: torch.Tensor, phase: torch.Tensor) -> dict[str, Any]:
    return {
        **record,
        "magnitude": {"dtype": str(magnitude.dtype), "shape": list(magnitude.shape),
                      "sha256": tensor_sha256(magnitude)},
        "phase": {"dtype": str(phase.dtype), "shape": list(phase.shape),
                  "sha256": tensor_sha256(phase)},
    }


def validate_payload(record: dict[str, Any], payload: dict[str, Any]) -> tuple[torch.Tensor, torch.Tensor]:
    manifest = payload.get("manifest")
    if not isinstance(manifest, dict) or manifest.get("cache_schema_version") != CACHE_SCHEMA_VERSION:
        raise ValueError("incompatible geometry-cache schema")
    if manifest.get("geometry_layout_version") != GEOMETRY_LAYOUT_VERSION:
        raise ValueError("incompatible geometry-cache layout")
    if any(manifest.get(key) != record.get(key) for key in ("cache_key", "identity", "lookup_key")):
        raise ValueError("geometry-cache identity mismatch")
    magnitude, phase = payload["magnitude"].contiguous(), payload["phase"].contiguous()
    for name, tensor in (("magnitude", magnitude), ("phase", phase)):
        expected = manifest[name]
        if (str(tensor.dtype) != expected["dtype"] or list(tensor.shape) != expected["shape"]
                or tensor_sha256(tensor) != expected["sha256"]):
            raise ValueError(f"geometry-cache {name} corruption")
    return magnitude, phase


class GeometryCacheWriter:
    def __init__(self, stage: str | Path) -> None:
        self.stage = Path(stage)
        self.entries = self.stage / "entries"
        self.entries.mkdir(parents=True, exist_ok=True)

    def put(self, record: dict[str, Any], magnitude: torch.Tensor, phase: torch.Tensor) -> Path:
        magnitude = magnitude.detach().cpu().contiguous(); phase = phase.detach().cpu().contiguous()
        manifest = feature_manifest(record, magnitude, phase)
        payload = {"manifest": manifest, "magnitude": magnitude, "phase": phase}
        path = self.entries / f"{record['cache_key']}.pt"
        temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
        torch.save(payload, temporary)
        if path.exists():
            existing = torch.load(path, map_location="cpu", weights_only=False)
            left = validate_payload(record, existing)
            if not torch.equal(left[0], magnitude) or not torch.equal(left[1], phase):
                temporary.unlink(missing_ok=True)
                raise FileExistsError("geometry-cache same-ID/different-bytes collision")
        else:
            os.replace(temporary, path)
        temporary.unlink(missing_ok=True)
        validate_payload(record, torch.load(path, map_location="cpu", weights_only=False))
        return path

    def finalize(self, authority_id: str, expected_records: Sequence[dict[str, Any]]) -> dict[str, Any]:
        rows = []
        by_key = {record["cache_key"]: record for record in expected_records}
        if len(by_key) != len(expected_records):
            raise ValueError("duplicate geometry-cache key")
        lookup = {record["lookup_key"] for record in expected_records}
        if len(lookup) != len(expected_records):
            raise ValueError("duplicate geometry-cache lookup identity")
        raw_bytes = disk_bytes = 0
        for key in sorted(by_key):
            record = by_key[key]; path = self.entries / f"{key}.pt"
            if not path.is_file():
                raise ValueError(f"missing geometry-cache entry: {key}")
            payload = torch.load(path, map_location="cpu", weights_only=False)
            magnitude, phase = validate_payload(record, payload)
            size = path.stat().st_size; disk_bytes += size
            raw = magnitude.numel() * magnitude.element_size() + phase.numel() * phase.element_size()
            raw_bytes += raw
            rows.append({**payload["manifest"], "relative_path": f"entries/{key}.pt",
                         "payload_size_bytes": size, "payload_sha256": sha256_file(path),
                         "raw_tensor_bytes": raw})
        scientific = {"schema_version": CACHE_SCHEMA_VERSION, "status": "PASS",
                      "geometry_layout_version": GEOMETRY_LAYOUT_VERSION,
                      "training_authority_id": authority_id, "entry_count": len(rows),
                      "total_raw_tensor_bytes": raw_bytes, "entries": rows}
        scientific["content_sha256"] = canonical_digest(scientific)
        scientific["cache_id"] = "p7gc_" + scientific["content_sha256"][:24]
        scientific["total_disk_bytes"] = disk_bytes
        path = self.stage / "geometry_cache_manifest.json"
        path.write_bytes(canonical_json_bytes(scientific))
        (self.stage / "COMPLETE.json").write_bytes(canonical_json_bytes({
            "cache_id": scientific["cache_id"], "manifest_sha256": sha256_file(path)
        }))
        return scientific


class GeometryCacheReader:
    def __init__(self, manifest_path: str | Path, maximum_memory_bytes: int = 4 * 1024**3) -> None:
        self.manifest_path = Path(manifest_path)
        self.root = self.manifest_path.parent
        self.manifest = json.loads(self.manifest_path.read_text())
        complete = json.loads((self.root / "COMPLETE.json").read_text())
        scientific = {key: value for key, value in self.manifest.items()
                      if key not in {"content_sha256", "cache_id", "total_disk_bytes", "runtime"}}
        if (self.manifest.get("status") != "PASS"
                or self.manifest.get("schema_version") != CACHE_SCHEMA_VERSION
                or self.manifest.get("geometry_layout_version") != GEOMETRY_LAYOUT_VERSION
                or self.manifest.get("content_sha256") != canonical_digest(scientific)
                or self.manifest.get("cache_id") != "p7gc_" + canonical_digest(scientific)[:24]
                or complete.get("cache_id") != self.manifest.get("cache_id")
                or complete.get("manifest_sha256") != sha256_file(self.manifest_path)):
            raise ValueError("incomplete or incompatible geometry cache")
        self.index = {row["lookup_key"]: row for row in self.manifest["entries"]}
        if len(self.index) != int(self.manifest["entry_count"]):
            raise ValueError("geometry-cache index collision")
        self.maximum_memory_bytes = int(maximum_memory_bytes)
        self.memory: OrderedDict[str, tuple[torch.Tensor, torch.Tensor, int]] = OrderedDict()
        self.memory_bytes = self.hits = self.misses = self.evictions = 0

    def _get(self, role: str, scene_id: str, view_id: str) -> tuple[torch.Tensor, torch.Tensor]:
        lookup = f"{role}\0{scene_id}\0{view_id}"
        if lookup in self.memory:
            value = self.memory.pop(lookup); self.memory[lookup] = value; self.hits += 1
            return value[0], value[1]
        row = self.index.get(lookup)
        if row is None:
            raise KeyError(f"geometry-cache miss: {lookup}")
        path = self.root / row["relative_path"]
        if path.stat().st_size != row["payload_size_bytes"] or sha256_file(path) != row["payload_sha256"]:
            raise ValueError("geometry-cache payload checksum mismatch")
        payload = torch.load(path, map_location="cpu", mmap=True, weights_only=False)
        magnitude, phase = validate_payload(row, payload)
        size = int(row["raw_tensor_bytes"]); self.misses += 1
        while self.memory and self.memory_bytes + size > self.maximum_memory_bytes:
            _, (_, _, removed) = self.memory.popitem(last=False); self.memory_bytes -= removed; self.evictions += 1
        if size <= self.maximum_memory_bytes:
            self.memory[lookup] = (magnitude, phase, size); self.memory_bytes += size
        return magnitude, phase

    def batch(self, batch: dict[str, Any], role: str, device: torch.device) -> tuple[torch.Tensor, torch.Tensor]:
        values = [self._get(role, scene, str(view))
                  for scene, view in zip(batch["scene_ids"], batch["view_ids"], strict=True)]
        return (torch.cat([value[0] for value in values]).to(device),
                torch.cat([value[1] for value in values]).to(device))

    def stats(self) -> dict[str, int]:
        return {"hits": self.hits, "misses": self.misses, "evictions": self.evictions,
                "resident_entries": len(self.memory), "resident_bytes": self.memory_bytes}
