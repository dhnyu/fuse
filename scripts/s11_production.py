#!/usr/bin/env python
"""Single-stage S11 CLI for the isolated targets graph; full execution gated."""
from __future__ import annotations
import os
for name in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","NUMBA_NUM_THREADS","VECLIB_MAXIMUM_THREADS","NUMEXPR_NUM_THREADS"):
    os.environ[name]="1"
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"python"))
from s11_artifacts import context,payload,read_json
from s11_descriptors import make_plan,extract_shard,merge_descriptors,reader_threads
from s11_alignment import make_alignment_plan,build_alignment_block,summarize_alignment
from s11_umap import build_umap
from s11_production import accepted_parents,read_population,figures_tables,scientific_acceptance

def main():
    reader_threads()
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage",choices=["parents","descriptor_plan","descriptor_shard","descriptor_acceptance","umap",
        "alignment_plan","alignment_block","summaries","publication","acceptance","pilot_umap"])
    parser.add_argument("--request",required=True)
    args=parser.parse_args();r=read_json(args.request)
    if args.stage=="pilot_umap":
        ctx=context("pilot",r["pilot_root"])
        x,centers,ids=read_population(r["parent"])
        q=r["positions"]
        output=build_umap(ctx,r["parent"],x[q].copy(),[ids[i] for i in q])
    else:
        ctx=context("full")
        if args.stage=="parents":
            output=accepted_parents(ctx)
        elif args.stage=="descriptor_shard":
            output=extract_shard(ctx,r["plan"],r["spec"])
        elif args.stage=="descriptor_acceptance":
            output=merge_descriptors(ctx,r["plan"],r["shards"])
        elif args.stage=="publication":
            output=figures_tables(ctx,r["descriptors"],r["umap"],r["summaries"])
        elif args.stage=="acceptance":
            output=scientific_acceptance(ctx,r["parent"],r["descriptors"],r["umap"],r["plan"],r["blocks"],r["summaries"],r["publication"])
        else:
            x,centers,ids=read_population(r["parent"])
            if args.stage=="descriptor_plan":
                output=make_plan(ctx,ids,ids,[r["parent"]])
            elif args.stage=="umap":
                output=build_umap(ctx,r["parent"],x,ids)
            elif args.stage=="alignment_plan":
                output=make_alignment_plan(ctx,r["descriptors"],r["parent"],ids,range(9000))
            elif args.stage=="alignment_block":
                output=build_alignment_block(ctx,r["plan"],r["descriptors"],r["parent"],r["spec"],x,centers,ids)
            elif args.stage=="summaries":
                output=summarize_alignment(ctx,r["plan"],r["blocks"],ids)
    print(json.dumps({"manifest":output}))

if __name__=="__main__":
    main()
