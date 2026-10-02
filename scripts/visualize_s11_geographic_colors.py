#!/usr/bin/env python
"""Transfer fixed accepted UMAP colors to accepted geographic centers; presentation only."""
from pathlib import Path
import argparse,csv,json,hashlib,sys,shutil,platform,subprocess
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np,pyarrow as pa,pyarrow.parquet as pq
import geopandas as gpd,pyproj
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from revisualize_s11_publication import ROOT,RECEIPT,sha,snapshot,unchanged,write_json,run
VIZ=Path('/mnt/hdd002/dhnyu/fusedata/analysis_data/reduced/s11_visualization_only')
PRIOR=VIZ/'20260924_0102_main_umap_ai_lcdem_balanced_selection'
BOUNDARY=Path('/mnt/hdd002/dhnyu/fusedata/koreaadmin/bnd_sido_00_2025_2Q.shp')
NAMES=['Bremm','CubeDiagonal','Schumann','Steiger','Teuling2','Ziegler']
COMMIT='39dcc39ba4a66cface620fe068b596ef571570ed'

def inputs(out):
    sys.path.insert(0,str(out/'reference_source'));import pycolormap_2d as cm
    c=pq.read_table(ROOT/'umap/coordinates/coordinates.parquet').to_pydict();p=pq.read_table(ROOT/'accepted_parents/parents/population.parquet').to_pydict()
    assert len(c['scene_id'])==len(set(c['scene_id']))==9000 and c['scene_id']==p['scene_id']
    xy=np.column_stack([c['x'],c['y']]);geo=np.column_stack([p['center_x'],p['center_y']]);assert np.isfinite(xy).all() and np.isfinite(geo).all()
    ranges=[tuple(map(float,[xy[:,k].min(),xy[:,k].max()])) for k in [0,1]]
    return cm,c['scene_id'],xy,geo,ranges

def rgbmap(cm,name,xy,ranges):
    cmap=getattr(cm,'ColorMap2D'+name)(range_x=ranges[0],range_y=ranges[1]);rgb=np.array([cmap(float(x),float(y)) for x,y in xy]);assert rgb.shape==(9000,3) and rgb.dtype==np.uint8
    return cmap,rgb

def boundary():
    src=gpd.read_file(BOUNDARY);s=src.loc[src.SIDO_CD=='11'];assert len(s)==1 and s.SIDO_NM.iloc[0]=='서울특별시' and s.geometry.is_valid.all()
    return s.to_crs(5186)

def key(ax,cmap,ranges):
    # LUT axes are [x,y,channel]; transpose solely for conventional image row/column axes.
    ax.imshow(cmap.get_cmap_data().transpose(1,0,2),origin='lower',extent=[*ranges[0],*ranges[1]],interpolation='nearest',aspect='auto')
    ax.set(xlabel='UMAP 1',ylabel='UMAP 2');ax.set_xticks(ranges[0]);ax.set_yticks(ranges[1]);ax.tick_params(labelsize=7)
    from matplotlib.ticker import FormatStrFormatter
    ax.xaxis.set_major_formatter(FormatStrFormatter('%.1f'));ax.yaxis.set_major_formatter(FormatStrFormatter('%.1f'))

def draw(ax,xy,rgba,geography=False,b=None,size=4):
    if geography:b.plot(ax=ax,facecolor='#fafafa',edgecolor='#b5b5b5',linewidth=.65,zorder=0)
    sc=ax.scatter(xy[:,0],xy[:,1],c=rgba,s=size,linewidths=0,zorder=2)
    assert np.array_equal(sc.get_facecolors(),rgba) and np.array_equal(np.asarray(sc.get_offsets()),xy)
    ax.set_aspect('equal');ax.spines[['top','right']].set_visible(False)
    ax.set(xlabel='Easting (m; EPSG:5186)' if geography else 'UMAP 1',ylabel='Northing (m; EPSG:5186)' if geography else 'UMAP 2')
    if geography:ax.ticklabel_format(axis='both',style='plain',useOffset=False);ax.locator_params(axis='both',nbins=4)
    ax.tick_params(labelsize=8)
    return sc

