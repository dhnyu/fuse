"""Accepted P3 original-scene ingestion, dissertation 5.4 / frozen D1-D5.

Python authenticates tar/Zarr/Arrow transport; R/sf computes vector descriptors.
Only selected scenes are materialized. No model input or learned feature reader.
"""
from __future__ import annotations
import io
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import time
import resource
import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
import zarr
from numcodecs import blosc
from representation_analysis import ROOT, file_sha256
from s11_artifacts import (assert_population, configuration, dumps, load_bundle,
    payload, publish, read_json, require, write_json)

TABLES = {"building": "vector/building_observed.parquet", "road": "vector/road_observed.parquet",
    "poi": "vector/poi_observed.parquet", "edges": "relations/relation_edges.parquet",
    "nodes": "relations/relation_node_index.parquet", "statistics": "relations/scene_relation_statistics.parquet",
    "raster_index": "raster/scene_raster_index.parquet"}

def reader_threads():
    pa.set_cpu_count(1)
    pa.set_io_thread_count(1)
    blosc.set_nthreads(1)
    zarr.config.set({"async.concurrency": 1, "threading.max_workers": 1})

def p3_index():
    _, lock, execution = configuration()
    for pin in execution["p3_pins"].values():
        require(file_sha256(pin["path"]) == pin["sha256"], "P3_PARENT_HASH")
    accepted = read_json(execution["p3_pins"]["acceptance"]["path"])
    models = read_json(lock["parents"]["models"]["path"])
    require(models["body"]["roots"]["p3"] == execution["p3_root"] and accepted["status"] == "PASS" and
            accepted["split_counts"]["evaluation"] == 9000, "ACCEPTED_P3_LINEAGE")
    table = pq.read_table(execution["p3_pins"]["index"]["path"]).to_pylist()
    require(len({r["scene_id"] for r in table}) == len(table) == accepted["scene_count"], "P3_INDEX_UNIQUE")
    require(all(r["cache_id"] == accepted["cache_id"] for r in table), "P3_CACHE_ID")
    return {r["scene_id"]: r for r in table}

def make_plan(ctx, ids, accepted_ids, parents=()):
    _, _, execution = configuration()
    require(ids == sorted(set(ids)) and set(ids) <= set(accepted_ids), "PLAN_IDS")
    if ctx["scope"] == "full":
        assert_population(ids, accepted_ids)
        require(len(ids) == 9000, "PLAN_FULL_POPULATION")
    else:
        require(0 < len(ids) <= execution["pilot_scene_limit"], "DESCRIPTOR_PILOT_CAP")
    index = p3_index(); groups = {}
    for scene in ids:
        row = index[scene]; branch = row["branch_id"]
        require(row["payload_filename"] == branch + ".tar", "P3_FILENAME")
        group = groups.setdefault(branch, {"branch_id": branch, "scene_ids": [],
            "path": str(Path(execution["p3_root"]) / "shards" / branch / row["payload_filename"]),
            "sha256": row["payload_sha256"]})
        require(group["sha256"] == row["payload_sha256"], "P3_SHARD_HASH_CONFLICT")
        group["scene_ids"].append(scene)
    plan = {"scope": ctx["scope"], "scene_ids": ids, "shards": [groups[k] for k in sorted(groups)]}
    def build(stage):
        write_json(stage / "plan.json", plan)
        require(read_json(stage / "plan.json") == plan, "PLAN_READBACK")
        return {"scene_count": len(ids), "shard_count": len(groups)}
    return publish(ctx, "descriptor_plan", "plan", build, parents)

