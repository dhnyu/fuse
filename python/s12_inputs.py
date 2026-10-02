"""Accepted S09/S10/S11 consumers. Never reads P3 or loads a model."""
from pathlib import Path
import hashlib
import numpy as np
import pyarrow.parquet as pq
from retrieval_artifacts import load as accepted, validate_envelope, digest
from s12_runtime import (configuration,check_pin,model,publish,write_json,read_json,require,
    references,generation_bundle)
from representation_analysis import file_sha256


def population():
    c,_=configuration();p=check_pin(c['shared']['population']);t=pq.read_table(p)
    ids=t['scene_id'].to_pylist();centers=np.column_stack([t['center_x'].to_numpy(),t['center_y'].to_numpy()])
    require(len(ids)==9000 and ids==sorted(set(ids)) and hashlib.sha256('\n'.join(ids).encode()).hexdigest()==c['population']['order_sha256'],'S12_POPULATION')
    require(centers.shape==(9000,2) and np.isfinite(centers).all(),'S12_CENTERS')
    return ids,centers


def embeddings(key):
    m=model(key);p=check_pin(m['bindings']['vectors']);x=np.load(p,mmap_mode='r',allow_pickle=False)
    require(x.shape==(9000,m['dimension']) and x.dtype==np.float32 and x.flags.c_contiguous and np.isfinite(x).all(),'S12_EMBEDDINGS')
    require(np.allclose(np.linalg.norm(x,axis=1),1,rtol=0,atol=2e-6),'S12_NORMALIZATION')
    return x


def verify_shared():
    c,_=configuration();p=check_pin(c['scientific_parent']['receipt']);r=read_json(p)
    from s11_artifacts import dumps
    require(r['status']=='PASS' and r['scientific_payloads_unchanged'] and r['receipt_id']==c['scientific_parent']['receipt_id'],'S12_FM_ACCEPTANCE')
    require(r['receipt_id']=='s11rv_'+hashlib.sha256(dumps({k:v for k,v in r.items() if k!='receipt_id'}).encode()).hexdigest()[:24],'S12_RECEIPT_ID')
    for name,h in r['verifier']['sources'].items():require(file_sha256(Path(__file__).resolve().parents[1]/name)==h,'S12_ACCEPTED_VERIFIER_SOURCE')
    for key,pin in c['shared'].items():
        check_pin(pin);require(r['verified_payload_hashes'][pin['path']]==pin['sha256'],'S12_SHARED_RECEIPT_BINDING')
    check_pin(c['scientific_parent']['contract']);check_pin(c['scientific_parent']['lock'])
    registry=read_json(c['shared']['dictionary']['path'])
    require([d['id'] for d in registry]==c['descriptor_order'] and len(registry)==22 and sum(d['kind']=='scalar' for d in registry)==15,'S12_DESCRIPTOR_REGISTRY')
    ids,_=population();t=pq.read_table(c['shared']['descriptors']['path'])
    require(t['scene_id'].to_pylist()==ids,'S12_DESCRIPTOR_ORDER')
    support=pq.read_table(c['shared']['validity']['path'])
    require(support.num_rows==9000*22,'S12_SUPPORT_COUNT')
    return {'receipt_id':r['receipt_id'],'references':references(),'scene_count':9000,'descriptor_count':22,'duplicated_payloads':False}


