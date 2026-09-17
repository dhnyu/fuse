#!/usr/bin/env python3
"""CPU-only entrypoint for the independent 100-query targets graph."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from s10_query_revision import audit,generation,output_paths
p=argparse.ArgumentParser();p.add_argument('stage',choices=['audit','generation','viewer']);p.add_argument('--config',required=True);p.add_argument('--input')
a=p.parse_args()
if a.stage=='viewer':
    from s10_query_viewer import build
    result=build(a.config,a.input)
else:
    result=output_paths(audit(a.config) if a.stage=='audit' else generation(a.config,a.input))
    if a.stage=='generation':
        from retrieval_artifacts import load
        for path in load(result[0])['body']['artifacts']:
            result.extend(output_paths(path))
print(json.dumps(sorted(set(result))))
