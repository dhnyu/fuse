"""Read-only thematic UI validation; no scientific stage or checkpoint loading."""
import argparse
from collections import Counter
from functools import partial
import hashlib
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
import json
from pathlib import Path
import threading
import io
import tarfile
import pyarrow.compute as pc

import pyarrow.parquet as pq
import torch
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
ATTRS={'POI categories · L1':('poi',0),'Building use':('building',0),
       'Building structure':('building',1),'Road rank':('road',0)}


def validate(viewer, generation):
    viewer, generation = Path(viewer), Path(generation)
    receipt = json.loads((viewer/'viewer_receipt.json').read_text())
    for name, sha in receipt['files'].items():
        assert hashlib.sha256((viewer/name).read_bytes()).hexdigest() == sha, name
    config = json.loads((viewer/'config.json').read_text())
    live=(ROOT/'tools/augmentation_inspector/inspector.py').read_text()
    assert (viewer/'augmentation.css').read_text()==live.split('<style>',1)[1].split('</style>',1)[0]
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
    # Independent per-entity tensor membership check, all queries + 20 other scenes.
    ids=[q['scene_id'] for q in config['queries']]
    ids+=sorted(p.stem for p in (viewer/'scenes').glob('*.json') if p.stem not in ids)[:20]
    previous=viewer.parent/'viewer_404735cf7d702a5704f0b8f1'
    model_record=json.loads((generation/'model_manifest.json').read_text())
    raw_tables={}
    for sid in ids:
        s=torch.load(generation/'original_inputs'/(sid+'.pt'),map_location='cpu',weights_only=True)
        d=json.loads((viewer/'scenes'/(sid+'.json')).read_text())
        for title,(prefix,col) in ATTRS.items():
            theme=d['thematic']['maps'][title];ri=s['entities'][prefix+'_row_index'].tolist()
            categories=s['entities'][prefix+'_category'][:,col].tolist()
            assert [e['svg_index'] for e in theme['entities']]==ri
            assert [e['entity_id'] for e in theme['entities']]==s['entities']['local_entity_id'][ri].tolist()
            assert [e['category_index'] for e in theme['entities']]==categories
            assert {e['category_index']:e['count'] for e in theme['legend']}==dict(Counter(categories))
        lc=s['rasters']['landcover_class_fraction'].numpy().astype('float64')
        mass=(lc*s['rasters']['landcover_valid_support'].numpy()[None]*s['rasters']['landcover_valid_mask'].numpy().astype(bool)[None]).sum(axis=(1,2))
        expected_lc={f'LC {i+1}':float(v/mass.sum()*100) for i,v in enumerate(mass) if v>0}
        assert {r['label']:r['value'] for r in d['charts']['Land cover composition']}==expected_lc
        assert d['thematic']['road_lane']['available']
        parent=s['lineage']['parent']
        path=Path(model_record['body']['roots']['p3'])/'shards'/parent['branch_id']/parent['payload_filename']
        if path not in raw_tables:
            assert hashlib.sha256(path.read_bytes()).hexdigest()==parent['payload_sha256']
            with tarfile.open(path) as archive:
                raw_tables[path]=pq.read_table(io.BytesIO(archive.extractfile('vector/road_observed.parquet').read()),columns=['scene_id','local_entity_id','LANES'])
        table=raw_tables[path];roads=sorted(table.filter(pc.equal(table['scene_id'],sid)).to_pylist(),key=lambda r:r['local_entity_id'])
        lane=d['thematic']['maps']['Road lane']
        assert [(e['entity_id'],e['raw_value']) for e in lane['entities']]==[(r['local_entity_id'],r['LANES']) for r in roads]
        assert sum(x['count'] for x in lane['legend'])==len(roads)
        assert d['thematic']['binding']['p3_payload_sha256']==s['lineage']['parent']['payload_sha256']
        assert d['thematic']['binding']['original_input_sha256']==hashlib.sha256((generation/'original_inputs'/(sid+'.pt')).read_bytes()).hexdigest()
        old=json.loads((previous/'scenes'/(sid+'.json')).read_text())
        assert all(d[k]==old[k] for k in ['svg','lc','dem','charts','counts','relation_masks'])
    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),partial(Quiet,directory=str(viewer)))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    errors=[]
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            page=browser.new_page(viewport={'width':1800,'height':1200})
            page.on('pageerror',lambda e:errors.append(str(e)))
            url=f'http://127.0.0.1:{server.server_port}/'
            page.goto(url);page.wait_for_selector('#detailGrid .thematic-map',timeout=60000)
            for qi,mid,mode in [(0,'main','standard'),(0,'cmp_DS','nonlocal'),(1,'ofat_d_256','standard'),(29,'cmp_B9','nonlocal')]:
                page.select_option('#query',str(qi));page.select_option('#model',mid);page.select_option('#mode',mode)
                want=[config['queries'][qi]['scene_id']]+[r['gallery_scene_id'] for r in expected[config['queries'][qi]['scene_id'],mid,mode]]
                page.wait_for_function('(ids)=>JSON.stringify([...document.querySelectorAll("#vectorGrid>.panel")].map(x=>x.dataset.scene))===JSON.stringify(ids) && document.querySelectorAll(".thematic-map").length===30',arg=want,timeout=60000)
                assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
                for grid in ['vectorGrid','rasterGrid','summaryGrid','detailGrid']:
                    assert page.locator('#'+grid+'>.panel').count()==6
                    assert page.locator('#'+grid+'>.panel').evaluate_all('(els)=>els.map(x=>x.dataset.scene)')==want
                assert page.locator('.canvas-wrap img').evaluate_all('(images)=>images.every(x=>x.complete && x.naturalWidth>0)')
                # DOM thematic paints must retain exact original SVG geometry attributes.
                page.evaluate('''() => {
                  function signature(node){return [node,...node.querySelectorAll('*')].filter(x=>x.localName!=='title').map(x=>[x.localName,[...x.attributes].filter(a=>!['fill','stroke'].includes(a.name)&&!a.name.startsWith('data-')&&!a.name.startsWith('xmlns')).map(a=>[a.name,a.value]).sort()])}
                  for(let i=0;i<scenes.length;i++){
                    const s=scenes[i],orig=new DOMParser().parseFromString(s.svg,'image/svg+xml');
                    const shapes=[...orig.documentElement.children].find(x=>x.localName==='g').children;
                    for(const [title,theme] of Object.entries(s.thematic.maps)){
                      const section=[...document.querySelectorAll('#detailGrid>.panel')][i];
                      const item=[...section.querySelectorAll('[data-theme]')].find(x=>x.dataset.theme===title);
                      const actual=[...item.querySelectorAll('[data-entity-id]')];
                      if(actual.length!==theme.entities.length)throw Error('entity count mismatch');
                      actual.forEach((node,j)=>{let e=theme.entities[j];
                        if(+node.dataset.entityId!==e.entity_id||+node.dataset.categoryIndex!==e.category_index||node.dataset.color!==e.color)throw Error('category assignment mismatch');
                        for(const shape of [node,...node.querySelectorAll('*')]){const paint=theme.layer==='R'?'stroke':'fill';if(shape.hasAttribute(paint)&&shape.getAttribute(paint)!=='none'&&shape.getAttribute(paint)!==e.color)throw Error('paint mismatch')}
                        if(JSON.stringify(signature(node))!==JSON.stringify(signature(shapes[e.svg_index])))throw Error('geometry changed');
                      });
                    }
                  }
                }''')
            page.select_option('#query','0');page.select_option('#model','main');page.select_option('#mode','standard')
            page.wait_for_function('document.querySelectorAll(".thematic-map").length===30 && document.querySelector("#caseTitle").textContent.includes("main")')
            for layer,color in [('B','#667085'),('R','#e4a11b'),('P','#c83e63')]:
                page.uncheck(f'[data-layer={layer}]')
                elements=page.locator(f'.vector-map [fill="{color}"], .vector-map [stroke="{color}"]')
                assert elements.count()>0 and elements.evaluate_all('(nodes)=>nodes.every(x=>getComputedStyle(x).visibility==="hidden")')
                assert page.locator(f'[data-thematic-layer={layer}] .canvas-wrap').evaluate_all('(els)=>els.every(x=>getComputedStyle(x).visibility==="hidden")')
                page.check(f'[data-layer={layer}]')
            for layer in ['LC','DEM']:
                page.uncheck(f'[data-layer={layer}]');assert page.locator(f'[data-raster={layer}]').first.evaluate('x=>getComputedStyle(x).visibility')=='hidden';page.check(f'[data-layer={layer}]')
            d=page.locator('#detailGrid>.panel').first.locator('details')
            d.locator('summary').click();assert not d.evaluate('x=>x.open')
            d.locator('summary').click();assert d.evaluate('x=>x.open')
            page.locator('.vector-map').first.hover();page.mouse.wheel(0,-100)
            page.wait_for_function('view.scale>1');page.click('#resetZoom');assert page.evaluate('view.scale')==1
            page.click('#toggleProvenance');assert page.locator('#provenance').is_visible();page.click('#toggleProvenance')
            page.select_option('#group','OFAT');assert page.locator('#model option').count()==11
            page.select_option('#group','COMPARISON');assert page.locator('#model option').count()==17
            page.select_option('#group','all');assert page.locator('#model option').count()==28
            page.select_option('#model','main');page.wait_for_function('document.querySelectorAll(".thematic-map").length===30 && document.querySelector("#caseTitle").textContent.includes("main")')
            # Compare unchanged base computed layout properties against live template CSS.
            reference=browser.new_page(viewport={'width':1800,'height':1200})
            reference.set_content(live.split('return """<!doctype html>',1)[1].split('<script>const DATA=',1)[0])
            for selector,properties in [('header',['padding','position','backgroundColor']),('main',['padding','maxWidth']),('.brand h1',['fontSize','margin']),('.controls',['gap']),('.control select',['height','padding','borderRadius']),('.section>h2',['fontSize','padding','backgroundColor'])]:
                script='(el,props)=>Object.fromEntries(props.map(k=>[k,getComputedStyle(el)[k]]))'
                assert page.locator(selector).first.evaluate(script,properties)==reference.locator(selector).first.evaluate(script,properties),(selector,properties)
            reference.screenshot(path='/tmp/fuse-s10-augmentation-layout-reference.png',full_page=True)
            reference.close()
            page.screenshot(path='/tmp/fuse-s10-thematic-final.png',full_page=True)
            for width in [1600,1440]:
                page.set_viewport_size({'width':width,'height':1000});assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
            assert not errors,errors
            for missing in [False,True]:
                bad=browser.new_page();bad.route('**/queries/*.json',lambda route,request,missing=missing:route.fulfill(status=404 if missing else 200,body='{}',content_type='application/json'))
                bad.goto(url);bad.wait_for_selector('#error:visible')
                assert bad.locator('#vectorGrid>.panel').count()==0
                assert ('unavailable' if missing else 'checksum mismatch') in bad.locator('#error').inner_text();bad.close()
            browser.close()
    finally:
        server.shutdown();server.server_close();thread.join()
    print(json.dumps({'status':'PASS','exact_display_rows':count,'pages':len(config['queries']), 'scene_assets':receipt['scene_count'],'source_membership_scenes':len(ids),'thematic_maps_per_query':36,'browser_js_errors':errors,'verbatim_css_and_computed_layout':True,'unchanged_svg_geometry':True,'corrupt_and_missing_fail_closed':True},indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--viewer',required=True);parser.add_argument('--generation',required=True)
    args=parser.parse_args();torch.set_num_threads(1);validate(args.viewer,args.generation)
