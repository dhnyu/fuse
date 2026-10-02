#!/usr/bin/env python
"""Read-only source audit; dissertation 4 inference/cosine equation and 5.3.
No model loading, inference, training, target execution, or scientific writes.
Existing S10 float32 GEMV + stable lexical ties are preserved exactly.
"""
from pathlib import Path
import argparse, hashlib, json, os, sys, time, tempfile, shutil, subprocess
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from scipy.stats import rankdata, skew, kurtosis
from scipy.spatial import ConvexHull
from threadpoolctl import threadpool_limits, threadpool_info
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'python'))
from s10_extreme_rank1 import lineage, sha, read, band_ranks
MODES=('standard','nonlocal')
PROBS=np.array([0,.01,.05,.10,.25,.5,.75,.90,.95,.99,1])
QN=['min','p01','p05','p10','p25','median','p75','p90','p95','p99','max']
BINS=np.array([0,250,500,750,1000,1500,2000,3000,5000,10000,np.inf])
LABELS=['[0,.25)','[.25,.5)','[.5,.75)','[.75,1)','[1,1.5)','[1.5,2)','[2,3)','[3,5)','[5,10)','[10,inf)']
TOL=1e-6

def stats(x):
    x=np.asarray(x,dtype=np.float64);x=x[np.isfinite(x)];n=len(x)
    if not n:return dict(n=0)
    q=dict(zip(QN,map(float,np.quantile(x,PROBS))));sd=float(x.std(ddof=0));mean=float(x.mean())
    return dict(n=n,mean=mean,sd=sd,**q,iqr=q['p75']-q['p25'],mad=float(np.median(np.abs(x-q['median']))),
                skewness=float(skew(x,bias=True)) if sd else None,excess_kurtosis=float(kurtosis(x,bias=True)) if sd else None,
                cv=sd/mean if mean>0 and x.min()>=0 else None)

def corr(a,b):
    a=np.asarray(a,dtype=float);b=np.asarray(b,dtype=float)
    return float(np.corrcoef(a,b)[0,1]) if np.ptp(a)>0 and np.ptp(b)>0 else np.nan

