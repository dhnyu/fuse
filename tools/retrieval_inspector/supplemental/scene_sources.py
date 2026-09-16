"""Stream exact accepted P3 vector records for display, never preprocess them."""
import io
from pathlib import Path
import tarfile
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
from retrieval_artifacts import file_hash, require


def scene_sources(model, scene_ids):
    body=model['body'];pins=body['config']['source_pins']
    ip=next(Path(p) for p in pins if p.endswith('/scene_to_shard.parquet'))
    require(file_hash(ip)==pins[str(ip)],'DISPLAY_INDEX_HASH')
    index=pq.read_table(ip);entries=index.filter(pc.is_in(index['scene_id'],value_set=pa.array(sorted(scene_ids)))).to_pylist()
    require(len(entries)==len(scene_ids) and {e['scene_id'] for e in entries}==set(scene_ids),'DISPLAY_INDEX_MEMBERSHIP')
    root=Path(body['roots']['p3']).resolve();groups={}
    for p in entries:
        require(p['cache_id']==body['parents']['scene_cache_id'],'DISPLAY_CACHE')
        groups.setdefault(p['branch_id'],[]).append(p)
    for branch,parents in sorted(groups.items()):
        path=(root/'shards'/branch/parents[0]['payload_filename']).resolve()
        require(path.is_relative_to(root/'shards') and all(p['payload_sha256']==parents[0]['payload_sha256'] for p in parents)
                and file_hash(path)==parents[0]['payload_sha256'],'DISPLAY_PAYLOAD_HASH')
        with tarfile.open(path) as archive:
            tables={}
            for kind,name in [('B','building'),('R','road'),('P','poi')]:
                columns=['scene_id','local_entity_id','observed_geometry','scene_center_x_5186','scene_center_y_5186']
                if kind=='R':columns+=['LANES']
                with archive.extractfile(f'vector/{name}_observed.parquet') as member:
                    tables[kind]=pq.read_table(io.BytesIO(member.read()),columns=columns)
            # Stored extent supplies an exact center for scenes with no vector entities.
            with archive.extractfile('raster/scene_raster_index.parquet') as member:
                extents=pq.read_table(io.BytesIO(member.read()),columns=['scene_id','xmin','xmax','ymin','ymax'])
        for parent in parents:
            sid=parent['scene_id'];entities=[];roads=[]
            for kind,table in tables.items():
                rows=table.filter(pc.equal(table['scene_id'],sid)).to_pylist()
                entities.extend({**r,'entity_type':kind} for r in rows)
                if kind=='R':roads=sorted(rows,key=lambda r:r['local_entity_id'])
            entities.sort(key=lambda r:r['local_entity_id'])
            bounds=extents.filter(pc.equal(extents['scene_id'],sid)).to_pylist()
            require(len(bounds)==1,'DISPLAY_EXTENT')
            b=bounds[0];center=((b['xmin']+b['xmax'])/2,(b['ymin']+b['ymax'])/2)
            require(not entities or (entities[0]['scene_center_x_5186'],entities[0]['scene_center_y_5186'])==center,'DISPLAY_CENTER_IDENTITY')
            yield {'scene_id':sid,'parent':parent,'entities':entities,'center':center}, {'parent':parent,'rows':roads}, {str(ip):pins[str(ip)],str(path):parent['payload_sha256']}
