"""Small analytic fixtures for approved dissertation 5.4, no real inference."""
import hashlib
import json
from pathlib import Path
import shutil

import numpy as np
import pytest
from scipy.stats import spearmanr
from threadpoolctl import threadpool_limits

from representation_analysis import (ROOT, band_indices, band_positions, cosine_block,
    descriptor_differences, eligibility, load_frozen_contract, query_summary,
    select_illustrations, spearman_rows, summarize_bands)


def test_frozen_contract_and_unapproved_edits(tmp_path):
    c, _ = load_frozen_contract()
    assert len(c['descriptors']) == 22
    assert sum(x['kind']=='compositional' for x in c['descriptors']) == 7
    assert len(c['umap']['panels']) == 6
    assert c['scope']['full_analysis_authorized'] is False
    for f in ['s11_representation_analysis.json','s11_representation_analysis.lock.json']:
        (tmp_path/'config').mkdir(exist_ok=True)
        shutil.copy(ROOT/'config'/f,tmp_path/'config'/f)
    p=tmp_path/'config/s11_representation_analysis.json'
    v=json.loads(p.read_text());v['umap']['n_neighbors']=15;p.write_text(json.dumps(v))
    with pytest.raises(ValueError,match='FROZEN_CONTRACT_HASH'):
        load_frozen_contract(tmp_path,verify_dissertation=False)


def test_native_batched_dot_exact_reference_and_block_cap():
    x=np.random.default_rng(11).normal(size=(120,256)).astype('float32')
    x/=np.linalg.norm(x,axis=1,keepdims=True)
    x[6]=x[5]
    q=np.array([0,5,7,41])
    before=x.copy()
    with threadpool_limits(limits=1): reference=np.stack([x@x[i] for i in q])
    assert np.array_equal(cosine_block(x,q),reference)
    assert np.array_equal(np.concatenate([cosine_block(x,q[:1]),cosine_block(x,q[1:])]),reference)
    assert np.array_equal(x,before)
    with pytest.raises(ValueError,match='BOUNDED'):cosine_block(x,np.arange(33))


def test_strict_boundary_and_rank_bands_with_lexical_ties():
    centers=np.column_stack([np.arange(120)*500.,np.zeros(120)])
    centers[1,0]=np.nextafter(2000.,0.)
    centers[2,0]=np.nextafter(2000.,np.inf)
    distance,modes=eligibility(centers,[0])
    assert not modes['nonlocal'][0,1]
    assert modes['nonlocal'][0,2] and modes['nonlocal'][0,4]
    assert distance[0,4]==2000 and modes['standard'].sum()==119
    scores=np.ones((1,120),dtype='float32')
    for mode,mask in modes.items():
        selected=band_indices(scores,mask)
        expected=np.flatnonzero(mask[0])
        for key,positions in band_positions(mask.sum(1)).items():
            assert np.array_equal(selected[key][0],expected[positions[0]-1])
    bands=band_positions(np.array([8999,9000]))
    assert bands['middle'][0].tolist()==list(range(4495,4505))
    assert bands['middle'][1].tolist()==list(range(4496,4506))
    assert bands['lower'][0].tolist()==list(range(8990,9000))
    with pytest.raises(ValueError,match='OVERLAPPING'):band_positions(np.array([31]))


def test_differences_and_pair_missingness():
    x=np.array([[1.,0],[0,1],[.5,.5],[np.nan,np.nan]])
    d,valid=descriptor_differences(x,[0,3],[True,True,True,False])
    assert d[0,1]==pytest.approx(np.sqrt(2))
    assert d[0,2]==pytest.approx(np.sqrt(.5))
    assert not valid[1].any() and not valid[:,3].any()
    scalar,ok=descriptor_differences(np.array([1.,4.,np.nan]),[0],[True,True,False])
    assert scalar[0,1]==3 and not ok[0,2]
    with pytest.raises(ValueError,match='COMPOSITION'):
        descriptor_differences(np.array([[.3,.4]]),[0],[True])


