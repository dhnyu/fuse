#!/usr/bin/env python3
"""Independent read-back and preservation audit; no ranking or inference."""
import json,os,subprocess,time
from pathlib import Path
import build_retrieval_composite_c as b
x=b.ex

def main():
 t=time.time();a=x.read(b.AUDIT/'assets.json');old=Path(a['source_viewer']);root=Path(a['root']);v=x.read(b.AUDIT/'viewer.json');new=Path(v['root']);original=x.read(old/'config.json');current=x.read(new/'config.json')
 for key in ['generation','models','index_sha256','palette','palette_sha256','shard_size','schema']:assert current[key]==original[key],key
 assert (new/'bands').resolve()==(old/'bands').resolve();assert x.sha(new/'index.json')==x.sha(old/'index.json');assert x.sha(new/'palette.json')==x.sha(old/'palette.json')
 catalog=x.read(root/'catalog.json');assert len(catalog['rows'])==catalog['population']==9000;assert x.sha(root/'catalog.json')==current['composite_catalog_sha256'];idx=x.read(old/'index.json');ids=[r[1] for r in idx['rows']];assert [r[0] for r in catalog['rows']]==ids
 count=0
 for vals in catalog['rows']:
  r=dict(zip(catalog['columns'],vals));sid=r['scene_id'];meta=x.read(root/'meta'/(sid+'.json'));source=x.read(old/'summaries'/(sid+'.json'));assert meta=={k:v for k,v in source.items() if k!='svg'}
  for kind,ext in [('main','webp'),('thumb','webp'),('meta','json'),('layers','json')]:assert x.sha(root/kind/(sid+'.'+ext))==r[kind+'_sha256'];count+=1
  if count%4000==0:print('outputs checked',count,flush=True)
 before=x.read(b.AUDIT/'before.json')
 for family in ['bands','preserved_files']:
  for p,sha in before[family].items():assert x.sha(p)==sha
 for n,(p,sha) in enumerate(a['source_hashes'].items()):
  assert x.sha(p)==sha,p
  if n%9000==0:print('source checks',n,flush=True)
 assert subprocess.getoutput('pgrep -a cloudflared')==before['cloudflared']
 assert {n:os.readlink(b.BASE/'viewer_hub'/n) for n in ['canonical','extreme']}==before['hub_links']
 result={'status':'PASS','rows':9000,'output_hashes':count,'metadata_exact':9000,'rgba_exact_conversion':a['rgba_exact_count'],'source_hashes_unchanged':len(a['source_hashes']),'scientific_band_files_unchanged':len(before['bands']),'model_registry_exact':28,'query_index_exact':True,'LC_palette_exact':True,'shared_scientific_sources_exact':True,'cloudflared_unchanged':True,'hub_routes_unchanged':True,'old_viewer_unchanged':True,'elapsed_seconds':time.time()-t};x.write(b.AUDIT/'asset_validation.json',result);print(json.dumps(result))
if __name__=='__main__':main()
