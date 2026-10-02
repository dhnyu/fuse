"""Post-selection paired diagnostics. Never selects checkpoints or changes inputs."""
from pathlib import Path
import json
import numpy as np
import torch
import pyarrow as pa
import pyarrow.parquet as pq
from b6_formal_training import read, sha256_file, immutable_json, checked_path, ARMS, CACHE_ROOT
from training_finalization import evaluate_selection_candidate, qualifies_patience_reset

DESCRIPTORS=Path('/mnt/hdd002/dhnyu/fusedata/analysis_data/reduced/s11_representation/df3b397b64b6aeebde547b2e')
STATISTICS=Path('/mnt/hdd002/dhnyu/fusedata/scene_data/reduced/observations/obs_ee28248872c4ab0ce8b3ea4f/production/acceptance/bsa_bd504b7e871945a5a6207664/scene_spatial_statistics.parquet')
KEYS=['retrieval_loss','margin','MRR','HIT@1','HIT@5','HIT@10']


def query_metrics(vectors, temperature=.1):
    sim=vectors[:2000]@vectors[2000:].T; positive=torch.arange(1000).repeat_interleave(2)
    loss=torch.nn.functional.cross_entropy(sim/temperature,positive,reduction='none')
    rank=(torch.argsort(sim,dim=1,descending=True,stable=True)==positive[:,None]).nonzero()[:,1]+1
    pos=sim[torch.arange(2000),positive]; sim[torch.arange(2000),positive]=-torch.inf
    return torch.stack([loss,pos-sim.max(1).values,1/rank.float(),(rank<=1).float(),(rank<=5).float(),(rank<=10).float()],1).numpy()


def grouped_bootstrap(delta, indices, seed, repeats):
    """Mean paired differences; the two views of every scene stay together."""
    if not len(indices): return None
    values=delta.reshape(-1,2,delta.shape[1]).mean(1)[indices]
    rng=np.random.default_rng(seed)
    boot=np.stack([values[rng.integers(0,len(values),len(values))].mean(0) for _ in range(repeats)])
    return {key:{'difference':float(values[:,i].mean()),'ci95':np.quantile(boot[:,i],[.025,.975]).tolist()} for i,key in enumerate(KEYS)}


def masks(counts,lengths):
    return {'whole':np.ones(len(counts),bool),'road_nonempty':counts>0,'zero_road':counts==0,
        'count_1_8':(counts>=1)&(counts<=8),'count_9_49':(counts>=9)&(counts<=49),'count_50_plus':counts>=50,
        **{f'length_{lo}_{hi}':(counts>0)&(lengths>=lo)&(lengths<hi) for lo,hi in [(0,50),(50,100),(100,250),(250,500),(500,np.inf)]}}


def replay(out,c):
    best=None;patience=0;rows=[]
    for path in sorted(out.glob('boundary-*.json')):
        row=read(path); metric=row['metric']
        selected,basis=evaluate_selection_candidate(metric,best,1e-4)
        reset=qualifies_patience_reset(metric,best,1e-4);patience=0 if reset else patience+1
        assert row['selected']==selected and row['basis']==basis and row['patience']==patience
        assert sha256_file(out/row['checkpoint'])==row['checkpoint_sha256']
        assert sha256_file(out/f"validation-{row['epoch']:03d}.pt")==row['validation_sha256']
        ck=torch.load(out/row['checkpoint'],map_location='cpu',weights_only=False)
        assert ck['progress']['global_update']==76*row['epoch'] and ck['world_size']==2
        assert ck['run_identity']==read(out/'authority.json')['authority_id']
        assert ck['configuration_identity']==read(out/'authority.json')['configuration_hash']
        if selected:best=metric
        rows.append(row)
    completion=read(out/'completion.json')
    assert best['completed_epoch']==completion['selected']['completed_epoch']
    assert completion['completed_epoch']==rows[-1]['epoch']
    assert completion['reason']=='EARLY_STOPPING_PATIENCE' and patience==4 or completion['completed_epoch']==200
    return completion,rows


