"""Cache contract unit tests. Real GPU/model equivalence is in the bounded pilot."""
from pathlib import Path
from contextlib import nullcontext
import io
import sys
from copy import deepcopy
import numpy as np
import pytest
import torch
import yaml
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'python'))
import retrieval_geometry as geo
from retrieval_artifacts import publish, publish_bytes, load, file_hash, digest

GEOMETRY = dict(normalization_length_m=500., radial_frequencies=8, angular_orientations=16,
                minimum_radial_frequency=.5, maximum_radial_frequency=50.)


@pytest.fixture
def cache_fixture(tmp_path, monkeypatch):
    import retrieval_inference as inference
    monkeypatch.setattr(inference,'device_lock',lambda cfg:nullcontext())
    monkeypatch.setattr(inference,'initialize_inference',lambda cfg:torch.device('cpu'))
    monkeypatch.setattr(geo,'build_vocabulary',lambda path:{})
    monkeypatch.setattr(geo,'collate',lambda samples,v:samples[0])
    def compute(sample,cfg,device):
        n=len(sample['entities']['local_entity_id']);d=cfg['geometry']['radial_frequencies']*cfg['geometry']['angular_orientations']
        return torch.arange(n*d,dtype=torch.float32).reshape(n,d),torch.zeros(n,2*d)
    monkeypatch.setattr(geo,'geometry_fourier_features',compute)
    monkeypatch.setattr(geo,'materialize_hyperparameter_configuration',lambda c,t,b:{'model':{'model':{'geometry':c['geometry']}}})
    config_path=tmp_path/'training.yml';config_path.write_text('{}')
    pre=tmp_path/'pre.json';pre.write_text('{"preprocessing_id":"ppc_fixture"}')
    cats=tmp_path/'cats.json';cats.write_text('{}')
    roots={'preprocessing':str(pre),'categories':str(cats)}
    cfg={'training_config':str(config_path),'model_config':str(config_path),'device':'cuda:0','batch_size':1,
         'threads':1,'inference_seed':20260916,'gallery_count':2,'publication_root':str(tmp_path/'forbidden')}
    models=[{'configuration_id':name,'model_id':family,'scientific_configuration':{'content':{'geometry':dict(GEOMETRY)}}}
            for name,family in [('main','FM'),('cmp_A4','A4'),('ofat_d_256','FM'),('cmp_DS','DS')]]
    ctx={k:'fixture' for k in ('generation_id','runtime_id','model_manifest_id','query_manifest_id','gallery_manifest_id')}
    samples=[];files=[];sample_rows=[]
    for i,n in enumerate((0,3)):
        sample={'scene_id':f's{i}','split':'evaluation','view_id':'original','profile':None,
                'entities':{'local_entity_id':torch.arange(n),'entity_type':torch.zeros(n,dtype=torch.int64)},
                'geometry':{'part_coordinates_xy_m':torch.zeros(n,2),'ring_coordinates_xy_m':torch.zeros(n,2)}}
        samples.append(sample);b=io.BytesIO();torch.save(sample,b)
        filename=f's{i}.pt';files.append(publish_bytes(tmp_path/filename,b.getvalue()));sample_rows.append({'scene_id':f's{i}','path':filename})
    orig=publish(tmp_path/'originals.json','original_inputs',{**ctx,'scope':'noncanonical_smoke','samples':sample_rows,
        'preprocessing_id':'ppc_fixture','preprocessing_sha256':file_hash(pre),'categories_sha256':file_hash(cats)},files)
    path=geo.create_cache(cfg,models,roots,orig,tmp_path/'cache')
    return cfg,models,roots,orig,path,samples


def reader(f):
    cfg,models,roots,orig,path,samples=f
    return geo.GeometryReader(path,load(orig),GEOMETRY,cfg)


def test_geometry_active_inventory():
    from retrieval_ranking import OFAT,COMPARISON
    models=[{'model_id':'FM'} for _ in OFAT]+[{'model_id':m} for m in COMPARISON]
    assert sum(geo.active(m) for m in models)==25
    assert [m['model_id'] for m in models if not geo.active(m)]==['A1','SSV','DS']


def test_group_identity_ignores_dimension_checkpoint_and_separates_configs(cache_fixture):
    cfg,models,*_=cache_fixture
    groups=geo.configuration_groups(cfg,models)
    assert len(groups)==1 and groups[0]['models']==['main','cmp_A4','ofat_d_256']
    assert groups[0]['configuration_sha256']==digest(GEOMETRY)
    changed=deepcopy(models);changed[2]['scientific_configuration']['content']['geometry']['radial_frequencies']=4
    assert len(geo.configuration_groups(cfg,changed))==2


