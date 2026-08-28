"""Read accepted P3/P4 artifacts and render a standalone visual QC inspector."""

from __future__ import annotations

import hashlib
import io
import json
import math
import os
import resource
import tarfile
import tempfile
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pyarrow.parquet as pq
import shapely
import yaml
import zarr

EXPECTED = {
    "p3_cache": "oscache_c89fa07e3d6cb1819a7994a6",
    "p3_acceptance": "osca_a55d2c02c3737c5f5557092a",
    "p4_bank": "augbank_a470cb156612cff12fb316fc",
    "p4_acceptance": "aba_b6ee67e0d798020a6c418c05",
    "p4_index": "abi_f9ff792612ca86f486576491",
    "supplement": "p4-determinism-v1",
}
PROFILES = ("weak_0.5x", "main_1.0x", "strong_2.0x")
PROFILE_LABELS = {
    "original": "Original spatial scene",
    "weak_0.5x": "Weak augmentation (0.5x)",
    "main_1.0x": "Main augmentation (1.0x)",
    "strong_2.0x": "Strong augmentation (2.0x)",
}
TABLES = (
    "candidates", "removals", "geometry", "fallbacks", "attributes",
    "raster", "relation_delta", "topology", "absorption",
)


class InspectorError(RuntimeError):
    """A rejected artifact, lookup, or output contract."""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InspectorError(f"cannot read JSON: {path.name}: {exc}") from exc


def _safe_extract(archive: tarfile.TarFile, destination: Path) -> None:
    root = destination.resolve()
    for member in archive.getmembers():
        target = (destination / member.name).resolve()
        if target != root and root not in target.parents:
            raise InspectorError(f"archive path escape: {member.name}")
    archive.extractall(destination, filter="data")


def _normalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _normalize(item) for key, item in sorted(value.items(), key=lambda x: str(x[0]))}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).hex()
    if isinstance(value, np.generic):
        return _normalize(value.item())
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def _coordinates(geometry: Any) -> dict[str, Any]:
    mapping = shapely.geometry.mapping(geometry)
    return {"type": mapping["type"], "coordinates": _normalize(mapping["coordinates"])}


