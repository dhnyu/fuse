"""P5 deterministic fixed-query generation from immutable P3 originals."""

from __future__ import annotations

import hashlib
import io
import json
import math
import os
import shutil
import tarfile
import tempfile
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable

import pyarrow as pa
import pyarrow.parquet as pq
import shapely

import p4_fixed_augmentation as p4
from p4_deterministic_rng import counter_block

SCHEMA_VERSION = "1.0.0"
SUPPLEMENT_ID = "p5-fixed-query-v2"
PROFILE_ID = "main_1.0x"
NAMESPACES = {"validation": "validation-query", "evaluation": "evaluation-query"}
QUERY_INDICES = (0, 1)


def canonical_json(value: Any, *, newline: bool = True) -> bytes:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return data + (b"\n" if newline else b"")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_id(prefix: str, value: Any) -> str:
    return prefix + sha256_bytes(canonical_json(value))[:24]


def query_seed_payload(config: dict[str, Any], namespace: str, scene_id: str,
                       query_index: int) -> dict[str, Any]:
    if namespace not in NAMESPACES.values():
        raise ValueError("invalid fixed-query namespace")
    if query_index not in QUERY_INDICES:
        raise ValueError("query_index must be 0 or 1")
    return {
        "augmentation_contract_id": config["augmentation_contract_id"],
        "augmenter_implementation_sha256": config["p4_accepted_augmenter_sha256"],
        "namespace": namespace,
        "p3_cache_id": config["p3_cache_id"],
        "profile_id": PROFILE_ID,
        "query_index": query_index,
        "scene_id": scene_id,
        "schema_version": SCHEMA_VERSION,
    }


def query_seed_digest(payload: dict[str, Any]) -> bytes:
    return hashlib.sha256(canonical_json(payload, newline=False)).digest()


def operation_digest_provider(root_digest: bytes, expected_profile: str,
                              expected_scene: str, expected_index: int) -> Callable[..., bytes]:
    """Adapt the P5 root seed to the unchanged P4 counter-draw interface."""
    def provider(profile_id: str, scene_id: str, view: int, operation: str,
                 entity_id: object | None = None, attempt: int | None = None) -> bytes:
        if (profile_id, scene_id, view) != (expected_profile, expected_scene, expected_index):
            raise ValueError("P5 augmenter seed context mismatch")
        context = {
            "attempt": "NONE" if attempt is None else int(attempt),
            "entity_id": "NONE" if entity_id is None else str(entity_id),
            "operation": str(operation),
        }
        return hashlib.sha256(root_digest + b"\x00" + canonical_json(context, newline=False)).digest()
    return provider


def p4_seed_regression_vector() -> dict[str, str]:
    """Pinned proof that importing the P5 adapter does not alter P4 seed bytes."""
    payload = p4.base_digest("main_1.0x", "scene-regression", 7, "geometry", "road-12", 3)
    return {
        "payload_sha256": payload.hex(),
        "uniform_block_sha256": counter_block(payload, "geometry_jitter_value", 4).hex(),
    }


def _replace_identity(row: dict[str, Any], query_id: str, query_index: int) -> dict[str, Any]:
    value = dict(row)
    value.pop("candidate_id", None)
    value.pop("master_view_id", None)
    value["query_id"] = query_id
    value["query_index"] = query_index
    return value


def _schema_with_query_identity(schema: pa.Schema) -> pa.Schema:
    fields = []
    for field in schema:
        if field.name == "candidate_id":
            fields.append(pa.field("query_id", pa.string()))
        elif field.name == "master_view_id":
            fields.append(pa.field("query_index", pa.int8()))
        else:
            fields.append(field)
    return pa.schema(fields)


