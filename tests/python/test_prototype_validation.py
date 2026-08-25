from __future__ import annotations

import math

import torch
import pytest

from prototype_validation import NEW_SELECTION_RULE, replay_early_stopping, retrieval_metrics, select_best
from run_prototype_training import make_optimizer, optimizer_steps_per_epoch


def contract() -> dict:
    return {
        "checkpoint_selection": NEW_SELECTION_RULE,
        "patience_reset": "higher_MRR_or_saturated_retrieval_loss_min_delta",
        "evaluation_split_for_selection": "validation_only",
        "fixed_query_views": True,
        "fixed_query_augmentation_seed": True,
        "fixed_candidate_gallery": True,
        "retrieval_loss": {
            "definition": "deterministic_full_gallery_retrieval_cross_entropy",
            "logits": "cosine_similarity_divided_by_temperature",
            "temperature": 0.1,
            "reduction": "mean_over_two_fixed_query_views_and_validation_scenes",
            "candidate_exclusion": "none",
            "positive": "unique_same_scene_unaugmented_candidate",
        },
        "retrieval_loss_min_delta": 1.0e-4,
        "floating_point_tolerance": 1.0e-12,
        "mrr_saturation_value": 1.0,
    }


def row(epoch: int, mrr: float, loss: float, margin: float) -> dict:
    return {"epoch": epoch, "MRR": mrr, "HIT@1": 1.0,
            "validation_retrieval_loss": loss,
            "mean_positive_hardest_negative_margin": margin}


def test_retrieval_cross_entropy_and_continuous_metrics_are_exactly_repeatable() -> None:
    candidates = torch.tensor([[1.0, 0.0], [0.0, 1.0]], dtype=torch.float32)
    queries = torch.cat((candidates, candidates))
    first = retrieval_metrics(queries, candidates, ["a", "b"], contract(), repr)
    second = retrieval_metrics(queries, candidates, ["a", "b"], contract(), repr)
    assert first == second
    assert first["MRR"] == first["HIT@1"] == 1.0
    assert math.isclose(first["validation_retrieval_loss"], math.log1p(math.exp(-10.0)), rel_tol=5e-4)
    assert first["mean_positive_hardest_negative_margin"] == 1.0


def test_selection_uses_loss_then_margin_then_earliest() -> None:
    history = [row(5, 1.0, 0.2, 0.3), row(10, 1.0, 0.1, 0.2), row(15, 1.0, 0.1, 0.4)]
    assert select_best(history, contract())["epoch"] == 15
    history.append(row(20, 1.0, 0.1, 0.4))
    assert select_best(history, contract())["epoch"] == 15


def test_patience_resets_only_after_cumulative_saturated_loss_min_delta() -> None:
    history = [row(5, 1.0, 0.20000, 0.1), row(10, 1.0, 0.19995, 0.2)]
    patience, _, state = replay_early_stopping(history, contract())
    assert patience == 1
    assert state["saturated_retrieval_loss_reference"] == 0.2
    history.append(row(15, 1.0, 0.19989, 0.2))
    patience, _, state = replay_early_stopping(history, contract())
    assert patience == 0
    assert state["saturated_retrieval_loss_reference"] == 0.19989


def test_legacy_checkpoint_selection_remains_readable() -> None:
    history = [{"epoch": 5, "MRR": 1.0, "HIT@1": 1.0}, {"epoch": 10, "MRR": 1.0, "HIT@1": 1.0}]
    patience, selected, _ = replay_early_stopping(history)
    assert patience == 1
    assert selected["epoch"] == 5


def test_schedule_steps_are_derived_and_validated() -> None:
    assert optimizer_steps_per_epoch({"training_scenes": 256, "effective_batch_scenes": 32, "optimizer": {}}) == 8
    assert optimizer_steps_per_epoch({"training_scenes": 2432, "effective_batch_scenes": 32,
                                      "optimizer": {"optimizer_steps_per_epoch": 76}}) == 76
    with pytest.raises(ValueError, match="divisible"):
        optimizer_steps_per_epoch({"training_scenes": 257, "effective_batch_scenes": 32, "optimizer": {}})
    with pytest.raises(ValueError, match="mismatch"):
        optimizer_steps_per_epoch({"training_scenes": 256, "effective_batch_scenes": 32,
                                   "optimizer": {"optimizer_steps_per_epoch": 7}})


def test_nonfinite_validation_embedding_is_rejected() -> None:
    candidates = torch.eye(2); queries = torch.cat((candidates, candidates)); queries[0, 0] = torch.nan
    with pytest.raises(ValueError, match="non-finite"):
        retrieval_metrics(queries, candidates, ["a", "b"], contract(), repr)


def test_warmup_and_cosine_use_derived_optimizer_steps() -> None:
    model = torch.nn.Linear(1, 1)
    spec = {"training_scenes": 256, "effective_batch_scenes": 32, "optimizer": {
        "learning_rate": 1e-4, "weight_decay": 1e-4, "warmup_epochs": 10, "maximum_epochs": 200,
    }}
    optimizer, scheduler = make_optimizer(model, spec)
    applied = []
    for _ in range(81):
        applied.append(optimizer.param_groups[0]["lr"])
        optimizer.zero_grad(); model(torch.ones(1, 1)).sum().backward(); optimizer.step(); scheduler.step()
    assert applied[0] == pytest.approx(1e-4 / 80)
    assert applied[79] == pytest.approx(1e-4)
    assert applied[80] == pytest.approx(1e-4)
