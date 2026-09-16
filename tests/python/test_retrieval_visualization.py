import ast
from copy import deepcopy
from pathlib import Path
import sys
import numpy as np
import pytest
import yaml
import jsonschema

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))
from retrieval_artifacts import publish, load, read_json, publish_bytes
from retrieval_ranking import sample_queries, rank, check_embeddings, OFAT, COMPARISON
from retrieval_pipeline import common, embeddings, validate_rankings, acceptance


def gallery(n=9000):
    return [{"scene_id": f"s{i:05}", "center_x": i*2000., "center_y": 0., "split":"evaluation", "epsg":5186} for i in range(n)]


def test_query_sampling_deterministic_uniform_without_replacement():
    first = sample_queries(gallery(), 20260916)
    assert first == sample_queries(gallery(),20260916)
    assert len(first) == len({r['scene_id'] for r in first}) == 30
    assert first != sample_queries(gallery(),20260917)
    assert [r['query_index'] for r in first] == list(range(1,31))


@pytest.mark.parametrize('bad', ['duplicate','unsorted','wrong_count'])
def test_gallery_membership_rejected(bad):
    rows = gallery()
    if bad=='duplicate': rows[1]=rows[0]
    elif bad=='unsorted': rows.reverse()
    else: rows.pop()
    with pytest.raises(ValueError, match='GALLERY_POPULATION'): sample_queries(rows,20260916)


def ranking_fixture():
    rows=gallery(5)
    rows[1]['center_x']=1999.999
    vectors=np.array([[1.,0.],[1.,0.],[1.,0.],[0.,1.],[-1.,0.]],dtype=np.float32)
    model={'configuration_id':'main','group':'OFAT','checkpoint_id':'exact'}
    return vectors,rows,model


def test_self_nonlocal_boundary_ties_sort_and_topk():
    v,g,m=ranking_fixture()
    g[2]['center_x']=2000.
    result=rank(v,g,[g[0]],m,{'generation_id':'fixed'},2)
    standard=[r for r in result if r['retrieval_mode']=='standard']
    remote=[r for r in result if r['retrieval_mode']=='nonlocal']
    assert [r['gallery_scene_id'] for r in standard]==['s00001','s00002']
    assert [r['gallery_scene_id'] for r in remote]==['s00002','s00003']
    assert standard[0]['excluded_by_nonlocal'] and not remote[0]['excluded_by_nonlocal']
    assert remote[0]['geographic_distance_m']==2000
    assert all(r['gallery_scene_id']!='s00000' for r in result)
    assert len(result)==4


@pytest.mark.parametrize('value',[np.nan,np.inf,-np.inf])
def test_nonfinite_embedding_rejected(value):
    v,g,m=ranking_fixture(); v[1,1]=value
    with pytest.raises(ValueError,match='NONFINITE'): rank(v,g,[g[0]],m,{},2)


def test_embedding_norm_and_candidate_shortage_rejected():
    v,g,m=ranking_fixture()
    with pytest.raises(ValueError,match='INSUFFICIENT'): rank(v,g,[g[0]],m,{},50)
    v[1]*=2
    with pytest.raises(ValueError,match='NOT_NORMALIZED'): check_embeddings(v,5)


def test_duplicate_queries_rejected():
    v,g,m=ranking_fixture()
    with pytest.raises(ValueError,match='DUPLICATE_QUERY'): rank(v,g,[g[0],g[0]],m,{},2)


def test_immutable_publication_and_corruption(tmp_path):
    payload=publish_bytes(tmp_path/'data',b'first')
    p=publish(tmp_path/'manifest.json','fixture',{'fixed':True},[payload])
    assert publish(tmp_path/'manifest.json','fixture',{'fixed':True},[payload])==p
    with pytest.raises(ValueError,match='COLLISION'): publish_bytes(payload,b'changed')
    payload.write_bytes(b'wrong')
    with pytest.raises(ValueError,match='ARTIFACT_HASH'): load(p)


def test_manifest_hash_corruption(tmp_path):
    p=Path(publish(tmp_path/'manifest.json','fixture',{'fixed':True}))
    p.write_text(p.read_text().replace('true','false'))
    with pytest.raises(ValueError,match='MANIFEST_HASH'): load(p)


def test_invalid_schema_is_never_published(tmp_path):
    path=tmp_path/'invalid.json'
    with pytest.raises(jsonschema.ValidationError): publish(path,'queries',{})
    assert not path.exists()


@pytest.fixture
def manifests(tmp_path):
    cfg={'query_seed':20260916,'query_count':2,'gallery_count':5,'model_count':1,'top_k':2}
    model={'configuration_id':'main','group':'OFAT','checkpoint_id':'exact'}
    ctx={'generation_id':'fixed','runtime_id':'fixed','scope':'formal'}
    m=publish(tmp_path/'model_manifest.json','models',{**ctx,'config':cfg,'models':[model]})
    g=publish(tmp_path/'gallery_manifest.json','gallery',{**ctx,'model_manifest_id':load(m)['artifact_id'],'rows':gallery(5)})
    q=publish(tmp_path/'query_manifest.json','queries',{**ctx,'model_manifest_id':load(m)['artifact_id'],
        'gallery_manifest_id':load(g)['artifact_id'],'seed':20260916,'rows':sample_queries(gallery(5),20260916,2,5)})
    return m,g,q


