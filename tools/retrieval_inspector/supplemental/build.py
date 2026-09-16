"""Supplemental display publisher. Never executes the S10 scientific pipeline.

Reads accepted rankings, SVGs and stored original-input tensors. Categorical counts
and raster colour mapping are display summaries, not new scientific artifacts.
"""
import argparse
import base64
from collections import Counter, defaultdict
import io
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image
import pyarrow.parquet as pq
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'python'))
from retrieval_artifacts import load, read_json, file_hash, digest, encoded, publish_bytes, require

ACCEPTANCE = 's10_acceptance_5471f74031f267c4253df231'
# UI palette inherited from augmentation_inspector; channel 1 is palette entry 1.
PALETTE = ['#e41a1c','#377eb8','#4daf4a','#984ea3','#ff7f00','#ffff33','#a65628','#f781bf','#999999','#66c2a5','#fc8d62','#8da0cb','#e78ac3','#a6d854','#ffd92f','#e5c494','#b3b3b3','#1b9e77','#d95f02','#7570b3','#e7298a','#6a3d9a']


def labels(source):
    """Decode persisted indices using the accepted vocabulary's exact ordering."""
    result = {}
    for attr in ('A9', 'A11', 'ROAD_RANK', 'CLASS_L1'):
        rows = sorted((r for r in source['entries'] if r['attribute'] == attr),
                      key=lambda r: (int(r['source_order']), str(r['category_key']).encode()))
        result[attr] = [str(r['category_key']) + (' · ' + str(r['source_label']) if r.get('source_label') and str(r['source_label']) != str(r['category_key']) else '') for r in rows] + ['Unknown / missing', 'Masked']
    return result


def counts(values, names):
    c = Counter(int(v) for v in values)
    require(all(0 <= k < len(names) for k in c), 'VIEWER_CATEGORY_INDEX')
    return [{'label': names[k], 'value': v} for k, v in sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))]


