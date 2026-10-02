"""Dissertation 5.5 descriptor-level displays, with no pooled or family score."""
import csv
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from s12_runtime import configuration, model, generation_bundle, publish, payload, read_json, write_json, require, check_pin


def cross_rows(summaries, provenance):
    c,_=configuration();dictionary=read_json(check_pin(c['shared']['dictionary']))
    families={d['id']:d['family'] for d in dictionary};result=[]
    for key in c['model_order']:
        m=model(key);lookup={(r['mode'],r['descriptor'],r['region']):r for r in summaries[key]}
        require(len(lookup)==len(summaries[key])==220,'S12_SOURCE_SUMMARY_KEYS')
        for mode in ('standard','nonlocal'):
            for d in c['descriptor_order']:
                for region in c['protocol']['regions']:
                    r=lookup[(mode,d,region)]
                    result.append({**{k:m[k] for k in ('configuration_id','model_id','checkpoint_id','selected_epoch','embedding_manifest_id')},
                        'mode':mode,'descriptor':d,'family':families[d],'region':region,
                        **{k:r['query_'+k] for k in ('median','q1','q3','iqr','total_count','valid_count','invalid_count','null_reason')},
                        **{k:r[k] for k in ('candidate_total_count','candidate_valid_count','candidate_invalid_count')},
                        'source_manifest':provenance[key], 'shared_descriptor_sha256':c['shared']['descriptors']['sha256'],
                        's11_receipt_id':c['scientific_parent']['receipt_id'],'fm_reused':key=='cmp_FM'})
    validate_cross_rows(result);return result


def validate_cross_rows(rows):
    import jsonschema
    from representation_analysis import ROOT
    jsonschema.validate(rows,read_json(ROOT/'config/schemas/s12_products.schema.json')['$defs']['comparison'])
    c,_=configuration();expected=[(key,mode,d,region) for key in c['model_order'] for mode in ('standard','nonlocal') for d in c['descriptor_order'] for region in c['protocol']['regions']]
    require([(r['configuration_id'],r['mode'],r['descriptor'],r['region']) for r in rows]==expected,'S12_CROSS_POPULATION_ORDER')
    for r in rows:
        require(r['total_count']==9000==r['valid_count']+r['invalid_count'],'S12_CROSS_QUERY_COUNTS')
        require(r['candidate_total_count']==r['candidate_valid_count']+r['candidate_invalid_count'],'S12_CROSS_SUPPORT')
        vals=[r[k] for k in ('q1','median','q3','iqr')]
        if r['valid_count']:
            require(all(v is not None and np.isfinite(v) for v in vals) and vals[0]<=vals[1]<=vals[2] and vals[3]>=0,'S12_CROSS_QUANTILES')
            if r['region']=='rho':require(-1-1e-15<=vals[0]<=vals[2]<=1+1e-15,'S12_RHO_RANGE')
        else:require(all(v is None for v in vals),'S12_CROSS_NULL')
        require(r['shared_descriptor_sha256']==c['shared']['descriptors']['sha256'] and r['s11_receipt_id']==c['scientific_parent']['receipt_id'] and r['fm_reused']==(r['configuration_id']=='cmp_FM'),'S12_CROSS_SHARED_BINDING')
        require(r['null_reason']==(None if r['valid_count'] else 'no_valid_queries'),'S12_CROSS_NULL_REASON')
        m=model(r['configuration_id']);require(all(r[k]==m[k] for k in ('model_id','checkpoint_id','selected_epoch','embedding_manifest_id')),'S12_CROSS_MODEL_BINDING')
    return True


def contrast_rows(rows,series):
    c,_=configuration();lookup={(r['configuration_id'],r['mode'],r['descriptor']):r for r in rows if r['region']=='rho'};result=[]
    for new,previous in c['comparisons'][series]:
        for mode in ('standard','nonlocal'):
            for d in c['descriptor_order']:
                a,b=lookup[(new,mode,d)],lookup[(previous,mode,d)]
                result.append({'new':new,'reference':previous,'mode':mode,'descriptor':d,'family':a['family'],
                    'new_median_rho':a['median'],'reference_median_rho':b['median'],
                    'delta_median_rho':None if a['median'] is None or b['median'] is None else a['median']-b['median'],
                    'new_valid_queries':a['valid_count'],'reference_valid_queries':b['valid_count'],
                    'new_undefined_queries':a['invalid_count'],'reference_undefined_queries':b['invalid_count'],
                    'definition':c['comparisons']['delta'],'new_source':a['source_manifest'],'reference_source':b['source_manifest']})
    return result


