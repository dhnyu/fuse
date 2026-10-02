#!/usr/bin/env python3
"""Read back every supplemental shard/order and check all model/query contracts."""
import sys,json,pathlib,hashlib
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'python'))
import numpy as np
from s10_all_models import AUDIT,HEADER,MAGIC
from s10_extreme_rank1 import read,sha,encode
record=np.dtype([('rank','<u2'),('index','<u2'),('score','<f4'),('distance','<f8')]);mode=np.dtype([('count','<u2'),('reserved','<u2'),('records',record,(31,))]);assert mode.itemsize==500
b=read(AUDIT/'bands.json');root=pathlib.Path(b['root']);out={'models':{},'rows':0,'status':'PASS'}
for key,m in b['models'].items():
 orders=read(root/m['orders']);all_counts=[]
 for item in m['shards']:
  p=root/item['path'];assert sha(p)==item['sha256'];raw=p.read_bytes();magic,start,n=HEADER.unpack_from(raw);assert magic==MAGIC and n==100 and len(raw)==16+n*1000;arr=np.frombuffer(raw,dtype=mode,offset=16).reshape(n,2);records=arr['records'];indices=np.arange(start,start+n)
  assert (arr['reserved']==0).all() and (arr['count'][:,0]==8999).all();assert (records['index']>=1).all() and (records['index']<=9000).all() and (records['index']!=indices[:,None,None]).all();assert np.isfinite(records['score']).all() and (records['distance'][:,1]>=2000).all()
  for mi,mode_name in enumerate(['standard','nonlocal']):
   counts=arr['count'][:,mi].astype(int);ranks=np.column_stack([np.ones(n,int),np.tile(np.arange(2,12),(n,1)),(counts-10)[:,None]//2+np.arange(1,11),(counts-9)[:,None]+np.arange(10)])
   assert np.array_equal(records['rank'][:,mi],ranks);scores=records['score'][:,mi];ids=records['index'][:,mi];assert (np.diff(scores,axis=1)<=0).all();assert ((scores[:,1:]!=scores[:,:-1])|(ids[:,1:]>ids[:,:-1])).all();assert scores[:,0].tolist()==orders['modes'][mode_name]['scores'][start-1:start-1+n]
  all_counts.extend(arr['count'][:,1].tolist());out['rows']+=n*2*31
 assert sha(root/m['orders'])==m['orders_sha256']
 for mode_name in ['standard','nonlocal']:
  o=orders['modes'][mode_name]
  for ordering,sign in [('asc',1),('desc',-1)]:assert o[ordering]==sorted(range(1,9001),key=lambda i:(sign*o['scores'][i-1],i))
 out['models'][key]={'queries':9000,'rows':558000,'nonlocal_min':min(all_counts),'nonlocal_median':float(np.median(all_counts)),'nonlocal_max':max(all_counts),'orders_exact':True,'shards':len(m['shards'])}
assert out['rows']==15624000
(AUDIT/'bands_readback.json').write_bytes(encode(out));print('PASS',out['rows'],len(out['models']))