def verify_inputs():
    c,_=configuration();shared=verify_shared()
    for p in c['parents'].values():check_pin(p)
    acceptance=accepted(c['parents']['s10_acceptance']['path'],'acceptance')
    gallery=accepted(c['parents']['gallery']['path'],'gallery');models=accepted(c['parents']['models']['path'],'models')
    ids,centers=population();require([r['scene_id'] for r in gallery['body']['rows']]==ids and all(r['split']=='evaluation' for r in gallery['body']['rows']),'S12_GALLERY')
    require(np.array_equal(centers,[[r['center_x'],r['center_y']] for r in gallery['body']['rows']]),'S12_CENTER_BINDING')
    prep=read_json(c['parents']['original_inputs']['path']);validate_envelope(prep)
    require(prep['sha256']==digest({k:v for k,v in prep.items() if k not in ('sha256','artifact_id')}) and [r['scene_id'] for r in prep['body']['samples']]==ids,'S12_ORIGINAL_INPUTS')
    campaign=read_json(c['parents']['s09_campaign']['path']);require(campaign['status']=='PASS','S12_CAMPAIGN')
    result=[]
    for m in c['models']:
        for pin in m['bindings'].values():check_pin(pin)
        key=m['configuration_id'];original=next(x for x in models['body']['models'] if x['configuration_id']==key)
        e=accepted(m['bindings']['embedding_manifest']['path'],'embeddings');ranking=accepted(m['bindings']['ranking_manifest']['path'],'rankings')
        require(e['artifact_id']==m['embedding_manifest_id'] and e['body']['model']==ranking['body']['model']==original,'S12_MODEL_BINDING')
        require(acceptance['body']['artifacts'][m['bindings']['ranking_manifest']['path']]==ranking['artifact_id'] and ranking['body']['embedding_manifest_id']==e['artifact_id'],'S12_S10_ACCEPTANCE_CHAIN')
        require(e['body']['scene_ids']==ids and e['body']['gallery_manifest_id']==gallery['artifact_id'] and e['body']['prepared_manifest_id']==prep['artifact_id'] and e['body']['runtime_id']==m['runtime_id'],'S12_EMBEDDING_LINEAGE')
        require(original['checkpoint_id']==m['checkpoint_id'] and original['model_id']==m['model_id'] and original['acceptance_id']==m['s09_acceptance_id'],'S12_CHECKPOINT_SELECTION')
        cm=read_json(m['bindings']['checkpoint_manifest']['path']);cr=read_json(m['bindings']['campaign_result']['path']);ac=read_json(m['bindings']['canonical_acceptance']['path']);commit=read_json(m['bindings']['acceptance_commit']['path']);final=read_json(m['bindings']['finalization']['path'])
        require(cr['status']=='PASS' and cr['checkpoint_id']==cm['checkpoint_id']==ac['checkpoint_id']==m['checkpoint_id'] and cr['completed_epoch']==cm['completed_epoch']==m['selected_epoch'],'S12_SELECTED_EPOCH')
        require(commit['status']=='COMMITTED' and commit['acceptance_sha256']==m['bindings']['canonical_acceptance']['sha256'] and commit['finalization_result_sha256']==m['bindings']['finalization']['sha256'],'S12_NATIVE_ACCEPTANCE')
        require(final['scientific_state']=='COMPLETE' and final['evidence_class']=='VALID_SCIENTIFIC_EVIDENCE' and final['selected_checkpoint']['checkpoint_id']==m['checkpoint_id'],'S12_FINALIZATION')
        require(m['bindings']['campaign_result']['path'] in campaign['comparison_acceptance_records'],'S12_CAMPAIGN_MEMBERSHIP')
        x=embeddings(key);result.append({'configuration_id':key,'checkpoint_id':m['checkpoint_id'],'shape':list(x.shape),'scene_count':9000,'status':'PASS'})
    return {'models':result,'shared':shared,'training':False,'inference':False,'p3_access':False}


def accepted_inputs(ctx):
    verification=verify_inputs();c,_=configuration()
    parents=[p['path'] for p in c['parents'].values()]+[c['scientific_parent']['receipt']['path']]
    parents += [p['path'] for m in c['models'] for p in m['bindings'].values()]
    return publish(ctx,'s12_accepted_inputs','accepted',lambda stage:(write_json(stage/'verification.json',verification) or {'models':17,'fm_reused':True}),parents)


def shared_descriptors(ctx,accepted_manifest):
    generation_bundle(accepted_manifest,ctx,'s12_accepted_inputs');data=verify_shared();c,_=configuration()
    return publish(ctx,'s12_shared_descriptors','references',lambda stage:(write_json(stage/'references.json',data) or {'scene_count':9000,'descriptors':22,'copy':False}),[accepted_manifest,*[v['path'] for v in c['shared'].values()]])
