"""Selected B6 evaluation export; exact S10 ranking/Composite C presentation.

Dissertation retrieval: evaluation originals, self exclusion, EPSG:5186 >=2km,
float32 cosine GEMV and lexical stable ties. No optimizer/selection execution.
S50 uses the accepted Stage B subdivision, CON lift, full-source G/Ppre builders.
"""
from pathlib import Path
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
import argparse,copy,json,os,tempfile,time,multiprocessing,shutil,struct
import numpy as np
import torch,yaml
import pyarrow as pa
from retrieval_artifacts import read_json as read,file_hash as sha,digest,encoded,load
from b6_con_census import build_children
from b6_con_lift import lift_accepted_parent_con_to_children,POLICY_HASH
from b6_segmented_inputs import full_source_graphs,tensorize_children
from b6_s50_cache import stable_save,copy_without_edges
from b6_stage_b_preparation import tensor_digest
from training_family_inputs import project,projected_collate,family_encoder_batch
from model_data import build_vocabulary,validate_vocabulary_contract
from model_families import build_scene_encoder
from training_support import to_device
from scene_encoder import geometry_fourier_features
from retrieval_inference import initialize_inference,device_lock
from retrieval_lineage import OriginalCatalog
from retrieval_originals import OriginalReader
from s10_all_query import select
from s10_all_models import HEADER,MAGIC,pack_query,unpack_query,order_index,band_ranks

REPO=Path(__file__).resolve().parents[1]
ROOT=Path('/mnt/hdd002/dhnyu/fusedata/experiments/b6_nonlocal_retrieval_viewer')
OLD=Path('/mnt/hdd002/dhnyu/fusedata/retrieval_data/reduced/s10_all_model_viewers/viewer_composite_c_e067ad37b57973b09f35349b')
S10=Path('/mnt/hdd002/dhnyu/fusedata/retrieval_data/reduced/s10/s10gen_a24b979d4c1557387cbbec35')
FORMAL=Path('/mnt/hdd002/dhnyu/fusedata/experiments/b6_road_granularity_stage_b_training/b6formal_e593d0bb2f2f6acd77056c76')
ARMS=['B6-original','B6-S50-G','B6-S50-Ppre'];EPOCHS=[90,135,130]
def put(p,x):Path(p).write_bytes(encoded(x))
def check(root):
 m=read(root/'manifest.json')
 for r in m['files']:assert sha(root/r['path'])==r['sha256']
 return root/'manifest.json'
def finish(stage,dest,extra=None):
 put(stage/'manifest.json',{'files':[{'path':str(p.relative_to(stage)),'sha256':sha(p)} for p in sorted(stage.rglob('*')) if p.is_file() and p.name!='manifest.json'],**(extra or {})})
 check(stage);stage.rename(dest);return dest/'manifest.json'
def contract():
 cfg=yaml.safe_load((REPO/'config/b6_nonlocal_viewer.yml').read_text());assert cfg['arms']==ARMS and cfg['epochs']==EPOCHS
 assert cfg['output_root']==str(ROOT) and cfg['inference']['batch_size']==1 and cfg['nonlocal_m']==2000
 assert not cfg['training'] and cfg['queries']==cfg['gallery']==9000
 sources={str(p.relative_to(REPO)):sha(p) for p in sorted((REPO/'python').glob('*.py'))}
 for p in [REPO/'config/b6_nonlocal_viewer.yml',REPO/'R/b6_nonlocal_viewer.R',REPO/'targets/b6_nonlocal_viewer.R',REPO/'_targets_b6_nonlocal_viewer.R']:sources[str(p.relative_to(REPO))]=sha(p)
 old=read(OLD/'viewer_receipt.json')
 for p,h in old['files'].items():assert sha(OLD/p)==h
 g=load(S10/'gallery_manifest.json','gallery');assert len(g['body']['rows'])==9000
 a=load(S10/'acceptance.json','acceptance');assert a['body']['status']=='PASS' and a['body']['artifacts'][str(S10/'gallery_manifest.json')]==g['artifact_id']
 ids=[r['scene_id'] for r in g['body']['rows']];assert ids==sorted(set(ids)) and all(r['split']=='evaluation' and r['epsg']==5186 for r in g['body']['rows'])
 index=read(OLD/'index.json');assert [dict(zip(index['columns'],r))['scene_id'] for r in index['rows']]==ids
 cp=[]
 for arm,e in zip(ARMS,EPOCHS):
  d=FORMAL/arm;done=read(d/'completion.json');b=read(d/f'boundary-{e:03d}.json');assert done['selected']['completed_epoch']==e
  p=d/b['checkpoint'];assert sha(p)==b['checkpoint_sha256']
  cp.append({'arm':arm,'epoch':e,'path':str(p),'sha256':sha(p),'authority':read(d/'authority.json')['authority_id']})
 c={'config':cfg,'sources':sources,'checkpoints':cp,'con_policy_hash':POLICY_HASH,'gallery_id':g['artifact_id'],
    'parents':{str(p):sha(p) for p in [S10/'acceptance.json',S10/'gallery_manifest.json',S10/'original_inputs/manifest.json',OLD/'viewer_receipt.json',FORMAL/'contract.json',FORMAL/'comparison/manifest.json',FORMAL/'final_audit/manifest.json']},
    'old_ui_files':old['files'],'scope':'post-training evaluation/viewer export; not validation selection'}
 c['design_id']='b6nonlocal_'+digest(c)[:24]
 root=ROOT/c['design_id'];root.mkdir(parents=True,exist_ok=True)
 path=root/'contract.json'
 if path.exists():assert read(path)==c
 else:put(path,c)
 return path

