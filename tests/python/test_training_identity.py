"""Focused non-formal tests for P9 identity failure evidence and accounting."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import torch

from training_support import empty_queue, local_infonce_sum
from training_identity import SceneIdentityLookupError, assemble_rank_manifest


def tensors(ids: list[int]) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
    rows = len(ids)
    return (torch.ones((rows, 4)), torch.ones((rows, 4)), torch.zeros((rows, 2)), torch.tensor(ids))


def test_valid_identity_path_is_numerically_stable() -> None:
    q1, q2, centers, ids = tensors([10, 20])
    queue = empty_queue(torch.device("cpu"), capacity=4, dimension=4)
    before = local_infonce_sum(q1, q2, q1, q2, centers, centers, ids, ids, queue, 0.2, 0.0)
    after = local_infonce_sum(q1, q2, q1, q2, centers, centers, ids, ids, queue, 0.2, 0.0)
    assert before[1] == after[1] == 4
    assert torch.equal(before[0], after[0])


@pytest.mark.parametrize(("local", "global_ids", "classification"), [
    ([10], [20], "CURRENT_BATCH_ID_MISSING"),
    ([10], [10, 10], "CURRENT_BATCH_ID_DUPLICATE"),
])
def test_lookup_failures_are_classified_and_atomically_captured(tmp_path: Path, local: list[int], global_ids: list[int], classification: str) -> None:
    q1, q2, centers, _ = tensors(global_ids)
    queue = empty_queue(torch.device("cpu"), capacity=4, dimension=4)
    context = {"diagnostic_root": str(tmp_path), "rank": 0, "world_size": 2,
               "epoch": 16, "batch_index": 0, "attempt_id": "synthetic"}
    with pytest.raises(SceneIdentityLookupError, match=classification):
        local_infonce_sum(q1[:1], q2[:1], q1, q2, centers[:1], centers, torch.tensor(local),
                          torch.tensor(global_ids), queue, 0.2, 0.0, context)
    row = json.loads((tmp_path / "rank-0.json").read_text())
    assert row["classification"] == classification
    assert row["first_failing_id"] == 10


def test_gather_length_and_queue_alignment_fail_closed() -> None:
    q1, q2, centers, ids = tensors([10, 20])
    queue = empty_queue(torch.device("cpu"), capacity=4, dimension=4)
    with pytest.raises(SceneIdentityLookupError, match="GATHER_LENGTH_MISMATCH"):
        local_infonce_sum(q1, q2, q1[:1], q2[:1], centers, centers, ids, ids, queue, 0.2, 0.0)
    queue["centers"] = queue["centers"][:3]
    with pytest.raises(SceneIdentityLookupError, match="QUEUE_ALIGNMENT_MISMATCH"):
        local_infonce_sum(q1, q2, q1, q2, centers, centers, ids, ids, queue, 0.2, 0.0)


def test_partial_and_complete_rank_manifests(tmp_path: Path) -> None:
    (tmp_path / "rank-0.json").write_text(json.dumps({"rank": 0, "classification": "CURRENT_BATCH_ID_MISSING"}))
    assert assemble_rank_manifest(tmp_path, 2)["completeness"] == "PARTIAL"
    (tmp_path / "rank-1.json").write_text(json.dumps({"rank": 1, "classification": "CURRENT_BATCH_ID_MISSING"}))
    assert assemble_rank_manifest(tmp_path, 2)["completeness"] == "COMPLETE"
