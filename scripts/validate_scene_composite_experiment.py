import json,pathlib,sys,hashlib,base64,io,subprocess,time
import numpy as np
import torch
from PIL import Image
from playwright.sync_api import sync_playwright
sys.path.insert(0,'scripts');import build_scene_composite_experiment as c
a=c.AUDIT;r=c.read(a/'result.json');root=pathlib.Path(r['root']);view=pathlib.Path(r['viewer']);m=c.read(root/'manifest.json');checks={};torch.set_num_threads(1)
colors=np.array([x['rgb'] for x in c.read('config/retrieval_lc_official_palette.json')['rows']])
for rec in m['records']:
 sid=rec['row']['scene_id'];sample=torch.load(c.INPUT/(sid+'.pt'),weights_only=True,mmap=True,map_location='cpu');ras=sample['rasters'];frac=ras['landcover_class_fraction'].numpy();valid=ras['landcover_valid_mask'].numpy().astype(bool);lc=c.read(c.VIEWER/'lc'/(sid+'.json'))
 rgba=np.concatenate([np.uint8(np.clip(np.einsum('cyx,ck->yxk',frac.astype(float),colors),0,255)),valid.astype('uint8')[...,None]*255],axis=2)
 assert np.array_equal(rgba,np.asarray(c.uri_image(lc['lc'])))
 assert hashlib.sha256(frac.tobytes()).hexdigest()==lc['fraction_sha256']
 assert hashlib.sha256(valid.tobytes()).hexdigest()==lc['valid_sha256']
 assert np.array_equal(np.asarray(Image.open(root/'images'/f'{sid}_lc.png')),np.asarray(c.uri_image(lc['lc']).resize((500,500),Image.Resampling.NEAREST)))
 # Verify the source SVG's observed entity order/type against stored original input.
 summary=c.read(c.VIEWER/'summaries'/(sid+'.json'));svg=c.ET.fromstring(summary['svg']);g=next(n for n in svg if n.tag==c.NS+'g')
 types=sample['entities']['entity_type'].tolist();assert len(types)==len(g)
 assert all(c.kind(node)==['building','road','poi'][t] for node,t in zip(g,types))
 # POI point centers independently agree with scene-local tensor positions (float32 tolerance).
 point_checks=0
 for node,t,xy in zip(g,types,sample['entities']['relative_position_m'].numpy()):
  if t==2 and node.tag==c.NS+'circle':
   assert abs(float(node.get('cx'))-(float(xy[0])+250))<1e-3
   assert abs(float(node.get('cy'))-(float(xy[1])+250))<1e-3
   point_checks+=1
 checks[sid]={'palette_and_fraction_rgba_exact':True,'types_order_exact':True,'poi_center_checks':point_checks,'raster_extent':'center +/-250 m','lc_shape':list(frac.shape),'dem_shape':list(ras['dem_standardized_mean'].shape),'dem_valid':int(ras['dem_valid_mask'].sum())}
errors=[];failed=[]
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True);page=browser.new_page(viewport={'width':1600,'height':1100});page.on('pageerror',lambda e:errors.append(str(e)));page.on('requestfailed',lambda q:failed.append(q.url))
 response=page.goto('http://127.0.0.1:18771/',wait_until='networkidle');assert response.status==200
 assert page.locator('section').count()==18 and page.locator('section img').count()==144
 # Explicitly decode every lazy image, including hidden reference panels.
 decoded=page.evaluate('''async()=>{const images=[...document.querySelectorAll('section img')];for(const im of images){im.loading='eager';await im.decode();if(im.naturalWidth!==500||im.naturalHeight!==500)throw Error(im.src)}return images.length}''')
 for rec in m['records']:
  sid=rec['row']['scene_id'];page.select_option('#scene',sid);assert page.locator('section:visible').count()==1
  page.locator('section:visible summary').click();assert page.locator('section:visible details').get_attribute('open') is not None
  page.locator('section:visible img').first.click();assert page.locator('#zoom').is_visible();page.locator('#close').click()
 page.select_option('#scene','all');page.screenshot(path=str(a/'gallery_browser.png'))
 browser.close()
assert not errors and not failed
assert all(c.sha(p)==h for p,h in m['source_hashes'].items())
assert all(c.sha(root/p)==h for p,h in m['output_hashes'].items())
before=c.read(a/'before.json');listener=subprocess.getoutput("ss -H -ltnp 'sport = :8765'");assert listener==before['listeners']
result={'scenes':checks,'image_decodes':decoded,'browser_errors':errors,'failed_requests':failed,'scene_selector_cases':18,'reference_panel_cases':18,'enlarge_dialog_cases':18,'source_hashes_unchanged':len(m['source_hashes']),'output_hashes_verified':len(m['output_hashes']),'production_listener_unchanged':True,'experiment_listener':subprocess.getoutput("ss -H -ltnp 'sport = :18771'"),'total_image_bytes':sum(p.stat().st_size for p in (root/'images').glob('*')),'total_artifact_bytes':sum(p.stat().st_size for p in root.rglob('*') if p.is_file()),'terrain_screening_pool_size':len(m['terrain_screening_pool'])}
c.write(a/'validation.json',result);print(json.dumps({k:v for k,v in result.items() if k!='scenes'},indent=2))
