"""Deterministic validation retrieval and checkpoint-selection contracts."""

from __future__ import annotations

import hashlib
from typing import Any, Callable, Iterable

import torch
import torch.nn.functional as F


NEW_SELECTION_RULE = (
    "highest_MRR_then_lowest_validation_retrieval_loss_then_"
    "highest_mean_positive_hardest_negative_margin_then_earliest_epoch"
)
NEW_PATIENCE_RULE = "higher_MRR_or_saturated_retrieval_loss_min_delta"
NEW_METRIC_KEYS = (
    "MRR", "HIT@1", "HIT@5", "HIT@10", "mean_rank", "median_rank",
    "validation_retrieval_loss", "mean_positive_similarity",
    "mean_hardest_negative_similarity", "mean_positive_hardest_negative_margin",
    "mean_top1_top2_similarity_gap", "population", "embedding_digest",
    "retrieval_digest", "scene_ids_digest",
)


def _tensor_digest(values: tuple[torch.Tensor, ...]) -> str:
    digest = hashlib.sha256()
    for value in values:
        array = value.detach().cpu().contiguous().numpy()
        digest.update(str(array.dtype).encode())
        digest.update(str(array.shape).encode())
        digest.update(array.tobytes())
    return digest.hexdigest()


def validate_contract(config: dict[str, Any]) -> None:
    loss = config.get("retrieval_loss") or {}
    expected = {
        "checkpoint_selection": NEW_SELECTION_RULE,
        "patience_reset": NEW_PATIENCE_RULE,
        "evaluation_split_for_selection": "validation_only",
        "fixed_query_views": True,
        "fixed_query_augmentation_seed": True,
        "fixed_candidate_gallery": True,
    }
    for key, value in expected.items():
        if config.get(key) != value:
            raise ValueError(f"validation contract mismatch: {key}")
    loss_expected = {
        "definition": "deterministic_full_gallery_retrieval_cross_entropy",
        "logits": "cosine_similarity_divided_by_temperature",
        "reduction": "mean_over_two_fixed_query_views_and_validation_scenes",
        "candidate_exclusion": "none",
        "positive": "unique_same_scene_unaugmented_candidate",
    }
    for key, value in loss_expected.items():
        if loss.get(key) != value:
            raise ValueError(f"validation retrieval-loss contract mismatch: {key}")
    if float(loss.get("temperature", 0.0)) <= 0.0:
        raise ValueError("validation retrieval-loss temperature must be positive")
    if float(config.get("retrieval_loss_min_delta", 0.0)) <= 0.0:
        raise ValueError("validation retrieval-loss min_delta must be positive")
    tolerance = float(config.get("floating_point_tolerance", -1.0))
    if tolerance < 0.0:
        raise ValueError("validation floating-point tolerance must be non-negative")


def retrieval_metrics(
    queries: torch.Tensor,
    candidates: torch.Tensor,
    scene_ids: list[str],
    config: dict[str, Any],
    digest: Callable[[Any], str] | None = None,
) -> dict[str, Any]:
    """Evaluate two fixed query views against one fixed validation gallery."""
    validate_contract(config)
    population = len(scene_ids)
    if population < 2 or candidates.shape != (population, queries.shape[1]):
        raise ValueError("validation candidate population/shape mismatch")
    if queries.shape != (2 * population, candidates.shape[1]):
        raise ValueError("validation requires exactly two queries per candidate")
    if len(set(scene_ids)) != population:
        raise ValueError("validation candidate gallery contains duplicate scene IDs")
    similarity = queries @ candidates.T
    targets = torch.arange(population, device=similarity.device).repeat(2)
    order = torch.argsort(similarity, dim=1, descending=True, stable=True)
    ranks = torch.nonzero(order == targets[:, None], as_tuple=False)[:, 1] + 1
    temperature = float(config["retrieval_loss"]["temperature"])
    loss = F.cross_entropy(similarity / temperature, targets, reduction="mean")
    positive = similarity.gather(1, targets[:, None]).squeeze(1)
    negative_mask = torch.ones_like(similarity, dtype=torch.bool)
    negative_mask.scatter_(1, targets[:, None], False)
    hardest_negative = similarity.masked_fill(~negative_mask, -torch.inf).max(dim=1).values
    top_two = torch.topk(similarity, k=2, dim=1, largest=True, sorted=True).values
    if not all(bool(torch.isfinite(value).all()) for value in (similarity, loss, positive, hardest_negative, top_two)):
        raise ValueError("validation retrieval contains a non-finite value")
    digest_fn = digest or _tensor_digest
    return {
        "MRR": float((1.0 / ranks.float()).mean()),
        "HIT@1": float((ranks <= 1).float().mean()),
        "HIT@5": float((ranks <= 5).float().mean()),
        "HIT@10": float((ranks <= 10).float().mean()),
        "mean_rank": float(ranks.float().mean()),
        "median_rank": float(ranks.float().median()),
        "validation_retrieval_loss": float(loss),
        "mean_positive_similarity": float(positive.mean()),
        "mean_hardest_negative_similarity": float(hardest_negative.mean()),
        "mean_positive_hardest_negative_margin": float((positive - hardest_negative).mean()),
        "mean_top1_top2_similarity_gap": float((top_two[:, 0] - top_two[:, 1]).mean()),
        "population": population,
        "embedding_digest": digest_fn((queries, candidates)),
        "retrieval_digest": digest_fn((order, ranks, positive, hardest_negative)),
        "scene_ids_digest": digest_fn(scene_ids),
    }


