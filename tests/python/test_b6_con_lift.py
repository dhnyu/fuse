from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'python'))
import pytest
from shapely.geometry import LineString, MultiLineString
from b6_con_lift import source_run, select_child, subdivide_receiver, lift_accepted_parent_con_to_children, ChainMappingError
from b6_postbank_adapter import resolve_receiver

def make(parent, coords, observed=None, nodes=('F','T'), receiver=None, start=1):
    g=LineString(coords);o=observed or g;local=start;receiver=receiver or local
    roads={local:{'local_entity_id':local,'source_entity_id':parent,'source_geometry_wkb':g.wkb,'observed_geometry':o.wkb}}
    top=[{'road_local_entity_id':local,'source_node_id':n,'source_node_position':i,'source_node_x_5186':xy[0],'source_node_y_5186':xy[1]} for i,(n,xy) in enumerate(zip(nodes,[coords[0],coords[-1]]))]
    row={'local_entity_id':local,'geometry_wkb':o.wkb,'fallback':True}
    mapped=resolve_receiver(roads,top,[],row,[],{},(-1000,-1000,1000,1000))
    for p in mapped:p['receiver_local_id']=receiver
    return subdivide_receiver('scene','view',mapped,roads,row,top)

def test_straight_bent_multipart_and_chain_distances():
    x=make('a',[(0,0),(100,0),(100,100)],LineString([(80,0),(100,0),(100,100)]))
    chosen,a=select_child(x,'a','F')
    assert a['mode']=='logical_off_support' and a['chain_distance_m']==pytest.approx(80)
    assert chosen['ordinal']==0 and len(x)==3
    assert sum(c['geometry'].length for c in x)==pytest.approx(120)
    assert [c['child_id'] for c in x]==[c['child_id'] for c in make('a',[(0,0),(100,0),(100,100)],LineString([(80,0),(100,0),(100,100)]))]
    m=make('m',[(0,0),(150,0)],MultiLineString([[(10,0),(30,0)],[(100,0),(130,0)]]))
    assert len(m)==2 and select_child(m,'m','T')[0]['component']==1

def test_cut_boundary_terminal_single_owner_and_junctions():
    x=make('a',[(0,0),(100,0)])
    # Explicit internal original source node at a cut, not a synthetic node.
    for c in x:c['nodes'].append({'source_node_id':'J','source_node_position':0,'source_node_x_5186':50.,'source_node_y_5186':0.})
    chosen,d=select_child(x,'a','J');assert chosen['ordinal']==0 and d['mode']=='physical_on_support'
    arms=[make(str(i),[(0,0),end],nodes=('J',str(i)),start=i) for i,end in enumerate([(100,0),(0,100),(-100,0),(0,-100)],1)]
    for n in (3,4):
        children=sum(arms[:n],[]);pairs,records=lift_accepted_parent_con_to_children([(i,j) for i in range(1,n+1) for j in range(i+1,n+1)],children)
        assert len(pairs)==n*(n-1)//2 and len(records)==len(pairs)
        assert all(r['node_id']=='J' for r in records)

def test_two_nodes_same_pair_distinct_coordinates_ids_and_no_synthetic_con():
    a=make('a',[(0,0),(100,0)],nodes=('F','T'),start=1)
    b=make('b',[(0,0),(50,1),(100,0)],nodes=('F','T'),start=2)
    pairs,r=lift_accepted_parent_con_to_children([(1,2),(2,1)],a+b)
    assert len(r)==2 and len(pairs)==2 and {x['node_id'] for x in r}=={'F','T'}
    c=make('c',[(0,0),(100,0)],nodes=('OTHER','OTHER_T'),start=3)
    with pytest.raises(ChainMappingError,match='lacks shared'):lift_accepted_parent_con_to_children([(1,3)],a+c)
    assert lift_accepted_parent_con_to_children([],a)[0]==set()

def test_exact_parent_lineage_dominates_receiver_and_euclidean():
    a=make('a',[(0,0),(100,0),(100,1),(0,1)],LineString([(50,0),(100,0),(100,1),(0,1)]),nodes=('N','T'),start=1,receiver=10)
    donor=make('donor',[(0,0),(10,0)],start=2,receiver=10)
    selected,d=select_child(a+donor,'a','N')
    assert selected['source_parent']=='a' and selected['ordinal']==0
    assert d['chain_distance_m']==pytest.approx(50)
    # The last visible endpoint is only one metre away in Euclidean space.
    assert selected['geometry'].distance(__import__('shapely').Point(0,0))>1

def test_ambiguous_retracing_source_fails_closed():
    with pytest.raises(ChainMappingError):source_run(LineString([(0,0),(100,0),(0,0),(100,0)]),LineString([(20,0),(40,0)]))


def test_closed_visible_run_preserves_original_vertex_direction():
    source=LineString([(0,0),(10,0),(10,10),(0,10),(0,0)])
    observed=LineString(source.coords)
    positions=source_run(source,observed)
    assert list(positions)==[0,10,20,30,40]


