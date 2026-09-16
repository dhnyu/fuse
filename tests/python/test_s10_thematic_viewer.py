"""Stored entity -> paint binding and literal augmentation shell reuse."""
import copy
import importlib.util
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

import pytest
import torch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/retrieval_inspector/supplemental'))
import thematic as t


def fixture():
    sample={'scene_id':'scene','lineage':{'parent':{'payload_sha256':'p3sha'}},
            'entities':{'local_entity_id':torch.tensor([4,8,10,15]),'entity_type':torch.tensor([0,0,1,2]),
                        'building_row_index':torch.tensor([0,1]),'building_category':torch.tensor([[0,1],[2,0]]),
                        'road_row_index':torch.tensor([2]),'road_category':torch.tensor([[1,0]]),
                        'poi_row_index':torch.tensor([3]),'poi_category':torch.tensor([[0]*6])}}
    svg='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 500 500"><rect width="500" height="500"/><g transform="translate(0 500) scale(1 -1)"><path fill="#667085" d="M 1,1 L 2,2 z"/><g><path fill="#667085" d="M 2,3 L 4,5 z"/></g><polyline stroke="#e4a11b" points="1,2 4,8"/><circle fill="#c83e63" cx="5" cy="7" r="1"/></g></svg>'
    names={a:['category0','category1','Unknown / missing','Masked'] for a in ['A9','A11','ROAD_RANK','CLASS_L1']}
    record={'source_scene_data_identity':'p3sha'}
    return sample,svg,record,names,'inputsha'


@pytest.mark.parametrize('title,indices,categories',[
    ('POI categories · L1',[3],[0]),('Building use',[0,1],[0,2]),
    ('Building structure',[0,1],[1,0]),('Road rank',[2],[1])])
def test_exact_membership(title,indices,categories):
    result=t.bind(*fixture())['maps'][title]
    assert [e['svg_index'] for e in result['entities']]==indices
    assert [e['category_index'] for e in result['entities']]==categories
    assert sum(e['count'] for e in result['legend'])==len(indices)
    assert all(e['color']==t.color(e['category_index'],4) for e in result['entities'])


def test_unknown_gray_no_imputation():
    d=t.bind(*fixture())['maps']['Building use']['entities'][1]
    assert d['label']=='Unknown / missing' and d['color']=='#999999'
    assert t.color(3,4)=='#999999'


def test_lane_not_inferred_from_standardized_values():
    args=fixture();args[0]['entities']['road_numerical']=torch.tensor([[1.234]])
    d=t.bind(*args)
    assert not d['road_lane']['available']
    assert d['road_lane']['reason']==t.LANE_UNAVAILABLE
    assert 'Road lane' not in d['maps']


def test_source_and_geometry_not_mutated():
    args=fixture();before=copy.deepcopy(args)
    t.bind(*args)
    assert args[1:]==before[1:]
    assert all(torch.equal(v,before[0]['entities'][k]) for k,v in args[0]['entities'].items())


@pytest.mark.parametrize('fault',['parent','count','order','type','row','category','frame'])
def test_invalid_source_fails_closed(fault):
    s,svg,r,n,h=fixture()
    if fault=='parent':r['source_scene_data_identity']='stale'
    if fault=='count':s['entities']['local_entity_id']=torch.tensor([4])
    if fault=='order':s['entities']['local_entity_id']=torch.tensor([8,4,10,15])
    if fault=='type':s['entities']['entity_type'][0]=1
    if fault=='row':s['entities']['building_row_index']=torch.tensor([1,0])
    if fault=='category':s['entities']['road_category'][0,0]=40
    if fault=='frame':svg=svg.replace('0 0 500 500','0 0 400 400')
    with pytest.raises(ValueError):t.bind(s,svg,r,n,h)


def test_augmentation_layout_contract():
    folder=ROOT/'tools/retrieval_inspector/supplemental'
    html=(folder/'index.html').read_text();css=(folder/'style.css').read_text();builder=(folder/'build.py').read_text()
    live=(ROOT/'tools/augmentation_inspector/inspector.py').read_text()
    for token in ['class="brand"','class="controls"','class="control"','class="case-meta"','class="section"']:
        assert token in live
        assert token in (html+(folder/'app.js').read_text())
    assert "className='panel'" in live and "className='panel'" in (folder/'app.js').read_text()
    assert "augmentation_text.split('<style>',1)[1].split('</style>',1)[0]" in builder
    assert '<link rel="stylesheet" href="augmentation.css">' in html
    assert [html.index(x) for x in ['id="vectorGrid"','id="rasterGrid"','id="summaryGrid"','id="detailGrid"']]==sorted(html.index(x) for x in ['id="vectorGrid"','id="rasterGrid"','id="summaryGrid"','id="detailGrid"'])
    assert 'repeat(6,minmax(0,1fr))' in css
    assert all(x not in html for x in ['Focused inspection','class="strip"','summary-strip','hero'])
    assert 'function chart(' not in (folder/'app.js').read_text()


def test_no_geometry_reconstruction_imports():
    source=(ROOT/'tools/retrieval_inspector/supplemental/thematic.py').read_text()
    assert all(x not in source for x in ['import shapely','import geopandas','import model_data','import retrieval_inference','import retrieval_ranking','torch.load','nearest'])


@pytest.mark.parametrize('raw',[None,0,1,2,3,4,5,3.5])
def test_raw_lane_assignment_no_inverse_scaling(raw):
    s,svg,r,n,h=fixture()
    s['entities']['road_numerical']=torch.tensor([[999.123]])
    source={'parent':s['lineage']['parent'],'rows':[{'scene_id':'scene','local_entity_id':10,'LANES':raw}]}
    result=t.bind_lanes(s,source)
    entity=result['entities'][0]
    assert entity['entity_id']==10 and entity['svg_index']==2 and entity['raw_value']==raw
    assert result['legend'][0]['count']==1
    if raw is None:assert entity['color']=='#999999' and entity['label']=='Unknown / unavailable'
    else:assert str(raw).rstrip('.0') in entity['label'] if raw else entity['label']=='0 lanes'


@pytest.mark.parametrize('fault',['parent','entity','scene'])
def test_lane_source_mismatch_rejected(fault):
    s,*_=fixture()
    source={'parent':dict(s['lineage']['parent']),'rows':[{'scene_id':'scene','local_entity_id':10,'LANES':3}]}
    if fault=='parent':source['parent']['payload_sha256']='stale'
    if fault=='entity':source['rows'][0]['local_entity_id']=4
    if fault=='scene':source['rows'][0]['scene_id']='other'
    with pytest.raises(ValueError):t.bind_lanes(s,source)


def test_lane_payload_sha_rejection(tmp_path):
    import lane_source
    import pyarrow as pa
    import pyarrow.parquet as pq
    from retrieval_artifacts import file_hash
    index=tmp_path/'scene_to_shard.parquet'
    pq.write_table(pa.Table.from_pylist([{'scene_id':'scene','branch_id':'branch','cache_id':'cache','payload_filename':'branch.tar','payload_sha256':'incorrect'}]),index)
    (tmp_path/'shards/branch').mkdir(parents=True)
    (tmp_path/'shards/branch/branch.tar').write_bytes(b'corrupt')
    model={'body':{'config':{'source_pins':{str(index):file_hash(index)}},'roots':{'p3':str(tmp_path)},'parents':{'scene_cache_id':'cache'}}}
    with pytest.raises(ValueError,match='LANE_PAYLOAD_HASH'):lane_source.load_lanes(model,{'scene'})
