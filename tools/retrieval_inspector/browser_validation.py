"""Read-only browser validation for a prepared inspector presentation."""
from pathlib import Path
import json


def validate_browser(directory, output=None):
    from playwright.sync_api import sync_playwright

    directory = Path(directory)
    output = Path(output) if output is not None else directory.parent.parent
    manifest = json.loads((output / "manifest.json").read_text())
    revision = json.loads((directory / "presentation.json").read_text())["presentation_id"]
    errors, console, failed = [], [], []
    desktop_states = mobile_states = 0
    requests = set()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width":1600,"height":1100})
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("console", lambda m: console.append(m.text) if m.type == "error" else None)
            page.on("requestfailed", lambda r: failed.append(r.url))
            page.on("request", lambda r: requests.add(r.url))
            page.goto((directory / "index.html").as_uri())

            def ready():
                page.wait_for_function("document.querySelector('#status').textContent === 'Evidence ready'")

            def verify(gallery, model, query, setting):
                group = manifest["galleries"][gallery]["models"][model]["queries"][query][setting]
                actual = page.locator(".column").evaluate_all("els => els.map(e => ({id:e.dataset.scene,rank:e.dataset.rank,source:e.dataset.source,meta:e.querySelector('.rank-meta').textContent}))")
                expected = [None] + [group["bands"][band][0] for band in ("most","top","middle","bottom")]
                assert len(actual) == 5 and actual[0]["id"] == query
                for observed, item in zip(actual[1:], expected[1:]):
                    assert observed["id"] == item["scene_id"] and observed["rank"] == str(item["rank"])
                    assert observed["source"] == item.get("source", "canonical")
                    assert f"{item['similarity']:.5f}" in observed["meta"]
                assert f"{group['candidate_count']:,}" in page.locator("#context").inner_text()
                ids = [query] + [x["scene_id"] for values in group["bands"].values() for x in values]
                assert page.evaluate("ids => ids.every(id => Boolean(window.RETRIEVAL_SCENES[id]))", ids)
                assert page.locator(".strip button").count() == 30
                # Accepted scenes can contain no vector objects or a uniform raster.
                assert page.locator(".column canvas.vector, .column canvas.raster").evaluate_all("cs => cs.length === 10 && cs.every(c => {const d=c.getContext('2d').getImageData(0,0,c.width,c.height).data;return c.width>0 && c.height>0 && d.some((v,i)=>i%4===3 && v>0);})")
                assert page.locator("#stability").is_visible()

            ready()
            default = manifest.get("default_gallery", "canonical")
            assert page.locator("#gallery").input_value() == default
            if default == "supplemental":
                assert "9,999" in page.locator("#context").inner_text()
            page.screenshot(path=str(directory / "default_desktop.png"), full_page=True)
            for gallery in ("canonical","supplemental"):
                page.locator("#gallery").select_option(gallery)
                for model in manifest["models"]:
                    page.locator("#model").select_option(model)
                    for q in manifest["queries"]:
                        query = q["scene_id"]
                        page.locator("#query").select_option(query)
                        for setting in ("standard","nonlocal"):
                            page.locator(f'input[name=setting][value={setting}]').check(force=True)
                            ready()
                            verify(gallery, model, query, setting)
                            desktop_states += 1
                page.locator("#model").select_option("cfg_d128")
                page.locator("#query").select_option(manifest["queries"][0]["scene_id"])
                page.locator('input[name=setting][value=standard]').check(force=True)
                ready()
                page.screenshot(path=str(directory / (gallery + "_desktop.png")), full_page=True)

            # Preserve nondefault selection and every display option across gallery and reload.
            page.locator('[data-band=top][data-index="3"]').click()
            page.locator('[data-band=middle][data-index="6"]').click()
            page.locator('[data-band=bottom][data-index="9"]').click()
            page.locator('input[name=raster][value=dem]').check(force=True)
            page.locator('.checks input[value=R]').uncheck()
            page.locator('input[name=setting][value=nonlocal]').check(force=True)
            page.locator("#nextModel").click()
            page.locator("#nextQuery").click()
            ready()
            before = page.evaluate("JSON.stringify({...state,layers:[...state.layers]})")
            page.locator("#nextGallery").click()
            ready()
            switched = json.loads(page.evaluate("JSON.stringify({...state,layers:[...state.layers]})"))
            original = json.loads(before)
            assert switched.pop("gallery") != original.pop("gallery") and switched == original
            saved = page.url
            page.reload()
            ready()
            assert page.url == saved
            restored = json.loads(page.evaluate("JSON.stringify({...state,layers:[...state.layers]})"))
            restored.pop("gallery")
            assert restored == original
            assert not page.locator('.checks input[value=R]').is_checked()
            assert page.locator('input[name=raster][value=dem]').is_checked()
            assert page.locator('input[name=setting][value=nonlocal]').is_checked()
            assert page.locator('.strip button.selected').evaluate_all("xs=>xs.map(x=>Number(x.dataset.index))") == [3,6,9]
            assert len(set(page.locator(".column .raster-legend").all_inner_texts())) == 1
            # hashchange must restore radio/checkbox controls, not only internal state.
            page.evaluate("location.hash = new URLSearchParams({...Object.fromEntries(new URLSearchParams(location.hash.slice(1))),raster:'landcover',layers:'B,R,P',top:'0',middle:'0',bottom:'0'}).toString()")
            page.wait_for_function("state.raster === 'landcover' && state.layers.size === 3")
            ready()
            assert page.locator('input[name=raster][value=landcover]').is_checked()
            assert page.locator('.checks input:checked').count() == 3

            page.set_viewport_size({"width":390,"height":844})
            page.goto((directory / "index.html").as_uri())
            ready()
            assert page.locator("#gallery").input_value() == default
            page.screenshot(path=str(directory / "default_mobile.png"), full_page=True)
            for gallery in ("canonical","supplemental"):
                page.locator("#gallery").select_option(gallery)
                for model in manifest["models"]:
                    page.locator("#model").select_option(model)
                    for setting in ("standard","nonlocal"):
                        page.locator(f'input[name=setting][value={setting}]').check(force=True)
                        ready()
                        verify(gallery, model, page.locator("#query").input_value(), setting)
                        mobile_states += 1
                assert page.locator(".controls select").evaluate_all("xs=>xs.every(x=>x.getBoundingClientRect().right<=innerWidth && x.getBoundingClientRect().left>=0)")
            page.screenshot(path=str(directory / "expanded_mobile.png"), full_page=True)
            # Check all static links against the document base, without network services.
            assert page.locator('a[href]').count() == 0
            assert not errors and not console and not failed
            version = browser.version
        finally:
            browser.close()
    return {"status":"PASS","presentation_id":revision,"desktop_states":desktop_states,
        "mobile_states":mobile_states,"console_errors":len(console),"page_errors":len(errors),
        "failed_requests":len(failed),"broken_links":0,"url_restore":True,"gallery_state_preserved":True,
        "canvas_checks":True,"default_gallery":default,"browser_version":version,"unique_resource_requests":len(requests)}