def test_segmented_full_source_topk_and_policy_only_sn():
    from b6_segmented_inputs import full_source_graphs
    from shapely.geometry import box,Point
    children=[]
    for i in range(21):
        children.append({'child_id':str(i),'receiver':1 if i<20 else 2,'source_parent':'a' if i<20 else 'b','component':0,'ordinal':i,'geometry':LineString([(0,0),(1,0)])})
    delta={'geometry':[],'removals':[]}
    _,graphs,stats=full_source_graphs([],delta,children,set())
    def edges(g,bit):return {tuple(p) for p,m in zip(g['edge_index'].T.tolist(),g['relation_mask'].tolist()) if m&bit}
    assert edges(graphs['G'],8)==edges(graphs['Ppre'],8)
    assert not edges(graphs['G'],16)
    assert len(edges(graphs['Ppre'],1)-edges(graphs['G'],1))>0
    assert all(a==20 or b==20 for a,b in edges(graphs['Ppre'],1))
    buildings=[{'entity_type':'B','local_entity_id':i,'source_entity_id':str(i),'observed_geometry':box(-1,-1,2,1).wkb} for i in range(30)]
    pois=[{'entity_type':'P','local_entity_id':31,'source_entity_id':'p','observed_geometry':Point(0,0).wkb}]
    _,g,_=full_source_graphs(buildings+pois,delta,children[:2],set())
    assert edges(g['G'],1)==set()  # All road top-k slots consumed by B, no induced road SN.
    assert edges(g['G'],8)=={(0,1),(1,0)}


def test_missing_lineage_fails_and_boundary_ties_are_single_owner():
    x=make('a',[(0,0),(100,0)])
    with pytest.raises(ChainMappingError,match='missing exact'):select_child(x,'unknown','F')
    with pytest.raises(ChainMappingError,match='missing source-node'):select_child(x,'a','unknown')
    # Both intervals carry the same original-node chain location at their cut.
    for c in x:
        c['nodes']=[{'source_node_id':'J','source_node_position':1,'source_node_x_5186':50.,'source_node_y_5186':0.}]
        c['source_length']=50.
    selected,diagnostic=select_child(x,'a','J')
    assert diagnostic['ties_before']==2 and diagnostic['ties_after']==1
    assert selected['ordinal']==0 and diagnostic['physical_terminal_preference']


def test_config_schema_and_bounded_runner_safety():
    import yaml,json,jsonschema,ast
    config=yaml.safe_load(Path('config/b6_con_lift.yml').read_text())
    jsonschema.validate(config,json.loads(Path('config/schemas/b6_con_lift.schema.json').read_text()))
    assert config['global_batch']==32 and config['world_size']==2
    assert config['full_training'] is False and config['checkpoint_publication'] is False
    tree=ast.parse(Path('python/b6_bounded_pilot.py').read_text())
    calls={getattr(n.func,'attr',getattr(n.func,'id','')) for n in ast.walk(tree) if isinstance(n,ast.Call)}
    assert 'training_update' in calls
    assert not ({'run_worker','_stage_checkpoint','full_validation','torch_save'}&calls)


def test_gpu_worker_refuses_canonical_output_namespace():
    from b6_bounded_pilot import checked_output
    with pytest.raises(ValueError,match='namespace'):checked_output('/mnt/hdd002/dhnyu/fusedata/models/reduced/training')
    with pytest.raises(ValueError,match='namespace'):checked_output('/tmp/not-b6-pilot')


def test_accepted_counterexample_complete_census_receipt():
    import json
    path=Path('/mnt/hdd002/dhnyu/fusedata/experiments/b6_con_lift/b6con_032b560f2d826f3177854e91/census/census.json')
    if not path.exists():pytest.skip('accepted external integration census not installed')
    census=json.loads(path.read_text());assert census['verdict']=='PASS'
    rows=[r for branch in census['results'] for r in branch['examples'] if r['node_id']=='1020026002']
    assert len(rows)==1
    r=rows[0];assert {r['receiver_a'],r['receiver_b']}=={262,267}
    assert r['a']['mode']==r['b']['mode']=='logical_off_support'
    assert not r['collapsed_existing_pair'] and r['child_a']!=r['child_b']
    assert r['a']['chain_distance_m']==pytest.approx(185.13427407976698)
    assert r['b']['chain_distance_m']==pytest.approx(185.40713226605942)


def test_experimental_sn_near_ties_quantized_before_top16():
    from b6_segmented_inputs import full_source_graphs
    children=[]
    for i in range(18):
        x=0. if i==0 else 1.+(1e-10 if i==17 else 4e-10)
        children.append({'child_id':str(i),'receiver':i,'source_parent':str(i),'component':0,'ordinal':0,'geometry':LineString([(x,0),(x,1)])})
    _,graphs,_=full_source_graphs([],{'geometry':[],'removals':[]},children,set())
    for g in graphs.values():
        neighbors={b for (a,b),mask in zip(g['edge_index'].T.tolist(),g['relation_mask'].tolist()) if a==0 and mask&1}
        assert neighbors==set(range(1,17))
