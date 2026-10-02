"""Five production-equivalent DDP updates only. No checkpoint/validation runner.

Dissertation training protocol; engineering measurements are not scientific metrics.
"""
import argparse, copy, json, os, subprocess, sys, tempfile, time, resource
from pathlib import Path
import numpy as np
import torch
import torch.distributed as dist
import yaml
from torch.nn.parallel import DistributedDataParallel
import training_worker as production
import training_family_inputs as family_inputs
from training_prepared_cache import ProductionPreparedData
from training_geometry_cache import GeometryCacheReader
from training_runtime_inputs import SceneCenterIndex
from training_transport import gpu_pair_environment, require_no_conflicting_gpu_workload
from model_data import build_vocabulary,validate_vocabulary_contract
from b6_s50_cache import contract as cache_contract,ROOT as CACHE_ROOT
from b6_stage_b_preparation import read,write,sha256_file,tensor_digest
from b6_postbank_adapter import digest

ROOT=Path('/mnt/hdd002/dhnyu/fusedata/experiments/b6_bounded_updates')
ARMS=('B6-original','B6-S50-G','B6-S50-Ppre')

class PairedReader:
    def __init__(self,root,arm,original):
        self.root=Path(root);self.arm=arm;self.index={ (r['role'],r['scene_id'],r['view']):r for r in read(self.root/'manifest.json')['entries']}
        self.views=original.views;self.training_scenes=original.training_scenes;self.physical_training_role=original.physical_training_role
        self.loaded={};self.geometry_index={};self.read_bytes=0;self.read_seconds=0.
    def sample(self,role,scene,view):
        row=self.index[(role,scene,view)];t=time.monotonic();path=self.root/row['path']
        assert sha256_file(path)==row['sha256'];v=torch.load(path,map_location='cpu',weights_only=False)
        self.read_bytes+=path.stat().st_size;self.read_seconds+=time.monotonic()-t
        sample=v['sample']
        if self.arm.endswith('Ppre'):
            sample['edges']=v['ppre_edges'];sample['resources']['ordered_edges']=len(sample['edges']['relation_mask'])
        self.loaded[(scene,str(sample['view_id']))]=v
        self.geometry_index[(scene,str(sample['view_id']))]=v['fourier']
        return sample
    def _get(self,role,scene,view):return self.geometry_index[(scene,view)]
    def rng(self,batch):return [i for s,v in zip(batch['scene_ids'],batch['view_ids']) for i in self.loaded[(s,str(v))]['rng_ids']]


def authority():
    c=cache_contract();root=CACHE_ROOT/c['design_id']/'prepared';a=read(root/'acceptance.json')
    assert a['status']=='PASS' and a['count']==a['original_parity']==22368 and a['G_Ppre_only_SN']
    assert sha256_file(root/'manifest.json')==a['manifest_sha256']
    d={'bounded_engineering_pilot':True,'scientific_metric':False,'formal_training':False,'checkpoint_publication':False,
       'arms':ARMS,'updates':5,'warmup_updates':1,'global_batch':32,'world_size':2,'input_contract':c,
       'cache_acceptance_sha256':sha256_file(root/'acceptance.json'),'runner_sha256':sha256_file(__file__),
       'production_update_sha256':sha256_file('python/training_worker.py'),'masking_sha256':sha256_file('python/training_family_inputs.py')}
    d['pilot_id']='b6pilot_'+digest(d)[:24];return d


def checked_output(out):
    path=Path(out).resolve()
    if not path.is_relative_to(ROOT) or path==ROOT:raise ValueError('experimental pilot output namespace only')
    return path

