#!/usr/bin/env python3
"""Read-only browser and full file/QC acceptance of the 100-query viewer."""
import argparse
import json
from pathlib import Path
import sys
from playwright.sync_api import sync_playwright
from serve_s10_viewer import ROOT, BASE_URL, ACCESS_URL, verify_http
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from retrieval_artifacts import read_json as read,file_hash


def validate(viewer,audit_root):
    viewer=Path(viewer);audit_root=Path(audit_root);audit_root.mkdir(parents=True,exist_ok=True)
    if viewer.resolve()!=ROOT:raise ValueError('Only the canonical production root is supported')
    serving=verify_http()
    receipt=read(viewer/'viewer_receipt.json');cfg=read(viewer/'config.json');metadata=read(viewer/'location_metadata.json')
    for name,h in receipt['files'].items():assert file_hash(viewer/name)==h,name
    assert len(cfg['queries'])==len({q['scene_id'] for q in cfg['queries']})==100
    assert len(cfg['models'])==28 and cfg['gallery_count']==9000
    assert sum(q['object_count']<10 for q in cfg['queries'])<=5
    assert cfg['acceptance']==receipt['parent']
    total=0
    for q in cfg['queries']:
        data=read(viewer/'queries'/f"{q['scene_id']}.json")
        assert set(data)=={m['id'] for m in cfg['models']}
        for mid,modes in data.items():
            assert set(modes)=={'standard','nonlocal'}
            for mode,e in modes.items():
                n=e['candidate_count'];assert n==8999 if mode=='standard' else 50<=n<=8999
                expected={'most':[1],'top':list(range(2,12)),'middle':list(range((n-10)//2+1,(n-10)//2+11)),'bottom':list(range(n-9,n+1))}
                for band,rows in e['bands'].items():
                    assert [r['rank'] for r in rows]==expected[band]
                    for r in rows:
                        assert r['query_id']==q['scene_id'] and r['model_id']==mid and r['retrieval_mode']==mode
                        assert r['gallery_scene_id']!=q['scene_id']
                        if mode=='nonlocal':assert r['geographic_distance_m']>=2000
                    total+=len(rows)
    assert total==173600
    errors=[];cases=[];clicks=0
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True)
        context=browser.new_context(service_workers='block',viewport={'width':1800,'height':1200})
        page=context.new_page()
        cdp=context.new_cdp_session(page);cdp.send('Network.enable');cdp.send('Network.setCacheDisabled',{'cacheDisabled':True});cdp.send('Network.setBypassServiceWorker',{'bypass':True})
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(ACCESS_URL)
        page.wait_for_selector('#query option',state='attached')
        assert page.locator('#query option').count()==100
        assert page.locator('#query option').first.inner_text().startswith('1 / 100')
        assert page.locator('#query option').last.inner_text().startswith('100 / 100')
        assert page.locator('#model option').count()==28
        dom_options=page.locator('#query option').all_text_contents()
        page.wait_for_function('document.body.dataset.configSha')
        document_sha=page.locator('body').get_attribute('data-config-sha')
        assert document_sha==serving['http_config_sha256']
        def check(ids):
            page.wait_for_function('''ids=>JSON.stringify([...document.querySelectorAll('#comparison>.column')].map(e=>e.dataset.scene))===JSON.stringify(ids)&&JSON.stringify([...document.querySelectorAll('.scene-location')].map(e=>e.dataset.locationScene))===JSON.stringify(ids)&&document.querySelectorAll('.lc-canvas[data-smoothing]').length===5&&[...document.querySelectorAll('.raster-pair img')].every(e=>e.complete&&e.naturalWidth===17)''',arg=ids,timeout=60000)
            assert not page.locator('#error').is_visible()
            assert page.locator('.strip button').count()==30
            assert page.locator('.detail-host .thematic-map').count()==25
            assert page.locator('.vector-map>svg').count()==5
            for i,sid in enumerate(ids):
                loc=metadata['scenes'][sid];block=page.locator('.scene-location').nth(i)
                assert block.locator('.location-name').inner_text()==loc['sigungu_name']+' · '+loc['eupmyeondong_name']
                assert block.locator('.location-lonlat').inner_text()==f"Lon {loc['longitude']:.5f} · Lat {loc['latitude']:.5f}"
            assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
        for qi in [0,29,30,49,99]:
            sid=cfg['queries'][qi]['scene_id'];stored=read(viewer/'queries'/f'{sid}.json')
            # Direct page loading as well as dropdown navigation.
            page.goto(f'{BASE_URL}/query_{qi+1:02d}.html')
            page.wait_for_selector('#query option',state='attached')
            assert page.input_value('#query')==str(qi)
            for mid in ['main','ofat_d_256','cmp_DS','cmp_B9']:
                for mode in ['standard','nonlocal']:
                    page.select_option('#query',str(qi));page.select_option('#model',mid);page.select_option('#mode',mode)
                    e=stored[mid][mode];ids=[sid,e['bands']['most'][0]['gallery_scene_id']]+[e['bands'][k][0]['gallery_scene_id'] for k in ['top','middle','bottom']]
                    check(ids)
                    for band,index in [('top',2),('middle',3),('bottom',4)]:
                        page.locator(f'.strip button[data-band="{band}"][data-index="9"]').click()
                        ids[index]=e['bands'][band][9]['gallery_scene_id'];check(ids);clicks+=1
                    cases.append({'query':qi+1,'model':mid,'mode':mode,'url':page.url})
                    print(f'Browser PASS {qi+1} {mid} {mode}',flush=True)
            page.screenshot(path=str(audit_root/f'query_{qi+1}.png'),full_page=True)
        # Switch to different queries through the dropdown without reloading.
        for qi in [0,29,30,49,99]:
            page.select_option('#query',str(qi))
            sid=cfg['queries'][qi]['scene_id']
            e=read(viewer/'queries'/f'{sid}.json')['cmp_B9']['nonlocal']
            ids=[sid,e['bands']['most'][0]['gallery_scene_id']]+[e['bands'][k][0]['gallery_scene_id'] for k in ['top','middle','bottom']]
            check(ids)
            assert f'Query {qi+1} / 100' in page.locator('#caseTitle').inner_text()
        vector=page.locator('.vector-map').first;vector.hover();page.mouse.wheel(0,-100)
        page.click('#resetZoom');assert page.evaluate('view.scale===1&&view.dx===0&&view.dy===0')
        for layer in ['LC','DEM']:
            page.uncheck(f'[data-layer="{layer}"]');assert page.locator(f'[data-raster="{layer}"]').first.evaluate('e=>getComputedStyle(e).visibility')=='hidden';page.check(f'[data-layer="{layer}"]')
        for layer in ['B','R','P']:
            page.uncheck(f'[data-layer="{layer}"]');assert page.locator('body').evaluate('(e,k)=>e.classList.contains("hide-"+k)',layer);page.check(f'[data-layer="{layer}"]')
        details=page.locator('.detail-host details').first;details.locator('summary').first.click();assert not details.evaluate('e=>e.open');details.locator('summary').first.click();assert details.evaluate('e=>e.open')
        page.click('#toggleProvenance');assert page.locator('#provenance').is_visible();assert metadata['artifact_id'] in page.locator('#provenanceText').inner_text()
        for width in [1600,1200]:page.set_viewport_size({'width':width,'height':1100});check(ids)
        assert not errors,errors;browser.close()
    result={'status':'PASS','serving':serving,'dom_query_count':len(dom_options),'document_config_sha256':document_sha,'selected_options':{str(i+1):dom_options[i] for i in [0,29,30,49,99]},'viewer':str(viewer),'browser_cases':cases,'thumbnail_clicks':clicks,'band_rows':total,'javascript_errors':errors}
    (audit_root/'validation.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--viewer',required=True);p.add_argument('--audit-root',required=True);a=p.parse_args();validate(a.viewer,a.audit_root)