def write_rows(stage,name,rows):
    write_json(stage/(name+'.json'),rows);pq.write_table(pa.Table.from_pylist(rows),stage/(name+'.parquet'),compression='zstd')
    with (stage/(name+'.csv')).open('w',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    require(pq.read_table(stage/(name+'.parquet')).to_pylist()==rows,'S12_PUBLICATION_READBACK')


def tables(ctx,acceptances):
    require(ctx['scope']=='full','S12_NO_PARTIAL_CROSS_MODEL_PUBLICATION')
    c,_=configuration();summaries={'cmp_FM':pq.read_table(check_pin(c['shared']['fm_summary'])).to_pylist()}
    provenance={'cmp_FM':str(check_pin(c['shared']['fm_summary_manifest']))}
    for p in acceptances:
        b=generation_bundle(p,ctx,'s12_model_acceptance');m=b['metadata'];require(m['scientific_acceptance'] and m['query_count']==9000,'S12_UNACCEPTED_MODEL')
        key=m['configuration_id'];require(key not in summaries,'S12_DUPLICATE_MODEL')
        summaries[key]=pq.read_table(payload(m['summary_manifest'],'summary.parquet')).to_pylist();provenance[key]=m['summary_manifest']
    require(set(summaries)==set(c['model_order']),'S12_ALL_MODELS_REQUIRED')
    def build(stage):
        rows=cross_rows(summaries,provenance);write_rows(stage,'comparison',rows)
        write_rows(stage,'a_contrasts',contrast_rows(rows,'a_series'));write_rows(stage,'b_comparisons',contrast_rows(rows,'b_series'))
        return {'rows':3740,'a_rows':220,'b_rows':396,'models':c['model_order'],'fm_reference':provenance['cmp_FM'],'overall_score':False}
    return publish(ctx,'s12_cross_model_tables','tables',build,[*acceptances,c['shared']['fm_summary_manifest']['path'],c['shared']['fm_summary']['path']])


def render_figures(stage,rows):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    c,_=configuration();ds=c['descriptor_order'];dictionary=read_json(check_pin(c['shared']['dictionary']));family={d['id']:d['family'] for d in dictionary}
    def draw(name,keys,values,limit,title):
        data=np.array([[np.nan if values.get((key,d)) is None else values[(key,d)] for d in ds] for key in keys])
        fig,ax=plt.subplots(figsize=(15,max(5,len(keys)*.35+3)))
        im=ax.imshow(np.ma.masked_invalid(data),cmap='RdBu_r',vmin=-limit,vmax=limit,aspect='auto',interpolation='nearest')
        ax.set_xticks(range(22),[d.replace('_',' ') for d in ds],rotation=65,ha='right',fontsize=8)
        ax.set_yticks(range(len(keys)),[k.replace('cmp_','') for k in keys]);ax.set_title(title,pad=35)
        for f in c['families']:
            idx=[i for i,d in enumerate(ds) if family[d]==f['id']]
            ax.axvline(idx[0]-.5,color='black',lw=.7);ax.text((idx[0]+idx[-1])/2,-.7,f['label'],ha='center',va='bottom',fontsize=7,rotation=15)
        fig.colorbar(im,ax=ax,label='Median query-wise rho' if limit==1 else 'Difference of median query-wise rho')
        fig.tight_layout();fig.savefig(stage/(name+'.pdf'),metadata={'CreationDate':None,'ModDate':None});plt.close(fig)
    for mode in ('standard','nonlocal'):
        draw(mode+'_rho',c['model_order'],{(r['configuration_id'],r['descriptor']):r['median'] for r in rows if r['mode']==mode and r['region']=='rho'},1,mode+' — signed descriptor alignment')
        for series in ('a_series','b_series'):
            cr=contrast_rows(rows,series);keys=[a+' − '+b for a,b in c['comparisons'][series]]
            draw(mode+'_'+series,keys,{(r['new']+' − '+r['reference'],r['descriptor']):r['delta_median_rho'] for r in cr if r['mode']==mode},2,mode+' — difference of medians (no improvement labels)')


def figures(ctx,table_manifest):
    require(ctx['scope']=='full','S12_NO_PARTIAL_COMPARISON_FIGURES');generation_bundle(table_manifest,ctx,'s12_cross_model_tables')
    def build(stage):
        rows=pq.read_table(payload(table_manifest,'comparison.parquet')).to_pylist();validate_cross_rows(rows);render_figures(stage,rows)
        require(len(list(stage.glob('*.pdf')))==6,'S12_FIGURES_COMPLETE')
        return {'figures':6,'rho_scale':[-1,1],'delta_scale':[-2,2],'model_umap':False,'family_averaging':False}
    return publish(ctx,'s12_comparison_figures','figures',build,[table_manifest])
