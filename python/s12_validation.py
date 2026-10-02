"""Independent fixed-query checks; no P3, cdist, fit or producer calls."""
from pathlib import Path
import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
from scipy.stats import spearmanr
from threadpoolctl import threadpool_limits
from representation_analysis import cosine_block,eligibility,band_positions,band_indices,file_sha256
from s11_independent_oracle import independent_difference
from s11_alignment import validate_metrics
from s12_runtime import (configuration,model,generation_bundle,publish,payload,read_json,write_json,require,check_pin)
from s12_inputs import population,embeddings,verify_inputs,verify_shared
from s12_alignment import arrays,binding,SCHEMA


def parity(keys):
    # Reads only selected historical S10 band shards; no all-model build calls.
    import struct
    from retrieval_artifacts import load as accepted
    c,_=configuration();ids,centers=population();positions=c['protocol']['independent_queries']
    p=check_pin(c['parents']['supplemental_bands']);supp=read_json(p);results=[]
    for key in keys:
        m=model(key);savedmodel=supp['models'][key]
        require(savedmodel['embedding_manifest']==m['embedding_manifest_id'] and savedmodel['payload_sha256']==m['bindings']['vectors']['sha256'],'S12_BAND_PARENT')
        x=embeddings(key);s=cosine_block(x,positions);distance,modes=eligibility(centers,positions)
        production={mode:band_indices(s,mask) for mode,mask in modes.items()};checked=0
        for i,q in enumerate(positions):
            with threadpool_limits(limits=1):reference=x@x[q]
            require(np.array_equal(reference.view(np.uint32),s[i].view(np.uint32)),'S12_GEMV_PARITY')
            path=p.parent/key/f'{q//100:03d}.bin';require(file_sha256(path)==supp['files'][str(path.relative_to(p.parent))],'S12_BAND_HASH')
            raw=path.read_bytes();magic,start,n=struct.unpack_from('<8sII',raw)
            require(magic==b'S10BND01' and start<=q+1<start+n and len(raw)==16+n*1000,'S12_BAND_BINARY')
            offset=16+(q+1-start)*1000
            for mode in ('standard','nonlocal'):
                mask=modes[mode][i];eligible=np.flatnonzero(mask);order=eligible[np.lexsort((np.asarray(ids)[eligible],-reference[eligible]))]
                stable=np.argsort(-s[i],kind='stable');require(np.array_equal(order,stable[mask[stable]]),'S12_FULL_RANK_PARITY')
                count,reserved=struct.unpack_from('<HH',raw,offset);offset+=4;require(count==len(order) and reserved==0,'S12_CANDIDATE_COUNT')
                for band,ranks in band_positions([count]).items():
                    js=order[ranks[0]-1];require(np.array_equal(js,production[mode][band][i]),'S12_BAND_MEMBERSHIP')
                    for rank,j in zip(ranks[0],js):
                        old=struct.unpack_from('<HHfd',raw,offset);offset+=16
                        require(old==(int(rank),int(j)+1,float(reference[j]),float(distance[i,j])),'S12_ACCEPTED_S10_BAND')
                        checked+=1
        results.append({'configuration_id':key,'queries':positions,'scores_bitwise_equal':True,'full_rankings':8,'s10_band_rows':checked})
    return results


