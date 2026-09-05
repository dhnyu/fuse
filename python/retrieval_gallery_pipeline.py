"""Isolated supplementary gallery orchestration; canonical P0-P11 are read-only.

Production is unavailable until all three complete pilot records pass. No method
selection, augmented queries, held-out metrics, UMAP, or downstream work is exposed.
"""
from __future__ import annotations

import concurrent.futures
from dataclasses import asdict
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pyarrow.compute as pc
import yaml

from p10_evaluation import evaluation_population, load_contract, resolve_model_bindings
from p9_v2_canonical import canonical_sha256
from retrieval_gallery_inputs import digest, prepare_originals
from retrieval_gallery_gpu import build_geometry, infer_all
from retrieval_gallery_ranking import rank_gallery, stability


REPOSITORY = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(Path(path).read_text())


def publish_json(path, value):
    path = Path(path)
    raw = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError(f"Immutable JSON collision: {path}")
        return path
    temporary = path.with_name(path.name + f".pending-{os.getpid()}")
    with temporary.open("xb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.link(temporary, path)
    finally:
        temporary.unlink()
    return path


def import_script(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_spatial_summaries(result):
    for stage_paths in result["files"].values():
        for path in stage_paths:
            if Path(path).name.endswith("qc.json") and read(path)["status"] != "PASS":
                raise ValueError("Spatial stage QC failed")
    paths = {Path(p).name: Path(p) for p in result["files"]["relations"]}
    edges = pq.read_table(paths["relation_edges.parquet"], columns=["scene_id", "relation_mask"])
    for name, bit in (("sn", 1), ("cnt", 2), ("wit", 4), ("int", 8), ("con", 16)):
        edges = edges.append_column(name, pc.not_equal(pc.bit_wise_and(edges["relation_mask"], bit), 0))
    grouped = edges.group_by("scene_id").aggregate([("relation_mask", "count")] +
                                                   [(name, "sum") for name in ("sn", "cnt", "wit", "int", "con")])
    counts = {r["scene_id"]: r for r in grouped.to_pylist()}
    stats = pq.read_table(paths["scene_relation_statistics.parquet"]).to_pylist()
    for row in stats:
        observed = counts.get(row["scene_id"], {})
        if row["ordered_pair_count"] != observed.get("relation_mask_count", 0) or row["outside_poi_count"] < 0:
            raise ValueError("Per-scene relation summary gate failed")
        for name in ("sn", "cnt", "wit", "int", "con"):
            if row[name + "_edge_count"] != observed.get(name + "_sum", 0):
                raise ValueError("Per-scene relation-type summary gate failed")
    return True


def gate_pilots(config, evidence):
    cfg = yaml.safe_load(Path(config).read_text())
    records = read(evidence)
    sampling = read(records["sampling_qc"])
    if not (sampling["status"] == "PASS" and sampling["exact_prefix"] and sampling["deterministic_replay"]
            and sampling["count"] == 8400 and sampling["first_batch_eligible"] == 4257
            and sampling["minimum_training_distance_m"] >= 50):
        raise ValueError("Historical sampling/continuation gate failed")
    if (sampling["canonical_counts"] != {"training": 2421, "validation": 400, "evaluation": 1600}
            or any(sampling[key] != 0 for key in ("coordinate_duplicates", "id_collisions", "domain_violations", "buffer_violations"))):
        raise ValueError("Separation, uniqueness, or geographic support gate failed")
    if digest(records["scene_index"]) != sampling["index_sha256"]:
        raise ValueError("Sampling index checksum mismatch")
    if set(records["pilots"]) != {"100", "500", "1000"}:
        raise ValueError("All nested pilots required")
    for count, paths in records["pilots"].items():
        spatial, inputs = read(paths["spatial"]), read(paths["inputs"])
        if (spatial["status"] != "SPATIAL_PASS" or not spatial["preservation_pass"]
                or inputs["status"] != "PASS" or inputs["models"] != 8
                or inputs["count"] != int(count) or spatial["count"] != int(count)):
            raise ValueError(f"Pilot gate failed: {count}")
        for branch in spatial["branches"]:
            validate_spatial_summaries(read(Path(branch["root"]) / "spatial_result.json"))
        for model in resolve_model_bindings(load_contract(cfg["p10_contract"])):
            binding = read(Path(paths["inputs"]).parent / "embeddings" / (model.configuration_id + ".json"))
            if (binding["checkpoint_id"] != model.checkpoint_id or binding["checkpoint_sha256"] != model.payload_sha256
                    or binding["shape"] != [int(count), 128] or not binding["deterministic_bounded_rerun"]):
                raise ValueError("Pilot checkpoint/embedding gate failed")
            path = Path(paths["inputs"]).parent / "embeddings" / (model.configuration_id + ".npy")
            array = np.load(path, allow_pickle=False)
            if (digest(path) != binding["sha256"] or array.shape != (int(count), 128)
                    or array.dtype != np.float32 or not np.isfinite(array).all()):
                raise ValueError("Pilot embedding payload gate failed")
            if not np.allclose(np.linalg.norm(array, axis=1), 1, atol=1e-6, rtol=0):
                raise ValueError("Pilot original embeddings fail the accepted normalization contract")
    if shutil.disk_usage(cfg["runtime_root"]).free < cfg["execution"]["minimum_free_bytes"]:
        raise ValueError("Insufficient working headroom")
    if records.get("selected_workers") not in (4, 8, 16, 20, 32, 40):
        raise ValueError("Measured production worker selection missing")
    baseline = read(records["pilots"]["1000"]["spatial"])
    if records["selected_workers"] != baseline["workers"]:
        scaling = read(records["worker_scaling_pilot"])
        parity = read(records["worker_scaling_parity"])
        if (scaling["status"] != "SPATIAL_PASS" or not scaling["preservation_pass"]
                or scaling["count"] != 1000 or scaling["workers"] != records["selected_workers"]
                or scaling["wall_seconds"] >= baseline["wall_seconds"] or parity["status"] != "PASS"
                or parity["count"] != 1000 or parity["parquet_tables_checked"] <= 0
                or parity["raster_shards_checked"] != len(baseline["branches"])
                or parity["left_receipt_sha256"] != digest(records["pilots"]["1000"]["spatial"])
                or parity["right_receipt_sha256"] != digest(records["worker_scaling_pilot"])):
            raise ValueError("Additional worker scaling/parity gate failed")
    prepared = read(Path(records["pilots"]["1000"]["inputs"]).parent / "prepared/prepared_manifest.json")
    if records.get("selected_preparation_workers") != prepared["workers"]:
        raise ValueError("Preparation workers must match the completed 1000-scene input pilot")
    if not records.get("scaling_500_to_1000_reviewed") or read(records["spatial_parity"])["status"] != "PASS":
        raise ValueError("Scaling/parity review missing")
    if not 0 < records.get("projected_hours", 0) <= cfg["execution"]["maximum_projected_hours"]:
        raise ValueError("Projected runtime outside reviewed envelope")
    return cfg, records


def authority(config, evidence):
    cfg, records = gate_pilots(config, evidence)
    p10 = load_contract(cfg["p10_contract"])
    bindings = resolve_model_bindings(p10)
    root = Path(p10["publication_root"])
    scientific = cfg["scientific"]
    acceptance_path = root / "execution_attempts" / scientific["p10_attempt_id"] / "commit/evaluation_acceptance.json"
    query_path = root / "qualitative" / (scientific["query_contract_id"] + ".json")
    accepted, queries = read(acceptance_path), read(query_path)
    if accepted["acceptance_id"] != scientific["p10_acceptance_id"] or queries["contract_id"] != scientific["query_contract_id"]:
        raise ValueError("Historical P10 authority mismatch")
    files = [Path(config), REPOSITORY / "R/retrieval_gallery.R", REPOSITORY / "scripts/retrieval_gallery.R",
        REPOSITORY / "scripts/retrieval_gallery_pipeline.py", REPOSITORY / "R/retrieval_gallery_targets.R",
        REPOSITORY / "targets/retrieval_gallery_targets.R", REPOSITORY / "_targets_retrieval_gallery.R"]
    files += list((REPOSITORY / "python").glob("retrieval_gallery*.py"))
    files += list((REPOSITORY / "config/schemas/retrieval_gallery").glob("*.json"))
    files += [REPOSITORY / "R/research_base_spatial.R", REPOSITORY / "R/research_relation.R",
              REPOSITORY / "R/research_observation.R", REPOSITORY / "R/research_raster_observation.R"]
    files += [REPOSITORY / "python" / name for name in ("prototype_encoder.py", "p6_model.py",
        "p6_data.py", "p7_training.py", "p9_model_families.py", "p10_prepared_input.py", "p10_evaluation.py",
        "write_geoparquet.py", "write_raster_zarr.py")]
    files += [REPOSITORY / "R" / (name + ".R") for name in ("config_paths", "io_spatial", "research_contracts",
        "research_canonical_config", "research_methodology_authority", "research_runtime_mirror",
        "research_scene_index", "research_scene_index_reduced", "research_membership",
        "research_spatial_acceptance", "research_original_scene_cache")]
    files += [REPOSITORY / "scripts/p3_deterministic_tar.py", REPOSITORY / "config/schemas/retrieval_topology.schema.json"]
    files += [REPOSITORY / "config" / (name + ".yml") for name in ("research_paths", "p1_scene_index",
        "membership", "membership_runtime", "vector_observation", "vector_observation_runtime",
        "raster_observation", "raster_observation_runtime", "relation_graph", "relation_graph_runtime")]
    files += [REPOSITORY / "tools/retrieval_inspector" / name for name in
              ("inspector.py", "app.js", "index.html", "style.css")]
    frozen_inputs = {str(Path(p)): digest(p) for p in (p10["inputs"]["preprocessing"], p10["inputs"]["categories"],
        Path(p10["prepared_input"]["geometry_root"]) / "p10geo_8cdab54a6886cb8217c0088b/prepared_geometry_manifest.json")}
    for source in (Path(cfg["p10_contract"]), *(Path(p) for p in p10["inputs"].values())):
        if source.is_file():
            frozen_inputs[str(source.resolve())] = digest(source)
    historical_source = yaml.safe_load((REPOSITORY / "config/p1_scene_index.yml").read_text())["off_grid_source"]
    for kind in ("parquet", "manifest", "qc"):
        source = historical_source[kind]
        if digest(source["path"]) != source["sha256"]:
            raise ValueError("Historical off-grid source authority changed")
        frozen_inputs[source["path"]] = source["sha256"]
    inventory_path = Path("/mnt/hdd002/dhnyu/fusedata/scene_data/reduced/index/_inputs/rin_fc622f56cb4afdcb9a5db08b/study_data_inventory.json")
    source_paths = yaml.safe_load((REPOSITORY / "config/research_paths.yml").read_text())["inputs"]
    frozen_inputs[str(inventory_path)] = digest(inventory_path)
    for row in read(inventory_path)["scientific"]["files"]:
        source = Path(source_paths[row["role"]])
        if digest(source) != row["sha256"]:
            raise ValueError("Accepted study source snapshot changed")
        frozen_inputs[str(source)] = row["sha256"]
    historical = {}
    for name in ("p11_downstream_dataset", "p11_spatial_readiness_acceptance",
                 "p11_ridge_evaluation_acceptance", "p11_diagnostic_probe_acceptance"):
        pointer = REPOSITORY / "config" / (name + ".yml")
        metadata = yaml.safe_load(pointer.read_text())
        path = Path(metadata["acceptance_path"])
        if digest(path) != metadata["acceptance_sha256"]:
            raise ValueError("Historical P11 acceptance checksum mismatch")
        historical[name] = {"pointer_sha256": digest(pointer), "acceptance_sha256": digest(path),
                            "acceptance_path": str(path), "authority": read(path)}
        frozen_inputs[str(pointer)] = digest(pointer)
        frozen_inputs[str(path)] = digest(path)
    scientific_record = {"contract_version": cfg["contract_version"], "scientific": scientific,
        "audit_report_sha256": digest(REPOSITORY / cfg["audit_report"]),
        "canonical_evaluation_unchanged": 1600, "supplementary_retrieval_only": True,
        "p10_acceptance_sha256": digest(acceptance_path), "query_contract_sha256": digest(query_path),
        "fixed_query_ids": queries["selected_scene_ids"], "scene_index_sha256": digest(records["scene_index"]),
        "models": [{k: v for k, v in asdict(b).items() if k != "checkpoint_path"} for b in bindings],
        "historical_p11_unchanged": historical,
        "implementation": {str(p.resolve().relative_to(REPOSITORY)): digest(p) for p in files},
        "frozen_inputs": frozen_inputs}
    identity = "retrag_" + canonical_sha256(scientific_record)[:24]
    destination = Path(cfg["root"]) / identity
    pilot_paths = {key: records[key] for key in ("sampling_qc", "spatial_parity", "preservation_before")}
    for count, pair in records["pilots"].items():
        pilot_paths.update({count + "_" + stage: p for stage, p in pair.items()})
    for key in ("worker_scaling_pilot", "worker_scaling_parity", "benchmark_summary"):
        if key in records:
            pilot_paths[key] = records[key]
    value = {"authority_id": identity, "scientific": scientific_record,
             "execution": {"workers": records["selected_workers"], "threads": 1, "gpus": 2,
                           "preparation_workers": records["selected_preparation_workers"],
                           "batch_size": 8, "projected_hours": records["projected_hours"]},
             "pilot_evidence_sha256": digest(evidence), "pilot_evidence_path": str(Path(evidence).resolve()),
             "pilot_artifacts": {label: {"path": str(Path(p).resolve()), "sha256": digest(p)}
                                 for label, p in pilot_paths.items()},
             "status": "AUTHORIZED_SUPPLEMENT_ONLY"}
    path = publish_json(destination / "methodology.json", value)
    index = destination / "index/supplemental_scene_index.parquet"
    if not index.exists():
        index.parent.mkdir(parents=True, exist_ok=True)
        with index.open("xb") as target, Path(records["scene_index"]).open("rb") as source:
            shutil.copyfileobj(source, target)
    if digest(index) != sampling_sha(records):
        raise ValueError("Published supplemental center checksum mismatch")
    return path


def assert_frozen(root):
    value = read(Path(root) / "methodology.json")
    for relative, expected in value["scientific"]["implementation"].items():
        if digest(REPOSITORY / relative) != expected:
            raise ValueError("Frozen implementation changed after authorization")
    for path, expected in value["scientific"]["frozen_inputs"].items():
        if digest(path) != expected:
            raise ValueError("Frozen preprocessing or geometry authority changed")
    for record in value["pilot_artifacts"].values():
        if digest(record["path"]) != record["sha256"]:
            raise ValueError("Frozen pilot evidence changed")
    return value


def sampling_sha(records):
    return read(records["sampling_qc"])["index_sha256"]


def verify_seal(root):
    seal = read(root / "verified_files.json")
    for relative, checksum in seal["files"].items():
        if digest(root / relative) != checksum:
            raise ValueError(f"Completed shard checksum mismatch: {root / relative}")
    return seal


def spatial_job(job):
    root = Path(job["root"])
    if (root / "verified_files.json").exists():
        seal = verify_seal(root)
        if seal["job_sha256"] != canonical_sha256(job):
            raise ValueError("Completed shard input mismatch")
        return read(root / "spatial_result.json")
    retries = list(root.parent.glob(root.name + ".failed-*"))
    if root.exists():
        failure = root / "failed_attempt.json"
        if not failure.exists() or read(failure)["job_sha256"] != canonical_sha256(job):
            raise ValueError(f"Unverified interrupted shard requires recovery review: {root}")
        if read(root / "job.json") != job:
            raise ValueError("Failed shard input mismatch")
        archive = root.with_name(root.name + f".failed-{len(retries) + 1:04d}")
        root.rename(archive)
        retries.append(archive)
    root.mkdir(parents=True)
    publish_json(root / "job.json", job)
    env = {**os.environ, **{k: "1" for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
                                             "NUMEXPR_NUM_THREADS", "GDAL_NUM_THREADS")}}
    start = time.monotonic()
    with (root / "worker.log").open("x") as log:
        completed = subprocess.run(["Rscript", "scripts/retrieval_gallery.R", "spatial", str(root / "job.json")],
                       cwd=REPOSITORY, env=env, stdout=log, stderr=subprocess.STDOUT)
    if completed.returncode:
        publish_json(root / "failed_attempt.json", {"job_sha256": canonical_sha256(job),
                     "returncode": completed.returncode, "retry_count": len(retries)})
        raise RuntimeError("Spatial worker failed; identical-input retry is available")
    result = read(root / "spatial_result.json")
    if result["status"] != "PASS" or result["scene_ids"] != sorted(s["scene_id"] for s in job["scenes"]):
        raise ValueError("Spatial shard acceptance mismatch")
    publish_json(root / "verified_files.json", {"status": "PASS", "job_sha256": canonical_sha256(job),
        "wall_seconds": time.monotonic() - start, "retry_count": len(retries),
        "files": {str(p.relative_to(root)): digest(p) for p in sorted(root.rglob("*"))
                  if p.is_file() and p.name != "worker.log"}})
    return result


def spatial_production(methodology):
    path = Path(methodology)
    value = read(path)
    root = path.parent
    assert_frozen(root)
    if (root / "spatial_manifest.json").exists():
        old = read(root / "spatial_manifest.json")
        for branch in old["branches"]:
            verify_seal(Path(branch))
        return root / "spatial_manifest.json"
    # Fail closed if any bound implementation changed after production authorization.
    for relative, expected in value["scientific"]["implementation"].items():
        if digest(REPOSITORY / relative) != expected:
            raise ValueError("Frozen implementation changed after authorization")
    rows = pq.read_table(root / "index/supplemental_scene_index.parquet").to_pylist()
    if len(rows) != 8400:
        raise ValueError("Exactly 8400 supplemental scenes required")
    jobs = []
    for offset in range(0, 8400, 25):
        scenes = [{k: r[k] for k in ("scene_id", "split", "center_x", "center_y", "xmin", "ymin", "xmax", "ymax")}
                  for r in rows[offset:offset+25]]
        for scene in scenes:
            scene.update(scene_footprint_id=scene["scene_id"], estimated_cost=0)
        branch = "retrbr_" + canonical_sha256({"authority": value["authority_id"], "scenes": scenes})[:24]
        jobs.append({"root": str(root / "spatial" / branch), "branch_id": branch,
                     "dataset_id": value["authority_id"], "index_id": "retridx_" + value["scientific"]["scene_index_sha256"][:24], "scenes": scenes})
    start = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=value["execution"]["workers"]) as pool:
        results = list(pool.map(spatial_job, jobs))
    return publish_json(root / "spatial_manifest.json", {"status": "PASS", "authority_id": value["authority_id"],
        "count": sum(r["count"] for r in results), "branches": [j["root"] for j in jobs],
        "wall_seconds": time.monotonic() - start,
        "seals": {j["branch_id"]: digest(Path(j["root"]) / "verified_files.json") for j in jobs}})


