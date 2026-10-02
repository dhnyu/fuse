#!/usr/bin/env python
"""Bounded real-P3/UMAP/alignment pilot. No full execution option exists."""
from __future__ import annotations
import os
for name in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","NUMBA_NUM_THREADS","VECLIB_MAXIMUM_THREADS","NUMEXPR_NUM_THREADS"):
    os.environ[name]="1"
import datetime
import hashlib
from pathlib import Path
import resource
import subprocess
import sys
import tempfile
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"python"))
import numpy as np
import pyarrow.parquet as pq
from scipy.stats import spearmanr
from threadpoolctl import threadpool_limits
from representation_analysis import cosine_block,eligibility,band_positions,file_sha256
from s11_artifacts import (configuration,context,load_bundle,payload,read_json,require,runtime,write_json)
from s11_descriptors import make_plan,extract_shard,extract_records,merge_descriptors,write_descriptor_tables,reader_threads
from s11_alignment import descriptor_arrays,make_alignment_plan,build_alignment_block,summarize_alignment
from s11_production import accepted_parents,read_population

def selection(ids):
    _,lock,execution=configuration()
    stats=pq.read_table(lock["parents"]["scene_statistics"]["path"]).to_pylist()
    stats=[r for r in stats if r["scene_id"] in set(ids)]
    stats.sort(key=lambda r:(hashlib.sha256(("20260923"+r["scene_id"]).encode()).hexdigest(),r["scene_id"]))
    predicates={"ordinary_dense":lambda r:r["building_count"]>=100 and r["road_count"]>=20 and r["poi_count"]>=100,
        "zero_building":lambda r:r["building_count"]==0 and r["node_count"]>0,
        "zero_road":lambda r:r["road_count"]==0 and r["node_count"]>0,
        "zero_poi":lambda r:r["poi_count"]==0 and r["node_count"]>0,
        "all_vector_empty":lambda r:r["node_count"]==0,
        "relation_edge_free":lambda r:r["ordered_pair_count"]==0 and r["node_count"]>0}
    roles={k:next(r["scene_id"] for r in stats if test(r)) for k,test in predicates.items()}
    chosen=set(roles.values())
    for row in stats:
        if len(chosen)>=execution["pilot_scene_limit"]:
            break
        chosen.add(row["scene_id"])
    return sorted(chosen),roles

def usage():
    own=resource.getrusage(resource.RUSAGE_SELF);child=resource.getrusage(resource.RUSAGE_CHILDREN)
    io={k:int(v.strip()) for k,v in (line.split(":",1) for line in Path("/proc/self/io").read_text().splitlines())}
    return {"cpu_seconds":own.ru_utime+own.ru_stime+child.ru_utime+child.ru_stime,
        "max_rss_self_kib":own.ru_maxrss,"max_rss_child_kib":child.ru_maxrss,"io":io}

