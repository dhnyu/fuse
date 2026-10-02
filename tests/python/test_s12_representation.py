"""Bounded analytic S12 fixtures. No full execution and no P3 access."""
import copy
import json
from pathlib import Path
import numpy as np
import pytest
import jsonschema
from s12_runtime import configuration,block_specs,require_spec,context,identity,ROOT,read_json
from s12_publication import cross_rows,contrast_rows,validate_cross_rows,render_figures,write_rows
from s12_alignment import alignment_block
from s11_independent_oracle import independent_difference
from representation_analysis import descriptor_differences,query_summary


def test_contract_exact_bindings_and_schema_rejects_change():
    c,lock=configuration();assert len(c['models'])==17 and len(c['computed_models'])==16
    assert c['model_order'][0]=='cmp_FM' and c['population']['size']==9000
    for mutation in ('protocol','models','execution'):
        bad=copy.deepcopy(c)
        if mutation=='protocol':bad[mutation]['rho_atol']=1e-5
        elif mutation=='models':bad[mutation][1]['selected_epoch']+=1
        else:bad[mutation]['query_block_size']=33
        with pytest.raises(jsonschema.ValidationError):jsonschema.validate(bad,read_json(ROOT/'config/schemas/s12_representation_alignment.schema.json'))


def test_plan_is_bounded_fm_excluded_and_four_checks_covered():
    c,_=configuration();full=block_specs('full');pilot=block_specs('pilot')
    assert len(full)==16*282 and len(pilot)==12
    assert all(0<len(s['positions'])<=32 and s['configuration_id']!='cmp_FM' for s in full)
    for key in c['execution']['pilot_models']:
        qs=[q for s in pilot if s['configuration_id']==key for q in s['positions']]
        assert len(qs)==72 and set(c['protocol']['independent_queries'])<=set(qs)
    with pytest.raises(ValueError,match='BLOCK_SCOPE'):require_spec({'scope':'pilot'},{**pilot[0],'configuration_id':'cmp_FM'})
    with pytest.raises(ValueError,match='BLOCK_SCOPE'):require_spec({'scope':'pilot'},full[1])


def test_full_execution_requires_explicit_authorization(monkeypatch):
    monkeypatch.delenv('FUSE_S12_FULL_EXECUTION',raising=False)
    with pytest.raises(ValueError,match='FULL_NOT_AUTHORIZED'):context('full')


def test_model_wrapper_keeps_constant_similarity_null_and_fixed_slots():
    # >31 candidates required by frozen disjoint rank regions.
    n=64;ids=[f's{i:04}' for i in range(n)];x=np.zeros((n,256),np.float32);x[:,0]=1
    centers=np.column_stack([np.arange(n)*2100.,np.zeros(n)])
    v=np.arange(n,dtype=np.float64);valid=np.ones(n,bool);valid[1:11]=False
    rows,bands=alignment_block(x,centers,ids,[0],{'example':(v,valid)})
    rho=[r for r in rows if r['region']=='rho'];assert all(r['value'] is None and r['null_reason']=='constant_similarity' for r in rho)
    upper=[r for r in rows if r['region']=='upper'];assert all(r['valid_count']==1 and r['value']==11 for r in upper)
    assert all(r['candidate_scene_id']==ids[r['rank']] for r in bands)


def test_independent_ordered_oracle_and_type7():
    v=np.random.default_rng(19).dirichlet(np.ones(17),50).astype('float64')
    distance,_=descriptor_differences(v,[0],np.ones(50,bool))
    assert np.array_equal(distance[0].view('uint64'),independent_difference(v,0).view('uint64'))
    q=query_summary([1.,2.,4.,None]);assert q['median']==2 and q['q1']==1.5 and q['q3']==3


def synthetic():
    c,_=configuration();summaries={};provenance={}
    for i,key in enumerate(c['model_order']):
        summaries[key]=[];provenance[key]='fixture://'+key
        for mode in ('standard','nonlocal'):
            for d in c['descriptor_order']:
                for region in c['protocol']['regions']:
                    value=-i/20 if region=='rho' else 1.
                    summaries[key].append({'descriptor':d,'mode':mode,'region':region,
                        'query_q1':value,'query_median':value,'query_q3':value,'query_iqr':0.,'query_total_count':9000,'query_valid_count':8000,'query_invalid_count':1000,'query_null_reason':None,
                        'candidate_total_count':9000,'candidate_valid_count':8000,'candidate_invalid_count':1000})
    return cross_rows(summaries,provenance)


def test_complete_comparison_and_signed_median_contrasts(tmp_path):
    rows=synthetic();assert len(rows)==3740;assert sum(r['fm_reused'] for r in rows)==220
    a=contrast_rows(rows,'a_series');b=contrast_rows(rows,'b_series');assert len(a)==220 and len(b)==396
    assert a[0]['delta_median_rho']==pytest.approx(-.05)
    assert len({r['descriptor'] for r in rows if r['configuration_id']=='cmp_B6'})==22
    write_rows(tmp_path,'comparison',rows)
    bad=copy.deepcopy(rows);bad[0]['total_count']=8999
    with pytest.raises(ValueError,match='QUERY_COUNTS'):validate_cross_rows(bad)
    with pytest.raises(ValueError,match='POPULATION_ORDER'):validate_cross_rows(rows[::-1])


def test_synthetic_publication_all_families_and_null(tmp_path):
    rows=synthetic()
    rows[0].update(median=None,q1=None,q3=None,iqr=None,valid_count=0,invalid_count=9000,null_reason='no_valid_queries')
    validate_cross_rows(rows);assert contrast_rows(rows,'a_series')[-44]['delta_median_rho'] is None
    render_figures(tmp_path,rows);assert len(list(tmp_path.glob('*.pdf')))==6


def test_cross_rho_range_matches_existing_s11_validation():
    rows=synthetic();rows[0].update(q1=1.+5e-16,median=1.+5e-16,q3=1.+5e-16,iqr=0.)
    validate_cross_rows(rows)
    rows[0]['q3']=1.01
    with pytest.raises(ValueError,match='RHO_RANGE'):validate_cross_rows(rows)
