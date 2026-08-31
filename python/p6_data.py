"""Read-only P3/P4/P5 scene composition and production ragged collation."""

from __future__ import annotations

import hashlib
import io
import json
import math
import os
import tarfile
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np
import pyarrow.parquet as pq
import shapely
import torch
import zarr
from torch.utils.data import Dataset, Sampler

from serialize_prototype_shard import geometry_parts


RELATION_BITS = {"SN": 1, "CNT": 2, "WIT": 4, "INT": 8, "CON": 16}
TYPE_CODES = {"B": 0, "R": 1, "P": 2}
GEOMETRY_LAYOUT_VERSION = "3.0.0"


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def scientific_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _table(archive: tarfile.TarFile, name: str, scene_id: str | None = None,
           identity_field: str | None = None, identity: str | None = None) -> list[dict[str, Any]]:
    member = archive.extractfile(name)
    if member is None:
        raise ValueError(f"missing tar member: {name}")
    rows = pq.read_table(io.BytesIO(member.read())).to_pylist()
    if scene_id is not None:
        rows = [row for row in rows if row.get("scene_id") == scene_id]
    if identity_field is not None:
        rows = [row for row in rows if row.get(identity_field) == identity]
    return rows


class RunningStats:
    def __init__(self) -> None:
        self.count = 0
        self.mean = 0.0
        self.m2 = 0.0

    def add_many(self, values: Iterable[float]) -> None:
        for value in values:
            if not math.isfinite(value):
                continue
            self.count += 1
            delta = value - self.mean
            self.mean += delta / self.count
            self.m2 += delta * (value - self.mean)

    def result(self) -> dict[str, Any]:
        if not self.count:
            raise ValueError("training-only normalization field has no valid observations")
        sd = math.sqrt(self.m2 / self.count)
        return {"count": self.count, "mean": self.mean, "sd": sd, "scale": sd if sd else 1.0,
                "constant": sd == 0.0}


class ArtifactCatalog:
    """Resolve accepted immutable payloads using official indices only."""

    def __init__(self, roots: dict[str, str | Path], expected: dict[str, str], verify: bool = True) -> None:
        self.roots = {key: Path(value) for key, value in roots.items()}
        self.expected = expected
        p3_indices = list((self.roots["p3"] / "index").glob("*/scene_to_shard.parquet"))
        if len(p3_indices) != 1:
            raise ValueError("P3 accepted scene index is missing or ambiguous")
        self.p3_rows = pq.read_table(p3_indices[0]).to_pylist()
        self.p3_by_scene = {row["scene_id"]: row for row in self.p3_rows}
        if len(self.p3_by_scene) != 4421 or any(row["cache_id"] != expected["p3_cache_id"] for row in self.p3_rows):
            raise ValueError("P3 scene population/cache identity mismatch")
        acceptance_dirs = list((self.roots["p4"] / "acceptance").glob("*/augmentation_bank_acceptance.json"))
        if len(acceptance_dirs) != 1:
            raise ValueError("P4 acceptance is missing or ambiguous")
        p4_acceptance = json.loads(acceptance_dirs[0].read_text())
        if p4_acceptance["bank_id"] != expected["p4_master_bank_id"] or p4_acceptance["status"] != "PASS":
            raise ValueError("P4 accepted bank mismatch")
        effective = acceptance_dirs[0].with_name("effective_bank_index.parquet")
        self.k8_rows = pq.read_table(effective).to_pylist()
        self.k8 = defaultdict(list)
        for row in self.k8_rows:
            if row["profile_id"] == "main_1.0x" and int(row["requested_k"]) == 8:
                self.k8[row["scene_id"]].append(row)
        if len(self.k8) != 2421 or any(len(rows) != 8 for rows in self.k8.values()):
            raise ValueError("P4 main K8 population mismatch")
        self.p4_branch = {}
        p3_branch_by_sha = {row["payload_sha256"]: row["branch_id"] for row in self.p3_rows}
        for manifest_path in sorted((self.roots["p4"] / "shards" / "main_1.0x").glob("*/branch_manifest.json")):
            manifest = json.loads(manifest_path.read_text())
            parent_branch = p3_branch_by_sha.get(manifest["parent_tar_sha256"])
            if parent_branch is None:
                raise ValueError("P4 branch does not resolve to an accepted P3 payload")
            self.p4_branch[parent_branch] = (manifest_path.parent / manifest["payload"]["filename"], manifest)
        if len(self.p4_branch) != 96:
            raise ValueError("P4 main branch/P3 shard mapping mismatch")
        p5_dirs = list((self.roots["p5"] / "acceptance").glob("*/fixed_query_acceptance.json"))
        if len(p5_dirs) != 1:
            raise ValueError("P5 acceptance is missing or ambiguous")
        self.p5_acceptance_root = p5_dirs[0].parent
        p5_acceptance = json.loads(p5_dirs[0].read_text())
        if p5_acceptance["query_authority_id"] != expected["p5_query_authority_id"] or p5_acceptance["status"] != "PASS":
            raise ValueError("P5 accepted authority mismatch")
        self.query_rows, self.gallery_rows = {}, {}
        for split in ("validation", "evaluation"):
            queries = pq.read_table(self.p5_acceptance_root / f"{split}_query_index.parquet").to_pylist()
            galleries = pq.read_table(self.p5_acceptance_root / f"{split}_gallery.parquet").to_pylist()
            self.query_rows[split] = sorted(queries, key=lambda row: (row["scene_id"], int(row["query_index"])))
            self.gallery_rows[split] = sorted(galleries, key=lambda row: row["scene_id"])
        if [len(self.gallery_rows[x]) for x in ("validation", "evaluation")] != [400, 1600] or [len(self.query_rows[x]) for x in ("validation", "evaluation")] != [800, 3200]:
            raise ValueError("P5 population mismatch")
        self._verified: set[Path] = set()
        self.verify = verify

    def p3_tar(self, scene_id: str) -> tuple[Path, dict[str, Any]]:
        row = self.p3_by_scene.get(scene_id)
        if row is None:
            raise KeyError(f"unknown accepted scene: {scene_id}")
        path = self.roots["p3"] / "shards" / row["branch_id"] / row["payload_filename"]
        self._verify(path, row["payload_sha256"])
        return path, row

    def p4_tar(self, scene_id: str) -> tuple[Path, dict[str, Any]]:
        _, parent = self.p3_tar(scene_id)
        path, manifest = self.p4_branch[parent["branch_id"]]
        self._verify(path, manifest["payload"]["sha256"])
        return path, manifest

    def p5_tar(self, row: dict[str, Any]) -> Path:
        path = self.roots["p5"] / row["namespace"] / "shards" / row["query_branch_id"] / row["query_payload_filename"]
        self._verify(path, row["query_payload_sha256"])
        return path

    def _verify(self, path: Path, checksum: str) -> None:
        if not path.is_file():
            raise ValueError(f"missing immutable payload: {path.name}")
        if self.verify and path not in self._verified:
            if sha256_file(path) != checksum:
                raise ValueError(f"immutable payload checksum mismatch: {path.name}")
            self._verified.add(path)


