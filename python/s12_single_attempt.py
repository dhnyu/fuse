"""Durable, fail-fast local scheduling. No scientific code or retry mechanism.

Linux process groups and retained Popen handles replace crew for recovery only.
Each namespace is single-use, including after an interrupted supervisor.
"""
import ctypes
import errno
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import time


def exclusive(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(value, sort_keys=True, allow_nan=False) + '\n').encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, 'wb') as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
    finally:
        d = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(d)
        finally: os.close(d)


def arm_parent_death(expected_parent):
    """Worker entrypoint: terminate the whole session if its supervisor dies."""
    def die(signum, frame):
        os.killpg(os.getpgrp(), signal.SIGKILL)
    signal.signal(signal.SIGTERM, die)
    if ctypes.CDLL(None, use_errno=True).prctl(1, signal.SIGTERM, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), 'PR_SET_PDEATHSIG')
    if os.getppid() != expected_parent:
        die(None, None)


class SingleAttemptError(RuntimeError):
    pass


def run_tasks(root, tasks, workers, validate, forbidden=(), sample_interval=.03):
    """Task dict: key, argv, ack. Validates ack before another dispatch.

    Namespace ownership is claimed before any launch. All state files are append-
    only/exclusive, including failure and uncertain events. Never re-open a run.
    """
    root = Path(root); tasks = list(tasks)
    keys = [t['key'] for t in tasks]
    if workers not in (1, 4, 8) or len(keys) != len(set(keys)):
        raise SingleAttemptError('INVALID_WORKERS_OR_DUPLICATE_KEYS')
    if set(keys) & set(forbidden):
        raise SingleAttemptError('ADOPTED_KEY_SCHEDULED')
    if any('/' in k or k in ('', '.', '..') for k in keys):
        raise SingleAttemptError('UNSAFE_KEY')
    # Claimed or failed namespaces cannot be resumed, even if they look complete.
    exclusive(root/'owner.json', {'pid': os.getpid(), 'keys': keys, 'workers': workers, 'time': time.time()})
    if ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), 'PR_SET_CHILD_SUBREAPER')
    active = {}; outputs = {}; launched = []; old_handlers = {}; peak = 0
    start = time.monotonic(); usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    def state(key, name, **extra):
        exclusive(root/'states'/key/(name+'.json'), {'state': name, 'time': time.time(), **extra})
    def cancel(signum, frame): raise SingleAttemptError('SUPERVISOR_SIGNAL:'+str(signum))
    def kill_groups():
        # Always address groups, even when a group leader has already exited.
        for pid in launched:
            try: os.killpg(pid, signal.SIGTERM)
            except ProcessLookupError: pass
        deadline = time.monotonic()+2
        while time.monotonic()<deadline and any(p.poll() is None for p,_,_ in active.values()):
            time.sleep(.01)
        for pid in launched:
            try: os.killpg(pid, signal.SIGKILL)
            except ProcessLookupError: pass
        for p,_,handle in active.values():
            p.wait(); handle.close()
        # Adopted grandchildren of killed groups must be reaped too.
        deadline=time.monotonic()+2
        while time.monotonic()<deadline:
            try:
                pid,_=os.waitpid(-1, os.WNOHANG)
                if pid==0: time.sleep(.01)
            except ChildProcessError: break
    def drain():
        # Poll every active worker first: an available failure outranks success.
        done=[(key,p,task,h,p.poll()) for key,(p,task,h) in active.items() if p.poll() is not None]
        for key,p,task,h,rc in done:
            if rc != 0:
                state(key,'failed',returncode=rc)
                raise SingleAttemptError('WORKER_EXIT:'+key+':'+str(rc))
        for key,p,task,h,rc in done:
            try:
                ack=json.loads(Path(task['ack']).read_text())
                if ack.get('key')!=key or ack.get('status')!='PASS':
                    raise SingleAttemptError('BROKEN_STATUS_CHANNEL:'+key)
                value=validate(task,ack)
                state(key,'published',ack=ack)
                state(key,'verified',result=value)
            except BaseException:
                state(key,'uncertain',reason='publication_or_ack_validation_failed')
                raise
            # A successful leader cannot leave a background child running.
            import psutil
            group=[]
            for child in psutil.Process().children(recursive=True):
                try:
                    if os.getpgid(child.pid)==p.pid: group.append(child.pid)
                except ProcessLookupError: pass
            if group: raise SingleAttemptError('ORPHAN_AFTER_SUCCESS:'+key)
            outputs[key]=value; p.wait();h.close();del active[key]
    try:
        for sig in (signal.SIGINT,signal.SIGTERM):
            old_handlers[sig]=signal.signal(sig,cancel)
        for task in tasks: state(task['key'],'planned')
        cursor=0
        while cursor<len(tasks) or active:
            drain()
            if cursor<len(tasks) and len(active)<workers:
                drain()  # No batch of unchecked launches.
                task=tasks[cursor];key=task['key'];cursor+=1
                exclusive(root/'claims'/(key+'.json'), {'key':key,'time':time.time(),'launch_count':1})
                handle=(root/(key+'.log')).open('xb')
                env=dict(os.environ)
                for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMBA_NUM_THREADS','VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS'):env[name]='1'
                env['S12_RECOVERY_SUPERVISOR_PID']=str(os.getpid())
                try:
                    p=subprocess.Popen(task['argv'],stdin=subprocess.DEVNULL,stdout=handle,stderr=subprocess.STDOUT,env=env,start_new_session=True)
                except BaseException:
                    handle.close();state(key,'failed',reason='launch_failed');raise
                launched.append(p.pid);active[key]=(p,task,handle)
                state(key,'started',pid=p.pid,launch_count=1)
                continue
            import psutil
            rss=0
            for p in [psutil.Process(),*psutil.Process().children(recursive=True)]:
                try: rss+=p.memory_info().rss
                except psutil.Error: pass
            peak=max(peak,rss)
            time.sleep(sample_interval)
        after=resource.getrusage(resource.RUSAGE_CHILDREN);wall=time.monotonic()-start
        receipt={'status':'PASS','launch_counts':{k:1 for k in keys},'pids':launched,'workers':workers,'threads':1,
                 'wall_seconds':wall,'cpu_seconds':after.ru_utime+after.ru_stime-usage.ru_utime-usage.ru_stime,
                 'peak_tree_rss_bytes':peak,'read_bytes':(after.ru_inblock-usage.ru_inblock)*512,
                 'write_bytes':(after.ru_oublock-usage.ru_oublock)*512,'outputs':outputs,'retry_count':0}
        exclusive(root/'receipt.json',receipt)
        return receipt
    except BaseException as exc:
        try:
            exclusive(root/'failure.json',{'status':'BLOCKED','error':repr(exc),'time':time.time(),'launched_pids':launched})
            for key in active:
                if not (root/'states'/key/'uncertain.json').exists() and not (root/'states'/key/'failed.json').exists():
                    state(key,'uncertain',reason='supervisor_stopped')
        finally:
            # Cleanup must run even when the failure journal's filesystem fails.
            kill_groups()
        raise
    finally:
        for sig,handler in old_handlers.items():signal.signal(sig,handler)
