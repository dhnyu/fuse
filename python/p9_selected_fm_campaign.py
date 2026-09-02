"""Sequential two-run selected-FM confirmation and validation-only decision."""

from __future__ import annotations

import fcntl
import json
import os
import subprocess
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

import yaml

from p8_experiment_plan import materialize_comparison
from p9_a_campaign import atomic_write, campaign_parents, implementation_hash, publish_authority
from p9_infrastructure import configuration_seed
from p9_v2_canonical import canonical_json_bytes, canonical_sha256
from p9_v2_downstream import AcceptedCheckpointResolver, load_acceptance_eligibility
from p9_v2_ledger import fsync_directory, write_all
from p9_v2_prepared_cache import ProductionPreparedData
from p9_v2_schema import validate_instance
from p9_v2_training_controller import build_training_authority, validate_training_authority
from p9_v2_training_lifecycle import scientific_configuration_content


CONFIGURATIONS = ("cfg_selected_fm_ip0", "cfg_selected_fm_ip1")
EXPECTED_SOURCE_HASHES = (
    "961fac037720ab45a9e295598bdef41be59183a2fe3a2a5335d900217bb75bb7",
    "cd0e6c835b4e788408e60a42ea516f7f0f00e3388a969fe1471f195dae02fb32",
)


class SelectedFMCampaignError(RuntimeError):
    """The bounded selected-FM comparison cannot safely advance."""


@dataclass(frozen=True)
class SelectedFMCampaignPaths:
    root: Path
    repository: Path
    base_contract: Path
    matrix: Path

    @property
    def status(self) -> Path:
        return self.root / "campaign_status.json"


class CampaignLock:
    def __init__(self, path: Path):
        self.path = path
        self.stream = None

    def __enter__(self) -> "CampaignLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = self.path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise SelectedFMCampaignError("P9_SELECTED_FM_CAMPAIGN_ALREADY_RUNNING") from error
        return self

    def __exit__(self, *_: object) -> None:
        assert self.stream is not None
        fcntl.flock(self.stream.fileno(), fcntl.LOCK_UN)
        self.stream.close()


def load_confirmation_rows(path: str | Path) -> list[dict[str, Any]]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_instance("selected_fm_confirmation_matrix", value)
    rows = value.get("rows")
    if not isinstance(rows, list) or tuple(row.get("configuration_id") for row in rows) != CONFIGURATIONS:
        raise SelectedFMCampaignError("SELECTED_FM_CONFIGURATION_ORDER_INVALID")
    if tuple(row.get("scientific_hash") for row in rows) != EXPECTED_SOURCE_HASHES:
        raise SelectedFMCampaignError("SELECTED_FM_SOURCE_HASH_INVALID")
    left, right = rows
    if left["run_seed_configuration_id"] != "cfg_selected_fm" or right["run_seed_configuration_id"] != "cfg_selected_fm":
        raise SelectedFMCampaignError("SELECTED_FM_SEED_NAMESPACE_INVALID")
    differences = {
        key for key in left["scientific"]
        if left["scientific"][key] != right["scientific"][key]
    }
    if differences != {"lambda_ip"} or left["scientific"]["lambda_ip"] != 0.0 or right["scientific"]["lambda_ip"] != 1.0:
        raise SelectedFMCampaignError("SELECTED_FM_NOT_EXACT_IP_COMPARISON")
    for row in rows:
        bank = row["bank_binding"]
        if (bank["nested_subset_identity"], bank["effective_k"], bank["profile_id"]) != (
            "p8abi_24471ee4574c585c98083b53", 4, "weak_0.5x"
        ) or row["evaluation_ancestry"] is not False or row["evaluation_query_identity"] is not None:
            raise SelectedFMCampaignError("SELECTED_FM_BANK_OR_EVALUATION_INVALID")
    return rows


def selected_contract(base: Mapping[str, Any], matrix: Path, eligibility: Path) -> dict[str, Any]:
    value = json.loads(json.dumps(base))
    value["roots"]["configuration_matrix"] = str(matrix.resolve())
    value["roots"]["eligibility_snapshot"] = str(eligibility.resolve())
    return value


