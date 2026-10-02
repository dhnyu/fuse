"""Stage B CPU preparation gates. GPU pilot is deferred by explicit user decision.

No full training function, optimizer, checkpoint writer, or canonical publisher.
"""
from __future__ import annotations
import argparse, copy, hashlib, io, json, os, resource, tarfile, time, multiprocessing, tempfile
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
import torch
import yaml
import jsonschema
from b6_postbank_adapter import resolve_receiver, AmbiguousLineage, original_adapter, digest
from model_data import ArtifactCatalog, sha256_file
from training_prepared_cache import ProductionPreparedData
from training_family_inputs import project, check_sample
from training_configuration import materialize_hyperparameter_configuration
from training_finalization import selection_contract_content

ROOT=Path('/mnt/hdd002/dhnyu/fusedata/experiments/b6_road_granularity_stage_b')
SOURCES=['python/b6_postbank_adapter.py','python/b6_stage_b_preparation.py','config/b6_stage_b_preparation.yml',
 'config/schemas/b6_stage_b_preparation.schema.json','R/b6_stage_b_preparation.R','targets/b6_stage_b_preparation.R','_targets_b6_stage_b_preparation.R',
 'config/training_controller.yml','python/augmentation_rng.py','python/training_prepared_cache.py','python/training_support.py','python/model_families.py','python/current_methodology.py','python/canonical_config.py','python/augmentation_bank.py','python/model_data.py','python/training_family_inputs.py','python/training_configuration.py',
 'python/training_finalization.py','config/training.yml','config/model_inputs.yml','config/p4_deterministic_augmentation.yml','config/p5_deterministic_queries.yml']

def write(p,x): p.write_text(json.dumps(x,sort_keys=True,indent=2,allow_nan=False)+'\n')
def read(p): return json.loads(Path(p).read_text())
def safe_root(p):
    p=Path(p)
    if p!=ROOT or p.resolve()!=p: raise ValueError('experimental Stage B namespace only')
    return p

def scientific_snapshot(value):
    """Non-executable settings: never export canonical writable destinations."""
    if isinstance(value,dict):
        return {k:scientific_snapshot(v) for k,v in value.items() if k not in ("publication_root","staging_root")}
    if isinstance(value,list): return [scientific_snapshot(v) for v in value]
    return value

def contract():
    cfg=yaml.safe_load(Path('config/b6_stage_b_preparation.yml').read_text());safe_root(cfg['output_root'])
    jsonschema.validate(cfg,read('config/schemas/b6_stage_b_preparation.schema.json'))
    a=read(Path(cfg['stage_a_root'])/'acceptance/acceptance.json')
    assert a['status']=='PASS' and a['design_id']==cfg['stage_a_id']
    assert cfg['arms']==['B6-original','B6-S50-G','B6-S50-Ppre']
    assert cfg['outside_node_child_lift']=='unresolved_fail_closed'
    assert not cfg['full_training_allowed'] and not cfg['checkpoint_publication_allowed']
    authority=read(cfg['accepted_authority']);assert authority['identity']=='s09auth_478c450cdf0e9fa4921ef485'
    sci=authority['content']['scientific'];assert sci['root_seed']==cfg['root_seed']==1629790839
    train=yaml.safe_load(Path('config/training.yml').read_text());model=yaml.safe_load(Path('config/model_inputs.yml').read_text())
    row={**sci['hyperparameters'],'configuration_id':'cmp_B6','model_family':'B6'}
    routed=materialize_hyperparameter_configuration(row,train,model)
    assert routed['training']['training']['root_seed']==1629790839
    t=routed['training'];m=routed['model']['model']
    expected={'d':256,'d_c':256,'attention_heads':4,'relation_layers':3,'dropout':.2}
    assert all(m[k]==v for k,v in expected.items())
    assert (t['training']['global_batch_size'],t['training']['world_size'],t['queue']['capacity'])==(32,2,8192)
    t=scientific_snapshot(t)
    t['validation']['patience_reset']=selection_contract_content()['patience_reset']
    value={'execution_authority':'NOT_ISSUED; scientific snapshot only','schema_version':'1.0.0','settings':cfg,'accepted_authority_sha256':sha256_file(cfg['accepted_authority']),
      'stage_a_acceptance_sha256':sha256_file(Path(cfg['stage_a_root'])/'acceptance/acceptance.json'),
      'resolved_training':t,'resolved_model':scientific_snapshot(routed['model']),'selection':selection_contract_content(),
      'seed_group':{'identity':cfg['seed_group'],'root_seed':1629790839,'rng_configuration_identity':'cmp_B6',
                    'arm_labels_do_not_derive_seed':True,'view_order':'accepted production epoch/view sampler unchanged'},
      'con':'Preserve accepted P4/P5 connectivity semantics, including existing outside-node behavior. Child lift undecided; do not drop or broadcast CON.',
      'validation':{'queries':2000,'gallery':1000,'normalize':True,'similarity':'cosine','metrics':['retrieval_loss','separation_margin','MRR','HIT@1','HIT@5','HIT@10']},
      'diagnostics':{'gallery':'same accepted 1000 scenes','road_count_bins':['0','1-8','9-49','50+'],
                     'parent_length_bins_m':[0,50,100,250,500,'infinity'],
                     'parent_length_statistic':'scene mean original observed parent length; empty separate',
                     'descriptors':['road_density','road_orientation_dispersion','mean_road_segment_length','road_location_dispersion','road_type_composition','road_hierarchy_composition','relation_composition','mean_relational_degree'],
                     'descriptor_geometry':'original parents; synthetic cuts never count as intersections','selection_uses_strata':False},
      'source_hashes':{p:sha256_file(p) for p in SOURCES}}
    value['design_id']='b6b_'+digest(value)[:24]
    return value