def test_rerun_payload_manifest_bytes_exact(cache_fixture,tmp_path):
    cfg,models,roots,orig,path,samples=cache_fixture
    other=geo.create_cache(cfg,models,roots,orig,tmp_path/'second')
    assert Path(path).read_bytes()==Path(other).read_bytes()
    assert load(path)['artifact_id']==load(other)['artifact_id']
    for record in load(path)['files']:
        assert (Path(path).parent/record['path']).read_bytes()==(Path(other).parent/record['path']).read_bytes()
    assert geo.create_cache(cfg,models,roots,orig,Path(path).parent)==path


def test_features_exact_empty_and_nonempty(cache_fixture):
    r=reader(cache_fixture)
    for sample in cache_fixture[-1]:
        actual=r.get(sample)
        expected=geo.geometry_fourier_features(sample,{'geometry':GEOMETRY},torch.device('cpu'))
        assert all(torch.equal(a,b) for a,b in zip(actual,expected,strict=True))
        assert all(a.dtype==torch.float32 for a in actual)


def test_stale_config_rejected(cache_fixture):
    cfg,_,_,orig,path,_=cache_fixture
    with pytest.raises(ValueError,match='GEOMETRY_CONFIG'):
        geo.GeometryReader(path,load(orig),{**GEOMETRY,'normalization_length_m':250},cfg)


def test_source_manifest_mismatch_rejected(cache_fixture):
    cfg,_,_,orig,path,_=cache_fixture
    o=load(orig);o['artifact_id']='stale'
    with pytest.raises(ValueError,match='GEOMETRY_ORIGINAL_BINDING'):geo.GeometryReader(path,o,GEOMETRY,cfg)


def test_implementation_mismatch_rejected(cache_fixture,monkeypatch):
    current=geo.implementation_identity();monkeypatch.setattr(geo,'implementation_identity',lambda:{**current,'sha256':'0'*64})
    with pytest.raises(ValueError,match='GEOMETRY_IMPLEMENTATION'):reader(cache_fixture)


def test_corrupt_cache_rejected(cache_fixture):
    path=Path(cache_fixture[4]);row=load(path)['files'][0];(path.parent/row['path']).write_bytes(b'corrupt')
    with pytest.raises(ValueError,match='ARTIFACT_HASH'):reader(cache_fixture)


def test_missing_scene_feature_rejected(cache_fixture):
    r=reader(cache_fixture);s=deepcopy(cache_fixture[-1][1]);s['scene_id']='absent'
    with pytest.raises(ValueError,match='GEOMETRY_MISSING_SCENE'):r.get(s)


def test_entity_order_source_binding_rejected(cache_fixture):
    r=reader(cache_fixture);s=deepcopy(cache_fixture[-1][1]);s['entities']['local_entity_id']=torch.tensor([2,1,0])
    with pytest.raises(ValueError,match='GEOMETRY_ENTITY_SOURCE_BINDING'):r.get(s)


def test_order_and_immutable_collision(cache_fixture,tmp_path):
    cfg,models,roots,orig,path,samples=cache_fixture
    original=load(orig);body=deepcopy(original['body']);body['samples'].reverse()
    changed=publish(tmp_path/'unsorted.json','original_inputs',body,[tmp_path/r['path'] for r in original['files']])
    with pytest.raises(ValueError,match='GEOMETRY_SCENE_ORDER'):geo.create_cache(cfg,models,roots,changed,tmp_path/'bad')
    (Path(path).parent/load(path)['files'][0]['path']).write_bytes(b'wrong')
    with pytest.raises(ValueError,match='IMMUTABLE_COLLISION'):geo.create_cache(cfg,models,roots,orig,Path(path).parent)


def test_oom_does_not_publish_completion(cache_fixture,tmp_path,monkeypatch):
    def oom(*args):raise torch.cuda.OutOfMemoryError('fixture')
    monkeypatch.setattr(geo,'geometry_fourier_features',oom)
    cfg,models,roots,orig,*_=cache_fixture
    with pytest.raises(torch.cuda.OutOfMemoryError):geo.create_cache(cfg,models,roots,orig,tmp_path/'oom')
    assert not (tmp_path/'oom/manifest.json').exists()


def test_batch_expansion_rejected_before_model_loading():
    from retrieval_inference import infer
    with pytest.raises(ValueError,match='BATCH_ONE_REQUIRED'):infer({'batch_size':4},{},{},[])


