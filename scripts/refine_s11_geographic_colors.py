#!/usr/bin/env python
"""Presentation-only palette/layout refinement of accepted fixed UMAP/centers."""
from pathlib import Path
import argparse,csv,json,shutil,sys,hashlib
import numpy as np,pyarrow as pa,pyarrow.parquet as pq,geopandas as gpd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from visualize_s11_geographic_colors import inputs,rgbmap,key,ROOT,RECEIPT,VIZ,NAMES,COMMIT
from revisualize_s11_publication import snapshot,unchanged,write_json,sha,run
OLD=VIZ/'20260924_0130_umap_2d_colormap_geographic_transfer'
GU=Path('/mnt/hdd002/dhnyu/fusedata/koreaadmin/bnd_sigungu_00_2025_2Q.shp')

def gu():
    src=gpd.read_file(GU);s=src.loc[src.SIGUNGU_CD.str.startswith('11')].copy();assert len(s)==25 and s.geometry.is_valid.all();return s.to_crs(5186)

def draw(ax,xy,rgba,geo=False,b=None,size=4):
    if geo:
        b.boundary.plot(ax=ax,color='#dedede',linewidth=.28,zorder=0)
    sc=ax.scatter(*xy.T,c=rgba,s=size,linewidths=0,zorder=2)
    assert np.array_equal(sc.get_facecolors(),rgba) and np.array_equal(np.asarray(sc.get_offsets()),xy)
    ax.set_aspect('equal')
    if geo:ax.set_axis_off()
    else:
        ax.spines[['top','right']].set_visible(False);ax.set(xlabel='UMAP 1',ylabel='UMAP 2');ax.tick_params(labelsize=8)
    return sc

def save(fig,out,name,dpi=250):
    fig.savefig(out/(name+'.pdf'),metadata={'CreationDate':None,'ModDate':None});fig.savefig(out/(name+'.png'),dpi=dpi);plt.close(fig)

