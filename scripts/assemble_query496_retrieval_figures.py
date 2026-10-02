#!/usr/bin/env python3
"""Dissertation 5.3 qualitative figures: copy existing pixels and recorded ranks.
No embedding/model/ranking imports or inference; only metadata validation/layout.
"""
import argparse,csv,hashlib,json,math,shutil,subprocess
from pathlib import Path
BASE=Path('/mnt/hdd002/dhnyu/fusedata/retrieval_data/reduced')
S10=BASE/'s10/s10gen_a24b979d4c1557387cbbec35'
BANDS=BASE/'s10_all_query_bands/s10all_0d929355b8cad37b85860e2c'
VIEWER=BASE/'s10_all_query_viewers/viewer_all_57226fcbe9128cdd90b40f59'
ASSETS=BASE/'s10_composite_c/s10composite_c_eff9b2cd9b0af4dd6a0f97f5'
SID='scn_0dea54258b31af6c02290e8b'
DISTRICTS={'성북구':'Seongbuk-gu','용산구':'Yongsan-gu','동대문구':'Dongdaemun-gu','은평구':'Eunpyeong-gu','양천구':'Yangcheon-gu','송파구':'Songpa-gu','관악구':'Gwanak-gu','강북구':'Gangbuk-gu','도봉구':'Dobong-gu'}
DONGS={'장위1동':'Jangwi 1-dong','청파동':'Cheongpa-dong','용산2가동':'Yongsan 2-ga-dong','답십리1동':'Dapsimni 1-dong','진관동':'Jingwan-dong','제기동':'Jegi-dong','신정6동':'Sinjeong 6-dong','잠실2동':'Jamsil 2-dong','청룡동':'Cheongnyong-dong','인헌동':'Inheon-dong','우이동':'Ui-dong','도봉1동':'Dobong 1-dong'}
def read(p):return json.loads(Path(p).read_text())
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def write(p,s):
 with Path(p).open('x') as f:f.write(s)
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--dissertation',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
 assert not a.output.exists();root=a.dissertation;fig=root/'template/materials/figures';dest=fig/'results-03-query496-assets';assert not dest.exists()
 for repo in [Path(__file__).resolve().parents[1],root]:assert subprocess.check_output(['git','branch','--show-current'],cwd=repo,text=True).strip()=='reduced'
 source=[S10/'gallery_manifest.json',S10/'model_manifest.json',S10/'embeddings/cmp_FM/manifest.json',BANDS/'manifest.json',BANDS/'bands.parquet',BANDS/'queries/0496.json',VIEWER/'index.json',VIEWER/'config.json',VIEWER/'viewer_receipt.json',ASSETS/'manifest.json',ASSETS/'catalog.json']
 g=read(source[0]);rows=g['body']['rows'];assert len(rows)==9000 and len({r['scene_id'] for r in rows})==9000 and all(r['split']=='evaluation' and r['epsg']==5186 for r in rows)
 model=next(r for r in read(S10/'model_manifest.json')['body']['models'] if r['configuration_id']=='cmp_FM');emb=read(S10/'embeddings/cmp_FM/manifest.json');assert emb['body']['model']==model and emb['body']['scene_ids']==[r['scene_id'] for r in rows]
 assert model['checkpoint_id']=='p9ck_8ff9d205b9ff93e4d985ab06'
 ix=read(VIEWER/'index.json');vc=read(VIEWER/'config.json');assert sha(VIEWER/'index.json')==vc['index_sha256'];vrows=[dict(zip(ix['columns'],r)) for r in ix['rows']]
 assert vrows[495]['query_index']==496 and vrows[495]['scene_id']==rows[495]['scene_id']==SID
 band=read(BANDS/'queries/0496.json');bm=read(BANDS/'manifest.json');assert sha(BANDS/'queries/0496.json')==bm['query_hashes']['496']==vrows[495]['band_sha256'];assert band['query_scene_id']==SID and band['query_index']==496 and band['checkpoint']==model['checkpoint_id'] and band['embedding_manifest']==emb['artifact_id']
 cat=read(ASSETS/'catalog.json');am=read(ASSETS/'manifest.json');assert sha(ASSETS/'catalog.json')==am['catalog_sha256'];cr={r[0]:dict(zip(cat['columns'],r)) for r in cat['rows']};assert len(cr)==9000
 # Existing complete population region table is an independent source comparison.
 import pyarrow.parquet as pq
 table=pq.read_table(BANDS/'bands.parquet',filters=[('query_scene_id','=',SID)]).to_pylist();lookup={(r['mode'],r['band'],r['rank']):r for r in table}
 selected=[];checks=[]
 for mode in ['standard','nonlocal']:
  n=band['modes'][mode]['candidate_count'];assert n==(8999 if mode=='standard' else 8803)
  chosen=[('query',0,496,None,None)]
  for b in ['most','top','middle','bottom']:
   rr=band['modes'][mode]['bands'][b];expected={'most':[1],'top':list(range(2,12)),'middle':list(range((n-10)//2+1,(n-10)//2+11)),'bottom':list(range(n-9,n+1))}[b]
   assert [r[0] for r in rr]==expected
   for j in ([0] if b=='most' else [0,4,9]):chosen.append((b,*rr[j]))
  for k,(b,rank,index,sim,distance) in enumerate(chosen):
   scene=rows[index-1];sid=scene['scene_id'];meta=ASSETS/'meta'/f'{sid}.json';png=ASSETS/'main'/f'{sid}.png';source.extend([meta,png]);assert sha(meta)==cr[sid]['meta_sha256'] and sha(png)==cr[sid]['main_sha256']
   md=read(meta);assert md['scene_id']==sid and md['center']==[scene['center_x'],scene['center_y']];loc=md['location'];assert loc['dong_join_status']==loc['sigungu_join_status']=='unique_match'
   if b!='query':
    record=lookup[mode,b,rank];assert record['candidate_scene_id']==sid and record['cosine']==sim and record['distance_m']==distance
    actual=math.hypot(scene['center_x']-rows[495]['center_x'],scene['center_y']-rows[495]['center_y']);assert abs(actual-distance)<1e-8
    assert sid!=SID and (mode=='standard' or distance>=2000)
   name='Query' if b=='query' else 'Rank 1' if b=='most' else {'top':'Upper','middle':'Middle','bottom':'Lower'}[b]+' '+str((k-2)%3+1)
   selected.append(dict(mode=mode,panel=k+1,title=name,band=b,rank=rank if b!='query' else None,viewer_index=index,scene_id=sid,cosine_similarity=sim,distance_m=distance,distance_display='' if distance is None else f'{distance:.1f} m' if distance<1000 else f'{distance/1000:.2f} km',similarity_display='' if sim is None else f'{sim:.3f}',district_ko=loc['sigungu_name'],dong_ko=loc['eupmyeondong_name'],district_en=DISTRICTS[loc['sigungu_name']],dong_en=DONGS[loc['eupmyeondong_name']],center_x=scene['center_x'],center_y=scene['center_y'],epsg=5186,source_image=str(png),image_sha256=sha(png)))
 snapshots={str(p):sha(p) for p in source};a.output.mkdir(parents=True);dest.mkdir()
 for r in selected:
  target=dest/(r['scene_id']+'.png')
  if not target.exists():shutil.copyfile(r['source_image'],target)
  assert sha(target)==r['image_sha256']
 write(dest/'selection.json',json.dumps(selected,indent=2,ensure_ascii=False))
 with (a.output/'selected_scenes.csv').open('x') as f:
  w=csv.DictWriter(f,fieldnames=list(selected[0]));w.writeheader();w.writerows(selected)
 helper='''// Assembly of immutable Composite C scene images; no scene rerendering.
#let retrieval-panel(r, large: false) = {
  let size = if large { 44mm } else { 32.5mm }
  set text(font: "New Computer Modern", size: 7pt, fill: black)
  set par(leading: 0pt, spacing: 0pt, justify: false)
  align(center, stack(dir: ttb, spacing: 1pt,
    text(size: if large { 10.5pt } else { 8.5pt }, weight: "bold", r.title),
    text(size: 6.5pt, if r.band == "query" { "Viewer query 496" } else { "Global rank " + str(r.rank) }),
    box(stroke: 0.35pt + luma(160), image("results-03-query496-assets/" + r.scene_id + ".png", width: size, height: size)),
    text(r.district_en + ", " + r.dong_en),
    text(if r.band == "query" { "500 m × 500 m · north up" } else { r.distance_display + " · cosine " + r.similarity_display }),
  ))
}
#let qualitative-retrieval-layout(mode) = {
  let all = json("results-03-query496-assets/selection.json")
  let rows = all.filter(r => r.mode == mode)
  assert(rows.len() == 11)
  set par(leading: 0pt, spacing: 0pt, justify: false)
  stack(dir: ttb, spacing: 3mm,
    grid(columns: (1fr, 1fr), column-gutter: 3mm,
      retrieval-panel(rows.at(0), large: true), retrieval-panel(rows.at(1), large: true)),
    grid(columns: (1fr, 1fr, 1fr), column-gutter: 2mm, row-gutter: 2.5mm,
      ..rows.slice(2).map(r => retrieval-panel(r))),
  )
}
'''
 write(fig/'results-03-qualitative-retrieval-layout.typ',helper)
 for mode,num in [('standard','031'),('nonlocal','032')]:
  display='Standard' if mode=='standard' else 'Non-local';exclusion='Only the query itself is excluded.' if mode=='standard' else 'The query and candidates less than 2 km away are excluded.'
  content=f'''#import "../../../src/captions.typ": thesis-caption
#import "results-03-qualitative-retrieval-layout.typ": qualitative-retrieval-layout

#let qualitative-retrieval-{mode} = figure(
  qualitative-retrieval-layout("{mode}"),
  kind: image,
  caption: thesis-caption(
    caption-title: [Qualitative retrieval example under {display} retrieval.],
    caption-detail: [Both figures use query 496. {exclusion} Upper, Middle, and Lower show positions 1, 5, and 10 within ranks 2–11, the midpoint ten, and the final ten. Each map spans 500 m; labels give center distance and cosine similarity.],
  ),
)
'''
  write(fig/f'results-{num}-qualitative-retrieval-{mode}.typ',content)
 provenance=dict(status='PASS',query_scene_id=SID,viewer_index=496,checkpoint=model['checkpoint_id'],embedding_manifest=emb['artifact_id'],band_generation=band['generation_id'],source_sha256=snapshots,selection_rule='Rank1 plus offsets 0,4,9 in each ten-member band; identical in both modes',location_labels='Display-only English romanization of accepted Korean administrative-dong labels; no geocoding or spatial join',scientific_recomputation=False,source_unchanged=all(sha(p)==h for p,h in snapshots.items()),selected=selected)
 write(a.output/'provenance.json',json.dumps(provenance,indent=2,ensure_ascii=False));write(dest/'provenance.json',json.dumps({k:v for k,v in provenance.items() if k!='selected'},indent=2,ensure_ascii=False))
 print('PASS: 496 mapping; 22 panels; selected rank/band/score parity; distances; source image hashes; preserved sources')
 print(a.output)
if __name__=='__main__':main()
