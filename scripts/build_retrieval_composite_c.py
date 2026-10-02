#!/usr/bin/env python3
"""New model-independent display assets only. Never imports model/ranking code."""
from pathlib import Path
import sys,json,hashlib,subprocess,shlex,re,os,time,base64,io,argparse
import numpy as np
from PIL import Image
import build_scene_composite_experiment as ex
AUDIT=Path('/mnt/hdd002/dhnyu/fusedata/tmp/fuse/variant_c_20260922')
BASE=ex.BASE

def discover():
 candidates=[]
 for line in subprocess.check_output(['ps','-eo','pid,args'],text=True).splitlines():
  if 'scripts/serve_viewer_hub_fast.py --root ' not in line:continue
  parts=shlex.split(line)
  if not Path(parts[1]).name.startswith('python'):continue
  if '--root' not in parts:continue
  root=Path(parts[parts.index('--root')+1])
  if root.parent==BASE/'s10_all_model_viewers' and (root/'viewer_receipt.json').exists():candidates.append((int(parts[0]),root))
 assert len(candidates)==1,candidates
 pid,root=candidates[0];cfg=ex.read(root/'config.json');receipt=ex.read(root/'viewer_receipt.json');assert len(cfg['models'])==28
 assert all(ex.sha(root/k)==v for k,v in receipt['files'].items())
 assert root.name==cfg['viewer_id']==receipt['viewer_id'];return pid,root,cfg

def build(pilot=False,workers=4):
 import torch
 from playwright.sync_api import sync_playwright
 torch.set_num_threads(1);AUDIT.mkdir(parents=True,exist_ok=True);pid,old,cfg=discover();started=time.time()
 er=ex.read(ex.AUDIT/'result.json');experiment=Path(er['root']);contract=ex.read(experiment/'manifest.json')
 assert ex.sha(ex.__file__)==contract['code_sha256'];assert ex.VARIANTS['C']==contract['variants']['C'];assert ex.STYLES['outline']==contract['styles']['outline']
 idx=ex.read(old/'index.json');records=[dict(zip(idx['columns'],r)) for r in idx['rows']];assert len(records)==9000
 manifest=ex.read(ex.INPUT/'manifest.json');input_hashes={f['path']:f['sha256'] for f in manifest['files']}
 identity={'source_viewer':str(old),'source_receipt_sha256':ex.sha(old/'viewer_receipt.json'),'experiment':str(experiment),'experiment_manifest_sha256':ex.sha(experiment/'manifest.json'),'contract':contract['variants']['C'],'style':contract['styles']['outline'],'hillshade':contract['hillshade'],'builder_sha256':ex.sha(__file__),'main_size':500,'thumbnail_size':128,'thumbnail':'lossless WebP, nearest display downsampling','palette_sha256':cfg['palette_sha256']}
 gid='s10composite_c_'+hashlib.sha256(ex.enc(identity)).hexdigest()[:24]
 root=(AUDIT/f'pilot_w{workers}') if pilot else BASE/'s10_composite_c'/gid
 if not pilot:
  assert not root.exists();stage=root.with_name('.staging_'+gid)
 else:stage=root
 stage.mkdir(parents=True,exist_ok=False)
 for d in ('main','thumb','meta','layers'):(stage/d).mkdir()
 if pilot:
  wanted={x['row']['scene_id'] for x in contract['records']}
  wanted.update(r['scene_id'] for r in records[:14]);records=[r for r in records if r['scene_id'] in wanted]
 before={'source_viewer':str(old),'source_pid':pid,'head':subprocess.getoutput('git rev-parse HEAD'),'branch':subprocess.getoutput('git branch --show-current'),'status':subprocess.getoutput('git status --short'),'listeners':subprocess.getoutput("ss -H -ltnp | rg '18769|18771|8765'"),'cloudflared':subprocess.getoutput('pgrep -a cloudflared'),'hub_links':{n:os.readlink(BASE/'viewer_hub'/n) for n in ['canonical','extreme']},'preserved_files':{str(old/k):ex.sha(old/k) for k in ex.read(old/'viewer_receipt.json')['files']}}
 assert before['branch']=='reduced'
 if not pilot:
  before['bands']={str(p):ex.sha(p) for p in (old/'bands').rglob('*') if p.is_file()}
 ex.write(AUDIT/('pilot_before.json' if pilot else 'before.json'),before)
 outputs=[];source_hashes={};matches={};totals={k:[] for k in ['main','thumb','meta','layers']}
 from concurrent.futures import ProcessPoolExecutor
 import multiprocessing
 environment={'old':str(old),'stage':str(stage),'experiment':str(experiment),'cfg':cfg,'input_hashes':input_hashes}
 with ProcessPoolExecutor(max_workers=workers,mp_context=multiprocessing.get_context('spawn'),initializer=initialize_worker,initargs=(environment,)) as pool:
  for n,(out,sizes,hashes,match) in enumerate(pool.map(render_one,records,chunksize=4)):
   outputs.append(out);source_hashes.update(hashes)
   for kind in totals:totals[kind].append(sizes[kind])
   if match:matches[out['scene_id']]=match
   if (n+1)%100==0 or pilot:print(n+1,out['scene_id'],'seconds',round(time.time()-started,1),flush=True)
 assert len(matches)==18
 catalog={'generation_id':gid,'identity':identity,'columns':list(outputs[0]),'rows':[list(x.values()) for x in outputs],'population':len(records)};ex.write(stage/'catalog.json',catalog)
 sizes={k:{'count':len(v),'median':float(np.median(v)),'p95':float(np.quantile(v,.95)),'max':max(v),'total':sum(v)} for k,v in totals.items()}
 receipt={'generation_id':gid,'identity':identity,'catalog_sha256':ex.sha(stage/'catalog.json'),'source_hashes':source_hashes,'visual_regression':matches,'sizes':sizes,'elapsed_seconds':time.time()-started,'population':len(records),'validation':{'geometry_signature_exact':True,'centers_exact':True,'source_hashes_verified':True,'no_ranking_access':True}}
 ex.write(stage/'manifest.json',receipt)
 if not pilot:stage.rename(root)
 result={'root':str(root),'generation_id':gid,'source_viewer':str(old),**receipt};ex.write(AUDIT/('pilot.json' if pilot else 'assets.json'),result);print(json.dumps({'root':str(root),'sizes':sizes,'elapsed':receipt['elapsed_seconds']}),flush=True)