def test_schema_batch_one():
    import jsonschema
    root=Path(__file__).resolve().parents[2]
    cfg=yaml.safe_load((root/'config/retrieval_visualization.yml').read_text());cfg['batch_size']=4
    with pytest.raises(jsonschema.ValidationError):jsonschema.validate(cfg,__import__('json').loads((root/'config/schemas/retrieval_visualization.schema.json').read_text()))


def test_inactive_ds_never_opens_geometry_cache(tmp_path,monkeypatch):
    import retrieval_inference as inf
    class Control(torch.nn.Module):
        def forward(self,batch,geometry,ds):
            assert geometry is None
            return {'scene_embedding':torch.tensor([[1.,2.]])}
    checkpoint=tmp_path/'checkpoint.pt';torch.save({'configuration_identity':'fixed','online_model':{}},checkpoint)
    sample=tmp_path/'s.pt';torch.save({'scene_id':'s','scene_center_5186':torch.tensor([0.,0.],dtype=torch.float64)},sample)
    cfgfile=tmp_path/'cfg.yml';cfgfile.write_text('{}')
    pre=tmp_path/'pre.json';pre.write_text('{}')
    cfg={'device':'cpu','threads':1,'batch_size':1,'inference_seed':1,'training_config':str(cfgfile),'model_config':str(cfgfile)}
    model={'model_id':'DS','payload':str(checkpoint),'payload_sha256':file_hash(checkpoint),
           'scientific_configuration':{'content':{},'content_sha256':'fixed'}}
    monkeypatch.setattr(inf,'materialize_hyperparameter_configuration',lambda *a:{'model':{}})
    monkeypatch.setattr(inf,'build_vocabulary',lambda *a:{})
    monkeypatch.setattr(inf,'validate_vocabulary_contract',lambda *a:{})
    monkeypatch.setattr(inf,'build_scene_encoder',lambda *a:Control())
    monkeypatch.setattr(inf,'load',lambda *a:{'body':{'samples':[{'scene_id':'s','path':'s.pt'}]}})
    monkeypatch.setattr(inf,'project',lambda *a:({},{}))
    monkeypatch.setattr(inf,'projected_collate',lambda *a:{'entities':{'object_raster':torch.empty(0,0)}})
    monkeypatch.setattr(inf,'ds_raster_from_batch',lambda *a:torch.ones(1,26,100,100))
    monkeypatch.setattr(inf,'family_encoder_batch',lambda *a:{})
    monkeypatch.setattr(geo,'GeometryReader',lambda *a:pytest.fail('DS read geometry cache'))
    args=(cfg,model,{'categories':'unused','preprocessing':str(pre)},[{'scene_id':'s','center_x':0.,'center_y':0.}],tmp_path/'originals.json')
    assert np.array_equal(inf.infer(*args),inf.infer(*args,precomputed_geometry_features=tmp_path/'does_not_exist'))


def test_missing_entry_and_order_tampering(cache_fixture,tmp_path):
    cfg,_,_,orig,path,_=cache_fixture
    original=load(path);body=deepcopy(original['body']);body['groups'][0]['entries'].pop()
    bad=publish(Path(path).parent/'missing.json','geometry_features',body,[Path(path).parent/f['path'] for f in original['files']])
    with pytest.raises(ValueError,match='GEOMETRY_MISSING_SCENE'):geo.GeometryReader(bad,load(orig),GEOMETRY,cfg)


def test_tensor_digest_checks_after_valid_payload_checksum(cache_fixture):
    cfg,_,_,orig,path,samples=cache_fixture
    doc=load(path);payload=Path(path).parent/doc['files'][0]['path'];values=torch.load(payload,weights_only=False)
    values[1]['features'][0][0,0]+=1
    torch.save(values,payload)  # Deliberately corrupt a fixture and re-envelope its file checksum.
    bad=publish(Path(path).parent/'tampered.json','geometry_features',doc['body'],[payload])
    r=geo.GeometryReader(bad,load(orig),GEOMETRY,cfg)
    with pytest.raises(ValueError,match='GEOMETRY_FEATURE_HASH'):r.get(samples[1])


def test_cache_has_no_training_or_s11_execution_dependency():
    import ast
    root=Path(__file__).resolve().parents[2]
    tree=ast.parse((root/'python/retrieval_geometry.py').read_text())
    names={n.func.attr for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)}
    assert not {'train','backward','step'} & names
    modules={n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)}
    assert not {'evaluation','evaluation_inputs','training_controller'} & modules
    stage=(root/'targets/s10_retrieval_visualization.R').read_text()
    assert 's11_evaluation' not in stage and 's09_training' not in stage