def worker(arm,out):
    out=checked_output(out)
    a=authority();c=a['input_contract'];old=c['con_method']['frozen_science'];config=old['resolved_training'];rank=int(os.environ['RANK'])
    assert int(os.environ['WORLD_SIZE'])==2 and config['training']['global_batch_size']==32
    device=production.configure_process(config,rank);dist.init_process_group('nccl',device_id=device)
    try:
        canonical=ProductionPreparedData(old['settings']['prepared_parent'],'main_1.0x',8,verify_payloads=True)
        roots=yaml.safe_load(Path('config/training_controller.yml').read_text())['roots'];vocab=build_vocabulary(roots['categories'])
        data=canonical if arm=='B6-original' else PairedReader(CACHE_ROOT/c['design_id']/'prepared',arm,canonical)
        geo=GeometryCacheReader(Path(old['settings']['prepared_parent'])/'geometry/geometry_cache_manifest.json') if arm=='B6-original' else data
        values={'config':config,'model_config':old['resolved_model'],'family':'B6','data':data,'geometry_cache':geo,'vocabulary':vocab,
            'vocabulary_sizes':validate_vocabulary_contract(vocab),'scene_centers':SceneCenterIndex.from_current_contract(config,old['settings']['prepared_parent']),
            'row':{'scientific':{'peak_learning_rate':.001,'ema':.999}}}
        state=production.create_state(values,device)
        ddp=DistributedDataParallel(state.model.online,device_ids=[rank],output_device=rank,find_unused_parameters=False,bucket_cap_mb=50,gradient_as_bucket_view=False,static_graph=False)
        torch.cuda.manual_seed(1629790839+rank)
        metrics={};rows=[];mask_receipts=[]
        old_sample=data.sample
        def sample_read(role,scene,view):
            t=time.monotonic();result=old_sample(role,scene,view)
            metrics['prepared_read_seconds']=metrics.get('prepared_read_seconds',0.)+time.monotonic()-t
            if arm=='B6-original':
                spec=data.index[(role,scene,view)];size=(data.root/'prepared'/f"{spec['global_index']:06d}.pt").stat().st_size
            else:size=data.index[(role,scene,view)]['bytes']
            metrics['prepared_bytes_requested']=metrics.get('prepared_bytes_requested',0)+size
            return result
        data.sample=sample_read
        old_geo=geo._get
        def geometry_read(role,scene,view):
            t=time.monotonic();result=old_geo(role,scene,view)
            metrics['fourier_read_seconds']=metrics.get('fourier_read_seconds',0.)+time.monotonic()-t
            return result
        geo._get=geometry_read
        original_mask=family_inputs.family_modality_assignments
        def masking(batch,cfg,epoch,role,global_rank=0):
            if arm!='B6-original':batch={**batch,'entities':{**batch['entities'],'local_entity_id':torch.tensor(data.rng(batch),dtype=torch.int64)}}
            result=original_mask(batch,cfg,epoch,role,global_rank)
            mask_receipts.append({'role':role,'ids':tensor_digest(batch['entities']['local_entity_id']),'assignments':tensor_digest(result)})
            return result
        family_inputs.family_modality_assignments=masking
        old_batches=production._local_batches
        def load(*args,**kwargs):
            t=time.monotonic();result=old_batches(*args,**kwargs);metrics['batch_load_seconds']=time.monotonic()-t
            cpu=result[0];metrics['road_rows']=sum(len(b['entities']['entity_type']) for b in cpu);metrics['fourier_rows']=sum(len(b['_family_geometry'][0]) for b in cpu)
            metrics['relation_rows']=sum(len(b['edges']['relation_mask']) for b in cpu)
            for label,bit in [('SN',1),('INT',8),('CON',16)]:metrics[label]=sum(int(((b['edges']['relation_mask']&bit)!=0).sum()) for b in cpu)
            return result
        production._local_batches=load
        def timed(owner,name,key):
            original=getattr(owner,name)
            def call(*args,**kwargs):
                torch.cuda.synchronize(device);t=time.monotonic();result=original(*args,**kwargs);torch.cuda.synchronize(device)
                metrics[key]=metrics.get(key,0.)+time.monotonic()-t;metrics[key+'_calls']=metrics.get(key+'_calls',0)+1
                return result
            setattr(owner,name,call)
        timed(ddp,'forward','forward_seconds');timed(state.model.target,'forward','target_forward_seconds')
        timed(torch.Tensor,'backward','backward_seconds');timed(state.optimizer,'step','optimizer_seconds')
        timed(state.scheduler,'set_for_next_update','scheduler_set_seconds');timed(state.scheduler,'advance','scheduler_seconds');timed(state.model,'update_target','ema_seconds')
        # Warmup is update 1 in the same state trajectory, not an uncounted optimizer step.
        for update in range(5):
            metrics={};mask_receipts.clear();torch.cuda.reset_peak_memory_stats(device);dist.barrier();t=time.monotonic()
            if arm!='B6-original':before_bytes=data.read_bytes;before_read=data.read_seconds
            result=production.training_update(ddp,state,values,1,update,rank,device)
            torch.cuda.synchronize(device);elapsed=time.monotonic()-t
            params=[p for p in state.model.online.parameters() if p.requires_grad]
            assert all(p.grad is not None and bool(torch.isfinite(p.grad).all()) for p in params)
            assert all(bool(torch.isfinite(p).all()) for p in state.model.target.parameters())
            assert state.scheduler.completed_updates==update+1 and result['queue_count']==64*(update+1) and result['queue_pointer']==64*(update+1)
            assert all(metrics[k+'_calls']==1 for k in ['optimizer_seconds','scheduler_seconds','ema_seconds','backward_seconds'])
            assert np.isfinite(result['total_loss'])
            assert bool(torch.isfinite(state.queue['values']).all()) and bool(torch.isfinite(state.queue['centers']).all())
            rows.append({'arm':arm,'rank':rank,'update':update+1,'warmup':update==0,'total_seconds':elapsed,**metrics,
                'peak_allocated_bytes':torch.cuda.max_memory_allocated(device),'peak_reserved_bytes':torch.cuda.max_memory_reserved(device),
                'rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,'loss_finite':True,'gradients_finite':True,
                'active_gradient_parameters':len(params),'queue_order_hash':tensor_digest((state.queue['scene_ids'][:state.queue['valid_count']],state.queue['centers'][:state.queue['valid_count']])),'ema_finite':True,'queue_finite':True,'queue_count':result['queue_count'],'queue_pointer':result['queue_pointer'],
                'batch_identity':result['batch_identity_digest'],'masking':copy.deepcopy(mask_receipts),
                'cache_bytes':data.read_bytes-before_bytes if arm!='B6-original' else None,
                'cache_read_seconds':data.read_seconds-before_read if arm!='B6-original' else None})
            if arm!='B6-original':data.loaded.clear();data.geometry_index.clear()
        write(Path(out)/f'{arm}.rank{rank}.json',rows)
    finally:dist.destroy_process_group()


