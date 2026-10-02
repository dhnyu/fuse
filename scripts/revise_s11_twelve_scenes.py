#!/usr/bin/env python
"""S11 presentation-only twelve-scene extension; immutable scientific inputs."""
from pathlib import Path
import argparse,copy,csv,hashlib,json,tarfile,tempfile,xml.etree.ElementTree as ET
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pyarrow.compute as pc
import shapely,zarr
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from revisualize_s11_publication import ROOT,RECEIPT,sha,snapshot,unchanged,run,write_json
from s11_v4_presentation_assets import display_layers,uri,NS,XL
VIZ=Path('/mnt/hdd002/dhnyu/fusedata/analysis_data/reduced/s11_visualization_only')
V4=VIZ/'20260923_1518_publication_v4_lcdem_compactlegend'
V5=VIZ/'20260924_0003_main_six_revision'

def inside(xy,b):return (xy[:,0]>=b[0])&(xy[:,0]<=b[1])&(xy[:,1]>=b[2])&(xy[:,1]<=b[3])
def node(tag,attrs):return ET.Element(NS+tag,{k:str(v) for k,v in attrs.items()})
def geometry_svg(parent,g,name,xmin,ymin):
    pieces=list(g.geoms) if hasattr(g,'geoms') else [g]
    unit=500/207.839844
    for p in pieces:
        if name=='building':
            paths=[]
            for ring in [p.exterior,*p.interiors]:
                a=np.array(ring.coords);a-=np.array([xmin,ymin]);paths.append('M '+' L '.join(f'{x:.12g},{y:.12g}' for x,y in a)+' Z')
            parent.append(node('path',{'d':' '.join(paths),'fill':'#777777','fill-rule':'evenodd','stroke':'none'}))
        elif name=='road':
            a=np.array(p.coords)-np.array([xmin,ymin]);parent.append(node('polyline',{'points':' '.join(f'{x:.12g},{y:.12g}' for x,y in a),'fill':'none','stroke':'#2166ac','stroke-width':.5*unit,'stroke-linecap':'square'}))
        else:parent.append(node('circle',{'cx':p.x-xmin,'cy':p.y-ymin,'r':.25*unit,'fill':'#b2182b'}))

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);out=ap.parse_args().output;assert not out.exists()
    baseline=json.loads((V5/'preservation_snapshot.json').read_text());unchanged(baseline)
    baseline.update(snapshot(p for p in VIZ.rglob('*') if p.is_file()))
    receipt=json.loads(RECEIPT.read_text());assert receipt['status']=='PASS'
    for p,h in receipt['verified_payload_hashes'].items():assert sha(p)==h
    out.mkdir();print('Preservation preflight PASS',flush=True)
    coords=pq.read_table(ROOT/'umap/coordinates/coordinates.parquet').to_pydict();ids=coords['scene_id'];xy=np.column_stack([coords['x'],coords['y']])
    assert len(ids)==len(set(ids))==9000 and ids==pq.read_table(ROOT/'accepted_parents/parents/population.parquet')['scene_id'].to_pylist()
    old=list(csv.DictReader((V4/'scene_mapping_a_i.csv').open()));rows=[]
    for r in old:
        i=ids.index(r['scene_id']);assert np.array_equal(xy[i],[float(r['x']),float(r['y'])]);rows.append(dict(label=r['label'],scene_id=r['scene_id'],x=float(r['x']),y=float(r['y']),region='original A-I',selection_sha256=r['selection_sha256']))
    windows=json.loads((V4/'layout_plan.json').read_text())['viewports'];taken={r['scene_id'] for r in rows}
    for label,region in [('J','sw'),('K','east'),('L','main')]:
        candidates=[s for s,ok in zip(ids,inside(xy,windows[region])) if ok and s not in taken]
        sid=min(candidates,key=lambda s:(hashlib.sha256(('20260904'+s).encode()).hexdigest(),s));i=ids.index(sid);taken.add(sid)
        rows.append(dict(label=label,scene_id=sid,x=float(xy[i,0]),y=float(xy[i,1]),region=region,selection_sha256=hashlib.sha256(('20260904'+sid).encode()).hexdigest()))
    write_json(out/'selection_frozen_before_render.json',{'rule':'Min SHA256(ASCII 20260904 || UTF8 scene_id), lexical tie; fixed V4 viewports; exclude A-I; no observation/result inspection or replacement','scenes':rows})
    print(json.dumps(rows[-3:]),flush=True)
    cfg=json.loads(Path('config/s11_execution.json').read_text())
    for pin in cfg['p3_pins'].values():assert sha(pin['path'])==pin['sha256'];baseline[pin['path']]=pin['sha256']
    index={r['scene_id']:r for r in pq.read_table(cfg['p3_pins']['index']['path']).to_pylist()}
    zarr.config.set({'async.concurrency':1,'threading.max_workers':1})
    newnodes={};source_records=[]
    for r in rows[-3:]:
        sid=r['scene_id'];sp=index[sid];source=Path(cfg['p3_root'])/'shards'/sp['branch_id']/sp['payload_filename'];assert sha(source)==sp['payload_sha256'];baseline[str(source)]=sp['payload_sha256']
        with tempfile.TemporaryDirectory(prefix='s11-12scene-') as temp,tarfile.open(source,'r:') as tar:
            table=pq.read_table(pa.BufferReader(tar.extractfile('raster/scene_raster_index.parquet').read()));rr=table.filter(pc.equal(table['scene_id'],sid)).to_pylist();assert len(rr)==1;rr=rr[0];z=rr['zarr_index']
            assert rr['split']=='evaluation' and rr['row_order']=='north_to_south' and rr['column_order']=='west_to_east';assert rr['xmax']-rr['xmin']==rr['ymax']-rr['ymin']==500
            for member in tar.getmembers():
                parts=Path(member.name).parts
                if len(parts)<3 or parts[:2] not in [('raster','scene_landcover.zarr'),('raster','scene_dem.zarr')]:continue
                if not (parts[-1].startswith('.') or parts[-1].split('.')[0]==str(z)):continue
                assert member.isfile() and '..' not in parts and not Path(member.name).is_absolute();dest=Path(temp)/member.name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(tar.extractfile(member).read())
            lc=zarr.open_group(str(Path(temp)/'raster/scene_landcover.zarr'),mode='r');dem=zarr.open_group(str(Path(temp)/'raster/scene_dem.zarr'),mode='r')
            shade,lci=display_layers(lc['class_fraction'][z],lc['valid_mask'][z].astype(bool),dem['raw_mean_m'][z],dem['valid_mask'][z].astype(bool))
            scene=node('svg',{'viewBox':'0 0 500 500','overflow':'hidden'})
            for im,opacity in [(shade,1),(lci,.5)]:scene.append(node('image',{'x':0,'y':0,'width':500,'height':500,'preserveAspectRatio':'none','opacity':opacity,XL+'href':uri(im)}))
            vectors=node('g',{'transform':'translate(0 500) scale(1 -1)'});scene.append(vectors);counts={};gh={}
            for name in ['building','road','poi']:
                table=pq.read_table(pa.BufferReader(tar.extractfile('vector/'+name+'_observed.parquet').read()));wkbs=table.filter(pc.equal(table['scene_id'],sid))['observed_geometry'].to_pylist();counts[name]=len(wkbs);gh[name]=hashlib.sha256(b''.join(wkbs)).hexdigest()
                for g in shapely.from_wkb(wkbs):geometry_svg(vectors,g,name,rr['xmin'],rr['ymin'])
            newnodes[r['label']]=scene;source_records.append({'label':r['label'],'scene_id':sid,'source':str(source),'sha256':sp['payload_sha256'],'extent':[rr[k] for k in ['xmin','ymin','xmax','ymax']],'observed_entities_rendered':counts,'WKB_sha256':gh,'raster_index':rr})
        print('Rendered bounded original scene '+r['label'],flush=True)
    # Left UMAP coordinates are unchanged. Islands appear in zoom insets, never projected onto main viewport.
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'svg.fonttype':'none','axes.linewidth':.6})
    fig=plt.figure(figsize=(13.4,12));full=fig.add_axes([.045,.66,.255,.255]);zoom=fig.add_axes([.045,.16,.255,.435])
    zoom_box=[-3.5,4.5,8.,18.];offsets={s:(-12,7) if s in 'ADG' else (7,7) for s in 'ABCDEFGHIJKL'};offsets['L']=(7,-13)
    def paint(ax,subset,selected,small=False):
        sc=ax.scatter(xy[subset,0],xy[subset,1],color='#d1d1d1',s=2,alpha=.85,linewidths=0);assert np.array_equal(np.asarray(sc.get_offsets()),xy[subset])
        for r in selected:
            ax.scatter(r['x'],r['y'],facecolors='white',edgecolors='#151515',s=30 if small else 42,linewidths=.85,zorder=4)
            ax.annotate(r['label'],(r['x'],r['y']),xytext=offsets[r['label']],textcoords='offset points',fontsize=8 if small else 10,weight='bold',zorder=5,bbox={'facecolor':'white','edgecolor':'none','alpha':.88,'pad':.4})
        ax.set_aspect('equal');ax.spines[['top','right']].set_visible(False)
    paint(full,np.ones(9000,bool),rows,True);paint(zoom,inside(xy,zoom_box),[r for r in rows if r['label'] not in 'JK'])
    full.set(xlabel='UMAP 1',ylabel='UMAP 2');zoom.set(xlim=zoom_box[:2],ylim=zoom_box[2:],xlabel='UMAP 1',ylabel='UMAP 2')
    full.add_patch(Rectangle((zoom_box[0],zoom_box[2]),8,10,fill=False,lw=.65,edgecolor='#6a6a6a'));full.set_title('(a) Full extent',loc='left',fontsize=10);zoom.set_title('(b) Zoomed view',loc='left',fontsize=10)
    for label,region,box in [('J','sw',[.015,.025,.18,.18]),('K','east',[.77,.025,.20,.20])]:
        ax=zoom.inset_axes(box);b=windows[region];paint(ax,inside(xy,b),[r for r in rows if r['label']==label],True);ax.set(xlim=b[:2],ylim=b[2:],xticks=[],yticks=[])
        for s in ax.spines.values():s.set_visible(True);s.set_linewidth(.5);s.set_color('#777')
    fig.suptitle('FM representation space and original scene illustrations',fontsize=14,y=.98)
    for x,t,c in [(.60,'Buildings','#777777'),(.70,'Roads','#2166ac'),(.77,'POIs','#b2182b')]:fig.text(x,.947,t,color=c,fontsize=9)
    fig.text(.54,.018,'A–L: fixed illustrative scenes; no cluster or prototype interpretation',fontsize=9,ha='center')
    fig.text(.17,.09,'Zoom insets: original coordinates;\nspacing to main view not preserved.',fontsize=8,ha='center')
    svgpath=out/'main_umap_ai_lc_dem_v2.svg';fig.savefig(svgpath);plt.close(fig)
    doc=ET.parse(svgpath);root=doc.getroot();oldroot=ET.parse(V4/'main_umap_ai_lc_dem.svg').getroot();prior=oldroot.findall(NS+'svg');assert len(prior)==9
    defs=next(d for d in list(oldroot) if any(e.get('id')=='acceptedIllustrationPage' for e in d.iter()));root.append(copy.deepcopy(defs))
    placements=[];size=190.8
    for i,r in enumerate(rows):
        scene=copy.deepcopy(prior[i]) if i<9 else newnodes[r['label']];x=4.65*72+(i%3)*(size+8.64);y=.69*72+(i//3)*(size+8.64)
        if i<9:assert [ET.tostring(e) for e in scene]==[ET.tostring(e) for e in prior[i]]
        scene.set('x',str(x));scene.set('y',str(y));scene.set('width',str(size));scene.set('height',str(size));root.append(scene)
        root.append(node('rect',{'x':x+.5,'y':y+.5,'width':size-1,'height':size-1,'fill':'none','stroke':'#777','stroke-width':.5}))
        root.append(node('rect',{'x':x+3,'y':y+3,'width':17,'height':19,'fill':'white','fill-opacity':.93}))
        tx=node('text',{'x':x+7,'y':y+17,'fill':'#111','font-family':'sans-serif','font-size':12,'font-weight':'bold'});tx.text=r['label'];root.append(tx)
        placements.append({'label':r['label'],'x_pt':x,'y_pt':y,'size_pt':size})
    doc.write(svgpath,encoding='utf-8',xml_declaration=True)
    run('rsvg-convert','--format=pdf','--output',out/'main_umap_ai_lc_dem_v2.pdf',svgpath)
    run('pdftoppm','-singlefile','-png','-r','300',out/'main_umap_ai_lc_dem_v2.pdf',out/'main_umap_ai_lc_dem_v2')
    run('pdftoppm','-singlefile','-png','-scale-to','1800',out/'main_umap_ai_lc_dem_v2.pdf',out/'preview')
    with (out/'scene_mapping_a_l.csv').open('w') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    assert len(root.findall(NS+'svg'))==12 and len({r['scene_id'] for r in rows})==12
    write_json(out/'figure_metadata.json',{'accepted_receipt':str(RECEIPT),'receipt_sha256':sha(RECEIPT),'coordinates_sha256':sha(ROOT/'umap/coordinates/coordinates.parquet'),'source_figure':str(V4/'main_umap_ai_lc_dem.svg'),'source_figure_sha256':sha(V4/'main_umap_ai_lc_dem.svg'),'selection':rows,'new_scene_sources':source_records,'A_I_children_and_viewboxes_unchanged':True,'A_I_original_selection_unchanged':True,'original_scene_box_pt':float(prior[0].get('width')),'new_scene_box_pt':size,'linear_enlargement_ratio':size/float(prior[0].get('width')),'placements':placements,'grid':[4,3],'J_K_L_in_full_and_zoom':True,'zoom_islands':'J/K shown in original-coordinate insets; L within main viewport. No coordinate transformation; inset-to-main spacing not preserved.','rendering_style':json.loads((V4/'illustration_layer_metadata.json').read_text())['hillshade'],'layer_order':['DEM hillshade','LC opacity 0.50','buildings','roads','POIs'],'scientific_analysis':False,'interpretation':'All 12 are fixed illustrations only, not clusters, centroids or prototypes. No replacements after source rendering.'})
    unchanged(baseline);write_json(out/'preservation_snapshot.json',baseline)
    write_json(out/'visualization_manifest.json',{'status':'PASS','created_at':datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),'S11_unchanged':1352,'S12_unchanged':27427,'all_preserved_files':len(baseline),'scientific_analysis':False,'source_script':str(Path(__file__).resolve()),'source_script_sha256':sha(__file__),'payload_sha256':snapshot(p for p in out.rglob('*') if p.is_file())})
    print('PASS '+str(out),flush=True)
if __name__=='__main__':main()
