#!/usr/bin/env python3
"""Publish new Composite C viewer; immutable inputs and routes remain untouched."""
from pathlib import Path
import shutil,os
import build_retrieval_composite_c as a
ex=a.ex

def build():
 assets=ex.read(a.AUDIT/'assets.json');old=Path(assets['source_viewer']);root_asset=Path(assets['root']);cfg=ex.read(old/'config.json');source=Path(__file__).resolve().parents[1]/'tools/retrieval_inspector/composite_c'
 assert assets['population']==9000 and len(assets['visual_regression'])==18
 code={p.name:ex.sha(p) for p in source.iterdir() if p.is_file()};identity={'source_viewer':str(old),'source_receipt_sha256':ex.sha(old/'viewer_receipt.json'),'composite_generation':assets['generation_id'],'composite_manifest_sha256':ex.sha(root_asset/'manifest.json'),'code':code,'builder_sha256':ex.sha(__file__)}
 vid='viewer_composite_c_'+a.hashlib.sha256(ex.enc(identity)).hexdigest()[:24];root=a.BASE/'s10_all_model_viewers'/vid;assert not root.exists();stage=root.with_name('.staging_'+vid);stage.mkdir()
 for p in old.iterdir():
  if p.name not in ('runtime.js','index.html','prototype.css','viewer_receipt.json','config.json'):(stage/p.name).symlink_to(p)
 (stage/'composite').symlink_to(root_asset)
 cfg={**cfg,'viewer_id':vid,'composite_generation':assets['generation_id'],'composite_catalog_sha256':assets['catalog_sha256'],'display_variant':'C','composite_main_format':assets.get('main_format','png')};ex.write(stage/'config.json',cfg)
 for name in ('runtime.js','prototype.css'):shutil.copyfile(source/name,stage/name)
 (stage/'index.html').write_text((source/'index.html').read_text().replace('__CONFIG_SHA__',ex.sha(stage/'config.json')))
 receipt={'viewer_id':vid,'identity':identity,'files':{p.name:ex.sha(p) for p in stage.iterdir() if p.is_file()},'band_root':str((old/'bands').resolve()),'source_viewer':str(old),'composite_root':str(root_asset)};ex.write(stage/'viewer_receipt.json',receipt);stage.rename(root);ex.write(a.AUDIT/'viewer.json',{'root':str(root),**receipt});print(root)
if __name__=='__main__':build()
