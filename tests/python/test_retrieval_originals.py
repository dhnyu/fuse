"""S10 I/O equivalence and bounded reader lifecycle, without S09 source edits."""
from pathlib import Path
import sys
import io
import tarfile
from types import SimpleNamespace
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'python'))
from retrieval_originals import OriginalReader
from retrieval_artifacts import file_hash
from model_data import _table


def fixture_catalog(tmp_path):
    path=tmp_path/'one.tar'
    table=pa.Table.from_pylist([{'scene_id':'b','value':None,'geometry':b'raw'},
                               {'scene_id':'a','value':2.,'geometry':b'bytes'},
                               {'scene_id':'b','value':3.,'geometry':b'more'}])
    buf=io.BytesIO();pq.write_table(table,buf)
    with tarfile.open(path,'w') as t:
        member=tarfile.TarInfo('table.parquet');member.size=len(buf.getvalue());t.addfile(member,io.BytesIO(buf.getvalue()))
    sha=file_hash(path)
    def checked(s):
        if file_hash(path)!=sha:raise ValueError('P3_PAYLOAD')
        return path,{'scene_id':s}
    return SimpleNamespace(p3_tar=checked,p3_by_scene={'b':{'branch_id':'one'},'a':{'branch_id':'one'}})


def test_arrow_filter_preserves_native_rows_and_order(tmp_path):
    cat=fixture_catalog(tmp_path)
    with OriginalReader(cat) as reader:
        reader._open('b')
        with tarfile.open(tmp_path/'one.tar') as archive:
            for sid in ('a','b','absent'):
                assert reader._rows('table.parquet',sid)==_table(archive,'table.parquet',sid)
        original=reader.tables['table.parquet']
        reader._open('a');reader._rows('table.parquet','a')
        assert reader.tables['table.parquet'] is original
    assert reader.path is None and not reader.tables and reader.archive.closed


def test_shard_order_and_duplicate_rejection(tmp_path):
    with OriginalReader(fixture_catalog(tmp_path)) as reader:
        assert reader.ordered_ids(['b','a'])==reader.ordered_ids(['a','b'])==['a','b']
        with pytest.raises(ValueError,match='DUPLICATE'):reader.ordered_ids(['a','a'])


def test_stale_payload_rejected(tmp_path):
    cat=fixture_catalog(tmp_path)
    (tmp_path/'one.tar').write_bytes(b'corrupt')
    with OriginalReader(cat) as reader,pytest.raises(ValueError,match='P3_PAYLOAD'):
        reader._open('a')


def test_exception_closes_shard(tmp_path):
    reader=OriginalReader(fixture_catalog(tmp_path))
    with pytest.raises(RuntimeError):
        with reader:
            reader._open('a');raise RuntimeError('simulated OOM or interruption')
    assert reader.archive.closed and reader.path is None


def test_reader_is_s10_only_and_keeps_scientific_source_registry():
    import ast
    from training_runtime_provenance import runtime_implementation_provenance
    root=Path(__file__).resolve().parents[2]
    # Runtime implementation files must never be modified to speed up this consumer.
    from retrieval_lineage import config
    from retrieval_artifacts import read_json
    cfg=config(root/'config/retrieval_visualization.yml')
    campaign=read_json(cfg['campaign'])
    assert runtime_implementation_provenance(root)['implementation_sha256']==campaign['runtime_implementation_sha256']
    tree=ast.parse((root/'python/retrieval_originals.py').read_text())
    modules={node.module for node in ast.walk(tree) if isinstance(node,ast.ImportFrom)}
    assert not {'evaluation','evaluation_inputs','training'} & modules