def _new_contract(history: Iterable[dict[str, Any]], config: dict[str, Any] | None) -> bool:
    values = list(history)
    return bool(
        config
        and config.get("checkpoint_selection") == NEW_SELECTION_RULE
        and all("validation_retrieval_loss" in value for value in values)
    )


def selected_before(candidate: dict[str, Any], incumbent: dict[str, Any], config: dict[str, Any]) -> bool:
    tolerance = float(config["floating_point_tolerance"])
    candidate_mrr, incumbent_mrr = float(candidate["MRR"]), float(incumbent["MRR"])
    if candidate_mrr > incumbent_mrr + tolerance:
        return True
    if candidate_mrr < incumbent_mrr - tolerance:
        return False
    candidate_loss = float(candidate["validation_retrieval_loss"])
    incumbent_loss = float(incumbent["validation_retrieval_loss"])
    if candidate_loss < incumbent_loss - tolerance:
        return True
    if candidate_loss > incumbent_loss + tolerance:
        return False
    candidate_margin = float(candidate["mean_positive_hardest_negative_margin"])
    incumbent_margin = float(incumbent["mean_positive_hardest_negative_margin"])
    if candidate_margin > incumbent_margin + tolerance:
        return True
    if candidate_margin < incumbent_margin - tolerance:
        return False
    return int(candidate["epoch"]) < int(incumbent["epoch"])


def select_best(history: Iterable[dict[str, Any]], config: dict[str, Any] | None = None) -> dict[str, Any] | None:
    values = list(history)
    if not values:
        return None
    if not _new_contract(values, config):
        return dict(max(values, key=lambda value: (value["MRR"], value["HIT@1"], -value["epoch"])))
    selected = values[0]
    for value in values[1:]:
        if selected_before(value, selected, config or {}):
            selected = value
    return dict(selected)


def replay_early_stopping(
    history: Iterable[dict[str, Any]], config: dict[str, Any] | None = None
) -> tuple[int, dict[str, Any] | None, dict[str, Any]]:
    values = list(history)
    if not _new_contract(values, config):
        patience = 0
        best_mrr: float | None = None
        for value in values:
            mrr = float(value["MRR"])
            improved = best_mrr is None or mrr > best_mrr
            patience = 0 if improved else patience + 1
            if improved:
                best_mrr = mrr
        return patience, select_best(values, config), {"best_mrr": best_mrr}
    assert config is not None
    tolerance = float(config["floating_point_tolerance"])
    saturation = float(config["mrr_saturation_value"])
    min_delta = float(config["retrieval_loss_min_delta"])
    best_mrr: float | None = None
    saturated_loss_reference: float | None = None
    patience = 0
    for value in values:
        mrr = float(value["MRR"])
        loss = float(value["validation_retrieval_loss"])
        primary_improved = best_mrr is None or mrr > best_mrr + tolerance
        saturated = mrr >= saturation - tolerance
        loss_improved = bool(
            saturated
            and best_mrr is not None
            and best_mrr >= saturation - tolerance
            and saturated_loss_reference is not None
            and loss <= saturated_loss_reference - min_delta + tolerance
        )
        if primary_improved or loss_improved:
            patience = 0
            if primary_improved:
                best_mrr = mrr
            if saturated:
                saturated_loss_reference = loss
        else:
            patience += 1
        if saturated and saturated_loss_reference is None:
            saturated_loss_reference = loss
    state = {"best_mrr": best_mrr, "saturated_retrieval_loss_reference": saturated_loss_reference}
    return patience, select_best(values, config), state
