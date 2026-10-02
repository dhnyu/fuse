"""Temporary, immutable display export of selected Stage B validation vectors.

Uses dissertation validation cosine / stable gallery-order tie semantics. No
inference, training, model selection or canonical publication. Reuses the S10
observed-vector renderer and palette. Direct display entrypoint, no research DAG.
"""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
import json, hashlib, shutil, tempfile, os
import numpy as np
import torch
from shapely.geometry import LineString, MultiLineString
from training_prepared_cache import ProductionPreparedData
from retrieval_render import render_scene
from b6_formal_analysis import query_metrics

REPO=Path(__file__).resolve().parents[1]
PARENT=Path('/mnt/hdd002/dhnyu/fusedata/experiments/b6_road_granularity_stage_b_training/b6formal_e593d0bb2f2f6acd77056c76')
ROOT=Path('/mnt/hdd002/dhnyu/fusedata/experiments/b6_retrieval_viewer')
ARMS=['B6-original','B6-S50-G','B6-S50-Ppre']
EPOCHS=[90,135,130]
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def put(p,x):p.write_text(json.dumps(x,separators=(',',':'),allow_nan=False)+'\n')
def checked_manifest(root):
 for r in read(root/'manifest.json')['files']:assert sha(root/r['path'])==r['sha256']
def road_scene(sample):
 g=sample['geometry'];e=sample['entities'];rows=[]
 xy=g['part_coordinates_xy_m_scientific'].numpy();pos=e['relative_position_m'].numpy()
 for i in e['road_row_index'].tolist():
  parts=[]
  for j in range(int(g['entity_part_offsets'][i]),int(g['entity_part_offsets'][i+1])):
   a,b=map(int,g['part_coordinate_offsets'][j:j+2]);points=xy[a:b]+pos[i]
   assert len(points)>=2
   parts.append(LineString(points))
  shape=parts[0] if len(parts)==1 else MultiLineString(parts)
  rows.append({'entity_type':'R','observed_geometry':shape.wkb})
 return {'scene_id':sample['scene_id'],'center':[0,0],'entities':rows}
