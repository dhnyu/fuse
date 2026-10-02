#!/usr/bin/env python3
"""Add display-only OBJ20 HIGH sets without changing population statistics."""
import json
import os
from pathlib import Path
import sys
import tempfile
import numpy as np
import pyarrow.parquet as pq
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
import s10_extreme_rank1 as base
from s10_extreme_rank1 import read,write,sha,digest,require,envelope,stats,make_bands

REPO=Path(__file__).resolve().parents[1]
DATA=Path('/mnt/hdd002/dhnyu/fusedata/retrieval_data/reduced')
PARENT=DATA/'s10_extreme_rank1/s10ext_e907433b34cee238114526a0'
ORIGINAL=DATA/'s10_extreme_viewers/viewer_49689e157402015da2e68b52'
PREVIOUS=DATA/'s10_extreme_nonempty/s10nonempty_88c61f8701b8c691b3f8bfc5'
OLD=DATA/'s10_extreme_viewers/viewer_7869c1a59347db22f6155d86'
DISPLAY=['STANDARD_HIGH_OBJ20','STANDARD_LOW','NONLOCAL_HIGH_OBJ20','NONLOCAL_LOW']
NEW=['STANDARD_HIGH_OBJ20','NONLOCAL_HIGH_OBJ20']
LABELS=dict(zip(DISPLAY,['Standard HIGH (obj ≥ 20)','Standard LOW','Non-local HIGH (obj ≥ 20)','Non-local LOW']))|{'STANDARD_HIGH':'Standard HIGH (all)','NONLOCAL_HIGH':'Non-local HIGH (all)','STANDARD_HIGH_NONEMPTY':'Standard HIGH (obj ≥ 1)','NONLOCAL_HIGH_NONEMPTY':'Non-local HIGH (obj ≥ 1)'}
DEFINITION='Display-only: queries with n_B+n_R+n_P >= 20; mode Rank1 cosine descending, query scene ID ascending; top 100. Gallery unchanged.'


def select(rows,counts,mode):
    score='rank1_cosine' if mode=='standard' else 'nonlocal_rank1_cosine'
    eligible=[r for r in rows if sum(counts[r['query_scene_id']][k] for k in ('n_buildings','n_roads','n_pois'))>=20]
    result=sorted(eligible,key=lambda r:(-r[score],r['query_scene_id']))[:100]
    require(len(result)==100,'Insufficient nonempty queries')
    return result


def hashes(root,receipt):
    result={}
    for f,h in receipt['files'].items():
        require(sha(root/f)==h,f'Parent hash changed: {root/f}');result[str(root/f)]=h
    result[str(root/'receipt.json' if (root/'receipt.json').exists() else root/'viewer_receipt.json')]=sha(root/('receipt.json' if (root/'receipt.json').exists() else 'viewer_receipt.json'))
    return result