def test_common_manifests_and_wrong_gallery_identity(manifests,tmp_path):
    m,g,q=manifests
    assert common(m,g,q)[2]['body']['rows']==sample_queries(gallery(5),20260916,2,5)
    changed=deepcopy(load(g)['body']); changed['rows'][0]['center_x']+=1
    g2=publish(tmp_path/'wrong.json','gallery',changed)
    with pytest.raises(ValueError,match='QUERY_MANIFEST_BINDING'): common(m,g2,q)


def test_cross_model_manifest_identity_rejected(manifests,tmp_path):
    m,g,q=manifests; changed=deepcopy(load(m)['body']); changed['models'][0]['checkpoint_id']='stale'
    m2=publish(tmp_path/'wrong.json','models',changed)
    with pytest.raises(ValueError,match='GALLERY_MODEL_BINDING'): common(m2,g,q)


def test_query_seed_cannot_drift_within_generation(manifests,tmp_path):
    m,g,q=manifests; changed=deepcopy(load(q)['body']); changed['seed']+=1
    q2=publish(tmp_path/'wrong_seed.json','queries',changed)
    with pytest.raises(ValueError,match='QUERY_SEED_BINDING'): common(m,g,q2)


def test_missing_model_result_rejected(manifests):
    with pytest.raises(ValueError,match='MODEL_RESULT_COUNT'): validate_rankings(*manifests,[])


def test_full_inference_requires_explicit_authorization(manifests,monkeypatch):
    monkeypatch.delenv('FUSE_S10_FULL_AUTHORIZED',raising=False)
    with pytest.raises(ValueError,match='FULL_INFERENCE_NOT_AUTHORIZED'): embeddings(*manifests,'main')


@pytest.mark.parametrize('field,value',[('query_count',29),('model_count',27),('gallery_count',10000),('top_k',5),('nonlocal_m',1999)])
def test_formal_config_counts_rejected(field,value):
    cfg=yaml.safe_load((ROOT/'config/retrieval_visualization.yml').read_text()); cfg[field]=value
    with pytest.raises(jsonschema.ValidationError): jsonschema.validate(cfg,read_json(ROOT/'config/schemas/retrieval_visualization.schema.json'))


def test_campaign_and_historical_checkpoint_pin_rejection(tmp_path):
    from retrieval_lineage import inventory,config
    cfg=config(ROOT/'config/retrieval_visualization.yml')
    cfg['campaign']=str(tmp_path/'historical.json'); Path(cfg['campaign']).write_text('{}')
    with pytest.raises(ValueError,match='CAMPAIGN_PIN'): inventory(cfg)


def test_viewer_has_no_scientific_recomputation_or_fallback():
    tree=ast.parse((ROOT/'tools/retrieval_inspector/viewer.py').read_text())
    modules={n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)}
    assert modules <= {'pathlib','collections','retrieval_artifacts'}
    imports={n.name for node in ast.walk(tree) if isinstance(node,ast.Import) for n in node.names}
    assert imports=={'html','os','pyarrow.parquet'}
    text=(ROOT/'tools/retrieval_inspector/viewer.py').read_text()
    for forbidden in ('torch','numpy','argsort','cosine_similarity','retrieval_inference','retrieval_ranking'):
        assert forbidden not in text


def test_viewer_rejects_missing_artifact(tmp_path):
    sys.path.insert(0,str(ROOT/'tools/retrieval_inspector'))
    from viewer import pages
    with pytest.raises(FileNotFoundError): pages(tmp_path/'absent',tmp_path/'absent',[],tmp_path/'absent',tmp_path)


def test_s11_number_only_seed_and_blocked_contract():
    from evaluation import make_qualitative_contract,load_contract,P11Error
    cfg=yaml.safe_load((ROOT/'config/evaluation.yml').read_text())
    jsonschema.validate(cfg,read_json(ROOT/'config/schemas/evaluation.schema.json'))
    with pytest.raises(P11Error,match='PENDING_RECOMPUTATION'): load_contract(ROOT/'config/evaluation.yml')
    q=make_qualitative_contract(cfg,gallery())
    import hashlib
    from artifact_protocol import canonical_sha256
    preimage='p10-qualitative-query-v1'+cfg['accepted_evaluation']['split_acceptance_id']+canonical_sha256([r['scene_id'] for r in gallery()])
    seed=int.from_bytes(hashlib.sha256(preimage.encode()).digest()[:8],'big')
    expected=np.random.Generator(np.random.PCG64(seed)).choice(9000,10,replace=False)
    assert q['selected_scene_ids']==[gallery()[int(i)]['scene_id'] for i in expected]
    assert 'bundle_record' not in read_json(ROOT/'config/schemas/evaluation.schema.json')['properties']['model_set']['items']['properties']


