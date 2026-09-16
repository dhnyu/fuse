#!/usr/bin/env python3
"""Real accepted-checkpoint smoke: 2 models, 2 queries, 6 originals; auto-cleanup."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time

for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[key] = "1"
os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from retrieval_artifacts import publish, load, digest, require, file_hash
from retrieval_lineage import config, inventory, population, runtime
from retrieval_ranking import sample_queries
from retrieval_pipeline import (GUARDRAILS, context, original_inputs, embeddings, rankings, render_cache,
                               comparison_pages, summary, acceptance, validate_rankings)


def smoke():
    started = time.monotonic()
    cfg = config("config/retrieval_visualization.yml")
    body = inventory(cfg)
    print("Validated exact 28 native acceptance/checkpoint chains", flush=True)
    gallery, source = population(cfg, body)
    # Small geographically spread subset selected only from source centers, never model results.
    chosen = []
    for row in gallery:
        if all((row["center_x"]-r["center_x"])**2 + (row["center_y"]-r["center_y"])**2 >= 2500**2 for r in chosen):
            chosen.append(row)
        if len(chosen) == 6: break
    require(len(chosen) == 6, "SMOKE_CANDIDATES")
    cfg = {**cfg, "model_count": 2, "gallery_count": 6, "query_count": 2, "top_k": 2}
    body["models"] = [r for r in body["models"] if r["configuration_id"] in ("main", "cmp_DS")]
    body.update({"config": cfg, "runtime": runtime(cfg), "scope": "noncanonical_smoke", "guardrails": GUARDRAILS})
    body["runtime_id"] = body["runtime"]["runtime_id"]
    body["generation_id"] = "smoke_" + digest(body)[:24]
    with tempfile.TemporaryDirectory(prefix="fuse-s10-smoke-") as directory:
        root = Path(directory)
        m = publish(root/"model_manifest.json", "models", body)
        mv = load(m)
        g = publish(root/"gallery_manifest.json", "gallery", {**context(mv),
            "model_manifest_id": mv["artifact_id"], "source": source,
            "source_manifest_identity": digest(source), "crs": "EPSG:5186", "units": "metres", "rows": chosen})
        gv = load(g)
        q = publish(root/"query_manifest.json", "queries", {**context(mv),
            "model_manifest_id": mv["artifact_id"], "gallery_manifest_id": gv["artifact_id"],
            "source_manifest_identity": digest(source), "seed": cfg["query_seed"], "top_k": 2,
            "rows": sample_queries(chosen,cfg["query_seed"],2,6)})
        ranking_paths = []
        preparation_start = time.monotonic()
        prepared = original_inputs(m,g,q)
        preparation_seconds = time.monotonic()-preparation_start
        inference_start = time.monotonic()
        for model in body["models"]:
            e = embeddings(m,g,q,model["configuration_id"],prepared)
            before = file_hash(e)
            # Two real inference passes must publish identical bytes in the same runtime.
            require(file_hash(embeddings(m,g,q,model["configuration_id"],prepared)) == before, "SMOKE_RERUN")
            ranking_paths.append(rankings(m,g,q,e))
        inference_seconds = time.monotonic()-inference_start
        render = render_cache(m,g,q,ranking_paths)
        pages = comparison_pages(m,g,q,ranking_paths,render)
        s = summary(m,g,q,ranking_paths,pages)
        a = acceptance(m,g,q,ranking_paths,pages,s)
        from html.parser import HTMLParser
        class Links(HTMLParser):
            def handle_starttag(self, tag, attrs):
                for key,value in attrs:
                    if key in ("href","src"):
                        require((root/"pages"/value).is_file(), "SMOKE_BROKEN_LINK")
        for page in (root/"pages").glob("*.html"):
            Links().feed(page.read_text())
        # Browser runtime check if installed; failure is not silently discarded.
        from playwright.sync_api import sync_playwright
        with sync_playwright() as browser_api:
            browser = browser_api.chromium.launch(headless=True)
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto((root/"pages/query_01.html").as_uri())
            require(page.locator('.model:visible').count()==2, "SMOKE_STANDARD_UI")
            for image in page.locator('img:visible').all():
                image.scroll_into_view_if_needed()
            page.wait_for_function('Array.from(document.images).filter(i => i.offsetParent !== null).every(i => i.complete && i.naturalWidth > 0)')
            page.select_option('#mode','nonlocal')
            require(page.locator('.model:visible').count()==2 and
                    page.locator('.model:visible').first.get_attribute('data-mode')=='nonlocal', "SMOKE_MODE_SWITCH")
            # Hidden lazy images need not load. Scroll and await visible images rather
            # than racing the browser's asynchronous resource/decode work.
            for image in page.locator('img:visible').all():
                image.scroll_into_view_if_needed()
            page.wait_for_function('Array.from(document.images).filter(i => i.offsetParent !== null).every(i => i.complete && i.naturalWidth > 0)')
            page.set_viewport_size({"width":390,"height":844})
            require(page.locator('#mode').is_visible(), "SMOKE_MOBILE_CONTROL")
            screenshot = os.environ.get("FUSE_S10_SMOKE_SCREENSHOT")
            if screenshot:
                page.screenshot(path=screenshot,full_page=True)
            require(not errors, "SMOKE_BROWSER_ERROR")
            browser.close()
        result={"status":"PASS", "scope":"NONCANONICAL", "accepted_models_validated":28,
                "inference_models":[r['configuration_id'] for r in body['models']], "gallery":6,"queries":2,
                "rows":len(validate_rankings(m,g,q,ranking_paths)), "rerun_byte_equality":True,
                "viewer_browser":"PASS", "inference_seconds_two_passes":inference_seconds,
                "preparation_seconds":preparation_seconds,
                "elapsed_seconds":time.monotonic()-started, "acceptance_id":load(a)['artifact_id'],
                "temporary_directory":directory}
    require(not Path(directory).exists(), "SMOKE_CLEANUP")
    result['cleanup']='PASS'
    print(json.dumps(result,sort_keys=True),flush=True)


if __name__ == "__main__":
    smoke()
