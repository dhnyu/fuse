#!/usr/bin/env python
"""Publication presentation of accepted S11 §5.4.1. No scientific recomputation.
Only new output paths are writable. Quantiles are display normalization only.
"""
import argparse, copy, csv, hashlib, json, math, re, subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from concurrent.futures import ThreadPoolExecutor
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import colors, font_manager, ticker
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle
import numpy as np
import pyarrow.parquet as pq
from PIL import Image
from visualize_s11_descriptors import ROOT, RECEIPT, PRIMARY, FAMILIES, UNITS, sha, write_json, title

PREVIOUS=Path('/mnt/hdd002/dhnyu/fusedata/analysis_data/reduced/s11_visualization_only/20260923_1323_descriptor_expansion')
S12=Path('/mnt/hdd002/dhnyu/fusedata/analysis_data/reduced/s12_recovery/3c86147cd5c73e4047453653')
ORIGINAL12=Path('/mnt/hdd002/dhnyu/fusedata/analysis_data/reduced/s12_representation_alignment/s12_25d79952cccdf4b3165e4229')
DISS=Path('/members/dhnyu/dhnyu-masters-dissertation')
ROBUST=['poi_density','mean_building_footprint_size','mean_road_segment_length','mean_elevation','elevation_variability','road_density','mean_lane_count']
INTERPRETIVE=['building_use_composition','building_structure_composition','landcover_composition','mean_elevation','elevation_variability','building_coverage']
SVG='http://www.w3.org/2000/svg'; XLINK='http://www.w3.org/1999/xlink'
ET.register_namespace('',SVG); ET.register_namespace('xlink',XLINK)
NA='#b0b0b0'; POINT=2.2; ALPHA=.80

def snapshot(paths):
    paths=sorted(set(map(str,paths)))
    with ThreadPoolExecutor(max_workers=4) as pool:return dict(zip(paths,pool.map(sha,paths)))

def unchanged(snap):
    new=snapshot(snap)
    for p,h in snap.items():
        if new[p]!=h:raise RuntimeError('PRESERVATION_HASH '+p)

