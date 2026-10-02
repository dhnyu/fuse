"""Read-only UI parity and S10 band readback for corrected B6 export."""
from pathlib import Path
import sys,json,hashlib
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from s10_all_models import unpack_query
from playwright.sync_api import sync_playwright
OLD=Path('/mnt/hdd002/dhnyu/fusedata/retrieval_data/reduced/s10_all_model_viewers/viewer_composite_c_e067ad37b57973b09f35349b')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main(root,url,oldurl,out):
 root=Path(root);out=Path(out);out.mkdir(parents=True,exist_ok=True);cfg=json.loads((root/'config.json').read_text());receipt={'cases':[],'errors':[],'ui_authority':str(OLD),'url':url}
 for name in ['augmentation.css','style.css','legacy_bands.css','bands.css','locations.css','prototype.css','app.js','helpers.js','locations.js','index.json']:
  assert sha(root/name)==sha(OLD/name),name
 def done(p):
  p.wait_for_function('inspection.thumbsReady>0&&navigationReady',timeout=60000)
  assert p.locator('#error').is_hidden(),p.locator('#error').inner_text()
 def verify(p):
  got=p.evaluate('({q:queryIndex+1,model:document.querySelector("#model").value,mode:document.querySelector("#mode").value,n:activeEvidence.candidate_count,bands:Object.fromEntries(Object.entries(activeEvidence.bands).map(([k,rs])=>[k,rs.map(r=>[r.rank,r.scene_index,r.similarity,r.geographic_distance_m])]))})')
  expected=unpack_query((root/'bands'/got['model']/f"{(got['q']-1)//100:03d}.bin").read_bytes(),got['q'])[got['mode']]
  assert got['bands']==expected['bands'] and got['n']==expected['candidate_count']
  assert p.locator('.column').count()==5 and p.locator('.strip button>img').count()==30
  if got['mode']=='nonlocal':assert all(r[3]>=2000 and r[1]!=got['q'] for rs in got['bands'].values() for r in rs)
  receipt['cases'].append({k:v for k,v in got.items() if k!='bands'})
 with sync_playwright() as pw:
  browser=pw.chromium.launch(headless=True,args=['--no-sandbox']);p=browser.new_page(viewport={'width':1600,'height':1100});p.on('pageerror',lambda e:receipt['errors'].append(str(e)))
  p.goto(url);done(p);assert p.input_value('#mode')=='nonlocal' and p.locator('#model option').count()==3;verify(p)
  p.screenshot(path=str(out/'b6.png'),full_page=True)
  layout=p.locator('.column').evaluate_all('es=>es.map(e=>({width:e.getBoundingClientRect().width,x:e.getBoundingClientRect().x}))')
  query=p.locator('.column:first-child .composite-map img').evaluate('im=>im.naturalWidth');assert query==500
  if oldurl:
   old=browser.new_page(viewport={'width':1600,'height':1100});old.goto(oldurl+'?model=cmp_B6&mode=nonlocal&order=original&pos=1');done(old);old.screenshot(path=str(out/'old.png'),full_page=True)
   oldlayout=old.locator('.column').evaluate_all('es=>es.map(e=>({width:e.getBoundingClientRect().width,x:e.getBoundingClientRect().x}))');assert oldlayout==layout
   assert old.locator('.column:first-child .composite-map img').get_attribute('data-scene')==p.locator('.column:first-child .composite-map img').get_attribute('data-scene')
   receipt['identical_column_layout']=layout;old.close()
  for m in cfg['models']:
   p.select_option('#model',m['configuration']);done(p)
   for mode in ['standard','nonlocal']:
    p.select_option('#mode',mode);done(p)
    for q in [1,4500,9000]:p.evaluate('go',q);done(p);verify(p)
  p.select_option('#order','roadfirst');assert p.evaluate('displayOrder.length')==9000
  p.fill('#position','1');p.click('#positionGo');done(p);assert p.evaluate('rowFor(queryIndex+1).n_roads')>0
  for order in ['asc','desc','original']:
   p.select_option('#order',order);p.fill('#position','2');p.click('#positionGo');done(p);verify(p)
  p.click('#next');done(p);assert p.input_value('#position')=='3';p.click('#prev');done(p);assert p.input_value('#position')=='2'
  p.click('#random');done(p);verify(p)
  for band in ['top','middle','bottom']:
   p.locator(f'.strip button[data-band={band}][data-index="9"]').click();done(p);verify(p)
  sid=p.evaluate('config.queries[8999].scene_id');p.fill('#search',sid);p.wait_for_function('filtered.length===1');p.locator('#searchPanel').evaluate('d=>d.open=true');p.locator('#searchResults button').click();done(p);assert p.evaluate('queryIndex')==8999
  for layer in ['LC','H','B','R','P']:
   p.uncheck('[data-layer='+layer+']');p.wait_for_function('document.querySelectorAll(".composite-map svg").length===5');p.check('[data-layer='+layer+']');p.wait_for_function('document.querySelectorAll(".composite-map img").length===5')
  p.locator('.detail-host').first.evaluate('d=>d.open=true');p.wait_for_function('document.querySelector(".detail-host").dataset.loaded==="true"')
  state=p.url;p.reload();done(p);assert p.url==state;verify(p)
  browser.close()
 assert not receipt['errors'];receipt['status']='PASS';(out/'browser.json').write_text(json.dumps(receipt,indent=2));print('PASS',len(receipt['cases']),'browser readbacks')
if __name__=='__main__':main(*sys.argv[1:])
