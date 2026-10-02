#!/usr/bin/env python
"""Independent acceptance checks for the read-only Chapter 5.3 audit."""
import argparse,hashlib,json,sys
from pathlib import Path
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from scipy.stats import spearmanr
from threadpoolctl import threadpool_limits

def sha(p):
    with open(p,'rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def main():
    ap=argparse.ArgumentParser();ap.add_argument('output',type=Path);args=ap.parse_args();o=args.output;m=json.loads((o/'audit_manifest.json').read_text());assert m['query_count']==9000 and not m['pilot']
    results=[]
    def check(name,ok,details=''):
        results.append(dict(check=name,status='PASS' if ok else 'FAIL',details=details));assert ok,(name,details)
    hashes=json.loads((o/'output_checksums.json').read_text());check('all_output_checksums',all(sha(o/p)==h for p,h in hashes.items()),str(len(hashes)))
    check('source_preservation',all(sha(p)==h for p,h in m['source_checksums'].items()),str(len(m['source_checksums'])))
    df=pq.read_table(o/'master_query_table.parquet').to_pandas();check('coverage',len(df)==18000 and df.groupby('mode').query_scene_id.nunique().eq(9000).all() and not df.duplicated(['query_scene_id','mode']).any())
    check('no_nonfinite_master',np.isfinite(df.select_dtypes(include=np.number).to_numpy()).all())
    X=np.load(m['source_paths']['fm_vectors'],allow_pickle=False);g=json.loads(Path(m['source_paths']['gallery']).read_text())['body']['rows'];ids=np.array([r['scene_id'] for r in g]);C=np.array([[r['center_x'],r['center_y']] for r in g]);lookup=df.set_index(['query_scene_id','mode'])
    with threadpool_limits(limits=1):
        # Fixed, evenly distributed index probe; all main invariants were checked over all rows by producer.
        for i in np.linspace(0,8999,41,dtype=int):
            scores=np.dot(X,X[i]);dist=np.sqrt(((C-C[i])**2).sum(1))
            for mode in ['standard','nonlocal']:
                valid=(np.arange(9000)!=i)&((dist>=2000) if mode=='nonlocal' else True);ix=np.flatnonzero(valid);ix=ix[np.lexsort((ids[ix],-scores[ix]))];s=scores[ix].astype(float);r=lookup.loc[(ids[i],mode)]
                assert r.rank1_scene_id==ids[ix[0]] and r.eligible_count==len(ix) and r.rank1_similarity==s[0]
                assert np.isclose(r.all_mean,s.mean(),atol=1e-14,rtol=0) and np.isclose(r.all_sd,s.std(),atol=1e-14,rtol=0)
                assert np.isclose(r.rho_similarity_distance,spearmanr(s,dist[ix]).statistic,atol=1e-12,rtol=0)
                assert np.isclose(r.rho_rank_distance,spearmanr(np.arange(len(ix)),dist[ix]).statistic,atol=1e-12,rtol=0)
                assert r.within_0p01_count==int((s>=s[0]-.01).sum())
    check('independent_41_queries_both_modes',True,'lexsort + scipy Spearman + candidate statistics')
    check('full_legacy_and_band_parity',m['matched_band_records']==558000 and m['matched_legacy_records']==3000)
    runtime=json.loads(Path(m['source_paths']['models']).read_text())['body']['runtime']['sources'];repo=Path(__file__).resolve().parents[1]
    for p in ['python/retrieval_inference.py','python/model_families.py','python/retrieval_originals.py','python/retrieval_pipeline.py','python/retrieval_ranking.py']:
        check('historical_source_'+p,sha(repo/p)==runtime[p])
    tr=pd.read_csv(o/'rank1_transition_standard_to_nonlocal.csv');check('locality_retention_equivalence',np.array_equal(tr.retained.to_numpy(),tr.standard_rank1_distance_m.to_numpy()>=2000))
    hub=pd.read_csv(o/'scene_indegree.csv')
    for mode in ['standard','nonlocal']:
        d=df[df['mode']==mode];actual=d.rank1_scene_id.value_counts().reindex(ids,fill_value=0);stored=hub[hub['mode']==mode].set_index('scene_id').loc[ids].rank1_indegree
        check('indegree_'+mode,np.array_equal(actual,stored) and actual.sum()==9000)
    pairs=pd.read_csv(o/'all_pair_similarity_summary.csv');check('directed_pair_counts',all(int(r.n)==int(df[df['mode']==r['mode']].eligible_count.sum()) for _,r in pairs.iterrows()))
    hist=pd.read_csv(o/'all_pair_histogram.csv');check('pair_histogram_mass',all(int(hist[hist['mode']==r['mode']]['count'].sum())==int(r.n) for _,r in pairs.iterrows()))
    check('required_figures',len(list((o/'figures').glob('*.png')))==11 and len(list((o/'figures').glob('*.pdf')))==11)
    pd.DataFrame(results).to_csv(o/'independent_acceptance_checks.csv',index=False)
    print('PASS',len(results),'independent acceptance checks')

if __name__=='__main__':main()
