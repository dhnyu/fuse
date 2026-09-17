#!/usr/bin/env python3
"""Serve the accepted S10 viewer on its sole permitted localhost port."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.request import urlopen

ROOT = Path('/mnt/hdd002/dhnyu/fusedata/retrieval_data/reduced/s10_viewers/viewer_eb2cd9af73816e89b1390ded')
BASE_URL = 'http://127.0.0.1:8765'
ACCESS_URL = BASE_URL + '/?model=main&mode=standard'
ACCEPTANCE = 's10_acceptance_e41bb7c33d2ae4171a1f2c59'
LAST_QUERY = 'scn_8d90cc0a32f275618d6927a1'


def command_root(args):
    """Recognize only the explicit Python http.server invocation we support."""
    if not args or not Path(args[0]).name.startswith('python'):
        return None
    try:
        pos = args.index('-m')
        if args[pos + 1:pos + 3] != ['http.server', '8765']:
            return None
        if args[args.index('--bind') + 1] != '127.0.0.1':
            return None
        return Path(args[args.index('--directory') + 1]).resolve()
    except (ValueError, IndexError):
        return None


def listener():
    output = subprocess.check_output(['ss', '-H', '-ltnp', 'sport = :8765'], text=True)
    if not output.strip():
        return None
    pids = set(re.findall(r'pid=(\d+)', output))
    if len(pids) != 1 or len(output.strip().splitlines()) != 1:
        raise RuntimeError('BLOCKED: ambiguous/unknown 8765 listener; inspect ss -ltnp. No fallback port.')
    pid = int(pids.pop())
    proc = Path('/proc') / str(pid)
    args = proc.joinpath('cmdline').read_bytes().decode().rstrip('\0').split('\0')
    root = command_root(args)
    if root != ROOT:
        kind = 'old S10 viewer' if root and root.parent == ROOT.parent and root.name.startswith('viewer_') else 'unrelated or unverified process'
        raise RuntimeError(f'BLOCKED: 8765 PID {pid} is {kind}: {args}. Inspect and explicitly stop it before retrying; this helper never kills a PID.')
    return {'pid': pid, 'cmdline': args, 'cwd': str(proc.joinpath('cwd').resolve()), 'root': str(root), 'listener': output.strip()}


def verify_http():
    info = listener()
    if info is None:
        raise RuntimeError('BLOCKED: start scripts/serve_s10_viewer.py first; 8765 has no listener.')
    with urlopen(BASE_URL + '/config.json', timeout=10) as response:
        body = response.read()
    expected = ROOT.joinpath('config.json').read_bytes()
    if body != expected:
        raise RuntimeError('HTTP config differs from production bytes')
    cfg = json.loads(body)
    if len(cfg['queries']) != 100 or len(cfg['models']) != 28 or cfg['acceptance'] != ACCEPTANCE or cfg['queries'][-1]['scene_id'] != LAST_QUERY:
        raise RuntimeError('Unexpected production config binding')
    return {**info, 'url': ACCESS_URL, 'http_query_count': len(cfg['queries']), 'models': len(cfg['models']), 'acceptance': cfg['acceptance'], 'last_query': LAST_QUERY, 'filesystem_config_sha256': hashlib.sha256(expected).hexdigest(), 'http_config_sha256': hashlib.sha256(body).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Verify the existing 8765 listener and HTTP config only')
    args = parser.parse_args()
    try:
        if args.check or listener() is not None:
            print(json.dumps(verify_http(), indent=2))
            return
        if not ROOT.joinpath('viewer_receipt.json').is_file():
            raise RuntimeError('Missing production viewer receipt')
        print(f'Serving {ROOT} at {ACCESS_URL}; Ctrl+C stops this foreground server.', flush=True)
        os.execv(sys.executable, [sys.executable, '-u', '-m', 'http.server', '8765', '--bind', '127.0.0.1', '--directory', str(ROOT)])
    except (RuntimeError, OSError) as exc:
        parser.exit(1, f'{exc}\n')


if __name__ == '__main__':
    main()
