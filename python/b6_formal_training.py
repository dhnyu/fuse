"""Isolated formal B6 experiment; dissertation training/selection equations.

Reuses production scientific update, validation, selection, checkpoint and RNG
implementations. All writes are restricted to a new experimental namespace.
"""
from __future__ import annotations
import argparse
import copy
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import time
import tempfile
import hashlib
import numpy as np
import torch
import torch.distributed as dist
import yaml
from torch.nn.parallel import DistributedDataParallel
import training_worker as engine
import training_family_inputs as family
from training_finalization import selection_contract_content, evaluate_selection_candidate, qualifies_patience_reset
from b6_bounded_pilot import PairedReader, ARMS, authority as pilot_authority, ROOT as PILOT_ROOT
from b6_s50_cache import ROOT as CACHE_ROOT
from b6_stage_b_preparation import read, write, sha256_file, tensor_digest
from b6_postbank_adapter import digest
from training_prepared_cache import ProductionPreparedData
from training_geometry_cache import GeometryCacheReader
from training_runtime_inputs import SceneCenterIndex
from model_data import build_vocabulary, validate_vocabulary_contract
from training_transport import gpu_pair_environment, require_no_conflicting_gpu_workload

ROOT = Path('/mnt/hdd002/dhnyu/fusedata/experiments/b6_road_granularity_stage_b_training')
CONFIG = Path('config/b6_stage_b_training.yml')


def checked_path(path):
    path = Path(path).resolve()
    if not path.is_relative_to(ROOT) or path == ROOT:
        raise ValueError('B6 formal experimental namespace required')
    return path


def immutable_json(path, value):
    path = checked_path(path)
    if path.exists():
        if read(path) != value: raise ValueError(f'immutable collision: {path}')
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.incomplete')
    with tmp.open('x') as f:
        json.dump(value, f, sort_keys=True, indent=2, allow_nan=False)
        f.write('\n'); f.flush(); os.fsync(f.fileno())
    tmp.rename(path)


def manifest_check(root):
    n = 0
    for m in Path(root).rglob('manifest.json'):
        d = read(m)
        for row in d.get('files', d.get('entries', [])):
            p = m.parent / row.get('path', row.get('name', ''))
            if sha256_file(p) != row['sha256']: raise ValueError(f'checksum: {p}')
            n += 1
    return n


def source_inventory():
    # Includes scientific transitive imports and experimental orchestration;
    # excludes reports/network HTML so results can be documented after freeze.
    paths = list(Path('python').glob('*.py')) + list(Path('config').rglob('*.yml'))
    paths += list(Path('config/schemas').glob('*.json'))
    paths += [Path(p) for p in ('R/scene_descriptors.R', 'R/b6_validation_descriptors.R', 'R/b6_stage_b_training.R', 'targets/b6_stage_b_training.R', '_targets_b6_stage_b_training.R')]
    return {str(p): sha256_file(p) for p in sorted(set(paths))}


def resolve_contract():
    cfg = yaml.safe_load(CONFIG.read_text())
    import jsonschema
    jsonschema.validate(cfg, read('config/schemas/b6_stage_b_training.schema.json'))
    assert tuple(cfg['arms']) == ARMS and cfg['root_seed'] == 1629790839
    p = pilot_authority(); pilot = PILOT_ROOT / p['pilot_id'] / 'results'
    assert read(pilot / 'acceptance.json')['verdict'] == 'READY_FOR_STAGE_B_TRAINING_AUTHORIZATION'
    c = p['input_contract']; old = c['con_method']['frozen_science']
    cache = CACHE_ROOT / c['design_id'] / 'prepared'
    a = read(cache / 'acceptance.json')
    assert a['status'] == 'PASS' and a['count'] == a['original_parity'] == 22368 and a['G_Ppre_only_SN']
    values = old['resolved_training']; model = old['resolved_model']['model']
    assert model['d'] == model['d_c'] == 256 and model['attention_heads'] == 4 and model['relation_layers'] == 3 and model['dropout'] == .2
    assert values['training']['root_seed'] == cfg['root_seed']
    assert [values['training'][k] for k in ('global_batch_size','world_size','per_rank_batch_size','maximum_epochs','updates_per_epoch','logical_k')] == [32,2,16,200,76,8]
    body = {'namespace': cfg['namespace'], 'settings': cfg, 'sources': source_inventory(),
            'frozen_science': old, 'input_contract': c, 'cache_acceptance': a,
            'cache_manifest_sha256': sha256_file(cache / 'manifest.json'),
            'pilot_acceptance_sha256': sha256_file(pilot / 'acceptance.json'),
            'pilot_id': p['pilot_id'], 'selection': selection_contract_content(),
            'validation': {'queries': 2000, 'gallery': 1000, 'normalized': True, 'similarity': 'cosine'},
            'fresh_initialization': True, 'canonical_resolver_eligible': False,
            'predeclared_interpretation': ['both improve: granularity support', 'G only: sibling dependence',
                'Ppre more: sibling competition', 'neither: no benefit evidence',
                'loss/margin without HIT: ceiling compatible', 'HIT1 above 0.857: stop and audit']}
    body['design_id'] = 'b6formal_' + digest(body)[:24]
    return body


