"""Publish supplemental full-order bands and a legacy-layout viewer.

This is NOT a formal S10 execution/acceptance. Reads accepted vectors; never loads
checkpoints or invokes inference, Fourier features or input preprocessing.
"""
import argparse
from pathlib import Path
import sys
import json
import re
import time
import numpy as np
import torch
import pyarrow.parquet as pq
from threadpoolctl import threadpool_limits

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE));sys.path.insert(0,str(HERE.parents[2]/'python'))
from retrieval_artifacts import load, read_json, encoded, digest, file_hash, publish_bytes, require
from retrieval_render import render_scene
from build import labels, scene_display, ACCEPTANCE
from thematic import bind, bind_lanes
from bands import reconstruct
from scene_sources import scene_sources

PREVIOUS=Path('/mnt/hdd002/dhnyu/fusedata/retrieval_data/reduced/s10_viewers/viewer_f8d14a826a75bc8451f219c5')


def legacy_css():
    """Copy the historical comparison DOM's exact CSS declarations, scoped to it."""
    source=(HERE/'legacy_retrieval_10c02e4.css').read_text()
    names=('.comparison','.column','.column-head','.rank-meta','.strip','.strip-spacer','.row','.row-title','.map-frame')
    result=[]
    # Base comparison rules precede the first media query; no global/header tokens copied.
    for selector,body in re.findall(r'([^{}]+)\{([^{}]*)\}',source.split('@media',1)[0]):
        if any(selector==n or selector.startswith(n+' ') or selector.startswith(n+':') for n in names):
            target='#comparison' if selector=='.comparison' else '#comparison '+selector
            result.append(target+'{'+body+'}')
    return '\n'.join(result)+'\n'


