import sys
from pathlib import Path

import numpy as np
import torch
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "python"))

from prototype_encoder import _geometry_frequencies, _triangle_fourier, _triangle_fourier_batched
from run_prototype_training_ddp import RankLogicalGroupSampler, RankSceneSampler


def test_scene_sampler_preserves_rank_microbatch_order_and_boundaries():
    rows = [
        {
            "scene_id": f"scene-{index:02d}", "node_count": 1,
            "ordered_edge_count": 1, "coordinate_count": 1,
            "actual_payload_bytes": 1,
        }
        for index in range(32)
    ]
    budgets = {"scenes": 8, "nodes": 8, "ordered_edges": 8, "coordinates": 8, "actual_payload_bytes": 8}
    grouped = RankLogicalGroupSampler(rows, budgets, seed=20260822, rank=0)
    batches = grouped.batches()
    assert list(RankSceneSampler(grouped)) == [task for batch in batches for task in batch]
    assert len(RankSceneSampler(grouped)) == sum(map(len, batches)) == 16


def test_ordered_vectorized_triangle_fourier_is_bitwise_legacy_equivalent():
    triangles = np.asarray([
        [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]],
        [[0.0, 0.0], [1.0, 1.0], [0.0, 1.0]],
        [[-0.2, 0.1], [0.7, -0.1], [0.3, 0.8]],
    ], dtype=np.float64)
    frequencies = torch.tensor([[0.01, 0.0], [0.1, 0.2], [-0.3, 0.4]], dtype=torch.float32)
    assert torch.equal(_triangle_fourier(triangles, frequencies), _triangle_fourier_batched(triangles, frequencies))


def test_i21_runtime_keeps_40_workers_prefetch_four_and_resident_frequencies():
    config = yaml.safe_load(Path("config/prototype_training.yml").read_text())
    assert config["execution"]["workers"] == 40
    assert config["execution"]["workers_per_rank"] == 20
    assert config["execution"]["native_threads_per_worker"] == 1
    assert config["execution"]["prefetch_factor"] == 4
    source = Path(config["execution"]["archive_source_root"])
    runtime = Path(config["execution"]["archive_runtime_root"])
    assert source != runtime
    assert str(runtime).startswith("/members/dhnyu/fuse_runtime_mirror/")
    assert config["execution"]["archive_runtime_identity"] == "excluded_execution_only"
    encoder = yaml.safe_load(Path("config/model_architecture.yml").read_text())
    first = _geometry_frequencies(encoder, torch.device("cpu"))
    assert _geometry_frequencies(encoder, torch.device("cpu")) is first
