"""Fail-stop orchestration for the predeclared sequential P9-A campaign."""

from __future__ import annotations

import fcntl
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml

from p8_experiment_plan import reporting_configuration_id
from p9_infrastructure import configuration_seed
from p9_v2_canonical import canonical_json_bytes, canonical_sha256, sha256_file
from p9_v2_downstream import AcceptedCheckpointResolver, load_acceptance_eligibility
from p9_v2_ledger import fsync_directory, write_all
from p9_v2_training_controller import build_training_authority, validate_training_authority
from p9_v2_training_lifecycle import scientific_configuration_content


CAMPAIGN_CONFIGURATIONS = (
    "cfg_d128", "cfg_k2", "cfg_k4", "cfg_k16", "cfg_intensity_05",
    "cfg_intensity_20", "cfg_ema_990", "cfg_ip_0", "cfg_lr_2",
    "cfg_lr_3", "cfg_lr_10",
)
IMPLEMENTATION_SOURCES = (
    "python/p9_v2_prepared_cache.py", "python/p9_v2_training_worker.py",
    "python/p9_v2_training_controller.py",
    "python/p9_v2_training_lifecycle.py", "python/p9_infrastructure.py",
    "python/p9_model_families.py",
    "config/p7_deterministic_training.yml",
    "config/p6_model_dataloader.yml",
)


class CampaignError(RuntimeError):
    """The sequential campaign cannot safely advance."""


def implementation_hash(repository_root: Path) -> str:
    return canonical_sha256({name: sha256_file(repository_root / name) for name in IMPLEMENTATION_SOURCES})


def campaign_parents(contract: Mapping[str, Any]) -> dict[str, str]:
    keys = (
        "p8_acceptance_id", "p7_runtime_acceptance_id", "p7_acceptance_id",
        "p6_acceptance_id", "p5_validation_acceptance_id", "p4_bank_id",
        "p4_bank_acceptance_id", "p3_cache_acceptance_id", "production_cache_id",
        "production_cache_acceptance_id", "v1_retirement_id",
    )
    parents = {key: contract["parents"][key] for key in keys}
    if "selected_fm_acceptance_id" in contract["parents"]:
        parents["selected_fm_acceptance_id"] = contract["parents"]["selected_fm_acceptance_id"]
    if "full_model_acceptance_id" in contract["parents"]:
        parents["full_model_acceptance_id"] = contract["parents"]["full_model_acceptance_id"]
    parents["methodology_commit"] = contract["source"]["dissertation_commit"]
    return parents


def build_campaign_authority(
    configuration_id: str, row: Mapping[str, Any], contract: Mapping[str, Any],
    repository_root: Path,
) -> dict[str, Any]:
    if configuration_id not in CAMPAIGN_CONFIGURATIONS or row["configuration_id"] != configuration_id:
        raise CampaignError("CAMPAIGN_CONFIGURATION_NOT_AUTHORIZED")
    parents = campaign_parents(contract)
    return build_training_authority(
        configuration_id=configuration_id,
        configuration_hash=canonical_sha256(scientific_configuration_content(row)),
        p8_configuration_hash=row["scientific_hash"],
        scientific_implementation_hash=implementation_hash(repository_root),
        root_seed=configuration_seed(20260828, configuration_id),
        parents=parents,
        parent_hashes={key: canonical_sha256({"identity": value}) for key, value in parents.items()},
    )


