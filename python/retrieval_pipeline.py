"""Formal S10 orchestration and acceptance, isolated from S11 evaluation lifecycle."""
from pathlib import Path
import io
import os
import sys
import time
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import yaml

from retrieval_artifacts import require, load, publish, publish_bytes, file_hash, digest
from retrieval_lineage import config, runtime, inventory, population, OriginalCatalog, ROOT
from retrieval_ranking import sample_queries, rank, check_embeddings, OFAT, COMPARISON

GUARDRAILS = {"training": False, "optimizer_used": False, "checkpoint_mutation": False,
    "s11_execution": False, "historical_embedding_adoption": False, "model_selection": False,
    "hyperparameter_retuning": False, "s11_protocol_changes": False}


def model_manifest(cfg):
    body = inventory(cfg)
    body.update({"runtime": runtime(cfg), "config": cfg, "scope": "formal", "guardrails": GUARDRAILS})
    body["runtime_id"] = body["runtime"]["runtime_id"]
    body["generation_id"] = "s10gen_" + digest({"campaign": cfg["campaign_sha256"],
        "config": cfg, "runtime": body["runtime_id"]})[:24]
    root = Path(cfg["publication_root"]) / body["generation_id"]
    return publish(root / "model_manifest.json", "models", body)


def context(models):
    body = models["body"]
    return {k: body[k] for k in ("generation_id", "runtime_id", "scope")}


def common(model_path, gallery_path, query_path=None):
    m, g = load(model_path, "models"), load(gallery_path, "gallery")
    require(all(g["body"][k] == v for k, v in context(m).items()), "GALLERY_RUNTIME_BINDING")
    require(g["body"]["model_manifest_id"] == m["artifact_id"], "GALLERY_MODEL_BINDING")
    if query_path is None:
        return m, g
    q = load(query_path, "queries")
    require(q["body"]["seed"] == m["body"]["config"]["query_seed"], "QUERY_SEED_BINDING")
    require(q["body"]["gallery_manifest_id"] == g["artifact_id"] and
            q["body"]["model_manifest_id"] == m["artifact_id"], "QUERY_MANIFEST_BINDING")
    require(all(q["body"][k] == v for k, v in context(m).items()), "QUERY_RUNTIME_BINDING")
    require(q["body"]["rows"] == sample_queries(g["body"]["rows"], q["body"]["seed"],
            len(q["body"]["rows"]), len(g["body"]["rows"])), "QUERY_SELECTION")
    return m, g, q


def gallery_manifest(model_path):
    m = load(model_path, "models")
    rows, source = population(m["body"]["config"], m["body"])
    return publish(Path(model_path).parent / "gallery_manifest.json", "gallery",
        {**context(m), "model_manifest_id": m["artifact_id"], "source": source,
         "source_manifest_identity": digest(source), "rows": rows, "crs": "EPSG:5186", "units": "metres"})


def query_manifest(model_path, gallery_path):
    m, g = common(model_path, gallery_path)
    cfg = m["body"]["config"]
    rows = sample_queries(g["body"]["rows"], cfg["query_seed"], cfg["query_count"], cfg["gallery_count"])
    return publish(Path(model_path).parent / "query_manifest.json", "queries",
        {**context(m), "model_manifest_id": m["artifact_id"], "gallery_manifest_id": g["artifact_id"],
         "source_manifest_identity": g["body"]["source_manifest_identity"], "seed": cfg["query_seed"],
         "algorithm": "PCG64.choice_without_replacement_sorted_scene_ids_preserve_draw_order",
         "top_k": cfg["top_k"], "rows": rows})


def bindings(m, g, q):
    return {**context(m), "model_manifest_id": m["artifact_id"], "query_manifest_id": q["artifact_id"],
            "gallery_manifest_id": g["artifact_id"]}


