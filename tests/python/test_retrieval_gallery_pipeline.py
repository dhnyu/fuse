"""Synthetic data-plane and fail-closed tests, never scientific production."""
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

import retrieval_gallery_pipeline as pipeline
from p10_evaluation import MODEL_IDS


def test_immutable_json_rejects_replacement(tmp_path):
    path = tmp_path / "record.json"
    pipeline.publish_json(path, {"a": 1})
    pipeline.publish_json(path, {"a": 1})
    with pytest.raises(ValueError, match="collision"):
        pipeline.publish_json(path, {"a": 2})


def test_acceptance_binds_all_parents_and_blocks_prohibited_work(tmp_path, monkeypatch):
    from jsonschema import ValidationError
    method = {"authority_id": "retrag_" + "a" * 24}
    monkeypatch.setattr(pipeline, "assert_frozen", lambda _: method)
    for relative in ("methodology.json", "index/supplemental_scene_index.parquet", "spatial_manifest.json",
            "cache/cache_manifest.json", "prepared/prepared_manifest.json", "geometry/geometry_manifest.json",
            "embeddings/embedding_manifest.json", "union/union_manifest.json", "rankings/ranking_manifest.json",
            "inspector/manifest.json"):
        pipeline.publish_json(tmp_path / relative, {"fixture": True})
    prohibited = {key: 0 for key in ("training", "fine_tuning", "checkpoint_reselection", "model_reselection",
        "p9_rerun", "canonical_p10_acceptance_mutation", "p11_rematerialization", "ridge_mlp_fitting",
        "target_transformation_changes", "canonical_evaluation_replacement", "dissertation_mutation")}
    validation = {"status": "PASS", "models": 8, "union_count": 10000, "prohibited_work": prohibited}
    path = pipeline.publish_json(tmp_path / "validation/validation.json", validation)
    accepted = pipeline.accept_production(path)
    assert pipeline.read(accepted)["acceptance_id"].startswith("retr10k_")
    assert len(pipeline.read(accepted)["parents_sha256"]) == 11
    assert pipeline.accept_production(path) == accepted
    validation["prohibited_work"]["training"] = 1
    import json
    path.write_text(json.dumps(validation))
    with pytest.raises(ValidationError):
        pipeline.accept_production(path)


def test_incomplete_pilots_cannot_authorize_production(tmp_path):
    evidence = tmp_path / "evidence.json"
    pipeline.publish_json(evidence, {"sampling_qc": str(tmp_path / "missing.json")})
    with pytest.raises(FileNotFoundError):
        pipeline.gate_pilots(Path(__file__).resolve().parents[2] / "config/retrieval_gallery.yml", evidence)


def test_failed_spatial_attempt_retries_identical_inputs_and_sealed_reuse(tmp_path, monkeypatch):
    root = tmp_path / "branch"
    job = {"root": str(root), "scenes": [{"scene_id": "fixture_b"}, {"scene_id": "fixture_a"}]}
    calls = []

    def worker(*args, **kwargs):
        calls.append(args)
        if len(calls) == 1:
            return SimpleNamespace(returncode=1)
        pipeline.publish_json(root / "spatial_result.json", {"status": "PASS", "scene_ids": ["fixture_a", "fixture_b"]})
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(pipeline.subprocess, "run", worker)
    with pytest.raises(RuntimeError, match="identical-input retry"):
        pipeline.spatial_job(job)
    assert pipeline.spatial_job(job)["status"] == "PASS"
    assert pipeline.verify_seal(root)["retry_count"] == 1
    assert (tmp_path / "branch.failed-0001/failed_attempt.json").is_file()
    assert pipeline.spatial_job(job)["status"] == "PASS"
    assert len(calls) == 2
    (root / "spatial_result.json").write_text("corrupt")
    with pytest.raises(ValueError, match="checksum"):
        pipeline.spatial_job(job)


