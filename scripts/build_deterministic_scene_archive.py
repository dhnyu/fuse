#!/usr/bin/env python3
"""Write or validate a deterministic POSIX tar without altering source files."""
import argparse, hashlib, json, os, pathlib, tarfile

def sha(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for chunk in iter(lambda:f.read(8*1024*1024),b""): h.update(chunk)
    return h.hexdigest()

def inputs(spec):
    rows=[]
    for group in spec["source_groups"]:
        root=pathlib.Path(group["root"])
        members=group["members"] if isinstance(group["members"],list) else [group["members"]]
        for rel in members:
            p=root/rel
            if p.is_dir():
                for q in sorted((x for x in p.rglob("*") if x.is_file()),key=lambda x:x.relative_to(root).as_posix()):
                    rows.append((group["prefix"]+"/"+q.relative_to(root).as_posix(),q))
            else: rows.append((group["prefix"]+"/"+rel,p))
    rows.sort(key=lambda x:x[0])
    if len({x[0] for x in rows}) != len(rows): raise RuntimeError("duplicate tar member")
    return rows

def write(spec,out):
    rows=inputs(spec); tmp=out+".tmp"
    os.makedirs(os.path.dirname(out),exist_ok=True)
    with tarfile.open(tmp,"w",format=tarfile.PAX_FORMAT) as tf:
        for name,path in rows:
            st=path.stat(); info=tarfile.TarInfo(name); info.size=st.st_size
            info.mode=0o644; info.mtime=0; info.uid=info.gid=0; info.uname=info.gname=""
            with open(path,"rb") as f: tf.addfile(info,f)
    os.replace(tmp,out)
    members=[{"path":n,"size_bytes":p.stat().st_size,"sha256":sha(p)} for n,p in rows]
    return members

def validate(tar_path, expected):
    with tarfile.open(tar_path,"r") as tf:
        got=[]
        for m in tf:
            if not m.isfile(): continue
            h=hashlib.sha256(); f=tf.extractfile(m)
            for chunk in iter(lambda:f.read(8*1024*1024),b""): h.update(chunk)
            got.append({"path":m.name,"size_bytes":m.size,"sha256":h.hexdigest()})
    if got != expected: raise RuntimeError("tar member round-trip mismatch")

def main():
    p=argparse.ArgumentParser(); p.add_argument("--spec",required=True); p.add_argument("--output",required=True); p.add_argument("--manifest",required=True)
    a=p.parse_args(); spec=json.load(open(a.spec)); members=write(spec,a.output); validate(a.output,members)
    json.dump({"members":members,"payload":{"filename":os.path.basename(a.output),"size_bytes":os.path.getsize(a.output),"sha256":sha(a.output)}},open(a.manifest,"w"),sort_keys=True,separators=(",",":"))
if __name__=="__main__": main()