def _resolve_scene_root(repository: Path) -> Path:
    override = os.environ.get("FUSE_REDUCED_SCENE_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    config = yaml.safe_load((repository / "config/p4_deterministic_augmentation.yml").read_text(encoding="utf-8"))
    publication = Path(config["publication_root"])
    return publication.parent


class AcceptedArtifacts:
    """Index-backed, checksum-validating reader for accepted immutable artifacts."""

    def __init__(
        self,
        repository: Path,
        original_cache_root: Path | None = None,
        augmentation_bank_root: Path | None = None,
        master_bank_id: str = EXPECTED["p4_bank"],
        logical_index_id: str = EXPECTED["p4_index"],
    ) -> None:
        reduced_root = _resolve_scene_root(repository)
        self.p3_root = (original_cache_root or reduced_root / "original_scene_cache" / EXPECTED["p3_cache"]).resolve()
        self.p4_root = (augmentation_bank_root or reduced_root / "augmentation_banks" / master_bank_id).resolve()
        self.master_bank_id = master_bank_id
        self.logical_index_id = logical_index_id
        self._load_manifests()

    def _load_manifests(self) -> None:
        p3_manifest_paths = list(self.p3_root.glob("manifests/original_scene_cache_manifest.json"))
        p3_acceptance_paths = list(self.p3_root.glob("acceptance/*/original_scene_dataset_acceptance.json"))
        p4_acceptance_paths = list(self.p4_root.glob("acceptance/*/augmentation_bank_acceptance.json"))
        index_json_paths = list(self.p4_root.glob("acceptance/*/effective_bank_index.json"))
        index_parquet_paths = list(self.p4_root.glob("acceptance/*/effective_bank_index.parquet"))
        p3_index_paths = list(self.p3_root.glob("index/*/scene_to_shard.parquet"))
        groups = (p3_manifest_paths, p3_acceptance_paths, p4_acceptance_paths, index_json_paths, index_parquet_paths, p3_index_paths)
        if any(len(paths) != 1 for paths in groups):
            raise InspectorError("accepted P3/P4 manifest or index resolution is ambiguous")
        self.p3_manifest = _json(p3_manifest_paths[0])
        self.p3_acceptance = _json(p3_acceptance_paths[0])
        self.p4_acceptance = _json(p4_acceptance_paths[0])
        self.index_manifest = _json(index_json_paths[0])
        self.index_parquet = index_parquet_paths[0]
        checks = (
            (self.p3_manifest.get("cache_id"), EXPECTED["p3_cache"], "P3 cache"),
            (self.p3_acceptance.get("acceptance_id"), EXPECTED["p3_acceptance"], "P3 acceptance"),
            (self.p4_acceptance.get("bank_id"), self.master_bank_id, "P4 bank"),
            (self.p4_acceptance.get("status"), "PASS", "P4 status"),
            (self.index_manifest.get("index_id"), self.logical_index_id, "logical index"),
        )
        for observed, expected, label in checks:
            if observed != expected:
                raise InspectorError(f"{label} mismatch: {observed!r} != {expected!r}")
        if self.p3_manifest.get("split_counts") != {"training": 2421, "validation": 400, "evaluation": 1600}:
            raise InspectorError("P3 scene population mismatch")
        if self.p4_acceptance.get("physical_candidate_count") != 116208:
            raise InspectorError("P4 physical candidate count mismatch")
        self.p3_rows = {row["scene_id"]: row for row in pq.read_table(p3_index_paths[0]).to_pylist()}
        index_table = pq.read_table(self.index_parquet, filters=[("requested_k", "=", 16)])
        self.logical_rows = {
            (row["profile_id"], row["scene_id"], int(row["master_view_id"])): row
            for row in index_table.to_pylist()
        }
        if len(self.logical_rows) != 116208:
            raise InspectorError("physical K16 index coverage mismatch")
        self.branch_by_scene: dict[tuple[str, str], tuple[Path, dict[str, Any]]] = {}
        for manifest_path in sorted(self.p4_root.glob("shards/*/*/branch_manifest.json")):
            manifest = _json(manifest_path)
            if manifest.get("bank_id") != self.master_bank_id or manifest.get("status") != "PASS":
                raise InspectorError(f"rejected P4 branch manifest: {manifest_path.name}")
            for scene_id in manifest["scene_ids"]:
                key = (manifest["profile_id"], scene_id)
                if key in self.branch_by_scene:
                    raise InspectorError(f"duplicate P4 scene/profile branch: {key}")
                self.branch_by_scene[key] = (manifest_path, manifest)
        if len(self.branch_by_scene) != 2421 * 3:
            raise InspectorError("P4 scene/profile branch coverage mismatch")

    def validate_scene_view(self, scene_id: str, view: int) -> None:
        if view < 0 or view > 15:
            raise InspectorError("master view ID must be in [0, 15]")
        p3 = self.p3_rows.get(scene_id)
        if p3 is None:
            raise InspectorError(f"unknown scene ID: {scene_id}")
        if any((profile, scene_id, view) not in self.logical_rows for profile in PROFILES):
            raise InspectorError(f"scene is not an accepted P4 training scene: {scene_id}")

    def p3_tar(self, scene_id: str, verify: bool = True) -> tuple[Path, dict[str, Any]]:
        row = self.p3_rows[scene_id]
        path = self.p3_root / "shards" / row["branch_id"] / row["payload_filename"]
        if not path.is_file():
            raise InspectorError(f"missing P3 shard: {row['branch_id']}")
        if verify and sha256_file(path) != row["payload_sha256"]:
            raise InspectorError(f"P3 shard checksum mismatch: {row['branch_id']}")
        return path, row

    def p4_tar(self, profile: str, scene_id: str, verify: bool = True) -> tuple[Path, dict[str, Any]]:
        manifest_path, manifest = self.branch_by_scene[(profile, scene_id)]
        path = manifest_path.parent / manifest["payload"]["filename"]
        if not path.is_file():
            raise InspectorError(f"missing P4 shard: {manifest['branch_id']}")
        if verify and sha256_file(path) != manifest["payload"]["sha256"]:
            raise InspectorError(f"P4 shard checksum mismatch: {manifest['branch_id']}")
        return path, manifest

    def scan_candidate_summaries(self) -> list[dict[str, Any]]:
        """Read only the small candidates member from each branch, never full payload tables."""
        rows: list[dict[str, Any]] = []
        for manifest_path in sorted(self.p4_root.glob("shards/*/*/branch_manifest.json")):
            manifest = _json(manifest_path)
            tar_path = manifest_path.parent / manifest["payload"]["filename"]
            with tarfile.open(tar_path) as archive:
                raw = archive.extractfile("candidates.parquet").read()
            member = next(item for item in manifest["members"] if item["path"] == "candidates.parquet")
            if sha256_bytes(raw) != member["sha256"]:
                raise InspectorError(f"candidate summary checksum mismatch: {manifest['branch_id']}")
            rows.extend(pq.read_table(io.BytesIO(raw)).to_pylist())
        if len(rows) != 116208:
            raise InspectorError("candidate summary coverage mismatch")
        return rows

    def select_qc_extremes(self, max_cases: int) -> list[dict[str, Any]]:
        if max_cases < 1:
            raise InspectorError("max cases must be positive")
        grouped: dict[tuple[str, int], dict[str, float]] = defaultdict(lambda: defaultdict(float))
        for row in self.scan_candidate_summaries():
            key = (row["scene_id"], int(row["master_view_id"]))
            metrics = grouped[key]
            metrics["geometry fallbacks"] += float(row["geometry_fallback_count"])
            metrics["absorbed donors"] += float(row["absorbed_donor_count"])
            metrics["direct removals"] += float(row["direct_removed_count"])
            metrics["cascade POI removals"] += float(row["cascade_removed_count"])
            metrics["geometry perturbations"] += float(row["geometry_override_count"])
            metrics["attribute perturbations"] += float(row["attribute_override_count"])
            metrics["LC changed cells"] += float(row["landcover_mask_count"])
            metrics["DEM perturbed cells"] += float(row["dem_noise_count"])
        for metrics in grouped.values():
            metrics["total activity"] = sum(metrics[name] for name in (
                "geometry fallbacks", "absorbed donors", "direct removals", "cascade POI removals",
                "geometry perturbations", "attribute perturbations", "LC changed cells",
            ))
        ordered_keys = sorted(grouped)
        total_values = sorted(grouped[key]["total activity"] for key in ordered_keys)
        median = total_values[len(total_values) // 2]
        objectives = [
            ("geometry fallbacks", "max"), ("absorbed donors", "max"),
            ("direct removals", "max"), ("cascade POI removals", "max"),
            ("geometry perturbations", "max"), ("attribute perturbations", "max"),
            ("LC changed cells", "max"), ("median activity", "median"),
            ("control-like activity", "min"),
        ]
        selected: list[dict[str, Any]] = []
        seen: set[tuple[str, int]] = set()
        for reason, mode in objectives:
            if len(selected) >= max_cases:
                break
            metric = "total activity" if mode in ("median", "min") else reason
            if mode == "max":
                ranked = sorted(ordered_keys, key=lambda key: (-grouped[key][metric], key[0], key[1]))
            elif mode == "median":
                ranked = sorted(ordered_keys, key=lambda key: (abs(grouped[key][metric] - median), key[0], key[1]))
            else:
                ranked = sorted(ordered_keys, key=lambda key: (grouped[key][metric], key[0], key[1]))
            key = next((item for item in ranked if item not in seen), None)
            if key is None:
                continue
            seen.add(key)
            selected.append({"scene_id": key[0], "master_view_id": key[1], "reason": reason, "metric_value": grouped[key][metric]})
        return selected


def _rows_from_tar(path: Path, names: Iterable[str], candidate_id: str) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    with tarfile.open(path) as archive:
        for name in names:
            raw = archive.extractfile(f"{name}.parquet").read()
            result[name] = pq.read_table(
                io.BytesIO(raw), filters=[("candidate_id", "=", candidate_id)]
            ).to_pylist()
    return result


def _original_scene(artifacts: AcceptedArtifacts, scene_id: str, temporary: Path) -> dict[str, Any]:
    tar_path, p3_index = artifacts.p3_tar(scene_id)
    extract = temporary / p3_index["branch_id"]
    if not extract.exists():
        extract.mkdir()
        with tarfile.open(tar_path) as archive:
            _safe_extract(archive, extract)
    entities: list[dict[str, Any]] = []
    entity_by_id: dict[int, dict[str, Any]] = {}
    fields = {
        "B": ("vector/building_observed.parquet", ("A9", "A11", "A14", "observed_area_m2", "observed_gross_floor_area_m2")),
        "R": ("vector/road_observed.parquet", ("LANES", "ROAD_RANK", "ROAD_TYPE", "observed_length_m")),
        "P": ("vector/poi_observed.parquet", tuple(f"CLASS_L{i}_CODE" for i in range(1, 7))),
    }
    for entity_type, (relative, attribute_names) in fields.items():
        table = pq.read_table(extract / relative, filters=[("scene_id", "=", scene_id)])
        for row in table.to_pylist():
            geometry = shapely.from_wkb(bytes(row["observed_geometry"]))
            local = int(row["local_entity_id"])
            record = {
                "id": local,
                "source_id": str(row["source_entity_id"]),
                "type": entity_type,
                "geometry": _coordinates(geometry),
                "area": float(geometry.area),
                "length": float(geometry.length),
                "attributes": {name: _normalize(row.get(name)) for name in attribute_names},
            }
            entities.append(record)
            entity_by_id[local] = record
    entities.sort(key=lambda item: item["id"])
    raster_index = pq.read_table(extract / "raster/scene_raster_index.parquet", filters=[("scene_id", "=", scene_id)]).to_pylist()
    if len(raster_index) != 1 or raster_index[0]["split"] != "training":
        raise InspectorError(f"scene is not training: {scene_id}")
    raster_row = raster_index[0]
    index = int(raster_row["zarr_index"])
    lc_group = zarr.open_group(str(extract / "raster/scene_landcover.zarr"), mode="r")
    dem_group = zarr.open_group(str(extract / "raster/scene_dem.zarr"), mode="r")
    fractions = np.asarray(lc_group["class_fraction"][index], dtype=np.float32)
    lc_mask = np.asarray(lc_group["valid_mask"][index], dtype=np.uint8)
    lc_codes = np.argmax(fractions, axis=0).astype(np.int16) + 1
    lc_codes[lc_mask == 0] = 0
    dem = np.asarray(dem_group["raw_mean_m"][index], dtype=np.float32)
    dem_mask = np.asarray(dem_group["valid_mask"][index], dtype=np.uint8)
    dem_values = [None if not dem_mask.flat[i] else float(dem.flat[i]) for i in range(dem.size)]
    bounds = [float(raster_row[key]) for key in ("xmin", "ymin", "xmax", "ymax")]
    return {
        "scene_id": scene_id,
        "split": "training",
        "bounds": bounds,
        "entities": entities,
        "entity_by_id": entity_by_id,
        "landcover": {"shape": [100, 100], "values": [int(x) for x in lc_codes.ravel()]},
        "dem": {"shape": [17, 17], "values": dem_values},
        "p3_branch_id": p3_index["branch_id"],
        "p3_payload_sha256": p3_index["payload_sha256"],
    }


def _candidate_slice_checksum(tables: dict[str, list[dict[str, Any]]]) -> str:
    normalized = {key: [_normalize(row) for row in value] for key, value in sorted(tables.items())}
    return sha256_bytes(canonical_json(normalized))


def _augmented_profile(
    artifacts: AcceptedArtifacts,
    original: dict[str, Any],
    profile: str,
    view: int,
    table_cache: dict[tuple[Path, str], dict[str, list[dict[str, Any]]]],
) -> dict[str, Any]:
    scene_id = original["scene_id"]
    index_row = artifacts.logical_rows[(profile, scene_id, view)]
    candidate_id = index_row["candidate_id"]
    tar_path, manifest = artifacts.p4_tar(profile, scene_id)
    cache_key = (tar_path, candidate_id)
    if cache_key not in table_cache:
        table_cache[cache_key] = _rows_from_tar(tar_path, TABLES, candidate_id)
    selected = table_cache[cache_key]
    if len(selected["candidates"]) != 1:
        raise InspectorError(f"candidate lookup failed: {candidate_id}")
    candidate = _normalize(selected["candidates"][0])
    removals = {int(row["local_entity_id"]): row["removal_role"] for row in selected["removals"]}
    absorption = [_normalize(row) for row in selected["absorption"]]
    receiver_ids = {int(row["receiver"]) for row in selected["absorption"] if row.get("status") == "ABSORBED" and row.get("receiver") is not None}
    geometry_changes: list[dict[str, Any]] = []
    for row in selected["geometry"]:
        local = int(row["local_entity_id"])
        if bool(row["changed_from_post_absorption"]) or bool(row["fallback"]) or local in receiver_ids:
            geometry = shapely.from_wkb(bytes(row["geometry_wkb"]))
            geometry_changes.append({
                "id": local,
                "geometry": _coordinates(geometry),
                "operation": row["geometry_operation"],
                "fallback": bool(row["fallback"]),
                "receiver": local in receiver_ids,
                "area": float(row["area_m2"]),
                "length": float(row["length_m"]),
                "accepted_attempt": _normalize(row["accepted_attempt"]),
            })
    attributes = []
    for row in selected["attributes"]:
        local = int(row["local_entity_id"])
        entity = original["entity_by_id"].get(local, {})
        attributes.append({
            "profile": profile, "master_view_id": view, "entity_type": entity.get("type", "Not recorded"),
            "entity_id": local, "operation": row["action"], "attribute_name": row["field"],
            "original_value": row["original"], "augmented_value": row["augmented"], "changed": True,
            "change_type": row["action"], "provenance_key": f"{candidate_id}:{local}:{row['field']}",
        })
    lc = list(original["landcover"]["values"])
    dem = list(original["dem"]["values"])
    for row in selected["raster"]:
        flat = int(row["flat_index"])
        if row["modality"] == "landcover":
            lc[flat] = -1
        elif row["modality"] == "dem":
            dem[flat] = _normalize(row["value"])
    relation_counts = json.loads(candidate["relation_counts_json"])
    fallback_ids = [int(row["local_entity_id"]) for row in selected["fallbacks"]]
    direct = sum(1 for role in removals.values() if role == "DIRECT")
    cascade = sum(1 for role in removals.values() if role == "CASCADE_POI")
    donors = sum(1 for role in removals.values() if role == "ABSORBED_ROAD")
    summary = {
        "changed_entities": len(set(item["entity_id"] for item in attributes) | set(item["id"] for item in geometry_changes) | set(removals)),
        "masked_fields": sum(item["change_type"] == "MASK" for item in attributes),
        "replaced_categorical_fields": sum(item["change_type"] == "REPLACE" for item in attributes),
        "lane_perturbations": sum(item["attribute_name"] == "LANES" for item in attributes),
        "unchanged_entities": int(candidate["retained_entity_count"]) - len(set(item["entity_id"] for item in attributes) | set(item["id"] for item in geometry_changes)),
        "removed_entities": len(removals),
        "geometry_only_changes": len(set(item["id"] for item in geometry_changes) - set(item["entity_id"] for item in attributes)),
        "attribute_only_changes": len(set(item["entity_id"] for item in attributes) - set(item["id"] for item in geometry_changes)),
    }
    qc = {
        "directly_removed_entities": direct,
        "cascade_removed_pois": cascade,
        "geometry_perturbations": int(candidate["geometry_override_count"]),
        "geometry_fallbacks": len(fallback_ids),
        "attribute_perturbations": len(attributes),
        "lc_masked_cells": int(candidate["landcover_mask_count"]),
        "dem_noise_statistics": "Not recorded" if not selected["raster"] else {
            "changed_cells": int(candidate["dem_noise_count"]),
            "max_abs_difference": max((abs(float(dem[i]) - float(original["dem"]["values"][i])) for i in range(len(dem)) if dem[i] is not None and original["dem"]["values"][i] is not None), default=0.0),
        },
        "absorbed_donors": donors,
        "receiver_groups": len(receiver_ids),
        "sn_reconstructed_count": int(relation_counts["SN"]["final"]),
        "preserved_counts": {name: int(relation_counts[name]["final"]) for name in ("CNT", "WIT", "INT", "CON")},
        "dangling_references": 0,
        "validation_status": candidate["status"],
    }
    return {
        "profile_id": profile,
        "label": PROFILE_LABELS[profile],
        "candidate_id": candidate_id,
        "candidate_slice_sha256": _candidate_slice_checksum(selected),
        "branch_id": manifest["branch_id"],
        "branch_payload_sha256": manifest["payload"]["sha256"],
        "in_k8": view < 8,
        "removals": [{"id": local, "role": role} for local, role in sorted(removals.items())],
        "geometry_changes": sorted(geometry_changes, key=lambda item: item["id"]),
        "fallback_ids": fallback_ids,
        "absorption": absorption,
        "attributes": sorted(attributes, key=lambda item: (item["entity_type"], item["entity_id"], item["attribute_name"])),
        "landcover": {"shape": [100, 100], "values": lc},
        "dem": {"shape": [17, 17], "values": dem},
        "summary": summary,
        "qc": qc,
        "candidate": candidate,
    }


def _case(artifacts: AcceptedArtifacts, specification: dict[str, Any], temporary: Path, table_cache: dict[tuple[Path, str], Any]) -> dict[str, Any]:
    scene_id = specification["scene_id"]
    view = int(specification["master_view_id"])
    artifacts.validate_scene_view(scene_id, view)
    original = _original_scene(artifacts, scene_id, temporary)
    profiles = {profile: _augmented_profile(artifacts, original, profile, view, table_cache) for profile in PROFILES}
    public_original = {key: value for key, value in original.items() if key != "entity_by_id"}
    return {
        "scene_id": scene_id,
        "master_view_id": view,
        "reason": specification.get("reason", "explicit scene/view"),
        "metric_value": specification.get("metric_value"),
        "original": public_original,
        "profiles": profiles,
    }


def _template(data_json: str) -> str:
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>P4 Augmentation Inspector</title>
<style>
:root{--ink:#172126;--muted:#5b6870;--line:#cbd3d7;--panel:#fff;--band:#eef2f3;--accent:#006d77;--remove:#c43c35;--change:#d68400;--absorb:#7856a7;--receiver:#007c91}*{box-sizing:border-box}body{margin:0;background:#f5f7f7;color:var(--ink);font:14px/1.4 system-ui,sans-serif;overflow-x:hidden}header{position:sticky;top:0;z-index:20;background:#fff;border-bottom:1px solid var(--line);padding:12px 18px}.brand{display:flex;align-items:baseline;gap:12px;margin-bottom:10px}.brand h1{font-size:20px;margin:0;letter-spacing:0}.brand span{color:var(--muted)}.controls{display:flex;flex-wrap:wrap;gap:10px;align-items:end;min-width:0;width:100%}.control{display:grid;gap:3px;min-width:0}.control label{font-size:11px;text-transform:uppercase;color:var(--muted);font-weight:700;min-width:0}.control select,.control input,.control button{height:34px;max-width:100%;border:1px solid #aeb9be;background:#fff;padding:0 9px;border-radius:4px;color:var(--ink)}button{cursor:pointer}.layer-group{display:flex;gap:8px;height:34px;align-items:center}.layer-group label{font-size:13px;text-transform:none;color:var(--ink);font-weight:500}main{padding:18px;max-width:1800px;margin:auto}.case-meta{display:flex;justify-content:space-between;gap:16px;margin-bottom:12px}.case-meta h2{font-size:16px;margin:0}.case-meta code{font-size:12px}.section{margin:0 0 20px;min-width:0}.section>h2{font-size:15px;margin:0;padding:9px 12px;background:#263238;color:#fff}.grid4{display:grid;grid-template-columns:repeat(4,minmax(240px,1fr));gap:1px;background:var(--line);border:1px solid var(--line)}.panel{background:var(--panel);min-width:0}.panel h3{font-size:13px;margin:0;padding:8px 10px;border-bottom:1px solid var(--line);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.canvas-wrap{position:relative;aspect-ratio:1/1;background:#fafbfb;overflow:hidden}.canvas-wrap canvas{display:block;width:100%;height:100%}.north{position:absolute;right:9px;top:7px;font-weight:800}.scale{position:absolute;left:10px;bottom:8px;width:20%;border-bottom:3px solid #111;text-align:center;font-size:10px}.tooltip{position:fixed;display:none;z-index:50;pointer-events:none;max-width:340px;padding:7px 9px;background:#101719;color:white;border-radius:3px;font-size:12px;white-space:pre-wrap}.legend{display:flex;flex-wrap:wrap;gap:10px;padding:8px 10px;background:#fff;border:1px solid var(--line);border-top:0}.legend span:before{content:"";display:inline-block;width:16px;height:8px;margin-right:4px;border:2px solid var(--c);background:var(--b);vertical-align:middle}.summary{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:4px;padding:9px;font-size:11px}.summary div{background:var(--band);padding:5px 7px}.summary b{display:block;font-size:13px}.table-tools{display:flex;flex-wrap:wrap;gap:8px;padding:10px;background:#fff;border:1px solid var(--line);border-bottom:0}.table-tools input,.table-tools select{height:32px;border:1px solid #aeb9be;padding:0 8px}.table-wrap{overflow:auto;max-width:100%;max-height:480px;border:1px solid var(--line);background:#fff}table{border-collapse:collapse;width:100%;font-size:12px}th{position:sticky;top:0;background:#e5eaec;text-align:left;cursor:pointer}th,td{padding:7px 8px;border-bottom:1px solid #dde3e5;max-width:240px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}tr.selected{outline:2px solid var(--accent)}.pager{display:flex;justify-content:flex-end;gap:8px;padding:8px;background:#fff;border:1px solid var(--line);border-top:0}.provenance{background:#fff;border:1px solid var(--line);padding:12px}.provenance pre{white-space:pre-wrap;word-break:break-word;font-size:11px}.hidden{display:none!important}.warning{color:#8a2c27;font-weight:700}@media(max-width:1050px){.grid4{grid-template-columns:repeat(2,minmax(260px,1fr))}}@media(max-width:620px){main{padding:8px}.grid4{grid-template-columns:1fr}header{position:relative;padding:10px}.control:first-child{width:100%;max-width:calc(100vw - 20px)}#caseSelect{width:100%;min-width:0;max-width:calc(100vw - 20px)}.case-meta{display:block}.case-meta code{display:block;margin-top:4px;overflow-wrap:anywhere}}
</style></head><body><header><div class="brand"><h1>P4 Augmentation Inspector</h1><span>Read-only human visual QC</span></div><div class="controls">
<div class="control"><label>QC case</label><select id="caseSelect"></select></div><div class="control"><label>Scene ID</label><input id="sceneId" readonly size="28"></div><div class="control"><label>Master view</label><input id="viewId" readonly size="4"></div>
<div class="control"><label>Vector layers</label><div class="layer-group"><label><input type="checkbox" data-layer="B" checked>Building</label><label><input type="checkbox" data-layer="R" checked>Road</label><label><input type="checkbox" data-layer="P" checked>POI</label></div></div>
<div class="control"><label>Raster variable</label><select id="rasterVar"><option value="landcover">Land cover</option><option value="dem">DEM</option></select></div><div class="control"><label>Display mode</label><select id="rasterMode"><option value="actual">Actual value</option><option value="difference">Difference from original</option></select></div>
<div class="control"><label>Commands</label><div><button id="resetZoom" title="Reset all vector panels to the 500 m extent">Reset zoom</button> <button id="toggleProvenance">Provenance</button></div></div></div></header>
<main><div class="case-meta"><h2 id="caseTitle"></h2><code id="identity"></code></div>
<section class="section"><h2>Vector transformation</h2><div class="grid4" id="vectorGrid"></div><div class="legend"><span style="--c:#4f5b60;--b:#d9dfe1">Unchanged</span><span style="--c:#c43c35;--b:transparent">Removed ghost</span><span style="--c:#d68400;--b:#ffe0a3">Geometry perturbed</span><span style="--c:#7856a7;--b:transparent">Absorbed donor</span><span style="--c:#007c91;--b:#b8e2e6">Receiver</span><span style="--c:#111;--b:#fff">Geometry fallback</span></div></section>
<section class="section"><h2>Raster transformation</h2><div class="grid4" id="rasterGrid"></div></section>
<section class="section"><h2>Attribute transformation</h2><div class="grid4" id="summaryGrid"></div><div class="table-tools"><input id="search" placeholder="Search entity/value"><select id="profileFilter"><option value="">All profiles</option></select><select id="entityFilter"><option value="">All entity types</option><option>B</option><option>R</option><option>P</option></select><select id="operationFilter"><option value="">All operations</option><option>MASK</option><option>REPLACE</option><option>PERTURB</option></select><label><input type="checkbox" id="changedOnly" checked> Changed only</label></div><div class="table-wrap"><table><thead><tr id="tableHead"></tr></thead><tbody id="attributeBody"></tbody></table></div><div class="pager"><button id="prevPage">Previous</button><span id="pageInfo"></span><button id="nextPage">Next</button></div></section>
<section id="provenance" class="section provenance hidden"><h2>Provenance and QC summary</h2><pre id="provenanceText"></pre></section></main><div class="tooltip" id="tooltip"></div>
<script>const DATA=""" + data_json + """;
const profiles=['original','weak_0.5x','main_1.0x','strong_2.0x'];const labels={original:'Original spatial scene','weak_0.5x':'Weak augmentation (0.5x)','main_1.0x':'Main augmentation (1.0x)','strong_2.0x':'Strong augmentation (2.0x)'};
let caseIndex=0,view={scale:1,dx:0,dy:0},drag=null,page=0,sortKey='profile',sortAsc=true,selectedEntity=null;const pageSize=80;const $=id=>document.getElementById(id);const tip=$('tooltip');
function current(){return DATA.cases[caseIndex]}function profileData(c,p){return p==='original'?c.original:c.profiles[p]}function esc(v){return String(v??'Not recorded').replace(/[&<>"']/g,x=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[x]))}
function init(){DATA.cases.forEach((c,i)=>{let o=document.createElement('option');o.value=i;o.textContent=`${i+1}. ${c.reason} · ${c.scene_id} / v${c.master_view_id}`;$('caseSelect').append(o)});['weak_0.5x','main_1.0x','strong_2.0x'].forEach(p=>{let o=document.createElement('option');o.value=p;o.textContent=labels[p];$('profileFilter').append(o)});$('caseSelect').onchange=e=>{caseIndex=+e.target.value;view={scale:1,dx:0,dy:0};page=0;render()};document.querySelectorAll('[data-layer]').forEach(x=>x.onchange=renderVectors);$('rasterVar').onchange=renderRasters;$('rasterMode').onchange=renderRasters;$('resetZoom').onclick=()=>{view={scale:1,dx:0,dy:0};renderVectors()};$('toggleProvenance').onclick=()=>$('provenance').classList.toggle('hidden');['search','profileFilter','entityFilter','operationFilter','changedOnly'].forEach(id=>$(id).oninput=()=>{page=0;renderTable()});$('prevPage').onclick=()=>{page=Math.max(0,page-1);renderTable()};$('nextPage').onclick=()=>{page++;renderTable()};render()}
function panel(title,kind){let d=document.createElement('div');d.className='panel';d.innerHTML=`<h3 title="${esc(title)}">${esc(title)}</h3><div class="canvas-wrap"><canvas data-kind="${kind}"></canvas>${kind==='vector'?'<b class="north">N↑</b><span class="scale">100 m</span>':''}</div>`;return d}
function resize(canvas){let r=canvas.getBoundingClientRect(),d=devicePixelRatio||1;if(canvas.width!==Math.round(r.width*d)||canvas.height!==Math.round(r.height*d)){canvas.width=Math.round(r.width*d);canvas.height=Math.round(r.height*d)}return [canvas.width,canvas.height]}
function geomParts(g){if(!g)return[];let c=g.coordinates;if(g.type==='Point')return[[c]];if(g.type==='LineString')return[c];if(g.type==='MultiLineString')return c;if(g.type==='Polygon')return c;if(g.type==='MultiPolygon')return c.flat();return[]}
function entityState(c,p){let original=new Map(c.original.entities.map(e=>[e.id,{...e,status:'unchanged'}]));if(p==='original')return [...original.values()];let d=c.profiles[p],removed=new Map(d.removals.map(r=>[r.id,r.role]));for(let [id,role] of removed){let e=original.get(id);if(e){e={...e,status:role==='ABSORBED_ROAD'?'donor':'removed',removal_role:role};original.set(id,e)}}for(let change of d.geometry_changes){let e=original.get(change.id);if(e){original.set(change.id,{...e,geometry:change.geometry,status:change.receiver?'receiver':change.fallback?'fallback':'perturbed',operation:change.operation,area:change.area,length:change.length,accepted_attempt:change.accepted_attempt})}}let attr=new Set(d.attributes.map(a=>a.entity_id));for(let id of attr){let e=original.get(id);if(e&&e.status==='unchanged')original.set(id,{...e,status:'attribute'})}return [...original.values()]}
function transform(bounds,w,h,x,y){let cx=(bounds[0]+bounds[2])/2,cy=(bounds[1]+bounds[3])/2,s=Math.min(w,h)/500*view.scale;return[w/2+(x-cx)*s+view.dx,h/2-(y-cy)*s+view.dy]}
function drawGeometry(ctx,g,b,w,h,style){ctx.beginPath();for(let part of geomParts(g)){part.forEach((xy,i)=>{let q=transform(b,w,h,xy[0],xy[1]);i?ctx.lineTo(q[0],q[1]):ctx.moveTo(q[0],q[1])});if(g.type.includes('Polygon'))ctx.closePath()}ctx.globalAlpha=style.alpha??1;ctx.setLineDash(style.dash||[]);ctx.strokeStyle=style.stroke;ctx.lineWidth=style.width||1;ctx.fillStyle=style.fill||'transparent';if(g.type.includes('Polygon'))ctx.fill();ctx.stroke();ctx.globalAlpha=1;ctx.setLineDash([])}
function vectorStyle(e){if(e.status==='removed')return{stroke:'#c43c35',dash:[5,3],alpha:.65,width:2};if(e.status==='donor')return{stroke:'#7856a7',dash:[3,3],alpha:.75,width:3};if(e.status==='receiver')return{stroke:'#007c91',fill:'#b8e2e6',width:3};if(e.status==='perturbed')return{stroke:'#d68400',fill:'#ffe0a3',width:2};if(e.status==='fallback')return{stroke:'#111',fill:'#fff',dash:[2,2],width:3};if(e.status==='attribute')return{stroke:'#33658a',fill:'#d9dfe1',width:2};return{stroke:'#59666b',fill:e.type==='B'?'#d9dfe1':'transparent',width:e.type==='R'?1.5:1}}
function renderVectors(){let c=current(),grid=$('vectorGrid');grid.innerHTML='';for(let p of profiles){let el=panel(labels[p],'vector'),canvas=el.querySelector('canvas');canvas.dataset.profile=p;grid.append(el);requestAnimationFrame(()=>drawVector(canvas,c,p));canvas.onwheel=e=>{e.preventDefault();let factor=e.deltaY<0?1.2:1/1.2;view.scale=Math.max(1,Math.min(12,view.scale*factor));renderVectors()};canvas.onpointerdown=e=>{drag=[e.clientX,e.clientY,view.dx,view.dy];canvas.setPointerCapture(e.pointerId)};canvas.onpointermove=e=>{if(drag){view.dx=drag[2]+(e.clientX-drag[0])*(devicePixelRatio||1);view.dy=drag[3]+(e.clientY-drag[1])*(devicePixelRatio||1);renderVectors()}};canvas.onpointerup=()=>drag=null;canvas.onmousemove=e=>vectorHover(e,canvas,c,p);canvas.onclick=e=>vectorClick(e,canvas,c,p)}}
function drawVector(canvas,c,p){let [w,h]=resize(canvas),ctx=canvas.getContext('2d');ctx.clearRect(0,0,w,h);ctx.fillStyle='#fbfcfc';ctx.fillRect(0,0,w,h);let b=c.original.bounds;ctx.strokeStyle='#91a0a6';ctx.strokeRect((w-Math.min(w,h))/2,(h-Math.min(w,h))/2,Math.min(w,h),Math.min(w,h));let layers=new Set([...document.querySelectorAll('[data-layer]:checked')].map(x=>x.dataset.layer));let entities=entityState(c,p).filter(e=>layers.has(e.type));for(let type of ['B','R','P'])for(let e of entities.filter(x=>x.type===type)){let st=vectorStyle(e);if(type==='P'){let q=transform(b,w,h,e.geometry.coordinates[0],e.geometry.coordinates[1]);ctx.beginPath();ctx.arc(q[0],q[1],e.status==='unchanged'?2.2:4,0,Math.PI*2);ctx.fillStyle=st.fill==='transparent'?st.stroke:st.fill;ctx.fill();ctx.strokeStyle=st.stroke;ctx.stroke()}else drawGeometry(ctx,e.geometry,b,w,h,st)}canvas._entities=entities}
function nearestEntity(e,canvas,c){let r=canvas.getBoundingClientRect(),px=(e.clientX-r.left)*(canvas.width/r.width),py=(e.clientY-r.top)*(canvas.height/r.height),best=null,bd=10*(devicePixelRatio||1);for(let ent of canvas._entities||[]){let coords=geomParts(ent.geometry).flat(),b=c.original.bounds;for(let xy of coords){let q=transform(b,canvas.width,canvas.height,xy[0],xy[1]),d=Math.hypot(q[0]-px,q[1]-py);if(d<bd){bd=d;best=ent}}}return best}
function vectorHover(e,canvas,c,p){let ent=nearestEntity(e,canvas,c);if(!ent){tip.style.display='none';return}let rel=p==='original'?'Original relations: Not summarized':JSON.stringify(c.profiles[p].qc.preserved_counts);tip.textContent=`${labels[p]}\n${ent.type} ${ent.id} · ${ent.source_id}\nStatus: ${ent.status}\nOperation: ${ent.operation||'Not recorded'}\nArea: ${ent.area.toFixed(3)} m² · Length: ${ent.length.toFixed(3)} m\nRelations: ${rel}`;tip.style.display='block';tip.style.left=(e.clientX+12)+'px';tip.style.top=(e.clientY+12)+'px'}
function vectorClick(e,canvas,c,p){let ent=nearestEntity(e,canvas,c);if(ent){selectedEntity=ent.id;$('search').value=String(ent.id);page=0;renderTable()}}
const lcPalette=['#000000','#e41a1c','#377eb8','#4daf4a','#984ea3','#ff7f00','#ffff33','#a65628','#f781bf','#999999','#66c2a5','#fc8d62','#8da0cb','#e78ac3','#a6d854','#ffd92f','#e5c494','#b3b3b3','#1b9e77','#d95f02','#7570b3','#e7298a','#6a3d9a'];
function rasterValues(c,p,v){let d=p==='original'?c.original:c.profiles[p];return d[v].values}
function renderRasters(){let c=current(),grid=$('rasterGrid'),variable=$('rasterVar').value,mode=$('rasterMode').value;grid.innerHTML='';let all=profiles.map(p=>rasterValues(c,p,variable)),numeric=all.flat().filter(x=>x!==null&&x>=0);let min=Math.min(...numeric),max=Math.max(...numeric),diffs=[];if(variable==='dem')for(let k=1;k<4;k++)all[k].forEach((x,i)=>{let o=all[0][i];if(x!==null&&o!==null)diffs.push(x-o)});let M=Math.max(1e-9,...diffs.map(Math.abs));for(let pi=0;pi<4;pi++){let p=profiles[pi],el=panel(labels[p],'raster'),canvas=el.querySelector('canvas');grid.append(el);requestAnimationFrame(()=>drawRaster(canvas,c,p,variable,mode,min,max,M));canvas.onmousemove=e=>rasterHover(e,canvas,c,p,variable)}}
function colorRamp(t){t=Math.max(0,Math.min(1,t));let r=Math.round(35+220*t),g=Math.round(92+100*(1-Math.abs(t-.5)*2)),b=Math.round(160-120*t);return`rgb(${r},${g},${b})`}
function drawRaster(canvas,c,p,v,mode,min,max,M){let [w,h]=resize(canvas),ctx=canvas.getContext('2d'),shape=(p==='original'?c.original:c.profiles[p])[v].shape,vals=rasterValues(c,p,v),orig=rasterValues(c,'original',v),cw=w/shape[1],ch=h/shape[0];ctx.clearRect(0,0,w,h);for(let row=0;row<shape[0];row++)for(let col=0;col<shape[1];col++){let i=row*shape[1]+col,x=vals[i],o=orig[i],color;if(v==='landcover'){if(mode==='difference'){color=x===-1?'#222':x===o?'#e5eaec':'#d68400'}else color=x===-1?'#222':x===0?'#fff':lcPalette[x%lcPalette.length]}else{let value=mode==='difference'?(p==='original'?0:(x===null||o===null?null:x-o)):x;color=value===null?'#fff':mode==='difference'?colorRamp((value+M)/(2*M)):colorRamp((value-min)/(max-min||1))}ctx.fillStyle=color;ctx.fillRect(col*cw,row*ch,Math.ceil(cw)+.2,Math.ceil(ch)+.2);if(v==='landcover'&&x===-1){ctx.strokeStyle='#fff8';ctx.beginPath();ctx.moveTo(col*cw,row*ch);ctx.lineTo((col+1)*cw,(row+1)*ch);ctx.stroke()}}canvas._shape=shape}
function rasterHover(e,canvas,c,p,v){let r=canvas.getBoundingClientRect(),shape=canvas._shape,col=Math.floor((e.clientX-r.left)/r.width*shape[1]),row=Math.floor((e.clientY-r.top)/r.height*shape[0]);if(row<0||col<0||row>=shape[0]||col>=shape[1])return;let i=row*shape[1]+col,o=rasterValues(c,'original',v)[i],x=rasterValues(c,p,v)[i],b=c.original.bounds,cx=b[0]+(col+.5)*(500/shape[1]),cy=b[3]-(row+.5)*(500/shape[0]);tip.textContent=`${v==='dem'?'DEM':'Land cover'} [${row}, ${col}]\nEPSG:5186 ${cx.toFixed(2)}, ${cy.toFixed(2)}\nOriginal: ${o??'nodata'}\n${labels[p]}: ${x===-1?'masked':x??'nodata'}\nDifference: ${v==='dem'&&o!==null&&x!==null?(x-o).toFixed(4):x===o?'unchanged':'changed'}`;tip.style.display='block';tip.style.left=(e.clientX+12)+'px';tip.style.top=(e.clientY+12)+'px'}
function renderSummaries(){let c=current(),grid=$('summaryGrid');grid.innerHTML='';for(let p of profiles){let el=document.createElement('div');el.className='panel';let s=p==='original'?{changed_entities:0,masked_fields:0,replaced_categorical_fields:0,lane_perturbations:0,unchanged_entities:c.original.entities.length,removed_entities:0,geometry_only_changes:0,attribute_only_changes:0}:c.profiles[p].summary;el.innerHTML=`<h3>${labels[p]}</h3><div class="summary">${Object.entries(s).map(([k,v])=>`<div><b>${v}</b>${esc(k.replaceAll('_',' '))}</div>`).join('')}</div>`;grid.append(el)}}
const columns=['profile','master_view_id','entity_type','entity_id','operation','attribute_name','original_value','augmented_value','changed','change_type','provenance_key'];
function attributeRows(){let c=current(),rows=profiles.slice(1).flatMap(p=>c.profiles[p].attributes),q=$('search').value.toLowerCase(),pf=$('profileFilter').value,ef=$('entityFilter').value,of=$('operationFilter').value;return rows.filter(r=>(!q||JSON.stringify(r).toLowerCase().includes(q))&&(!pf||r.profile===pf)&&(!ef||r.entity_type===ef)&&(!of||r.operation===of)&&(!$('changedOnly').checked||r.changed)).sort((a,b)=>{let av=String(a[sortKey]??''),bv=String(b[sortKey]??'');return(av.localeCompare(bv,undefined,{numeric:true})||(a.entity_id-b.entity_id))*(sortAsc?1:-1)})}
function renderTable(){let head=$('tableHead');head.innerHTML='';for(let col of columns){let th=document.createElement('th');th.textContent=col.replaceAll('_',' ');th.onclick=()=>{if(sortKey===col)sortAsc=!sortAsc;else{sortKey=col;sortAsc=true}renderTable()};head.append(th)}let rows=attributeRows(),pages=Math.max(1,Math.ceil(rows.length/pageSize));page=Math.min(page,pages-1);$('attributeBody').innerHTML=rows.slice(page*pageSize,(page+1)*pageSize).map(r=>`<tr class="${selectedEntity===r.entity_id?'selected':''}">${columns.map(c=>`<td title="${esc(r[c])}">${esc(r[c])}</td>`).join('')}</tr>`).join('');$('pageInfo').textContent=`Page ${page+1}/${pages} · ${rows.length} rows`}
function renderProvenance(){let c=current();$('provenanceText').textContent=JSON.stringify({artifact_ids:DATA.artifact_ids,scene_id:c.scene_id,master_view_id:c.master_view_id,reason:c.reason,metric_value:c.metric_value,original_shard_id:c.original.p3_branch_id,profiles:Object.fromEntries(profiles.slice(1).map(p=>[p,{candidate_id:c.profiles[p].candidate_id,candidate_slice_sha256:c.profiles[p].candidate_slice_sha256,augmentation_shard_id:c.profiles[p].branch_id,branch_payload_sha256:c.profiles[p].branch_payload_sha256,in_k8:c.profiles[p].in_k8,qc:c.profiles[p].qc,attempt_histogram:JSON.parse(c.profiles[p].candidate.attempt_histogram_json)}]))},null,2)}
function render(){let c=current();$('sceneId').value=c.scene_id;$('viewId').value=c.master_view_id;$('caseTitle').textContent=`${c.reason} · metric ${c.metric_value??'Not recorded'}`;$('identity').textContent=`${c.scene_id} / master view ${c.master_view_id}`;selectedEntity=null;renderVectors();renderRasters();renderSummaries();renderTable();renderProvenance()}
window.addEventListener('resize',()=>{renderVectors();renderRasters()});window.addEventListener('load',init);</script></body></html>"""


def validate_html(path: Path, expected_cases: int | None = None) -> dict[str, Any]:
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    required = (
        "Original spatial scene", "Weak augmentation (0.5x)", "Main augmentation (1.0x)",
        "Strong augmentation (2.0x)", "Vector transformation", "Raster transformation",
        "Attribute transformation", "caseSelect", "rasterVar", "rasterMode", "provenance",
        EXPECTED["p3_cache"], EXPECTED["p4_bank"], EXPECTED["p4_index"],
    )
    missing = [item for item in required if item not in text]
    external = any(token in text.lower() for token in ("https://", "http://", "cdn.", "@import url"))
    absolute = "/mnt/hdd002/" in text or "/members/dhnyu/" in text
    marker = "const DATA="
    start = text.index(marker) + len(marker)
    end = text.index(";\nconst profiles", start)
    data = json.loads(text[start:end])
    if expected_cases is not None and len(data["cases"]) != expected_cases:
        missing.append(f"case_count:{len(data['cases'])}")
    if missing or external or absolute:
        raise InspectorError(f"HTML validation failed: missing={missing}, external={external}, absolute_path={absolute}")
    return {"status": "PASS", "sha256": sha256_bytes(raw), "size_bytes": len(raw), "case_count": len(data["cases"])}


def generate_inspector(
    repository: Path,
    output: Path,
    scene_id: str | None = None,
    master_view_id: int | None = None,
    preset: str | None = None,
    max_cases: int = 8,
    original_cache_root: Path | None = None,
    augmentation_bank_root: Path | None = None,
    master_bank_id: str = EXPECTED["p4_bank"],
    logical_index_id: str = EXPECTED["p4_index"],
    overwrite: bool = False,
) -> dict[str, Any]:
    started = time.monotonic()
    if output.exists() and not overwrite:
        raise InspectorError(f"output exists; pass --overwrite: {output}")
    if preset and (scene_id is not None or master_view_id is not None):
        raise InspectorError("use either an explicit scene/view or a preset")
    if preset not in (None, "qc-extremes"):
        raise InspectorError(f"unsupported preset: {preset}")
    if not preset and (scene_id is None or master_view_id is None):
        raise InspectorError("explicit mode requires --scene-id and --master-view-id")
    artifacts = AcceptedArtifacts(repository, original_cache_root, augmentation_bank_root, master_bank_id, logical_index_id)
    specifications = artifacts.select_qc_extremes(max_cases) if preset else [{"scene_id": scene_id, "master_view_id": master_view_id}]
    table_cache: dict[tuple[Path, str], dict[str, list[dict[str, Any]]]] = {}
    with tempfile.TemporaryDirectory(prefix="augmentation-inspector-") as temporary:
        cases = [_case(artifacts, specification, Path(temporary), table_cache) for specification in specifications]
    payload = {
        "schema_version": "1.0.0",
        "tool": "P4 augmentation inspector",
        "scientific_status": "supplementary human visual QC; not scientific acceptance",
        "artifact_ids": {
            "p3_cache_id": artifacts.p3_manifest["cache_id"],
            "p3_acceptance_id": artifacts.p3_acceptance["acceptance_id"],
            "p4_supplement_version": EXPECTED["supplement"],
            "p4_master_bank_id": artifacts.p4_acceptance["bank_id"],
            "p4_logical_index_id": artifacts.index_manifest["index_id"],
        },
        "cases": cases,
    }
    encoded = canonical_json(payload).decode("utf-8").replace("<", "\\u003c").replace("</script", "<\\/script")
    rendered = _template(encoded).encode("utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_output = output.parent / f".{output.name}.{os.getpid()}.tmp"
    try:
        temporary_output.write_bytes(rendered)
        validation = validate_html(temporary_output, len(cases))
        os.replace(temporary_output, output)
    finally:
        temporary_output.unlink(missing_ok=True)
    return {
        **validation,
        "output": str(output),
        "selected_cases": [{key: case[key] for key in ("scene_id", "master_view_id", "reason", "metric_value")} for case in cases],
        "runtime_seconds": time.monotonic() - started,
        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }
