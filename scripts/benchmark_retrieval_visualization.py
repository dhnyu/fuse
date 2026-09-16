#!/usr/bin/env python3
"""Bounded NONCANONICAL S10 performance pilot; never calls the formal graph.

The work directory must be a newly created system-temporary directory. The
operator owns its cleanup. All selected inputs/checkpoints come from native S09
validation; no historical embedding or evaluation lifecycle is used.
"""
import os
for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[key] = "1"
os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
from pathlib import Path
import argparse
import collections
import io
import json
import sys
import threading
import time
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
import numpy as np
import psutil
import torch
import yaml
from retrieval_artifacts import file_hash, publish_bytes, require
from retrieval_lineage import OriginalCatalog, config, inventory, population
from model_data import read_original_scene, tensorize_scene, build_vocabulary
from retrieval_originals import OriginalReader


class Meter:
    def __enter__(self):
        self.process = psutil.Process()
        self.io = self.process.io_counters()
        self.cpu = self.process.cpu_times()
        self.host = psutil.cpu_times()
        self.start = time.monotonic()
        self.peak = self.process.memory_info().rss
        self.stop = threading.Event()
        def monitor():
            while not self.stop.wait(.1):
                self.peak = max(self.peak, self.process.memory_info().rss)
        self.worker = threading.Thread(target=monitor, daemon=True)
        self.worker.start()
        return self

    def __exit__(self, *args):
        self.stop.set(); self.worker.join()
        wall = time.monotonic()-self.start
        io1, cpu, host = self.process.io_counters(), self.process.cpu_times(), psutil.cpu_times()
        total = sum(host)-sum(self.host)
        self.result = dict(wall_s=wall, cpu_percent=100*(cpu.user+cpu.system-self.cpu.user-self.cpu.system)/wall,
            host_iowait_percent=100*(host.iowait-self.host.iowait)/total if total else 0,
            read_bytes=io1.read_bytes-self.io.read_bytes, write_bytes=io1.write_bytes-self.io.write_bytes,
            read_chars=io1.read_chars-self.io.read_chars, write_chars=io1.write_chars-self.io.write_chars,
            peak_rss_bytes=self.peak)


def equivalent(a,b):
    if isinstance(a, torch.Tensor):
        return isinstance(b,torch.Tensor) and a.dtype==b.dtype and a.shape==b.shape and torch.equal(a,b)
    if isinstance(a,np.ndarray):
        return isinstance(b,np.ndarray) and a.dtype==b.dtype and np.array_equal(a,b,equal_nan=True)
    if isinstance(a,dict):
        return a.keys()==b.keys() and all(equivalent(a[k],b[k]) for k in a)
    if isinstance(a,(tuple,list)):
        return type(a)==type(b) and len(a)==len(b) and all(equivalent(x,y) for x,y in zip(a,b))
    return a==b or (isinstance(a,float) and isinstance(b,float) and np.isnan(a) and np.isnan(b))