def prepare():
    c = resolve_contract(); root = checked_path(ROOT / c['design_id'])
    if (root / 'contract.json').exists():
        assert read(root / 'contract.json') == c
        assert read(root / 'preflight.json')['status'] == 'PASS'
        return root
    # No scientific dirty files at authority issuance. Reports may be committed later.
    dirty = subprocess.check_output(['git','status','--porcelain'], text=True)
    if dirty.strip(): raise ValueError('commit validated source before authority issuance')
    assert subprocess.check_output(['git','branch','--show-current'], text=True).strip() == 'B6'
    sha = subprocess.check_output(['git','rev-parse','HEAD'], text=True).strip()
    exp = ROOT.parent
    roots = [exp/'b6_road_granularity/b6a_f5d6a32cdd09cf5688b0666a',
             exp/'b6_road_granularity_stage_b'/c['frozen_science']['design_id'],
             exp/'b6_con_lift'/c['input_contract']['con_method']['design_id']/'census',
             PILOT_ROOT/c['pilot_id']/'results', CACHE_ROOT/c['input_contract']['design_id']/'prepared']
    counts = {str(r): manifest_check(r) for r in roots}
    parity = read(roots[1]/'parity/original_parity.json')
    assert parity['status'] == 'PASS' and parity['sample_count'] == 22368 and parity['full_population_checked']
    destination=root
    ROOT.mkdir(parents=True,exist_ok=True)
    root=Path(tempfile.mkdtemp(prefix='.authority-staging-',dir=ROOT))
    immutable_json(root/'contract.json', c)
    immutable_json(root/'preflight.json', {'status':'PASS','checksummed_files':counts,'original_parity':22368,'source_sha':sha,
        'runtime':{'python':sys.version,'torch':torch.__version__,'cuda':torch.version.cuda,
            'gpu':subprocess.check_output(['nvidia-smi','--query-gpu=name,uuid,driver_version,memory.total','--format=csv,noheader'],text=True).splitlines(),
            'cpu_affinity':sorted(os.sched_getaffinity(0))},
        'preservation':{'reduced':subprocess.check_output(['git','rev-parse','reduced'],text=True).strip(),
            'dissertation':subprocess.check_output(['git','-C','/members/dhnyu/dhnyu-masters-dissertation','rev-parse','HEAD'],text=True).strip()}})
    from b6_validation_descriptors import build
    descriptors=build(root,c)
    for arm in ARMS:
        body = {'namespace': c['namespace'], 'arm':arm, 'source_sha':sha, 'design_id':c['design_id'],
                'contract_sha256':sha256_file(root/'contract.json'),'descriptors_sha256':sha256_file(descriptors),'formal_training':True,'fresh':True,
                'canonical_resolver_eligible':False,'seed_group':c['settings']['seed_group'],
                'root_seed':1629790839,'configuration_hash':digest(c['frozen_science']['resolved_training']),
                'input_identity': c['cache_acceptance']['arm_identities'].get(arm, 'accepted_hash_bound_original'),
                'shared_fourier': c['cache_acceptance']['shared_geometry_identity'] if arm != ARMS[0] else 'accepted_hash_bound_original'}
        body['authority_id'] = 'b6formalauth_' + digest(body)[:24]
        immutable_json(root/arm/'authority.json', body)
    root.rename(destination)
    return destination


