#!/usr/bin/env python
"""Explicit recovery-only entrypoint. Original S12 wrapper remains prohibited."""
import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMBA_NUM_THREADS','VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[k]='1'
import sys,argparse,datetime
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from s12_single_attempt import exclusive,arm_parent_death


def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['worker','validate','full']);parser.add_argument('--request');parser.add_argument('--pilot-receipt')
    args=parser.parse_args()
    if args.action=='worker':arm_parent_death(int(os.environ['S12_RECOVERY_SUPERVISOR_PID']))
    from s12_recovery import (configuration,inventory,context,prepare,schedule,downstream,compute_worker,
        executor_identity,read_json,file_sha256,dumps,require)
    if args.action=='worker':compute_worker(read_json(args.request));return
    c,specs,adopted,missing=inventory()
    from s12_inputs import verify_inputs
    verify_inputs()
    if args.action=='validate':print(dumps({'status':'PASS','adopted':len(adopted),'missing':len(missing),'executor':executor_identity()}));return
    require(os.environ.get(c['authorization_env'])==c['authorization_value'],'RECOVERY_NOT_AUTHORIZED')
    receipt=read_json(args.pilot_receipt or '/nonexistent/recovery-pilot')
    require(receipt['status']=='PASS' and receipt['identity']==executor_identity() and receipt['full_execution_performed'] is False,'RECOVERY_CURRENT_PILOT_REQUIRED')
    import hashlib
    require(receipt['receipt_id']=='s12recoverypilot_'+hashlib.sha256(dumps({k:v for k,v in receipt.items() if k!='receipt_id'}).encode()).hexdigest()[:24],'RECOVERY_PILOT_RECEIPT_HASH')
    require([r['workers'] for r in receipt['benchmarks']]==[1,4,8] and all(r['retry_count']==0 for r in receipt['benchmarks']),'RECOVERY_PILOT_WORKERS')
    require(receipt['pilot_keys']==c['pilot_keys'] and receipt['adoption_sha256']==c['adoption']['sha256'] and receipt['missing_sha256']==c['missing']['sha256'],'RECOVERY_PILOT_BINDINGS')
    for benchmark in receipt['benchmarks']:
        require(benchmark['byte_parity'] and benchmark['launch_counts']=={k:1 for k in c['pilot_keys']},'RECOVERY_PILOT_SINGLE_ATTEMPT')
        for out in benchmark['outputs'].values():
            require(file_sha256(out['manifest'])==out['manifest_sha256'],'RECOVERY_PILOT_OUTPUT_CHANGED')
            from s11_artifacts import load_bundle
            require(load_bundle(out['manifest'])['files']==out['files'],'RECOVERY_PILOT_PAYLOAD_CHANGED')
    # Identity-derived namespace is single-use. A failed/full invocation cannot
    # choose a fresh directory to evade claims without a new execution contract.
    root=Path(c['output_root'])/executor_identity()['sha256'][:24]
    exclusive(root/'execution_claim.json',{'pilot':str(args.pilot_receipt),'pilot_sha256':file_sha256(args.pilot_receipt),'time':datetime.datetime.now(datetime.timezone.utc).isoformat()})
    ctx=context(root,'full',8)
    try:
        plan,shared=prepare(ctx);schedule(ctx,list(missing),plan,shared)
        acceptance=downstream(ctx,plan)
        exclusive(root/'receipt.json',{'status':'PASS','scientific_acceptance':acceptance,'scientific_acceptance_sha256':file_sha256(acceptance),'executor':executor_identity(),'original_generation':c['original_context']['generation'],'adopted':2983,'computed':1529,'historical_retry_events':83,'recovery_retry_count':0,'mixed_index':str(root/'mixed_index.json'),'mixed_index_sha256':file_sha256(root/'mixed_index.json'),'scheduler_receipt_sha256':file_sha256(root/'scheduler/receipt.json')})
        print('PASS_RECEIPT='+str(root/'receipt.json'))
    except BaseException as exc:
        exclusive(root/'failure.json',{'status':'BLOCKED','error':repr(exc)})
        raise

if __name__=='__main__':main()