def launch():
    a=authority();root=ROOT/a['pilot_id'];root.mkdir(parents=True,exist_ok=True);dest=root/'results'
    if dest.exists():
        for f in read(dest/'manifest.json')['files']:assert sha256_file(dest/f['path'])==f['sha256']
        return dest
    stage=Path(tempfile.mkdtemp(prefix='.stage-',dir=root));write(stage/'pilot_authority.json',a)
    execution=yaml.safe_load(Path('config/training_controller.yml').read_text())['execution']
    with gpu_pair_environment(execution) as env:
        require_no_conflicting_gpu_workload()
        env.update(PYTHONPATH=str(Path('python').resolve()),OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1')
        for arm in ARMS:
            with (stage/(arm+'.log')).open('w') as log:
                subprocess.run([sys.executable,'-m','torch.distributed.run','--standalone','--nproc_per_node=2',__file__,'worker','--arm',arm,'--output',str(stage)],env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=900)
    allrows={arm:[r for rank in range(2) for r in read(stage/f'{arm}.rank{rank}.json')] for arm in ARMS}
    for rank in range(2):
        sets=[read(stage/f'{arm}.rank{rank}.json') for arm in ARMS]
        assert all([r['batch_identity'] for r in s]==[r['batch_identity'] for r in sets[0]] for s in sets)
        assert all([r['queue_order_hash'] for r in s]==[r['queue_order_hash'] for r in sets[0]] for s in sets)
        assert [r['masking'] for r in sets[1]]==[r['masking'] for r in sets[2]]
    summary={}
    for arm,rows in allrows.items():
        warm=[r for r in rows if not r['warmup']]
        summary[arm]={key:dict(zip(['p50','p95','max'],map(float,np.quantile([r[key] for r in warm],[.5,.95,1])))) for key in ['total_seconds','batch_load_seconds','forward_seconds','target_forward_seconds','backward_seconds','optimizer_seconds','ema_seconds','peak_allocated_bytes','peak_reserved_bytes','rss_bytes','road_rows','relation_rows','fourier_rows','SN','INT','CON','prepared_read_seconds','prepared_bytes_requested','fourier_read_seconds','scheduler_seconds','scheduler_set_seconds']}
    write(stage/'acceptance.json',{'verdict':'READY_FOR_STAGE_B_TRAINING_AUTHORIZATION','summary':summary,'seed_masking_equivalence':True,
        'global_batch':32,'world_size':2,'full_training':False,'formal_checkpoints':False,'bounded_updates_per_arm':5,'warmup_updates':1})
    write(stage/'manifest.json',{'files':[{'path':p.name,'sha256':sha256_file(p)} for p in sorted(stage.iterdir())]});stage.rename(dest);return dest

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['launch','worker']);p.add_argument('--arm',choices=ARMS);p.add_argument('--output');args=p.parse_args()
    if args.action=='launch':print(launch())
    else:worker(args.arm,args.output)