def cache_production(spatial_manifest):
    root = Path(spatial_manifest).parent
    assert_frozen(root)
    manifest = read(spatial_manifest)
    writer = import_script("retrieval_tar_writer", REPOSITORY / "scripts/p3_deterministic_tar.py")
    if (root / "cache/cache_manifest.json").exists():
        old = read(root / "cache/cache_manifest.json")
        for row in old["shards"]:
            if digest(row["path"]) != row["sha256"]:
                raise ValueError("Completed scene cache checksum mismatch")
        return root / "cache/cache_manifest.json"
    start = time.monotonic()
    shards, catalog = [], []
    for branch_root in manifest["branches"]:
        branch_root = Path(branch_root)
        verify_seal(branch_root)
        result = read(branch_root / "spatial_result.json")
        branch = result["branch_id"]
        path = root / "cache/shards" / (branch + ".tar")
        record_path = path.with_suffix(".json")
        if record_path.exists():
            record = read(record_path)
            if digest(path) != record["sha256"]:
                raise ValueError("Completed tar checksum mismatch")
            writer.validate(path, record["members"])
        else:
            if path.exists():
                raise ValueError("Unsealed tar requires recovery review")
            members = writer.write(read(result["serialization_spec"]), str(path))
            writer.validate(path, members)
            record = {"sha256": digest(path), "members": members, "size_bytes": path.stat().st_size}
            publish_json(record_path, record)
        shards.append({"branch_id": branch, "path": str(path), "sha256": record["sha256"], "size_bytes": path.stat().st_size})
        for scene_id in result["scene_ids"]:
            catalog.append({"scene_id": scene_id, "split": "retrieval_only", "branch_id": branch,
                            "payload_path": str(path), "payload_filename": path.name, "payload_sha256": record["sha256"]})
    scene_ids = pq.read_table(root / "index/supplemental_scene_index.parquet", columns=["scene_id"]).column(0).to_pylist()
    lookup = {row["scene_id"]: row for row in catalog}
    if len(catalog) != 8400 or len(lookup) != 8400 or set(lookup) != set(scene_ids):
        raise ValueError("Supplemental scene cache population mismatch")
    catalog = [lookup[s] for s in scene_ids]
    identity = {"version": "supplemental-original-cache-v3", "authority": manifest["authority_id"],
                "scenes": [{"scene_id": r["scene_id"], "payload_sha256": r["payload_sha256"]} for r in catalog]}
    publish_json(root / "cache/catalog.json", catalog)
    return publish_json(root / "cache/cache_manifest.json", {"status": "PASS", "cache_id": "retrcache_" + canonical_sha256(identity)[:24],
        "identity": identity, "shards": shards, "count": 8400, "wall_seconds": time.monotonic() - start})


