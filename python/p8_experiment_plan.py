"""P8 plan-only scientific configuration and comparison-template contracts."""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import jsonschema
import torch
from torch import nn
import yaml


SCHEMA_VERSION = "1.0.0"
CONFIG_IDS = (
    "cfg_main", "cfg_d48", "cfg_d128", "cfg_k2", "cfg_k4", "cfg_k16",
    "cfg_intensity_05", "cfg_intensity_20", "cfg_ema_990", "cfg_ip_0",
    "cfg_lr_2", "cfg_lr_3", "cfg_lr_10",
)
TEMPLATE_IDS = (
    "cmp_a1_no_geometry", "cmp_a2_no_semantics", "cmp_a3_no_raster_context",
    "cmp_a4_no_spatial_relations", "cmp_a5_radius_context", "cmp_ssv_like", "cmp_ds_like",
)


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def identity(prefix: str, value: Any) -> str:
    return prefix + digest(value)[:24]


def file_sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def load_config(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("invalid P8 configuration")
    return value


def git_head(root: Path) -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()


def dissertation_modules(config: dict[str, Any], dissertation_root: Path) -> dict[str, str]:
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=dissertation_root, text=True).strip()
    if commit != config["methodology"]["dissertation_commit"]:
        raise ValueError("dissertation commit mismatch")
    return {name: file_sha256(dissertation_root / name) for name in config["methodology"]["modules"]}


def _complete(defaults: dict[str, Any], **changes: Any) -> dict[str, Any]:
    value = copy.deepcopy(defaults)
    value.update(changes)
    value["d_c"] = value["d"]
    value["per_head_dimension"] = value["d"] // value["attention_heads"]
    value["ffn_dimension"] = value["d"] * value["ffn_multiplier"]
    return value


def build_hyperparameter_rows(config: dict[str, Any]) -> list[dict[str, Any]]:
    defaults = config["scientific_defaults"]
    variations = (
        ("cfg_main", "main", None, {}), ("cfg_d48", "d", 48, {"d": 48}),
        ("cfg_d128", "d", 128, {"d": 128}), ("cfg_k2", "K", 2, {"effective_k": 2}),
        ("cfg_k4", "K", 4, {"effective_k": 4}), ("cfg_k16", "K", 16, {"effective_k": 16}),
        ("cfg_intensity_05", "intensity", "0.5x", {"intensity": "weak_0.5x"}),
        ("cfg_intensity_20", "intensity", "2.0x", {"intensity": "strong_2.0x"}),
        ("cfg_ema_990", "EMA", 0.990, {"ema": 0.990}),
        ("cfg_ip_0", "lambda_IP", 0.0, {"lambda_ip": 0.0}),
        ("cfg_lr_2", "peak_LR", 0.002, {"peak_learning_rate": 0.002}),
        ("cfg_lr_3", "peak_LR", 0.003, {"peak_learning_rate": 0.003}),
        ("cfg_lr_10", "peak_LR", 0.01, {"peak_learning_rate": 0.01}),
    )
    rows = []
    parents = config["parents"]
    for config_id, factor, changed, updates in variations:
        scientific = _complete(defaults, **updates)
        profile = scientific["intensity"]
        k = scientific["effective_k"]
        bank_binding = {
            "physical_bank_id": parents["p4_bank_id"], "bank_acceptance_id": parents["p4_acceptance_id"],
            "logical_index_id": parents["p4_index_id"], "profile_id": profile,
            "effective_k": k, "nested_subset_identity": identity("p8abi_", {"index": parents["p4_index_id"], "profile": profile, "k": k}),
        }
        scientific_payload = {
            "configuration_family": "hyperparameter", "configuration_id": config_id,
            "scientific": scientific, "bank_binding": bank_binding,
            "validation_acceptance_id": parents["p5_validation_acceptance_id"],
            "run_seed_namespace": f"p9-a/{config_id}", "run_seed_formula": "sha256_canonical_json_root_seed_configuration_id",
            "parent_p7_acceptance_id": parents["p7_acceptance_id"],
            "runtime_acceptance_id": parents["p7_runtime_acceptance_id"],
        }
        rows.append({
            "schema_version": SCHEMA_VERSION, "configuration_id": config_id,
            "configuration_family": "hyperparameter", "changed_factor": factor,
            "changed_value": changed, **scientific_payload,
            "evaluation_query_identity": None, "evaluation_ancestry": False,
            "scientific_hash": digest(scientific_payload),
        })
    validate_hyperparameter_rows(rows)
    return rows