VOCABULARY_FIELDS = frozenset({"A9", "A11", "ROAD_RANK", "ROAD_TYPE", *(f"CLASS_L{x}" for x in range(1, 7))})


def validate_vocabulary_contract(vocabulary: dict[str, Any]) -> dict[str, int]:
    """Validate the accepted direct field mapping and return embedding sizes."""
    if set(vocabulary) != VOCABULARY_FIELDS:
        missing = sorted(VOCABULARY_FIELDS - set(vocabulary))
        extra = sorted(set(vocabulary) - VOCABULARY_FIELDS)
        raise ValueError(f"official category dictionary field mismatch: missing={missing}, extra={extra}")
    sizes: dict[str, int] = {}
    for field in sorted(VOCABULARY_FIELDS):
        contract = vocabulary[field]
        if not isinstance(contract, dict):
            raise ValueError(f"invalid vocabulary field contract: {field}")
        required = {"keys", "mapping", "missing", "mask", "size"}
        if not required.issubset(contract):
            raise ValueError(f"incomplete vocabulary field contract: {field}")
        size = contract["size"]
        if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
            raise ValueError(f"invalid vocabulary size: {field}")
        keys = contract["keys"]
        if not isinstance(keys, list) or len(keys) + 2 != size:
            raise ValueError(f"vocabulary reserved-token size mismatch: {field}")
        if contract["missing"] != len(keys) or contract["mask"] != len(keys) + 1:
            raise ValueError(f"vocabulary missing/mask index mismatch: {field}")
        mapping = contract["mapping"]
        if not isinstance(mapping, dict) or not mapping:
            raise ValueError(f"invalid vocabulary mapping: {field}")
        for label, index in mapping.items():
            if not isinstance(label, str) or isinstance(index, bool) or not isinstance(index, int):
                raise ValueError(f"non-integer vocabulary mapping index: {field}")
            if not 0 <= index < size:
                raise ValueError(f"out-of-range vocabulary mapping index: {field}")
        sizes[field] = size
    return sizes


def build_vocabulary(category_path: str | Path) -> dict[str, Any]:
    source = json.loads(Path(category_path).read_text())
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in source["entries"]:
        grouped[row["attribute"]].append(row)
    result = {}
    for attribute, rows in grouped.items():
        rows.sort(key=lambda row: (int(row["source_order"]), str(row["category_key"]).encode("utf-8")))
        keys = [str(row["category_key"]) for row in rows]
        if len(keys) != len(set(keys)):
            raise ValueError(f"duplicate official category key: {attribute}")
        mapping = {key: index for index, key in enumerate(keys)}
        for index, row in enumerate(rows):
            for alias in [row.get("source_label"), row.get("source_code"), *(row.get("source_codes") or [])]:
                if alias is not None and str(alias) not in mapping:
                    mapping[str(alias)] = index
        result[attribute] = {"keys": keys, "mapping": mapping,
                             "missing": len(keys), "mask": len(keys) + 1, "size": len(keys) + 2}
    for attribute, rows in source["missing_markers"]["poi_by_level"].items():
        result[attribute]["missing_codes"] = sorted({str(row["code"]) for row in rows})
    if set(result) != VOCABULARY_FIELDS:
        raise ValueError("official category dictionary field mismatch")
    # Accepted P2 exact source alias: canonical A10 code 12 is exposed as A11.
    result["A11"]["mapping"]["블록구조"] = result["A11"]["mapping"]["12"]
    if source.get("oov_policy") != "hard_failure_no_oov_token":
        raise ValueError("official category dictionary OOV policy mismatch")
    if source.get("reserved_tokens") != ["MISSING", "MASK"]:
        raise ValueError("official category dictionary reserved-token mismatch")
    validate_vocabulary_contract(result)
    return result


