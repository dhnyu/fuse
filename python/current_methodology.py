"""Canonical implementation contract for the current reduced dissertation."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

SCHEMA_VERSION = "2.0.0"
ENTITY_SOURCES = ("B", "R", "P")
RASTER_SOURCES = ("LC", "DEM")
RELATION_LABELS = ("SN", "CNT", "WIT", "INT", "CON")
COMPONENT_NAMES = ("FM", "A1", "A2", "A3", "A4", "A5", "SSV", "DS")
SOURCE_ABLATION_NAMES = tuple(f"B{i}" for i in range(1, 10))
COMPARISON_NAMES = ("FM", "A1", "A2", "A3", "A4", "A5", *SOURCE_ABLATION_NAMES, "SSV", "DS")


def load_current_methodology(path: str | Path) -> dict[str, Any]:
    value = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    validate_current_methodology(value)
    return value


def component_contracts() -> dict[str, dict[str, Any]]:
    full = ("relative", "geometry", "semantic", "environmental")
    return {
        "FM": {"modalities": full, "fusion": True, "relation": "heterogeneous", "scene_raster": True},
        "A1": {"modalities": ("relative",), "fusion": False, "relation": "none", "scene_raster": False},
        "A2": {"modalities": ("relative", "geometry"), "fusion": True, "relation": "none", "scene_raster": False},
        "A3": {"modalities": full, "fusion": True, "relation": "none", "scene_raster": False},
        "A4": {"modalities": full, "fusion": True, "relation": "generic", "scene_raster": False,
               "edge_policy": "exact_FM_directed_edges_preserve_direction_and_multiplicity"},
        "A5": {"modalities": full, "fusion": True, "relation": "heterogeneous", "scene_raster": False},
        "SSV": {"modalities": ("relative", "semantic"), "fusion": True, "relation": "none", "scene_raster": False},
        "DS": {"modalities": (), "fusion": False, "relation": "none", "scene_raster": "DS_multichannel"},
    }


def source_contracts() -> dict[str, tuple[str, ...]]:
    return {
        "FM": ("B", "R", "P", "LC", "DEM"), "B1": ("B", "R", "P"),
        "B2": ("B", "R"), "B3": ("B", "P"), "B4": ("R", "P"),
        "B5": ("B",), "B6": ("R",), "B7": ("P",),
        "B8": ("B", "R", "P", "LC"), "B9": ("B", "R", "P", "DEM"),
    }


def build_ofat(config: dict[str, Any]) -> list[dict[str, Any]]:
    main = {
        "d": config["model"]["d"], "d_c": config["model"]["d_c"],
        "K_aug": config["training"]["K_aug"],
        "augmentation_intensity": config["training"]["augmentation_intensity"],
        "ema_momentum": config["training"]["ema_momentum"],
        "peak_learning_rate": config["training"]["peak_learning_rate"],
    }
    rows = [{"configuration_id": "main", **main}]
    axes = config["hyperparameter_study"]
    for axis in ("d", "K_aug", "augmentation_intensity", "ema_momentum", "peak_learning_rate"):
        for value in axes[axis]:
            if value == main[axis]:
                continue
            row = copy.deepcopy(main)
            row[axis] = value
            if axis == "d":
                row["d_c"] = value
            rows.append({"configuration_id": f"ofat_{axis}_{value}", **row})
    if len(rows) != 11 or len({json.dumps(row, sort_keys=True) for row in rows}) != 11:
        raise ValueError("current methodology requires exactly 11 unique OFAT configurations")
    return rows


def comparison_contracts(config: dict[str, Any]) -> list[dict[str, Any]]:
    components = component_contracts()
    sources = source_contracts()
    rows = []
    for name in COMPARISON_NAMES:
        base = components.get(name, components["FM"])
        rows.append({"name": name, **base,
                     "retained_sources": sources.get(name, sources["FM"]),
                     "source_removal": "input_level",
                     "relation_filter": "induced_subgraph_preserve_existing_edges_only"})
    return rows


def retained_entity_mask(entity_types: list[str], retained_sources: tuple[str, ...]) -> list[bool]:
    retained = set(retained_sources) & set(ENTITY_SOURCES)
    return [value in retained for value in entity_types]


def induced_subgraph(edge_index: list[tuple[int, int]], keep: list[bool]) -> list[tuple[int, int]]:
    return [(source, target) for source, target in edge_index if keep[source] and keep[target]]


def active_raster_sources(retained_sources: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(source for source in RASTER_SOURCES if source in retained_sources)


def validate_current_methodology(value: dict[str, Any]) -> None:
    if value.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("current methodology schema mismatch")
    if value["scene_split"] != {"total_off_grid": 10000, "validation": 1000, "evaluation": 9000,
                                 "minimum_training_center_distance_m": 50}:
        raise ValueError("current scene split mismatch")
    model = value["model"]
    if (model["d"], model["d_c"], model["information_preservation"], model["reconstruction_decoders"]) != (128, 128, False, False):
        raise ValueError("current model contract mismatch")
    prohibited = {"lambda_IP", "lambda_ip", "information_preservation_weight", "reconstruction_loss"}
    if prohibited & set(value["training"]):
        raise ValueError("current training contract contains a removed objective field")
    if tuple(value["comparison"]["ordered_models"]) != COMPARISON_NAMES:
        raise ValueError("current comparison set must contain exactly 17 ordered models")
    configured_components = {
        key: {field: tuple(item) if field == "modalities" else item
              for field, item in contract.items()}
        for key, contract in value["comparison"]["component_variants"].items()
    }
    if configured_components != component_contracts():
        raise ValueError("component-ablation contract mismatch")
    if {key: tuple(item) for key, item in value["comparison"]["retained_sources"].items()} != source_contracts():
        raise ValueError("source-ablation retained-source contract mismatch")
    build_ofat(value)


def build_plan(path: str | Path) -> dict[str, Any]:
    config = load_current_methodology(path)
    content = {"schema_version": SCHEMA_VERSION, "dissertation_commit": config["dissertation_commit"],
               "scene_split": config["scene_split"], "model": config["model"], "training": config["training"],
               "hyperparameter_configurations": build_ofat(config),
               "comparison_configurations": comparison_contracts(config)}
    digest = hashlib.sha256(json.dumps(content, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    plan = {**content, "plan_id": f"s08plan_{digest[:24]}", "content_sha256": digest, "status": "PASS"}
    validate_plan(plan, config)
    return plan


def validate_plan(plan: dict[str, Any], config: dict[str, Any]) -> None:
    content = {key: value for key, value in plan.items() if key not in {"plan_id", "content_sha256", "status"}}
    digest = hashlib.sha256(json.dumps(content, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if plan.get("plan_id") != f"s08plan_{digest[:24]}" or plan.get("content_sha256") != digest or plan.get("status") != "PASS":
        raise ValueError("current experiment plan identity mismatch")
    if plan["hyperparameter_configurations"] != build_ofat(config):
        raise ValueError("current experiment plan OFAT mismatch")
    if plan["comparison_configurations"] != comparison_contracts(config):
        raise ValueError("current experiment plan comparison mismatch")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(build_plan(args.config), ensure_ascii=False, sort_keys=True,
                                separators=(",", ":")) + "\n", encoding="utf-8")
