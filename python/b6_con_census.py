"""Complete optimizer-free CON gate; no cache/GPU publication before PASS."""
import argparse, json, tarfile, time, resource, os, multiprocessing
from pathlib import Path
from collections import defaultdict, Counter
from concurrent.futures import ProcessPoolExecutor
import shapely
import pyarrow as pa
import pyarrow.parquet as pq
from b6_stage_b_preparation import lineage_jobs,table,filtered_rows,contract as previous_contract,ROOT as PREVIOUS_ROOT,read,write,sha256_file
from b6_postbank_adapter import resolve_receiver,digest
from b6_con_lift import subdivide_receiver,lift_accepted_parent_con_to_children,ChainMappingError,POLICY,POLICY_TEXT,POLICY_HASH

ROOT=Path('/mnt/hdd002/dhnyu/fusedata/experiments/b6_con_lift')
SOURCES=['python/b6_con_lift.py','python/b6_con_census.py','config/b6_con_lift.yml']

def contract():
    import yaml
    cfg=yaml.safe_load(Path(SOURCES[-1]).read_text())
    assert cfg['policy']==POLICY and cfg['L']==50 and cfg['full_training'] is False
    assert Path(cfg['output_root'])==ROOT
    old=previous_contract()
    c={'policy':POLICY,'policy_text':POLICY_TEXT,'policy_hash':POLICY_HASH,'previous_method':old['design_id'],
       'previous_method_sha256':sha256_file(PREVIOUS_ROOT/old['design_id']/'contract/method_contract.json'),
       'config':cfg,'source_hashes':{p:sha256_file(p) for p in SOURCES},'frozen_science':old}
    c['design_id']='b6con_'+digest(c)[:24];return c

def scene_inputs(job):
    path=Path(job['p3']);assert sha256_file(path)==job['p3_sha256']
    with tarfile.open(path) as t:
        tables={k:table(t,v).to_pylist() for k,v in [('roads','vector/road_observed.parquet'),('topology','topology/source_topology.parquet'),('relations','relations/relation_edges.parquet')]}
    out={k:defaultdict(list) for k in tables}
    for k,rows in tables.items():
        for row in rows:out[k][row['scene_id']].append(row)
    return out

def views(job,original):
    for scene in job['gallery_scenes']:
        yield scene,'original',{'geometry':[{'local_entity_id':r['local_entity_id'],'geometry_wkb':r['observed_geometry'],'fallback':True} for r in original['roads'][scene]],'absorption':[],'attributes':[],'relation_delta':[],'removals':[]}
    for bank in job['banks']:
        path=Path(bank['path']);assert sha256_file(path)==bank['sha256']
        ids={r['identity']:r['scene_id'] for r in bank['views']};field=bank['field']
        with tarfile.open(path) as t:
            data={k:filtered_rows(t,k+'.parquet',field,list(ids)) for k in ['geometry','absorption','attributes','relation_delta','removals']}
        grouped={k:defaultdict(list) for k in data}
        for k,rows in data.items():
            for r in rows:grouped[k][r[field]].append(r)
        for view,scene in ids.items():yield scene,view,{k:grouped[k][view] for k in grouped}

def build_children(scene,view,delta,original,profile):
    roads={int(r['local_entity_id']):r for r in original['roads'][scene]};top=original['topology'][scene]
    children=[]
    for row in delta['geometry']:
        local=int(row['local_entity_id'])
        if local not in roads:continue
        r=roads[local];cx,cy=r['scene_center_x_5186'],r['scene_center_y_5186']
        mapped=resolve_receiver(roads,top,delta['absorption'],row,delta['attributes'],profile,(cx-250,cy-250,cx+250,cy+250))
        children.extend(subdivide_receiver(scene,view,mapped,roads,row,top))
    removed={int(r['local_entity_id']) for r in delta['removals']}
    con={(int(r['source_local_entity_id']),int(r['destination_local_entity_id'])) for r in original['relations'][scene] if int(r['relation_mask'])&16 and int(r['source_local_entity_id']) not in removed and int(r['destination_local_entity_id']) not in removed}
    for r in delta['relation_delta']:
        if r['relation_type']=='CON':
            p=(int(r['source']),int(r['destination']))
            if r['action']=='ADD':con.add(p)
            else:con.discard(p)
    assert con=={(b,a) for a,b in con}
    return children,con

