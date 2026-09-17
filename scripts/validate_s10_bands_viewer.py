"""Independent full-order, band-browser, and raster-display audit (read-only)."""
import argparse
import base64
from collections import Counter
from functools import partial
import hashlib
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
import io
import json
from pathlib import Path
import threading

import numpy as np
from PIL import Image
import pyarrow.parquet as pq
import torch
from playwright.sync_api import sync_playwright
from threadpoolctl import threadpool_limits


def validate(viewer,generation,audit_path):
    viewer=Path(viewer);generation=Path(generation)
    receipt=json.loads((viewer/'viewer_receipt.json').read_text());config=json.loads((viewer/'config.json').read_text())
    for name,h in receipt['files'].items():assert hashlib.sha256((viewer/name).read_bytes()).hexdigest()==h,name
    gallery=json.loads((generation/'gallery_manifest.json').read_text())['body']['rows'];ids=[r['scene_id'] for r in gallery]
    centers=np.array([[r['center_x'],r['center_y']] for r in gallery],dtype='float64')
    data={q['scene_id']:json.loads((viewer/'queries'/(q['scene_id']+'.json')).read_text()) for q in config['queries']}
    total=0;counts=[]
    for model in config['models']:
        mid=model['id'];em=json.loads((generation/'embeddings'/mid/'manifest.json').read_text());assert receipt['embedding_manifest_ids'][mid]==em['artifact_id']
        v=np.load(generation/'embeddings'/mid/'vectors.npy',allow_pickle=False)
        rm=json.loads((generation/'rankings'/mid/'manifest.json').read_text());formal=pq.read_table(generation/'rankings'/mid/rm['files'][0]['path']).to_pylist()
        formal={(r['query_id'],r['retrieval_mode'],r['rank']):r for r in formal}
        for q in config['queries']:
            sid=q['scene_id'];qi=ids.index(sid)
            with threadpool_limits(limits=1):scores=v@v[qi]
            distance=np.linalg.norm(centers-centers[qi],axis=1)
            # Independent tuple sort specifies the scene-ID secondary key explicitly.
            order=sorted(range(len(ids)),key=lambda i:(-float(scores[i]),ids[i]))
            for mode in ['standard','nonlocal']:
                eligible=[i for i in order if i!=qi and (mode=='standard' or distance[i]>=2000)]
                n=len(eligible);actual=data[sid][mid][mode];assert actual['candidate_count']==n
                if mode=='standard':assert n==8999
                expected={'most':[1],'top':list(range(2,12)),'middle':list(range((n-10)//2+1,(n-10)//2+11)),'bottom':list(range(n-9,n+1))}
                for rank in range(1,51):
                    i=eligible[rank-1];r=formal[sid,mode,rank]
                    assert r['gallery_scene_id']==ids[i] and r['similarity']==float(scores[i]) and r['geographic_distance_m']==float(distance[i])
                for band,positions in expected.items():
                    rows=actual['bands'][band];assert [r['rank'] for r in rows]==positions
                    for row,position in zip(rows,positions,strict=True):
                        i=eligible[position-1];assert row['gallery_scene_id']==ids[i] and row['similarity']==float(scores[i]) and row['geographic_distance_m']==float(distance[i]);assert row['model_id']==mid and row['query_id']==sid and row['retrieval_mode']==mode
                    total+=len(rows)
                counts.append(n)
    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self,*args):pass
    # Serve parent to audit the immutable previous viewer alongside the new one.
    # Historical viewer validation also uses only 8765; conflicts fail, never fall back.
    server=ThreadingHTTPServer(('127.0.0.1',8765),partial(Quiet,directory=str(viewer.parent)))
    t=threading.Thread(target=server.serve_forever,daemon=True);t.start();errors=[];measurements=[]
    try:
        with sync_playwright() as p:
            b=p.chromium.launch(headless=True);page=b.new_page(viewport={'width':1800,'height':1200});page.on('pageerror',lambda e:errors.append(str(e)))
            url=f'http://127.0.0.1:{server.server_port}/{viewer.name}/'
            page.goto(url);page.wait_for_selector('.lc-canvas[data-smoothing]',timeout=60000)
            for qi,mid,mode in [(0,'main','standard'),(1,'ofat_d_256','nonlocal'),(29,'cmp_DS','standard'),(0,'cmp_B9','nonlocal')]:
                page.select_option('#query',str(qi));page.select_option('#model',mid);page.select_option('#mode',mode)
                qid=config['queries'][qi]['scene_id'];entry=data[qid][mid][mode]
                want=[qid,entry['bands']['most'][0]['gallery_scene_id']]+[entry['bands'][k][0]['gallery_scene_id'] for k in ['top','middle','bottom']]
                page.wait_for_function('(ids)=>JSON.stringify([...document.querySelectorAll("#comparison>.column")].map(e=>e.dataset.scene))===JSON.stringify(ids)&&document.querySelectorAll(".lc-canvas[data-smoothing]").length===5',arg=want,timeout=60000)
                assert page.locator('.strip button').count()==30
                assert page.locator('.detail-host .thematic-map').count()==25
                for band in ['top','middle','bottom']:
                    assert page.locator(f'.strip button[data-band={band}]').count()==10
                    for pos in [0,4,9]:
                        row=entry['bands'][band][pos];page.locator(f'.strip button[data-band={band}]').nth(pos).click()
                        page.wait_for_function('([band,sid,rank])=>document.querySelector(`.column[data-band="${band}"]`)?.dataset.scene===sid && +document.querySelector(`.column[data-band="${band}"]`).dataset.rank===rank && document.querySelectorAll(".lc-canvas[data-smoothing]").length===5',arg=[band,row['gallery_scene_id'],row['rank']],timeout=60000)
                assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
            page.select_option('#query','0');page.select_option('#model','main');page.select_option('#mode','standard')
            page.wait_for_function("document.querySelector('#caseTitle').textContent.includes('main')&&document.querySelectorAll('.lc-canvas[data-smoothing]').length===5")
            for layer in ['LC','DEM']:
                page.uncheck(f'[data-layer={layer}]');assert page.locator(f'[data-raster={layer}]').first.evaluate('e=>getComputedStyle(e).visibility')=='hidden';page.check(f'[data-layer={layer}]')
            d=page.locator('.detail-host details').first;d.locator('summary').first.click();assert not d.evaluate('e=>e.open');d.locator('summary').first.click()
            # Exact nearest-neighbour validation: every output RGB is an existing source RGB.
            nearest=page.evaluate('''async()=>{let results=[];for(const c of document.querySelectorAll('.lc-canvas')){const im=new Image();im.src=c.dataset.png;await im.decode();const src=document.createElement('canvas');src.width=100;src.height=100;const cx=src.getContext('2d');cx.drawImage(im,0,0);const a=cx.getImageData(0,0,100,100).data,b=c.getContext('2d').getImageData(0,0,c.width,c.height).data;let colors=new Set();for(let i=0;i<a.length;i+=4)if(a[i+3]===255)colors.add(`${a[i]},${a[i+1]},${a[i+2]}`);let introduced=0;for(let i=0;i<b.length;i+=4)if(b[i+3]===255&&!colors.has(`${b[i]},${b[i+1]},${b[i+2]}`))introduced++;results.push({introduced,smoothing:c.getContext('2d').imageSmoothingEnabled})}return results}''')
            assert all(r['introduced']==0 and not r['smoothing'] for r in nearest)
            for col in page.locator('#comparison>.column').all():
                sid=col.get_attribute('data-scene');role=col.get_attribute('data-band')
                if role=='top':continue
                scene=json.loads((viewer/'scenes'/(sid+'.json')).read_text());sample=torch.load(generation/'original_inputs'/(sid+'.pt'),weights_only=True,map_location='cpu')
                for kind in ['LC','DEM']:
                    im=Image.open(io.BytesIO(base64.b64decode(scene['lc' if kind=='LC' else 'dem'].split(',')[1])))
                    selector='.lc-canvas' if kind=='LC' else '.raster-pair img'
                    m=col.locator(selector).evaluate('(e)=>({css:[e.getBoundingClientRect().width,e.getBoundingClientRect().height],backing:[e.width,e.height],interpolation:getComputedStyle(e).imageRendering,dpr:devicePixelRatio,smoothing:e.tagName==="CANVAS"?e.getContext("2d").imageSmoothingEnabled:null})')
                    tensor=sample['rasters']['landcover_class_fraction' if kind=='LC' else 'dem_standardized_mean']
                    mixed=int(((sample['rasters']['landcover_class_fraction']>0).sum(0)>1).sum()) if kind=='LC' else None
                    measurements.append({'scene_role':role,'scene_id':sid,'raster':kind,'stored':list(tensor.shape),'intrinsic':list(im.size),'mixed_fraction_cells':mixed,**m})
            page.screenshot(path=str(audit_path)+'.png',full_page=True)
            # Baseline role parity from the prior accepted display generation.
            old=b.new_page(viewport={'width':1800,'height':1200});old.goto(f'http://127.0.0.1:{server.server_port}/viewer_f8d14a826a75bc8451f219c5/');old.wait_for_selector('#rasterGrid>.panel img',timeout=60000);old.wait_for_function('[...document.querySelectorAll("#rasterGrid img")].every(im=>im.complete&&im.naturalWidth>0)')
            baseline=old.locator('#rasterGrid>.panel').evaluate_all('(els)=>els.slice(0,2).flatMap((el,i)=>[...el.querySelectorAll("img")].map(im=>({role:i?"rank1":"query",intrinsic:[im.naturalWidth,im.naturalHeight],css:[im.getBoundingClientRect().width,im.getBoundingClientRect().height],interpolation:getComputedStyle(im).imageRendering})))');old.close()
            # A corrupt embedded raster must stop inspection, never synthesize a fallback.
            await_result=page.evaluate("async()=>{const c=document.createElement('canvas');c.dataset.png='data:image/png;base64,AAAA';try{await drawLC(c);return false}catch(e){bandFail(e);return true}}")
            assert await_result and page.locator('#error').is_visible() and page.locator('#comparison>.column').count()==0
            for width,dpr in [(1600,1),(1800,2)]:
                test=b.new_page(viewport={'width':width,'height':1000},device_scale_factor=dpr);test.goto(url);test.wait_for_selector('.lc-canvas[data-smoothing]',timeout=60000);assert not test.evaluate('document.documentElement.scrollWidth>innerWidth');assert test.locator('.lc-canvas').first.evaluate('e=>e.width===Math.round(e.getBoundingClientRect().width*devicePixelRatio)');test.close()
            assert not errors,errors;b.close()
    finally:server.shutdown();server.server_close();t.join()
    result={'status':'PASS','bands_verified':total,'formal_top50_rows_verified':84000,'eligible_range':[min(counts),max(counts)],'browser_js_errors':errors,'nearest_display':nearest,'previous_renderer_dimensions':baseline,'raster_measurements':measurements}
    Path(audit_path).write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--viewer',required=True);p.add_argument('--generation',required=True);p.add_argument('--audit-output',required=True)
    a=p.parse_args();torch.set_num_threads(1);validate(a.viewer,a.generation,a.audit_output)