def publish(c,name,build):
    root=safe_root(c['settings']['output_root'])/c['design_id'];root.mkdir(parents=True,exist_ok=True)
    dest=root/name
    if dest.exists():
        m=read(dest/'manifest.json');assert m['design_id']==c['design_id']
        for f in m['files']: assert sha256_file(dest/f['path'])==f['sha256']
        return dest
    stage=Path(tempfile.mkdtemp(prefix='.stage-'+name+'-',dir=root))
    build(stage)
    files=[{'path':p.name,'sha256':sha256_file(p),'bytes':p.stat().st_size} for p in sorted(stage.iterdir()) if p.is_file()]
    write(stage/'manifest.json',{'design_id':c['design_id'],'publication_qc':'PASS','files':files})
    stage.rename(dest);return dest

def catalog():
    c=yaml.safe_load(Path('config/training_controller.yml').read_text());t=yaml.safe_load(Path('config/training.yml').read_text())
    return ArtifactCatalog({k:c['roots'][k] for k in ['p3','p4','p5']},t['parents'],verify=False)

def inventory(c,stage):
    root=Path(c['settings']['prepared_parent']);data=ProductionPreparedData(root,'main_1.0x',8)
    manifest=read(root/'production_cache_manifest.json');checks={int(x['global_index']):x for x in manifest['entries']};cat=catalog()
    selected=[]
    query_lookup={(r['scene_id'],int(r['query_index'])):r['query_id'] for r in cat.query_rows['validation']}
    for (role,scene,view),x in sorted(data.index.items(),key=lambda pair:str(pair[0])):
        if role=='training' and view not in data.views[scene]:continue
        if role not in ('training','validation_gallery','validation_query'):continue
        if role=='training': assert x['candidate_id']=={int(r['master_view_id']):r['candidate_id'] for r in cat.k8[scene]}[view]
        if role=='validation_query': assert x['candidate_id']==query_lookup[(scene,int(view))]
        receipt=checks[x['global_index']]
        selected.append({**x,'prepared_sha256':receipt['prepared_sha256'],'prepared_bytes':receipt['prepared_size'],
                         'fourier_reference':receipt['record']})
    counts={role:sum(x['role']==role for x in selected) for role in ('training','validation_gallery','validation_query')}
    assert counts=={'training':19368,'validation_gallery':1000,'validation_query':2000},counts
    assert {x['scene_id'] for x in selected if x['role']=='validation_gallery'}=={r['scene_id'] for r in cat.gallery_rows['validation']}
    write(stage/'inventory.json',{'count':len(selected),'counts':counts,'parent':str(root),'manifest_sha256':sha256_file(root/'production_cache_manifest.json'),'entries':selected})
    write(stage/'cache_contract.json',{'minimum_entries_per_arm':len(selected),'not_required':'other intensities, K>8, evaluation, DS rasters',
      'model_ready_ids':{arm:'b6mr_'+digest({'method':c['design_id'],'arm':arm,'inventory':digest(selected)})[:24] for arm in c['settings']['arms']},
      'prepared_identity_fields':['method','arm','inventory','parent_hashes','tensor_schema','tensor_content'],
      'fourier_identity_fields':['child_geometry_float64','entity_order','normalization_length_500m','128_frequencies','implementation_sha256','parent_hashes'],
      'original_reuse':'hash-bound immutable accepted prepared/Fourier references; never relabel their authority',
      'segmented_payload_status':'NOT_GENERATED_METHOD_GATE','experimental_training_authority':'NOT_ISSUED_METHOD_GATE',
      'fourier_geometry_config':c['resolved_model']['model']['geometry'],
      'authority_identity_recipe':'hash resolved settings, shared seed group, parent hashes, per-arm dataset and Fourier identities; canonical S09 IDs forbidden'})