def fit_training_preprocessing(catalog: ArtifactCatalog) -> dict[str, Any]:
    stats = {key: RunningStats() for key in (
        "building_observed_area_m2", "building_observed_gross_floor_area_m2", "road_lanes",
        "object_dem_mean_m", "object_dem_sd_m", "scene_dem_mean_m",
    )}
    training_scenes = set(catalog.k8)
    for branch_id in sorted({catalog.p3_by_scene[scene]["branch_id"] for scene in training_scenes}):
        example = next(row for row in catalog.p3_rows if row["branch_id"] == branch_id)
        tar_path = catalog.roots["p3"] / "shards" / branch_id / example["payload_filename"]
        catalog._verify(tar_path, example["payload_sha256"])
        with tarfile.open(tar_path) as archive:
            buildings = [row for row in _table(archive, "vector/building_observed.parquet") if row["scene_id"] in training_scenes]
            roads = [row for row in _table(archive, "vector/road_observed.parquet") if row["scene_id"] in training_scenes]
            contexts = [row for row in _table(archive, "raster/object_raster_context.parquet") if row["scene_id"] in training_scenes]
            stats["building_observed_area_m2"].add_many(math.log1p(float(row["observed_area_m2"])) for row in buildings if row["observed_area_m2"] is not None and row["observed_area_m2"] > 0)
            stats["building_observed_gross_floor_area_m2"].add_many(math.log1p(float(row["observed_gross_floor_area_m2"])) for row in buildings if row["observed_gross_floor_area_m2"] is not None and row["observed_gross_floor_area_m2"] >= 0)
            stats["road_lanes"].add_many(float(row["LANES"]) for row in roads if row["LANES"] is not None and row["LANES"] > 0)
            stats["object_dem_mean_m"].add_many(float(row["dem_mean_m"]) for row in contexts if row["dem_mean_m"] is not None)
            stats["object_dem_sd_m"].add_many(float(row["dem_sd_m"]) for row in contexts if row["dem_sd_m"] is not None and row["dem_sd_m"] >= 0)
        with tempfile.TemporaryDirectory(prefix="p6-fit-") as temporary:
            with tarfile.open(tar_path) as archive:
                members = [member for member in archive.getmembers() if member.name.startswith("raster/scene_dem.zarr/")]
                archive.extractall(temporary, members=members, filter="data")
                scene_rows = _table(archive, "raster/scene_raster_index.parquet")
            group = zarr.open_group(str(Path(temporary) / "raster/scene_dem.zarr"), mode="r")
            for row in scene_rows:
                if row["scene_id"] not in training_scenes:
                    continue
                index = int(row["zarr_index"])
                values = np.asarray(group["raw_mean_m"][index], dtype=np.float64)
                valid = np.asarray(group["valid_mask"][index], dtype=bool)
                stats["scene_dem_mean_m"].add_many(values[valid].tolist())
    return {"fit_split": "training", "scene_count": len(training_scenes),
            "fields": {key: value.result() for key, value in stats.items()}}


def _standardize(value: Any, key: str, preprocessing: dict[str, Any], transform: str = "identity") -> tuple[float, int]:
    if value is None or not math.isfinite(float(value)):
        return 0.0, 1
    numeric = float(value)
    if transform == "log1p":
        numeric = math.log1p(numeric)
    stats = preprocessing["fields"][key]
    return (numeric - float(stats["mean"])) / float(stats["scale"]), 0


def _extract_raster(archive_path: Path, scene_id: str) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    with tempfile.TemporaryDirectory(prefix="p6-raster-") as temporary:
        with tarfile.open(archive_path) as archive:
            index_rows = _table(archive, "raster/scene_raster_index.parquet", scene_id)
            if len(index_rows) != 1:
                raise ValueError("scene raster index mismatch")
            members = [member for member in archive.getmembers() if member.name.startswith(("raster/scene_landcover.zarr/", "raster/scene_dem.zarr/"))]
            archive.extractall(temporary, members=members, filter="data")
        index = int(index_rows[0]["zarr_index"])
        lc = zarr.open_group(str(Path(temporary) / "raster/scene_landcover.zarr"), mode="r")
        dem = zarr.open_group(str(Path(temporary) / "raster/scene_dem.zarr"), mode="r")
        arrays = {
            "landcover_class_fraction": np.asarray(lc["class_fraction"][index], dtype=np.float32),
            "landcover_valid_mask": np.asarray(lc["valid_mask"][index], dtype=np.uint8),
            "landcover_intentional_mask": np.zeros_like(np.asarray(lc["valid_mask"][index], dtype=np.uint8)),
            "landcover_valid_support": np.asarray(lc["valid_support_ratio"][index], dtype=np.float32),
            "dem_raw_mean": np.asarray(dem["raw_mean_m"][index], dtype=np.float64),
            "dem_valid_mask": np.asarray(dem["valid_mask"][index], dtype=np.uint8),
            "dem_valid_support": np.asarray(dem["valid_support_ratio"][index], dtype=np.float32),
        }
    return arrays, index_rows[0]


def read_original_scene(catalog: ArtifactCatalog, scene_id: str) -> dict[str, Any]:
    path, parent = catalog.p3_tar(scene_id)
    with tarfile.open(path) as archive:
        vectors = []
        for entity_type, name in (("B", "building"), ("R", "road"), ("P", "poi")):
            for row in _table(archive, f"vector/{name}_observed.parquet", scene_id):
                row = dict(row); row["entity_type"] = entity_type
                vectors.append(row)
        contexts = {int(row["local_entity_id"]): row for row in _table(archive, "raster/object_raster_context.parquet", scene_id)}
        relations = _table(archive, "relations/relation_edges.parquet", scene_id)
        topology = _table(archive, "topology/source_topology.parquet", scene_id)
    rasters, raster_index = _extract_raster(path, scene_id)
    if not vectors:
        split = raster_index["split"]
        center = ((raster_index["xmin"] + raster_index["xmax"]) / 2, (raster_index["ymin"] + raster_index["ymax"]) / 2)
    else:
        split = vectors[0]["split"]
        center = (vectors[0]["scene_center_x_5186"], vectors[0]["scene_center_y_5186"])
    return {"scene_id": scene_id, "split": split, "view_id": "original", "profile": None,
            "positive_scene_id": scene_id, "parent": parent, "entities": sorted(vectors, key=lambda row: int(row["local_entity_id"])),
            "contexts": contexts, "relations": relations, "topology": topology, "rasters": rasters,
            "center": center, "bounds": [raster_index[key] for key in ("xmin", "ymin", "xmax", "ymax")]}


