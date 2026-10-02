"""Frozen D6 UMAP. Invoked in a fresh, single-threaded process; never clusters."""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from representation_analysis import select_illustrations
from s11_artifacts import (configuration, load_bundle, payload, publish,
    read_json, require, runtime, write_json)

THREAD_ENV = {k: "1" for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
    "NUMBA_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS")}

def fit_coordinates(vectors, scene_ids, scope):
    contract, _, execution = configuration()
    require(all(os.environ.get(k) == v for k,v in THREAD_ENV.items()), "UMAP_THREAD_ENV")
    require(vectors.dtype == np.float32 and vectors.shape == (len(scene_ids), 256) and
            np.isfinite(vectors).all() and vectors.flags.c_contiguous, "UMAP_INPUT")
    require(scene_ids == sorted(set(scene_ids)) and
            np.allclose(np.linalg.norm(vectors, axis=1), 1, rtol=0, atol=2e-6), "UMAP_ORDER_NORMALIZATION")
    require((scope == "full" and len(scene_ids) == 9000) or
            (scope == "pilot" and len(scene_ids) == execution["umap_pilot_scenes"]), "UMAP_SCOPE")
    provenance = runtime()
    import numba
    import umap
    from threadpoolctl import threadpool_info, threadpool_limits
    numba.set_num_threads(1)
    settings = {k:contract["umap"][k] for k in ("n_components", "n_neighbors", "min_dist", "metric",
        "random_state", "transform_seed", "n_jobs", "init", "low_memory", "n_epochs")}
    with threadpool_limits(limits=1):
        coordinates = umap.UMAP(**settings).fit_transform(vectors)
        blas = threadpool_info()
    require(coordinates.shape == (len(scene_ids), 2) and np.isfinite(coordinates).all(), "UMAP_COORDINATES")
    require(numba.get_num_threads() == 1 and all(b["num_threads"] == 1 for b in blas), "UMAP_SINGLE_THREAD")
    return coordinates, {"runtime":provenance, "blas":blas, "settings":settings,
        "input_bytes_sha256":hashlib.sha256(vectors.tobytes()).hexdigest(),
        "scene_order_sha256":hashlib.sha256("\n".join(scene_ids).encode()).hexdigest(),
        "coordinate_bytes_sha256":hashlib.sha256(coordinates.tobytes()).hexdigest(),
        "panels":contract["umap"]["panels"], "purpose":"visualization only; no geographic similarity inferred from UMAP distances"}

def build_umap(ctx, parent_manifest, vectors, scene_ids):
    contract, _, _ = configuration()
    def build(stage):
        xy, provenance = fit_coordinates(vectors, scene_ids, ctx["scope"])
        table = pa.table({"scene_id":scene_ids,"x":xy[:,0],"y":xy[:,1]})
        pq.write_table(table, stage / "coordinates.parquet", compression="zstd")
        read = pq.read_table(stage / "coordinates.parquet")
        require(read.equals(table), "UMAP_READBACK")
        write_json(stage / "runtime.json", provenance)
        write_json(stage / "panels.json", contract["umap"]["panels"])
        write_json(stage / "illustrations.json", select_illustrations(xy, scene_ids, contract["illustrations"]["selection_seed"]))
        return {"scene_count":len(scene_ids),"input_dimension":256,"output_dimension":2,"coordinate_schema":"scene_id:string,x:float32,y:float32"}
    return publish(ctx, "umap", "coordinates", build, [parent_manifest])
