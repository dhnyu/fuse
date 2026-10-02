#!/usr/bin/env python3
"""Publish a new immutable supplemental final-FM Rank1 diagnostic generation."""
import argparse
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from s10_extreme_rank1 import read,publish

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',default='config/s10_extreme_rank1.json')
    args=parser.parse_args()
    publish(read(args.config))
