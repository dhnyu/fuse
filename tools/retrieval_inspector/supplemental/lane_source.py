"""Read raw LANES from the exact accepted P3 parent payload, without preprocessing.

No external GIS source, spatial/nearest join, lane inference or inverse scaling.
The index is pinned in the accepted S10 model manifest. Every tar is SHA-verified.
"""
import io
from pathlib import Path
import tarfile

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
from retrieval_artifacts import file_hash, require


def load_lanes(model_manifest, scene_ids):
    body=model_manifest['body']
    pins=body['config']['source_pins']
    index_path=next(Path(p) for p in pins if p.endswith('/scene_to_shard.parquet'))
    require(file_hash(index_path)==pins[str(index_path)], 'LANE_INDEX_HASH')
    index=pq.read_table(index_path)
    entries=index.filter(pc.is_in(index['scene_id'],value_set=pa.array(sorted(scene_ids)))).to_pylist()
    require(len(entries)==len(scene_ids) and {e['scene_id'] for e in entries}==set(scene_ids), 'LANE_INDEX_MEMBERSHIP')
    root=Path(body['roots']['p3']).resolve()
    result={};sources={str(index_path):pins[str(index_path)]}
    grouped={}
    for row in entries:
        require(row['cache_id']==body['parents']['scene_cache_id'], 'LANE_CACHE_BINDING')
        grouped.setdefault(row['branch_id'],[]).append(row)
    for branch,rows in sorted(grouped.items()):
        path=(root/'shards'/branch/rows[0]['payload_filename']).resolve()
        require(path.is_relative_to(root/'shards') and len({r['payload_sha256'] for r in rows})==1 and
                file_hash(path)==rows[0]['payload_sha256'], 'LANE_PAYLOAD_HASH')
        sources[str(path)]=rows[0]['payload_sha256']
        with tarfile.open(path) as archive:
            member=archive.extractfile('vector/road_observed.parquet')
            require(member is not None, 'LANE_ROAD_PAYLOAD_MISSING')
            with member:
                table=pq.read_table(io.BytesIO(member.read()),columns=['scene_id','local_entity_id','LANES'])
        for parent in rows:
            selected=table.filter(pc.equal(table['scene_id'],parent['scene_id'])).to_pylist()
            # Canonical entity ID order; verify it against the stored road rows before display.
            selected.sort(key=lambda r:int(r['local_entity_id']))
            result[parent['scene_id']]={'parent':parent,'rows':selected}
    return result,sources
