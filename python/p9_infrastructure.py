"""Fail-closed P9-A/P9-B planning and bounded-pilot contracts."""

from __future__ import annotations

import hashlib
import json
import subprocess
import copy
from pathlib import Path
from typing import Any

import yaml
import torch

from canonical_config import canonical_json_bytes
from rotating_padding_sampler import logical_groups, rotating_padding_state
from p9_v2_downstream import AcceptedCheckpointResolver, resolve_p9_b_checkpoint

SCHEMA_VERSION = "1.0.0"
FAMILIES = ("FM", "A1", "A2", "A3", "A4", "A5", "SSV", "DS")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text())


def load_contract(path: str | Path) -> dict[str, Any]:
    value = yaml.safe_load(Path(path).read_text())
    if value.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported P9 infrastructure schema")
    if value["authorization"] != {
        "formal_training": False,
        "hyperparameter_selection": False,
        "comparison_materialization": False,
        "bounded_pilot_max_updates": 40,
    }:
        raise ValueError("P9 authorization must remain plan-only plus bounded pilot")
    if value["population"] != {
        "training_scenes": 2421,
        "validation_scenes": 400,
        "validation_queries": 800,
        "evaluation_ancestry": False,
    }:
        raise ValueError("P9 population/evaluation contract mismatch")
    sampler = value["sampler"]
    if (sampler["policy"], sampler["padded_scenes_per_epoch"],
            sampler["padding_scenes_per_epoch"], sampler["optimizer_updates_per_epoch"]) != (
            "deterministic_epoch_rotating_padding", 2432, 11, 76):
        raise ValueError("P9 full-population sampler contract mismatch")
    execution = value["execution"]
    required_execution = {
        "world_size": 2, "global_batch_size": 32, "per_rank_batch_size": 16,
        "backend": "nccl", "precision": "float32", "amp": False, "tf32": False,
        "deterministic_algorithms": True, "find_unused_parameters": False,
        "bucket_cap_mb": 50, "gradient_as_bucket_view": False, "static_graph": False,
        "runtime_acceptance_required": True,
    }
    if execution != required_execution:
        raise ValueError("P9 DDP/numeric execution contract mismatch")
    return value


def validate_p8_bundle(root: str | Path, contract: dict[str, Any]) -> dict[str, Any]:
    root = Path(root)
    acceptance = read_json(root / "formal_experiment_plan_acceptance.json")
    hyper = read_json(root / "hyperparameter_configuration_matrix.json")
    comparisons = read_json(root / "comparison_variant_template_matrix.json")
    bank = read_json(root / "experiment_augmentation_bank_index.json")
    a5 = read_json(root / "a5_generic_relation_mapping_contract.json")
    ds = read_json(root / "ds_raster_materialization_contract.json")
    parents = contract["parents"]
    observed = {
        "p8_acceptance_id": acceptance["acceptance_id"],
        "p8_hyperparameter_matrix_id": hyper["matrix_id"],
        "p8_comparison_matrix_id": comparisons["matrix_id"],
        "p8_a5_contract_id": a5["contract_id"],
        "p8_ds_contract_id": ds["contract_id"],
        "p8_bank_index_id": bank["index_id"],
    }
    if any(observed[key] != parents[key] for key in observed):
        raise ValueError("P9 canonical P8 parent mismatch")
    if hyper["count"] != 13 or comparisons["count"] != 7:
        raise ValueError("P9 13+7 plan mismatch")
    if comparisons["materialized_count"] != 0:
        raise ValueError("P9-B was materialized before selected FM")
    if any(row.get("evaluation_ancestry") or row.get("evaluation_query_identity") is not None
           for row in [*hyper["rows"], *comparisons["templates"]]):
        raise ValueError("evaluation identity entered P9 ancestry")
    return {"acceptance": acceptance, "hyper": hyper, "comparisons": comparisons,
            "bank": bank, "a5": a5, "ds": ds}