def test_query_spearman_average_ties_rerank_and_nulls():
    s=np.array([[.9,.8,.8,.5,.1],[.9,.8,.8,.5,.1],[1,1,1,1,1],[1,2,3,4,5],[1,2,3,4,5]])
    d=np.array([[1,2,2,4,5],[5,1,1,4,2],[0,1,2,3,4],[1,1,1,1,1],[0,1,2,3,4]])
    eligible=np.ones(s.shape,bool); eligible[1,[0,3]]=False
    valid=np.ones(s.shape,bool);valid[4,1:]=False
    rows=spearman_rows(s,d,eligible,valid)
    assert rows[0]['rho']==pytest.approx(-1)
    kept=eligible[1]&valid[1]
    assert rows[1]['rho']==pytest.approx(spearmanr(s[1,kept],d[1,kept]).statistic)
    assert [r['null_reason'] for r in rows[2:]]==['constant_similarity','constant_difference','fewer_than_two_valid_pairs']
    assert all(r['rho'] is None for r in rows[2:])
    json.dumps(rows,allow_nan=False)
    none=spearman_rows(s[:1],d[:1],eligible[:1],np.zeros_like(valid[:1]))[0]
    assert none['rho'] is None and none['valid_count']==0 and none['invalid_count']==5


def test_masked_block_spearman_matches_independent_query_references():
    rng=np.random.default_rng(112)
    scores=rng.integers(-2,4,size=(7,40)).astype(float)
    diff=rng.integers(0,5,size=(7,40)).astype(float)
    eligible=rng.random((7,40))>.2
    valid=rng.random((7,40))>.25
    result=spearman_rows(scores,diff,eligible,valid)
    for i,row in enumerate(result):
        mask=eligible[i]&valid[i]
        assert row['rho']==pytest.approx(spearmanr(scores[i,mask],diff[i,mask]).statistic,abs=1e-15)


def test_no_refill_fixed_band_and_equal_weight_type7():
    d=np.arange(100,dtype=float)[None,:]
    valid=np.ones_like(d,bool);valid[0,1]=False
    indices=band_indices(-d,np.ones_like(d,bool))
    result=summarize_bands(d,valid,indices)
    assert result['upper'][0]['mean_difference']==pytest.approx(np.mean(np.arange(2,11)))
    assert result['upper'][0]['valid_count']==9
    assert result['upper'][0]['invalid_count']==1
    summary=query_summary([0.,1.,2.,10.,None])
    assert summary['q1']==.75 and summary['median']==1.5 and summary['q3']==4.
    assert summary['iqr']==3.25 and summary['invalid_count']==1
    assert query_summary([None])['median'] is None


def test_predeclared_hash_illustrations_no_input_order_dependency():
    xy=np.array([[x,y] for x in range(5) for y in range(5)],float)
    ids=[f's{i:03}' for i in range(len(xy))]
    a=select_illustrations(xy,ids)
    b=select_illustrations(xy[::-1],ids[::-1])
    assert a==b and len(a['scenes'])==9
    for row in a['scenes']:
        assert row['selection_sha256']==hashlib.sha256(('20260904'+row['scene_id']).encode()).hexdigest()
    collapsed=select_illustrations(np.zeros((4,2)),ids[:4])
    assert len(collapsed['scenes'])==1 and collapsed['scenes'][0]['cell_x']==2


def test_no_scientific_execution_imports():
    import ast
    tree=ast.parse((ROOT/'python/representation_analysis.py').read_text())
    imports=[]
    for node in ast.walk(tree):
        if isinstance(node,ast.ImportFrom):imports.append(node.module)
        elif isinstance(node,ast.Import):imports.extend(n.name for n in node.names)
    assert not any(any(x in name for x in ['torch','evaluation','model','training','inference']) for name in imports)


def test_pilot_cli_rejects_full_execution():
    import subprocess
    import sys
    result=subprocess.run([sys.executable,str(ROOT/'scripts/pilot_s11_representation.py'),'--full'],capture_output=True,text=True)
    assert result.returncode==2 and 'unrecognized arguments: --full' in result.stderr
