"""GPU smoke for the dissertation joint contrastive/reconstruction model."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

import jsonschema
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import torch
import yaml

from prototype_dataloader import AcceptedPrototypeDataset, canonical_json_bytes, ragged_collate, sha256_file
from prototype_encoder import geometry_fourier_features
from prototype_joint_model import (
    JointPrototypeModel,
    enqueue,
    modality_mask_assignments,
    reconstruction_losses,
    symmetric_infonce_components,
)


def move(value: Any, device: torch.device) -> Any:
    if isinstance(value, torch.Tensor):
        return value.to(device)
    if isinstance(value, dict):
        return {key: move(item, device) for key, item in value.items()}
    return value


def output_record(path: Path, root: Path) -> dict[str, Any]:
    return {"relative_path": path.relative_to(root).as_posix(), "size_bytes": path.stat().st_size, "sha256": sha256_file(path)}


def publish(stage: Path, final: Path, names: list[str]) -> tuple[list[Path], str]:
    if final.exists():
        for name in names:
            existing, candidate = final / name, stage / name
            if not existing.is_file() or sha256_file(existing) != sha256_file(candidate):
                raise FileExistsError(f"same joint-model ID has different content: {final}")
        shutil.rmtree(stage)
        return [final / name for name in names], "identical_reuse"
    os.replace(stage, final)
    return [final / name for name in names], "new_publish"


def parameter_rows(model: JointPrototypeModel) -> list[dict[str, Any]]:
    return [{
        "name": name, "elements": parameter.numel(), "trainable": parameter.requires_grad,
        "gradient_present": parameter.grad is not None,
        "gradient_finite": bool(parameter.grad is not None and torch.isfinite(parameter.grad).all()),
        "gradient_l2": float(parameter.grad.norm().detach().cpu()) if parameter.grad is not None else None,
    } for name, parameter in model.named_parameters()]


def run_smoke(accepted_path: Path, loader_path: Path, encoder_manifest_path: Path,
              augmentation_manifest_path: Path, gate_manifest_path: Path, joint_config_path: Path,
              encoder_config_path: Path, tensor_contract_path: Path, schema_path: Path) -> dict[str, Any]:
    started = time.perf_counter()
    joint = yaml.safe_load(joint_config_path.read_text())
    encoder_config = yaml.safe_load(encoder_config_path.read_text())
    schema = json.loads(schema_path.read_text())
    upstream = {
        "accepted": json.loads(accepted_path.read_text()), "loader": json.loads(loader_path.read_text()),
        "encoder": json.loads(encoder_manifest_path.read_text()), "augmentation": json.loads(augmentation_manifest_path.read_text()),
        "gate": json.loads(gate_manifest_path.read_text()),
    }
    expected = joint["identity"]
    observed = {
        "accepted_dataset_id": upstream["accepted"]["training_dataset_id"],
        "dataloader_smoke_id": upstream["loader"]["smoke_id"],
        "encoder_acceptance_id": upstream["encoder"]["encoder_acceptance_id"],
        "augmentation_acceptance_id": upstream["augmentation"]["augmentation_acceptance_id"],
        "no_op_gate_id": upstream["gate"]["gate_id"],
    }
    if observed != {key: expected[key] for key in observed}:
        raise ValueError(f"joint smoke upstream mismatch: {observed}")
    if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
        raise RuntimeError("joint smoke requires exactly one lock-selected GPU")
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    torch.use_deterministic_algorithms(True)
    seed = int(joint["smoke"]["seed"])
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    device = torch.device("cuda:0")
    torch.cuda.set_device(0)
    torch.cuda.reset_peak_memory_stats()

    dataset = AcceptedPrototypeDataset(accepted_path, tensor_contract_path, split="training", verify_checksums=True)
    rows = sorted(
        ((index, row) for index, row in enumerate(dataset.rows) if int(row["node_count"]) > 0),
        key=lambda item: (int(item[1]["actual_payload_bytes"]), item[1]["scene_id"]),
    )[:32]
    samples = [dataset[index] for index, _ in rows]
    if not any(sample["entities"]["building_missing"].numel() and
               bool((sample["entities"]["building_missing"][:, 1] == 0).any()) for sample in samples):
        selected_ids = {sample["scene_id"] for sample in samples}
        for candidate_index, candidate_row in sorted(enumerate(dataset.rows), key=lambda item: item[1]["scene_id"]):
            if candidate_row["scene_id"] in selected_ids:
                continue
            candidate = dataset[candidate_index]
            if candidate["entities"]["building_missing"].numel() and bool((candidate["entities"]["building_missing"][:, 1] == 0).any()):
                samples[-1] = candidate
                break
    if len(samples) != 32 or len({sample["scene_id"] for sample in samples}) != 32:
        raise ValueError("joint smoke effective batch is not 32 unique training scenes")
    mask_indices = {name: next(iter(values)) for name, values in dataset.category_mask_index.items()}
    microbatches = [samples[index:index + 8] for index in range(0, 32, 8)]
    model = JointPrototypeModel(encoder_config, joint).to(device=device, dtype=torch.float32)
    model.train()

    # IP-only routing is checked independently on one representative microbatch.
    isolation_batch = move(ragged_collate(microbatches[0]), device)
    isolation_batch["category_mask_indices"] = mask_indices
    isolation_geometry = geometry_fourier_features(isolation_batch, encoder_config, device)
    isolation_assignments = modality_mask_assignments(isolation_batch, seed, 0, 0, 0.30)
    isolation = model.forward_online(isolation_batch, isolation_geometry, isolation_assignments)
    isolation_ip = reconstruction_losses(model, isolation_batch, isolation_geometry, isolation.modalities, joint)["information_preservation"]
    isolation_ip.backward()
    allowed_prefixes = (
        "online.position_encoder", "online.magnitude_encoder", "online.phase_encoder", "online.geometry_fusion",
        "online.category_embeddings", "online.building_numerical", "online.building_fusion",
        "online.road_numerical", "online.road_fusion", "online.poi_embeddings", "online.poi_projections",
        "online.poi_score", "online.poi_fusion", "online.object_raster_encoder", "decoders.",
    )
    forbidden_ip = [name for name, parameter in model.named_parameters()
                    if parameter.grad is not None and float(parameter.grad.abs().max().cpu()) > 0 and not name.startswith(allowed_prefixes)]
    if forbidden_ip:
        raise ValueError(f"L_IP gradient escaped pre-fusion encoders/decoders: {forbidden_ip}")
    model.zero_grad(set_to_none=True)

    online_views: list[list[Any]] = [[], []]
    target_keys: list[torch.Tensor] = []
    modality_views: list[list[dict[str, torch.Tensor]]] = [[], []]
    geometry_views: list[tuple[torch.Tensor, torch.Tensor]] = []
    device_batches: list[dict[str, Any]] = []
    for batch_samples in microbatches:
        batch = move(ragged_collate(batch_samples), device)
        batch["category_mask_indices"] = mask_indices
        geometry = geometry_fourier_features(batch, encoder_config, device)
        device_batches.append(batch)
        geometry_views.append(geometry)
        with torch.no_grad():
            target_keys.append(model.forward_target(batch, geometry)["projection"])
        for view in (0, 1):
            assignments = modality_mask_assignments(batch, seed, 0, view, 0.30)
            forward = model.forward_online(batch, geometry, assignments)
            online_views[view].append(forward.outputs["projection"])
            modality_views[view].append(forward.modalities)

    q1, q2 = (torch.cat(values) for values in online_views)
    keys = torch.cat(target_keys)
    centers = torch.tensor([sample["meta"]["center_xy_5186"] for sample in samples], dtype=torch.float32, device=device)
    queue_values = torch.zeros((8192, 128), device=device)
    queue_centers = torch.zeros((8192, 2), device=device)
    components = symmetric_infonce_components(q1, q2, keys, keys, centers, queue_values, queue_centers, 0, 0.1, 750.0)
    scene_loss = components.mean()
    microbatch_scene_loss = sum(components[index:index + 8].sum() for index in range(0, 64, 8)) / 64
    equivalence_error = float((scene_loss - microbatch_scene_loss).abs().detach().cpu())
    if equivalence_error > float(joint["smoke"]["equivalence_atol"]):
        raise ValueError("effective-batch scene-loss microbatch normalization mismatch")

    full_batch = move(ragged_collate(samples), device)
    full_batch["category_mask_indices"] = mask_indices
    full_geometry = tuple(torch.cat([value[index] for value in geometry_views]) for index in (0, 1))
    ip_terms = []
    for view in (0, 1):
        combined = {name: torch.cat([value[name] for value in modality_views[view]]) for name in ("relative", "geometry", "semantic", "environmental")}
        ip_terms.append(reconstruction_losses(model, full_batch, full_geometry, combined, joint))
    global_counts = {name: sum(term["modalities"][name]["local_valid_count"] for term in ip_terms)
                     for name in ("relative", "geometry", "semantic", "environmental")}
    active_modalities = [name for name, count in global_counts.items() if count]
    ip_loss = sum(sum(term["modalities"][name]["loss_sum"] for term in ip_terms) / global_counts[name]
                  for name in active_modalities) / len(active_modalities)
    total_loss = scene_loss + 0.5 * ip_loss
    if not all(torch.isfinite(value) for value in (scene_loss, ip_loss, total_loss)):
        raise ValueError("non-finite joint smoke loss")
    total_loss.backward()
    parameters = parameter_rows(model)
    trainable = [row for row in parameters if row["trainable"]]
    missing = [row["name"] for row in trainable if not row["gradient_present"]]
    invalid = [row["name"] for row in trainable if row["gradient_present"] and not row["gradient_finite"]]
    zero = [row["name"] for row in trainable if row["gradient_present"] and row["gradient_l2"] == 0.0]
    target_gradients = [row["name"] for row in parameters if row["name"].startswith("target.") and row["gradient_present"]]
    if missing or invalid or zero or target_gradients:
        raise ValueError(f"joint gradient coverage failed missing={missing} invalid={invalid} zero={zero} target={target_gradients}")

    online_parameter_count = sum(parameter.numel() for parameter in model.online.parameters())
    decoder_parameter_count = sum(parameter.numel() for parameter in model.decoders.parameters())
    mask_parameter_count = model.modality_mask_embeddings.numel()
    if online_parameter_count != 1996534 or decoder_parameter_count != 668094 or mask_parameter_count != 512:
        raise ValueError("joint-model parameter contract mismatch")

    # EMA and queue behavior are verified without constructing an optimizer or taking a step.
    first_online = next(model.online.parameters())
    first_target = next(model.target.parameters())
    target_before = first_target.detach().clone()
    with torch.no_grad():
        first_online.add_(1.0e-6)
        online_after = first_online.detach().clone()
    model.update_target(0.999)
    ema_expected = target_before.clone().mul_(0.999).add_(online_after, alpha=0.001)
    ema_error = float((first_target - ema_expected).abs().max().cpu())
    queue_scene_ids = torch.full((8192,), -1, dtype=torch.int64, device=device)
    scene_ids_numeric = torch.arange(32, device=device, dtype=torch.int64).repeat_interleave(2)
    queue_insert = torch.stack((keys, keys), dim=1).reshape(64, 128)
    queue_insert_centers = centers.repeat_interleave(2, dim=0)
    pointer, occupancy = enqueue(queue_values, queue_scene_ids, queue_centers, 0, 0, queue_insert, scene_ids_numeric, queue_insert_centers)
    if not torch.equal(first_target, ema_expected) or pointer != 64 or occupancy != 64 or not torch.equal(queue_values[:64], queue_insert):
        raise ValueError(f"EMA/queue update contract mismatch: ema={ema_error} pointer={pointer} occupancy={occupancy}")

    torch.cuda.synchronize()
    elapsed = time.perf_counter() - started
    scientific_identity = {
        **observed,
        "upstream_sha256": {name: sha256_file(path) for name, path in {
            "accepted": accepted_path, "loader": loader_path, "encoder": encoder_manifest_path,
            "augmentation": augmentation_manifest_path, "gate": gate_manifest_path,
        }.items()},
        "joint_config_sha256": sha256_file(joint_config_path),
        "encoder_config_sha256": sha256_file(encoder_config_path),
        "tensor_contract_sha256": sha256_file(tensor_contract_path),
        "implementation_sha256": sha256_file(Path(__file__).with_name("prototype_joint_model.py")),
        "smoke_sha256": sha256_file(Path(__file__)),
        "launcher_sha256": sha256_file(Path(__file__).with_name("run_prototype_joint_model_smoke.py")),
        "dissertation_commit": expected["dissertation_commit"],
    }
    acceptance_id = "pjm_" + hashlib.sha256(canonical_json_bytes(scientific_identity)).hexdigest()[:24]
    final = accepted_path.parent / joint["output"]["subdirectory"] / acceptance_id
    final.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{acceptance_id}.stage-", dir=final.parent))
    names = [joint["output"][key] for key in ("qc", "parameters", "log", "manifest")]
    qc = {
        "status": "PASS", "optimizer_step_performed": False, "logical_scenes": 32, "microbatch_sizes": [8, 8, 8, 8],
        "scene_loss": float(scene_loss.detach().cpu()), "information_preservation_loss": float(ip_loss.detach().cpu()),
        "total_loss": float(total_loss.detach().cpu()), "microbatch_equivalence_error": equivalence_error,
        "ip_forbidden_gradient_tensors": 0, "target_gradient_tensors": 0,
        "missing_gradient_tensors": 0, "zero_gradient_tensors": 0, "invalid_gradient_tensors": 0,
        "ema_max_error": ema_error, "queue_pointer": pointer, "queue_occupancy": occupancy,
    }
    (stage / joint["output"]["qc"]).write_bytes(canonical_json_bytes(qc))
    pq.write_table(pa.Table.from_pylist(parameters), stage / joint["output"]["parameters"], compression="zstd")
    (stage / joint["output"]["log"]).write_bytes(canonical_json_bytes({"event": "joint_model_smoke_complete", **qc}))
    outputs = [output_record(stage / name, stage) for name in names[:-1]]
    manifest = {
        "schema_version": "1.0.0", "status": "PASS", "joint_model_acceptance_id": acceptance_id,
        "scientific_identity": scientific_identity,
        "architecture": {"encoder_parameters": online_parameter_count, "encoder_parameter_tensors": 231,
                         "decoder_parameters": decoder_parameter_count, "mask_parameters": mask_parameter_count,
                         "joint_trainable_parameters": online_parameter_count + decoder_parameter_count + mask_parameter_count,
                         "joint_trainable_parameter_tensors": len(trainable), "decoder_count": 6},
        "gradient_routing": {"information_preservation": "online_modality_encoders_and_decoders_only",
                             "scene": "online_encoder_projection_and_mask_embeddings", "target": "no_gradient"},
        "loss": qc, "ema_queue": {"update_order": joint["contrastive"]["update_order"], "status": "PASS"},
        "gpu_runtime": {"device": torch.cuda.get_device_name(), "elapsed_seconds": elapsed,
                        "peak_allocated_bytes": int(torch.cuda.max_memory_allocated()),
                        "peak_reserved_bytes": int(torch.cuda.max_memory_reserved()),
                        "physical_index": int(os.environ["FUSE_GPU_PHYSICAL_INDEX"]),
                        "torch": torch.__version__, "cuda": torch.version.cuda, "platform": platform.platform()},
        "outputs": outputs,
    }
    jsonschema.validate(manifest, schema)
    (stage / joint["output"]["manifest"]).write_bytes(canonical_json_bytes(manifest))
    files, publish_status = publish(stage, final, names)
    return {"status": "PASS", "joint_model_acceptance_id": acceptance_id,
            "publish_status": publish_status, "output_files": [str(path) for path in files]}
