"""Supplemental diagnostics from accepted original embeddings; no model execution.

The retrieval contract follows dissertation spatial-scene retrieval, except that
this explicitly supplemental diagnostic uses all evaluation scenes as queries.
S10 float32 GEMV is retained inside bounded query blocks for exact reproducibility.
"""
from __future__ import annotations
import hashlib
import json
import os
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from threadpoolctl import threadpool_limits, threadpool_info

REPO = Path(__file__).resolve().parents[1]
SETS = ('STANDARD_HIGH', 'STANDARD_LOW', 'NONLOCAL_HIGH', 'NONLOCAL_LOW')


def encode(x):
    return json.dumps(x, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()


def digest(x):
    return hashlib.sha256(encode(x)).hexdigest()


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write(path, x):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as f:
        f.write(encode(x))


def require(ok, message):
    if not ok:
        raise ValueError(message)


def envelope(path, payload=False):
    d = read(path)
    require(digest({k:v for k,v in d.items() if k not in ('sha256','artifact_id')}) == d['sha256'], f'Envelope hash: {path}')
    require(d['artifact_id'].endswith(d['sha256'][:24]), f'Artifact ID: {path}')
    if payload:
        for f in d['files']:
            p = Path(path).parent / f['path']
            require(p.stat().st_size == f['bytes'] and sha(p) == f['sha256'], f'Payload: {p}')
    return d


def lineage(cfg):
    o, n, v = (Path(cfg[k]) for k in ('original_generation','query_revision','accepted_viewer'))
    a, a100 = envelope(o/'acceptance.json'), envelope(n/'acceptance.json')
    require(a['body']['status'] == a100['body']['status'] == 'PASS', 'Unaccepted parents')
    g, m = envelope(o/'gallery_manifest.json'), envelope(o/'model_manifest.json')
    r = envelope(o/'rankings'/cfg['configuration']/'manifest.json', True)
    epath = Path(r['body']['embedding_manifest'])
    e = envelope(epath, True)
    models = [x for x in m['body']['models'] if x['configuration_id'] == cfg['configuration']]
    require(len(models)==1, 'Ambiguous model')
    model = models[0]
    require(model == e['body']['model'] == r['body']['model'], 'Model lineage mismatch')
    require(model['configuration_id']=='cmp_FM' and model['model_id']=='FM' and model['group']=='COMPARISON', 'Not final FM')
    require(r['body']['embedding_manifest_id']==e['artifact_id'], 'Embedding binding')
    for doc, path in [(g,o/'gallery_manifest.json'),(m,o/'model_manifest.json'),(r,o/'rankings/cmp_FM/manifest.json')]:
        require(a['body']['artifacts'][str(path)]==doc['artifact_id'], 'Acceptance binding')
    require(e['body']['gallery_manifest_id']==g['artifact_id'], 'Embedding gallery')
    respath = Path(cfg['lifecycle_root'])/model['authority_id']/'resolution.json'
    res = read(respath)
    for k in ('checkpoint_id','acceptance_id','payload_sha256','manifest_sha256'):
        require(res[k]==model[k], f'Resolution {k}')
    require(sha(model['payload'])==model['payload_sha256'], 'Checkpoint bytes changed')  # hash only; never deserialize
    rows = g['body']['rows']
    ids = [x['scene_id'] for x in rows]
    require(len(ids)==9000 and len(set(ids))==9000 and ids==sorted(ids), 'Population/order')
    require(ids==e['body']['scene_ids'], 'Embedding scene order')
    prepared=envelope(e['body']['prepared_manifest'])
    require(prepared['artifact_id']==e['body']['prepared_manifest_id'] and prepared['body']['gallery_manifest_id']==g['artifact_id'], 'Original input binding')
    require([x['scene_id'] for x in prepared['body']['samples']]==ids, 'Original input population')
    require(all(x['split']=='evaluation' and x['epsg']==5186 for x in rows), 'Split/CRS')
    X = np.load(epath.parent/'vectors.npy', allow_pickle=False)
    require(X.shape==(9000,256) and X.dtype==np.float32 and e['body']['dtype']=='float32' and e['body']['shape']==[9000,256], 'Embedding dimensions')
    norms = np.linalg.norm(X,axis=1)
    require(np.isfinite(X).all() and np.max(np.abs(norms-1))<1e-6, 'Normalized embeddings required; no renormalization')
    counts = envelope(n/'object_counts_manifest.json')
    require(counts['body']['gallery_manifest_id']==g['artifact_id'] and a100['body']['artifacts'][str(n/'object_counts_manifest.json')]==counts['artifact_id'], 'Counts binding')
    vr = read(v/'viewer_receipt.json')
    require(vr['parent']==a100['artifact_id'], 'Viewer parent')
    require(vr['parent_sha256']==sha(n/'acceptance.json'), 'Viewer acceptance bytes')
    source_paths = [o/'acceptance.json',n/'acceptance.json',o/'gallery_manifest.json',o/'model_manifest.json',epath,respath,Path(model['payload']),n/'object_counts_manifest.json',v/'viewer_receipt.json',v/'config.json']
    info = dict(model=model, resolution=res, embedding_manifest=e['artifact_id'], embedding_path=str(epath), embedding_sha256=sha(epath.parent/'vectors.npy'), gallery_manifest=g['artifact_id'], original_acceptance=a['artifact_id'], revision_acceptance=a100['artifact_id'], normalization_min=float(norms.min()), normalization_max=float(norms.max()), source_sha256={str(p):sha(p) for p in source_paths})
    return X, np.array([[x['center_x'],x['center_y']] for x in rows],dtype=np.float64), ids, counts['body']['counts'], info


def rank1(X, centers, ids, block_size=32, threshold=2000):
    require(ids==sorted(ids) and len(set(ids))==len(ids), 'Lexical gallery order required')
    require(block_size>0, 'Positive block size')
    out=[]
    with threadpool_limits(limits=1):
        for start in range(0,len(ids),block_size):
            # Bounded block, same float32 reduction as accepted S10 (GEMV).
            scores=np.stack([X @ X[i] for i in range(start,min(start+block_size,len(ids)))])
            for offset, s in enumerate(scores):
                i=start+offset
                d=np.linalg.norm(centers-centers[i],axis=1)
                s[i]=-np.inf
                j=int(np.argmax(s)); standard=float(s[j])
                eligible=(d>=threshold);eligible[i]=False
                count=int(eligible.sum());require(count>0, 'Empty Non-local pool')
                s[~eligible]=-np.inf
                k=int(np.argmax(s));nonlocal_score=float(s[k])
                require(np.isfinite([standard,nonlocal_score]).all() and standard>=nonlocal_score, 'Invalid score/delta')
                out.append(dict(query_scene_id=ids[i],query_center_x=float(centers[i,0]),query_center_y=float(centers[i,1]),standard_candidate_count=len(ids)-1,rank1_scene_id=ids[j],rank1_cosine=standard,geographic_distance_m=float(d[j]),candidate_center_x=float(centers[j,0]),candidate_center_y=float(centers[j,1]),nonlocal_rank1_scene_id=ids[k],nonlocal_rank1_cosine=nonlocal_score,nonlocal_distance_m=float(d[k]),nonlocal_candidate_center_x=float(centers[k,0]),nonlocal_candidate_center_y=float(centers[k,1]),nonlocal_candidate_count=count,delta_rank1=standard-nonlocal_score))
    return out


def memberships(rows, size=100):
    result={}
    for name in SETS:
        mode='standard' if name.startswith('STANDARD') else 'nonlocal'
        score='rank1_cosine' if mode=='standard' else 'nonlocal_rank1_cosine'
        sign=-1 if name.endswith('HIGH') else 1
        result[name]=sorted(rows,key=lambda r:(sign*r[score],r['query_scene_id']))[:size]
        require(len(result[name])==size and len({r['query_scene_id'] for r in result[name]})==size, 'Set size')
    return result


def stats(values):
    x=np.asarray(values,dtype=np.float64)
    result={'n':len(x),'min':float(x.min()),'mean':float(x.mean()),'standard_deviation':float(x.std(ddof=0)),'max':float(x.max())}
    for p in (1,5,10,25,50,75,90,95,99):
        result['median' if p==50 else f'p{p}']=float(np.quantile(x,p/100,method='linear'))
    result['IQR']=result['p75']-result['p25']
    return result


def summarize(rows, sets, counts):
    result={k:stats([r[k] for r in rows]) for k in ('rank1_cosine','nonlocal_rank1_cosine','delta_rank1','geographic_distance_m','nonlocal_distance_m','nonlocal_candidate_count')}
    result['quantile_convention']='NumPy linear: h=(n-1)*p; interpolate floor/ceil(h). Population standard deviation ddof=0.'
    result['distance_bins']={}
    for label,lo,hi in [('0 <= d < 500 m',0,500),('500 <= d < 1000 m',500,1000),('1000 <= d < 2000 m',1000,2000),('d >= 2000 m',2000,np.inf)]:
        n=sum(lo<=r['geographic_distance_m']<hi for r in rows);result['distance_bins'][label]={'count':n,'proportion':n/len(rows)}
    for label,fn in [('standard_already_nonlocal',lambda r:r['geographic_distance_m']>=2000),('same_rank1_scene',lambda r:r['rank1_scene_id']==r['nonlocal_rank1_scene_id']),('delta_zero',lambda r:r['delta_rank1']==0),('delta_positive',lambda r:r['delta_rank1']>0),('delta_negative',lambda r:r['delta_rank1']<0)]:
        n=sum(fn(r) for r in rows);result[label]={'count':n,'proportion':n/len(rows)}
    result['sets']={}
    for name,rs in sets.items():
        mode='standard' if name.startswith('STANDARD') else 'nonlocal'
        score='rank1_cosine' if mode=='standard' else 'nonlocal_rank1_cosine'
        distance='geographic_distance_m' if mode=='standard' else 'nonlocal_distance_m'
        cs=[counts[r['query_scene_id']] for r in rs]
        result['sets'][name]={'cosine':stats([r[score] for r in rs]),'distance_m':stats([r[distance] for r in rs]),**{k:stats([c[k] for c in cs]) for k in ('n_buildings','n_roads','n_pois','object_count')},'sparse_lt10':sum(c['object_count']<10 for c in cs),'objects_ge100':sum(c['object_count']>=100 for c in cs),'distance_lt500':sum(r[distance]<500 for r in rs),'boundary_score':rs[-1][score]}
    result['overlaps']={a+' & '+b:len({r['query_scene_id'] for r in sets[a]} & {r['query_scene_id'] for r in sets[b]}) for a,b in [('STANDARD_HIGH','NONLOCAL_HIGH'),('STANDARD_LOW','NONLOCAL_LOW'),('STANDARD_HIGH','NONLOCAL_LOW'),('STANDARD_LOW','NONLOCAL_HIGH')]}
    return result


def band_ranks(n):
    start=(n-10)//2+1
    return {'most':[1],'top':list(range(2,12)),'middle':list(range(start,start+10)),'bottom':list(range(n-9,n+1))}


def make_bands(X,centers,ids,selected,rank_rows):
    index={s:i for i,s in enumerate(ids)};lookup={r['query_scene_id']:r for r in rank_rows};result={}
    with threadpool_limits(limits=1):
        for sid in sorted(selected):
            i=index[sid];scores=X @ X[i];d=np.linalg.norm(centers-centers[i],axis=1)
            order=np.argsort(-scores,kind='stable');entry={}
            for mode in ('standard','nonlocal'):
                eligible=[int(j) for j in order if j!=i and (mode=='standard' or d[j]>=2000)]
                key='rank1_scene_id' if mode=='standard' else 'nonlocal_rank1_scene_id'
                require(ids[eligible[0]]==lookup[sid][key], 'Band rank1 mismatch')
                bands={}
                for name,ranks in band_ranks(len(eligible)).items():
                    bands[name]=[dict(query_id=sid,model_id='cmp_FM',retrieval_mode=mode,rank=r,gallery_scene_id=ids[eligible[r-1]],similarity=float(scores[eligible[r-1]]),geographic_distance_m=float(d[eligible[r-1]]),excluded_by_nonlocal=False) for r in ranks]
                entry[mode]={'candidate_count':len(eligible),'bands':bands}
            result[sid]={'cmp_FM':entry}
    return result


def safety_snapshot(cfg, info):
    # Hash all immutable manifests/receipts and all accepted viewer bytes; record
    # every original/revision file's stat as an additional no-mutation guard.
    hashes=dict(info['source_sha256']);inventory={}
    for key in ('original_generation','query_revision','accepted_viewer'):
        root=Path(cfg[key])
        for p in sorted(root.rglob('*')):
            if p.is_file():
                st=p.stat();inventory[str(p)]=[st.st_size,st.st_mtime_ns]
                if key=='accepted_viewer' or p.suffix=='.json':hashes[str(p)]=sha(p)
    hashes[info['embedding_path'].replace('manifest.json','vectors.npy')]=sha(Path(info['embedding_path']).parent/'vectors.npy')
    hashes[info['model']['payload']]=sha(info['model']['payload'])
    fallback=Path(cfg['display_fallback'])
    for p in (fallback/'viewer_receipt.json',fallback/'scenes/scn_beb12e42ea773cee2916f099.json'):
        hashes[str(p)]=sha(p)
    return {'sha256':hashes,'file_stats':inventory}


def validate_reference(rows,X,centers,ids,cfg):
    require(rows==rank1(X,centers,ids,17), 'Block-size invariance')
    # Independent full sort, rather than argmax; separate geometric count logic.
    with threadpool_limits(limits=1):
        for i,r in enumerate(rows):
            d2=np.sum((centers-centers[i])**2,axis=1)
            require(r['nonlocal_candidate_count']==int(np.count_nonzero(d2>=2000**2)), 'Independent pool count')
            require(r['query_scene_id'] not in (r['rank1_scene_id'],r['nonlocal_rank1_scene_id']), 'Self match')
            require(r['nonlocal_distance_m']>=2000 and r['standard_candidate_count']==8999,'Pool constraints')
        for i in np.linspace(0,len(ids)-1,101,dtype=int):
            scores=X @ X[i];d=np.linalg.norm(centers-centers[i],axis=1)
            order=np.lexsort((np.array(ids),-scores))
            for mode,key in [('standard','rank1_scene_id'),('nonlocal','nonlocal_rank1_scene_id')]:
                expected=next(j for j in order if j!=i and (mode=='standard' or d[j]>=2000))
                require(rows[i][key]==ids[expected], 'Independent lexsort reference')
    matches=0;lookup={r['query_scene_id']:r for r in rows}
    for root in (cfg['original_generation'],cfg['query_revision']):
        manifest=envelope(Path(root)/'rankings/cmp_FM/manifest.json',True)
        for r in pq.read_table(Path(root)/'rankings/cmp_FM/rankings.parquet').to_pylist():
            if r['rank']!=1:continue
            z=lookup[r['query_id']];mode=r['retrieval_mode'];prefix='' if mode=='standard' else 'nonlocal_'
            require(z[prefix+'rank1_scene_id']==r['gallery_scene_id'] and z[prefix+'rank1_cosine']==r['similarity'], 'Accepted rank1 mismatch')
            matches+=1
    return {'block_sizes':[32,17],'all_9000_exactly_equal':True,'independent_lexsort_queries':101,'accepted_rank1_records_exact':matches,'independent_candidate_counts':9000,'cpu_threads':1,'gpu_used':False}


def publish(cfg):
    X,centers,ids,counts,info=lineage(cfg)
    before=safety_snapshot(cfg,info)
    print('Lineage and safety snapshot verified',flush=True)
    rows=rank1(X,centers,ids,cfg['block_size'])
    checks=validate_reference(rows,X,centers,ids,cfg)
    selected=memberships(rows,cfg['set_size']);summary=summarize(rows,selected,counts)
    code_paths=[REPO/'python/s10_extreme_rank1.py',REPO/'scripts/s10_extreme_rank1.py',REPO/'config/s10_extreme_rank1.json',*sorted((REPO/'tools/retrieval_inspector/extreme').glob('*'))]
    code={str(p.relative_to(REPO)):sha(p) for p in code_paths if p.is_file()}
    identity={'config':cfg,'lineage':info,'code':code,'runtime':{'python':platform.python_version(),'numpy':np.__version__,'pyarrow':pa.__version__,'blas':threadpool_info()},'rank1_content_sha256':digest(rows)}
    generation='s10ext_'+digest(identity)[:24];viewer_id='viewer_'+digest({'generation':generation,'display_parent':sha(Path(cfg['accepted_viewer'])/'viewer_receipt.json')})[:24]
    final=Path(cfg['publication_root'])/generation;vfinal=Path(cfg['viewer_root'])/viewer_id
    require(not final.exists() and not vfinal.exists(),'Immutable generation already exists; use validation, never overwrite')
    final.parent.mkdir(parents=True,exist_ok=True);vfinal.parent.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix='.staging_',dir=final.parent));vstage=Path(tempfile.mkdtemp(prefix='.staging_',dir=vfinal.parent))
    write(stage/'safety_before.json',before);write(stage/'lineage.json',identity)
    pq.write_table(pa.Table.from_pylist(rows),stage/'rank1.parquet')
    require(pq.read_table(stage/'rank1.parquet').to_pylist()==rows,'Parquet readback')
    manifests={}
    for name,rs in selected.items():
        mode='standard' if name.startswith('STANDARD') else 'nonlocal';prefix='' if mode=='standard' else 'nonlocal_';out=[]
        for index,r in enumerate(rs,1):
            z={k:r[k] for k in ('query_scene_id','query_center_x','query_center_y')}
            z.update(set_name=name,query_index=index,selection_mode=mode,rank1_scene_id=r[prefix+'rank1_scene_id'],rank1_cosine=r[prefix+'rank1_cosine'],rank1_distance_m=r['geographic_distance_m' if mode=='standard' else 'nonlocal_distance_m'],nonlocal_candidate_count=r['nonlocal_candidate_count'] if mode=='nonlocal' else None,configuration='cmp_FM',checkpoint_id=info['model']['checkpoint_id'],source_embedding_manifest_id=info['embedding_manifest'],source_gallery_manifest_id=info['gallery_manifest'],generation_id=generation)
            z['content_hash']=digest(z);out.append(z)
        body={'rows':out,'boundary_score':out[-1]['rank1_cosine'],'selection':'query cosine, then lexical query ID; exact ties','generation_id':generation}
        manifest={'manifest_id':'s10ext_queries_'+digest(body)[:24],'content_hash':digest(body),'body':body};manifests[name]=manifest
        write(stage/'sets'/f'{name}.json',manifest)
    write(stage/'statistics.json',summary)
    selected_ids={r['query_scene_id'] for rs in selected.values() for r in rs}
    bands=make_bands(X,centers,ids,selected_ids,rows)
    for sid,data in bands.items():write(stage/'bands'/f'{sid}.json',data)
    print(f'Rank1 validated; {len(selected_ids)} unique selected queries',flush=True)
    build_viewer(cfg,vstage,bands,manifests,info,generation,viewer_id)
    checks['viewer']=browser_validate(vstage)
    after=safety_snapshot(cfg,info);require(before==after,'EXISTING ARTIFACT MUTATION')
    write(stage/'safety_after.json',after)
    checks.update(status='PASS',existing_artifacts_unchanged=True,hashed_existing_files=len(before['sha256']),stat_checked_existing_files=len(before['file_stats']),generation_id=generation,viewer_id=viewer_id,viewer_root=str(vfinal),generation_root=str(final),unique_selected_queries=len(selected_ids))
    write(stage/'validation.json',checks)
    write(vstage/'viewer_receipt.json',{'status':'PASS','viewer_id':viewer_id,'generation_id':generation,'scientific_parent':str(final),'source_viewer':cfg['accepted_viewer'],'files':{str(p.relative_to(vstage)):sha(p) for p in sorted(vstage.rglob('*')) if p.is_file()},'validation':checks['viewer']})
    write(stage/'receipt.json',{'status':'PASS','generation_id':generation,'supplemental':True,'files':{str(p.relative_to(stage)):sha(p) for p in sorted(stage.rglob('*')) if p.is_file()},'viewer_receipt_sha256':sha(vstage/'viewer_receipt.json')})
    os.rename(vstage,vfinal);os.rename(stage,final)
    print(json.dumps(checks,indent=2),flush=True)
    return final,vfinal


