#!/usr/bin/env python3
"""At most 100 S10 originals: exact Fourier cache/reader equivalence and timing.

Consumes the temporary receipt made by benchmark_retrieval_visualization.py
--stage initialize and exact legacy/optimized originals. Never executes targets.
"""
import os
for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):
    os.environ[key]='1'
os.environ['CUBLAS_WORKSPACE_CONFIG']=':4096:8'
from pathlib import Path
import sys
import argparse
import io
import json
import hashlib
import time
import threading
import subprocess
import tempfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
import numpy as np
import torch
from benchmark_retrieval_visualization import Meter
from retrieval_artifacts import require, publish, load, digest, file_hash
from retrieval_lineage import config, runtime
from retrieval_geometry import create_cache, GeometryReader, configuration_groups, active
import retrieval_geometry as geometry_module
import retrieval_inference as inference
from retrieval_ranking import rank, sample_queries
from training_family_inputs import project, project_fourier

EDGELESS = {'scn_40cc5ee26478726df91243a6','scn_709daf6833f15dfc32609f81'}


class GPUMeter(Meter):
    def __enter__(self):
        super().__enter__()
        self.gpu=[]
        def poll():
            while not self.stop.is_set():
                text=subprocess.check_output(['nvidia-smi','--id=0','--query-gpu=utilization.gpu,memory.used',
                    '--format=csv,noheader,nounits'],text=True)
                self.gpu.append([float(v.strip()) for v in text.strip().split(',')])
                self.stop.wait(.5)
        torch.cuda.reset_peak_memory_stats()
        self.gpu_worker=threading.Thread(target=poll,daemon=True);self.gpu_worker.start()
        return self

    def __exit__(self,*args):
        super().__exit__(*args);self.gpu_worker.join()
        self.result.update(gpu_samples=len(self.gpu),gpu_util_mean=float(np.mean([r[0] for r in self.gpu])) if self.gpu else None,
            gpu_peak_mib=max([r[1] for r in self.gpu],default=0),cuda_peak_allocated_bytes=torch.cuda.max_memory_allocated())


def input_hash(value):
    h=hashlib.sha256()
    def add(v):
        if isinstance(v,torch.Tensor):
            h.update(str(v.dtype).encode());h.update(str(tuple(v.shape)).encode());h.update(v.detach().cpu().contiguous().numpy().tobytes())
        elif isinstance(v,dict):
            for k in sorted(v):h.update(k.encode());add(v[k])
        elif isinstance(v,(tuple,list)):
            h.update(str(type(v)).encode())
            for x in v:add(x)
        else:h.update(repr(v).encode())
    add(value);return h.hexdigest()


