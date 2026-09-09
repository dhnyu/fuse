"""Deterministic current-lineage S09 campaign planning; never launches training."""

from __future__ import annotations

import hashlib
import json
import os
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Any, Iterable, Mapping

from artifact_protocol import canonical_json_bytes, canonical_sha256, sha256_file
from training_configuration import (
    configuration_seed, materialize_hyperparameter_configuration, scientific_row_hash,
)
from training_controller import TrainingControllerError, build_training_authority
from training_finalization import selection_contract_content


CURRENT_LINEAGE_KEYS = (
    "methodology_authority_id", "experiment_plan_id", "dataset_acceptance_id",
    "query_acceptance_id", "bank_acceptance_id", "scene_cache_acceptance_id",
    "scene_cache_id", "scientific_revision_token",
)
COMPARISON_IDS = ("FM", "A1", "A2", "A3", "A4", "A5", "B1", "B2", "B3",
                  "B4", "B5", "B6", "B7", "B8", "B9", "SSV", "DS")


def scientific_implementation_hash(root: str | Path) -> str:
    root = Path(root)
    paths = (
        "python/model_data.py", "python/model_families.py", "python/scene_model.py",
        "python/training_configuration.py", "python/training_support.py",
        "python/training_worker.py",
    )
    return canonical_sha256({path: sha256_file(root / path) for path in paths})


def canonical_selection(plan: Mapping[str, Any]) -> dict[str, Any]:
    selection = dict(plan.get("selection_protocol") or {})
    expected = {**selection_contract_content(), "minimum_delta": 0.0001}
    if selection != expected:
        raise TrainingControllerError("S08_S09_SELECTION_CONTRACT_MISMATCH")
    return selection


def selection_hash(plan: Mapping[str, Any]) -> str:
    return canonical_sha256(canonical_selection(plan))


def s08_selection_document(plan: Mapping[str, Any]) -> dict[str, Any]:
    """Return the S08-frozen selection object in the native lifecycle envelope."""
    content = canonical_selection(plan)
    digest = canonical_sha256(content)
    return {"schema_version": "2.0.0", "identity": "p9selc_" + digest[:24],
            "content_sha256": digest, "content": content}


def scientific_configuration(row: Mapping[str, Any], model_id: str) -> dict[str, Any]:
    keys = ("configuration_id", "d", "d_c", "K_aug", "augmentation_intensity",
            "ema_momentum", "peak_learning_rate")
    return {**{key: row[key] for key in keys}, "model_family": model_id}


def current_lineage(plan: Mapping[str, Any], contract: Mapping[str, Any]) -> dict[str, str]:
    lineage = dict(plan.get("lineage") or {})
    parents = dict(contract.get("parents") or {})
    source = dict(contract.get("source") or {})
    observed = {
        "methodology_authority_id": lineage.get("p0_authority_id"),
        "experiment_plan_id": plan.get("plan_id"),
        "dataset_acceptance_id": lineage.get("p6_acceptance_id"),
        "query_acceptance_id": lineage.get("p5_acceptance_id"),
        "bank_acceptance_id": lineage.get("p4_acceptance_id"),
        "scene_cache_acceptance_id": lineage.get("p3_acceptance_id"),
        "scene_cache_id": lineage.get("p3_cache_id"),
        "scientific_revision_token": lineage.get("scientific_revision_token"),
    }
    expected = {key: (source if key == "scientific_revision_token" else parents).get(key)
                for key in CURRENT_LINEAGE_KEYS}
    if any(not isinstance(value, str) or not value for value in observed.values()):
        raise TrainingControllerError("CURRENT_TRAINING_LINEAGE_INCOMPLETE")
    if observed != expected:
        raise TrainingControllerError("CURRENT_TRAINING_LINEAGE_MISMATCH")
    if any("PENDING" in value for value in observed.values()):
        raise TrainingControllerError("CURRENT_TRAINING_LINEAGE_PLACEHOLDER")
    return observed


def cache_identity(lineage: Mapping[str, str], membership_sha256: str,
                   entry_count: int = 80_472) -> tuple[str, str]:
    content = {"schema_version": "1.0.0", "artifact_type": "s09_prepared_cache",
               "parents": dict(sorted(lineage.items())), "entry_count": int(entry_count),
               "membership_sha256": membership_sha256,
               "optimizer_updates": 0, "training_runs": 0}
    digest = canonical_sha256(content)
    return "s09cache_" + digest[:24], digest


def authority_parents(lineage: Mapping[str, str], cache_acceptance: Mapping[str, Any]) -> dict[str, str]:
    result = dict(lineage)
    result.update({
        "production_cache_id": str(cache_acceptance["cache_id"]),
        "production_cache_acceptance_id": str(cache_acceptance["acceptance_id"]),
        "retirement_id": "p9ret_246eaf97570f115d4faaf3d1",
    })
    return result


def ofat_authorities(plan: Mapping[str, Any], base_training: Mapping[str, Any],
                     base_model: Mapping[str, Any], parents: Mapping[str, str],
                     implementation_hash: str) -> list[dict[str, Any]]:
    rows = plan.get("hyperparameter_configurations")
    if not isinstance(rows, list) or len(rows) != 11 or len({row.get("configuration_id") for row in rows}) != 11:
        raise TrainingControllerError("S09_OFAT_INVENTORY_INVALID")
    selection = selection_hash(plan)
    values = []
    for row in rows:
        routed = materialize_hyperparameter_configuration(dict(row), dict(base_training), dict(base_model))
        configuration = scientific_configuration(row, "FM")
        values.append(build_training_authority(
            configuration_id=str(row["configuration_id"]), configuration_hash=canonical_sha256(configuration),
            plan_configuration_hash=scientific_row_hash(dict(row)),
            scientific_implementation_hash=implementation_hash,
            root_seed=int(routed["training"]["training"]["root_seed"]), parents=dict(parents),
            phase="OFAT", model_id="FM", selection_contract_hash=selection,
            prepared_cache_id=parents["production_cache_id"], hyperparameters=routed["scientific"]))
    return values