def _delta_tables(path: Path, identity_field: str, identity: str) -> dict[str, list[dict[str, Any]]]:
    names = ("removals", "geometry", "attributes", "context", "raster", "relation_delta", "topology", "absorption")
    with tarfile.open(path) as archive:
        return {name: _table(archive, f"{name}.parquet", identity_field=identity_field, identity=identity) for name in names}


def apply_delta(original: dict[str, Any], delta: dict[str, list[dict[str, Any]]], identity: str,
                profile: str, query_index: int | None = None) -> dict[str, Any]:
    removed = {int(row["local_entity_id"]) for row in delta["removals"]}
    entities = {int(row["local_entity_id"]): dict(row) for row in original["entities"] if int(row["local_entity_id"]) not in removed}
    for row in delta["geometry"]:
        local = int(row["local_entity_id"])
        if local not in entities:
            raise ValueError("geometry override references removed/unknown entity")
        target = entities[local]
        target["observed_geometry"] = bytes(row["geometry_wkb"])
        target["observed_center_x_5186"] = row["center_x"]
        target["observed_center_y_5186"] = row["center_y"]
        target["relative_center_x_m"] = row["relative_x"]
        target["relative_center_y_m"] = row["relative_y"]
        if target["entity_type"] == "B":
            target["observed_area_m2"] = row["observed_area_m2"]
            target["observed_gross_floor_area_m2"] = row["observed_gross_floor_area_m2"]
        elif target["entity_type"] == "R":
            target["observed_length_m"] = row["length_m"]
    for row in delta["attributes"]:
        local = int(row["local_entity_id"])
        if local not in entities:
            raise ValueError("attribute override references removed/unknown entity")
        value = row["augmented"]
        entities[local][row["field"]] = None if value == "MASK" else value
        entities[local].setdefault("masked_fields", set())
        if value == "MASK":
            entities[local]["masked_fields"].add(row["field"].removesuffix("_CODE"))
    contexts = {key: value for key, value in original["contexts"].items() if key in entities}
    for row in delta["context"]:
        contexts[int(row["local_entity_id"])] = row
    relations = {(int(row["source_local_entity_id"]), int(row["destination_local_entity_id"]), name): True
                 for row in original["relations"] for name, bit in RELATION_BITS.items() if int(row["relation_mask"]) & bit
                 if int(row["source_local_entity_id"]) in entities and int(row["destination_local_entity_id"]) in entities}
    for row in delta["relation_delta"]:
        key = (int(row["source"]), int(row["destination"]), row["relation_type"])
        if row["action"] == "REMOVE": relations.pop(key, None)
        elif row["action"] == "ADD": relations[key] = True
        else: raise ValueError("unknown relation delta action")
    grouped: dict[tuple[int, int], int] = defaultdict(int)
    for source, destination, relation_type in relations:
        if source not in entities or destination not in entities or source == destination:
            raise ValueError("augmented relation endpoint invariant failure")
        grouped[(source, destination)] |= RELATION_BITS[relation_type]
    relation_rows = [{"source_local_entity_id": source, "destination_local_entity_id": destination, "relation_mask": mask}
                     for (source, destination), mask in sorted(grouped.items())]
    topology = [row for row in original["topology"] if int(row["road_local_entity_id"]) in entities]
    receivers = {int(row["receiver_local_entity_id"]) for row in delta["topology"]}
    topology = [row for row in topology if int(row["road_local_entity_id"]) not in receivers]
    for row in delta["topology"]:
        topology.append({"road_local_entity_id": int(row["receiver_local_entity_id"]), "road_id": row["receiver_source_road_id"],
                         "source_road_link_id": row["component_source_road_id"], "road_type": None, "road_hierarchy": None,
                         "source_node_position": int(row["chain_position"]), "source_node_id": row["source_node_id"],
                         "source_node_x_5186": row["x"], "source_node_y_5186": row["y"],
                         "source_node_offset_start": row["chain_offset_start"], "source_node_offset_end": row["chain_offset_end"],
                         "component_index": row["component_index"], "source_chain_index": row["source_chain_index"]})
    rasters = {key: np.array(value, copy=True) for key, value in original["rasters"].items()}
    for row in delta["raster"]:
        index = int(row["flat_index"])
        if row["modality"] == "landcover":
            y, x = divmod(index, 100); rasters["landcover_class_fraction"][:, y, x] = 0
            rasters["landcover_valid_mask"][y, x] = 0
            rasters["landcover_intentional_mask"][y, x] = 1
        elif row["modality"] == "dem":
            y, x = divmod(index, 17); rasters["dem_raw_mean"][y, x] = float(row["value"])
        else: raise ValueError("unknown augmented raster modality")
    return {**original, "view_id": identity, "profile": profile, "query_index": query_index,
            "entities": [entities[key] for key in sorted(entities)], "contexts": contexts,
            "relations": relation_rows, "topology": topology, "rasters": rasters}


def read_training_view(catalog: ArtifactCatalog, scene_id: str, master_view_id: int) -> dict[str, Any]:
    eligible = {int(row["master_view_id"]): row for row in catalog.k8[scene_id]}
    if master_view_id not in eligible:
        raise ValueError("training view is not a main-profile logical K8 member")
    row = eligible[master_view_id]
    path, _ = catalog.p4_tar(scene_id)
    return apply_delta(read_original_scene(catalog, scene_id), _delta_tables(path, "candidate_id", row["candidate_id"]),
                       row["candidate_id"], "main_1.0x")