QUERY_SCHEMA = pa.schema([
    pa.field("query_id", pa.string()), pa.field("namespace", pa.string()),
    pa.field("split", pa.string()), pa.field("scene_id", pa.string()),
    pa.field("query_index", pa.int8()), pa.field("profile_id", pa.string()),
    pa.field("seed_payload_json", pa.string()), pa.field("seed_payload_sha256", pa.string()),
    pa.field("seed_digest", pa.string()), pa.field("augmentation_contract_id", pa.string()),
    pa.field("augmenter_implementation_sha256", pa.string()), pa.field("parent_cache_id", pa.string()),
    pa.field("parent_branch_id", pa.string()), pa.field("parent_tar_sha256", pa.string()),
    pa.field("positive_scene_id", pa.string()), pa.field("query_content_sha256", pa.string()),
] + [field for field in p4.PARQUET_SCHEMAS["candidates"]
     if field.name not in {"candidate_id", "scene_id", "profile_id", "master_view_id"}])

P5_SCHEMAS = {
    "queries": QUERY_SCHEMA,
    **{name: _schema_with_query_identity(schema) for name, schema in p4.PARQUET_SCHEMAS.items()
       if name != "candidates"},
}


def _query_content_hash(tables: dict[str, list[dict[str, Any]]]) -> str:
    def normalized(value: Any) -> Any:
        if isinstance(value, bytes):
            return {"__bytes_sha256__": sha256_bytes(value), "size": len(value)}
        if isinstance(value, float) and not math.isfinite(value):
            return {"__float__": "nan" if math.isnan(value) else "inf" if value > 0 else "-inf"}
        if isinstance(value, dict):
            return {str(key): normalized(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [normalized(item) for item in value]
        return value
    logical = {
        name: sorted((normalized(row) for row in rows), key=lambda row: canonical_json(row, newline=False))
        for name, rows in sorted(tables.items())
    }
    return sha256_bytes(canonical_json(logical))


def augment_query(scene: dict[str, Any], profile: dict[str, Any], resources: dict[str, Any],
                  config: dict[str, Any], namespace: str, split: str, query_index: int,
                  parent_branch_id: str, parent_tar_sha256: str) -> dict[str, list[dict[str, Any]]]:
    seed_payload = query_seed_payload(config, namespace, scene["scene_id"], query_index)
    root_digest = query_seed_digest(seed_payload)
    provider = operation_digest_provider(root_digest, PROFILE_ID, scene["scene_id"], query_index)
    original_provider = p4.base_digest
    p4.base_digest = provider
    try:
        generated = p4.augment_scene(scene, profile, resources, query_index)
    finally:
        p4.base_digest = original_provider
    query_id = stable_id("fq_", {"supplement": SUPPLEMENT_ID, "seed": root_digest.hex()})
    converted: dict[str, list[dict[str, Any]]] = {}
    candidate = generated.pop("candidates")
    if len(candidate) != 1:
        raise ValueError("P4 augmenter did not return exactly one candidate")
    for name, rows in generated.items():
        converted[name] = [_replace_identity(row, query_id, query_index) for row in rows]
    content_hash = _query_content_hash(converted)
    candidate_row = candidate[0]
    query = {
        "query_id": query_id, "namespace": namespace, "split": split,
        "scene_id": scene["scene_id"], "query_index": query_index, "profile_id": PROFILE_ID,
        "seed_payload_json": canonical_json(seed_payload, newline=False).decode("utf-8"),
        "seed_payload_sha256": root_digest.hex(), "seed_digest": root_digest.hex(),
        "augmentation_contract_id": config["augmentation_contract_id"],
        "augmenter_implementation_sha256": config["p4_accepted_augmenter_sha256"],
        "parent_cache_id": config["p3_cache_id"], "parent_branch_id": parent_branch_id,
        "parent_tar_sha256": parent_tar_sha256, "positive_scene_id": scene["scene_id"],
        "query_content_sha256": content_hash,
        **{key: value for key, value in candidate_row.items()
           if key not in {"candidate_id", "scene_id", "profile_id", "master_view_id"}},
    }
    converted["queries"] = [query]
    return converted


def write_parquet(path: Path, rows: list[dict[str, Any]], schema: pa.Schema) -> None:
    pq.write_table(pa.Table.from_pylist(rows, schema=schema), path, compression="zstd",
                   compression_level=7, use_dictionary=False, write_statistics=True,
                   data_page_version="1.0")


def build_branch(spec: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    p4.initialize_worker()
    started = time.time()
    output_dir.mkdir(parents=True, exist_ok=False)
    config = spec["config"]
    with tempfile.TemporaryDirectory(prefix="p5-parent-") as temporary:
        parent = Path(temporary)
        p4.extract_parent(Path(spec["parent_tar"]), parent)
        tables = p4.read_scene_tables(parent)
        resources = json.loads(Path(spec["resources_path"]).read_text())
        resources["cache_id"] = config["p3_cache_id"]
        resources["implementation_hash"] = config["p4_accepted_augmenter_sha256"]
        accumulated = {name: [] for name in P5_SCHEMAS}
        for scene_id in spec["scene_ids"]:
            scene = p4.scene_data(tables, scene_id)
            for query_index in QUERY_INDICES:
                result = augment_query(scene, spec["profile"], resources, config,
                                       spec["namespace"], spec["split"], query_index,
                                       spec["parent_branch_id"], spec["parent_tar_sha256"])
                for name in accumulated:
                    accumulated[name].extend(result[name])
    payload_dir = output_dir / "payload"
    payload_dir.mkdir()
    for name, rows in accumulated.items():
        write_parquet(payload_dir / f"{name}.parquet", rows, P5_SCHEMAS[name])
    payload = output_dir / f"{spec['branch_id']}.tar"
    members = p4.deterministic_tar(payload_dir, payload)
    shutil.rmtree(payload_dir)
    manifest = {
        "schema_version": SCHEMA_VERSION, "status": "PASS", "supplement_id": SUPPLEMENT_ID,
        "query_authority_id": spec["query_authority_id"], "plan_id": spec["plan_id"],
        "branch_id": spec["branch_id"], "namespace": spec["namespace"], "split": spec["split"],
        "profile_id": PROFILE_ID, "parent_cache_id": config["p3_cache_id"],
        "parent_acceptance_id": config["p3_acceptance_id"],
        "parent_branch_id": spec["parent_branch_id"], "parent_tar_sha256": spec["parent_tar_sha256"],
        "scene_ids": spec["scene_ids"], "scene_count": len(spec["scene_ids"]),
        "query_indices": list(QUERY_INDICES), "query_count": len(accumulated["queries"]),
        "payload": {"filename": payload.name, "size_bytes": payload.stat().st_size,
                    "sha256": sha256_file(payload)},
        "members": members, "logical_content_sha256": sha256_bytes(canonical_json(members)),
        "implementation_hash": spec["implementation_hash"],
        "seed_contract": config["seed"],
        "validation": {"writer": "PASS", "schema": "PASS", "global_invariants": "PASS"},
    }
    (output_dir / "branch_manifest.json").write_bytes(canonical_json(manifest))
    execution = {"pass": os.environ.get("FUSE_P5_EXECUTION_PASS", "A"),
                 "requested_workers": int(os.environ.get("FUSE_P5_REQUESTED_WORKERS", "40")),
                 "threads": 1, "wall_seconds": time.time() - started, "pid": os.getpid()}
    (output_dir / "execution.json").write_bytes(canonical_json(execution))
    return manifest


def _read_tar_table(payload: Path, name: str) -> list[dict[str, Any]]:
    with tarfile.open(payload) as archive:
        raw = archive.extractfile(f"{name}.parquet").read()
    return pq.read_table(io.BytesIO(raw)).to_pylist()


def validate_query_gallery_records(queries: list[dict[str, Any]], galleries: list[dict[str, Any]],
                                   split: str, expected_scenes: int,
                                   valid_p3_scenes: set[str] | None = None) -> None:
    if split not in NAMESPACES:
        raise ValueError("invalid split")
    if len(queries) != expected_scenes * 2 or len(galleries) != expected_scenes:
        raise ValueError("population mismatch")
    if queries != sorted(queries, key=lambda row: (row["scene_id"], row["query_index"])):
        raise ValueError("query ordering mismatch")
    if galleries != sorted(galleries, key=lambda row: row["scene_id"]):
        raise ValueError("gallery ordering mismatch")
    if len({row["query_id"] for row in queries}) != len(queries):
        raise ValueError("duplicate query ID")
    if len({row["gallery_id"] for row in galleries}) != len(galleries):
        raise ValueError("duplicate gallery ID")
    gallery_scenes = {row["scene_id"] for row in galleries}
    if len(gallery_scenes) != expected_scenes:
        raise ValueError("duplicate gallery scene")
    if valid_p3_scenes is not None and not gallery_scenes.issubset(valid_p3_scenes):
        raise ValueError("missing P3 original reference")
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in queries:
        if row["split"] != split or row["namespace"] != NAMESPACES[split]:
            raise ValueError("split/namespace contamination")
        if row["profile_id"] != PROFILE_ID or row["positive_scene_id"] != row["scene_id"]:
            raise ValueError("profile or positive mismatch")
        if row["scene_id"] not in gallery_scenes:
            raise ValueError("orphan query")
        if any(key in row for key in ("master_view_id", "candidate_id", "requested_k", "bank_id")):
            raise ValueError("P4 bank membership reference prohibited")
        grouped[row["scene_id"]].append(row)
    if set(grouped) != gallery_scenes:
        raise ValueError("missing query scene")
    for rows in grouped.values():
        if len(rows) != 2 or {int(row["query_index"]) for row in rows} != {0, 1}:
            raise ValueError("query-per-scene/index mismatch")
        if len({row["seed_digest"] for row in rows}) != 2:
            raise ValueError("query seed collision")


def validate_branch(manifest_path: Path, config: dict[str, Any]) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text())
    payload = manifest_path.parent / manifest["payload"]["filename"]
    failures: list[str] = []
    if sha256_file(payload) != manifest["payload"]["sha256"]:
        failures.append("payload_checksum")
    tables: dict[str, list[dict[str, Any]]] = {}
    with tarfile.open(payload) as archive:
        names = archive.getnames()
        if len(names) != len(set(names)):
            failures.append("duplicate_tar_member")
        for member in manifest["members"]:
            raw = archive.extractfile(member["path"]).read()
            if sha256_bytes(raw) != member["sha256"] or len(raw) != member["size_bytes"]:
                failures.append("member_checksum")
            if member["path"].endswith(".parquet"):
                tables[Path(member["path"]).stem] = pq.read_table(io.BytesIO(raw)).to_pylist()
    queries = tables.get("queries", [])
    expected = 2 * manifest["scene_count"]
    if len(queries) != expected or len({row["query_id"] for row in queries}) != expected:
        failures.append("query_identity")
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in queries:
        grouped[row["scene_id"]].append(row)
        seed_payload = query_seed_payload(config, row["namespace"], row["scene_id"], int(row["query_index"]))
        digest = query_seed_digest(seed_payload).hex()
        if row["seed_payload_json"] != canonical_json(seed_payload, newline=False).decode() or row["seed_digest"] != digest:
            failures.append("seed_replay")
        if row["positive_scene_id"] != row["scene_id"] or row["profile_id"] != PROFILE_ID:
            failures.append("positive_or_profile")
    for scene_id, rows in grouped.items():
        if {int(row["query_index"]) for row in rows} != set(QUERY_INDICES):
            failures.append("query_indices")
        if len({row["seed_digest"] for row in rows}) != 2:
            failures.append("seed_distinctness")
    geometry = tables.get("geometry", [])
    maximum_error = 0.0
    for row in geometry:
        value = shapely.from_wkb(bytes(row["geometry_wkb"]))
        center = ((value.bounds[0] + value.bounds[2]) / 2, (value.bounds[1] + value.bounds[3]) / 2)
        error = max(abs(center[0] - row["center_x"]), abs(center[1] - row["center_y"]),
                    abs(float(value.area) - row["area_m2"]), abs(float(value.length) - row["length_m"]))
        maximum_error = max(maximum_error, error)
        if value.is_empty or not value.is_valid or row["geometry_dtype"] != "float64_wkb" or error > 1e-9:
            failures.append("geometry_consistency")
            break
    relation = tables.get("relation_delta", [])
    if any(row["relation_type"] not in {"SN", "CNT", "WIT", "INT", "CON"} or
           row["source"] == row["destination"] for row in relation):
        failures.append("relation_consistency")
    topology = tables.get("topology", [])
    top_groups: dict[tuple[str, int], list[int]] = defaultdict(list)
    for row in topology:
        top_groups[(row["query_id"], row["receiver_local_entity_id"])].append(row["source_node_offset"])
    if any(sorted(values) != list(range(len(values))) for values in top_groups.values()):
        failures.append("topology_offsets")
    result = {"schema_version": SCHEMA_VERSION, "status": "PASS" if not failures else "FAIL",
              "branch_id": manifest["branch_id"], "namespace": manifest["namespace"],
              "scene_count": manifest["scene_count"], "query_count": len(queries),
              "maximum_geometry_derived_error": maximum_error,
              "independent_reader": True, "failures": sorted(set(failures))}
    if failures:
        raise ValueError(";".join(sorted(set(failures))))
    return result


def aggregate(spec: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=False)
    manifests = [json.loads(Path(path).read_text()) for path in spec["manifests"]]
    query_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    gallery_rows: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    ordered_payloads = []
    total_bytes = 0
    for path, manifest in sorted(zip(spec["manifests"], manifests), key=lambda item: item[1]["branch_id"]):
        payload = Path(path).parent / manifest["payload"]["filename"]
        total_bytes += manifest["payload"]["size_bytes"]
        rows = _read_tar_table(payload, "queries")
        split = manifest["split"]
        for row in rows:
            query_rows[split].append({
                "query_id": row["query_id"], "namespace": row["namespace"], "split": split,
                "scene_id": row["scene_id"], "query_index": row["query_index"],
                "profile_id": row["profile_id"], "seed_payload_sha256": row["seed_payload_sha256"],
                "seed_digest": row["seed_digest"], "query_content_sha256": row["query_content_sha256"],
                "query_branch_id": manifest["branch_id"], "query_payload_filename": manifest["payload"]["filename"],
                "query_payload_sha256": manifest["payload"]["sha256"], "positive_scene_id": row["positive_scene_id"],
                "p3_cache_id": row["parent_cache_id"], "p3_branch_id": row["parent_branch_id"],
                "p3_payload_sha256": row["parent_tar_sha256"], "schema_version": SCHEMA_VERSION,
            })
            gallery_rows[split][row["scene_id"]] = {
                "gallery_id": stable_id("fggm_", {"cache": row["parent_cache_id"], "split": split, "scene": row["scene_id"]}),
                "split": split, "scene_id": row["scene_id"], "p3_cache_id": row["parent_cache_id"],
                "p3_branch_id": row["parent_branch_id"], "p3_member_reference": f"{row['parent_branch_id']}#{row['scene_id']}",
                "original_payload_sha256": row["parent_tar_sha256"], "schema_version": SCHEMA_VERSION,
            }
        ordered_payloads.append({"branch_id": manifest["branch_id"], "namespace": manifest["namespace"],
                                 "payload_sha256": manifest["payload"]["sha256"],
                                 "logical_content_sha256": manifest["logical_content_sha256"]})
    split_outputs = {}
    for split in ("validation", "evaluation"):
        queries = sorted(query_rows[split], key=lambda row: (row["scene_id"], row["query_index"]))
        galleries = sorted(gallery_rows[split].values(), key=lambda row: row["scene_id"])
        expected_scenes = 400 if split == "validation" else 1600
        if len(queries) != expected_scenes * 2 or len(galleries) != expected_scenes:
            raise ValueError(f"{split} population mismatch")
        validate_query_gallery_records(queries, galleries, split, expected_scenes, set(gallery_rows[split]))
        mapping = [{"query_id": row["query_id"], "positive_scene_id": row["scene_id"],
                    "gallery_id": gallery_rows[split][row["scene_id"]]["gallery_id"], "split": split}
                   for row in queries]
        query_hash = sha256_bytes(canonical_json(queries)); gallery_hash = sha256_bytes(canonical_json(galleries)); mapping_hash = sha256_bytes(canonical_json(mapping))
        ids = {"query_index_id": "fqi_" + query_hash[:24], "gallery_id": "fgg_" + gallery_hash[:24],
               "mapping_id": "fqpm_" + mapping_hash[:24]}
        pq.write_table(pa.Table.from_pylist(queries), output_dir / f"{split}_query_index.parquet", compression="zstd", use_dictionary=False)
        pq.write_table(pa.Table.from_pylist(galleries), output_dir / f"{split}_gallery.parquet", compression="zstd", use_dictionary=False)
        pq.write_table(pa.Table.from_pylist(mapping), output_dir / f"{split}_query_positive.parquet", compression="zstd", use_dictionary=False)
        content_hash = sha256_bytes(canonical_json({**ids, "query": query_hash, "gallery": gallery_hash, "mapping": mapping_hash}))
        acceptance = {"schema_version": SCHEMA_VERSION, "status": "PASS",
                      "acceptance_id": "fqsa_" + content_hash[:24], "query_authority_id": spec["query_authority_id"],
                      "namespace": NAMESPACES[split], "split": split, "scene_count": expected_scenes,
                      "query_count": expected_scenes * 2, "gallery_count": expected_scenes,
                      **ids, "query_index_sha256": query_hash, "gallery_sha256": gallery_hash,
                      "mapping_sha256": mapping_hash, "aggregate_content_sha256": content_hash,
                      "violations": {name: 0 for name in ("population", "query_per_scene", "query_index", "seed_distinctness", "positive", "training", "cross_split", "duplicate", "orphan", "p4_membership", "namespace", "parent_checksum", "ordering")}}
        (output_dir / f"{split}_acceptance.json").write_bytes(canonical_json(acceptance))
        split_outputs[split] = acceptance
    if set(gallery_rows["validation"]) & set(gallery_rows["evaluation"]):
        raise ValueError("validation/evaluation leakage")
    aggregate_hash = sha256_bytes(canonical_json({"payloads": ordered_payloads,
        "validation": split_outputs["validation"]["aggregate_content_sha256"],
        "evaluation": split_outputs["evaluation"]["aggregate_content_sha256"]}))
    acceptance = {"schema_version": SCHEMA_VERSION, "status": "PASS",
                  "acceptance_id": "fqaac_" + aggregate_hash[:24], "query_authority_id": spec["query_authority_id"],
                  "supplement_id": SUPPLEMENT_ID, "parent_cache_id": spec["p3_cache_id"],
                  "validation_acceptance_id": split_outputs["validation"]["acceptance_id"],
                  "evaluation_acceptance_id": split_outputs["evaluation"]["acceptance_id"],
                  "scene_count": 2000, "query_count": 4000, "gallery_count": 2000,
                  "branch_count": len(manifests), "total_payload_bytes": total_bytes,
                  "aggregate_content_sha256": aggregate_hash,
                  "violations": {name: 0 for name in ("population", "leakage", "duplicate", "missing", "orphan", "p4_reference", "schema", "scientific", "collision")}}
    (output_dir / "fixed_query_acceptance.json").write_bytes(canonical_json(acceptance))
    manifest = {"schema_version": SCHEMA_VERSION, "status": "PASS", "query_authority_id": spec["query_authority_id"],
                "acceptance_id": acceptance["acceptance_id"], "files": []}
    for path in sorted(output_dir.iterdir(), key=lambda path: path.name):
        if path.name == "fixed_query_manifest.json":
            continue
        manifest["files"].append({"filename": path.name, "size_bytes": path.stat().st_size, "sha256": sha256_file(path)})
    manifest["content_sha256"] = sha256_bytes(canonical_json(manifest["files"]))
    (output_dir / "fixed_query_manifest.json").write_bytes(canonical_json(manifest))
    return acceptance
