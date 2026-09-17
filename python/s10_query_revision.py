"""New S10 qualitative policy; dissertation sec:spatial-scene-retrieval.

Authorized 100-query extension, independent of the immutable 30-query contract.
Object population follows sec:overview / def-geospatial-entity: |B|+|R|+|P|.
Only accepted original P3 records and normalized parent embeddings are read.
No checkpoint, model inference, training, or S11 execution dependency.
"""
from collections import Counter
import io
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import time

import numpy as np
import pyarrow.parquet as pq
import pyarrow as pa
from threadpoolctl import threadpool_limits
from retrieval_artifacts import load, read_json, file_hash, digest, encoded, publish, require, output_paths
from retrieval_ranking import sample_queries, rank, check_embeddings, OFAT, COMPARISON

ROOT = Path(__file__).resolve().parents[1]
DEFINITION = 'object_count = |B^(l)| + |R^(l)| + |P^(l)|; unique accepted P3 original observed entity rows, before model-family projection; not geometry parts, topology nodes, or raster cells'
SOURCES = ['python/s10_query_revision.py', 'python/s10_query_viewer.py', 'python/retrieval_artifacts.py',
           'python/retrieval_ranking.py', 'scripts/s10_query_revision.py', 'R/s10_query_revision.R',
           'targets/s10_query_revision.R', '_targets_s10_query_revision.R', 'config/s10_query_revision.json',
           'tools/retrieval_inspector/supplemental/bands.py']


def select_queries(rows, counts, seed, count=100, maximum_sparse=5, threshold=10):
    """Sort IDs; one PCG64 stream draws sparse first, regular second; preserve draw order."""
    rows = sorted(rows, key=lambda r: r['scene_id'])
    ids = [r['scene_id'] for r in rows]
    require(len(ids) == len(set(ids)) and set(ids) == set(counts), 'REVISION_POPULATION')
    require(all(isinstance(counts[s]['object_count'], int) and counts[s]['object_count'] >= 0 for s in ids), 'OBJECT_COUNT')
    sparse = [r for r in rows if counts[r['scene_id']]['object_count'] < threshold]
    regular = [r for r in rows if counts[r['scene_id']]['object_count'] >= threshold]
    ns = min(maximum_sparse, len(sparse))
    require(0 <= ns <= count and len(regular) >= count-ns, 'REGULAR_SHORTAGE')
    rng = np.random.Generator(np.random.PCG64(seed))
    selected = [sparse[int(i)] for i in rng.choice(len(sparse), ns, replace=False)]
    selected += [regular[int(i)] for i in rng.choice(len(regular), count-ns, replace=False)]
    return [{**r, **counts[r['scene_id']], 'query_index': i+1, 'sampling_seed': seed} for i,r in enumerate(selected)]


def statistics(rows, counts):
    x = np.array([counts[r['scene_id']]['object_count'] for r in rows])
    return {'n':len(x), 'min':int(x.min()), 'median':float(np.median(x)), 'mean':float(x.mean()),
            **{f'p{p}':float(np.percentile(x,p)) for p in (10,25,75,90)}, 'max':int(x.max()),
            'zero':int((x==0).sum()), 'lt5':int((x<5).sum()), 'lt10':int((x<10).sum()), 'ge10':int((x>=10).sum()),
            'regular_bins':{label:int(((x>=lo)&(x<hi)).sum()) for label,lo,hi in
              [('10–24',10,25),('25–49',25,50),('50–99',50,100),('100–249',100,250),('>=250',250,np.inf)]}}


def settings(path):
    cfg = read_json(path)
    require((cfg['query_count'],cfg['gallery_count'],cfg['model_count'],cfg['sparse_threshold'],cfg['max_sparse_queries'],cfg['top_k'],cfg['threads']) == (100,9000,28,10,5,50,1), 'REVISION_CONTRACT')
    require(cfg['policy']=='s10-100-query-sparse-v1' and cfg['selection_seed']==20260916, 'REVISION_POLICY')
    return cfg


