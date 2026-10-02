"""Supplemental all-model bands. No torch/model/checkpoint access in this path.
Accepted S10 retrieval: normalized float32 GEMV, EPSG:5186, lexical exact ties.
Binary v1: header <8sII; query has 2 mode blocks <HH + 31*<HHfd (1000 bytes).
"""
from pathlib import Path
import argparse,json,os,time,struct,gzip
import numpy as np
from threadpoolctl import threadpool_limits
from s10_extreme_rank1 import envelope,read,sha,encode,digest,require,band_ranks
from s10_all_query import select
BASE=Path('/mnt/hdd002/dhnyu/fusedata/retrieval_data/reduced')
AUDIT=Path('/mnt/hdd002/dhnyu/fusedata/tmp/fuse/all_model_20260922')
OLD=BASE/'s10_all_query_viewers/viewer_all_57226fcbe9128cdd90b40f59'
SHARD=100
RECORD=struct.Struct('<HHfd');HEADER=struct.Struct('<8sII');MAGIC=b'S10BND01'
BANDS=('most','top','middle','bottom');MODES=('standard','nonlocal')
def audit():
 cfg=read('config/s10_extreme_rank1.json');root=Path(cfg['original_generation']);a=envelope(root/'acceptance.json');g=envelope(root/'gallery_manifest.json');m=envelope(root/'model_manifest.json');assert a['body']['status']=='PASS'
 for name,doc in [('gallery_manifest.json',g),('model_manifest.json',m)]:assert a['body']['artifacts'][str(root/name)]==doc['artifact_id']
 ids=[r['scene_id'] for r in g['body']['rows']];assert len(set(ids))==9000 and ids==sorted(ids);assert all(r['epsg']==5186 and r['split']=='evaluation' for r in g['body']['rows']);C=np.array([[r['center_x'],r['center_y']] for r in g['body']['rows']])
 registry=[];sources={str(root/f):sha(root/f) for f in ['acceptance.json','gallery_manifest.json','model_manifest.json']}
 for model in m['body']['models']:
  key=model['configuration_id'];rp=root/'rankings'/key/'manifest.json';r=envelope(rp);assert a['body']['artifacts'][str(rp)]==r['artifact_id'];ep=Path(r['body']['embedding_manifest']);e=envelope(ep,True)
  assert r['body']['model']==model==e['body']['model'];assert r['body']['embedding_manifest_id']==e['artifact_id'];assert e['body']['gallery_manifest_id']==g['artifact_id'];assert e['body']['scene_ids']==ids
  prep=envelope(e['body']['prepared_manifest']);assert prep['artifact_id']==e['body']['prepared_manifest_id'] and prep['body']['gallery_manifest_id']==g['artifact_id'];assert [s['scene_id'] for s in prep['body']['samples']]==ids
  resolution=Path(cfg['lifecycle_root'])/model['authority_id']/'resolution.json';res=read(resolution)
  for k in ['checkpoint_id','acceptance_id','manifest_sha256','payload_sha256']:assert model[k]==res[k],(key,k)
  X=np.load(ep.parent/'vectors.npy',allow_pickle=False);assert list(X.shape)==e['body']['shape'] and X.shape[0]==9000 and X.dtype==np.float32 and e['body']['dtype']=='float32';norm=np.linalg.norm(X,axis=1);assert np.isfinite(X).all() and np.max(np.abs(norm-1))<1e-6
  row={'configuration':key,'family':model['model_id'],'group':model['group'],'checkpoint':model['checkpoint_id'],'authority':model['authority_id'],'acceptance':model['acceptance_id'],'embedding_manifest':e['artifact_id'],'embedding_path':str(ep),'payload':str(ep.parent/'vectors.npy'),'payload_sha256':sha(ep.parent/'vectors.npy'),'dimension':X.shape[1],'bytes':(ep.parent/'vectors.npy').stat().st_size,'norm_min':float(norm.min()),'norm_max':float(norm.max())};registry.append(row)
  for p in [rp,ep,ep.parent/'vectors.npy',resolution,Path(e['body']['prepared_manifest'])]:sources[str(p)]=sha(p)
 assert len(registry)==28 and len(set(r['configuration'] for r in registry))==28
 result={'models':registry,'gallery_manifest':g['artifact_id'],'original_acceptance':a['artifact_id'],'scene_ids':ids,'centers':C.tolist(),'sources':sources,'original_root':str(root),'accepted_viewer':cfg['accepted_viewer']}
 AUDIT.mkdir(parents=True,exist_ok=True);(AUDIT/'inventory.json').write_bytes(encode(result));return result

def order_index(scores):
 # Validated gallery order is lexical scene ID; stable sort preserves exact ties.
 a=np.asarray(scores);return {'scores':a.tolist(),'asc':(np.argsort(a,kind='stable')+1).tolist(),'desc':(np.argsort(-a,kind='stable')+1).tolist()}
def pack_query(data):
 out=bytearray()
 for mode in MODES:
  d=data[mode];out+=struct.pack('<HH',d['candidate_count'],0)
  for band in BANDS:
   for r,j,s,dist in d['bands'][band]:out+=RECORD.pack(r,j,s,dist)
 assert len(out)==1000;return out

def unpack_query(raw,index):
 magic,start,n=HEADER.unpack_from(raw);assert magic==MAGIC and start<=index<start+n and len(raw)==16+n*1000
 pos=16+(index-start)*1000;answer={}
 for mode in MODES:
  count,reserved=struct.unpack_from('<HH',raw,pos);assert reserved==0;pos+=4;bands={}
  for key,number in [('most',1),('top',10),('middle',10),('bottom',10)]:
   bands[key]=[list(RECORD.unpack_from(raw,pos+k*16)) for k in range(number)];pos+=number*16
  answer[mode]={'candidate_count':count,'bands':bands}
 return answer

