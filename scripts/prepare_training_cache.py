#!/usr/bin/env python3
"""Build the optimizer-free current S09 prepared cache from accepted P3-P6 inputs."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import multiprocessing as mp
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping

import pyarrow.parquet as pq
import torch
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from artifact_protocol import canonical_json_bytes, canonical_sha256, sha256_file  # noqa: E402
from model_data import (  # noqa: E402
    ArtifactCatalog, _delta_tables, apply_delta, build_vocabulary, read_fixed_query,
    read_original_scene, ragged_collate, tensorize_scene,
)
from model_families import ds_raster_from_batch  # noqa: E402
from scene_encoder import geometry_fourier_features  # noqa: E402
from training_campaign import cache_identity, current_lineage  # noqa: E402
from training_geometry_cache import GeometryCacheWriter, cache_record  # noqa: E402
from training_prepared_cache import DS_RASTER_CONTRACT_ID  # noqa: E402
from training_schema import validate_instance  # noqa: E402


PROFILE_K = {"weak_0.5x": 8, "main_1.0x": 16, "strong_2.0x": 8}
EXPECTED_ENTRIES = 80_472
_VALUES: dict[str, Any] | None = None


def atomic_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != payload:
            raise FileExistsError(f"immutable publication collision: {path}")
        return
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_bytes(payload); os.replace(temporary, path)


class PreparedCatalog(ArtifactCatalog):
    def __init__(self, roots: Mapping[str, str], expected: Mapping[str, str], verify: bool = True):
        super().__init__(dict(roots), dict(expected), verify=verify)
        acceptance = next((self.roots["p4"] / "acceptance").glob("*/effective_bank_index.parquet"))
        rows = pq.read_table(acceptance).to_pylist()
        self.selected: dict[str, dict[str, dict[int, dict[str, Any]]]] = {}
        for profile, requested_k in PROFILE_K.items():
            selected = [row for row in rows if row["profile_id"] == profile
                        and int(row["requested_k"]) == requested_k]
            if len(selected) != 2421 * requested_k:
                raise ValueError(f"S09 prepared-cache {profile} membership mismatch")
            grouped: dict[str, dict[int, dict[str, Any]]] = {}
            for row in selected:
                grouped.setdefault(row["scene_id"], {})[int(row["master_view_id"])] = row
            if len(grouped) != 2421 or any(len(value) != requested_k for value in grouped.values()):
                raise ValueError(f"S09 prepared-cache {profile} scene coverage mismatch")
            self.selected[profile] = grouped
        parent_by_sha = {row["payload_sha256"]: row["branch_id"] for row in self.p3_rows}
        self.profile_branches = {}
        for profile in PROFILE_K:
            branches = {}
            for manifest_path in sorted((self.roots["p4"] / "shards" / profile).glob("*/branch_manifest.json")):
                manifest = json.loads(manifest_path.read_text())
                parent = parent_by_sha.get(manifest["parent_tar_sha256"])
                if parent is None:
                    raise ValueError("S09 prepared-cache P4/P3 branch mismatch")
                branches[parent] = (manifest_path.parent / manifest["payload"]["filename"], manifest)
            if len(branches) != 96:
                raise ValueError(f"S09 prepared-cache {profile} branch coverage mismatch")
            self.profile_branches[profile] = branches

    def training_view(self, profile: str, scene_id: str, view: int) -> dict[str, Any]:
        row = self.selected[profile].get(scene_id, {}).get(int(view))
        if row is None:
            raise ValueError("S09 prepared-cache training view missing")
        parent = self.p3_by_scene[scene_id]
        path, _ = self.profile_branches[profile][parent["branch_id"]]
        self._verify(path, self.profile_branches[profile][parent["branch_id"]][1]["payload"]["sha256"])
        return apply_delta(read_original_scene(self, scene_id),
                           _delta_tables(path, "candidate_id", row["candidate_id"]),
                           row["candidate_id"], profile)


def canonical_specs(catalog: PreparedCatalog) -> list[dict[str, Any]]:
    rows = []
    for profile in sorted(PROFILE_K):
        role = "training" if profile == "main_1.0x" else f"training:{profile}"
        for scene_id in sorted(catalog.selected[profile]):
            for view, source in sorted(catalog.selected[profile][scene_id].items()):
                rows.append({"role": role, "profile": profile, "scene_id": scene_id,
                             "view": view, "candidate_id": source["candidate_id"]})
    for source in catalog.query_rows["validation"]:
        rows.append({"role": "validation_query", "profile": source["profile_id"],
                     "scene_id": source["scene_id"], "view": int(source["query_index"]),
                     "candidate_id": source["query_id"]})
    for source in catalog.gallery_rows["validation"]:
        rows.append({"role": "validation_gallery", "profile": "original",
                     "scene_id": source["scene_id"], "view": None, "candidate_id": "original"})
    rows.sort(key=lambda row: (row["role"], row["scene_id"], -1 if row["view"] is None else row["view"]))
    for index, row in enumerate(rows): row["global_index"] = index
    if len(rows) != EXPECTED_ENTRIES:
        raise ValueError("S09 prepared-cache must contain exactly 80,472 entries")
    return rows


def load_values(contract_path: str | Path, verify: bool) -> dict[str, Any]:
    contract = yaml.safe_load(Path(contract_path).read_text())
    training = yaml.safe_load((ROOT / "config/training.yml").read_text())
    expected = training["parents"]
    catalog = PreparedCatalog({key: contract["roots"][key] for key in ("p3", "p4", "p5")}, expected, verify)
    preprocessing = json.loads(Path(contract["roots"]["preprocessing"]).read_text())
    vocabulary = build_vocabulary(contract["roots"]["categories"])
    model = yaml.safe_load((ROOT / "config/model_inputs.yml").read_text())
    return {"contract": contract, "training": training, "catalog": catalog, "preprocessing": preprocessing,
            "vocabulary": vocabulary, "model": model}


def sample_for(values: Mapping[str, Any], spec: Mapping[str, Any]) -> dict[str, Any]:
    catalog = values["catalog"]
    if str(spec["role"]).startswith("training"):
        scene = catalog.training_view(spec["profile"], spec["scene_id"], int(spec["view"]))
    elif spec["role"] == "validation_query":
        scene = read_fixed_query(catalog, "validation", spec["scene_id"], int(spec["view"]))
    else:
        scene = read_original_scene(catalog, spec["scene_id"])
    return tensorize_scene(scene, values["preprocessing"], values["vocabulary"])


def worker_init(contract: str) -> None:
    global _VALUES
    for key in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        os.environ[key] = "1"
    torch.set_num_threads(1)
    _VALUES = load_values(contract, verify=False)


def prepare_one(task: tuple[dict[str, Any], str]) -> dict[str, Any]:
    spec, staging_text = task
    assert _VALUES is not None
    staging = Path(staging_text); index = int(spec["global_index"])
    prepared_path = staging / "prepared" / f"{index:06d}.pt"
    sample = sample_for(_VALUES, spec)
    batch = ragged_collate([sample])
    magnitude, phase = geometry_fourier_features(batch, _VALUES["model"]["model"], torch.device("cpu"))
    record = cache_record(sample, _VALUES["training"]["parents"], _VALUES["model"]["model"]["geometry"],
                          sha256_file(ROOT / "python/scene_encoder.py"), spec["role"])
    GeometryCacheWriter(staging / "geometry").put(record, magnitude, phase)
    ds = ds_raster_from_batch(batch)[0].contiguous()
    ds_identity = {"schema_version": "1.0.0", "contract_id": DS_RASTER_CONTRACT_ID,
                   "geometry_layout_version": "3.0.0", "role": spec["role"],
                   "scene_id": spec["scene_id"], "view_id": str(spec["candidate_id"]),
                   "source_cache_key": record["cache_key"], "shape": list(ds.shape),
                   "dtype": str(ds.dtype), "raw_sha256": hashlib.sha256(ds.numpy().tobytes()).hexdigest()}
    ds_identity["cache_key"] = canonical_sha256(ds_identity)
    ds_path = staging / "ds/entries" / f"{ds_identity['cache_key']}.pt"
    ds_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = ds_path.with_name(f".{ds_path.name}.{os.getpid()}.tmp")
    torch.save({"manifest": ds_identity, "raster": ds}, temporary); os.replace(temporary, ds_path)
    prepared_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = prepared_path.with_name(f".{prepared_path.name}.{os.getpid()}.tmp")
    torch.save({"global_index": index, "spec": spec, "sample": sample}, temporary); os.replace(temporary, prepared_path)
    return {"global_index": index, "spec": spec, "record": record, "ds": ds_identity,
            "prepared_sha256": sha256_file(prepared_path), "prepared_size": prepared_path.stat().st_size,
            "ds_sha256": sha256_file(ds_path), "ds_size": ds_path.stat().st_size}


def validate_cache(root: str | Path, verify_payloads: bool = True) -> dict[str, Any]:
    root = Path(root); manifest_path = root / "production_cache_manifest.json"
    manifest = json.loads(manifest_path.read_text()); plan = json.loads((root / "canonical_cache_plan.json").read_text())
    acceptance = json.loads((root / "acceptance.json").read_text())
    validate_instance("prepared_cache_acceptance", acceptance)
    acceptance_scientific = {key: value for key, value in acceptance.items()
                             if key not in {"acceptance_id", "content_sha256"}}
    acceptance_digest = canonical_sha256(acceptance_scientific)
    scientific = {key: value for key, value in manifest.items() if key not in {"cache_id", "content_sha256"}}
    digest = canonical_sha256(scientific)
    expected_id, _ = cache_identity(manifest.get("parents", {}), str(manifest.get("membership_sha256", "")),
                                    int(manifest.get("entry_count", -1)))
    if (manifest.get("content_sha256") != digest or manifest.get("cache_id") != expected_id
            or plan.get("entry_count") != manifest.get("entry_count")
            or acceptance.get("status") != "PASS" or acceptance.get("cache_id") != manifest.get("cache_id")
            or acceptance.get("manifest_sha256") != sha256_file(manifest_path)
            or acceptance.get("content_sha256") != acceptance_digest
            or acceptance.get("acceptance_id") != "s09ca_" + acceptance_digest[:24]):
        raise ValueError("S09 prepared-cache identity/acceptance mismatch")
    if verify_payloads:
        for row in manifest["entries"]:
            path = root / "prepared" / f"{int(row['global_index']):06d}.pt"
            if not path.is_file() or path.stat().st_size != row["prepared_size"] or sha256_file(path) != row["prepared_sha256"]:
                raise ValueError("S09 prepared-cache payload mismatch")
    return acceptance


def build(contract_path: str | Path, workers: int, fixture_limit: int | None = None,
          fixture_root: str | Path | None = None) -> Path:
    values = load_values(contract_path, verify=True)
    plan_rows = canonical_specs(values["catalog"])
    fixture = fixture_limit is not None
    if fixture: plan_rows = plan_rows[:int(fixture_limit)]
    lineage = current_lineage(json.loads(Path(values["contract"]["roots"]["experiment_plan"]).read_text()), values["contract"])
    membership = canonical_sha256(plan_rows)
    lineage = {**lineage, "cache_implementation_sha256": sha256_file(Path(__file__))}
    provisional_id, _ = cache_identity(lineage, membership, len(plan_rows))
    publication = Path(fixture_root) if fixture_root else Path(values["contract"]["roots"]["production_cache"])
    destination = publication / provisional_id
    if destination.exists():
        validate_cache(destination); return destination / "acceptance.json"
    staging = Path(tempfile.mkdtemp(prefix="s09-cache-", dir=str(publication.parent if not fixture else publication.parent)))
    try:
        plan = {"schema_version": "1.0.0", "parents": lineage, "entry_count": len(plan_rows),
                "membership_sha256": membership, "entries": plan_rows, "fixture_only": fixture}
        atomic_bytes(staging / "canonical_cache_plan.json", canonical_json_bytes(plan))
        if workers == 1:
            worker_init(str(contract_path)); rows = [prepare_one((row, str(staging))) for row in plan_rows]
        else:
            with concurrent.futures.ProcessPoolExecutor(max_workers=workers, mp_context=mp.get_context("spawn"),
                    initializer=worker_init, initargs=(str(contract_path),)) as pool:
                rows = list(pool.map(prepare_one, [(row, str(staging)) for row in plan_rows], chunksize=1))
        rows.sort(key=lambda row: row["global_index"])
        geometry = GeometryCacheWriter(staging / "geometry").finalize(provisional_id, [row["record"] for row in rows])
        ds_entries = [{**row["ds"], "global_index": row["global_index"],
                       "relative_path": f"entries/{row['ds']['cache_key']}.pt",
                       "payload_size_bytes": row["ds_size"], "payload_sha256": row["ds_sha256"]} for row in rows]
        ds_scientific = {"schema_version": "1.0.0", "status": "PASS", "contract_id": DS_RASTER_CONTRACT_ID,
                         "entry_count": len(rows), "entries": ds_entries}
        ds_hash = canonical_sha256(ds_scientific)
        ds_manifest = {**ds_scientific, "content_sha256": ds_hash, "cache_id": "s09ds_" + ds_hash[:24]}
        atomic_bytes(staging / "ds/ds_cache_manifest.json", canonical_json_bytes(ds_manifest))
        scientific = {"schema_version": "1.0.0", "status": "PASS", "parents": lineage,
                      "entry_count": len(rows), "membership_sha256": membership,
                      "plan_sha256": sha256_file(staging / "canonical_cache_plan.json"), "entries": rows,
                      "geometry": {"cache_id": geometry["cache_id"], "manifest_sha256": sha256_file(staging / "geometry/geometry_cache_manifest.json")},
                      "ds": {"cache_id": ds_manifest["cache_id"], "manifest_sha256": sha256_file(staging / "ds/ds_cache_manifest.json")},
                      "execution_counts": {"optimizer_updates": 0, "training_runs": 0}, "fixture_only": fixture}
        digest = canonical_sha256(scientific); cache_id = provisional_id
        manifest = {**scientific, "content_sha256": digest, "cache_id": cache_id}
        atomic_bytes(staging / "production_cache_manifest.json", canonical_json_bytes(manifest))
        acceptance_content = {"schema_version": "1.0.0", "status": "PASS", "cache_id": cache_id,
                              "parents": lineage, "manifest_sha256": sha256_file(staging / "production_cache_manifest.json"),
                              "entry_count": len(rows), "optimizer_updates": 0, "training_runs": 0, "fixture_only": fixture}
        acceptance_hash = canonical_sha256(acceptance_content)
        acceptance = {**acceptance_content, "acceptance_id": "s09ca_" + acceptance_hash[:24],
                      "content_sha256": acceptance_hash}
        validate_instance("prepared_cache_acceptance", acceptance)
        atomic_bytes(staging / "acceptance.json", canonical_json_bytes(acceptance))
        destination = publication / cache_id
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            validate_cache(destination)
        else: os.replace(staging, destination)
        validate_cache(destination)
        return destination / "acceptance.json"
    finally:
        if staging.exists(): shutil.rmtree(staging)


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("mode", choices=("build", "validate"))
    parser.add_argument("--contract", default="config/training_controller.yml")
    parser.add_argument("--workers", type=int, default=16); parser.add_argument("--root")
    parser.add_argument("--fixture-limit", type=int)
    args = parser.parse_args()
    if args.mode == "build":
        print(build(args.contract, args.workers, args.fixture_limit, args.root))
    else:
        print(json.dumps(validate_cache(args.root), sort_keys=True))


if __name__ == "__main__": main()
