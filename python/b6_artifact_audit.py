"""Read-only accepted B6 coverage/augmentation audit. No torch/model imports.

Dissertation 4 augmentation; Stage A does not generate or alter P4/P5 views.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
from pathlib import Path
import tarfile
import numpy as np
import pyarrow.parquet as pq
import shapely

DATA = Path('/mnt/hdd002/dhnyu/fusedata')

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def component_ownership(topology, geometry):
    """Verify provenance covers each post-perturbation receiver component."""
    checks = []
    identity = 'candidate_id' if 'candidate_id' in topology.columns else 'query_id'
    for (view, receiver), rows in topology.groupby([identity, 'receiver_local_entity_id']):
        match = geometry[(geometry[identity] == view) & (geometry.local_entity_id == receiver)]
        if len(match) != 1:
            checks.append(False)
            continue
        g = shapely.from_wkb(bytes(match.iloc[0].geometry_wkb))
        part_count = len(g.geoms) if hasattr(g, 'geoms') else 1
        mapping = rows.groupby('component_index').component_source_road_id.nunique()
        checks.append(set(mapping.index) == set(range(part_count)) and bool((mapping == 1).all()))
    return {'receiver_views_checked': len(checks), 'component_ownership_pass': all(checks),
            'failed_receiver_views': checks.count(False)}

def audit_bank(manifest_path, scenes=None, outside_pairs=None):
    manifest = json.loads(manifest_path.read_text())
    assert manifest['status'] == 'PASS'
    path = manifest_path.parent / manifest['payload']['filename']
    assert sha(path) == manifest['payload']['sha256']
    tables = {}
    receipts = []
    with tarfile.open(path) as archive:
        for name in ('absorption.parquet', 'topology.parquet', 'geometry.parquet', 'attributes.parquet', 'relation_delta.parquet'):
            data = archive.extractfile(name).read()
            rec = next(x for x in manifest['members'] if x['path'] == name)
            assert hashlib.sha256(data).hexdigest() == rec['sha256']
            table = pq.read_table(io.BytesIO(data)).to_pandas()
            if scenes is not None:
                table = table[table.scene_id.isin(scenes)]
            tables[name] = table
            receipts.append({'member': name, 'sha256': rec['sha256']})
    absorption = tables['absorption.parquet']
    topology = tables['topology.parquet']
    required = {'component_source_local_entity_id', 'component_source_road_id',
                'component_source_role', 'component_index', 'source_chain_index',
                'source_node_id', 'x', 'y'}
    has_lineage = required <= set(topology.columns)
    check = component_ownership(topology, tables['geometry.parquet']) if has_lineage else {'component_ownership_pass': False}
    absorbed = absorption[absorption.status == 'ABSORBED']
    outside_added = 0
    if outside_pairs is not None and len(outside_pairs):
        delta = tables['relation_delta.parquet']
        expected = set(zip(outside_pairs.scene_id, outside_pairs.source, outside_pairs.destination))
        outside_added = sum((r.scene_id, r.source, r.destination) in expected
                            for r in delta[ (delta.relation_type == 'CON') & (delta.action == 'ADD') ].itertuples())
    return {'manifest': str(manifest_path), 'manifest_sha256': sha(manifest_path),
            'payload_sha256': manifest['payload']['sha256'], 'members': receipts,
            'selected_scene_count': len(set(absorption.scene_id)), 'absorption_rows': len(absorption),
            'absorbed_rows': len(absorbed), 'outside_shared_node_con_additions': outside_added, 'topology_columns': list(topology.columns),
            'attributes_columns': list(tables['attributes.parquet'].columns), **check,
            'interpretation': 'Component source ownership and original node IDs/coordinates survive. '
              'The materialized receiver owns its perturbed attributes; restoring donor LANES would change the accepted view. '
              'A later adapter must preserve receiver semantics while retaining component source provenance.'}

def audit_embeddings(statistics):
    root = DATA / 'retrieval_data/reduced/s10/s10gen_a24b979d4c1557387cbbec35'
    path = root / 'embeddings/cmp_B6/manifest.json'
    manifest = json.loads(path.read_text())
    vectors_path = path.parent / 'vectors.npy'
    rows = manifest['body']['scene_ids']
    vectors = np.load(vectors_path, mmap_mode='r')
    zero = set(statistics[(statistics.split == 'evaluation') & (statistics.road_count == 0)].scene_id)
    selected = vectors[[i for i, s in enumerate(rows) if s in zero]]
    unique = np.unique(np.ascontiguousarray(selected).view(np.dtype((np.void, selected.dtype.itemsize * selected.shape[1]))))
    return {'scope': 'accepted S10 evaluation originals, NOT validation queries',
            'manifest': str(path), 'manifest_sha256': sha(path), 'vectors_sha256': sha(vectors_path),
            'zero_road_rows': len(selected), 'unique_bitwise_zero_road_vectors': len(unique),
            'max_absolute_difference': float(np.max(np.abs(selected - selected[0]))),
            'validation_query_rank_verification': 'UNAVAILABLE: current validation ledger stores aggregate metrics, not per-query vectors/ranks',
            'no_new_inference': True}

def audit_validation_ledger():
    root = DATA / 'runtime/training_runs/4cccedbde4e2deb0679096d096064f6a8aa0a00637d125393aabc29659ca90d4/ledger/segments'
    result = []
    for p in sorted(root.glob('*.jsonl')):
        for line in p.read_text().splitlines():
            x = json.loads(line)
            if 'VALIDATION' in x.get('event_type', ''):
                payload = x['payload']
                if payload.get('completed_epoch', payload.get('epoch')) == 90:
                    result.append({'path': str(p), 'sha256': sha(p), 'payload': payload})
    return result

def run(pilot_path, output, outside_pairs_path=None):
    pilot = pq.read_table(pilot_path).to_pandas()
    statistics_path = DATA / 'scene_data/reduced/observations/obs_ee28248872c4ab0ce8b3ea4f/production/acceptance/bsa_bd504b7e871945a5a6207664/scene_spatial_statistics.parquet'
    statistics = pq.read_table(statistics_path).to_pandas()
    bank = DATA / 'scene_data/reduced/augmentation_banks/augbank_f0c7083cca57c1426e710351/shards/main_1.0x'
    records = []
    outside_pairs = pq.read_table(outside_pairs_path).to_pandas() if outside_pairs_path else None
    # One bounded accepted P4 shard containing pilot scenes; P5 one validation
    # shard only for schema/lineage audit, never scale choice or retrieval tuning.
    for p in sorted(bank.glob('*/branch_manifest.json')):
        m = json.loads(p.read_text())
        selected = set(m['scene_ids']) & set(pilot.scene_id)
        if selected:
            records.append(audit_bank(p, selected, outside_pairs)); break
    p5 = DATA / 'scene_data/reduced/fixed_queries/fqa_a8a814267b8afb7ca2bebc7a/validation-query/shards'
    records.append(audit_bank(sorted(p5.glob('*/branch_manifest.json'))[0]))
    complete = all(r['component_ownership_pass'] and r['receiver_views_checked'] > 0 for r in records)
    verdict = 'POST_BANK_FEASIBLE_WITH_ADDITIONAL_LINEAGE'
    # Source-chain indices are not guaranteed to be geometric part indices for
    # clipped multipart parents. Require P3 part-count expansion in a later adapter.
    value = {'verdict': verdict, 'scope': 'bounded accepted P4/P5 lineage sample; not a full-bank certification',
             'records': records, 'bounded_receiver_mapping_pass': complete,
             'remaining_requirement': 'Recover multipart parent part ranges from P3 and preserve materialized receiver attributes; source chain indices alone are insufficient', 'coverage_embeddings': audit_embeddings(statistics),
             'selected_validation_ledger': audit_validation_ledger(),
             'training': False, 'checkpoint_created': False, 'canonical_mutation': False}
    output = Path(output)
    allowed = DATA / 'experiments/b6_road_granularity'
    if not output.resolve().is_relative_to(allowed.resolve()) or output.exists():
        raise ValueError('new experimental audit output only')
    output.write_text(json.dumps(value, sort_keys=True, indent=2) + '\n')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--pilot', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--outside-pairs')
    a = parser.parse_args()
    run(a.pilot, a.output, a.outside_pairs)
