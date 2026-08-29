from __future__ import annotations

import copy
import json
import math
import sys
from pathlib import Path

import jsonschema
import pytest
import torch
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from p7_training import (ExactLRScheduler, canonical_digest, derive_seed, empty_queue, enqueue,
                         epoch_scene_order, learning_rate, load_config, modality_assignments, replay_selector,
                         scientific_config, seed_payload, selected_view_pair, selector_decision,
                         state_content_digest)


def config():
    return load_config(ROOT / "config/p7_deterministic_training.yml")


def test_supplement_and_all_p7_schemas_parse():
    value = yaml.safe_load((ROOT / "config/p7_deterministic_training.yml").read_text())
    schema = json.loads((ROOT / "config/schemas/p7_deterministic_training_supplement.schema.json").read_text())
    jsonschema.Draft202012Validator(schema).validate(value)
    schema_paths = sorted((ROOT / "config/schemas").glob("p7_*.schema.json"))
    assert len(schema_paths) == 11
    assert {path.name for path in schema_paths} >= {
        "p7_cold_path_runtime_contract.schema.json",
        "p7_cold_path_runtime_acceptance.schema.json",
    }
    for path in schema_paths:
        candidate = json.loads(path.read_text())
        jsonschema.Draft202012Validator.check_schema(candidate)
        if candidate.get("additionalProperties") is False:
            assert set(candidate.get("required", ())) <= set(candidate.get("properties", {}))


def test_exact_scheduler_boundaries_and_restore():
    expected = {
        1: 1.25e-5,
        79: 0.001 * 79 / 80,
        80: 0.001,
        81: 0.5e-3 * (1 + math.cos(math.pi / 1520)),
        1599: 0.5e-3 * (1 + math.cos(math.pi * 1519 / 1520)),
        1600: 0.0,
    }
    for update, value in expected.items():
        assert learning_rate(update) == pytest.approx(value, rel=0, abs=1e-18)
    parameter = torch.nn.Parameter(torch.tensor(1.0)); optimizer = torch.optim.AdamW([parameter], lr=0)
    scheduler = ExactLRScheduler(optimizer, 79)
    assert scheduler.set_for_next_update() == 0.001
    scheduler.advance(); state = scheduler.state_dict()
    restored = ExactLRScheduler(optimizer); restored.load_state_dict(state)
    assert restored.completed_updates == 80
    assert restored.set_for_next_update() == learning_rate(81)
    with pytest.raises(ValueError): ExactLRScheduler(optimizer).load_state_dict({"completed_updates": 2, "next_update": 2})


def test_seed_payload_is_canonical_and_role_rank_epoch_separated():
    cfg = config(); payload = seed_payload(cfg, "dropout", epoch=3, global_rank=1, worker_id=0, operation="forward")
    assert list(payload) == ["schema_version", "supplement_name", "root_run_seed", "p6_aggregate_acceptance_id",
                             "prototype_selection_id", "role", "epoch", "global_rank", "worker_id", "stochastic_operation"]
    seed = derive_seed(cfg, "dropout", epoch=3, global_rank=1, worker_id=0, operation="forward")
    assert seed == derive_seed(cfg, "dropout", epoch=3, global_rank=1, worker_id=0, operation="forward")
    assert seed != derive_seed(cfg, "dropout", epoch=3, global_rank=0, worker_id=0, operation="forward")
    assert seed != derive_seed(cfg, "view", epoch=3, global_rank=1, worker_id=0, operation="forward")
    assert 0 <= seed < 2**63


def test_global_sampler_and_k8_view_pair_contract():
    cfg = config(); scenes = [f"scene-{index:03d}" for index in range(256)]
    first = epoch_scene_order(scenes, cfg, 1)
    assert first == epoch_scene_order(list(reversed(scenes)), cfg, 1)
    assert first != epoch_scene_order(scenes, cfg, 2)
    assert sorted(first) == sorted(scenes) and len(first) == len(set(first)) == 256
    pair = selected_view_pair("scene-001", list(reversed(range(8))), cfg, 1)
    assert pair == selected_view_pair("scene-001", range(8), cfg, 1)
    assert pair[0] != pair[1] and set(pair) <= set(range(8))
    with pytest.raises(ValueError, match="logical K8"): selected_view_pair("scene-001", range(7), cfg, 1)


