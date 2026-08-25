#!/usr/bin/env python3
"""Validate a completed I21 run and publish acceptance without training."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, Iterable

import torch
import yaml

from prototype_dataloader import canonical_json_bytes, sha256_file
from prototype_training_runtime import (
    CANONICAL_OUTPUTS, atomic_publish, scientific_parent_hashes,
    select_resume_checkpoint, validate_acceptance_manifest, validate_output_records,
)
from prototype_validation import NEW_METRIC_KEYS, NEW_SELECTION_RULE, select_best as select_validation_best


def training_contract_sha256(training: dict[str, Any]) -> str:
    scientific_training = copy.deepcopy(training)
    scientific_training["execution"].pop("archive_source_root", None)
    scientific_training["execution"].pop("archive_runtime_root", None)
    scientific_training["execution"].pop("profiler", None)
    return hashlib.sha256(canonical_json_bytes(scientific_training)).hexdigest()


OUTPUT_ROLES = tuple(CANONICAL_OUTPUTS.values())
REQUIRED_CHECKPOINT_KEYS = {
    "online_model", "target_model", "projection_and_decoders", "optimizer", "scheduler",
    "ema_update_count", "queue_values", "queue_scene_ids", "queue_scene_centers",
    "queue_pointer", "queue_occupancy", "distributed_rank_states",
    "best_checkpoint_metric_state", "validation_history", "early_stopping_patience_state",
    "optimizer_step", "scene_consumptions", "scientific_parents", "run_id", "seed",
    "schema_version", "world_size",
}
REQUIRED_RANK_STATE_KEYS = {
    "rank", "python_rng", "numpy_rng", "torch_cpu_rng", "torch_cuda_rng",
    "sampler_epoch", "sampler_permutation", "sampler_position",
    "accumulation_scene_count", "accumulation_gradient_state",
}


def json_file(path: Path) -> Any:
    return json.loads(path.read_text())


def file_record(path: Path, role: str | None = None) -> dict[str, Any]:
    value = {"path": str(path.resolve()), "size_bytes": path.stat().st_size, "sha256": sha256_file(path)}
    if role is not None:
        value["role"] = role
    return value


def publish_preserved_terminal_stage(
    run: dict[str, Any], config: dict[str, Any], schema: dict[str, Any], final_checkpoint: Path
) -> dict[str, Any]:
    """Publish a preserved direct-publisher stage without invoking training or CUDA."""
    acceptance_root = Path(run["output_root"]).resolve() / "acceptance"
    parents = scientific_parent_hashes(run)
    candidates = []
    for candidate_path in sorted(acceptance_root.glob(".*.stage-*/manifest-candidate.json")):
        manifest = json_file(candidate_path)
        if manifest.get("run_id") != run["run_id"] or manifest.get("plan_id") != run["plan_id"]:
            continue
        if manifest.get("final_checkpoint", {}).get("sha256") != sha256_file(final_checkpoint):
            continue
        validate_acceptance_manifest(manifest, schema, run, parents)
        validate_output_records(manifest["outputs"], candidate_path.parent)
        candidates.append((candidate_path, manifest))
    if len(candidates) != 1:
        raise RuntimeError(f"expected one preserved terminal publication stage, found {len(candidates)}")
    candidate_path, manifest = candidates[0]
    manifest_name = config["output"]["manifest_name"]
    final = acceptance_root / manifest["training_acceptance_id"]
    stage = Path(tempfile.mkdtemp(prefix=f".{manifest['training_acceptance_id']}.recovery-stage-", dir=acceptance_root))
    for name in CANONICAL_OUTPUTS: shutil.copy2(candidate_path.parent/name,stage/name)
    manifest_path = stage / manifest_name
    manifest_path.write_bytes(canonical_json_bytes(manifest))
    names = (*CANONICAL_OUTPUTS, manifest_name)
    status = atomic_publish(stage, final, names)
    return {"status": "PASS", "publish_status": status, "training_acceptance_id": manifest["training_acceptance_id"],
            "additional_optimizer_steps": 0, "cuda_operations": 0,
            "output_files": [str(final / name) for name in names]}


def finite_tensors(value: Any) -> bool:
    if isinstance(value, torch.Tensor):
        return not (value.is_floating_point() or value.is_complex()) or bool(torch.isfinite(value).all())
    if isinstance(value, dict):
        return all(finite_tensors(child) for child in value.values())
    if isinstance(value, (list, tuple)):
        return all(finite_tensors(child) for child in value)
    return True


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def select_best(history: list[dict[str, Any]], validation: dict[str, Any] | None = None) -> dict[str, Any]:
    selected = select_validation_best(history, validation)
    if selected is None:
        raise ValueError("validation history is empty")
    return selected


def checkpoint_record(path: Path, state: dict[str, Any]) -> dict[str, Any]:
    return {
        **file_record(path),
        "optimizer_step": int(state["optimizer_step"]),
        "scene_consumptions": int(state["scene_consumptions"]),
        "validation_count": len(state["validation_history"]),
    }


def audit_checkpoint(path: Path, run: dict[str, Any], parents: dict[str, str]) -> dict[str, Any]:
    state = torch.load(path, map_location="cpu", weights_only=False)
    missing = REQUIRED_CHECKPOINT_KEYS.difference(state)
    if missing:
        raise ValueError(f"checkpoint missing state: {path.name}: {sorted(missing)}")
    if state["run_id"] != run["run_id"] or int(state["seed"]) != int(run["seed"]):
        raise ValueError(f"foreign checkpoint lineage: {path.name}")
    if state["scientific_parents"] != parents or state["world_size"] != 2:
        raise ValueError(f"checkpoint parent/world mismatch: {path.name}")
    if run.get("validation", {}).get("checkpoint_selection") == NEW_SELECTION_RULE and "early_stopping_metric_state" not in state:
        raise ValueError(f"checkpoint missing new validation resume state: {path.name}")
    if not finite_tensors(state):
        raise ValueError(f"non-finite checkpoint tensor: {path.name}")
    rank_states = state["distributed_rank_states"]
    if len(rank_states) != 2 or [value.get("rank") for value in rank_states] != [0, 1]:
        raise ValueError(f"checkpoint rank-state mismatch: {path.name}")
    if any(REQUIRED_RANK_STATE_KEYS.difference(value) for value in rank_states):
        raise ValueError(f"checkpoint incomplete rank state: {path.name}")
    return state


def validate_post_termination_evidence(
    acceptance_id: str, post_termination_paths: list[Path], interrupted_steps: list[Path],
    interrupted_telemetry: list[Path], accepted_steps: list[dict[str, Any]],
) -> Path | None:
    """Distinguish preserved legacy overrun evidence from a clean terminal run."""
    if acceptance_id == "pta_d97bcaf3178d05690600cd31":
        if [path.name for path in post_termination_paths] != ["epoch-060.pt", "epoch-065.pt"]:
            raise ValueError("I21 post-termination checkpoint evidence differs from epochs 60/65")
        post_termination_ledgers = []
        for path in interrupted_steps:
            rows = read_jsonl(path)
            if (
                len(rows) == 520
                and rows[:440] == accepted_steps
                and [int(row["optimizer_step"]) for row in rows[440:]] == list(range(441, 521))
            ):
                post_termination_ledgers.append(path)
        if len(post_termination_ledgers) != 1:
            raise ValueError("expected exactly one preserved 80-step post-termination ledger")
        return post_termination_ledgers[0]
    if post_termination_paths or interrupted_steps or interrupted_telemetry:
        raise ValueError("clean I21 acceptance contains post-termination evidence")
    return None


def immutable_snapshot(paths: Iterable[Path]) -> dict[str, dict[str, Any]]:
    return {str(path.resolve()): file_record(path) for path in sorted(paths, key=lambda value: str(value))}


def audit_existing_accepted_bundle(
    run: dict[str, Any], config: dict[str, Any], schema: dict[str, Any], bundle: Path,
    training_implementation: Path, accepted_training_implementation_sha256: str,
    current_runtime_implementation_sha256: str,
) -> dict[str, Any]:
    """Audit and return an existing terminal acceptance without publishing or training."""
    run_root = Path(run["output_root"]).resolve()
    bundle = bundle.resolve()
    if bundle.parent != run_root / "acceptance":
        raise ValueError("accepted bundle is outside the approved run acceptance root")
    expected_names = {
        config["output"]["qc_name"], config["output"]["validation_name"],
        config["output"]["manifest_name"],
    }
    actual_names = {path.name for path in bundle.iterdir() if path.is_file()}
    if actual_names != expected_names:
        raise ValueError(f"accepted bundle file-set mismatch: {sorted(actual_names)}")

    mutable = run_root / "mutable-ddp"
    checkpoints_root = mutable / "checkpoints"
    epoch_paths = sorted(checkpoints_root.glob("epoch-*.pt"))
    control_paths = [checkpoints_root / "initial-step-000000.pt", checkpoints_root / "controlled-step-000001.pt"]
    step_path = mutable / config["output"]["steps_name"]
    telemetry_path = mutable / config["output"]["telemetry_name"]
    interrupted_steps = sorted(mutable.glob(f"{config['output']['steps_name']}.interrupted-*"))
    interrupted_telemetry = sorted(mutable.glob(f"{config['output']['telemetry_name']}.interrupted-*"))
    evidence_paths = [*bundle.iterdir(), *control_paths, *epoch_paths, step_path, telemetry_path,
                      *interrupted_steps, *interrupted_telemetry]
    if any(not path.is_file() for path in evidence_paths):
        raise ValueError("I21 immutable evidence set contains a missing/non-file path")
    before = immutable_snapshot(evidence_paths)

    manifest_path = bundle / config["output"]["manifest_name"]
    manifest = json_file(manifest_path)
    parents = scientific_parent_hashes(run)
    validate_acceptance_manifest(manifest, schema, run, parents)
    validate_output_records(manifest["outputs"], bundle)
    scientific = manifest["scientific_identity"]
    if scientific["run_spec_sha256"] != sha256_file(Path(run["_run_spec_path"])):
        raise ValueError("accepted run-spec checksum differs from current I20 plan")
    if scientific["training_contract_sha256"] != training_contract_sha256(config):
        raise ValueError("accepted training scientific contract differs from current contract")
    if scientific["training_implementation_sha256"] != accepted_training_implementation_sha256:
        raise ValueError("accepted logical training implementation hash is unexpected")
    current_hash = sha256_file(training_implementation)
    if current_hash != current_runtime_implementation_sha256:
        raise ValueError("current runtime-only training implementation hash is unexpected")
    expected_acceptance = "pta_" + hashlib.sha256(canonical_json_bytes(scientific)).hexdigest()[:24]
    if manifest["training_acceptance_id"] != expected_acceptance or bundle.name != expected_acceptance:
        raise ValueError("accepted bundle ID does not match its scientific identity")

    steps = read_jsonl(step_path)
    if [int(row["optimizer_step"]) for row in steps] != list(range(1, 441)):
        raise ValueError("accepted optimizer ledger is not exactly steps 1-440")
    selection = select_resume_checkpoint(epoch_paths, run, parents, step_path)
    if selection is None or not selection.decision.terminal:
        raise ValueError("I21 checkpoint set has no terminal selection")
    if (selection.path.name, selection.decision.completed_epoch, selection.decision.optimizer_step,
        selection.decision.reason) != ("epoch-055.pt", 55, 440, "early_stopping"):
        raise ValueError("I21 terminal checkpoint selection differs from accepted epoch 55/step 440")
    post_termination_ledger = validate_post_termination_evidence(
        manifest["training_acceptance_id"], selection.post_termination_paths,
        interrupted_steps, interrupted_telemetry, steps,
    )

    final_state = audit_checkpoint(selection.path, run, parents)
    history = list(final_state["validation_history"])
    best = select_best(history, run.get("validation"))
    if int(best["epoch"]) != 5:
        raise ValueError("I21 best-checkpoint replay no longer selects epoch 5")
    best_path = checkpoints_root / "epoch-005.pt"
    audit_checkpoint(best_path, run, parents)
    for key, path, epoch, step in (("best_checkpoint", best_path, 5, 40),
                                   ("final_checkpoint", selection.path, 55, 440)):
        record = manifest[key]
        if (record["sha256"], int(record["size_bytes"]), int(record["epoch"]),
            int(record["optimizer_step"])) != (sha256_file(path), path.stat().st_size, epoch, step):
            raise ValueError(f"accepted {key} record mismatch")
    if manifest["completion"] != {"epochs_completed": 55, "optimizer_steps": 440,
                                   "training_scene_consumptions": 14080, "termination": "early_stopping"}:
        raise ValueError("accepted I21 completion record changed")
    if json_file(bundle / config["output"]["validation_name"]) != history:
        raise ValueError("accepted validation history differs from terminal checkpoint")

    after = immutable_snapshot(evidence_paths)
    if before != after:
        raise RuntimeError("I21 immutable evidence changed during read-only graph recovery")
    return {
        "status": "PASS", "mode": "existing_terminal_bundle_read_only",
        "training_acceptance_id": manifest["training_acceptance_id"],
        "terminal_epoch": 55, "terminal_optimizer_step": 440, "best_epoch": 5,
        "accepted_ledger_rows": 440,
        "post_termination_checkpoints": [str(path) for path in selection.post_termination_paths],
        "post_termination_ledger": str(post_termination_ledger) if post_termination_ledger else None,
        "formal_training_process_count": 0, "cuda_operation_count": 0,
        "optimizer_step_count": 0, "dataloader_worker_spawn_count": 0,
        "new_checkpoint_count": 0, "ledger_append_count": 0,
        "publication_count": 0, "artifact_mutation_count": 0,
        "scientific_implementation_sha256": accepted_training_implementation_sha256,
        "runtime_implementation_sha256": current_runtime_implementation_sha256,
        "output_files": [str(bundle / name) for name in (
            config["output"]["qc_name"], config["output"]["validation_name"],
            config["output"]["manifest_name"],
        )],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    for name in ("run-spec", "training-config", "schema", "training-implementation", "recovery-implementation"):
        parser.add_argument(f"--{name}", required=True, type=Path)
    parser.add_argument("--completed-artifact", action="append", type=Path)
    parser.add_argument("--accepted-bundle", type=Path)
    parser.add_argument("--accepted-training-implementation-sha256")
    parser.add_argument("--current-runtime-implementation-sha256")
    args = parser.parse_args()
    run = json_file(args.run_spec); config = yaml.safe_load(args.training_config.read_text()); schema = json_file(args.schema)
    run["_run_spec_path"] = str(args.run_spec.resolve())
    if run["plan_id"] != config["identity"]["plan_id"] or run["run_id"] != config["identity"]["run_id"]:
        raise ValueError("completed run does not match current I20 plan/run")
    if args.accepted_bundle is not None:
        if args.completed_artifact:
            raise ValueError("read-only accepted-bundle audit does not accept completed-artifact inputs")
        if not args.accepted_training_implementation_sha256 or not args.current_runtime_implementation_sha256:
            raise ValueError("read-only accepted-bundle audit requires both implementation hashes")
        result = audit_existing_accepted_bundle(
            run, config, schema, args.accepted_bundle, args.training_implementation,
            args.accepted_training_implementation_sha256, args.current_runtime_implementation_sha256,
        )
        print(json.dumps(result, sort_keys=True))
        return 0
    if not args.completed_artifact:
        raise ValueError("publication recovery requires completed-artifact inputs")
    by_name: dict[str, Path] = {}
    for path in (value.resolve() for value in args.completed_artifact):
        if path.name in by_name: raise ValueError(f"duplicate completed artifact basename: {path.name}")
        by_name[path.name] = path
    run_root = Path(run["output_root"]).resolve(); mutable = run_root / "mutable-ddp"; checkpoints_root = mutable / "checkpoints"
    required_base = {config["output"]["steps_name"], config["output"]["telemetry_name"], config["output"]["qc_name"],
                     "initial-step-000000.pt", "controlled-step-000001.pt"}
    checkpoint_names = sorted(name for name in by_name if re.fullmatch(r"epoch-\d+\.pt", name))
    if not checkpoint_names or not required_base.issubset(by_name):
        raise ValueError(f"completed artifact set missing runtime evidence: {sorted(required_base-set(by_name))}")
    allowed = required_base | set(checkpoint_names)
    if set(by_name) != allowed: raise ValueError(f"foreign completed artifacts: {sorted(set(by_name)-allowed)}")
    if any(by_name[name].parent != checkpoints_root for name in checkpoint_names + ["initial-step-000000.pt", "controlled-step-000001.pt"]):
        raise ValueError("checkpoint outside approved run directory")
    if by_name[config["output"]["steps_name"]].parent != mutable: raise ValueError("step ledger outside approved run directory")
    before = {name: file_record(path) for name, path in sorted(by_name.items())}; parents = scientific_parent_hashes(run)
    for record in run.values():
        if isinstance(record, dict) and {"path", "size_bytes", "sha256"}.issubset(record):
            path = Path(record["path"])
            if not path.is_file() or path.stat().st_size != int(record["size_bytes"]) or sha256_file(path) != record["sha256"]:
                raise ValueError(f"I20 forwarded artifact mismatch: {path}")
    steps_path = by_name[config["output"]["steps_name"]]; steps = read_jsonl(steps_path)
    selection = select_resume_checkpoint((by_name[name] for name in checkpoint_names), run, parents, steps_path)
    if selection is None or not selection.decision.terminal: raise ValueError("completed artifact set has no terminal checkpoint")
    final = audit_checkpoint(selection.path, run, parents); final_step = selection.decision.optimizer_step
    if len(steps) != final_step: raise ValueError(f"optimizer ledger/final checkpoint mismatch: {len(steps)} != {final_step}")
    for index, row in enumerate(steps, 1):
        if (int(row["optimizer_step"]), int(row["scenes_consumed"]), int(row["ema_update_count"])) != (index, 32, index):
            raise ValueError(f"optimizer ledger sequence mismatch at step {index}")
        for field in ("total_loss", "scene_loss", "information_preservation_loss", "gradient_norm", "learning_rate"):
            if not isinstance(row[field], (int, float)) or not torch.isfinite(torch.tensor(row[field])):
                raise ValueError(f"non-finite optimizer ledger value at step {index}: {field}")
    history = list(final["validation_history"]); selected = select_best(history, run.get("validation"))
    if int(final["early_stopping_patience_state"]) != selection.decision.patience: raise ValueError("patience state mismatch")
    best_name = f"epoch-{int(selected['epoch']):03d}.pt"
    if best_name not in by_name: raise ValueError(f"best checkpoint missing: {best_name}")
    best_state = audit_checkpoint(by_name[best_name], run, parents)
    best_record = {**checkpoint_record(by_name[best_name], best_state), "epoch": int(selected["epoch"]), "role": "best"}
    final_record = {**checkpoint_record(selection.path, final), "epoch": selection.decision.completed_epoch, "role": "final"}
    pointer = final.get("best_checkpoint_metric_state") or {}
    if int(pointer.get("epoch", -1)) != int(selected["epoch"]): raise ValueError("best-checkpoint selection replay mismatch")
    rank_states = final["distributed_rank_states"]
    if rank_states[0]["sampler_permutation"] != rank_states[1]["sampler_permutation"]: raise ValueError("final rank sampler ordering mismatch")
    diagnostic = json_file(by_name[config["output"]["qc_name"]]); resume = diagnostic.get("exact_resume", {})
    if resume.get("status") != "PASS" or resume.get("direct_state_digest") != resume.get("replay_state_digest"):
        raise ValueError("controlled resume evidence mismatch")
    after = {name: file_record(path) for name, path in sorted(by_name.items())}
    if before != after: raise RuntimeError("completed run artifact changed during recovery audit")
    metric_keys = NEW_METRIC_KEYS if run.get("validation", {}).get("checkpoint_selection") == NEW_SELECTION_RULE else ("MRR","HIT@1","HIT@5","HIT@10")
    reproduction = {"status":"PASS","mode":"terminal_checkpoint_validation_history_replay_cpu_only",
        "best_epoch":int(selected["epoch"]),"metrics":{key:selected[key] for key in metric_keys if key in selected and not key.endswith("digest")},
        "embedding_digest":selected["embedding_digest"],"retrieval_digest":selected["retrieval_digest"]}
    recovery = {"status":"PASS","cuda_operations":0,"forward_backward_operations":0,"additional_optimizer_steps":0,
        "artifacts_unchanged":True,"post_termination_evidence":[str(path) for path in selection.post_termination_paths]}
    resources = {**diagnostic,"recovery_publication":recovery}
    scientific = {"plan_id":run["plan_id"],"run_id":run["run_id"],"parents":parents,
        "run_spec_sha256":sha256_file(args.run_spec),"training_contract_sha256":training_contract_sha256(config),
        "training_implementation_sha256":sha256_file(args.training_implementation),"seed":run["seed"],
        "numerical_policy":"two_process_ddp_float32_no_tf32","world_size":2}
    acceptance = "pta_" + hashlib.sha256(canonical_json_bytes(scientific)).hexdigest()[:24]
    acceptance_root = run_root / "acceptance"; final_dir = acceptance_root / acceptance
    acceptance_root.mkdir(parents=True, exist_ok=True); stage = Path(tempfile.mkdtemp(prefix=f".{acceptance}.stage-", dir=acceptance_root))
    try:
        documents = {config["output"]["qc_name"]:resources, config["output"]["validation_name"]:history}
        for name, value in documents.items(): (stage/name).write_bytes(canonical_json_bytes(value))
        outputs = [{"relative_path":name,"size_bytes":(stage/name).stat().st_size,"sha256":sha256_file(stage/name)} for name in documents]
        completion = {"epochs_completed":selection.decision.completed_epoch,"optimizer_steps":final_step,
            "training_scene_consumptions":int(final["scene_consumptions"]),"termination":selection.decision.reason}
        manifest = {"schema_version":"1.0.0","status":"PASS","training_acceptance_id":acceptance,
            "plan_id":run["plan_id"],"run_id":run["run_id"],"scientific_identity":scientific,"completion":completion,
            "validation_history":history,"best_checkpoint":best_record,"final_checkpoint":final_record,
            "exact_resume":resume,"fresh_process_validation":reproduction,"resources":resources,"outputs":outputs}
        validate_acceptance_manifest(manifest,schema,run,parents); validate_output_records(outputs,stage)
        manifest_name=config["output"]["manifest_name"];(stage/manifest_name).write_bytes(canonical_json_bytes(manifest))
        publish=atomic_publish(stage,final_dir,(*documents,manifest_name))
    except Exception:
        raise
    final_after={name:file_record(path) for name,path in sorted(by_name.items())}
    if before!=final_after:raise RuntimeError("checkpoint or completed-run evidence changed during publication")
    print(json.dumps({"status":"PASS","training_acceptance_id":acceptance,"publish_status":publish,
        "additional_optimizer_steps":0,"cuda_operations":0,"output_files":[str(final_dir/name) for name in (*documents,manifest_name)]},sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