def table(tar,name): return pq.read_table(io.BytesIO(tar.extractfile(name).read()))
def filtered_rows(t,name,field,values):
    x=table(t,name);return x.filter(pc.is_in(x[field],value_set=pa.array(values,type=x[field].type))).to_pylist()

def lineage_job(job):
    torch.set_num_threads(1);pa.set_cpu_count(1);start=time.monotonic()
    p3=Path(job['p3']);assert sha256_file(p3)==job['p3_sha256']
    with tarfile.open(p3) as t:
        roads=table(t,'vector/road_observed.parquet').to_pylist();top=table(t,'topology/source_topology.parquet').to_pylist()
    roads_scene=defaultdict(dict);top_scene=defaultdict(list)
    for r in roads: roads_scene[r['scene_id']][int(r['local_entity_id'])]=r
    for r in top: top_scene[r['scene_id']].append(r)
    failures=[];counters=defaultdict(int);outside=[];receipts=[];proof=hashlib.sha256()
    for scene in job['gallery_scenes']:
        counters['original_gallery_scenes']+=1
        for row in roads_scene[scene].values():
            from b6_postbank_adapter import parts
            import shapely
            for i,g in enumerate(parts(shapely.from_wkb(bytes(row['observed_geometry'])))):
                counters['original_gallery_parts']+=1
                proof.update(digest([scene,str(row['source_entity_id']),i,hashlib.sha256(g.wkb).hexdigest()]).encode())
    for bank in job['banks']:
        path=Path(bank['path']);assert sha256_file(path)==bank['sha256'];receipts.append({'path':str(path),'sha256':bank['sha256']})
        identities={x['identity']:x['scene_id'] for x in bank['views']};field=bank['field']
        with tarfile.open(path) as t:
            tables={name:filtered_rows(t,name+'.parquet',field,list(identities)) for name in ['geometry','attributes','absorption','relation_delta','topology']}
        grouped={name:defaultdict(list) for name in tables}
        for name,rows in tables.items():
            for row in rows:grouped[name][row[field]].append(row)
        for view,scene in identities.items():
            counters['views']+=1;original=roads_scene[scene];topology=top_scene[scene]
            material={int(r['local_entity_id']):r for r in grouped['geometry'][view] if int(r['local_entity_id']) in original}
            if not material:counters['zero_road_views']+=1
            ownership={};node_support={};all_nodes={}
            for local,row in material.items():
                parent=original[local];cx=parent['scene_center_x_5186'];cy=parent['scene_center_y_5186']
                try:
                    mapped=resolve_receiver(original,topology,grouped['absorption'][view],row,grouped['attributes'][view],job['profile'],(cx-250,cy-250,cx+250,cy+250))
                    ledger=[r for r in grouped['topology'][view] if int(r['receiver_local_entity_id'])==local]
                    owners={p['source_local_id'] for p in mapped}
                    if len(owners)>1:
                        recorded={(int(r['component_source_local_entity_id']),str(r['source_node_id']),float(r['x']),float(r['y'])) for r in ledger}
                        expected={(int(r['road_local_entity_id']),str(r['source_node_id']),float(r['source_node_x_5186']),float(r['source_node_y_5186'])) for r in topology if int(r['road_local_entity_id']) in owners}
                        if recorded!=expected: raise AmbiguousLineage('accepted topology ledger disagrees with expanded source recipe')
                except (AmbiguousLineage,KeyError,ValueError) as err:
                    failures.append({'scene':scene,'view':view,'receiver':local,'error':str(err)});continue
                counters['receivers']+=1;counters['parts']+=len(mapped);counters['multipart_receivers']+=len(mapped)>1
                counters['absorbed_receivers']+=any(x['role']=='DONOR' for x in mapped)
                ownership[local]=mapped
                node_support[local]={n['node_id'] for part in mapped for n in part['true_nodes_on_support']}
                all_nodes[local]={n['node_id'] for part in mapped for n in part['true_nodes_on_support']+part['source_chain_nodes_off_part']}
                for part in mapped:proof.update(digest({k:v for k,v in part.items() if k!='geometry'}).encode())
            # Existing P4 additions expose the real outside-node lifting problem.
            for edge in grouped['relation_delta'][view]:
                if edge['relation_type']!='CON' or edge['action']!='ADD':continue
                a,b=int(edge['source']),int(edge['destination'])
                for node in sorted(all_nodes.get(a,set())&all_nodes.get(b,set())):
                    if node not in node_support.get(a,set()) or node not in node_support.get(b,set()):
                        counters['outside_con_node_pair_rows']+=1
                        if len(outside)<20:outside.append({'scene_id':scene,'view_id':view,'source':a,'destination':b,'node_id':node,
                          'source_parts':len(ownership[a]),'destination_parts':len(ownership[b]),
                          'source_node_on_support':node in node_support[a],'destination_node_on_support':node in node_support[b]})
    return {'job':job['id'],'counts':dict(counters),'ambiguous_count':len(failures),'failures':failures,
            'outside_examples':outside,'lineage_proof_sha256':proof.hexdigest(),'receipts':[{'path':str(p3),'sha256':job['p3_sha256']}]+receipts,
            'seconds':time.monotonic()-start,'peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024}

def lineage_jobs():
    cat=catalog();profiles=yaml.safe_load(Path('config/p4_deterministic_augmentation.yml').read_text())['profiles'];profile=next(x for x in profiles if x['profile_id']=='main_1.0x')
    jobs={}
    for scene in sorted(set(cat.k8)|{r['scene_id'] for r in cat.query_rows['validation']}):
        p=cat.p3_by_scene[scene];branch=p['branch_id']
        if branch not in jobs:jobs[branch]={'id':branch,'p3':str(cat.roots['p3']/'shards'/branch/p['payload_filename']),'p3_sha256':p['payload_sha256'],'banks':{},'profile':profile,'gallery_scenes':[]}
        j=jobs[branch]
        if scene not in cat.k8:j['gallery_scenes'].append(scene)
        if scene in cat.k8:
            path,m=cat.p4_branch[branch];k=str(path)
            bank=j['banks'].setdefault(k,{'path':k,'sha256':m['payload']['sha256'],'field':'candidate_id','views':[]})
            bank['views'].extend({'identity':r['candidate_id'],'scene_id':scene} for r in cat.k8[scene])
        for r in cat.query_rows['validation']:
            if r['scene_id']!=scene:continue
            path=cat.roots['p5']/r['namespace']/'shards'/r['query_branch_id']/r['query_payload_filename'];k=str(path)
            bank=j['banks'].setdefault(k,{'path':k,'sha256':r['query_payload_sha256'],'field':'query_id','views':[]})
            bank['views'].append({'identity':r['query_id'],'scene_id':scene})
    for j in jobs.values():j['banks']=list(j['banks'].values())
    return list(jobs.values())

def tensor_digest(x):
    h=hashlib.sha256()
    def feed(v):
        if torch.is_tensor(v):
            t=v.detach().cpu().contiguous();h.update(str((str(t.dtype),tuple(t.shape))).encode());h.update(t.numpy().tobytes())
        elif isinstance(v,dict):
            for k in sorted(v):h.update(k.encode());feed(v[k])
        elif isinstance(v,(list,tuple)):
            h.update(str(len(v)).encode())
            for y in v:feed(y)
        else:h.update(repr(v).encode())
    feed(x);return h.hexdigest()

def parity_chunk(job):
    parent,selected=job;parent=Path(parent);torch.set_num_threads(1);start=time.monotonic();rows=[]
    for x in selected:
        path=parent/'prepared'/f"{x['global_index']:06d}.pt";assert sha256_file(path)==x['prepared_sha256']
        original=torch.load(path,map_location='cpu',weights_only=False)['sample'];before=tensor_digest(original)
        adapted=original_adapter(original);expected=project(original,'B6');check_sample(adapted[0])
        if tensor_digest(expected)!=tensor_digest(adapted) or before!=tensor_digest(original):
            raise ValueError('BLOCKED: Original paired-view tensor parity failed')
        ids=original['entities']['local_entity_id'][original['entities']['entity_type']==1]
        assert torch.equal(adapted[0]['entities']['local_entity_id'],ids)
        rows.append({'global_index':x['global_index'],'scene':x['scene_id'],'role':x['role'],'view':x['view'],'prepared_sha256':x['prepared_sha256'],
                     'projected_tensor_sha256':tensor_digest(adapted),'roads':len(ids)})
    return {'rows':rows,'seconds':time.monotonic()-start,'peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024}

def parity(c,stage,inventory_root):
    torch.set_num_threads(1);inv=read(inventory_root/'inventory.json');parent=Path(inv['parent'])
    pilot=pq.read_table(Path(c['settings']['stage_a_root'])/'selection/pilot_scenes.parquet').to_pylist();train={r['scene_id'] for r in pilot}
    val=sorted({x['scene_id'] for x in inv['entries'] if x['role']=='validation_gallery'},key=lambda x:digest(['b6-stage-b-parity',x]))[:32]
    selected=[x for x in inv['entries'] if (x['role']=='training' and x['scene_id'] in train) or (x['role']!='training' and x['scene_id'] in val)]
    assert len(selected)==352
    first=parity_chunk((str(parent),selected));results=[first]
    # Only expand after exact sample parity, using its observed engineering cost.
    estimate=first['seconds']/352*len(inv['entries'])/c['settings']['resources']['workers']
    full=estimate<=900 and first['peak_rss_bytes']<8*1024**3
    if full:
        seen={x['global_index'] for x in selected};remaining=[x for x in inv['entries'] if x['global_index'] not in seen]
        jobs=[(str(parent),remaining[i:i+256]) for i in range(0,len(remaining),256)]
        with ProcessPoolExecutor(max_workers=c['settings']['resources']['workers'],mp_context=multiprocessing.get_context('spawn')) as pool:
            for result in pool.map(parity_chunk,jobs):results.append(result)
    rows=sorted([r for result in results for r in result['rows']],key=lambda r:r['global_index'])
    assert len(rows)==(22368 if full else 352)
    write(stage/'original_parity.json',{'status':'PASS','scope':'accepted prepared control pass-through/family projection; not independent raw raster reconstruction',
      'full_population_checked':full,'sample_count':len(rows),'rows':rows,'pilot_seconds':first['seconds'],'projected_full_seconds':estimate,
      'summed_worker_seconds':sum(x['seconds'] for x in results),'peak_rss_bytes':max(x['peak_rss_bytes'] for x in results),
      'checks':['all projected tensors/metadata','geometry offsets/coordinates','semantics','modality availability','relation masks/endpoints','local ID/order','unchanged accepted input']})

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['contract','inventory','lineage','parity','readiness']);p.add_argument('--workers',type=int,default=1);a=p.parse_args()
    c=contract();root=ROOT/c['design_id']
    if a.action=='contract':out=publish(c,'contract',lambda d:write(d/'method_contract.json',c))
    elif a.action=='inventory':out=publish(c,'inventory',lambda d:inventory(c,d))
    elif a.action=='parity':out=publish(c,'parity',lambda d:parity(c,d,root/'inventory'))
    elif a.action=='lineage':
        def build(d):
            jobs=lineage_jobs();assert 1<=a.workers<=40
            # First branch is the measured single-worker pilot before widening.
            first=lineage_job(jobs[0]);write(d/'pilot_resource.json',{k:first[k] for k in ('seconds','peak_rss_bytes')})
            assert first['peak_rss_bytes']<8*1024**3
            results=[first]
            with ProcessPoolExecutor(max_workers=a.workers,mp_context=multiprocessing.get_context("spawn")) as pool:
                for x in pool.map(lineage_job,jobs[1:]):results.append(x)
            totals=defaultdict(int)
            for x in results:
                for k,v in x['counts'].items():totals[k]+=v
            assert totals['views']==21368,totals
            write(d/'lineage_audit.json',{'counts':dict(totals),'ambiguous_components':sum(x['ambiguous_count'] for x in results),
              'status':'PASS' if all(x['ambiguous_count']==0 for x in results) else 'FAIL_CLOSED',
              'workers':a.workers,'threads':1,'jobs':results})
        out=publish(c,'lineage',build)
    else:
        def build(d):
            l=read(root/'lineage/lineage_audit.json');q=read(root/'parity/original_parity.json')
            write(d/'readiness.json',{'verdict':('NEEDS_METHOD_DECISION' if l['status']=='PASS' and q['status']=='PASS' else 'NEEDS_ENGINEERING_FIX'),'lineage':l['status'],'ambiguous_components':l['ambiguous_components'],
              'original_parity':q['status'],'outside_con_child_lift':'UNRESOLVED_USER_DEFERRED','gpu_pilot':'NOT_EXECUTED_USER_DEFERRED',
              'segmented_model_ready':'NOT_PUBLISHED','segmented_fourier':'NOT_PUBLISHED','training_authority':'NOT_ISSUED',
              'global_batch':32,'world_size':2,'full_training':False,'checkpoints':False,'canonical_mutation':False})
        out=publish(c,'readiness',build)
    print(out)

if __name__=='__main__': main()
