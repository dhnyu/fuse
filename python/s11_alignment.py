"""Blockwise full-population alignment, dissertation 5.4.2 / D4,D7.

Only native batched GEMV scores. No generic GEMM, GPU, or persisted N*N array.
Numerics are batched; Python loops serialize query records, not score queries.
"""
from __future__ import annotations
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from representation_analysis import (band_indices, band_positions, cosine_block,
    descriptor_differences, eligibility, query_summary, spearman_rows, summarize_bands)
from s11_artifacts import (assert_population, configuration, load_bundle, payload,
    publish, read_json, require, write_json)

METRIC_SCHEMA = pa.schema([("query_scene_id",pa.string()),("query_index",pa.int32()),
    ("mode",pa.string()),("descriptor",pa.string()),("region",pa.string()),
    ("value",pa.float64()),("null_reason",pa.string()),("total_count",pa.int32()),
    ("valid_count",pa.int32()),("invalid_count",pa.int32())])

def descriptor_arrays(descriptor_manifest, ids, scope):
    manifest = load_bundle(descriptor_manifest, "descriptor_acceptance")
    require(manifest["context"]["scope"] == scope, "ALIGNMENT_DESCRIPTOR_SCOPE")
    rows = pq.read_table(payload(descriptor_manifest,"descriptors.parquet")).to_pylist()
    dictionary = read_json(payload(descriptor_manifest,"dictionary.json"))
    stored_ids = [r["scene_id"] for r in rows]
    if scope == "full":
        assert_population(stored_ids, ids)
        require(len(rows) == 9000, "ALIGNMENT_FULL_DESCRIPTORS")
    else:
        require(set(stored_ids) <= set(ids) and len(rows) <= configuration()[2]["pilot_scene_limit"], "ALIGNMENT_PILOT_DESCRIPTORS")
    lookup = {r["scene_id"]:r for r in rows}
    arrays = {}
    for d in dictionary:
        values = [lookup.get(scene, {}).get(d["id"]) for scene in ids]
        valid = np.array([v is not None for v in values], dtype=bool)
        shape = (len(ids),) if d["kind"] == "scalar" else (len(ids),len(d["category_keys"]))
        v = np.zeros(shape, dtype=np.float64)
        for i in np.flatnonzero(valid):
            v[i] = values[i]
        arrays[d["id"]] = (v,valid)
    return arrays

def alignment_block(vectors, centers, ids, positions, arrays):
    require(ids == sorted(set(ids)) and vectors.shape == (len(ids),256) and centers.shape == (len(ids),2), "ALIGNMENT_INPUT")
    q = np.asarray(positions,dtype=np.int64)
    scores = cosine_block(vectors, q)
    distance, modes = eligibility(centers,q)
    indices = {mode:band_indices(scores,mask) for mode,mask in modes.items()}
    records = []
    for descriptor, (values,valid) in arrays.items():
        # LC float32 cached cell fractions are validated at their accepted 1e-6
        # tolerance. Do NOT renormalize raw observations to force binary equality.
        differences, pair_valid = descriptor_differences(values,q,valid,
            composition_tolerance=1e-6 if descriptor == "landcover_composition" else 1e-12)
        for mode, mask in modes.items():
            rho = spearman_rows(scores,differences,mask,pair_valid)
            bands = summarize_bands(differences,pair_valid,indices[mode])
            for region, summaries in [("rho",rho),*bands.items()]:
                field = "rho" if region == "rho" else "mean_difference"
                for position, summary in zip(q,summaries,strict=True):
                    records.append({"query_scene_id":ids[position],"query_index":int(position),"mode":mode,
                        "descriptor":descriptor,"region":region,"value":summary[field],
                        **{k:summary[k] for k in ("null_reason","total_count","valid_count","invalid_count")}})
    bands = []
    for mode, groups in indices.items():
        ranks = band_positions(modes[mode].sum(axis=1))
        for band,index in groups.items():
            for qi,position in enumerate(q):
                for rank,candidate in zip(ranks[band][qi],index[qi],strict=True):
                    bands.append({"query_scene_id":ids[position],"query_index":int(position),"mode":mode,
                        "band":band,"rank":int(rank),"candidate_scene_id":ids[candidate],
                        "candidate_count":int(modes[mode][qi].sum()),"cosine":float(scores[qi,candidate]),
                        "distance_m":float(distance[qi,candidate])})
    return records,bands

def validate_metrics(records, ids, positions, descriptor_names):
    keys = [(r["query_index"],r["mode"],r["descriptor"],r["region"]) for r in records]
    expected = {(int(q),m,d,b) for q in positions for m in ("standard","nonlocal") for d in descriptor_names
                for b in ("rho","rank1","upper","middle","lower")}
    require(len(keys) == len(set(keys)) and set(keys) == expected, "ALIGNMENT_KEY_COVERAGE")
    for r in records:
        require(r["query_scene_id"] == ids[r["query_index"]] and
                r["total_count"] == r["valid_count"]+r["invalid_count"] and
                min(r["valid_count"],r["invalid_count"]) >= 0, "ALIGNMENT_SUPPORT")
        require((r["value"] is None and bool(r["null_reason"])) or
                (r["value"] is not None and np.isfinite(r["value"]) and r["null_reason"] is None), "ALIGNMENT_NULL_FINITE")
        if r["region"] == "rho" and r["value"] is not None:
            require(-1-1e-15 <= r["value"] <= 1+1e-15 and r["valid_count"] >= 2, "RHO_RANGE")