def read_fixed_query(catalog: ArtifactCatalog, split: str, scene_id: str, query_index: int) -> dict[str, Any]:
    matches = [row for row in catalog.query_rows[split] if row["scene_id"] == scene_id and int(row["query_index"]) == query_index]
    if len(matches) != 1:
        raise ValueError("fixed query lookup is missing or ambiguous")
    row = matches[0]
    result = apply_delta(read_original_scene(catalog, scene_id), _delta_tables(catalog.p5_tar(row), "query_id", row["query_id"]),
                         row["query_id"], row["profile_id"], query_index)
    result["positive_scene_id"] = row["positive_scene_id"]
    return result


def _category(vocab: dict[str, Any], attribute: str, value: Any, masked: bool = False) -> int:
    contract = vocab[attribute]
    if masked: return int(contract["mask"])
    if value is None or value == "": return int(contract["missing"])
    key = str(value)
    if key not in contract["mapping"]:
        raise ValueError(f"categorical OOV: {attribute}:{key}")
    return int(contract["mapping"][key])


def _poi_category_key(row: dict[str, Any], level: int, vocab: dict[str, Any]) -> str | None:
    codes = []
    for current in range(1, level + 1):
        attribute = f"CLASS_L{current}"
        code = row.get(f"{attribute}_CODE")
        if code is None or str(code).strip() == "" or str(code) in vocab[attribute]["missing_codes"]:
            return None
        codes.append(str(code))
    return "/".join(codes)