def build_bands(root,destination,smoke=False):
    started=time.monotonic();root=Path(root).resolve();destination=Path(destination).resolve()
    require(not destination.is_relative_to(root),'BANDS_SEPARATE_ROOT')
    a=load(root/'acceptance.json','acceptance');require(a['artifact_id']==ACCEPTANCE and a['body']['status']=='PASS','BANDS_PARENT')
    sources={str(root/'acceptance.json'):file_hash(root/'acceptance.json')}
    def accepted(path,kind):
        value=load(path,kind);require(a['body']['artifacts'].get(str(path))==value['artifact_id'],'BANDS_ACCEPTED_ID')
        sources[str(path)]=file_hash(path);return value
    q=accepted(root/'query_manifest.json','queries');g=accepted(root/'gallery_manifest.json','gallery');m=accepted(root/'model_manifest.json','models')
    render_manifest=accepted(root/'renders/manifest.json','renders')
    prepared=load(root/'original_inputs/manifest.json','original_inputs');sources[str(root/'original_inputs/manifest.json')]=file_hash(root/'original_inputs/manifest.json')
    require(len(q['body']['rows'])==30 and len(g['body']['rows'])==9000 and len(m['body']['models'])==28,'BANDS_COUNTS')
    selected_q=q['body']['rows'][:1] if smoke else q['body']['rows']
    selected_m=m['body']['models'][:1] if smoke else m['body']['models']
    all_data={r['scene_id']:{} for r in selected_q};embedding_ids={}
    for model in selected_m:
        mid=model['configuration_id'];r=accepted(root/'rankings'/mid/'manifest.json','rankings')
        ep=Path(r['body']['embedding_manifest']);e=load(ep,'embeddings');sources[str(ep)]=file_hash(ep)
        require(e['artifact_id']==r['body']['embedding_manifest_id'] and e['body']['model']==model and
                e['body']['prepared_manifest_id']==prepared['artifact_id'] and e['body']['scene_ids']==[s['scene_id'] for s in g['body']['rows']], 'BANDS_EMBEDDING_BINDING')
        for key,value in [('query_manifest_id',q['artifact_id']),('gallery_manifest_id',g['artifact_id']),('model_manifest_id',m['artifact_id'])]:
            require(r['body'][key]==e['body'][key]==prepared['body'][key]==value,'BANDS_COMMON_BINDING')
        vectors=np.load(ep.parent/e['files'][0]['path'],allow_pickle=False)
        formal=pq.read_table(root/'rankings'/mid/r['files'][0]['path']).to_pylist()
        with threadpool_limits(limits=1):
            result=reconstruct(vectors,g['body']['rows'],q['body']['rows'],mid,formal)
        embedding_ids[mid]=e['artifact_id']
        for query in selected_q:all_data[query['scene_id']][mid]=result[query['scene_id']]
        print('Verified exact formal Top50:',mid,flush=True)
    scenes={r['scene_id'] for r in selected_q}
    for models in all_data.values():
        for modes in models.values():
            for mode in modes.values():
                for rows in mode['bands'].values():scenes.update(r['gallery_scene_id'] for r in rows)
    previous=read_json(PREVIOUS/'viewer_receipt.json')
    require(previous['parent']==ACCEPTANCE and previous['parent_sha256']==sources[str(root/'acceptance.json')], 'BANDS_PREVIOUS_PARENT')
    sources[str(PREVIOUS/'viewer_receipt.json')]=file_hash(PREVIOUS/'viewer_receipt.json')
    code={p.name:file_hash(p) for p in HERE.iterdir() if p.suffix in ('.py','.js','.css','.html')}
    aug=HERE.parents[1]/'augmentation_inspector/inspector.py';code['augmentation_inspector']=file_hash(aug)
    identity={'parent':ACCEPTANCE,'sources':sources.copy(),'code':code,'scope':'noncanonical smoke' if smoke else 'supplemental full-order display bands',
              'embedding_manifest_ids':embedding_ids,'bands_implementation_sha256':file_hash(HERE/'bands.py'),
              'raster_display_implementation_sha256':file_hash(HERE/'bands_app.js'),
              'selection':'legacy 10c02e4: middle starts floor((N-10)/2)+1; 31 selected ranks from full eligible order'}
    out=destination/('viewer_'+digest(identity)[:24]);require(not out.exists(),'BANDS_IMMUTABLE_OUTPUT_EXISTS')
    files={}
    def put(name,raw):
        publish_bytes(out/name,raw);files[name]=file_hash(out/name)
    for name in ('app.js','style.css','bands_app.js','bands.css'):put(name,(HERE/name).read_bytes())
    put('augmentation.css',aug.read_text().split('<style>',1)[1].split('</style>',1)[0].encode())
    put('legacy_bands.css',legacy_css().encode())
    for query in selected_q:put('queries/'+query['scene_id']+'.json',encoded(all_data[query['scene_id']]))
    band_receipt={**identity,'query_manifest_id':q['artifact_id'],'gallery_manifest_id':g['artifact_id'],
                  'eligible_universe':9000,'formal_top50_exact':True,'full_order_not_published':True,
                  'band_rows':len(selected_q)*len(selected_m)*2*31,'files':files.copy()}
    band_receipt['evidence_id']='s10_supplemental_bands_'+digest(band_receipt)[:24]
    put('band_evidence_receipt.json',encoded(band_receipt))
    names_path=Path(m['body']['roots']['categories']);require(file_hash(names_path)==prepared['body']['categories_sha256'],'DISPLAY_CATEGORIES')
    names=labels(read_json(names_path));originals={r['path']:r for r in prepared['files']}
    rendered={r['scene_id']:r for r in render_manifest['body']['scenes']}
    for module in ('python/retrieval_render.py','python/retrieval_originals.py','python/model_data.py'):
        require(file_hash(HERE.parents[2]/module)==m['body']['runtime']['sources'][module],'DISPLAY_IMPLEMENTATION')
    n=0
    for scene,lanes,parent_sources in scene_sources(m,scenes):
        sources.update(parent_sources);sid=scene['scene_id'];name='scenes/'+sid+'.json'
        if name in previous['files']:
            require(file_hash(PREVIOUS/name)==previous['files'][name],'DISPLAY_PREVIOUS_HASH')
            display=read_json(PREVIOUS/name)
        else:
            sample=torch.load(root/'original_inputs'/(sid+'.pt'),map_location='cpu',weights_only=True)
            require(sample['lineage']['parent']==scene['parent'] and sample['scene_id']==sid and sample['split']=='evaluation','DISPLAY_INPUT_BINDING')
            require(sample['entities']['local_entity_id'].tolist()==[r['local_entity_id'] for r in scene['entities']], 'DISPLAY_ENTITY_ORDER')
            # Existing immutable, clipped observed geometry -> SVG only. No tensorization.
            record=rendered.get(sid)
            if record is None:
                record=render_scene(scene,scene['parent']['payload_sha256'],out/'vector_assets')
                rel=str(Path(record['path']).relative_to(out));files[rel]=file_hash(record['path'])
            display=scene_display(sample,names);display['svg']=Path(record['path']).read_text()
            display['thematic']=bind(sample,display['svg'],record,names,originals[sid+'.pt']['sha256'])
            display['thematic']['maps']['Road lane']=bind_lanes(sample,lanes)
            display['thematic']['road_lane']={'available':True,'source':'same accepted P3 parent payload; raw LANES, no inverse normalization'}
        require(display['scene_id']==sid and display['thematic']['binding']['p3_payload_sha256']==scene['parent']['payload_sha256'],'DISPLAY_REUSED_BINDING')
        put(name,encoded(display));n+=1
        if n%100==0:print(f'Display-only scenes {n}/{len(scenes)}',flush=True)
    config={'acceptance':ACCEPTANCE,'queries':selected_q,'models':[{'id':r['configuration_id'],'group':r['group']} for r in selected_m],
            'gallery_count':9000,'palette':__import__('build').PALETTE,'files':files.copy(),'evidence_id':band_receipt['evidence_id']}
    put('config.json',encoded(config))
    template=(HERE/'bands.html').read_text().replace('__CONFIG_SHA__',files['config.json'])
    for i,query in enumerate(selected_q):put(f'query_{query["query_index"]:02d}.html',template.replace('__QUERY__',str(i)).encode())
    put('index.html',template.replace('__QUERY__','0').encode())
    require(all(file_hash(p)==h for p,h in sources.items()),'BANDS_SOURCE_CHANGED')
    receipt={**identity,'sources':sources,'files':files,'band_evidence_id':band_receipt['evidence_id'],'scene_count':len(scenes),'output':str(out),'scientific_mutation':False}
    put('viewer_receipt.json',encoded(receipt))
    print(json.dumps({'output':str(out),'scenes':len(scenes),'band_rows':band_receipt['band_rows'],'elapsed_s':time.monotonic()-started}),flush=True)
    return out


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--generation',required=True);parser.add_argument('--output-root',required=True);parser.add_argument('--smoke',action='store_true')
    args=parser.parse_args();torch.set_num_threads(1);build_bands(args.generation,args.output_root,args.smoke)