def original_inputs(model_path, gallery_path, query_path):
    """Prepare common original tensors once, independently of model or retrieval result."""
    import torch
    from model_data import read_original_scene, tensorize_scene, build_vocabulary
    from retrieval_artifacts import read_json
    m, g, q = common(model_path,gallery_path,query_path)
    cfg = m["body"]["config"]
    if m["body"]["scope"] == "formal":
        require(os.environ.get("FUSE_S10_FULL_AUTHORIZED") == "1", "FULL_PREPARATION_NOT_AUTHORIZED")
    else:
        require(len(g["body"]["rows"]) <= 16, "SMOKE_SCOPE")
    root = Path(model_path).parent / "original_inputs"
    if (root / "manifest.json").exists():
        existing = load(root / "manifest.json", "original_inputs")
        require(all(existing["body"][k] == v for k,v in bindings(m,g,q).items()), "PREPARED_BINDING")
        return str(root / "manifest.json")
    roots = m["body"]["roots"]
    training = yaml.safe_load(Path(cfg["training_config"]).read_text())
    catalog = OriginalCatalog(roots,training)
    preprocessing = read_json(roots["preprocessing"])
    vocab = build_vocabulary(roots["categories"])
    samples, files = [], []
    for row in g["body"]["rows"]:
        scene = read_original_scene(catalog,row["scene_id"])
        require(scene["split"] == "evaluation" and np.array_equal(scene["center"],[row["center_x"],row["center_y"]]), "SCENE_CENTER_BINDING")
        sample = tensorize_scene(scene,preprocessing,vocab)
        sample["scene_center_5186"] = torch.tensor(scene["center"],dtype=torch.float64)
        buffer = io.BytesIO()
        torch.save(sample,buffer)
        filename = row["scene_id"] + ".pt"
        files.append(publish_bytes(root/filename,buffer.getvalue()))
        samples.append({"scene_id": row["scene_id"], "path": filename})
    return publish(root/"manifest.json", "original_inputs", {**bindings(m,g,q),
        "samples": samples, "preprocessing_sha256": file_hash(roots["preprocessing"]),
        "categories_sha256": file_hash(roots["categories"])}, files)


def embeddings(model_path, gallery_path, query_path, model_id, prepared_path=None):
    from retrieval_inference import infer
    m, g, q = common(model_path, gallery_path, query_path)
    cfg = m["body"]["config"]
    if m["body"]["scope"] == "formal":
        require(os.environ.get("FUSE_S10_FULL_AUTHORIZED") == "1", "FULL_INFERENCE_NOT_AUTHORIZED")
    else:
        require(len(g["body"]["rows"]) <= 16 and len(m["body"]["models"]) <= 2 and
                len(q["body"]["rows"]) <= 2 and not Path(model_path).resolve().is_relative_to(Path(config("config/retrieval_visualization.yml")["publication_root"])), "SMOKE_SCOPE")
    model = next(r for r in m["body"]["models"] if r["configuration_id"] == model_id)
    start = time.monotonic()
    require(prepared_path is not None, "PREPARED_INPUT_REQUIRED")
    prepared = load(prepared_path, "original_inputs")
    require(all(prepared["body"][k] == v for k,v in bindings(m,g,q).items()) and
            [r["scene_id"] for r in prepared["body"]["samples"]] == [r["scene_id"] for r in g["body"]["rows"]], "PREPARED_BINDING")
    vectors = infer(cfg, model, m["body"]["roots"], g["body"]["rows"], prepared_path)
    check_embeddings(vectors, len(g["body"]["rows"]))
    output = Path(model_path).parent / "embeddings" / model_id
    buffer = io.BytesIO()
    np.save(buffer, vectors, allow_pickle=False)
    payload = publish_bytes(output / "vectors.npy", buffer.getvalue())
    # Wall time is operational telemetry only, never part of immutable identity.
    print(f'S10 inference {model_id}: {len(vectors)} scenes in {time.monotonic()-start:.3f}s', file=sys.stderr)
    return publish(output / "manifest.json", "embeddings", {**bindings(m, g, q), "model": model,
        "scene_ids": [r["scene_id"] for r in g["body"]["rows"]], "shape": list(vectors.shape),
        "dtype": str(vectors.dtype), "guardrails": GUARDRAILS,
        "prepared_manifest": str(prepared_path), "prepared_manifest_id": prepared["artifact_id"]}, [payload])