def test_common_prepared_verification_is_local_to_one_validation(tmp_path,monkeypatch):
    import retrieval_pipeline as pipeline
    from retrieval_artifacts import publish,load,publish_bytes
    from retrieval_ranking import sample_queries
    models=[{'configuration_id':name,'group':'OFAT','checkpoint_id':name} for name in ('main','other')]
    ctx={'generation_id':'fixture','runtime_id':'fixture','scope':'noncanonical_smoke'}
    cfg={'query_seed':1,'top_k':2}
    m=publish(tmp_path/'models.json','models',{**ctx,'models':models,'config':cfg})
    gallery=[{'scene_id':f's{i}','center_x':i*2000.,'center_y':0.} for i in range(5)]
    g=publish(tmp_path/'gallery.json','gallery',{**ctx,'model_manifest_id':load(m)['artifact_id'],'rows':gallery})
    q=publish(tmp_path/'queries.json','queries',{**ctx,'model_manifest_id':load(m)['artifact_id'],
        'gallery_manifest_id':load(g)['artifact_id'],'seed':1,'rows':sample_queries(gallery,1,2,5)})
    binding=pipeline.bindings(*pipeline.common(m,g,q))
    payload=publish_bytes(tmp_path/'original','input'.encode())
    prepared=publish(tmp_path/'prepared.json','original_inputs',binding,[payload])
    paths=[]
    for model in models:
        root=tmp_path/model['configuration_id'];root.mkdir()
        buffer=io.BytesIO();np.save(buffer,np.array([[1.,0.]]*5,dtype=np.float32))
        v=publish_bytes(root/'vectors.npy',buffer.getvalue())
        e=publish(root/'embedding.json','embeddings',{**binding,'model':model,'scene_ids':[r['scene_id'] for r in gallery],
            'prepared_manifest':prepared,'prepared_manifest_id':load(prepared)['artifact_id']},[v])
        paths.append(pipeline.rankings(m,g,q,e))
    calls=[]
    def counted(path,kind=None):
        if kind=='original_inputs':calls.append(path)
        return load(path,kind)
    monkeypatch.setattr(pipeline,'load',counted)
    assert len(pipeline.validate_rankings(m,g,q,paths))==16
    assert len(calls)==1
    payload.write_bytes(b'wrong')
    with pytest.raises(ValueError,match='ARTIFACT_HASH'):pipeline.validate_rankings(m,g,q,paths)
    assert len(calls)==2


def test_empty_edge_batch_context_characterization():
    """Records the reason batching is blocked; does not repair frozen S09 math."""
    import torch
    from training_support import deterministic_relation_layer
    from scene_encoder import RelationAwareLayer
    torch.manual_seed(1)
    layer=RelationAwareLayer(8,2,3,0.).eval()
    with torch.no_grad():
        layer.output.bias.copy_(torch.arange(8,dtype=torch.float32)/10)
        values=torch.randn(3,8)
        singleton=deterministic_relation_layer(layer,values[:1],torch.empty((2,0),dtype=torch.int64),torch.empty((0,3)))
        mixed=deterministic_relation_layer(layer,values,torch.tensor([[1],[2]]),torch.zeros((1,3)))
    assert not torch.allclose(singleton,mixed[:1],atol=2e-6,rtol=2e-5)


def test_vector_render_reader_never_loads_raster_or_graph(monkeypatch):
    reader=OriginalReader(SimpleNamespace())
    monkeypatch.setattr(reader,'_open',lambda sid:{'scene_id':sid})
    visited=[]
    def rows(name,sid):
        visited.append(name)
        if name=='raster/scene_raster_index.parquet':
            return [{'split':'evaluation','xmin':0.,'ymin':0.,'xmax':500.,'ymax':500.}]
        assert name.startswith('vector/')
        return []
    monkeypatch.setattr(reader,'_rows',rows)
    monkeypatch.setattr(reader,'_raster',lambda _:pytest.fail('render cannot extract rasters'))
    with reader:
        scene=reader.read('scene',vectors_only=True)
    assert scene['center']==(250.,250.) and scene['entities']==[]
    assert len(visited)==4 and 'rasters' not in scene