WORK=None
def initialize_worker(environment):
 global WORK
 import torch
 from playwright.sync_api import sync_playwright
 torch.set_num_threads(1)
 engine=sync_playwright().start();browser=engine.chromium.launch(headless=True);page=browser.new_page()
 WORK=(environment,engine,browser,page)
def render_one(row):
 import torch
 env,engine,browser,page=WORK
 old=Path(env['old']);stage=Path(env['stage']);experiment=Path(env['experiment']);cfg=env['cfg'];input_hashes=env['input_hashes']
 source_hashes={};sizes={};match=None
 def raster(svg):
  return base64.b64decode(page.evaluate("""async svg=>{const im=new Image();const u=URL.createObjectURL(new Blob([svg],{type:'image/svg+xml'}));try{im.src=u;await im.decode();const c=document.createElement('canvas');c.width=c.height=500;c.getContext('2d').drawImage(im,0,0,500,500);return c.toDataURL('image/png').split(',')[1]}finally{URL.revokeObjectURL(u)}}""",svg))
 sid=row['scene_id'];sp=old/'summaries'/(sid+'.json');lp=old/'lc'/(sid+'.json');tp=ex.INPUT/(sid+'.pt')
 for path,sha in [(sp,row['summary_sha256']),(lp,row['lc_sha256']),(tp,input_hashes[sid+'.pt'])]:
  assert ex.sha(path)==sha;source_hashes[str(path)]=sha
 s=ex.read(sp);lc=ex.read(lp);assert s['scene_id']==lc['scene_id']==sid;assert lc['original_input_sha256']==input_hashes[sid+'.pt'];assert lc['palette_sha256']==cfg['palette_sha256']
 sample=torch.load(tp,weights_only=True,mmap=True,map_location='cpu');assert sample['scene_id']==sid;assert np.array_equal(sample['scene_center_5186'].numpy(),s['center'])
 z=sample['rasters']['dem_standardized_mean'].numpy().squeeze();valid=sample['rasters']['dem_valid_mask'].numpy().squeeze().astype(bool);assert z.shape==valid.shape==(17,17)
 lci=ex.uri_image(lc['lc']);assert lci.size==(100,100);h,good=ex.hillshade(z,valid);base=ex.composite_base(lci,h,good,'C')
 svg,counts=ex.vector_overlay(s['svg'],'outline',ex.image_uri(base));assert counts==s['counts'];main=raster(svg);(stage/'main'/(sid+'.png')).write_bytes(main)
 image=Image.open(io.BytesIO(main));image.resize((128,128),Image.Resampling.NEAREST).save(stage/'thumb'/(sid+'.webp'),format='WEBP',lossless=True,method=4)
 # Add display layer tags to the exact verified SVG; unchanged geometry and paint.
 tree=ex.ET.fromstring(svg);group=next(x for x in tree if x.tag==ex.NS+'g');b,r,pn=counts['building'],counts['road'],counts['poi'];assert len(group)==b+2*r+pn
 for i,node in enumerate(group):node.set('data-composite-layer','B' if i<b else 'R' if i<b+2*r else 'P')
 layer={'scene_id':sid,'svg':ex.ET.tostring(tree,encoding='unicode'),'lc':ex.image_uri(lci.resize((500,500),Image.Resampling.NEAREST)),'neutral_shade':ex.image_uri(ex.composite_base(Image.new('RGBA',(100,100),'#f4f6f3'),h,good,'C')),'neutral':ex.image_uri(Image.new('RGBA',(1,1),'#f4f6f3')),'source_sha256':s['source_sha256'],'variant':'C'}
 ex.write(stage/'layers'/(sid+'.json'),layer);meta={k:v for k,v in s.items() if k!='svg'};ex.write(stage/'meta'/(sid+'.json'),meta)
 out={'scene_id':sid}
 for kind,ext in [('main','png'),('thumb','webp'),('meta','json'),('layers','json')]:
  path=stage/kind/(sid+'.'+ext);out[kind+'_sha256']=ex.sha(path);sizes[kind]=path.stat().st_size
 reference=experiment/'images'/(sid+'_C.png')
 if reference.exists():
  assert main==reference.read_bytes(),'Experiment PNG bytes mismatch: '+sid
  match={'png_sha_exact':True,'sha256':ex.sha(reference)}
 return out,sizes,source_hashes,match

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--pilot',action='store_true');p.add_argument('--workers',type=int,default=4);args=p.parse_args();build(args.pilot,args.workers)