def job_run(job):
 torch.set_num_threads(1);pa.set_cpu_count(1);start=time.monotonic()
 roots=yaml.safe_load((REPO/'config/training_controller.yml').read_text())['roots'];training=yaml.safe_load((REPO/'config/training.yml').read_text())
 cat=OriginalCatalog(roots,training);result=[]
 with OriginalReader(cat) as reader:
  for record in job['rows']:
   sid=record['scene_id'];s=reader.read(sid,vectors_only=True);assert s['split']=='evaluation'
   assert s['center']==(record['center_x'],record['center_y'])
   top=reader._rows('topology/source_topology.parquet',sid);rels=reader._rows('relations/relation_edges.parquet',sid)
   original={'roads':{sid:[r for r in s['entities'] if r['entity_type']=='R']},'topology':{sid:top},'relations':{sid:rels}}
   path=S10/'original_inputs'/f'{sid}.pt';assert sha(path)==job['hashes'][sid+'.pt']
   accepted=torch.load(path,map_location='cpu',weights_only=False);assert accepted['scene_id']==sid and accepted['split']=='evaluation'
   assert accepted['lineage']['parent']==s['parent'] and np.array_equal(accepted['scene_center_5186'].numpy(),s['center'])
   delta={'geometry':[{'local_entity_id':r['local_entity_id'],'geometry_wkb':r['observed_geometry'],'fallback':True} for r in original['roads'][sid]],'absorption':[],'attributes':[],'relation_delta':[],'removals':[]}
   children,con=build_children(sid,'original',delta,original,None)
   pairs,causes=lift_accepted_parent_con_to_children(con,children)
   children,graphs,stats=full_source_graphs(s['entities'],delta,children,pairs)
   segmented,ppre,_,_=tensorize_children(accepted,children,graphs,s['center'],job['method'])
   assert tensor_digest(copy_without_edges(segmented))==tensor_digest(copy_without_edges(ppre))
   baseline,_=project(accepted,'B6');assert len(baseline['entities']['local_entity_id'])==len(original['roads'][sid])
   if not original['roads'][sid]:assert not children
   with torch.inference_mode():
    f0=geometry_fourier_features(baseline,job['model'],torch.device('cpu'));f1=geometry_fourier_features(segmented,job['model'],torch.device('cpu'))
   assert all(torch.isfinite(x).all() for x in (*f0,*f1))
   out=Path(job['stage'])/f'{sid}.pt';h=stable_save(out,{'original':baseline,'segmented':segmented,'ppre_edges':ppre['edges'],'fourier_original':f0,'fourier_s50':f1})
   result.append({'scene_id':sid,'path':out.name,'sha256':h,'original_roads':len(original['roads'][sid]),'children':len(children),'con_causes':len(causes),'logical_con_causes':sum(r['a']['mode']=='logical_off_support' or r['b']['mode']=='logical_off_support' for r in causes),'stats':stats})
 return {'rows':result,'seconds':time.monotonic()-start}