def preparation(work, ctx, reader, sizes):
    cfg, body = ctx['config'],ctx['body']
    training=yaml.safe_load(Path(cfg['training_config']).read_text())
    preprocessing=json.loads(Path(body['roots']['preprocessing']).read_text())
    vocab=build_vocabulary(body['roots']['categories'])
    for n in sizes:
        require(1<=n<=100,'BENCHMARK_LIMIT')
        rows=ctx['selected'][:n]
        for repeat in range(2):
            out=work/f'{reader}-{n}-{repeat}'
            out.mkdir(exist_ok=False)
            timings=collections.Counter()
            catalog=OriginalCatalog(body['roots'],training)
            old_hash=catalog.p3_tar
            def checked(s):
                start=time.monotonic();result=old_hash(s);timings['source_binding_hash_s']+=time.monotonic()-start;return result
            catalog.p3_tar=checked
            with Meter() as meter, OriginalReader(catalog) as cache:
                original_rows, original_raster = cache._rows, cache._raster
                def table_rows(name, sid):
                    t=time.monotonic();value=original_rows(name,sid)
                    timings['table_'+name.split('/')[0]+'_s']+=time.monotonic()-t
                    return value
                def raster(index):
                    t=time.monotonic();value=original_raster(index)
                    timings['raster_arrays_and_extract_s']+=time.monotonic()-t
                    return value
                cache._rows, cache._raster = table_rows, raster
                by_id={r['scene_id']:r for r in rows}
                ids=cache.ordered_ids(list(by_id)) if reader=='optimized' else list(by_id)
                for sid in ids:
                    t=time.monotonic()
                    scene=cache.read(sid) if reader=='optimized' else read_original_scene(catalog,sid)
                    timings['read_scene_inclusive_s']+=time.monotonic()-t
                    t=time.monotonic();sample=tensorize_scene(scene,preprocessing,vocab)
                    sample['scene_center_5186']=torch.tensor(scene['center'],dtype=torch.float64)
                    timings['tensorize_s']+=time.monotonic()-t
                    t=time.monotonic();buffer=io.BytesIO();torch.save(sample,buffer)
                    timings['serialize_s']+=time.monotonic()-t
                    t=time.monotonic();publish_bytes(out/(sid+'.pt'),buffer.getvalue())
                    timings['publish_fsync_s']+=time.monotonic()-t
                t=time.monotonic();hashes={p.name:file_hash(p) for p in sorted(out.glob('*.pt'))}
                timings['output_hash_s']+=time.monotonic()-t
            result=dict(kind='preparation',reader=reader,n=n,repeat=repeat,cache='cold-ish process handles' if repeat==0 else 'immediate warm OS cache; fresh reader',
                **meter.result,timings=dict(timings),shards=len(catalog.verified),files=len(hashes),bytes=sum(p.stat().st_size for p in out.glob('*.pt')))
            result.update(scenes_per_s=n/result['wall_s'],s_per_scene=result['wall_s']/n)
            for other in (work/f'{reader}-{n}-0',work/f'legacy-{n}-0'):
                if other!=out and other.is_dir():
                    require(all(equivalent(torch.load(p,weights_only=False),torch.load(other/p.name,weights_only=False)) for p in out.glob('*.pt')),'INPUT_EQUIVALENCE')
                    result['exact_input_equivalence']=True
            with (work/'measurements.jsonl').open('a') as f:f.write(json.dumps(result)+'\n')
            print(json.dumps(result),flush=True)


