#!/usr/bin/env python
"""S12 isolated stages. Full execution always requires a current pilot receipt."""
import os
for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMBA_NUM_THREADS','VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS'):
    os.environ[key]='1'
import sys,json,argparse,time,resource
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from s12_runtime import get_context,read_json
from s12_inputs import accepted_inputs,shared_descriptors
from s12_alignment import plan,build_block,summarize_model,PROFILE
from s12_validation import model_acceptance,scientific_acceptance
from s12_publication import tables,figures


def main():
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['preflight','parents','shared','plan','block','summary','model_acceptance','tables','figures','acceptance']);p.add_argument('--request',required=True);a=p.parse_args()
    r=read_json(a.request);t=time.perf_counter();ctx=get_context(r)
    if a.stage=='preflight':
        from s12_inputs import verify_inputs
        verify_inputs();print(json.dumps({'status':'PASS','context':ctx}));return
    if a.stage=='parents':result=accepted_inputs(ctx)
    elif a.stage=='shared':result=shared_descriptors(ctx,r['accepted'])
    elif a.stage=='plan':result=plan(ctx,r['accepted'],r['shared'])
    elif a.stage=='block':result=build_block(ctx,r['plan'],r['shared'],r['spec'])
    elif a.stage=='summary':result=summarize_model(ctx,r['model'],r['plan'],r['blocks'])
    elif a.stage=='model_acceptance':result=model_acceptance(ctx,r['model'],r['summary'])
    elif a.stage=='tables':result=tables(ctx,r['acceptances'])
    elif a.stage=='figures':result=figures(ctx,r['tables'])
    else:result=scientific_acceptance(ctx,r['acceptances'],r['tables'],r['figures'])
    ru=resource.getrusage(resource.RUSAGE_SELF)
    print(json.dumps({'manifest':str(result),'profile':dict(PROFILE),'wall_seconds':time.perf_counter()-t,'cpu_seconds':ru.ru_utime+ru.ru_stime,'peak_rss_bytes':ru.ru_maxrss*1024,'read_bytes':ru.ru_inblock*512,'write_bytes':ru.ru_oublock*512}))

if __name__=='__main__':main()
