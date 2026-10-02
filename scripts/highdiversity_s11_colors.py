#!/usr/bin/env python
"""Distribution-equalized display colors only; accepted positions remain immutable."""
from pathlib import Path
import argparse,csv,json,shutil,sys,hashlib,platform
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np,pyarrow as pa,pyarrow.parquet as pq
from scipy.stats import rankdata
from scipy.spatial import cKDTree
from scipy.ndimage import gaussian_filter
from scipy.interpolate import RegularGridInterpolator
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import hsv_to_rgb
from refine_s11_geographic_colors import gu,draw
from visualize_s11_geographic_colors import inputs,rgbmap,ROOT,RECEIPT,VIZ,NAMES,COMMIT
from revisualize_s11_publication import snapshot,unchanged,write_json,sha,run
OLD=VIZ/'20260924_0142_umap_geographic_color_transfer_refined'
PALETTES=NAMES+['HueChromaSweep','OpponentHueDisk']
STRATEGIES=['raw','marginal_cdf','winsor_cdf','conditional_equalized']

def transforms(xy):
    n=len(xy);lo=xy.min(axis=0);hi=xy.max(axis=0);raw=(xy-lo)/(hi-lo)
    cdf=np.column_stack([(rankdata(xy[:,j],method='average')-1)/(n-1) for j in range(2)])
    bounds=np.quantile(xy,[.01,.99],axis=0,method='linear');wins=np.clip(xy,bounds[0],bounds[1]);wcdf=np.column_stack([(rankdata(wins[:,j],method='average')-1)/(n-1) for j in range(2)])
    # Histogram-based smooth conditional CDF (Rosenblatt-like), a display candidate only.
    hist=np.histogram2d(cdf[:,0],cdf[:,1],bins=32,range=[[0,1],[0,1]])[0]
    smooth=gaussian_filter(hist,sigma=1.0,mode='nearest')+.5
    conditional=np.column_stack([np.zeros(32),np.cumsum(smooth/smooth.sum(axis=1,keepdims=True),axis=1)])
    xc=(np.arange(32)+.5)/32;xc=np.r_[0,xc,1];values=np.vstack([conditional[:1],conditional,conditional[-1:]])
    inter=RegularGridInterpolator((xc,np.linspace(0,1,33)),values,method='linear',bounds_error=True)
    de=np.column_stack([cdf[:,0],inter(cdf)])
    for arr in [raw,cdf,wcdf,de]:assert np.isfinite(arr).all() and arr.min()>=0 and arr.max()<=1
    return dict(zip(STRATEGIES,[raw,cdf,wcdf,de])),{'raw_bounds':[lo.tolist(),hi.tolist()],'winsor_limits_type7_p01_p99':bounds.tolist(),'conditional_histogram':hist.tolist(),'conditional_x_knots':xc.tolist(),'conditional_cdf_values':values.tolist(),'conditional_sigma_bins':1.0,'pseudocount_after_smoothing':.5}

def colors(cm,name,uv):
    if name=='OpponentHueDisk':
        dx=uv[:,0]-.5;dy=uv[:,1]-.5;r=np.sqrt(dx*dx+dy*dy)/np.sqrt(.5)
        h=(np.arctan2(dy,dx)/(2*np.pi)+.08)%1;ss=.92*r;vv=.94-.22*r+.06*dy
        return np.rint(hsv_to_rgb(np.column_stack([h,ss,vv]))*255).astype(np.uint8)
    if name=='HueChromaSweep':
        h=.02+.78*uv[:,0]+.12*uv[:,1];s=.45+.50*uv[:,1];v=.95-.18*uv[:,1]
        return np.rint(hsv_to_rgb(np.column_stack([h,s,v]))*255).astype(np.uint8)
    cmap=getattr(cm,'ColorMap2D'+name)(range_x=(0.,1.),range_y=(0.,1.))
    return np.array([cmap(float(x),float(y)) for x,y in uv])

def neighbors(xy,ids):
    tree=cKDTree(xy);distance,_=tree.query(xy,k=2);out=[]
    for i,d in enumerate(distance[:,1]):
        cand=[k for k in tree.query_ball_point(xy[i],np.nextafter(d,np.inf)) if k!=i]
        assert cand
        out.append(min(cand,key=lambda k:(float(((xy[k]-xy[i])**2).sum()),ids[k])))
    return np.array(out)

