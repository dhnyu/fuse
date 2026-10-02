#!/usr/bin/env python
"""Explicit verifier-only operator; never invokes targets or production stages."""
import os
for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMBA_NUM_THREADS','VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS'):
    os.environ[key]='1'
import argparse
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from s11_revalidation import revalidate

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('generation','pilot-receipt','output-root','fixture-receipt'):p.add_argument('--'+name,required=True)
    args=p.parse_args()
    path,receipt=revalidate(args.generation,args.pilot_receipt,args.output_root,args.fixture_receipt)
    print(receipt['status'],receipt['receipt_id'],path,flush=True)
    if receipt['status']!='PASS':
        print(receipt.get('failure'),file=sys.stderr)
        raise SystemExit(1)
