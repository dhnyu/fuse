#!/usr/bin/env python
"""Four preregistered missing keys, once per authorized 1/4/8 pilot namespace."""
import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMBA_NUM_THREADS','VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[k]='1'
import sys,time,datetime,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from s12_recovery import *
from s12_single_attempt import exclusive


def main():
    c,specs,adopted,missing=inventory();ident=executor_identity()
    # No automatic fresh pilot run under an already-claimed executor identity.
    root=Path(c['pilot_root'])/ident['sha256'][:24]
    exclusive(root/'pilot_claim.json',{'keys':c['pilot_keys'],'workers':[1,4,8],'identity':ident,'time':time.time()})
    start=time.time();print('PILOT_ROOT='+str(root),flush=True)
    try:
        from s12_inputs import verify_inputs
        from s12_validation import parity
        lineage=verify_inputs();numerical=parity([k.split('__')[0] for k in c['pilot_keys']])
        old=read_json(c['scientific_parent']['receipt']['path'])
        for p,h in old['verified_payload_hashes'].items():require(file_sha256(p)==h,'RECOVERY_S11_PRE')
        benchmarks=[];reference=None;checks=[]
        for workers in (1,4,8):
            ctx=context(root/f'w{workers}','pilot',workers);plan,shared=prepare(ctx)
            r=schedule(ctx,c['pilot_keys'],plan,shared)
            hashes={k:v['files'] for k,v in r['outputs'].items()}
            if reference is None:reference=hashes
            else:require(hashes==reference,'RECOVERY_PILOT_BYTE_PARITY')
            for key,out in r['outputs'].items():
                q=specs[key]['positions'];checks.append({'workers':workers,'key':key,**independent_block(out['manifest'],[q[0],q[-1]])})
            # Validate partial mixed provenance too, never aggregate it as full.
            mixed=mixed_index(ctx,False);exclusive(Path(ctx['root'])/'mixed_index.json',mixed)
            require(len(mixed['rows'])==2987,'RECOVERY_PILOT_MIXED_COUNT')
            scheduler=Path(ctx['root'])/'scheduler'
            require({p.stem for p in (scheduler/'worker_claims').glob('*.json')}==set(c['pilot_keys']),'RECOVERY_WORKER_LAUNCH_COUNTS')
            require(all(read_json(scheduler/'claims'/(k+'.json'))['launch_count']==1 for k in c['pilot_keys']),'RECOVERY_SUPERVISOR_LAUNCH_COUNTS')
            import psutil
            require(all(not psutil.pid_exists(pid) for pid in r['pids']),'RECOVERY_ORPHAN_PID')
            r['block_profiles']={k:read_json(scheduler/'acks'/(k+'.json'))['profile'] for k in c['pilot_keys']}
            r['byte_parity']=True;benchmarks.append(r)
            print(f'WORKERS={workers} PASS wall={r["wall_seconds"]:.3f}s peak_RSS={r["peak_tree_rss_bytes"]} launches={r["launch_counts"]}',flush=True)
        configuration.cache_clear();executor_runtime.cache_clear();executor_identity.cache_clear()
        require(executor_identity()==ident,'RECOVERY_POST_PILOT_EXECUTOR')
        inventory()
        verify_inputs()
        for p,h in old['verified_payload_hashes'].items():require(file_sha256(p)==h,'RECOVERY_S11_POST')
        result={'status':'PASS','identity':ident,'full_execution_performed':False,'benchmarks':benchmarks,'independent_checks':checks,
                'lineage':lineage,'s10_parity':numerical,'adopted_count':2983,'missing_count':1529,'adoption_sha256':c['adoption']['sha256'],
                'missing_sha256':c['missing']['sha256'],'recommended_workers':8,'pilot_keys':c['pilot_keys'],
                'replication_authorization':'User approved one launch per separate 1/4/8-worker pilot namespace',
                'scientific_payloads_unchanged':True,'wall_seconds':time.time()-start,'end_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
        result['receipt_id']='s12recoverypilot_'+hashlib.sha256(dumps(result).encode()).hexdigest()[:24]
        exclusive(root/'pilot_receipt.json',result);print('PASS_RECEIPT='+str(root/'pilot_receipt.json'),flush=True)
    except BaseException as exc:
        exclusive(root/'failure.json',{'status':'BLOCKED','error':repr(exc),'wall_seconds':time.time()-start});raise

if __name__=='__main__':main()
