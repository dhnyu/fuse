"""Production-reader and block-engine failures; no production I/O or full fits."""
from pathlib import Path
import numpy as np
import pyarrow.parquet as pq
import pytest
from scipy.stats import spearmanr
from s11_artifacts import context,load_bundle,publish,write_json
from s11_descriptors import raster_descriptors,dictionary,make_plan,write_descriptor_tables,validate_records
from s11_alignment import alignment_block,validate_metrics

def raster():
    f=np.zeros((22,100,100),np.float32);f[0]=1
    return [f,np.ones((100,100),np.float32),np.ones((100,100),np.uint8),
        np.full((17,17),10,np.float32),np.ones((17,17),np.float32),np.ones((17,17),np.uint8)]

def test_partial_raw_raster_weighted_definition():
    a=raster();a[0][0,0,0]=0;a[0][1,0,0]=1;a[1][0,0]=.5
    a[3][0,0]=20;a[4][0,0]=.5
    values,qc=raster_descriptors(*a)
    assert values['landcover_composition']['value'][1]==.5/9999.5
    mu=(2880+10)/288.5
    assert values['mean_elevation']['value']==mu
    assert values['elevation_variability']['value']==pytest.approx(np.sqrt((288*(10-mu)**2+.5*(20-mu)**2)/288.5))
    assert qc['lc_partial_cells']==qc['dem_partial_cells']==1

@pytest.mark.parametrize('failure',['shape','mask','invalid_lc_fill','bad_lc_sum','dem_fill','dem_valid_nodata','support'])
def test_raw_raster_contract_fails_closed(failure):
    a=raster()
    if failure=='shape':a[0]=a[0][:21]
    if failure=='mask':a[2][0,0]=0
    if failure=='invalid_lc_fill':a[1][0,0]=0;a[2][0,0]=0
    if failure=='bad_lc_sum':a[0][0,0,0]=.7
    if failure=='dem_fill':a[4][0,0]=0;a[5][0,0]=0
    if failure=='dem_valid_nodata':a[3][0,0]=-32767
    if failure=='support':a[4][0,0]=np.nan
    with pytest.raises(ValueError):raster_descriptors(*a)

def test_empty_raster_null_support():
    a=raster();a[0][:]=0;a[1][:]=0;a[2][:]=0;a[3][:]=-32767;a[4][:]=0;a[5][:]=0
    d,_=raster_descriptors(*a)
    assert all(v['value'] is None and v['null_reason']=='no_valid_raster_support' and v['valid_count']==0 for v in d.values())

def test_frozen_dictionary_exact_22_and_17_paths():
    d=dictionary()
    assert len(d)==22
    poi=next(x for x in d if x['id']=='poi_l2_composition')
    assert len(poi['category_keys'])==17 and all('/' in k for k in poi['category_keys'])

def test_all_null_compositions_roundtrip_and_dictionary_length(tmp_path):
    registry=dictionary();values={}
    for d in registry:
        values[d['id']]={'value':0 if d['empty']=='zero' else None,'null_reason':None if d['empty']=='zero' else 'no_support',
            'total_count':0,'valid_count':0,'invalid_count':0}
    rows=[{'scene_id':'empty','descriptors':values,'qc':{}}]
    validate_records(rows,['empty']);write_descriptor_tables(tmp_path,rows)
    assert pq.read_table(tmp_path/'descriptors.parquet')['relation_composition'].to_pylist()==[None]
    values['relation_composition'].update(value=[1.,0.],null_reason=None,category_keys=['SN','INC'])
    with pytest.raises(ValueError,match='COMPOSITION'):validate_records(rows,['empty'])

def test_immutable_receipt_last_reuse_and_corruption(tmp_path):
    ctx={'root':str(tmp_path),'scope':'pilot'}
    def build(stage):
        write_json(stage/'data.json',{'valid':True})
        return {'count':1}
    m=publish(ctx,'fixture','one',build)
    assert publish(ctx,'fixture','one',lambda stage:pytest.fail('must reuse'))==m
    (Path(m).parent/'data.json').write_text('corrupt')
    with pytest.raises(ValueError,match='HASH'):load_bundle(m)
    with pytest.raises(ValueError,match='HASH'):publish(ctx,'fixture','one',build)

def test_full_context_fails_without_authorization(monkeypatch):
    monkeypatch.delenv('FUSE_S11_FULL_EXECUTION',raising=False)
    with pytest.raises(ValueError,match='NOT_AUTHORIZED'):context('full')

def test_descriptor_pilot_cannot_expand_before_read():
    ids=[f'scene_{i:04d}' for i in range(17)]
    with pytest.raises(ValueError,match='PILOT_CAP'):make_plan({'scope':'pilot'},ids,ids)

def test_production_block_support_scipy_and_exact_boundary():
    rng=np.random.default_rng(11);x=rng.normal(size=(80,256)).astype(np.float32);x/=np.linalg.norm(x,axis=1)[:,None]
    # Retrieval ties use lexical order. Average ties belong to Spearman only.
    x[2]=x[1];centers=np.column_stack([np.arange(80)*2000,np.zeros(80)])
    ids=[f'scene_{i:03d}' for i in range(80)];v=np.arange(80)%7;ok=np.ones(80,bool);ok[[1,3]]=False
    arrays={'scalar':(v,ok),'constant':(np.ones(80),ok),'undefined':(v,np.zeros(80,bool))}
    rows,bands=alignment_block(x,centers,ids,[0,1],arrays)
    validate_metrics(rows,ids,[0,1],list(arrays))
    row=next(r for r in rows if r['query_index']==0 and r['mode']=='nonlocal' and r['descriptor']=='scalar' and r['region']=='rho')
    mask=ok.copy();mask[0]=False
    from representation_analysis import cosine_block
    ref=spearmanr(cosine_block(x,[0])[0,mask],abs(v[mask]-v[0])).statistic
    assert row['value']==pytest.approx(ref,abs=1e-14)
    assert row['total_count']==79 # equality at 2km included
    assert all(r['value'] is None for r in rows if r['descriptor']=='undefined')
    assert all(r['null_reason']=='constant_difference' for r in rows if r['descriptor']=='constant' and r['region']=='rho' and r['query_index']==0)
    assert len(bands)==2*2*31
