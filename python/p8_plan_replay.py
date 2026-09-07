"""Read-only replay of accepted P8 experimental-setup/hyperparameter evidence.

No imports from the scientific builder: even dimension compatibility is readback.
"""

import argparse
import hashlib
import json
from pathlib import Path

import jsonschema
import yaml


ARTIFACTS = (
    "methodology_compatibility",
    "hyperparameter_configuration_matrix",
    "a5_generic_relation_mapping_contract",
    "ds_raster_materialization_contract",
    "comparison_variant_template_matrix",
    "experiment_augmentation_bank_index",
    "formal_hyperparameter_experiment_plan",
    "comparison_variant_materialization_template",
    "formal_experiment_plan_acceptance",
)
IDENTITY_FIELDS = (
    "compatibility_id", "matrix_id", "contract_id", "contract_id", "matrix_id",
    "index_id", "plan_id", "template_id", "acceptance_id",
)
ACCEPTANCE_LINKS = (
    "compatibility_id", "hyperparameter_matrix_id", "a5_generic_relation_contract_id",
    "ds_raster_materialization_contract_id", "comparison_matrix_id", "bank_index_id",
    "hyperparameter_plan_id", "materialization_template_id",
)
COUNTS = {
    "hyperparameter_attempts": 13, "comparison_attempts": 7, "total_attempts": 20,
    "main_training_duplication": 0, "immediately_executable_specs": 13,
    "materializable_comparison_specs_before_selection": 0,
}


def require(condition, message):
    if not condition:
        raise ValueError("P8 replay: " + message)


def read_json_bytes(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate JSON key: " + key)
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError("P8 replay: invalid JSON constant " + value)

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid_constant)


def validate_bundle(bundle, anchor, config):
    compatibility, hyper, a5, ds, comparison, bank, plan, materialization, acceptance = (
        bundle[name] for name in ARTIFACTS
    )
    for name, field, spec in zip(ARTIFACTS, IDENTITY_FIELDS, anchor["artifacts"]):
        require(spec["identity_field"] == field, "identity field mapping mismatch")
        require(bundle[name][field] == spec["identity"], "artifact identity mismatch: " + name)
        require(bundle[name]["status"] == "PASS", "acceptance/status is not PASS: " + name)
    for name, field, link in zip(ARTIFACTS, IDENTITY_FIELDS, ACCEPTANCE_LINKS):
        require(acceptance[link] == bundle[name][field], "cross-artifact identity mismatch: " + link)
    require(acceptance["authority_id"] == anchor["authority_id"], "authority identity mismatch")
    require(acceptance["acceptance_id"] == anchor["acceptance_id"], "acceptance identity mismatch")
    require(compatibility["source_commit"] == anchor["source_commit"], "producer commit mismatch")
    require(compatibility["dissertation_commit"] == anchor["dissertation_commit"]
            == config["methodology"]["dissertation_commit"], "dissertation commit mismatch")
    require(compatibility["p0_p7_main_semantics_changed"] is False, "main semantics changed")
    parents = config["parents"]
    require(acceptance["parents"] == parents, "accepted parent identities mismatch")
    require(compatibility["preserved_acceptances"]
            == {"p6": parents["p6_acceptance_id"], "p7": parents["p7_acceptance_id"]},
            "preserved acceptance mismatch")
    require(a5["parent_p7_acceptance_id"] == ds["parent_p7_acceptance_id"]
            == parents["p7_acceptance_id"], "comparison parent mismatch")
    require(bank["bank_id"] == parents["p4_bank_id"]
            and bank["bank_acceptance_id"] == parents["p4_acceptance_id"]
            and bank["logical_index_id"] == parents["p4_index_id"], "bank identity mismatch")
    require(plan["configuration_matrix_id"] == hyper["matrix_id"]
            and materialization["template_matrix_id"] == comparison["matrix_id"],
            "plan matrix identity mismatch")
    for document in (comparison, materialization):
        require(document["a5_generic_relation_contract_id"] == a5["contract_id"]
                and document["ds_raster_materialization_contract_id"] == ds["contract_id"],
                "comparison contract identity mismatch")

    require(acceptance["counts"] == config["run_accounting"] == COUNTS, "attempt accounting mismatch")
    rows, templates = hyper["rows"], comparison["templates"]
    require(len(rows) == hyper["count"] == plan["attempt_count"] == 13, "configuration count mismatch")
    ids = [row["configuration_id"] for row in rows]
    hashes = [row["scientific_hash"] for row in rows]
    require(len(set(ids)) == len(set(hashes)) == 13 and ids.count("cfg_main") == 1,
            "duplicate configurations")
    require(plan["configuration_ids"] == ids and plan["configuration_hashes"] == hashes,
            "configuration order/hash mismatch")
    require(hyper["main_count"] == 1 and hyper["duplicate_hashes"] == 0
            and hyper["factor_count"] == 6, "factor accounting mismatch")
    require(len(templates) == comparison["count"] == materialization["expected_materialization_count"] == 7,
            "comparison count mismatch")
    template_ids = [row["template_id"] for row in templates]
    require(len(set(template_ids)) == 7 and materialization["template_ids"] == template_ids,
            "template order mismatch")
    require(sum(row["comparison_class"] == "ablation" for row in templates)
            == comparison["ablation_count"] == 5, "ablation accounting mismatch")
    require(sum(row["comparison_class"] == "controlled_baseline" for row in templates)
            == comparison["controlled_baseline_count"] == 2, "baseline accounting mismatch")
    require(comparison["materialized_count"] == materialization["materializable_before_selection"] == 0,
            "premature materialization")
    require(materialization["hyperparameter_selection_eligible"] is False,
            "comparison selection eligibility mismatch")
    require(plan["validation_acceptance_id"] == parents["p5_validation_acceptance_id"],
            "validation parent mismatch")
    for row in rows + templates:
        require(row["evaluation_ancestry"] is False and row["evaluation_query_identity"] is None,
                "evaluation ancestry is prohibited")
        require(row["validation_acceptance_id"] == parents["p5_validation_acceptance_id"],
                "row validation parent mismatch")
    for row in rows:
        require(row["parent_p7_acceptance_id"] == parents["p7_acceptance_id"]
                and row["runtime_acceptance_id"] == parents["p7_runtime_acceptance_id"],
                "configuration parent mismatch")
        binding = row["bank_binding"]
        require(binding["physical_bank_id"] == bank["bank_id"]
                and binding["bank_acceptance_id"] == bank["bank_acceptance_id"]
                and binding["logical_index_id"] == bank["logical_index_id"], "row bank mismatch")
    for row in templates:
        require(row["required_bank_identity"] == bank["bank_id"]
                and row["hyperparameter_selection_eligible"] is False
                and row["final_config_hash_status"] == "UNRESOLVED_UNTIL_P9_A_SELECTION",
                "template materialization/parent mismatch")
    require(plan["evaluation_ancestry"] is False and materialization["evaluation_ancestry"] is False,
            "plan evaluation ancestry is prohibited")
    for field in ("evaluation_ancestry_count", "optimizer_update_count",
                  "checkpoint_creation_count", "p9_p10_p11_execution_count"):
        require(type(acceptance[field]) is int and acceptance[field] == 0, field + " must be zero")
    require(all(value is False or (type(value) is int and value == 0)
                for value in config["execution_prohibitions"].values()), "execution prohibition mismatch")
    dimension = acceptance["dimension_compatibility"]
    require(dimension["status"] == "PASS" and dimension["legacy_d128_artifact_adopted"] is False
            and [row["d"] for row in dimension["rows"]] == [48, 64, 128]
            and all(row["construction"] == "PASS" for row in dimension["rows"]),
            "dimension compatibility evidence mismatch")