def check_alignment(block,descriptors,x,centers,ids,positions,lock):
    arrays=descriptor_arrays(descriptors,ids,"pilot")
    metrics=pq.read_table(payload(block,"metrics.parquet")).to_pylist()
    bands=pq.read_table(payload(block,"bands.parquet")).to_pylist()
    with threadpool_limits(limits=1):
        scores=np.stack([x@x[q] for q in positions])
    require(np.array_equal(scores,cosine_block(x,positions)),"PILOT_GEMV_SCORE_PARITY")
    distances,modes=eligibility(centers,positions)
    stored=pq.read_table(lock["parents"]["bands"]["path"],filters=[("query_scene_id","in",[ids[q] for q in positions])]).to_pylist()
    stored={(r["query_scene_id"],r["mode"],r["rank"]):r for r in stored}
    checked=0;rho_checks=0;null_checks=0;bands_lookup={}
    lexical=np.array(ids)
    for qi,q in enumerate(positions):
        for mode,mask in modes.items():
            eligible=np.flatnonzero(mask[qi]);order=eligible[np.lexsort((lexical[eligible],-scores[qi,eligible]))]
            actual=eligible[np.argsort(-cosine_block(x,[q])[0,eligible],kind="stable")]
            require(np.array_equal(order,actual),"PILOT_FULL_ORDER")
            ranks=band_positions(np.array([len(order)]))
            for band,rank in ranks.items():
                bands_lookup[(q,mode,band)]=order[rank[0]-1]
    for r in bands:
        old=stored[(r["query_scene_id"],r["mode"],r["rank"])]
        require(all(r[k]==old[k] for k in ["candidate_scene_id","candidate_count","cosine","distance_m"]),"PILOT_ACCEPTED_BAND_PARITY")
        checked+=1
    for r in metrics:
        q=r["query_index"];qi=positions.index(q);v,valid=arrays[r["descriptor"]]
        diff=np.abs(v-v[q]) if v.ndim==1 else np.linalg.norm(v-v[q],axis=1)
        if r["region"]=="rho":
            mask=modes[r["mode"]][qi]&valid&valid[q];s=scores[qi,mask];d=diff[mask]
            reason="fewer_than_two_valid_pairs" if len(d)<2 else "constant_similarity" if np.ptp(s)==0 else "constant_difference" if np.ptp(d)==0 else None
            require(r["valid_count"]==int(mask.sum()) and r["null_reason"]==reason,"PILOT_RHO_SUPPORT_REASON")
            if reason:
                require(r["value"] is None,"PILOT_UNDEFINED_RHO");null_checks+=1
            else:
                require(abs(float(spearmanr(s,d).statistic)-r["value"])<=2e-12,"PILOT_SCIPY_RHO");rho_checks+=1
        else:
            candidates=bands_lookup[(q,r["mode"],r["region"])];ok=valid[candidates]&valid[q]
            require(r["valid_count"]==int(ok.sum()) and r["total_count"]==len(candidates),"PILOT_FIXED_BAND_SUPPORT")
            if np.any(ok):
                require(abs(float(np.mean(diff[candidates[ok]]))-r["value"])<=2e-10,"PILOT_FIXED_BAND_MEAN")
            else:
                require(r["value"] is None,"PILOT_NO_REFILL")
    return {"score_bitwise_equal":True,"exact_full_rankings":2*len(positions),"accepted_band_records":checked,
        "independent_scipy_rho_checks":rho_checks,"undefined_rho_checks":null_checks,"metric_records":len(metrics)}