def worker(job):
    pa.set_cpu_count(1);start=time.monotonic();original=scene_inputs(job)
    counts=Counter();failures=[];audit=[];offdist=[];examples=[];proof=[]
    for scene,view,delta in views(job,original):
        counts['views']+=1
        try:
            children,con=build_children(scene,view,delta,original,job['profile'])
            pairs,records=lift_accepted_parent_con_to_children(con,children)
        except (ValueError,KeyError,AssertionError) as e:
            counts['failed_views']+=1
            if len(failures)<30:failures.append({'scene':scene,'view':view,'error':str(e)})
            continue
        counts['child_entities']+=len(children);counts['zero_road_views']+=not children
        counts['accepted_parent_pairs']+=len(con)//2;counts['accepted_causes']+=len(records);counts['unique_unordered_child_pairs']+=len(pairs)
        pairnodes=defaultdict(set)
        for r in records:
            modes=[r[k]['mode'] for k in ('a','b')];counts['on_support_endpoints']+=modes.count('physical_on_support');counts['off_support_endpoints']+=modes.count('logical_off_support')
            counts['logical_causes']+= 'logical_off_support' in modes;counts['physical_causes']+= all(m=='physical_on_support' for m in modes)
            counts['collapsed_causes']+=r['collapsed_existing_pair'];counts['same_parent_con']+=r['parent_a']==r['parent_b']
            counts['ties_before']+=sum(r[k]['ties_before']>1 for k in ('a','b'));assert all(r[k]['ties_after']==1 for k in ('a','b'))
            offdist.extend(r[k]['chain_distance_m'] for k in ('a','b') if r[k]['mode']=='logical_off_support')
            pairnodes[(r['receiver_a'],r['receiver_b'])].add(r['node_id'])
            # Compact causes table does not retain per-vertex geometry.
            audit.append({'scene':scene,'view':view,**{k:v for k,v in r.items() if k not in ('a','b')},'mode_a':r['a']['mode'],'mode_b':r['b']['mode'],'chain_distance_a':r['a']['chain_distance_m'],'chain_distance_b':r['b']['chain_distance_m']})
            if view=='augv_2bf305fd65d508a89be664e8' and {r['receiver_a'],r['receiver_b']}=={262,267}:examples.append({'scene':scene,'view':view,**r})
        counts['multi_node_parent_pairs']+=sum(len(n)>1 for n in pairnodes.values())
        proof.append(digest([scene,view,sorted(pairs),[c['child_id'] for c in children]]))
    path=Path(job['stage'])/(job['id']+'.parquet')
    if audit:pq.write_table(pa.Table.from_pylist(audit),path,compression='zstd')
    return {'branch':job['id'],'counts':dict(counts),'failures':failures,'examples':examples,'off_distance_min':min(offdist) if offdist else None,'off_distance_max':max(offdist) if offdist else None,'proof':digest(proof),'audit_file':path.name if audit else None,'seconds':time.monotonic()-start,'rss':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024}

def run(workers=8,pilot=False):
    import tempfile
    c=contract();root=ROOT/c['design_id'];root.mkdir(parents=True,exist_ok=True);dest=root/('pilot' if pilot else 'census')
    if dest.exists():
        for f in read(dest/'manifest.json')['files']:assert sha256_file(dest/f['path'])==f['sha256']
        return dest
    stage=Path(tempfile.mkdtemp(prefix='.staging-',dir=root));write(stage/'method.json',c)
    jobs=lineage_jobs()
    # Explicit known counterexample branch first.
    jobs.sort(key=lambda j: j['id']!='bmb_73580eb0e4936f2a9703f1a2')
    for j in jobs:j['stage']=str(stage)
    first=worker(jobs[0]);results=[first]
    if not pilot and not first['failures']:
        with ProcessPoolExecutor(max_workers=workers,mp_context=multiprocessing.get_context('spawn')) as pool:
            results.extend(pool.map(worker,jobs[1:]))
    totals=Counter()
    for r in results:totals.update(r['counts'])
    complete=totals['views']==22368
    verdict='PASS' if complete and not totals['failed_views'] else ('PILOT_PASS' if pilot and not totals['failed_views'] else 'BLOCKED_CON_CHAIN_MAPPING')
    write(stage/'census.json',{'verdict':verdict,'counts':dict(totals),'complete':complete,'workers':workers,'threads':1,'results':results,'synthetic_con':0,'false_clique':0,'ties_after':0})
    files=[{'path':p.name,'sha256':sha256_file(p),'bytes':p.stat().st_size} for p in sorted(stage.iterdir())]
    write(stage/'manifest.json',{'design_id':c['design_id'],'files':files});stage.rename(dest);return dest

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--workers',type=int,default=8);p.add_argument('--pilot',action='store_true');a=p.parse_args();print(run(a.workers,a.pilot))
