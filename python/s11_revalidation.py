"""Verifier-only certification of an immutable historical S11 generation.

No production build/fit/align/publish function is called. Original generator
sources remain frozen; this verifier has a separate identity and receipt root.
"""
from __future__ import annotations
import csv
import hashlib
import json
import os
from pathlib import Path
import tempfile
from datetime import datetime, timezone
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from scipy.stats import spearmanr
from threadpoolctl import threadpool_limits
from representation_analysis import (ROOT, file_sha256, cosine_block, eligibility,
    band_positions, select_illustrations)
from s11_independent_oracle import independent_difference
from s11_artifacts import configuration, runtime, read_json, dumps, require
from s11_inputs import verify_inputs
from s11_production import read_population
from s11_alignment import descriptor_arrays, validate_metrics, METRIC_SCHEMA
from s11_descriptors import dictionary, p3_index, extract_records

VERSION = 's11-independent-revalidation-v1'
PILOT_SHA256 = '6ac524578ddc6205a2456bd7cffc7c69b724393649a705947db022d561b8e4c4'
EXTRA_SOURCES = ['python/s11_independent_oracle.py', 'python/s11_revalidation.py',
    'scripts/revalidate_s11.py', 'config/schemas/s11_revalidation.schema.json',
    'tests/python/test_s11_independent_oracle.py', 'tests/python/test_s11_revalidation.py',
    'tests/fixtures/s11_euclidean_ties.json']


def snapshot_tree(root):
    root = Path(root)
    require(not any(p.is_symlink() for p in root.rglob('*')), 'REVALIDATION_SYMLINK')
    return {str(p): file_sha256(p) for p in sorted(root.rglob('*')) if p.is_file()}


def verify_manifest_tree(root, context, snapshot):
    manifests = {}
    covered = set()
    for path in sorted(root.glob('*/*/manifest.json')):
        m = read_json(path)
        require(m['status'] == 'PASS' and m['context'] == context, 'ORIGINAL_BUNDLE_CONTEXT')
        require(m['kind'] == path.parent.parent.name, 'ORIGINAL_BUNDLE_KIND')
        covered.add(str(path))
        for name, checksum in m['files'].items():
            require(Path(name).name == name and snapshot.get(str(path.parent/name)) == checksum,
                    'ORIGINAL_PAYLOAD_HASH')
            covered.add(str(path.parent/name))
        for parent, checksum in m['parents'].items():
            require(file_sha256(parent) == checksum, 'ORIGINAL_PARENT_HASH')
        manifests[str(path)] = m
    require(covered == set(snapshot), 'UNREGISTERED_GENERATION_FILE')
    return manifests