def main():
    p=argparse.ArgumentParser();p.add_argument('phase',choices=['preview','tune','final','verify']);p.add_argument('--output',type=Path,required=True);p.add_argument('--selected',choices=NAMES);p.add_argument('--scale',type=float,default=.8);p.add_argument('--alpha',type=float,default=1);a=p.parse_args();out=a.output
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'axes.labelsize':9,'axes.titlesize':11,'pdf.fonttype':42})
    oldmeta=json.loads((OLD/'figure_metadata.json').read_text())
    if a.phase=='preview':
        assert not out.exists();base=json.loads((OLD/'preservation_snapshot.json').read_text());unchanged(base)
        oldman=json.loads((OLD/'visualization_manifest.json').read_text())
        for path,h in oldman['payload_sha256'].items():assert sha(path)==h
        assert sha(oldman['source_script'])==oldman['source_script_sha256']
        base.update(snapshot(p for p in VIZ.rglob('*') if p.is_file()));base.update(snapshot(GU.with_suffix(e) for e in ['.shp','.dbf','.shx','.prj','.cpg']))
        receipt=json.loads(RECEIPT.read_text());assert receipt['status']=='PASS'
        for path,h in receipt['verified_payload_hashes'].items():assert sha(path)==h
        out.mkdir();write_json(out/'preservation_snapshot.json',base)
        shutil.copytree(OLD/'reference_source',out/'reference_source',ignore=shutil.ignore_patterns('__pycache__'))
        write_json(out/'reference_source/adoption.json',{'source':str(OLD/'reference_source'),'commit':COMMIT,'version':'1.1.7','license':'Apache-2.0','adopted_source_hashes':snapshot(p for p in (OLD/'reference_source').rglob('*') if p.is_file() and '__pycache__' not in str(p))})
    cm,ids,xy,geo,ranges=inputs(out)
    assert ranges==[tuple(r) for r in oldmeta['normalization_ranges']]
    assert sha(ROOT/'umap/coordinates/coordinates.parquet')==oldmeta['coordinate_sha256'] and sha(ROOT/'accepted_parents/parents/population.parquet')==oldmeta['centers_sha256']
    if a.phase=='verify':
        table=pq.read_table(out/'scene_color_mapping.parquet');name=table['colormap_name'][0].as_py();alpha=table['A'][0].as_py();cmap,rgb=rgbmap(cm,name,xy,ranges)
        rebuilt=pa.table({'scene_id':ids,'accepted_scene_index':np.arange(9000,dtype=np.int64),'UMAP1':xy[:,0],'UMAP2':xy[:,1],'center_x':geo[:,0],'center_y':geo[:,1],'R':rgb[:,0],'G':rgb[:,1],'B':rgb[:,2],'A':np.full(9000,alpha,dtype=float),'colormap_name':[name]*9000})
        assert rebuilt.equals(table);sink=pa.BufferOutputStream();pq.write_table(rebuilt,sink,compression='zstd');assert hashlib.sha256(sink.getvalue().to_pybytes()).hexdigest()==sha(out/'scene_color_mapping.parquet');print('Fresh process mapping/Parquet bytes PASS');return
    b=gu()
    if a.phase=='preview':
        fig=plt.figure(figsize=(12,18));gs=fig.add_gridspec(6,3,width_ratios=[1,1.05,.35],left=.06,right=.98,bottom=.035,top=.965,hspace=.40,wspace=.14)
        for i,name in enumerate(NAMES):
            cmap,rgb=rgbmap(cm,name,xy,ranges);rgba=np.column_stack([rgb/255,np.ones(9000)])
            ax=fig.add_subplot(gs[i,0]);draw(ax,xy,rgba,size=4);ax.set_title(name+' — UMAP',loc='left')
            ax=fig.add_subplot(gs[i,1]);draw(ax,geo,rgba,True,b,size=5.6);ax.set_title('Seoul: same scene colors',loc='left')
            container=fig.add_subplot(gs[i,2]);container.axis('off');k=container.inset_axes([.05,.35,.90,.38]);key(k,cmap,ranges);k.set_title('2D key',fontsize=8);k.xaxis.label.set_size(7);k.yaxis.label.set_size(7)
        fig.suptitle('Fixed global normalization and identical rendering for all candidates',fontsize=12,y=.991);save(fig,out,'colormap_comparison_v2',180)
        print('PREVIEW READY '+str(out));return
    assert a.selected
    cmap,rgb=rgbmap(cm,a.selected,xy,ranges);rgba=np.column_stack([rgb/255,np.full(9000,a.alpha)])
    if a.phase=='tune':
        with PdfPages(out/'point_alpha_comparison.pdf',metadata={'CreationDate':None,'ModDate':None}) as pdf:
            for scale in [1,.8,1.1]:
                fig,axes=plt.subplots(3,2,figsize=(11,14),layout='constrained')
                for row,alpha in enumerate([.85,.95,1.]):
                    trial=rgba.copy();trial[:,3]=alpha;draw(axes[row,0],xy,trial,size=5*scale);draw(axes[row,1],geo,trial,True,b,size=7*scale)
                    axes[row,0].set_title(f'{a.selected}: size {5*scale:g}, alpha {alpha}');axes[row,1].set_title(f'Seoul: size {7*scale:g}, alpha {alpha}')
                pdf.savefig(fig);fig.savefig(out/f'point_alpha_comparison_scale_{scale:g}.png',dpi=150);plt.close(fig)
        print('TUNING READY');return
    assert a.scale in [1,.8,1.1] and a.alpha in [.85,.95,1]
    table=pa.table({'scene_id':ids,'accepted_scene_index':np.arange(9000,dtype=np.int64),'UMAP1':xy[:,0],'UMAP2':xy[:,1],'center_x':geo[:,0],'center_y':geo[:,1],'R':rgb[:,0],'G':rgb[:,1],'B':rgb[:,2],'A':np.full(9000,a.alpha,dtype=float),'colormap_name':[a.selected]*9000})
    pq.write_table(table,out/'scene_color_mapping.parquet',compression='zstd')
    with (out/'scene_color_mapping.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=table.column_names);w.writeheader();w.writerows(table.to_pylist())
    layout={}
    for suffix in ['','_no_title']:
        fig=plt.figure(figsize=(14,6.5));left=fig.add_axes([.055,.24,.43,.71]);right=fig.add_axes([.565,.22,.38,.73]);legend=fig.add_axes([.239,.065,1.0816/14,.71825/6.5])
        l=draw(left,xy,rgba,size=5*a.scale);r=draw(right,geo,rgba,True,b,size=7*a.scale);assert np.array_equal(l.get_facecolors(),r.get_facecolors())
        left.set_title('(a) FM representation space',loc='left');right.set_title('(b) Geographic distribution in Seoul',loc='left');key(legend,cmap,ranges);legend.xaxis.label.set_size(8);legend.yaxis.label.set_size(8);legend.tick_params(labelsize=6.5)
        fig.canvas.draw();W,H=fig.get_size_inches();lb=left.get_position().bounds;rb=right.get_position().bounds
        layout={'UMAP_plot_inches':[lb[2]*W,lb[3]*H],'Seoul_plot_inches':[rb[2]*W,rb[3]*H],'actual_width_ratio':rb[2]/lb[2],'key_inches':[1.0816,.71825],'key_linear_scale_vs_previous':.65,'figure_inches':[W,H],'overall_title':False}
        save(fig,out,'umap_geographic_color_transfer_v2'+suffix,300)
    # Same palette and windows as previous locator; purely descriptive display.
    windows={'central-lower':[-1.5,1.2,8.1,10.2],'left-lower':[-3.5,-2.3,-.75,.75],'right-lower':[15.5,16.22,3.98,4.62]}
    fig,axes=plt.subplots(1,3,figsize=(13,5),layout='constrained')
    for ax,(name,(x0,x1,y0,y1)) in zip(axes,windows.items()):
        mask=(xy[:,0]>=x0)&(xy[:,0]<=x1)&(xy[:,1]>=y0)&(xy[:,1]<=y1);b.boundary.plot(ax=ax,color='#e3e3e3',linewidth=.28);ax.scatter(*geo.T,s=2,c='#ececec',linewidths=0);ax.scatter(*geo[mask].T,s=7*a.scale,c=rgba[mask],linewidths=0);ax.set_aspect('equal');ax.set_axis_off();ax.set_title(name+' UMAP portion')
    save(fig,out,'lower_island_locator_v2')
    lut=cmap.get_cmap_data();ix=np.rint((xy[:,0]-ranges[0][0])*(lut.shape[0]-1)/(ranges[0][1]-ranges[0][0])).astype(int);iy=np.rint((xy[:,1]-ranges[1][0])*(lut.shape[1]-1)/(ranges[1][1]-ranges[1][0])).astype(int);assert np.array_equal(lut[ix,iy],rgb)
    assert pq.read_table(out/'scene_color_mapping.parquet').equals(table)
    csvrows=list(csv.DictReader((out/'scene_color_mapping.csv').open()))
    for r,e in zip(csvrows,table.to_pylist(),strict=True):
        for k,v in e.items():assert (float(r[k])==v if isinstance(v,float) else int(r[k])==v if isinstance(v,int) else r[k]==v)
    oldtable=pq.read_table(OLD/'scene_color_mapping.parquet')
    for c in ['scene_id','accepted_scene_index','UMAP1','UMAP2','center_x','center_y']:assert table[c].equals(oldtable[c])
    result=run(sys.executable,Path(__file__),'verify','--output',out);print(result,flush=True)
    write_json(out/'validation.json',{'status':'PASS','scene_count':9000,'exact_order_coordinates_centers':True,'no_missing_colors_or_nonfinite_coordinates':True,'all_scene_left_right_RGBA_exact':True,'all_scene_direct_LUT_parity':True,'CSV_Parquet_readback':True,'fresh_process_Parquet_bytes_identical':True,'geo_axes_removed':True,'Seoul_sigungu_count':len(b)})
    write_json(out/'figure_metadata.json',{'source_metadata':str(OLD/'figure_metadata.json'),'source_metadata_sha256':sha(OLD/'figure_metadata.json'),'input_coordinate_sha256':oldmeta['coordinate_sha256'],'input_centers_sha256':oldmeta['centers_sha256'],'accepted_receipt':str(RECEIPT),'receipt_sha256':sha(RECEIPT),'selected_colormap':a.selected,'normalization_ranges':ranges,'palette_commit':COMMIT,'package_version':'1.1.7','license':'Apache-2.0','runtime':oldmeta['runtime'],'point_sizes_pt2':{'UMAP':5*a.scale,'Seoul':7*a.scale},'alpha':a.alpha,'layout':layout,'background':{'source':str(GU),'feature_selector':'SIGUNGU_CD starts with 11','features':25,'source_crs':str(gpd.read_file(GU).crs),'display_crs':'EPSG:5186','center_transform':False,'boundary_transform':'GeoPandas.to_crs(5186), pyproj always_xy','line_color':'#dedede','line_width_pt':.28,'fill':'none','grid_or_scene_boundaries':False,'axes':'off'},'limitations':oldmeta['limitations'],'scientific_recomputation':False})
    unchanged(json.loads((out/'preservation_snapshot.json').read_text()))
    write_json(out/'visualization_manifest.json',{'status':'PASS','S11_unchanged':1352,'S12_unchanged':27427,'previous_visualizations_dissertation_unchanged':True,'scientific_analysis':False,'source_script':str(Path(__file__).resolve()),'source_script_sha256':sha(__file__),'payload_sha256':snapshot(p for p in out.rglob('*') if p.is_file() and '__pycache__' not in str(p) and p.name!='visualization_manifest.json')})
    print('FINAL READY '+str(out))
if __name__=='__main__':main()