def build_authority(row: Mapping[str, Any], contract: Mapping[str, Any], repository: Path) -> dict[str, Any]:
    parents = campaign_parents(contract)
    return build_training_authority(
        configuration_id=row["configuration_id"],
        configuration_hash=canonical_sha256(scientific_configuration_content(row)),
        p8_configuration_hash=row["scientific_hash"],
        scientific_implementation_hash=implementation_hash(repository),
        root_seed=configuration_seed(20260828, row["run_seed_configuration_id"]),
        parents=parents,
        parent_hashes={key: canonical_sha256({"identity": value}) for key, value in parents.items()},
    )


def compare_results(left: Mapping[str, Any], right: Mapping[str, Any], tolerance: float = 1e-4) -> str:
    loss_delta = Decimal.from_float(float(left["validation_retrieval_loss"])) - Decimal.from_float(float(right["validation_retrieval_loss"]))
    if abs(loss_delta) >= Decimal.from_float(tolerance):
        return "cfg_selected_fm_ip0" if loss_delta < 0 else "cfg_selected_fm_ip1"
    margin_delta = Decimal.from_float(float(left["mean_source_separation_margin"])) - Decimal.from_float(float(right["mean_source_separation_margin"]))
    if margin_delta:
        return "cfg_selected_fm_ip0" if margin_delta > 0 else "cfg_selected_fm_ip1"
    return "cfg_selected_fm_ip0"


def _publish_file(path: Path, value: Mapping[str, Any]) -> Path:
    raw = canonical_json_bytes(dict(value))
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != raw:
            raise SelectedFMCampaignError("IMMUTABLE_PUBLICATION_COLLISION")
        return path
    staging = path.with_name(f".{path.name}.incomplete-{os.getpid()}")
    descriptor = os.open(staging, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o640)
    try:
        write_all(descriptor, raw)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    try:
        os.link(staging, path)
    except FileExistsError:
        if path.read_bytes() != raw:
            raise SelectedFMCampaignError("IMMUTABLE_PUBLICATION_COLLISION")
    finally:
        staging.unlink(missing_ok=True)
    fsync_directory(path.parent)
    if path.read_bytes() != raw:
        raise SelectedFMCampaignError("IMMUTABLE_PUBLICATION_VERIFY_FAILED")
    return path


def _status(paths: SelectedFMCampaignPaths, **values: Any) -> None:
    current = {} if not paths.status.exists() else json.loads(paths.status.read_text(encoding="utf-8"))
    current.update(values)
    atomic_write(paths.status, canonical_json_bytes(current))


def _resolver(canonical: Path, eligibility: Path, completed: list[dict[str, Any]]) -> AcceptedCheckpointResolver:
    roots = {}
    for item in completed:
        handoff = json.loads(Path(item["bundle_record"]).read_text(encoding="utf-8"))
        roots[handoff["checkpoint_namespace"]] = Path(handoff["checkpoint_root"])
    return AcceptedCheckpointResolver(
        canonical / "acceptances", canonical / "bundles", roots,
        load_acceptance_eligibility(eligibility),
    )


def _restore(paths: SelectedFMCampaignPaths, rows: list[dict[str, Any]], contract: Mapping[str, Any]) -> tuple[list[dict[str, Any]], Path]:
    eligibility = Path(contract["roots"]["eligibility_snapshot"])
    if not paths.status.exists():
        return [], eligibility
    status = json.loads(paths.status.read_text(encoding="utf-8"))
    completed = status.get("completed", [])
    if [item.get("configuration_id") for item in completed] != list(CONFIGURATIONS[:len(completed)]):
        raise SelectedFMCampaignError("SELECTED_FM_COMPLETED_PREFIX_INVALID")
    if not completed:
        return [], eligibility
    eligibility = Path(status["latest_eligibility"])
    resolver = _resolver(Path(contract["roots"]["canonical_publication"]), eligibility, completed)
    for row, item in zip(rows[:len(completed)], completed, strict=True):
        authority = json.loads(Path(item["authority_path"]).read_text(encoding="utf-8"))
        validate_training_authority(authority)
        if (authority["content"]["scientific"]["configuration_id"] != row["configuration_id"] or
                authority["content"]["scientific"]["configuration_hash"] != canonical_sha256(scientific_configuration_content(row))):
            raise SelectedFMCampaignError("SELECTED_FM_RESTORE_CONFIGURATION_MISMATCH")
        resolved = resolver.resolve_accepted_checkpoint(item["acceptance_id"])
        if resolved.authority_id != authority["identity"] or resolved.checkpoint_id != item["checkpoint_id"]:
            raise SelectedFMCampaignError("SELECTED_FM_RESTORE_RESOLVER_MISMATCH")
    return list(completed), eligibility