def rankings(model_path, gallery_path, query_path, embedding_path):
    m, g, q = common(model_path, gallery_path, query_path)
    e = load(embedding_path, "embeddings")
    b = bindings(m, g, q)
    require(all(e["body"][k] == v for k, v in b.items()), "EMBEDDING_BINDING")
    require(e["body"]["model"] in m["body"]["models"] and e["body"]["scene_ids"] == [r["scene_id"] for r in g["body"]["rows"]], "EMBEDDING_MODEL_GALLERY")
    vectors = np.load(Path(embedding_path).parent / e["files"][0]["path"], allow_pickle=False)
    rows = rank(vectors, g["body"]["rows"], q["body"]["rows"], e["body"]["model"], b, m["body"]["config"]["top_k"])
    output = Path(model_path).parent / "rankings" / e["body"]["model"]["configuration_id"]
    sink = pa.BufferOutputStream()
    pq.write_table(pa.Table.from_pylist(rows), sink, compression="zstd")
    payload = publish_bytes(output / "rankings.parquet", sink.getvalue().to_pybytes())
    return publish(output / "manifest.json", "rankings", {**b, "model": e["body"]["model"],
        "embedding_manifest": str(embedding_path), "embedding_manifest_id": e["artifact_id"],
        "rows": len(rows), "top_k": m["body"]["config"]["top_k"]}, [payload])


def validate_rankings(model_path, gallery_path, query_path, ranking_paths):
    m, g, q = common(model_path, gallery_path, query_path)
    cfg = m["body"]["config"]
    require(len(ranking_paths) == len(m["body"]["models"]), "MODEL_RESULT_COUNT")
    seen, result = set(), []
    for path in ranking_paths:
        r = load(path, "rankings")
        b = bindings(m, g, q)
        require(all(r["body"][k] == v for k, v in b.items()), "RANKING_BINDING")
        model = r["body"]["model"]
        require(model in m["body"]["models"] and model["configuration_id"] not in seen, "MODEL_RESULT_IDENTITY")
        seen.add(model["configuration_id"])
        ep = Path(r["body"]["embedding_manifest"])
        e = load(ep, "embeddings")
        prepared = load(e["body"]["prepared_manifest"], "original_inputs")
        require(prepared["artifact_id"] == e["body"]["prepared_manifest_id"] and
                all(prepared["body"][k] == v for k,v in b.items()), "PREPARED_BINDING")
        require(e["artifact_id"] == r["body"]["embedding_manifest_id"] and e["body"]["model"] == model and
                all(e["body"][k] == v for k, v in b.items()) and
                e["body"]["scene_ids"] == [row["scene_id"] for row in g["body"]["rows"]], "EMBEDDING_BINDING")
        actual = pq.read_table(Path(path).parent / r["files"][0]["path"]).to_pylist()
        expected = rank(np.load(ep.parent / e["files"][0]["path"], allow_pickle=False),
            g["body"]["rows"], q["body"]["rows"], model, b, cfg["top_k"])
        require(actual == expected and r["body"]["rows"] == len(expected), "RANKING_CONTENT")
        result.extend(actual)
    return result


def render_cache(model_path, gallery_path, query_path, ranking_paths):
    from model_data import read_original_scene
    from retrieval_render import render_scene
    m, g, q = common(model_path, gallery_path, query_path)
    rows = validate_rankings(model_path, gallery_path, query_path, ranking_paths)
    scenes = sorted({r["gallery_scene_id"] for r in rows if r["rank"] <= 5} | {r["scene_id"] for r in q["body"]["rows"]})
    catalog = OriginalCatalog(m["body"]["roots"], yaml.safe_load(Path(m["body"]["config"]["training_config"]).read_text()))
    output = Path(model_path).parent / "renders"
    rendered = [render_scene(read_original_scene(catalog, scene),
        catalog.p3_by_scene[scene]["payload_sha256"], output) for scene in scenes]
    return publish(output / "manifest.json", "renders", {**bindings(m, g, q), "scenes": rendered},
                   [r["path"] for r in rendered])


def comparison_pages(model_path, gallery_path, query_path, ranking_paths, render_path):
    sys.path.insert(0, str(ROOT / "tools/retrieval_inspector"))
    from viewer import pages
    m, g, q = common(model_path, gallery_path, query_path)
    validate_rankings(model_path, gallery_path, query_path, ranking_paths)
    render = load(render_path, "renders")
    require(all(render["body"][k] == v for k, v in bindings(m, g, q).items()), "RENDER_BINDING")
    root = Path(model_path).parent / "pages"
    paths = pages(query_path, model_path, ranking_paths, render_path, root)
    return publish(root / "manifest.json", "pages", {**bindings(m, g, q),
        "render_manifest": str(render_path), "render_manifest_id": render["artifact_id"],
        "query_page_count": len(q["body"]["rows"]), "viewer_science": "READ_ONLY_NO_FALLBACK"}, paths)


