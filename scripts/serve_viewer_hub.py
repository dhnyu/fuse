#!/usr/bin/env python3
"""Serve/check the immutable-viewer Hub on localhost:8765; never stop a process."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from urllib.request import urlopen

from serve_s10_viewer import command_root
import subprocess

BASE = Path('/mnt/hdd002/dhnyu/fusedata/retrieval_data/reduced')
ROOT = BASE / 'viewer_hub'
TARGETS = {
    'canonical': BASE / 's10_viewers/viewer_eb2cd9af73816e89b1390ded',
    'extreme': BASE / 's10_extreme_viewers/viewer_2ae08c126d6d54d8c953befe',
}
URL = 'http://127.0.0.1:8765'


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def verify_root():
    receipt = json.loads((ROOT / 'hub_receipt.json').read_text())
    for name, target in TARGETS.items():
        link = ROOT / name
        if not link.is_symlink() or link.resolve() != target:
            raise RuntimeError(f'Invalid Hub symlink: {link}')
        for file in ('config.json', 'viewer_receipt.json'):
            if sha(target / file) != receipt['targets'][name][file]:
                raise RuntimeError(f'Viewer identity changed: {name}/{file}')
    for file, checksum in receipt['files'].items():
        if sha(ROOT / file) != checksum:
            raise RuntimeError(f'Hub file changed: {file}')
    canonical = json.loads((ROOT / 'canonical/config.json').read_text())
    extreme = json.loads((ROOT / 'extreme/config.json').read_text())
    if len(canonical['queries']) != 100 or len(canonical['models']) != 28 or not any(m['id']=='cmp_FM' for m in canonical['models']):
        raise RuntimeError('Canonical contract mismatch')
    if set(extreme['sets']) != {'STANDARD_HIGH','STANDARD_LOW','NONLOCAL_HIGH','NONLOCAL_LOW','STANDARD_HIGH_NONEMPTY','NONLOCAL_HIGH_NONEMPTY','STANDARD_HIGH_OBJ20','NONLOCAL_HIGH_OBJ20'} or any(len(s)!=100 for s in extreme['sets'].values()) or extreme['models'] != [{'group':'COMPARISON','id':'cmp_FM'}]:
        raise RuntimeError('Extreme contract mismatch')
    return receipt


def listener():
    output = subprocess.check_output(['ss','-H','-ltnp','sport = :8765'],text=True).strip()
    if not output:
        return None
    pids = set(re.findall(r'pid=(\d+)',output))
    if len(pids)!=1 or len(output.splitlines())!=1:
        raise RuntimeError('BLOCKED: ambiguous 8765 listener; no process stopped or fallback port.')
    pid=int(pids.pop())
    args=Path(f'/proc/{pid}/cmdline').read_bytes().decode().rstrip('\0').split('\0')
    if command_root(args)!=ROOT:
        raise RuntimeError(f'BLOCKED: remote 8765 occupied by PID {pid}, command {args}. Stop that service manually before starting Hub. No process was stopped.')
    return {'pid':pid,'command':args,'root':str(ROOT)}


def check():
    verify_root()
    current=listener()
    if current is None:
        raise RuntimeError('BLOCKED: Hub is built but no server is listening on 8765.')
    for route in ('index.html','style.css','canonical/config.json','extreme/config.json'):
        with urlopen(URL+'/'+route,timeout=15) as response:
            if response.read()!=(ROOT/route).read_bytes():
                raise RuntimeError(f'HTTP/root mismatch: {route}')
    return dict(status='PASS',url=URL+'/',**current)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    try:
        verify_root()
        if args.check or listener() is not None:
            print(json.dumps(check(),indent=2));return
        print(f'Serving {ROOT} at {URL}/',flush=True)
        os.execv(sys.executable,[sys.executable,'-u','-m','http.server','8765','--bind','127.0.0.1','--directory',str(ROOT)])
    except (OSError,ValueError,KeyError,RuntimeError) as exc:
        parser.exit(1,f'{exc}\n')


if __name__=='__main__':
    main()