def build(inv):
 context={'schema':'S10BND01','models':inv['models'],'gallery_manifest':inv['gallery_manifest'],'shard_size':SHARD,'code_sha256':sha(__file__),'selection_code_sha256':sha(Path(__file__).parent/'s10_all_query.py')};gid='s10models_'+digest(context)[:24];root=BASE/'s10_all_model_bands'/gid
 if root.exists():return root
 stage=root.with_name(root.name+'.staging');stage.mkdir(parents=True,exist_ok=False)
 ids=inv['scene_ids'];C=np.array(inv['centers']);idindex={sid:j+1 for j,sid in enumerate(ids)};parent=Path(inv['accepted_viewer']);pc=read(parent/'config.json');accepted={}
 for q in pc['queries']:
  p=parent/'queries'/f"{q['scene_id']}.json";assert sha(p)==pc['files'][str(p.relative_to(parent))];accepted[idindex[q['scene_id']]]=read(p)
 samples=np.random.default_rng(20260922).choice(9000,100,False);manifest={'generation':gid,**context,'models':{},'files':{},'validation':{},'rows':0};started=time.perf_counter()
 with threadpool_limits(limits=1):
  for model in inv['models']:
   t=time.perf_counter();key=model['configuration'];X=np.load(model['payload'],allow_pickle=False);directory=stage/key;directory.mkdir();scores={m:[] for m in MODES};shards=[];matched=0
   for start in range(0,9000,SHARD):
    raw=bytearray(HEADER.pack(MAGIC,start+1,SHARD))
    for i in range(start,start+SHARD):
     data=select(X,C,ids,i)
     for mode,d in data.items():
      assert d['candidate_count']==(8999 if mode=='standard' else int((np.linalg.norm(C-C[i],axis=1)>=2000).sum()))
      assert sum(map(len,d['bands'].values()))==31
      for band,rs in d['bands'].items():
       assert [z[0] for z in rs]==band_ranks(d['candidate_count'])[band]
       assert all(j!=i+1 and np.isfinite(s) and (mode=='standard' or dist>=2000) for r,j,s,dist in rs)
      scores[mode].append(d['bands']['most'][0][2])
     raw+=pack_query(data)
     if i+1 in accepted:
      old=accepted[i+1][key]
      for mode in MODES:
       assert old[mode]['candidate_count']==data[mode]['candidate_count']
       for band,rs in old[mode]['bands'].items():
        for a,b in zip(rs,data[mode]['bands'][band],strict=True):assert [a['rank'],idindex[a['gallery_scene_id']],a['similarity'],a['geographic_distance_m']]==b,(key,i,mode,band);matched+=1
    file=f'{key}/{start//SHARD:03d}.bin';(stage/file).write_bytes(raw);h=sha(stage/file);manifest['files'][file]=h;shards.append({'path':file,'sha256':h,'start':start+1,'queries':SHARD,'bytes':len(raw),'gzip3':len(gzip.compress(raw,3,mtime=0))})
   # Independently reconstruct 100 full ranks using lexical secondary key, then decode stored bytes.
   for i in samples:
    i=int(i);z=np.dot(X,X[i]);dist=np.linalg.norm(C-C[i],axis=1);order=np.lexsort((np.asarray(ids),-z));data=unpack_query((directory/f'{i//SHARD:03d}.bin').read_bytes(),i+1)
    for mode in MODES:
     eligible=[int(j) for j in order if j!=i and (mode=='standard' or dist[j]>=2000)];n=len(eligible);positions={'most':[1],'top':range(2,12),'middle':range((n-10)//2+1,(n-10)//2+11),'bottom':range(n-9,n+1)}
     assert data[mode]['candidate_count']==n
     for band,ranks in positions.items():assert data[mode]['bands'][band]==[[r,eligible[r-1]+1,float(z[eligible[r-1]]),float(dist[eligible[r-1]])] for r in ranks]
   oi={'configuration':key,'checkpoint':model['checkpoint'],'embedding_manifest':model['embedding_manifest'],'generation':gid,'shards':shards,'modes':{m:order_index(scores[m]) for m in MODES}}
   for m,d in oi['modes'].items():
    for name,sign in [('asc',1),('desc',-1)]:assert d[name]==sorted(range(1,9001),key=lambda j:(sign*d['scores'][j-1],ids[j-1]))
   file=f'{key}/orders.json';(stage/file).write_bytes(encode(oi));manifest['files'][file]=sha(stage/file);manifest['models'][key]={**model,'orders':file,'orders_sha256':sha(stage/file),'shards':shards};manifest['rows']+=558000;manifest['validation'][key]={'accepted_exact_records':matched,'independent_full_queries':100,'counts_self_distance_all':True,'sort_permutations_exact':True,'seconds':time.perf_counter()-t};assert matched==6200
   print(key,manifest['validation'][key],flush=True)
 assert manifest['rows']==15624000
 for p,h in inv['sources'].items():assert sha(p)==h,p
 manifest['build_seconds']=time.perf_counter()-started;manifest['storage']={'raw':sum((stage/p).stat().st_size for p in manifest['files']),'gzip3':sum(len(gzip.compress((stage/p).read_bytes(),3,mtime=0)) for p in manifest['files']),'files':len(manifest['files'])};(stage/'manifest.json').write_bytes(encode(manifest));os.rename(stage,root);(AUDIT/'bands.json').write_bytes(encode({'root':str(root),**manifest}));return root
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--audit-only',action='store_true');args=p.parse_args();inv=audit();print('AUDIT PASS',len(inv['models']),flush=True)
 if not args.audit_only:print(build(inv))