def build():
 torch.set_num_threads(1)
 checked_manifest(PARENT/'comparison');checked_manifest(PARENT/'final_audit')
 ui=REPO/'tools/retrieval_inspector/b6'; sources={str(p):sha(p) for p in [Path(__file__),REPO/'python/retrieval_render.py',REPO/'tools/retrieval_inspector/supplemental/build.py',*sorted(ui.iterdir())]}
 parents={str(PARENT/'comparison/manifest.json'):sha(PARENT/'comparison/manifest.json')}
 data=[];scenes=None
 for arm,epoch in zip(ARMS,EPOCHS):
  out=PARENT/arm;boundary=read(out/f'boundary-{epoch:03d}.json');done=read(out/'completion.json')
  assert done['selected']['completed_epoch']==epoch and done['status']=='COMPLETE'
  path=out/f'validation-{epoch:03d}.pt';assert sha(path)==boundary['validation_sha256']
  assert sha(out/boundary['checkpoint'])==boundary['checkpoint_sha256']
  parents[str(path)]=sha(path)
  v=torch.load(path,map_location='cpu',weights_only=False)
  if scenes is None:scenes=v['scene_ids']
  assert scenes==v['scene_ids'] and len(scenes)==1000 and v['vectors'].shape==(3000,256)
  sim=v['vectors'][:2000]@v['vectors'][2000:].T
  order=torch.argsort(sim,descending=True,stable=True).numpy();metrics=query_metrics(v['vectors'])
  assert np.isclose(metrics[:,3].astype(float).mean(),done['selected']['HIT@1'],atol=1e-7)
  data.append((sim.numpy(),order,metrics))
 identity={'sources':sources,'parents':parents,'epochs':EPOCHS,'scope':'validation_2000_1000','tie':'stable accepted gallery order','top':50,'bands':'491-500;991-1000'}
 design='b6viewer_'+hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:24]
 ROOT.mkdir(exist_ok=True,parents=True);dest=ROOT/design
 if dest.exists():checked_manifest(dest);return dest
 stage=Path(tempfile.mkdtemp(prefix='.stage-',dir=ROOT));(stage/'queries').mkdir();(stage/'assets').mkdir()
 cfg=read(PARENT/'contract.json');reader=ProductionPreparedData(cfg['frozen_science']['settings']['prepared_parent'],'main_1.0x',8,verify_payloads=True)
 assert scenes==reader.validation_scenes
 desc={r['scene_id']:r for r in read(PARENT/'validation_descriptors/descriptors.json')}
 # Reuse accepted S10 raster colouring helper, without changing raster cells.
 sys.path.insert(0,str(REPO/'tools/retrieval_inspector/supplemental'))
 from build import png, PALETTE
 colors=np.array([[int(c[i:i+2],16) for i in (1,3,5)] for c in PALETTE])
 gallery=[];queries=[];assetmap={}
 def render(sample,key):
  spec=reader.index[key];src=reader.payload_checks[spec['global_index']]['prepared_sha256']
  result=render_scene(road_scene(sample),src,stage/'assets');svg=Path(result['path']).relative_to(stage).as_posix()
  # Static LC context is explicitly not a B6 input; default display remains roads.
  ras=sample['rasters'];lc=ras['landcover_class_fraction'].numpy();valid=ras['landcover_valid_mask'].numpy()
  import base64
  raw=base64.b64decode(png(np.einsum('cyx,ck->yxk',lc,colors),valid).split(',')[1])
  name=f'assets/{src}.png';(stage/name).write_bytes(raw)
  return {'svg':svg,'lc':name,'observed_roads':len(sample['entities']['road_row_index'])}
 for i,sid in enumerate(scenes):
  sample=reader.sample('validation_gallery',sid,None);n=len(sample['entities']['road_row_index']);length=float(desc[sid]['mean_road_segment_length'] or 0)
  countbin='0' if n==0 else '1–8' if n<=8 else '9–49' if n<=49 else '50+'
  lengthbin='empty' if n==0 else next((f'{a}–{b}' for a,b in [(0,50),(50,100),(100,250),(250,500)] if a<=length<b),'500+')
  gallery.append({'id':sid,'roads':n,'length':length,'countbin':countbin,'lengthbin':lengthbin,'descriptors':desc[sid],**render(sample,('validation_gallery',sid,None))})
  for view in (0,1):
   qi=2*i+view;qsample=reader.sample('validation_query',sid,view);qid=qsample['view_id'];assert qid==reader.index[('validation_query',sid,view)]['candidate_id']
   summaries=[];rankings=[]
   for sim,order,metrics in data:
    ranks=order[qi];correct=int(np.flatnonzero(ranks==i)[0])+1
    positive=float(sim[qi,i]);wrong=float(np.max(np.delete(sim[qi],i)))
    summaries.append({'rank':correct,'top':int(ranks[0]),'positive':positive,'incorrect':wrong,'margin':float(metrics[qi,1]),'loss':float(metrics[qi,0])})
    picks=list(range(50))+list(range(490,500))+list(range(990,1000))
    rankings.append([[k+1,int(ranks[k]),float(sim[qi,ranks[k]])] for k in picks])
   q={'i':qi,'id':qid,'scene':i,'view':view,'arms':summaries,'gp_top10_diff':not np.array_equal(data[1][1][qi,:10],data[2][1][qi,:10]),**render(qsample,('validation_query',sid,view))}
   put(stage/'queries'/f'{qi}.json',{'arms':rankings});queries.append(q)
  if i%100==0:print(f'rendered {i}/1000 scenes',flush=True)
 assert len({q['id'] for q in queries})==2000 and sum(g['roads']==0 for g in gallery)==144
 arms=[{'name':a,'epoch':e,'authority':read(PARENT/a/'authority.json')['authority_id'],'checkpoint_sha256':read(PARENT/a/f'boundary-{e:03d}.json')['checkpoint_sha256']} for a,e in zip(ARMS,EPOCHS)]
 put(stage/'catalog.json',{'design':design,'arms':arms,'gallery':gallery,'queries':queries,'palette':PALETTE})
 for p in ui.iterdir():shutil.copyfile(p,stage/p.name)
 assert all(sha(p)==h for p,h in parents.items()) and all(sha(p)==h for p,h in sources.items())
 put(stage/'acceptance.json',{'status':'PASS','identity':identity,'queries':2000,'gallery':1000,'zero_road_scenes':144,'selected_only':True,'inference':False,'training':False,'rank_metrics_match':True,'render':'accepted post-bank road tensors; original gallery; optional LC context not B6 input'})
 put(stage/'manifest.json',{'files':[{'path':str(p.relative_to(stage)),'sha256':sha(p)} for p in sorted(stage.rglob('*')) if p.is_file()]})
 checked_manifest(stage);stage.rename(dest);return dest
if __name__=='__main__':print(build())
