"""P9 production-cache planning, immutable publication, and formal reservation gates."""

from __future__ import annotations

import hashlib
import json
import os
import socket
import time
from pathlib import Path
from typing import Any, Iterable

import pyarrow.parquet as pq
import yaml

from canonical_config import canonical_json_bytes

SCHEMA_VERSION = "1.0.0"
ARTIFACT_NAMES = (
    "cache_reuse_graph", "cache_identity_contract", "cache_resource_plan",
    "cache_shard_plan", "production_cache_build_authority",
)
PREFIXES = {
    "cache_reuse_graph": "p9crg_", "cache_identity_contract": "p9cic_",
    "cache_resource_plan": "p9crp_", "cache_shard_plan": "p9csp_",
    "production_cache_build_authority": "p9cba_",
}


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def sha256_file(path: str | Path) -> str:
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text())


def load_config(path: str | Path) -> dict[str, Any]:
    value = yaml.safe_load(Path(path).read_text())
    if value.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported P9 formal-authorization contract")
    cache = value["cache"]
    if cache["allowed_profiles"] != {"main_1.0x": 16, "weak_0.5x": 8, "strong_2.0x": 8}:
        raise ValueError("P9 canonical cache profile/K union mismatch")
    if (cache["geometry_layout_version"], cache["ds_shape"], cache["ds_dtype"]) != (
            "3.0.0", [26, 100, 100], "torch.float32"):
        raise ValueError("P9 cache scientific layout mismatch")
    if value["formal"]["cfg_main_status"] != "AUTHORIZED_NOT_STARTED":
        raise ValueError("P9 configuration must remain unstarted during authorization")
    return value


def _require_id(value: dict[str, Any], field: str, expected: str, path: Path) -> None:
    if value.get(field) != expected:
        raise ValueError(f"canonical lineage mismatch in {path}: {field}")