def summary(model_path, gallery_path, query_path, ranking_paths, pages_path):
    m, g, q = common(model_path, gallery_path, query_path)
    rows = validate_rankings(model_path, gallery_path, query_path, ranking_paths)
    p = load(pages_path, "pages")
    return publish(Path(model_path).parent / "summary.json", "summary", {**bindings(m, g, q),
        "models": len(m["body"]["models"]), "queries": len(q["body"]["rows"]),
        "gallery": len(g["body"]["rows"]), "ranking_rows": len(rows),
        "pages_manifest_id": p["artifact_id"], "guardrails": GUARDRAILS})


def acceptance(model_path, gallery_path, query_path, ranking_paths, pages_path, summary_path):
    m, g, q = common(model_path, gallery_path, query_path)
    rows = validate_rankings(model_path, gallery_path, query_path, ranking_paths)
    p, s = load(pages_path, "pages"), load(summary_path, "summary")
    cfg = m["body"]["config"]
    require([len(m["body"]["models"]), len(g["body"]["rows"]), len(q["body"]["rows"])] ==
            [cfg["model_count"], cfg["gallery_count"], cfg["query_count"]], "FORMAL_COUNTS")
    require(len(rows) == cfg["model_count"] * cfg["query_count"] * 2 * cfg["top_k"], "RANKING_COUNT")
    if m["body"]["scope"] == "formal":
        require((cfg["model_count"], cfg["gallery_count"], cfg["query_count"], cfg["top_k"]) == (28,9000,30,50), "FORMAL_COUNTS")
        require([r["configuration_id"] for r in m["body"]["models"]] == list(OFAT) + ["cmp_" + n for n in COMPARISON], "MODEL_INVENTORY")
        current = inventory(config("config/retrieval_visualization.yml"))
        require(current["models"] == m["body"]["models"], "ACCEPTANCE_LINEAGE_CHANGED")
        canonical_rows, canonical_source = population(cfg, current)
        require(g["body"]["rows"] == canonical_rows and g["body"]["source"] == canonical_source and
                g["body"]["source_manifest_identity"] == digest(canonical_source) and
                g["body"]["crs"] == "EPSG:5186" and g["body"]["units"] == "metres", "CANONICAL_GALLERY_BINDING")
    for path, checksum in {**m["body"]["evidence"], **cfg["source_pins"]}.items():
        require(file_hash(path) == checksum, "SCIENTIFIC_SOURCE_MUTATED")
    for model in m["body"]["models"]:
        require(file_hash(model["payload"]) == model["payload_sha256"], "CHECKPOINT_MUTATED")
    require(runtime(cfg)["runtime_id"] == m["body"]["runtime_id"], "RUNTIME_CHANGED")
    for doc in (p,s):
        require(all(doc["body"][k] == v for k,v in bindings(m,g,q).items()), "PUBLICATION_BINDING")
    require(s["body"]["pages_manifest_id"] == p["artifact_id"] and s["body"]["ranking_rows"] == len(rows), "SUMMARY_BINDING")
    page_names = {Path(r["path"]).name for r in p["files"]}
    require({f'query_{i:02d}.html' for i in range(1,cfg["query_count"]+1)} <= page_names and p["body"]["query_page_count"] == cfg["query_count"], "PAGES_INCOMPLETE")
    render = load(p["body"]["render_manifest"], "renders")
    require(render["artifact_id"] == p["body"]["render_manifest_id"], "RENDER_IDENTITY")
    paths = [model_path,gallery_path,query_path,*ranking_paths,pages_path,summary_path,p["body"]["render_manifest"]]
    return publish(Path(model_path).parent / "acceptance.json", "acceptance" if m["body"]["scope"] == "formal" else "smoke_acceptance",
        {**bindings(m,g,q), "status": "PASS", "guardrails": GUARDRAILS,
         "artifacts": {str(path): load(path)["artifact_id"] for path in paths},
         "row_count": len(rows), "deterministic_rerun": "same runtime/source identity: immutable byte equality required",
         "purpose": "qualitative interpretation only; no winner changes, B8/B9 selection, tuning or S11 changes"})