def _publish_decision(paths: SelectedFMCampaignPaths, contract: Mapping[str, Any], completed: list[dict[str, Any]], eligibility: Path) -> tuple[Path, Path]:
    canonical = Path(contract["roots"]["canonical_publication"])
    resolver = _resolver(canonical, eligibility, completed)
    resolved = {item["configuration_id"]: resolver.resolve_accepted_checkpoint(item["acceptance_id"])
                for item in completed}
    evidence = {name: {
        "acceptance_id": value.acceptance_id, "checkpoint_id": value.checkpoint_id,
        "selected_epoch": value.completed_epoch,
        "validation_retrieval_loss": value.validation_retrieval_loss,
        "mean_source_separation_margin": value.mean_source_separation_margin,
    } for name, value in resolved.items()}
    winner = compare_results(evidence[CONFIGURATIONS[0]], evidence[CONFIGURATIONS[1]])
    payload = {
        "schema_version": "1.0.0", "artifact_type": "p9_selected_fm_decision",
        "status": "SELECTED", "selection_contract": "validation_loss_1e-4_margin_then_ip0",
        "eligibility_id": load_acceptance_eligibility(eligibility)["eligibility_id"],
        "results": evidence, "selected_configuration_id": winner,
        "selected_acceptance_id": resolved[winner].acceptance_id,
        "evaluation_consumption_count": 0,
    }
    digest = canonical_sha256(payload)
    decision = {**payload, "decision_id": "p9sfm_" + digest[:24], "content_sha256": digest}
    validate_instance("selected_fm_decision", decision)
    decision_path = _publish_file(canonical / "selected_fm" / f"{decision['decision_id']}.json", decision)
    template_path = Path(contract["roots"]["p8_bundle"]) / "comparison_variant_template_matrix.json"
    templates = json.loads(template_path.read_text(encoding="utf-8"))["templates"]
    materialized = [materialize_comparison(template, resolved[winner].acceptance_id, resolver) for template in templates]
    p9b_payload = {
        "schema_version": "1.0.0", "artifact_type": "p9_b_selected_model_plan",
        "status": "MATERIALIZED_NOT_EXECUTED", "selected_fm_decision_id": decision["decision_id"],
        "selected_fm_acceptance_id": resolved[winner].acceptance_id,
        "selected_scientific_configuration": resolved[winner].scientific_configuration,
        "comparisons": materialized, "count": 7, "evaluation_consumption_count": 0,
    }
    p9b_digest = canonical_sha256(p9b_payload)
    p9b = {**p9b_payload, "plan_id": "p9bplan_" + p9b_digest[:24], "content_sha256": p9b_digest}
    validate_instance("p9_b_selected_model_plan", p9b)
    p9b_path = _publish_file(canonical / "p9_b_plans" / f"{p9b['plan_id']}.json", p9b)
    atomic_write(paths.root / "comparison_result.json", canonical_json_bytes({
        "decision_path": str(decision_path), "p9_b_plan_path": str(p9b_path), **decision,
    }))
    return decision_path, p9b_path


