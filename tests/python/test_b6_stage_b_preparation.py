import copy,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'python'))
import pytest
from shapely.geometry import LineString,MultiLineString
from b6_postbank_adapter import resolve_receiver,AmbiguousLineage,OutsideNodeMethodDecision,require_physical_node_lift,child_rng_identity,shared_training_config,receiver_semantics
from b6_stage_b_preparation import safe_root,digest
from training_support import derive_seed

PROFILE={'jitter_probability':.2,'jitter_displacement_m':1.}
def fixture():
    geoms={1:MultiLineString([[(0,0),(20,0)],[(40,0),(60,0)]]),2:LineString([(60,0),(80,0)]),3:LineString([(80,0),(100,0)])}
    roads={i:{'local_entity_id':i,'source_entity_id':str(i),'observed_geometry':g.wkb,'LANES':i,'ROAD_TYPE':'A','ROAD_RANK':'B'} for i,g in geoms.items()}
    topology=[{'road_local_entity_id':i,'source_node_position':0,'source_node_id':str(i),'source_node_x_5186':float(i*10),'source_node_y_5186':0.} for i in roads]
    absorption=[{'donor':i,'receiver':1,'status':'ABSORBED'} for i in [3,2]]
    composed=MultiLineString([*geoms[1].geoms,geoms[2],geoms[3]])
    row={'local_entity_id':1,'geometry_wkb':composed.wkb,'fallback':True,'geometry_operation':'JITTER'}
    return roads,topology,absorption,row

def test_multipart_receiver_multiple_donors_recipe_and_semantics():
    roads,top,absorption,row=fixture()
    attrs=[{'local_entity_id':1,'field':'LANES','augmented':'7'}]
    out=resolve_receiver(roads,top,absorption,row,attrs,PROFILE,(-100,-100,500,500))
    assert [x['source_road_id'] for x in out]==['1','1','2','3']
    assert [x['source_part_index'] for x in out]==[0,1,0,0]
    assert all(x['semantic_owner_local_id']==1 and x['semantics']['LANES']=='7' for x in out)
    assert all(not x['synthetic_part_boundary_is_network_node'] for x in out)

def test_unabsorbed_and_true_node_incidence():
    roads,top,_,_=fixture();g=LineString([(20,0),(60,0)])
    roads[2]['observed_geometry']=g.wkb
    row={'local_entity_id':2,'geometry_wkb':g.wkb,'fallback':True}
    out=resolve_receiver(roads,top,[],row,[],PROFILE,(-100,-100,500,500))
    assert out[0]['true_nodes_on_support'][0]['node_id']=='2'
    assert require_physical_node_lift(out,'2')==out
    with pytest.raises(OutsideNodeMethodDecision):require_physical_node_lift(out,'outside')

def test_permuted_parts_unknown_receiver_and_duplicate_donor_reject():
    roads,top,absorption,row=fixture()
    row['geometry_wkb']=MultiLineString([[(80,0),(100,0)],[(0,0),(20,0)],[(40,0),(60,0)],[(60,0),(80,0)]]).wkb
    with pytest.raises(AmbiguousLineage,match='replay mismatch'):resolve_receiver(roads,top,absorption,row,[],PROFILE,(-100,-100,500,500))
    with pytest.raises(AmbiguousLineage,match='duplicate'):resolve_receiver(roads,top,absorption+absorption,row,[],PROFILE,(-100,-100,500,500))

def test_semantic_mask_and_donor_do_not_replace_receiver():
    parent={'local_entity_id':1,'LANES':2,'ROAD_TYPE':'A','ROAD_RANK':'B'}
    values,masked=receiver_semantics(parent,[{'local_entity_id':2,'field':'LANES','augmented':'9'},{'local_entity_id':1,'field':'ROAD_TYPE','augmented':'MASK'}])
    assert values['LANES']==2 and values['ROAD_TYPE'] is None and masked==['ROAD_TYPE']

def test_shared_seed_configuration_rename_and_child_identity():
    base={'training':{'root_seed':123},'parents':{'p6_aggregate_acceptance_id':'p6','scene_index_id':'p1'}}
    a={'content':{'scientific':{'root_seed':1629790839}}}
    values=[]
    for arm in ['B6-original','B6-S50-G','renamed-Ppre']:
        cfg=shared_training_config({**base,'configuration_id':arm},a)
        values.append(derive_seed(cfg,'training-scene-order',epoch=1))
    assert len(set(values))==1
    x=child_rng_identity('scene','view','parent',0,0,50)
    assert x==child_rng_identity('scene','view','parent',0,0,50)
    assert x!=child_rng_identity('scene','other-view','parent',0,0,50)
    assert x!=child_rng_identity('scene','view','parent',0,50,100)

def test_cache_recipe_changes_and_safety():
    base={'child_geometry':'aaa','policy':'G','parent':'p'}
    assert digest(base)!=digest({**base,'child_geometry':'bbb'})
    assert digest(base)!=digest({**base,'policy':'P-pre'})
    assert digest(base)==digest(copy.deepcopy(base))
    for p in ['/tmp/b6','/mnt/hdd002/dhnyu/fusedata/models/reduced/training']:
        with pytest.raises(ValueError):safe_root(p)
    text=Path('targets/b6_stage_b_preparation.R').read_text()
    assert 'tar_target(s09_' not in text and 'torchrun' not in text

def test_rng_wrapper_leaves_graph_ids_unchanged_and_pairs_policies():
    import torch
    from b6_postbank_adapter import paired_modality_assignments
    cfg={'training':{'root_seed':1629790839,'modality_mask_probability':.3},'parents':{'p6_aggregate_acceptance_id':'p6','scene_index_id':'p1'}}
    batch={'family_projection':[{'family':'B6'}],'entities':{'local_entity_id':torch.arange(3),'modality_available':torch.tensor([[1,1,1,0]]*3)},'scene_ptr':torch.tensor([0,3]),'scene_ids':['scene']}
    ids=[child_rng_identity('scene','view','parent',0,i*50,(i+1)*50) for i in range(3)]
    a=paired_modality_assignments(batch,cfg,1,0,child_rng_ids=ids)
    b=paired_modality_assignments(batch,{**cfg,'configuration_id':'renamed'},1,0,child_rng_ids=ids)
    assert all(torch.equal(x,y) for x,y in zip(a,b,strict=True))
    assert torch.equal(batch['entities']['local_entity_id'],torch.arange(3))

def test_original_control_preserves_sample_and_projection_metadata():
    import importlib.util
    from b6_postbank_adapter import original_adapter
    from b6_stage_b_preparation import tensor_digest
    from training_family_inputs import project,check_sample
    p=Path(__file__).with_name('test_training_family_projection.py')
    spec=importlib.util.spec_from_file_location('b6_projection_fixture',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    sample=m.fixture();before=tensor_digest(sample)
    actual=original_adapter(sample);expected=project(sample,'B6')
    assert isinstance(actual,tuple) and len(actual)==2
    check_sample(actual[0]);assert tensor_digest(actual)==tensor_digest(expected)
    assert tensor_digest(sample)==before


def test_scientific_snapshot_removes_canonical_write_destinations():
    from b6_stage_b_preparation import scientific_snapshot
    source={"publication_root":"canonical","nested":{"staging_root":"canonical","root_seed":42}}
    assert scientific_snapshot(source)=={"nested":{"root_seed":42}}
    assert source["publication_root"]=="canonical"
