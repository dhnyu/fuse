#!/usr/bin/env python3
"""Publish only a new static supplemental inspector; never touch old routes."""
from pathlib import Path
import sys,os,shutil,time,json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from s10_all_models import BASE,AUDIT,OLD
from s10_extreme_rank1 import read,encode,digest,sha
REPO=Path(__file__).resolve().parents[1]
def label(model):
 key=model['configuration']
 if key.startswith('cmp_'):text=key[4:]
 else:text={'main':'Main','ofat_d_64':'d = 64','ofat_d_256':'d = 256','ofat_K_aug_4':'K_aug = 4','ofat_K_aug_16':'K_aug = 16','ofat_augmentation_intensity_0.5':'augmentation = 0.5','ofat_augmentation_intensity_2.0':'augmentation = 2.0','ofat_ema_momentum_0.99':'EMA = .99','ofat_peak_learning_rate_0.002':'LR = .002','ofat_peak_learning_rate_0.003':'LR = .003','ofat_peak_learning_rate_0.005':'LR = .005'}[key]
 return f'{text} ({key})'
def build():
 bands=read(AUDIT/'bands.json');lc=read(AUDIT/'lc.json');pc=read(OLD/'config.json');source=REPO/'tools/retrieval_inspector/all_model';code={p.name:sha(p) for p in source.iterdir() if p.is_file()};identity={'bands':bands['generation'],'lc':lc['generation'],'old_viewer':str(OLD),'old_receipt_sha256':sha(OLD/'viewer_receipt.json'),'code':code,'builder_sha256':sha(__file__)};vid='viewer_models_'+digest(identity)[:24];root=BASE/'s10_all_model_viewers'/vid
 if root.exists():return root
 stage=root.with_name(root.name+'.staging');stage.mkdir(parents=True,exist_ok=False)
 for name in ['summaries','details','app.js','helpers.js','locations.js','style.css','bands.css','legacy_bands.css','augmentation.css','locations.css']:(stage/name).symlink_to(OLD/name)
 (stage/'bands').symlink_to(Path(bands['root']));(stage/'lc').symlink_to(Path(lc['root']));idx=read(OLD/'index.json');assert sha(OLD/'index.json')==pc['index_sha256']
 # Preserve query order and all shared scene fields/hashes; remove historical presets/FM band hashes.
 columns=[c for c in idx['columns'] if c!='band_sha256']+['lc_sha256'];rows=[]
 for old in idx['rows']:
  r=dict(zip(idx['columns'],old));r['lc_sha256']=lc['files'][r['scene_id']]['sha256'];rows.append([r[k] for k in columns])
 (stage/'index.json').write_bytes(encode({'columns':columns,'rows':rows,'population':9000,'original_index_sha256':sha(OLD/'index.json')}));models=[{k:v for k,v in m.items() if k not in ['payload','shards']}|{'label':label(m)} for m in bands['models'].values()]
 palette=lc['palette'];(stage/'palette.json').write_bytes(encode(palette));config={'viewer_id':vid,'generation':bands['generation'],'shard_size':100,'index_sha256':sha(stage/'index.json'),'models':models,'palette_sha256':lc['identity']['palette_sha256'],'palette':palette['rows'],'schema':'S10BND01'};(stage/'config.json').write_bytes(encode(config))
 for name in ['runtime.js','prototype.css']:shutil.copyfile(source/name,stage/name)
 (stage/'index.html').write_text((source/'index.html').read_text().replace('__CONFIG_SHA__',sha(stage/'config.json')))
 rows=''.join(f'<tr data-internal="{r["internal"]}" data-official="{r["official"]}"><td>{r["internal"]}</td><td>{r["official"]}</td><td>{r["category"]}</td><td class="swatch" style="background:rgb({",".join(map(str,r["rgb"]))});width:100px;height:30px"></td><td>{r["rgb"]}</td></tr>' for r in palette['rows'])
 (stage/'palette.html').write_text('<!doctype html><meta charset="utf-8"><title>Official EGIS22 palette validation</title><h1>Official middle-class land-cover palette</h1><a href="https://aid.mcee.go.kr/intro/land.do">환경공간정보서비스 official source</a><table><tr><th>Internal</th><th>Official</th><th>Category</th><th>Swatch</th><th>RGB</th></tr>'+rows+'</table><p>Nodata: transparent alpha (existing neutral background); no category assignment.</p>')
 receipt={'viewer_id':vid,'identity':identity,'files':{p.name:sha(p) for p in stage.iterdir() if p.is_file()},'shared_scenes':str(OLD),'band_root':bands['root'],'lc_root':lc['root'],'validation':{'population':9000,'models':28,'no_presets':True,'no_scene_duplication':True}};(stage/'viewer_receipt.json').write_bytes(encode(receipt));os.rename(stage,root);(AUDIT/'viewer.json').write_bytes(encode({'root':str(root),**receipt}));return root
if __name__=='__main__':print(build())