def test_modality_mask_substream_is_rank_separated():
    cfg = config()
    batch = {
        "scene_ids": ["scene-001"], "scene_ptr": torch.tensor([0, 128]),
        "entities": {"entity_type": torch.zeros(128, dtype=torch.int64),
                     "local_entity_id": torch.arange(128),
                     "modality_available": torch.ones((128, 4), dtype=torch.bool)},
    }
    rank0 = modality_assignments(batch, cfg, epoch=3, view_role=0, global_rank=0)
    rank1 = modality_assignments(batch, cfg, epoch=3, view_role=0, global_rank=1)
    assert not torch.equal(rank0, rank1)
    assert torch.equal(rank0, modality_assignments(batch, cfg, epoch=3, view_role=0, global_rank=0))


def test_queue_empty_partial_fill_wraparound_and_order():
    queue = empty_queue(torch.device("cpu"), capacity=4, dimension=2)
    assert queue["pointer"] == queue["valid_count"] == queue["enqueue_count"] == 0
    assert torch.count_nonzero(queue["values"]) == 0
    enqueue(queue, torch.tensor([[1., 0.], [2., 0.], [3., 0.]]), torch.tensor([10, 11, 12]), torch.zeros((3, 2)))
    assert (queue["pointer"], queue["valid_count"], queue["enqueue_count"]) == (3, 3, 3)
    enqueue(queue, torch.tensor([[4., 0.], [5., 0.], [6., 0.]]), torch.tensor([13, 14, 15]), torch.zeros((3, 2)))
    assert (queue["pointer"], queue["valid_count"], queue["enqueue_count"]) == (2, 4, 6)
    assert queue["values"][:, 0].tolist() == [5., 6., 3., 4.]
    assert queue["scene_ids"].tolist() == [14, 15, 12, 13]


def event(epoch, loss, margin):
    return {"epoch": epoch, "validation_retrieval_loss": loss, "mean_source_separation_margin": margin}


def test_selector_threshold_margin_tie_and_patience():
    best = event(5, 1.0, 0.1)
    assert selector_decision(best, event(10, 0.9998, -1.0))
    assert selector_decision(best, event(10, 1.00005, 0.2))
    assert not selector_decision(best, event(10, 1.00005, 0.05))
    assert not selector_decision(best, event(10, 1.0, 0.1))
    selected, patience = replay_selector([best, event(10, 1.0002, 1.0), event(15, 1.0003, 2.0),
                                          event(20, 1.0004, 3.0), event(25, 1.0005, 4.0)])
    assert selected["epoch"] == 5 and patience == 4


def test_scientific_identity_excludes_operational_paths_and_workers():
    cfg = config(); changed = copy.deepcopy(cfg)
    changed["publication_root"] = "/different"; changed["staging_root"] = "/elsewhere"
    changed["runtime"]["dataloader_workers_per_rank"] = 99
    changed["runtime"]["selected_gpu_indices"] = [7, 8]
    changed["runtime"]["nccl_p2p_disable"] = False
    changed["runtime"]["nccl_ib_disable"] = False
    assert canonical_digest(scientific_config(cfg)) == canonical_digest(scientific_config(changed))
    changed["optimizer"]["weight_decay"] = 0.0
    assert canonical_digest(scientific_config(cfg)) != canonical_digest(scientific_config(changed))


def test_state_digest_is_mapping_order_stable_and_tensor_sensitive():
    left = {"b": torch.tensor([1., 2.]), "a": {"x": 1}}
    right = {"a": {"x": 1}, "b": torch.tensor([1., 2.])}
    assert state_content_digest(left) == state_content_digest(right)
    right["b"][1] = 3
    assert state_content_digest(left) != state_content_digest(right)


def test_config_adversarial_rejects_amp_world_size_and_optimizer_change(tmp_path):
    raw = yaml.safe_load((ROOT / "config/p7_deterministic_training.yml").read_text())
    for mutate in (
        lambda value: value["numeric"].__setitem__("amp", True),
        lambda value: value["training"].__setitem__("world_size", 1),
        lambda value: value["optimizer"].__setitem__("betas", [0.8, 0.9]),
    ):
        changed = copy.deepcopy(raw); mutate(changed)
        path = tmp_path / (canonical_digest(changed) + ".yml"); path.write_text(yaml.safe_dump(changed))
        with pytest.raises(ValueError): load_config(path)