def prepare(path,pilot=False):
 c=read(path);root=Path(path).parent;dest=root/('pilot_inputs' if pilot else 'inputs')
 if dest.exists():return check(dest)
 stage=Path(tempfile.mkdtemp(prefix='.inputs-',dir=root));g=load(S10/'gallery_manifest.json','gallery')['body']['rows']
 cat=OriginalCatalog(yaml.safe_load((REPO/'config/training_controller.yml').read_text())['roots'],yaml.safe_load((REPO/'config/training.yml').read_text()))
 grouped=defaultdict(list)
 for r in g:grouped[cat.p3_by_scene[r['scene_id']]['branch_id']].append(r)
 hashes={r['path']:r['sha256'] for r in load(S10/'original_inputs/manifest.json','original_inputs')['files']}
 model=read(FORMAL/'contract.json')['frozen_science']['resolved_model']['model']
 jobs=[{'rows':rs,'hashes':hashes,'stage':str(stage),'model':model,'method':c['design_id']} for _,rs in sorted(grouped.items())]
 if pilot:
  # Deterministic zero/sparse/dense scenes based on exact previous viewer counts.
  ix=read(OLD/'index.json');rows=[dict(zip(ix['columns'],r)) for r in ix['rows']]
  chosen={next(r['scene_id'] for r in rows if r['n_roads']==0),next(r['scene_id'] for r in rows if 0<r['n_roads']<=8),max(rows,key=lambda r:r['n_roads'])['scene_id']}
  jobs=[{**j,'rows':[r for r in j['rows'] if r['scene_id'] in chosen]} for j in jobs];jobs=[j for j in jobs if j['rows']]
 results=[]
 if pilot:
  for j in jobs:results.append(job_run(j))
 else:
  with ProcessPoolExecutor(max_workers=c['config']['workers'],mp_context=multiprocessing.get_context('spawn')) as pool:
   for i,r in enumerate(pool.map(job_run,jobs)):
    results.append(r);print('prepared branch',i+1,'/',len(jobs),flush=True)
 rows=sorted([r for v in results for r in v['rows']],key=lambda x:x['scene_id'])
 assert len(rows)==(3 if pilot else 9000)
 put(stage/'index.json',{'rows':rows,'branch_seconds':[r['seconds'] for r in results],'zero_road':sum(r['original_roads']==0 for r in rows),'ambiguity':0,'g_ppre_only_sn':True})
 return finish(stage,dest,{'status':'PASS','count':len(rows)})

def embeddings(path,pilot=False):
 c=read(path);root=Path(path).parent;dest=root/('pilot_embeddings' if pilot else 'embeddings');inputs=root/('pilot_inputs' if pilot else 'inputs')
 if dest.exists():return check(dest)
 check(inputs);stage=Path(tempfile.mkdtemp(prefix='.embeddings-',dir=root));rows=read(inputs/'index.json')['rows']
 cfg=c['config']['inference'];device=initialize_inference(cfg)
 frozen=read(FORMAL/'contract.json')['frozen_science']['resolved_model'];roots=yaml.safe_load((REPO/'config/training_controller.yml').read_text())['roots']
 vocab=build_vocabulary(roots['categories']);records=[]
 with device_lock(cfg):
  for ai,cp in enumerate(c['checkpoints']):
   assert sha(cp['path'])==cp['sha256'];payload=torch.load(cp['path'],map_location='cpu',weights_only=False)
   assert payload['run_identity']==cp['authority'] and payload['progress']['completed_epoch']==cp['epoch']
   model=build_scene_encoder(frozen,validate_vocabulary_contract(vocab),'B6').to(device)
   model.load_state_dict(payload['online_model'],strict=True);del payload
   model.eval();model.requires_grad_(False);vectors=[];t=time.monotonic();torch.cuda.reset_peak_memory_stats(device)
   with torch.inference_mode():
    for k,r in enumerate(rows):
     p=inputs/r['path'];assert sha(p)==r['sha256'];d=torch.load(p,map_location='cpu',weights_only=False)
     s=d['original'] if ai==0 else d['segmented'];f=d['fourier_original'] if ai==0 else d['fourier_s50']
     if ai==2:s['edges']=d['ppre_edges']
     sample,meta=project(s,'B6');assert tensor_digest(sample['geometry'])==tensor_digest(s['geometry'])
     cpu=projected_collate([(sample,meta)],vocab);cpu['family_name']='B6';cpu['environment']={}
     batch=to_device(family_encoder_batch(cpu),device);features=tuple(x.to(device) for x in f)
     out=model(batch,features,None)['scene_embedding'];v=torch.nn.functional.normalize(out,dim=1).cpu().numpy()
     assert np.isfinite(v).all() and np.max(abs(np.linalg.norm(v,axis=1)-1))<1e-6
     vectors.append(v)
     if pilot:
      again=torch.nn.functional.normalize(model(batch,features,None)['scene_embedding'],dim=1).cpu().numpy();assert np.array_equal(v,again)
     if k%1000==0:print(cp['arm'],k,'/',len(rows),flush=True)
   x=np.concatenate(vectors);file=stage/(cp['arm']+'.npy');np.save(file,x,allow_pickle=False)
   records.append({**cp,'vectors':file.name,'vectors_sha256':sha(file),'rows':len(x),'dimension':256,'seconds':time.monotonic()-t,'peak_vram':torch.cuda.max_memory_allocated(device),'embedding_id':'b6eval_'+digest({'method':c['design_id'],'checkpoint':cp['sha256'],'vectors':sha(file)})[:24]})
   del model;torch.cuda.empty_cache();assert sha(cp['path'])==cp['sha256']
 put(stage/'index.json',{'models':records,'scene_ids':[r['scene_id'] for r in rows],'normalized':True,'training':False,'inference_batch':1})
 return finish(stage,dest,{'status':'PASS','count':len(rows)})