def inference_benchmark(work, ctx):
    import subprocess
    import gc
    from retrieval_inference import infer
    from retrieval_ranking import rank
    from retrieval_artifacts import publish
    cfg, body = (ctx['config'], ctx['body'])
    gallery = sorted(ctx['selected'][:50], key=lambda r: r['scene_id'])
    src = work / 'optimized-50-0'
    p = publish(src / 'manifest.json', 'original_inputs', {'scope': 'noncanonical_smoke', 'generation_id': 'bounded_performance', 'runtime_id': 'pilot', 'samples': [{'scene_id': r['scene_id'], 'path': r['scene_id'] + '.pt'} for r in gallery]}, [src / (r['scene_id'] + '.pt') for r in gallery])
    for model_id in ('main', 'cmp_DS', 'cmp_A4', 'ofat_d_256'):
        model = next((m for m in body['models'] if m['configuration_id'] == model_id))
        baseline = None
        baseline_rows = None
        for bs in (1,):  # Batch one is now a scientific contract.
            gpu = []
            stop = threading.Event()

            def monitor():
                while not stop.is_set():
                    raw = subprocess.check_output(['nvidia-smi', '--id=0', '--query-gpu=utilization.gpu,memory.used', '--format=csv,noheader,nounits'], text=True)
                    gpu.append([float(x.strip()) for x in raw.strip().split(',')])
                    stop.wait(0.5)
            th = threading.Thread(target=monitor)
            th.start()
            torch.cuda.reset_peak_memory_stats()
            start = time.monotonic()
            try:
                with Meter() as meter:
                    vec = infer({**cfg, 'batch_size': bs}, model, body['roots'], gallery, p)
                rows = rank(vec, gallery, gallery[:2], model, {}, 20)
                if baseline is None:
                    baseline = vec.copy()
                    baseline_rows = rows
                keys = lambda rs: [(r['query_id'], r['retrieval_mode'], r['rank'], r['gallery_scene_id']) for r in rs]
                diff = float(np.abs(vec - baseline).max())
                scores = float(np.abs(vec @ vec.T - baseline @ baseline.T).max())
                result = {'kind': 'inference', 'model': model_id, 'batch': bs, 'n': 50, **meter.result, 'scenes_per_s': 50 / meter.result['wall_s'], 'max_abs_embedding_difference': diff, 'embedding_allclose': bool(np.allclose(vec, baseline, atol=2e-06, rtol=2e-05)), 'max_abs_cosine_difference': scores, 'exact_ranking_identity': keys(rows) == keys(baseline_rows), 'exact_all_query_full_order': bool(np.array_equal(np.argsort(-(vec @ vec.T), axis=1, kind='stable'), np.argsort(-(baseline @ baseline.T), axis=1, kind='stable'))), 'peak_cuda_allocated_bytes': torch.cuda.max_memory_allocated(), 'peak_cuda_reserved_bytes': torch.cuda.max_memory_reserved()}
                np.save(work / f'{model_id}-batch{bs}.npy', vec)
            except torch.cuda.OutOfMemoryError:
                result = {'kind': 'inference', 'model': model_id, 'batch': bs, 'status': 'OOM_FAIL_CLOSED'}
            finally:
                stop.set()
                th.join()
            result.update(gpu_samples=len(gpu), gpu_util_mean=float(np.mean([r[0] for r in gpu])) if gpu else None, gpu_memory_peak_mib=max([r[1] for r in gpu], default=0))
            print(json.dumps(result), flush=True)
            with (work / 'inference.jsonl').open('a') as f:
                f.write(json.dumps(result) + '\n')
            gc.collect()
            torch.cuda.empty_cache()
            if result.get('status') == 'OOM_FAIL_CLOSED':
                break


def initialize(work):
    require(not (work/'context.json').exists(),'BENCHMARK_CONTEXT_EXISTS')
    cfg=config('config/retrieval_visualization.yml');body=inventory(cfg)
    gallery,source=population(cfg,body)
    chosen=[]
    for row in gallery:
        if all((row['center_x']-r['center_x'])**2+(row['center_y']-r['center_y'])**2>=2500**2 for r in chosen):
            chosen.append(row)
        if len(chosen)==6:break
    ids={r['scene_id'] for r in chosen}
    remaining=[r for r in gallery if r['scene_id'] not in ids]
    extra=np.random.Generator(np.random.PCG64(20260916)).permutation(len(remaining))[:94]
    selected=chosen+[remaining[int(i)] for i in extra]
    (work/'context.json').write_text(json.dumps(dict(config=cfg,body=body,gallery=gallery,source=source,selected=selected)))


def main():
    p=argparse.ArgumentParser();p.add_argument('--workdir',type=Path,required=True)
    p.add_argument('--reader',choices=['legacy','optimized'],default='optimized')
    p.add_argument('--stage',choices=['initialize','preparation','inference'],default='preparation')
    p.add_argument('--sizes',type=int,nargs='+',default=[6,25,50,100]);args=p.parse_args()
    require(args.workdir.resolve().is_relative_to(Path(tempfile.gettempdir()).resolve()),'NONCANONICAL_TEMP_ONLY')
    if args.stage=='initialize':
        initialize(args.workdir);return
    ctx=json.loads((args.workdir/'context.json').read_text())
    require(ctx['config']['campaign_id']=='s09camp_d2f6749da19ad6aa56c2d303' and len(ctx['selected'])==100,'BENCHMARK_CONTEXT')
    # Receipt generated by native inventory; pins are rechecked before every pilot.
    require(file_hash(ctx['config']['campaign'])==ctx['config']['campaign_sha256'],'CAMPAIGN_PIN')
    for path,sha in ctx['config']['source_pins'].items():require(file_hash(path)==sha,'SOURCE_PIN')
    if args.stage=='inference':
        inference_benchmark(args.workdir,ctx)
    else:
        preparation(args.workdir,ctx,args.reader,args.sizes)

if __name__=='__main__':main()
