"""Synthetic single-attempt lifecycle tests; never invoke scientific producers."""
import os
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'python'))
import json
import signal
import subprocess
import time
from s12_single_attempt import run_tasks,exclusive,arm_parent_death,SingleAttemptError


def synthetic_worker(request):
    arm_parent_death(int(os.environ['S12_RECOVERY_SUPERVISOR_PID']))
    r=json.loads(Path(request).read_text());root=Path(r['root']);key=r['key'];action=r['action']
    exclusive(root/(key+'.launch'),{'pid':os.getpid()})
    if action=='exit':sys.exit(7)
    if action=='signal':os.kill(os.getpid(),signal.SIGKILL)
    if action in ('sleep','child'):
        if action=='child':
            p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'])
            exclusive(root/'child.json',{'pid':p.pid})
        time.sleep(60)
    time.sleep(.12)
    exclusive(root/(key+'.payload'),{'value':key})
    if action=='lost_ack':return
    if action=='broken':Path(r['ack']).parent.mkdir(exist_ok=True);Path(r['ack']).write_text('{broken');return
    exclusive(r['ack'],{'key':key,'status':'PASS','payload':str(root/(key+'.payload'))})


def tasks(root,actions):
    root=Path(root);root.mkdir(parents=True,exist_ok=True);out=[]
    for i,action in enumerate(actions):
        key=f'key{i}';ack=root/(key+'.ack');req=root/(key+'.request')
        exclusive(req,{'root':str(root),'key':key,'ack':str(ack),'action':action})
        out.append({'key':key,'ack':str(ack),'argv':[sys.executable,__file__,'--worker',str(req)]})
    return out


def validate(task,ack):
    data=json.loads(Path(ack['payload']).read_text());assert data['value']==task['key'];return ack['payload']


def wait_file(path):
    for _ in range(500):
        if Path(path).exists():return
        time.sleep(.01)
    raise AssertionError('file never appeared: '+str(path))


if __name__=='__main__':
    if sys.argv[1]=='--worker':synthetic_worker(sys.argv[2])
    elif sys.argv[1]=='--supervisor':
        root=Path(sys.argv[2]);run_tasks(root/'run',tasks(root,['child']),1,validate)
    sys.exit(0)

import pytest
import psutil


def assert_dead(pid):
    for _ in range(100):
        if not psutil.pid_exists(pid):return
        time.sleep(.01)
    raise AssertionError('orphan remains '+str(pid))


def test_adopted_never_launches(tmp_path):
    ts=tasks(tmp_path,['ok'])
    with pytest.raises(SingleAttemptError,match='ADOPTED'):run_tasks(tmp_path/'run',ts,1,validate,forbidden=['key0'])
    assert not (tmp_path/'key0.launch').exists()


def test_missing_once_and_second_invocation_refused(tmp_path):
    ts=tasks(tmp_path,['ok']);r=run_tasks(tmp_path/'run',ts,1,validate)
    assert r['launch_counts']=={'key0':1} and r['retry_count']==0
    with pytest.raises(FileExistsError):run_tasks(tmp_path/'run',ts,1,validate)
    for pid in r['pids']:assert_dead(pid)


@pytest.mark.parametrize('action',['exit','signal','broken','lost_ack'])
def test_failure_no_requeue_or_next_dispatch(tmp_path,action):
    ts=tasks(tmp_path,[action,'ok'])
    with pytest.raises(Exception):run_tasks(tmp_path/'run',ts,1,validate)
    assert (tmp_path/'key0.launch').exists() and not (tmp_path/'key1.launch').exists()
    assert len(list((tmp_path/'run/claims').glob('*.json')))==1
    assert (tmp_path/'run/failure.json').exists()
    with pytest.raises(FileExistsError):run_tasks(tmp_path/'run',ts,1,validate)
    if action=='lost_ack':assert (tmp_path/'key0.payload').exists()
    for p in (tmp_path/'run/states').glob('*/started.json'):assert_dead(json.loads(p.read_text())['pid'])


def test_payload_failure_stops(tmp_path):
    ts=tasks(tmp_path,['ok','ok'])
    def bad(*args):raise ValueError('hash mismatch')
    with pytest.raises(ValueError,match='hash mismatch'):run_tasks(tmp_path/'run',ts,1,bad)
    assert not (tmp_path/'key1.launch').exists()


def test_eight_workers_normal_and_gc(tmp_path):
    import gc
    ts=tasks(tmp_path,['ok']*16)
    def checked(*args):gc.collect();return validate(*args)
    r=run_tasks(tmp_path/'run',ts,8,checked)
    assert r['launch_counts']=={f'key{i}':1 for i in range(16)} and len(list(tmp_path.glob('*.launch')))==16
    for pid in r['pids']:assert_dead(pid)


def test_duplicate_input_refused_before_launch(tmp_path):
    ts=tasks(tmp_path,['ok'])
    with pytest.raises(SingleAttemptError,match='DUPLICATE'):run_tasks(tmp_path/'run',ts+ts,8,validate)
    assert not (tmp_path/'key0.launch').exists()