def bands(path):
 from threadpoolctl import threadpool_limits
 c=read(path);root=Path(path).parent;dest=root/'bands'
 if dest.exists():return check(dest)
 check(root/'embeddings');stage=Path(tempfile.mkdtemp(prefix='.bands-',dir=root));g=load(S10/'gallery_manifest.json','gallery')['body']['rows'];ids=[r['scene_id'] for r in g];centers=np.array([[r['center_x'],r['center_y']] for r in g]);em=read(root/'embeddings/index.json');assert ids==em['scene_ids']
 models=[];tests={};samples=np.random.default_rng(20261003).choice(9000,100,False).tolist();counts=read(root/'inputs/index.json')['rows'];samples+= [next(i for i,r in enumerate(counts) if not r['original_roads']),next(i for i,r in enumerate(counts) if 0<r['original_roads']<=8),int(np.argmax([r['original_roads'] for r in counts]))]
 with threadpool_limits(limits=1):
  for m in em['models']:
   key=m['arm'];(stage/key).mkdir();x=np.load(root/'embeddings'/m['vectors']);scores={'standard':[],'nonlocal':[]};shards=[]
   for start in range(0,9000,100):
    raw=bytearray(HEADER.pack(MAGIC,start+1,100))
    for i in range(start,start+100):
     data=select(x,centers,ids,i)
     for mode,d in data.items():
      distances=np.linalg.norm(centers-centers[i],axis=1);expected=8999 if mode=='standard' else int((distances>=2000).sum())
      assert d['candidate_count']==expected
      for band,rows in d['bands'].items():
       assert [r[0] for r in rows]==band_ranks(expected)[band]
       assert all(j!=i+1 and (mode=='standard' or distance>=2000) for rank,j,score,distance in rows)
      scores[mode].append(d['bands']['most'][0][2])
     raw+=pack_query(data)
    name=f'{key}/{start//100:03d}.bin';(stage/name).write_bytes(raw);shards.append({'path':name,'sha256':sha(stage/name),'start':start+1,'queries':100,'bytes':len(raw)})
   for i in samples:
    z=x@x[i];dist=np.linalg.norm(centers-centers[i],axis=1);order=np.lexsort((np.array(ids),-z));d=unpack_query((stage/key/f'{i//100:03d}.bin').read_bytes(),i+1)
    for mode in scores:
     eligible=[int(j) for j in order if j!=i and (mode=='standard' or dist[j]>=2000)];n=len(eligible)
     assert d[mode]['candidate_count']==n
     for b,rs in band_ranks(n).items():assert d[mode]['bands'][b]==[[r,eligible[r-1]+1,float(z[eligible[r-1]]),float(dist[eligible[r-1]])] for r in rs]
   name=f'{key}/orders.json';orders={'configuration':key,'checkpoint':m['sha256'],'embedding_manifest':m['embedding_id'],'generation':c['design_id'],'shards':shards,'modes':{mode:order_index(v) for mode,v in scores.items()}}
   for mode in orders['modes']:orders['modes'][mode]['roadfirst']=sorted(range(1,9001),key=lambda j:(counts[j-1]['original_roads']==0,j))
   put(stage/name,orders);models.append({'configuration':key,'label':f'{key} · epoch {m["epoch"]}','group':'COMPARISON','checkpoint':m['sha256'],'embedding_manifest':m['embedding_id'],'orders':name,'orders_sha256':sha(stage/name)})
   tests[key]={'independent_queries':len(set(samples)),'all_counts_self_distance':True};print('bands',key,flush=True)
 put(stage/'registry.json',{'models':models,'validation':tests,'gallery':9000,'queries':9000})
 return finish(stage,dest,{'status':'PASS'})

