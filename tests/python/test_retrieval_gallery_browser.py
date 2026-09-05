"""Browser-only fixture: no supplemental scientific results are fabricated/published."""
import copy
import json
from pathlib import Path
import shutil

import pytest


ROOT = Path(__file__).resolve().parents[2]


def test_explicit_gallery_switch_with_existing_scene_assets(tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    example = json.loads((ROOT / "tools/retrieval_inspector/example_output.json").read_text())
    accepted = (ROOT / example["output_path"]).parent
    if not (accepted / "manifest.json").is_file():
        pytest.skip("Local inspector fixture assets unavailable")
    canonical = json.loads((accepted / "manifest.json").read_text())
    supplemental = copy.deepcopy(canonical)
    supplemental["gallery_count"] = 10000
    supplemental["scientific_status"] = "NONSCIENTIFIC_BROWSER_TEST_FIXTURE"
    for model in supplemental["models"].values():
        for query in model["queries"].values():
            query["standard"]["candidate_count"] = 9999
    manifest = {**canonical, "galleries": {"canonical": canonical, "supplemental": supplemental}}
    for name in ("index.html", "style.css", "app.js"):
        shutil.copyfile(ROOT / "tools/retrieval_inspector" / name, tmp_path / name)
    (tmp_path / "assets").symlink_to(accepted / "assets", target_is_directory=True)
    (tmp_path / "manifest.js").write_text("window.RETRIEVAL_MANIFEST=" + json.dumps(manifest) + ";\n")
    errors = []
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1600, "height": 1000})
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto((tmp_path / "index.html").as_uri())
            page.wait_for_function("document.querySelector('#status').textContent === 'Evidence ready'")
            assert page.locator("#gallery").input_value() == "canonical"
            page.locator("#gallery").select_option("supplemental")
            page.wait_for_function("document.querySelector('#status').textContent === 'Evidence ready'")
            assert "9,999" in page.locator("#context").inner_text()
            assert "supplementary" in page.locator(".eyebrow").inner_text().lower()
            assert "gallery=supplemental" in page.url
            for setting in ("nonlocal", "standard"):
                page.locator(f"input[name=setting][value={setting}]").check(force=True)
                page.wait_for_function("document.querySelector('#status').textContent === 'Evidence ready'")
            assert page.locator(".column").count() == 5
            assert page.locator(".column canvas.vector").evaluate_all("cs => cs.every(c => c.width > 0 && c.height > 0)")
            assert page.locator(".column canvas.vector").evaluate_all("cs => cs.every(c => { const d = c.getContext('2d').getImageData(0,0,c.width,c.height).data; return d.some((v,i) => i%4===3 && v>0); })")
            page.locator("#gallery").select_option("canonical")
            page.wait_for_function("document.querySelector('#status').textContent === 'Evidence ready'")
            assert "1,599" in page.locator("#context").inner_text()
            page.set_viewport_size({"width": 390, "height": 844})
            page.reload()
            page.wait_for_function("document.querySelector('#status').textContent === 'Evidence ready'")
            bounds = page.locator("#gallery").bounding_box()
            assert bounds["width"] > 0 and bounds["x"] >= 0
            assert page.locator(".controls select").evaluate_all("xs => xs.every(x => x.getBoundingClientRect().right <= innerWidth)")
            assert not errors
        finally:
            browser.close()