def parents(cfg):
    root = Path(cfg['parent_generation'])
    a = load(root/'acceptance.json','acceptance')
    require(a['artifact_id']==cfg['parent_acceptance_id'] and a['body']['status']=='PASS', 'REVISION_PARENT')
    docs=[]
    for name,kind in [('model_manifest.json','models'),('gallery_manifest.json','gallery'),('query_manifest.json','queries')]:
        d=load(root/name,kind);require(a['body']['artifacts'].get(str(root/name))==d['artifact_id'], 'PARENT_ACCEPTED_ID');docs.append(d)
    m,g,q=docs
    require(len(m['body']['models'])==28 and len(g['body']['rows'])==9000, 'PARENT_COUNTS')
    require([r['configuration_id'] for r in m['body']['models']]==list(OFAT)+['cmp_'+n for n in COMPARISON], 'PARENT_MODELS')
    require(q['body']['rows']==sample_queries(g['body']['rows'],20260916), 'PARENT_QUERY_SELECTION')
    require(all(r['split']=='evaluation' and r['epsg']==5186 for r in g['body']['rows']), 'EVALUATION_ONLY')
    require(g['body']['model_manifest_id']==m['artifact_id'] and q['body']['gallery_manifest_id']==g['artifact_id'] and q['body']['model_manifest_id']==m['artifact_id'], 'PARENT_BINDINGS')
    return root,a,m,g,q


def identity(cfg):
    code={p:file_hash(ROOT/p) for p in SOURCES}
    runtime={'code':code,'numpy':np.__version__,'pyarrow':pa.__version__, 'threads':1}
    rid=digest(runtime)
    gid='s10gen_'+digest({'config':cfg,'runtime':runtime})[:24]
    return {'generation_id':gid,'runtime_id':rid,'scope':'formal'},runtime


def count_population(cfg):
    root,a,m,g,q=parents(cfg)
    ip=next(Path(p) for p in m['body']['config']['source_pins'] if p.endswith('/scene_to_shard.parquet'))
    require(file_hash(ip)==m['body']['config']['source_pins'][str(ip)],'P3_INDEX_HASH')
    index={r['scene_id']:r for r in pq.read_table(ip).to_pylist()}
    counts={r['scene_id']:{} for r in g['body']['rows']};groups={};sources={str(ip):file_hash(ip)}
    for r in g['body']['rows']:
        p=index[r['scene_id']]
        require(p['cache_id']==m['body']['parents']['scene_cache_id'] and p['payload_sha256']==r['source_payload_sha256'],'P3_GALLERY_BINDING')
        groups.setdefault(p['branch_id'],[]).append(r['scene_id'])
    for branch,sids in sorted(groups.items()):
        first=index[sids[0]];path=Path(m['body']['roots']['p3'])/'shards'/branch/first['payload_filename']
        require(all(index[s]['payload_sha256']==first['payload_sha256'] for s in sids) and file_hash(path)==first['payload_sha256'],'P3_PAYLOAD_HASH')
        sources[str(path)]=first['payload_sha256'];local={s:[] for s in sids}
        with tarfile.open(path) as archive:
            for key,name in [('n_buildings','building'),('n_roads','road'),('n_pois','poi')]:
                with archive.extractfile(f'vector/{name}_observed.parquet') as f:
                    table=pq.read_table(io.BytesIO(f.read()),columns=['scene_id','local_entity_id','source_entity_id','split'])
                rows=[r for r in table.to_pylist() if r['scene_id'] in local]
                require(all(r['split']=='evaluation' for r in rows),'P3_SPLIT')
                keys=[(r['scene_id'],r['source_entity_id']) for r in rows]
                require(len(keys)==len(set(keys)),'P3_DUPLICATE_ENTITY')
                frequencies=Counter(r['scene_id'] for r in rows)
                for r in rows:local[r['scene_id']].append(r['local_entity_id'])
                for s in sids:counts[s][key]=frequencies[s]
        for s,keys in local.items():
            require(sorted(keys)==list(range(len(keys))),'P3_LOCAL_ENTITY_POPULATION')
            counts[s]['object_count']=sum(counts[s].values())
    return counts,sources