class FormalReader(PairedReader):
    def __init__(self, root, arm, original):
        super().__init__(root, arm, original)
        self.validation_scenes = original.validation_scenes
    def clear(self):
        self.loaded.clear(); self.geometry_index.clear()


def build_values(c, arm):
    old = c['frozen_science']; config = copy.deepcopy(old['resolved_training'])
    canonical = ProductionPreparedData(old['settings']['prepared_parent'], 'main_1.0x', 8, verify_payloads=True)
    roots = yaml.safe_load(Path('config/training_controller.yml').read_text())['roots']
    vocab = build_vocabulary(roots['categories'])
    data = canonical if arm == ARMS[0] else FormalReader(CACHE_ROOT/c['input_contract']['design_id']/'prepared', arm, canonical)
    geo = GeometryCacheReader(Path(old['settings']['prepared_parent'])/'geometry/geometry_cache_manifest.json') if arm == ARMS[0] else data
    return {'config':config,'model_config':old['resolved_model'],'family':'B6','data':data,
            'geometry_cache':geo,'vocabulary':vocab,'vocabulary_sizes':validate_vocabulary_contract(vocab),
            'scene_centers':SceneCenterIndex.from_current_contract(config, old['settings']['prepared_parent']),
            'row':{'scientific':{'peak_learning_rate':.001,'ema':.999}}}


def install_masking(data, arm, receipts):
    original = family.family_modality_assignments
    def masking(batch, cfg, epoch, role, global_rank=0):
        if arm != ARMS[0]:
            batch = {**batch,'entities':{**batch['entities'], 'local_entity_id':torch.tensor(data.rng(batch),dtype=torch.int64)}}
        result = original(batch, cfg, epoch, role, global_rank)
        receipts.append(digest({'role':role,'ids':tensor_digest(batch['entities']['local_entity_id']), 'assignments':tensor_digest(result)}))
        return result
    family.family_modality_assignments = masking
    return original


def validation(state, values, device, rank, epoch):
    """Production validation, with read-only output hooks for post-selection analysis."""
    vectors = []; mech = []
    def hook(module, args, result):
        batch = args[0]
        vectors.append(torch.nn.functional.normalize(result['scene_embedding'],dim=1).detach().cpu())
        scene_index = batch['entity_scene_index']; weights = result['modality_weights']
        scores = module.pool(result['entity']).squeeze(-1)
        for i, scene in enumerate(batch['scene_ids']):
            rows = scene_index == i; n = int(rows.sum())
            w = torch.softmax(scores[rows],0)
            pos = batch['entities']['relative_position_m'][rows]
            parent_max=None;parent_effective=None
            if n and str(batch['view_ids'][i])=='original':
                if isinstance(values['data'],FormalReader) and scene in values.get('gallery_parents',{}):
                    parents=values['gallery_parents'][scene]; assert len(parents)==n
                    totals={}
                    for parent,weight in zip(parents,w.cpu().tolist()): totals[parent]=totals.get(parent,0.)+weight
                    parent_max=max(totals.values());parent_effective=1/sum(x*x for x in totals.values())
                elif not isinstance(values['data'],FormalReader):
                    parent_max=float(w.max());parent_effective=float(1/w.square().sum())
            mech.append({'scene_id':scene,'entities':n,'parent_attention_max':parent_max,'parent_attention_effective':parent_effective,
                'attention_effective_entities':float(1/(w.square().sum())) if n else None,
                'attention_max':float(w.max()) if n else None,
                'position_dispersion_m':float(((pos-pos.mean(0)).square().sum(1).mean()).sqrt()) if n else None,
                'gate_mean':weights[rows].mean((0,2)).cpu().tolist() if n else None})
        if isinstance(values['data'], FormalReader): values['data'].clear()
    handle = state.model.online.register_forward_hook(hook)
    try: metric = engine.full_validation(state, values, device, rank, epoch)
    finally: handle.remove()
    gathered = [None,None] if rank == 0 else None
    dist.gather_object({'vectors':torch.cat(vectors),'mechanistic':mech}, gathered, dst=0)
    payload = None
    if rank == 0:
        combined = torch.empty(3000,256)
        rows = [None]*3000
        for r in range(2):
            combined[r::2] = gathered[r]['vectors']
            rows[r::2] = gathered[r]['mechanistic']
        payload = {'vectors':combined, 'scene_ids':values['data'].validation_scenes,'mechanistic':rows,'metric':metric}
    return metric, payload