def prepared_production(cache_manifest):
    root = Path(cache_manifest).parent.parent
    assert_frozen(root)
    target = root / "prepared/prepared_manifest.json"
    if target.exists():
        manifest = read(target)
        for row in manifest["batches"]:
            if digest(target.parent / row["relative_path"]) != row["payload_sha256"]:
                raise ValueError("Prepared input checksum mismatch")
        return target
    method = read(root / "methodology.json")
    prepare_originals(read(root / "cache/catalog.json"), load_contract(REPOSITORY / "config/p10_evaluation.yml"),
                      target.parent, method["execution"]["preparation_workers"])
    return target


def geometry_production(prepared_manifest):
    root = Path(prepared_manifest).parent.parent
    assert_frozen(root)
    target = root / "geometry/geometry_manifest.json"
    if target.exists():
        for row in read(target)["entries"]:
            if digest(target.parent / row["relative_path"]) != row["payload_sha256"]:
                raise ValueError("Geometry checksum mismatch")
        return target
    p10 = load_contract(REPOSITORY / "config/p10_evaluation.yml")
    accepted = Path(p10["prepared_input"]["geometry_root"]) / "p10geo_8cdab54a6886cb8217c0088b/prepared_geometry_manifest.json"
    build_geometry(root / "prepared", target.parent, accepted)
    return target


