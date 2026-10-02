"""S12 recovery execution/provenance only; dissertation 5.4/5.5 math unchanged."""
import hashlib
import json
import os
from pathlib import Path
import sys
import types
from functools import lru_cache
import time
import numpy as np
import pyarrow.parquet as pq
from s11_artifacts import dumps,read_json,write_json,publish,load_bundle,payload,require
from representation_analysis import ROOT,file_sha256
from s12_runtime import configuration as scientific_configuration,identity as scientific_identity,block_specs
from s12_single_attempt import exclusive,run_tasks

SOURCES=['python/s12_recovery.py','python/s12_single_attempt.py','scripts/run_s12_recovery.py',
         'scripts/pilot_s12_recovery.py','tests/python/test_s12_recovery.py',
         'config/schemas/s12_recovery.schema.json','config/schemas/s12_recovery_index.schema.json']


def pin(p):
    require(file_sha256(p['path'])==p['sha256'],'RECOVERY_PIN:'+p['path'])
    return Path(p['path'])


@lru_cache(maxsize=1)
def configuration():
    import jsonschema
    c=read_json(ROOT/'config/s12_recovery.json');lock=read_json(ROOT/'config/s12_recovery.lock.json')
    require(file_sha256(ROOT/'config/s12_recovery.json')==lock['contract_sha256'],'RECOVERY_CONTRACT')
    jsonschema.validate(c,read_json(ROOT/'config/schemas/s12_recovery.schema.json'))
    require(scientific_identity()==c['original_context']['identity'],'RECOVERY_SCIENTIFIC_SOURCE_RUNTIME')
    for p,h in lock['sources'].items():require(file_sha256(ROOT/p)==h,'RECOVERY_EXECUTOR_CHANGED:'+p)
    require(executor_runtime()==lock['runtime'],'RECOVERY_RUNTIME_CHANGED')
    pin(c['scientific_contract'])
    sci,_=scientific_configuration()
    for k in ('models','shared','scientific_parent','model_order'):require(c[k]==sci[k],'RECOVERY_BINDINGS')
    return c,lock


@lru_cache(maxsize=1)
def executor_runtime():
    import platform,importlib.metadata,subprocess
    # Actual scheduler is stdlib Popen; capture the excluded historical chain too.
    r=json.loads(subprocess.check_output(['Rscript','-e','cat(jsonlite::toJSON(setNames(lapply(c("targets","crew","mirai","nanonext","processx"),function(p) as.character(packageVersion(p))),c("targets","crew","mirai","nanonext","processx")),auto_unbox=TRUE))'],text=True))
    from threadpoolctl import threadpool_info
    native={t['filepath']:file_sha256(t['filepath']) for t in threadpool_info() if t['user_api']=='blas'}
    return {'native_blas_sha256':native,'python':platform.python_version(),'executable_sha256':file_sha256(sys.executable),'system':platform.system(),
            'machine':platform.machine(),'libc':list(platform.libc_ver()),'psutil':importlib.metadata.version('psutil'),
            'historical_scheduler_packages':r,'active_scheduler':'stdlib subprocess.Popen; exclusive durable claims; no crew'}


@lru_cache(maxsize=1)
def executor_identity():
    c,lock=configuration()
    return {'contract_sha256':lock['contract_sha256'],'sources':lock['sources'],'runtime':lock['runtime'],
            'sha256':hashlib.sha256(dumps(lock).encode()).hexdigest()}


def key_of(spec):return spec['configuration_id']+'__'+spec['block_id']