def materialize_comparison(
    template: dict[str, Any],
    acceptance_identity: str | None,
    resolver: AcceptedCheckpointResolver | None = None,
    evaluation_identity: str | None = None,
) -> dict[str, Any]:
    if evaluation_identity is not None:
        raise ValueError("evaluation identity is prohibited in P9")
    if not isinstance(acceptance_identity, str):
        raise ValueError("stable selected FM acceptance identity is required before P9-B materialization")
    if resolver is None:
        raise ValueError("canonical accepted-checkpoint resolver is required")
    selected = resolve_p9_b_checkpoint(acceptance_identity, resolver)
    if template.get("template_id") not in {
            "cmp_a1_geometric_core", "cmp_a2_semantic_enriched",
            "cmp_a3_object_context_enriched", "cmp_a4_raster_complete_non_relational",
            "cmp_a5_relation_type_agnostic", "cmp_ssv_like", "cmp_ds_like"}:
        raise ValueError("unknown comparison template")
    scientific = selected.scientific_configuration["content"]
    payload = {"selected_configuration_identity": selected.acceptance_id,
               "template_id": template["template_id"], "template_hash": template["template_hash"],
               "scientific": scientific, "checkpoint_id": selected.checkpoint_id,
               "evaluation_ancestry": False}
    return {**payload, "scientific_hash": digest(payload)}


def bounded_groups(scene_ids: list[str], seed: int, maximum_updates: int) -> list[tuple[str, ...]]:
    if maximum_updates < 1 or maximum_updates > 40:
        raise ValueError("bounded P9 pilot is limited to 40 optimizer updates")
    groups = logical_groups(rotating_padding_state(scene_ids, seed, 0), 32)
    if len(groups) != 76:
        raise ValueError("P9 epoch must contain exactly 76 logical groups")
    return groups[:maximum_updates]


def configuration_seed(root_seed: int, configuration_id: str) -> int:
    payload = {"namespace": f"p9-a/{configuration_id}", "root_seed": int(root_seed),
               "schema_version": SCHEMA_VERSION}
    return int.from_bytes(hashlib.sha256(canonical_json_bytes(payload)).digest()[:8], "big") % (2**31)


def materialize_hyperparameter_configuration(
        row: dict[str, Any], base_training: dict[str, Any], base_model: dict[str, Any]) -> dict[str, Any]:
    """Route one accepted P8 OFAT row without authorizing or starting a P9 run."""
    if row.get("configuration_family") != "hyperparameter" or row.get("evaluation_ancestry") is not False:
        raise ValueError("P9-A requires an evaluation-free hyperparameter row")
    if row.get("evaluation_query_identity") is not None:
        raise ValueError("evaluation query identity is prohibited in P9-A")
    scientific = row["scientific"]
    if scientific["d"] != scientific["d_c"] or scientific["per_head_dimension"] != scientific["d"] // 4:
        raise ValueError("P9-A relative-to-d model contract mismatch")
    if scientific["ffn_dimension"] != 2 * scientific["d"] or scientific["attention_heads"] != 4:
        raise ValueError("P9-A attention/FFN contract mismatch")
    training = copy.deepcopy(base_training)
    model = copy.deepcopy(base_model)
    model["model"].update({
        "d": scientific["d"], "d_c": scientific["d_c"],
        "head_dimension": scientific["per_head_dimension"],
        "ffn_dimension": scientific["ffn_dimension"],
    })
    training["training"].update({
        "profile_id": scientific["intensity"], "logical_k": scientific["effective_k"],
        "root_seed": configuration_seed(int(base_training["training"]["root_seed"]), row["configuration_id"]),
    })
    training["optimizer"]["peak_learning_rate"] = scientific["peak_learning_rate"]
    training["objective"]["information_preservation_weight"] = scientific["lambda_ip"]
    training["ema"]["coefficient"] = scientific["ema"]
    training["queue"]["embedding_dimension"] = scientific["d"]
    return {
        "configuration_id": row["configuration_id"], "scientific_hash": row["scientific_hash"],
        "bank_binding": copy.deepcopy(row["bank_binding"]), "training": training, "model": model,
        "formal_authorized": False, "evaluation_ancestry": False,
    }


def cache_requirements(family: str, bank_binding: dict[str, Any]) -> dict[str, Any]:
    """Classify data/view caches independently from model and runtime-only settings."""
    if family not in FAMILIES:
        raise ValueError("unknown P9 cache family")
    geometry = family in {"FM", "A1", "A2", "A3", "A4", "A5"}
    return {
        "geometry_feature_cache": geometry,
        "geometry_identity": {
            "layout_version": "3.0.0", "physical_bank_id": bank_binding["physical_bank_id"],
            "profile_id": bank_binding["profile_id"],
            "nested_subset_identity": bank_binding["nested_subset_identity"],
        } if geometry else None,
        "relation_edge_support": "accepted_fm_edges" if family in {"FM", "A5"} else None,
        "relation_label_materialization": "generic_runtime_map" if family == "A5" else (
            "heterogeneous" if family == "FM" else None),
        "ds_raster_cache": family == "DS",
        "model_dimension_dependent": False,
    }


