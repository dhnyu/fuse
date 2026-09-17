#!/usr/bin/env python3
"""Read-only location/browser validation; never loads embeddings or model payloads."""
import argparse
from functools import partial
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading

from playwright.sync_api import sync_playwright


def read(p):
    return json.loads(Path(p).read_text())


def sha(p):
    with Path(p).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def validate(viewer, audit_root):
    viewer=Path(viewer); audit_root=Path(audit_root); audit_root.mkdir(parents=True,exist_ok=True)
    receipt=read(viewer/'viewer_receipt.json'); parent=Path(receipt['parent_viewer']['path']).parent
    assert sha(parent/'viewer_receipt.json')==receipt['parent_viewer']['sha256']
    previous=read(parent/'viewer_receipt.json')
    for name,h in receipt['files'].items():
        assert sha(viewer/name)==h,name
    for name,h in previous['files'].items():
        assert sha(parent/name)==h,name
    for name,h in receipt['reused_files'].items():
        assert receipt['files'][name]==previous['files'][name]==h,name
    assert all(n in receipt['reused_files'] for n in previous['files'] if n.startswith(('queries/','scenes/','vector_assets/')))
    assert receipt['files']['band_evidence_receipt.json']==previous['files']['band_evidence_receipt.json']
    metadata=read(viewer/'location_metadata.json'); config=read(viewer/'config.json')
    assert len(config['models'])==28 and config['models']==read(parent/'config.json')['models']
    assert config['queries']==read(parent/'config.json')['queries']
    gallery=read(receipt['gallery']['path']);assert sha(receipt['gallery']['path'])==receipt['gallery']['sha256']
    assert set(metadata['scenes'])=={r['scene_id'] for r in gallery['body']['rows']}
    for g in gallery['body']['rows']:
        row=metadata['scenes'][g['scene_id']]
        assert (row['center_x'],row['center_y'],row['source_crs'])==(g['center_x'],g['center_y'],'EPSG:5186')
        assert row['eupmyeondong_code'][:5]==row['sigungu_code']
    user=metadata['scenes']['scn_4f609c4a79de5923a3b66063']
    assert user['sigungu_name']=='금천구' and user['eupmyeondong_name']=='독산1동'
    assert abs(user['longitude']-126.89031)<1e-5 and abs(user['latitude']-37.45650)<1e-5
    assert all(receipt[k] is False for k in ['scientific_mutation','ranking_recomputation','inference'])
    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self,*args):pass
    # Historical viewer validation also uses only 8765; conflicts fail, never fall back.
    server=ThreadingHTTPServer(('127.0.0.1',8765),partial(Quiet,directory=str(viewer.parent)))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    errors=[]; cases=[]; clicks=0; proof=[]; external=[]
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True)
            page=browser.new_page(viewport={'width':1800,'height':1200})
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.on('request',lambda req:external.append(req.url) if not req.url.startswith(('http://127.0.0.1:','data:','blob:')) else None)
            url=f'http://127.0.0.1:{server.server_port}/{viewer.name}/'
            page.goto(url)
            def wait(ids):
                try:
                    page.wait_for_function('''ids=>JSON.stringify([...document.querySelectorAll('#comparison>.column')].map(e=>e.dataset.scene))===JSON.stringify(ids)&&JSON.stringify([...document.querySelectorAll('.scene-location')].map(e=>e.dataset.locationScene))===JSON.stringify(ids)&&document.querySelectorAll('.lc-canvas[data-smoothing]').length===5&&[...document.querySelectorAll('.raster-pair img')].every(e=>e.complete&&e.naturalWidth===17)''',arg=ids,timeout=60000)
                except Exception:
                    print('WAIT_FAILURE',json.dumps({'expected':ids,'title':page.locator('#caseTitle').inner_text(),'selection':page.evaluate('bandsSelection'),'columns':page.locator('#comparison>.column').evaluate_all('es=>es.map(e=>e.dataset.scene)'),'error':page.locator('#error').inner_text(),'js_errors':errors},ensure_ascii=False),flush=True)
                    page.screenshot(path=str(audit_root/'failure.png'),full_page=True)
                    raise
                assert not page.locator('#error').is_visible()
            def check(ids):
                wait(ids)
                assert page.locator('.strip button').count()==30
                assert page.locator('.detail-host .thematic-map').count()==25
                assert page.locator('.vector-map>svg').count()==5
                assert page.locator('.scene-location').count()==5
                for i,sid in enumerate(ids):
                    row=metadata['scenes'][sid];block=page.locator('.scene-location').nth(i)
                    assert block.locator('.location-name').inner_text()==row['sigungu_name']+' · '+row['eupmyeondong_name']
                    assert block.locator('.location-lonlat').inner_text()==f"Lon {row['longitude']:.5f} · Lat {row['latitude']:.5f}"
                    assert block.locator('.location-xy').inner_text()==f"X {row['center_x']:,.1f} · Y {row['center_y']:,.1f}"
                    assert block.evaluate('e=>e.scrollHeight<=e.clientHeight&&e.scrollWidth<=e.clientWidth')
                assert len(set(page.locator('.scene-location').evaluate_all('els=>els.map(e=>e.getBoundingClientRect().height)')))==1
                assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
            for qi in [0,1,29]:
                qid=config['queries'][qi]['scene_id']; stored=read(viewer/'queries'/f'{qid}.json')
                for mid in ['main','ofat_d_256','cmp_DS','cmp_B9']:
                    for mode in ['standard','nonlocal']:
                        page.select_option('#query',str(qi));page.select_option('#model',mid);page.select_option('#mode',mode)
                        e=stored[mid][mode]; ids=[qid,e['bands']['most'][0]['gallery_scene_id']]+[e['bands'][k][0]['gallery_scene_id'] for k in ['top','middle','bottom']]
                        check(ids)
                        for band in ['top','middle','bottom']:
                            index={'top':2,'middle':3,'bottom':4}[band]
                            for pos in [0,4,9]:
                                page.locator(f'.strip button[data-band="{band}"][data-index="{pos}"]').click()
                                ids[index]=e['bands'][band][pos]['gallery_scene_id'];check(ids);clicks+=1
                        cases.append({'query_index':qi+1,'model':mid,'mode':mode})
                        print(f"Browser PASS query {qi+1} {mid} {mode}",flush=True)
            # Requested proof positions from cmp_FM, read existing band JSON only.
            q=config['queries'][0];e=read(viewer/'queries'/f"{q['scene_id']}.json")['cmp_FM']['standard']
            page.select_option('#query','0');page.select_option('#model','cmp_FM');page.select_option('#mode','standard')
            ids=[q['scene_id'],e['bands']['most'][0]['gallery_scene_id']]+[e['bands'][k][0]['gallery_scene_id'] for k in ['top','middle','bottom']]
            check(ids)
            for role,index in [('query1',0),('rank1',1),('middle_first',3),('bottom_first',4)]:
                proof.append({'role':role,**metadata['scenes'][ids[index]]})
            # Find a stored band/query occurrence for the exact user example; no new rank lookup.
            found=None
            for qr in config['queries']:
                data=read(viewer/'queries'/f"{qr['scene_id']}.json")
                for mid,modes in data.items():
                    for mode,entry in modes.items():
                        for band,items in entry['bands'].items():
                            for pos,r in enumerate(items):
                                if r['gallery_scene_id']==user['scene_id']:
                                    found=(qr,mid,mode,band,pos);break
                            if found:break
                        if found:break
                    if found:break
                if found:break
            assert found,'User example absent from existing bands'
            qr,mid,mode,band,pos=found;page.select_option('#query',str(qr['query_index']-1));page.select_option('#model',mid);page.select_option('#mode',mode)
            entry=read(viewer/'queries'/f"{qr['scene_id']}.json")[mid][mode]
            ids=[qr['scene_id'],entry['bands']['most'][0]['gallery_scene_id']]+[entry['bands'][k][0]['gallery_scene_id'] for k in ['top','middle','bottom']];check(ids)
            if band!='most':
                page.locator(f'.strip button[data-band="{band}"][data-index="{pos}"]').click();ids[{'top':2,'middle':3,'bottom':4}[band]]=user['scene_id'];check(ids)
            proof.append({'role':'user_xy_example','viewer_selection':{'query':qr['query_index'],'model':mid,'mode':mode,'band':band,'index':pos},**user})
            page.screenshot(path=str(audit_root/'user_example.png'),full_page=True)
            # All existing toggles and expanded thematic summaries remain functional.
            for layer in ['LC','DEM']:
                page.uncheck(f'[data-layer="{layer}"]');assert page.locator(f'[data-raster="{layer}"]').first.evaluate('e=>getComputedStyle(e).visibility')=='hidden';page.check(f'[data-layer="{layer}"]')
            for layer in ['B','R','P']:
                page.uncheck(f'[data-layer="{layer}"]');assert page.locator('body').evaluate('(e,k)=>e.classList.contains("hide-"+k)',layer);page.check(f'[data-layer="{layer}"]')
            details=page.locator('.detail-host details').first;details.locator('summary').first.click();assert not details.evaluate('e=>e.open');details.locator('summary').first.click();assert details.evaluate('e=>e.open')
            page.click('#toggleProvenance');assert page.locator('#provenance').is_visible();assert metadata['artifact_id'] in page.locator('#provenanceText').inner_text()
            vector=page.locator('.vector-map').first;vector.hover();page.mouse.wheel(0,-100);page.click('#resetZoom');assert page.evaluate('view.scale===1&&view.dx===0&&view.dy===0')
            for width in [1600,1200]:
                page.set_viewport_size({'width':width,'height':1100});check(ids)
            # UI status fixtures: rendering only, never modifying metadata files.
            statuses=page.evaluate('''()=>{const base={sigungu_name:'금천구',eupmyeondong_name:'독산1동',sigungu_join_status:'unique_match',dong_join_status:'unique_match'};return {missing:S10Locations.statusName({...base,dong_join_status:'no_polygon_match'},'dong'),ambiguous:S10Locations.statusName({...base,dong_join_status:'boundary_ambiguous'},'dong')}}''')
            assert statuses=={'missing':'행정동 확인 불가','ambiguous':'행정동 경계 지점'}
            # Side-by-side structural regression check on the same immutable first query.
            old=browser.new_page(viewport={'width':1800,'height':1200});old.goto(f'http://127.0.0.1:{server.server_port}/{parent.name}/')
            old.wait_for_selector('.lc-canvas[data-smoothing]',timeout=60000)
            page.set_viewport_size({'width':1800,'height':1200});page.goto(url);page.wait_for_selector('.scene-location',timeout=60000)
            old_ids=old.locator('#comparison>.column').evaluate_all('es=>es.map(e=>e.dataset.scene)');check(old_ids)
            measure='es=>es.map(e=>({width:e.getBoundingClientRect().width,strip:e.querySelectorAll(".strip button").length,vectorHeight:e.querySelector(".vector-map").getBoundingClientRect().height,lcWidth:e.querySelector(".lc-canvas").width,demWidth:e.querySelector(".raster-pair img").naturalWidth,thematics:e.querySelectorAll(".thematic-map").length}))'
            baseline=old.locator('#comparison>.column').evaluate_all(measure);current=page.locator('#comparison>.column').evaluate_all(measure);assert baseline==current,(baseline,current)
            page.screenshot(path=str(audit_root/'location_viewer.png'),full_page=True)
            old.close();assert not errors,errors;assert not external,external;browser.close()
    finally:
        server.shutdown();server.server_close();thread.join()
    result={'status':'PASS','viewer':str(viewer),'qc':receipt['qc'],'browser_cases':cases,'thumbnail_clicks':clicks,'proof_examples':proof,'javascript_errors':errors,'external_requests':external,'ui_status_fixtures':statuses,'parent_structure':baseline,'new_structure':current,'reused_files_verified':len(receipt['reused_files']),'scientific_mutation':False,'ranking_recomputation':False,'inference':False}
    (audit_root/'validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps({'status':'PASS','cases':len(cases),'clicks':clicks,'output':str(audit_root/'validation.json')}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--viewer',required=True);parser.add_argument('--audit-root',required=True)
    args=parser.parse_args();validate(args.viewer,args.audit_root)