def inventory(check_payloads=True):
    c,_=configuration();a=read_json(pin(c['adoption']));missing=read_json(pin(c['missing']))
    audited=read_json(pin(c['audited_inventory']));oldmissing=read_json(pin(c['audited_missing']))
    require(missing==oldmissing and hashlib.sha256(dumps(missing).encode()).hexdigest()==c['missing_order_sha256'],'RECOVERY_MISSING_HASH')
    require(a['producing_context']==c['original_context'],'RECOVERY_ORIGINAL_CONTEXT')
    plan=read_json(payload(pin(c['original_plan']),'plan.json'))['blocks']
    require(plan==block_specs('full'),'RECOVERY_ORIGINAL_PLAN')
    specs={key_of(s):s for s in plan};adopted={key_of(r):r for r in a['rows']};absent={key_of(r):r for r in missing}
    require(len(a['rows'])==len(adopted)==2983 and len(missing)==len(absent)==1529,'RECOVERY_COUNTS')
    require(not(set(adopted)&set(absent)) and set(adopted)|set(absent)==set(specs) and len(specs)==4512,'RECOVERY_PARTITION')
    require('cmp_B2__0186' in adopted,'RECOVERY_UNRECORDED_ADOPTION')
    audited_by={key_of(r):r for r in audited}
    for key,r in {**adopted,**absent}.items():
        qs=specs[key]['positions']
        require((r['query_start'],r['query_end'],r['query_count'])==(qs[0],qs[-1],len(qs)),'RECOVERY_QUERY_INTERVAL')
        if key in adopted:
            for field in ('manifest_path','manifest_sha256','metrics_sha256','bands_sha256'):
                require(r[field]==audited_by[key][field],'RECOVERY_AUDITED_HASH')
            if check_payloads:verify_adopted(r,c)
    for model in c['model_order'][1:]:
        ss=[s for s in plan if s['configuration_id']==model]
        require(len(ss)==282 and [q for s in ss for q in s['positions']]==list(range(9000)),'RECOVERY_MODEL_COVERAGE')
    return c,specs,adopted,absent


def verify_adopted(r,c):
    p=Path(r['manifest_path']);require(file_sha256(p)==r['manifest_sha256'],'RECOVERY_ADOPTED_MANIFEST')
    b=load_bundle(p,'s12_alignment_blocks');require(b['context']==c['original_context'],'RECOVERY_ADOPTED_CONTEXT')
    require(b['files']=={'metrics.parquet':r['metrics_sha256'],'bands.parquet':r['bands_sha256']},'RECOVERY_ADOPTED_PAYLOADS')
    require(all(file_sha256(p)==h for p,h in b['parents'].items()),'RECOVERY_ADOPTED_PARENTS')
    return b


def context(root,phase,workers):
    c,_=configuration();root=Path(root).resolve()
    require(phase in ('pilot','full'),'RECOVERY_PHASE')
    require(root.is_relative_to(Path(c['pilot_root'] if phase=='pilot' else c['output_root'])),'RECOVERY_OUTPUT_NAMESPACE')
    require(workers in ((1,4,8) if phase=='pilot' else (8,)),'RECOVERY_WORKERS')
    if phase=='full':require(os.environ.get(c['authorization_env'])==c['authorization_value'],'RECOVERY_NOT_AUTHORIZED')
    ident=executor_identity()
    # scope=full identifies the unchanged 9000-scene numerical population only.
    body={'scope':'full','execution_phase':phase,'identity':c['original_context']['identity'],'recovery_executor':ident,
          'original_generation':c['original_context']['generation'],'workers':workers,'threads':1,
          'shared_receipt':c['scientific_parent']['receipt_id'],'historical_retries':83,'new_execution_retry_limit':0}
    return {**body,'generation':'s12recovery_'+hashlib.sha256(dumps(body).encode()).hexdigest()[:24],'root':str(root)}


def prepare(ctx):
    c,_,_,_=inventory(False);root=Path(ctx['root']);root.mkdir(parents=True,exist_ok=True)
    # Both new manifests explicitly reference their original immutable parents.
    shared=publish(ctx,'s12_shared_descriptors','references',lambda st:(write_json(st/'references.json',{'references':c['shared'],'copy':False}) or {'reused':True}),[pin(c['original_shared']),pin(c['adoption'])])
    plan=publish(ctx,'s12_model_block_plan','plan',lambda st:(write_json(st/'plan.json',{'blocks':block_specs('full'),'scope':'full','adopted':2983,'missing':1529}) or {'blocks':4512}),[pin(c['original_plan']),pin(c['missing']),shared])
    return plan,shared


