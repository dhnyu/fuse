"""Immutable, acceptance-last S11 bundles. No S09/S10 writer is imported."""
from __future__ import annotations
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import tempfile
from functools import lru_cache
import numpy as np
from representation_analysis import ROOT, file_sha256, load_frozen_contract

SOURCE_FILES = ["config/s11_representation_analysis.json", "config/s11_representation_analysis.lock.json",
    "config/schemas/s11_representation_analysis.schema.json", "python/representation_analysis.py", "python/s11_inputs.py",
    "python/s11_artifacts.py", "python/s11_descriptors.py", "python/s11_alignment.py",
    "python/s11_umap.py", "python/s11_production.py", "R/scene_descriptors.R",
    "R/s11_p3_reader.R", "scripts/s11_descriptor_worker.R", "scripts/s11_production.py",
    "scripts/pilot_s11_production.py", "R/s11_representation.R",
    "targets/s11_representation.R", "_targets_representation.R", "config/s11_execution.json"]
SOURCE_FILES.append("scripts/run_s11_representation.R")

def require(ok, message):
    if not ok:
        raise ValueError("S11_" + message)

def dumps(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False,
                      separators=(",", ":")) + "\n"

def write_json(path, value):
    Path(path).write_text(dumps(value), encoding="utf-8")

def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def configuration():
    contract, lock = load_frozen_contract()
    execution = read_json(ROOT / "config/s11_execution.json")
    require(execution["contract_sha256"] == lock["contract_sha256"], "EXECUTION_CONTRACT")
    require(execution["workers"] == execution["threads"] == 1, "EXECUTION_RESOURCES")
    require(execution["query_block_size"] == 32, "EXECUTION_BLOCK")
    for relative, checksum in execution["observation_config_pins"].items():
        require(file_sha256(ROOT / relative) == checksum, "OBSERVATION_CONTRACT_CHANGED")
    return contract, lock, execution

@lru_cache(maxsize=1)
def r_runtime():
    command = 'cat(jsonlite::toJSON(list(R=R.version.string,packages=setNames(lapply(c("sf","arrow","jsonlite","data.table"),function(p) as.character(packageVersion(p))),c("sf","arrow","jsonlite","data.table")),spatial=as.list(sf::sf_extSoftVersion())),auto_unbox=TRUE))'
    return json.loads(subprocess.check_output(["Rscript", "-e", command], text=True))

def runtime():
    _, _, execution = configuration()
    require(platform.python_version() == execution["python"], "PYTHON_VERSION")
    versions = {p: importlib.metadata.version(p) for p in execution["versions"]}
    require(versions == execution["versions"], "RUNTIME_VERSIONS")
    from threadpoolctl import threadpool_info
    # Deduplicate the same BLAS implementation if a runtime loads several copies.
    blas = [dict(t) for t in sorted({tuple((k,b[k]) for k in ("internal_api","version","architecture","threading_layer"))
        for b in threadpool_info() if b["user_api"]=="blas"})]
    require(blas == execution["blas"], "BLAS_RUNTIME")
    require(r_runtime() == execution["r_runtime"], "R_SPATIAL_RUNTIME")
    return {"python": platform.python_version(), "packages": versions,
            "blas": blas, "r_runtime": r_runtime(),
            "sources": {f: file_sha256(ROOT / f) for f in SOURCE_FILES}}

def context(scope, pilot_root=None):
    contract, lock, execution = configuration()
    provenance = {"scope": scope, "contract_sha256": lock["contract_sha256"],
                  "runtime": runtime(), "checkpoint_id": lock["checkpoint_id"],
                  "embedding_manifest_id": lock["embedding_manifest_id"]}
    if scope == "full":
        require(os.environ.get(execution["authorization_env"]) == execution["authorization_value"], "FULL_EXECUTION_NOT_AUTHORIZED")
        receipt = read_json(os.environ.get(execution["pilot_receipt_env"], "/nonexistent/s11-pilot-receipt"))
        require(receipt["status"] == "PASS" and receipt["runtime"] == provenance["runtime"] and
                receipt["contract_sha256"] == lock["contract_sha256"], "CURRENT_PILOT_REQUIRED")
        root = Path(execution["output_root"])
    else:
        require(scope == "pilot" and pilot_root is not None, "PILOT_CONTEXT")
        root = Path(pilot_root)
        require(root.resolve().is_relative_to(Path(execution["pilot_root"]).resolve()), "PILOT_ROOT")
    generation = hashlib.sha256(dumps(provenance).encode()).hexdigest()[:24]
    return {**provenance, "root": str(root / generation), "generation": generation}

def load_bundle(manifest, kind=None):
    path = Path(manifest)
    value = read_json(path)
    require(value["status"] == "PASS" and (kind is None or value["kind"] == kind), "BUNDLE_KIND_STATUS")
    for name, checksum in value["files"].items():
        require(Path(name).name == name and file_sha256(path.parent / name) == checksum, "BUNDLE_PAYLOAD_HASH")
    return value

def publish(ctx, kind, key, build, parents=()):
    """Build in a private stage, hash/read back, link payloads, link receipt last.

    File links are exclusive, never replacing an existing artifact. A retry may
    reuse only byte-identical existing content, including the final receipt.
    """
    root = Path(ctx["root"]); root.mkdir(parents=True, exist_ok=True)
    destination = root / kind / str(key)
    manifest = destination / "manifest.json"
    parent_hashes = {str(p): file_sha256(p) for p in parents}
    if manifest.exists():
        old = load_bundle(manifest, kind)
        require(old["context"] == ctx and old["parents"] == parent_hashes, "IMMUTABLE_LINEAGE_CONFLICT")
        return str(manifest)
    with tempfile.TemporaryDirectory(prefix=".stage-", dir=root) as temporary:
        stage = Path(temporary)
        metadata = build(stage)
        files = sorted(stage.iterdir())
        require(files and all(p.is_file() and p.name != "manifest.json" for p in files), "BUNDLE_FILES")
        body = {"schema_version": "1.0.0", "status": "PASS", "kind": kind,
                "context": ctx, "parents": parent_hashes,
                "files": {p.name: file_sha256(p) for p in files}, "metadata": metadata}
        # All input manifests must remain unchanged while the stage is built.
        require(all(file_sha256(p) == h for p, h in parent_hashes.items()), "PARENT_CHANGED_DURING_BUILD")
        write_json(stage / "manifest.json", body)
        destination.mkdir(parents=True, exist_ok=True)
        for source in files + [stage / "manifest.json"]:
            target = destination / source.name
            try:
                os.link(source, target)
            except FileExistsError:
                require(file_sha256(source) == file_sha256(target), "IMMUTABLE_CONTENT_CONFLICT")
        load_bundle(manifest, kind)
    return str(manifest)

def payload(manifest, name):
    body = load_bundle(manifest)
    require(name in body["files"], "MISSING_PAYLOAD")
    return Path(manifest).parent / name

def assert_population(ids, expected):
    require(ids == expected and len(ids) == len(set(ids)), "EXACT_POPULATION_ORDER")