def validate_hyperparameter_rows(rows: list[dict[str, Any]]) -> None:
    if tuple(row["configuration_id"] for row in rows) != CONFIG_IDS or len(rows) != 13:
        raise ValueError("P8 requires exactly 13 ordered hyperparameter configurations")
    if len({row["scientific_hash"] for row in rows}) != 13:
        raise ValueError("duplicate hyperparameter scientific hash")
    main = rows[0]["scientific"]
    mutable = {"d", "d_c", "per_head_dimension", "ffn_dimension", "effective_k", "intensity", "ema", "lambda_ip", "peak_learning_rate"}
    for row in rows:
        scientific = row["scientific"]
        if scientific["d"] != scientific["d_c"] or scientific["d"] != scientific["attention_heads"] * scientific["per_head_dimension"]:
            raise ValueError("dimension/head contract mismatch")
        if row["configuration_id"] != "cfg_main":
            changed = {name for name in mutable if scientific[name] != main[name]}
            factor_groups = ({"d", "d_c", "per_head_dimension", "ffn_dimension"}, {"effective_k"}, {"intensity"}, {"ema"}, {"lambda_ip"}, {"peak_learning_rate"})
            if sum(bool(changed & group) for group in factor_groups) != 1:
                raise ValueError("non-main configuration is not OFAT")
        if row["evaluation_query_identity"] is not None or row["evaluation_ancestry"]:
            raise ValueError("evaluation identity is prohibited in P8")


def build_comparison_templates(config: dict[str, Any]) -> list[dict[str, Any]]:
    common = {
        "selected_fm_dependency": "selected_configuration_identity",
        "inherited_settings": "all_validation_selected_FM_settings_except_explicit_transformation",
        "required_bank_identity": config["parents"]["p4_bank_id"],
        "validation_acceptance_id": config["parents"]["p5_validation_acceptance_id"],
        "evaluation_query_identity": None, "evaluation_ancestry": False,
        "final_config_hash_status": "UNRESOLVED_UNTIL_P9_A_SELECTION",
        "expected_materialization_count": 1, "hyperparameter_selection_eligible": False,
        "unsupported_fallbacks": ["cfg_main_substitution", "latest_checkpoint", "old_p7_lineage", "evaluation_identity"],
    }
    specs = [
        ("cmp_a1_no_geometry", "ablation", {"remove": ["intrinsic_geometry", "ip_geometry"], "retain_ip": ["relative_position", "semantic", "environmental_background"]}),
        ("cmp_a2_no_semantics", "ablation", {"remove": ["semantic", "ip_semantic"], "retain_ip": ["relative_position", "intrinsic_geometry", "environmental_background"]}),
        ("cmp_a3_no_raster_context", "ablation", {"remove": ["object_environmental_background", "scene_raster_branch", "ip_environmental_background"], "retain": ["vector_entities", "relations"]}),
        ("cmp_a4_no_spatial_relations", "ablation", {"remove": ["relation_aware_contextualization"], "replacement": "h_ra_equals_h_0", "retain": ["object_modalities", "raster_branches"]}),
        ("cmp_a5_radius_context", "ablation", {"replace": "heterogeneous_relation_graph_with_SN_radius_generic_relation", "omit": ["CNT", "WIT", "INT", "CON", "relation_embeddings", "relation_attention_terms", "relation_message_terms"], "retain": ["attention", "FFN", "residual", "pooling", "fusion"]}),
        ("cmp_ssv_like", "controlled_baseline", {"retain": ["relative_position", "semantic", "scene_contrastive", "ip_relative_position", "ip_semantic"], "remove": ["intrinsic_geometry", "object_environmental_background", "scene_raster_branch", "relation_aware_contextualization"], "direct_reproduction": False}),
        ("cmp_ds_like", "controlled_baseline", {"representation": "all_scene_observations_raster", "channels": "C_cat_plus_4", "building": "cell_coverage_proportion", "road": "geometry_presence", "poi": "log_counts", "landcover": "C_cat_composition_masked_zero", "dem": "standardized_continuous", "encoder": "dissertation_raster_CNN_GAP_d_projection", "remove": ["entity_modality_encoders"], "lambda_ip": 0.0, "direct_reproduction": False}),
    ]
    output = []
    for template_id, comparison_class, transformation in specs:
        payload = {"template_id": template_id, "configuration_family": "comparison", "comparison_class": comparison_class, **common, "transformation_contract": transformation}
        output.append({"schema_version": SCHEMA_VERSION, **payload, "template_hash": digest(payload), "implementation_readiness": "PLAN_VALIDATED_IMPLEMENTATION_REQUIRED_BEFORE_P9_B"})
    validate_comparison_templates(output)
    return output


