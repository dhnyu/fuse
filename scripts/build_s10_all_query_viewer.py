#!/usr/bin/env python3
"""Build a supplemental display generation; never write accepted input files."""
import sys,os,json,time,gzip,hashlib,shutil
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from s10_extreme_rank1 import read,sha,encode,digest,envelope,require
from s10_all_query import BASE,AUDIT
REPO=Path(__file__).resolve().parents[1]

def build():
 cfg=read(REPO/'config/s10_extreme_rank1.json');result=read(AUDIT/'band_result.json');band=Path(result['root']);parent=Path(cfg['accepted_viewer']);fallback=Path(cfg['display_fallback']);extreme=BASE/'s10_extreme_viewers/viewer_2ae08c126d6d54d8c953befe'
 gallery=envelope(Path(cfg['original_generation'])/'gallery_manifest.json')['body']['rows'];counts=envelope(Path(cfg['query_revision'])/'object_counts_manifest.json')['body']['counts'];location=read(parent/'location_metadata.json');pc=read(parent/'config.json');assert sha(parent/'location_metadata.json')==pc['files']['location_metadata.json']
 source_receipts={str(p):read(p/'viewer_receipt.json') for p in [parent,fallback]};originals=envelope(Path(cfg['original_generation'])/'original_inputs/manifest.json');original_hashes={Path(f['path']).stem:f['sha256'] for f in originals['files']};ec=read(extreme/'config.json');er=read(extreme/'viewer_receipt.json')
 assert er['status']=='PASS' and sha(extreme/'config.json')==er['files']['config.json']
 preset_manifests={}
 for name in ['STANDARD_HIGH_OBJ20','STANDARD_LOW','NONLOCAL_HIGH_OBJ20','NONLOCAL_LOW']:
  path=Path(er['display_parent'] if name.endswith('OBJ20') else er['scientific_parent'])/'sets'/f'{name}.json';doc=read(path);rows=doc['body']['rows'];assert [r['query_scene_id'] for r in rows]==[r['scene_id'] for r in ec['sets'][name]]
  preset_manifests[name]={'path':str(path),'sha256':sha(path),'manifest_id':doc.get('manifest_id'), 'query_ids':[r['query_scene_id'] for r in rows]}
 source=REPO/'tools/retrieval_inspector/all_query';code={p.name:sha(p) for p in source.iterdir() if p.is_file()};identity={'band':result['generation_id'],'code':code,'builder':sha(__file__),'scene_parents':{str(p):sha(p/'viewer_receipt.json') for p in [parent,fallback]},'presets_config':sha(extreme/'config.json')};vid='viewer_all_'+digest(identity)[:24];root=BASE/'s10_all_query_viewers'/vid
 if root.exists():return root
 stage=root.with_name(root.name+'.staging');stage.mkdir(parents=True,exist_ok=False)
 for d in ['summaries','details']:(stage/d).mkdir()
 (stage/'bands').symlink_to(band/'queries');index=[];sources=[];stats={'original_raw':0,'summary_raw':0,'summary_gzip3':0,'detail_raw':0,'detail_gzip3':0};started=time.perf_counter()
 summary_keys=['scene_id','center','counts','ordered_edges','relation_masks','svg']
 for i,row in enumerate(gallery):
  sid=row['scene_id'];relative=f'scenes/{sid}.json';src=parent/relative
  if not src.is_file():src=fallback/relative
  source_root=src.parent.parent;data=src.read_bytes();h=hashlib.sha256(data).hexdigest();assert h==source_receipts[str(source_root)]['files'][relative]
  s=json.loads(data);assert s['scene_id']==sid and s['center']==[row['center_x'],row['center_y']] and s['thematic']['binding']['original_input_sha256']==original_hashes[sid]
  count=counts[sid];assert s['counts']=={'building':count['n_buildings'],'road':count['n_roads'],'poi':count['n_pois']}
  loc=location['scenes'][sid];assert loc['center_x']==row['center_x'] and loc['center_y']==row['center_y']
  summary={k:s[k] for k in summary_keys};detail={k:v for k,v in s.items() if k not in summary_keys};assert {**summary,**detail}==s
  summary.update(location=loc,source_sha256=h);detail.update(scene_id=sid,source_sha256=h)
  sh,dh=encode(summary),encode(detail);(stage/'summaries'/f'{sid}.json').write_bytes(sh);(stage/'details'/f'{sid}.json').write_bytes(dh)
  index.append([i+1,sid,row['center_x'],row['center_y'],loc['longitude'],loc['latitude'],loc['sigungu_name'],loc['eupmyeondong_name'],count['n_buildings'],count['n_roads'],count['n_pois'],count['object_count'],hashlib.sha256(sh).hexdigest(),hashlib.sha256(dh).hexdigest(),result['query_hashes'][str(i+1)]])
  sources.append({'scene_id':sid,'path':str(src),'sha256':h});stats['original_raw']+=len(data);stats['summary_raw']+=len(sh);stats['detail_raw']+=len(dh);stats['summary_gzip3']+=len(gzip.compress(sh,compresslevel=3,mtime=0));stats['detail_gzip3']+=len(gzip.compress(dh,compresslevel=3,mtime=0))
 # Membership is read from current immutable OBJ20 viewer, never recomputed.
 ids={r[1]:r[0] for r in index};preset_names=['STANDARD_HIGH_OBJ20','STANDARD_LOW','NONLOCAL_HIGH_OBJ20','NONLOCAL_LOW'];presets={n:[ids[r['scene_id']] for r in ec['sets'][n]] for n in preset_names};assert all(len(v)==len(set(v))==100 for v in presets.values())
 catalog={'columns':['query_index','scene_id','center_x','center_y','longitude','latitude','sigungu','dong','n_buildings','n_roads','n_pois','n_obj','summary_sha256','detail_sha256','band_sha256'],'rows':index,'presets':presets,'preset_sources':preset_manifests,'preset_config_sha256':sha(extreme/'config.json')};raw=encode(catalog);(stage/'index.json').write_bytes(raw);stats.update(index_raw=len(raw),index_gzip3=len(gzip.compress(raw,compresslevel=3,mtime=0)))
 for name in ['app.js','augmentation.css','style.css','legacy_bands.css','bands.css','locations.css']:(stage/name).symlink_to(parent/name)
 # Pure display helpers; no old init or scientific changes.
 old=(parent/'bands_app.js').read_text();(stage/'helpers.js').write_text(old[:old.index('async function renderBandColumns')])
 loc=(parent/'locations.js').read_text();loc=loc[loc.index(' function statusName'):loc.index(' async function init')];loc=loc.replace("metadata?.scenes[scene.scene_id]","scene.location");(stage/'locations.js').write_text("window.S10Locations=(()=>{\n"+loc+"\nreturn {block,statusName};})();")
 for name in ['runtime.js','prototype.css']:shutil.copyfile(source/name,stage/name)
 config={'viewer_id':vid,'generation':result['generation_id'],'configuration':'cmp_FM','checkpoint':result['checkpoint'],'embedding_manifest':result['embedding_manifest'],'index_sha256':sha(stage/'index.json'),'palette':pc['palette'],'models':[{'id':'cmp_FM','group':'COMPARISON'}],'parent_receipts':identity['scene_parents'],'files':{}}
 (stage/'config.json').write_bytes(encode(config));html=(source/'index.html').read_text().replace('__CONFIG_SHA__',sha(stage/'config.json'));(stage/'index.html').write_text(html)
 receipt={'viewer_id':vid,'identity':identity,'band_root':str(band),'sources':sources,'storage':stats,'build_seconds':time.perf_counter()-started,'validation':{'all_9000_reconstructed_dict_exact':True,'all_source_receipt_hashes':True,'all_original_inputs_and_centers':True,'counts_exact':True,'presets_exact':True},'files':{p.name:sha(p) for p in stage.iterdir() if p.is_file()}}
 (stage/'viewer_receipt.json').write_bytes(encode(receipt));os.rename(stage,root);(AUDIT/'viewer_result.json').write_bytes(encode({'root':str(root),**receipt}));return root
if __name__=='__main__':print(build())