def atomic_write(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.incomplete-{os.getpid()}")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o640)
    try:
        write_all(descriptor, raw)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(temporary, path)
    fsync_directory(path.parent)


def publish_authority(authority: Mapping[str, Any], authority_root: Path) -> Path:
    value = dict(authority)
    validate_training_authority(value)
    raw = canonical_json_bytes(value)
    path = authority_root / f"{value['identity']}.json"
    if path.exists():
        if path.read_bytes() != raw:
            raise CampaignError("TRAINING_AUTHORITY_PUBLICATION_COLLISION")
        return path
    atomic_write(path, raw)
    if path.read_bytes() != raw:
        raise CampaignError("TRAINING_AUTHORITY_PUBLICATION_VERIFY_FAILED")
    return path


def campaign_contract(base: Mapping[str, Any], eligibility_path: str | Path) -> dict[str, Any]:
    value = json.loads(json.dumps(base))
    value["roots"]["eligibility_snapshot"] = str(Path(eligibility_path).resolve())
    return value


def campaign_plan(matrix: Mapping[str, Any]) -> list[dict[str, Any]]:
    source = matrix["rows"]
    identifiers = [row["configuration_id"] for row in source]
    if len(source) != 13 or len(set(identifiers)) != 13:
        raise CampaignError("P8_CAMPAIGN_MATRIX_INVALID")
    rows = {row["configuration_id"]: row for row in source}
    if tuple(item for item in CAMPAIGN_CONFIGURATIONS if item in rows) != CAMPAIGN_CONFIGURATIONS:
        raise CampaignError("P8_CAMPAIGN_MATRIX_INCOMPLETE")
    return [rows[configuration_id] for configuration_id in CAMPAIGN_CONFIGURATIONS]


def restore_campaign_progress(
    paths: "CampaignPaths", rows: list[dict[str, Any]], contract: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], Path]:
    """Fail closed while restoring a canonical accepted prefix from campaign status."""
    eligibility = Path(contract["roots"]["eligibility_snapshot"])
    if not paths.status.exists():
        return [], eligibility
    status = json.loads(paths.status.read_text(encoding="utf-8"))
    if status.get("configurations") != list(CAMPAIGN_CONFIGURATIONS):
        raise CampaignError("CAMPAIGN_STATUS_PLAN_MISMATCH")
    completed = status.get("completed")
    if not isinstance(completed, list):
        raise CampaignError("CAMPAIGN_STATUS_COMPLETED_INVALID")
    expected_prefix = [row["configuration_id"] for row in rows[:len(completed)]]
    if [item.get("configuration_id") for item in completed] != expected_prefix:
        raise CampaignError("CAMPAIGN_COMPLETED_PREFIX_INVALID")
    if not completed:
        return [], eligibility
    eligibility = Path(status.get("latest_eligibility", ""))
    if not eligibility.is_file():
        raise CampaignError("CAMPAIGN_LATEST_ELIGIBILITY_MISSING")
    snapshot = load_acceptance_eligibility(eligibility)
    if snapshot["eligibility_id"] != completed[-1].get("eligibility_id"):
        raise CampaignError("CAMPAIGN_LATEST_ELIGIBILITY_ID_MISMATCH")
    canonical = Path(contract["roots"]["canonical_publication"])
    restored: list[dict[str, Any]] = []
    implementation_lineages: list[str] = []
    for row, item in zip(rows, completed, strict=False):
        configuration_id = row["configuration_id"]
        if item.get("evaluation_consumption_count") != 0:
            raise CampaignError("CAMPAIGN_EVALUATION_CONSUMPTION_NONZERO")
        authority_id = item.get("authority_id")
        authority_path = canonical / "authorities" / f"{authority_id}.json"
        if not authority_path.is_file():
            raise CampaignError("CAMPAIGN_AUTHORITY_MISSING")
        authority = json.loads(authority_path.read_text(encoding="utf-8"))
        validate_training_authority(authority)
        scientific = authority["content"]["scientific"]
        if (
            authority["identity"] != authority_id
            or scientific["configuration_id"] != configuration_id
            or scientific["p8_configuration_hash"] != row["scientific_hash"]
            or scientific["configuration_hash"] != canonical_sha256(scientific_configuration_content(row))
        ):
            raise CampaignError("CAMPAIGN_AUTHORITY_CONFIGURATION_MISMATCH")
        implementation_lineages.append(scientific["scientific_implementation_hash"])
        lifecycle = Path(contract["roots"]["lifecycle_records"]) / authority_id
        handoff_path = lifecycle / "eligibility.json"
        resolution_path = lifecycle / "resolution.json"
        if not handoff_path.is_file() or not resolution_path.is_file():
            raise CampaignError("CAMPAIGN_LIFECYCLE_HANDOFF_MISSING")
        handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
        recorded = json.loads(resolution_path.read_text(encoding="utf-8"))
        if (
            handoff.get("acceptance_id") != item.get("acceptance_id")
            or handoff.get("eligibility_id") != item.get("eligibility_id")
            or recorded.get("acceptance_id") != item.get("acceptance_id")
            or recorded.get("checkpoint_id") != item.get("checkpoint_id")
            or recorded.get("evaluation_consumption_count") != 0
        ):
            raise CampaignError("CAMPAIGN_LIFECYCLE_RECORD_MISMATCH")
        resolver = AcceptedCheckpointResolver(
            canonical / "acceptances", canonical / "bundles",
            {handoff["checkpoint_namespace"]: Path(handoff["checkpoint_root"])}, snapshot)
        resolved = resolver.resolve_accepted_checkpoint(item["acceptance_id"])
        if (
            resolved.authority_id != authority_id
            or resolved.authority_hash != authority["content_sha256"]
            or resolved.checkpoint_id != item["checkpoint_id"]
            or resolved.scientific_configuration["identity"] != configuration_id
            or resolved.scientific_configuration["content"] != scientific_configuration_content(row)
        ):
            raise CampaignError("CAMPAIGN_RESOLVER_RESTORATION_MISMATCH")
        restored.append(dict(item))
    transitions = [index for index in range(1, len(implementation_lineages))
                   if implementation_lineages[index] != implementation_lineages[index - 1]]
    expected_transition = CAMPAIGN_CONFIGURATIONS.index("cfg_intensity_05")
    if transitions not in ([], [expected_transition]):
        raise CampaignError("CAMPAIGN_COMPLETED_IMPLEMENTATION_LINEAGE_AMBIGUOUS")
    return restored, eligibility


@dataclass(frozen=True)
class CampaignPaths:
    root: Path
    repository: Path
    base_contract: Path

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
            raise CampaignError("P9_A_CAMPAIGN_ALREADY_RUNNING") from error
        return self

    def __exit__(self, *_: object) -> None:
        assert self.stream is not None
        fcntl.flock(self.stream.fileno(), fcntl.LOCK_UN)
        self.stream.close()