def run():
    reader_threads()
    contract,lock,execution=configuration()
    root=Path(execution["pilot_root"]);root.mkdir(parents=True,exist_ok=True)
    directory=Path(tempfile.mkdtemp(prefix=datetime.datetime.now().strftime("%Y%m%d_%H%M%S_"),dir=root))
    ctx=context("pilot",directory);started=time.perf_counter();before=usage()
    print("pilot_directory="+str(directory),flush=True)
    parent=accepted_parents(ctx);x,centers,ids=read_population(parent)
    selected,roles=selection(ids)
    write_json(directory/"selection.json",{"scene_ids":selected,"roles":roles,"selection":"first SHA256(seed||scene_id) per prespecified count predicate, fill to 16 in same hash order","seed":20260923})
    plan=make_plan(ctx,selected,ids,[parent]);specs=read_json(payload(plan,"plan.json"))["shards"]
    shards=[];measurements=[]
    for spec in specs:
        tick=time.perf_counter();cpu=usage()["cpu_seconds"]
        shard=extract_shard(ctx,plan,spec);shards.append(shard)
        measurement={"branch_id":spec["branch_id"],"scene_count":len(spec["scene_ids"]),"tar_bytes":Path(spec["path"]).stat().st_size,
            "first_pass_wall_seconds":time.perf_counter()-tick,"first_pass_cpu_seconds":usage()["cpu_seconds"]-cpu}
        # Force a new read and fresh R process; do not reuse the published bundle.
        with tempfile.TemporaryDirectory(dir=directory,prefix="recompute-") as temporary:
            records=extract_records(spec,temporary)
            output=Path(temporary)/"readback";output.mkdir();write_descriptor_tables(output,records)
            for name in ("descriptors.parquet","validity.parquet","dictionary.json","qc.json"):
                require(file_sha256(output/name)==file_sha256(payload(shard,name)),"PILOT_DETERMINISTIC_DESCRIPTOR_BYTES:"+name)
        measurements.append(measurement)
        print("descriptor_shard_PASS="+spec["branch_id"],flush=True)
    descriptors=merge_descriptors(ctx,plan,shards)
    qids=sorted(set(roles.values()))
    qids=sorted(set(qids+[s for s in selected if s not in qids][:execution["pilot_query_limit"]-len(qids)]))
    positions=[ids.index(s) for s in qids]
    alignment_plan=make_alignment_plan(ctx,descriptors,parent,ids,positions)
    spec=read_json(payload(alignment_plan,"plan.json"))["blocks"][0]
    tick=time.perf_counter();block=build_alignment_block(ctx,alignment_plan,descriptors,parent,spec,x,centers,ids)
    alignment_seconds=time.perf_counter()-tick
    parity=check_alignment(block,descriptors,x,centers,ids,positions,lock)
    summaries=summarize_alignment(ctx,alignment_plan,[block],ids)
    print("alignment_PASS",flush=True)
    selection64=sorted(sorted(range(9000),key=lambda i:hashlib.sha256(("20260923"+ids[i]).encode()).hexdigest())[:64])
    fits=[];umap_seconds=[]
    for repeat in range(2):
        request=directory/f"umap_request_{repeat}.json"
        write_json(request,{"pilot_root":str(directory/f"umap_{repeat}"),"parent":parent,"positions":selection64})
        tick=time.perf_counter()
        completed=subprocess.run([sys.executable,str(ROOT/"scripts/s11_production.py"),"pilot_umap","--request",str(request)],cwd=ROOT,text=True,capture_output=True)
        require(completed.returncode==0,"UMAP_SUBPROCESS:"+completed.stderr)
        manifest=__import__("json").loads(completed.stdout.splitlines()[-1])["manifest"]
        fits.append(manifest);umap_seconds.append(time.perf_counter()-tick)
        print(f"UMAP_fresh_process_{repeat}_PASS",flush=True)
    require(pq.read_table(payload(fits[0],"coordinates.parquet")).equals(pq.read_table(payload(fits[1],"coordinates.parquet"))),"UMAP_FRESH_PROCESS_COORDINATES")
    for name in ("coordinates.parquet","runtime.json","panels.json","illustrations.json"):
        require(file_sha256(payload(fits[0],name))==file_sha256(payload(fits[1],name)),"UMAP_FRESH_PROCESS_BYTES:"+name)
    qc=read_json(payload(descriptors,"qc.json"));partial=[r["scene_id"] for r in qc if any(v>0 for v in r["raster"].values())]
    for role,pin in lock["parents"].items():
        require(file_sha256(pin["path"])==pin["sha256"],"PILOT_PARENT_UNCHANGED:"+role)
    require(runtime()==ctx["runtime"],"SOURCE_OR_RUNTIME_CHANGED_DURING_PILOT")
    result={"status":"PASS","scope":"bounded production implementation pilot; NOT scientific acceptance",
        "contract_sha256":lock["contract_sha256"],"runtime":runtime(),"scene_count":len(selected),"roles":roles,
        "partial_raster_scene_ids":partial,"partial_raster_note":"not available among the fixed 16 pilot scenes" if not partial else "observed",
        "descriptor_count":22,"deterministic_descriptor_bytes":True,"query_count":len(positions),"candidate_count":9000,
        "unsampled_candidate_descriptors":"pilot not observed; only the selected 16 provide valid descriptor comparisons",
        "parity":parity,"umap":{"scene_count":64,"fresh_process_fits":2,"identical_coordinates_and_artifact_bytes":True,"wall_seconds":umap_seconds},
        "measurements":{"shards":measurements,"before":before,"after":usage(),"wall_seconds":time.perf_counter()-started,"alignment_seconds":alignment_seconds},
        "artifacts":{"parent":parent,"descriptor_plan":plan,"descriptors":descriptors,"alignment_block":block,"summaries":summaries,"umap":fits},
        "full_execution_performed":False,"training":False,"inference":False,"parents_unchanged":True}
    receipt=directory/"pilot_receipt.json";write_json(receipt,result)
    require(read_json(receipt)==result,"PILOT_RECEIPT_READBACK")
    print("PASS receipt="+str(receipt),flush=True)

if __name__=="__main__":
    require(len(sys.argv)==1,"PILOT_NO_SCOPE_OVERRIDES")
    run()