def validate_comparison_templates(rows: list[dict[str, Any]]) -> None:
    if tuple(row["template_id"] for row in rows) != TEMPLATE_IDS or len(rows) != 7:
        raise ValueError("P8 requires exactly seven ordered comparison templates")
    if sum(row["comparison_class"] == "ablation" for row in rows) != 5 or sum(row["comparison_class"] == "controlled_baseline" for row in rows) != 2:
        raise ValueError("comparison family count mismatch")
    for row in rows:
        if row["final_config_hash_status"] != "UNRESOLVED_UNTIL_P9_A_SELECTION" or row["hyperparameter_selection_eligible"]:
            raise ValueError("comparison template was prematurely materialized")
        if row["evaluation_query_identity"] is not None or row["evaluation_ancestry"]:
            raise ValueError("evaluation identity is prohibited in comparison template")


def materialize_comparison(template: dict[str, Any], selected: dict[str, Any] | None) -> dict[str, Any]:
    if selected is None or selected.get("status") != "STABLE_ACCEPTED" or not selected.get("selected_configuration_identity"):
        raise ValueError("stable selected FM identity is required before P9-B materialization")
    if template["template_id"] not in TEMPLATE_IDS:
        raise ValueError("unrecognized comparison template")
    payload = {"selected_fm": selected["selected_configuration_identity"], "template_hash": template["template_hash"], "transformation": template["transformation_contract"]}
    return {**template, "selected_fm_dependency": selected["selected_configuration_identity"], "final_config_hash_status": "RESOLVED", "final_scientific_hash": digest(payload)}


