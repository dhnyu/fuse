from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "python"), str(ROOT / "scripts")]

from p7_cold_path_runtime import (load_runtime_config, required_memory_bytes, safe_cleanup_candidate,
                                  select_worker_tier, validate_staging_root)
import p7_cold_path_runtime_cli as runtime_cli
from p7_cold_path_runtime_cli import (EagerData, PROBLEM_VIEW, build_plan, digest,
                                      finalize_runtime_cache,
                                      publish_prepared_manifest, sha256_file,
                                      state_content_digest, validate_fixed_indices)
from p7_geometry_cache import GeometryCacheWriter


def test_fixed_index_coverage_rejects_missing_and_duplicate():
    validate_fixed_indices([{"global_index": 0}, {"global_index": 1}], 2)
    with pytest.raises(ValueError, match="missing or duplicate"):
        validate_fixed_indices([{"global_index": 0}], 2)
    with pytest.raises(ValueError, match="missing or duplicate"):
        validate_fixed_indices([{"global_index": 0}, {"global_index": 0}], 2)


def test_bounded_plan_is_canonical_and_contains_problem_candidate(tmp_path):
    first = build_plan(tmp_path / "first.json", 8)
    second = build_plan(tmp_path / "second.json", 8)
    assert first == second
    assert [row["global_index"] for row in first["entries"]] == list(range(8))
    assert len({row["lookup_key"] for row in first["entries"]}) == 8
    assert any(PROBLEM_VIEW in row["lookup_key"] for row in first["entries"])


def _write_payload(path: Path, index: int, sample: dict):
    torch.save({"global_index": index, "sample": sample,
                "sample_digest": state_content_digest(sample)}, path)


def test_eager_data_exact_lookup_and_corruption_rejection(tmp_path):
    prepared = tmp_path / "prepared"
    prepared.mkdir()
    training = {"value": torch.tensor([1.0])}; query = {"value": torch.tensor([2.0])}; gallery = {"value": torch.tensor([3.0])}
    samples = [training, query, gallery]
    entries = [
        {"global_index": 0, "lookup_key": "training\0s\0v", "spec": ["training", "s", 7]},
        {"global_index": 1, "lookup_key": "validation_query\0q\0fq", "spec": ["validation_query", "q", 0]},
        {"global_index": 2, "lookup_key": "validation_gallery\0q\0original", "spec": ["validation_gallery", "q", None]},
    ]
    rows = []
    for index, sample in enumerate(samples):
        path = prepared / f"{index:06d}.pt"
        _write_payload(path, index, sample)
        rows.append({"global_index": index, "lookup_key": entries[index]["lookup_key"], "cache_key": f"cache-{index}",
                     "sample_digest": state_content_digest(sample), "payload_size_bytes": path.stat().st_size,
                     "payload_sha256": sha256_file(path)})
    plan = {"entry_count": 3, "entries": entries}
    plan["plan_sha256"] = digest(plan)
    publish_prepared_manifest(plan, rows, tmp_path / "prepared_manifest.json")
    base = SimpleNamespace(members={"training": ["s"]}, catalog=object())
    eager = EagerData(base, plan, prepared)
    assert torch.equal(eager.training_view("s", 7)["value"], training["value"])
    assert torch.equal(eager.validation_query("q", 0)["value"], query["value"])
    assert torch.equal(eager.validation_gallery("q")["value"], gallery["value"])
    payload = torch.load(prepared / "000001.pt", weights_only=False); payload["sample"]["value"][0] = 9
    torch.save(payload, prepared / "000001.pt")
    with pytest.raises(ValueError, match="checksum|corruption"):
        EagerData(base, plan, prepared)


def test_eager_data_rejects_incomplete_prepared_manifest(tmp_path):
    prepared = tmp_path / "prepared"
    prepared.mkdir()
    sample = {"value": torch.tensor([1.0])}
    _write_payload(prepared / "000000.pt", 0, sample)
    entries = [{"global_index": 0, "lookup_key": "training\0s\0v", "spec": ["training", "s", 7]}]
    plan = {"entry_count": 1, "entries": entries}
    plan["plan_sha256"] = digest(plan)
    base = SimpleNamespace(members={"training": ["s"]}, catalog=object())
    with pytest.raises(FileNotFoundError):
        EagerData(base, plan, prepared)