def test_union_reuses_canonical_rows_and_old_cache_without_repacking(tmp_path, monkeypatch):
    root, old_root, p3 = tmp_path / "supplement", tmp_path / "p10", tmp_path / "p3"
    for path in (root / "index", root / "embeddings", root / "cache", p3 / "index/fixture"):
        path.mkdir(parents=True)
    old_ids = [f"canonical_{i:04d}" for i in range(1600)]
    new_ids = [f"retrscn_fixture_{i:04d}" for i in range(8400)]
    pq.write_table(pa.Table.from_pylist([{"scene_id": s, "center_x": float(i), "center_y": 1.0}
                                       for i, s in enumerate(new_ids)]), root / "index/supplemental_scene_index.parquet")
    pq.write_table(pa.Table.from_pylist([{"scene_id": s, "branch_id": "unchanged_branch", "payload_filename": "old.tar"}
                                       for s in old_ids]), p3 / "index/fixture/scene_to_shard.parquet")
    pipeline.publish_json(root / "cache/catalog.json", [{"scene_id": s, "payload_path": "new.tar"} for s in new_ids])
    canonical = np.full((1600, 128), 0.25, dtype=np.float32)
    new = np.full((8400, 128), 0.5, dtype=np.float32)
    bindings = [SimpleNamespace(configuration_id=m, checkpoint_id="frozen_checkpoint", acceptance_id="frozen_acceptance") for m in MODEL_IDS]
    before = {}
    for binding in bindings:
        folder = old_root / "execution_attempts/p10exec_7fee193dac532190c79e02c6/evaluations" / binding.configuration_id
        folder.mkdir(parents=True)
        pipeline.publish_json(folder / "evaluation.json", {"checkpoint_id": binding.checkpoint_id, "acceptance_id": binding.acceptance_id})
        path = folder / "evaluation_embeddings_ranks_analysis.npz"
        np.savez(path, embeddings=np.concatenate([np.zeros((3200, 128), dtype=np.float32), canonical]), centers=np.zeros((4800, 2)))
        before[path] = pipeline.digest(path)
        np.save(root / "embeddings" / (binding.configuration_id + ".npy"), new)
    monkeypatch.setattr(pipeline, "assert_frozen", lambda _: {})
    monkeypatch.setattr(pipeline, "load_contract", lambda _: {"publication_root": str(old_root), "inputs": {"p3_root": str(p3)}})
    monkeypatch.setattr(pipeline, "resolve_model_bindings", lambda _: bindings)
    monkeypatch.setattr(pipeline, "evaluation_population", lambda _: ([], [{"scene_id": s} for s in old_ids]))
    result = pipeline.union_production(root / "embeddings/embedding_manifest.json")
    assert pipeline.read(result)["total_count"] == 10000
    for model in MODEL_IDS:
        joined = np.load(result.parent / (model + ".npy"))
        assert joined[:1600].tobytes() == canonical.tobytes()
        assert joined[1600:].tobytes() == new.tobytes()
    assert all(pipeline.digest(p) == checksum for p, checksum in before.items())
    catalog = pipeline.read(result.parent / "union_catalog.json")
    assert catalog[0]["payload_path"] == str(p3 / "shards/unchanged_branch/old.tar")
    assert [row["scene_id"] for row in catalog] == old_ids + new_ids


def test_synthetic_eight_model_ten_query_ranking_artifacts(tmp_path, monkeypatch):
    rng = np.random.default_rng(260905)
    ids = [f"fixture_{i:05d}" for i in range(10000)]
    centers = rng.uniform(0, 30000, size=(10000, 2))
    vectors = rng.normal(size=(10000, 128)).astype(np.float32)
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
    root = tmp_path
    (root / "union").mkdir()
    for model in MODEL_IDS:
        np.save(root / "union" / (model + ".npy"), vectors, allow_pickle=False)
    gallery = [{"scene_id": sid, "center_x": float(x), "center_y": float(y)}
               for sid, (x, y) in zip(ids, centers)]
    pq.write_table(pa.Table.from_pylist(gallery), root / "union/gallery.parquet")
    pipeline.publish_json(root / "union/union_manifest.json", {"union_id": "NONSCIENTIFIC_FIXTURE"})
    canonical = {"qualitative_contract_sha256": "0" * 64,
                 "queries": [{"scene_id": sid} for sid in ids[:10]],
                 "models": {model: {"label": model} for model in MODEL_IDS}}

    def bands(n):
        start = (n - 10) // 2 + 1
        return {"most": [1], "top": list(range(2, 12)), "middle": list(range(start, start + 10)),
                "bottom": list(range(n - 9, n + 1))}

    monkeypatch.setattr(pipeline, "assert_frozen", lambda _: {})
    monkeypatch.setattr(pipeline, "import_script", lambda *_: SimpleNamespace(
        build_rank_manifest=lambda _: (canonical, set(ids[:10])), band_ranks=bands))
    path = pipeline.rankings_production(root / "union/union_manifest.json")
    result = pipeline.read(path)
    assert len(result["ranking_files"]) == 16
    assert len(pipeline.read(path.parent / "stability_diagnostics.json")) == 160
    for model in MODEL_IDS:
        for query in ids[:10]:
            assert result["models"][model]["queries"][query]["standard"]["candidate_count"] == 9999
        table = pq.read_table(path.parent / (model + "_nonlocal.parquet"))
        assert min(table["distance_m"].to_pylist()) >= 2000
    assert pipeline.rankings_production(root / "union/union_manifest.json") == path
