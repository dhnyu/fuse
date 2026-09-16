import ast
import importlib.util
from pathlib import Path
import sys
import numpy as np
import pytest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/retrieval_inspector/supplemental'))
from bands import band_ranks,reconstruct
from retrieval_ranking import rank


def fixture():
    rng=np.random.default_rng(17);v=rng.normal(size=(120,8)).astype('float32');v/=np.linalg.norm(v,axis=1,keepdims=True)
    v[5]=v[6] # exact ties; sorted IDs determine order
    g=[{'scene_id':f's{i:03d}','center_x':float(i*500),'center_y':0.} for i in range(120)]
    m={'configuration_id':'model','group':'OFAT','checkpoint_id':'ck'}
    return v,g,[g[0]],m


@pytest.mark.parametrize('n',[8999,9000,8950,100,99])
def test_exact_legacy_band_positions(n):
    b=band_ranks(n);assert b['most']==[1];assert b['top']==list(range(2,12))
    assert b['middle']==list(range((n-10)//2+1,(n-10)//2+11))
    assert b['bottom']==list(range(n-9,n+1))
    assert len(set(sum(b.values(),[])))==31


def test_full_eligible_sort_and_top50_exact():
    v,g,q,m=fixture();before=v.copy();formal=rank(v,g,q,m,{})
    result=reconstruct(v,g,q,'model',formal)
    scores=v@v[0]
    ordered=sorted(range(1,120),key=lambda i:(-float(scores[i]),g[i]['scene_id']))
    for mode in ['standard','nonlocal']:
        eligible=[i for i in ordered if mode=='standard' or i*500>=2000]
        value=result['s000'][mode];assert value['candidate_count']==len(eligible)
        assert value['candidate_count']==(119 if mode=='standard' else 116)
        for name,positions in band_ranks(len(eligible)).items():
            assert [r['gallery_scene_id'] for r in value['bands'][name]]==[g[eligible[p-1]]['scene_id'] for p in positions]
            for row in value['bands'][name]:
                if row['rank']<=50:
                    reference=next(r for r in formal if r['retrieval_mode']==mode and r['rank']==row['rank'])
                    assert all(reference[k]==v for k,v in row.items())
    assert np.array_equal(v,before)
    assert 's004' in [g[i]['scene_id'] for i in ordered if i*500>=2000] # equality retained


def test_ties_exact_scene_id_order():
    v,g,q,m=fixture();v[:]=0;v[:,0]=1
    r=reconstruct(v,g,q,'model',rank(v,g,q,m,{}))['s000']['standard']
    assert r['bands']['most'][0]['gallery_scene_id']=='s001'
    assert [x['gallery_scene_id'] for x in r['bands']['bottom']]==[f's{i:03d}' for i in range(110,120)]


@pytest.mark.parametrize('fault',['score','missing','unnormalized'])
def test_invalid_evidence_fail_closed(fault):
    v,g,q,m=fixture();f=rank(v,g,q,m,{})
    if fault=='score':f[0]['similarity']+=.001
    elif fault=='missing':f.pop()
    else:v[0]*=2
    with pytest.raises(ValueError):reconstruct(v,g,q,'model',f)


def test_no_scientific_execution_imports():
    module=ROOT/'tools/retrieval_inspector/supplemental/bands.py'
    tree=ast.parse(module.read_text());imports=[]
    for node in ast.walk(tree):
        if isinstance(node,ast.ImportFrom):imports.append(node.module)
        if isinstance(node,ast.Import):imports.extend(a.name for a in node.names)
    assert set(imports)=={'numpy','retrieval_artifacts'}


def test_band_layout_and_raster_contract():
    f=ROOT/'tools/retrieval_inspector/supplemental'
    js=(f/'bands_app.js').read_text();html=(f/'bands.html').read_text()
    assert 'id="comparison" class="comparison"' in html
    for value in ['Rank 1 / Most similar','strip-spacer','data-band','data-index','renderBandColumns']:
        assert value in js
    assert "...['top','middle','bottom']" in js
    assert 'imageSmoothingEnabled=false' in js and 'devicePixelRatio' in js
    assert 'img.naturalWidth!==100' in js and 'img.naturalWidth!==17' in js
    assert '[data-raster="DEM"] img{image-rendering:auto}' in (f/'bands.css').read_text()
    assert 'host.append(details(s,i))' in js # unchanged thematic renderer reused
