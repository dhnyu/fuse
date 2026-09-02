"""Winner-bound sequential P9-B comparison campaign."""

from __future__ import annotations

import copy
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Mapping

import yaml

from p9_a_campaign import atomic_write, campaign_parents, implementation_hash, publish_authority
from p9_infrastructure import configuration_seed
from p9_selected_fm_campaign import CampaignLock, _resolver, _status, SelectedFMCampaignPaths
from p9_v2_canonical import canonical_json_bytes, canonical_sha256
from p9_v2_schema import validate_instance
from p9_v2_training_controller import build_training_authority, validate_training_authority
from p9_v2_training_lifecycle import scientific_configuration_content


CONFIGURATIONS = (
    "cmp_a1_geometric_core", "cmp_a2_semantic_enriched",
    "cmp_a3_object_context_enriched", "cmp_a4_raster_complete_non_relational",
    "cmp_a5_relation_type_agnostic", "cmp_ssv_like", "cmp_ds_like",
)
FAMILIES = {name: name.split("_")[1].upper() for name in CONFIGURATIONS[:5]} | {
    "cmp_ssv_like": "SSV", "cmp_ds_like": "DS",
}


class P9BCampaignError(RuntimeError):
    """The selected-model comparison campaign cannot safely advance."""


def build_training_matrix(plan: Mapping[str, Any]) -> dict[str, Any]:
    validate_instance("p9_b_selected_model_plan", dict(plan))
    content = {key: value for key, value in plan.items() if key not in ("plan_id", "content_sha256")}
    observed = canonical_sha256(content)
    if plan["content_sha256"] != observed or plan["plan_id"] != "p9bplan_" + observed[:24]:
        raise P9BCampaignError("P9_B_PLAN_IDENTITY_INVALID")
    if tuple(item.get("template_id") for item in plan["comparisons"]) != CONFIGURATIONS:
        raise P9BCampaignError("P9_B_TEMPLATE_ORDER_INVALID")
    selected = plan["selected_scientific_configuration"]["content"]
    if selected.get("configuration_id") != "cfg_selected_fm_ip1":
        raise P9BCampaignError("P9_B_SELECTED_FM_WINNER_INVALID")
    rows = []
    for item in plan["comparisons"]:
        configuration_id = item["template_id"]; family = FAMILIES[configuration_id]
        scientific = copy.deepcopy(selected["scientific"])
        if family == "DS": scientific["lambda_ip"] = 0.0
        rows.append({
            "configuration_id": configuration_id, "configuration_family": "comparison",
            "model_family": family, "scientific_hash": item["final_scientific_hash"],
            "scientific": scientific, "bank_binding": copy.deepcopy(selected["bank_binding"]),
            "transformation_contract": copy.deepcopy(item["transformation_contract"]),
            "selected_fm_acceptance_id": plan["selected_fm_acceptance_id"],
            "p9_b_plan_id": plan["plan_id"], "run_seed_configuration_id": configuration_id,
            "run_seed_formula": "sha256_canonical_json_root_seed_configuration_id",
            "run_seed_namespace": f"p9-b/{configuration_id}",
            "parent_p7_acceptance_id": selected["parent_p7_acceptance_id"],
            "runtime_acceptance_id": selected["runtime_acceptance_id"],
            "validation_acceptance_id": selected["validation_acceptance_id"],
            "evaluation_query_identity": None, "evaluation_ancestry": False,
        })
    value = {"schema_version": "1.0.0", "artifact_type": "p9_b_training_matrix",
             "status": "MATERIALIZED_NOT_EXECUTED", "plan_id": plan["plan_id"],
             "selected_fm_acceptance_id": plan["selected_fm_acceptance_id"],
             "count": 7, "evaluation_ancestry": False, "rows": rows}
    validate_instance("p9_b_training_matrix", value)
    return value