def raster_descriptors(fractions, lc_support, lc_mask, dem, dem_support, dem_mask):
    """D5 raw float32 cell observations promoted to float64, no re-extraction."""
    require(fractions.shape == (22, 100, 100) and lc_support.shape == lc_mask.shape == (100, 100) and
            dem.shape == dem_support.shape == dem_mask.shape == (17, 17), "RASTER_SHAPE")
    result = {}; qc = {}
    for name, support, mask in [("lc", lc_support, lc_mask), ("dem", dem_support, dem_mask)]:
        require(np.isfinite(support).all() and np.all((support >= 0) & (support <= 1)), "RASTER_SUPPORT")
        require(np.isin(mask, [0, 1]).all() and np.array_equal(mask.astype(bool), support > 0), "RASTER_MASK")
        qc[name + "_partial_cells"] = int(np.count_nonzero((support > 0) & (support < 1)))
        qc[name + "_invalid_cells"] = int(np.count_nonzero(support == 0))
    def record(value, support):
        n = int(np.count_nonzero(support)); total = int(support.size)
        return {"value": value, "null_reason": None if n else "no_valid_raster_support",
                "total_count": total, "valid_count": n, "invalid_count": total-n,
                "valid_weight": float(support.astype(np.float64).sum())}
    valid = lc_support > 0
    require(np.isfinite(fractions).all() and np.all(fractions >= 0) and np.all(fractions[:, ~valid] == 0), "LC_VALUES")
    require(np.all(np.abs(fractions[:, valid].astype(np.float64).sum(axis=0)-1) <= 1e-6), "LC_CELL_COMPOSITION")
    weight = lc_support[valid].astype(np.float64)
    composition = ((fractions[:, valid].astype(np.float64)*weight).sum(axis=1)/weight.sum()).tolist() if len(weight) else None
    result["landcover_composition"] = record(composition, lc_support)
    result["landcover_composition"]["category_keys"] = [str(i) for i in range(1, 23)]
    valid = dem_support > 0
    require(np.isfinite(dem).all() and np.all(dem[~valid] == -32767) and np.all(dem[valid] != -32767), "DEM_VALUES")
    v = dem[valid].astype(np.float64); w = dem_support[valid].astype(np.float64)
    mean = float((v*w).sum()/w.sum()) if len(w) else None
    sd = float(np.sqrt((w*(v-mean)**2).sum()/w.sum())) if len(w) else None
    result["mean_elevation"] = record(mean, dem_support)
    result["elevation_variability"] = record(sd, dem_support)
    return result, qc

def dictionary():
    contract, lock, _ = configuration()
    entries = read_json(lock["parents"]["categories"]["path"])["entries"]
    attributes = {"building_use_composition": "A9", "building_structure_composition": "A11",
        "road_type_composition": "ROAD_TYPE", "road_hierarchy_composition": "ROAD_RANK", "poi_l2_composition": "CLASS_L2"}
    result = []
    for descriptor in contract["descriptors"]:
        d = dict(descriptor)
        if d["id"] in attributes:
            category = sorted([r for r in entries if r["attribute"] == attributes[d["id"]]], key=lambda r: (r["source_order"], r["category_key"]))
            d["category_keys"] = [r["category_key"] for r in category]
            d["category_labels"] = [r["source_label"] for r in category]
        elif d["id"] == "relation_composition":
            d["category_keys"] = ["SN", "INC", "INT", "CON"]
        elif d["id"] == "landcover_composition":
            d["category_keys"] = [str(i) for i in range(1, 23)]
        result.append(d)
    require(len(result) == len({r["id"] for r in result}) == 22, "REGISTRY_22")
    return result

def validate_records(records, expected_ids):
    assert_population([r["scene_id"] for r in records], expected_ids)
    registry = dictionary(); names = [d["id"] for d in registry]
    for row in records:
        require(set(row["descriptors"]) == set(names), "DESCRIPTOR_REGISTRY")
        for d in registry:
            value = row["descriptors"][d["id"]]
            require(value["total_count"] == value["valid_count"] + value["invalid_count"] and
                    min(value["valid_count"], value["invalid_count"]) >= 0, "DESCRIPTOR_SUPPORT")
            if value["value"] is None:
                require(bool(value["null_reason"]), "NULL_REASON")
            else:
                require(value["null_reason"] is None and np.isfinite(value["value"]).all(), "DESCRIPTOR_FINITE")
                if d["kind"] == "compositional":
                    v = np.asarray(value["value"])
                    require(v.shape == (len(d["category_keys"]),) and np.all(v >= 0) and abs(v.sum()-1) <= 1e-6, "DESCRIPTOR_COMPOSITION")
                    require(value["category_keys"] == d["category_keys"], "CATEGORY_ORDER")