def make_alignment_plan(ctx, descriptors, parents, ids, positions):
    positions = list(map(int,positions)); execution=configuration()[2]
    require(positions == sorted(set(positions)) and all(0<=q<len(ids) for q in positions), "QUERY_PLAN")
    require((ctx["scope"] == "full" and positions == list(range(9000))) or
            (ctx["scope"] == "pilot" and 0<len(positions)<=execution["pilot_query_limit"]), "ALIGNMENT_QUERY_CAP")
    blocks = [{"block_id":f"{i//32:04d}","positions":positions[i:i+32]} for i in range(0,len(positions),32)]
    def build(stage):
        write_json(stage / "plan.json", {"blocks":blocks,"scope":ctx["scope"],"query_count":len(positions),"candidate_count":len(ids)})
        return {"block_count":len(blocks),"kernel":"native_batched_gemv","permanent_score_matrix":False}
    return publish(ctx,"alignment_plan","plan",build,[descriptors,parents])

def build_alignment_block(ctx, plan_manifest, descriptor_manifest, parent_manifest, spec, vectors, centers, ids):
    plan = read_json(payload(plan_manifest,"plan.json"))
    require(spec in plan["blocks"] and plan["scope"] == ctx["scope"], "ALIGNMENT_BLOCK_PLAN")
    def build(stage):
        arrays = descriptor_arrays(descriptor_manifest,ids,ctx["scope"])
        records,bands = alignment_block(vectors,centers,ids,spec["positions"],arrays)
        validate_metrics(records,ids,spec["positions"],list(arrays))
        table=pa.Table.from_pylist(records,schema=METRIC_SCHEMA)
        pq.write_table(table,stage/"metrics.parquet",compression="zstd")
        pq.write_table(pa.Table.from_pylist(bands),stage/"bands.parquet",compression="zstd")
        require(pq.read_table(stage/"metrics.parquet").to_pylist()==records and
                pq.read_table(stage/"bands.parquet").to_pylist()==bands,"ALIGNMENT_READBACK")
        return {"positions":spec["positions"],"metric_rows":len(records),"band_rows":len(bands),
            "unsampled_descriptors": "pilot only: not observed; never scientific missingness" if ctx["scope"]=="pilot" else None}
    return publish(ctx,"alignment_blocks",spec["block_id"],build,[plan_manifest,descriptor_manifest,parent_manifest])

def summarize_alignment(ctx, plan_manifest, blocks, ids):
    plan=read_json(payload(plan_manifest,"plan.json"))
    expected=[q for b in plan["blocks"] for q in b["positions"]]
    actual=[q for m in blocks for q in load_bundle(m,"alignment_blocks")["metadata"]["positions"]]
    require(sorted(actual)==expected and len(set(actual))==len(actual),"SUMMARY_BLOCK_COVERAGE")
    def build(stage):
        # <2m narrow rows, not an N*N payload. Arrow group filtering bounds Python
        # materialization to one descriptor/mode/region (9000 records) at a time.
        table=pa.concat_tables([pq.read_table(payload(m,"metrics.parquet")) for m in blocks])
        import pyarrow.compute as pc
        summaries=[]
        for descriptor in [d["id"] for d in configuration()[0]["descriptors"]]:
            for mode in ("standard","nonlocal"):
                for region in ("rho","rank1","upper","middle","lower"):
                    part=table.filter(pc.and_(pc.and_(pc.equal(table["descriptor"],descriptor),pc.equal(table["mode"],mode)),pc.equal(table["region"],region)))
                    require(sorted(part["query_index"].to_pylist())==expected,"SUMMARY_QUERY_COVERAGE")
                    summary=query_summary(part["value"].to_pylist())
                    summaries.append({"descriptor":descriptor,"mode":mode,"region":region,
                        **{"query_"+k:v for k,v in summary.items()},
                        **{"candidate_"+k:int(pc.sum(part[k]).as_py()) for k in ("total_count","valid_count","invalid_count")}})
        pq.write_table(table,stage/"query_metrics.parquet",compression="zstd")
        pq.write_table(pa.Table.from_pylist(summaries),stage/"summary.parquet",compression="zstd")
        write_json(stage/"summary.json",summaries)
        require(pq.read_table(stage/"summary.parquet").to_pylist()==summaries,"SUMMARY_READBACK")
        return {"query_count":len(expected),"metric_rows":table.num_rows,"summary_rows":len(summaries),"quantiles":"linear/type7"}
    return publish(ctx,"alignment_summaries","summaries",build,[plan_manifest,*blocks])