def png(rgb, valid):
    rgba = np.concatenate([np.uint8(np.clip(rgb, 0, 255)), (np.asarray(valid, dtype=np.uint8)*255)[..., None]], axis=2)
    stream = io.BytesIO()
    Image.fromarray(rgba).save(stream, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(stream.getvalue()).decode()


def scene_display(sample, names):
    """Colour existing raster cells only: no extraction, interpolation or derivation."""
    e, r = sample['entities'], sample['rasters']
    lc = r['landcover_class_fraction'].numpy().astype(np.float64)
    valid = r['landcover_valid_mask'].numpy().astype(bool)
    support = r['landcover_valid_support'].numpy()
    dem = r['dem_standardized_mean'].numpy()
    dv = r['dem_valid_mask'].numpy().astype(bool)
    require(lc.shape == (22,100,100) and dem.shape == (17,17), 'VIEWER_RASTER_SHAPE')
    require(np.isfinite(lc).all() and np.isfinite(dem[dv]).all(), 'VIEWER_RASTER_FINITE')
    colors = np.array([[int(c[i:i+2],16) for i in (1,3,5)] for c in PALETTE])
    # Fraction-weighted colour, with no new class assignment or raster resampling.
    rgb = np.einsum('cyx,ck->yxk', lc, colors)
    mass = (lc * support[None] * valid[None]).sum(axis=(1,2))
    total = float(mass.sum())
    t = np.clip((np.where(dv, dem, 0)+3)/6, 0, 1)
    dem_rgb = np.stack((35+220*t,92+100*(1-np.abs(t-.5)*2),160-120*t),axis=-1)
    charts = {
        'POI categories · L1': counts(e['poi_category'][:,0].tolist(), names['CLASS_L1']),
        'Building use': counts(e['building_category'][:,0].tolist(), names['A9']),
        'Building structure': counts(e['building_category'][:,1].tolist(), names['A11']),
        'Road rank': counts(e['road_category'][:,0].tolist(), names['ROAD_RANK']),
        'Land cover composition': [{'label': f'LC {i+1}', 'value': float(v/total*100) if total else 0,
                                    'color': PALETTE[i]} for i,v in enumerate(mass) if v > 0],
    }
    return {'scene_id': sample['scene_id'], 'center': sample['scene_center_5186'].tolist(),
            'counts': {k: int(e[k+'_row_index'].numel()) for k in ('building','road','poi')},
            'ordered_edges': int(sample['edges']['edge_index'].shape[1]),
            'relation_masks': counts(sample['edges']['relation_mask'].tolist(), [str(i) for i in range(256)]),
            'charts': charts, 'lc': png(rgb,valid), 'dem': png(dem_rgb,dv),
            'lc_valid_cells': int(valid.sum()), 'dem_valid_cells': int(dv.sum())}


def top_five(rows, queries, model):
    grouped = defaultdict(list)
    for row in rows:
        require(row['model_id'] == model and row['query_id'] in queries, 'VIEWER_ROW_BINDING')
        require(row['retrieval_mode'] in ('standard','nonlocal'), 'VIEWER_MODE')
        if row['rank'] <= 5:
            grouped[(row['query_id'], row['retrieval_mode'])].append(row)
    for q in queries:
        for mode in ('standard','nonlocal'):
            require([r['rank'] for r in grouped[q,mode]] == [1,2,3,4,5], 'VIEWER_TOP5')
    return grouped


def build(root, destination, limit=None):
    root, destination = Path(root).resolve(), Path(destination).resolve()
    require(not destination.is_relative_to(root), 'VIEWER_SEPARATE_ROOT')
    acceptance = load(root/'acceptance.json','acceptance')
    require(acceptance['artifact_id'] == ACCEPTANCE and acceptance['body']['status'] == 'PASS', 'VIEWER_PARENT')
    bound = acceptance['body']['artifacts']
    consumed = {}
    def accepted(path, kind):
        path = Path(path)
        value = load(path,kind)
        require(bound.get(str(path)) == value['artifact_id'], 'VIEWER_ACCEPTED_BINDING')
        consumed[str(path)] = file_hash(path)
        return value
    queries = accepted(root/'query_manifest.json','queries')
    models = accepted(root/'model_manifest.json','models')
    gallery = accepted(root/'gallery_manifest.json','gallery')
    renders = accepted(root/'renders/manifest.json','renders')
    require(len(queries['body']['rows']) == 30 and len(models['body']['models']) == 28 and len(gallery['body']['rows']) == 9000, 'VIEWER_COUNTS')
    original = load(root/'original_inputs/manifest.json','original_inputs')
    consumed[str(root/'original_inputs/manifest.json')] = file_hash(root/'original_inputs/manifest.json')
    names_path = next(Path(p) for p in models['body']['config']['source_pins'] if p.endswith('/spatial_categories.json'))
    require(file_hash(names_path) == original['body']['categories_sha256'] == models['body']['config']['source_pins'][str(names_path)], 'VIEWER_VOCABULARY')
    names = labels(read_json(names_path))
    consumed[str(names_path)] = file_hash(names_path)
    qrows = queries['body']['rows']
    qids = [q['scene_id'] for q in qrows]
    data = {q: {} for q in qids}
    for m in models['body']['models']:
        mid = m['configuration_id']
        rank = accepted(root/'rankings'/mid/'manifest.json','rankings')
        for key,value in [('query_manifest_id',queries['artifact_id']),('gallery_manifest_id',gallery['artifact_id']),('model_manifest_id',models['artifact_id'])]:
            require(rank['body'][key] == value == original['body'][key], 'VIEWER_COMMON_BINDING')
        # Verify the accepted ranking -> embedding -> prepared input binding without inference.
        emb = load(rank['body']['embedding_manifest'],'embeddings')
        require(emb['artifact_id'] == rank['body']['embedding_manifest_id'] and emb['body']['prepared_manifest_id'] == original['artifact_id'], 'VIEWER_PREPARED_BINDING')
        consumed[rank['body']['embedding_manifest']] = file_hash(rank['body']['embedding_manifest'])
        rows = pq.read_table(root/'rankings'/mid/rank['files'][0]['path']).to_pylist()
        require(len(rows) == 3000, 'VIEWER_RANK_COUNT')
        groups = top_five(rows,qids,mid)
        for q in qids:
            data[q][mid] = {mode: groups[q,mode] for mode in ('standard','nonlocal')}
    selected = qrows[:limit] if limit else qrows
    source = Path(__file__).parent
    code = {p.name:file_hash(p) for p in sorted(source.iterdir()) if p.suffix in ('.py','.js','.css','.html')}
    identity = {'parent':acceptance['artifact_id'], 'parent_sha256':file_hash(root/'acceptance.json'),
                'sources':consumed,'code':code,'query_count':len(selected),'scope':'supplemental UI only'}
    out = destination / ('viewer_'+digest(identity)[:24])
    require(not out.exists(), 'VIEWER_OUTPUT_EXISTS')
    files = {}
    def put(name, raw):
        publish_bytes(out/name,raw)
        files[name] = file_hash(out/name)
    for name in ('app.js','style.css'):
        put(name,(source/name).read_bytes())
    scene_ids = {q['scene_id'] for q in selected}
    for q in selected:
        for modes in data[q['scene_id']].values():
            for rows in modes.values(): scene_ids.update(r['gallery_scene_id'] for r in rows)
    by_scene = {s['scene_id']:s for s in renders['body']['scenes']}
    verified = {(root/'renders'/f['path']).resolve() for f in renders['files']}
    original_files = {f['path']:f for f in original['files']}
    for i,sid in enumerate(sorted(scene_ids)):
        require(sid in by_scene and Path(by_scene[sid]['path']).resolve() in verified, 'VIEWER_SVG_BINDING')
        require(sid+'.pt' in original_files, 'VIEWER_INPUT_MISSING')
        sample = torch.load(root/'original_inputs'/(sid+'.pt'), map_location='cpu', weights_only=True)
        require(sample['scene_id'] == sid and sample['split'] == 'evaluation', 'VIEWER_SCENE_BINDING')
        display = scene_display(sample,names)
        display['svg'] = Path(by_scene[sid]['path']).read_text()
        put('scenes/'+sid+'.json',encoded(display))
        if i%100 == 0: print(f'display scenes {i+1}/{len(scene_ids)}',flush=True)
    config = {'acceptance':acceptance['artifact_id'],'queries':selected,
              'models':[{'id':m['configuration_id'],'group':m['group']} for m in models['body']['models']],
              'gallery_count':9000,'palette':PALETTE}
    for q in selected: put('queries/'+q['scene_id']+'.json',encoded(data[q['scene_id']]))
    config['files'] = files.copy()
    put('config.json',encoded(config))
    template = (source/'index.html').read_text().replace('__CONFIG_SHA__',files['config.json'])
    for i,q in enumerate(selected):
        put(f'query_{q["query_index"]:02d}.html',template.replace('__QUERY__',str(i)).encode())
    put('index.html',template.replace('__QUERY__','0').encode())
    # Validate sources again, never modify an accepted file.
    require(all(file_hash(p)==h for p,h in consumed.items()), 'VIEWER_SOURCE_CHANGED')
    require(file_hash(root/'acceptance.json') == identity['parent_sha256'], 'VIEWER_ACCEPTANCE_CHANGED')
    receipt = {**identity,'files':files,'scene_count':len(scene_ids),'output':str(out),'scientific_mutation':False}
    publish_bytes(out/'viewer_receipt.json',encoded(receipt))
    print(json.dumps({'output':str(out),'scenes':len(scene_ids),'pages':len(selected)},indent=2),flush=True)
    return out


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--generation',required=True)
    parser.add_argument('--output-root',required=True)
    parser.add_argument('--smoke-query-count',type=int,choices=[1,2])
    args = parser.parse_args()
    torch.set_num_threads(1)
    build(args.generation,args.output_root,args.smoke_query_count)