class DimensionCompatibilityModel(nn.Module):
    """Construction-only shape gate for future P9 dimension variants."""

    def __init__(self, d: int, heads: int = 4, fixed_type: int = 16, fixed_relation: int = 32) -> None:
        super().__init__()
        if d not in (48, 64, 128) or d % heads:
            raise ValueError("unsupported dimension configuration")
        self.input_projection = nn.Linear(64, d)
        self.type_gate = nn.Linear(d + fixed_type, d)
        self.attention = nn.MultiheadAttention(d, heads, dropout=0.2, batch_first=True)
        self.relation_projection = nn.Linear(fixed_relation, heads * (d // heads))
        self.ffn = nn.Sequential(nn.Linear(d, 2 * d), nn.GELU(), nn.Linear(2 * d, d))
        self.scene_projection = nn.Linear(5 * d, d)
        self.contrastive_projection = nn.Sequential(nn.Linear(d, 2 * d), nn.GELU(), nn.Linear(2 * d, d))


def dimension_compatibility() -> dict[str, Any]:
    rows = []
    for d in (48, 64, 128):
        torch.manual_seed(20260830)
        model = DimensionCompatibilityModel(d)
        names = tuple(model.state_dict().keys())
        rows.append({"d": d, "d_c": d, "heads": 4, "per_head_dimension": d // 4, "state_dict_namespace_sha256": digest(names), "parameter_count": sum(p.numel() for p in model.parameters()), "construction": "PASS"})
    return {"status": "PASS", "legacy_d128_artifact_adopted": False, "rows": rows}


def build_bundle(config: dict[str, Any], root: Path, dissertation_root: Path) -> dict[str, dict[str, Any]]:
    source_commit = git_head(root)
    module_digests = dissertation_modules(config, dissertation_root)
    parents = config["parents"]
    compatibility_payload = {"source_commit": source_commit, "dissertation_commit": config["methodology"]["dissertation_commit"], "module_digests": module_digests, "scope": config["methodology"]["compatibility_scope"], "p0_p7_main_semantics_changed": False, "preserved_acceptances": {"p6": parents["p6_acceptance_id"], "p7": parents["p7_acceptance_id"]}}
    compatibility = {"schema_version": SCHEMA_VERSION, "status": "PASS", "compatibility_id": identity("p8mc_", compatibility_payload), **compatibility_payload}
    hyper_rows = build_hyperparameter_rows(config)
    hyper_payload = {"rows": hyper_rows, "count": 13, "factor_count": 6, "main_count": 1, "duplicate_hashes": 0}
    hyper = {"schema_version": SCHEMA_VERSION, "status": "PASS", "matrix_id": identity("p8hm_", hyper_payload), **hyper_payload}
    templates_rows = build_comparison_templates(config)
    template_payload = {"templates": templates_rows, "count": 7, "ablation_count": 5, "controlled_baseline_count": 2, "materialized_count": 0}
    templates = {"schema_version": SCHEMA_VERSION, "status": "PASS", "matrix_id": identity("p8cm_", template_payload), **template_payload}
    bank_payload = {"bank_id": parents["p4_bank_id"], "bank_acceptance_id": parents["p4_acceptance_id"], "logical_index_id": parents["p4_index_id"], "physical_k": 16, "nested_prefixes": [2, 4, 8, 16], "default_k": 8, "profile_mapping": {"weak_0.5x": 8, "main_1.0x": [2, 4, 8, 16], "strong_2.0x": 8}}
    bank = {"schema_version": SCHEMA_VERSION, "status": "PASS", "index_id": identity("p8bi_", bank_payload), **bank_payload}
    plan_payload = {"configuration_matrix_id": hyper["matrix_id"], "configuration_ids": list(CONFIG_IDS), "configuration_hashes": [row["scientific_hash"] for row in hyper_rows], "p9_stage": "P9-A", "attempt_count": 13, "selection": {"primary": "validation_retrieval_loss", "equivalence_threshold": 0.0001, "secondary": "source_separation_margin", "final_tie_break": "earlier_epoch"}, "validation_acceptance_id": parents["p5_validation_acceptance_id"], "evaluation_ancestry": False, "divergence_policy": config["divergence_policy"]}
    plan = {"schema_version": SCHEMA_VERSION, "status": "PASS", "plan_id": identity("p8hp_", plan_payload), **plan_payload}
    materialization_payload = {"template_matrix_id": templates["matrix_id"], "template_ids": list(TEMPLATE_IDS), "p9_stage": "P9-B", "depends_on": "selected_configuration_identity", "materializable_before_selection": 0, "expected_materialization_count": 7, "hyperparameter_selection_eligible": False, "evaluation_ancestry": False}
    materialization = {"schema_version": SCHEMA_VERSION, "status": "PASS", "template_id": identity("p8mt_", materialization_payload), **materialization_payload}
    authority_payload = {"source_commit": source_commit, "methodology_compatibility_id": compatibility["compatibility_id"], "p7_acceptance_id": parents["p7_acceptance_id"], "p7_best_checkpoint_id": parents["p7_best_checkpoint_id"], "runtime_acceptance_id": parents["p7_runtime_acceptance_id"], "validation_acceptance_id": parents["p5_validation_acceptance_id"]}
    authority_id = identity("p8a_", authority_payload)
    aggregate_payload = {"authority_id": authority_id, "compatibility_id": compatibility["compatibility_id"], "hyperparameter_matrix_id": hyper["matrix_id"], "comparison_matrix_id": templates["matrix_id"], "bank_index_id": bank["index_id"], "hyperparameter_plan_id": plan["plan_id"], "materialization_template_id": materialization["template_id"], "parents": parents, "counts": config["run_accounting"], "evaluation_ancestry_count": 0, "optimizer_update_count": 0, "checkpoint_creation_count": 0, "p9_p10_p11_execution_count": 0}
    acceptance = {"schema_version": SCHEMA_VERSION, "status": "PASS", "authority_id": authority_id, "acceptance_id": identity("p8acc_", aggregate_payload), **aggregate_payload, "dimension_compatibility": dimension_compatibility(), "content_sha256": digest(aggregate_payload)}
    return {"methodology_compatibility": compatibility, "hyperparameter_configuration_matrix": hyper, "comparison_variant_template_matrix": templates, "experiment_augmentation_bank_index": bank, "formal_hyperparameter_experiment_plan": plan, "comparison_variant_materialization_template": materialization, "formal_experiment_plan_acceptance": acceptance}


def validate_schema(value: dict[str, Any], schema_path: Path) -> None:
    jsonschema.Draft202012Validator(json.loads(schema_path.read_text())).validate(value)


def write_bundle(bundle: dict[str, dict[str, Any]], output: Path, schemas: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    for name, value in bundle.items():
        validate_schema(value, schemas / f"p8_{name}.schema.json")
        (output / f"{name}.json").write_bytes(canonical_bytes(value))
