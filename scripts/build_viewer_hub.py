#!/usr/bin/env python3
"""Publish only launcher files and symlinks; never modify viewer targets."""
import json
import os
from pathlib import Path
import shutil
import tempfile
from serve_viewer_hub import ROOT,TARGETS,sha,verify_root


def main():
    if ROOT.exists():
        verify_root();print('Existing Hub verified:',ROOT);return
    source=Path(__file__).resolve().parents[1]/'tools/retrieval_inspector/hub'
    for target in TARGETS.values():
        if not (target/'viewer_receipt.json').is_file():
            raise RuntimeError(f'Missing immutable viewer: {target}')
    stage=Path(tempfile.mkdtemp(prefix='.viewer_hub_staging_',dir=ROOT.parent))
    for name,target in TARGETS.items():
        (stage/name).symlink_to(os.path.relpath(target,ROOT),target_is_directory=True)
    for file in ('index.html','style.css'):
        shutil.copyfile(source/file,stage/file)
    receipt={'scope':'read-only navigation infrastructure','targets':{name:{'path':str(target),**{file:sha(target/file) for file in ('config.json','viewer_receipt.json')}} for name,target in TARGETS.items()},'files':{file:sha(stage/file) for file in ('index.html','style.css')}}
    (stage/'hub_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    os.rename(stage,ROOT)
    verify_root();print('Hub published:',ROOT)


if __name__=='__main__':
    main()
