"""Supplemental full-evaluation band index. Dissertation spatial retrieval contract.
No training/model/checkpoint deserialization. Float32 GEMV matches accepted S10.
"""
from pathlib import Path
import json,time,os,hashlib,gzip
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from threadpoolctl import threadpool_limits
from s10_extreme_rank1 import lineage,read,sha,encode,digest,band_ranks,envelope,require

BASE=Path('/mnt/hdd002/dhnyu/fusedata/retrieval_data/reduced')
AUDIT=Path('/mnt/hdd002/dhnyu/fusedata/tmp/fuse/all_query_20260922')

def select(X,C,ids,i):
 scores=X@X[i];distance=np.linalg.norm(C-C[i],axis=1)
 order=np.argsort(-scores,kind='stable');answer={}
 for mode in ['standard','nonlocal']:
  eligible=order[(order!=i)&((distance[order]>=2000) if mode=='nonlocal' else True)]
  answer[mode]={'candidate_count':len(eligible),'bands':{b:[[r,int(eligible[r-1])+1,float(scores[eligible[r-1]]),float(distance[eligible[r-1]])] for r in ranks] for b,ranks in band_ranks(len(eligible)).items()}}
 return answer

def benchmark(X,C,ids,counts):
 # Predefined object-count quantiles, center/periphery, fixed random sample.
 count=np.array([counts[x]['object_count'] for x in ids]);center=np.linalg.norm(C-C.mean(axis=0),axis=1)
 chosen=sorted(set(np.argsort(count,kind='stable')[np.linspace(0,8999,10,dtype=int)].tolist()+np.argsort(center,kind='stable')[np.linspace(0,8999,10,dtype=int)].tolist()+np.random.default_rng(20260922).choice(9000,20,False).tolist()))
 rows=[]
 for threads in [1,4]:
  with threadpool_limits(limits=threads):
   for i in chosen:
    for repeat in range(3):
     t=time.perf_counter_ns();scores=X@X[i];a=time.perf_counter_ns();d=np.linalg.norm(C-C[i],axis=1);b=time.perf_counter_ns()
     for mode in ['standard','nonlocal']:
      t0=time.perf_counter_ns();eligible=np.flatnonzero((np.arange(len(ids))!=i)&((d>=2000) if mode=='nonlocal' else True));t1=time.perf_counter_ns();order=eligible[np.argsort(-scores[eligible],kind='stable')];t2=time.perf_counter_ns();bands={k:order[np.array(v)-1].tolist() for k,v in band_ranks(len(order)).items()};t3=time.perf_counter_ns()
      rows.append(dict(query_scene_id=ids[i],query_index=i+1,threads=threads,mode=mode,repeat=repeat,objects=int(count[i]),centrality_m=float(center[i]),cosine_ms=(a-t)/1e6,distance_ms=(b-a)/1e6,mask_ms=(t1-t0)/1e6,sort_ms=(t2-t1)/1e6,extract_ms=(t3-t2)/1e6,total_ms=(a-t+b-a+t3-t0)/1e6))
 return rows

