#!/usr/bin/env python3
"""Switch Hub navigation to the validated NONEMPTY viewer, without a restart."""
import json
import os
from pathlib import Path
import tempfile
from serve_viewer_hub import ROOT,TARGETS,verify_root,sha


def atomic(path,raw):
    fd,tmp=tempfile.mkstemp(prefix='.hub_update_',dir=ROOT)
    with os.fdopen(fd,'wb') as stream:stream.write(raw)
    os.replace(tmp,path)


def main():
    receipt=json.loads((ROOT/'hub_receipt.json').read_text())
    old=ROOT.parent/'s10_extreme_viewers/viewer_49689e157402015da2e68b52'
    new=TARGETS['extreme']
    if (ROOT/'extreme').resolve()==new:
        verify_root();print('NONEMPTY Hub already verified');return
    if (ROOT/'extreme').resolve()!=old:raise RuntimeError('Unexpected Hub target; refusing update')
    for file,h in receipt['files'].items():
        if sha(ROOT/file)!=h:raise RuntimeError('Hub source hash mismatch')
    for name,meta in receipt['targets'].items():
        for file in ('config.json','viewer_receipt.json'):
            if sha(Path(meta['path'])/file)!=meta[file]:raise RuntimeError('Existing viewer identity mismatch')
    rc=json.loads((new/'viewer_receipt.json').read_text())
    if rc['status']!='PASS':raise RuntimeError('Unvalidated new viewer')
    archive=ROOT.parent/'viewer_hub_history'/sha(ROOT/'hub_receipt.json')
    archive.mkdir(parents=True,exist_ok=False)
    for file in ('hub_receipt.json','index.html','style.css'):
        (archive/file).write_bytes((ROOT/file).read_bytes())
    source=Path(__file__).resolve().parents[1]/'tools/retrieval_inspector/hub/index.html'
    receipt['targets']['extreme']={'path':str(new),**{f:sha(new/f) for f in ('config.json','viewer_receipt.json')}}
    receipt['files']['index.html']=sha(source)
    link=ROOT/'.extreme_nonempty_pending'
    link.symlink_to(os.path.relpath(new,ROOT),target_is_directory=True)
    os.replace(link,ROOT/'extreme')
    atomic(ROOT/'index.html',source.read_bytes())
    atomic(ROOT/'hub_receipt.json',(json.dumps(receipt,indent=2)+'\n').encode())
    verify_root();print('NONEMPTY Hub published; prior navigation archived:',archive)

if __name__=='__main__':main()