def inference_production(geometry_manifest):
    root = Path(geometry_manifest).parent.parent
    assert_frozen(root)
    p10 = load_contract(REPOSITORY / "config/p10_evaluation.yml")
    target = root / "embeddings/embedding_manifest.json"
    if target.exists():
        for row in read(target)["models"]:
            if digest(root / "embeddings" / row["filename"]) != row["sha256"]:
                raise ValueError("Supplemental embedding checksum mismatch")
        return target
    wall = infer_all(p10, root / "prepared", root / "geometry", target.parent)
    rows = []
    expected_ids = [r["scene_id"] for r in read(root / "cache/catalog.json")]
    for binding in resolve_model_bindings(p10):
        path = target.parent / (binding.configuration_id + ".npy")
        metadata = read(path.with_suffix(".json"))
        array = np.load(path, allow_pickle=False)
        if (metadata["scene_ids"] != expected_ids or metadata["checkpoint_sha256"] != binding.payload_sha256
                or array.shape != (8400, 128) or array.dtype != np.float32 or not np.isfinite(array).all()):
            raise ValueError("Production original-only embedding gate failed")
        rows.append({"model": binding.configuration_id, "filename": path.name, "sha256": digest(path),
                     "metadata_sha256": digest(path.with_suffix(".json")), "checkpoint_id": binding.checkpoint_id})
    return publish_json(target, {"status": "PASS", "count_per_model": 8400, "models": rows, "wall_seconds": wall})


