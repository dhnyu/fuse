#!/usr/bin/env python3
"""Colour-only supplemental display from accepted original-input raster tensors.
No model/checkpoint imports or inference; torch reads data tensors with weights_only.
"""
from pathlib import Path
import sys,os,base64,io,time,hashlib,json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from s10_all_models import BASE,AUDIT,OLD
from s10_extreme_rank1 import read,sha,encode,digest,envelope
import numpy as np
from PIL import Image
import torch

def rgba(fractions,valid,colors):
 rgb=np.einsum('cyx,ck->yxk',fractions.astype(np.float64),np.asarray(colors));return np.concatenate([np.uint8(np.clip(rgb,0,255)),(valid.astype(np.uint8)*255)[...,None]],axis=2)
def png(a):
 buf=io.BytesIO();Image.fromarray(a).save(buf,format='PNG');return 'data:image/png;base64,'+base64.b64encode(buf.getvalue()).decode()
def image(s):return np.asarray(Image.open(io.BytesIO(base64.b64decode(s.split(',',1)[1]))))
def build():
 torch.set_num_threads(1);inv=read(AUDIT/'inventory.json');orig=Path(inv['original_root'])/'original_inputs';manifest=envelope(orig/'manifest.json');palette=read('config/retrieval_lc_official_palette.json');pc=read(OLD/'config.json');oldcolors=[[int(c[j:j+2],16) for j in [1,3,5]] for c in pc['palette']];colors=[r['rgb'] for r in palette['rows']];index=read(OLD/'index.json');records={r[1]:dict(zip(index['columns'],r)) for r in index['rows']};files={Path(f['path']).stem:f for f in manifest['files']};identity={'original_manifest':manifest['artifact_id'],'source_viewer':str(OLD),'palette_sha256':sha('config/retrieval_lc_official_palette.json'),'code_sha256':sha(__file__)};gid='s10lc_'+digest(identity)[:24];root=BASE/'s10_all_model_lc'/gid
 if root.exists():return root
 stage=root.with_name(root.name+'.staging');stage.mkdir(parents=True,exist_ok=False);checks={};started=time.perf_counter();invalid=0;total=0
 # One-hot class colours are exact; fractional mixing and invalid alpha unchanged.
 one=np.eye(22).reshape(22,1,22);assert (rgba(one,np.ones((1,22),bool),colors)[0,:,:3]==np.array(colors)).all();assert rgba(one,np.zeros((1,22),bool),colors)[...,3].sum()==0
 for j,sid in enumerate(inv['scene_ids']):
  source=orig/files[sid]['path'];assert source.parent==orig and source.name==sid+'.pt';assert sha(source)==files[sid]['sha256'];sample=torch.load(source,map_location='cpu',weights_only=True,mmap=True);assert sample['scene_id']==sid
  r=sample['rasters'];lc=r['landcover_class_fraction'].numpy();valid=r['landcover_valid_mask'].numpy().astype(bool);support=r['landcover_valid_support'].numpy();assert lc.shape==(22,100,100) and np.isfinite(lc).all();assert valid.shape==(100,100)
  oldpath=OLD/'details'/f'{sid}.json';assert sha(oldpath)==records[sid]['detail_sha256'];d=read(oldpath);assert np.array_equal(rgba(lc,valid,oldcolors),image(d['lc'])),sid
  mass=(lc.astype(np.float64)*support[None]*valid[None]).sum(axis=(1,2));totalmass=float(mass.sum());oldchart=d['charts']['Land cover composition'];assert len(oldchart)==int((mass>0).sum())
  chart=[]
  for old,(k,v) in zip(oldchart,[(k,v) for k,v in enumerate(mass) if v>0],strict=True):
   assert old['label']==f'LC {k+1}' and old['value']==float(v/totalmass*100);entry=palette['rows'][k];chart.append({**old,'color':entry['hex'],'label':f"LC {k+1} · {entry['official']} · {entry['category']}",'internal_code':k+1,'official_code':entry['official']})
  new=rgba(lc,valid,colors);assert new.shape==image(d['lc']).shape and np.array_equal(new[...,3],image(d['lc'])[...,3]);data={'scene_id':sid,'source_sha256':d['source_sha256'],'original_input_sha256':files[sid]['sha256'],'fraction_sha256':hashlib.sha256(lc.tobytes()).hexdigest(),'valid_sha256':hashlib.sha256(valid.tobytes()).hexdigest(),'shape':[22,100,100],'lc':png(new),'chart':chart,'palette_sha256':identity['palette_sha256']};path=stage/f'{sid}.json';path.write_bytes(encode(data));checks[sid]={'sha256':sha(path),'input_sha256':files[sid]['sha256'],'fractions_sha256':data['fraction_sha256']};invalid+=int((~valid).sum());total+=path.stat().st_size
  if j==9:print('LC pilot10: old pixels, fractions, chart values, alpha PASS',flush=True)
  if (j+1)%1000==0:print('LC',j+1,flush=True)
  del sample,r,lc
 result={'generation':gid,'identity':identity,'palette':palette,'files':checks,'bytes':total,'seconds':time.perf_counter()-started,'validation':{'scenes':9000,'old_rgba_exact':True,'composition_values_exact':True,'dimensions_alpha_unchanged':True,'one_hot_22_rgb_exact':True,'invalid_pixels':invalid,'no_fraction_mutation':True}}
 (stage/'manifest.json').write_bytes(encode(result));os.rename(stage,root);(AUDIT/'lc.json').write_bytes(encode({'root':str(root),**result}));return root
if __name__=='__main__':print(build())
