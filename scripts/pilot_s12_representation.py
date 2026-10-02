#!/usr/bin/env python
"""Bounded, preregistered S12 1/4/8-worker pilot; never full scientific execution."""
import os
for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMBA_NUM_THREADS','VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[key]='1'
import sys,json,time,tempfile,subprocess,threading,resource,datetime,hashlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import psutil
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from s12_runtime import configuration,identity,context,block_specs,read_json,write_json,require,payload,dumps
from s12_inputs import verify_inputs
from s12_validation import parity
from representation_analysis import ROOT,file_sha256


def main():
    c,_=configuration();ident=identity();base=Path(c['execution']['pilot_root']);base.mkdir(parents=True,exist_ok=True)
    root=Path(tempfile.mkdtemp(prefix=datetime.datetime.now().strftime('%Y%m%d_%H%M%S_'),dir=base))
    print('PILOT_ROOT='+str(root),flush=True)
    start=time.time();result={'status':'RUNNING','identity':ident,'full_execution_performed':False,'root':str(root),'start_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    try:
        result['lineage']=verify_inputs();result['parity']=parity(c['model_order']);print('17-model lineage and fixed-query S10 parity PASS',flush=True)
        old=read_json(c['scientific_parent']['receipt']['path']);result['s11_payloads_verified']=len(old['verified_payload_hashes'])
        for p,h in old['verified_payload_hashes'].items():require(file_sha256(p)==h,'S12_PRE_PILOT_S11_PAYLOAD')
        def stage(name,request,label):
            p=root/(label+'.request.json');write_json(p,request)
            t=time.perf_counter();r=subprocess.run([sys.executable,str(ROOT/'scripts/s12_representation.py'),name,'--request',str(p)],cwd=ROOT,capture_output=True,text=True)
            (root/(label+'.log')).write_text(r.stdout+r.stderr)
            require(r.returncode==0,'S12_PILOT_STAGE:'+label+':'+r.stderr[-3000:]);out=json.loads(r.stdout.strip().splitlines()[-1]);out['process_wall_seconds']=time.perf_counter()-t;return out
        benchmarks=[];reference={};contexts={}
        for workers in c['execution']['pilot_workers']:
            req={'scope':'pilot','pilot_root':str(root),'workers':workers};ctx=context('pilot',root,workers)
            parent=stage('parents',req,f'w{workers}_parents')['manifest']
            shared=stage('shared',{**req,'accepted':parent},f'w{workers}_shared')['manifest']
            plan=stage('plan',{**req,'accepted':parent,'shared':shared},f'w{workers}_plan')['manifest']
            stop=threading.Event();rss=[]
            def monitor():
                while not stop.is_set():
                    try:
                        procs=[psutil.Process(),*psutil.Process().children(recursive=True)]
                        rss.append(sum(p.memory_info().rss for p in procs if p.is_running()))
                    except (psutil.NoSuchProcess,psutil.AccessDenied):pass
                    stop.wait(.1)
            thread=threading.Thread(target=monitor,daemon=True);thread.start();t=time.perf_counter();before=resource.getrusage(resource.RUSAGE_CHILDREN)
            specs=block_specs('pilot')
            def one(spec):return stage('block',{**req,'plan':plan,'shared':shared,'spec':spec},f'w{workers}_{spec["configuration_id"]}_{spec["block_id"]}')
            with ThreadPoolExecutor(max_workers=workers) as pool:outputs=list(pool.map(one,specs))
            wall=time.perf_counter()-t;after=resource.getrusage(resource.RUSAGE_CHILDREN);stop.set();thread.join()
            manifests=[o['manifest'] for o in outputs]
            for spec,path in zip(specs,manifests):
                key=(spec['configuration_id'],spec['block_id']);hashes={n:file_sha256(payload(path,n)) for n in ('metrics.parquet','bands.parquet')}
                if workers==1:reference[key]=hashes
                else:require(reference[key]==hashes,'S12_CONCURRENT_BYTES')
            cpu=after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime
            benchmark={'workers':workers,'threads_per_worker':1,'blocks':len(specs),'queries':288,'wall_seconds':wall,'cpu_seconds':cpu,'cpu_average_cores':cpu/wall,'cpu_fraction_of_worker_capacity':cpu/wall/workers,'peak_process_tree_rss_bytes':max(rss),'peak_worker_rss_bytes':max(o['peak_rss_bytes'] for o in outputs),'physical_read_bytes':(after.ru_inblock-before.ru_inblock)*512,'physical_write_bytes':(after.ru_oublock-before.ru_oublock)*512,'blocks_per_second':len(specs)/wall,'scientific_payload_bytes':sum(Path(payload(p,n)).stat().st_size for p in manifests for n in ('metrics.parquet','bands.parquet')),'byte_parity':True,'block_profiles':outputs}
            benchmarks.append(benchmark);contexts[workers]=(req,ctx,plan,manifests)
            write_json(root/'benchmark_progress.json',benchmarks);print(f'{workers} workers PASS: {wall:.3f}s, peak tree RSS {max(rss)/2**30:.3f} GiB',flush=True)
        # Declared before examining scientific values: 8 only for >=10% throughput gain.
        recommended=8 if benchmarks[2]['blocks_per_second']>=1.10*benchmarks[1]['blocks_per_second'] else 4
        req,ctx,plan,manifests=contexts[recommended];acceptances=[]
        for key in c['execution']['pilot_models']:
            summary=stage('summary',{**req,'model':key,'plan':plan,'blocks':manifests},key+'_summary')['manifest']
            acceptance=stage('model_acceptance',{**req,'model':key,'summary':summary},key+'_acceptance')['manifest']
            acceptances.append(acceptance);print(key+' independent acceptance pilot PASS',flush=True)
        require(identity()==ident,'S12_PILOT_SOURCE_CHANGED');verify_inputs()
        for p,h in old['verified_payload_hashes'].items():require(file_sha256(p)==h,'S12_POST_PILOT_S11_PAYLOAD')
        result.update(status='PASS',benchmarks=benchmarks,recommended_workers=recommended,model_acceptances=acceptances,
            selection_rule='8 workers only if throughput >=1.10 times 4 workers; otherwise 4',full_model_queries=9000,pilot_queries_per_model=72,
            original_s11_payloads_unchanged=True,wall_seconds=time.time()-start,end_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
        result['receipt_id']='s12pilot_'+hashlib.sha256(dumps(result).encode()).hexdigest()[:24]
        write_json(root/'pilot_receipt.json',result);print('PASS_RECEIPT='+str(root/'pilot_receipt.json'),flush=True)
    except Exception as exc:
        result.update(status='BLOCKED',error=repr(exc),wall_seconds=time.time()-start);write_json(root/'blocked_receipt.json',result);raise

if __name__=='__main__':main()
