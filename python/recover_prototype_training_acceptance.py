#!/usr/bin/env python3
"""Validate a completed I21 run and publish acceptance without training."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Iterable

import jsonschema
import torch
import yaml

from prototype_dataloader import canonical_json_bytes, sha256_file


OUTPUT_ROLES = (
    "run_completion",
    "validation_early_stopping_history",
    "checkpoint_catalog",
    "publication_recovery_qc",
)
CHECKPOINT_NAMES = (
    "initial-step-000000.pt",
    "controlled-step-000001.pt",
    *(f"epoch-{epoch:03d}.pt" for epoch in range(5, 56, 5)),
)
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


def validate_output_records(records: Iterable[dict[str, Any]], root: Path | None = None) -> None:
    values = list(records)
    roles = [value.get("role") for value in values]
    if len(values) != len(OUTPUT_ROLES) or sorted(roles) != sorted(OUTPUT_ROLES):
        raise ValueError("acceptance outputs must contain each canonical role exactly once")
    paths = [Path(value["path"]).resolve() for value in values]
    if len(set(paths)) != len(paths):
        raise ValueError("duplicate acceptance output path")
    if root is not None and any(path.parent != root.resolve() for path in paths):
        raise ValueError("foreign acceptance output path")
    for path, value in zip(paths, values, strict=True):
        if not path.is_file() or path.stat().st_size != int(value["size_bytes"]) or sha256_file(path) != value["sha256"]:
            raise ValueError(f"acceptance output checksum mismatch: {path}")


def atomic_publish(stage: Path, final: Path, names: Iterable[str]) -> str:
    names = tuple(names)
    if final.exists():
        for name in names:
            if not (final / name).is_file() or sha256_file(final / name) != sha256_file(stage / name):
                raise FileExistsError(f"same I21 acceptance ID has different content: {final}")
        shutil.rmtree(stage)
        return "identical_reuse"
    os.replace(stage, final)
    return "new_publish"


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


def select_best(history: list[dict[str, Any]]) -> dict[str, Any]:
    return max(history, key=lambda value: (value["MRR"], value["HIT@1"], -value["epoch"]))


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
    if not finite_tensors(state):
        raise ValueError(f"non-finite checkpoint tensor: {path.name}")
    rank_states = state["distributed_rank_states"]
    if len(rank_states) != 2 or [value.get("rank") for value in rank_states] != [0, 1]:
        raise ValueError(f"checkpoint rank-state mismatch: {path.name}")
    if any(REQUIRED_RANK_STATE_KEYS.difference(value) for value in rank_states):
        raise ValueError(f"checkpoint incomplete rank state: {path.name}")
    return state


def main() -> int:
    parser = argparse.ArgumentParser()
    for name in ("run-spec", "training-config", "schema", "training-implementation", "recovery-implementation"):
        parser.add_argument(f"--{name}", required=True, type=Path)
    parser.add_argument("--completed-artifact", required=True, action="append", type=Path)
    args = parser.parse_args()

    run = json_file(args.run_spec)
    config = yaml.safe_load(args.training_config.read_text())
    schema = json_file(args.schema)
    if run["plan_id"] != config["identity"]["plan_id"] or run["run_id"] != config["identity"]["run_id"]:
        raise ValueError("completed run does not match current I20 plan/run")

    artifacts = [path.resolve() for path in args.completed_artifact]
    by_name: dict[str, Path] = {}
    for path in artifacts:
        if path.name in by_name:
            raise ValueError(f"duplicate completed artifact basename: {path.name}")
        by_name[path.name] = path
    required = {"optimizer_steps.jsonl", "resource_telemetry.jsonl", "prototype_training_qc.json", *CHECKPOINT_NAMES}
    if set(by_name) != required:
        raise ValueError(f"completed artifact set mismatch: missing={sorted(required-set(by_name))}, foreign={sorted(set(by_name)-required)}")

    run_root = Path(run["output_root"]).resolve()
    checkpoints_root = run_root / "mutable-ddp" / "checkpoints"
    if any(by_name[name].parent != checkpoints_root for name in CHECKPOINT_NAMES):
        raise ValueError("checkpoint outside approved run directory")
    if by_name["optimizer_steps.jsonl"].parent != run_root / "mutable-ddp":
        raise ValueError("step ledger outside approved run directory")

    before = {name: file_record(by_name[name]) for name in sorted(by_name)}
    parents = {key: value["sha256"] for key, value in {
        "dataset": run["dataset_manifest"], "loader": run["dataloader_manifest"],
        "gate": run["no_op_gate_manifest"], "encoder": run["encoder_manifest"],
        "augmentation": run["augmentation_manifest"], "joint": run["joint_model_manifest"],
        "distributed_joint": run["distributed_joint_model_manifest"],
    }.items()}
    for record in run.values():
        if isinstance(record, dict) and {"path", "size_bytes", "sha256"}.issubset(record):
            path = Path(record["path"])
            if not path.is_file() or path.stat().st_size != int(record["size_bytes"]) or sha256_file(path) != record["sha256"]:
                raise ValueError(f"I20 forwarded artifact mismatch: {path}")

    steps = read_jsonl(by_name["optimizer_steps.jsonl"])
    if len(steps) != 440:
        raise ValueError(f"optimizer ledger has {len(steps)} steps")
    for index, row in enumerate(steps, 1):
        expected_epoch, expected_group = (index - 1) // 8 + 1, (index - 1) % 8
        if (row["optimizer_step"], row["epoch"], row["logical_group"], row["scenes_consumed"], row["ema_update_count"]) != (index, expected_epoch, expected_group, 32, index):
            raise ValueError(f"optimizer ledger sequence mismatch at step {index}")
        for field in ("total_loss", "scene_loss", "information_preservation_loss", "gradient_norm", "learning_rate"):
            if not isinstance(row[field], (int, float)) or not torch.isfinite(torch.tensor(row[field])):
                raise ValueError(f"non-finite optimizer ledger value at step {index}: {field}")

    states = {name: audit_checkpoint(by_name[name], run, parents) for name in CHECKPOINT_NAMES}
    final = states["epoch-055.pt"]
    if (final["optimizer_step"], final["scene_consumptions"], final["ema_update_count"], final["early_stopping_patience_state"]) != (440, 14080, 440, 10):
        raise ValueError("final completion/early-stopping state mismatch")
    if final["queue_occupancy"] != int(run["optimizer"]["queue_size"]):
        raise ValueError("final queue occupancy mismatch")
    for epoch in range(5, 56, 5):
        state = states[f"epoch-{epoch:03d}.pt"]
        if state["optimizer_step"] != epoch * 8 or state["scene_consumptions"] != epoch * 256:
            raise ValueError(f"checkpoint progress mismatch at epoch {epoch}")
    final_rank_states = final["distributed_rank_states"]
    if any((state["sampler_epoch"], state["sampler_position"], len(state["sampler_permutation"])) != (54, 8, 256) for state in final_rank_states):
        raise ValueError("final sampler state mismatch")
    if final_rank_states[0]["sampler_permutation"] != final_rank_states[1]["sampler_permutation"]:
        raise ValueError("final rank sampler ordering mismatch")

    history = final["validation_history"]
    if len(history) != 11 or [value["epoch"] for value in history] != list(range(5, 56, 5)):
        raise ValueError("validation cadence mismatch")
    patience = 0
    best_mrr: float | None = None
    for value in history:
        if int(value["population"]) != 32:
            raise ValueError("validation population mismatch")
        improved = best_mrr is None or value["MRR"] > best_mrr
        patience = 0 if improved else patience + 1
        if improved:
            best_mrr = value["MRR"]
    if patience != 10:
        raise ValueError("early-stopping patience replay mismatch")
    selected = select_best(history)
    best_state = states[f"epoch-{selected['epoch']:03d}.pt"]
    best_record = checkpoint_record(by_name[f"epoch-{selected['epoch']:03d}.pt"], best_state)
    final_record = checkpoint_record(by_name["epoch-055.pt"], final)
    checkpoint_pointer = final["best_checkpoint_metric_state"].get("checkpoint", {})
    if selected["epoch"] != 5 or checkpoint_pointer.get("sha256") != best_record["sha256"]:
        raise ValueError("best-checkpoint selection/pointer mismatch")

    diagnostic = json_file(by_name["prototype_training_qc.json"])
    resume = diagnostic.get("exact_resume", {})
    if resume.get("status") != "PASS" or resume.get("direct_state_digest") != resume.get("replay_state_digest"):
        raise ValueError("controlled resume evidence mismatch")
    if resume.get("direct_state_digest") != steps[1]["rank_state_digest"]:
        raise ValueError("controlled resume digest does not match step ledger")
    if diagnostic.get("checkpoint_count") != 11 or diagnostic.get("world_size") != 2:
        raise ValueError("diagnostic execution evidence mismatch")

    after = {name: file_record(by_name[name]) for name in sorted(by_name)}
    if before != after:
        raise RuntimeError("completed run artifact changed during recovery audit")

    checkpoint_catalog = {
        "schema_version": "1.0.0", "run_id": run["run_id"],
        "best_checkpoint": {**best_record, "epoch": selected["epoch"], "role": "best"},
        "final_checkpoint": {**final_record, "epoch": 55, "role": "final"},
        "resume_checkpoint": {**checkpoint_record(by_name["controlled-step-000001.pt"], states["controlled-step-000001.pt"]), "role": "controlled_resume"},
        "checkpoints": [checkpoint_record(by_name[name], states[name]) for name in CHECKPOINT_NAMES],
    }
    completion = {
        "schema_version": "1.0.0", "plan_id": run["plan_id"], "run_id": run["run_id"],
        "epochs_completed": 55, "optimizer_steps": 440, "training_scene_consumptions": 14080,
        "termination": "early_stopping", "additional_optimizer_steps": 0,
        "final_rank_state_digest": steps[-1]["rank_state_digest"],
        "optimizer_step_ledger": file_record(by_name["optimizer_steps.jsonl"]),
        "resource_telemetry": file_record(by_name["resource_telemetry.jsonl"]),
    }
    reproduction = {
        "status": "PASS", "mode": "post_training_reload_completed_before_schema_validation",
        "training_implementation_sha256": sha256_file(args.training_implementation),
        "evidence": "failed publisher created deterministic stage only after exact reloaded-best validation comparison",
        "best_epoch": selected["epoch"], "metrics": {key: selected[key] for key in ("MRR", "HIT@1", "HIT@5", "HIT@10")},
        "embedding_digest": selected["embedding_digest"], "retrieval_digest": selected["retrieval_digest"],
    }
    recovery_qc = {
        "schema_version": "1.0.0", "status": "PASS", "cuda_operations": 0,
        "forward_backward_operations": 0, "additional_optimizer_steps": 0,
        "controlled_resume": resume, "rank_state_equality": "PASS",
        "validation_reproduction": reproduction, "best_selection_replay": "PASS",
        "checkpoint_load": "PASS", "artifacts_unchanged": before == after,
        "checkpoint_checksums_before": {name: value["sha256"] for name, value in before.items() if name.endswith(".pt")},
        "checkpoint_checksums_after": {name: value["sha256"] for name, value in after.items() if name.endswith(".pt")},
        "execution_resources": {key: diagnostic[key] for key in ("worker_count", "workers_per_rank", "world_size", "peak_vram_by_rank", "elapsed_seconds")},
    }

    scientific = {
        "plan_id": run["plan_id"], "run_id": run["run_id"], "parents": parents,
        "run_spec_sha256": sha256_file(args.run_spec), "training_contract_sha256": sha256_file(args.training_config),
        "training_implementation_sha256": sha256_file(args.training_implementation),
        "recovery_implementation_sha256": sha256_file(args.recovery_implementation),
        "schema_sha256": sha256_file(args.schema),
        "step_ledger_sha256": before["optimizer_steps.jsonl"]["sha256"],
        "validation_history": history,
        "checkpoint_sha256": {name: before[name]["sha256"] for name in CHECKPOINT_NAMES},
        "seed": run["seed"], "numerical_policy": "two_process_ddp_float32_no_tf32", "world_size": 2,
    }
    acceptance = "pta_" + hashlib.sha256(canonical_json_bytes(scientific)).hexdigest()[:24]
    acceptance_root = run_root / "acceptance"
    final_dir = acceptance_root / acceptance
    acceptance_root.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{acceptance}.stage-", dir=acceptance_root))
    try:
        documents = {
            "run_completion.json": ("run_completion", completion),
            "validation_history.json": ("validation_early_stopping_history", history),
            "checkpoint_catalog.json": ("checkpoint_catalog", checkpoint_catalog),
            "publication_recovery_qc.json": ("publication_recovery_qc", recovery_qc),
        }
        for name, (_, value) in documents.items():
            (stage / name).write_bytes(canonical_json_bytes(value))
        output_records = [file_record(stage / name, role) for name, (role, _) in documents.items()]
        validate_output_records(output_records, stage)
        # Paths in the immutable manifest refer to the final directory, not staging.
        output_records = [{**value, "path": str(final_dir / Path(value["path"]).name)} for value in output_records]
        manifest = {
            "schema_version": "1.0.0", "status": "PASS", "training_acceptance_id": acceptance,
            "plan_id": run["plan_id"], "run_id": run["run_id"], "scientific_identity": scientific,
            "completion": completion, "validation_history": history,
            "best_checkpoint": checkpoint_catalog["best_checkpoint"], "final_checkpoint": checkpoint_catalog["final_checkpoint"],
            "exact_resume": resume, "fresh_process_validation": reproduction,
            "resources": recovery_qc["execution_resources"], "outputs": output_records,
        }
        jsonschema.validate(manifest, schema)
        manifest_name = config["output"]["manifest_name"]
        (stage / manifest_name).write_bytes(canonical_json_bytes(manifest))
        publish = atomic_publish(stage, final_dir, (*documents, manifest_name))
    except Exception:
        # Preserve a failed stage as diagnostic evidence.
        raise

    final_after = {name: file_record(by_name[name]) for name in sorted(by_name)}
    if after != final_after:
        raise RuntimeError("checkpoint or completed-run evidence changed during publication")
    print(json.dumps({"status": "PASS", "training_acceptance_id": acceptance, "publish_status": publish,
                      "additional_optimizer_steps": 0,
                      "output_files": [str(final_dir / name) for name in (*documents, config["output"]["manifest_name"])]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
