#!/usr/bin/env python3
"""Publish a new immutable display bundle; reuse all scientific bytes by symlink."""
import hashlib,json,os
from pathlib import Path
BASE=Path('/mnt/hdd002/dhnyu/fusedata/retrieval_data/reduced')
PARENTS={'canonical':BASE/'s10_viewers/viewer_eb2cd9af73816e89b1390ded','extreme':BASE/'s10_extreme_viewers/viewer_2ae08c126d6d54d8c953befe'}

def build():
 runtime=(Path(__file__).resolve().parents[1]/'tools/retrieval_inspector/performance/runtime.js').read_text()
 output={};identity={}
 for name,parent in PARENTS.items():
  app=(parent/'app.js').read_text().replace('return JSON.parse(new TextDecoder().decode(bytes));','if(window.S10Perf)S10Perf.sizes.set(path,bytes.byteLength);\n  return JSON.parse(new TextDecoder().decode(bytes));')
  bands=(parent/'bands_app.js').read_text();entry='initExtreme().catch(bandFail);' if name=='extreme' else 'initBands().catch(bandFail);'
  assert bands.count(entry)==1
  # Suppress the old render declaration to avoid confusing duplicate functions.
  a=bands.index('async function renderBandColumns(token){');b=bands.index('\n}',a)+2
  bands=bands[:a]+bands[b:];bands=bands.replace('await renderBandColumns(token);\n const url', 'await renderBandColumns(token);if(token!==serial)return;\n const url');bands=bands.replace(entry,runtime+'\n'+entry)
  output[name]={'app.js':app,'bands_app.js':bands}
  identity[name]={'parent':str(parent),'config_sha256':hashlib.sha256((parent/'config.json').read_bytes()).hexdigest(),'code':{k:hashlib.sha256(v.encode()).hexdigest() for k,v in output[name].items()}}
 ident='viewer_perf_'+hashlib.sha256(json.dumps({'schema':1,'parents':identity},sort_keys=True).encode()).hexdigest()[:24]
 root=BASE/'viewer_performance'/ident
 if root.exists():return root
 stage=root.with_name(ident+'.staging');stage.mkdir(parents=True,exist_ok=False)
 for name,parent in PARENTS.items():
  child=stage/name;child.mkdir()
  for item in parent.iterdir():
   if item.name in output[name]:(child/item.name).write_text(output[name][item.name])
   elif item.suffix=='.html':
    html=item.read_text()
    for asset,source in output[name].items():html=html.replace('src="'+asset+'"','src="'+asset+'?v='+hashlib.sha256(source.encode()).hexdigest()[:16]+'"')
    (child/item.name).write_text(html)
   else:(child/item.name).symlink_to(item.resolve())
 # Pilot Hub uses the identical launcher and route names.
 for item in (BASE/'viewer_hub').iterdir():
  if item.is_file():(stage/item.name).symlink_to(item.resolve())
 (stage/'performance_receipt.json').write_text(json.dumps({'id':ident,'parents':identity,'scientific_mutation':False},indent=2))
 os.rename(stage,root);return root
if __name__=='__main__':print(build())
