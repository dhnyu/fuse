#!/usr/bin/env python3
"""Validate Hub routes without scientific computation or viewer mutation."""
import argparse
import json
import mimetypes
from pathlib import Path
from urllib.parse import urlparse,unquote
from playwright.sync_api import sync_playwright
from serve_viewer_hub import ROOT,TARGETS,URL,verify_root,check,sha


def validate(offline=False):
    verify_root()
    serving=None if offline else check()
    before={}
    for label,target in TARGETS.items():
        receipt=json.loads((target/'viewer_receipt.json').read_text())
        before[label]={}
        for file,checksum in receipt['files'].items():
            actual=sha(target/file)
            if actual!=checksum:raise RuntimeError(f'Existing artifact checksum mismatch: {label}/{file}')
            before[label][file]=actual
        before[label]['viewer_receipt.json']=sha(target/'viewer_receipt.json')
    errors=[];cases=[]
    base='https://viewer-hub.test' if offline else URL
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,args=['--no-sandbox'])
        context=browser.new_context(service_workers='block',viewport={'width':1600,'height':1000})
        page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
        context.new_cdp_session(page).send('Network.setCacheDisabled',{'cacheDisabled':True})
        if offline:
            def route(r):
                relative=unquote(urlparse(r.request.url).path).lstrip('/')
                file=ROOT/relative
                if file.is_dir():file=file/'index.html'
                if not file.is_file():r.fulfill(status=404,body='missing');return
                r.fulfill(status=200,body=file.read_bytes(),content_type=mimetypes.guess_type(file)[0] or 'application/octet-stream')
            page.route(base+'/**',route)
        page.goto(base+'/')
        assert page.title()=='Spatial Scene Inspector'
        links=page.locator('a');assert links.count()==5
        assert all(links.nth(i).is_visible() for i in range(5))
        destinations=links.evaluate_all('(xs)=>xs.map(x=>x.getAttribute("href"))')
        page.get_by_role('link',name='Canonical 100-query').click()
        page.wait_for_function("document.querySelectorAll('#comparison .column').length===5",timeout=60000)
        assert page.locator('#query option').count()==100
        assert page.locator('#model option').count()==28
        assert page.locator('#model').input_value()=='cmp_FM'
        page.select_option('#mode','nonlocal')
        page.wait_for_function("document.querySelectorAll('#comparison .column').length===5 && new URL(location).searchParams.get('mode')==='nonlocal'",timeout=60000)
        cases.append({'route':'canonical','queries':100,'models':28,'selected_model':'cmp_FM','modes':['standard','nonlocal']})
        page.goto(base+'/')
        for href in destinations[1:]:
            page.locator('a[href="'+href+'"]').click()
            page.wait_for_function("document.body.dataset.readyMode===document.querySelector('#mode').value",timeout=60000)
            name=page.locator('#set').input_value()
            assert page.locator('#set option').count()==8
            assert page.locator('#query option').count()==100
            assert page.locator('#model').count()==0
            assert page.locator('h1').inner_text()=='Final FM HIGH/LOW Inspector'
            default='standard' if name.startswith('STANDARD') else 'nonlocal'
            assert page.locator('#mode').input_value()==default
            for mode in ('standard','nonlocal'):
                page.select_option('#mode',mode)
                page.wait_for_function("document.body.dataset.readyMode===document.querySelector('#mode').value && document.querySelectorAll('#comparison .column').length===5",timeout=60000)
                assert page.locator('#set').input_value()==name
                assert page.locator('#query option').count()==100
                assert page.locator('#error').is_hidden()
            # The dropdown changes fixed sets as well as the launcher deep links.
            alternate='STANDARD_LOW' if name!='STANDARD_LOW' else 'NONLOCAL_HIGH'
            page.select_option('#set',alternate)
            page.wait_for_function("document.body.dataset.readyMode===document.querySelector('#mode').value && document.body.dataset.readyQuery==='0'",timeout=60000)
            assert page.locator('#query option').count()==100
            cases.append({'set':name,'queries':100,'default':default,'modes':['standard','nonlocal'],'fm_only':True,'set_dropdown':True})
            page.goto(base+'/')
        assert not errors,errors
        browser.close()
    after={label:{file:sha(target/file) for file in before[label]} for label,target in TARGETS.items()}
    assert before==after,'Viewer bytes changed'
    if not offline:
        assert check()['pid']==serving['pid'],'Server restarted during navigation'
    return {'status':'PASS','method':'offline Chromium route interception' if offline else 'live HTTP Chromium','serving':serving,'hub_links':destinations,'cases':cases,'javascript_errors':errors,'immutable_files_verified':{label:len(files) for label,files in before.items()},'before_after_unchanged':True}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--offline',action='store_true',help='File-route browser validation only; does not claim live serving')
    args=parser.parse_args()
    print(json.dumps(validate(args.offline),indent=2))
