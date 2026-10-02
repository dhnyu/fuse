#!/usr/bin/env python3
"""Independent read-back audit of a published supplemental generation and viewer."""
import argparse
import json
from pathlib import Path
import sys
import numpy as np
import pyarrow.parquet as pq
from threadpoolctl import threadpool_limits
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from s10_extreme_rank1 import read,sha,digest,require,SETS,lineage,safety_snapshot


def validate(root):
    root=Path(root);identity=read(root/'lineage.json');cfg=identity['config'];validation=read(root/'validation.json');v=Path(validation['viewer_root'])
    receipt=read(root/'receipt.json');vr=read(v/'viewer_receipt.json')
    require(sha(v/'viewer_receipt.json')==receipt['viewer_receipt_sha256'],'Viewer receipt binding')
    for base,rc in [(root,receipt),(v,vr)]:
        for path,h in rc['files'].items():require(sha(base/path)==h,f'Published hash: {path}')
    X,c,ids,counts,info=lineage(cfg);index={sid:i for i,sid in enumerate(ids)}
    rows=pq.read_table(root/'rank1.parquet').to_pylist();lookup={r['query_scene_id']:r for r in rows}
    require(len(rows)==9000 and list(lookup)==ids,'9000 readback population')
    require(digest(rows)==identity['rank1_content_sha256'],'Rank1 content hash')
    vc=read(v/'config.json');selected=set();boundary={}
    for name in SETS:
        m=read(root/'sets'/f'{name}.json');require(digest(m['body'])==m['content_hash'],'Set hash')
        rs=m['body']['rows'];mode=rs[0]['selection_mode'];score='rank1_cosine' if mode=='standard' else 'nonlocal_rank1_cosine';high=name.endswith('HIGH')
        expected=sorted(rows,key=lambda r:((-1 if high else 1)*r[score],r['query_scene_id']))[:100]
        require([r['query_scene_id'] for r in rs]==[r['query_scene_id'] for r in expected],'Independent membership sort')
        for position,r in enumerate(rs,1):
            require(r['content_hash']==digest({k:z for k,z in r.items() if k!='content_hash'}),'Row hash')
            require(r['query_index']==position and r['set_name']==name and r['checkpoint_id']==info['model']['checkpoint_id'],'Row identity')
            require(vc['sets'][name][position-1]==dict(r,scene_id=r['query_scene_id']),'Viewer membership readback')
        selected.update(r['query_scene_id'] for r in rs)
        threshold=rs[-1]['rank1_cosine'];better=sum((r[score]>threshold if high else r[score]<threshold) for r in rows);tied=sum(r[score]==threshold for r in rows)
        boundary[name]={'threshold':threshold,'strictly_better':better,'population_tied_at_boundary':tied,'selected_at_boundary':100-better}
    band_rows=0;display=set(selected)
    with threadpool_limits(limits=1):
        for sid in sorted(selected):
            data=read(v/'queries'/f'{sid}.json')
            require(data==read(root/'bands'/f'{sid}.json'),'Viewer band readback')
            i=index[sid];scores=X @ X[i];dist=np.sqrt(((c-c[i])**2).sum(axis=1))
            for mode in ('standard','nonlocal'):
                eligible=[j for j in range(9000) if j!=i and (mode=='standard' or dist[j]>=2000)]
                ordered=sorted(eligible,key=lambda j:(-float(scores[j]),ids[j]))
                ev=data['cmp_FM'][mode];n=len(ordered);require(ev['candidate_count']==n,'Band candidate count')
                wanted={'most':[1],'top':list(range(2,12)),'middle':list(range((n-10)//2+1,(n-10)//2+11)),'bottom':list(range(n-9,n+1))}
                for band,items in ev['bands'].items():
                    require([r['rank'] for r in items]==wanted[band],'Band positions')
                    for r in items:
                        j=ordered[r['rank']-1]
                        require(r['gallery_scene_id']==ids[j] and r['similarity']==float(scores[j]) and r['geographic_distance_m']==float(dist[j]),'Independent band order/score/distance')
                        display.add(ids[j]);band_rows+=1
    for sid in display:
        s=read(v/'scenes'/f'{sid}.json');cs=counts[sid]
        require(s['counts']=={'building':cs['n_buildings'],'road':cs['n_roads'],'poi':cs['n_pois']},'Display/accepted count equality')
    before=read(root/'safety_before.json');after=safety_snapshot(cfg,info)
    require(before==after==read(root/'safety_after.json'),'Post-publication existing artifact safety')
    return {'status':'PASS','population':9000,'set_rows':400,'unique_queries':len(selected),'independently_sorted_band_rows':band_rows,'display_scenes':len(display),'boundaries':boundary,'source_safety':'unchanged','generation':str(root),'viewer':str(v)}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('generation');a=p.parse_args();print(json.dumps(validate(a.generation),indent=2))