def test_concurrent_exclusive_claim(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    def claim(i):
        try:exclusive(tmp_path/'claim.json',{'i':i});return True
        except FileExistsError:return False
    with ThreadPoolExecutor(max_workers=8) as pool:assert sum(pool.map(claim,range(16)))==1


def test_supervisor_cancellation_reaps_group_and_persists_claim(tmp_path):
    p=subprocess.Popen([sys.executable,__file__,'--supervisor',str(tmp_path)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    wait_file(tmp_path/'child.json');child=json.loads((tmp_path/'child.json').read_text())['pid']
    worker=json.loads((tmp_path/'key0.launch').read_text())['pid']
    p.send_signal(signal.SIGINT);assert p.wait(timeout=8)!=0
    assert_dead(worker);assert_dead(child)
    assert (tmp_path/'run/claims/key0.json').exists() and (tmp_path/'run/states/key0/uncertain.json').exists()
    with pytest.raises(FileExistsError):run_tasks(tmp_path/'run',[],1,validate)


def test_recovery_function_binding_preserves_accepted_code():
    from s12_recovery import bind_function
    import s12_alignment as a,s12_validation as v
    old=a.summarize_model.__globals__['generation_bundle']
    new=bind_function(a.summarize_model,generation_bundle=lambda *args:None)
    assert new.__code__ is a.summarize_model.__code__ and a.summarize_model.__globals__['generation_bundle'] is old
    assert bind_function(v.verify_model,generation_bundle=lambda *args:None).__code__ is v.verify_model.__code__


def test_contract_partition_and_adopted_worker_guard(monkeypatch):
    import s12_recovery as r
    c,specs,adopted,missing=r.inventory(False)
    assert len(adopted)==2983 and len(missing)==1529 and 'cmp_B2__0186' in adopted
    assert not set(adopted)&set(missing) and set(adopted)|set(missing)==set(specs)
    with pytest.raises(ValueError,match='ADOPTED_COMPUTATION_FORBIDDEN'):r.compute_worker({'key':next(iter(adopted))})


def test_full_authorization_and_pilot_aggregation_guard(tmp_path):
    import s12_recovery as r
    c,_=r.configuration()
    with pytest.raises(ValueError,match='NOT_AUTHORIZED'):r.context(Path(c['output_root'])/'forbidden','full',8)
    with pytest.raises(ValueError,match='NO_PILOT_FULL_AGGREGATION'):r.downstream({'execution_phase':'pilot'},None)


def test_mixed_reader_hash_tamper_and_unindexed_rejection(tmp_path):
    import s12_recovery as r
    from s11_artifacts import publish,write_json,load_bundle
    c,_,adopted,_=r.inventory(False);old=next(iter(adopted.values()));b=load_bundle(old['manifest_path'])
    ctx={'root':str(tmp_path),'scope':'full','execution_phase':'pilot','marker':'new-executor'}
    row={'manifest':old['manifest_path'],'manifest_sha256':old['manifest_sha256'],'producing_context':c['original_context'],'files':b['files']}
    reader=r.MixedReader(ctx,{'rows':[row]})
    assert reader(old['manifest_path'],ctx)['context']==c['original_context']
    p=publish(ctx,'fixture','new',lambda st:(write_json(st/'data.json',{'x':1}) or {}))
    assert reader(p,ctx)['context']==ctx
    fake=publish(ctx,'s12_alignment_blocks','unindexed',lambda st:(write_json(st/'data.json',{'x':1}) or {}))
    with pytest.raises(ValueError,match='UNINDEXED_BLOCK'):reader(fake,ctx)
    Path(p).parent.joinpath('data.json').write_text('{}')
    with pytest.raises(ValueError,match='HASH'):reader(p,ctx)


def test_mixed_summary_consumes_old_and_new_without_kernel(tmp_path):
    import s12_recovery as r,s12_alignment as a
    import pyarrow as pa,pyarrow.parquet as pq
    from s11_artifacts import publish,write_json,read_json,payload
    from representation_analysis import query_summary
    c,_,_,_=r.inventory(False)
    ctx={'root':str(tmp_path/'new'),'scope':'full','execution_phase':'pilot'}
    # Synthetic values only; manifests deliberately keep distinct contexts.
    oldctx={**ctx,'root':str(tmp_path/'old'),'executor':'old'}
    key='cmp_A1';desc='building_coverage';regions=['rho','rank1','upper','middle','lower']
    blocks=[];index=[]
    for i,context in enumerate((oldctx,ctx)):
        records=[{**a.binding(key),'query_index':i,'descriptor':desc,'mode':mode,'region':region,'value':float(i),'total_count':1,'valid_count':1,'invalid_count':0} for mode in ('standard','nonlocal') for region in regions]
        def build(st,records=records,i=i):
            pq.write_table(pa.Table.from_pylist(records),st/'metrics.parquet');return {'configuration_id':key,'positions':[i]}
        p=publish(context,'s12_alignment_blocks',key+f'__{i:04d}',build)
        b=r.load_bundle(p);blocks.append(p);index.append({'manifest':p,'manifest_sha256':r.file_sha256(p),'producing_context':context,'files':b['files']})
    plan=publish(ctx,'s12_model_block_plan','plan',lambda st:(write_json(st/'plan.json',{'blocks':[{'configuration_id':key,'positions':[0,1]}]}) or {}))
    reader=r.MixedReader(ctx,{'rows':index})
    fn=r.bind_function(a.summarize_model,generation_bundle=reader,configuration=lambda:({'descriptor_order':[desc],'protocol':{'regions':regions}},{}))
    p=fn(ctx,key,plan,blocks);rows=read_json(payload(p,'summary.json'))
    assert len(rows)==10 and all(x['query_median']==.5 and x['query_total_count']==2 for x in rows)
    assert r.load_bundle(blocks[0])['context']==oldctx


def test_failure_journal_error_still_reaps_children(tmp_path,monkeypatch):
    import s12_single_attempt as s
    ts=tasks(tmp_path,['exit','sleep']);original=s.exclusive
    def fail_log(path,value):
        if Path(path).name=='failure.json':raise OSError('simulated disk full')
        return original(path,value)
    monkeypatch.setattr(s,'exclusive',fail_log)
    with pytest.raises(OSError,match='disk full'):run_tasks(tmp_path/'run',ts,4,validate)
    for p in (tmp_path/'run/states').glob('*/started.json'):assert_dead(json.loads(p.read_text())['pid'])
