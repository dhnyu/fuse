#!/usr/bin/env python3
"""Noncanonical two-GPU update/resume/full-lifecycle remediation pilot."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from p9_infrastructure import configuration_seed  # noqa: E402
from p9_v2_canonical import canonical_json_bytes, canonical_sha256, sha256_file  # noqa: E402
from p9_v2_ledger import read_ledger  # noqa: E402
from p9_v2_training_controller import build_training_authority  # noqa: E402
from p9_v2_training_lifecycle import (  # noqa: E402
    publish_native_lifecycle, scientific_configuration_content,
)
from p9_v2_training_worker import scientific_state_digest  # noqa: E402


def _command(authority: Path, matrix: Path, cache: Path, categories: Path, *, stop: bool) -> str:
    values = [sys.executable, "-m", "torch.distributed.run", "--standalone", "--nproc_per_node=2",
              "scripts/p9_v2_training_worker.py", "--authority", str(authority), "--matrix", str(matrix),
              "--configuration-id", "cfg_d48", "--cache-root", str(cache), "--categories", str(categories),
              "--training-config", "config/p7_deterministic_training.yml",
              "--model-config", "config/p6_model_dataloader.yml", "--mode", "bounded-pilot"]
    if stop: values += ["--stop-after-schedule-index", "0"]
    return shlex.join(values)


def _controller(authority: Path, contract: Path, output: Path, worker: str, *, expect_success: bool) -> dict | None:
    command = [sys.executable, "scripts/p9_v2_training_controller.py", "run", "--authority", str(authority),
               "--contract", str(contract), "--output", str(output), "--science-worker-command", worker,
               "--noncanonical-pilot"]
    environment = os.environ.copy(); environment.update({"NCCL_P2P_DISABLE": "1", "NCCL_IB_DISABLE": "1",
                                                          "TORCH_NCCL_BLOCKING_WAIT": "1"})
    result = subprocess.run(command, cwd=ROOT, env=environment, text=True, capture_output=True)
    if expect_success and result.returncode:
        raise RuntimeError(f"controller failed: {result.stdout}\n{result.stderr[-4000:]}")
    if not expect_success and result.returncode == 0:
        raise RuntimeError("interrupt pilot unexpectedly completed")
    if not expect_success: return None
    return json.loads(result.stdout.splitlines()[-1])


def _latest_checkpoint(execution: dict) -> tuple[Path, dict]:
    ledger = read_ledger(execution["ledger_root"])
    event = next(item for item in reversed(ledger.events) if item["event_type"] == "VALIDATION_CHECKPOINT_COMMITTED")
    return Path(execution["checkpoint_root"]) / event["payload"]["checkpoint_id"] / "checkpoint.pt", event


def run(output: str | Path) -> dict:
    output = Path(output).resolve(); temporary = Path(tempfile.gettempdir()).resolve()
    if temporary not in output.parents: raise RuntimeError("pilot output must be under the system temporary root")
    output.mkdir(parents=True, exist_ok=False)
    contract_path = ROOT / "config/p9_v2_training_controller.yml"
    contract = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
    matrix = Path(contract["roots"]["p8_bundle"]) / "hyperparameter_configuration_matrix.json"
    rows = json.loads(matrix.read_text(encoding="utf-8"))["rows"]
    row = next(item for item in rows if item["configuration_id"] == "cfg_d48")
    scientific_hash = canonical_sha256(scientific_configuration_content(row))
    parents = {key: contract["parents"][key] for key in (
        "p8_acceptance_id", "p7_runtime_acceptance_id", "p7_acceptance_id",
        "p6_acceptance_id", "p5_validation_acceptance_id", "p4_bank_id", "p4_bank_acceptance_id",
        "p3_cache_acceptance_id", "production_cache_id", "production_cache_acceptance_id", "v1_retirement_id")}
    parents["methodology_commit"] = contract["source"]["dissertation_commit"]
    implementation_hash = canonical_sha256({name: sha256_file(ROOT / name) for name in (
        "python/p9_v2_training_worker.py", "python/p9_v2_training_controller.py",
        "python/p9_v2_training_lifecycle.py", "config/p7_deterministic_training.yml",
        "config/p6_model_dataloader.yml")})
    authority = build_training_authority(
        configuration_id="cfg_d48", configuration_hash=scientific_hash,
        p8_configuration_hash=row["scientific_hash"], scientific_implementation_hash=implementation_hash,
        root_seed=configuration_seed(20260828, "cfg_d48"), parents=parents,
        parent_hashes={key: canonical_sha256({"identity": value}) for key, value in parents.items()})
    authority_path = output / "noncanonical_pilot_authority.json"
    authority_path.write_bytes(canonical_json_bytes(authority))
    cache = Path(contract["roots"]["production_cache"]); categories = Path(contract["roots"]["categories"])

    uninterrupted_root = output / "uninterrupted"
    uninterrupted = _controller(authority_path, contract_path, uninterrupted_root,
                                _command(authority_path, matrix, cache, categories, stop=False), expect_success=True)
    resumed_root = output / "resumed"
    _controller(authority_path, contract_path, resumed_root,
                _command(authority_path, matrix, cache, categories, stop=True), expect_success=False)
    resumed = _controller(authority_path, contract_path, resumed_root,
                          _command(authority_path, matrix, cache, categories, stop=False), expect_success=True)
    assert uninterrupted is not None and resumed is not None
    uninterrupted_path, uninterrupted_event = _latest_checkpoint(uninterrupted)
    resumed_path, resumed_event = _latest_checkpoint(resumed)
    first = torch.load(uninterrupted_path, map_location="cpu", weights_only=False)
    second = torch.load(resumed_path, map_location="cpu", weights_only=False)
    first_digest, second_digest = scientific_state_digest(first), scientific_state_digest(second)
    if first_digest != second_digest:
        raise RuntimeError("EXACT_RESUME_SCIENTIFIC_STATE_MISMATCH")
    sources = [authority_path, contract_path, matrix,
               contract["roots"]["production_cache_acceptance"],
               ROOT / "python/p9_v2_training_worker.py", ROOT / "python/p9_v2_training_controller.py",
               ROOT / "python/p9_v2_training_lifecycle.py", ROOT / "config/p7_deterministic_training.yml",
               ROOT / "config/p6_model_dataloader.yml"]
    lifecycle = publish_native_lifecycle(
        authority, resumed["ledger_root"], resumed["checkpoint_root"], matrix,
        contract["roots"]["production_cache_acceptance"], output / "noncanonical-publication", sources,
        eligibility_namespace="p9-v2-remediation-pilot")
    diagnostics = sorted((Path(resumed["ledger_root"]).parent / "staging/diagnostics").glob("boundary-*.json"))
    performance = [json.loads(path.read_text(encoding="utf-8")) for path in diagnostics]
    result = {
        "verdict": "PASS", "pilot_kind": "NONCANONICAL_UPDATE_CAPABLE_REMEDIATION",
        "configuration_id": "cfg_d48", "formal_authority_publications": 0,
        "optimizer_updates_uninterrupted": uninterrupted_event["payload"]["optimizer_update"],
        "optimizer_updates_interrupted_resumed": resumed_event["payload"]["optimizer_update"],
        "exact_resume_equivalent": True, "scientific_state_digest": first_digest,
        "bundle_id": lifecycle.bundle_id, "finalization_id": lifecycle.finalization_id,
        "acceptance_id": lifecycle.acceptance_id, "eligibility_id": lifecycle.eligibility_id,
        "resolved_checkpoint_id": lifecycle.checkpoint_id,
        "canonical_cfg_d48_writes": 0, "evaluation_consumption_count": 0,
        "performance": performance,
    }
    (output / "pilot_result.json").write_bytes(canonical_json_bytes(result))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--output", required=True); args = parser.parse_args()
    print(json.dumps(run(args.output), sort_keys=True))


if __name__ == "__main__": main()