def audit(config_path):
    cfg=settings(config_path);root,a,m,g,q=parents(cfg);ctx,runtime=identity(cfg)
    counts,sources=count_population(cfg)
    chosen=select_queries(g['body']['rows'],counts,cfg['selection_seed'])
    body={**ctx,'policy':cfg['policy'],'runtime':runtime,'parent_acceptance_id':a['artifact_id'],
          'gallery_manifest_id':g['artifact_id'],'object_count_definition':DEFINITION,'counts':counts,
          'source_checksums':sources,'gallery_statistics':statistics(g['body']['rows'],counts),
          'old_query_statistics':statistics(q['body']['rows'],counts),'selected_statistics':statistics(chosen,counts),
          'old_new_overlap':sorted({r['scene_id'] for r in chosen}&{r['scene_id'] for r in q['body']['rows']})}
    return publish(Path(cfg['publication_root'])/ctx['generation_id']/'object_counts_manifest.json','summary',body)


def verified_embedding(root,a,m,g,q,model):
    mid=model['configuration_id'];rp=root/'rankings'/mid/'manifest.json';r=load(rp,'rankings')
    require(a['body']['artifacts'].get(str(rp))==r['artifact_id'],'ACCEPTED_RANKING')
    ep=Path(r['body']['embedding_manifest']);e=load(ep,'embeddings')
    require(e['artifact_id']==r['body']['embedding_manifest_id'] and e['body']['model']==model,'ACCEPTED_EMBEDDING')
    require(e['body']['scene_ids']==[x['scene_id'] for x in g['body']['rows']], 'EMBEDDING_POPULATION')
    for key,d in [('query_manifest_id',q),('gallery_manifest_id',g),('model_manifest_id',m)]:
        require(e['body'][key]==r['body'][key]==d['artifact_id'],'PARENT_EMBEDDING_BINDING')
    require(e['body']['generation_id']==m['body']['generation_id'] and e['body']['runtime_id']==m['body']['runtime_id'], 'PARENT_EMBEDDING_RUNTIME')
    v=np.load(ep.parent/e['files'][0]['path'],allow_pickle=False);check_embeddings(v,9000)
    require(v.dtype==np.float32,'EMBEDDING_DTYPE')
    return ep,e,v