def build_authority(row: Mapping[str, Any], contract: Mapping[str, Any], repository: Path) -> dict[str, Any]:
    if row["configuration_id"] not in CONFIGURATIONS:
        raise P9BCampaignError("P9_B_CONFIGURATION_INVALID")
    parents = campaign_parents(contract)
    if parents.get("selected_fm_acceptance_id") != row["selected_fm_acceptance_id"]:
        raise P9BCampaignError("P9_B_SELECTED_FM_PARENT_MISMATCH")
    return build_training_authority(
        configuration_id=row["configuration_id"],
        configuration_hash=canonical_sha256(scientific_configuration_content(row)),
        p8_configuration_hash=row["scientific_hash"],
        scientific_implementation_hash=implementation_hash(repository),
        root_seed=configuration_seed(20260828, row["run_seed_configuration_id"]),
        parents=parents,
        parent_hashes={key: canonical_sha256({"identity": value}) for key, value in parents.items()},
    )


def campaign_contract(base: Mapping[str, Any], matrix: Path, eligibility: Path,
                      selected_fm_acceptance_id: str) -> dict[str, Any]:
    value = json.loads(json.dumps(base)); value["roots"]["configuration_matrix"] = str(matrix.resolve())
    value["roots"]["eligibility_snapshot"] = str(eligibility.resolve())
    value["parents"]["selected_fm_acceptance_id"] = selected_fm_acceptance_id
    return value


def _restore(paths: SelectedFMCampaignPaths, rows: list[dict[str, Any]], contract: Mapping[str, Any]):
    eligibility = Path(contract["roots"]["eligibility_snapshot"])
    if not paths.status.exists(): return [], eligibility
    status = json.loads(paths.status.read_text(encoding="utf-8")); completed = status.get("completed", [])
    if [item.get("configuration_id") for item in completed] != list(CONFIGURATIONS[:len(completed)]):
        raise P9BCampaignError("P9_B_COMPLETED_PREFIX_INVALID")
    if not completed: return [], eligibility
    eligibility = Path(status["latest_eligibility"])
    resolver = _resolver(Path(contract["roots"]["canonical_publication"]), eligibility, completed)
    for row, item in zip(rows[:len(completed)], completed, strict=True):
        authority = json.loads(Path(item["authority_path"]).read_text(encoding="utf-8")); validate_training_authority(authority)
        if authority["content"]["scientific"]["configuration_hash"] != canonical_sha256(scientific_configuration_content(row)):
            raise P9BCampaignError("P9_B_RESTORE_CONFIGURATION_MISMATCH")
        resolved = resolver.resolve_accepted_checkpoint(item["acceptance_id"])
        if resolved.authority_id != authority["identity"] or resolved.checkpoint_id != item["checkpoint_id"]:
            raise P9BCampaignError("P9_B_RESTORE_RESOLVER_MISMATCH")
    return list(completed), eligibility