def run(work):
    cfg=config('config/retrieval_visualization.yml');ctx=json.loads((work/'context.json').read_text())
    require(ctx['config']['campaign_sha256']==cfg['campaign_sha256'],'BENCHMARK_CAMPAIGN')
    body=ctx['body'];rows=sorted(ctx['selected'],key=lambda r:r['scene_id'])
    require(len(rows)==100 and EDGELESS <= {r['scene_id'] for r in rows},'BENCHMARK_SCENES')
    for model in body['models']:require(file_hash(model['payload'])==model['payload_sha256'],'BENCHMARK_CHECKPOINT')
    cfg={**cfg,'gallery_count':100};rid=runtime(cfg)['runtime_id']
    groups=configuration_groups(cfg,body['models'])
    require(sum(len(g['models']) for g in groups)==25,'ACTIVE_COUNT')
    roots=body['roots'];pre=json.loads(Path(roots['preprocessing']).read_text())
    output=work/'fourier_benchmark.jsonl'
    require(not output.exists(),'BENCHMARK_EXISTS')
    def emit(value):
        with output.open('a') as f:f.write(json.dumps(value)+'\n')
        print(json.dumps(value),flush=True)
    emit({'kind':'inventory','groups':groups,'inactive':[m['configuration_id'] for m in body['models'] if not active(m)],'runtime_id':rid})
    def original_manifest(selected,directory,name):
        selected=sorted(selected,key=lambda r:r['scene_id'])
        bindings={'generation_id':'bounded_'+digest({'runtime':rid,'scenes':selected})[:24],
            'runtime_id':rid,'scope':'noncanonical_smoke','model_manifest_id':digest(body['models']),
            'gallery_manifest_id':digest(selected),'query_manifest_id':digest(sample_queries(selected,20260916,2,len(selected)))}
        return publish(directory/name,'original_inputs',{**bindings,
            'samples':[{'scene_id':r['scene_id'],'path':r['scene_id']+'.pt'} for r in selected],
            'preprocessing_id':pre['preprocessing_id'],'preprocessing_sha256':file_hash(roots['preprocessing']),
            'categories_sha256':file_hash(roots['categories'])},[directory/(r['scene_id']+'.pt') for r in selected])
    manifests={n:original_manifest(ctx['selected'][:n],work/'optimized-100-0',f'originals_{n}.json') for n in (6,25,50,100)}
    caches={}
    inference.initialize_inference(cfg)
    for n in (6,25,50,100):
        with GPUMeter() as meter:
            caches[n]=create_cache({**cfg,'gallery_count':n},body['models'],roots,manifests[n],work/f'geometry_{n}')
        emit({'kind':'cache_generation','n':n,**meter.result,'scenes_per_s':n/meter.result['wall_s'],
              'artifact_id':load(caches[n])['artifact_id']})
    with GPUMeter() as meter:
        repeated=create_cache(cfg,body['models'],roots,manifests[100],work/'geometry_100_repeat')
    require(Path(caches[100]).read_bytes()==Path(repeated).read_bytes(),'CACHE_MANIFEST_RERUN')
    for entry in load(caches[100])['files']:
        require((Path(caches[100]).parent/entry['path']).read_bytes()==(Path(repeated).parent/entry['path']).read_bytes(),'CACHE_PAYLOAD_RERUN')
    emit({'kind':'cache_regeneration','n':100,'manifest_payload_bytes_exact':True,**meter.result})
    # Storage prototype is a separately evaluated call of the unchanged GPU function.
    prototypes=torch.load(work/'prototype_features.pt',weights_only=False)
    raw_by_id={r['scene_id']:(r['magnitude'],r['phase']) for r in prototypes}
    prepared=load(manifests[100]);readers={g['configuration_sha256']:GeometryReader(caches[100],prepared,g['configuration'],cfg) for g in groups}
    for row in rows:
        sample=torch.load(work/'optimized-100-0'/(row['scene_id']+'.pt'),weights_only=False)
        for group in groups:
            cached=readers[group['configuration_sha256']].get(sample)
            require(input_hash(cached)==input_hash(raw_by_id[row['scene_id']]),'FOURIER_EXACT')
            for model in body['models']:
                if model['configuration_id'] not in group['models']:continue
                projected,metadata=project(sample,model['model_id'])
                a=project_fourier(cached,metadata,projected['entities']['local_entity_id'])
                b=project_fourier(raw_by_id[row['scene_id']],metadata,projected['entities']['local_entity_id'])
                require(input_hash(a)==input_hash(b),'PROJECTED_FOURIER_EXACT')
    emit({'kind':'features','n':100,'active_configurations':25,'fourier_and_all_family_projections_exact':True})
    # Full unchanged legacy reader created these separately; byte equality isolates reader change.
    legacy=original_manifest(rows,work/'legacy-100','originals_100.json')
    require(Path(legacy).read_bytes()==Path(manifests[100]).read_bytes(),'READER_ORIGINAL_MANIFEST')
    require(all(file_hash(work/'legacy-100'/(r['scene_id']+'.pt'))==file_hash(work/'optimized-100-0'/(r['scene_id']+'.pt')) for r in rows),'READER_BYTES')
    emit({'kind':'reader','n':100,'input_payload_and_manifest_bytes_exact':True})
    # Hook-only telemetry: no numerical transform, reordering or precision change.
    timing={};trace=[]
    build=inference.build_scene_encoder
    def traced_build(*args,**kw):
        model=build(*args,**kw);forward=model.forward
        model.register_forward_pre_hook(lambda module,args:trace.append(input_hash(args)))
        def timed_forward(*a,**k):
            torch.cuda.synchronize();t=time.monotonic();out=forward(*a,**k);torch.cuda.synchronize()
            timing['model_forward_s']+=time.monotonic()-t
            return out
        model.forward=timed_forward;return model
    inference.build_scene_encoder=traced_build
    get=geometry_module.GeometryReader.get
    def timed_get(self,*a,**kw):
        t=time.monotonic();out=get(self,*a,**kw);timing['cache_read_s']+=time.monotonic()-t;return out
    geometry_module.GeometryReader.get=timed_get
    original_fourier=inference.geometry_fourier_features
    def timed_fourier(*a,**kw):
        t=time.monotonic();out=original_fourier(*a,**kw);torch.cuda.synchronize();timing['fourier_s']+=time.monotonic()-t;return out
    inference.geometry_fourier_features=timed_fourier
    queries=sample_queries(rows,20260916,30,100)
    require(all(sum((r['center_x']-q['center_x'])**2+(r['center_y']-q['center_y'])**2>=2000**2 for r in rows)>=50 for q in queries),'PILOT_NONLOCAL_SUPPORT')
    for mid in ('main','cmp_A4','ofat_d_256','cmp_DS'):
        model=next(m for m in body['models'] if m['configuration_id']==mid)
        reference=None;reference_trace=None;reference_rank=None
        for mode,original,cache in [('legacy_onfly',legacy,None),('reader_onfly',manifests[100],None),
                                    ('reader_cached',manifests[100],caches[100] if active(model) else work/'MUST_NOT_BE_READ')]:
            timing={'model_forward_s':0.,'cache_read_s':0.,'fourier_s':0.};trace=[]
            with GPUMeter() as meter:values=inference.infer(cfg,model,roots,rows,original,cache)
            ranked=rank(values,rows,queries,model,{},50)
            if reference is None:reference,reference_trace,reference_rank=values.copy(),list(trace),ranked
            require(reference.dtype==values.dtype and reference.shape==values.shape and reference.tobytes()==values.tobytes(),'EMBEDDING_EXACT')
            require(trace==reference_trace,'MODEL_INPUT_EXACT')
            require((reference@reference.T).tobytes()==(values@values.T).tobytes(),'COSINE_EXACT')
            require(ranked==reference_rank,'RANKING_EXACT')
            edge_queries=[r for r in rows if r['scene_id'] in EDGELESS]
            require(rank(reference,rows,edge_queries,model,{},50)==rank(values,rows,edge_queries,model,{},50),'EDGELESS_RANKING_EXACT')
            emit({'kind':'inference','model':mid,'mode':mode,'n':100,**meter.result,**timing,
                'scenes_per_s':100/meter.result['wall_s'],'model_inputs_embeddings_cosines_rankings_exact':True,
                'edgeless_scene_ids':sorted(EDGELESS),'ranking_rows':len(ranked),'geometry_calls':0 if cache is not None or not active(model) else 100})
            np.save(work/f'{mid}_{mode}.npy',values)
    emit({'kind':'result','status':'PASS','batch_size':1,'maximum_scenes':100})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--workdir',type=Path,required=True)
    work=parser.parse_args().workdir.resolve()
    require(work.is_relative_to(Path(tempfile.gettempdir()).resolve()),'BENCHMARK_TEMP_ONLY')
    run(work)
