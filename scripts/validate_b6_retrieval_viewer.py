"""Read-only export and browser checks for the temporary B6 viewer."""
import sys,json,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
import torch,numpy as np
from playwright.sync_api import sync_playwright

def main(root,url):
 torch.set_num_threads(1);root=Path(root);c=json.loads((root/'catalog.json').read_text());a=json.loads((root/'acceptance.json').read_text())
 for row in json.loads((root/'manifest.json').read_text())['files']:assert hashlib.sha256((root/row['path']).read_bytes()).hexdigest()==row['sha256']
 assert len(c['queries'])==2000 and len(c['gallery'])==1000
 assert sum(not c['gallery'][q['scene']]['roads'] for q in c['queries'])==288
 paths=[p for p in a['identity']['parents'] if p.endswith('.pt')]
 for ai,arm in enumerate(c['arms']):
  p=next(p for p in paths if '/'+arm['name']+'/' in p)
  v=torch.load(p,map_location='cpu',weights_only=False);sim=v['vectors'][:2000]@v['vectors'][2000:].T
  rank=torch.argsort(sim,descending=True,stable=True)
  for q in c['queries']:
   rows=json.loads((root/'queries'/f"{q['i']}.json").read_text())['arms'][ai]
   assert c['gallery'][q['scene']]['id']==v['scene_ids'][q['i']//2]
   for k,g,s in rows:assert int(rank[q['i'],k-1])==g and float(sim[q['i'],g])==s
   summary=q['arms'][ai];assert summary['top']==int(rank[q['i'],0])
   assert summary['rank']==int((rank[q['i']]==q['scene']).nonzero()[0])+1
  print(arm['name'],'all exported rankings/scores/IDs exact')
 with sync_playwright() as p:
  browser=p.chromium.launch(headless=True,args=['--no-sandbox']);page=browser.new_page(viewport={'width':1560,'height':1100});errors=[]
  page.on('pageerror',lambda e:errors.append(str(e)));page.goto(url);page.wait_for_selector('.card');page.wait_for_function('document.querySelectorAll(".card").length===30')
  page.wait_for_function('Array.from(document.querySelectorAll("#query img")).every(x=>x.complete&&x.naturalWidth>0)');page.screenshot(path='/tmp/b6_viewer_default.png',full_page=False)
  for f in ['nonempty','zero','count1','count9','count50','length250–500','disagree','gwin','pwin','failure','gp','loss']:
   page.select_option('#filter',f);page.wait_for_timeout(180)
   expected=page.evaluate('C.queries.filter(q=>match(q,document.getElementById("filter").value)).length')
   assert (f'{expected} filtered' in page.locator('#status').inner_text()) if expected else ('0 matching' in page.locator('#status').inner_text())
  page.select_option('#filter','all')
  for depth,num in [('1',3),('5',15),('10',30),('50',150),('middle',30),('lower',30)]:
   page.select_option('#depth',depth);page.wait_for_function(f'document.querySelectorAll(".card").length==={num}')
  page.select_option('#depth','10');page.fill('#jump','1999');page.click('#go');page.wait_for_function('current===1998');page.wait_for_timeout(200)
  page.click('#next');page.wait_for_function('current===1999');page.click('#prev');page.wait_for_function('current===1998')
  page.fill('#jump',c['queries'][12]['id']);page.click('#go');page.wait_for_function('current===12')
  page.select_option('#map','lc');page.wait_for_function('Array.from(document.querySelectorAll("#query img")).every(x=>x.complete&&x.naturalWidth>0)');page.screenshot(path='/tmp/b6_viewer_landcover.png',full_page=False)
  page.select_option('#map','svg');page.select_option('#filter','zero');page.wait_for_function('Array.from(document.querySelectorAll("#query img")).every(x=>x.complete&&x.naturalWidth>0)');page.screenshot(path='/tmp/b6_viewer_zero.png',full_page=False)
  for option in page.locator('#sort option').evaluate_all('(x)=>x.map(o=>o.value)'):
   page.select_option('#sort',option);page.wait_for_timeout(100)
  page.click('#random');page.wait_for_timeout(200)
  bookmark=page.url;page.reload();page.wait_for_selector('.card');assert page.url==bookmark
  assert not errors,errors
  assert page.locator('img').evaluate_all('(images)=>images.filter(x=>x.loading!=="lazy" || x.getBoundingClientRect().top<1100).every(x=>x.complete && x.naturalWidth>0)')
  browser.close()
 print('PASS: selected vectors, all 420000 rank rows, zero-road labels, filters/navigation/depth/bookmarks/browser console')
if __name__=='__main__':main(*sys.argv[1:])