def summarize(x):
    return dict(zip(['q1','median','q3','p95','max'],map(float,[*np.quantile(x,[.25,.5,.75,.95],method='linear'),x.max()])))

def metrics(uv,rgb,nn,main):
    bins=np.minimum((uv*32).astype(int),31);occ=len(np.unique(bins,axis=0));x=rgb.astype(float)/255
    nd=np.sqrt(((x-x[nn])**2).sum(axis=1));spread=np.sqrt(((x[main]-np.median(x[main],axis=0))**2).sum(axis=1))
    return {'unique_RGB':len(np.unique(rgb,axis=0)),'main_unique_RGB':len(np.unique(rgb[main],axis=0)),'occupied_32x32_cells':occ,'palette_grid_occupied_fraction':occ/1024,'nearest_UMAP_neighbor_RGB_distance':summarize(nd),'within_main_RGB_distance_to_channelwise_median':summarize(spread),'main_RGB_channel_std':np.std(x[main],axis=0).tolist(),'main_RGB_channel_p10_p90':np.quantile(x[main],[.1,.9],axis=0,method='linear').tolist()}

def key(ax,cm,palette,strategy):
    xx,yy=np.meshgrid(np.linspace(0,1,256),np.linspace(0,1,256));im=colors(cm,palette,np.column_stack([xx.ravel(),yy.ravel()])).reshape(256,256,3)
    ax.imshow(im,origin='lower',extent=[0,1,0,1],interpolation='nearest',aspect='auto');ax.set_xticks([0,.5,1]);ax.set_yticks([0,.5,1]);ax.tick_params(labelsize=6)
    labels={'raw':('linear UMAP 1','linear UMAP 2'),'marginal_cdf':('CDF(UMAP 1)','CDF(UMAP 2)'),'winsor_cdf':('CDF(winsor x)','CDF(winsor y)'),'conditional_equalized':('CDF(UMAP 1)','conditional CDF y')}
    ax.set_xlabel(labels[strategy][0],fontsize=7);ax.set_ylabel(labels[strategy][1],fontsize=7)

def save(fig,out,name,dpi=230):
    fig.savefig(out/(name+'.pdf'),metadata={'CreationDate':None,'ModDate':None});fig.savefig(out/(name+'.png'),dpi=dpi);plt.close(fig)

def mapping_table(ids,xy,geo,uv,rgb,strategy,palette):
    return pa.table({'scene_id':ids,'accepted_scene_index':np.arange(9000,dtype=np.int64),'UMAP1':xy[:,0],'UMAP2':xy[:,1],'center_x':geo[:,0],'center_y':geo[:,1],'color_u':uv[:,0],'color_v':uv[:,1],'R':rgb[:,0],'G':rgb[:,1],'B':rgb[:,2],'A':np.ones(9000),'normalization':[strategy]*9000,'palette':[palette]*9000})

