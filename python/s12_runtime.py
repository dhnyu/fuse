"""Frozen S12 bindings and explicit pilot/full execution gates. No producers."""
from functools import lru_cache
import hashlib
import os
from pathlib import Path
import numpy as np
from representation_analysis import ROOT, file_sha256
from s11_artifacts import read_json, dumps, require, runtime as s11_runtime, publish, load_bundle, payload, write_json

SOURCES = ['config/s12_representation_alignment.json','config/s12_representation_alignment.lock.json',
 'config/schemas/s12_representation_alignment.schema.json','config/schemas/s12_products.schema.json',
 'python/s12_runtime.py','python/s12_inputs.py','python/s12_alignment.py','python/s12_validation.py',
 'python/s12_publication.py','scripts/s12_representation.py','scripts/pilot_s12_representation.py',
 'scripts/run_s12_representation.R','R/s12_representation.R','targets/s12_representation.R',
 '_targets_representation_comparison.R','tests/python/test_s12_representation.py',
 'tests/testthat/test-s12-representation.R','tools/targets-network/s12_representation_phases.yml']

@lru_cache(maxsize=1)
def configuration():
    import jsonschema
    c=read_json(ROOT/'config/s12_representation_alignment.json')
    lock=read_json(ROOT/'config/s12_representation_alignment.lock.json')
    require(file_sha256(ROOT/'config/s12_representation_alignment.json')==lock['contract_sha256'],'S12_CONTRACT_HASH')
    jsonschema.validate(c,read_json(ROOT/'config/schemas/s12_representation_alignment.schema.json'))
    for name,h in lock['kernel_sources'].items():require(file_sha256(ROOT/name)==h,'S12_KERNEL_CHANGED:'+name)
    import subprocess
    head=subprocess.check_output(['git','-C',lock['dissertation_root'],'rev-parse','reduced'],text=True).strip()
    require(head==lock['dissertation_commit'],'S12_DISSERTATION_HEAD')
    for name,h in lock['dissertation_sources'].items():require(file_sha256(Path(lock['dissertation_root'])/'template'/name)==h,'S12_DISSERTATION_CHANGED')
    require(c['model_order']==[m['configuration_id'] for m in c['models']] and c['computed_models']==c['model_order'][1:],'S12_MODEL_ORDER')
    require(len(set(c['descriptor_order']))==22,'S12_REGISTRY')
    return c,lock


def identity():
    c,lock=configuration();r=s11_runtime();environment={k:v for k,v in r.items() if k!='sources'}
    require(environment==c['runtime'],'S12_RUNTIME_CHANGED')
    source={p:file_sha256(ROOT/p) for p in SOURCES}
    source.update(lock['kernel_sources'])
    body={'contract_sha256':lock['contract_sha256'],'runtime':environment,'sources':source}
    return {**body,'sha256':hashlib.sha256(dumps(body).encode()).hexdigest()}


def check_pin(pin):
    require(file_sha256(pin['path'])==pin['sha256'],'S12_PIN_CHANGED:'+pin['path'])
    return Path(pin['path'])


def context(scope, pilot_root=None, workers=None):
    c,_=configuration();execution=c['execution']; ident=identity()
    if scope=='full':
        require(os.environ.get(execution['authorization_env'])==execution['authorization_value'],'S12_FULL_NOT_AUTHORIZED')
        receipt=read_json(os.environ.get(execution['pilot_receipt_env'],'/nonexistent/s12-pilot'))
        require(receipt['status']=='PASS' and receipt['identity']==ident and receipt['full_execution_performed'] is False,'S12_CURRENT_PILOT_REQUIRED')
        require(receipt['receipt_id']=='s12pilot_'+hashlib.sha256(dumps({k:v for k,v in receipt.items() if k!='receipt_id'}).encode()).hexdigest()[:24],'S12_PILOT_RECEIPT_HASH')
        require([b['workers'] for b in receipt['benchmarks']]==[1,4,8] and all(b['byte_parity'] for b in receipt['benchmarks']),'S12_PILOT_BENCHMARKS')
        checked=[]
        for p in receipt['model_acceptances']:
            b=load_bundle(p,'s12_model_acceptance');md=b['metadata']
            require(b['context']['identity']==ident and b['context']['scope']=='pilot' and md['query_count']==72 and not md['scientific_acceptance'],'S12_PILOT_MODEL_ACCEPTANCE')
            require(all(file_sha256(p)==h for p,h in b['parents'].items()),'S12_PILOT_PARENT_CHANGED')
            checked.append(md['configuration_id'])
        require(sorted(checked)==sorted(execution['pilot_models']),'S12_PILOT_MODEL_COVERAGE')
        workers=int(os.environ.get('FUSE_S12_WORKERS','0'))
        require(workers==receipt['recommended_workers'] and workers in execution['production_worker_candidates'],'S12_WORKERS')
        root=Path(execution['output_root'])
    else:
        require(scope=='pilot' and pilot_root is not None and workers in execution['pilot_workers'],'S12_PILOT_SCOPE')
        root=Path(pilot_root).resolve()
        require(root.is_relative_to(Path(execution['pilot_root']).resolve()),'S12_PILOT_ROOT')
    require(workers<=min(execution['maximum_workers'],len(os.sched_getaffinity(0))),'S12_CPU_BUDGET')
    body={'scope':scope,'identity':ident,'workers':workers,'threads':1,'shared_receipt':c['scientific_parent']['receipt_id']}
    generation='s12_'+hashlib.sha256(dumps(body).encode()).hexdigest()[:24]
    return {**body,'generation':generation,'root':str(root/generation)}


def get_context(request):
    if request.get('scope')=='pilot':return context('pilot',request['pilot_root'],request['workers'])
    return context('full')


def model(configuration_id):
    c,_=configuration()
    matches=[m for m in c['models'] if m['configuration_id']==configuration_id]
    require(len(matches)==1,'S12_UNKNOWN_MODEL')
    return matches[0]


def generation_bundle(path,ctx,kind=None):
    m=load_bundle(path,kind)
    require(m['context']==ctx,'S12_CONTEXT_MISMATCH')
    require(all(file_sha256(p)==h for p,h in m['parents'].items()),'S12_PARENT_CHANGED')
    return m


def block_specs(scope):
    c,_=configuration();keys=c['computed_models'] if scope=='full' else c['execution']['pilot_models']
    specs=[]
    # Round-robin models per block allows useful concurrency, no nested pools.
    for start in range(0,9000,32):
        block_id=f'{start//32:04d}'
        if scope=='pilot' and block_id not in c['execution']['pilot_block_ids']:continue
        for key in keys:specs.append({'configuration_id':key,'block_id':block_id,'positions':list(range(start,min(start+32,9000)))})
    return specs


def require_spec(ctx,spec):
    require(spec in block_specs(ctx['scope']) and spec['configuration_id']!='cmp_FM','S12_BLOCK_SCOPE')
    require(0<len(spec['positions'])<=32,'S12_BLOCK_SIZE')


def references():
    c,_=configuration()
    return {name:{**pin} for name,pin in c['shared'].items()}