def generation(config_path,counts_path):
    cfg=settings(config_path);root,a,m,g,oldq=parents(cfg);ctx,runtime=identity(cfg)
    c=load(counts_path,'summary');require(all(c['body'][k]==v for k,v in ctx.items()),'COUNTS_RUNTIME')
    # Recompute canonical counts at acceptance, rather than trusting an arbitrary display count.
    counts,sources=count_population(cfg)
    require(counts==c['body']['counts'] and sources==c['body']['source_checksums'] and c['body']['object_count_definition']==DEFINITION, 'REPRODUCIBLE_OBJECT_COUNTS')
    queries=select_queries(g['body']['rows'],counts,cfg['selection_seed'])
    require(queries==select_queries(list(reversed(g['body']['rows'])),counts,cfg['selection_seed']), 'DETERMINISTIC_SELECTION')
    out=Path(cfg['publication_root'])/ctx['generation_id'];qpath=out/'query_manifest.json'
    n_sparse=sum(r['object_count']<10 for r in queries)
    require(len(queries)==len({r['scene_id'] for r in queries})==100 and n_sparse<=5,'QUERY_COMPOSITION')
    publish(qpath,'queries',{**ctx,'policy':cfg['policy'],'parent_acceptance_id':a['artifact_id'],
        'model_manifest_id':m['artifact_id'],'gallery_manifest_id':g['artifact_id'],'object_counts_manifest_id':c['artifact_id'],
        'query_count':100,'selection_seed':cfg['selection_seed'],'population':'accepted evaluation 9000',
        'sampling_without_replacement':True,'object_count_definition':DEFINITION,'sparse_threshold':10,'max_sparse_queries':5,
        'actual_sparse_queries':n_sparse,'actual_regular_queries':100-n_sparse,
        'algorithm':'PCG64; lexical scene_id within strata; sparse draw then regular draw; preserve draw order',
        'source_manifest_ids':{'p3':g['body']['source'],'parent_query':oldq['artifact_id'],'parent_acceptance':a['artifact_id']},
        'source_checksums':{**sources, str(root/'acceptance.json'):file_hash(root/'acceptance.json'),str(root/'gallery_manifest.json'):file_hash(root/'gallery_manifest.json')},
        'rows':queries})
    q=load(qpath,'queries');bindings={**ctx,'model_manifest_id':m['artifact_id'],'gallery_manifest_id':g['artifact_id'],'query_manifest_id':q['artifact_id']}
    artifacts={str(root/'model_manifest.json'):m['artifact_id'],str(root/'gallery_manifest.json'):g['artifact_id'],str(qpath):q['artifact_id'],str(counts_path):c['artifact_id']}
    embeddings={};total=0
    for model in m['body']['models']:
        ep,e,v=verified_embedding(root,a,m,g,oldq,model);mid=model['configuration_id']
        with threadpool_limits(limits=1):rows=rank(v,g['body']['rows'],queries,model,bindings)
        rp=out/'rankings'/mid/'manifest.json';rp.parent.mkdir(parents=True,exist_ok=True)
        buffer=pa.BufferOutputStream();pq.write_table(pa.Table.from_pylist(rows),buffer,compression='zstd')
        from retrieval_artifacts import publish_bytes
        payload=publish_bytes(rp.parent/'rankings.parquet',buffer.getvalue().to_pybytes())
        publish(rp,'rankings',{**bindings,'model':model,'rows':len(rows),'top_k':50,
                'embedding_manifest':str(ep),'embedding_manifest_id':e['artifact_id'],
                'embedding_parent_acceptance_id':a['artifact_id'],'reuse_policy':'verify original parent bindings; never rebind embedding manifests'},[payload])
        actual=pq.read_table(payload).to_pylist()
        with threadpool_limits(limits=1):expected=rank(v,g['body']['rows'],queries,model,bindings)
        require(actual==expected and len(actual)==10000,'DETERMINISTIC_RANKING_READBACK')
        artifacts[str(rp)]=load(rp,'rankings')['artifact_id'];total+=len(actual)
        embeddings[mid]={'path':str(ep),'id':e['artifact_id'],'sha256':file_hash(ep),'payload_sha256':e['files'][0]['sha256']}
        print('Ranking/readback PASS '+mid, file=sys.stderr,flush=True)
    require(total==280000,'FORMAL_ROW_COUNT')
    require(identity(cfg)==(ctx,runtime),'REVISION_SOURCE_CHANGED')
    require(all(file_hash(p)==h for p,h in sources.items()),'P3_SOURCE_CHANGED')
    return publish(out/'acceptance.json','acceptance',{**bindings,'policy':cfg['policy'],'status':'PASS',
        'parent_acceptance_id':a['artifact_id'],'parent_acceptance_path':str(root/'acceptance.json'),
        'parent_acceptance_sha256':file_hash(root/'acceptance.json'),'artifacts':artifacts,
        'runtime':runtime,'embedding_reuse':embeddings,'row_count':total,'query_count':100,'gallery_count':9000,'model_count':28,
        'checks':{'canonical_counts_recomputed':True,'deterministic_sampling':True,'deterministic_ranking_readback':True,
                  'unchanged_gallery_centers':True,'evaluation_only':True,'sparse_queries':n_sparse,'regular_queries':100-n_sparse},
        'guardrails':{'training':False,'checkpoint_loading':False,'inference':False,'s09_mutation':False,'s11_mutation':False},
        'viewer_policy':'separate supplemental full-order bands receipt; no model selection'})


def validate_acceptance(config_path,path):
    cfg=settings(config_path);root,parent,m,g,oldq=parents(cfg);a=load(path,'acceptance');ctx,runtime=identity(cfg)
    require(all(a['body'][k]==v for k,v in ctx.items()) and a['body']['policy']==cfg['policy'],'REVISION_ACCEPTANCE_CONTEXT')
    require(a['body']['status']=='PASS' and a['body']['parent_acceptance_id']==parent['artifact_id'] and a['body']['parent_acceptance_sha256']==file_hash(root/'acceptance.json'),'REVISION_ACCEPTANCE_PARENT')
    for p,aid in a['body']['artifacts'].items():require(load(p)['artifact_id']==aid,'REVISION_ACCEPTANCE_ARTIFACT')
    q=load(Path(path).parent/'query_manifest.json','queries');c=load(Path(path).parent/'object_counts_manifest.json','summary')
    require(q['body']['rows']==select_queries(g['body']['rows'],c['body']['counts'],cfg['selection_seed']),'REVISION_ACCEPTANCE_QUERIES')
    require(a['body']['row_count']==280000 and q['body']['object_count_definition']==DEFINITION,'REVISION_ACCEPTANCE_COUNTS')
    return cfg,root,a,m,g,q
