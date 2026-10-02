"""Independent boundary/tie/population checks, no publication into accepted data."""
from pathlib import Path
import sys,json,hashlib
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
import numpy as np
from threadpoolctl import threadpool_limits
from s10_all_models import unpack_query,band_ranks
from b6_nonlocal_viewer import S10,FORMAL,OLD,ARMS,check,sha

def main(root):
 root=Path(root);c=json.loads((root/'contract.json').read_text())
 for stage in ['inputs','embeddings','bands','viewer']:check(root/stage)
 for p,h in c['parents'].items():assert sha(p)==h
 for cp in c['checkpoints']:assert sha(cp['path'])==cp['sha256']
 gallery=json.loads((S10/'gallery_manifest.json').read_text())['body']['rows'];ids=np.array([r['scene_id'] for r in gallery]);centers=np.array([[r['center_x'],r['center_y']] for r in gallery]);near={'below':(float('inf'),None),'above':(float('inf'),None)}
 for i in range(9000):
  dist=np.linalg.norm(centers-centers[i],axis=1)
  for key,valid in [('below',(dist<2000)&(dist>0)),('above',dist>=2000)]:
   delta=np.where(valid,abs(dist-2000),np.inf);j=int(delta.argmin())
   if delta[j]<near[key][0]:near[key]=(float(delta[j]),(i,j,float(dist[j])))
 counts=json.loads((root/'inputs/index.json').read_text())['rows'];assert len(counts)==9000 and [r['scene_id'] for r in counts]==ids.tolist();zero=[i for i,r in enumerate(counts) if not r['original_roads']];assert len(zero)==1261
 pilot=json.loads((root/'pilot_inputs/index.json').read_text())['rows']
 for row in pilot:assert sha(root/'inputs'/row['path'])==row['sha256'],'pilot/full input byte stability'
 samples=sorted(set([v[1][0] for v in near.values()]+zero[:2]+[int(np.argmax([r['original_roads'] for r in counts]))]))
 with threadpool_limits(limits=1):
  for arm in ARMS:
   x=np.load(root/'embeddings'/f'{arm}.npy');pilot_x=np.load(root/'pilot_embeddings'/f'{arm}.npy');assert np.array_equal(pilot_x,x[[ids.tolist().index(r['scene_id']) for r in pilot]]),'pilot/full inference exact';assert x.dtype==np.float32 and x.shape==(9000,256)
   assert len(np.unique(x[zero],axis=0))==1,'zero-road embeddings must remain identical'
   for i in samples:
    score=x@x[i];dist=np.linalg.norm(centers-centers[i],axis=1);ordered=np.lexsort((ids,-score));d=unpack_query((root/'bands'/arm/f'{i//100:03d}.bin').read_bytes(),i+1)
    for mode in ['standard','nonlocal']:
     eligible=[int(j) for j in ordered if j!=i and (mode=='standard' or dist[j]>=2000)]
     for b,rs in band_ranks(len(eligible)).items():assert d[mode]['bands'][b]==[[k,eligible[k-1]+1,float(score[eligible[k-1]]),float(dist[eligible[k-1]])] for k in rs]
 result={'status':'PASS','queries':9000,'gallery':9000,'zero_road':1261,'nearest_2km_pairs':near,'independent_boundary_dense_zero_queries':[ids[i] for i in samples],'immutable_parents_unchanged':True,'checkpoints_unchanged':True}
 print(json.dumps(result,indent=2))
if __name__=='__main__':main(sys.argv[1])
