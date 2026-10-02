#!/usr/bin/env python3
"""Supplemental display experiment; no models, embeddings or ranking computations.
Reuses S10 SVG geometry and raster observations (methodology scene representation).
All publication occurs in fresh roots, after rendering/identity validation.
"""
from pathlib import Path
import base64, copy, hashlib, io, json, math, os, subprocess, time
import xml.etree.ElementTree as ET
import numpy as np
from PIL import Image

BASE = Path('/mnt/hdd002/dhnyu/fusedata/retrieval_data/reduced')
VIEWER = BASE / 's10_all_model_viewers/viewer_models_ca8e9bba52741dd6a0ff563b'
INPUT = BASE / 's10/s10gen_a24b979d4c1557387cbbec35/original_inputs'
AUDIT = Path('/mnt/hdd002/dhnyu/fusedata/tmp/fuse/scene_composite_20260922')
NS = '{http://www.w3.org/2000/svg}'
ET.register_namespace('', NS[1:-1])
VARIANTS = {
 'A': dict(title='LC + vectors', shade='none', opacity=0, style='filled'),
 'B': dict(title='Multiply relief', shade='multiply', opacity=.35, style='filled'),
 'C': dict(title='Soft relief + outlines', shade='soft', opacity=.25, style='outline'),
 'D': dict(title='Normalized relief + quiet vectors', shade='normalized', opacity=.30, style='quiet'),
 'E': dict(title='Soft relief + quiet vectors', shade='soft', opacity=.25, style='quiet'),
}
STYLES = {
 'filled': dict(building_fill=.24, building_stroke=.65, road_width=1.5, halo=0, poi_radius=1.4, poi_opacity=.65),
 'outline': dict(building_fill=0, building_stroke=.75, road_width=1.7, halo=3.3, poi_radius=1.6, poi_opacity=.65),
 'quiet': dict(building_fill=.12, building_stroke=.38, road_width=1.7, halo=3.3, poi_radius=1.1, poi_opacity=.40),
}
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def enc(x): return json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(',',':')).encode()
def read(p): return json.loads(Path(p).read_text())
def write(p,x): Path(p).write_bytes(enc(x))
def image_uri(im):
 b=io.BytesIO(); im.save(b,format='PNG'); return 'data:image/png;base64,'+base64.b64encode(b.getvalue()).decode()
def uri_image(uri): return Image.open(io.BytesIO(base64.b64decode(uri.split(',',1)[1]))).convert('RGBA')
def hillshade(z, valid, size=500):
 """Display gain 100 metres per standardized unit; never a metric slope product.
 Pixel centers lie at (i+.5)*500/17; PIL resize uses the same pixel-center convention.
 """
 z=np.asarray(z,dtype=float); valid=np.asarray(valid,dtype=bool)
 dz_south,dz_east=np.gradient(np.where(valid,z,0)*100.,500/z.shape[0],500/z.shape[1])
 nx=-dz_east; ny=dz_south; nz=np.ones_like(z)
 az=math.radians(315); alt=math.radians(45)
 h=(nx*math.sin(az)*math.cos(alt)+ny*math.cos(az)*math.cos(alt)+nz*math.sin(alt))/np.sqrt(nx*nx+ny*ny+nz*nz)
 good=valid.copy()
 good[1:] &= valid[:-1];good[:-1] &= valid[1:];good[:,1:] &= valid[:,:-1];good[:,:-1] &= valid[:,1:]
 h=np.where(good,np.clip(h,0,1),math.sin(alt))
 # Linear resampling is for continuous display shade only, never categorical LC.
 up=lambda x: np.asarray(Image.fromarray(x.astype('float32')).resize((size,size),Image.Resampling.BILINEAR),dtype=float)
 return up(h), np.asarray(Image.fromarray((good*255).astype('uint8')).resize((size,size),Image.Resampling.NEAREST))>0

