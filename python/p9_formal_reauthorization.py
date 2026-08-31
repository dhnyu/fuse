"""Immutable P9 formal-execution reauthorization publication."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml

from canonical_config import canonical_json_bytes
from p9_formal_execution import REQUIRED_DUPLICATE_FIELDS, digest, duplicate_key, runtime_tree_manifest, sha256_file

SCHEMA_VERSION = "1.0.0"


def read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text())


def artifact(prefix: str, artifact_type: str, payload: dict[str, Any], identity_field: str) -> dict[str, Any]:
    value = {"schema_version": SCHEMA_VERSION, "artifact_type": artifact_type, **payload}
    value["content_sha256"] = digest(value); value[identity_field] = prefix + value["content_sha256"][:24]
    return value


def atomic_publish(root: Path, values: dict[str, dict[str, Any]]) -> list[Path]:
    payloads = {f"{name}.json": canonical_json_bytes(value) for name, value in values.items()}
    if root.exists():
        if any(not (root / name).is_file() or (root / name).read_bytes() != payload
               for name, payload in payloads.items()):
            raise FileExistsError("immutable P9 reauthorization publication collision")
    else:
        root.parent.mkdir(parents=True, exist_ok=True)
        stage = root.with_name(f".{root.name}.tmp-{os.getpid()}"); stage.mkdir()
        for name, payload in payloads.items(): (stage / name).write_bytes(payload)
        os.replace(stage, root)
    return [root / name for name in sorted(payloads)]


def _id(value: dict[str, Any], field: str, expected: str, label: str) -> None:
    if value.get(field) != expected:
        raise ValueError(f"{label} identity mismatch: {field}")


def build(config_path: str | Path, repository_root: str | Path) -> dict[str, dict[str, Any]]:
    config = yaml.safe_load(Path(config_path).read_text()); root = Path(repository_root)
    if config.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported P9 reauthorization configuration")
    runtime = runtime_tree_manifest(root, config["execution_contract"]["runtime_files"])
    if runtime["runtime_tree_sha256"] != config["execution_contract"]["runtime_tree_sha256"]:
        raise ValueError("reauthorization runtime tree digest mismatch")
    parents = config["parents"]; paths = config["artifacts"]
    required = {
        "p8": (paths["p8_acceptance"], "acceptance_id", parents["p8_acceptance_id"]),
        "runtime": (paths["p7_runtime_acceptance"], "acceptance_id", parents["p7_runtime_acceptance_id"]),
        "readiness": (paths["p9_readiness"], "readiness_id", parents["p9_readiness_id"]),
        "cache": (paths["production_cache_acceptance"], "acceptance_id", parents["production_cache_acceptance_id"]),
        "matrix": (paths["p8_hyperparameter_matrix"], "matrix_id", parents["p8_hyperparameter_matrix_id"]),
    }
    loaded = {}
    for label, (path, field, expected) in required.items():
        loaded[label] = read_json(path); _id(loaded[label], field, expected, label)
    rows = loaded["matrix"]["rows"]
    cfg = next((row for row in rows if row["configuration_id"] == "cfg_main"), None)
    if cfg is None or cfg.get("configuration_family") != "hyperparameter":
        raise ValueError("accepted cfg_main is missing")
    execution = {"implementation_commit": config["execution_contract"]["implementation_commit"],
                 "runtime_tree_sha256": runtime["runtime_tree_sha256"],
                 "runtime_files": [row["path"] for row in runtime["files"]],
                 "runtime_file_manifest": runtime["files"],
                 "allow_byte_identical_descendant": True,
                 "allowed_descendant_changes": "publication_reports_and_bindings_only"}
    authority = artifact("p9a_", "p9_formal_training_authority", {
        "status": "PASS", "parents": parents, "scientific_implementation_commit": config["scientific_implementation_commit"],
        "execution_contract": execution, "training_contract": config["training_contract"],
        "validation_contract": config["validation_contract"], "checkpoint_contract": config["checkpoint_contract"],
        "locking_contract": config["locking_contract"], "formal_attempts_started": 0,
        "optimizer_updates": 0, "evaluation_queries_consumed": 0,
    }, "authority_id")
    duplicate_fields = {
        "configuration_identity": cfg["scientific_hash"],
        "seed_identity": config["cfg_main"]["seed_identity"],
        "p8_acceptance_id": parents["p8_acceptance_id"],
        "p7_runtime_acceptance_id": parents["p7_runtime_acceptance_id"],
        "p9_readiness_id": parents["p9_readiness_id"],
        "production_cache_acceptance_id": parents["production_cache_acceptance_id"],
        "p9_formal_authority_id": authority["authority_id"],
        "authorized_execution_identity": runtime["runtime_tree_sha256"],
        "scientific_implementation_commit": config["scientific_implementation_commit"],
        "world_size": 2, "isolated_store_generation": "legacy_main_pipeline",
    }
    key = duplicate_key(duplicate_fields)
    attempt_id = "p9attempt_" + digest({"duplicate_key": key, "configuration_id": "cfg_main"})[:24]
    run_derivation = {"attempt_id": attempt_id, "reservation_state": "AUTHORIZED_NOT_STARTED",
                      "actual_launch_commit_required": True, "runtime_tree_sha256": runtime["runtime_tree_sha256"]}
    reservation = artifact("p9res_", "p9_formal_attempt_reservation", {
        "status": "AUTHORIZED_NOT_STARTED", "configuration_id": "cfg_main",
        "configuration_identity": cfg["scientific_hash"], "attempt_id": attempt_id,
        "run_identity_derivation": run_derivation, "formal_authority_id": authority["authority_id"],
        "duplicate_key": key, "duplicate_key_fields": duplicate_fields,
        "duplicate_key_required_fields": list(REQUIRED_DUPLICATE_FIELDS),
        "cache_subset_identity": config["cfg_main"]["cache_subset_identity"],
        "seed": int(config["cfg_main"]["seed"]), "seed_identity": config["cfg_main"]["seed_identity"],
        "formal_attempt_started": False, "optimizer_updates": 0, "formal_validation_runs": 0,
        "formal_checkpoints": 0, "evaluation_queries_consumed": 0,
    }, "reservation_id")
    supersession = artifact("p9sup_", "p9_formal_execution_supersession", {
        "status": "PASS", "superseded": config["superseded"],
        "classification": ["preserved", "unexecuted", "superseded", "ineligible_for_formal_execution"],
        "reason": "execution commit mismatch, incomplete duplicate key, and missing formal execution DAG",
        "replacement_authority_id": authority["authority_id"],
        "replacement_reservation_id": reservation["reservation_id"],
        "optimizer_updates": 0, "formal_validation_runs": 0, "checkpoints": 0,
        "evaluation_queries_consumed": 0,
    }, "supersession_id")
    return {"corrected_formal_authority": authority, "corrected_cfg_main_reservation": reservation,
            "formal_execution_supersession": supersession}


def publish(config_path: str | Path, repository_root: str | Path) -> list[Path]:
    config = yaml.safe_load(Path(config_path).read_text()); values = build(config_path, repository_root)
    root = Path(config["publication_root"]) / values["corrected_formal_authority"]["authority_id"]
    return atomic_publish(root, values)