def viewer(path):
 c=read(path);root=Path(path).parent;dest=root/'viewer'
 if dest.exists():return check(dest)
 check(root/'bands');stage=Path(tempfile.mkdtemp(prefix='.viewer-',dir=root));cfg=read(OLD/'config.json');registry=read(root/'bands/registry.json')
 # All original style/rendering/support assets reused verbatim, immutable mounts.
 for p in OLD.iterdir():
  if p.name not in ('runtime.js','index.html','viewer_receipt.json','config.json','bands'):(stage/p.name).symlink_to(p.resolve())
 (stage/'bands').symlink_to(root/'bands')
 cfg.update(viewer_id=c['design_id'],generation=c['design_id'],models=registry['models'])
 put(stage/'config.json',cfg)
 js=(OLD/'runtime.js').read_text();replacements={"config.models.length!==28":"config.models.length!==3","params.get('model')||'cmp_FM'":"params.get('model')||'B6-original'","params.get('mode')||'standard'":"params.get('mode')||'nonlocal'","['original','asc','desc'].includes(order)":"['original','asc','desc','roadfirst'].includes(order)","28 accepted model embedding matrices":"3 selected formal B6 checkpoint evaluation embedding matrices","${q.scene_id} · Query Rank-1":"${q.scene_id} · ${q.n_roads===0?'ZERO ROAD':q.n_roads+' original roads'} · Query Rank-1"}
 for old,new in replacements.items():assert old in js;js=js.replace(old,new)
 (stage/'runtime.js').write_text(js)
 html=(OLD/'index.html').read_text().replace(sha(OLD/'config.json'),sha(stage/'config.json')).replace('9,000 queries × 28 models','9,000 queries × 3 B6 models').replace('Composite C · Local validation edition · 28 accepted models · query ordering describes cosine, not correctness','Composite C · Selected B6 evaluation · B/P/LC/DEM are display context only; B6 uses roads · query ordering describes cosine, not correctness')
 html=html.replace('<option value="original">Original (reset)</option>','<option value="original">Original (reset)</option><option value="roadfirst">Road-containing scenes first</option>')
 (stage/'index.html').write_text(html)
 put(stage/'viewer_receipt.json',{'design':c['design_id'],'ui_authority':str(OLD),'old_ui_files':c['old_ui_files'],'changes':replacements,'default':'nonlocal','shared_scene_assets':True,'models':registry['models']})
 # Do not recursively duplicate/hash 9000 already-bound mounted scene assets here.
 put(stage/'manifest.json',{'status':'PASS','files':[{'path':p.name,'sha256':sha(p)} for p in stage.iterdir() if p.is_file()]})
 check(stage);stage.rename(dest);return dest/'manifest.json'

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('action',choices=['contract','pilot-inputs','pilot-embeddings','inputs','embeddings','bands','viewer']);p.add_argument('--contract');a=p.parse_args()
 actions={'contract':contract,'pilot-inputs':lambda:prepare(a.contract,True),'pilot-embeddings':lambda:embeddings(a.contract,True),'inputs':lambda:prepare(a.contract),'embeddings':lambda:embeddings(a.contract),'bands':lambda:bands(a.contract),'viewer':lambda:viewer(a.contract)}
 print(actions[a.action]())
