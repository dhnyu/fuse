"""Authorized supplemental band evidence from accepted normalized vectors only.

Band positions copied from 10c02e4:tools/retrieval_inspector/inspector.py:87.
Cosine/filter/sort operations match the immutable S10 retrieval_ranking.rank.
No checkpoint, inference, geometry, preprocessing or stage execution imports.
"""
import numpy as np
from retrieval_artifacts import require


def band_ranks(candidate_count):
    require(candidate_count >= 31, 'BAND_CANDIDATES')
    middle_start = (candidate_count - 10) // 2 + 1
    result = {'most':[1], 'top':list(range(2,12)),
              'middle':list(range(middle_start,middle_start+10)),
              'bottom':list(range(candidate_count-9,candidate_count+1))}
    flat=[r for ranks in result.values() for r in ranks]
    require(len(flat)==len(set(flat))==31, 'BAND_OVERLAP')
    return result


def reconstruct(vectors, gallery, queries, model, formal_rows):
    ids=[r['scene_id'] for r in gallery]
    require(ids==sorted(set(ids)) and vectors.ndim==2 and vectors.shape[0]==len(ids), 'BAND_GALLERY')
    require(vectors.dtype==np.float32 and np.isfinite(vectors).all() and
            np.allclose(np.linalg.norm(vectors,axis=1),1,rtol=0,atol=2e-6), 'BAND_NORMALIZED')
    centers=np.array([[r['center_x'],r['center_y']] for r in gallery],dtype=np.float64)
    require(np.isfinite(centers).all(), 'BAND_CENTERS')
    index={s:i for i,s in enumerate(ids)}; result={}
    formal={(r['query_id'],r['retrieval_mode'],r['rank']):r for r in formal_rows}
    require(len(formal)==len(formal_rows)==len(queries)*2*50,'BAND_FORMAL_COUNT')
    for query in queries:
        qi=index[query['scene_id']]
        scores=vectors @ vectors[qi]
        require(np.isfinite(scores).all(), 'BAND_SCORES')
        distances=np.linalg.norm(centers-centers[qi],axis=1)
        ordered=np.argsort(-scores,kind='stable')
        result[query['scene_id']]={}
        for mode in ('standard','nonlocal'):
            eligible=[int(i) for i in ordered if i!=qi and (mode=='standard' or distances[i]>=2000.0)]
            def row(position):
                i=eligible[position-1]
                return {'query_id':query['scene_id'],'model_id':model,'retrieval_mode':mode,
                        'rank':position,'gallery_scene_id':ids[i],'similarity':float(scores[i]),
                        'geographic_distance_m':float(distances[i]),'excluded_by_nonlocal':bool(distances[i]<2000.0)}
            for rank in range(1,51):
                actual=row(rank); expected=formal[query['scene_id'],mode,rank]
                require(all(expected[k]==v for k,v in actual.items()), 'BAND_FORMAL_TOP50_MISMATCH')
            result[query['scene_id']][mode]={'candidate_count':len(eligible),
                'bands':{name:[row(rank) for rank in ranks] for name,ranks in band_ranks(len(eligible)).items()}}
    return result