def build_viewer(cfg,root,bands,manifests,info,generation,viewer_id):
    parent=Path(cfg['accepted_viewer']);pc=read(parent/'config.json');receipt=read(parent/'viewer_receipt.json')
    def copy(relative):
        src=parent/relative;source_receipt=receipt
        if not src.is_file():
            fallback=Path(cfg['display_fallback']);source_receipt=read(fallback/'viewer_receipt.json')
            require(source_receipt['parent']==info['original_acceptance'], 'Fallback scientific parent')
            require(source_receipt['sources'][str(Path(cfg['original_generation'])/'acceptance.json')]==sha(Path(cfg['original_generation'])/'acceptance.json'), 'Fallback parent checksum')
            src=fallback/relative
        require(src.is_file(),f'Missing accepted display: {relative}')
        require(sha(src)==source_receipt['files'][relative],f'Display receipt mismatch: {relative}')
        dst=root/relative;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
    for f in ('app.js','style.css','augmentation.css','bands.css','legacy_bands.css','locations.js','locations.css','location_metadata.json'):copy(f)
    scene_ids=set(bands)
    for sid,data in bands.items():
        write(root/'queries'/f'{sid}.json',data)
        for mode in data['cmp_FM'].values():
            for rows in mode['bands'].values():scene_ids.update(r['gallery_scene_id'] for r in rows)
    for sid in sorted(scene_ids):
        copy('scenes/'+sid+'.json');scene=read(root/'scenes'/f'{sid}.json')
        require(scene['scene_id']==sid and scene['thematic']['binding']['scene_id']==sid,'Display scene binding')
    gallery=read(Path(cfg['original_generation'])/'gallery_manifest.json')['body']['rows']
    original=read(Path(cfg['original_generation'])/'original_inputs/manifest.json')
    original_hashes={Path(f['path']).stem:f['sha256'] for f in original['files']}
    for row in gallery:
        if row['scene_id'] not in scene_ids:continue
        scene=read(root/'scenes'/f"{row['scene_id']}.json")
        require(scene['center']==[row['center_x'],row['center_y']], 'Display center binding')
        require(scene['thematic']['binding']['original_input_sha256']==original_hashes[row['scene_id']], 'Display original input binding')
    prefix=(parent/'bands_app.js').read_text().split('async function renderBands(){')[0]
    (root/'bands_app.js').write_text(prefix+(REPO/'tools/retrieval_inspector/extreme/extreme_app.js').read_text())
    vc={k:pc[k] for k in ('palette','location_metadata','gallery_count')}
    vc.update(acceptance=info['revision_acceptance'],evidence_id=generation,viewer_id=viewer_id,models=[{'id':'cmp_FM','group':'COMPARISON'}],sets={name:[dict(r,scene_id=r['query_scene_id']) for r in m['body']['rows']] for name,m in manifests.items()})
    vc['files']={str(p.relative_to(root)):sha(p) for p in sorted(root.rglob('*')) if p.is_file()}
    write(root/'config.json',vc)
    html=(REPO/'tools/retrieval_inspector/extreme/index.html').read_text().replace('__CONFIG_SHA__',sha(root/'config.json'))
    (root/'index.html').write_text(html)


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
            if not f.is_relative_to(root.resolve()) or not f.is_file():
                r.fulfill(status=404,body='missing');return
            r.fulfill(status=200,body=f.read_bytes(),content_type=mimetypes.guess_type(f)[0] or 'application/octet-stream')
        page.route('https://s10-inspector.test/**',route)
        for name in SETS:
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