def run_campaign(paths: SelectedFMCampaignPaths) -> None:
    contract = yaml.safe_load(paths.base_contract.read_text(encoding="utf-8"))
    rows = load_confirmation_rows(paths.matrix)
    cache = ProductionPreparedData(contract["roots"]["production_cache"], "weak_0.5x", 4)
    if len(cache.training_scenes) != 2421 or any(len(value) != 4 for value in cache.views.values()):
        raise SelectedFMCampaignError("SELECTED_FM_WEAK_K4_POPULATION_INVALID")
    completed, eligibility = _restore(paths, rows, contract)
    _status(paths, status="RUNNING", configurations=list(CONFIGURATIONS), completed=completed,
            current_configuration=None, latest_eligibility=str(eligibility), evaluation_consumption_count=0,
            error=None, error_type=None)
    canonical = Path(contract["roots"]["canonical_publication"])
    for row in rows[len(completed):]:
        configuration_id = row["configuration_id"]
        authority = build_authority(row, contract, paths.repository)
        config_root = paths.root / configuration_id
        candidate = config_root / "authority_candidate.json"
        atomic_write(candidate, canonical_json_bytes(authority))
        dynamic = selected_contract(contract, paths.matrix, eligibility)
        contract_path = config_root / "training_contract.yml"
        atomic_write(contract_path, yaml.safe_dump(dynamic, sort_keys=True).encode("utf-8"))
        _status(paths, current_configuration=configuration_id, stage="PREAUTHORITY_PREFLIGHT")
        environment = os.environ.copy()
        environment.update({"PYTHONDONTWRITEBYTECODE": "1", "NCCL_P2P_DISABLE": "1", "NCCL_IB_DISABLE": "1"})
        subprocess.run([environment.get("PYTHON", "python"), "scripts/p9_v2_training_controller.py", "preflight",
                        "--authority", str(candidate), "--contract", str(contract_path)],
                       cwd=paths.repository, env=environment, check=True, stdout=subprocess.DEVNULL)
        authority_path = publish_authority(authority, canonical / "authorities")
        store = paths.root / "target_stores" / f"fuse-p9-v2-training-{authority['identity']}"
        environment.update({"P9_V2_TRAINING_AUTHORITY": str(authority_path),
                            "P9_V2_TRAINING_CONTRACT": str(contract_path)})
        log_path = config_root / "targets.log"
        _status(paths, stage="TARGET_RUNNING", authority_id=authority["identity"], target_store=str(store),
                configuration_log=str(log_path))
        print(f"CONFIG_TARGET_STARTED {configuration_id} {authority['identity']}", flush=True)
        expression = "targets::tar_make(script='_targets_p9_v2_training.R', " + f"store={json.dumps(str(store))}, reporter='timestamp')"
        with log_path.open("ab", buffering=0) as stream:
            result = subprocess.run(["Rscript", "-e", expression], cwd=paths.repository, env=environment,
                                    stdout=stream, stderr=subprocess.STDOUT)
        if result.returncode != 0:
            _status(paths, status="BLOCKED", stage="TARGET_FAILED", returncode=result.returncode)
            raise SelectedFMCampaignError(f"CONFIGURATION_FAILED:{configuration_id}")
        lifecycle = Path(contract["roots"]["lifecycle_records"]) / authority["identity"]
        eligibility_record = json.loads((lifecycle / "eligibility.json").read_text(encoding="utf-8"))
        resolution = json.loads((lifecycle / "resolution.json").read_text(encoding="utf-8"))
        eligibility = Path(eligibility_record["eligibility_path"])
        item = {
            "configuration_id": configuration_id, "authority_id": authority["identity"],
            "authority_path": str(authority_path), "acceptance_id": eligibility_record["acceptance_id"],
            "eligibility_id": eligibility_record["eligibility_id"], "checkpoint_id": resolution["checkpoint_id"],
            "bundle_record": str(lifecycle / "bundle.json"), "evaluation_consumption_count": 0,
        }
        completed.append(item)
        _status(paths, completed=completed, current_configuration=None, stage="CONFIGURATION_COMPLETE",
                latest_eligibility=str(eligibility))
        print(f"CONFIG_COMPLETE {configuration_id} {item['acceptance_id']}", flush=True)
    decision, p9b = _publish_decision(paths, contract, completed, eligibility)
    _status(paths, status="COMPLETE", stage="COMPARISON_COMPLETE", current_configuration=None,
            selected_fm_decision=str(decision), p9_b_plan=str(p9b), latest_eligibility=str(eligibility))


def execute(paths: SelectedFMCampaignPaths) -> None:
    with CampaignLock(paths.root / "campaign.lock"):
        try:
            run_campaign(paths)
        except BaseException as error:
            if paths.status.exists():
                _status(paths, status="BLOCKED", error_type=type(error).__name__, error=str(error))
            raise