def run(*args):return subprocess.run(list(map(str,args)),check=True,capture_output=True,text=True).stdout

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();out=args.output
    if out.exists():raise RuntimeError('NEW_OUTPUT_REQUIRED')
    receipt=json.loads(RECEIPT.read_text());assert receipt['status']=='PASS'
    paths=list(receipt['verified_payload_hashes'])+[str(RECEIPT)]
    for root in [PREVIOUS,S12,ORIGINAL12]:paths.extend(p for p in root.rglob('*') if p.is_file())
    paths.extend(DISS/p for p in run('git','-C',DISS,'ls-files').splitlines() if (DISS/p).is_file())
    for root in ['python','R','targets','config']:paths.extend(p.resolve() for p in Path(root).rglob('*') if p.is_file() and '__pycache__' not in str(p))
    before=snapshot(paths)
    for p,h in receipt['verified_payload_hashes'].items():assert before[p]==h,('S11_HASH',p)
    s12_receipt=json.loads((S12/'receipt.json').read_text());assert s12_receipt['status']=='PASS'
    assert before[s12_receipt['scientific_acceptance']]==s12_receipt['scientific_acceptance_sha256']
    assert before[s12_receipt['mixed_index']]==s12_receipt['mixed_index_sha256']
    for root in [S12,ORIGINAL12]:
        for p in root.rglob('manifest.json'):
            m=json.loads(p.read_text())
            for f,h in m.get('files',{}).items():assert before[str(p.parent/f)]==h,('S12_PAYLOAD',p,f)
    for p,h in json.loads((PREVIOUS/'visualization_manifest.json').read_text())['artifacts'].items():assert before[p]==h
    out.mkdir(parents=True,exist_ok=False)
    write_json(out/'preservation_snapshot.json',before)
    print('Preflight PASS: S11, S12, previous visualization, scientific sources and dissertation snapshot',flush=True)
    descriptors=pq.read_table(ROOT/'descriptor_acceptance/accepted/descriptors.parquet').to_pydict()
    coords=pq.read_table(ROOT/'umap/coordinates/coordinates.parquet').to_pydict()
    ids=coords['scene_id'];assert ids==descriptors['scene_id'] and len(set(ids))==9000
    xy=np.array([coords['x'],coords['y']]).T;assert np.isfinite(xy).all()
    dictionary=json.loads((ROOT/'descriptor_acceptance/accepted/dictionary.json').read_text());byid={d['id']:d for d in dictionary}
    assert len(dictionary)==22 and sum(d['kind']=='scalar' for d in dictionary)==15
    validrows=pq.read_table(ROOT/'descriptor_acceptance/accepted/validity.parquet').to_pylist()
    validmap={(r['scene_id'],r['descriptor']):r['valid'] for r in validrows}
    letters=json.loads((PREVIOUS/'selected_scene_letters.json').read_text())
    selection=json.loads((ROOT/'umap/coordinates/illustrations.json').read_text())
    assert {r['scene_id'] for r in letters}=={r['scene_id'] for r in selection['scenes']}
    for r in letters:assert np.array_equal(xy[ids.index(r['scene_id'])],[r['x'],r['y']])
    with open(out/'scene_mapping_a_i.csv','w') as f:
        w=csv.DictWriter(f,fieldnames=list(letters[0]));w.writeheader();w.writerows(letters)
    registry={r['descriptor']:r for r in json.loads((PREVIOUS/'panel_registry.json').read_text())}
    with open(PREVIOUS/'legend_dictionary.csv') as f:legendrows=list(csv.DictReader(f))
    styles={};display_quantiles={}
    for d in dictionary:
        k=d['id'];values=descriptors[k];valid=np.array([v is not None for v in values])
        assert all(bool(valid[i])==validmap[(s,k)] for i,s in enumerate(ids))
        if d['kind']=='scalar':
            a=np.array([v if v is not None else np.nan for v in values]);assert np.isfinite(a[valid]).all()
            styles[k]={'v':a,'valid':valid,'limits':registry[k]['scalar_color_limits']}
            if k in ROBUST:
                bounds=np.quantile(a[valid],[.05,.95],method='linear').tolist();assert bounds[0]<bounds[1]
                display_quantiles[k]=bounds
        else:
            a=np.full(9000,-1,dtype=int)
            for j,v in enumerate(values):
                if v is not None:
                    assert len(v)==len(d['category_keys']) and np.isfinite(v).all()
                    a[j]=int(np.argmax(v))
            rows=[r for r in legendrows if r['descriptor']==k and r['displayed_as_dominant']=='True']
            palette={int(r['dictionary_index']):r['color'] for r in rows}
            styles[k]={'v':a,'valid':valid,'palette':palette,'labels':{int(r['dictionary_index']):r['display_label'] for r in rows}}
    write_json(out/'display_plan.json',{'main_descriptors':PRIMARY,'robust_descriptors':ROBUST,'interpretive_descriptors':INTERPRETIVE,
        'selection':'Existing D6 and A-I unchanged; interpretive supplement follows user-listed set, last panel building coverage fixed before rendering.',
        'robust_rule':'Valid stored scalar values; NumPy linear/type-7 5th and 95th percentiles used for display Normalize only. No altered/clipped descriptor values stored.',
        'display_limits':display_quantiles,'NA':NA,'point_size':POINT,'alpha':ALPHA,'zoom_viewport':[-3.5,4.5,8.0,18.0],
        'zoom_rule':'Manual fixed viewport around visible main manifold; purely a crop of accepted coordinates, full extent always also shown.'})
    font_manager.fontManager.addfont('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')
    plt.rcParams.update({'font.family':'Noto Sans CJK JP','font.size':9,'axes.titlesize':10,'axes.labelsize':8,
                         'xtick.labelsize':7,'ytick.labelsize':7,'pdf.fonttype':42,'svg.fonttype':'path','axes.linewidth':.6})
    limits=[(float(xy[:,i].min())-1,float(xy[:,i].max())+1) for i in range(2)]
    meta={};common={'accepted_receipt':str(RECEIPT),'accepted_receipt_sha256':before[str(RECEIPT)],'accepted_receipt_id':receipt['receipt_id'],
        'coordinate_manifest':str(ROOT/'umap/coordinates/manifest.json'),'coordinate_manifest_sha256':sha(ROOT/'umap/coordinates/manifest.json'),
        'coordinate_table_sha256':sha(ROOT/'umap/coordinates/coordinates.parquet'),
        'descriptor_table':str(ROOT/'descriptor_acceptance/accepted/descriptors.parquet'),'descriptor_table_sha256':sha(ROOT/'descriptor_acceptance/accepted/descriptors.parquet'),
        'validity_sha256':sha(ROOT/'descriptor_acceptance/accepted/validity.parquet'),'dictionary_sha256':sha(ROOT/'descriptor_acceptance/accepted/dictionary.json'),
        'selection':str(ROOT/'umap/coordinates/illustrations.json'),'selection_sha256':sha(ROOT/'umap/coordinates/illustrations.json'),
        'A_I_mapping':letters,'NA_handling':'Gray for undefined only; observed zero remains viridis lower-range color.',
        'dominant_category_rule':'Stored-vector argmax; first frozen dictionary category wins exact ties. Visualization-only; full-vector quantitative analysis is unchanged.',
        'preservation_statement':'No UMAP refit; no embeddings/descriptors recomputation; no new statistical analysis; no clustering. Display percentiles only; accepted quantitative S11 uses all original values.',
        'UMAP_settings':'Accepted d=256 scene representations; cosine, n_neighbors=30, min_dist=0.1, seed=20260904.',
        'selection_rule':'Accepted 3x3 UMAP quantile grid; minimum SHA256(fixed_selection_seed || scene_id) per occupied cell; no replacements.',
        'palette':'Identical per-category hex colors to prior visualization legend_dictionary.csv; viridis continuous.',
        'limits':limits,'point_size':POINT,'alpha':ALPHA}

    def base(ax):
        ax.set(xlim=limits[0],ylim=limits[1],aspect='equal',xlabel='UMAP 1',ylabel='UMAP 2')
        ax.spines[['top','right']].set_visible(False);ax.xaxis.set_major_locator(ticker.MaxNLocator(4));ax.yaxis.set_major_locator(ticker.MaxNLocator(4))

    def panel(fig,spec,k,label,robust=False,overview=False):
        st=styles[k];d=byid[k]
        if isinstance(spec,dict):
            ax=fig.add_axes(spec['plot']);lg=fig.add_axes(spec['legend'])
        else:
            grid=spec.subgridspec(2,1,height_ratios=[1,.44 if d['kind']=='compositional' else .25],hspace=.13)
            ax=fig.add_subplot(grid[0]);lg=fig.add_subplot(grid[1])
        lg.axis('off');base(ax)
        ax.set_title(f'({label}) '+title(d).replace('landcover','land cover'),loc='left',fontsize=8 if overview else 10,pad=7)
        if d['kind']=='scalar':
            bounds=display_quantiles[k] if robust else st['limits'];norm=colors.Normalize(*bounds,clip=robust)
            rgba=plt.get_cmap('viridis')(norm(np.nan_to_num(st['v'])));rgba[~st['valid']]=colors.to_rgba(NA)
            ax.scatter(xy[:,0],xy[:,1],c=rgba,s=POINT,alpha=ALPHA,linewidths=0)
            cax=lg.inset_axes([.08,.65,.76,.12]);cb=fig.colorbar(plt.cm.ScalarMappable(norm=norm,cmap='viridis'),cax=cax,orientation='horizontal',extend='both' if robust else 'neither')
            cb.locator=ticker.MaxNLocator(4);cb.update_ticks();cb.ax.tick_params(labelsize=6 if overview else 7,pad=1)
            cb.set_label(UNITS[d['units']],fontsize=7 if overview else 8,labelpad=1)
            if robust:lg.text(.5,-.07,'Visualization scale: 5th–95th percentile',ha='center',fontsize=7,transform=lg.transAxes)
        else:
            ax.scatter(xy[:,0],xy[:,1],c=[st['palette'][int(v)] if ok else NA for v,ok in zip(st['v'],st['valid'])],s=POINT,alpha=ALPHA,linewidths=0)
            handles=[Line2D([],[],marker='o',ls='',markersize=3.7,color=st['palette'][i],label=st['labels'][i]) for i in sorted(st['palette'])]
            lg.legend(handles=handles,ncols=2 if len(handles)>8 else 1,loc='upper center',frameon=False,
                      fontsize=5.7 if overview else 7,handletextpad=.3,columnspacing=.65,borderaxespad=0,labelspacing=.18)
        return ax

    def register(name,keys,scale,caption,extra=None):
        meta[name]=dict(common,descriptors=keys,visualization_scale=scale,caption=caption,**(extra or {}))

    def save(fig,name,keys,robust=False,overview=False,caption=None):
        fig.savefig(out/(name+'.pdf'),metadata={'CreationDate':None,'ModDate':None})
        fig.savefig(out/(name+'.png'),dpi=300 if not overview else 240)
        plt.close(fig)
        register(name,keys,'5th–95th percentile, display normalization only' if robust else 'Full-range, unchanged prior color limits',caption or
            'Accepted FM UMAP coordinates colored by original scene descriptors. Gray denotes undefined values; defined zero retains the low-value viridis color. Dominant categories are visualization-only and do not replace full-vector quantitative analysis.',
            {'display_limits':{k:display_quantiles[k] for k in keys} if robust else {k:styles[k].get('limits') for k in keys}})
        print('Rendered '+name,flush=True)

    def grid_figure(name,keys,heading,robust=False):
        cols=min(3,len(keys));rows=math.ceil(len(keys)/cols)
        legend_heights=[]
        for row in range(rows):
            heights=[.62 if robust else .47]
            for k in keys[row*cols:(row+1)*cols]:
                if byid[k]['kind']=='compositional':
                    n=len(styles[k]['palette']);nrows=math.ceil(n/2) if n>8 else n
                    heights.append(.10+nrows*.115)
            legend_heights.append(max(heights))
        row_heights=[3.35+h+.62 for h in legend_heights]
        width=4.2*cols;height=sum(row_heights)+.9
        fig=plt.figure(figsize=(width,height));fig.suptitle(heading,fontsize=13,y=1-.15/height)
        fig.text(.5,.13/height,'Gray: undefined   •   Dominant categories: visualization only; quantitative analysis uses full vectors',fontsize=8,ha='center')
        for i,k in enumerate(keys):
            row,col=divmod(i,cols);bottom=.48+sum(row_heights[row+1:]);lh=legend_heights[row]
            bounds={'plot':[(4.2*col+.50)/width,(bottom+lh+.28)/height,3.35/width,3.35/height],
                    'legend':[(4.2*col+.13)/width,bottom/height,3.94/width,lh/height]}
            panel(fig,bounds,k,chr(97+i),robust=robust)
        save(fig,name,keys,robust)

    grid_figure('main_six_panels',PRIMARY,'FM representation space')
    for family,heading in FAMILIES.items():
        grid_figure('family_'+family,[d['id'] for d in dictionary if d['family']==family],heading)
    grid_figure('robust_scalar_supplement',ROBUST,'Scalar descriptors — robust display supplement',robust=True)
    grid_figure('semantic_environment_supplement',INTERPRETIVE,'Interpretive supplementary panels')
    fig=plt.figure(figsize=(18,37),layout='constrained');subfigs=fig.subfigures(6,1,height_ratios=[1,2,1,1,2,1],hspace=.012)
    fig.suptitle('FM S11 · all 22 descriptors — overview',fontsize=16)
    fig.supxlabel('Full-range colors • Gray: undefined • Dominant categories: visualization only',fontsize=10)
    for sub,(fam,heading) in zip(subfigs,FAMILIES.items()):
        ds=[d for d in dictionary if d['family']==fam];sub.suptitle(heading,fontsize=12,ha='left',x=.015);gs=sub.add_gridspec(math.ceil(len(ds)/3),3)
        for i,d in enumerate(ds):panel(sub,gs[i//3,i%3],d['id'],chr(97+list(byid).index(d['id'])),overview=True)
    save(fig,'all_22_overview',list(byid),overview=True)
    run('pdfunite',*[out/('family_'+k+'.pdf') for k in FAMILIES],out/'all_22_large_format.pdf')
    register('all_22_large_format',list(byid),'Full-range, unchanged prior color limits','Six readable family pages; exactly the same panels, colors and values as the family PDF set.',{'pages':6})

    # Main A-I: vector-preserving crop/reposition of accepted PDF illustration panels.
    source_svg=out/'accepted_illustrations_vector_source.svg'
    run('pdftocairo','-svg',ROOT/'publication/figures_tables/illustrations.pdf',source_svg)
    original=ET.parse(source_svg).getroot();black=[e for e in original.iter() if e.attrib.get('stroke')=='rgb(0%, 0%, 0%)']
    assert len(black)==36
    crops=[]
    for i in range(0,36,4):
        points=[]
        for path in black[i:i+4]:
            assert path.attrib['transform']=='matrix(1, 0, 0, -1, 0, 720)'
            v=list(map(float,re.findall(r'[-+]?\d*\.?\d+',path.attrib['d'])));points.extend(zip(v[::2],v[1::2]))
        x0=min(x for x,y in points);x1=max(x for x,y in points);y0=720-max(y for x,y in points);y1=720-min(y for x,y in points)
        crops.append([x0,y0,x1-x0,y1-y0])
    assert len(crops)==9
    fig=plt.figure(figsize=(13.4,8.2));gs=fig.add_gridspec(1,2,width_ratios=[.95,1.55],left=.045,right=.988,bottom=.065,top=.91,wspace=.17)
    left=gs[0].subgridspec(2,1,height_ratios=[1,1.35],hspace=.38)
    full=fig.add_subplot(left[0]);zoom=fig.add_subplot(left[1]);base(full);base(zoom)
    zoom_box=[-3.5,4.5,8.,18.]
    offsets={'A':(-12,7),'B':(7,7),'C':(7,7),'D':(-12,7),'E':(7,7),'F':(7,7),'G':(-12,7),'H':(7,7),'I':(7,7)}
    for ax in [full,zoom]:
        ax.scatter(xy[:,0],xy[:,1],color='#d1d1d1',s=2.0,alpha=.85,linewidths=0)
        for r in letters:
            ax.scatter(r['x'],r['y'],facecolors='white',edgecolors='#151515',s=30 if ax==full else 42,linewidths=.85,zorder=4)
            ax.annotate(r['label'],(r['x'],r['y']),xytext=offsets[r['label']],textcoords='offset points',fontsize=8 if ax==full else 10,weight='bold',zorder=5,
                        bbox={'facecolor':'white','edgecolor':'none','alpha':.88,'pad':.4})
    full.add_patch(Rectangle((zoom_box[0],zoom_box[2]),zoom_box[1]-zoom_box[0],zoom_box[3]-zoom_box[2],fill=False,lw=.65,edgecolor='#6a6a6a'))
    full.set_title('(a) Full extent',loc='left',fontsize=10);zoom.set(xlim=zoom_box[:2],ylim=zoom_box[2:]);zoom.set_title('(b) Zoomed view',loc='left',fontsize=10)
    right=gs[1].subgridspec(3,3,wspace=.055,hspace=.11);scene_axes=[]
    for i in range(9):
        ax=fig.add_subplot(right[i//3,i%3]);ax.set_aspect('equal');ax.set(xlim=(0,1),ylim=(0,1));ax.axis('off');scene_axes.append(ax)
    fig.suptitle('FM representation space and original scene illustrations',fontsize=14,y=.972)
    fig.text(.615,.935,'Buildings',color='#777777',fontsize=9);fig.text(.705,.935,'Roads',color='#2166ac',fontsize=9);fig.text(.77,.935,'POIs',color='#b2182b',fontsize=9)
    fig.text(.54,.02,'A–I: fixed illustrative scenes; no cluster or prototype interpretation',fontsize=9,ha='center')
    fig.canvas.draw();placements=[ax.get_position().bounds for ax in scene_axes]
    path=out/'main_umap_ai.svg';fig.savefig(path);plt.close(fig)
    doc=ET.parse(path);svg=doc.getroot();width,height=13.4*72,8.2*72
    defs=ET.SubElement(svg,'{'+SVG+'}defs');group=ET.SubElement(defs,'{'+SVG+'}g',id='acceptedIllustrationPage')
    for child in original:group.append(copy.deepcopy(child))
    for i,(pos,crop) in enumerate(zip(placements,crops)):
        x,y,w,h=pos;xx=x*width;yy=(1-y-h)*height;ww=w*width;hh=h*height
        nested=ET.SubElement(svg,'{'+SVG+'}svg',x=str(xx),y=str(yy),width=str(ww),height=str(hh),viewBox=' '.join(map(str,crop)),overflow='hidden')
        ET.SubElement(nested,'{'+SVG+'}use',{'{'+XLINK+'}href':'#acceptedIllustrationPage'})
        ET.SubElement(svg,'{'+SVG+'}rect',{'x':str(xx+.5),'y':str(yy+.5),'width':str(ww-1),'height':str(hh-1),'fill':'none','stroke':'#777','stroke-width':'.5'})
        ET.SubElement(svg,'{'+SVG+'}rect',{'x':str(xx+3),'y':str(yy+3),'width':'17','height':'19','fill':'white','stroke':'none','fill-opacity':'.93'})
        text=ET.SubElement(svg,'{'+SVG+'}text',{'x':str(xx+7),'y':str(yy+17),'fill':'#111','font-family':'sans-serif','font-size':'12','font-weight':'bold'});text.text=chr(65+i)
    doc.write(path,encoding='utf-8',xml_declaration=True)
    run('rsvg-convert','--format=pdf','--output',out/'main_umap_ai.pdf',path)
    run('pdftoppm','-singlefile','-png','-r','300',out/'main_umap_ai.pdf',out/'main_umap_ai')
    register('main_umap_ai',[],'Neutral gray; no descriptor color encoding',
        'Accepted FM representations for all 9,000 original evaluation scenes, projected by the already accepted UMAP. Full extent is retained in (a); the rectangle marks the unchanged-coordinate viewport enlarged in (b). A–I are the original deterministic illustrative scenes in their original 3×3 ordering. Original building/road/POI vector drawings are reused without reconstruction. Scene IDs are listed separately. No similarity is inferred from UMAP distances.',
        {'zoom_viewport':zoom_box,'illustration_source_pdf':str(ROOT/'publication/figures_tables/illustrations.pdf'),'illustration_source_sha256':sha(ROOT/'publication/figures_tables/illustrations.pdf'),
         'vector_crop_boxes_pdf_top_left_units':crops,'selection_cuts_visible':False,'original_geometry_unchanged':True})
    print('Rendered main_umap_ai with vector original scenes',flush=True)
    write_json(out/'figure_metadata.json',{'figures':meta,'created_at':datetime.now(ZoneInfo('Asia/Seoul')).isoformat()})
    captions=['# Caption-ready metadata','',common['preservation_statement'],'']
    for name,m in meta.items():
        captions += ['## '+name,'',m['caption'],'','Scale: '+m['visualization_scale']+'.',
                     'For robust panels, only color saturation changes at the valid-value 5th and 95th percentiles; quantitative analysis uses unchanged full values.' if name=='robust_scalar_supplement' else '',
                     'Receipt: `'+receipt['receipt_id']+'`. Input hashes and A–I mapping: `figure_metadata.json`.','']
    (out/'figure_captions.md').write_text('\n'.join(captions))
    # Read-back and preservation gates, before publication manifest is written last.
    for p in out.glob('*.png'):
        with Image.open(p) as im:im.verify()
    for p in out.glob('*.pdf'):
        info=run('pdfinfo',p);pages=int(re.search(r'Pages:\s+(\d+)',info).group(1));assert pages==(6 if p.stem=='all_22_large_format' else 1)
    # Accepted scientific and previous presentation bytes stay identical, including dissertation.
    unchanged(before)
    payloads=snapshot(p for p in out.iterdir() if p.is_file())
    counts={str(root):sum(str(p).startswith(str(root)+'/') for p in before) for root in [S12,ORIGINAL12,PREVIOUS,DISS]}
    write_json(out/'visualization_manifest.json',{'status':'PASS','scope':'presentation only','created_at':datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
        'accepted_S11_receipt_id':receipt['receipt_id'],'S11_receipt_listed_payload_count':len(receipt['verified_payload_hashes']),
        'preservation_verified_before_and_after':True,'preservation_file_counts':counts,'all_snapshot_files':len(before),
        'source_script':str(Path(__file__).resolve()),'source_script_sha256':sha(__file__),
        'scientific_recomputation':False,'display_quantiles_only':True,'UMAP_refit':False,'clustering':False,
        'figures':list(meta),'payload_sha256':payloads,'checks':['accepted input identities/order/validity','same category palette and D6 selection','same A-I scene IDs and coordinates','no scene ID titles in cropped illustration panels','vector PDF output','all PNG/PDF read-back','S11/S12/previous visualization/scientific source/dissertation unchanged']})
    print('PASS '+str(out),flush=True)

if __name__=='__main__':main()
