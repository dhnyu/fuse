"""Publish isolated P9 formal-execution authorization artifacts."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml

from canonical_config import canonical_json_bytes
from p9_formal_execution import (
    REQUIRED_DUPLICATE_FIELDS,
    digest,
    duplicate_key,
    runtime_tree_manifest,
    sha256_file,
)

SCHEMA_VERSION = "1.0.0"


def read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text())


def artifact(prefix: str, artifact_type: str, payload: dict[str, Any], identity_field: str) -> dict[str, Any]:
    value = {"schema_version": SCHEMA_VERSION, "artifact_type": artifact_type, **payload}
    value["content_sha256"] = digest(value)
    value[identity_field] = prefix + value["content_sha256"][:24]
    return value


def _validate_root(name: str, spec: dict[str, Any]) -> dict[str, Any]:
    path = Path(spec["path"])
    if not path.is_file():
        raise FileNotFoundError(f"missing isolated P9 immutable root: {name}")
    if path.stat().st_size != int(spec["expected_size"]):
        raise ValueError(f"isolated P9 immutable root size mismatch: {name}")
    if sha256_file(path) != spec["sha256"]:
        raise ValueError(f"isolated P9 immutable root SHA-256 mismatch: {name}")
    value = read_json(path)
    field = spec.get("identity_field")
    if field and value.get(field) != spec.get("expected_identity"):
        raise ValueError(f"isolated P9 immutable root identity mismatch: {name}")
    if value.get("status") not in (None, "PASS"):
        raise ValueError(f"isolated P9 immutable root is not accepted: {name}")
    if value.get("schema_version") is None:
        raise ValueError(f"isolated P9 immutable root schema is missing: {name}")
    return {
        "name": name,
        "canonical_path": str(path.resolve()),
        "artifact_type": spec["artifact_type"],
        "expected_identity": spec.get("expected_identity"),
        "size": path.stat().st_size,
        "sha256": spec["sha256"],
        "schema_version": value["schema_version"],
        "immutability_status": "ACCEPTED_IMMUTABLE_INPUT",
    }


def _validate_cache(config: dict[str, Any]) -> list[dict[str, Any]]:
    root = Path(config["cache"]["root"])
    rows: list[dict[str, Any]] = []
    for spec in config["cache"]["manifests"]:
        path = root / spec["path"]
        if not path.is_file() or path.stat().st_size != int(spec["expected_size"]):
            raise ValueError(f"isolated P9 cache manifest size mismatch: {spec['path']}")
        if sha256_file(path) != spec["sha256"]:
            raise ValueError(f"isolated P9 cache manifest SHA-256 mismatch: {spec['path']}")
        rows.append({"path": str(path.resolve()), "relative_path": spec["path"],
                     "size": path.stat().st_size, "sha256": spec["sha256"]})
    production = read_json(root / "production_cache_manifest.json")
    if production.get("cache_id") != config["cache"]["cache_id"]:
        raise ValueError("isolated P9 production cache identity mismatch")
    if int(production.get("entry_count", -1)) != int(config["cache"]["entry_count"]):
        raise ValueError("isolated P9 production cache entry-count mismatch")
    return rows


def _training_contract(config: dict[str, Any]) -> dict[str, Any]:
    source = config["training_contract"]
    return {
        "runner_class": source["runner_class"],
        "bounded_pilot_output_accepted": False,
        "trajectory": {
            "maximum_epochs": int(source["maximum_epochs"]),
            "updates_per_epoch": int(source["updates_per_epoch"]),
            "maximum_updates": int(source["maximum_updates"]),
        },
        **{key: source[key] for key in (
            "world_size", "global_batch_size", "per_rank_batch_size", "precision",
            "amp", "tf32", "allowed_operational_overrides", "scientific_cli_overrides"
        )},
    }


def build(runtime_config_path: str | Path, publication_config_path: str | Path,
          repository_root: str | Path) -> dict[str, dict[str, Any]]:
    runtime_config = yaml.safe_load(Path(runtime_config_path).read_text())
    publication = yaml.safe_load(Path(publication_config_path).read_text())
    repository = Path(repository_root)
    if runtime_config.get("schema_version") != SCHEMA_VERSION or publication.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported isolated P9 authorization configuration")

    runtime = runtime_tree_manifest(repository, publication["runtime_files"])
    if runtime["runtime_tree_sha256"] != publication["runtime_tree_sha256"]:
        raise ValueError("isolated P9 runtime tree digest mismatch")
    roots = [_validate_root(name, spec) for name, spec in sorted(runtime_config["roots"].items())]
    cache_manifests = _validate_cache(runtime_config)
    loaded = {name: read_json(spec["path"]) for name, spec in runtime_config["roots"].items()}
    matrix = loaded["p8_hyperparameter_matrix"]
    row = next((item for item in matrix["rows"] if item["configuration_id"] == "cfg_main"), None)
    if row is None or row.get("configuration_family") != "hyperparameter":
        raise ValueError("accepted cfg_main is missing")

    parents = {
        "p7_acceptance_id": loaded["p7_acceptance"]["acceptance_id"],
        "p7_runtime_acceptance_id": loaded["p7_runtime_acceptance"]["acceptance_id"],
        "p8_acceptance_id": loaded["p8_acceptance"]["acceptance_id"],
        "p8_hyperparameter_matrix_id": matrix["matrix_id"],
        "p8_bank_index_id": loaded["p8_bank_index"]["index_id"],
        "p9_readiness_id": loaded["p9_readiness"]["readiness_id"],
        "production_cache_acceptance_id": loaded["production_cache_acceptance"]["acceptance_id"],
        "production_cache_id": runtime_config["cache"]["cache_id"],
        "dissertation_commit": runtime_config["dissertation_commit"],
    }
    execution = {
        "pipeline_script": runtime_config["pipeline"]["script"],
        "isolated_store": runtime_config["pipeline"]["store"],
        "main_research_store_prohibited": runtime_config["pipeline"]["main_research_store_prohibited"],
        "implementation_commit": publication["implementation_commit"],
        "runtime_tree_sha256": runtime["runtime_tree_sha256"],
        "runtime_files": [item["path"] for item in runtime["files"]],
        "runtime_file_manifest": runtime["files"],
        "allow_byte_identical_descendant": True,
        "allowed_descendant_changes": "publication_reports_and_bindings_only",
    }
    authority = artifact("p9a_", "p9_formal_training_authority", {
        "status": "PASS", "parents": parents,
        "scientific_implementation_commit": runtime_config["scientific_implementation_commit"],
        "execution_contract": execution,
        "training_contract": _training_contract(runtime_config),
        "validation_contract": runtime_config["validation_contract"],
        "checkpoint_contract": publication["checkpoint_contract"],
        "locking_contract": publication["locking_contract"],
        "formal_attempts_started": 0, "optimizer_updates": 0,
        "evaluation_queries_consumed": 0,
    }, "authority_id")

    fields = {
        "configuration_identity": row["scientific_hash"],
        "seed_identity": runtime_config["execution"]["seed_identity"],
        "p8_acceptance_id": parents["p8_acceptance_id"],
        "p7_runtime_acceptance_id": parents["p7_runtime_acceptance_id"],
        "p9_readiness_id": parents["p9_readiness_id"],
        "production_cache_acceptance_id": parents["production_cache_acceptance_id"],
        "p9_formal_authority_id": authority["authority_id"],
        "authorized_execution_identity": runtime["runtime_tree_sha256"],
        "scientific_implementation_commit": runtime_config["scientific_implementation_commit"],
        "world_size": int(runtime_config["training_contract"]["world_size"]),
    }
    key = duplicate_key(fields)
    attempt_id = "p9attempt_" + digest({"duplicate_key": key, "configuration_id": "cfg_main"})[:24]
    reservation = artifact("p9res_", "p9_formal_attempt_reservation", {
        "status": "AUTHORIZED_NOT_STARTED", "configuration_id": "cfg_main",
        "configuration_identity": row["scientific_hash"], "attempt_id": attempt_id,
        "run_identity_derivation": {"attempt_id": attempt_id,
            "reservation_state": "AUTHORIZED_NOT_STARTED", "actual_launch_commit_required": True,
            "runtime_tree_sha256": runtime["runtime_tree_sha256"]},
        "formal_authority_id": authority["authority_id"], "duplicate_key": key,
        "duplicate_key_fields": fields,
        "duplicate_key_required_fields": list(REQUIRED_DUPLICATE_FIELDS),
        "cache_subset_identity": runtime_config["execution"]["cache_subset_identity"],
        "seed": int(runtime_config["execution"]["seed"]),
        "seed_identity": runtime_config["execution"]["seed_identity"],
        "formal_attempt_started": False, "optimizer_updates": 0,
        "formal_validation_runs": 0, "formal_checkpoints": 0,
        "evaluation_queries_consumed": 0,
    }, "reservation_id")
    preassigned = artifact("p9pre_", "p9_isolated_preassigned_attempt", {
        "status": "AUTHORIZED_NOT_STARTED", "authority_id": authority["authority_id"],
        "reservation_id": reservation["reservation_id"], "attempt_id": attempt_id,
        "configuration_id": "cfg_main", "configuration_identity": row["scientific_hash"],
        "duplicate_key": key, "runtime_tree_sha256": runtime["runtime_tree_sha256"],
        "production_cache_acceptance_id": parents["production_cache_acceptance_id"],
        "formal_attempt_started": False, "optimizer_updates": 0,
        "formal_validation_runs": 0, "checkpoints": 0, "evaluation_queries_consumed": 0,
    }, "preassignment_id")
    superseded = runtime_config["superseded"]
    supersession = artifact("p9sup_", "p9_formal_execution_supersession", {
        "status": "PASS", "superseded": superseded,
        "classification": ["preserved", "scientifically_valid_but_operationally_unexecutable",
                           "unstarted", "superseded", "ineligible_for_formal_execution"],
        "reason": "unsafe first-bootstrap closure traversed historical scientific producers",
        "replacement_authority_id": authority["authority_id"],
        "replacement_reservation_id": reservation["reservation_id"],
        "replacement_attempt_id": attempt_id, "optimizer_updates": 0,
        "formal_validation_runs": 0, "checkpoints": 0, "evaluation_queries_consumed": 0,
    }, "supersession_id")
    inventory = artifact("p9root_", "p9_isolated_immutable_root_inventory", {
        "status": "PASS", "roots": roots, "cache_manifests": cache_manifests,
        "cache_id": runtime_config["cache"]["cache_id"],
        "cache_entry_count": int(runtime_config["cache"]["entry_count"]),
        "cache_inventory_file_count": int(runtime_config["cache"]["inventory_file_count"]),
        "cache_physical_bytes": int(runtime_config["cache"]["physical_bytes"]),
    }, "inventory_id")
    acceptance = artifact("p9xacc_", "p9_isolated_execution_authorization_acceptance", {
        "status": "PASS", "authority_id": authority["authority_id"],
        "reservation_id": reservation["reservation_id"], "attempt_id": attempt_id,
        "preassignment_id": preassigned["preassignment_id"],
        "supersession_id": supersession["supersession_id"],
        "root_inventory_id": inventory["inventory_id"],
        "runtime_tree_sha256": runtime["runtime_tree_sha256"],
        "pipeline_script": runtime_config["pipeline"]["script"],
        "isolated_store": runtime_config["pipeline"]["store"],
        "formal_attempts_started": 0, "optimizer_updates": 0,
        "formal_validation_runs": 0, "checkpoints": 0,
        "evaluation_queries_consumed": 0, "gpu_executions": 0,
    }, "acceptance_id")
    return {
        "immutable_root_inventory": inventory,
        "formal_execution_supersession": supersession,
        "formal_training_authority": authority,
        "cfg_main_attempt_reservation": reservation,
        "cfg_main_preassigned_attempt": preassigned,
        "execution_authorization_acceptance": acceptance,
    }


def atomic_publish(root: Path, values: dict[str, dict[str, Any]]) -> list[Path]:
    payloads = {f"{name}.json": canonical_json_bytes(value) for name, value in values.items()}
    if root.exists():
        for name, payload in payloads.items():
            if not (root / name).is_file() or (root / name).read_bytes() != payload:
                raise FileExistsError("immutable isolated P9 authorization publication collision")
    else:
        root.parent.mkdir(parents=True, exist_ok=True)
        stage = root.with_name(f".{root.name}.tmp-{os.getpid()}")
        stage.mkdir()
        for name, payload in payloads.items():
            (stage / name).write_bytes(payload)
        os.replace(stage, root)
    return [root / name for name in sorted(payloads)]


def publish(runtime_config_path: str | Path, publication_config_path: str | Path,
            repository_root: str | Path) -> list[Path]:
    values = build(runtime_config_path, publication_config_path, repository_root)
    config = yaml.safe_load(Path(runtime_config_path).read_text())
    root = Path(config["execution"]["publication_root"]) / values["formal_training_authority"]["authority_id"]
    return atomic_publish(root, values)