def verify_model(ctx,key,summary_manifest):
    summary=generation_bundle(summary_manifest,ctx,'s12_model_summaries');require(summary['metadata']['configuration_id']==key,'S12_ACCEPTANCE_MODEL')
    c,_=configuration();ids,centers=population();x=embeddings(key);desc=arrays()
    blocks=summary['metadata']['block_manifests'];positions=[];all_tables=[];by_query={}
    for path in blocks:
        b=generation_bundle(path,ctx,'s12_alignment_blocks');require(b['metadata']['configuration_id']==key,'S12_BLOCK_MODEL')
        qs=b['metadata']['positions'];positions+=qs
        t=pq.read_table(payload(path,'metrics.parquet'));require(t.schema==SCHEMA,'S12_METRIC_SCHEMA')
        records=t.to_pylist();validate_metrics(records,ids,qs,list(desc))
        require(all(all(r[k]==v for k,v in binding(key).items()) for r in records),'S12_RECORD_BINDING')
        br=pq.read_table(payload(path,'bands.parquet')).to_pylist()
        require(len(br)==len(qs)*62 and len({(r['query_index'],r['mode'],r['rank']) for r in br})==len(br),'S12_BAND_ROW_COUNT')
        _,masks=eligibility(centers,qs);counts={(q,mode):int(mask[i].sum()) for mode,mask in masks.items() for i,q in enumerate(qs)}
        for r in br:
            count=counts[(r['query_index'],r['mode'])]
            require(r['candidate_count']==count and r['rank'] in band_positions([count])[r['band']][0] and
                r['query_scene_id']==ids[r['query_index']] and r['candidate_scene_id']!=r['query_scene_id'] and
                np.isfinite(r['cosine']) and np.isfinite(r['distance_m']) and
                (r['mode']!='nonlocal' or r['distance_m']>=2000) and all(r[k]==v for k,v in binding(key).items()),'S12_BAND_SCHEMA')
        for r in records:
            total=counts[(r['query_index'],r['mode'])] if r['region']=='rho' else 1 if r['region']=='rank1' else 10
            require(r['total_count']==total,'S12_EXACT_REGION_SUPPORT')
        all_tables.append(t)
        for q in qs:by_query[q]=path
    expected=9000 if ctx['scope']=='full' else sum(len(s['positions']) for s in __import__('s12_runtime').block_specs('pilot') if s['configuration_id']==key)
    require(len(positions)==len(set(positions))==expected and (ctx['scope']!='full' or sorted(positions)==list(range(9000))),'S12_ACCEPTANCE_POPULATION')
    require(pq.read_table(payload(summary_manifest,'query_metrics.parquet')).equals(pa.concat_tables(all_tables)),'S12_QUERY_READBACK')
    rows=read_json(payload(summary_manifest,'summary.json'))
    require(pq.read_table(payload(summary_manifest,'summary.parquet')).to_pylist()==rows and len(rows)==220,'S12_SUMMARY_SCHEMA')
    require({(r['descriptor'],r['mode'],r['region']) for r in rows}=={(d,m,b) for d in desc for m in ('standard','nonlocal') for b in c['protocol']['regions']},'S12_SUMMARY_KEYS')
    merged=pa.concat_tables(all_tables)
    for r in rows:
        part=merged.filter(pc.and_(pc.and_(pc.equal(merged['descriptor'],r['descriptor']),pc.equal(merged['mode'],r['mode'])),pc.equal(merged['region'],r['region'])))
        values=np.array([v for v in part['value'].to_pylist() if v is not None],dtype=np.float64)
        if len(values):
            q1,median,q3=np.quantile(values,[.25,.5,.75],method='linear')
            require([r['query_q1'],r['query_median'],r['query_q3'],r['query_iqr']]==[q1,median,q3,q3-q1],'S12_TYPE7_READBACK')
        else:require(all(r['query_'+k] is None for k in ('q1','median','q3','iqr')),'S12_SUMMARY_NULL')
        require(r['query_valid_count']==len(values) and all(r['candidate_'+k]==pc.sum(part[k]).as_py() for k in ('total_count','valid_count','invalid_count')),'S12_SUMMARY_SUPPORT_READBACK')
        require(r['query_total_count']==expected==r['query_valid_count']+r['query_invalid_count'] and r['candidate_total_count']==r['candidate_valid_count']+r['candidate_invalid_count'],'S12_SUMMARY_COUNTS')
    rho_checks=0;null_checks=0;band_checks=0
    for q in c['protocol']['independent_queries']:
        require(q in by_query,'S12_INDEPENDENT_QUERY_MISSING')
        records=pq.read_table(payload(by_query[q],'metrics.parquet'),filters=[('query_index','=',q)]).to_pylist()
        saved=pq.read_table(payload(by_query[q],'bands.parquet'),filters=[('query_index','=',q)]).to_pylist()
        with threadpool_limits(limits=1):score=x@x[q]
        require(np.array_equal(score,cosine_block(x,[q])[0]),'S12_GEMV_INDEPENDENT')
        _,modes=eligibility(centers,[q]);lookup={}
        for mode,mask in modes.items():
            eligible=np.flatnonzero(mask[0]);order=eligible[np.lexsort((np.asarray(ids)[eligible],-score[eligible]))]
            for band,rank in band_positions([len(order)]).items():lookup[(mode,band)]=order[rank[0]-1]
            for r in (r for r in saved if r['mode']==mode):
                j=order[r['rank']-1];require(r['candidate_scene_id']==ids[j] and r['cosine']==float(score[j]) and r['candidate_count']==len(order),'S12_INDEPENDENT_BAND');band_checks+=1
        differences={name:independent_difference(v,q) for name,(v,valid) in desc.items()}
        for r in records:
            v,valid=desc[r['descriptor']];mask=modes[r['mode']][0]&valid&valid[q];diff=differences[r['descriptor']]
            if r['region']=='rho':
                s=score[mask];d=diff[mask];reason='fewer_than_two_valid_pairs' if len(d)<2 else 'constant_similarity' if np.ptp(s)==0 else 'constant_difference' if np.ptp(d)==0 else None
                require(r['valid_count']==int(mask.sum()) and r['null_reason']==reason,'S12_RHO_VALIDITY')
                if reason:require(r['value'] is None,'S12_RHO_NULL');null_checks+=1
                else:require(np.isclose(float(spearmanr(s,d).statistic),r['value'],rtol=0,atol=2e-12),'S12_INDEPENDENT_RHO');rho_checks+=1
            else:
                js=lookup[(r['mode'],r['region'])];ok=valid[js]&valid[q];require(r['valid_count']==int(ok.sum()),'S12_BAND_SUPPORT')
                if np.any(ok):require(np.isclose(float(np.mean(diff[js[ok]])),r['value'],rtol=1e-12,atol=2e-10),'S12_INDEPENDENT_BAND_MEAN')
                else:require(r['value'] is None,'S12_BAND_NULL')
    return {'scope':ctx['scope'],'scientific_acceptance':ctx['scope']=='full','configuration_id':key,
        'query_count':expected,'rho_checks':rho_checks,'null_rho_checks':null_checks,'band_checks':band_checks,'positions':c['protocol']['independent_queries'],'oracle':'ordered_binary64','summary_manifest':summary_manifest,'p3_access':False}


