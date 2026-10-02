import sys,json,pathlib,time,base64,io
import numpy as np
from PIL import Image
from playwright.sync_api import sync_playwright
sys.path.insert(0,'/members/dhnyu/fuse/python')
from s10_all_models import unpack_query
P=pathlib.Path('/mnt/hdd002/dhnyu/fusedata/tmp/fuse/variant_c_20260922');v=json.loads((P/'viewer.json').read_text());root=pathlib.Path(v['root']);cfg=json.loads((root/'config.json').read_text());bdata={'root':str(root/'bands'),'models':{m['configuration']:m for m in cfg['models']}};idx=json.loads((root/'index.json').read_text());ids=[r[1] for r in idx['rows']];cases=[];out={'cases':cases,'errors':[],'actions':{},'palette':{}};orderdocs={}
for model,m in bdata['models'].items():orderdocs[model]=json.loads((pathlib.Path(bdata['root'])/m['orders']).read_text())
def save(): (P/'browser_validation.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
def done(p,q=None):
 p.wait_for_function('inspection.thumbsReady>0&&navigationReady',timeout=45000)
 if q:assert p.evaluate('queryIndex+1')==q
 assert p.locator('#error').is_hidden()
def snap(p):return p.evaluate("()=>({q:queryIndex+1,model:document.querySelector('#model').value,mode:document.querySelector('#mode').value,n:activeEvidence.candidate_count,bands:Object.fromEntries(Object.entries(activeEvidence.bands).map(([k,rs])=>[k,rs.map(r=>[r.rank,r.scene_index,r.similarity,r.geographic_distance_m])])),main:inspection.mainReady-inspection.started,thumbs:inspection.thumbsReady-inspection.started})")
def verify(p,model,mode,q):
 got=snap(p);expected=unpack_query((pathlib.Path(bdata['root'])/model/f'{(q-1)//100:03d}.bin').read_bytes(),q);assert got['q']==q and got['model']==model and got['mode']==mode;assert got['n']==expected[mode]['candidate_count'] and got['bands']==expected[mode]['bands'];assert got['main']<got['thumbs'];cases.append({'model':model,'mode':mode,'query':q,'order':p.input_value('#order'),'position':p.input_value('#position'),'main_ms':got['main'],'thumbs_ms':got['thumbs']});save()
with sync_playwright() as pw:
 browser=pw.chromium.launch(headless=True,args=['--no-sandbox']);ctx=browser.new_context(viewport={'width':1600,'height':1000});p=ctx.new_page();p.on('pageerror',lambda e:out['errors'].append(str(e)));p.goto('http://127.0.0.1:18773/');done(p);assert p.locator('#model option').count()==28 and p.locator('#model optgroup').count()==2 and p.locator('#preset').count()==0
 for model in ['cmp_FM','cmp_A4','cmp_B9','cmp_DS','ofat_d_64','ofat_d_256']:
  q=p.evaluate('queryIndex+1');p.select_option('#model',model);done(p,q)
  for mode in ['standard','nonlocal']:
   q=p.evaluate('queryIndex+1');p.select_option('#mode',mode);done(p,q)
   for order in ['original','asc','desc']:
    before=p.evaluate('({q:queryIndex+1,serial,resources:performance.getEntriesByType("resource").length,main:document.querySelector(".column").dataset.scene})');p.select_option('#order',order);p.wait_for_timeout(50);assert p.evaluate('queryIndex+1')==before['q'] and p.evaluate('serial')==before['serial'];assert p.evaluate('performance.getEntriesByType("resource").length')==before['resources'];expected=list(range(1,9001)) if order=='original' else orderdocs[model]['modes'][mode][order];assert p.evaluate('displayOrder')==expected
    for pos in [1,4500,9000]:
     p.fill('#position',str(pos));p.click('#positionGo');q=expected[pos-1];done(p,q);verify(p,model,mode,q)
   q=p.evaluate('queryIndex+1');p.select_option('#order','original');done(p,q);assert int(p.input_value('#position'))==q
   p.locator('.detail-host').first.evaluate('(d)=>d.open=true');p.wait_for_function('document.querySelector(".detail-host").dataset.loaded==="true"');full=p.evaluate('({id:scenes[0].scene_id,lc:document.querySelector(".lc-canvas").dataset.png,dem:document.querySelector(".raster-pair img").src,charts:[...document.querySelectorAll(".column:first-child [data-raster=LC] .legend-row")].map(r=>({label:r.title,value:+r.dataset.value,color:r.querySelector("i").style.getPropertyValue("--category-color")}))})');overlay=json.loads((root/'lc'/f'{full["id"]}.json').read_text());assert full['lc']==overlay['lc'];assert full['charts']==[{'label':r['label'],'value':r['value'],'color':r['color']} for r in overlay['chart']]
   old=json.loads((root/'details'/f'{full["id"]}.json').read_text());assert full['dem']==old['dem']
  print(model,'PASS',len(cases),flush=True)
 # Additional content cases, both modes, exact bands and stable scene search.
 objects={r[0]:r[11] for r in idx['rows']};airport=ids.index('scn_fb994acfc7bb85ec26e12ab2')+1;dense=max(objects,key=objects.get);sparse=min((q for q,n in objects.items() if n>=20),key=lambda q:(objects[q],q));out['special_queries']={'airport':airport,'dense':dense,'sparse_obj20':sparse}
 p.select_option('#model','cmp_FM');done(p)
 for q in [airport,dense,sparse]:
  for mode in ['standard','nonlocal']:
   p.select_option('#mode',mode);done(p);p.evaluate('go',q);done(p,q);verify(p,'cmp_FM',mode,q)
 for band in ['top','middle','bottom']:
  sid=p.evaluate('(k)=>activeEvidence.bands[k][9].gallery_scene_id',band);p.locator(f'.strip button[data-band={band}][data-index="9"]').click();done(p);assert p.locator(f'.column[data-band={band}]').get_attribute('data-scene')==sid
 out['actions']['thumbnail_selection']=True
 p.select_option('#order','desc');q=p.evaluate('displayOrder[4500]');p.evaluate('go',q);done(p,q);p.click('#next');done(p);assert int(p.input_value('#position'))==4502;p.click('#prev');done(p,q);out['actions']['sorted_next_prev']=True
 p.fill('#search',ids[-1]);p.wait_for_function('filtered.length===1');p.locator('#searchPanel').evaluate('d=>d.open=true');p.locator('#searchResults button').click();done(p,9000);out['actions']['scene_search']=True
 p.fill('#search','공항동');p.wait_for_timeout(180);assert p.locator('#searchResults button').count()>0;out['actions']['location_search']=True
 # Deep links: position binding and stable scene override regardless of order.
 for url,q in [('?model=cmp_B9&mode=nonlocal&order=asc&pos=1',orderdocs['cmp_B9']['modes']['nonlocal']['asc'][0]),('?model=ofat_d_64&mode=standard&order=desc&pos=1&scene='+ids[4499],4500)]:p.goto('http://127.0.0.1:18773/'+url);done(p,q)
 out['actions']['deep_links']=True
 # Superseded async model loads cannot replace the final selection.
 p.evaluate("()=>{document.querySelector('#model').value='cmp_DS';switchModelMode();document.querySelector('#model').value='cmp_FM';switchModelMode()}");done(p,4500);assert p.input_value('#model')=='cmp_FM';verify(p,'cmp_FM','standard',4500);out['actions']['stale_switch']=True
 # Exact actual default raster display pixels, including all 18 experimental scenes.
 import hashlib
 assets=json.loads((P/'assets.json').read_text());experimental=list(assets['visual_regression']);additional=[1,2,50,100,1000,4500,8999,airport,dense,sparse]+[ids.index(sid)+1 for sid in json.loads((P/'additional_scenes.json').read_text()).values()]
 out['display_pixels']=[]
 for sid in dict.fromkeys(experimental+[ids[q-1] for q in additional]):
  q=ids.index(sid)+1;p.evaluate('go',q);done(p,q)
  digest=p.locator('.column:first-child .composite-map img').evaluate('''async im=>{const c=document.createElement('canvas');c.width=c.height=500;c.getContext('2d').drawImage(im,0,0);return [...new Uint8Array(await crypto.subtle.digest('SHA-256',c.getContext('2d').getImageData(0,0,500,500).data))].map(x=>x.toString(16).padStart(2,'0')).join('')}''')
  expected=hashlib.sha256(Image.open(pathlib.Path(assets['root'])/'main'/f'{sid}.{assets.get("main_format","png")}').convert('RGBA').tobytes()).hexdigest();assert digest==expected
  out['display_pixels'].append({'scene':sid,'canvas_rgba_sha256':digest,'exact':True})
 # Default thumbnail path is pre-rendered images, with no source-SVG/thematic fetch.
 assert p.locator('.strip button>img').count()==30
 out['actions']['prerendered_thumbnails']=True
 saved=snap(p);url=p.url
 for layer in ['LC','H','B','R','P']:
  p.uncheck('[data-layer='+layer+']');p.wait_for_function('document.querySelectorAll(".composite-map svg").length===5')
  assert snap(p)['bands']==saved['bands'] and p.url==url
  if layer in ['B','R','P']:assert p.locator('.column:first-child .composite-map [data-composite-layer='+layer+']').evaluate_all('es=>es.every(e=>e.getAttribute("visibility")=="hidden")')
  p.check('[data-layer='+layer+']');p.wait_for_function('document.querySelectorAll(".composite-map img").length===5')
 p.uncheck('[data-layer=B]');p.wait_for_function('document.querySelectorAll(".composite-map svg").length===5');p.evaluate('go',2);done(p,2);assert not p.is_checked('[data-layer=B]');p.check('[data-layer=B]');p.wait_for_function('document.querySelectorAll(".composite-map img").length===5')
 out['actions']['layer_toggles_display_only_and_persist']=True
 p.locator('.detail-host').first.evaluate('d=>d.open=true');p.wait_for_function('document.querySelector(".detail-host").dataset.loaded==="true"');assert p.locator('.detail-host .vector-map svg').count()>=1
 p.screenshot(path=str(P/'viewer.png'));save()
 # Real production LC draw function tested on a one-hot22-class100x100 fixture.
 palette=json.loads((root/'palette.json').read_text());expected=[r['rgb'] for r in palette['rows']];rgba=np.zeros((100,100,4),dtype=np.uint8)
 for k,rgb in enumerate(expected):rgba[:,k*4:(k+1)*4,:3]=rgb;rgba[:,k*4:(k+1)*4,3]=255
 buf=io.BytesIO();Image.fromarray(rgba).save(buf,format='PNG');url='data:image/png;base64,'+base64.b64encode(buf.getvalue()).decode()
 rendered=p.evaluate('''async url=>{const c=document.createElement('canvas');c.style.width='100px';c.style.height='100px';c.dataset.png=url;document.body.append(c);await drawLC(c);const ctx=c.getContext('2d'),values=Array.from({length:22},(_,i)=>Array.from(ctx.getImageData(i*4+1,1,1,1).data)),invalid=Array.from(ctx.getImageData(99,1,1,1).data);c.remove();return {values,invalid}}''',url);assert rendered['values']==[rgb+[255] for rgb in expected];assert rendered['invalid'][3]==0;out['palette']['canvas_22_exact']=rendered
 p.goto('http://127.0.0.1:18773/palette.html');actual=p.locator('.swatch').evaluate_all('es=>es.map(e=>getComputedStyle(e).backgroundColor)');assert actual==['rgb('+', '.join(map(str,rgb))+')' for rgb in expected];out['palette']['swatches_22_exact']=True;p.screenshot(path=str(P/'official_palette.png'),full_page=True);ctx.close();browser.close()
assert not out['errors'],out['errors'];out['status']='PASS';save();print('BROWSER PASS',len(cases),flush=True)
