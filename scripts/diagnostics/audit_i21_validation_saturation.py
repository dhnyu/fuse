#!/usr/bin/env python3
"""Read-only checkpoint sweep for the I21 prototype validation contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any

for _name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_name] = "1"

import numpy as np
import torch
import yaml

ROOT = Path(__file__).resolve().parents[2]
import sys

sys.path.insert(0, str(ROOT / "python"))

from prototype_ddp_joint_model import DistributedJointPrototypeModel
from prototype_encoder import geometry_fourier_features
from run_prototype_augmentation_benchmark import load_resources
from run_prototype_training import AugmentedPairDataset, collate_pairs, device_batch, state_digest
from run_prototype_training_ddp import RankLogicalGroupSampler


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-spec", required=True)
    parser.add_argument("--training-config", required=True)
    parser.add_argument("--joint-config", required=True)
    parser.add_argument("--encoder-config", required=True)
    parser.add_argument("--augmentation-config", required=True)
    parser.add_argument("--tensor-contract", required=True)
    parser.add_argument("--i19-manifest", required=True)
    parser.add_argument("--checkpoint-directory", required=True)
    parser.add_argument("--validation-history", required=True)
    parser.add_argument("--optimizer-ledger", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--device", default="cuda:0")
    return parser.parse_args()


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def fixed_rank_batches(
    dataset: AugmentedPairDataset, budgets: dict[str, int], seed: int
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    batches: list[dict[str, Any]] = []
    covered: list[int] = []
    input_audit = {
        "scene_id_mismatch_count": 0,
        "query_views_identical_count": 0,
        "query_candidate_identical_count": 0,
        "query_count": 0,
    }
    for rank in (0, 1):
        sampler = RankLogicalGroupSampler(dataset.base.rows, budgets, seed, rank)
        sampler.permutation = lambda: list(range(len(dataset)))
        for planned in sampler.batches():
            covered.extend(position for position, _, _ in planned)
            items = [dataset[task] for task in planned]
            for item in items:
                scene_ids = [view["scene_id"] for view in item["views"]]
                input_audit["scene_id_mismatch_count"] += int(len(set(scene_ids)) != 1)
                input_audit["query_views_identical_count"] += int(
                    item["views"][0]["training_tensor_digest"] == item["views"][1]["training_tensor_digest"]
                )
                input_audit["query_candidate_identical_count"] += sum(
                    item["views"][view]["training_tensor_digest"] == item["views"][2]["training_tensor_digest"]
                    for view in (0, 1)
                )
                input_audit["query_count"] += 2
            batches.append(collate_pairs(items))
    if sorted(covered) != list(range(len(dataset))):
        raise RuntimeError("rank validation plan has duplicate or missing scenes")
    return batches, input_audit


def embed_batches(
    model: DistributedJointPrototypeModel,
    batches: list[dict[str, Any]],
    encoder: dict[str, Any],
    masks: dict[str, int],
    device: torch.device,
) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    model.eval()
    with torch.inference_mode():
        for item in batches:
            outputs = []
            for view in range(3):
                batch = device_batch(item["views"][view], device, masks)
                geometry = geometry_fourier_features(batch, encoder, device)
                assignments = torch.full(
                    (batch["entities"]["entity_type"].numel(),), -1, dtype=torch.int64, device=device
                )
                outputs.append(model.forward_online(batch, geometry, assignments).outputs["scene_embedding"].cpu())
            for offset, scene_id in enumerate(item["views"][0]["scene_ids"]):
                if scene_id in records:
                    raise RuntimeError(f"duplicate scene ID during embedding: {scene_id}")
                records[scene_id] = {
                    "embeddings": [value[offset] for value in outputs],
                    "center": [float(value) for value in item["centers"][offset]],
                }
    return records


def retrieval_metrics(
    query_records: dict[str, dict[str, Any]], candidate_records: dict[str, dict[str, Any]]
) -> tuple[dict[str, Any], torch.Tensor, torch.Tensor, list[str], list[str]]:
    query_ids = sorted(query_records)
    candidate_ids = sorted(candidate_records)
    candidate_index = {scene_id: index for index, scene_id in enumerate(candidate_ids)}
    missing = sorted(set(query_ids) - set(candidate_ids))
    if missing:
        raise RuntimeError(f"positive candidates absent: {missing}")
    candidates = torch.stack([candidate_records[scene_id]["embeddings"][2] for scene_id in candidate_ids])
    queries = torch.cat(tuple(torch.stack([query_records[scene_id]["embeddings"][view] for scene_id in query_ids])
                              for view in (0, 1)))
    targets = torch.tensor([candidate_index[scene_id] for scene_id in query_ids] * 2, dtype=torch.int64)
    similarity = queries @ candidates.T
    order = torch.argsort(similarity, dim=1, descending=True, stable=True)
    ranks = torch.nonzero(order == targets[:, None])[:, 1] + 1
    row = torch.arange(len(queries))
    positive = similarity[row, targets]
    negative_mask = torch.ones_like(similarity, dtype=torch.bool)
    negative_mask[row, targets] = False
    hardest_negative = similarity.masked_fill(~negative_mask, -torch.inf).max(dim=1).values
    top2 = torch.topk(similarity, k=2, dim=1, largest=True, sorted=True).values
    metrics = {
        "MRR": float((1.0 / ranks.float()).mean()),
        "mean_rank": float(ranks.float().mean()),
        "median_rank": float(ranks.float().median()),
        "HIT@1": float((ranks <= 1).float().mean()),
        "HIT@5": float((ranks <= 5).float().mean()),
        "HIT@10": float((ranks <= 10).float().mean()),
        "validation_retrieval_loss_temperature_0_1": float(
            torch.nn.functional.cross_entropy(similarity / 0.1, targets, reduction="mean")
        ),
        "positive_similarity_mean": float(positive.mean()),
        "positive_similarity_median": float(positive.median()),
        "hardest_negative_similarity_mean": float(hardest_negative.mean()),
        "hardest_negative_similarity_median": float(hardest_negative.median()),
        "positive_hardest_negative_margin_mean": float((positive - hardest_negative).mean()),
        "positive_hardest_negative_margin_median": float((positive - hardest_negative).median()),
        "top1_top2_similarity_gap_mean": float((top2[:, 0] - top2[:, 1]).mean()),
        "top1_top2_similarity_gap_median": float((top2[:, 0] - top2[:, 1]).median()),
        "query_count": len(queries),
        "candidate_count": len(candidates),
        "embedding_digest": state_digest((queries, candidates)),
        "retrieval_digest": state_digest((order, ranks)),
        "continuous_digest": state_digest((similarity, positive, hardest_negative, top2)),
    }
    return metrics, queries, candidates, query_ids, candidate_ids


def non_local_metrics(
    queries: torch.Tensor,
    candidates: torch.Tensor,
    query_ids: list[str],
    candidate_ids: list[str],
    query_records: dict[str, dict[str, Any]],
    candidate_records: dict[str, dict[str, Any]],
    radius_m: float = 2000.0,
) -> dict[str, Any]:
    similarity = queries @ candidates.T
    query_centers = np.asarray([query_records[scene_id]["center"] for scene_id in query_ids] * 2)
    candidate_centers = np.asarray([candidate_records[scene_id]["center"] for scene_id in candidate_ids])
    distances = np.linalg.norm(query_centers[:, None, :] - candidate_centers[None, :, :], axis=2)
    allowed = torch.from_numpy(distances >= radius_m)
    counts = allowed.sum(dim=1)
    if int(counts.min()) < 2:
        raise RuntimeError("non-local candidate pool has fewer than two candidates")
    filtered = similarity.masked_fill(~allowed, -torch.inf)
    top2 = torch.topk(filtered, k=2, dim=1, largest=True, sorted=True).values
    order = torch.argsort(filtered, dim=1, descending=True, stable=True)
    return {
        "contract": "diagnostic_only_no_relevance_ground_truth",
        "exclusion": "candidate center distance < 2000 m",
        "candidate_count_min": int(counts.min()),
        "candidate_count_median": float(counts.float().median()),
        "candidate_count_max": int(counts.max()),
        "top1_similarity_mean": float(top2[:, 0].mean()),
        "top1_top2_similarity_gap_mean": float((top2[:, 0] - top2[:, 1]).mean()),
        "retrieval_digest": state_digest((order, counts)),
    }


def epoch_losses(path: Path) -> dict[int, float]:
    values: dict[int, list[float]] = {}
    with path.open() as stream:
        for line in stream:
            if not line.strip():
                continue
            row = json.loads(line)
            values.setdefault(int(row["epoch"]), []).append(float(row["total_loss"]))
    return {epoch: sum(losses) / len(losses) for epoch, losses in values.items()}


def correlation(rows: list[dict[str, Any]], key: str) -> dict[str, float]:
    loss = np.asarray([row["training_loss"] for row in rows], dtype=np.float64)
    value = np.asarray([row["expanded"][key] for row in rows], dtype=np.float64)
    loss_rank = np.argsort(np.argsort(loss))
    value_rank = np.argsort(np.argsort(value))
    return {
        "pearson": float(np.corrcoef(loss, value)[0, 1]),
        "spearman_no_ties": float(np.corrcoef(loss_rank, value_rank)[0, 1]),
    }


def main() -> None:
    args = parse_args()
    if not torch.cuda.is_available() and str(args.device).startswith("cuda"):
        raise RuntimeError("CUDA inference device is unavailable")
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    spec = json.loads(Path(args.run_spec).read_text())
    training = yaml.safe_load(Path(args.training_config).read_text())
    joint = yaml.safe_load(Path(args.joint_config).read_text())
    encoder = yaml.safe_load(Path(args.encoder_config).read_text())
    augmentation = yaml.safe_load(Path(args.augmentation_config).read_text())
    i19 = json.loads(Path(args.i19_manifest).read_text())
    history = {int(row["epoch"]): row for row in json.loads(Path(args.validation_history).read_text())}
    losses = epoch_losses(Path(args.optimizer_ledger))
    accepted = spec["dataset_manifest"]["path"]
    thresholds = {0: float(i19["logical_results"]["thresholds"]["building"]),
                  1: float(i19["logical_results"]["thresholds"]["road"])}
    archive = {
        "archive_source_root": training["execution"]["archive_source_root"],
        "archive_runtime_root": training["execution"]["archive_runtime_root"],
    }
    validation = AugmentedPairDataset(accepted, args.tensor_contract, "validation", augmentation, thresholds,
                                      validation=True, **archive)
    evaluation = AugmentedPairDataset(accepted, args.tensor_contract, "evaluation", augmentation, thresholds,
                                      validation=True, **archive)
    if len(validation) != 32 or len(evaluation) != 32:
        raise RuntimeError("prototype off-lattice split population mismatch")
    validation_batches, validation_input_audit = fixed_rank_batches(
        validation, spec["hard_budgets"], int(spec["seed"])
    )
    evaluation_batches, evaluation_input_audit = fixed_rank_batches(
        evaluation, spec["hard_budgets"], int(spec["seed"])
    )
    masks = {name: next(iter(values)) for name, values in validation.base.category_mask_index.items()}
    device = torch.device(args.device)
    model = DistributedJointPrototypeModel(encoder, joint).to(device).eval()
    checkpoints = sorted(Path(args.checkpoint_directory).glob("epoch-*.pt"))
    if [int(path.stem.rsplit("-", 1)[1]) for path in checkpoints] != list(range(5, 56, 5)):
        raise RuntimeError("checkpoint sweep is not exactly epoch 5..55 by 5")
    rows = []
    scene_sets = None
    for checkpoint in checkpoints:
        epoch = int(checkpoint.stem.rsplit("-", 1)[1])
        state = torch.load(checkpoint, map_location="cpu", weights_only=False)
        if state["run_id"] != spec["run_id"] or int(state["completed_epoch"]) != epoch:
            raise RuntimeError(f"checkpoint lineage mismatch: {checkpoint}")
        model.online.load_state_dict(state["online_model"])
        model.target.load_state_dict(state["target_model"])
        validation_records = embed_batches(model, validation_batches, encoder, masks, device)
        evaluation_records = embed_batches(model, evaluation_batches, encoder, masks, device)
        original, queries, _, query_ids, _ = retrieval_metrics(validation_records, validation_records)
        expected = history[epoch]
        for key in ("MRR", "HIT@1", "HIT@5", "HIT@10", "embedding_digest", "retrieval_digest"):
            if original[key] != expected[key]:
                raise RuntimeError(f"epoch {epoch} original validation reproduction mismatch: {key}")
        combined = {**validation_records, **evaluation_records}
        if len(combined) != 64:
            raise RuntimeError("validation/evaluation scene ID overlap")
        expanded, expanded_queries, expanded_candidates, expanded_query_ids, candidate_ids = retrieval_metrics(
            validation_records, combined
        )
        non_local = non_local_metrics(expanded_queries, expanded_candidates, expanded_query_ids, candidate_ids,
                                      validation_records, combined)
        current_sets = {
            "validation_scene_ids_digest": canonical_digest(sorted(validation_records)),
            "evaluation_scene_ids_digest": canonical_digest(sorted(evaluation_records)),
            "combined_scene_ids_digest": canonical_digest(sorted(combined)),
        }
        scene_sets = current_sets if scene_sets is None else scene_sets
        if current_sets != scene_sets:
            raise RuntimeError("scene population changed across checkpoints")
        rows.append({
            "epoch": epoch,
            "optimizer_step": int(state["optimizer_step"]),
            "training_loss": losses[epoch],
            "checkpoint_path": str(checkpoint),
            "original": original,
            "expanded": expanded,
            "non_local": non_local,
        })
        print(json.dumps({"epoch": epoch, "original_MRR": original["MRR"],
                          "expanded_MRR": expanded["MRR"],
                          "expanded_margin": expanded["positive_hardest_negative_margin_mean"]}, sort_keys=True), flush=True)
    output = {
        "status": "PASS",
        "mode": "read_only_checkpoint_inference",
        "run_id": spec["run_id"],
        "plan_id": spec["plan_id"],
        "device": str(device),
        "formal_training_invocations": 0,
        "optimizer_steps": 0,
        "training_dataloader_workers": 0,
        "publication_count": 0,
        "validation_population": 32,
        "diagnostic_candidate_population": 64,
        "diagnostic_evaluation_use": "negative_candidates_only_not_checkpoint_selection_or_acceptance",
        "input_augmentation_audit": {
            "validation": validation_input_audit,
            "evaluation": evaluation_input_audit,
        },
        "scene_sets": scene_sets,
        "checkpoint_results": rows,
        "correlations": {
            "loss_vs_positive_similarity": correlation(rows, "positive_similarity_mean"),
            "loss_vs_hardest_negative_similarity": correlation(rows, "hardest_negative_similarity_mean"),
            "loss_vs_margin": correlation(rows, "positive_hardest_negative_margin_mean"),
            "loss_vs_top1_top2_gap": correlation(rows, "top1_top2_similarity_gap_mean"),
        },
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary.write_text(json.dumps(output, sort_keys=True, indent=2) + "\n")
    os.replace(temporary, output_path)


if __name__ == "__main__":
    main()