def _status(paths: CampaignPaths, **values: Any) -> None:
    current = {} if not paths.status.exists() else json.loads(paths.status.read_text(encoding="utf-8"))
    current.update(values)
    atomic_write(paths.status, canonical_json_bytes(current))


def run_campaign(paths: CampaignPaths) -> None:
    contract = yaml.safe_load(paths.base_contract.read_text(encoding="utf-8"))
    matrix_path = Path(contract["roots"]["p8_bundle"]) / "hyperparameter_configuration_matrix.json"
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    rows = campaign_plan(matrix)
    canonical_root = Path(contract["roots"]["canonical_publication"])
    completed, eligibility = restore_campaign_progress(paths, rows, contract)
    _status(paths, status="RUNNING", configurations=list(CAMPAIGN_CONFIGURATIONS), completed=completed,
            current_configuration=None, evaluation_consumption_count=0,
            restored_completed_count=len(completed), latest_eligibility=str(eligibility),
            error=None, error_type=None, returncode=None, authority_id=None,
            target_store=None, configuration_log=None)
    for index, row in enumerate(rows[len(completed):], start=len(completed) + 1):
        configuration_id = row["configuration_id"]
        authority = build_campaign_authority(configuration_id, row, contract, paths.repository)
        config_root = paths.root / configuration_id
        candidate = config_root / "authority_candidate.json"
        atomic_write(candidate, canonical_json_bytes(authority))
        dynamic = campaign_contract(contract, eligibility)
        contract_path = config_root / "training_contract.yml"
        atomic_write(contract_path, yaml.safe_dump(dynamic, sort_keys=True).encode("utf-8"))
        _status(paths, current_configuration=configuration_id, current_reporting_id=reporting_configuration_id(configuration_id),
                current_index=index, stage="PREAUTHORITY_PREFLIGHT")
        environment = os.environ.copy()
        environment.update({"PYTHONDONTWRITEBYTECODE": "1", "NCCL_P2P_DISABLE": "1", "NCCL_IB_DISABLE": "1"})
        subprocess.run([
            environment.get("PYTHON", "python"), "scripts/p9_v2_training_controller.py", "preflight",
            "--authority", str(candidate), "--contract", str(contract_path),
        ], cwd=paths.repository, env=environment, check=True, stdout=subprocess.DEVNULL)
        authority_path = publish_authority(authority, canonical_root / "authorities")
        store = paths.root / "target_stores" / f"fuse-p9-v2-training-{authority['identity']}"
        environment.update({
            "P9_V2_TRAINING_AUTHORITY": str(authority_path),
            "P9_V2_TRAINING_CONTRACT": str(contract_path),
        })
        log_path = config_root / "targets.log"
        _status(paths, stage="TARGET_RUNNING", authority_id=authority["identity"], target_store=str(store),
                configuration_log=str(log_path))
        print(f"CONFIG_TARGET_STARTED {configuration_id} {authority['identity']}", flush=True)
        expression = (
            "targets::tar_make(script='_targets_p9_v2_training.R', "
            f"store={json.dumps(str(store))}, reporter='timestamp')"
        )
        with log_path.open("ab", buffering=0) as stream:
            result = subprocess.run(["Rscript", "-e", expression], cwd=paths.repository,
                                    env=environment, stdout=stream, stderr=subprocess.STDOUT)
        if result.returncode != 0:
            _status(paths, status="BLOCKED", stage="TARGET_FAILED", returncode=result.returncode)
            raise CampaignError(f"CONFIGURATION_FAILED:{configuration_id}")
        lifecycle_root = Path(contract["roots"]["lifecycle_records"]) / authority["identity"]
        eligibility_record = json.loads((lifecycle_root / "eligibility.json").read_text(encoding="utf-8"))
        resolution = json.loads((lifecycle_root / "resolution.json").read_text(encoding="utf-8"))
        eligibility = Path(eligibility_record["eligibility_path"])
        item = {
            "configuration_id": configuration_id,
            "reporting_configuration_id": reporting_configuration_id(configuration_id),
            "authority_id": authority["identity"], "acceptance_id": eligibility_record["acceptance_id"],
            "eligibility_id": eligibility_record["eligibility_id"],
            "checkpoint_id": resolution["checkpoint_id"], "evaluation_consumption_count": 0,
        }
        completed.append(item)
        _status(paths, completed=completed, current_configuration=None, stage="CONFIGURATION_COMPLETE",
                latest_eligibility=str(eligibility))
        print(f"CONFIG_COMPLETE {configuration_id} {item['acceptance_id']}", flush=True)
    _status(paths, status="COMPLETE", stage="CAMPAIGN_COMPLETE", current_configuration=None,
            latest_eligibility=str(eligibility))


def execute(paths: CampaignPaths) -> None:
    with CampaignLock(paths.root / "campaign.lock"):
        try:
            run_campaign(paths)
        except BaseException as error:
            if paths.status.exists():
                _status(paths, status="BLOCKED", error_type=type(error).__name__, error=str(error))
            raise
