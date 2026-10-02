import gzip
import hashlib
import http.client
import importlib.util
from pathlib import Path
import tempfile
import threading
import unittest

spec=importlib.util.spec_from_file_location('fast',Path(__file__).parents[1]/'scripts/serve_viewer_hub_fast.py')
fast=importlib.util.module_from_spec(spec);spec.loader.exec_module(fast)

class ServerTests(unittest.TestCase):
 def test_contract(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);body=b'{"scene":"unchanged"}'*100
   (root/'index.html').write_bytes(body);(root/'binary.png').write_bytes(body)
   server=fast.StaticServer(('127.0.0.1',0),root);threading.Thread(target=server.serve_forever,daemon=True).start()
   try:
    c=http.client.HTTPConnection('127.0.0.1',server.server_port)
    c.request('GET','/',headers={'Accept-Encoding':'gzip'});r=c.getresponse();headers=dict(r.getheaders());raw=r.read();self.assertEqual(gzip.decompress(raw),body);self.assertEqual(int(headers['Content-Length']),len(raw));sock=c.sock
    c.request('HEAD','/',headers={'Accept-Encoding':'gzip'});r=c.getresponse();self.assertEqual(r.read(),b'');self.assertIs(sock,c.sock)
    for h in [{'If-None-Match':headers['ETag'],'Accept-Encoding':'gzip'},{'If-Modified-Since':headers['Last-Modified']}]:
     c.request('GET','/',headers=h);r=c.getresponse();self.assertEqual(r.status,304);self.assertEqual(r.read(),b'')
    for h in [{},{'Accept-Encoding':'gzip;q=0, *;q=1'}]:
     c.request('GET','/',headers=h);r=c.getresponse();self.assertIsNone(r.getheader('Content-Encoding'));self.assertEqual(r.read(),body)
    c.request('GET','/binary.png',headers={'Accept-Encoding':'gzip'});r=c.getresponse();self.assertIsNone(r.getheader('Content-Encoding'));r.read()
    for path in ['/../etc/passwd','/%2e%2e/etc/passwd','/unknown/','/missing']:
     c.request('GET',path);r=c.getresponse();self.assertIn(r.status,[403,404]);r.read()
    (root/'late-link').symlink_to('/etc/passwd');c.request('GET','/late-link');r=c.getresponse();self.assertEqual(r.status,404);r.read()
    (root/'index.html').write_bytes(b'new');c.request('GET','/');r=c.getresponse();self.assertEqual(r.read(),b'new')
    c.close()
   finally:server.shutdown();server.server_close()

if __name__=='__main__':unittest.main()