def regions(n):
    return {'rank1':np.array([0]),'upper':np.arange(1,11),'middle':np.arange((n-10)//2,(n-10)//2+10),'lower':np.arange(n-10,n)}

def eligible_order(scores,d,i,mode):
    o=np.argsort(-scores,kind='stable');return o[(o!=i)&((d[o]>=2000) if mode=='nonlocal' else True)]

def fixture():
    s=np.array([1,.8,.8,.7,.6]);d=np.array([0,1999.999,2000,2000.001,3000.])
    assert eligible_order(s,d,0,'standard').tolist()==[1,2,3,4]
    assert eligible_order(s,d,0,'nonlocal').tolist()==[2,3,4]
    for n in [8999,8800,8799,100]:
        assert (regions(n)['middle']+1).tolist()==band_ranks(n)['middle']
    assert regions(8999)['middle'].tolist()==list(range(4494,4504))
    assert stats([1,2,3])['sd']==np.std([1,2,3],ddof=0)
    print('fixture PASS: self, exact 2km boundary, ties, odd/even middle, statistics',flush=True)

def csv(out,name,rows):
    df=rows if isinstance(rows,pd.DataFrame) else pd.DataFrame(rows)
    df.to_csv(out/(name+'.csv'),index=False);return df

def jsonout(path,obj):
    path.write_text(json.dumps(obj,indent=2,ensure_ascii=False,default=lambda x:x.item() if isinstance(x,np.generic) else str(x)))

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path);ap.add_argument('--pilot',type=int,default=0);ap.add_argument('--fixture-only',action='store_true');args=ap.parse_args()
    fixture()
    if args.fixture_only:return
    assert args.output and not args.output.exists(),'new output directory required'
    started=time.perf_counter();started_at=datetime.now(ZoneInfo('Asia/Seoul')).isoformat();cfg=read(REPO/'config/s10_extreme_rank1.json')
    X,C,ids,counts,info=lineage(cfg);ids=np.array(ids);N=len(ids);nq=args.pilot or N
    lock=read(REPO/'config/s11_representation_analysis.lock.json')
    source={k:v['path'] for k,v in lock['parents'].items()}
    source.update(original_reader_code=str(REPO/'python/retrieval_originals.py'),pipeline_code=str(REPO/'python/retrieval_pipeline.py'),lineage_builder_code=str(REPO/'python/retrieval_lineage.py'),inference_code=str(REPO/'python/retrieval_inference.py'),ranking_code=str(REPO/'python/retrieval_ranking.py'),
                  encoder_code=str(REPO/'python/model_families.py'),audit_code=str(Path(__file__).resolve()),lineage_code=str(REPO/'python/s10_extreme_rank1.py'),
                  audit_config=str(REPO/'config/s10_extreme_rank1.json'),lineage_lock=str(REPO/'config/s11_representation_analysis.lock.json'))
    for key,pin in lock['parents'].items():assert sha(pin['path'])==pin['sha256'],key
    source.update({f'lineage_{i}':p for i,p in enumerate(info['source_sha256'])})
    diss=Path('/members/dhnyu/dhnyu-masters-dissertation/template')
    for f in ['sections/chapters/results/03-spatial-scene-retrieval.typ','sections/chapters/results/02-model-training-and-selection.typ','sections/chapters/04-methodology-training.typ','main.pdf']:
        source[f'dissertation_{Path(f).name}']=str(diss/f)
    lifecycle=Path('/mnt/hdd002/dhnyu/fusedata/runtime/training_lifecycle')/info['model']['authority_id']
    handoff=read(lifecycle/'finalization.json');source['finalization']=handoff['finalization_path']
    final=read(source['finalization']);info['finalization']=final
    assert final['selected_checkpoint']['checkpoint_id']==info['model']['checkpoint_id'] and final['selected_checkpoint']['completed_epoch']==60
    assert final['status']=='SUCCEEDED' and final['evaluation_consumption_count']==0
    for p in Path(handoff['bundle_path']).rglob('*'):
        if p.is_file() and p.suffix in ['.json','.csv','.parquet']:source['bundle_'+p.name]=str(p)
    snapshots={p:sha(p) for p in source.values()}
    out=args.output;out.mkdir(parents=True);(out/'figures').mkdir();(out/'reproduction').mkdir()
    for p in [Path(__file__),REPO/'python/s10_extreme_rank1.py',REPO/'config/s10_extreme_rank1.json']:
        shutil.copyfile(p,out/'reproduction'/p.name)
    jsonout(out/'source_checksums_before.json',snapshots)
    # Coordinate binding to accepted scene index, not a new geospatial derivation.
    si=pq.read_table(source['scene_index']).to_pandas()
    evaluation=si[si.split=='evaluation'].set_index('scene_id')
    assert evaluation.index.is_unique and set(evaluation.index)==set(ids)
    assert np.array_equal(evaluation.loc[ids,['center_x','center_y']].to_numpy(),C)
    assert (evaluation.loc[ids,'epsg']==5186).all()
    csv(out,'evaluation_scene_identity',evaluation.loc[ids].reset_index().drop(columns=['geometry','center_wkt']))
    print('scene index center/split/CRS/9000 ID binding PASS',flush=True)
    gallery=read(source['gallery'])['body']['rows']
    # Band artifact is reused for all four regions, with complete independent parity check.
    band=pq.read_table(source['bands']).to_pandas()
    assert len(band)==558000 and band.groupby('mode').query_scene_id.nunique().to_dict()=={'nonlocal':9000,'standard':9000}
    old=pq.read_table(Path(cfg['original_generation'])/'rankings/cmp_FM/rankings.parquet').to_pandas()
    source['legacy_ranking']=str(Path(cfg['original_generation'])/'rankings/cmp_FM/rankings.parquet');snapshots[source['legacy_ranking']]=sha(source['legacy_ranking'])
    bandgroups={(int(q)-1,m):g for (q,m),g in band.groupby(['query_index','mode'],sort=False)}
    oldgroups={(q,m):g for (q,m),g in old.groupby(['query_id','retrieval_mode'],sort=False)}
    # Edge proxies only: evaluation-center convex hull and center centroid, no external labels.
    hull=ConvexHull(C);edge=np.min(-(C@hull.equations[:,:2].T+hull.equations[:,2]),axis=1)
    center_distance=np.linalg.norm(C-C.mean(axis=0),axis=1)
    curve_ranks=np.unique(np.r_[np.arange(1,101),np.rint(np.geomspace(101,8000,60)).astype(int)])
    curves={m:[] for m in MODES};top={m:np.empty((nq,10),np.int32) for m in MODES}
    rows=[];selected=[];checks=[];near=[];duplicate=[];numeric=[];pair_summ=[];pair_hist=[]
    _,inverse,dupcounts=np.unique(X,axis=0,return_inverse=True,return_counts=True)
    for group in np.flatnonzero(dupcounts>1):
        members=np.flatnonzero(inverse==group)
        for i in members:duplicate.append(dict(group=int(group),group_size=len(members),query_scene_id=ids[i],center_x=C[i,0],center_y=C[i,1],object_count=counts[ids[i]]['object_count'],source_payload_sha256=gallery[i]['source_payload_sha256']))
    csv(out,'duplicate_representation_groups',duplicate)
    duplicate_pairs=[]
    for group in np.flatnonzero(dupcounts>1):
        members=np.flatnonzero(inverse==group)
        for a,i in enumerate(members):
            for j in members[a+1:]:duplicate_pairs.append(dict(group=int(group),scene_a=ids[i],scene_b=ids[j],distance_m=float(np.linalg.norm(C[i]-C[j])),same_source_shard=gallery[i]['source_payload_sha256']==gallery[j]['source_payload_sha256']))
    csv(out,'exact_duplicate_pairs',duplicate_pairs)
    matched_bands=matched_old=0;global_fail={'self':0,'nonlocal_distance':0,'monotonic':0,'nonfinite':0,'eligible_count':0,'band_parity':0,'legacy_parity':0,'distance_range':0,'tie_lexical':0}
    maxdistance=0.;exact_boundary=0;greater_one=0;pairmax={m:-np.inf for m in MODES};pairmin={m:np.inf for m in MODES}
    temps=tempfile.TemporaryDirectory(prefix='pair_quantiles_',dir=out)
    mm={m:np.memmap(Path(temps.name)/(m+'.bin'),mode='w+',dtype=np.float32,shape=(nq*(N-1),)) for m in MODES}
    offsets={m:0 for m in MODES};mom={m:np.zeros(4,dtype=np.float64) for m in MODES};hist={m:np.zeros(2000,dtype=np.int64) for m in MODES}
    nearstats={t:{'unordered_pairs':0,'local_pairs':0,'distance_sum':0.,'distance_min':np.inf,'distance_max':0.,'examples':0} for t in [.99,.995,.999,.9999,1-1e-6]}
    with threadpool_limits(limits=1):
      for i in range(nq):
        scores=X@X[i];d=np.linalg.norm(C-C[i],axis=1);maxdistance=max(maxdistance,float(d.max()));exact_boundary+=int((d==2000).sum())
        greater_one+=int(((scores>1)&(np.arange(N)!=i)).sum())
        if i%max(1,nq//32)==0:
            xd=X.astype(np.float64);exact=xd@xd[i]/(np.linalg.norm(xd,axis=1)*np.linalg.norm(xd[i]));o32=eligible_order(scores,d,i,'standard');o64=eligible_order(exact,d,i,'standard')
            numeric.append(dict(query_scene_id=ids[i],max_abs_float32_vs_float64_cosine=float(np.max(np.abs(scores-exact))),rank1_changed=bool(o32[0]!=o64[0]),rank1_similarity_error=float(scores[o32[0]]-exact[o32[0]])))
        for t,a in nearstats.items():
            ix=np.flatnonzero((scores>t)&(np.arange(N)>i));dd=d[ix];a['unordered_pairs']+=len(ix);a['local_pairs']+=int((dd<2000).sum());a['distance_sum']+=float(dd.sum())
            if len(ix):a['distance_min']=min(a['distance_min'],float(dd.min()));a['distance_max']=max(a['distance_max'],float(dd.max()))
            for j in ix[:max(0,20-a['examples'])]:
                near.append(dict(threshold=t,query_scene_id=ids[i],candidate_scene_id=ids[j],cosine=float(scores[j]),distance_m=float(d[j]),exact_duplicate=bool(inverse[i]==inverse[j])));a['examples']+=1
        order=np.argsort(-scores,kind='stable')
        for mode in MODES:
            o=order[(order!=i)&((d[order]>=2000) if mode=='nonlocal' else True)];s=scores[o].astype(float);dist=d[o];n=len(o);r=regions(n)
            global_fail['self']+=int((o==i).sum());global_fail['nonlocal_distance']+=int((dist<2000).sum()) if mode=='nonlocal' else 0
            global_fail['monotonic']+=int((np.diff(s)>0).sum());global_fail['nonfinite']+=int((~np.isfinite(s)).sum());global_fail['eligible_count']+=int(n!=(N-1 if mode=='standard' else (d>=2000).sum()))
            global_fail['distance_range']+=int(((dist<0)|(~np.isfinite(dist))).sum());ties=np.flatnonzero(np.diff(s)==0);global_fail['tie_lexical']+=int((o[ties]>o[ties+1]).sum())
            bg=bandgroups[(i,mode)];pos=bg['rank'].to_numpy()-1
            bad=(ids[o[pos]]!=bg.candidate_scene_id.to_numpy())|(s[pos]!=bg.cosine.to_numpy())|(dist[pos]!=bg.distance_m.to_numpy())|(n!=bg.candidate_count.to_numpy())
            global_fail['band_parity']+=int(bad.sum());matched_bands+=len(bg)
            if (ids[i],mode) in oldgroups:
                og=oldgroups[(ids[i],mode)];p=og['rank'].to_numpy()-1;bad=(ids[o[p]]!=og.gallery_scene_id.to_numpy())|(s[p]!=og.similarity.to_numpy())|(dist[p]!=og.geographic_distance_m.to_numpy());global_fail['legacy_parity']+=int(bad.sum());matched_old+=len(og)
            top[mode][i]=o[:10];curves[mode].append(s[curve_ranks-1]);q=np.quantile(s,[.5,.95,.99]);sd=s.std();rd=rankdata(dist);rs=rankdata(s)
            row=dict(query_index=i,query_scene_id=ids[i],mode=mode,center_x=C[i,0],center_y=C[i,1],epsg=5186,object_count=counts[ids[i]]['object_count'],hull_edge_proxy_m=edge[i],centroid_distance_m=center_distance[i],eligible_count=n,excluded_nonlocal_count=N-1-n,excluded_nonlocal_proportion=(N-1-n)/(N-1),rank1_scene_id=ids[o[0]],rank1_similarity=s[0],rank1_distance_m=dist[0],rank1_distance_km=dist[0]/1000,
              all_mean=s.mean(),all_sd=sd,all_median=q[0],all_p95=q[1],all_p99=q[2],all_min=s[-1],all_max=s[0],max_minus_p99=s[0]-q[2],max_minus_mean=s[0]-s.mean(),max_zscore=(s[0]-s.mean())/sd if sd else np.nan,
              gap_rank1_rank2=s[0]-s[1],gap_rank1_rank5=s[0]-s[4],gap_rank1_rank10=s[0]-s[9],gap_rank1_rank100=s[0]-s[99],gap_rank1_median=s[0]-q[0],gap_rank1_bottom=s[0]-s[-1],
              gap_rank1_top5_mean=s[0]-s[:5].mean(),gap_rank1_top10_mean=s[0]-s[:10].mean(),top10_sd=s[:10].std(),top10_range=np.ptp(s[:10]),rho_rank_distance=corr(np.arange(n),rd),rho_similarity_distance=corr(rs,rd),score_tie_adjacent_count=len(ties),rank1_exact_tie_count=int((s==s[0]).sum()),middle_start_rank=int(r['middle'][0]+1),middle_end_rank=int(r['middle'][-1]+1))
            for margin in [.005,.01,.025,.05]:
                key=str(margin).replace('.','p');k=int((s>=s[0]-margin).sum());row['within_'+key+'_count']=k;row['within_'+key+'_proportion']=k/n
            for t in nearstats:row['cosine_gt_'+str(t)]=int((s>t).sum())
            for region,ix in r.items():row[region+'_mean_similarity']=float(s[ix].mean());row[region+'_mean_distance_m']=float(dist[ix].mean())
            for a,b in [('rank1','upper'),('upper','middle'),('middle','lower'),('rank1','lower')]:row[a+'_minus_'+b]=row[a+'_mean_similarity']-row[b+'_mean_similarity']
            rows.append(row)
            for label,p in [(str(k),k-1) for k in [1,2,5,10,11,25,50,100]]+[('midpoint',(n-1)//2),('bottom10_start',n-10),('last',n-1)]:
                selected.append(dict(query_scene_id=ids[i],mode=mode,rank_label=label,rank=p+1,candidate_scene_id=ids[o[p]],cosine=s[p],distance_m=dist[p]))
            off=offsets[mode];mm[mode][off:off+n]=scores[o];offsets[mode]+=n
            for k in range(1,5):mom[mode][k-1]+=np.sum(s**k)
            hist[mode]+=np.histogram(s,np.linspace(-1.000001,1.000001,2001))[0];pairmin[mode]=min(pairmin[mode],s[-1]);pairmax[mode]=max(pairmax[mode],s[0])
        if (i+1)%500==0:print(f'{i+1}/{nq} queries; {time.perf_counter()-started:.1f}s',flush=True)
    df=pd.DataFrame(rows);selection=pd.DataFrame(selected);summary=[]
    for mode in MODES:
        x=mm[mode][:offsets[mode]];q=np.quantile(x,PROBS,overwrite_input=True);mean=mom[mode][0]/len(x);variance=mom[mode][1]/len(x)-mean**2
        pair_summ.append(dict(mode=mode,metric='all_eligible_pair_similarity',n=len(x),mean=mean,sd=np.sqrt(max(0,variance)),**dict(zip(QN,map(float,q))),iqr=float(q[6]-q[4])))
        edges=np.linspace(-1.000001,1.000001,2001)
        pair_hist.extend(dict(mode=mode,bin_left=edges[j],bin_right=edges[j+1],count=int(v)) for j,v in enumerate(hist[mode]))
    del x;mm.clear();temps.cleanup()
    for mode,g in df.groupby('mode'):
        for col in g.select_dtypes(include=np.number):
            if col not in ['query_index','center_x','center_y','epsg']:summary.append(dict(metric=col,mode=mode,**stats(g[col])))
    # Mode-paired transition is a one-to-one ID join over ALL queries.
    st=df[df['mode']=='standard'].set_index('query_scene_id');nl=df[df['mode']=='nonlocal'].set_index('query_scene_id')
    transition=pd.DataFrame(index=st.index)
    for mode,g in [('standard',st),('nonlocal',nl)]:
        for col in ['rank1_scene_id','rank1_similarity','rank1_distance_m','eligible_count']:transition[mode+'_'+col]=g[col]
    transition['retained']=transition.standard_rank1_scene_id==transition.nonlocal_rank1_scene_id
    transition['delta_sim']=nl.rank1_similarity-st.rank1_similarity;transition['similarity_drop']=-transition.delta_sim
    transition['standard_distance_bin']=pd.cut(st.rank1_distance_m,BINS,right=False,labels=LABELS)
    csv(out,'rank1_transition_standard_to_nonlocal',transition.reset_index())
    for col in ['delta_sim','similarity_drop']:summary.append(dict(metric=col,mode='paired',**stats(transition[col])))
    for col in transition.select_dtypes(include=np.number):
        if col.startswith('nonlocal_'):summary.append(dict(metric='local_substitution_'+col,mode='paired',**stats(transition.loc[st.rank1_distance_m<2000,col])))
    correlations=[]
    for name,a,b in [('standard_similarity_delta',st.rank1_similarity,transition.delta_sim),('standard_distance_delta',st.rank1_distance_m,transition.delta_sim),('edge_proxy_nonlocal_count',nl.hull_edge_proxy_m,nl.eligible_count),('centroid_distance_nonlocal_count',nl.centroid_distance_m,nl.eligible_count)]:
        correlations.append(dict(metric=name,pearson=corr(a,b),spearman=corr(rankdata(a),rankdata(b)),n=len(a)))
    thresholds=[]
    for mode,g in df.groupby('mode'):
        for t in [.70,.75,.80,.85,.90,.95]:thresholds.append(dict(mode=mode,metric='rank1_similarity',operator='>=',threshold=t,count=int((g.rank1_similarity>=t).sum()),proportion=float((g.rank1_similarity>=t).mean())))
        for t in [250,500,750,1000,1500,2000,3000,5000,10000,15000,20000,30000]:thresholds.append(dict(mode=mode,metric='rank1_distance_m',operator='<',threshold=t,count=int((g.rank1_distance_m<t).sum()),proportion=float((g.rank1_distance_m<t).mean())))
        for col in ['rho_rank_distance','rho_similarity_distance']:
            for label,mask in [('negative',g[col]<0),('positive',g[col]>0),('near_zero_abs_le_0.05',g[col].abs()<=.05)]:thresholds.append(dict(mode=mode,metric=col,operator=label,threshold=0 if label!='near_zero_abs_le_0.05' else .05,count=int(mask.sum()),proportion=float(mask.mean())))
    for t in [0,-.01,-.025,-.05,-.10]:
        mask=transition.delta_sim==0 if t==0 else transition.delta_sim<=t;thresholds.append(dict(mode='paired',metric='delta_sim',operator='==' if t==0 else '<=',threshold=t,count=int(mask.sum()),proportion=float(mask.mean())))
    thresholds.extend([dict(mode='paired',metric='rank1_retained',operator='==',threshold=1,count=int(transition.retained.sum()),proportion=float(transition.retained.mean())),dict(mode='paired',metric='rank1_changed',operator='==',threshold=1,count=int((~transition.retained).sum()),proportion=float((~transition.retained).mean()))])
    csv(out,'threshold_proportions',thresholds);csv(out,'correlations',correlations)
    distance_rows=[];locality=[]
    for mode,g in df.groupby('mode'):
        for label in LABELS:
            mask=pd.cut(g.rank1_distance_m,BINS,right=False,labels=LABELS)==label
            distance_rows.append(dict(mode=mode,distance_bin_km=label,count=int(mask.sum()),proportion=float(mask.mean())))
    for label,mask in [(l,transition.standard_distance_bin==l) for l in LABELS]+[('local_lt_2km',st.rank1_distance_m<2000),('nonlocal_ge_2km',st.rank1_distance_m>=2000)]:
        m=np.asarray(mask);t=transition.loc[m];a=st.loc[m]
        for col,values in [('standard_rank1_similarity',a.rank1_similarity),('top1_top2_margin',a.gap_rank1_rank2),('top10_sd',a.top10_sd),('within_0p01_count',a.within_0p01_count),('delta_sim',t.delta_sim),('similarity_drop',t.similarity_drop),('nonlocal_similarity',t.nonlocal_rank1_similarity),('nonlocal_distance_m',t.nonlocal_rank1_distance_m),('nonlocal_eligible_count',t.nonlocal_eligible_count)]:locality.append(dict(group=label,metric=col,retention_rate=float(t.retained.mean()) if len(t) else None,**stats(values)))
    csv(out,'distance_bin_summary',distance_rows);csv(out,'locality_diagnostics',locality)
    boundary=[]
    for col in ['hull_edge_proxy_m','centroid_distance_m','center_x','center_y']:
        bins=pd.qcut(nl[col],5,duplicates='drop')
        for label,g in nl.groupby(bins,observed=True):boundary.append(dict(proxy=col,band=str(label),**stats(g.eligible_count)))
    csv(out,'boundary_proxy_summary',boundary)
    profile=[]
    for mode in MODES:
        arr=np.array(curves[mode]);
        for j,k in enumerate(curve_ranks):profile.append(dict(mode=mode,rank=int(k),**stats(arr[:,j])))
    csv(out,'rank_profile',profile);pq.write_table(pa.Table.from_pandas(selection,preserve_index=False),out/'selected_rank_source.parquet',compression='zstd')
    selected_summ=[]
    for (mode,label),g in selection.groupby(['mode','rank_label']):
        for metric in ['cosine','distance_m']:selected_summ.append(dict(mode=mode,rank_label=label,metric=metric,**stats(g[metric])))
    csv(out,'selected_rank_summary',selected_summ)
    region_summ=[];effect=[];regnames={'most':'rank1','top':'upper','middle':'middle','bottom':'lower'}
    active_band=band[band.query_index<=nq]
    pq.write_table(pa.Table.from_pandas(active_band,preserve_index=False),out/'rank_region_source.parquet',compression='zstd')
    for (mode,region),g in active_band.groupby(['mode','band']):
        for metric in ['cosine','distance_m']:
            region_summ.append(dict(mode=mode,region=regnames[region],metric=metric,aggregation='pooled',**stats(g[metric])))
            region_summ.append(dict(mode=mode,region=regnames[region],metric=metric,aggregation='query_mean',**stats(g.groupby('query_scene_id')[metric].mean())))
    for mode,g in df.groupby('mode'):
        for a,b in [('rank1','upper'),('upper','middle'),('middle','lower'),('rank1','lower')]:
            s=stats(g[a+'_minus_'+b]);effect.append(dict(mode=mode,contrast=a+'-'+b,standardized_paired_difference=s['mean']/s['sd'] if s['sd'] else None,**s))
    csv(out,'rank_region_summary',region_summ);csv(out,'paired_region_differences',effect)
    hubs=[];hubsummary=[];mutual=[]
    for mode in MODES:
        choices=top[mode];indegree=np.bincount(choices[:,0],minlength=N)
        for i in range(N):hubs.append(dict(mode=mode,scene_id=ids[i],rank1_indegree=int(indegree[i])))
        d=stats(indegree);z=np.sort(indegree);gini=float((2*np.sum(np.arange(1,N+1)*z)/(N*z.sum()))-(N+1)/N)
        h=dict(mode=mode,**d,gini=gini,never_selected_proportion=float((indegree==0).mean()))
        for p in [.01,.05,.10]:h['top_'+str(p)+'_selection_share']=float(z[-int(np.ceil(N*p)):].sum()/z.sum())
        for k in [1,5,10]:
            edges=sum(int(i in choices[j,:k]) for i in range(nq) for j in choices[i,:k] if j<nq)
            h['mutual_top'+str(k)+'_unordered_pairs']=edges//2;h['mutual_top'+str(k)+'_directed_edge_fraction']=edges/(nq*k)
        hubsummary.append(h)
        for i in range(nq):
            j=choices[i,0]
            if j<nq and choices[j,0]==i and i<j:mutual.append(dict(mode=mode,scene_a=ids[i],scene_b=ids[j],distance_m=float(np.linalg.norm(C[i]-C[j]))))
        mask=df['mode']==mode;df.loc[mask,'rank1_indegree']=indegree[:nq];df.loc[mask,'rank1_candidate_indegree']=indegree[choices[:,0]]
    csv(out,'hubness_summary',hubsummary);hubtable=csv(out,'scene_indegree',hubs);csv(out,'hub_top20',hubtable.sort_values(['mode','rank1_indegree','scene_id'],ascending=[True,False,True]).groupby('mode').head(20));csv(out,'mutual_rank1_pairs',mutual)
    near_summary=[]
    for t,a in nearstats.items():
        n=a['unordered_pairs'];near_summary.append(dict(threshold=t,operator='>',unordered_pairs=n,distinct_scene_pairs_orientation='lower lexical ID query only',standard_distinct_scenes=int((df[df['mode']=='standard']['cosine_gt_'+str(t)]>0).sum()),nonlocal_distinct_scenes=int((df[df['mode']=='nonlocal']['cosine_gt_'+str(t)]>0).sum()),local_pairs=a['local_pairs'],distant_pairs=n-a['local_pairs'],mean_distance_m=a['distance_sum']/n if n else None,min_distance_m=a['distance_min'] if n else None,max_distance_m=a['distance_max'] if n else None))
    csv(out,'near_duplicate_summary',near_summary);csv(out,'near_duplicate_examples',near);csv(out,'numerical_precision_probe',numeric)
    # Plot-ready exact ECDF support, histogram counts, density source is master table.
    ecdf=[];histrows=[]
    for mode,g in df.groupby('mode'):
        for col in ['rank1_similarity','rank1_distance_m','gap_rank1_rank2']:
            v,c=np.unique(g[col],return_counts=True);ecdf.extend(dict(mode=mode,metric=col,x=float(x),count=int(k),ecdf=float(y)) for x,k,y in zip(v,c,np.cumsum(c)/len(g)))
            ct,ed=np.histogram(g[col],bins=80);histrows.extend(dict(mode=mode,metric=col,left=float(ed[j]),right=float(ed[j+1]),count=int(v)) for j,v in enumerate(ct))
    v,c=np.unique(transition.delta_sim,return_counts=True);ecdf.extend(dict(mode='paired',metric='delta_sim',x=float(x),count=int(k),ecdf=float(y)) for x,k,y in zip(v,c,np.cumsum(c)/len(transition)))
    ct,ed=np.histogram(transition.delta_sim,bins=80);histrows.extend(dict(mode='paired',metric='delta_sim',left=float(ed[j]),right=float(ed[j+1]),count=int(v)) for j,v in enumerate(ct))
    csv(out,'ecdf_points',ecdf);csv(out,'histogram_counts',histrows);csv(out,'all_pair_similarity_summary',pair_summ);csv(out,'all_pair_histogram',pair_hist)
    csv(out,'summary_statistics',summary+pair_summ)
    csv(out,'candidate_count_distribution',df.groupby(['mode','eligible_count']).size().rename('query_count').reset_index())
    # Wide spatial CSV/Parquet preserves original projected centers; explicit CRS sidecar.
    master=df.merge(transition[['delta_sim','similarity_drop','retained']].reset_index(),on='query_scene_id',validate='many_to_one')
    csv(out,'master_query_table',master);pq.write_table(pa.Table.from_pandas(master,preserve_index=False),out/'master_query_table.parquet',compression='zstd')
    jsonout(out/'spatial_metadata.json',dict(crs='EPSG:5186',geometry='point',x='center_x',y='center_y',distance='Euclidean projected meters',source=source['gallery'],note='CSV/Parquet coordinate table, not GeoParquet; no reprojection or external labels. Hull is sample-center support proxy, not administrative boundary.'))
    inventory=[]
    for mode,g in master.groupby('mode'):
        for col in ['rank1_similarity','rank1_distance_m','gap_rank1_rank2','rank1_candidate_indegree']:
            for ascending in [True,False]:
                z=g.sort_values([col,'query_scene_id'],ascending=[ascending,True]).head(20)
                for _,r in z.iterrows():inventory.append(dict(category=mode+'_'+col+('_lowest' if ascending else '_highest'),**r.to_dict()))
        for _,r in g[g.rank1_distance_m>=10000].sort_values(['rank1_similarity','query_scene_id'],ascending=[False,True]).head(20).iterrows():inventory.append(dict(category=mode+'_distant_ge10km_high_similarity',**r.to_dict()))
        mutual_ids={p['scene_a'] for p in mutual if p['mode']==mode}|{p['scene_b'] for p in mutual if p['mode']==mode}
        for _,r in g[g.query_scene_id.isin(mutual_ids)].sort_values('query_scene_id').head(20).iterrows():inventory.append(dict(category=mode+'_mutual_rank1',**r.to_dict()))
    g=master[master['mode']=='standard']
    for ascending in [True,False]:
        for _,r in g.sort_values(['similarity_drop','query_scene_id'],ascending=[ascending,True]).head(20).iterrows():inventory.append(dict(category='similarity_drop_'+('smallest' if ascending else 'largest'),**r.to_dict()))
    csv(out,'extreme_query_inventory',inventory)
    # Every tested invariant gets a named numerical failure count.
    for name,value in global_fail.items():checks.append(dict(check=name,failures=value,status='PASS' if value==0 else 'FAIL',tolerance=0))
    for name,value,tol in [('nonlocal_rank1_increase',int((transition.delta_sim>TOL).sum()),TOL),('already_nonlocal_changed_id',int(((st.rank1_distance_m>=2000)&(~transition.retained)).sum()),0),('already_nonlocal_changed_similarity',int(((st.rank1_distance_m>=2000)&(transition.delta_sim!=0)).sum()),0),('population_coverage',int(not args.pilot and (len(master)!=18000 or any(master.groupby('mode').query_scene_id.nunique()!=9000))),0),('embedding_nonfinite',int((~np.isfinite(X)).sum()),0),('zero_norm',int((np.linalg.norm(X,axis=1)==0).sum()),0),('norm_tolerance',int((np.abs(np.linalg.norm(X,axis=1)-1)>2e-6).sum()),2e-6),('duplicate_scene_ids',N-len(set(ids)),0),('source_bytes_mutated',sum(sha(p)!=h for p,h in snapshots.items()),0),('coordinate_source_binding',0,0),('selected_checkpoint_binding',0,0)]:checks.append(dict(check=name,failures=value,status='PASS' if value==0 else 'FAIL',tolerance=tol))
    csv(out,'invariant_checks',checks)
    plots(out,master,transition,pd.DataFrame(profile),pd.DataFrame(region_summ),hubtable)
    jsonout(out/'source_checksums_before.json',snapshots)
    info.update(source_paths=source,source_checksums=snapshots,branch=subprocess.check_output(['git','branch','--show-current'],cwd=REPO,text=True).strip(),git_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),dissertation_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=diss,text=True).strip(),query_count=nq,modes=MODES,matched_band_records=matched_bands,matched_legacy_records=matched_old,exact_boundary_directed_pairs=exact_boundary,distinct_directed_scores_gt_one=greater_one,max_distance_m=maxdistance,duplicate_embedding_extra_rows=int((dupcounts-1).sum()),duplicate_embedding_groups=int((dupcounts>1).sum()),repeated_source_shard_hash_extra_rows=N-len({g['source_payload_sha256'] for g in gallery}),versions={m:__import__(m).__version__ for m in ['numpy','pandas','scipy','pyarrow','matplotlib']},blas=threadpool_info(),threads=1,worker_processes=1,gpu=False,elapsed_seconds=time.perf_counter()-started,started_at=started_at,pilot=bool(args.pilot),all_invariants_pass=all(c['status']=='PASS' for c in checks),raw_positive_delta_count=int((transition.delta_sim>0).sum()))
    jsonout(out/'audit_manifest.json',info)
    jsonout(out/'output_checksums.json',{str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.is_file()})
    print('COMPLETE',out,info['elapsed_seconds'],'seconds',info['all_invariants_pass'],flush=True)
    assert info['all_invariants_pass'],'Invariant failure: inspect report before use'

def plots(out,df,tr,profile,regionsummary,hubs):
    root=out/'figures';plt.rcParams.update({'font.size':10,'figure.dpi':120})
    def save(name,title):
        plt.suptitle(title+'\nExploratory candidate — not final dissertation figure',fontsize=11);plt.tight_layout();plt.savefig(root/(name+'.png'),dpi=160);plt.savefig(root/(name+'.pdf'));plt.close()
    colors={'standard':'#2864A0','nonlocal':'#CC6633'}
    plt.figure(figsize=(7,4))
    for m,g in df.groupby('mode'):plt.hist(g.rank1_similarity,bins=np.linspace(float(df.rank1_similarity.min())-.001,1.001,80),density=True,histtype='step',label=m,color=colors[m])
    plt.xlabel('Rank-1 cosine similarity');plt.ylabel('Density');plt.legend();save('01_rank1_similarity','Rank-1 similarity')
    plt.figure(figsize=(7,4))
    for m,g in df.groupby('mode'):
        x=np.sort(g.rank1_distance_km);plt.step(x,np.arange(1,len(x)+1)/len(x),where='post',label=m)
    plt.axvline(2,color='grey',ls='--');plt.xlabel('Rank-1 center distance (km)');plt.ylabel('ECDF');plt.legend();save('02_distance_ecdf','Rank-1 geographic distance')
    plt.figure(figsize=(7,4));x=df[df['mode']=='standard'].rank1_distance_m;plt.hist(x,bins=np.geomspace(max(x.min(),.01),x.max(),65));plt.xscale('log');plt.xlabel('Standard Rank-1 distance (m; logarithmic bins)');plt.ylabel('Queries');save('03_distance_histogram','Standard distance distribution')
    plt.figure(figsize=(7,4));plt.hist(tr.delta_sim,bins=80);plt.xlabel('Non-local − Standard Rank-1 cosine');plt.ylabel('Queries');save('04_similarity_drop','Change after Non-local exclusion')
    fig,ax=plt.subplots(1,2,figsize=(11,4));cats=tr.standard_distance_bin
    for a,col in zip(ax,['standard_rank1_similarity','similarity_drop']):
        vals=[tr.loc[cats==l,col].to_numpy() for l in LABELS];a.boxplot(vals,showfliers=False);a.set_xticks(range(1,11),LABELS,rotation=65);a.set_ylabel(col);a.set_xlabel('Standard Rank-1 distance band (km)')
    save('05_locality_bands','Similarity and drop by locality')
    plt.figure(figsize=(7,4))
    for m,g in profile.groupby('mode'):plt.plot(g['rank'],g['mean'],label=m)
    plt.xscale('log');plt.xlabel('Rank (log scale)');plt.ylabel('Mean cosine similarity');plt.legend();save('06_rank_profile','Similarity across eligible rankings')
    plt.figure(figsize=(7,4));reg=['rank1','upper','middle','lower']
    for m in MODES:
        g=regionsummary[(regionsummary['mode']==m)&(regionsummary.metric=='cosine')&(regionsummary.aggregation=='query_mean')].set_index('region').loc[reg];plt.errorbar(reg,g['median'],yerr=[g['median']-g.p25,g.p75-g['median']],label=m,marker='o',capsize=4)
    plt.ylabel('Query region mean cosine: median and IQR');plt.legend();save('07_rank_regions','Four rank regions')
    plt.figure(figsize=(7,4))
    for m,g in df.groupby('mode'):plt.hist(g.gap_rank1_rank2,bins=80,histtype='step',label=m,density=True)
    plt.xlabel('Rank1 − Rank2 cosine margin');plt.ylabel('Density');plt.legend();save('08_top1_top2_margin','Nearest-neighbor ambiguity')
    plt.figure(figsize=(7,4))
    for m,g in hubs.groupby('mode'):
        x=g.rank1_indegree.value_counts().sort_index();plt.plot(x.index,x.values,marker='o',label=m)
    plt.yscale('log');plt.xlabel('Rank-1 indegree');plt.ylabel('Scenes (log scale)');plt.legend();save('09_hubness','Rank-1 selection concentration')
    fig,ax=plt.subplots(1,2,figsize=(11,4))
    for a,m in zip(ax,MODES):
        g=df[df['mode']==m];h=a.hexbin(g.rank1_distance_km,g.rank1_similarity,gridsize=45,mincnt=1,bins='log');a.set_title(m);a.set_xlabel('Rank-1 distance (km)');a.set_ylabel('Rank-1 cosine');fig.colorbar(h,ax=a,label='Query count')
    save('10_distance_similarity','Distance and similarity')
    fig,ax=plt.subplots(2,2,figsize=(10,9));g=df[df['mode']=='standard']
    for a,col in zip(ax.flat,['rank1_similarity','rank1_distance_km','similarity_drop','rank1_indegree']):
        h=a.scatter(g.center_x,g.center_y,c=g[col],s=3,cmap='viridis');a.set_aspect('equal');a.set_title(col);a.set_xlabel('EPSG:5186 easting (m)');a.set_ylabel('Northing (m)');fig.colorbar(h,ax=a)
    save('11_spatial_query_statistics','Query-center spatial exports')

if __name__=='__main__':main()