def replay(root, contract="config/p8_refactor_replay.yml"):
    root = Path(root).resolve(strict=True)
    anchor = yaml.safe_load((root / contract).read_text())
    require(anchor["schema_version"] == "1.0.0"
            and anchor["policy"] == "fail_closed_read_only_no_fallback", "unsupported replay policy")
    specs = anchor["artifacts"]
    require([spec["basename"] for spec in specs] == [name + ".json" for name in ARTIFACTS],
            "artifact ordering mismatch")
    directory = Path(anchor["bundle_root"])
    require(directory.is_absolute(), "bundle root must be absolute")
    config_raw = (root / "config/p8_formal_experiment_plan.yml").read_bytes()
    require(hashlib.sha256(config_raw).hexdigest() == anchor["scientific_config_sha256"],
            "scientific config anchor mismatch")
    config = yaml.safe_load(config_raw)
    bundle, paths = {}, []
    for name, spec in zip(ARTIFACTS, specs):
        require(spec["schema"] == "config/schemas/p8_" + name + ".schema.json",
                "schema mapping mismatch")
        path = directory / spec["basename"]
        raw = path.read_bytes()
        require(len(raw) == spec["size"], "size mismatch: " + path.name)
        require(hashlib.sha256(raw).hexdigest() == spec["sha256"], "SHA-256 mismatch: " + path.name)
        document = read_json_bytes(raw)
        schema = read_json_bytes((root / spec["schema"]).read_bytes())
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.Draft202012Validator(schema).validate(document)
        bundle[name] = document
        paths.append(str(path))
    validate_bundle(bundle, anchor, config)
    return paths


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--contract", default="config/p8_refactor_replay.yml")
    arguments = parser.parse_args()
    print(json.dumps(replay(arguments.root, arguments.contract)))