def save(fig,out,name):
    fig.savefig(out/(name+'.pdf'),metadata={'CreationDate':None,'ModDate':None});fig.savefig(out/(name+'.png'),dpi=220);plt.close(fig)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('phase',choices=['preview','final','verify']);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--selected',choices=NAMES);a=ap.parse_args();out=a.output
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'axes.labelsize':9,'axes.titlesize':11,'pdf.fonttype':42})
    if a.phase=='preview':
        assert not out.exists();base=json.loads((PRIOR/'preservation_snapshot.json').read_text());unchanged(base);base.update(snapshot(p for p in VIZ.rglob('*') if p.is_file()));base.update(snapshot(BOUNDARY.with_suffix(ext) for ext in ['.shp','.shx','.dbf','.prj','.cpg']))
        rec=json.loads(RECEIPT.read_text());assert rec['status']=='PASS'
        for p,h in rec['verified_payload_hashes'].items():assert sha(p)==h
        out.mkdir();write_json(out/'preservation_snapshot.json',base)
        ref=Path('/tmp/s11_pycolormap_2d_reference');assert run('git','-C',ref,'rev-parse','HEAD').strip()==COMMIT
        (out/'reference_source').mkdir()
        shutil.copytree(ref/'pycolormap_2d',out/'reference_source/pycolormap_2d')
        for n in ['LICENSE','README.md','pyproject.toml']:shutil.copy2(ref/n,out/'reference_source'/n)
        write_json(out/'reference_source/provenance.json',{'url':'https://github.com/spinthil/pycolormap-2d','commit':COMMIT,'version':'1.1.7','license':'Apache-2.0','source_hashes':snapshot(p for p in (out/'reference_source').rglob('*') if p.is_file()),'runtime_installation':False})
    cm,ids,xy,geo,ranges=inputs(out)
    if a.phase=='verify':
        expected=pq.read_table(out/'scene_color_mapping.parquet');sel=expected['colormap_name'][0].as_py();cmap,rgb=rgbmap(cm,sel,xy,ranges)
        rebuilt=pa.table({'scene_id':ids,'accepted_scene_index':np.arange(9000,dtype=np.int64),'UMAP1':xy[:,0],'UMAP2':xy[:,1],'center_x':geo[:,0],'center_y':geo[:,1],'R':rgb[:,0],'G':rgb[:,1],'B':rgb[:,2],'A':np.ones(9000,dtype=np.uint8),'colormap_name':[sel]*9000})
        assert rebuilt.equals(expected);sink=pa.BufferOutputStream();pq.write_table(rebuilt,sink,compression='zstd');assert hashlib.sha256(sink.getvalue().to_pybytes()).hexdigest()==sha(out/'scene_color_mapping.parquet')
        print('Fresh-process deterministic table and Parquet bytes PASS');return
    b=boundary()
    if a.phase=='preview':
        fig,ax=plt.subplots(6,3,figsize=(12,22),gridspec_kw={'width_ratios':[.55,1,1.2]},layout='constrained')
        for i,name in enumerate(NAMES):
            cmap,rgb=rgbmap(cm,name,xy,ranges);rgba=np.column_stack([rgb/255,np.ones(9000)])
            key(ax[i,0],cmap,ranges);ax[i,0].set_title(name);draw(ax[i,1],xy,rgba);draw(ax[i,2],geo,rgba,True,b)
            ax[i,1].set_title('Fixed UMAP');ax[i,2].set_title('Same colors in Seoul')
        fig.suptitle('2D colormap comparison — global UMAP normalization; 9,000 scenes',fontsize=13);save(fig,out,'colormap_comparison')
        write_json(out/'preview_metadata.json',{'ranges':ranges,'candidate_order':NAMES,'boundary_source_crs':'EPSG:5179','plot_crs':'EPSG:5186','center_transform':False,'boundary_transform':pyproj.Transformer.from_crs(5179,5186,always_xy=True).description})
        print('PREVIEW READY '+str(out));return
    assert a.selected
    cmap,rgb=rgbmap(cm,a.selected,xy,ranges);rgba=np.column_stack([rgb/255,np.ones(9000)])
    table=pa.table({'scene_id':ids,'accepted_scene_index':np.arange(9000,dtype=np.int64),'UMAP1':xy[:,0],'UMAP2':xy[:,1],'center_x':geo[:,0],'center_y':geo[:,1],'R':rgb[:,0],'G':rgb[:,1],'B':rgb[:,2],'A':np.ones(9000,dtype=np.uint8),'colormap_name':[a.selected]*9000})
    pq.write_table(table,out/'scene_color_mapping.parquet',compression='zstd')
    with (out/'scene_color_mapping.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=table.column_names);w.writeheader();w.writerows(table.to_pylist())
    # Bounded opacity display check; colors never change between paired panels.
    fig,axes=plt.subplots(2,2,figsize=(11,10),layout='constrained')
    for i,alpha in enumerate([.85,1.]):
        trial=rgba.copy();trial[:,3]=alpha;draw(axes[i,0],xy,trial,size=4);draw(axes[i,1],geo,trial,True,b,size=6);axes[i,0].set_title(f'UMAP; alpha {alpha}');axes[i,1].set_title(f'Seoul; alpha {alpha}')
    save(fig,out,'alpha_comparison')
    for title in [True,False]:
        fig=plt.figure(figsize=(12.8,6.5));left=fig.add_axes([.06,.35,.39,.58]);right=fig.add_axes([.54,.12,.43,.81]);legend=fig.add_axes([.205,.06,.13,.17])
        lsc=draw(left,xy,rgba,size=5);rsc=draw(right,geo,rgba,True,b,size=7);assert np.array_equal(lsc.get_facecolors(),rsc.get_facecolors())
        left.set_title('(a) FM representation space',loc='left');right.set_title('(b) Geographic distribution in Seoul',loc='left');key(legend,cmap,ranges)
        if title:fig.suptitle('Mapping the FM representation space to geographic space',fontsize=14,y=.995)
        name='umap_geographic_color_transfer'+('' if title else '_no_title');save(fig,out,name)
    # Supplementary position-only locator views to audit each named lower portion independently.
    windows={'central-lower':[-1.5,1.2,8.1,10.2],'left-lower':[-3.5,-2.3,-.75,.75],'right-lower':[15.5,16.22,3.98,4.62]}
    fig,axes=plt.subplots(1,3,figsize=(13,5),layout='constrained')
    sample=[0,4499,8999];sample_info=[]
    for ax,(name,(x0,x1,y0,y1)) in zip(axes,windows.items()):
        mask=(xy[:,0]>=x0)&(xy[:,0]<=x1)&(xy[:,1]>=y0)&(xy[:,1]<=y1);b.plot(ax=ax,facecolor='#fafafa',edgecolor='#bbb',linewidth=.5);ax.scatter(*geo.T,s=2,c='#e4e4e4',linewidths=0);ax.scatter(*geo[mask].T,s=9,c=rgba[mask],linewidths=0);ax.set_title(name+' UMAP portion');ax.set_aspect('equal');ax.set_axis_off();sample.append(int(np.flatnonzero(mask)[0]))
    save(fig,out,'lower_island_geographic_locator')
    sample.extend([ids.index(r['scene_id']) for r in json.loads((PRIOR/'figure_metadata.json').read_text())['selection'][:9]])
    lut=cmap.get_cmap_data()
    for i in sorted(set(sample)):
        # Independent direct index lookup reproduces the pinned upstream arithmetic.
        ix=round((float(xy[i,0])-ranges[0][0])*(lut.shape[0]-1)/(ranges[0][1]-ranges[0][0]));iy=round((float(xy[i,1])-ranges[1][0])*(lut.shape[1]-1)/(ranges[1][1]-ranges[1][0]));assert np.array_equal(lut[ix,iy],rgb[i]);sample_info.append({'index':i,'scene_id':ids[i],'RGB':rgb[i].tolist(),'left_right_exact':True,'direct_LUT_check':True})
    assert pq.read_table(out/'scene_color_mapping.parquet').equals(table)
    csvrows=list(csv.DictReader((out/'scene_color_mapping.csv').open()))
    for r,e in zip(csvrows,table.to_pylist(),strict=True):
        for k,v in e.items():assert (float(r[k])==v if isinstance(v,float) else int(r[k])==v if isinstance(v,int) else r[k]==v)
    write_json(out/'validation.json',{'status':'PASS','population':9000,'IDs_order_exact':True,'coordinates_exact':True,'all_9000_collection_facecolors_exact_in_both_panels':True,'CSV_Parquet_exact_readback':True,'independent_samples':sample_info,'NaN_Inf':False})
    write_json(out/'figure_metadata.json',{'scope':'visualization only','colormap':a.selected,'reference_commit':COMMIT,'package_version':'1.1.7','license':'Apache-2.0','normalization_ranges':ranges,'normalization':'Upstream nearest-LUT sampling: global min/max of all 9000; x/y lookup, ties-to-even rounding. No rotations, island scaling, geographic or descriptor inputs. LUT is quantized uint8 rather than a mathematically injective continuous function.','RGB_encoding':'uint8 0..255; A=1 means opaque','alpha':1,'point_sizes_pt2':{'UMAP':5,'geography':7},'accepted_receipt':str(RECEIPT),'receipt_sha256':sha(RECEIPT),'coordinate_sha256':sha(ROOT/'umap/coordinates/coordinates.parquet'),'centers_sha256':sha(ROOT/'accepted_parents/parents/population.parquet'),'geographic_CRS':'EPSG:5186','center_transform':False,'boundary_source':str(BOUNDARY),'boundary_source_CRS':'EPSG:5179','boundary_display_transform':'pyproj/PROJ EPSG:5179 to EPSG:5186, always_xy=True; geopandas.to_crs','runtime':{'python':platform.python_version(),'numpy':np.__version__,'matplotlib':matplotlib.__version__,'pyarrow':pa.__version__,'geopandas':gpd.__version__,'pyproj':pyproj.__version__,'PROJ':pyproj.proj_version_str},'limitations':'UMAP nonlinear projection; colors encode only fixed 2D coordinates, not semantic classes or 256D metric distance. Similar color need not imply unique nearby 2D locations; finite LUT and perceptual ambiguity. No validity, causal, independence or geographic-smoothness claim.','island_locator':'Supplementary fixed coordinate-window display only; no clustering or new statistical metric.'})
    print(run(sys.executable,Path(__file__),'verify','--output',out),flush=True)
    unchanged(json.loads((out/'preservation_snapshot.json').read_text()))
    write_json(out/'visualization_manifest.json',{'status':'PASS','S11_unchanged':1352,'S12_unchanged':27427,'previous_visualizations_dissertation_unchanged':True,'scientific_analysis':False,'fresh_process_table_bytes_identical':True,'source_script':str(Path(__file__).resolve()),'source_script_sha256':sha(__file__),'payload_sha256':snapshot(p for p in out.rglob('*') if p.is_file() and '__pycache__' not in str(p) and p.name!='visualization_manifest.json')})
    print('FINAL READY '+str(out))
if __name__=='__main__':main()
