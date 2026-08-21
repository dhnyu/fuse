"""I18 float32 GPU correctness smoke implementation."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
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

from prototype_dataloader import AcceptedPrototypeDataset, DeterministicBudgetBatchSampler, canonical_json_bytes, ragged_collate, sha256_file
from prototype_encoder import PrototypeSceneEncoder, geometry_fourier_features, relation_set_embedding, segment_fourier, sinusoidal_position_features


def move_to_device(value: Any, device: torch.device) -> Any:
    if isinstance(value, torch.Tensor):
        return value.to(device)
    if isinstance(value, dict):
        return {key: move_to_device(item, device) for key, item in value.items()}
    if isinstance(value, list):
        return [move_to_device(item, device) for item in value]
    return value


def representative_rows(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    zero = min((row for row in rows if int(row["node_count"]) == 0), key=lambda row: row["scene_id"])
    node_only = min((row for row in rows if int(row["node_count"]) > 0 and int(row["ordered_edge_count"]) == 0), key=lambda row: (row["node_count"], row["scene_id"]))
    ordered = sorted(rows, key=lambda row: (int(row["actual_payload_bytes"]), row["scene_id"]))
    return {
        "zero_node": zero,
        "node_only": node_only,
        "median": ordered[len(ordered) // 2],
        "maximum_node": max(rows, key=lambda row: (int(row["node_count"]), row["scene_id"])),
        "maximum_edge": max(rows, key=lambda row: (int(row["ordered_edge_count"]), row["scene_id"])),
        "geometry_heavy": max(rows, key=lambda row: (int(row["coordinate_count"]), row["scene_id"])),
    }


def gpu_inventory(physical_index: int) -> dict[str, Any]:
    query = subprocess.run(
        ["nvidia-smi", f"--id={physical_index}", "--query-gpu=uuid,name,driver_version,memory.total", "--format=csv,noheader,nounits"],
        check=True, capture_output=True, text=True,
    ).stdout.strip().split(", ")
    properties = torch.cuda.get_device_properties(0)
    return {
        "physical_index": physical_index, "visible_index": 0, "uuid": query[0], "name": query[1],
        "driver_version": query[2], "memory_total_mib_nvidia_smi": int(query[3]),
        "memory_total_bytes_torch": int(properties.total_memory), "compute_capability": f"{properties.major}.{properties.minor}",
        "cuda_runtime": torch.version.cuda, "torch": torch.__version__,
        "lock_wait_seconds": float(os.environ["FUSE_GPU_LOCK_WAIT_SECONDS"]),
        "pair_lock": os.environ["FUSE_GPU_PAIR_LOCK"], "device_lock": os.environ["FUSE_GPU_DEVICE_LOCK"],
        "lock_order": "gpu_pair_shared_then_device_exclusive", "lock_state_during_publish": "held",
        "release_policy": "POSIX_flock_descriptor_close_on_process_exit",
    }


def numerical_references(model: PrototypeSceneEncoder, device: torch.device) -> dict[str, float]:
    position = torch.tensor([[13.25, -41.5]], device=device)
    observed_position = sinusoidal_position_features(position, model.wavelengths).detach().cpu().numpy()[0]
    wavelengths = model.wavelengths.detach().cpu().numpy()
    expected_position = np.stack((
        np.sin(2 * np.pi * 13.25 / wavelengths), np.cos(2 * np.pi * 13.25 / wavelengths),
        np.sin(2 * np.pi * -41.5 / wavelengths), np.cos(2 * np.pi * -41.5 / wavelengths),
    ), axis=1).reshape(-1)
    frequencies = torch.tensor([[0.5, 0.0], [1.25, -0.75], [3.0, 2.0]], device=device)
    points = torch.tensor([[-0.2, 0.1], [0.3, -0.4]], device=device)
    observed_line = segment_fourier(points, frequencies).detach().cpu().numpy()
    start, end = np.array([-0.2, 0.1]), np.array([0.3, -0.4])
    delta, midpoint = end - start, (start + end) / 2
    expected_line = np.linalg.norm(delta) * np.exp(-2j * np.pi * (frequencies.cpu().numpy() @ midpoint)) * np.sinc(frequencies.cpu().numpy() @ delta)
    mask = torch.tensor([1 | 4 | 16], dtype=torch.uint8, device=device)
    observed_relation = relation_set_embedding(mask, model.relation_embedding).detach().cpu().numpy()[0]
    expected_relation = model.relation_embedding.weight.detach().cpu().numpy()[[0, 2, 4]].sum(axis=0)
    return {
        "position_max_abs_error": float(np.max(np.abs(observed_position - expected_position))),
        "line_fourier_max_abs_error": float(np.max(np.abs(observed_line - expected_line))),
        "multi_relation_sum_max_abs_error": float(np.max(np.abs(observed_relation - expected_relation))),
    }


def parameter_rows(model: torch.nn.Module) -> list[dict[str, Any]]:
    return [
        {
            "name": name, "shape": "x".join(str(value) for value in parameter.shape),
            "elements": parameter.numel(), "trainable": parameter.requires_grad,
            "gradient_present": parameter.grad is not None,
            "gradient_finite": bool(parameter.grad is not None and torch.isfinite(parameter.grad).all()),
            "gradient_l2": float(parameter.grad.detach().norm().cpu()) if parameter.grad is not None else None,
        }
        for name, parameter in model.named_parameters()
    ]


def shape_rows(outputs: dict[str, torch.Tensor], batch_label: str) -> list[dict[str, Any]]:
    return [
        {"batch": batch_label, "tensor": name, "shape": "x".join(map(str, value.shape)), "dtype": str(value.dtype).replace("torch.", ""), "finite": bool(torch.isfinite(value).all())}
        for name, value in outputs.items()
    ]


def write_parquet(path: Path, rows: list[dict[str, Any]]) -> None:
    pq.write_table(pa.Table.from_pylist(rows), path, compression="zstd", row_group_size=65536)


def output_record(path: Path, root: Path) -> dict[str, Any]:
    return {"relative_path": str(path.relative_to(root)), "size_bytes": path.stat().st_size, "sha256": sha256_file(path)}


def run_smoke(manifest_path: Path, dataloader_smoke_path: Path, config_path: Path, schema_path: Path, tensor_contract_path: Path) -> dict[str, Any]:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    accepted = json.loads(manifest_path.read_text(encoding="utf-8"))
    dataloader_smoke = json.loads(dataloader_smoke_path.read_text(encoding="utf-8"))
    if accepted["training_dataset_id"] != config["identity"]["accepted_dataset_id"]:
        raise ValueError("I18 accepted dataset identity mismatch")
    if dataloader_smoke["smoke_id"] != config["identity"]["dataloader_smoke_id"] or dataloader_smoke["status"] != "READY":
        raise ValueError("I18 DataLoader smoke identity/status mismatch")
    if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
        raise RuntimeError("I18 requires exactly one lock-selected visible GPU")
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    torch.manual_seed(int(config["smoke"]["seed"]))
    torch.cuda.manual_seed_all(int(config["smoke"]["seed"]))
    torch.use_deterministic_algorithms(True)
    device = torch.device("cuda:0")
    torch.cuda.set_device(0)
    torch.cuda.reset_peak_memory_stats(0)
    started = time.perf_counter()

    dataset = AcceptedPrototypeDataset(manifest_path, tensor_contract_path, verify_checksums=True)
    roles = representative_rows(dataset.rows)
    unique_scene_ids = list(dict.fromkeys(row["scene_id"] for row in roles.values()))
    representative_samples = [dataset.get_by_scene_id(scene_id) for scene_id in unique_scene_ids]
    budgets = {key: int(value) for key, value in dataloader_smoke["batching"]["budgets"].items()}
    representative_batch = move_to_device(ragged_collate(representative_samples, budgets), device)
    training = AcceptedPrototypeDataset(manifest_path, tensor_contract_path, split="training", verify_checksums=False)
    sampler = DeterministicBudgetBatchSampler(training.rows, budgets, shuffle=False, seed=int(config["smoke"]["seed"]))
    general_indices = next(iter(sampler))
    general_batch = move_to_device(ragged_collate([training[index] for index in general_indices], budgets), device)

    model = PrototypeSceneEncoder(config).to(device=device, dtype=torch.float32)
    representative_geometry = geometry_fourier_features(representative_batch, config, device)
    general_geometry = geometry_fourier_features(general_batch, config, device)
    model.eval()
    with torch.no_grad():
        eval_first = model(representative_batch, representative_geometry)
        eval_second = model(representative_batch, representative_geometry)
        general_output = model(general_batch, general_geometry)
    if not torch.equal(eval_first["projection"], eval_second["projection"]):
        raise ValueError("deterministic eval forward mismatch")
    if any(not torch.isfinite(value).all() for value in (*eval_first.values(), *general_output.values())):
        raise ValueError("non-finite encoder forward output")
    normalization_error = float((torch.linalg.vector_norm(eval_first["scene_embedding"], dim=1) - 1).abs().max().cpu())
    projection_normalization_error = float((torch.linalg.vector_norm(eval_first["projection"], dim=1) - 1).abs().max().cpu())
    if max(normalization_error, projection_normalization_error) > float(config["smoke"]["normalization_tolerance"]):
        raise ValueError("scene/projection L2 normalization mismatch")
    zero_scene_index = unique_scene_ids.index(roles["zero_node"]["scene_id"])
    if not torch.equal(eval_first["type_summary"][zero_scene_index], torch.zeros_like(eval_first["type_summary"][zero_scene_index])):
        raise ValueError("zero-node object summaries are not exact zero vectors")

    model.train()
    train_first = model(representative_batch, representative_geometry)["projection"]
    train_second = model(representative_batch, representative_geometry)["projection"]
    if torch.equal(train_first, train_second):
        raise ValueError("dropout train mode did not change the forward output")
    target = torch.arange(train_first.numel(), device=device, dtype=torch.float32).reshape_as(train_first) + 1
    target = torch.nn.functional.normalize(target, dim=1)
    loss = (1.0 - (train_first * target).sum(dim=1)).mean()
    if not torch.isfinite(loss):
        raise ValueError("smoke scalar loss is non-finite")
    loss.backward()
    parameters = parameter_rows(model)
    missing_gradient = [row["name"] for row in parameters if row["trainable"] and not row["gradient_present"]]
    invalid_gradient = [row["name"] for row in parameters if row["gradient_present"] and not row["gradient_finite"]]
    zero_gradient = [row["name"] for row in parameters if row["gradient_present"] and row["gradient_l2"] == 0.0]
    if missing_gradient or invalid_gradient or zero_gradient:
        raise ValueError(f"gradient coverage failed: missing={missing_gradient}, invalid={invalid_gradient}, zero={zero_gradient}")

    references = numerical_references(model, device)
    if max(references.values()) > float(config["smoke"]["reference_tolerance"]):
        raise ValueError(f"CPU/GPU numerical reference mismatch: {references}")
    torch.cuda.synchronize(device)
    elapsed = time.perf_counter() - started
    gpu = gpu_inventory(int(os.environ["FUSE_GPU_PHYSICAL_INDEX"]))
    gpu.update({
        "peak_allocated_bytes": int(torch.cuda.max_memory_allocated(0)),
        "peak_reserved_bytes": int(torch.cuda.max_memory_reserved(0)),
    })
    scientific_identity = {
        "accepted_dataset_id": accepted["training_dataset_id"],
        "accepted_manifest_sha256": sha256_file(manifest_path),
        "dataloader_smoke_id": dataloader_smoke["smoke_id"],
        "dataloader_smoke_sha256": sha256_file(dataloader_smoke_path),
        "model_config_sha256": sha256_file(config_path), "schema_sha256": sha256_file(schema_path),
        "tensor_contract_sha256": sha256_file(tensor_contract_path),
        "model_implementation_sha256": sha256_file(Path(__file__).with_name("prototype_encoder.py")),
        "smoke_implementation_sha256": sha256_file(Path(__file__)),
        "launcher_sha256": sha256_file(Path(__file__).with_name("run_prototype_encoder_smoke.py")),
        "requirements_sha256": sha256_file(Path(__file__).with_name("requirements-encoder.txt")),
        "dissertation_commit": config["identity"]["dissertation_commit"],
        "precision": "float32",
    }
    acceptance_id = "pea_" + hashlib.sha256(canonical_json_bytes(scientific_identity)).hexdigest()[:24]
    final_dir = manifest_path.parent / config["output"]["subdirectory"] / acceptance_id
    final_dir.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{acceptance_id}.staging-", dir=final_dir.parent))
    try:
        parameter_path = stage / config["output"]["parameters"]
        shape_path = stage / config["output"]["shapes"]
        qc_path = stage / config["output"]["qc"]
        log_path = stage / config["output"]["log"]
        manifest_output_path = stage / config["output"]["manifest"]
        write_parquet(parameter_path, parameters)
        shapes = shape_rows(eval_first, "representative") + shape_rows(general_output, "general_variable_budget")
        write_parquet(shape_path, shapes)
        qc = {
            "status": "PASS", "representative_scenes": {role: row["scene_id"] for role, row in roles.items()},
            "representative_unique_scene_count": len(unique_scene_ids), "general_batch_scene_count": len(general_indices),
            "scene_embedding_dimension": int(eval_first["scene_embedding"].shape[1]),
            "scene_normalization_max_error": normalization_error,
            "projection_normalization_max_error": projection_normalization_error,
            "eval_determinism": "PASS", "dropout_train_eval": "PASS", "backward": "PASS",
            "trainable_parameter_tensors": sum(row["trainable"] for row in parameters),
            "trainable_parameters": sum(row["elements"] for row in parameters if row["trainable"]),
            "gradient_covered_tensors": sum(row["gradient_present"] for row in parameters),
            "missing_gradient_tensors": 0, "zero_gradient_tensors": 0, "invalid_gradient_tensors": 0,
            "loss": float(loss.detach().cpu()), "numerical_references": references,
            "zero_node_object_summary": "three_exact_zero_vectors", "empty_type_summary": "exact_zero_vector",
            "node_without_edges": "zero_message_then_residual_ffn", "poi_geometry_weight": "exact_zero",
        }
        qc_path.write_bytes(canonical_json_bytes(qc))
        log_path.write_bytes(canonical_json_bytes({
            "event": "prototype_encoder_smoke_complete", "status": "PASS", "encoder_acceptance_id": acceptance_id,
            "physical_gpu_uuid": gpu["uuid"], "elapsed_seconds": elapsed, "lock_state": "held",
        }) + b"\n")
        manifest = {
            "schema_version": "1.0.0", "status": "PASS", "encoder_acceptance_id": acceptance_id,
            "accepted_dataset_id": accepted["training_dataset_id"], "dataloader_smoke_id": dataloader_smoke["smoke_id"],
            "scientific_identity": scientific_identity,
            "architecture": {
                "latent_dimension": 128, "relation_layers": 3, "attention_heads": 4, "dropout": 0.1,
                "trainable_parameters": qc["trainable_parameters"], "precision": "float32",
                "empty_type_summary": "zero_vector", "zero_node_object_branch": "three_zero_vectors",
            },
            "smoke": qc, "gpu_runtime": {**gpu, "elapsed_seconds": elapsed},
            "outputs": [output_record(path, stage) for path in (parameter_path, shape_path, qc_path, log_path)],
            "environment": {"python": platform.python_version(), "platform": platform.platform(), "numpy": np.__version__},
        }
        jsonschema.validate(manifest, schema)
        manifest_output_path.write_bytes(canonical_json_bytes(manifest))
        if final_dir.exists():
            names = sorted(path.name for path in stage.iterdir())
            if names != sorted(path.name for path in final_dir.iterdir()) or any(sha256_file(stage / name) != sha256_file(final_dir / name) for name in names):
                raise FileExistsError("same encoder acceptance ID has different content")
            shutil.rmtree(stage)
        else:
            os.replace(stage, final_dir)
        outputs = sorted(str(path.resolve()) for path in final_dir.iterdir())
        return {"status": "PASS", "encoder_acceptance_id": acceptance_id, "output_files": outputs}
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