def verify_block(path,ctx,spec):
    from s12_alignment import SCHEMA,binding,arrays
    from s11_alignment import validate_metrics
    from s12_inputs import population
    b=load_bundle(path,'s12_alignment_blocks');require(b['context']==ctx,'RECOVERY_NEW_CONTEXT')
    require(all(file_sha256(p)==h for p,h in b['parents'].items()),'RECOVERY_NEW_PARENTS')
    md=b['metadata'];qs=spec['positions'];bound=binding(spec['configuration_id'])
    require(md['positions']==qs and all(md[k]==v for k,v in bound.items()),'RECOVERY_NEW_SPEC')
    c,_=scientific_configuration();m=next(m for m in c['models'] if m['configuration_id']==spec['configuration_id'])
    require(md['embedding_manifest_id']==m['embedding_manifest_id'],'RECOVERY_NEW_EMBEDDING')
    expected_parents={str(Path(ctx['root'])/'s12_model_block_plan/plan/manifest.json'),str(Path(ctx['root'])/'s12_shared_descriptors/references/manifest.json'),m['bindings']['embedding_manifest']['path'],m['bindings']['vectors']['path']}
    require(set(b['parents'])==expected_parents,'RECOVERY_NEW_PARENT_SET')
    ids,_=population();t=pq.read_table(payload(path,'metrics.parquet'))
    require(t.schema==SCHEMA and t.num_rows==len(qs)*220,'RECOVERY_METRIC_SCHEMA')
    rows=t.to_pylist();validate_metrics(rows,ids,qs,c['descriptor_order'])
    require(all(all(r[k]==v for k,v in bound.items()) for r in rows),'RECOVERY_RECORD_BINDING')
    bands=pq.read_table(payload(path,'bands.parquet')).to_pylist()
    require(len(bands)==len(qs)*62 and len({(r['query_index'],r['mode'],r['rank']) for r in bands})==len(bands),'RECOVERY_BAND_ROWS')
    return {'manifest':str(path),'manifest_sha256':file_sha256(path),'files':b['files'],'positions':qs}


def compute_worker(request):
    c,specs,adopted,missing=inventory(False);key=request['key']
    require(key not in adopted,'RECOVERY_ADOPTED_COMPUTATION_FORBIDDEN')
    require(key in missing,'RECOVERY_NOT_MISSING')
    ctx=request['context'];require(ctx==context(ctx['root'],ctx['execution_phase'],ctx['workers']),'RECOVERY_WORKER_IDENTITY')
    if ctx['execution_phase']=='pilot':require(key in c['pilot_keys'],'RECOVERY_PILOT_BOUND')
    namespace=Path(request['scheduler_root']);claim=namespace/'claims'/(key+'.json')
    require(claim.exists() and read_json(claim)['launch_count']==1,'RECOVERY_EXCLUSIVE_CLAIM_REQUIRED')
    # A second worker cannot use an existing supervisor claim to invoke the kernel.
    exclusive(namespace/'worker_claims'/(key+'.json'),{'pid':os.getpid(),'key':key})
    destination=Path(ctx['root'])/'s12_alignment_blocks'/key
    require(not destination.exists(),'RECOVERY_PUBLICATION_CONFLICT')
    from threadpoolctl import threadpool_info
    require(all(t['num_threads']==1 for t in threadpool_info() if t['user_api']=='blas'),'RECOVERY_NUMERICAL_THREADS')
    from s12_alignment import build_block,PROFILE
    path=build_block(ctx,request['plan'],request['shared'],specs[key])
    verified=verify_block(path,ctx,specs[key])
    exclusive(request['ack'],{'status':'PASS','key':key,'manifest':path,'verified':verified,'profile':dict(PROFILE)})


