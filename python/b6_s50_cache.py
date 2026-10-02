"""Immutable paired S50 prepared/Fourier products, gated by the complete CON census."""
import argparse, io, json, multiprocessing, tempfile, time, resource, tarfile
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
from collections import defaultdict
import numpy as np
import pyarrow as pa
import torch
from b6_con_census import contract as con_contract, ROOT as CON_ROOT, lineage_jobs,scene_inputs,views,build_children
from b6_con_lift import lift_accepted_parent_con_to_children,POLICY_HASH
from b6_segmented_inputs import full_source_graphs,tensorize_children
from b6_stage_b_preparation import read,write,sha256_file,table,tensor_digest,ROOT as PREP_ROOT
from b6_postbank_adapter import digest,original_adapter
from scene_encoder import geometry_fourier_features

ROOT=Path('/mnt/hdd002/dhnyu/fusedata/experiments/b6_s50_inputs')
SOURCES=['python/b6_s50_cache.py','python/b6_segmented_inputs.py','python/scene_encoder.py','python/training_family_inputs.py','python/model_data.py']

def contract():
    c=con_contract();census=CON_ROOT/c['design_id']/'census'
    assert read(census/'census.json')['verdict']=='PASS','CON census must pass before S50 inputs'
    old=c['frozen_science'];prep=PREP_ROOT/old['design_id']
    out={'con_method':c,'con_census_sha256':sha256_file(census/'census.json'),'inventory_sha256':sha256_file(prep/'inventory/inventory.json'),
         'sources':{p:sha256_file(p) for p in SOURCES},'arms':['B6-S50-G','B6-S50-Ppre'],'shared_fourier':True,'formal_training':False}
    out['design_id']='b6s50_'+digest(out)[:24];return out

def stable_save(path,value):
    buffer=io.BytesIO();torch.save(value,buffer);data=buffer.getvalue();path.write_bytes(data)
    # Fixed archive name from BytesIO yields byte-stable serialization.
    return hashlib_sha(data)

def hashlib_sha(x):
    import hashlib
    return hashlib.sha256(x).hexdigest()

def cache_worker(job):
    torch.set_num_threads(1);pa.set_cpu_count(1);start=time.monotonic();original=scene_inputs(job)
    with tarfile.open(job['p3']) as t:
        others=table(t,'vector/building_observed.parquet').to_pylist()+table(t,'vector/poi_observed.parquet').to_pylist()
    other_scene=defaultdict(list)
    for row in others:other_scene[row['scene_id']].append(row)
    entries=read(job['inventory_path'])['entries'];selected={}
    scenes=set(job['gallery_scenes'])|{v['scene_id'] for b in job['banks'] for v in b['views']}
    for r in entries:
        if r['scene_id'] in scenes:selected[(r['scene_id'],'original' if r['role']=='validation_gallery' else r['candidate_id'])]=r
    parity={x['global_index']:x['projected_tensor_sha256'] for x in read(job['parity_path'])['rows']}
    from training_runtime_inputs import SceneCenterIndex
    centers=SceneCenterIndex.from_current_contract(job['training'],job['parent']).centers
    output=Path(job['stage']);(output/job['id']).mkdir();records=[]
    for scene,view,delta in views(job,original):
        t0=time.monotonic();spec=selected[(scene,view)];index=spec['global_index']
        path=Path(job['parent'])/'prepared'/f'{index:06d}.pt';assert sha256_file(path)==spec['prepared_sha256']
        accepted=torch.load(path,map_location='cpu',weights_only=False)['sample']
        assert tensor_digest(original_adapter(accepted))==parity[index],'Original parity changed'
        children,con=build_children(scene,view,delta,original,job['profile']);pairs,causes=lift_accepted_parent_con_to_children(con,children)
        allrows=original['roads'][scene]+other_scene[scene]
        t1=time.monotonic();children,graphs,stats=full_source_graphs(allrows,delta,children,pairs);t2=time.monotonic()
        center=centers[scene][:2]
        sample,other,rng,incidence=tensorize_children(accepted,children,graphs,center,job['method'])
        common=copy_without_edges(sample);assert tensor_digest(common)==tensor_digest(copy_without_edges(other))
        with torch.inference_mode():fourier=geometry_fourier_features(sample,job['model'],torch.device('cpu'))
        assert all(torch.isfinite(x).all() for x in fourier)
        t3=time.monotonic();geo_id='b6fourier_'+digest({'geometry':tensor_digest(sample['geometry']),'order':tensor_digest(sample['entities']['local_entity_id']),
            'encoder':job['encoder_sha'],'config':job['model']['geometry'],'con_policy':POLICY_HASH,'parent_sha':spec['prepared_sha256']})[:32]
        file=output/job['id']/f'{index:06d}.pt'
        payload={'sample':sample,'ppre_edges':other['edges'],'fourier':fourier,'fourier_id':geo_id,'rng_ids':rng,'incidence':incidence,
                 'accepted_parent_sha256':spec['prepared_sha256'],'method':job['method']}
        sha=stable_save(file,payload)
        if not records:
            assert stable_bytes(payload)==file.read_bytes(),'serialization not byte-stable'
            reread=torch.load(file,map_location='cpu',weights_only=False)
            assert tensor_digest(reread)==tensor_digest(payload)
            again=geometry_fourier_features(sample,job['model'],torch.device('cpu'))
            assert all(torch.equal(a,b) for a,b in zip(fourier,again))
        records.append({'global_index':index,'role':spec['role'],'scene_id':scene,'view':spec['view'],'view_id':view,
          'path':str(file.relative_to(output)),'sha256':sha,'bytes':file.stat().st_size,'tensor_G':tensor_digest(sample),'tensor_Ppre':tensor_digest(other),
          'fourier_id':geo_id,'fourier_hash':tensor_digest(fourier),'common_tensor_hash':tensor_digest(common),'rng_hash':digest(rng),
          'children':len(children),'statistics':stats,'lineage_seconds':t1-t0,'relation_seconds':t2-t1,'fourier_tensor_seconds':t3-t2})
    return {'branch':job['id'],'records':records,'seconds':time.monotonic()-start,'rss':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024}