def model_acceptance(ctx,key,summary_manifest):
    checks=verify_model(ctx,key,summary_manifest)
    return publish(ctx,'s12_model_acceptance',key,lambda stage:(write_json(stage/'acceptance.json',checks) or checks),[summary_manifest])


def scientific_acceptance(ctx,acceptances,tables,figures):
    require(ctx['scope']=='full','S12_NO_PILOT_SCIENTIFIC_ACCEPTANCE')
    c,_=configuration();actual=[]
    for p in acceptances:
        m=generation_bundle(p,ctx,'s12_model_acceptance');require(m['metadata']['scientific_acceptance'] and m['metadata']['query_count']==9000,'S12_MODEL_NOT_SCIENTIFIC');actual.append(m['metadata']['configuration_id'])
    require(sorted(actual)==sorted(c['computed_models']) and len(actual)==16,'S12_MODEL_ACCEPTANCE_COVERAGE')
    generation_bundle(tables,ctx,'s12_cross_model_tables');generation_bundle(figures,ctx,'s12_comparison_figures')
    from s12_publication import validate_cross_rows,cross_rows,contrast_rows
    rows=pq.read_table(payload(tables,'comparison.parquet')).to_pylist();validate_cross_rows(rows)
    require(read_json(payload(tables,'comparison.json'))==rows,'S12_CROSS_READBACK')
    sources={'cmp_FM':pq.read_table(check_pin(c['shared']['fm_summary'])).to_pylist()}
    provenance={'cmp_FM':str(check_pin(c['shared']['fm_summary_manifest']))}
    for p in acceptances:
        metadata=generation_bundle(p,ctx)['metadata'];key=metadata['configuration_id']
        sources[key]=pq.read_table(payload(metadata['summary_manifest'],'summary.parquet')).to_pylist()
        provenance[key]=metadata['summary_manifest']
    require(cross_rows(sources,provenance)==rows,'S12_CROSS_SOURCE_READBACK')
    for name,series in (('a_contrasts','a_series'),('b_comparisons','b_series')):
        expected=contrast_rows(rows,series)
        require(read_json(payload(tables,name+'.json'))==pq.read_table(payload(tables,name+'.parquet')).to_pylist()==expected,'S12_CONTRAST_READBACK')
    expected_figures={mode+'_'+suffix+'.pdf' for mode in ('standard','nonlocal') for suffix in ('rho','a_series','b_series')}
    require(set(generation_bundle(figures,ctx)['files'])==expected_figures,'S12_FIGURE_REGISTRY')
    for p in acceptances:
        metadata=generation_bundle(p,ctx)['metadata'];verify_model(ctx,metadata['configuration_id'],metadata['summary_manifest'])
    verify_inputs()
    body={'status':'PASS','models':17,'computed_models':16,'fm_recomputed':False,'descriptors_recomputed':False,'rows':3740,'umap':False,'shared_receipt':c['scientific_parent']['receipt_id'],'full_queries_per_model':9000}
    return publish(ctx,'s12_scientific_acceptance','accepted',lambda stage:(write_json(stage/'acceptance.json',body) or body),[*acceptances,tables,figures,c['scientific_parent']['receipt']['path']])
