"""Read-only supplemental UI checks. Never computes retrieval or opens checkpoints."""
import argparse
from functools import partial
import hashlib
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
import json
from pathlib import Path
import threading

import pyarrow.parquet as pq
from playwright.sync_api import sync_playwright


def validate(viewer, generation):
    viewer, generation = Path(viewer), Path(generation)
    receipt = json.loads((viewer/'viewer_receipt.json').read_text())
    for name, sha in receipt['files'].items():
        assert hashlib.sha256((viewer/name).read_bytes()).hexdigest() == sha, name
    config = json.loads((viewer/'config.json').read_text())
    expected = {}
    for m in config['models']:
        manifest = json.loads((generation/'rankings'/m['id']/'manifest.json').read_text())
        rows = pq.read_table(generation/'rankings'/m['id']/manifest['files'][0]['path']).to_pylist()
        for row in rows:
            if row['rank'] <= 5:
                expected.setdefault((row['query_id'],m['id'],row['retrieval_mode']),[]).append(row)
    count=0
    for q in config['queries']:
        data=json.loads((viewer/'queries'/(q['scene_id']+'.json')).read_text())
        for model, modes in data.items():
            for mode, rows in modes.items():
                assert rows == expected[q['scene_id'],model,mode]
                count+=len(rows)
    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),partial(Quiet,directory=str(viewer)))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    errors=[]
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            page=browser.new_page(viewport={'width':1600,'height':1100})
            page.on('pageerror',lambda e:errors.append(str(e)))
            url=f'http://127.0.0.1:{server.server_port}/'
            page.goto(url);page.wait_for_selector('.scene-panel')
            assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
            for qi,mid,mode in [(0,'main','standard'),(0,'cmp_DS','nonlocal'),(1,'ofat_d_256','standard'),(29,'cmp_B9','nonlocal')]:
                page.select_option('#query',str(qi))
                page.select_option('#model',mid)
                page.select_option('#mode',mode)
                want=[config['queries'][qi]['scene_id']]+[r['gallery_scene_id'] for r in expected[config['queries'][qi]['scene_id'],mid,mode]]
                page.wait_for_function('(ids)=>JSON.stringify([...document.querySelectorAll(".thumb")].map(x=>x.dataset.scene))===JSON.stringify(ids)',arg=want)
                assert page.locator('.scene-panel').count()==2
                assert page.locator('.chart').count()==12
                assert page.locator('.raster-grid img').evaluate_all('(images)=>images.every(x=>x.complete && x.naturalWidth>0)')
                page.locator('.thumb').nth(5).click()
                assert page.locator('.scene-panel').nth(1).get_attribute('data-scene')==want[5]
            # Verify actual SVG layer visibility, not only checkbox state.
            page.select_option('#query','0');page.select_option('#model','main');page.select_option('#mode','standard')
            page.wait_for_function('document.querySelectorAll(".thumb").length===6 && document.querySelector("#summary").textContent.includes("main")')
            for layer,color in [('B','#667085'),('R','#e4a11b'),('P','#c83e63')]:
                page.uncheck(f'[data-layer={layer}]')
                elements=page.locator(f'.map [fill="{color}"], .map [stroke="{color}"]')
                assert elements.count()>0
                assert elements.evaluate_all('(nodes)=>nodes.every(x=>getComputedStyle(x).visibility==="hidden")')
                page.check(f'[data-layer={layer}]')
            for layer in ['LC','DEM']:
                page.uncheck(f'[data-layer={layer}]')
                assert page.locator(f'[data-raster={layer}]').first.evaluate('x=>getComputedStyle(x).visibility')=='hidden'
                page.check(f'[data-layer={layer}]')
            page.select_option('#group','OFAT');assert page.locator('#model option').count()==11
            page.select_option('#group','COMPARISON');assert page.locator('#model option').count()==17
            page.select_option('#group','all');assert page.locator('#model option').count()==28
            page.select_option('#model','main');page.wait_for_selector('.scene-panel')
            # Chart bar magnitudes must match the stored display summaries, including Other.
            scene_id=page.locator('.scene-panel').first.get_attribute('data-scene')
            display=json.loads((viewer/'scenes'/(scene_id+'.json')).read_text())
            for title,items in display['charts'].items():
                regular=sorted([x for x in items if x['label']!='Unknown / missing'],key=lambda x:-x['value'])
                values=[x['value'] for x in regular[:5]]+[x['value'] for x in items if x['label']=='Unknown / missing']
                if len(regular)>5:values.append(sum(x['value'] for x in regular[5:]))
                chart=page.locator('.scene-panel').first.locator('.chart').filter(has=page.locator('h5',has_text=title))
                actual=chart.locator('.bar-row').evaluate_all('(nodes)=>nodes.map(x=>+x.dataset.value)')
                assert actual==values,(title,actual,values)
            page.screenshot(path='/tmp/fuse-s10-viewer-final.png',full_page=True)
            assert not errors,errors
            # Corruption and missing payload must clear the view, with no fallback.
            for missing in [False,True]:
                bad=browser.new_page()
                bad.route('**/queries/*.json',lambda route,request,missing=missing:route.fulfill(status=404 if missing else 200,body='{}',content_type='application/json'))
                bad.goto(url);bad.wait_for_selector('#error:visible')
                assert bad.locator('.thumb').count()==0 and bad.locator('.scene-panel').count()==0
                assert ('unavailable' if missing else 'checksum mismatch') in bad.locator('#error').inner_text()
                bad.close()
            browser.close()
    finally:
        server.shutdown();server.server_close();thread.join()
    print(json.dumps({'status':'PASS','exact_display_rows':count,'pages':len(config['queries']), 'scene_assets':receipt['scene_count'],'browser_js_errors':errors,'corrupt_and_missing_fail_closed':True},indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--viewer',required=True);parser.add_argument('--generation',required=True)
    args=parser.parse_args();validate(args.viewer,args.generation)