def schedule(ctx,keys,plan,shared):
    c,specs,adopted,missing=inventory(False)
    require(set(keys)<=set(missing) and not(set(keys)&set(adopted)),'RECOVERY_ADOPTED_KEY_SCHEDULED')
    if ctx['execution_phase']=='pilot':require(keys==c['pilot_keys'],'RECOVERY_PILOT_EXACT_KEYS')
    else:require(keys==list(missing),'RECOVERY_FULL_EXACT_KEYS')
    root=Path(ctx['root'])/'scheduler';tasks=[]
    for key in keys:
        ack=root/'acks'/(key+'.json');req=root/'requests'/(key+'.json')
        exclusive(req,{'key':key,'context':ctx,'plan':plan,'shared':shared,'ack':str(ack),'scheduler_root':str(root)})
        tasks.append({'key':key,'ack':str(ack),'argv':[sys.executable,str(ROOT/'scripts/run_s12_recovery.py'),'worker','--request',str(req)]})
    def validate(task,ack):return verify_block(ack['manifest'],ctx,specs[task['key']])
    return run_tasks(root,tasks,ctx['workers'],validate,forbidden=adopted)


def mixed_index(ctx,require_complete=True):
    c,specs,adopted,missing=inventory();rows=[]
    for key,spec in specs.items():
        if key in adopted:
            r=adopted[key];b=verify_adopted(r,c);p=r['manifest_path'];origin='adopted_original'
        else:
            p=str(Path(ctx['root'])/'s12_alignment_blocks'/key/'manifest.json')
            if not Path(p).exists():
                require(not require_complete,'RECOVERY_MISSING_UNION_KEY:'+key);continue
            verify_block(p,ctx,spec);b=load_bundle(p);origin='single_attempt_recovery'
            scheduler=Path(ctx['root'])/'scheduler'
            require((scheduler/'states'/key/'verified.json').exists(),'RECOVERY_UNVERIFIED_CLAIM')
        rows.append({'key':key,'configuration_id':spec['configuration_id'],'block_id':spec['block_id'],'positions':spec['positions'],
            'manifest':p,'manifest_sha256':file_sha256(p),'files':b['files'],'producing_context':b['context'],'origin':origin,'status':'PASS'})
    import jsonschema
    value={'schema_version':'1.0.0','complete':require_complete,'scientific_contract_sha256':c['scientific_contract']['sha256'],'rows':rows}
    jsonschema.validate(value,read_json(ROOT/'config/schemas/s12_recovery_index.schema.json'))
    if require_complete:require([r['key'] for r in rows]==list(specs),'RECOVERY_UNION_COVERAGE')
    return value


def bind_function(function,**overrides):
    """Reuse exact accepted bytecode; inject only explicit provenance dependencies.

    No mutation/monkeypatch of scientific modules, source, arrays or values.
    """
    globals_=dict(function.__globals__);globals_.update(overrides)
    return types.FunctionType(function.__code__,globals_,function.__name__,function.__defaults__,function.__closure__)


class MixedReader:
    def __init__(self,ctx,index):
        self.ctx=ctx;self.c=configuration()[0];self.rows={str(Path(r['manifest']).resolve()):r for r in index['rows']}
    def __call__(self,path,ctx,kind=None):
        require(ctx==self.ctx,'RECOVERY_READER_CONTEXT')
        p=str(Path(path).resolve());b=load_bundle(p,kind)
        if p in self.rows:
            r=self.rows[p];require(file_sha256(p)==r['manifest_sha256'] and b['context']==r['producing_context'] and b['files']==r['files'],'RECOVERY_INDEX_BINDING')
        else:
            require(Path(p).is_relative_to(Path(ctx['root'])) and b['context']==ctx,'RECOVERY_UNINDEXED_PARENT')
            require(b['kind']!='s12_alignment_blocks','RECOVERY_UNINDEXED_BLOCK')
        require(all(file_sha256(p)==h for p,h in b['parents'].items()),'RECOVERY_READER_PARENT')
        return b


