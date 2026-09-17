"""Supplemental full-order viewer for the separately accepted S10 query revision.

Dissertation retrieval inspection; unchanged cosine and legacy full-order bands.
Only missing display scenes read stored tensors. No inference or tensorization.
"""
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time

import numpy as np
import pyarrow.parquet as pq
from threadpoolctl import threadpool_limits
from retrieval_artifacts import load,read_json,file_hash,require,encoded,digest
from s10_query_revision import validate_acceptance,parents,verified_embedding,ROOT

HERE=ROOT/'tools/retrieval_inspector/supplemental'


def build(config_path,acceptance_path):
    started=time.monotonic()
    cfg,root,a,m,g,q=validate_acceptance(config_path,acceptance_path)
    revision=Path(acceptance_path).parent
    canonical_counts=load(revision/'object_counts_manifest.json','summary')['body']['counts']
    sys.path.insert(0,str(HERE))
    from bands import reconstruct
    from build_bands import legacy_css
    parent=Path(cfg['display_parent']);previous=read_json(parent/'viewer_receipt.json')
    require(previous['parent']==cfg['parent_acceptance_id'] and previous['parent_sha256']==a['body']['parent_acceptance_sha256'],'VIEWER_DISPLAY_PARENT')
    sources={str(parent/'viewer_receipt.json'):file_hash(parent/'viewer_receipt.json'), str(acceptance_path):file_hash(acceptance_path)}
    for name,h in previous['files'].items():require(file_hash(parent/name)==h,'VIEWER_PARENT_HASH:'+name)
    location=read_json(parent/'location_metadata.json')
    require(previous['files']['location_metadata.json']==previous['location_metadata']['sha256'],'LOCATION_RECEIPT_BINDING')
    require(set(location['scenes'])=={r['scene_id'] for r in g['body']['rows']},'LOCATION_GALLERY')
    for r in g['body']['rows']:
        loc=location['scenes'][r['scene_id']]
        require((loc['center_x'],loc['center_y'])==(r['center_x'],r['center_y']),'LOCATION_CENTER')
    _,pa,pm,pg,pqold=parents(cfg)
    data={r['scene_id']:{} for r in q['body']['rows']};embedding_ids={}
    for model in m['body']['models']:
        mid=model['configuration_id'];ep,e,v=verified_embedding(root,pa,pm,pg,pqold,model)
        rp=revision/'rankings'/mid/'manifest.json';r=load(rp,'rankings')
        formal=pq.read_table(rp.parent/r['files'][0]['path']).to_pylist()
        with threadpool_limits(limits=1):selected=reconstruct(v,g['body']['rows'],q['body']['rows'],mid,formal)
        for sid in data:data[sid][mid]=selected[sid]
        embedding_ids[mid]=e['artifact_id'];sources[str(ep)]=file_hash(ep)
    scenes=set(data)
    for models in data.values():
        for modes in models.values():
            for mode in modes.values():
                for rows in mode['bands'].values():scenes.update(r['gallery_scene_id'] for r in rows)
    code={str(p.relative_to(ROOT)):file_hash(p) for p in HERE.iterdir() if p.suffix in ('.py','.js','.css','.html')}
    code['python/s10_query_viewer.py']=file_hash(__file__)
    identity={'parent':a['artifact_id'],'parent_sha256':file_hash(acceptance_path),'sources':sources,
              'code':code,'scope':'supplemental 100-query full-order bands and scene locations',
              'query_manifest_id':q['artifact_id'],'gallery_manifest_id':g['artifact_id'],
              'embedding_manifest_ids':embedding_ids,'display_parent':str(parent)}
    vid='viewer_'+digest(identity)[:24];output=Path(cfg['viewer_root'])/vid
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.s10-100-viewer-',dir=output.parent) as temp:
        stage=Path(temp);files={};reused={}
        def put(name,raw):
            p=stage/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw);files[name]=file_hash(p)
        for name in ['app.js','style.css','bands.css','locations.js','locations.css']:
            put(name,(HERE/name).read_bytes())
        # Only the dropdown label changes: the shared legacy UI implementation is preserved.
        js=(HERE/'bands_app.js').read_text()
        old='`${q.query_index}. ${q.scene_id}`';require(js.count(old)==1,'QUERY_LABEL_ANCHOR')
        put('bands_app.js',js.replace(old,'`${q.query_index} / ${config.queries.length} · ${q.scene_id}`').encode())
        put('augmentation.css',(parent/'augmentation.css').read_bytes());put('legacy_bands.css',legacy_css().encode())
        for sid,rows in data.items():put('queries/'+sid+'.json',encoded(rows))
        band={'parent':a['artifact_id'],'query_manifest_id':q['artifact_id'],'gallery_manifest_id':g['artifact_id'],
              'embedding_manifest_ids':embedding_ids,'band_rows':100*28*2*31,'formal_top50_exact':True,
              'selection':'legacy 10c02e4: middle starts floor((N-10)/2)+1; true bottom N-9..N',
              'eligible_universe':9000,'full_order_not_published':True,'files':{n:h for n,h in files.items() if n.startswith('queries/')}}
        band['evidence_id']='s10_supplemental_bands_'+digest(band)[:24]
        put('band_evidence_receipt.json',encoded(band))
        missing=[];display_sources={}
        for sid in sorted(scenes):
            name='scenes/'+sid+'.json'
            if name in previous['files']:
                display=read_json(parent/name);loc=location['scenes'][sid]
                require(display['scene_id']==sid and display['center']==[loc['center_x'],loc['center_y']],'DISPLAY_CENTER_BINDING')
                put(name,(parent/name).read_bytes());reused[name]=files[name]
            else:missing.append(sid)
        if missing:
            import torch
            from build import labels,scene_display
            from thematic import bind,bind_lanes
            from scene_sources import scene_sources
            from retrieval_render import render_scene
            # Parent file hashes, exact P3 entity ordering and tensor lineage are checked before rendering.
            prepared=load(root/'original_inputs/manifest.json','original_inputs')
            require(prepared['body']['query_manifest_id']==pqold['artifact_id'] and prepared['body']['gallery_manifest_id']==g['artifact_id'],'PREPARED_DISPLAY_BINDING')
            originals={r['path']:r for r in prepared['files']}
            categories=Path(m['body']['roots']['categories'])
            require(file_hash(categories)==prepared['body']['categories_sha256'],'DISPLAY_CATEGORIES')
            names=labels(read_json(categories))
            for module in ['python/retrieval_render.py','python/retrieval_originals.py','python/model_data.py']:
                require(file_hash(ROOT/module)==m['body']['runtime']['sources'][module],'DISPLAY_IMPLEMENTATION')
            for scene,lanes,parent_sources in scene_sources(m,missing):
                sid=scene['scene_id'];sample=torch.load(root/'original_inputs'/(sid+'.pt'),map_location='cpu',weights_only=True)
                require(sample['lineage']['parent']==scene['parent'] and sample['scene_id']==sid and sample['split']=='evaluation','DISPLAY_INPUT_BINDING')
                require(sample['entities']['local_entity_id'].tolist()==[r['local_entity_id'] for r in scene['entities']], 'DISPLAY_ENTITY_ORDER')
                record=render_scene(scene,scene['parent']['payload_sha256'],stage/'vector_assets')
                display=scene_display(sample,names);display['svg']=Path(record['path']).read_text()
                display['thematic']=bind(sample,display['svg'],record,names,originals[sid+'.pt']['sha256'])
                display['thematic']['maps']['Road lane']=bind_lanes(sample,lanes)
                display['thematic']['road_lane']={'available':True,'source':'same accepted P3 parent payload; raw LANES, no inverse normalization'}
                put('scenes/'+sid+'.json',encoded(display))
                display_sources.update(parent_sources)
            # SVG is embedded verbatim in scene JSON; redundant standalone copies are omitted.
            shutil.rmtree(stage/'vector_assets')
        require(all(file_hash(p)==h for p,h in display_sources.items()),'DISPLAY_SOURCE_CHANGED')
        for sid in scenes:
            display=read_json(stage/'scenes'/f'{sid}.json')
            require(display['counts']=={k:canonical_counts[sid][v] for k,v in [('building','n_buildings'),('road','n_roads'),('poi','n_pois')]},'DISPLAY_CANONICAL_ENTITY_COUNTS')
        put('location_metadata.json',(parent/'location_metadata.json').read_bytes())
        config={'acceptance':a['artifact_id'],'queries':q['body']['rows'],
                'models':[{'id':r['configuration_id'],'group':r['group']} for r in m['body']['models']],
                'gallery_count':9000,'palette':read_json(parent/'config.json')['palette'],
                'files':files.copy(),'evidence_id':band['evidence_id'],'location_metadata':previous['location_metadata']}
        put('config.json',encoded(config))
        html=(HERE/'bands.html').read_text().replace('__CONFIG_SHA__',files['config.json'])
        html=html.replace('</head>','<link rel="stylesheet" href="locations.css"></head>')
        html=html.replace('<script src="bands_app.js"></script>','<script src="locations.js"></script><script src="bands_app.js"></script>')
        for i in range(100):put(f'query_{i+1:02d}.html',html.replace('__QUERY__',str(i)).encode())
        put('index.html',html.replace('__QUERY__','0').encode())
        receipt={**identity,'viewer_id':vid,'output':str(output),'files':files,'reused_files':reused,
                 'band_evidence_id':band['evidence_id'],'scene_count':len(scenes),'new_display_scenes':len(missing),
                 'location_metadata':previous['location_metadata'],'scientific_mutation':False,'inference':False}
        require(all(file_hash(stage/n)==h for n,h in files.items()),'VIEWER_STAGING_HASH')
        require(all(file_hash(p)==h for p,h in sources.items()),'VIEWER_SOURCE_CHANGED')
        require(all(file_hash(ROOT/p)==h for p,h in code.items()),'VIEWER_CODE_CHANGED')
        # Receipt-last, create-or-validate; old and incomplete generations are never overwritten.
        if output.exists():
            require(read_json(output/'viewer_receipt.json')==receipt,'VIEWER_IMMUTABLE_COLLISION')
            require(all(file_hash(output/n)==h for n,h in files.items()),'VIEWER_EXISTING_HASH')
        else:
            output.mkdir()
            for child in stage.iterdir():os.rename(child,output/child.name)
            with (output/'viewer_receipt.json').open('xb') as f:f.write(encoded(receipt))
    print(json.dumps({'viewer':str(output),'scenes':len(scenes),'new_display_scenes':len(missing),'elapsed_s':time.monotonic()-started}),file=sys.stderr,flush=True)
    return [str(output/'viewer_receipt.json'),*[str(output/n) for n in files]]