def run_campaign(paths: SelectedFMCampaignPaths, plan_path: Path) -> None:
    base = yaml.safe_load(paths.base_contract.read_text(encoding="utf-8"))
    plan = json.loads(plan_path.read_text(encoding="utf-8")); matrix_value = build_training_matrix(plan)
    templates = json.loads((Path(base["roots"]["p8_bundle"]) / "comparison_variant_template_matrix.json").read_text())["templates"]
    for current, source in zip(plan["comparisons"], templates, strict=True):
        if (current["template_id"], current["template_hash"], current["transformation_contract"]) != (
                source["template_id"], source["template_hash"], source["transformation_contract"]):
            raise P9BCampaignError("P9_B_TEMPLATE_SOURCE_MISMATCH")
    atomic_write(paths.matrix, canonical_json_bytes(matrix_value)); rows = matrix_value["rows"]
    base["parents"]["selected_fm_acceptance_id"] = plan["selected_fm_acceptance_id"]
    selected_acceptance = json.loads((Path(base["roots"]["canonical_publication"]) / "acceptances" /
                                      plan["selected_fm_acceptance_id"] / "acceptance.json").read_text())
    selected_lifecycle = Path(base["roots"]["lifecycle_records"]) / selected_acceptance["authority_id"] / "bundle.json"
    selected_resolver = _resolver(Path(base["roots"]["canonical_publication"]),
                                  Path(base["roots"]["eligibility_snapshot"]),
                                  [{"bundle_record": str(selected_lifecycle)}])
    selected = selected_resolver.resolve_accepted_checkpoint(plan["selected_fm_acceptance_id"])
    if (selected.scientific_configuration["content"]["configuration_id"] != "cfg_selected_fm_ip1" or
            any(item["selected_checkpoint_id"] != selected.checkpoint_id for item in plan["comparisons"])):
        raise P9BCampaignError("P9_B_SELECTED_FM_RESOLUTION_MISMATCH")
    completed, eligibility = _restore(paths, rows, base)
    _status(paths, status="RUNNING", configurations=list(CONFIGURATIONS), completed=completed,
            current_configuration=None, latest_eligibility=str(eligibility), evaluation_consumption_count=0,
            selected_fm_acceptance_id=plan["selected_fm_acceptance_id"], p9_b_plan_id=plan["plan_id"],
            error=None, error_type=None)
    canonical = Path(base["roots"]["canonical_publication"])
    for row in rows[len(completed):]:
        configuration_id = row["configuration_id"]; authority = build_authority(row, base, paths.repository)
        config_root = paths.root / configuration_id; candidate = config_root / "authority_candidate.json"
        atomic_write(candidate, canonical_json_bytes(authority))
        dynamic = campaign_contract(base, paths.matrix, eligibility, plan["selected_fm_acceptance_id"])
        contract_path = config_root / "training_contract.yml"
        atomic_write(contract_path, yaml.safe_dump(dynamic, sort_keys=True).encode("utf-8"))
        _status(paths, current_configuration=configuration_id, stage="PREAUTHORITY_PREFLIGHT")
        environment = os.environ.copy(); environment.update({"PYTHONDONTWRITEBYTECODE":"1", "NCCL_P2P_DISABLE":"1", "NCCL_IB_DISABLE":"1"})
        subprocess.run([environment.get("PYTHON", "python"), "scripts/p9_v2_training_controller.py", "preflight",
                        "--authority", str(candidate), "--contract", str(contract_path)],
                       cwd=paths.repository, env=environment, check=True, stdout=subprocess.DEVNULL)
        authority_path = publish_authority(authority, canonical / "authorities")
        store = paths.root / "target_stores" / f"fuse-p9-v2-training-{authority['identity']}"
        environment.update({"P9_V2_TRAINING_AUTHORITY":str(authority_path), "P9_V2_TRAINING_CONTRACT":str(contract_path)})
        log_path = config_root / "targets.log"; _status(paths, stage="TARGET_RUNNING", authority_id=authority["identity"], target_store=str(store), configuration_log=str(log_path))
        print(f"CONFIG_TARGET_STARTED {configuration_id} {authority['identity']}", flush=True)
        expression = "targets::tar_make(script='_targets_p9_v2_training.R', " + f"store={json.dumps(str(store))}, reporter='timestamp')"
        with log_path.open("ab", buffering=0) as stream:
            result = subprocess.run(["Rscript", "-e", expression], cwd=paths.repository, env=environment, stdout=stream, stderr=subprocess.STDOUT)
        if result.returncode != 0:
            _status(paths, status="BLOCKED", stage="TARGET_FAILED", returncode=result.returncode)
            raise P9BCampaignError(f"CONFIGURATION_FAILED:{configuration_id}")
        lifecycle = Path(base["roots"]["lifecycle_records"]) / authority["identity"]
        eligibility_record=json.loads((lifecycle/"eligibility.json").read_text()); resolution=json.loads((lifecycle/"resolution.json").read_text())
        eligibility=Path(eligibility_record["eligibility_path"])
        item={"configuration_id":configuration_id,"authority_id":authority["identity"],"authority_path":str(authority_path),
              "acceptance_id":eligibility_record["acceptance_id"],"eligibility_id":eligibility_record["eligibility_id"],
              "checkpoint_id":resolution["checkpoint_id"],"bundle_record":str(lifecycle/"bundle.json"),"evaluation_consumption_count":0}
        completed.append(item); _status(paths, completed=completed,current_configuration=None,stage="CONFIGURATION_COMPLETE",latest_eligibility=str(eligibility))
        print(f"CONFIG_COMPLETE {configuration_id} {item['acceptance_id']}",flush=True)
    _status(paths,status="COMPLETE",stage="P9_B_COMPLETE",current_configuration=None,latest_eligibility=str(eligibility))


def execute(paths: SelectedFMCampaignPaths, plan_path: Path) -> None:
    with CampaignLock(paths.root / "campaign.lock"):
        try: run_campaign(paths, plan_path)
        except BaseException as error:
            if paths.status.exists(): _status(paths,status="BLOCKED",error_type=type(error).__name__,error=str(error))
            raise
