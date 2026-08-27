#!/usr/bin/env python3
"""Independent reader for Serialization-v3 tar shards."""
import argparse, hashlib, json, tarfile

def main():
    p=argparse.ArgumentParser(); p.add_argument('--payload',required=True); p.add_argument('--manifest',required=True); p.add_argument('--output',required=True); a=p.parse_args()
    manifest=json.load(open(a.manifest)); observed=[]
    with tarfile.open(a.payload,'r') as tf:
        for m in tf:
            if not m.isfile(): continue
            h=hashlib.sha256(); f=tf.extractfile(m)
            for block in iter(lambda:f.read(8*1024*1024),b''): h.update(block)
            observed.append({'path':m.name,'size_bytes':m.size,'sha256':h.hexdigest()})
    if observed != manifest['members']: raise SystemExit('member checksum/order mismatch')
    required=('scene/','membership/','vector/','raster/','relations/','topology/')
    names=[x['path'] for x in observed]
    if any(not any(n.startswith(prefix) for n in names) for prefix in required): raise SystemExit('required payload group missing')
    json.dump({'status':'PASS','member_count':len(observed),'byte_parity':True},open(a.output,'w'),sort_keys=True,separators=(',',':'))
if __name__=='__main__': main()