def downstream(ctx,plan):
    require(ctx['execution_phase']=='full','RECOVERY_NO_PILOT_FULL_AGGREGATION')
    c,_=configuration();require(os.environ.get(c['authorization_env'])==c['authorization_value'],'RECOVERY_NOT_AUTHORIZED')
    index=mixed_index(ctx);exclusive(Path(ctx['root'])/'mixed_index.json',index)
    read=MixedReader(ctx,index)
    import s12_alignment as a,s12_validation as v,s12_publication as p
    summarize=bind_function(a.summarize_model,generation_bundle=read)
    verify=bind_function(v.verify_model,generation_bundle=read)
    accept=bind_function(v.model_acceptance,generation_bundle=read,verify_model=verify)
    tables=bind_function(p.tables,generation_bundle=read)
    figures=bind_function(p.figures,generation_bundle=read)
    final=bind_function(v.scientific_acceptance,generation_bundle=read,verify_model=verify)
    paths=[r['manifest'] for r in index['rows']];accepted=[]
    for key in c['model_order'][1:]:
        summary=summarize(ctx,key,plan,paths);accepted.append(accept(ctx,key,summary))
    table=tables(ctx,accepted);figure=figures(ctx,table);result=final(ctx,accepted,table,figure)
    return result


def independent_block(path,queries):
    """Bounded independent read-back, using the accepted ordered binary64 oracle."""
    from s12_inputs import embeddings,population
    from s12_alignment import arrays
    from s11_independent_oracle import independent_difference
    from representation_analysis import cosine_block,eligibility,band_positions
    from scipy.stats import spearmanr
    from threadpoolctl import threadpool_limits
    b=load_bundle(path);key=b['metadata']['configuration_id'];x=embeddings(key);ids,centers=population();desc=arrays()
    checks={'rho':0,'null':0,'band_means':0,'band_rows':0,'queries':queries,'oracle':'ordered_binary64'}
    require(set(queries)<=set(b['metadata']['positions']),'RECOVERY_INDEPENDENT_QUERIES')
    for q in queries:
        with threadpool_limits(limits=1):score=x@x[q]
        require(np.array_equal(score.view('uint32'),cosine_block(x,[q])[0].view('uint32')),'RECOVERY_SCORE_BYTES')
        distance,modes=eligibility(centers,[q]);look={}
        for mode,mask in modes.items():
            candidates=np.flatnonzero(mask[0]);order=candidates[np.lexsort((np.asarray(ids)[candidates],-score[candidates]))]
            stable=np.argsort(-score,kind='stable');require(np.array_equal(order,stable[mask[0,stable]]),'RECOVERY_RANK_PARITY')
            for band,ranks in band_positions([len(order)]).items():look[mode,band]=order[ranks[0]-1]
            for r in pq.read_table(payload(path,'bands.parquet'),filters=[('query_index','=',q),('mode','=',mode)]).to_pylist():
                j=order[r['rank']-1];require(r['candidate_scene_id']==ids[j] and r['cosine']==float(score[j]) and r['distance_m']==float(distance[0,j]) and r['candidate_count']==len(order),'RECOVERY_BAND_PARITY');checks['band_rows']+=1
        diffs={d:independent_difference(v,q) for d,(v,valid) in desc.items()}
        for r in pq.read_table(payload(path,'metrics.parquet'),filters=[('query_index','=',q)]).to_pylist():
            _,valid=desc[r['descriptor']];d=diffs[r['descriptor']];mask=modes[r['mode']][0]&valid&valid[q]
            if r['region']=='rho':
                s=score[mask];v=d[mask];reason='fewer_than_two_valid_pairs' if len(v)<2 else 'constant_similarity' if np.ptp(s)==0 else 'constant_difference' if np.ptp(v)==0 else None
                require(r['valid_count']==int(mask.sum()) and r['null_reason']==reason,'RECOVERY_RHO_SUPPORT')
                if reason:require(r['value'] is None,'RECOVERY_RHO_NULL');checks['null']+=1
                else:require(np.isclose(float(spearmanr(s,v).statistic),r['value'],rtol=0,atol=2e-12),'RECOVERY_RHO');checks['rho']+=1
            else:
                js=look[r['mode'],r['region']];ok=valid[js]&valid[q];require(r['valid_count']==int(ok.sum()),'RECOVERY_BAND_SUPPORT')
                if ok.any():require(np.isclose(float(np.mean(d[js[ok]])),r['value'],rtol=1e-12,atol=2e-10),'RECOVERY_BAND_MEAN')
                else:require(r['value'] is None,'RECOVERY_BAND_NULL')
                checks['band_means']+=1
    return checks