def build():
    identity=read(PARENT/'lineage.json');cfg=identity['config'];info=identity['lineage'];canonical=Path(cfg['accepted_viewer'])
    before=hashes(PREVIOUS,read(PREVIOUS/'receipt.json'))|hashes(ORIGINAL,read(ORIGINAL/'viewer_receipt.json'))|hashes(PARENT,read(PARENT/'receipt.json'))|hashes(OLD,read(OLD/'viewer_receipt.json'))|hashes(canonical,read(canonical/'viewer_receipt.json'))
    for filename in ['20260921_s10_final_fm_rank1_high_low_inspector.md','20260921_s10_final_fm_rank1_high_low_inspector_nonempty_high_addendum.md']:
        report=REPO/'reports'/filename;before[str(report)]=sha(report)
    cm=envelope(Path(cfg['query_revision'])/'object_counts_manifest.json');counts=cm['body']['counts']
    require(sha(Path(cfg['query_revision'])/'object_counts_manifest.json')==info['source_sha256'][str(Path(cfg['query_revision'])/'object_counts_manifest.json')], 'Accepted counts hash')
    require(cm['body']['gallery_manifest_id']==info['gallery_manifest'],'Count gallery')
    rows=pq.read_table(PARENT/'rank1.parquet').to_pylist();require(len(rows)==9000,'Population')
    require(all(c['object_count']==c['n_buildings']+c['n_roads']+c['n_pois'] for c in counts.values()),'Object count sum')
    selected={name:select(rows,counts,'standard' if name.startswith('STANDARD') else 'nonlocal') for name in NEW}
    source={'parent':str(PARENT),'parent_receipt_sha256':sha(PARENT/'receipt.json'),'counts_manifest_id':cm['artifact_id'],'counts_manifest_sha256':sha(Path(cfg['query_revision'])/'object_counts_manifest.json'),'definition':DEFINITION,'previous_generation':str(PREVIOUS),'previous_receipt_sha256':sha(PREVIOUS/'receipt.json'),'code':{str(p.relative_to(REPO)):sha(p) for p in [Path(__file__),REPO/'tools/retrieval_inspector/obj20/extreme_app.js']}}
    generation='s10obj20_'+digest(source)[:24];viewer_id='viewer_'+digest({'generation':generation,'parent':str(OLD)})[:24]
    final=DATA/'s10_extreme_obj20'/generation;vf=DATA/'s10_extreme_viewers'/viewer_id
    require(not final.exists() and not vf.exists(),'Immutable output exists')
    final.parent.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix='.staging_',dir=final.parent));vs=Path(tempfile.mkdtemp(prefix='.staging_',dir=vf.parent))
    manifests={};summary={}
    for name,chosen in selected.items():
        mode='standard' if name.startswith('STANDARD') else 'nonlocal';prefix='' if mode=='standard' else 'nonlocal_';out=[]
        for i,r in enumerate(chosen,1):
            c=counts[r['query_scene_id']]
            z={'set_name':name,'query_index':i,'query_scene_id':r['query_scene_id'],'scene_id':r['query_scene_id'],'query_center_x':r['query_center_x'],'query_center_y':r['query_center_y'],'selection_mode':mode,'rank1_scene_id':r[prefix+'rank1_scene_id'],'rank1_cosine':r[prefix+'rank1_cosine'],'rank1_distance_m':r['geographic_distance_m' if mode=='standard' else 'nonlocal_distance_m'],**c,'n_B':c['n_buildings'],'n_R':c['n_roads'],'n_P':c['n_pois'],'n_obj':c['object_count'],'eligible':True,'eligibility_threshold':20,'source_embedding_manifest_id':info['embedding_manifest'],'source_gallery_manifest_id':info['gallery_manifest'],'source_set_definition':DEFINITION,'source_original_set':name.replace('_OBJ20',''),'source_rank1_sha256':sha(PARENT/'rank1.parquet'),'configuration':'cmp_FM','checkpoint_id':info['model']['checkpoint_id'],'generation_id':generation}
            z['content_hash']=digest(z);out.append(z)
        body={'definition':DEFINITION,'rows':out};manifest={'manifest_id':'s10obj20_queries_'+digest(body)[:24],'sha256':digest(body),'body':body};manifests[name]=manifest
        write(stage/'sets'/f'{name}.json',manifest)
        original=read(PARENT/'sets'/f"{name.replace('_OBJ20','')}.json")['body']['rows']
        summary[name]={'cosine':stats([z['rank1_cosine'] for z in out]),**{k:stats([z[k] for z in out]) for k in ('n_B','n_R','n_P','n_obj')},'original_high_below20_excluded':sum(counts[z['query_scene_id']]['object_count']<20 for z in original),'original_high_retained':len({z['query_scene_id'] for z in original}&{z['query_scene_id'] for z in out})}
        previous=read(PREVIOUS/'sets'/f"{name.replace('_OBJ20','_NONEMPTY')}.json")['body']['rows']
        summary[name]['nonempty_high_retained']=len({z['query_scene_id'] for z in previous}&{z['query_scene_id'] for z in out})
        summary[name]['nonempty_high_below20_excluded']=sum(z['n_obj']<20 for z in previous)
    ids={r['query_scene_id'] for values in selected.values() for r in values};missing={sid for sid in ids if not (OLD/'queries'/f'{sid}.json').exists()}
    ep=Path(info['embedding_path']);emb=envelope(ep,True);require(emb['artifact_id']==info['embedding_manifest'],'Embedding lineage')
    before[str(ep.parent/'vectors.npy')]=sha(ep.parent/'vectors.npy')
    gallery=envelope(Path(cfg['original_generation'])/'gallery_manifest.json');gallery_ids=[r['scene_id'] for r in gallery['body']['rows']]
    require(gallery_ids==emb['body']['scene_ids'],'Scene order')
    X=np.load(ep.parent/'vectors.npy',allow_pickle=False);centers=np.array([[r['center_x'],r['center_y']] for r in gallery['body']['rows']],float)
    # Only supplemental display bands for newly inspected queries. No Rank1
    # population recomputation; no gallery object-count filter.
    bands=make_bands(X,centers,gallery_ids,missing,rows)
    original_config=read(OLD/'config.json');vc=dict(original_config)
    vc['sets']=dict(original_config['sets'])
    vc['sets'].update({name:m['body']['rows'] for name,m in manifests.items()})
    vc.update(display_order=DISPLAY,set_labels=LABELS,default_set='STANDARD_HIGH_OBJ20',evidence_id=generation,viewer_id=viewer_id,display_only_definition=DEFINITION)
    sources={}
    def link(relative,src):
        dst=vs/relative;dst.parent.mkdir(parents=True,exist_ok=True);dst.symlink_to(src);sources[relative]={'path':str(src),'sha256':sha(src)}
    # Reuse original viewer bytes, including all four original query sets.
    for p in sorted(OLD.rglob('*')):
        if p.is_file() and p.name not in ('viewer_receipt.json','config.json','index.html','bands_app.js'):
            link(str(p.relative_to(OLD)),p)
    scenes=set(ids)
    for sid in ids:
        data=bands.get(sid) or read(OLD/'queries'/f'{sid}.json')
        if sid in bands:write(vs/'queries'/f'{sid}.json',data)
        for mode in data['cmp_FM'].values():
            for br in mode['bands'].values():scenes.update(z['gallery_scene_id'] for z in br)
    receipts={}
    for sid in sorted(scenes):
        rel='scenes/'+sid+'.json'
        if (vs/rel).exists():continue
        src=canonical/rel
        if not src.exists():src=Path(cfg['display_fallback'])/rel
        root=src.parent.parent;rc=receipts.setdefault(str(root),read(root/'viewer_receipt.json'))
        require(sha(src)==rc['files'][rel],'Display receipt')
        s=read(src);require(s['scene_id']==sid,'Scene binding')
        require(s['counts']=={'building':counts[sid]['n_buildings'],'road':counts[sid]['n_roads'],'poi':counts[sid]['n_pois']},'Display counts')
        link(rel,src)
    prefix=(OLD/'bands_app.js').read_text().split('async function renderExtreme(){')[0]
    (vs/'bands_app.js').write_text(prefix+(REPO/'tools/retrieval_inspector/obj20/extreme_app.js').read_text())
    vc['files']={str(p.relative_to(vs)):sha(p) for p in sorted(vs.rglob('*')) if p.is_file()}
    write(vs/'config.json',vc)
    html=(OLD/'index.html').read_text().replace(sha(OLD/'config.json'),sha(vs/'config.json'))
    (vs/'index.html').write_text(html)
    for name in original_config['sets']:require(vc['sets'][name]==original_config['sets'][name],'Original membership mutation')
    # Independent selection/read-back using numpy lexsort on the eligible rows.
    for name in NEW:
        mode='standard' if name.startswith('STANDARD') else 'nonlocal';score='rank1_cosine' if mode=='standard' else 'nonlocal_rank1_cosine'
        candidates=[r for r in rows if counts[r['query_scene_id']]['object_count']>=20]
        order=np.lexsort((np.array([r['query_scene_id'] for r in candidates]),-np.array([r[score] for r in candidates])))[:100]
        saved=read(stage/'sets'/f'{name}.json')['body']['rows']
        require([z['query_scene_id'] for z in saved]==[candidates[i]['query_scene_id'] for i in order],'Independent selection')
        require(len({z['query_scene_id'] for z in saved})==100 and all(z['n_obj']>=20 for z in saved),'Eligibility/uniqueness')
    browser=browser_validate(vs)
    require(all(sha(p)==h for p,h in before.items()),'Existing artifact/report mutated')
    validation={'status':'PASS','browser':browser,'original_sets_unchanged':True,'full_population_statistics_unchanged':True,'old_report_unchanged':True,'source_files_verified':len(before),'eligible_population':sum(c['object_count']>=20 for c in counts.values()),'excluded_population':sum(c['object_count']<20 for c in counts.values()),'excluded_zero':sum(c['object_count']==0 for c in counts.values()),'excluded_nonzero_small':sum(1<=c['object_count']<20 for c in counts.values()),'previous_nonempty_unchanged':True,'new_unique_queries':len(ids),'new_display_band_queries':len(missing),'viewer_root':str(vf),'generation_root':str(final)}
    write(stage/'source.json',source);write(stage/'statistics.json',summary);write(stage/'validation.json',validation);write(stage/'preserved_sha256.json',before)
    write(vs/'viewer_receipt.json',{'status':'PASS','viewer_id':viewer_id,'generation_id':generation,'scientific_parent':str(PARENT),'display_parent':str(final),'files':{str(p.relative_to(vs)):sha(p) for p in sorted(vs.rglob('*')) if p.is_file()},'reused_files':sources})
    write(stage/'receipt.json',{'status':'PASS','generation_id':generation,'files':{str(p.relative_to(stage)):sha(p) for p in sorted(stage.rglob('*')) if p.is_file()},'viewer_receipt_sha256':sha(vs/'viewer_receipt.json')})
    os.rename(vs,vf);os.rename(stage,final)
    print(json.dumps(validation,indent=2))