def main():
    ap=argparse.ArgumentParser();ap.add_argument('phase',choices=['search','extend','final','verify']);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--strategy',choices=STRATEGIES);ap.add_argument('--palette',choices=PALETTES);a=ap.parse_args();out=a.output
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'axes.labelsize':9,'axes.titlesize':11,'pdf.fonttype':42})
    if a.phase=='search':
        assert not out.exists();baseline=json.loads((OLD/'preservation_snapshot.json').read_text());unchanged(baseline)
        oldman=json.loads((OLD/'visualization_manifest.json').read_text())
        for p,h in oldman['payload_sha256'].items():assert sha(p)==h
        assert sha(oldman['source_script'])==oldman['source_script_sha256']
        baseline.update(snapshot(p for p in VIZ.rglob('*') if p.is_file()))
        receipt=json.loads(RECEIPT.read_text());assert receipt['status']=='PASS'
        for p,h in receipt['verified_payload_hashes'].items():assert sha(p)==h
        out.mkdir();write_json(out/'preservation_snapshot.json',baseline)
        shutil.copytree(OLD/'reference_source',out/'reference_source',ignore=shutil.ignore_patterns('__pycache__'))
        write_json(out/'reference_source_adoption.json',{'source':str(OLD/'reference_source'),'hashes':snapshot(p for p in (OLD/'reference_source').rglob('*') if p.is_file() and '__pycache__' not in str(p))})
    cm,ids,xy,geo,ranges=inputs(out);alluv,tmeta=transforms(xy)
    oldmeta=json.loads((OLD/'figure_metadata.json').read_text());assert ranges==[tuple(x) for x in oldmeta['normalization_ranges']]
    if a.phase=='verify':
        expected=pq.read_table(out/'scene_color_mapping_highdiversity.parquet');strategy=expected['normalization'][0].as_py();palette=expected['palette'][0].as_py();uv=alluv[strategy];rgb=colors(cm,palette,uv);actual=mapping_table(ids,xy,geo,uv,rgb,strategy,palette);assert expected.equals(actual)
        sink=pa.BufferOutputStream();pq.write_table(actual,sink,compression='zstd');assert hashlib.sha256(sink.getvalue().to_pybytes()).hexdigest()==sha(out/'scene_color_mapping_highdiversity.parquet');print('Fresh process exact mapping and Parquet bytes PASS');return
    b=gu();mainmask=(xy[:,0]>=-3.5)&(xy[:,0]<=4)&(xy[:,1]>=10.5)&(xy[:,1]<=18)
    if a.phase in ['search','extend']:
        nn=neighbors(xy,ids);np.save(out/'display_neighbor_indices.npy',nn,allow_pickle=False)
        results={};rgbs={}
        for strategy in STRATEGIES:
            for palette in PALETTES:
                k=strategy+'__'+palette;rgbs[k]=colors(cm,palette,alluv[strategy]);results[k]=metrics(alluv[strategy],rgbs[k],nn,mainmask)
        # Exact prior raw baseline: upstream direct ranges can differ at a numerical rounding boundary.
        previous=pq.read_table(OLD/'scene_color_mapping.parquet').to_pydict();oldrgb=np.column_stack([previous[k] for k in ['R','G','B']]);results['previous_raw__Teuling2']=metrics(alluv['raw'],oldrgb,nn,mainmask)
        write_json(out/'color_quality_metrics.json',results);write_json(out/'transform_specification.json',tmeta)
        np.savez_compressed(out/'candidate_RGB.npz',**rgbs)
        shortlist=['raw__Teuling2','marginal_cdf__Teuling2','marginal_cdf__Bremm','marginal_cdf__CubeDiagonal','marginal_cdf__Ziegler','marginal_cdf__HueChromaSweep','marginal_cdf__OpponentHueDisk','winsor_cdf__OpponentHueDisk','conditional_equalized__OpponentHueDisk']
        write_json(out/'comparison_shortlist.json',{'candidates':shortlist,'rule':'Initial eight-candidate search followed by one bounded custom extension to address x-dominated hue bands. Final nine-panel sheet includes raw baseline, four CDF built-ins, two custom CDF palettes and C/D for OpponentHueDisk. All 32 metrics retained; no geographic objective.'})
        fig=plt.figure(figsize=(12,27));gs=fig.add_gridspec(9,3,width_ratios=[1,1.05,.38],left=.055,right=.985,bottom=.025,top=.975,hspace=.44,wspace=.15)
        for i,k in enumerate(shortlist):
            strategy,palette=k.split('__');rgba=np.column_stack([rgbs[k]/255,np.ones(9000)])
            left=fig.add_subplot(gs[i,0]);draw(left,xy,rgba,size=4);left.set_title(strategy+' / '+palette,fontsize=9,loc='left')
            right=fig.add_subplot(gs[i,1]);draw(right,geo,rgba,True,b,size=5.6);right.set_title('Same scene colors in Seoul',fontsize=9)
            container=fig.add_subplot(gs[i,2]);container.axis('off');ka=container.inset_axes([.07,.42,.84,.36]);key(ka,cm,palette,strategy)
            m=results[k];container.text(.5,.04,f'RGB: {m["unique_RGB"]} / 9000\n32² occupancy: {100*m["palette_grid_occupied_fraction"]:.1f}%',ha='center',fontsize=7)
        fig.suptitle('Visualization-only color search — identical accepted point positions',fontsize=12,y=.993);save(fig,out,'umap_geographic_color_transfer_colorsearch',170)
        flat=[]
        for k,m in results.items():
            st,pal=k.split('__');row={'strategy':st,'palette':pal,'unique_RGB':m['unique_RGB'],'main_unique_RGB':m['main_unique_RGB'],'palette_grid_occupied_fraction':m['palette_grid_occupied_fraction']}
            for prefix,keyname in [('NN','nearest_UMAP_neighbor_RGB_distance'),('main_spread','within_main_RGB_distance_to_channelwise_median')]:row.update({prefix+'_'+q:v for q,v in m[keyname].items()})
            flat.append(row)
        with (out/'color_quality_metrics.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(flat[0]));w.writeheader();w.writerows(flat)
        print('SEARCH READY '+str(out));return
    assert a.strategy and a.palette
    uv=alluv[a.strategy];rgb=colors(cm,a.palette,uv);rgba=np.column_stack([rgb/255,np.ones(9000)]);table=mapping_table(ids,xy,geo,uv,rgb,a.strategy,a.palette)
    pq.write_table(table,out/'scene_color_mapping_highdiversity.parquet',compression='zstd')
    with (out/'scene_color_mapping_highdiversity.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=table.column_names);w.writeheader();w.writerows(table.to_pylist())
    # Store all monotonic CDF knots, enabling replay without refitting any embedding/projection.
    knots=[]
    for j,axis in enumerate(['UMAP1','UMAP2']):
        for value in np.unique(xy[:,j]):knots.append({'axis':axis,'coordinate':float(value),'normalized_average_rank':float(alluv['marginal_cdf'][np.flatnonzero(xy[:,j]==value)[0],j])})
    pq.write_table(pa.Table.from_pylist(knots),out/'marginal_cdf_knots.parquet')
    for suffix in ['','_no_title']:
        fig=plt.figure(figsize=(14,6.7));left=fig.add_axes([.055,.25,.43,.69]);right=fig.add_axes([.565,.23,.38,.71]);legend=fig.add_axes([.22,.065,.12,.13])
        l=draw(left,xy,rgba,size=4);r=draw(right,geo,rgba,True,b,size=5.6);assert np.array_equal(l.get_facecolors(),r.get_facecolors())
        left.set_title('(a) FM representation space',loc='left');right.set_title('(b) Geographic distribution in Seoul',loc='left');key(legend,cm,a.palette,a.strategy)
        fig.canvas.draw();bbox=fig.get_tightbbox(fig.canvas.get_renderer());assert bbox.x0>=0 and bbox.y0>=0 and bbox.x1<=14 and bbox.y1<=6.7
        save(fig,out,'umap_geographic_color_transfer_highdiversity'+suffix,300)
    # Display occupancy comparison in transformed palette coordinates; never used to alter plot positions.
    fig,axes=plt.subplots(1,2,figsize=(8,4),layout='constrained')
    for ax,arr,label in [(axes[0],alluv['raw'],'Previous: raw linear'),(axes[1],uv,'Selected: '+a.strategy)]:
        ax.scatter(*arr.T,c=rgba,s=2,linewidths=0);ax.set(xlim=(0,1),ylim=(0,1),aspect='equal',xlabel='color u',ylabel='color v',title=label)
    save(fig,out,'palette_coordinate_occupancy')
    # Source table readback, same input columns, independent rank/tie check.
    expected=pq.read_table(OLD/'scene_color_mapping.parquet')
    for col in ['scene_id','accepted_scene_index','UMAP1','UMAP2','center_x','center_y']:assert table[col].equals(expected[col])
    for j in range(2):
        sort=np.sort(xy[:,j]);left=np.searchsorted(sort,xy[:,j],side='left');right=np.searchsorted(sort,xy[:,j],side='right');independent=((left+right-1)/2)/(len(xy)-1)
        assert np.array_equal(independent,alluv['marginal_cdf'][:,j])
    assert pq.read_table(out/'scene_color_mapping_highdiversity.parquet').equals(table)
    for row,src in zip(csv.DictReader((out/'scene_color_mapping_highdiversity.csv').open()),table.to_pylist(),strict=True):
        for k,v in src.items():assert (float(row[k])==v if isinstance(v,float) else int(row[k])==v if isinstance(v,int) else row[k]==v)
    print(run(sys.executable,Path(__file__),'verify','--output',out),flush=True)
    write_json(out/'validation.json',{'status':'PASS','scenes':9000,'accepted_positions_ids_order_exact':True,'all_plot_colors_and_offsets_verified':True,'independent_average_rank_all_scenes_exact':True,'fresh_process_Parquet_bytes_identical':True,'CSV_Parquet_readback_all_cells':True,'no_NaN_Inf':True,'all_figure_text_inside_canvas':True})
    meta={'scientific_recomputation':False,'selected_strategy':a.strategy,'selected_palette':a.palette,'position_rule':'unchanged accepted UMAP and EPSG:5186 centers','color_rule':'data-distribution transform only; deterministic function of fixed UMAP and frozen population','rank_formula':'(average_rank - 1)/(9000 - 1), each marginal independently; equal coordinates same color-coordinate; no jitter or scene-ID-derived colors','transforms':tmeta,'custom_opponent_palette':'dx=u-.5, dy=v-.5, r=hypot(dx,dy)/sqrt(.5); H=(atan2(dy,dx)/(2pi)+.08) mod1; S=.92r; V=.94-.22r+.06dy. Saturation tends to zero at center, so angular seam/undefined center hue creates no RGB discontinuity. Not perceptually uniform.', 'custom_palette':'HSV: H=0.02+0.78u+0.12v, S=0.45+0.50v, V=0.95-0.18v; H in [0.02,0.92], no hue wrap. Matplotlib hsv_to_rgb then rint(255*RGB) uint8. Not perceptually uniform.','reference_package':'pycolormap-2d 1.1.7 Apache-2.0; commit '+COMMIT,'input_hashes':{'UMAP':sha(ROOT/'umap/coordinates/coordinates.parquet'),'centers':sha(ROOT/'accepted_parents/parents/population.parquet'),'receipt':sha(RECEIPT)},'previous_metadata':str(OLD/'figure_metadata.json'),'previous_metadata_sha256':sha(OLD/'figure_metadata.json'),'point_sizes_pt2':[4,5.6],'alpha':1,'boundary':oldmeta['background'],'runtime':dict(oldmeta['runtime'],scipy=__import__('scipy').__version__),'quality_definitions':{'unique_RGB':'exact distinct uint8 triplets; not perceptual distinguishability','occupancy':'distinct floor(32*[u,v]) cells with endpoint1 clamped to31, divided by1024; fixed common grid independent of palette LUT resolution','NN':'Euclidean distance of gamma-encoded sRGB/255 to nearest scene in original fixed 2D UMAP; exact distance ties by lexical scene ID; summaries type7. Not DeltaE/JND or scientific similarity.','main_spread':'sRGB/255 distance to componentwise color median over same main display window x[-3.5,4], y[10.5,18]; channel std and p10/p90 also retained. No scientific descriptor.','selection_constraints':'No geography or descriptor drives transform or palette tuning; positions never transformed.'},'limits':'Nonlinear CDF equalizes marginal distributions, not Euclidean geometry. Color differences are descriptive display features, not new scientific evidence or 256D distances. 9000 unique RGB codes cannot guarantee 9000 perceptually separable colors.'}
    write_json(out/'figure_metadata.json',meta);unchanged(json.loads((out/'preservation_snapshot.json').read_text()))
    write_json(out/'visualization_manifest.json',{'status':'PASS','S11_unchanged':1352,'S12_unchanged':27427,'previous_visualizations_dissertation_unchanged':True,'source_script':str(Path(__file__).resolve()),'source_script_sha256':sha(__file__),'payload_sha256':snapshot(p for p in out.rglob('*') if p.is_file() and '__pycache__' not in str(p) and p.name!='visualization_manifest.json')})
    print('FINAL READY '+str(out))
if __name__=='__main__':main()
