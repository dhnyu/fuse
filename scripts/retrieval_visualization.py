#!/usr/bin/env python3
"""S10 target worker; full inference is separately authorized by the operator."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
# Establish thread limits before importing scientific libraries.
for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[key] = os.environ.get("FUSE_S10_THREADS", "1")
os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
from retrieval_artifacts import output_paths
from retrieval_lineage import config, runtime
import retrieval_pipeline as pipeline


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("sources", "models", "gallery", "queries", "originals", "embeddings", "rankings", "renders", "pages", "summary", "acceptance"))
    parser.add_argument("--config", default="config/retrieval_visualization.yml")
    for name in ("models", "gallery", "queries", "model-id", "embedding", "render", "pages", "summary", "prepared"):
        parser.add_argument("--" + name)
    parser.add_argument("--rankings", nargs="+", default=[])
    args = parser.parse_args()
    if args.stage == "sources":
        print(json.dumps([str(ROOT / p) for p in runtime(config(args.config))["sources"]]))
        return
    if args.stage == "models": result = pipeline.model_manifest(config(args.config))
    elif args.stage == "gallery": result = pipeline.gallery_manifest(args.models)
    elif args.stage == "queries": result = pipeline.query_manifest(args.models, args.gallery)
    elif args.stage == "originals": result = pipeline.original_inputs(args.models,args.gallery,args.queries)
    elif args.stage == "embeddings": result = pipeline.embeddings(args.models,args.gallery,args.queries,args.model_id,args.prepared)
    elif args.stage == "rankings": result = pipeline.rankings(args.models,args.gallery,args.queries,args.embedding)
    elif args.stage == "renders": result = pipeline.render_cache(args.models,args.gallery,args.queries,args.rankings)
    elif args.stage == "pages": result = pipeline.comparison_pages(args.models,args.gallery,args.queries,args.rankings,args.render)
    elif args.stage == "summary": result = pipeline.summary(args.models,args.gallery,args.queries,args.rankings,args.pages)
    else: result = pipeline.acceptance(args.models,args.gallery,args.queries,args.rankings,args.pages,args.summary)
    print(json.dumps(output_paths(result)))


if __name__ == "__main__":
    main()