def union_production(embedding_manifest):
    root = Path(embedding_manifest).parent.parent
    assert_frozen(root)
    target = root / "union/union_manifest.json"
    if target.exists():
        old = read(target)
        for row in old["models"]:
            if digest(target.parent / row["filename"]) != row["sha256"]:
                raise ValueError("Union checksum mismatch")
        return target
    target.parent.mkdir(parents=True, exist_ok=False)
    p10 = load_contract(REPOSITORY / "config/p10_evaluation.yml")
    _, old_gallery = evaluation_population(p10)
    canonical_ids = [r["scene_id"] for r in old_gallery]
    supplemental = pq.read_table(root / "index/supplemental_scene_index.parquet").to_pylist()
    scene_ids = canonical_ids + [r["scene_id"] for r in supplemental]
    if len(scene_ids) != 10000 or len(set(scene_ids)) != 10000:
        raise ValueError("Union identity cardinality mismatch")
    model_rows, centers = [], None
    for binding in resolve_model_bindings(p10):
        model = binding.configuration_id
        old_root = Path(p10["publication_root"]) / "execution_attempts/p10exec_7fee193dac532190c79e02c6/evaluations" / model
        evaluation = read(old_root / "evaluation.json")
        if evaluation["checkpoint_id"] != binding.checkpoint_id or evaluation["acceptance_id"] != binding.acceptance_id:
            raise ValueError("Canonical embedding checkpoint identity mismatch")
        old_path = old_root / "evaluation_embeddings_ranks_analysis.npz"
        with np.load(old_path) as old:
            accepted = old["embeddings"][3200:]
            canonical_centers = old["centers"][3200:]
        additions_path = root / "embeddings" / (model + ".npy")
        additions = np.load(additions_path, allow_pickle=False)
        result = np.concatenate([accepted, additions])
        if result.dtype != np.float32 or result.shape != (10000, 128) or result[:1600].tobytes() != accepted.tobytes():
            raise ValueError("Accepted original rows changed in union")
        path = target.parent / (model + ".npy")
        with path.open("xb") as handle:
            np.save(handle, result, allow_pickle=False)
        xy = np.concatenate([canonical_centers, np.asarray([[r["center_x"], r["center_y"]] for r in supplemental], dtype=np.float64)])
        if centers is not None and not np.array_equal(centers, xy):
            raise ValueError("Model center mapping differs")
        centers = xy
        model_rows.append({"model": model, "filename": path.name, "sha256": digest(path),
            "accepted_arrays_sha256": digest(old_path), "supplemental_arrays_sha256": digest(additions_path),
            "canonical_rows_byte_identical": True, "checkpoint_id": binding.checkpoint_id})
    gallery = [{"gallery_index": i, "scene_id": scene_id, "source": "canonical" if i < 1600 else "supplemental",
                "center_x": float(centers[i, 0]), "center_y": float(centers[i, 1])} for i, scene_id in enumerate(scene_ids)]
    pq.write_table(pa.Table.from_pylist(gallery), target.parent / "gallery.parquet", compression="zstd")
    cache_index = next((Path(p10["inputs"]["p3_root"]) / "index").glob("*/scene_to_shard.parquet"))
    old_cache = {r["scene_id"]: r for r in pq.read_table(cache_index).to_pylist()}
    catalog = []
    for scene_id in canonical_ids:
        row = old_cache[scene_id]
        catalog.append({**row, "payload_path": str(Path(p10["inputs"]["p3_root"]) / "shards" / row["branch_id"] / row["payload_filename"])})
    catalog.extend(read(root / "cache/catalog.json"))
    publish_json(target.parent / "union_catalog.json", catalog)
    identity = {"gallery_sha256": digest(target.parent / "gallery.parquet"), "models": model_rows,
                "canonical_count": 1600, "supplemental_count": 8400, "total_count": 10000}
    return publish_json(target, {"status": "PASS", "union_id": "retrunion_" + canonical_sha256(identity)[:24], **identity})


