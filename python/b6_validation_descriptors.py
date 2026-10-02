"""Validation original-parent descriptors using unchanged S11 R functions."""
from pathlib import Path
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
import io
import tarfile
import tempfile
import subprocess
import hashlib
import torch
from b6_con_census import build_children
from b6_s50_cache import ROOT as CACHE_ROOT
import pyarrow.parquet as pq
import yaml
from b6_stage_b_preparation import catalog,read,write,sha256_file


def build(root,c):
    __import__('pyarrow').set_cpu_count(1)
    torch.set_num_threads(1)
    dest=root/'validation_descriptors'
    if dest.exists():
        m=read(dest/'manifest.json')
        for f in m['files']:assert sha256_file(dest/f['path'])==f['sha256']
        return dest/'descriptors.json'
    inventory=read(Path(c['frozen_science']['settings']['output_root'])/c['frozen_science']['design_id']/'inventory/inventory.json')['entries']
    scenes=sorted(r['scene_id'] for r in inventory if r['role']=='validation_gallery');assert len(scenes)==1000
    cache=CACHE_ROOT/c['input_contract']['design_id']/'prepared'
    cache_rows={r['scene_id']:r for r in read(cache/'manifest.json')['entries'] if r['role']=='validation_gallery'}
    parent_maps={};structural={}
    cat=catalog();bybranch=defaultdict(list)
    for scene in scenes:bybranch[cat.p3_by_scene[scene]['branch_id']].append(scene)
    stage=Path(tempfile.mkdtemp(prefix='.descriptors-',dir=root));inputs=stage/'input';inputs.mkdir()
    def extract(item):
        branch,selected=item;p=cat.p3_by_scene[selected[0]];path=cat.roots['p3']/'shards'/branch/p['payload_filename'];out=inputs/branch;out.mkdir()
        receipts=[]; tables={}
        with tarfile.open(path) as tar:
            for member,name in [('vector/road_observed.parquet','roads'),('relations/relation_edges.parquet','edges'),('relations/relation_node_index.parquet','nodes'),('topology/source_topology.parquet','topology')]:
                raw=tar.extractfile(member).read();table=pq.read_table(io.BytesIO(raw));table=table.filter(__import__('pyarrow').compute.is_in(table['scene_id'],value_set=__import__('pyarrow').array(selected)))
                tables[name]=table.to_pylist()
                pq.write_table(table,out/(name+'.parquet'))
                receipts.append({'parent':str(path),'accepted_parent_sha256':p['payload_sha256'],'member':member,'member_sha256':hashlib.sha256(raw).hexdigest()})
        original={k:defaultdict(list) for k in ['roads','topology','relations']}
        for name,key in [('roads','roads'),('topology','topology'),('edges','relations')]:
            for row in tables[name]:original[key][row['scene_id']].append(row)
        for scene in selected:
            delta={'geometry':[{'local_entity_id':r['local_entity_id'],'geometry_wkb':r['observed_geometry'],'fallback':True} for r in original['roads'][scene]],
                'absorption':[],'attributes':[],'relation_delta':[],'removals':[]}
            children,_=build_children(scene,'original',delta,original,None)
            mapping={r['child_id']:r['source_parent'] for r in children}
            rec=cache_rows[scene];file=cache/rec['path'];assert sha256_file(file)==rec['sha256']
            payload=torch.load(file,map_location='cpu',weights_only=False)
            ids=payload['sample']['lineage']['child_ids'];assert set(ids)==set(mapping)
            parents=[mapping[i] for i in ids];parent_maps[scene]=parents
            graphs={'G':payload['sample']['edges'],'Ppre':payload['ppre_edges']};stats={};sn={}
            for policy,g in graphs.items():
                pairs=g['edge_index'].T.tolist();masks=g['relation_mask'].tolist()
                sibling=[parents[a]==parents[b] for a,b in pairs]
                sn[policy]={tuple(p) for p,m in zip(pairs,masks) if m&1}
                stats[policy]={'entities':len(parents),'pairs':len(pairs),'SN':sum(bool(m&1) for m in masks),
                    'INT':sum(bool(m&8) for m in masks),'CON':sum(bool(m&16) for m in masks),
                    'sibling_SN':sum(s and bool(m&1) for s,m in zip(sibling,masks)),
                    'sibling_INT':sum(s and bool(m&8) for s,m in zip(sibling,masks)),
                    'sibling_CON':sum(s and bool(m&16) for s,m in zip(sibling,masks))}
            stats['external_SN_recovered']=len(sn['Ppre']-sn['G'])
            assert all(parents[a]!=parents[b] for a,b in sn['Ppre'])
            structural[scene]=stats
        return receipts
    with ThreadPoolExecutor(max_workers=c['settings']['resources']['descriptor_workers']) as pool:receipts=[r for batch in pool.map(extract,sorted(bybranch.items())) for r in batch]
    write(inputs/'index.json',{'branches':sorted(bybranch),'scenes_by_branch':dict(bybranch)})
    categories=yaml.safe_load(Path('config/training_controller.yml').read_text())['roots']['categories']
    subprocess.run(['Rscript','R/b6_validation_descriptors.R',str(inputs),str(stage/'descriptors.json'),categories],check=True)
    rows=read(stage/'descriptors.json');assert sorted(r['scene_id'] for r in rows)==scenes
    write(stage/'child_parents.json',parent_maps)
    write(stage/'structural.json',structural)
    write(stage/'provenance.json',{'receipts':receipts,'categories_sha256':sha256_file(categories),
        'definitions_sha256':sha256_file('R/scene_descriptors.R'),'validation_only':True,'segmented_geometry':False})
    write(stage/'manifest.json',{'files':[{'path':str(p.relative_to(stage)),'sha256':sha256_file(p)} for p in sorted(stage.rglob('*')) if p.is_file()]})
    stage.rename(dest);return dest/'descriptors.json'