def event(root, kind, **fields):
    path = checked_path(root/'events.jsonl')
    with path.open('a') as f:
        f.write(json.dumps({'time':engine.utc_now(),'event':kind,**fields},sort_keys=True,allow_nan=False)+'\n')
        f.flush(); os.fsync(f.fileno())


def save_tensor(path, value):
    path = checked_path(path)
    if path.exists():
        old = torch.load(path, map_location='cpu',weights_only=False)
        if tensor_digest(old) != tensor_digest(value): raise ValueError(f'checkpoint collision {path}')
        return
    temp = path.with_suffix(path.suffix+'.incomplete')
    with temp.open('xb') as f:
        torch.save(value,f); f.flush(); os.fsync(f.fileno())
    test = torch.load(temp,map_location='cpu',weights_only=False)
    assert tensor_digest(test) == tensor_digest(value)
    temp.rename(path)


def worker(root, arm):
    root = checked_path(root); c = read(root/'contract.json'); out = root/arm; a = read(out/'authority.json')
    assert source_inventory() == c['sources'], 'source freeze changed'
    assert a['contract_sha256'] == sha256_file(root/'contract.json')
    rank = int(os.environ['RANK']); assert int(os.environ['WORLD_SIZE']) == 2
    values = build_values(c, arm)
    values['gallery_parents']=read(root/'validation_descriptors/child_parents.json')
    device = engine.configure_process(values['config'],rank)
    dist.init_process_group('nccl',device_id=device)
    try:
        state = engine.create_state(values,device)
        ddp = DistributedDataParallel(state.model.online,device_ids=[rank],output_device=rank,find_unused_parameters=False,
            bucket_cap_mb=50,gradient_as_bucket_view=False,static_graph=False)
        torch.cuda.manual_seed(1629790839+rank)
        immutable_initial = tensor_digest(state.model.online.state_dict())
        masks=[]; install_masking(values['data'],arm,masks)
        load_metrics={}
        original_batches=engine._local_batches
        def measured_batches(*args,**kwargs):
            began=time.monotonic(); result=original_batches(*args,**kwargs)
            load_metrics['assembly_seconds']=time.monotonic()-began
            load_metrics['entity_rows']=sum(len(b['entities']['local_entity_id']) for b in result[0])
            load_metrics['relation_rows']=sum(len(b['edges']['relation_mask']) for b in result[0])
            return result
        engine._local_batches=measured_batches
        checkpoints = sorted(out.glob('boundary-*.json'))
        expected = {'run_identity':a['authority_id'],'configuration_identity':a['configuration_hash'],
                    'parent_identities':{'contract_sha256':a['contract_sha256']},'world_size':2}
        start = 1
        if checkpoints:
            last = read(checkpoints[-1]); path = out/last['checkpoint']
            assert sha256_file(path) == last['checkpoint_sha256']
            restored = engine.restore_checkpoint(path,state,rank,expected)
            start = restored['progress']['resume_epoch']
        if rank == 0: event(out,'RESUMED' if checkpoints else 'FRESH_INITIALIZATION',epoch=start,initial_model_hash=immutable_initial,authority=a['authority_id'])
        selection = c['selection']; campaign_start=time.monotonic()
        reason = 'MAXIMUM_EPOCH'
        if state.events_without_improvement >= 4: reason='EARLY_STOPPING_PATIENCE'
        else:
            for epoch in range(start,201):
                if source_inventory() != c['sources']: raise ValueError('source changed during campaign')
                if rank == 0: event(out,'EPOCH_STARTED',epoch=epoch)
                t=time.monotonic(); times=[]; alignment=[]; loads=[]; torch.cuda.reset_peak_memory_stats(device)
                for batch in range(76):
                    masks.clear(); b=time.monotonic()
                    row=engine.training_update(ddp,state,values,epoch,batch,rank,device)
                    torch.cuda.synchronize(device); times.append(time.monotonic()-b)
                    assert np.isfinite(row['total_loss'])
                    state.training_trace.append(row)
                    loads.append(dict(load_metrics))
                    alignment.append({'batch':row['batch_identity_digest'],'mask':digest(masks),
                        'queue':tensor_digest((state.queue['scene_ids'],state.queue['centers'],state.queue['pointer'],state.queue['valid_count']))})
                    if isinstance(values['data'],FormalReader): values['data'].clear()
                perf={'epoch':epoch,'rank':rank,'seconds':time.monotonic()-t,'update_seconds':times,'loads':loads,
                    'peak_allocated':torch.cuda.max_memory_allocated(device),'peak_reserved':torch.cuda.max_memory_reserved(device),
                    'peak_rss':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,'alignment':alignment}
                gathered=[None,None] if rank==0 else None; dist.gather_object(perf,gathered,dst=0)
                if rank==0:
                    event(out,'EPOCH_COMPLETED',epoch=epoch,updates=state.scheduler.completed_updates,seconds=max(r['seconds'] for r in gathered))
                    # Attempt-specific evidence preserves interrupted work without overwriting it.
                    attempt=hashlib.sha256(json.dumps(gathered,sort_keys=True).encode()).hexdigest()[:12]
                    immutable_json(out/f'performance-{epoch:03d}-{attempt}.json',{'ranks':gathered})
                if epoch%5: continue
                assert all(bool(torch.isfinite(p).all()) for p in state.model.parameters())
                assert bool(torch.isfinite(state.queue['values']).all())
                vt=time.monotonic(); metric,payload=validation(state,values,device,rank,epoch)
                if metric['HIT@1'] > .857 + 1e-6:
                    raise ValueError('HIT1 ceiling exceeded: stop campaign for population/input/leakage audit')
                selected,basis=evaluate_selection_candidate(metric,state.best,selection['equivalence_tolerance'])
                reset=qualifies_patience_reset(metric,state.best,selection['equivalence_tolerance'])
                state.events_without_improvement=0 if reset else state.events_without_improvement+1
                if selected: state.best={**metric,'checkpoint_id':f'epoch-{epoch:03d}.pt'}
                state.validation_trace.append(metric)
                # Canonical complete state including both rank RNGs; experimental authority envelope only.
                envelope={'content':{'scientific':{'configuration_hash':a['configuration_hash']},'parents':expected['parent_identities']}}
                staged,ck=engine._stage_checkpoint(state,values,rank,a['authority_id'],envelope,epoch,epoch,out)
                if rank==0:
                    target=out/f'epoch-{epoch:03d}.pt'
                    if target.exists(): assert sha256_file(target)==sha256_file(staged)
                    else: os.link(staged,target)
                    reread=torch.load(target,map_location='cpu',weights_only=False)
                    assert engine.scientific_state_digest(reread)==engine.scientific_state_digest(ck)
                    save_tensor(out/f'validation-{epoch:03d}.pt',payload)
                    receipt={'epoch':epoch,'metric':metric,'selected':selected,'basis':basis,'patience':state.events_without_improvement,
                        'checkpoint':target.name,'checkpoint_sha256':sha256_file(target),'validation_sha256':sha256_file(out/f'validation-{epoch:03d}.pt'),
                        'validation_seconds':time.monotonic()-vt,'state_digest':engine.scientific_state_digest(ck)}
                    immutable_json(out/f'boundary-{epoch:03d}.json',receipt)
                    event(out,'VALIDATION_CHECKPOINT_COMMITTED',**receipt)
                    print(arm,epoch,metric,'patience',state.events_without_improvement,flush=True)
                dist.barrier()
                if state.events_without_improvement==4:
                    reason='EARLY_STOPPING_PATIENCE'; break
        if rank==0:
            final={'status':'COMPLETE','reason':reason,'completed_epoch':state.validation_trace[-1]['completed_epoch'],
                'selected':state.best,'authority_id':a['authority_id'],'source_sha':a['source_sha'],
                'updates':state.scheduler.completed_updates,'initial_model_hash':immutable_initial,
                'invocation_seconds':time.monotonic()-campaign_start,'validation_trace':state.validation_trace}
            selected_path=out/state.best['checkpoint_id']; assert selected_path.exists()
            final['selected_checkpoint_sha256']=sha256_file(selected_path)
            event(out,'TRAINING_COMPLETED',**final)
            immutable_json(out/'completion.json',final)
        dist.barrier()
    finally: dist.destroy_process_group()