def rankings_production(union_manifest):
    root = Path(union_manifest).parent.parent
    assert_frozen(root)
    target = root / "rankings/ranking_manifest.json"
    if target.exists():
        for row in read(target)["ranking_files"]:
            if digest(target.parent / row["filename"]) != row["sha256"]:
                raise ValueError("Ranking checksum mismatch")
        return target
    target.parent.mkdir(parents=True, exist_ok=False)
    inspector = import_script("supplemental_inspector", REPOSITORY / "tools/retrieval_inspector/inspector.py")
    canonical, required = inspector.build_rank_manifest(REPOSITORY)
    publish_json(target.parent / "canonical_rank_manifest.json", canonical)
    gallery = pq.read_table(root / "union/gallery.parquet").to_pylist()
    ids = [r["scene_id"] for r in gallery]
    centers = np.asarray([[r["center_x"], r["center_y"]] for r in gallery], dtype=np.float64)
    query_ids = [r["scene_id"] for r in canonical["queries"]]
    models, diagnostics, files = {}, [], []
    start = time.monotonic()
    for model in canonical["models"]:
        embeddings = np.load(root / "union" / (model + ".npy"), allow_pickle=False)
        rankings = rank_gallery(ids, centers, embeddings, query_ids, already_normalized=True)
        queries, tables = {}, {"standard": [], "nonlocal": []}
        for query in query_ids:
            queries[query] = {}
            qindex = ids.index(query)
            # Reproduce the canonical inspector's GEMV order for the paired baseline.
            old_scores = embeddings[:1600] @ embeddings[qindex]
            old_distances = np.sqrt(((centers[:1600] - centers[qindex]) ** 2).sum(axis=1))
            old_order = np.asarray(sorted((i for i in range(1600) if i != qindex), key=lambda i: (-float(old_scores[i]), ids[i])))
            for setting in ("standard", "nonlocal"):
                ranked = rankings[query][setting]
                count = len(ranked["indices"])
                if setting == "standard" and count != 9999:
                    raise ValueError("Supplemental standard candidates must be 9999")
                if setting == "nonlocal" and np.any(ranked["distances"] < 2000):
                    raise ValueError("Non-local radius gate failed")
                indices = ranked["indices"]
                if any(ids[i] == query for i in indices):
                    raise ValueError("Self candidate retained")
                bands = {}
                for band, positions in inspector.band_ranks(count).items():
                    bands[band] = []
                    for rank in positions:
                        index = indices[rank - 1]
                        required.add(ids[index])
                        bands[band].append({"rank": rank, "scene_id": ids[index],
                            "similarity": float(ranked["similarities"][rank - 1]), "distance_m": float(ranked["distances"][rank - 1]),
                            "source": "canonical" if index < 1600 else "supplemental"})
                queries[query][setting] = {"candidate_count": count, "gallery_count": 10000,
                                           "self_excluded": True, "bands": bands}
                old_indices = old_order if setting == "standard" else old_order[old_distances[old_order] >= 2000]
                old = {"indices": old_indices, "similarities": old_scores[old_indices], "distances": old_distances[old_indices]}
                diagnostics.append({"model": model, "query": query, "setting": setting,
                                    **stability(old, ranked, ids, set(ids[:1600]))})
                tables[setting].append(pa.table({"query_scene_id": [query] * count,
                    "rank": np.arange(1, count + 1, dtype=np.int32), "candidate_scene_id": [ids[i] for i in indices],
                    "similarity": ranked["similarities"], "distance_m": ranked["distances"],
                    "source": ["canonical" if i < 1600 else "supplemental" for i in indices]}))
        for setting, values in tables.items():
            path = target.parent / (model + "_" + setting + ".parquet")
            pq.write_table(pa.concat_tables(values), path, compression="zstd")
            files.append({"model": model, "setting": setting, "filename": path.name, "sha256": digest(path)})
        models[model] = {**canonical["models"][model], "queries": queries,
                         "union_embedding_sha256": digest(root / "union" / (model + ".npy"))}
    publish_json(target.parent / "stability_diagnostics.json", diagnostics)
    identity = {"union_sha256": digest(union_manifest), "ranking_files": files,
                "query_contract_sha256": canonical["qualitative_contract_sha256"],
                "diagnostics_sha256": digest(target.parent / "stability_diagnostics.json")}
    return publish_json(target, {**canonical, "gallery_id": read(union_manifest)["union_id"], "gallery_count": 10000,
        "scientific_status": "supplementary original-only retrieval; canonical P10/P11 unchanged",
        "models": models, "ranking_files": files, "ranking_sha256": canonical_sha256(models),
        "ranking_id": "retrrank_" + canonical_sha256(identity)[:24], "identity": identity,
        "required_scene_ids": sorted(required), "wall_seconds": time.monotonic() - start, "status": "PASS"})