def build():
 cfg=read('config/s10_extreme_rank1.json');X,C,ids,counts,info=lineage(cfg);AUDIT.mkdir(parents=True,exist_ok=True)
 context={'configuration':'cmp_FM','checkpoint':info['model']['checkpoint_id'],'embedding_manifest':info['embedding_manifest'],'gallery_manifest':info['gallery_manifest'],'source_sha256':info['embedding_sha256'],'algorithm':'float32 GEMV; stable lexical order; midpoint floor((N-10)/2)+1','schema':1,'code_sha256':sha(__file__)}
 generation='s10all_'+digest(context)[:24];root=BASE/'s10_all_query_bands'/generation
 if root.exists():return root
 stage=root.with_name(root.name+'.staging');stage.mkdir(parents=True,exist_ok=False);(stage/'queries').mkdir()
 bench=benchmark(X,C,ids,counts);(AUDIT/'ranking_benchmark.json').write_bytes(encode(bench))
 query_files={};writer=None;rows=[];started=time.perf_counter();idindex={s:i for i,s in enumerate(ids)}
 with threadpool_limits(limits=1):
  for start in range(0,9000,32):
   # Bounded query batches, no permanent/full pairwise similarity matrix.
   for i in range(start,min(9000,start+32)):
    data=select(X,C,ids,i)
    body={'query_index':i+1,'query_scene_id':ids[i],**context,'generation_id':generation,'modes':data}
    raw=encode(body);file=f'queries/{i+1:04d}.json';(stage/file).write_bytes(raw);query_files[str(i+1)]=hashlib.sha256(raw).hexdigest()
    for mode,item in data.items():
     require(item['candidate_count']==8999 if mode=='standard' else item['candidate_count']==int((np.linalg.norm(C-C[i],axis=1)>=2000).sum()),'candidate count')
     for band,records in item['bands'].items():
      for rank,j,score,distance in records:
       require(j!=i+1 and np.isfinite(score) and (mode=='standard' or distance>=2000),'invalid candidate')
       rows.append(dict(query_scene_id=ids[i],query_index=i+1,mode=mode,candidate_count=item['candidate_count'],band=band,rank=rank,candidate_scene_id=ids[j-1],cosine=score,distance_m=distance,configuration='cmp_FM',checkpoint=context['checkpoint'],embedding_manifest=context['embedding_manifest'],generation_id=generation))
   table=pa.Table.from_pylist(rows)
   if writer is None:writer=pq.ParquetWriter(stage/'bands.parquet',table.schema,compression='zstd',use_dictionary=True)
   writer.write_table(table);rows=[]
 writer.close();build_seconds=time.perf_counter()-started
 # Independent full sorting/record reconstruction for 100 preselected queries.
 selected=np.random.default_rng(20260922).choice(9000,100,replace=False)
 with threadpool_limits(limits=1):
  for i in selected:
   i=int(i);scores=np.dot(X,X[i]);distance=np.linalg.norm(C-C[i],axis=1);order=np.lexsort((np.array(ids),-scores));stored=read(stage/f'queries/{i+1:04d}.json')['modes']
   for mode in ['standard','nonlocal']:
    candidates=[int(j) for j in order if j!=i and (mode=='standard' or distance[j]>=2000)]
    n=len(candidates);positions={'most':[1],'top':list(range(2,12)),'middle':list(range((n-10)//2+1,(n-10)//2+11)),'bottom':list(range(n-9,n+1))}
    assert n==stored[mode]['candidate_count']
    for band,ranks in positions.items():assert stored[mode]['bands'][band]==[[r,candidates[r-1]+1,float(scores[candidates[r-1]]),float(distance[candidates[r-1]])] for r in ranks]
 # Exact accepted 100-query viewer comparison, all 31 records in both modes.
 parent=Path(cfg['accepted_viewer']);pc=read(parent/'config.json');matched=0
 for q in pc['queries']:
  source=parent/'queries'/f"{q['scene_id']}.json";assert sha(source)==pc['files'][str(source.relative_to(parent))]
  old=read(source)['cmp_FM'];new=read(stage/f"queries/{idindex[q['scene_id']]+1:04d}.json")['modes']
  for mode in ['standard','nonlocal']:
   assert old[mode]['candidate_count']==new[mode]['candidate_count']
   for band,rs in old[mode]['bands'].items():
    for r,z in zip(rs,new[mode]['bands'][band],strict=True):
     assert [r['rank'],idindex[r['gallery_scene_id']]+1,r['similarity'],r['geographic_distance_m']]==z,(q['scene_id'],mode,band,r,z)
     matched+=1
 for path,h in info['source_sha256'].items():assert sha(path)==h
 manifest={**context,'generation_id':generation,'queries':9000,'rows':pq.read_metadata(stage/'bands.parquet').num_rows,'query_hashes':query_files,'parquet_sha256':sha(stage/'bands.parquet'),'info':info,'build_seconds':build_seconds,'validation':{'independent_queries':list(map(lambda i:int(i)+1,selected)),'accepted_exact_records':matched,'all_counts_self_distance':True},'storage':{'parquet':(stage/'bands.parquet').stat().st_size,'json_raw':sum(p.stat().st_size for p in (stage/'queries').iterdir()),'json_gzip3':sum(len(gzip.compress(p.read_bytes(),compresslevel=3,mtime=0)) for p in (stage/'queries').iterdir())}}
 assert manifest['rows']==558000 and matched==6200
 (stage/'manifest.json').write_bytes(encode(manifest));os.rename(stage,root);(AUDIT/'band_result.json').write_bytes(encode({'root':str(root),**manifest}));return root
if __name__=='__main__':print(build())