def extract_records(spec, temporary):
    """One authenticated P3 tar; read only selected rows and raster chunks."""
    _, lock, _ = configuration()
    reader_threads()
    gallery = read_json(lock["parents"]["gallery"]["path"])["body"]["rows"]
    centers = {r["scene_id"]:(r["center_x"],r["center_y"]) for r in gallery}
    require(file_sha256(spec["path"]) == spec["sha256"], "P3_PAYLOAD_HASH")
    directory = Path(temporary); selected = spec["scene_ids"]
    with tarfile.open(spec["path"], "r:") as tar:
        require(len(tar.getnames()) == len(set(tar.getnames())), "P3_DUPLICATE_MEMBER")
        tables = {}
        for name, member in TABLES.items():
            table = pq.read_table(pa.BufferReader(tar.extractfile(member).read()))
            table = table.filter(pc.is_in(table["scene_id"], value_set=pa.array(selected)))
            require(all(v == "evaluation" for v in table["split"].to_pylist()), "P3_SPLIT")
            if name in ("building", "road", "poi"):
                for row in table.select(["scene_id","scene_center_x_5186","scene_center_y_5186"]).to_pylist():
                    require(centers[row["scene_id"]] == (row["scene_center_x_5186"],row["scene_center_y_5186"]), "P3_VECTOR_GALLERY_CENTER")
                geo = read_json_bytes(table.schema.metadata[b"geo"])
                require(geo["primary_column"] == "observed_geometry" and
                        geo["columns"]["observed_geometry"]["crs"]["id"]["code"] == 5186, "P3_VECTOR_CRS")
                # Remove automatic GeoArrow extension conversion; preserve exact WKB bytes.
                fields = [pa.field(f.name, f.type, nullable=f.nullable) for f in table.schema]
                table = pa.Table.from_arrays(table.columns, schema=pa.schema(fields))
            tables[name] = table
            pq.write_table(table, directory / (name + ".parquet"))
        raster_rows = sorted(tables["raster_index"].to_pylist(), key=lambda r: r["scene_id"])
        assert_population([r["scene_id"] for r in raster_rows], selected)
        selected_indices = {str(r["zarr_index"]) for r in raster_rows}
        # Extract only metadata and chunks for selected scenes. No extractall/path traversal.
        for member in tar.getmembers():
            parts = Path(member.name).parts
            if len(parts) < 3 or parts[0] != "raster" or parts[1] not in ("scene_landcover.zarr", "scene_dem.zarr"):
                continue
            leaf = parts[-1]
            if not (leaf.startswith(".") or leaf.split(".")[0] in selected_indices):
                continue
            require(member.isfile() and ".." not in parts and not Path(member.name).is_absolute(), "P3_UNSAFE_MEMBER")
            dest = directory / member.name; dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(tar.extractfile(member).read())
    write_json(directory / "selection.json", {"scene_ids": selected})
    env = dict(os.environ, OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")
    subprocess.run(["Rscript", str(ROOT / "scripts/s11_descriptor_worker.R"), str(directory),
        lock["parents"]["categories"]["path"], str(directory / "vectors.json")], cwd=ROOT, env=env, check=True)
    records = read_json(directory / "vectors.json")
    require(isinstance(records, list), "R_READER_RECORDS")
    lc = zarr.open_group(str(directory / "raster/scene_landcover.zarr"), mode="r")
    dem = zarr.open_group(str(directory / "raster/scene_dem.zarr"), mode="r")
    for group, array, shape in [(lc, "class_fraction", (22,100,100)), (dem,"raw_mean_m",(17,17))]:
        require(group[array].shape[1:] == shape and group[array].chunks[0] == 1, "P3_RASTER_LAYOUT")
    for row, index in zip(records, raster_rows, strict=True):
        require(row["scene_id"] == index["scene_id"] and index["lc_height"] == index["lc_width"] == 100 and
                index["dem_height"] == index["dem_width"] == 17 and index["xmax"]-index["xmin"] == 500 and
                index["ymax"]-index["ymin"] == 500, "P3_RASTER_INDEX")
        require(index["row_order"]=="north_to_south" and index["column_order"]=="west_to_east" and
                index["lc_pixel_width_m"]==5 and index["lc_pixel_height_m"]==-5 and
                abs(index["dem_pixel_width_m"]-500/17)<1e-12 and
                abs(index["dem_pixel_height_m"]+500/17)<1e-12, "P3_RASTER_CELL_AREA")
        require((index["xmin"]+250,index["ymin"]+250)==centers[row["scene_id"]], "P3_RASTER_GALLERY_CENTER")
        z = index["zarr_index"]
        raster, qc = raster_descriptors(lc["class_fraction"][z], lc["valid_support_ratio"][z], lc["valid_mask"][z],
            dem["raw_mean_m"][z], dem["valid_support_ratio"][z], dem["valid_mask"][z])
        row["descriptors"].update(raster); row["qc"]["raster"] = qc
    validate_records(records, selected)
    require(file_sha256(spec["path"]) == spec["sha256"], "P3_CHANGED_DURING_READ")
    return records

def read_json_bytes(value):
    import json
    return json.loads(value)

def write_descriptor_tables(stage, records):
    registry = dictionary()
    values = {"scene_id": pa.array([r["scene_id"] for r in records])}
    support = []
    for d in registry:
        # Nullable fixed-size lists fail Parquet read-back in the pinned Arrow
        # runtime for empty scenes. List lengths are enforced by the dictionary
        # validator, while physical storage uses nullable variable-size lists.
        arrow_type = pa.float64() if d["kind"] == "scalar" else pa.list_(pa.float64())
        values[d["id"]] = pa.array([r["descriptors"][d["id"]]["value"] for r in records], type=arrow_type)
        for r in records:
            v = r["descriptors"][d["id"]]
            support.append({"scene_id": r["scene_id"], "descriptor": d["id"], "valid": v["value"] is not None,
                **{k: v.get(k) for k in ("null_reason", "total_count", "valid_count", "invalid_count", "valid_weight", "missing_count", "unknown_count", "alias_collision_count")}})
    pq.write_table(pa.table(values), stage / "descriptors.parquet", compression="zstd")
    support_schema = pa.schema([("scene_id",pa.string()),("descriptor",pa.string()),("valid",pa.bool_()),
        ("null_reason",pa.string()),("total_count",pa.int64()),("valid_count",pa.int64()),("invalid_count",pa.int64()),
        ("valid_weight",pa.float64()),("missing_count",pa.int64()),("unknown_count",pa.int64()),("alias_collision_count",pa.int64())])
    pq.write_table(pa.Table.from_pylist(support, schema=support_schema), stage / "validity.parquet", compression="zstd")
    write_json(stage / "dictionary.json", registry)
    write_json(stage / "qc.json", [{"scene_id": r["scene_id"], **r["qc"]} for r in records])
    require(pq.read_table(stage / "descriptors.parquet").to_pydict() == pa.table(values).to_pydict(), "DESCRIPTOR_READBACK")
    require(pq.read_table(stage / "validity.parquet").to_pylist() == support, "SUPPORT_READBACK")

def extract_shard(ctx, plan_manifest, spec):
    plan = read_json(payload(plan_manifest, "plan.json"))
    require(spec in plan["shards"] and plan["scope"] == ctx["scope"], "SHARD_PLAN")
    def build(stage):
        with tempfile.TemporaryDirectory(prefix="p3-", dir=stage.parent) as temporary:
            records = extract_records(spec, temporary)
        write_descriptor_tables(stage, records)
        return {"scene_ids": spec["scene_ids"], "p3_payload": spec["path"], "p3_sha256": spec["sha256"], "descriptor_count": 22}
    return publish(ctx, "descriptor_shards", spec["branch_id"], build, [plan_manifest])

def merge_descriptors(ctx, plan_manifest, shard_manifests):
    plan = read_json(payload(plan_manifest, "plan.json"))
    shards = [load_bundle(m, "descriptor_shards") for m in shard_manifests]
    require(len(shards) == len(plan["shards"]), "SHARD_COVERAGE")
    require(sorted(s["metadata"]["p3_payload"] for s in shards) == sorted(s["path"] for s in plan["shards"]), "SHARD_SET")
    def build(stage):
        for name in ["descriptors.parquet", "validity.parquet"]:
            table = pa.concat_tables([pq.read_table(payload(m, name)) for m in shard_manifests])
            sort = [("scene_id", "ascending")] + ([("descriptor", "ascending")] if name.startswith("validity") else [])
            table = table.sort_by(sort)
            if name.startswith("descriptors"):
                assert_population(table["scene_id"].to_pylist(), plan["scene_ids"])
                require(len(table.column_names) == 23, "MERGED_REGISTRY")
            else:
                require(table.num_rows == 22*len(plan["scene_ids"]), "MERGED_SUPPORT_COUNT")
                keys = list(zip(table["scene_id"].to_pylist(),table["descriptor"].to_pylist()))
                require(len(keys) == len(set(keys)), "MERGED_SUPPORT_UNIQUE")
            pq.write_table(table, stage / name, compression="zstd")
            require(pq.read_table(stage / name).equals(table), "MERGED_READBACK")
        write_json(stage / "dictionary.json", dictionary())
        qc = [r for m in shard_manifests for r in read_json(payload(m, "qc.json"))]
        write_json(stage / "qc.json", sorted(qc, key=lambda r:r["scene_id"]))
        return {"scene_count": len(plan["scene_ids"]), "descriptor_count":22, "scene_ids":plan["scene_ids"], "original_only":True}
    return publish(ctx, "descriptor_acceptance", "accepted", build, [plan_manifest, *shard_manifests])
