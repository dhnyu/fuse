"""Model-aware orchestration of unchanged S11 numerical kernels (5.4/5.5)."""
from pathlib import Path
import time
PROFILE = {}
import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
from s11_alignment import alignment_block, descriptor_arrays, validate_metrics, METRIC_SCHEMA
from representation_analysis import query_summary
from s12_runtime import (configuration,model,require_spec,block_specs,generation_bundle,
    publish,payload,read_json,write_json,require)
from s12_inputs import population,embeddings

MODEL_FIELDS=pa.schema([('configuration_id',pa.string()),('model_id',pa.string()),('checkpoint_id',pa.string())])
SCHEMA=pa.schema(list(MODEL_FIELDS)+list(METRIC_SCHEMA))

def binding(key):
    m=model(key)
    return {k:m[k] for k in ('configuration_id','model_id','checkpoint_id')}


def arrays():
    c,_=configuration();ids,_=population()
    # Accepted full descriptors even for bounded pilots; never sparse P3 inputs.
    return descriptor_arrays(c['shared']['descriptor_manifest']['path'],ids,'full')


def plan(ctx,accepted,shared):
    generation_bundle(accepted,ctx,'s12_accepted_inputs');generation_bundle(shared,ctx,'s12_shared_descriptors')
    specs=block_specs(ctx['scope']);keys=list(dict.fromkeys(s['configuration_id'] for s in specs))
    value={'scope':ctx['scope'],'models':keys,'blocks':specs,'fm_reuse':configuration()[0]['scientific_parent'],
        'queries_per_model':sum(len(s['positions']) for s in specs if s['configuration_id']==keys[0])}
    return publish(ctx,'s12_model_block_plan','plan',lambda stage:(write_json(stage/'plan.json',value) or {'models':len(keys),'blocks':len(specs)}),[accepted,shared])


def build_block(ctx,plan_manifest,shared,spec):
    PROFILE.clear();started=time.perf_counter()
    require_spec(ctx,spec);generation_bundle(plan_manifest,ctx,'s12_model_block_plan');generation_bundle(shared,ctx,'s12_shared_descriptors')
    require(spec in read_json(payload(plan_manifest,'plan.json'))['blocks'],'S12_PLAN_SPEC')
    key=spec['configuration_id'];m=model(key);ids,centers=population()
    def build(stage):
        tick=time.perf_counter();x=embeddings(key);PROFILE['embedding_read_seconds']=time.perf_counter()-tick
        tick=time.perf_counter();desc=arrays();PROFILE['shared_descriptor_read_seconds']=time.perf_counter()-tick
        tick=time.perf_counter()
        records,bands=alignment_block(x,centers,ids,spec['positions'],desc)
        PROFILE['alignment_compute_seconds']=time.perf_counter()-tick
        tick=time.perf_counter()
        validate_metrics(records,ids,spec['positions'],list(desc))
        bound=binding(key)
        table=pa.Table.from_pylist([{**bound,**r} for r in records],schema=SCHEMA)
        bt=pa.Table.from_pylist([{**bound,**r} for r in bands])
        pq.write_table(table,stage/'metrics.parquet',compression='zstd');pq.write_table(bt,stage/'bands.parquet',compression='zstd')
        require(pq.read_table(stage/'metrics.parquet').equals(table) and pq.read_table(stage/'bands.parquet').equals(bt),'S12_BLOCK_READBACK')
        PROFILE['serialization_qc_seconds']=time.perf_counter()-tick
        return {**bound,'positions':spec['positions'],'metric_rows':len(records),'band_rows':len(bands),'embedding_manifest_id':m['embedding_manifest_id']}
    result=publish(ctx,'s12_alignment_blocks',key+'__'+spec['block_id'],build,[plan_manifest,shared,m['bindings']['embedding_manifest']['path'],m['bindings']['vectors']['path']])
    PROFILE['block_total_seconds']=time.perf_counter()-started
    PROFILE['orchestration_publication_seconds']=PROFILE['block_total_seconds']-sum(PROFILE.get(k,0) for k in ('embedding_read_seconds','shared_descriptor_read_seconds','alignment_compute_seconds','serialization_qc_seconds'))
    return result


def summarize_model(ctx,key,plan_manifest,blocks):
    require(key!='cmp_FM','S12_FM_RECOMPUTATION_FORBIDDEN')
    generation_bundle(plan_manifest,ctx,'s12_model_block_plan');p=read_json(payload(plan_manifest,'plan.json'))
    expected=[q for s in p['blocks'] if s['configuration_id']==key for q in s['positions']]
    chosen=[path for path in blocks if Path(path).parent.name.startswith(key+'__')]
    require(len(chosen)>0,'S12_MISSING_BLOCKS')
    actual=[]
    for path in chosen:
        b=generation_bundle(path,ctx,'s12_alignment_blocks');require(b['metadata']['configuration_id']==key,'S12_BLOCK_MODEL');actual+=b['metadata']['positions']
    require(sorted(actual)==expected and len(set(actual))==len(actual),'S12_MODEL_QUERY_COVERAGE')
    def build(stage):
        table=pa.concat_tables([pq.read_table(payload(path,'metrics.parquet')) for path in sorted(chosen)])
        summaries=[];c,_=configuration()
        for descriptor in c['descriptor_order']:
            for mode in ('standard','nonlocal'):
                for region in c['protocol']['regions']:
                    part=table.filter(pc.and_(pc.and_(pc.equal(table['descriptor'],descriptor),pc.equal(table['mode'],mode)),pc.equal(table['region'],region)))
                    require(sorted(part['query_index'].to_pylist())==expected,'S12_SUMMARY_QUERY_COVERAGE')
                    summary=query_summary(part['value'].to_pylist())
                    summaries.append({**binding(key),'descriptor':descriptor,'mode':mode,'region':region,
                        **{'query_'+k:v for k,v in summary.items()},
                        **{'candidate_'+k:int(pc.sum(part[k]).as_py()) for k in ('total_count','valid_count','invalid_count')}})
        pq.write_table(table,stage/'query_metrics.parquet',compression='zstd');pq.write_table(pa.Table.from_pylist(summaries),stage/'summary.parquet',compression='zstd')
        write_json(stage/'summary.json',summaries)
        require(pq.read_table(stage/'query_metrics.parquet').equals(table) and pq.read_table(stage/'summary.parquet').to_pylist()==summaries,'S12_SUMMARY_READBACK')
        return {**binding(key),'queries':len(expected),'metric_rows':table.num_rows,'summary_rows':len(summaries),'block_manifests':sorted(chosen)}
    return publish(ctx,'s12_model_summaries',key,build,[plan_manifest,*sorted(chosen)])