def tensorize_scene(scene: dict[str, Any], preprocessing: dict[str, Any], vocab: dict[str, Any]) -> dict[str, Any]:
    entities = scene["entities"]
    local_ids = [int(row["local_entity_id"]) for row in entities]
    if local_ids != sorted(local_ids) or len(local_ids) != len(set(local_ids)):
        raise ValueError("entity local ordering/identity mismatch")
    id_to_row = {local: index for index, local in enumerate(local_ids)}
    types = np.asarray([TYPE_CODES[row["entity_type"]] for row in entities], dtype=np.int64)
    relative = np.asarray([[row["relative_center_x_m"], row["relative_center_y_m"]] for row in entities], dtype=np.float32).reshape((-1, 2))
    contexts = scene["contexts"]
    background = np.zeros((len(entities), 26), dtype=np.float32)
    for index, row in enumerate(entities):
        context = contexts.get(int(row["local_entity_id"]))
        if context:
            background[index, :22] = [float(context[f"lc_fraction_{value:02d}"] or 0) for value in range(1, 23)]
            background[index, 22] = float(context["lc_valid_support_ratio"] or 0)
            background[index, 23] = _standardize(context["dem_mean_m"], "object_dem_mean_m", preprocessing)[0]
            background[index, 24] = _standardize(context["dem_sd_m"], "object_dem_sd_m", preprocessing)[0]
            background[index, 25] = float(context["dem_valid_support_ratio"] or 0)
    building_rows = [i for i, row in enumerate(entities) if row["entity_type"] == "B"]
    road_rows = [i for i, row in enumerate(entities) if row["entity_type"] == "R"]
    poi_rows = [i for i, row in enumerate(entities) if row["entity_type"] == "P"]
    building_category, building_num, building_missing = [], [], []
    for index in building_rows:
        row = entities[index]; masked = row.get("masked_fields", set())
        building_category.append([_category(vocab, "A9", row.get("A9"), "A9" in masked), _category(vocab, "A11", row.get("A11"), "A11" in masked)])
        values = [_standardize(row.get("observed_area_m2"), "building_observed_area_m2", preprocessing, "log1p"),
                  _standardize(row.get("observed_gross_floor_area_m2"), "building_observed_gross_floor_area_m2", preprocessing, "log1p")]
        building_num.append([v[0] for v in values]); building_missing.append([v[1] for v in values])
    road_category, road_num, road_missing = [], [], []
    for index in road_rows:
        row = entities[index]; masked = row.get("masked_fields", set())
        road_category.append([_category(vocab, "ROAD_RANK", row.get("ROAD_RANK"), "ROAD_RANK" in masked), _category(vocab, "ROAD_TYPE", row.get("ROAD_TYPE"), "ROAD_TYPE" in masked)])
        value = _standardize(row.get("LANES"), "road_lanes", preprocessing)
        road_num.append([value[0]]); road_missing.append([value[1]])
    poi_category = []
    for index in poi_rows:
        row = entities[index]; masked = row.get("masked_fields", set())
        values = []
        for level in range(1, 7):
            attribute = f"CLASS_L{level}"
            values.append(_category(vocab, attribute, _poi_category_key(row, level, vocab), attribute in masked))
        poi_category.append(values)
    part_coordinates, entity_offsets, part_offsets, entity_part_offsets = [], [0], [0], [0]
    ring_coordinates = []
    ring_start, ring_end, ring_hole, ring_component, entity_ring_offsets = [], [], [], [], [0]
    geometry_types, available = [], []
    for row in entities:
        geometry = shapely.from_wkb(bytes(row["observed_geometry"]))
        parts, rings, component_indices = geometry_parts(geometry)
        geometry_types.append({"Point": 0, "MultiPoint": 1, "LineString": 2, "MultiLineString": 3, "Polygon": 4, "MultiPolygon": 5}[geometry.geom_type])
        available.append(row["entity_type"] != "P")
        center = np.asarray([row["observed_center_x_5186"], row["observed_center_y_5186"]], dtype=np.float64)
        for part in parts:
            values = np.asarray(part, dtype=np.float64)
            part_coordinates.extend((values - center).tolist()); part_offsets.append(len(part_coordinates))
        entity_offsets.append(len(part_coordinates)); entity_part_offsets.append(len(part_offsets) - 1)
        for (ring, is_hole), component in zip(rings, component_indices, strict=True):
            values = np.asarray(ring, dtype=np.float64); start = len(ring_coordinates)
            ring_coordinates.extend((values - center).tolist()); end = len(ring_coordinates)
            ring_start.append(start); ring_end.append(end); ring_hole.append(is_hole); ring_component.append(entity_part_offsets[-2] + component)
        entity_ring_offsets.append(len(ring_hole))
    edge_groups: dict[tuple[int, int], int] = defaultdict(int)
    for row in scene["relations"]:
        source = int(row["source_local_entity_id"]); destination = int(row["destination_local_entity_id"])
        if source not in id_to_row or destination not in id_to_row or source == destination:
            raise ValueError("relation endpoint out of bounds/self-edge")
        edge_groups[(id_to_row[source], id_to_row[destination])] |= int(row["relation_mask"])
    edge_keys = sorted(edge_groups)
    topology_rows = sorted(scene["topology"], key=lambda row: (id_to_row.get(int(row["road_local_entity_id"]), 10**12), int(row.get("component_index", 0)), int(row.get("source_chain_index", 0)), int(row["source_node_position"])))
    chain_groups: dict[tuple[int, int, int], list[dict[str, Any]]] = defaultdict(list)
    for row in topology_rows:
        local = int(row["road_local_entity_id"])
        if local not in id_to_row: raise ValueError("topology references missing road")
        chain_groups[(id_to_row[local], int(row.get("component_index", 0)), int(row.get("source_chain_index", 0)))].append(row)
    source_node_xy, source_node_ids, source_chain_offsets, source_chain_road = [], [], [0], []
    for key in sorted(chain_groups):
        rows = chain_groups[key]
        positions = [int(row["source_node_position"]) for row in rows]
        if positions != list(range(len(rows))): raise ValueError("source-node chain position mismatch")
        source_chain_road.append(key[0])
        for row in rows:
            source_node_xy.append([row["source_node_x_5186"], row["source_node_y_5186"]]); source_node_ids.append(str(row["source_node_id"]))
        source_chain_offsets.append(len(source_node_ids))
    rasters = scene["rasters"]
    dem = np.asarray(rasters["dem_raw_mean"], dtype=np.float64)
    valid_dem = np.asarray(rasters["dem_valid_mask"], dtype=bool)
    dem_stats = preprocessing["fields"]["scene_dem_mean_m"]
    dem_standardized = np.zeros((17, 17), dtype=np.float32)
    dem_standardized[valid_dem] = ((dem[valid_dem] - dem_stats["mean"]) / dem_stats["scale"]).astype(np.float32)
    sample = {
        "scene_id": scene["scene_id"], "split": scene["split"], "view_id": scene["view_id"], "profile": scene["profile"],
        "geometry_layout_version": GEOMETRY_LAYOUT_VERSION,
        "positive_scene_id": scene["positive_scene_id"], "lineage": {"parent": scene["parent"]},
        "entities": {
            "local_entity_id": torch.tensor(local_ids), "entity_type": torch.tensor(types),
            "relative_position_m": torch.tensor(relative), "object_raster": torch.tensor(background),
            "modality_available": torch.tensor([[1, int(kind != 2), 1, 1] for kind in types], dtype=torch.uint8),
            "building_row_index": torch.tensor(building_rows, dtype=torch.int64), "building_category": torch.tensor(building_category, dtype=torch.int64).reshape((-1, 2)),
            "building_numerical": torch.tensor(building_num, dtype=torch.float32).reshape((-1, 2)), "building_missing": torch.tensor(building_missing, dtype=torch.uint8).reshape((-1, 2)),
            "road_row_index": torch.tensor(road_rows, dtype=torch.int64), "road_category": torch.tensor(road_category, dtype=torch.int64).reshape((-1, 2)),
            "road_numerical": torch.tensor(road_num, dtype=torch.float32).reshape((-1, 1)), "road_missing": torch.tensor(road_missing, dtype=torch.uint8).reshape((-1, 1)),
            "poi_row_index": torch.tensor(poi_rows, dtype=torch.int64), "poi_category": torch.tensor(poi_category, dtype=torch.int64).reshape((-1, 6)),
        },
        "geometry": {
            "part_coordinates_xy_m": torch.tensor(part_coordinates, dtype=torch.float64).reshape((-1, 2)).to(torch.float32),
            "part_coordinates_xy_m_scientific": torch.tensor(part_coordinates, dtype=torch.float64).reshape((-1, 2)),
            "ring_coordinates_xy_m": torch.tensor(ring_coordinates, dtype=torch.float64).reshape((-1, 2)).to(torch.float32),
            "ring_coordinates_xy_m_scientific": torch.tensor(ring_coordinates, dtype=torch.float64).reshape((-1, 2)),
            "geometry_type": torch.tensor(geometry_types), "geometry_available": torch.tensor(available, dtype=torch.uint8),
            "entity_coordinate_offsets": torch.tensor(entity_offsets), "entity_part_offsets": torch.tensor(entity_part_offsets),
            "part_coordinate_offsets": torch.tensor(part_offsets), "entity_component_offsets": torch.tensor(entity_part_offsets),
            "component_coordinate_offsets": torch.tensor(part_offsets), "entity_ring_offsets": torch.tensor(entity_ring_offsets),
            "ring_coordinate_start": torch.tensor(ring_start), "ring_coordinate_end": torch.tensor(ring_end),
            "ring_is_hole": torch.tensor(ring_hole, dtype=torch.uint8), "ring_component_index": torch.tensor(ring_component),
        },
        "edges": {"edge_index": (torch.tensor(edge_keys, dtype=torch.int64).T if edge_keys else torch.empty((2, 0), dtype=torch.int64)),
                  "relation_mask": torch.tensor([edge_groups[key] for key in edge_keys], dtype=torch.uint8)},
        "topology": {"source_chain_offsets": torch.tensor(source_chain_offsets), "source_chain_road_index": torch.tensor(source_chain_road),
                     "source_node_xy_5186": torch.tensor(source_node_xy, dtype=torch.float64).reshape((-1, 2)), "source_node_ids": source_node_ids},
        "rasters": {"landcover_class_fraction": torch.tensor(rasters["landcover_class_fraction"], dtype=torch.float32),
                    "landcover_valid_mask": torch.tensor(rasters["landcover_valid_mask"], dtype=torch.uint8),
                    "landcover_intentional_mask": torch.tensor(rasters["landcover_intentional_mask"], dtype=torch.uint8),
                    "landcover_valid_support": torch.tensor(rasters["landcover_valid_support"], dtype=torch.float32),
                    "dem_standardized_mean": torch.tensor(dem_standardized), "dem_valid_mask": torch.tensor(rasters["dem_valid_mask"], dtype=torch.uint8),
                    "dem_valid_support": torch.tensor(rasters["dem_valid_support"], dtype=torch.float32)},
    }
    sample["resources"] = {"nodes": len(entities), "ordered_edges": len(edge_keys),
                           "part_coordinates": len(part_coordinates), "ring_coordinates": len(ring_coordinates),
                           "coordinates": len(part_coordinates) + len(ring_coordinates),
                           "source_nodes": len(source_node_ids)}
    validate_geometry_layout(sample)
    return sample


