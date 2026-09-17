"""100-query policy fixtures and scientific binding rejection checks."""
import ast
import copy
from pathlib import Path
import numpy as np
import pytest
import s10_query_revision as revision
from retrieval_ranking import rank


def population(sparse=20, regular=180):
    rows=[{'scene_id':f's{i:04d}','center_x':float(i*500),'center_y':0.,'split':'evaluation'} for i in range(sparse+regular)]
    counts={r['scene_id']:{'n_buildings':0,'n_roads':0,'n_pois':9 if i<sparse else 10,'object_count':9 if i<sparse else 10} for i,r in enumerate(rows)}
    return rows,counts


def test_deterministic_exact_100_unique_evaluation_stable_order():
    rows,counts=population();a=revision.select_queries(rows,counts,20260916)
    assert a==revision.select_queries(rows[::-1],counts,20260916)
    assert len(a)==len({r['scene_id'] for r in a})==100
    assert {r['scene_id'] for r in a} <= {r['scene_id'] for r in rows}
    assert all(r['split']=='evaluation' for r in a)
    assert sum(r['object_count']<10 for r in a)==5
    assert sum(r['object_count']>=10 for r in a)==95
    assert [r['query_index'] for r in a]==list(range(1,101))
    assert [r['object_count'] for r in a[:5]]==[9]*5
    assert [r['object_count'] for r in a[5:]]==[10]*95


@pytest.mark.parametrize('sparse',[0,1,4,5])
def test_sparse_shortage_fill_regular(sparse):
    rows,counts=population(sparse);selected=revision.select_queries(rows,counts,20260916)
    assert len(selected)==100 and sum(r['object_count']<10 for r in selected)==sparse


@pytest.mark.parametrize('fault',['duplicate','count_missing','negative','shortage'])
def test_bad_population_fails(fault):
    rows,counts=population()
    if fault=='duplicate':rows.append(rows[0])
    elif fault=='count_missing':counts.pop(rows[0]['scene_id'])
    elif fault=='negative':counts[rows[0]['scene_id']]['object_count']=-1
    else:rows,counts=population(110,90)
    with pytest.raises(ValueError):revision.select_queries(rows,counts,20260916)


def test_standard_nonlocal_ties_top50_all_queries():
    rows,counts=population();queries=revision.select_queries(rows,counts,20260916)
    v=np.zeros((len(rows),2),dtype=np.float32);v[:,0]=1
    model={'configuration_id':'fixture','group':'OFAT','checkpoint_id':'untouched'}
    result=rank(v,rows,queries,model,{})
    assert len(result)==100*2*50 and result==rank(v,rows,queries,model,{})
    for q in queries:
        for mode in ['standard','nonlocal']:
            actual=[r for r in result if r['query_id']==q['scene_id'] and r['retrieval_mode']==mode]
            expected=[r['scene_id'] for r in rows if r['scene_id']!=q['scene_id'] and (mode=='standard' or abs(r['center_x']-q['center_x'])>=2000)][:50]
            assert [r['gallery_scene_id'] for r in actual]==expected
            assert [r['rank'] for r in actual]==list(range(1,51))


def test_binding_refuses_rebinding_to_new_query(monkeypatch,tmp_path):
    model={'configuration_id':'main'}
    oldq={'artifact_id':'old_query'};g={'artifact_id':'gallery','body':{'rows':[]}};m={'artifact_id':'models','body':{}}
    rp=tmp_path/'rankings/main/manifest.json'
    parent={'body':{'artifacts':{str(rp):'accepted_ranking'}}}
    body={'model':model,'embedding_manifest':str(tmp_path/'embedding.json'),'embedding_manifest_id':'embedding',
          'query_manifest_id':'new_query','gallery_manifest_id':'gallery','model_manifest_id':'models'}
    ranking={'artifact_id':'accepted_ranking','body':body}
    embedding={'artifact_id':'embedding','body':{**body,'scene_ids':[]}}
    monkeypatch.setattr(revision,'load',lambda path,kind:ranking if kind=='rankings' else embedding)
    with pytest.raises(ValueError,match='PARENT_EMBEDDING_BINDING'):
        revision.verified_embedding(tmp_path,parent,m,g,oldq,model)


def test_no_training_checkpoint_inference_execution_imports():
    tree=ast.parse(Path(revision.__file__).read_text());imports=[]
    for node in ast.walk(tree):
        if isinstance(node,ast.Import):imports.extend(n.name for n in node.names)
        if isinstance(node,ast.ImportFrom):imports.append(node.module)
    assert not any(any(k in name for k in ['inference','training','checkpoint','evaluation','model_data','torch']) for name in imports)
    source=Path(revision.__file__).read_text()
    assert "vector/{name}_observed.parquet" in source
    assert "source_entity_id" in source and "P3_PAYLOAD_HASH" in source
    assert 'REPRODUCIBLE_OBJECT_COUNTS' in source


def test_counts_read_exact_hash_bound_p3_records(monkeypatch,tmp_path):
    import io
    import tarfile
    import pyarrow as pa
    import pyarrow.parquet as pq
    from retrieval_artifacts import file_hash
    branch='branch';shard=tmp_path/'shards'/branch/'payload.tar';shard.parent.mkdir(parents=True)
    with tarfile.open(shard,'w') as archive:
        for name,identifiers in [('building',[0,1]),('road',[2]),('poi',[3,4,5])]:
            records=[{'scene_id':'scene','local_entity_id':i,'source_entity_id':f'{name}:{i}','split':'evaluation'} for i in identifiers]
            stream=io.BytesIO();pq.write_table(pa.Table.from_pylist(records),stream)
            raw=stream.getvalue();info=tarfile.TarInfo(f'vector/{name}_observed.parquet');info.size=len(raw);archive.addfile(info,io.BytesIO(raw))
    checksum=file_hash(shard);ip=tmp_path/'scene_to_shard.parquet'
    pq.write_table(pa.Table.from_pylist([{'scene_id':sid,'branch_id':branch,'cache_id':'accepted_cache','payload_sha256':checksum,'payload_filename':'payload.tar'} for sid in ['scene','empty']]),ip)
    model={'body':{'config':{'source_pins':{str(ip):file_hash(ip)}},'parents':{'scene_cache_id':'accepted_cache'},'roots':{'p3':str(tmp_path)}}}
    gallery={'body':{'rows':[{'scene_id':sid,'source_payload_sha256':checksum} for sid in ['scene','empty']]}}
    monkeypatch.setattr(revision,'parents',lambda cfg:(tmp_path,{},model,gallery,{}))
    counts,sources=revision.count_population({})
    assert counts['scene']=={'n_buildings':2,'n_roads':1,'n_pois':3,'object_count':6}
    assert counts['empty']=={'n_buildings':0,'n_roads':0,'n_pois':0,'object_count':0}
    assert sources[str(shard)]==checksum and sources[str(ip)]==file_hash(ip)
    # Corruption cannot be substituted as an alternate object-count source.
    with shard.open('ab') as f:f.write(b'corrupt')
    with pytest.raises(ValueError,match='P3_PAYLOAD_HASH'):revision.count_population({})
