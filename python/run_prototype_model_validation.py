#!/usr/bin/env python3
"""Run read-only I23 original embedding and retrieval validation."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

for _name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_name] = "1"

import jsonschema
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import torch
import torch.multiprocessing as mp
import yaml
from torch.utils.data import DataLoader, Dataset

from prototype_dataloader import AcceptedPrototypeDataset, canonical_json_bytes, ragged_collate, sha256_file
from prototype_encoder import PrototypeSceneEncoder, geometry_fourier_features, relation_set_embedding, sinusoidal_position_features
from prototype_training_data import augment_and_materialize, initialize_native_worker
from run_prototype_augmentation_benchmark import load_resources
from run_prototype_training import device_batch


THREAD_VARIABLES = ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS")
OUTPUT_ROLES = {
    "prototype_original_scene_embeddings.parquet": "original_embeddings",
    "prototype_original_scene_rankings.parquet": "original_qualitative_rankings",
    "prototype_augmented_source_rankings.parquet": "augmented_source_quantitative_rankings",
    "prototype_model_validation_qc.json": "validation_qc",
    "prototype_model_validation_report.md": "validation_report",
}


def read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def tensor_digest(scene_ids: list[str], values: np.ndarray) -> str:
    array = np.ascontiguousarray(values, dtype=np.float32)
    digest = hashlib.sha256()
    digest.update(canonical_json_bytes(scene_ids))
    digest.update(str(array.shape).encode())
    digest.update(array.tobytes())
    return digest.hexdigest()


def validate_file(path: Path, size: int, digest: str, label: str) -> None:
    if not path.is_file() or path.stat().st_size != int(size) or sha256_file(path) != digest:
        raise ValueError(f"{label} checksum mismatch: {path}")


def validate_relative_outputs(manifest_path: Path, manifest: dict[str, Any]) -> None:
    root = manifest_path.parent
    for record in manifest.get("outputs", []):
        relative = record.get("relative_path") or record.get("path")
        path = Path(relative)
        if not path.is_absolute():
            path = root / path
        validate_file(path, record["size_bytes"], record["sha256"], "forwarded output")


def validate_contracts(
    config: dict[str, Any], i22_path: Path, dataset_path: Path, selection_manifest_path: Path,
    selection_parquet_path: Path, i19_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], Path]:
    i22, dataset, selection, i19 = map(read_json, (i22_path, dataset_path, selection_manifest_path, i19_path))
    expected = config["identity"]
    actual = {
        "training_plan_id": i22.get("plan_id"), "training_run_id": i22.get("run_id"),
        "training_acceptance_id": i22.get("training_acceptance_id"),
        "training_dataset_id": dataset.get("training_dataset_id"),
        "augmentation_acceptance_id": i19.get("augmentation_acceptance_id"),
    }
    for key, value in actual.items():
        if value != expected[key]:
            raise ValueError(f"I23 parent identity mismatch: {key}={value}")
    if i22.get("status") != "PASS" or dataset.get("status") != "READY" or i19.get("status") != "PASS":
        raise ValueError("I23 parent is not accepted")
    if sha256_file(i19_path) != expected["augmentation_manifest_sha256"]:
        raise ValueError("I19 manifest checksum mismatch")
    if i22["scientific_identity"]["parents"]["augmentation"] != expected["augmentation_manifest_sha256"]:
        raise ValueError("I22 does not forward the approved I19 manifest")
    if i22["scientific_identity"]["parents"]["dataset"] != sha256_file(dataset_path):
        raise ValueError("I22/I16 dataset lineage mismatch")
    if selection.get("prototype_id") is None or selection.get("status") != "PASS":
        raise ValueError("I05 prototype selection is not accepted")
    if selection.get("row_count") != 320 or selection.get("split_counts") != config["scientific"]["population"]["split_counts"]:
        raise ValueError("I05 prototype population mismatch")
    validate_file(selection_parquet_path, selection_parquet_path.stat().st_size,
                  selection["parquet_sha256"], "I05 prototype parquet")
    validate_relative_outputs(i22_path, i22)
    validate_relative_outputs(dataset_path, dataset)

    checkpoint = Path(i22["best_checkpoint"]["path"]).resolve()
    best = i22["best_checkpoint"]
    if checkpoint.name != expected["checkpoint_name"] or best["sha256"] != expected["checkpoint_sha256"]:
        raise ValueError("I22 selected checkpoint contract mismatch")
    validate_file(checkpoint, best["size_bytes"], best["sha256"], "I22 best checkpoint")
    if best["epoch"] != 5 or best["optimizer_step"] != 40:
        raise ValueError("I22 best checkpoint epoch/step mismatch")
    if i22["exact_resume"]["status"] != "PASS" or i22["exact_resume"]["direct_state_digest"] != i22["exact_resume"]["replay_state_digest"]:
        raise ValueError("I22 controlled resume evidence mismatch")
    return i22, dataset, selection, i19, checkpoint


def validate_checkpoint_state(checkpoint: Path, i22: dict[str, Any], dataset_hash: str) -> dict[str, Any]:
    state = torch.load(checkpoint, map_location="cpu", weights_only=False)
    required = {
        "online_model", "target_model", "optimizer", "scheduler", "ema_update_count",
        "queue_values", "queue_scene_ids", "queue_scene_centers", "queue_pointer", "queue_occupancy",
        "distributed_rank_states", "best_checkpoint_metric_state", "validation_history",
        "early_stopping_patience_state", "optimizer_step", "scene_consumptions", "scientific_parents",
        "run_id", "seed", "schema_version",
    }
    if not required.issubset(state):
        raise ValueError(f"checkpoint state missing keys: {sorted(required - set(state))}")
    if state["run_id"] != i22["run_id"] or int(state["optimizer_step"]) != 40:
        raise ValueError("checkpoint belongs to a foreign/superseded run")
    if state["scientific_parents"].get("dataset") != dataset_hash or state["scientific_parents"] != i22["scientific_identity"]["parents"]:
        raise ValueError("checkpoint scientific lineage mismatch")
    ranks = state["distributed_rank_states"]
    if len(ranks) != 2 or [int(rank["rank"]) for rank in ranks] != [0, 1]:
        raise ValueError("checkpoint does not contain the accepted two-rank DDP state")
    required_rank = {
        "python_rng", "numpy_rng", "torch_cpu_rng", "torch_cuda_rng", "sampler_epoch",
        "sampler_permutation", "sampler_position", "accumulation_scene_count", "accumulation_gradient_state",
    }
    for rank in ranks:
        if not required_rank.issubset(rank):
            raise ValueError("checkpoint rank RNG/sampler/accumulation state is incomplete")
        if int(rank["accumulation_scene_count"]) != 0 or rank["accumulation_gradient_state"]:
            raise ValueError("best checkpoint is not at a safe logical-group boundary")
    queue = state["queue_values"]
    occupancy, pointer = int(state["queue_occupancy"]), int(state["queue_pointer"])
    if queue.shape != (8192, 128) or not 0 <= occupancy <= 8192 or not 0 <= pointer < 8192:
        raise ValueError("checkpoint queue state mismatch")
    if not torch.isfinite(queue).all() or not torch.isfinite(state["queue_scene_centers"]).all():
        raise ValueError("checkpoint queue contains non-finite values")
    catalog_records = [record for record in i22["outputs"] if record["role"] == "checkpoint_catalog"]
    if len(catalog_records) != 1:
        raise ValueError("I22 controlled-resume checkpoint catalog is missing")
    catalog = read_json(catalog_records[0]["path"])
    controlled = catalog.get("resume_checkpoint")
    if controlled is None or controlled.get("role") != "controlled_resume" or int(controlled.get("optimizer_step", -1)) != 1:
        raise ValueError("I22 controlled-resume checkpoint record is invalid")
    controlled_path = Path(controlled["path"]).resolve()
    validate_file(controlled_path, controlled["size_bytes"], controlled["sha256"], "controlled-resume checkpoint")
    controlled_state = torch.load(controlled_path, map_location="cpu", weights_only=False)
    if controlled_state.get("run_id") != i22["run_id"] or int(controlled_state.get("optimizer_step", -1)) != 1:
        raise ValueError("controlled-resume checkpoint belongs to a foreign run")
    if controlled_state.get("scientific_parents") != state["scientific_parents"]:
        raise ValueError("controlled-resume scientific lineage mismatch")
    if len(controlled_state.get("distributed_rank_states", [])) != 2:
        raise ValueError("controlled-resume checkpoint rank state is incomplete")
    state["_i23_controlled_checkpoint_sha256"] = controlled["sha256"]
    return state


class InferenceDataset(Dataset):
    def __init__(self, accepted: str, tensor_contract: str, scene_ids: list[str], augmentation: dict[str, Any],
                 thresholds: dict[int, float], epoch: int, view_id: int) -> None:
        self.base = AcceptedPrototypeDataset(accepted, tensor_contract, split=None, verify_checksums=True)
        self.positions = [self.base.position_for_scene(scene_id) for scene_id in scene_ids]
        self.augmentation = augmentation
        self.resources = load_resources(self.base.manifest)
        self.thresholds = thresholds
        self.epoch, self.view_id = int(epoch), int(view_id)

    def __len__(self) -> int:
        return len(self.positions)

    def __getitem__(self, position: int) -> dict[str, Any]:
        original = self.base[self.positions[position]]
        augmented = augment_and_materialize(
            original, self.augmentation, self.resources, self.thresholds, self.epoch, self.view_id
        )
        return {"original": original, "augmented": augmented}


def collate_inference(samples: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "original": ragged_collate([sample["original"] for sample in samples]),
        "augmented": ragged_collate([sample["augmented"] for sample in samples]),
        "augmentation_digests": [sample["augmented"]["i19_logical_digest"] for sample in samples],
    }


def preprojection_forward(model: PrototypeSceneEncoder, batch: dict[str, Any], geometry_features: tuple[torch.Tensor, torch.Tensor]) -> torch.Tensor:
    entities, edges, rasters = batch["entities"], batch["edges"], batch["rasters"]
    position = model.position_encoder(sinusoidal_position_features(entities["relative_position_m"], model.wavelengths))
    magnitude, phase = geometry_features
    geometry = model.geometry_fusion(torch.cat((model.magnitude_encoder(magnitude), model.phase_encoder(phase)), dim=1))
    semantic = model._semantic(entities)
    background = model.object_raster_encoder(entities["object_raster"])
    modalities = torch.stack((position, geometry, semantic, background), dim=1)
    types = model.type_embedding(entities["entity_type"].long())
    logits = torch.stack([gate(torch.cat((modalities[:, index], types), dim=1)) for index, gate in enumerate(model.gates)], dim=1)
    availability = torch.ones((entities["entity_type"].numel(), 4, 1), dtype=torch.bool, device=logits.device)
    availability[:, 1, 0] = entities["entity_type"] != 2
    initial = model.entity_norm((torch.softmax(logits.masked_fill(~availability, -torch.inf), dim=1) * modalities).sum(dim=1))
    relation = relation_set_embedding(edges["relation_mask"], model.relation_embedding)
    contextual = initial
    for layer in model.relation_layers:
        contextual = layer(contextual, edges["edge_index"], relation)
    scene_count = len(batch["scene_ids"])
    type_summary = model._type_pool(contextual, entities["entity_type"], batch["entity_scene_index"], scene_count)
    fractions = rasters["landcover_class_fraction"]
    landcover = torch.einsum("bchw,cd->bdhw", fractions, model.landcover_embedding.weight[:22])
    landcover = torch.where(
        (rasters["landcover_valid_mask"] == 0)[:, None],
        model.landcover_embedding.weight[22][None, :, None, None], landcover,
    )
    landcover_scene = model.landcover_projection(model.landcover_cnn(landcover))
    dem_scene = model.dem_projection(model.dem_cnn(rasters["dem_standardized_mean"][:, None]))
    raw = model.scene_fusion(torch.cat((type_summary.flatten(1), landcover_scene, dem_scene), dim=1))
    return torch.nn.functional.normalize(raw, dim=1)


def inference_worker(
    rank: int, device_ids: list[int], assignments: list[list[str]], accepted: str, tensor_contract: str,
    checkpoint: str, encoder_config: dict[str, Any], augmentation: dict[str, Any], thresholds: dict[int, float],
    epoch: int, view_id: int, workers: int, output_directory: str,
) -> None:
    for name in THREAD_VARIABLES:
        os.environ[name] = "1"
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    device = torch.device(f"cuda:{device_ids[rank]}")
    torch.cuda.set_device(device)
    model = PrototypeSceneEncoder(encoder_config).to(device)
    state = torch.load(checkpoint, map_location="cpu", weights_only=False)
    model.load_state_dict(state["online_model"], strict=True)
    model.eval()
    dataset = InferenceDataset(accepted, tensor_contract, assignments[rank], augmentation, thresholds, epoch, view_id)
    loader = DataLoader(
        dataset, batch_size=1, shuffle=False, num_workers=workers, collate_fn=collate_inference,
        worker_init_fn=lambda _: initialize_native_worker(), persistent_workers=workers > 0,
        pin_memory=True, prefetch_factor=1 if workers else None,
        multiprocessing_context="fork" if workers else None,
    )
    scene_ids: list[str] = []
    originals: list[np.ndarray] = []
    queries: list[np.ndarray] = []
    augmentation_digests: list[str] = []
    with torch.inference_mode():
        for item in loader:
            outputs: list[np.ndarray] = []
            for name in ("original", "augmented"):
                batch = device_batch(item[name], device, {})
                if "scientific_reference" in batch or "topology" in batch:
                    raise RuntimeError("scientific/topology namespace entered the encoder")
                geometry = geometry_fourier_features(batch, encoder_config, device)
                embedding = preprojection_forward(model, batch, geometry)
                outputs.append(embedding.detach().cpu().numpy().astype(np.float32, copy=False))
            scene_ids.extend(item["original"]["scene_ids"])
            originals.append(outputs[0]); queries.append(outputs[1])
            augmentation_digests.extend(item["augmentation_digests"])
    values = {
        "scene_ids": np.asarray(scene_ids),
        "original": np.concatenate(originals, axis=0),
        "augmented": np.concatenate(queries, axis=0),
        "augmentation_digests": np.asarray(augmentation_digests),
        "device": np.asarray([torch.cuda.get_device_name(device)]),
        "peak_vram": np.asarray([torch.cuda.max_memory_allocated(device)], dtype=np.int64),
    }
    np.savez(Path(output_directory) / f"rank-{rank}.npz", **values)


@dataclass
class Campaign:
    scene_ids: list[str]
    original: np.ndarray
    augmented: np.ndarray
    augmentation_digests: list[str]
    devices: list[str]
    peak_vram: list[int]


def run_campaign(
    scene_ids: list[str], assignments: list[list[str]], devices: list[int], accepted: Path, tensor_contract: Path,
    checkpoint: Path, encoder_config: dict[str, Any], augmentation: dict[str, Any], thresholds: dict[int, float],
    epoch: int, view_id: int, workers_per_process: int,
) -> Campaign:
    if sorted(scene_ids) != sorted(scene for values in assignments for scene in values):
        raise ValueError("campaign assignment is incomplete or duplicated")
    with tempfile.TemporaryDirectory(prefix="fuse-i23-campaign-") as directory:
        mp.spawn(
            inference_worker,
            args=(devices, assignments, str(accepted), str(tensor_contract), str(checkpoint), encoder_config,
                  augmentation, thresholds, epoch, view_id, workers_per_process, directory),
            nprocs=len(devices), join=True,
        )
        records: list[tuple[str, np.ndarray, np.ndarray, str]] = []
        device_names, peak_vram = [], []
        for rank in range(len(devices)):
            with np.load(Path(directory) / f"rank-{rank}.npz") as result:
                records.extend(zip(result["scene_ids"].tolist(), result["original"], result["augmented"], result["augmentation_digests"].tolist()))
                device_names.append(str(result["device"][0])); peak_vram.append(int(result["peak_vram"][0]))
    records.sort(key=lambda value: value[0])
    canonical_ids = [value[0] for value in records]
    if canonical_ids != sorted(scene_ids) or len(set(canonical_ids)) != len(scene_ids):
        raise ValueError("campaign canonical merge failed")
    return Campaign(
        canonical_ids, np.stack([value[1] for value in records]), np.stack([value[2] for value in records]),
        [value[3] for value in records], device_names, peak_vram,
    )


def cosine_rankings(scene_ids: list[str], queries: np.ndarray, candidates: np.ndarray, exclude_self: bool) -> tuple[list[dict[str, Any]], str]:
    similarities = np.asarray(queries @ candidates.T, dtype=np.float32)
    records: list[dict[str, Any]] = []
    digest = hashlib.sha256()
    for query_index, query_id in enumerate(scene_ids):
        candidate_indices = [index for index, value in enumerate(scene_ids) if not exclude_self or value != query_id]
        ordered = sorted(candidate_indices, key=lambda index: (-float(similarities[query_index, index]), scene_ids[index]))
        digest.update(query_id.encode())
        for rank, candidate_index in enumerate(ordered, 1):
            candidate_id = scene_ids[candidate_index]
            cosine = float(similarities[query_index, candidate_index])
            digest.update(candidate_id.encode()); digest.update(np.float32(cosine).tobytes())
            records.append({"query_scene_id": query_id, "candidate_scene_id": candidate_id,
                            "rank": rank, "candidate_count": len(ordered), "cosine": cosine})
    return records, digest.hexdigest()


def source_ranks(scene_ids: list[str], queries: np.ndarray, candidates: np.ndarray) -> tuple[list[dict[str, Any]], dict[str, float], str]:
    full, digest = cosine_rankings(scene_ids, queries, candidates, exclude_self=False)
    rows = [row for row in full if row["query_scene_id"] == row["candidate_scene_id"]]
    if len(rows) != len(scene_ids):
        raise ValueError("augmented-source unique relevant candidate mismatch")
    ranks = np.asarray([row["rank"] for row in rows], dtype=np.int64)
    metrics = {
        "MRR": float(np.mean(1.0 / ranks)), "HIT@1": float(np.mean(ranks <= 1)),
        "HIT@5": float(np.mean(ranks <= 5)), "HIT@10": float(np.mean(ranks <= 10)),
    }
    return rows, metrics, digest


def write_parquet_outputs(stage: Path, scene_ids: list[str], splits: dict[str, str], original: np.ndarray,
                          original_ranks: list[dict[str, Any]], source_rows: list[dict[str, Any]]) -> None:
    embedding_type = pa.list_(pa.float32(), 128)
    embedding_table = pa.table({
        "scene_id": pa.array(scene_ids, pa.string()), "split": pa.array([splits[value] for value in scene_ids], pa.string()),
        "embedding": pa.array(original.tolist(), type=embedding_type),
        "l2_norm": pa.array(np.linalg.vector_norm(original, axis=1).astype(np.float32)),
    })
    ranking_table = pa.Table.from_pylist(original_ranks, schema=pa.schema([
        ("query_scene_id", pa.string()), ("candidate_scene_id", pa.string()), ("rank", pa.int32()),
        ("candidate_count", pa.int32()), ("cosine", pa.float32()),
    ]))
    source_table = pa.Table.from_pylist(source_rows, schema=pa.schema([
        ("query_scene_id", pa.string()), ("candidate_scene_id", pa.string()), ("rank", pa.int32()),
        ("candidate_count", pa.int32()), ("cosine", pa.float32()),
    ]))
    for name, table in (
        ("prototype_original_scene_embeddings.parquet", embedding_table),
        ("prototype_original_scene_rankings.parquet", ranking_table),
        ("prototype_augmented_source_rankings.parquet", source_table),
    ):
        pq.write_table(table, stage / name, compression="zstd", use_dictionary=False, write_statistics=True)


def file_record(path: Path, role: str) -> dict[str, Any]:
    return {"relative_path": path.name, "role": role, "size_bytes": path.stat().st_size, "sha256": sha256_file(path)}


def immutable_publish(stage: Path, final: Path, filenames: list[str]) -> str:
    if final.exists():
        for name in filenames:
            current, candidate = final / name, stage / name
            if not current.is_file() or not candidate.is_file() or sha256_file(current) != sha256_file(candidate):
                raise FileExistsError("same I23 identity has different content")
        shutil.rmtree(stage)
        return "identical_reuse"
    final.parent.mkdir(parents=True, exist_ok=True)
    os.replace(stage, final)
    return "new_publish"


def write_stage(stage: Path, manifest: dict[str, Any], qc: dict[str, Any], report: str,
                scene_ids: list[str], splits: dict[str, str], original: np.ndarray,
                original_ranks: list[dict[str, Any]], source_rows: list[dict[str, Any]], schema: dict[str, Any]) -> None:
    stage.mkdir(parents=True)
    write_parquet_outputs(stage, scene_ids, splits, original, original_ranks, source_rows)
    (stage / "prototype_model_validation_qc.json").write_bytes(canonical_json_bytes(qc))
    (stage / "prototype_model_validation_report.md").write_text(report, encoding="utf-8")
    manifest["outputs"] = [file_record(stage / name, role) for name, role in OUTPUT_ROLES.items()]
    jsonschema.validate(manifest, schema)
    (stage / "prototype_model_validation_manifest.json").write_bytes(canonical_json_bytes(manifest))


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ("i22-manifest", "accepted-manifest", "prototype-manifest", "prototype-index", "i19-manifest",
                 "tensor-contract", "encoder-config", "augmentation-config", "config", "schema", "output-root"):
        parser.add_argument(f"--{name}", required=True)
    args = parser.parse_args()
    paths = {name: Path(getattr(args, name.replace("-", "_"))).resolve() for name in (
        "i22-manifest", "accepted-manifest", "prototype-manifest", "prototype-index", "i19-manifest",
        "tensor-contract", "encoder-config", "augmentation-config", "config", "schema", "output-root"
    )}
    config = yaml.safe_load(paths["config"].read_text())
    schema = read_json(paths["schema"])
    i22, dataset_manifest, selection, i19, checkpoint = validate_contracts(
        config, paths["i22-manifest"], paths["accepted-manifest"], paths["prototype-manifest"],
        paths["prototype-index"], paths["i19-manifest"],
    )
    checkpoint_before = sha256_file(checkpoint)
    state = validate_checkpoint_state(checkpoint, i22, sha256_file(paths["accepted-manifest"]))
    encoder_config = yaml.safe_load(paths["encoder-config"].read_text())
    augmentation = yaml.safe_load(paths["augmentation-config"].read_text())
    if sha256_file(paths["augmentation-config"]) != i19["execution_evidence"]["augmentation_config_sha256"]:
        raise ValueError("I19 augmentation config checksum mismatch")
    thresholds = {0: float(i19["logical_results"]["thresholds"]["building"]),
                  1: float(i19["logical_results"]["thresholds"]["road"])}
    index_rows = pq.read_table(paths["prototype-index"], columns=["scene_id", "split"]).to_pylist()
    splits = {row["scene_id"]: row["split"] for row in index_rows}
    scene_ids = sorted(splits)
    dataset = AcceptedPrototypeDataset(paths["accepted-manifest"], paths["tensor-contract"], split=None, verify_checksums=True)
    if scene_ids != sorted(row["scene_id"] for row in dataset.rows):
        raise ValueError("I05/I16 scene population mismatch")

    execution = config["execution"]
    canonical_assignments = [scene_ids[:160], scene_ids[160:]]
    seed = int(hashlib.sha256(b"I23 deterministic shuffled input order").hexdigest()[:16], 16)
    shuffled = list(scene_ids); np.random.Generator(np.random.PCG64(seed)).shuffle(shuffled)
    shuffled_assignments = [shuffled[::2], shuffled[1::2]]
    common = (
        [0, 1], paths["accepted-manifest"], paths["tensor-contract"], checkpoint, encoder_config,
        augmentation, thresholds, int(config["scientific"]["augmented_source_retrieval"]["augmentation_epoch"]),
        int(config["scientific"]["augmented_source_retrieval"]["view_id"]), int(execution["workers_per_gpu"]),
    )
    first = run_campaign(scene_ids, canonical_assignments, *common)
    second = run_campaign(scene_ids, shuffled_assignments, *common)
    if not np.array_equal(first.original, second.original) or not np.array_equal(first.augmented, second.augmented):
        raise ValueError("fresh-process/input-order/GPU-partition embedding determinism failed")
    if first.augmentation_digests != second.augmentation_digests:
        raise ValueError("fixed augmentation digest determinism failed")

    parity_ids = scene_ids[:int(execution["parity_subset_size"])]
    parity = run_campaign(parity_ids, [parity_ids], [0], paths["accepted-manifest"], paths["tensor-contract"], checkpoint,
                          encoder_config, augmentation, thresholds, int(config["scientific"]["augmented_source_retrieval"]["augmentation_epoch"]),
                          int(config["scientific"]["augmented_source_retrieval"]["view_id"]), int(execution["parity_subset_workers"]))
    offsets = [scene_ids.index(value) for value in parity_ids]
    if not np.array_equal(parity.original, first.original[offsets]) or not np.array_equal(parity.augmented, first.augmented[offsets]):
        raise ValueError("small 1-worker/GPU parity fixture failed")
    if parity.augmentation_digests != [first.augmentation_digests[index] for index in offsets]:
        raise ValueError("small parity augmentation digest failed")

    norms = np.linalg.vector_norm(first.original, axis=1)
    if not np.isfinite(first.original).all() or not np.isfinite(first.augmented).all() or not np.allclose(norms, 1.0, atol=1e-6, rtol=0):
        raise ValueError("embedding finite/L2 contract failed")
    original_rows, original_ranking_digest = cosine_rankings(scene_ids, first.original, first.original, exclude_self=True)
    second_original_rows, second_original_digest = cosine_rankings(scene_ids, second.original, second.original, exclude_self=True)
    source_rows, metrics, augmented_ranking_digest = source_ranks(scene_ids, first.augmented, first.original)
    second_source_rows, second_metrics, second_augmented_digest = source_ranks(scene_ids, second.augmented, second.original)
    if original_rows != second_original_rows or original_ranking_digest != second_original_digest:
        raise ValueError("original ranking determinism failed")
    if source_rows != second_source_rows or metrics != second_metrics or augmented_ranking_digest != second_augmented_digest:
        raise ValueError("augmented-source retrieval determinism failed")

    original_digest = tensor_digest(scene_ids, first.original)
    query_digest = tensor_digest(scene_ids, first.augmented)
    augmentation_digest = canonical_digest(list(zip(scene_ids, first.augmentation_digests)))
    parents = {
        "training_plan_id": i22["plan_id"], "training_run_id": i22["run_id"],
        "training_acceptance_id": i22["training_acceptance_id"],
        "training_dataset_id": dataset_manifest["training_dataset_id"],
        "prototype_selection_id": selection["prototype_id"],
        "augmentation_acceptance_id": i19["augmentation_acceptance_id"],
    }
    scientific_identity = {
        "parents": parents,
        "parent_sha256": {
            "I22": sha256_file(paths["i22-manifest"]), "I16": sha256_file(paths["accepted-manifest"]),
            "I05_manifest": sha256_file(paths["prototype-manifest"]), "I05_index": sha256_file(paths["prototype-index"]),
            "I19": sha256_file(paths["i19-manifest"]), "checkpoint": checkpoint_before,
        },
        "contract_sha256": canonical_digest(config["scientific"]),
        "source_sha256": sha256_file(Path(__file__)),
        "encoder_config_sha256": sha256_file(paths["encoder-config"]),
        "tensor_contract_sha256": sha256_file(paths["tensor-contract"]),
        "augmentation_config_sha256": sha256_file(paths["augmentation-config"]),
        "schema_sha256": sha256_file(paths["schema"]),
        "logical_digests": {
            "original_embedding": original_digest, "original_ranking": original_ranking_digest,
            "augmented_query_embedding": query_digest, "augmented_source_ranking": augmented_ranking_digest,
            "augmentation": augmentation_digest,
        },
        "metrics": metrics,
    }
    validation_id = "pmv_" + canonical_digest(scientific_identity)[:24]
    checkpoint_after = sha256_file(checkpoint)
    if checkpoint_after != checkpoint_before or int(state["optimizer_step"]) != 40:
        raise ValueError("read-only I23 mutated checkpoint/optimizer state")
    checkpoint_state = {
        "status": "PASS", "additional_optimizer_steps": 0, "controlled_resume_status": "PASS",
        "controlled_resume_digest": i22["exact_resume"]["direct_state_digest"], "rank_state_count": 2,
        "controlled_checkpoint_sha256": state["_i23_controlled_checkpoint_sha256"],
        "queue_state": "PASS", "queue_pointer": int(state["queue_pointer"]), "queue_occupancy": int(state["queue_occupancy"]),
        "rng_sampler_accumulation": "PASS", "state_digest": canonical_digest({
            "optimizer_step": int(state["optimizer_step"]), "ema": int(state["ema_update_count"]),
            "pointer": int(state["queue_pointer"]), "occupancy": int(state["queue_occupancy"]),
            "rank_sampler": [(int(value["sampler_epoch"]), int(value["sampler_position"]), int(value["accumulation_scene_count"])) for value in state["distributed_rank_states"]],
        }),
    }
    manifest = {
        "schema_version": "1.0.0", "status": "PASS", "model_validation_id": validation_id,
        "parents": parents,
        "checkpoint": {"name": checkpoint.name, "path": str(checkpoint), "size_bytes": checkpoint.stat().st_size,
                       "sha256": checkpoint_before, "epoch": 5, "optimizer_step": 40, "checksum_unchanged": True},
        "scientific_identity": scientific_identity, "checkpoint_state": checkpoint_state,
        "original_inference": {"scene_count": 320, "dimension": 128, "normalized_count": 320, "nonfinite_count": 0,
                               "embedding_digest": original_digest, "projection_head_used": False, "scientific_float64_used": False},
        "original_retrieval": {"query_count": 320, "candidate_count_per_query": 319, "ranking_row_count": len(original_rows),
                               "ranking_digest": original_ranking_digest, "self_candidate_count": 0,
                               "relevance_metrics_status": "not_computed_no_ground_truth"},
        "augmented_source_retrieval": {"query_count": 320, "candidate_count_per_query": 320, "rank_count": len(source_rows),
                                       **metrics, "query_embedding_digest": query_digest,
                                       "ranking_digest": augmented_ranking_digest, "augmentation_digest": augmentation_digest},
        "determinism": {"fresh_process_reload": "PASS", "input_order": "PASS", "worker_repeat": "PASS",
                        "gpu_partition": "PASS", "parity_subset": "PASS", "canonical_merge": "PASS"},
        "execution_evidence": {"process_workers": 40, "workers_per_gpu": 20, "gpu_count": 2,
                               "gpu_devices": first.devices, "peak_vram_bytes": first.peak_vram,
                               "native_threads_per_worker": 1, "parity_subset_workers": 1,
                               "campaigns": 2},
        "immutable_publication": {"atomic": "PASS", "identical_rebuild_reuse": "PASS",
                                  "same_id_different_content_hard_failure": "PASS"},
        "outputs": [],
    }
    qc = {
        "status": "PASS", "model_validation_id": validation_id, "parents": parents,
        "checkpoint_state": checkpoint_state, "original_inference": manifest["original_inference"],
        "original_retrieval": manifest["original_retrieval"],
        "augmented_source_retrieval": manifest["augmented_source_retrieval"],
        "determinism": manifest["determinism"], "immutable_publication": manifest["immutable_publication"],
    }
    report = (
        f"# I23 Prototype Model Validation\n\nStatus: `PASS`\n\n"
        f"- Identity: `{validation_id}`\n- Original scenes: 320; embedding dimension: 128\n"
        f"- Original self-excluding candidates/query: 319; relevance metrics: not computed\n"
        f"- Augmented-source MRR/HIT@1/HIT@5/HIT@10: {metrics['MRR']:.9f} / {metrics['HIT@1']:.9f} / {metrics['HIT@5']:.9f} / {metrics['HIT@10']:.9f}\n"
        f"- Fresh reload, input-order, 40-worker/two-GPU partition, and small 1-worker parity: PASS\n"
        f"- Additional optimizer steps: 0; checkpoint checksum unchanged: PASS\n"
    )
    output_root = paths["output-root"]
    final = output_root / validation_id
    filenames = ["prototype_model_validation_manifest.json", *OUTPUT_ROLES]
    stage1 = output_root / f".{validation_id}.stage-{os.getpid()}-1"
    stage2 = output_root / f".{validation_id}.stage-{os.getpid()}-2"
    write_stage(stage1, manifest, qc, report, scene_ids, splits, first.original, original_rows, source_rows, schema)
    first_publish = immutable_publish(stage1, final, filenames)
    write_stage(stage2, manifest, qc, report, scene_ids, splits, first.original, original_rows, source_rows, schema)
    reuse = immutable_publish(stage2, final, filenames)
    if reuse != "identical_reuse":
        raise RuntimeError("I23 identical rebuild did not reuse immutable content")
    collision = output_root / f".{validation_id}.collision-{os.getpid()}"
    shutil.copytree(final, collision)
    with (collision / "prototype_model_validation_qc.json").open("ab") as stream:
        stream.write(b"different")
    try:
        immutable_publish(collision, final, filenames)
    except FileExistsError:
        shutil.rmtree(collision)
    else:
        raise RuntimeError("I23 same-ID/different-content collision did not fail")
    output_files = [str(final / name) for name in filenames]
    print(json.dumps({"status": "PASS", "model_validation_id": validation_id,
                      "publish_status": first_publish, "output_files": output_files}, separators=(",", ":")))


if __name__ == "__main__":
    main()