def verify_descriptor_readback(root, ids, registry):
    folder = root/'descriptor_acceptance/accepted'
    table = pq.read_table(folder/'descriptors.parquet')
    require(table.column_names == ['scene_id']+[d['id'] for d in registry] and
            table['scene_id'].to_pylist() == ids, 'DESCRIPTOR_POPULATION_REGISTRY')
    require(read_json(folder/'dictionary.json') == registry, 'DESCRIPTOR_DICTIONARY')
    rows = table.to_pylist()
    support = pq.read_table(folder/'validity.parquet').to_pylist()
    lookup = {(r['scene_id'],r['descriptor']):r for r in support}
    require(len(lookup) == len(support) == 9000*22, 'DESCRIPTOR_SUPPORT_UNIQUE')
    require(sum(d['kind']=='scalar' for d in registry) == 15 and len(registry)==22, 'REGISTRY_22')
    coverage = {}
    for d in registry:
        name = d['id']; count = 0
        for row in rows:
            value = row[name]; s = lookup[(row['scene_id'], name)]
            require(s['valid'] == (value is not None) and s['total_count'] == s['valid_count']+s['invalid_count']
                    and min(s['valid_count'],s['invalid_count']) >= 0, 'DESCRIPTOR_SUPPORT')
            require(bool(s['null_reason']) if value is None else s['null_reason'] is None, 'DESCRIPTOR_NULL')
            for k in ('missing_count','unknown_count','alias_collision_count','valid_weight'):
                require(s[k] is None or (np.isfinite(s[k]) and s[k] >= 0), 'SUPPORT_FINITE')
            if value is None: continue
            count += 1
            require(np.isfinite(value).all(), 'DESCRIPTOR_NONFINITE')
            if d['kind']=='compositional':
                a = np.asarray(value)
                require(a.shape==(len(d['category_keys']),) and np.all(a>=0) and
                        abs(a.sum()-1) <= (1e-6 if name=='landcover_composition' else 1e-12), 'COMPOSITION')
        coverage[name] = {'valid':count,'undefined':9000-count}
    qc = read_json(folder/'qc.json')
    require([r['scene_id'] for r in qc] == ids, 'QC_ORDER')
    for row in qc:
        c = row['counts']; rel = row['relations']
        require(c['cnt_edge_count']==c['wit_edge_count']==c['contained_poi_count'], 'RELATION_INVERSES')
        require(all(c[k]%2==0 for k in ('sn_edge_count','int_edge_count','con_edge_count')), 'SYMMETRIC_RELATIONS')
        require(c['node_count']==c['building_count']+c['road_count']+c['poi_count']==rel['nodes'], 'RELATION_NODES')
        require(rel['event_counts']==[c['sn_edge_count']//2,c['cnt_edge_count'],c['int_edge_count']//2,c['con_edge_count']//2], 'RELATION_EVENTS')
        # Historical production source already enforced the frozen per-entity
        # geometry tolerance and raster shapes/masks. Check receipts are finite.
        require(all(np.isfinite(v) and v>=0 for g in row['geometry'].values() for v in g.values()), 'GEOMETRY_QC')
        require(all(isinstance(v,int) and v>=0 for v in row['raster'].values()), 'RASTER_QC')
    return {'scene_count':9000,'descriptors':22,'support_rows':len(support),'coverage':coverage}


def verify_umap_readback(root, ids, vectors, contract, original_runtime):
    folder = root/'umap/coordinates'; t = pq.read_table(folder/'coordinates.parquet')
    require(t.schema == pa.schema([('scene_id',pa.string()),('x',pa.float32()),('y',pa.float32())]), 'UMAP_SCHEMA')
    xy = np.column_stack([t['x'].to_numpy(),t['y'].to_numpy()])
    require(t['scene_id'].to_pylist()==ids and xy.shape==(9000,2) and np.isfinite(xy).all(), 'UMAP_VALUES')
    r = read_json(folder/'runtime.json')
    require(r['runtime']==original_runtime and all(r['settings'][k]==contract['umap'][k] for k in r['settings']), 'UMAP_PROVENANCE')
    require(all(b['num_threads']==1 for b in r['blas']), 'UMAP_THREAD_COUNT')
    require(r['input_bytes_sha256']==hashlib.sha256(vectors.tobytes()).hexdigest() and
            r['coordinate_bytes_sha256']==hashlib.sha256(xy.tobytes()).hexdigest() and
            r['scene_order_sha256']==hashlib.sha256('\n'.join(ids).encode()).hexdigest(), 'UMAP_ARRAY_HASH')
    panels = read_json(folder/'panels.json'); illustrations = read_json(folder/'illustrations.json')
    require(panels==contract['umap']['panels']==r['panels'] and len(panels)==6, 'UMAP_PANELS')
    require(illustrations==select_illustrations(xy,ids,contract['illustrations']['selection_seed']), 'ILLUSTRATION_SELECTION')
    return {'coordinates':9000,'panels':panels,'illustrations':illustrations,'fit_rerun':False}


def verify_alignment_readback(root, ids, registry):
    specs = read_json(root/'alignment_plan/plan/plan.json')['blocks']
    require([q for b in specs for q in b['positions']] == list(range(9000)) and len(specs)==282, 'BLOCK_PLAN')
    tables = []; band_rows=0; id_set=set(ids); rank_cache={}
    for spec in specs:
        folder=root/'alignment_blocks'/spec['block_id']; t=pq.read_table(folder/'metrics.parquet')
        require(t.schema==METRIC_SCHEMA, 'METRIC_SCHEMA')
        validate_metrics(t.to_pylist(),ids,spec['positions'],[d['id'] for d in registry])
        tables.append(t)
        bands=pq.read_table(folder/'bands.parquet').to_pylist()
        require(len(bands)==len(spec['positions'])*62, 'BAND_ROW_COUNT')
        keys=set()
        for b in bands:
            key=(b['query_index'],b['mode'],b['band'],b['rank']); require(key not in keys, 'BAND_DUPLICATE'); keys.add(key)
            require(b['query_index'] in spec['positions'] and b['query_scene_id']==ids[b['query_index']] and
                    b['candidate_scene_id'] in id_set and b['candidate_scene_id']!=b['query_scene_id'], 'BAND_POPULATION')
            require(b['mode'] in ('standard','nonlocal') and np.isfinite(b['cosine']) and np.isfinite(b['distance_m']), 'BAND_FINITE')
            require(b['candidate_count']==8999 if b['mode']=='standard' else b['distance_m']>=2000, 'BAND_ELIGIBILITY')
            count=b['candidate_count']
            if count not in rank_cache:rank_cache[count]=band_positions([count])
            require(b['rank'] in rank_cache[count][b['band']][0], 'BAND_RANK_REGION')
        band_rows+=len(bands)
    concatenated=pa.concat_tables(tables)
    merged=pq.read_table(root/'alignment_summaries/summaries/query_metrics.parquet')
    require(merged.equals(concatenated) and merged.num_rows==1980000, 'MERGED_METRICS_READBACK')
    summaries=read_json(root/'alignment_summaries/summaries/summary.json')
    require(pq.read_table(root/'alignment_summaries/summaries/summary.parquet').to_pylist()==summaries, 'SUMMARY_FORMAT_READBACK')
    expected={(d['id'],m,b) for d in registry for m in ('standard','nonlocal') for b in ('rho','rank1','upper','middle','lower')}
    require(len(summaries)==220 and {(r['descriptor'],r['mode'],r['region']) for r in summaries}==expected, 'SUMMARY_KEYS')
    for r in summaries:
        require(r['query_total_count']==9000 and r['query_valid_count']+r['query_invalid_count']==9000 and
                r['candidate_total_count']==r['candidate_valid_count']+r['candidate_invalid_count'], 'SUMMARY_SUPPORT')
        vals=[r[k] for k in ('query_q1','query_median','query_q3','query_iqr')]
        require(all(v is None for v in vals) if not r['query_valid_count'] else
                all(v is not None and np.isfinite(v) for v in vals) and vals[0]<=vals[1]<=vals[2] and vals[3]>=0,
                'SUMMARY_VALUES')
    with (root/'publication/figures_tables/alignment_summary.csv').open() as stream:
        csvrows=list(csv.DictReader(stream))
    require(csvrows==[{k:'' if v is None else str(v) for k,v in r.items()} for r in summaries], 'PUBLICATION_CSV')
    for name in ('umap_six_panels.pdf','illustrations.pdf'):
        path=root/'publication/figures_tables'/name
        require(path.stat().st_size>0 and path.read_bytes().startswith(b'%PDF-'), 'PUBLICATION_PDF')
    fm=read_json(root/'publication/figures_tables/figure_metadata.json')
    require(fm['panels']==read_json(root/'umap/coordinates/panels.json') and
            fm['illustrations']==read_json(root/'umap/coordinates/illustrations.json') and fm['clustering'] is False, 'FIGURE_METADATA')
    return {'query_count':9000,'block_count':282,'metric_rows':merged.num_rows,'band_rows':band_rows,
            'summary_rows':220,'scientific_values_regenerated':False}


def verify_fixed_queries(root, ids, vectors, centers, temporary_root):
    arrays=descriptor_arrays(root/'descriptor_acceptance/accepted/manifest.json',ids,'full')
    checks=[]; band_checks=0; null_checks=0; source_checks=0
    for q in [0,4499,8999]:
        folder=root/f'alignment_blocks/{q//32:04d}'
        metrics=pq.read_table(folder/'metrics.parquet',filters=[('query_index','=',q)]).to_pylist()
        validate_metrics(metrics,ids,[q],list(arrays))
        with threadpool_limits(limits=1):reference=vectors@vectors[q]
        require(np.array_equal(reference,cosine_block(vectors,[q])[0]), 'ACCEPTANCE_GEMV_PARITY')
        _,modes=eligibility(centers,[q]);lookup={}
        saved=pq.read_table(folder/'bands.parquet',filters=[('query_index','=',q)]).to_pylist()
        for mode, mask in modes.items():
            eligible=np.flatnonzero(mask[0]);order=eligible[np.lexsort((np.array(ids)[eligible],-reference[eligible]))]
            for name,rank in band_positions([len(order)]).items():lookup[(mode,name)]=order[rank[0]-1]
            for row in (r for r in saved if r['mode']==mode):
                j=order[row['rank']-1]
                require(row['candidate_scene_id']==ids[j] and row['cosine']==float(reference[j]) and row['candidate_count']==len(order), 'INDEPENDENT_BAND_RANKING')
                band_checks+=1
        # Independent computation, once per descriptor; no production distances.
        differences={name:independent_difference(v,q) for name,(v,valid) in arrays.items()}
        for r in metrics:
            v,valid=arrays[r['descriptor']]; mask=modes[r['mode']][0]&valid&valid[q];diff=differences[r['descriptor']]
            if r['region']=='rho':
                s=reference[mask];d=diff[mask]
                reason='fewer_than_two_valid_pairs' if len(d)<2 else 'constant_similarity' if np.ptp(s)==0 else 'constant_difference' if np.ptp(d)==0 else None
                require(r['null_reason']==reason and r['valid_count']==int(mask.sum()), 'INDEPENDENT_RHO_SUPPORT')
                if reason:
                    require(r['value'] is None,'INDEPENDENT_NULL_RHO');null_checks+=1
                else:
                    rho=float(spearmanr(s,d).statistic)
                    require(np.isclose(rho,r['value'],rtol=0,atol=2e-12), 'INDEPENDENT_RHO')
                    checks.append({'query':q,'descriptor':r['descriptor'],'mode':r['mode'],
                        'stored_rho':r['value'],'independent_rho':rho,'valid_pairs':int(mask.sum())})
            else:
                candidates=lookup[(r['mode'],r['region'])];ok=valid[candidates]&valid[q]
                require(r['valid_count']==int(ok.sum()), 'INDEPENDENT_BAND_SUPPORT')
                if np.any(ok):require(np.isclose(np.mean(diff[candidates[ok]]),r['value'],rtol=1e-12,atol=2e-10),'INDEPENDENT_BAND_MEAN')
                else:require(r['value'] is None,'INDEPENDENT_BAND_NULL')
    index=p3_index();execution=configuration()[2]
    for q in [0,4499,8999]:
        scene=ids[q];item=index[scene]
        spec={'scene_ids':[scene],'path':str(Path(execution['p3_root'])/'shards'/item['branch_id']/item['payload_filename']),'sha256':item['payload_sha256']}
        with tempfile.TemporaryDirectory(prefix='source-readback-',dir=temporary_root) as temporary:
            original=extract_records(spec,temporary)[0]['descriptors']
        for name,(v,valid) in arrays.items():
            value=original[name]['value'];require(bool(valid[q])==(value is not None),'SOURCE_DESCRIPTOR_VALIDITY')
            if value is not None:require(np.array_equal(v[q],value),'SOURCE_DESCRIPTOR_VALUE')
            source_checks+=1
    return {'positions':[0,4499,8999],'rho_checks':len(checks),'null_rho_checks':null_checks,
            'band_score_rank_checks':band_checks,'descriptor_source_checks':source_checks,
            'descriptor_reread_scenes':3,'rho_atol':2e-12,'rho_rtol':0,'rho_details':checks}


def verifier_identity():
    r=runtime()
    sources={**r['sources'],**{name:file_sha256(ROOT/name) for name in EXTRA_SOURCES}}
    body={'version':VERSION,'runtime':{k:v for k,v in r.items() if k!='sources'},'sources':sources}
    return {**body,'identity_sha256':hashlib.sha256(dumps(body).encode()).hexdigest()}


def revalidate(generation, pilot_receipt, output_root, fixture_receipt):
    import jsonschema
    root=Path(generation).resolve();output=Path(output_root).resolve()
    require(not output.is_relative_to(root) and not root.is_relative_to(output), 'SEPARATE_RECEIPT_ROOT')
    require(file_sha256(pilot_receipt)==PILOT_SHA256,'ORIGINAL_PILOT_HASH')
    pilot=read_json(pilot_receipt);ctx=read_json(root/'accepted_parents/parents/manifest.json')['context']
    original=ctx['runtime']; require(pilot['status']=='PASS' and pilot['runtime']==original,'ORIGINAL_PILOT_RUNTIME')
    require(runtime()==original,'ORIGINAL_SOURCE_RUNTIME_CHANGED')
    provenance={k:v for k,v in ctx.items() if k not in ('root','generation')}
    require(hashlib.sha256(dumps(provenance).encode()).hexdigest()[:24]==ctx['generation']==root.name and ctx['root']==str(root), 'ORIGINAL_GENERATION_ID')
    fixture=read_json(fixture_receipt);identity=verifier_identity()
    require(fixture['status']=='PASS' and fixture['verifier_identity']==identity['identity_sha256'], 'CURRENT_REGRESSION_RECEIPT')
    output.mkdir(parents=True,exist_ok=True)
    work=Path(tempfile.mkdtemp(prefix='s11rv_',dir=output))
    before=snapshot_tree(root)
    failed_evidence=[ROOT/'logs/20260923_0319_s11_full_execution.log',ROOT/'logs/20260923_0319_s11_full_target_metadata.json',ROOT/'logs/20260923_0319_s11_acceptance_failure_diagnostic.json']
    evidence={str(p):file_sha256(p) for p in failed_evidence}
    receipt={'schema_version':'1.0.0','status':'BLOCKED','generation':ctx['generation'],'original_context':ctx,
             'verifier':identity,'started_at':datetime.now(timezone.utc).isoformat(),'checks':{},
             'original_pilot':{'path':str(pilot_receipt),'sha256':PILOT_SHA256},
             'regression_receipt':{'path':str(fixture_receipt),'sha256':file_sha256(fixture_receipt)},
             'historical_failure_evidence':evidence,'verified_payload_hashes':{},'scientific_payloads_unchanged':False}
    try:
        manifests=verify_manifest_tree(root,ctx,before)
        contract,lock,execution=configuration();x,centers,ids=verify_inputs(contract,lock)
        require(ctx['contract_sha256']==lock['contract_sha256']==pilot['contract_sha256'], 'CONTRACT_BINDING')
        p3_index()
        plan=read_json(root/'descriptor_plan/plan/plan.json')
        for spec in plan['shards']:require(file_sha256(spec['path'])==spec['sha256'],'P3_SHARD_HASH')
        receipt['checks']['descriptor']=verify_descriptor_readback(root,ids,dictionary())
        receipt['checks']['umap']=verify_umap_readback(root,ids,x,contract,original)
        receipt['checks']['alignment_publication']=verify_alignment_readback(root,ids,dictionary())
        receipt['checks']['independent']=verify_fixed_queries(root,ids,x,centers,work)
        verify_inputs(contract,lock)
        require(snapshot_tree(root)==before,'SCIENTIFIC_PAYLOAD_CHANGED')
        require(runtime()==original and verifier_identity()==identity,'VERIFIER_CHANGED')
        require(all(file_sha256(p)==h for p,h in evidence.items()),'HISTORICAL_EVIDENCE_CHANGED')
        require(not (root/'scientific_acceptance/accepted/manifest.json').exists(),'HISTORICAL_ACCEPTANCE_OVERWRITE')
        receipt.update(status='PASS',scientific_payloads_unchanged=True,verified_payload_hashes=before,
                       manifest_count=len(manifests),parents_reverified=True)
    except Exception as exc:
        receipt['failure']={'type':type(exc).__name__,'message':str(exc)}
        receipt['scientific_payloads_unchanged']=snapshot_tree(root)==before
        receipt['verified_payload_hashes']=before
    receipt['verified_at']=datetime.now(timezone.utc).isoformat()
    receipt['receipt_id']='s11rv_'+hashlib.sha256(dumps(receipt).encode()).hexdigest()[:24]
    jsonschema.validate(receipt,read_json(ROOT/'config/schemas/s11_revalidation.schema.json'))
    # The sole publication of this entrypoint; receipt written last, exclusive.
    target=work/'receipt.json'
    with target.open('x') as stream:stream.write(dumps(receipt))
    require(read_json(target)==receipt,'REVALIDATION_RECEIPT_READBACK')
    return str(target),receipt
