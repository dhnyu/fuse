#!/usr/bin/env python3
"""Loopback-only static viewer server. No scientific computation or file writes.

Only files enumerated beneath the supplied Hub at startup are exposed. Existing
viewer symlinks are explicit mounts; subsequent unlisted symlinks are not followed.
Production is fixed at 8765; --test-port explicitly opts into a loopback pilot.
"""
import argparse
from collections import OrderedDict
import email.utils
import gzip
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import threading
import subprocess
import re
import sys
from urllib.request import urlopen
from urllib.parse import unquote, urlsplit

ROOT = Path('/mnt/hdd002/dhnyu/fusedata/retrieval_data/reduced/viewer_hub')
TEXT = {'application/json', 'application/javascript', 'text/javascript',
        'text/html', 'text/css', 'image/svg+xml'}


class StaticServer(ThreadingHTTPServer):
    request_queue_size = 256
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, root):
        self.root = Path(root).resolve()
        self.files = {}
        for directory, _, names in os.walk(self.root, followlinks=True):
            for name in names:
                path = Path(directory) / name
                self.files[path.relative_to(self.root).as_posix()] = path.resolve(strict=True)
        self.cache = OrderedDict()
        self.cache_bytes = 0
        self.cache_limit = 128 * 1024 * 1024
        self.cache_lock = threading.Lock()
        super().__init__(address, Handler)

    def content(self, path, compressed):
        stat = path.stat()
        key = (str(path), stat.st_ino, stat.st_mtime_ns, stat.st_size, compressed)
        with self.cache_lock:
            if key in self.cache:
                self.cache.move_to_end(key)
                return self.cache[key]
        raw = path.read_bytes()
        data = gzip.compress(raw, compresslevel=3, mtime=0) if compressed else raw
        result = (data, '"' + hashlib.sha256(data).hexdigest() + '"', stat.st_mtime)
        with self.cache_lock:
            if key not in self.cache and len(data) <= self.cache_limit:
                self.cache[key] = result
                self.cache_bytes += len(data)
                while self.cache_bytes > self.cache_limit:
                    _, old = self.cache.popitem(last=False)
                    self.cache_bytes -= len(old[0])
        return result


def accepts_gzip(value):
    choices = {}
    for item in value.lower().split(','):
        parts = [x.strip() for x in item.split(';')]
        if not parts[0]:
            continue
        try:
            choices[parts[0]] = next((float(x[2:]) for x in parts[1:] if x.startswith('q=')), 1)
        except ValueError:
            choices[parts[0]] = 0
    return choices.get('gzip', choices.get('*', 0)) > 0


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    server_version = 'ViewerHubFast/1'

    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def do_HEAD(self):
        self.respond(head=True)

    def do_GET(self):
        self.respond()

    def respond(self, head=False):
        path = unquote(urlsplit(self.path).path)
        if '\\' in path or '\x00' in path or any(x in ('.', '..') for x in path.split('/')):
            self.send_error(403)
            return
        relative = path.lstrip('/')
        if not relative or relative.endswith('/'):
            relative += 'index.html'
        target = self.server.files.get(relative)
        if target is None:
            self.send_error(404)
            return
        mime = mimetypes.guess_type(relative)[0] or 'application/octet-stream'
        compressed = mime in TEXT and accepts_gzip(self.headers.get('Accept-Encoding', ''))
        try:
            data, etag, modified = self.server.content(target, compressed)
        except OSError:
            self.send_error(404)
            return
        unchanged = False
        inm = self.headers.get('If-None-Match')
        if inm is not None:
            unchanged = '*' in inm or etag in [v.strip().removeprefix('W/') for v in inm.split(',')]
        elif self.headers.get('If-Modified-Since'):
            try:
                unchanged = int(modified) <= int(email.utils.parsedate_to_datetime(self.headers['If-Modified-Since']).timestamp())
            except (TypeError, ValueError, OverflowError):
                pass
        self.send_response(304 if unchanged else 200)
        self.send_header('Content-Type', mime)
        self.send_header('Vary', 'Accept-Encoding')
        self.send_header('ETag', etag)
        self.send_header('Last-Modified', email.utils.formatdate(modified, usegmt=True))
        # Stable routes can point to new display generations: never mark immutable.
        self.send_header('Cache-Control', 'no-cache')
        if compressed:
            self.send_header('Content-Encoding', 'gzip')
        if not unchanged:
            self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        if not unchanged and not head:
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--test-port', type=int)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if not (args.root / 'index.html').is_file():
        parser.error('Hub index.html missing')
    port = args.test_port or 8765
    if args.check:
        output = subprocess.check_output(['ss', '-H', '-ltnp', f'sport = :{port}'], text=True)
        pids = set(re.findall(r'pid=(\d+)', output))
        if len(pids) != 1 or f'127.0.0.1:{port}' not in output or len(output.strip().splitlines()) != 1:
            parser.exit(1, 'Missing or ambiguous loopback listener\n')
        pid = int(pids.pop())
        command = Path(f'/proc/{pid}/cmdline').read_bytes().decode().strip('\0').split('\0')
        if str(Path(__file__).resolve()) not in command:
            parser.exit(1, f'Unrecognized listener PID {pid}; no action taken\n')
        running_root = Path(command[command.index('--root')+1]) if '--root' in command else ROOT
        if running_root.resolve() != args.root.resolve():
            parser.exit(1, 'Wrong root; no action taken\n')
        for route in ['index.html', 'canonical/config.json', 'extreme/config.json']:
            with urlopen(f'http://127.0.0.1:{port}/{route}', timeout=10) as response:
                if response.read() != (args.root/route).read_bytes():
                    parser.exit(1, 'HTTP identity mismatch\n')
        print(json.dumps({'status':'PASS', 'pid':pid, 'root':str(args.root), 'port':port}))
        return
    server = StaticServer(('127.0.0.1', port), args.root)
    print(json.dumps({'root': str(server.root), 'port': port, 'files': len(server.files), 'backlog': server.request_queue_size}), flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