def launch(arm):
    root=prepare(); out=root/arm
    if (out/'completion.json').exists():
        completion=read(out/'completion.json')
        assert sha256_file(out/completion['selected']['checkpoint_id'])==completion['selected_checkpoint_sha256']
        return out/'completion.json'
    execution=yaml.safe_load(Path('config/training_controller.yml').read_text())['execution']
    with gpu_pair_environment(execution) as env:
        require_no_conflicting_gpu_workload()
        env.update(PYTHONPATH=str(Path('python').resolve()),OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1')
        stamp=time.time_ns()
        with (out/f'worker-{stamp}.log').open('x') as log:
            subprocess.run([sys.executable,'-m','torch.distributed.run','--standalone','--nproc_per_node=2',__file__,
                'worker','--arm',arm,'--root',str(root)],env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
    return out/'completion.json'


def smoke_worker(root, arm):
    """Optimizer-free validation/checkpoint smoke before formal source freeze."""
    root=checked_path(root); c=resolve_contract();rank=int(os.environ['RANK'])
    values=build_values(c,arm)
    if (root/'validation_descriptors/child_parents.json').exists():
        values['gallery_parents']=read(root/'validation_descriptors/child_parents.json')
    device=engine.configure_process(values['config'],rank)
    dist.init_process_group('nccl',device_id=device)
    try:
        state=engine.create_state(values,device)
        before=tensor_digest(state.model.state_dict())
        metric,payload=validation(state,values,device,rank,0)
        assert before==tensor_digest(state.model.state_dict())
        # Exact checkpoint/readback and RNG restoration use canonical implementation.
        authority={'content':{'scientific':{'configuration_hash':'smoke'},'parents':{'test':True}}}
        path,ck=engine._stage_checkpoint(state,values,rank,'smoke',authority,0,0,root/arm)
        paths=[str(path) if rank==0 else None];dist.broadcast_object_list(paths,src=0)
        engine.restore_checkpoint(paths[0],state,rank,{'run_identity':'smoke','world_size':2})
        assert before==tensor_digest(state.model.state_dict())
        if rank==0:
            save_tensor(root/arm/'validation.pt',payload)
            immutable_json(root/arm/'smoke.json',{'status':'PASS','optimizer_updates':state.scheduler.completed_updates,
                'validation_queries':metric['query_count'],'gallery':metric['gallery_count'],'checkpoint_restore':True})
    finally:dist.destroy_process_group()


def smoke():
    root=checked_path(ROOT/f'engineering-smoke-{time.time_ns()}');root.mkdir(parents=True)
    execution=yaml.safe_load(Path('config/training_controller.yml').read_text())['execution']
    with gpu_pair_environment(execution) as env:
        require_no_conflicting_gpu_workload()
        env.update(PYTHONPATH=str(Path('python').resolve()),OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1')
        for arm in ARMS:
            (root/arm).mkdir()
            with (root/(arm+'.log')).open('x') as log:
                subprocess.run([sys.executable,'-m','torch.distributed.run','--standalone','--nproc_per_node=2',__file__,
                    'smoke-worker','--arm',arm,'--root',str(root)],env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
    return root


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','launch','worker','summarize','smoke','smoke-worker'])
    parser.add_argument('--arm',choices=ARMS);parser.add_argument('--root');args=parser.parse_args()
    if args.action=='smoke': print(smoke())
    elif args.action=='smoke-worker': smoke_worker(args.root,args.arm)
    elif args.action=='prepare': print(prepare()/'contract.json')
    elif args.action=='launch': print(launch(args.arm))
    elif args.action=='worker': worker(args.root,args.arm)
    else:
        from b6_formal_analysis import summarize
        print(summarize(prepare()))