def browser_validate(root):
    # Route local bytes in Chromium: no listening port, no canonical server changes.
    from playwright.sync_api import sync_playwright
    import mimetypes
    from urllib.parse import urlparse,unquote
    errors=[];tested=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,args=['--no-sandbox'])
        page=browser.new_page(viewport={'width':1600,'height':1000})
        page.on('pageerror',lambda e:errors.append(str(e)))
        def route(r):
            rel=unquote(urlparse(r.request.url).path).lstrip('/') or 'index.html'
            f=(root/rel).resolve()
            if not (f.is_relative_to(root.resolve()) or f.is_relative_to(DATA)) or not f.is_file():
                r.fulfill(status=404,body='missing');return
            r.fulfill(status=200,body=f.read_bytes(),content_type=mimetypes.guess_type(f)[0] or 'application/octet-stream')
        page.route('https://s10-inspector.test/**',route)
        for name in DISPLAY+['STANDARD_HIGH','NONLOCAL_HIGH','STANDARD_HIGH_NONEMPTY','NONLOCAL_HIGH_NONEMPTY']:
            page.goto('https://s10-inspector.test/?set='+name)
            page.wait_for_function("document.querySelectorAll('#comparison .column').length===5",timeout=60000)
            require(page.locator('#query option').count()==100,'Browser query count')
            default='standard' if name.startswith('STANDARD') else 'nonlocal'
            require(page.locator('#mode').input_value()==default,'Default mode')
            for mode in ('standard','nonlocal'):
                page.select_option('#mode',mode)
                page.wait_for_function("document.body.dataset.readyMode===document.querySelector('#mode').value && document.querySelectorAll('#comparison .column').length===5")
                require(page.locator('#set').input_value()==name,'Mode changed membership')
                cfg=read(root/'config.json');sid=cfg['sets'][name][0]['query_scene_id'];data=read(root/'queries'/f'{sid}.json')['cmp_FM'][mode]
                candidate=data['bands']['most'][0]['gallery_scene_id']
                require(page.locator('.column[data-band="most"]').get_attribute('data-scene')==candidate,'Browser candidate')
                require(page.locator('#comparison .strip button').count()==30,'Band lengths')
                require(page.locator('#error').is_hidden(),'Browser displayed error')
                tested.append(name+'/'+mode)
            page.select_option('#query','99')
            page.wait_for_function("document.body.dataset.readyQuery==='99'")
            require(page.locator('#query option').count()==100,'Fixed set membership')
        browser.close()
    require(not errors,f'JavaScript errors: {errors}')
    return {'status':'PASS','tested_set_modes':tested,'last_query_each_set':True,'javascript_errors':errors,'method':'Chromium local file route interception; no server or port started'}

if __name__=='__main__':build()

