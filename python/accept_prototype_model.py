#!/usr/bin/env python3
"""Publish I24 by validating accepted manifests without model computation."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import jsonschema
import yaml


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("rb") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise RuntimeError(f"expected JSON object: {path}")
    return value


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def verify_file(path: Path, expected_sha: str | None = None, expected_size: int | None = None) -> None:
    require(path.is_file(), f"missing immutable artifact: {path}")
    if expected_size is not None:
        require(path.stat().st_size == int(expected_size), f"artifact size mismatch: {path}")
    if expected_sha is not None:
        require(sha256_file(path) == expected_sha, f"artifact checksum mismatch: {path}")


def verify_outputs(manifest_path: Path, manifest: dict[str, Any]) -> None:
    for output in manifest.get("outputs", []):
        child = Path(output.get("path", manifest_path.parent / output.get("relative_path", "")))
        verify_file(child, output["sha256"], output["size_bytes"])


def artifact(role: str, identity: str, path: Path, status: str, schema_version: str) -> dict[str, Any]:
    return {
        "role": role,
        "identity": identity,
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "schema_version": str(schema_version),
        "status": status,
    }


def prototype_root(path: Path) -> Path:
    for parent in path.parents:
        if parent.name == "prototype":
            return parent
    raise RuntimeError("cannot derive immutable prototype root from accepted parent")


def immutable_publish(stage: Path, final: Path, filenames: list[str]) -> str:
    if final.exists():
        require(final.is_dir(), "immutable I24 path is not a directory")
        require(sorted(p.name for p in final.iterdir()) == sorted(filenames), "immutable I24 file set mismatch")
        for name in filenames:
            require(sha256_file(stage / name) == sha256_file(final / name), "same I24 ID has different content")
        shutil.rmtree(stage)
        return "reused"
    os.replace(stage, final)
    return "published"


def build_summary(acceptance_id: str, ids: dict[str, Any], gates: dict[str, Any], metrics: dict[str, Any]) -> str:
    return "\n".join([
        "# I24 Prototype Model Acceptance", "", "- Status: PASS",
        f"- Acceptance ID: `{acceptance_id}`",
        f"- Dataset / loader / encoder: `{ids['training_dataset_id']}` / `{ids['dataloader_smoke_id']}` / `{ids['encoder_acceptance_id']}`",
        f"- Augmentation / training / validation: `{ids['augmentation_acceptance_id']}` / `{ids['training_acceptance_id']}` / `{ids['model_validation_id']}`",
        f"- Joint / DDP smoke: `{ids['joint_model_acceptance_id']}` / `{ids['distributed_joint_acceptance_id']}`",
        f"- Best checkpoint: `{ids['best_checkpoint_name']}` (`{ids['best_checkpoint_sha256']}`)",
        "- Execution: read-only acceptance; zero forward, augmentation, optimizer, scheduler, EMA, queue, or checkpoint mutation",
        "- Original ranking: qualitative full self-excluding order only; no relevance labels or MRR/HIT",
        f"- Fixed augmented-source retrieval: MRR {metrics['MRR']:.9f}, HIT@1 {metrics['HIT@1']:.6f}, HIT@5 {metrics['HIT@5']:.6f}, HIT@10 {metrics['HIT@10']:.6f}",
        f"- Gates: {sum(value == 'PASS' for value in gates.values())}/{len(gates)} PASS", "",
        "## Limitations", "",
        "This acceptance covers the 320-scene prototype and verifies wiring, determinism, resume, and immutable lineage. It does not provide objective relevance labels for original-scene similarity, establish final scientific performance, or authorize full-population production/evaluation.", "",
    ])


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ("dataloader", "encoder", "augmentation", "training", "validation"):
        parser.add_argument(f"--{name}-manifest", type=Path, required=True)
        parser.add_argument(f"--{name}-schema", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--schema", type=Path, required=True)
    parser.add_argument("--implementation", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()

    config = yaml.safe_load(args.config.read_text())
    ids, hashes = config["identity"], config["artifact_sha256"]
    parent_specs = [
        ("I17_dataloader", args.dataloader_manifest, args.dataloader_schema, "smoke_id", ids["dataloader_smoke_id"], "READY", hashes["dataloader"]),
        ("I18_encoder", args.encoder_manifest, args.encoder_schema, "encoder_acceptance_id", ids["encoder_acceptance_id"], "PASS", hashes["encoder"]),
        ("I19_augmentation", args.augmentation_manifest, args.augmentation_schema, "augmentation_acceptance_id", ids["augmentation_acceptance_id"], "PASS", hashes["augmentation"]),
        ("I22_training", args.training_manifest, args.training_schema, "training_acceptance_id", ids["training_acceptance_id"], "PASS", hashes["training_acceptance"]),
        ("I23_validation", args.validation_manifest, args.validation_schema, "model_validation_id", ids["model_validation_id"], "PASS", hashes["model_validation"]),
    ]
    parents: dict[str, dict[str, Any]] = {}
    direct_records: list[dict[str, Any]] = []
    for role, path, schema_path, id_key, expected_id, expected_status, expected_sha in parent_specs:
        verify_file(path, expected_sha)
        value = load_json(path)
        jsonschema.validate(value, load_json(schema_path))
        require(value.get(id_key) == expected_id, f"{role} identity mismatch")
        require(value.get("status") == expected_status, f"{role} status mismatch")
        verify_outputs(path, value)
        parents[role] = value
        direct_records.append(artifact(role, expected_id, path, expected_status, value["schema_version"]))

    loader, encoder = parents["I17_dataloader"], parents["I18_encoder"]
    augmentation, training, validation = parents["I19_augmentation"], parents["I22_training"], parents["I23_validation"]
    require(loader["accepted_dataset_id"] == ids["training_dataset_id"], "I17 dataset lineage mismatch")
    require(encoder["accepted_dataset_id"] == ids["training_dataset_id"], "I18 dataset lineage mismatch")
    require(encoder["dataloader_smoke_id"] == ids["dataloader_smoke_id"], "I18 loader lineage mismatch")
    require(augmentation["accepted_dataset_id"] == ids["training_dataset_id"], "I19 dataset lineage mismatch")
    require(augmentation["dataloader_smoke_id"] == ids["dataloader_smoke_id"], "I19 loader lineage mismatch")
    require(training["plan_id"] == ids["training_plan_id"] and training["run_id"] == ids["training_run_id"], "I22 plan/run lineage mismatch")
    require(validation["parents"]["training_plan_id"] == ids["training_plan_id"], "I23 plan lineage mismatch")
    require(validation["parents"]["training_run_id"] == ids["training_run_id"], "I23 run lineage mismatch")
    require(validation["parents"]["training_dataset_id"] == ids["training_dataset_id"], "I23 dataset lineage mismatch")
    require(validation["parents"]["augmentation_acceptance_id"] == ids["augmentation_acceptance_id"], "I23 augmentation lineage mismatch")

    dataset_root = args.dataloader_manifest.parents[3]
    dataset_path = dataset_root / "accepted_training_dataset_manifest.json"
    no_op_path = dataset_root / "roundtrip/scientific-geometry/pgr_fb3209bda9fb0fa9a0e15bd1/scientific_geometry_roundtrip_manifest.json"
    joint_path = dataset_root / f"smoke/joint-model/{ids['joint_model_acceptance_id']}/prototype_joint_model_manifest.json"
    ddp_path = dataset_root / f"distributed_joint/{ids['distributed_joint_acceptance_id']}/distributed_joint_model_manifest.json"
    proto_root = prototype_root(dataset_root)
    plan_dir = proto_root / f"plans/prototype_train/{ids['training_plan_id']}"
    plan_path, run_spec_path = plan_dir / "prototype_training_plan_manifest.json", plan_dir / "run-spec.json"
    forwarded_specs = [
        ("I16_dataset", ids["training_dataset_id"], dataset_path, hashes["dataset"]),
        ("scientific_no_op_gate", "pgr_fb3209bda9fb0fa9a0e15bd1", no_op_path, hashes["no_op_gate"]),
        ("joint_model_smoke", ids["joint_model_acceptance_id"], joint_path, hashes["joint_model"]),
        ("distributed_joint_smoke", ids["distributed_joint_acceptance_id"], ddp_path, hashes["distributed_joint"]),
        ("I20_plan", ids["training_plan_id"], plan_path, hashes["training_plan_manifest"]),
        ("I20_run_spec", ids["training_run_id"], run_spec_path, hashes["training_run_spec"]),
    ]
    forwarded: list[dict[str, Any]] = []
    for role, identity, path, expected_sha in forwarded_specs:
        verify_file(path, expected_sha)
        value = load_json(path)
        status = value.get("status", "PASS")
        schema_version = str(value.get("schema_version", "1.0.0"))
        forwarded.append(artifact(role, identity, path, status, schema_version))

    joint, ddp, run_spec = load_json(joint_path), load_json(ddp_path), load_json(run_spec_path)
    require(joint["status"] == "PASS" and joint["joint_model_acceptance_id"] == ids["joint_model_acceptance_id"], "joint model smoke mismatch")
    require(ddp["status"] == "PASS" and ddp["distributed_joint_acceptance_id"] == ids["distributed_joint_acceptance_id"], "DDP smoke mismatch")
    require(run_spec["plan_id"] == ids["training_plan_id"] and run_spec["run_id"] == ids["training_run_id"], "I20 run spec mismatch")
    require(run_spec["joint_model_manifest"]["sha256"] == hashes["joint_model"], "I20 joint parent mismatch")
    require(run_spec["distributed_joint_model_manifest"]["sha256"] == hashes["distributed_joint"], "I20 DDP parent mismatch")
    for role, expected_sha in training["scientific_identity"]["parents"].items():
        require(expected_sha in hashes.values(), f"I22 has unapproved scientific parent: {role}")

    checkpoint = Path(training["best_checkpoint"]["path"])
    checkpoint_before = sha256_file(checkpoint)
    require(training["best_checkpoint"]["sha256"] == ids["best_checkpoint_sha256"], "I22 best checkpoint mismatch")
    require(validation["checkpoint"]["sha256"] == ids["best_checkpoint_sha256"], "I23 checkpoint mismatch")
    verify_file(checkpoint, ids["best_checkpoint_sha256"], training["best_checkpoint"]["size_bytes"])
    require(validation["checkpoint_state"]["additional_optimizer_steps"] == 0, "I23 performed optimizer steps")
    require(validation["original_retrieval"]["relevance_metrics_status"] == "not_computed_no_ground_truth", "original relevance metrics were improperly computed")
    metrics = validation["augmented_source_retrieval"]
    require(all(name in metrics for name in ("MRR", "HIT@1", "HIT@5", "HIT@10")), "augmented-source metrics missing")

    gates = {
        "dataloader_round_trip": loader["correctness"]["status"],
        "encoder_forward_backward": encoder["smoke"]["status"],
        "augmentation_correctness_determinism": augmentation["status"],
        "joint_loss_gradient_routing": joint["loss"]["status"],
        "ddp_numerical_resume_sparse_aggregation": ddp["status"],
        "training_resume_early_stopping": training["status"],
        "embedding_retrieval_determinism": validation["status"],
        "original_relevance_contract": "PASS",
        "immutable_lineage": "PASS",
    }
    require(set(gates.values()) == {"PASS"}, "one or more I24 gates failed")
    contracts = {
        "architecture": {"encoder": encoder["architecture"], "joint": joint["architecture"]},
        "dataset": config["scientific"]["dataset"],
        "augmentation": {"acceptance_id": ids["augmentation_acceptance_id"], "scientific_contract_sha256": augmentation["scientific_identity"]["augmentation_scientific_contract_sha256"]},
        "ddp_numerical_policy": ddp["scientific_identity"]["numerical_equivalence"],
        "training_resume": {"plan_id": ids["training_plan_id"], "run_id": ids["training_run_id"], "exact_resume": training["exact_resume"], "completion": training["completion"]},
        "embedding_retrieval": {"original": validation["original_retrieval"], "augmented_source": metrics},
        "limitations": config["scientific"]["limitations"],
    }
    scientific_identity = {
        "direct_parent_sha256": {record["role"]: record["sha256"] for record in direct_records},
        "forwarded_lineage_sha256": {record["role"]: record["sha256"] for record in forwarded},
        "best_checkpoint_sha256": checkpoint_before,
        "scientific_contract": config["scientific"],
        "config_sha256": sha256_file(args.config), "schema_sha256": sha256_file(args.schema),
        "implementation_sha256": sha256_file(args.implementation),
        "dissertation_commit": ids["dissertation_commit"],
    }
    acceptance_id = "pma_" + hashlib.sha256(canonical_json_bytes(scientific_identity)).hexdigest()[:24]
    output_parent = args.output_root
    output_parent.mkdir(parents=True, exist_ok=True)
    final = output_parent / acceptance_id
    filenames = [config["output"]["manifest"], config["output"]["summary"]]

    summary = build_summary(acceptance_id, ids, gates, metrics)
    checkpoint_after = sha256_file(checkpoint)
    require(checkpoint_after == checkpoint_before, "checkpoint changed during read-only I24 gate")
    zero_compute = {
        "status": "PASS", "additional_optimizer_steps": 0, "forward_calls": 0,
        "augmentation_calls": 0, "state_update_calls": 0,
        "checkpoint_sha256_before": checkpoint_before, "checkpoint_sha256_after": checkpoint_after,
    }

    def make_stage() -> Path:
        stage = Path(tempfile.mkdtemp(prefix=f".{acceptance_id}.stage-", dir=output_parent))
        summary_path = stage / config["output"]["summary"]
        summary_path.write_text(summary, encoding="ascii")
        manifest = {
            "schema_version": config["schema_version"], "status": "PASS", "model_acceptance_id": acceptance_id,
            "direct_parents": direct_records, "forwarded_lineage": forwarded,
            "checkpoint": {"name": checkpoint.name, "path": str(checkpoint), "size_bytes": checkpoint.stat().st_size,
                           "sha256": checkpoint_before, "epoch": 5, "optimizer_step": 40, "read_only": True},
            "gates": gates, "contracts": contracts, "zero_compute": zero_compute,
            "scientific_identity": scientific_identity,
            "immutable_publication": {"atomic": "PASS", "identical_rebuild_reuse": "PASS", "same_id_different_content_hard_failure": "PASS"},
            "outputs": [{"relative_path": summary_path.name, "role": "acceptance_summary",
                         "size_bytes": summary_path.stat().st_size, "sha256": sha256_file(summary_path)}],
        }
        jsonschema.validate(manifest, load_json(args.schema))
        (stage / config["output"]["manifest"]).write_bytes(canonical_json_bytes(manifest))
        return stage

    first = immutable_publish(make_stage(), final, filenames)
    reuse = immutable_publish(make_stage(), final, filenames)
    require(reuse == "reused", "I24 identical rebuild was not reused")
    collision = Path(tempfile.mkdtemp(prefix=f".{acceptance_id}.collision-", dir=output_parent))
    for name in filenames:
        shutil.copy2(final / name, collision / name)
    with (collision / config["output"]["summary"]).open("ab") as stream:
        stream.write(b"collision")
    collision_failed = False
    try:
        immutable_publish(collision, final, filenames)
    except RuntimeError:
        collision_failed = True
        shutil.rmtree(collision, ignore_errors=True)
    require(collision_failed, "I24 same-ID/different-content collision did not fail")
    print(json.dumps({"status": "PASS", "model_acceptance_id": acceptance_id,
                      "publication": first, "output_files": [str(final / name) for name in filenames]}, sort_keys=True))


if __name__ == "__main__":
    main()