def expected_geometry_cache_entries(effective_k: int, training_scenes: int = 2421,
                                    validation_payloads: int = 1200) -> int:
    if effective_k not in (2, 4, 8, 16):
        raise ValueError("unsupported P9 logical K")
    return training_scenes * effective_k + validation_payloads


def p9_learning_rate(update: int, peak: float, maximum_epochs: int = 200,
                     steps_per_epoch: int = 76, warmup_epochs: int = 10) -> float:
    maximum = maximum_epochs * steps_per_epoch; warmup = warmup_epochs * steps_per_epoch
    if update < 1 or update > maximum: raise ValueError("P9 optimizer update outside schedule")
    if update <= warmup: return peak * update / warmup
    import math
    return 0.5 * peak * (1.0 + math.cos(math.pi * (update - warmup) / (maximum - warmup)))


class P9ExactScheduler:
    def __init__(self, optimizer: torch.optim.Optimizer, peak: float, completed_updates: int = 0) -> None:
        self.optimizer, self.peak, self.completed_updates = optimizer, float(peak), int(completed_updates)

    def set_for_next_update(self) -> float:
        value = p9_learning_rate(self.completed_updates + 1, self.peak)
        for group in self.optimizer.param_groups: group["lr"] = value
        return value

    def advance(self) -> None: self.completed_updates += 1
    def state_dict(self) -> dict[str, Any]: return {"completed_updates": self.completed_updates, "peak": self.peak}
    def load_state_dict(self, state: dict[str, Any]) -> None:
        if float(state["peak"]) != self.peak: raise ValueError("P9 scheduler peak mismatch")
        self.completed_updates = int(state["completed_updates"])


def build_readiness(config_path: str | Path, p8_root: str | Path, source_commit: str | None = None) -> dict[str, Any]:
    contract = load_contract(config_path)
    bundle = validate_p8_bundle(p8_root, contract)
    commit = source_commit or subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=Path(config_path).resolve().parents[1], text=True
    ).strip()
    value = {
        "schema_version": SCHEMA_VERSION, "status": "PASS", "source_commit": commit,
        "parents": contract["parents"],
        "counts": {"hyperparameter_configurations": 13, "comparison_templates": 7,
                   "formal_attempts_executed": 0, "optimizer_updates_executed": 0},
        "gates": {"evaluation_ancestry_zero": True, "p9_b_deferred": True,
                  "formal_training_disabled": True, "model_family_registry_complete": True,
                  "sampler_contract_bound": True, "duplicate_main_prohibited": True},
        "configuration_hashes": [row["scientific_hash"] for row in bundle["hyper"]["rows"]],
        "comparison_template_hashes": [row["template_hash"] for row in bundle["comparisons"]["templates"]],
    }
    scientific = dict(value)
    value["content_sha256"] = digest(scientific)
    value["readiness_id"] = "p9ready_" + value["content_sha256"][:24]
    return value


def validate_terminal_outcome(value: dict[str, Any]) -> None:
    outcome = value.get("terminal_outcome")
    if outcome == "SCIENTIFIC_DIVERGENCE":
        required = {"last_valid_update", "detector", "reason", "complete_trace_sha256"}
        if not required.issubset(value) or value.get("infrastructure_failure"):
            raise ValueError("infrastructure failure or incomplete evidence cannot masquerade as scientific divergence")
        if value.get("selected_checkpoint_id") is not None or value.get("winner_eligible") is not False:
            raise ValueError("divergent P9 configuration cannot be selected")
    elif outcome == "STABLE_ACCEPTED_RUN":
        if not value.get("selected_checkpoint_id") or value.get("winner_eligible") is not True:
            raise ValueError("stable P9 run requires a selected checkpoint")
    else:
        raise ValueError("unsupported P9 terminal outcome")


def reject_duplicate_formal_run(existing: list[dict[str, Any]], scientific_hash: str, seed: int) -> None:
    collisions = [row for row in existing if row.get("formal_attempt") is True
                  and row.get("scientific_hash") == scientific_hash and int(row.get("seed", -1)) == int(seed)]
    if collisions:
        raise FileExistsError("duplicate formal P9 configuration/seed attempt is prohibited")
