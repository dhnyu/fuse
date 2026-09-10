"""Current formal-training configuration materialization and scheduling."""

from __future__ import annotations

import copy
import hashlib
from typing import Any

import torch

from canonical_config import canonical_json_bytes
from current_methodology import COMPARISON_NAMES, component_contracts, source_contracts
from training_runtime_inputs import physical_profile_id


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def configuration_seed(root_seed: int, configuration_id: str) -> int:
    payload = {"namespace": f"training/{configuration_id}", "root_seed": int(root_seed),
               "schema_version": "2.0.0"}
    return int.from_bytes(hashlib.sha256(canonical_json_bytes(payload)).digest()[:8], "big") % (2**31)


def _current_scientific_row(row: dict[str, Any]) -> dict[str, Any]:
    required = ("configuration_id", "d", "d_c", "K_aug", "augmentation_intensity",
                "ema_momentum", "peak_learning_rate")
    missing = [key for key in required if key not in row]
    if missing:
        raise ValueError(f"current training row is incomplete: {', '.join(missing)}")
    if row["d"] != row["d_c"] or int(row["d"]) not in (64, 128, 256):
        raise ValueError("current training dimension contract mismatch")
    if int(row["K_aug"]) not in (4, 8, 16):
        raise ValueError("current augmentation-bank size mismatch")
    if float(row["augmentation_intensity"]) not in (0.5, 1.0, 2.0):
        raise ValueError("current augmentation intensity mismatch")
    if float(row["ema_momentum"]) not in (0.990, 0.999):
        raise ValueError("current EMA momentum mismatch")
    if float(row["peak_learning_rate"]) not in (1e-3, 2e-3, 3e-3, 5e-3):
        raise ValueError("current peak learning-rate mismatch")
    return {key: row[key] for key in required if key != "configuration_id"}


def current_plan_rows(plan: dict[str, Any]) -> list[dict[str, Any]]:
    rows = plan.get("hyperparameter_configurations")
    if not isinstance(rows, list) or len(rows) != 11:
        raise ValueError("current experiment plan must contain exactly 11 OFAT rows")
    return rows


def scientific_row_hash(row: dict[str, Any]) -> str:
    return digest(_current_scientific_row(row))


def materialize_hyperparameter_configuration(
        row: dict[str, Any], base_training: dict[str, Any], base_model: dict[str, Any]) -> dict[str, Any]:
    """Materialize one current 11-row OFAT configuration without starting a run."""
    scientific = _current_scientific_row(row)
    training = copy.deepcopy(base_training)
    model = copy.deepcopy(base_model)
    dimension = int(scientific["d"])
    model["model"].update({"d": dimension, "d_c": dimension,
                           "head_dimension": dimension // 4, "ffn_dimension": 2 * dimension})
    profile = physical_profile_id(scientific["augmentation_intensity"])
    training["training"].update({
        "profile_id": profile, "logical_k": int(scientific["K_aug"]),
        "root_seed": configuration_seed(int(base_training["training"]["root_seed"]), row["configuration_id"]),
    })
    training["optimizer"]["peak_learning_rate"] = float(scientific["peak_learning_rate"])
    training["ema"]["coefficient"] = float(scientific["ema_momentum"])
    training["queue"]["embedding_dimension"] = dimension
    prohibited = {"lambda_IP", "lambda_ip", "information_preservation_weight", "reconstruction_loss"}
    if prohibited & set(training.get("objective", {})):
        raise ValueError("current training configuration contains a removed objective")
    scientific_hash = digest(scientific)
    return {
        "configuration_id": row["configuration_id"], "scientific_hash": scientific_hash,
        "model_family": row.get("model_family", "FM"),
        "bank_binding": {"profile_id": profile, "effective_k": int(scientific["K_aug"])},
        "scientific": scientific, "training": training, "model": model,
        "formal_authorized": False, "evaluation_ancestry": False,
    }


def cache_requirements(family: str, bank_binding: dict[str, Any]) -> dict[str, Any]:
    """Classify current data caches independently from model parameters."""
    if family not in COMPARISON_NAMES:
        raise ValueError("unknown current comparison family")
    component = component_contracts().get(family, component_contracts()["FM"])
    retained = source_contracts().get(family, source_contracts()["FM"])
    geometry = family != "DS" and bool(set(retained) & {"B", "R", "P"})
    return {
        "geometry_feature_cache": geometry,
        "geometry_identity": {"layout_version": "3.0.0", **bank_binding} if geometry else None,
        "relation_edge_support": "accepted_fm_induced_subgraph" if component["relation"] != "none" else None,
        "relation_label_materialization": component["relation"],
        "retained_sources": retained, "ds_raster_cache": family == "DS",
        "model_dimension_dependent": False,
    }


def expected_geometry_cache_entries(effective_k: int, training_scenes: int = 2421,
                                    validation_payloads: int = 3000) -> int:
    if effective_k not in (4, 8, 16):
        raise ValueError("unsupported current logical K")
    return training_scenes * effective_k + validation_payloads


def training_learning_rate(update: int, peak: float, maximum_epochs: int = 200,
                           steps_per_epoch: int = 76, warmup_epochs: int = 10) -> float:
    maximum = maximum_epochs * steps_per_epoch
    warmup = warmup_epochs * steps_per_epoch
    if update < 1 or update > maximum:
        raise ValueError("optimizer update outside schedule")
    if update <= warmup:
        return peak * update / warmup
    import math
    return 0.5 * peak * (1.0 + math.cos(math.pi * (update - warmup) / (maximum - warmup)))


class ExactScheduler:
    def __init__(self, optimizer: torch.optim.Optimizer, peak: float, completed_updates: int = 0) -> None:
        self.optimizer, self.peak, self.completed_updates = optimizer, float(peak), int(completed_updates)

    def set_for_next_update(self) -> float:
        value = training_learning_rate(self.completed_updates + 1, self.peak)
        for group in self.optimizer.param_groups:
            group["lr"] = value
        return value

    def advance(self) -> None:
        self.completed_updates += 1

    def state_dict(self) -> dict[str, Any]:
        return {"completed_updates": self.completed_updates, "peak": self.peak}

    def load_state_dict(self, state: dict[str, Any]) -> None:
        if float(state["peak"]) != self.peak:
            raise ValueError("scheduler peak mismatch")
        self.completed_updates = int(state["completed_updates"])


def validate_terminal_outcome(value: dict[str, Any]) -> None:
    outcome = value.get("terminal_outcome")
    if outcome == "SCIENTIFIC_DIVERGENCE":
        required = {"last_valid_update", "detector", "reason", "complete_trace_sha256"}
        if not required.issubset(value) or value.get("infrastructure_failure"):
            raise ValueError("infrastructure failure or incomplete evidence cannot masquerade as scientific divergence")
        if value.get("selected_checkpoint_id") is not None or value.get("winner_eligible") is not False:
            raise ValueError("divergent configuration cannot be selected")
    elif outcome == "STABLE_ACCEPTED_RUN":
        if not value.get("selected_checkpoint_id") or value.get("winner_eligible") is not True:
            raise ValueError("stable run requires a selected checkpoint")
    else:
        raise ValueError("unsupported training terminal outcome")


def reject_duplicate_formal_run(existing: list[dict[str, Any]], scientific_hash: str, seed: int) -> None:
    collisions = [row for row in existing if row.get("formal_attempt") is True
                  and row.get("scientific_hash") == scientific_hash and int(row.get("seed", -1)) == int(seed)]
    if collisions:
        raise FileExistsError("duplicate formal configuration/seed attempt is prohibited")