def select_ofat_winner(plan: Mapping[str, Any], results: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    expected = [row["configuration_id"] for row in plan["hyperparameter_configurations"]]
    rows = [dict(row) for row in results]
    if len(rows) != 11 or {row.get("configuration_id") for row in rows} != set(expected):
        raise TrainingControllerError("S09_OFAT_RESULTS_INCOMPLETE")
    if any(row.get("status") != "PASS" or not row.get("checkpoint_id") for row in rows):
        raise TrainingControllerError("S09_OFAT_RESULT_NOT_ELIGIBLE")
    tolerance = float(canonical_selection(plan)["equivalence_tolerance"])
    ordered = sorted(rows, key=lambda row: expected.index(row["configuration_id"]))
    best = ordered[0]
    for candidate in ordered[1:]:
        loss_delta = float(candidate["validation_retrieval_loss"]) - float(best["validation_retrieval_loss"])
        if loss_delta < -tolerance:
            best = candidate
        elif abs(loss_delta) < tolerance:
            margin_delta = float(candidate["mean_source_separation_margin"]) - float(best["mean_source_separation_margin"])
            if margin_delta > 0 or (margin_delta == 0 and int(candidate["completed_epoch"]) < int(best["completed_epoch"])):
                best = candidate
    content = {"schema_version": "1.0.0", "artifact_type": "s09_ofat_winner",
               "experiment_plan_id": plan["plan_id"], "selection_contract_hash": selection_hash(plan),
               "candidate_results": ordered, "selected_configuration_id": best["configuration_id"],
               "selected_checkpoint_id": best["checkpoint_id"], "status": "PASS"}
    digest = canonical_sha256(content)
    return {**content, "winner_id": "s09winner_" + digest[:24], "content_sha256": digest}


def comparison_authorities(plan: Mapping[str, Any], winner: Mapping[str, Any],
                           base_training: Mapping[str, Any], base_model: Mapping[str, Any],
                           parents: Mapping[str, str], implementation_hash: str) -> list[dict[str, Any]]:
    if winner.get("status") != "PASS" or winner.get("experiment_plan_id") != plan.get("plan_id"):
        raise TrainingControllerError("S09_COMPARISON_WINNER_REQUIRED")
    winner_row = next((row for row in plan["hyperparameter_configurations"]
                       if row["configuration_id"] == winner["selected_configuration_id"]), None)
    comparisons = plan.get("comparison_configurations")
    if winner_row is None or not isinstance(comparisons, list) or tuple(row.get("name") for row in comparisons) != COMPARISON_IDS:
        raise TrainingControllerError("S09_COMPARISON_INVENTORY_INVALID")
    selection = selection_hash(plan)
    values = []
    for model in comparisons:
        row = {**winner_row, "configuration_id": f"cmp_{model['name']}", "model_family": model["name"]}
        routed = materialize_hyperparameter_configuration(row, dict(base_training), dict(base_model))
        comparison_hash = canonical_sha256(scientific_configuration(row, model["name"]))
        values.append(build_training_authority(
            configuration_id=row["configuration_id"], configuration_hash=comparison_hash,
            plan_configuration_hash=canonical_sha256(model), scientific_implementation_hash=implementation_hash,
            root_seed=configuration_seed(int(base_training["training"]["root_seed"]), row["configuration_id"]),
            parents={**dict(parents), "ofat_winner_id": str(winner["winner_id"])}, phase="COMPARISON",
            model_id=model["name"], selection_contract_hash=selection,
            prepared_cache_id=parents["production_cache_id"], hyperparameters=routed["scientific"]))
    return values


def publish_documents(documents: Iterable[Mapping[str, Any]], root: str | Path) -> list[str]:
    root = Path(root); paths = []
    for document in documents:
        identity = str(document["identity"])
        path = root / identity / "training_authority.json"
        payload = canonical_json_bytes(document)
        if path.exists() and path.read_bytes() != payload:
            raise FileExistsError("TRAINING_AUTHORITY_IMMUTABLE_COLLISION")
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
            temporary.write_bytes(payload); os.replace(temporary, path)
        paths.append(str(path))
    return paths


@contextmanager
def gpu_pair_environment(indices: Iterable[int], lock_root: str | Path, timeout_seconds: float):
    """Hold the configured pair and per-device locks for the complete DDP subprocess lifetime."""
    import fcntl
    import time
    devices = tuple(int(value) for value in indices)
    if len(devices) != 2 or len(set(devices)) != 2:
        raise TrainingControllerError("S09_EXACTLY_TWO_GPU_DEVICES_REQUIRED")
    root = Path(lock_root); root.mkdir(parents=True, exist_ok=True)
    streams = []
    deadline = time.monotonic() + float(timeout_seconds)
    try:
        for name in ("gpu_pair.lock", *(f"gpu{device}.lock" for device in devices)):
            stream = (root / name).open("a+")
            while True:
                try:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB); break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        stream.close(); raise TrainingControllerError("S09_GPU_LOCK_UNAVAILABLE")
                    time.sleep(0.1)
            streams.append(stream)
        environment = os.environ.copy()
        environment["CUDA_VISIBLE_DEVICES"] = ",".join(map(str, devices))
        yield environment
    finally:
        for stream in reversed(streams):
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN); stream.close()