def composite_base(lc, h, good, variant):
 b=np.asarray(lc.resize(h.shape[::-1],Image.Resampling.NEAREST),dtype=float)/255
 s=VARIANTS[variant];flat=math.sqrt(.5)
 if s['shade']=='none': return Image.fromarray(np.round(b*255).astype('uint8'))
 if s['shade']=='multiply': factor=np.clip(h/flat,0,1); out=b[:,:,:3]*factor[:,:,None]
 elif s['shade']=='normalized':
  vals=h[good]; lo,hi=np.quantile(vals,[.05,.95]) if len(vals) else (flat,flat)
  # Flat surfaces remain unchanged; cap normalization amplification to 4x.
  factor=np.clip(1+(h-hi)*min(4.,.8/max(hi-lo,1e-9)),.2,1) if hi-lo>1e-6 else np.ones_like(h)
  out=b[:,:,:3]*factor[:,:,None]
 else:
  s1=np.clip(.5+(h-flat),0,1)[:,:,None]; c=b[:,:,:3]
  d=np.where(c<=.25,((16*c-12)*c+4)*c,np.sqrt(c))
  out=np.where(s1<=.5,c-(1-2*s1)*c*(1-c),c+(2*s1-1)*(d-c))
 out=np.where(good[:,:,None],out,b[:,:,:3]); b[:,:,:3]=(1-s['opacity'])*b[:,:,:3]+s['opacity']*out
 return Image.fromarray(np.round(np.clip(b,0,1)*255).astype('uint8'))

def kind(node):
 colors={v.lower() for n in node.iter() for k,v in n.attrib.items() if k in ('fill','stroke')}
 found=[k for c,k in [('#667085','building'),('#e4a11b','road'),('#c83e63','poi')] if c in colors]
 if len(found)!=1: raise ValueError(('unrecognized vector type',colors))
 return found[0]
def geometry_signature(node):
 return [(n.tag,{k:v for k,v in n.attrib.items() if k in ('d','points','cx','cy','x','y','transform')}) for n in node.iter()]
def vector_overlay(svg, style, background_uri):
 root=ET.fromstring(svg);assert root.attrib['viewBox']=='0 0 500 500'
 g=next(n for n in root if n.tag==NS+'g'); assert g.attrib['transform']=='translate(0 500) scale(1 -1)'
 grouped={k:[] for k in ['building','road','poi']};counts={k:0 for k in grouped}
 for n in g: k=kind(n);grouped[k].append(n);counts[k]+=1
 out=ET.Element(NS+'svg',dict(viewBox='0 0 500 500',width='500',height='500'))
 ET.SubElement(out,NS+'image',dict(x='0',y='0',width='500',height='500',href=background_uri))
 dest=ET.SubElement(out,NS+'g',g.attrib);p=STYLES[style]
 def styled(src,k,halo=False):
  n=copy.deepcopy(src); sig=geometry_signature(n)
  for c in n.iter():
   if c.tag==NS+'g': continue
   c.set('opacity','1')
   if k=='building':
    c.set('fill','#344054');c.set('fill-opacity',str(p['building_fill']));c.set('stroke','#344054');c.set('stroke-opacity',str(p['building_stroke']));c.set('stroke-width','.7')
   elif k=='road':
    c.set('fill','none');c.set('stroke','#ffffff' if halo else '#164d68');c.set('stroke-width',str(p['halo'] if halo else p['road_width']));c.set('stroke-opacity','.85' if halo else '1');c.set('stroke-linecap','round');c.set('stroke-linejoin','round')
   else:
    c.set('fill','#76235d');c.set('stroke','#ffffff');c.set('stroke-width','.35');c.set('opacity',str(p['poi_opacity']))
    if c.tag==NS+'circle':c.set('r',str(p['poi_radius']))
  assert sig==geometry_signature(n), 'geometry changed'
  return n
 for n in grouped['building']:dest.append(styled(n,'building'))
 if p['halo']:
  for n in grouped['road']:dest.append(styled(n,'road',True))
 for n in grouped['road']:dest.append(styled(n,'road'))
 for n in grouped['poi']:dest.append(styled(n,'poi'))
 for n in root:
  if n.tag==NS+'text':out.append(copy.deepcopy(n))
 return ET.tostring(out,encoding='unicode'),counts

