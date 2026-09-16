"""UI-only display tests: no model/checkpoint/scientific stage execution."""
import ast
import importlib.util
from pathlib import Path

import numpy as np
import pytest
import torch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('supplemental_viewer', ROOT/'tools/retrieval_inspector/supplemental/build.py')
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)


def sample():
    return {'scene_id':'scene', 'scene_center_5186':torch.tensor([1.,2.]),
            'entities':{**{k+'_row_index':torch.arange(2) for k in ['building','road','poi']},
                        'building_category':torch.tensor([[0,1],[1,1]]),
                        'road_category':torch.tensor([[0,0],[0,0]]),
                        'poi_category':torch.tensor([[0]*6,[1]*6])},
            'edges':{'edge_index':torch.tensor([[0,1],[1,0]]),'relation_mask':torch.tensor([1,1])},
            'rasters':{'landcover_class_fraction':torch.cat([torch.ones(1,100,100)*.25,torch.ones(1,100,100)*.75,torch.zeros(20,100,100)]),
                       'landcover_valid_mask':torch.ones(100,100,dtype=torch.uint8),
                       'landcover_valid_support':torch.ones(100,100),
                       'dem_standardized_mean':torch.zeros(17,17),
                       'dem_valid_mask':torch.ones(17,17,dtype=torch.uint8)}}


def test_summary_values_and_input_unchanged():
    s=sample(); before=s['rasters']['landcover_class_fraction'].clone()
    d=v.scene_display(s,{a:['a','Unknown / missing'] for a in ['A9','A11','ROAD_RANK','CLASS_L1']})
    assert d['charts']['Land cover composition'] == [
        {'label':'LC 1','value':25.,'color':v.PALETTE[0]}, {'label':'LC 2','value':75.,'color':v.PALETTE[1]}]
    assert d['charts']['Building structure'] == [{'label':'Unknown / missing','value':2}]
    assert d['ordered_edges']==2 and d['counts']=={'building':2,'road':2,'poi':2}
    assert torch.equal(before,s['rasters']['landcover_class_fraction'])
    assert d==v.scene_display(s,{a:['a','Unknown / missing'] for a in ['A9','A11','ROAD_RANK','CLASS_L1']})


def test_category_unknown_and_index_failure():
    assert v.counts([2,0,2],['a','b','Unknown']) == [{'label':'Unknown','value':2},{'label':'a','value':1}]
    with pytest.raises(ValueError):v.counts([3],['a'])


def test_vocabulary_order():
    entries=[{'attribute':a,'source_order':i,'category_key':str(i)} for a in ['A9','A11','ROAD_RANK','CLASS_L1'] for i in [2,0,1]]
    assert v.labels({'entries':entries})['A9']==['0','1','2','Unknown / missing','Masked']


def ranking():
    return [{'model_id':'m','query_id':'q','retrieval_mode':mode,'rank':i,'gallery_scene_id':str(i),'similarity':1/i} for mode in ['standard','nonlocal'] for i in range(1,51)]


def test_top5_reads_exact_rows():
    rows=ranking();result=v.top_five(rows,['q'],'m')
    assert result['q','standard']==rows[:5]
    assert result['q','nonlocal']==rows[50:55]


@pytest.mark.parametrize('change',['missing','duplicate','model','query','mode'])
def test_invalid_display_rows_fail(change):
    rows=ranking()
    if change=='missing':rows.pop(0)
    elif change=='duplicate':rows[1]['rank']=1
    else:rows[0][{'model':'model_id','query':'query_id','mode':'retrieval_mode'}[change]]='wrong'
    with pytest.raises(ValueError):v.top_five(rows,['q'],'m')


def test_invalid_raster_fail():
    s=sample();s['rasters']['dem_standardized_mean'][0,0]=float('nan')
    with pytest.raises(ValueError,match='FINITE'):v.scene_display(s,{a:['a','b'] for a in ['A9','A11','ROAD_RANK','CLASS_L1']})


def test_import_boundary_no_scientific_fallback():
    tree=ast.parse((ROOT/'tools/retrieval_inspector/supplemental/build.py').read_text())
    imports=[n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
    assert not any(x and any(y in x for y in ['training','inference','ranking','evaluation','model_data','encoder','lineage']) for x in imports)
    assert [x for x in imports if x and x.startswith('retrieval_')]==['retrieval_artifacts']
    js=(ROOT/'tools/retrieval_inspector/supplemental/app.js').read_text()
    assert 'crypto.subtle.digest' in js and 'Artifact checksum mismatch' in js
    assert all(x not in js for x in ['checkpoint.pt','cosine_similarity','geometry_fourier','nonlocal_m'])


def test_separate_publication_and_immutable_writes(tmp_path):
    with pytest.raises(ValueError,match='SEPARATE_ROOT'):v.build(tmp_path,tmp_path/'pages')
    p=tmp_path/'asset';v.publish_bytes(p,b'old')
    with pytest.raises(ValueError,match='IMMUTABLE_COLLISION'):v.publish_bytes(p,b'new')
    assert p.read_bytes()==b'old'