def _validate_intervals(starts: torch.Tensor, ends: torch.Tensor, length: int, label: str) -> None:
    if starts.shape != ends.shape:
        raise ValueError(f"{label} interval shape mismatch")
    if starts.numel() and bool(((starts < 0) | (starts > ends) | (ends > length)).any()):
        raise ValueError(f"{label} interval is outside its storage")


def validate_geometry_layout(value: dict[str, Any]) -> None:
    """Validate the incompatible P6 v3 split part/ring coordinate layout."""
    version = value.get("geometry_layout_version")
    if version != GEOMETRY_LAYOUT_VERSION:
        raise ValueError(
            f"incompatible P6 geometry layout: expected {GEOMETRY_LAYOUT_VERSION}, got {version!r}"
        )
    geometry = value.get("geometry", {})
    required = {
        "part_coordinates_xy_m", "part_coordinates_xy_m_scientific",
        "ring_coordinates_xy_m", "ring_coordinates_xy_m_scientific",
        "entity_coordinate_offsets", "part_coordinate_offsets", "component_coordinate_offsets",
        "ring_coordinate_start", "ring_coordinate_end",
    }
    missing = sorted(required - set(geometry))
    if missing:
        raise ValueError(f"P6 geometry layout fields are missing: {missing}")
    part_length = int(geometry["part_coordinates_xy_m"].shape[0])
    ring_length = int(geometry["ring_coordinates_xy_m"].shape[0])
    if geometry["part_coordinates_xy_m_scientific"].shape != geometry["part_coordinates_xy_m"].shape:
        raise ValueError("part scientific/model coordinate shapes differ")
    if geometry["ring_coordinates_xy_m_scientific"].shape != geometry["ring_coordinates_xy_m"].shape:
        raise ValueError("ring scientific/model coordinate shapes differ")
    for key in ("entity_coordinate_offsets", "part_coordinate_offsets", "component_coordinate_offsets"):
        offsets = geometry[key]
        if offsets.numel() == 0 or int(offsets[0]) != 0 or int(offsets[-1]) != part_length:
            raise ValueError(f"{key} terminal does not match part-coordinate storage")
        if bool((offsets[1:] < offsets[:-1]).any()):
            raise ValueError(f"{key} is not monotone")
    _validate_intervals(geometry["ring_coordinate_start"], geometry["ring_coordinate_end"], ring_length, "ring")
    if geometry["ring_coordinate_start"].numel():
        if int(geometry["ring_coordinate_start"][0]) != 0 or int(geometry["ring_coordinate_end"][-1]) != ring_length:
            raise ValueError("ring intervals do not cover ring-coordinate storage")
        if not torch.equal(geometry["ring_coordinate_start"][1:], geometry["ring_coordinate_end"][:-1]):
            raise ValueError("ring intervals are not contiguous")