def summarize(root):
    root=checked_path(root);c=read(root/'contract.json');dest=root/'comparison'
    if dest.exists():
        for row in read(dest/'manifest.json')['files']:assert sha256_file(dest/row['path'])==row['sha256']
        return dest/'acceptance.json'
    # Fixed original-parent descriptors; no child-derived substitutions.
    paths=[root/'validation_descriptors/descriptors.json']
    desc={r['scene_id']:r for r in read(paths[0])}
    counts={r['scene_id']:r['road_count'] for r in pq.read_table(STATISTICS,columns=['scene_id','road_count']).to_pylist()}
    results={};arrays={};perf={};identities={};scenes=None
    for arm in ARMS:
        out=root/arm;completion,boundaries=replay(out,c)
        epoch=completion['selected']['completed_epoch']
        data=torch.load(out/f'validation-{epoch:03d}.pt',map_location='cpu',weights_only=False)
        if scenes is None:scenes=data['scene_ids']
        assert scenes==data['scene_ids'] and len(scenes)==1000
        arr=query_metrics(data['vectors']); arrays[arm]=arr
        metric=completion['selected']; mean=arr.mean(0)
        expected=[metric['validation_retrieval_loss'],metric['mean_source_separation_margin'],metric['MRR'],metric['HIT@1'],metric['HIT@5'],metric['HIT@10']]
        assert np.allclose(mean,expected,atol=2e-6,rtol=0)
        road_counts=np.array([counts[s] for s in scenes]);lengths=np.array([desc[s]['mean_road_segment_length'] or 0 for s in scenes])
        panels=masks(road_counts,lengths)
        subset={name:{'scenes':int(mask.sum()),'queries':int(mask.sum()*2),
            'metrics':dict(zip(KEYS,map(float,arr[np.repeat(mask,2)].mean(0)))) if mask.any() else None} for name,mask in panels.items()}
        zero=torch.tensor(np.flatnonzero(road_counts==0));zero_gallery=data['vectors'][2000:][zero];zero_queries=data['vectors'][:2000].reshape(1000,2,256)[zero].reshape(-1,256)
        assert len(zero)==144
        # FP batch-kernel noise is reported separately from exact tied ranking.
        zero_diag={'scenes':len(zero),'gallery_unique_bitwise':len(torch.unique(zero_gallery,dim=0)),
            'query_unique_bitwise':len(torch.unique(zero_queries,dim=0)),
            'max_gallery_absolute_difference':float((zero_gallery-zero_gallery[0]).abs().max()),
            'max_query_absolute_difference':float((zero_queries-zero_queries[0]).abs().max()),
            'HIT1_ceiling':.857}
        if mean[3]>.857+1e-6:raise ValueError('HIT1 CEILING EXCEEDED: population/input/leakage audit required')
        byepoch={}
        for p in sorted(out.glob('performance-*.json')):
            value=read(p); ep=value['ranks'][0]['epoch']
            # With recovery, independently preserve attempts and use final complete trace.
            byepoch[ep]=value
        assert set(byepoch)==set(range(1,completion['completed_epoch']+1))
        rows=[r for e in sorted(byepoch) for r in byepoch[e]['ranks']]
        perf[arm]=byepoch
        runtime={'training_epoch_seconds':sum(max(r['seconds'] for r in byepoch[e]['ranks']) for e in byepoch),
            'validation_and_checkpoint_seconds':sum(b['validation_seconds'] for b in boundaries),
            'peak_allocated':max(r['peak_allocated'] for r in rows),'peak_reserved':max(r['peak_reserved'] for r in rows),
            'peak_rss':max(r['peak_rss'] for r in rows),'assembly_seconds_p50_p95_max':np.quantile([v['assembly_seconds'] for r in rows for v in r['loads']],[.5,.95,1]).tolist(),
            'entity_rows_per_rank_batch_mean':float(np.mean([v['entity_rows'] for r in rows for v in r['loads']])),
            'relation_rows_per_rank_batch_mean':float(np.mean([v['relation_rows'] for r in rows for v in r['loads']])),
            'update_seconds_p50_p95_max':np.quantile([t for r in rows for t in r['update_seconds']],[.5,.95,1]).tolist()}
        mech=data['mechanistic'][2000:]
        mechanism={k:float(np.mean([r[k] for r in mech if r[k] is not None])) for k in ['entities','attention_effective_entities','attention_max','position_dispersion_m','parent_attention_max','parent_attention_effective']}
        mechanism['gate_mean']=np.mean([r['gate_mean'] for r in mech if r['gate_mean'] is not None],axis=0).tolist()
        results[arm]={'completion':completion,'subsets':subset,'zero_road':zero_diag,'resources':runtime,'mechanistic_gallery':mechanism}
        identities[arm]=completion['initial_model_hash']
    assert len(set(identities.values()))==1
    for left,right in [(ARMS[0],ARMS[1]),(ARMS[0],ARMS[2]),(ARMS[1],ARMS[2])]:
        for epoch in sorted(set(perf[left])&set(perf[right])):
            for rank in range(2):
                a=perf[left][epoch]['ranks'][rank]['alignment'];b=perf[right][epoch]['ranks'][rank]['alignment']
                assert [r['batch'] for r in a]==[r['batch'] for r in b]
                assert [r['queue'] for r in a]==[r['queue'] for r in b]
                if left==ARMS[1]:assert [r['mask'] for r in a]==[r['mask'] for r in b]
    bootstrap={}
    for left,right in [(ARMS[1],ARMS[0]),(ARMS[2],ARMS[0]),(ARMS[2],ARMS[1])]:
        bootstrap[f'{left} minus {right}']={name:grouped_bootstrap(arrays[left]-arrays[right],np.flatnonzero(mask),c['settings']['bootstrap_seed'],c['settings']['bootstrap_replicates']) for name,mask in panels.items()}
    # Interpretation is deliberately metric-by-metric, not an aggregate ranking.
    primary=[bootstrap[f'{a} minus {ARMS[0]}']['road_nonempty'] for a in ARMS[1:]]
    improves=[x['retrieval_loss']['ci95'][1]<0 and x['margin']['difference']>0 for x in primary]
    verdict=('EVIDENCE_SUPPORTS_GRANULARITY_HYPOTHESIS' if all(improves) else
             'EVIDENCE_SUGGESTS_SIBLING_RELATION_EFFECT' if improves==[True,False] else
             'NO_EVIDENCE_OF_GRANULARITY_BENEFIT' if all(x['retrieval_loss']['difference']>=0 and x['margin']['difference']<=0 for x in primary) else 'EVIDENCE_MIXED')
    # Keep structural diagnostics separate from external descriptors.
    cache=CACHE_ROOT/c['input_contract']['design_id']/'prepared'
    entries=[r for r in read(cache/'manifest.json')['entries'] if r['role']=='validation_gallery']
    structural=read(root/'validation_descriptors/structural.json')
    import tempfile
    stage=Path(tempfile.mkdtemp(prefix='.comparison-',dir=root))
    immutable_json(stage/'results.json',{'arms':results,'bootstrap':bootstrap,'verdict':verdict,
        'interpretation_rule':'road-nonempty paired loss CI and signed margin reported together; no aggregate score',
        'seed_masking_alignment':True,'limits':['single training seed','bootstrap covers scenes, not training seed uncertainty',
            'length strata use scene mean original-parent length; bins left-closed right-open']})
    immutable_json(stage/'original_descriptors.json',{'source_checksums':{str(p):sha256_file(p) for p in paths},'rows':[desc[s] for s in scenes]})
    immutable_json(stage/'structural_panel.json',structural)
    for arm in ARMS:
        table=pa.table({'scene_id':np.repeat(scenes,2),'query_view':np.tile([0,1],1000),**{k:arrays[arm][:,i] for i,k in enumerate(KEYS)}})
        pq.write_table(table,stage/f'{arm}-queries.parquet')
    immutable_json(stage/'acceptance.json',{'status':'PASS','verdict':verdict,'arms_completed':3,'selection_replayed':True,
        'checkpoint_readback':True,'fixed_gallery':1000,'queries':2000,'alignment':True,'canonical_mutation':False,
        'authorities':{arm:read(root/arm/'authority.json')['authority_id'] for arm in ARMS}})
    immutable_json(stage/'manifest.json',{'files':[{'path':p.name,'sha256':sha256_file(p)} for p in sorted(stage.iterdir())]})
    stage.rename(dest)
    return dest/'acceptance.json'