def copy_without_edges(sample):
    return {k:v for k,v in sample.items() if k not in ('edges','resources')}

def stable_bytes(payload):
    b=io.BytesIO();torch.save(payload,b);return b.getvalue()

def run(workers=8,pilot=False):
    c=contract();root=ROOT/c['design_id'];root.mkdir(parents=True,exist_ok=True);dest=root/('pilot' if pilot else 'prepared')
    if dest.exists():
        for r in read(dest/'manifest.json')['entries']:assert sha256_file(dest/r['path'])==r['sha256']
        return dest
    stage=Path(tempfile.mkdtemp(prefix='.stage-',dir=root));old=c['con_method']['frozen_science'];prep=PREP_ROOT/old['design_id']
    jobs=lineage_jobs();jobs.sort(key=lambda j:j['id']!='bmb_73580eb0e4936f2a9703f1a2')
    for j in jobs:j.update(stage=str(stage),parent=old['settings']['prepared_parent'],inventory_path=str(prep/'inventory/inventory.json'),
        parity_path=str(prep/'parity/original_parity.json'),method=c['design_id'],training=old['resolved_training'],model=old['resolved_model']['model'],encoder_sha=c['sources']['python/scene_encoder.py'])
    first=cache_worker(jobs[0]);results=[first]
    if not pilot:
        with ProcessPoolExecutor(max_workers=workers,mp_context=multiprocessing.get_context('spawn')) as pool:results.extend(pool.map(cache_worker,jobs[1:]))
    entries=sorted([r for x in results for r in x['records']],key=lambda r:r['global_index'])
    assert len({r['global_index'] for r in entries})==len(entries)
    if not pilot:assert len(entries)==22368
    for r in entries:assert sha256_file(stage/r['path'])==r['sha256']
    write(stage/'contract.json',c);write(stage/'manifest.json',{'design_id':c['design_id'],'entries':entries})
    arm_ids={arm:'b6prepared_'+digest({'method':c['design_id'],'policy':arm,'manifest':sha256_file(stage/'manifest.json')})[:24] for arm in c['arms']}
    write(stage/'acceptance.json',{'status':'PILOT_PASS' if pilot else 'PASS','count':len(entries),'original_parity':len(entries),'G_Ppre_only_SN':True,
        'arm_identities':arm_ids,'shared_geometry_identity':'b6shared_'+digest([r['fourier_id'] for r in entries])[:24],
        'manifest_sha256':sha256_file(stage/'manifest.json'),'workers':workers,'threads':1,'resources':[{k:x[k] for k in ('branch','seconds','rss')} for x in results],
        'total_payload_bytes':sum(r['bytes'] for r in entries),'full_training':False})
    stage.rename(dest);return dest

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--workers',type=int,default=8);p.add_argument('--pilot',action='store_true');a=p.parse_args();print(run(a.workers,a.pilot))
