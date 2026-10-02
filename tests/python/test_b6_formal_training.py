"""Formal isolation, accepted selection, paired diagnostics, and real input gates."""
from pathlib import Path
import copy
import numpy as np
import pytest
import torch
import b6_formal_training as f
from b6_formal_analysis import grouped_bootstrap, masks, query_metrics


def test_namespace_safety():
    for path in ['/tmp/x','/mnt/hdd002/dhnyu/fusedata/models/reduced/training',str(f.ROOT)]:
        with pytest.raises(ValueError):f.checked_path(path)
    assert f.checked_path(f.ROOT/'fixture')==f.ROOT/'fixture'


def test_frozen_contract_and_prerequisites():
    c=f.resolve_contract()
    assert c['cache_acceptance']['count']==22368
    assert c['settings']['arms']==list(f.ARMS)
    assert c['frozen_science']['resolved_training']['training']['maximum_updates']==15200
    assert c['selection']['patience_reset']=='retrieval_loss_decrease_at_least_tolerance_only'
    assert c['canonical_resolver_eligible'] is False


def test_actual_reader_validation_and_geometry():
    c=f.resolve_contract()
    for arm in f.ARMS:
        v=f.build_values(c,arm);d=v['data'];assert len(d.validation_scenes)==1000
        assert len(d.training_scenes)==2421
        # Empty and ordinary samples, fixed gallery and both query views.
        for role,scene,view in [('validation_gallery',d.validation_scenes[0],None),('validation_query',d.validation_scenes[0],0),('validation_query',d.validation_scenes[0],1)]:
            batch,geo,_=f.family.assemble_family_batch(v,[(role,scene,view)])
            assert geo[0].shape[0]==len(batch['entities']['local_entity_id'])
            assert (batch['entities']['entity_type']==1).all()
            if arm!=f.ARMS[0]:
                assert len(d.rng(batch))==len(batch['entities']['local_entity_id'])
                d.clear();assert not d.loaded and not d.geometry_index


def test_actual_child_masking_equal():
    c=f.resolve_contract();receipts=[];canonical=f.family.family_modality_assignments
    output=[]
    try:
        for arm in f.ARMS[1:]:
            v=f.build_values(c,arm);d=v['data'];s=d.training_scenes[0]
            batch,_,_=f.family.assemble_family_batch(v,[('training',s,0)])
            f.family.family_modality_assignments=canonical
            f.install_masking(d,arm,receipts)
            output.append(f.family.family_modality_assignments(batch,v['config'],1,0,0)[1])
        assert torch.equal(*output)
        assert receipts[0]==receipts[1]
    finally:f.family.family_modality_assignments=canonical


def test_bootstrap_keeps_views_together_and_seed_stable():
    delta=np.repeat(np.arange(5.)[:,None],2,axis=0)*np.ones((1,6))
    a=grouped_bootstrap(delta,np.arange(5),123,100)
    assert a==grouped_bootstrap(delta,np.arange(5),123,100)
    assert a['MRR']['difference']==2
    assert a['MRR']['ci95'][0]<=2<=a['MRR']['ci95'][1]
    assert grouped_bootstrap(delta,np.array([],dtype=int),1,10) is None


def test_parent_bins_and_zero_separation():
    p=masks(np.array([0,1,8,9,49,50]),np.array([0,50,100,250,500,10]))
    assert p['zero_road'].sum()==1 and p['road_nonempty'].sum()==5
    assert p['count_1_8'].sum()==2 and p['count_9_49'].sum()==2
    assert p['length_0_50'].sum()==1
    assert p['length_500_inf'].sum()==1


def test_selection_strict_tolerance_and_patience():
    prev={'completed_epoch':5,'validation_retrieval_loss':1.,'mean_source_separation_margin':.1}
    same={**prev,'completed_epoch':10,'mean_source_separation_margin':.2}
    assert f.evaluate_selection_candidate(same,prev,1e-4)[0]
    assert not f.qualifies_patience_reset(same,prev,1e-4)
    worse={**same,'validation_retrieval_loss':1.01}
    assert not f.evaluate_selection_candidate(worse,prev,1e-4)[0]


def test_rank_ties_stable_full_gallery():
    vectors=torch.zeros(3000,256)
    a=query_metrics(vectors)
    assert a.shape==(2000,6)
    assert a[:,3].sum()==2 # gallery index 0 only, both query views
    assert abs(float(a[:,0].mean())-np.log(1000))<2e-6


def test_checkpoint_immutable_roundtrip(tmp_path,monkeypatch):
    monkeypatch.setattr(f,'ROOT',tmp_path)
    path=tmp_path/'arm'/'checkpoint.pt';path.parent.mkdir()
    value={'online_model':{'w':torch.tensor([1.,2.])},'rng':torch.arange(10),'progress':{'epoch':5}}
    f.save_tensor(path,value);h=f.sha256_file(path);f.save_tensor(path,value)
    assert f.sha256_file(path)==h
    with pytest.raises(ValueError):f.save_tensor(path,{'x':torch.zeros(1)})