def validate_lineage(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    parents, paths = config["parents"], config["artifacts"]
    readiness_path = Path(paths["p9_readiness"]); readiness = read_json(readiness_path)
    _require_id(readiness, "readiness_id", parents["p9_readiness_id"], readiness_path)
    if readiness.get("source_commit") != config["readiness_implementation_commit"]:
        raise ValueError("P9 readiness implementation commit mismatch")
    p8_root = Path(paths["p8_bundle_root"])
    names = {
        "acceptance": "formal_experiment_plan_acceptance.json",
        "hyper": "hyperparameter_configuration_matrix.json",
        "comparisons": "comparison_variant_template_matrix.json",
        "a5": "a5_generic_relation_mapping_contract.json",
        "ds": "ds_raster_materialization_contract.json",
        "bank": "experiment_augmentation_bank_index.json",
    }
    bundle = {key: read_json(p8_root / filename) for key, filename in names.items()}
    checks = (
        ("acceptance", "acceptance_id", "p8_acceptance_id"),
        ("acceptance", "authority_id", "p8_authority_id"),
        ("hyper", "matrix_id", "p8_hyperparameter_matrix_id"),
        ("comparisons", "matrix_id", "p8_comparison_matrix_id"),
        ("a5", "contract_id", "p8_a5_contract_id"),
        ("ds", "contract_id", "p8_ds_contract_id"),
        ("bank", "index_id", "p8_bank_index_id"),
    )
    for key, field, parent in checks:
        _require_id(bundle[key], field, parents[parent], p8_root / names[key])
    runtime_path = Path(paths["p7_runtime_acceptance"]); runtime = read_json(runtime_path)
    _require_id(runtime, "acceptance_id", parents["p7_runtime_acceptance_id"], runtime_path)
    p7_path = Path(paths["p7_acceptance"]); p7 = read_json(p7_path)
    _require_id(p7, "acceptance_id", parents["p7_acceptance_id"], p7_path)
    if p7.get("best_checkpoint", {}).get("checkpoint_id") != parents["p7_selected_checkpoint_id"]:
        raise ValueError("P7 canonical selected checkpoint mismatch")
    if bundle["hyper"].get("count") != 13 or bundle["comparisons"].get("count") != 7:
        raise ValueError("P8 13+7 plan mismatch")
    if bundle["comparisons"].get("materialized_count") != 0:
        raise ValueError("P9-B templates were prematurely materialized")
    if any(row.get("evaluation_ancestry") is not False for row in
           [*bundle["hyper"]["rows"], *bundle["comparisons"]["templates"]]):
        raise ValueError("evaluation ancestry entered P9")
    return {**bundle, "readiness": readiness, "runtime": runtime, "p7": p7}


def effective_bank_rows(config: dict[str, Any]) -> list[dict[str, Any]]:
    paths = list((Path(config["roots"]["p4"]) / "acceptance").glob("*/effective_bank_index.parquet"))
    if len(paths) != 1:
        raise ValueError("accepted P4 effective bank index is missing or ambiguous")
    return pq.read_table(paths[0]).to_pylist()


def canonical_membership(config: dict[str, Any], bundle: dict[str, Any]) -> dict[str, Any]:
    rows = effective_bank_rows(config)
    profiles = config["cache"]["allowed_profiles"]
    selected: dict[str, list[dict[str, Any]]] = {}
    for profile, requested_k in profiles.items():
        values = [row for row in rows if row["profile_id"] == profile and int(row["requested_k"]) == requested_k]
        values.sort(key=lambda row: (row["scene_id"], int(row["master_view_id"]), row["candidate_id"]))
        if len(values) != 2421 * requested_k:
            raise ValueError(f"P4 {profile}/K{requested_k} population mismatch")
        keys = [(row["scene_id"], int(row["master_view_id"])) for row in values]
        if len(keys) != len(set(keys)):
            raise ValueError(f"P4 {profile}/K{requested_k} composite identity collision")
        selected[profile] = values
    main_rows = [row for row in rows if row["profile_id"] == "main_1.0x"]
    subset = {}
    full = {(row["scene_id"], int(row["master_view_id"])): row["candidate_id"]
            for row in selected["main_1.0x"]}
    for k in (2, 4, 8, 16):
        current = [row for row in main_rows if int(row["requested_k"]) == k]
        current.sort(key=lambda row: (row["scene_id"], int(row["master_view_id"])))
        if len(current) != 2421 * k:
            raise ValueError(f"main K{k} population mismatch")
        differences = sum(full.get((row["scene_id"], int(row["master_view_id"]))) != row["candidate_id"]
                          for row in current)
        if differences:
            raise ValueError(f"main K{k} is not byte-identity-addressable within K16")
        subset[str(k)] = {
            "entry_count": len(current),
            "membership_sha256": digest([[row["scene_id"], int(row["master_view_id"]), row["candidate_id"]]
                                          for row in current]),
            "candidate_differences_from_k16": differences,
            "payload_policy": "INDEX_ONLY_REFERENCE_TO_MAIN_K16",
        }
    validation_count = 1200
    profile_counts = {profile: len(values) for profile, values in selected.items()}
    union_count = sum(profile_counts.values()) + validation_count
    return {
        "profile_counts": profile_counts, "validation_count": validation_count,
        "canonical_union_count": union_count, "main_subsets": subset,
        "profile_membership_sha256": {profile: digest([
            [row["scene_id"], int(row["master_view_id"]), row["candidate_id"]] for row in values
        ]) for profile, values in selected.items()},
        "all_training_membership_sha256": digest([
            [profile, row["scene_id"], int(row["master_view_id"]), row["candidate_id"]]
            for profile in sorted(selected) for row in selected[profile]
        ]),
        "hyperparameter_scientific_hashes": [row["scientific_hash"] for row in bundle["hyper"]["rows"]],
        "comparison_template_hashes": [row["template_hash"] for row in bundle["comparisons"]["templates"]],
    }


def _artifact(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    value = {"schema_version": SCHEMA_VERSION, "artifact_type": name, **payload}
    value["content_sha256"] = digest(value)
    value["artifact_id"] = PREFIXES[name] + value["content_sha256"][:24]
    return value


def build_plan_bundle(config_path: str | Path, source_commit: str, execution_commit: str) -> dict[str, Any]:
    config = load_config(config_path); bundle = validate_lineage(config)
    membership = canonical_membership(config, bundle)
    if source_commit != config["canonical_implementation_commit"]:
        raise ValueError("canonical P9 publication commit mismatch")
    parents = {**config["parents"], "scientific_implementation_commit": source_commit,
               "execution_repository_commit": execution_commit}
    reuse = _artifact("cache_reuse_graph", {
        "status": "PASS", "parents": parents, "membership": membership,
        "rules": {
            "main_k2_k4_k8": "canonical prefix indexes into main K16; no payload duplication",
            "intensity_profiles": "distinct realized scientific bytes",
            "model_only_reuse": ["d", "d_c", "ema", "lambda_ip", "peak_learning_rate", "dropout"],
            "entity_raster_source": "shared immutable P3/P4/P5 realized-view payloads",
            "fm_a1_a2_a3_a4_a5_ssv": "consume modality subsets from shared realized views",
            "ds": "separate 26x100x100 derived raster; no duplicated upstream observation",
            "rank_worker_batch_host_independent": True,
        },
    })
    identity = _artifact("cache_identity_contract", {
        "status": "PASS", "parents": parents, "reuse_graph_id": reuse["artifact_id"],
        "scientific_byte_dimensions": [
            "geometry_layout_version", "p4_bank_id", "profile_id", "scene_id", "candidate_or_query_identity",
            "source_payload_sha256", "realized_geometry_sha256", "entity_order_sha256",
            "preprocessing_id", "feature_implementation_sha256", "dtype", "shape", "ds_contract_id",
        ],
        "excluded_execution_dimensions": ["rank", "worker_count", "batch_order", "hostname", "gpu_id"],
        "cache_families": ["accepted_realized_view_source", "geometry_fourier_v3", "ds_raster_26x100x100"],
        "layout_version": "3.0.0", "ds_contract_id": config["parents"]["p8_ds_contract_id"],
    })
    count = int(membership["canonical_union_count"]); cache = config["cache"]
    geometry = count * int(cache["expected_geometry_raw_bytes_per_entry"])
    ds = count * int(cache["expected_ds_raw_bytes_per_entry"])
    staging = int(geometry * 1.34)
    planned = geometry + ds + staging
    resource = _artifact("cache_resource_plan", {
        "status": "PASS", "parents": parents, "reuse_graph_id": reuse["artifact_id"],
        "expected": {"entry_count_per_derived_family": count, "geometry_raw_bytes": geometry,
                     "ds_raw_bytes": ds, "temporary_staging_bytes": staging,
                     "peak_total_additional_bytes": planned, "shard_count": int(cache["shard_count"]),
                     "build_wall_seconds_lower": 30000, "build_wall_seconds_upper": 45000,
                     "peak_rss_bytes": int(cache["measured_32_worker_peak_rss_bytes"])},
        "admission": {"minimum_free_space_bytes": int(cache["minimum_free_space_bytes"]),
                      "memory_safety_fraction": float(cache["memory_safety_fraction"]),
                      "worker_tiers": cache["cpu_worker_tiers"]},
        "roots": {key: config["roots"][key] for key in ("cache", "staging")},
    })
    shards = int(cache["shard_count"])
    shard_counts = [count // shards + (1 if index < count % shards else 0) for index in range(shards)]
    shard = _artifact("cache_shard_plan", {
        "status": "PASS", "parents": parents, "identity_contract_id": identity["artifact_id"],
        "assignment": "canonical_global_index_modulo_shard_count", "shard_count": shards,
        "expected_entries_per_shard": shard_counts, "canonical_manifest_order": "global_index_ascending",
        "atomic_publication": True, "resumable_at_entry_and_shard_boundaries": True,
    })
    authority = _artifact("production_cache_build_authority", {
        "status": "CACHE_BUILD_ONLY", "parents": parents, "reuse_graph_id": reuse["artifact_id"],
        "identity_contract_id": identity["artifact_id"], "resource_plan_id": resource["artifact_id"],
        "shard_plan_id": shard["artifact_id"], "allowed_roots": [config["roots"]["cache"], config["roots"]["staging"]],
        "optimizer_authorized": False, "formal_validation_authorized": False,
        "expected_entry_count_per_derived_family": count, "overwrite_existing": False,
    })
    return {name: value for name, value in zip(ARTIFACT_NAMES, (reuse, identity, resource, shard, authority), strict=True)}


def publish_plan_bundle(config: dict[str, Any], bundle: dict[str, Any]) -> list[Path]:
    authority = bundle["production_cache_build_authority"]
    root = Path(config["roots"]["publication"]) / authority["artifact_id"]
    payloads = {f"{name}.json": canonical_json_bytes(bundle[name]) for name in ARTIFACT_NAMES}
    if root.exists():
        for name, payload in payloads.items():
            if not (root / name).is_file() or (root / name).read_bytes() != payload:
                raise FileExistsError("immutable P9 cache-plan publication collision")
    else:
        root.parent.mkdir(parents=True, exist_ok=True)
        stage = root.with_name(f".{root.name}.tmp-{os.getpid()}"); stage.mkdir()
        for name, payload in payloads.items(): (stage / name).write_bytes(payload)
        os.replace(stage, root)
    return [root / f"{name}.json" for name in ARTIFACT_NAMES]


def cache_acceptance_payload(config: dict[str, Any], plan: dict[str, Any], validation: dict[str, Any],
                             execution_commit: str) -> dict[str, Any]:
    if validation.get("status") != "PASS" or any(int(validation.get(key, -1)) != 0 for key in (
            "missing_identities", "duplicate_identities", "orphan_entries", "shard_checksum_failures",
            "manifest_index_disagreements", "invalid_dem_support", "shape_dtype_schema_failures",
            "p7_overlap_byte_differences", "k_subset_overlap_byte_differences",
            "repeat_build_scientific_byte_differences", "rank_dependent_differences")):
        raise ValueError("P9 production cache validation did not pass")
    value = {
        "schema_version": SCHEMA_VERSION, "status": "PASS",
        "parents": {**config["parents"], "cache_build_authority_id": plan["artifact_id"],
                    "execution_repository_commit": execution_commit},
        "cache": validation["cache"], "validation": validation,
        "formal_training_authorized": False, "optimizer_updates_executed": 0,
        "formal_validation_runs_executed": 0, "evaluation_queries_consumed": 0,
    }
    value["content_sha256"] = digest(value); value["acceptance_id"] = "p9ca_" + value["content_sha256"][:24]
    return value


def formal_authority_payload(config: dict[str, Any], cache_acceptance: dict[str, Any], execution_commit: str) -> dict[str, Any]:
    if cache_acceptance.get("status") != "PASS": raise ValueError("cache acceptance is required")
    p8 = validate_lineage(config); hyper = p8["hyper"]; comparisons = p8["comparisons"]
    scientific = {
        "schema_version": SCHEMA_VERSION, "status": "AUTHORIZED",
        "source_commits": {"canonical_p9": config["canonical_implementation_commit"], "execution": execution_commit},
        "parents": {**config["parents"], "production_cache_acceptance_id": cache_acceptance["acceptance_id"]},
        "p9_a_configurations": [{"configuration_id": row["configuration_id"], "scientific_hash": row["scientific_hash"]}
                                for row in hyper["rows"]],
        "p9_b_templates": [{"template_id": row["template_id"], "template_hash": row["template_hash"],
                            "status": "UNRESOLVED_UNTIL_SELECTED_FM"} for row in comparisons["templates"]],
        "selection": {"data": "validation_only", "primary": "validation_retrieval_loss",
                      "equivalence_threshold": 0.0001, "secondary": "mean_source_separation_margin",
                      "final_tie_break": "earlier_epoch"},
        "budgets": {"maximum_epochs": 200, "updates_per_epoch": 76, "validation_interval_epochs": 5,
                    "patience_events": 4},
        "topology": {"world_size": 2, "global_batch_size": 32, "per_rank_batch_size": 16},
        "roots": {"target_store": config["roots"]["target_store"], "artifacts": config["roots"]["publication"],
                  "cache": config["roots"]["cache"], "locks": config["roots"]["locks"]},
        "evaluation_ancestry": False, "p9_b_authorities_issued": 0,
        "attempt_uniqueness_fields": ["configuration", "seed", "p8_parent", "p7_runtime_parent",
                                      "p9_readiness", "production_cache_acceptance", "scientific_source_commit"],
        "checkpoint_resume_contract": "full_state_exact_same_attempt_only",
    }
    value = dict(scientific); value["content_sha256"] = digest(scientific)
    value["authority_id"] = "p9a_" + value["content_sha256"][:24]
    return value


def cfg_main_reservation_payload(config: dict[str, Any], authority: dict[str, Any], cache_acceptance: dict[str, Any]) -> dict[str, Any]:
    rows = validate_lineage(config)["hyper"]["rows"]
    main = next(row for row in rows if row["configuration_id"] == "cfg_main")
    seed_payload = {"schema_version": "1.0.0", "namespace": "p9-a/cfg_main", "root_seed": 20260828}
    seed = int.from_bytes(hashlib.sha256(canonical_json_bytes(seed_payload)).digest()[:8], "big") % (2**31)
    key_payload = {
        "configuration": main["scientific_hash"], "seed": seed,
        "p8_parent": config["parents"]["p8_acceptance_id"],
        "p7_runtime_parent": config["parents"]["p7_runtime_acceptance_id"],
        "p9_readiness": config["parents"]["p9_readiness_id"],
        "production_cache_acceptance": cache_acceptance["acceptance_id"],
        "scientific_source_commit": config["canonical_implementation_commit"],
    }
    duplicate_key = digest(key_payload)
    scientific = {
        "schema_version": SCHEMA_VERSION, "status": "AUTHORIZED_NOT_STARTED",
        "formal_attempt": True, "attempt_started": False, "configuration_id": "cfg_main",
        "configuration_identity": main["scientific_hash"], "seed": seed,
        "seed_identity": digest(seed_payload), "formal_authority_id": authority["authority_id"],
        "production_cache_acceptance_id": cache_acceptance["acceptance_id"],
        "duplicate_attempt_key": duplicate_key, "run_identity_derivation": "p9run_ + sha256(reservation, start_nonce)[:24]",
        "lock_path": str(Path(config["roots"]["locks"]) / f"{duplicate_key}.lock.json"),
        "optimizer_updates_executed": 0, "formal_validation_runs_executed": 0,
        "checkpoint_artifacts_created": 0, "evaluation_queries_consumed": 0,
    }
    value = dict(scientific); value["content_sha256"] = digest(scientific)
    value["reservation_id"] = "p9res_" + value["content_sha256"][:24]
    return value


def publish_final_bundle(config: dict[str, Any], cache_acceptance: dict[str, Any],
                         authority: dict[str, Any], reservation: dict[str, Any]) -> list[Path]:
    root = Path(config["roots"]["publication"]) / authority["authority_id"]
    values = {"production_cache_acceptance.json": cache_acceptance,
              "p9_formal_training_authority.json": authority,
              "cfg_main_attempt_reservation.json": reservation}
    payloads = {name: canonical_json_bytes(value) for name, value in values.items()}
    if root.exists():
        for name, payload in payloads.items():
            if not (root / name).is_file() or (root / name).read_bytes() != payload:
                raise FileExistsError("immutable P9 formal publication collision")
    else:
        root.parent.mkdir(parents=True, exist_ok=True)
        stage = root.with_name(f".{root.name}.tmp-{os.getpid()}"); stage.mkdir()
        for name, payload in payloads.items(): (stage / name).write_bytes(payload)
        os.replace(stage, root)
    return [root / name for name in values]


class FormalAttemptLock:
    """Atomic duplicate-attempt lock; stale locks require explicit external authorization."""

    def __init__(self, path: str | Path, duplicate_key: str, rank: int = 0) -> None:
        self.path, self.duplicate_key, self.rank = Path(path), duplicate_key, int(rank)

    def acquire(self, resume_identity: str | None = None) -> dict[str, Any]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        owner = {"schema_version": SCHEMA_VERSION, "duplicate_attempt_key": self.duplicate_key,
                 "pid": os.getpid(), "hostname": socket.gethostname(), "rank": self.rank,
                 "owner": "DDP_CONTROLLER" if self.rank == 0 else "DDP_NON_OWNER",
                 "resume_identity": resume_identity, "state": "ACTIVE", "heartbeat_monotonic_ns": time.monotonic_ns()}
        if self.rank != 0:
            if not self.path.is_file(): raise FileNotFoundError("rank 0 has not acquired the formal attempt lock")
            existing = read_json(self.path)
            if existing.get("duplicate_attempt_key") != self.duplicate_key or existing.get("state") != "ACTIVE":
                raise FileExistsError("DDP formal attempt lock mismatch")
            if resume_identity is not None and existing.get("resume_identity") != resume_identity:
                raise FileExistsError("resume identity does not match active formal attempt")
            return existing
        descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream: stream.write(canonical_json_bytes(owner))
        return owner

    def heartbeat(self) -> None:
        if self.rank != 0: return
        value = read_json(self.path)
        if value.get("pid") != os.getpid() or value.get("duplicate_attempt_key") != self.duplicate_key:
            raise PermissionError("formal attempt lock ownership mismatch")
        value["heartbeat_monotonic_ns"] = time.monotonic_ns()
        temporary = self.path.with_name(f".{self.path.name}.tmp-{os.getpid()}")
        temporary.write_bytes(canonical_json_bytes(value)); os.replace(temporary, self.path)

    def release(self, terminal_state: str) -> Path:
        if self.rank != 0: return self.path
        if terminal_state not in {"COMPLETED", "FAILED", "SCIENTIFIC_DIVERGENCE"}:
            raise ValueError("formal lock terminal state is invalid")
        value = read_json(self.path)
        if value.get("pid") != os.getpid(): raise PermissionError("formal attempt lock ownership mismatch")
        value["state"] = terminal_state; value["released_monotonic_ns"] = time.monotonic_ns()
        terminal = self.path.with_suffix(self.path.suffix + f".{terminal_state.lower()}")
        if terminal.exists(): raise FileExistsError("formal attempt terminal lock already exists")
        temporary = terminal.with_name(f".{terminal.name}.tmp-{os.getpid()}")
        temporary.write_bytes(canonical_json_bytes(value)); os.replace(temporary, terminal)
        self.path.unlink()
        return terminal

    @staticmethod
    def authorize_stale_recovery(path: str | Path, recovery_authority: dict[str, Any]) -> Path:
        source = Path(path)
        if recovery_authority.get("status") != "APPROVED" or recovery_authority.get("lock_sha256") != sha256_file(source):
            raise PermissionError("explicit stale-lock recovery authority is invalid")
        destination = source.with_suffix(source.suffix + ".stale-authorized")
        if destination.exists(): raise FileExistsError("stale-lock recovery was already recorded")
        os.replace(source, destination)
        return destination