def runtime_config():
    return load_runtime_config(ROOT / "config/p7_cold_path_runtime.yml")


def test_memory_admission_selects_and_falls_back_without_unsafe_override():
    cfg = runtime_config()
    required = {tier: required_memory_bytes(cfg, tier) for tier in (32, 24, 16)}
    assert select_worker_tier(cfg, required[32] + 1)["selected_workers"] == 32
    assert select_worker_tier(cfg, required[32] - 1)["selected_workers"] == 24
    assert select_worker_tier(cfg, required[24] - 1)["selected_workers"] == 16
    with pytest.raises(MemoryError): select_worker_tier(cfg, required[16] - 1)
    with pytest.raises(ValueError): select_worker_tier(cfg, required[32] * 2, requested_workers=40)
    with pytest.raises(RuntimeError, match="swap-in"): select_worker_tier(cfg, required[32] * 2, swap_in_delta_bytes=1)


def test_runtime_contract_enforces_spawn_two_producers_and_batch_one():
    cfg = runtime_config()
    assert cfg["cpu_preparation"]["start_method"] == "spawn"
    assert cfg["cpu_preparation"]["worker_tiers"] == [32, 24, 16]
    assert cfg["gpu_producers"] == {"producer_count": 2, "batch_size": 1,
                                     "assignment": "canonical_index_modulo_2", "rank_to_device": [0, 1]}
    assert [index % 2 for index in range(8)] == [0, 1, 0, 1, 0, 1, 0, 1]


def test_cpu_worker_rejects_an_initialized_cuda_context(monkeypatch, tmp_path):
    monkeypatch.setattr(torch.cuda, "is_initialized", lambda: True)
    with pytest.raises(RuntimeError, match="CUDA"):
        runtime_cli.cpu_initializer(str(tmp_path))


def test_worker_thread_limits_are_one(monkeypatch):
    monkeypatch.setattr(torch, "set_num_threads", lambda value: None)
    runtime_cli.thread_limits()
    for name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
                 "NUMEXPR_NUM_THREADS", "GDAL_NUM_THREADS", "ARROW_NUM_THREADS"):
        assert runtime_cli.os.environ[name] == "1"


def test_staging_admission_and_cleanup_are_exact_namespace_only(tmp_path):
    cfg = runtime_config(); cfg["disk_staging"]["prohibited_roots"] = [str(tmp_path / "accepted")]
    allowed = tmp_path / "staging" / "run-1"
    assert validate_staging_root(allowed, cfg)["required_bytes"] > 0
    allowed.mkdir(parents=True)
    assert safe_cleanup_candidate(allowed, allowed.parent, "run-1") == allowed.resolve()
    with pytest.raises(ValueError, match="unsafe"): safe_cleanup_candidate(allowed, allowed.parent, "run-2")
    (allowed / "COMPLETE.json").write_text("{}")
    with pytest.raises(ValueError, match="completed"): safe_cleanup_candidate(allowed, allowed.parent, "run-1")
    with pytest.raises(ValueError, match="overlaps"):
        validate_staging_root(tmp_path / "accepted" / "child", cfg)


def test_runtime_cache_finalization_is_complete_and_no_rewrite(tmp_path):
    record = {"cache_schema_version": "3.0.0", "geometry_layout_version": "3.0.0",
              "cache_key": "a" * 64, "identity": {"role": "training"},
              "lookup_key": "training\0s\0v"}
    writer = GeometryCacheWriter(tmp_path)
    writer.put(record, torch.tensor([[1.0]]), torch.tensor([[2.0]]))
    first = finalize_runtime_cache(tmp_path, "p7a_test", [record])
    paths = [tmp_path / "geometry_cache_manifest.json", tmp_path / "COMPLETE.json"]
    before = [(path.stat().st_mtime_ns, sha256_file(path)) for path in paths]
    second = finalize_runtime_cache(tmp_path, "p7a_test", [record])
    after = [(path.stat().st_mtime_ns, sha256_file(path)) for path in paths]
    assert first == second
    assert before == after


def test_runtime_cache_rejects_partial_publication(tmp_path):
    (tmp_path / "geometry_cache_manifest.json").write_text("{}")
    with pytest.raises(ValueError, match="partial"):
        finalize_runtime_cache(tmp_path, "p7a_test", [])