def inspector_production(ranking_manifest):
    root = Path(ranking_manifest).parent.parent
    assert_frozen(root)
    target = root / "inspector/manifest.json"
    inspector = import_script("supplemental_inspector", REPOSITORY / "tools/retrieval_inspector/inspector.py")
    if target.exists():
        inspector.validate_output(target.parent)
        return target
    target.parent.mkdir(parents=True, exist_ok=False)
    canonical = read(root / "rankings/canonical_rank_manifest.json")
    supplemental = read(ranking_manifest)
    required = set(supplemental["required_scene_ids"])
    catalog = read(root / "union/union_catalog.json")
    start = time.monotonic()
    # Only required bands are rendered. The browser loads individual assets lazily.
    geographic_metadata, _ = inspector._district_metadata(REPOSITORY)
    hashes = inspector._scene_assets(REPOSITORY, supplemental, required, target.parent,
                                      catalog_rows=catalog, geographic_metadata=geographic_metadata)
    if set(hashes) != required:
        raise ValueError("Missing required inspector band assets")
    example = read(REPOSITORY / "tools/retrieval_inspector/example_output.json")
    previous_path = (REPOSITORY / example["output_path"]).parent / "manifest.json"
    previous = read(previous_path)
    canonical_asset_count = 0
    for scene_id, checksum in previous["scene_asset_sha256"].items():
        if scene_id in required:
            if hashes[scene_id] != checksum:
                raise ValueError("Canonical inspector scene asset changed")
            canonical_asset_count += 1
    implementation = {name: digest(REPOSITORY / "tools/retrieval_inspector" / name)
                      for name in ("index.html", "style.css", "app.js", "inspector.py")}
    render = {"crs": "EPSG:5186", "extent_m": [500, 500], "north_up": True,
              "landcover_colors": list(inspector.LC_COLORS), "dem_scale": "shared_current_comparison"}
    identity = {"ranking_sha256": digest(ranking_manifest), "implementation": implementation,
                "scene_assets": hashes, "canonical_inspector_manifest_sha256": digest(previous_path)}
    manifest = {**canonical, "inspector_id": "retrieval_inspector_" + canonical_sha256(identity)[:24],
        "galleries": {"canonical": {**canonical, "render": render}, "supplemental": {**supplemental, "render": render}},
        "scene_asset_sha256": hashes, "scene_asset_count": len(hashes), "render": render,
        "identity_preimage": identity, "canonical_scene_assets_byte_identical": canonical_asset_count,
        "render_wall_seconds": time.monotonic() - start}
    for name in ("index.html", "style.css", "app.js"):
        shutil.copyfile(REPOSITORY / "tools/retrieval_inspector" / name, target.parent / name)
    publish_json(target, manifest)
    raw = json.dumps(manifest, sort_keys=True, separators=(",", ":"), allow_nan=False).replace("<", "\\u003c")
    with (target.parent / "manifest.js").open("x") as handle:
        handle.write("window.RETRIEVAL_MANIFEST=" + raw + ";\n")
    inspector.validate_output(target.parent)
    return target