def ragged_collate(samples: Sequence[dict[str, Any]]) -> dict[str, Any]:
    if not samples: raise ValueError("cannot collate empty batch")
    for sample in samples:
        validate_geometry_layout(sample)
    node_counts = [sample["resources"]["nodes"] for sample in samples]
    part_coordinate_counts = [sample["resources"]["part_coordinates"] for sample in samples]
    ring_coordinate_counts = [sample["resources"]["ring_coordinates"] for sample in samples]
    part_counts = [sample["geometry"]["part_coordinate_offsets"].numel() - 1 for sample in samples]
    ring_counts = [sample["geometry"]["ring_is_hole"].numel() for sample in samples]
    chain_counts = [sample["topology"]["source_chain_offsets"].numel() - 1 for sample in samples]
    source_node_counts = [sample["resources"]["source_nodes"] for sample in samples]
    ptr = lambda counts: torch.tensor([0, *np.cumsum(counts).tolist()], dtype=torch.int64)
    scene_ptr, part_coordinate_ptr, ring_coordinate_ptr, part_ptr, ring_ptr, chain_ptr, source_node_ptr = map(
        ptr, (node_counts, part_coordinate_counts, ring_coordinate_counts, part_counts, ring_counts, chain_counts, source_node_counts))
    entities = {}
    for key in ("local_entity_id", "entity_type", "relative_position_m", "object_raster", "modality_available"):
        entities[key] = torch.cat([sample["entities"][key] for sample in samples])
    for prefix in ("building", "road", "poi"):
        row_key = f"{prefix}_row_index"
        entities[row_key] = torch.cat([sample["entities"][row_key] + scene_ptr[index] for index, sample in enumerate(samples)])
        for suffix in (("category",) if prefix == "poi" else ("category", "numerical", "missing")):
            entities[f"{prefix}_{suffix}"] = torch.cat([sample["entities"][f"{prefix}_{suffix}"] for sample in samples])
    geometry = {key: torch.cat([sample["geometry"][key] for sample in samples]) for key in (
        "part_coordinates_xy_m", "part_coordinates_xy_m_scientific", "ring_coordinates_xy_m",
        "ring_coordinates_xy_m_scientific", "geometry_type", "geometry_available", "ring_is_hole")}
    geometry["entity_coordinate_offsets"] = torch.cat([samples[0]["geometry"]["entity_coordinate_offsets"][:1], *[sample["geometry"]["entity_coordinate_offsets"][1:] + part_coordinate_ptr[index] for index, sample in enumerate(samples)]])
    for key in ("entity_part_offsets", "entity_component_offsets"):
        geometry[key] = torch.cat([samples[0]["geometry"][key][:1], *[sample["geometry"][key][1:] + part_ptr[index] for index, sample in enumerate(samples)]])
    for key in ("part_coordinate_offsets", "component_coordinate_offsets"):
        geometry[key] = torch.cat([samples[0]["geometry"][key][:1], *[sample["geometry"][key][1:] + part_coordinate_ptr[index] for index, sample in enumerate(samples)]])
    geometry["entity_ring_offsets"] = torch.cat([samples[0]["geometry"]["entity_ring_offsets"][:1], *[sample["geometry"]["entity_ring_offsets"][1:] + ring_ptr[index] for index, sample in enumerate(samples)]])
    geometry["ring_component_index"] = torch.cat([sample["geometry"]["ring_component_index"] + part_ptr[index] for index, sample in enumerate(samples)])
    for key in ("ring_coordinate_start", "ring_coordinate_end"):
        geometry[key] = torch.cat([sample["geometry"][key] + ring_coordinate_ptr[index] for index, sample in enumerate(samples)])
    edges = {"edge_index": torch.cat([sample["edges"]["edge_index"] + scene_ptr[index] for index, sample in enumerate(samples)], 1),
             "relation_mask": torch.cat([sample["edges"]["relation_mask"] for sample in samples])}
    topology = {"source_node_xy_5186": torch.cat([sample["topology"]["source_node_xy_5186"] for sample in samples]),
                "source_node_ids": [value for sample in samples for value in sample["topology"]["source_node_ids"]],
                "source_chain_road_index": torch.cat([sample["topology"]["source_chain_road_index"] + scene_ptr[index] for index, sample in enumerate(samples)])}
    topology["source_chain_offsets"] = torch.cat([samples[0]["topology"]["source_chain_offsets"][:1], *[sample["topology"]["source_chain_offsets"][1:] + source_node_ptr[index] for index, sample in enumerate(samples)]])
    rasters = {key: torch.stack([sample["rasters"][key] for sample in samples]) for key in samples[0]["rasters"]}
    batch = {"scene_ids": [sample["scene_id"] for sample in samples], "splits": [sample["split"] for sample in samples],
            "view_ids": [sample["view_id"] for sample in samples], "profiles": [sample["profile"] for sample in samples],
            "positive_scene_ids": [sample["positive_scene_id"] for sample in samples], "lineage": [sample["lineage"] for sample in samples],
            "geometry_layout_version": GEOMETRY_LAYOUT_VERSION,
            "scene_ptr": scene_ptr, "part_coordinate_ptr": part_coordinate_ptr,
            "ring_coordinate_ptr": ring_coordinate_ptr, "part_ptr": part_ptr, "ring_ptr": ring_ptr,
            "chain_ptr": chain_ptr, "source_node_ptr": source_node_ptr, "entities": entities, "geometry": geometry,
            "edges": edges, "topology": topology, "rasters": rasters,
            "entity_scene_index": torch.repeat_interleave(torch.arange(len(samples)), torch.tensor(node_counts))}
    validate_geometry_layout(batch)
    return batch


class DeterministicSceneSampler(Sampler[int]):
    def __init__(self, length: int, seed: int, epoch: int = 0, shuffle: bool = True) -> None:
        self.length, self.seed, self.epoch, self.shuffle = length, seed, epoch, shuffle
    def __iter__(self):
        if not self.shuffle: return iter(range(self.length))
        generator = torch.Generator().manual_seed(self.seed + self.epoch)
        return iter(torch.randperm(self.length, generator=generator).tolist())
    def __len__(self): return self.length


class ArtifactDataset(Dataset):
    def __init__(self, catalog: ArtifactCatalog, records: list[dict[str, Any]], preprocessing: dict[str, Any],
                 vocabulary: dict[str, Any]) -> None:
        self.catalog, self.records, self.preprocessing, self.vocabulary = catalog, records, preprocessing, vocabulary
    def __len__(self): return len(self.records)
    def __getitem__(self, index: int):
        record = self.records[index]
        if record["kind"] == "original": scene = read_original_scene(self.catalog, record["scene_id"])
        elif record["kind"] == "training_view": scene = read_training_view(self.catalog, record["scene_id"], record["view"])
        else: scene = read_fixed_query(self.catalog, record["split"], record["scene_id"], record["query_index"])
        return tensorize_scene(scene, self.preprocessing, self.vocabulary)
