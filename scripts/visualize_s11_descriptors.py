#!/usr/bin/env python
"""Visualization-only expansion of accepted S11 (dissertation §5.4.1).
No UMAP fitting, embedding/P3 reads, descriptor extraction, or metric calculation.
Read-only accepted inputs; exclusive new output directory; receipt hashes pre/post.
"""
import argparse
import csv
import hashlib
import json
import math
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager, colors, ticker
from matplotlib.lines import Line2D
import numpy as np
import pyarrow.parquet as pq
from PIL import Image

ROOT = Path('/mnt/hdd002/dhnyu/fusedata/analysis_data/reduced/s11_representation/df3b397b64b6aeebde547b2e')
RECEIPT = Path('/mnt/hdd002/dhnyu/fusedata/analysis_data/reduced/s11_revalidation/s11rv_c41x8mg_/receipt.json')
FAMILIES = {'composition':'Scene composition', 'geometry':'Intrinsic geometry',
            'configuration':'Spatial configuration', 'relations':'Relational structure',
            'semantics':'Semantic attributes', 'environment':'Environmental context'}
PRIMARY = ['building_coverage','mean_building_compactness','building_location_dispersion',
           'mean_relational_degree','poi_l2_composition','landcover_composition']
UNITS = {'fraction':'fraction', 'km/km2':'km/km²', 'entities/km2':'entities/km²',
         'm2':'m²', '1':'dimensionless', 'm':'m', 'neighbors/entity':'neighbors/entity',
         'lanes':'lanes', 'proportion':'dominant category'}
BOUNDED = {'building_coverage','mean_building_compactness','building_orientation_dispersion','road_orientation_dispersion'}
POINT_SIZE, ALPHA = 3.0, 0.80
NA = '#b0b0b0'

def sha(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(8*1024*1024),b''): h.update(b)
    return h.hexdigest()

def write_json(p,d):
    p.write_text(json.dumps(d,ensure_ascii=False,indent=2,allow_nan=False)+'\n')

def verify_all(receipt):
    for p,h in receipt['verified_payload_hashes'].items():
        if sha(p)!=h: raise RuntimeError('ACCEPTED_PAYLOAD_HASH: '+p)
    if receipt['status']!='PASS': raise RuntimeError('S11_NOT_ACCEPTED')