def test_stage_isolation_and_no_stale_evaluation_target_names():
    text=(ROOT/'_targets_evaluation.R').read_text()+(ROOT/'targets/s11_evaluation.R').read_text()
    assert 's10_evaluation' not in text and 's11_evaluation_acceptance' in text
    assert 's10_retrieval' not in text
    stage=(ROOT/'targets/s10_retrieval_visualization.R').read_text()
    assert 's09_training' not in stage and 's11_evaluation' not in stage
    assert len(OFAT)==11 and len(COMPARISON)==17
    assert not (ROOT/'targets/s10_evaluation.R').exists()


@pytest.fixture
def ranking_manifest(manifests,tmp_path):
    import io
    from retrieval_pipeline import bindings,rankings
    m,g,q=manifests
    mv,gv,qv=common(m,g,q)
    b=bindings(mv,gv,qv)
    prep=publish(tmp_path/'prepared.json','original_inputs',b)
    vectors,_,_=ranking_fixture()
    buffer=io.BytesIO(); np.save(buffer,vectors,allow_pickle=False)
    payload=publish_bytes(tmp_path/'vectors.npy',buffer.getvalue())
    e=publish(tmp_path/'embedding.json','embeddings',{**b,'model':mv['body']['models'][0],
        'scene_ids':[r['scene_id'] for r in gv['body']['rows']],
        'prepared_manifest':prep,'prepared_manifest_id':load(prep)['artifact_id']},[payload])
    return rankings(m,g,q,e)


def test_complete_ranking_readback(manifests,ranking_manifest):
    assert len(validate_rankings(*manifests,[ranking_manifest]))==8


def test_ranking_parquet_rerun_is_byte_identical(manifests,ranking_manifest):
    from retrieval_pipeline import rankings
    before=load(ranking_manifest)
    assert rankings(*manifests,before['body']['embedding_manifest'])==ranking_manifest
    assert load(ranking_manifest)==before


@pytest.mark.parametrize('mutation',['duplicate_rank','self_match','wrong_score','wrong_gallery','nonfinite','wrong_distance'])
def test_reject_corrupted_ranking_content(manifests,ranking_manifest,tmp_path,mutation):
    import pyarrow as pa
    import pyarrow.parquet as pq
    r=load(ranking_manifest)
    rows=pq.read_table(Path(ranking_manifest).parent/r['files'][0]['path']).to_pylist()
    if mutation=='duplicate_rank': rows[1]['rank']=rows[0]['rank']
    elif mutation=='self_match': rows[0]['gallery_scene_id']=rows[0]['query_id']
    elif mutation=='wrong_score': rows[0]['similarity']=-0.333
    elif mutation=='wrong_gallery': rows[0]['gallery_manifest_id']='historical'
    elif mutation=='nonfinite': rows[0]['similarity']=float('nan')
    else: rows[0]['geographic_distance_m']=1999
    sink=pa.BufferOutputStream(); pq.write_table(pa.Table.from_pylist(rows),sink)
    data=publish_bytes(tmp_path/'bad.parquet',sink.getvalue().to_pybytes())
    wrong=publish(tmp_path/'wrong_rankings.json','rankings',r['body'],[data])
    with pytest.raises(ValueError,match='RANKING_CONTENT'): validate_rankings(*manifests,[wrong])


def test_invalid_formal_counts_cannot_receive_acceptance(manifests,ranking_manifest,tmp_path):
    m,g,q=manifests
    from retrieval_pipeline import bindings
    b=bindings(*common(m,g,q))
    p=publish(tmp_path/'pages.json','pages',b)
    s=publish(tmp_path/'summary.json','summary',b)
    with pytest.raises(ValueError,match='FORMAL_COUNTS'): acceptance(m,g,q,[ranking_manifest],p,s)


def test_no_s11_in_s10_runtime_closure():
    from retrieval_lineage import runtime,config
    r=runtime(config(ROOT/'config/retrieval_visualization.yml'))
    assert 'python/evaluation.py' not in r['sources']
    assert 'python/evaluation_inputs.py' not in r['sources']


def test_s11_preparation_stops_before_reading_stale_sources(monkeypatch):
    import evaluation_inputs as stage
    cfg=yaml.safe_load((ROOT/'config/evaluation.yml').read_text())
    monkeypatch.setattr(stage,'_catalog',lambda *a,**k: pytest.fail('stale source read'))
    with pytest.raises(stage.P11PreparedInputError,match='LINEAGE_REPAIR_REQUIRED'):
        stage.make_cache_plan(cfg)
    with pytest.raises(stage.P11PreparedInputError,match='LINEAGE_REPAIR_REQUIRED'):
        stage.build_geometry_cache(cfg,'must-not-read')