def validate_production(inspector_manifest):
    root = Path(inspector_manifest).parent.parent
    method = assert_frozen(root)
    target = root / "validation/validation.json"
    if target.exists():
        return target
    target.parent.mkdir(parents=True, exist_ok=False)
    ranking = read(root / "rankings/ranking_manifest.json")
    gallery = pq.read_table(root / "union/gallery.parquet").to_pylist()
    ids = [r["scene_id"] for r in gallery]
    centers = np.asarray([[r["center_x"], r["center_y"]] for r in gallery])
    query_ids = [r["scene_id"] for r in ranking["queries"]]
    if len(ids) != 10000 or len(set(ids)) != 10000 or sum(r["source"] == "canonical" for r in gallery) != 1600:
        raise ValueError("Union population validation failed")
    checked_rows = 0
    for model in ranking["models"]:
        embeddings = np.load(root / "union" / (model + ".npy"), allow_pickle=False)
        rerun = rank_gallery(ids, centers, embeddings, query_ids, already_normalized=True)
        for setting in ("standard", "nonlocal"):
            table = pq.read_table(root / "rankings" / (model + "_" + setting + ".parquet"))
            for query in query_ids:
                rows = table.filter(pc.equal(table["query_scene_id"], query)).to_pydict()
                expected = rerun[query][setting]
                if rows["candidate_scene_id"] != [ids[i] for i in expected["indices"]]:
                    raise ValueError("Ranking deterministic rerun mismatch")
                if rows["rank"] != list(range(1, len(rows["rank"]) + 1)):
                    raise ValueError("Ranking ordinal mismatch")
                if not np.array_equal(np.asarray(rows["similarity"], dtype=np.float32), expected["similarities"]):
                    raise ValueError("Ranking similarity rerun mismatch")
                if not np.array_equal(rows["distance_m"], expected["distances"]):
                    raise ValueError("Ranking geographic distance mismatch")
                checked_rows += len(rows["rank"])
    inspector = import_script("supplemental_inspector", REPOSITORY / "tools/retrieval_inspector/inspector.py")
    assets = inspector.validate_output(Path(inspector_manifest).parent)
    from playwright.sync_api import sync_playwright
    errors, visits = [], 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1600, "height": 1000})
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            page.goto((root / "inspector/index.html").as_uri())
            page.wait_for_function("document.querySelector('#status').textContent === 'Evidence ready'")
            for mode in ("canonical", "supplemental"):
                page.locator("#gallery").select_option(mode)
                for model in ranking["models"]:
                    page.locator("#model").select_option(model)
                    for setting in ("standard", "nonlocal"):
                        page.locator(f"input[name=setting][value={setting}]").check(force=True)
                        page.wait_for_function("document.querySelector('#status').textContent === 'Evidence ready'")
                        visits += 1
                        if not page.locator(".column canvas.vector").evaluate_all("cs => cs.length === 5 && cs.every(c => { const d=c.getContext('2d').getImageData(0,0,c.width,c.height).data; return d.some((v,i)=>i%4===3 && v>0); })"):
                            raise ValueError("Inspector vector canvas is blank")
                page.screenshot(path=str(target.parent / (mode + "_desktop.png")), full_page=True)
            for query in query_ids:
                page.locator("#query").select_option(query)
                page.wait_for_function("document.querySelector('#status').textContent === 'Evidence ready'")
                visits += 1
            page.set_viewport_size({"width": 390, "height": 844})
            page.reload()
            page.wait_for_function("document.querySelector('#status').textContent === 'Evidence ready'")
            if not page.locator(".controls select").evaluate_all("xs => xs.every(x => x.getBoundingClientRect().right <= innerWidth)"):
                raise ValueError("Mobile gallery controls overflow")
            page.screenshot(path=str(target.parent / "supplemental_mobile.png"), full_page=True)
            if errors:
                raise ValueError("Inspector console/page errors: " + str(errors))
            browser_version = browser.version
        finally:
            browser.close()
    pilot_module = import_script("retrieval_pilot_snapshot", REPOSITORY / "scripts/retrieval_gallery_pilot.py")
    if digest(method["pilot_evidence_path"]) != method["pilot_evidence_sha256"]:
        raise ValueError("Reviewed pilot evidence changed")
    evidence = read(method["pilot_evidence_path"])
    before = read(evidence["preservation_before"])
    after = pilot_module.preservation()
    if before != after:
        raise ValueError("Historical acceptance/artifact preservation failed")
    counts = {name: sum(p.stat().st_size for p in (root / name).rglob("*") if p.is_file())
              for name in ("spatial", "cache", "prepared", "geometry", "embeddings", "union", "rankings", "inspector")}
    return publish_json(target, {"status": "PASS", "authority_id": method["authority_id"],
        "historical_files_byte_identical": len(after), "preservation_before_sha256": digest(evidence["preservation_before"]),
        "canonical_count": 1600, "supplemental_count": 8400, "union_count": 10000,
        "models": 8, "fixed_queries": 10, "standard_candidates": 9999,
        "ranking_rows_validated": checked_rows, "deterministic_ranking_rerun": True,
        "missing_required_scene_assets": 0, "inspector": assets, "browser_version": browser_version,
        "browser_states_visited": visits, "js_errors": 0, "storage_bytes": counts,
        "prohibited_work": {name: 0 for name in ("training", "fine_tuning", "checkpoint_reselection", "model_reselection",
            "p9_rerun", "canonical_p10_acceptance_mutation", "p11_rematerialization", "ridge_mlp_fitting",
            "target_transformation_changes", "canonical_evaluation_replacement", "dissertation_mutation")}})


def accept_production(validation_manifest):
    root = Path(validation_manifest).parent.parent
    method = assert_frozen(root)
    validation = read(validation_manifest)
    if validation["status"] != "PASS" or validation["models"] != 8 or validation["union_count"] != 10000:
        raise ValueError("Complete supplementary validation required")
    parents = {name: digest(root / relative) for name, relative in {
        "methodology": "methodology.json", "sampling_index": "index/supplemental_scene_index.parquet",
        "spatial_truth": "spatial_manifest.json", "scene_cache": "cache/cache_manifest.json",
        "prepared_input": "prepared/prepared_manifest.json", "geometry": "geometry/geometry_manifest.json",
        "embeddings": "embeddings/embedding_manifest.json", "union_gallery": "union/union_manifest.json",
        "rankings": "rankings/ranking_manifest.json", "inspector": "inspector/manifest.json",
        "validation": "validation/validation.json"}.items()}
    scientific = {"schema_version": "1.0.0", "artifact_type": "supplementary_retrieval_gallery_acceptance",
        "authority_id": method["authority_id"], "parents_sha256": parents,
        "canonical_p10_acceptance": "p10acc_6e5071beee7616750dec7907", "canonical_p10_unchanged": True,
        "canonical_p11_unchanged": True, "supplementary_retrieval_only": True,
        "canonical_evaluation_count": 1600, "supplemental_count": 8400, "union_count": 10000,
        "model_count": 8, "query_count": 10, "original_only": True,
        "standard_candidates": 9999, "nonlocal_exclusion_m": 2000,
        "model_selection_reopened": False, "augmented_queries": 0, "downstream_targets": 0,
        "status": "PASS", "prohibited_work": validation["prohibited_work"]}
    identity = "retr10k_" + canonical_sha256(scientific)[:24]
    payload = {"acceptance_id": identity, **scientific}
    from jsonschema import Draft202012Validator
    Draft202012Validator(read(REPOSITORY / "config/schemas/retrieval_gallery/acceptance.schema.json")).validate(payload)
    return publish_json(root / "acceptance" / (identity + ".json"), payload)
