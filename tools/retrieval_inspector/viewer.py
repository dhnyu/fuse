"""Read-only formal S10 artifact consumer. No scientific recomputation fallback."""
from pathlib import Path
from collections import defaultdict
import html
import os
import pyarrow.parquet as pq
from retrieval_artifacts import load, require, publish_bytes, file_hash


def pages(query_path, model_path, ranking_paths, render_path, output):
    queries = load(query_path, "queries")
    models = load(model_path, "models")
    renders = load(render_path, "renders")
    output = Path(output)
    by_scene = {r["scene_id"]: r for r in renders["body"]["scenes"]}
    require(len(by_scene) == len(renders["body"]["scenes"]), "VIEWER_DUPLICATE_SCENE")
    verified_paths = {(Path(render_path).parent / r["path"]).resolve() for r in renders["files"]}
    require({Path(r["path"]).resolve() for r in by_scene.values()} == verified_paths, "VIEWER_RENDER_PATHS")
    by_query = defaultdict(list)
    for path in ranking_paths:
        manifest = load(path, "rankings")
        require(manifest["body"]["query_manifest_id"] == queries["artifact_id"] and
                manifest["body"]["model_manifest_id"] == models["artifact_id"] and
                manifest["body"]["gallery_manifest_id"] == queries["body"]["gallery_manifest_id"], "VIEWER_BINDING")
        rows = pq.read_table(Path(path).parent / manifest["files"][0]["path"]).to_pylist()
        # Display a stored rank, never sort/recompute similarity, distances or eligibility.
        for row in rows:
            if row["rank"] <= 5:
                by_query[(row["query_id"], row["model_id"], row["retrieval_mode"])].append(row)
    def image(scene):
        require(scene in by_scene, "VIEWER_SCENE_MISSING")
        return '<img loading="lazy" alt="' + html.escape(scene) + '" src="' + html.escape(os.path.relpath(by_scene[scene]["path"], output)) + '">'
    script = (Path(__file__).parent / "app.js").read_bytes()
    style = (Path(__file__).parent / "style.css").read_bytes()
    publish_bytes(output / "app.js", script)
    publish_bytes(output / "style.css", style)
    result = [str(output / "app.js"), str(output / "style.css")]
    links = []
    for query in queries["body"]["rows"]:
        qid = query["scene_id"]
        filename = f'query_{query["query_index"]:02d}.html'
        links.append(f'<a href="{filename}">{query["query_index"]}. {html.escape(qid)}</a>')
        chunks = ['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">',
                  '<title>S10 Retrieval Visualization</title><link rel="stylesheet" href="style.css">',
                  '<main><a href="index.html">All queries</a><h1>S10 Retrieval Visualization</h1>',
                  '<p>Qualitative inspection only. No model selection or changes to S09 or S11.</p>',
                  '<label>Retrieval mode <select id="mode"><option value="standard">Standard</option><option value="nonlocal">Non-local ≥ 2 km</option></select></label>',
                  '<section class="query"><h2>Query ' + html.escape(qid) + '</h2>' + image(qid) + '</section>']
        group = None
        for model in models["body"]["models"]:
            if model["group"] != group:
                group = model["group"]
                chunks.append('<h2>' + html.escape(group) + '</h2>')
            for mode in ("standard", "nonlocal"):
                rows = by_query[(qid, model["configuration_id"], mode)]
                expected = min(5, queries["body"]["top_k"])
                require(len(rows) == expected and [r["rank"] for r in rows] == list(range(1, expected + 1)), "VIEWER_RANKS_MISSING")
                label = model["model_id"] if group == "COMPARISON" else {
                    "main": "main", "ofat_d_64": "d64", "ofat_d_256": "d256",
                    "ofat_K_aug_4": "K4", "ofat_K_aug_16": "K16",
                    "ofat_augmentation_intensity_0.5": "aug0.5", "ofat_augmentation_intensity_2.0": "aug2.0",
                    "ofat_ema_momentum_0.99": "ema0.99", "ofat_peak_learning_rate_0.002": "lr0.002",
                    "ofat_peak_learning_rate_0.003": "lr0.003", "ofat_peak_learning_rate_0.005": "lr0.005"
                }.get(model["configuration_id"], model["configuration_id"])
                chunks.append(f'<section class="model" data-mode="{mode}"><h3 title="{html.escape(model["configuration_id"])}">{html.escape(label)}</h3><div class="candidates">')
                for row in rows:
                    caption = (f'#{row["rank"]} · {row["gallery_scene_id"]}\n'
                               f'cos {row["similarity"]:.6f} · {row["geographic_distance_m"] / 1000:.2f} km · {mode}')
                    chunks.append('<figure>' + image(row["gallery_scene_id"]) + '<figcaption>' + html.escape(caption) + '</figcaption></figure>')
                chunks.append('</div></section>')
        chunks.append('</main><script src="app.js"></script></html>')
        result.append(str(publish_bytes(output / filename, ''.join(chunks).encode())))
    index = '<!doctype html><html lang="en"><meta charset="utf-8"><title>S10 queries</title><link rel="stylesheet" href="style.css"><main><h1>S10 Retrieval Visualization</h1><p>Fixed common queries. Interpretation only; no model selection.</p><nav>' + ''.join(links) + '</nav></main></html>'
    result.append(str(publish_bytes(output / "index.html", index.encode())))
    return result