def title(d):
    name=d['id'].replace('_',' ').capitalize().replace('Poi','POI')
    if d['kind']=='compositional': name='Dominant '+name.removesuffix(' composition').lower().replace('poi','POI').replace('l2','L2')
    return name

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--output',type=Path,required=True); args=ap.parse_args()
    out=args.output
    if out.exists(): raise RuntimeError('OUTPUT_ALREADY_EXISTS')
    receipt=json.loads(RECEIPT.read_text()); receipt_sha=sha(RECEIPT)
    verify_all(receipt)
    print('Accepted receipt and all payload hashes verified before rendering',flush=True)
    dictionary=json.loads((ROOT/'descriptor_acceptance/accepted/dictionary.json').read_text())
    table=pq.read_table(ROOT/'descriptor_acceptance/accepted/descriptors.parquet').to_pydict()
    support=pq.read_table(ROOT/'descriptor_acceptance/accepted/validity.parquet').to_pylist()
    coords=pq.read_table(ROOT/'umap/coordinates/coordinates.parquet').to_pydict()
    population=pq.read_table(ROOT/'accepted_parents/parents/population.parquet').to_pydict()
    assert table['scene_id']==coords['scene_id']==population['scene_id']
    assert len(set(coords['scene_id']))==9000 and len(dictionary)==22
    assert sum(d['kind']=='scalar' for d in dictionary)==15
    ids=coords['scene_id']; xy=np.column_stack([coords['x'],coords['y']]); assert np.isfinite(xy).all()
    byid={d['id']:d for d in dictionary}; validity={(r['scene_id'],r['descriptor']):r for r in support}
    assert len(validity)==9000*22
    selected=json.loads((ROOT/'umap/coordinates/illustrations.json').read_text())
    assert len(selected['scenes'])==9
    # Stored cutpoint rows are quantiles and columns are x/y (not the reverse).
    cuts=np.asarray(selected['cutpoints'],dtype=np.float64)
    assert cuts.shape==(2,2)
    # All selections are adopted, never selected again. Letters follow displayed grid row order.
    letters=[]
    for i,r in enumerate(sorted(selected['scenes'],key=lambda r:(-r['cell_y'],r['cell_x']))):
        j=ids.index(r['scene_id'])
        assert int(np.searchsorted(cuts[:,0],xy[j,0],side='right'))==r['cell_x']
        assert int(np.searchsorted(cuts[:,1],xy[j,1],side='right'))==r['cell_y']
        letters.append(dict(r,label=chr(65+i),x=float(xy[j,0]),y=float(xy[j,1])))
    lcpath=Path('config/retrieval_lc_official_palette.json')
    lc={str(r['internal']):r for r in json.loads(lcpath.read_text())['rows']}
    font_manager.fontManager.addfont('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')
    plt.rcParams.update({'font.family':'Noto Sans CJK JP','font.size':9,'axes.titlesize':11,
                         'pdf.fonttype':42,'savefig.facecolor':'white'})
    # Rules are fixed before visual inspection; no percentile clipping or hidden transforms.
    styles={}; display_rows=[]
    for d in dictionary:
        k=d['id']; vals=table[k]; valid=np.array([v is not None for v in vals])
        assert all(bool(valid[j])==validity[(s,k)]['valid'] for j,s in enumerate(ids))
        if d['kind']=='scalar':
            v=np.array([float(v) if v is not None else np.nan for v in vals]); assert np.isfinite(v[valid]).all()
            lo,hi=(0.,1.) if k in BOUNDED else (float(v[valid].min()),float(v[valid].max()))
            if lo==hi: hi=lo+1.
            styles[k]={'valid':valid,'v':v,'norm':colors.Normalize(lo,hi),'range':[lo,hi]}
        else:
            keys=d['category_keys']; labels=d.get('category_labels',keys)
            a=np.full(9000,-1,dtype=int)
            for j,v in enumerate(vals):
                if v is not None:
                    assert len(v)==len(keys) and np.isfinite(v).all()
                    a[j]=int(np.argmax(np.asarray(v,dtype=np.float64)))
            present=sorted(set(a[valid].tolist()))
            palette=list(plt.get_cmap('tab20').colors)+list(plt.get_cmap('tab20b').colors)
            cmap={i:(lc[keys[i]]['hex'] if k=='landcover_composition' else colors.to_hex(palette[n])) for n,i in enumerate(present)}
            names={i:((keys[i]+' '+lc[keys[i]]['category']) if k=='landcover_composition' else (keys[i] if labels[i]==keys[i] else keys[i]+' '+labels[i])) for i in present}
            styles[k]={'valid':valid,'v':a,'present':present,'colors':cmap,'names':names}
            for i,key in enumerate(keys):
                display_rows.append({'descriptor':k,'dictionary_index':i,'category_key':key,
                                     'accepted_label':labels[i], 'displayed_as_dominant':i in present,
                                     'display_label':names.get(i,''),'color':cmap.get(i,'')})
    out.mkdir(parents=True,exist_ok=False)
    write_json(out/'visualization_plan.json',{
        'scope':'visualization only; no scientific computation',
        'selected_six':PRIMARY,'selection_rule':'Retain the six prospectively approved D6 representatives, one per family; no result-driven substitution.',
        'coordinates':'unchanged accepted float32 x/y in accepted scene order',
        'scalar_color_rule':'Linear full observed valid range; dimensionless bounded coverage/compactness/orientation use [0,1]. No clipping, transforms, rescaling of descriptor values, or outlier removal.',
        'composition_rule':'Argmax of stored vector; exact ties choose first frozen dictionary index. No renormalization. Only categories present as argmax appear in panel legend; all categories remain in legend_dictionary.csv.',
        'point_size':POINT_SIZE,'alpha':ALPHA,'null_color':NA,
        'illustration_rule':'Reuse accepted PDF and selected IDs; A-I display-row order, no reselection.',
        'warning':'Dominant-category panels are visualization-only and do not replace accepted full-vector analysis.'})
    with open(out/'legend_dictionary.csv','w') as f:
        w=csv.DictWriter(f,fieldnames=list(display_rows[0]));w.writeheader();w.writerows(display_rows)
    write_json(out/'selected_scene_letters.json',letters)
    limits=[(float(xy[:,j].min())-1,float(xy[:,j].max())+1) for j in range(2)]

    def base(ax):
        ax.set(xlim=limits[0],ylim=limits[1],aspect='equal',xlabel='UMAP 1',ylabel='UMAP 2')
        ax.tick_params(labelsize=7); ax.spines[['top','right']].set_visible(False)

    def panel(fig,spec,d):
        grid=spec.subgridspec(1,2,width_ratios=[1,.76],wspace=.07)
        ax=fig.add_subplot(grid[0]); leg=fig.add_subplot(grid[1]);leg.axis('off')
        k=d['id'];st=styles[k]; valid=st['valid'];base(ax)
        ax.set_title(title(d)+'\n['+UNITS[d['units']]+']',loc='left',fontsize=10,pad=10)
        # Accepted order preserved, with identical size/alpha in every panel.
        if d['kind']=='scalar':
            rgba=plt.get_cmap('viridis')(st['norm'](np.nan_to_num(st['v'])));rgba[~valid]=colors.to_rgba(NA)
            ax.scatter(xy[:,0],xy[:,1],c=rgba,s=POINT_SIZE,alpha=ALPHA,linewidths=0,rasterized=True)
            cax=leg.inset_axes([.10,.20,.13,.57]); sm=plt.cm.ScalarMappable(norm=st['norm'],cmap='viridis')
            cb=fig.colorbar(sm,cax=cax);cb.set_label(UNITS[d['units']],fontsize=9)
            cb.locator=ticker.MaxNLocator(nbins=5);cb.update_ticks();cb.ax.tick_params(labelsize=8)
            leg.text(.04,.88,'Linear color scale\nFull range; no clipping',transform=leg.transAxes,fontsize=8)
            leg.legend(handles=[Line2D([],[],marker='o',linestyle='',color=NA,label='Undefined / NA')],loc='lower left',frameon=False,fontsize=8)
        else:
            rgba=[st['colors'][int(a)] if ok else NA for a,ok in zip(st['v'],valid)]
            ax.scatter(xy[:,0],xy[:,1],c=rgba,s=POINT_SIZE,alpha=ALPHA,linewidths=0,rasterized=True)
            handles=[Line2D([],[],marker='o',linestyle='',color=st['colors'][i],label=st['names'][i],markersize=5) for i in st['present']]
            handles.append(Line2D([],[],marker='o',linestyle='',color=NA,label='Undefined / NA',markersize=5))
            leg.legend(handles=handles,loc='center left',frameon=False,fontsize=7.2,handletextpad=.3,labelspacing=.35,
                       title='Dominant category only\nVisualization only',title_fontsize=8,borderaxespad=0)
        return ax

    outputs=[]
    def save(fig,name):
        for ext,dpi in [('pdf',160),('png',130)]:
            p=out/(name+'.'+ext);fig.savefig(p,dpi=dpi,bbox_inches='tight',metadata={'CreationDate':None,'ModDate':None} if ext=='pdf' else None);outputs.append(str(p))
        plt.close(fig);print('Rendered '+name,flush=True)

    # Subfigures preserve explicit family grouping in the complete diagnostic layout.
    fig=plt.figure(figsize=(25,44),layout='constrained')
    subfigs=fig.subfigures(6,1,height_ratios=[1,2,1,1,2,1],hspace=.018)
    fig.suptitle('FM S11 — all 22 accepted descriptors on the unchanged UMAP\nCategorical panels show dominant category only; gray = undefined. No clustering or new quantitative analysis.',fontsize=18)
    for sub,(fam,label) in zip(subfigs,FAMILIES.items()):
        ds=[d for d in dictionary if d['family']==fam];sub.suptitle(label,fontsize=16,ha='left',x=.01)
        gs=sub.add_gridspec(math.ceil(len(ds)/3),3)
        for i,d in enumerate(ds):panel(sub,gs[i//3,i%3],d)
    save(fig,'all_22_descriptors')
    for fam,label in FAMILIES.items():
        ds=[d for d in dictionary if d['family']==fam];cols=min(3,len(ds));rows=math.ceil(len(ds)/cols)
        fig=plt.figure(figsize=(8.4*cols,5.5*rows),layout='constrained');fig.suptitle(label+' — accepted FM S11 UMAP\nDominant categories are visualization-only; gray = undefined.',fontsize=15)
        gs=fig.add_gridspec(rows,cols)
        for i,d in enumerate(ds):panel(fig,gs[i//cols,i%cols],d)
        save(fig,'family_'+fam)
    fig=plt.figure(figsize=(25,12),layout='constrained');fig.suptitle('FM S11 — six preselected D6 representatives\nUnchanged coordinates; dominant categories are visualization-only; gray = undefined.',fontsize=16)
    gs=fig.add_gridspec(2,3)
    for i,k in enumerate(PRIMARY):panel(fig,gs[i//3,i%3],byid[k])
    save(fig,'candidate_six_d6')

    # Rasterize the accepted illustration page as-is. Never reconstruct scene observations.
    subprocess.run(['pdftoppm','-singlefile','-png','-r','200',str(ROOT/'publication/figures_tables/illustrations.pdf'),str(out/'accepted_illustrations_render')],check=True)
    illustration=Image.open(out/'accepted_illustrations_render.png')
    fig=plt.figure(figsize=(19,10),layout='constrained');gs=fig.add_gridspec(1,2,width_ratios=[.82,1.18])
    ax=fig.add_subplot(gs[0]);base(ax);ax.scatter(xy[:,0],xy[:,1],c='#c6c6c6',s=POINT_SIZE,alpha=ALPHA,linewidths=0,rasterized=True)
    for x in cuts[:,0]:ax.axvline(x,c='#999999',ls='--',lw=.6)
    for y in cuts[:,1]:ax.axhline(y,c='#999999',ls='--',lw=.6)
    for r in letters:
        ax.scatter(r['x'],r['y'],s=65,facecolors='white',edgecolors='black',linewidths=1,zorder=4)
        ax.annotate(r['label'],(r['x'],r['y']),xytext=(7,7),textcoords='offset points',fontsize=13,weight='bold',zorder=5,
                    bbox=dict(facecolor='white',edgecolor='none',alpha=.9,pad=1))
    ax.set_title('A–I: accepted deterministic illustrations\nDashed lines: original UMAP 1/3 and 2/3 cuts',fontsize=11)
    right=fig.add_subplot(gs[1]);right.imshow(illustration);right.axis('off')
    # Labels sit inside top-left of each original panel without replacing scene-ID titles.
    for r in letters:
        x=.045+r['cell_x']*.328;y=.920-(2-r['cell_y'])*.319
        right.text(x,y,r['label'],transform=right.transAxes,fontsize=15,weight='bold',va='top',
                   bbox=dict(facecolor='white',edgecolor='black',alpha=.95,pad=2))
    fig.suptitle('Fixed UMAP locations and unchanged original scene illustrations\nIllustrations only — no cluster, centroid, or prototype interpretation',fontsize=16)
    save(fig,'umap_with_illustrations_a_i')
    # Copy accepted summary values without recalculating any statistic.
    summary=pq.read_table(ROOT/'alignment_summaries/summaries/summary.parquet').to_pylist()
    rho=[r for r in summary if r['region']=='rho']
    with open(out/'accepted_rho_reference.csv','w') as f:
        w=csv.DictWriter(f,fieldnames=list(rho[0]));w.writeheader();w.writerows(rho)
    write_json(out/'panel_registry.json',[{'descriptor':d['id'],'family':d['family'],'kind':d['kind'],'units':d['units'],
                'scalar_color_limits':styles[d['id']].get('range'),'source_definition':d['definition']} for d in dictionary])
    verify_all(receipt);assert sha(RECEIPT)==receipt_sha
    artifacts={str(p):sha(p) for p in sorted(out.iterdir()) if p.is_file()}
    write_json(out/'visualization_manifest.json',{'status':'PASS','visualization_only':True,'created_at':datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
        'receipt_id':receipt['receipt_id'],'receipt_path':str(RECEIPT),'receipt_sha256':receipt_sha,
        'accepted_generation':str(ROOT),'all_accepted_payload_hashes_verified_before_and_after':len(receipt['verified_payload_hashes']),
        'scene_count':9000,'descriptor_count':22,'scalar_count':15,'compositional_count':7,'family_count':6,'illustration_count':9,
        'accepted_inputs':{p:h for p,h in receipt['verified_payload_hashes'].items() if any(s in p for s in ['descriptor_acceptance/accepted/','umap/coordinates/','publication/figures_tables/','alignment_summaries/summaries/','accepted_parents/parents/population'])},
        'source_script':str(Path(__file__).resolve()),'source_script_sha256':sha(__file__),
        'lc_display_dictionary':str(lcpath.resolve()),'lc_display_dictionary_sha256':sha(lcpath),
        'runtime':{'python':sys.version,'numpy':np.__version__,'matplotlib':matplotlib.__version__},
        'checks':['exact accepted 9000 scene order','22 descriptors: 15 scalar + 7 compositional','validity agrees with stored nulls','finite coordinate/scalar/vector values','frozen vector category lengths','argmax first-index ties','unchanged selected nine IDs and coordinates','all accepted payloads unchanged before/after'],
        'artifacts':artifacts})
    print('PASS '+str(out/'visualization_manifest.json'),flush=True)

if __name__=='__main__':main()
