#!/usr/bin/env python3
"""Independent read-only selection and display-band validation."""
import argparse
import json
from pathlib import Path
import sys
import numpy as np
import pyarrow.parquet as pq
from threadpoolctl import threadpool_limits
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from s10_extreme_rank1 import read,sha,require,digest


def validate(generation):
    root=Path(generation);validation=read(root/'validation.json');v=Path(validation['viewer_root']);source=read(root/'source.json');parent=Path(source['parent']);identity=read(parent/'lineage.json');cfg=identity['config']
    for where,receipt in [(root,read(root/'receipt.json')),(v,read(v/'viewer_receipt.json'))]:
        for path,h in receipt['files'].items():require(sha(where/path)==h,'Published file checksum')
    for path,h in read(root/'preserved_sha256.json').items():require(sha(path)==h,'Original data/report changed')
    rows=pq.read_table(parent/'rank1.parquet').to_pylist();lookup={r['query_scene_id']:r for r in rows};counts=read(Path(cfg['query_revision'])/'object_counts_manifest.json')['body']['counts'];vc=read(v/'config.json')
    newqueries=set();boundaries={}
    for name in ['STANDARD_HIGH_NONEMPTY','NONLOCAL_HIGH_NONEMPTY']:
        m=read(root/'sets'/f'{name}.json');require(digest(m['body'])==m['sha256'],'Manifest hash');saved=m['body']['rows'];score='rank1_cosine' if name.startswith('STANDARD') else 'nonlocal_rank1_cosine'
        candidates=[r for r in rows if counts[r['query_scene_id']]['object_count']>=1]
        candidates.sort(key=lambda r:(-r[score],r['query_scene_id']))
        require([r['query_scene_id'] for r in saved]==[r['query_scene_id'] for r in candidates[:100]],'Selection ordering')
        require(len(set(r['query_scene_id'] for r in saved))==100,'Unique 100')
        require(vc['sets'][name]==saved,'Viewer set readback')
        for r in saved:
            require(r['eligible'] and r['n_obj']==r['n_B']+r['n_R']+r['n_P']>=1,'Query eligibility')
            require(r['rank1_cosine']==lookup[r['query_scene_id']][score],'Stored selection score')
        newqueries.update(r['query_scene_id'] for r in saved)
        threshold=saved[-1]['rank1_cosine'];boundaries[name]={'threshold':threshold,'tied_population':sum(r[score]==threshold for r in candidates)}
    old=read(Path(cfg['viewer_root'])/'viewer_49689e157402015da2e68b52/config.json')
    for name in ['STANDARD_HIGH','STANDARD_LOW','NONLOCAL_HIGH','NONLOCAL_LOW']:require(vc['sets'][name]==old['sets'][name],'Original sets')
    ep=Path(identity['lineage']['embedding_path']);X=np.load(ep.parent/'vectors.npy',allow_pickle=False);gallery=read(Path(cfg['original_generation'])/'gallery_manifest.json')['body']['rows'];ids=[r['scene_id'] for r in gallery];index={s:i for i,s in enumerate(ids)};centers=np.array([[r['center_x'],r['center_y']] for r in gallery])
    inspected=0;empty_gallery_examples=0
    with threadpool_limits(limits=1):
        for sid in sorted(newqueries):
            i=index[sid];scores=X @ X[i];distance=np.linalg.norm(centers-centers[i],axis=1);data=read(v/'queries'/f'{sid}.json')['cmp_FM']
            for mode in ['standard','nonlocal']:
                ordered=sorted((j for j in range(9000) if j!=i and (mode=='standard' or distance[j]>=2000)),key=lambda j:(-float(scores[j]),ids[j]))
                require(data[mode]['candidate_count']==len(ordered),'Unfiltered gallery pool')
                for band in data[mode]['bands'].values():
                    for row in band:
                        j=ordered[row['rank']-1]
                        require(row['gallery_scene_id']==ids[j] and row['similarity']==float(scores[j]) and row['geographic_distance_m']==float(distance[j]),'Independent full gallery band')
                        inspected+=1;empty_gallery_examples+=counts[ids[j]]['object_count']==0
    return {'status':'PASS','original_sets_unchanged':True,'old_statistics_and_report_unchanged':True,'new_sets':2,'rows_per_set':100,'unique_nonempty_queries':len(newqueries),'independent_band_rows':inspected,'empty_gallery_band_rows_retained':empty_gallery_examples,'boundaries':boundaries}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('generation');a=p.parse_args();print(json.dumps(validate(a.generation),indent=2))