def main():
 import torch
 from playwright.sync_api import sync_playwright
 torch.set_num_threads(1);started=time.time();AUDIT.mkdir(parents=True,exist_ok=True)
 idx=read(VIEWER/'index.json');rows=[dict(zip(idx['columns'],r)) for r in idx['rows']];byid={r['scene_id']:r for r in rows};guard={}
 def checked(p,expected=None):
  s=sha(p)
  if expected:assert s==expected,str(p)
  guard[str(p)]=s;return read(p)
 for p in [VIEWER/'index.json',VIEWER/'config.json',VIEWER/'viewer_receipt.json',BASE/'viewer_hub/index.html',Path('config/retrieval_lc_official_palette.json'),INPUT/'manifest.json']:
  checked(p) if p.suffix=='.json' else guard.update({str(p):sha(p)})
 before={'head':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'branch':subprocess.check_output(['git','branch','--show-current'],text=True).strip(),'status':subprocess.check_output(['git','status','--short'],text=True),'listeners':subprocess.getoutput("ss -H -ltnp 'sport = :8765'"),'hub_routes':{n:os.readlink(BASE/'viewer_hub'/n) for n in ('canonical','extreme')}}
 assert before['branch']=='reduced';write(AUDIT/'before.json',before)
 # Selection uses only current display counts and immutable LC composition; no rankings computed.
 for r in rows:
  p=VIEWER/'lc'/(r['scene_id']+'.json');lc=checked(p,r['lc_sha256']); vals={x['internal_code']:x['value'] for x in lc['chart']}
  for name,codes in [('urban',range(1,7)),('agriculture',range(7,12)),('forest',range(12,15)),('green',range(12,17)),('water',range(21,23))]:r[name]=sum(vals.get(c,0) for c in codes)
 selected={}
 def add(r,reason): selected.setdefault(r['scene_id'],dict(row=r,reasons=[]))['reasons'].append(reason)
 def top(key,reason,predicate=lambda r:True):
  choices=sorted((r for r in rows if predicate(r)),key=lambda r:(-key(r),r['scene_id']))
  r=choices[0];add(r,reason);return choices
 top(lambda r:r['n_buildings'],'Maximum observed building count')
 top(lambda r:r['n_roads'],'Maximum observed road count')
 top(lambda r:r['n_pois'],'Maximum observed POI count')
 mixed=top(lambda r:min(r['urban'],r['green']),'Maximum min(urban %, green %)')
 forest=top(lambda r:r['forest'],'Maximum forest share')
 agri=top(lambda r:r['agriculture'],'Maximum agricultural share')
 water=top(lambda r:min(r['water'],100-r['water']),'Waterfront proxy: maximum min(water %, non-water %)')
 top(lambda r:r['n_obj'],'Most object-bearing waterfront',lambda r:20<=r['water']<=80)
 top(lambda r:-r['n_obj'],'Minimum positive vector-object count',lambda r:r['n_obj']>0)
 top(lambda r:r['green'],'Vector-empty green reference',lambda r:r['n_obj']==0)
 top(lambda r:r['agriculture'],'Object-bearing agricultural example',lambda r:r['n_obj']>=20)
 for name,path in [('STANDARD_LOW',BASE/'s10_extreme_rank1/s10ext_e907433b34cee238114526a0/sets/STANDARD_LOW.json'),('STANDARD_HIGH_OBJ20',BASE/'s10_extreme_obj20/s10obj20_231acf9cc8b0c27b6f7c63d2/sets/STANDARD_HIGH_OBJ20.json')]:
  doc=checked(path)
  for j,r in enumerate(doc['body']['rows'][:2]):add(byid[r['query_scene_id']],f'Immutable {name}: ordered member {j+1}')
 manifest=read(INPUT/'manifest.json');files={f['path']:f['sha256'] for f in manifest['files']};dems={}
 def dem_for(sid):
  if sid not in dems:
   p=INPUT/(sid+'.pt');assert sha(p)==files[p.name];guard[str(p)]=files[p.name]
   payload=torch.load(p,weights_only=True,mmap=True,map_location='cpu');assert payload['scene_id']==sid
   z=payload['rasters']['dem_standardized_mean'].numpy().squeeze().copy();valid=payload['rasters']['dem_valid_mask'].numpy().squeeze().astype(bool)
   assert z.shape==(17,17) and valid.shape==z.shape
   dems[sid]=(z,valid)
  return dems[sid]
 # Bounded, predeclared terrain screening pool. Not claimed a global steepest/flat inventory.
 pool=sorted(set(selected)|{r['scene_id'] for rs in (mixed,forest,agri,water) for r in rs[:12]}|{rows[j]['scene_id'] for j in range(0,9000,450)})
 scores=[]
 for sid in pool:
  z,v=dem_for(sid)
  if v.all():
   gy,gx=np.gradient(z,500/17);scores.append((float(np.mean(np.hypot(gx,gy))),sid))
 add(byid[max(scores)[1]],'Largest mean standardized DEM gradient in fixed screening pool')
 add(byid[min(scores)[1]],'Smallest mean standardized DEM gradient in fixed screening pool')
 # Fill to 18 using next-largest agricultural/forest shares without duplicates.
 for r in agri[:20]+forest[:20]:
  if len(selected)>=18:break
  if r['scene_id'] not in selected:add(r,'Additional agricultural contrast (composition order)')
 assert 16<=len(selected)<=20
 palette=read('config/retrieval_lc_official_palette.json')
 contract={'source_viewer':str(VIEWER),'palette_sha256':sha('config/retrieval_lc_official_palette.json'),'variants':VARIANTS,'styles':STYLES,'hillshade':{'azimuth_deg':315,'altitude_deg':45,'display_z_gain':100,'z_gain_units':'display metres per accepted standardized DEM unit; not metric slope','grid_m':500/17,'normalization':'B flat-reference multiply; C/E flat-centered soft-light; D per-scene p5/p95 contrast with max gain 4, flat guard 1e-6'},'selected':selected,'terrain_screening_pool':pool,'code_sha256':sha(__file__)}
 ident=hashlib.sha256(enc(contract)).hexdigest()[:24];gen='composite_'+ident;vid='viewer_composite_'+ident
 root=BASE/'scene_composite_experiments'/gen;view=BASE/'scene_composite_experiment_viewers'/vid
 assert not root.exists() and not view.exists(),'immutable output exists; do not overwrite'
 staging=root.parent/('.staging_'+gen);staging.mkdir(parents=True,exist_ok=False);(staging/'images').mkdir();(staging/'svg').mkdir()
 records=[]
 with sync_playwright() as p:
  browser=p.chromium.launch(headless=True);page=browser.new_page()
  def raster(svg):
   data=page.evaluate('''async (svg)=>{const im=new Image();const u=URL.createObjectURL(new Blob([svg],{type:'image/svg+xml'}));try{im.src=u;await im.decode();const c=document.createElement('canvas');c.width=c.height=500;c.getContext('2d').drawImage(im,0,0,500,500);return c.toDataURL('image/png').split(',')[1]}finally{URL.revokeObjectURL(u)}}''',svg)
   return base64.b64decode(data)
  for n,(sid,selection) in enumerate(selected.items(),1):
   r=selection['row'];s=checked(VIEWER/'summaries'/(sid+'.json'),r['summary_sha256']);d=checked(VIEWER/'details'/(sid+'.json'),r['detail_sha256']);lc=checked(VIEWER/'lc'/(sid+'.json'),r['lc_sha256']);z,v=dem_for(sid)
   assert s['scene_id']==d['scene_id']==lc['scene_id']==sid
   assert s['center']==[r['center_x'],r['center_y']]
   assert d['thematic']['binding']['original_input_sha256']==files[sid+'.pt']==lc['original_input_sha256']
   assert s['counts']==dict(building=r['n_buildings'],road=r['n_roads'],poi=r['n_pois'])
   lci=uri_image(lc['lc']);demi=uri_image(d['dem']);assert lci.size==(100,100) and demi.size==(17,17)
   (staging/'images'/f'{sid}_vector.png').write_bytes(raster(s['svg']))
   lci.resize((500,500),Image.Resampling.NEAREST).save(staging/'images'/f'{sid}_lc.png')
   demi.resize((500,500),Image.Resampling.NEAREST).save(staging/'images'/f'{sid}_dem.png')
   h,good=hillshade(z,v)
   for name in VARIANTS:
    base=composite_base(lci,h,good,name);svg,counts=vector_overlay(s['svg'],VARIANTS[name]['style'],image_uri(base));assert counts==s['counts']
    (staging/'svg'/f'{sid}_{name}.svg').write_text(svg)
    (staging/'images'/f'{sid}_{name}.png').write_bytes(raster(svg))
   gy,gx=np.gradient(z,500/17)
   rec=dict(selection,index=n,dem_min=float(z[v].min()),dem_max=float(z[v].max()),dem_valid=int(v.sum()),mean_standardized_gradient=float(np.mean(np.hypot(gx,gy)[v])),counts_verified=True,geometry_verified=True)
   records.append(rec);print(n,sid,selection['reasons'],flush=True)
  browser.close()
 contract['records']=records;contract['generation_id']=gen;contract['viewer_id']=vid;contract['elapsed_seconds']=time.time()-started
 contract['source_hashes']=guard
 contract['output_hashes']={str(p.relative_to(staging)):sha(p) for p in staging.rglob('*') if p.is_file()}
 assert all(sha(p)==s for p,s in guard.items()),'source mutation'
 assert subprocess.getoutput("ss -H -ltnp 'sport = :8765'")==before['listeners']
 assert {n:os.readlink(BASE/'viewer_hub'/n) for n in ('canonical','extreme')}==before['hub_routes']
 contract['validation']={'sources_unchanged':True,'production_listener_unchanged':True,'hub_routes_unchanged':True,'all_images_decodable':all(Image.open(p).size==(500,500) for p in (staging/'images').glob('*.png')),'scene_count':len(records),'image_count':len(list((staging/'images').glob('*.png')))}
 write(staging/'manifest.json',contract);root.parent.mkdir(parents=True,exist_ok=True);staging.rename(root)
 view.parent.mkdir(parents=True,exist_ok=True);view.mkdir();(view/'images').symlink_to(root/'images');(view/'manifest.json').symlink_to(root/'manifest.json')
 import html
 htm=['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Scene Composite Experiment</title><style>body{font:15px system-ui;background:#f5f5f2;color:#172b37;margin:24px}header{max-width:1100px}section{background:white;padding:18px;margin:22px 0;border:1px solid #ccd3d6;border-radius:8px}h2{font-size:18px}small{color:#465965}.variants,.reference{display:grid;grid-template-columns:repeat(5,minmax(180px,1fr));gap:12px;overflow:auto}figure{margin:0}img{width:100%;aspect-ratio:1;object-fit:contain;cursor:zoom-in;border:1px solid #d8dcdd}figcaption{font-size:13px;margin:6px 0}.reference{grid-template-columns:repeat(3,minmax(160px,280px));margin-top:10px}details{margin:15px 0}dialog{max-width:90vw;border:0;padding:15px}dialog img{width:min(80vh,800px);display:block}button,select{padding:7px}code{font-size:12px}table{border-collapse:collapse}td,th{padding:6px;border:1px solid #ccc}@media(max-width:800px){.variants{grid-template-columns:repeat(5,220px)}}</style><header><h1>Scene Composite Experiment</h1><p>Supplemental visualization study · 18 purpose-selected scenes · 500 m × 500 m · North up</p><p>LC uses the verified official 22-class palette. Hillshade uses <b>standardized DEM with display gain</b>, not metric slopes. A has no shade; B multiply; C soft + outlines; D locally normalized + quiet vectors; E soft + quiet vectors. Colors in shaded composites are blended; the LC reference preserves base colors.</p><label>Scene <select id="scene"><option value="all">All 18 scenes</option>']
 for rec in records:
  r=rec['row'];htm.append(f'<option value="{r["scene_id"]}">{rec["index"]}. {html.escape(r["sigungu"]+" "+r["dong"])} · {r["scene_id"]}</option>')
 htm.append('</select></label><p>Click a map for a 500 px comparison. Open “Separated references” for the unchanged vector, official LC and current DEM panels. No production viewer has changed.</p></header>')
 for rec in records:
  r=rec['row'];sid=r['scene_id'];reason=html.escape('; '.join(rec['reasons']))
  htm.append(f'<section data-scene="{sid}"><h2>{rec["index"]}. {html.escape(r["sigungu"]+" "+r["dong"])} · <code>{sid}</code></h2><p>{reason}</p><small>B {r["n_buildings"]} · R {r["n_roads"]} · P {r["n_pois"]} | Urban {r["urban"]:.1f}% · Forest {r["forest"]:.1f}% · Agriculture {r["agriculture"]:.1f}% · Water {r["water"]:.1f}% | DEM standardized span {rec["dem_max"]-rec["dem_min"]:.3f}</small><div class="variants">')
  for k,vv in VARIANTS.items():htm.append(f'<figure><figcaption><b>{k}</b> · {vv["title"]}</figcaption><img loading="lazy" src="images/{sid}_{k}.png" alt="{sid} variant {k}"></figure>')
  htm.append('</div><details><summary>Separated references · vector / official LC / current DEM display</summary><div class="reference">')
  for k,label in [('vector','Current vector'),('lc','Official LC'),('dem','Current DEM display (standardized, clipped color scale)')]:htm.append(f'<figure><figcaption>{label}</figcaption><img loading="lazy" src="images/{sid}_{k}.png" alt="{sid} {label}"></figure>')
  htm.append('</div></details></section>')
 htm.append('<h2>Official LC base palette</h2><p>Compositing changes displayed RGB. Category data and base colors are unchanged. Invalid raster support remains transparent; no category is assigned to nodata.</p><table><tr><th>Internal / official</th><th>Category</th><th>RGB</th></tr>')
 for row in palette['rows']:htm.append(f'<tr><td>{row["internal"]} / {row["official"]}</td><td><span style="display:inline-block;width:30px;height:15px;background:{row["hex"]}"></span> {row["category"]}</td><td>{row["rgb"]}</td></tr>')
 htm.append('</table><dialog id="zoom"><button id="close">Close</button><p></p><img alt="Enlarged map"></dialog><script>const z=document.querySelector("#zoom");document.querySelectorAll("section img").forEach(im=>im.onclick=()=>{z.querySelector("img").src=im.src;z.querySelector("p").textContent=im.alt;z.showModal()});document.querySelector("#close").onclick=()=>z.close();document.querySelector("#scene").onchange=e=>{document.querySelectorAll("section").forEach(s=>s.hidden=e.target.value!=="all"&&s.dataset.scene!==e.target.value)};</script></html>')
 (view/'index.html').write_text(''.join(htm));write(view/'viewer_receipt.json',dict(viewer_id=vid,generation_id=gen,root=str(view),html_sha256=sha(view/'index.html'),manifest_sha256=sha(root/'manifest.json')))
 write(AUDIT/'result.json',dict(root=str(root),viewer=str(view),generation=gen,viewer_id=vid,elapsed=time.time()-started));print(json.dumps(read(AUDIT/'result.json')),flush=True)
if __name__=='__main__':main()
