#!/usr/bin/env python
"""S11 presentation-only layout V2: unchanged coordinates, values and color mappings.
Manual viewports are display windows, never clusters. No fitting or statistics.
"""
import argparse, csv, json, math, shutil, copy, re
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET
import numpy as np
import pyarrow.parquet as pq
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import colors, font_manager, ticker
from matplotlib.lines import Line2D
from PIL import Image
from revisualize_s11_publication import snapshot, unchanged, run, ROOT, RECEIPT, PREVIOUS, S12, ORIGINAL12, DISS, PRIMARY, FAMILIES, UNITS, ROBUST, INTERPRETIVE, sha, write_json, title

V1=Path('/mnt/hdd002/dhnyu/fusedata/analysis_data/reduced/s11_visualization_only/20260923_1345_publication_revisualization')
WINDOWS={'main':[-3.5,4.0,8.1,18.0],'sw':[-3.5,-2.3,-.75,.75],'east':[15.5,16.22,3.98,4.62]}
INSETS={'sw':[.015,.025,.18,.18],'east':[.77,.025,.20,.20]}
POINT,INSET_POINT,ALPHA=2.2,1.2,.8
FOOTER='Two spatially separated UMAP islands are shown as insets using their original coordinates and the same descriptor scale.'
CAVEAT='UMAP coordinates unchanged. Inset relocation is visual layout only; distances between inset and main panel are not visually preserved. Quantitative similarity is evaluated in the original 256-dimensional representation space. Color scales/category definitions are shared and unchanged.'
NS='http://www.w3.org/2000/svg';ET.register_namespace('',NS)

def in_window(xy,box):
    a,b,c,d=box;return (xy[:,0]>=a)&(xy[:,0]<=b)&(xy[:,1]>=c)&(xy[:,1]<=d)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();out=a.output
    if out.exists():raise RuntimeError('EXCLUSIVE_NEW_OUTPUT_REQUIRED')
    previous_baseline=json.loads((V1/'preservation_snapshot.json').read_text())
    # Validate the existing baseline, then include every prior visualization byte.
    unchanged(previous_baseline)
    paths=list(previous_baseline)+[str(p) for p in V1.rglob('*') if p.is_file()]
    paths += [str(Path('scripts')/name) for name in ['visualize_s11_descriptors.py','revisualize_s11_publication.py']]
    baseline=snapshot(paths)
    old_manifest=json.loads((V1/'visualization_manifest.json').read_text())
    for p,h in old_manifest['payload_sha256'].items():assert baseline[p]==h
    receipt=json.loads(RECEIPT.read_text())
    for p,h in receipt['verified_payload_hashes'].items():assert baseline[p]==h
    print('Preflight preservation PASS',flush=True)
    d=pq.read_table(ROOT/'descriptor_acceptance/accepted/descriptors.parquet').to_pydict()
    c=pq.read_table(ROOT/'umap/coordinates/coordinates.parquet').to_pydict();ids=c['scene_id'];xy=np.array([c['x'],c['y']]).T
    assert ids==d['scene_id'] and len(set(ids))==9000 and np.isfinite(xy).all()
    masks={name:in_window(xy,box) for name,box in WINDOWS.items()}
    assert np.array_equal(sum(masks.values()),np.ones(9000,dtype=int)),'VIEWPORT_COVERAGE'
    counts={name:int(mask.sum()) for name,mask in masks.items()};assert counts=={'main':8646,'sw':291,'east':63}
    occlusion={}
    for name,(u,v,w,h) in INSETS.items():
        x0,x1,y0,y1=WINDOWS['main'];box=[x0+u*(x1-x0),x0+(u+w)*(x1-x0),y0+v*(y1-y0),y0+(v+h)*(y1-y0)]
        occlusion[name]=int(in_window(xy,box).sum());assert occlusion[name]==0,'INSET_OCCLUSION'
    dictionary=json.loads((ROOT/'descriptor_acceptance/accepted/dictionary.json').read_text());byid={r['id']:r for r in dictionary}
    assert len(byid)==22
    validmap={(r['scene_id'],r['descriptor']):r['valid'] for r in pq.read_table(ROOT/'descriptor_acceptance/accepted/validity.parquet').to_pylist()}
    registry={r['descriptor']:r for r in json.loads((PREVIOUS/'panel_registry.json').read_text())}
    v1plan=json.loads((V1/'display_plan.json').read_text());robust_limits=v1plan['display_limits']
    assert PRIMARY==v1plan['main_descriptors'] and ROBUST==v1plan['robust_descriptors'] and INTERPRETIVE==v1plan['interpretive_descriptors']
    with open(PREVIOUS/'legend_dictionary.csv') as f:legends=list(csv.DictReader(f))
    styles={};color_hashes={}
    for k,desc in byid.items():
        valid=np.array([v is not None for v in d[k]])
        assert all(bool(valid[i])==validmap[(s,k)] for i,s in enumerate(ids))
        st={'valid':valid}
        if desc['kind']=='scalar':
            values=np.array([float(v) if v is not None else np.nan for v in d[k]])
            assert np.isfinite(values[valid]).all();st.update(values=values,limits=registry[k]['scalar_color_limits'])
            for mode,limits in [('full',st['limits'])]+([('robust',robust_limits[k])] if k in ROBUST else []):
                norm=colors.Normalize(*limits,clip=mode=='robust')
                rgba=plt.get_cmap('viridis')(norm(np.nan_to_num(values)));rgba[~valid]=colors.to_rgba(v1plan['NA'])
                st[mode]=(rgba,norm);color_hashes[k+'__'+mode]=__import__('hashlib').sha256(rgba.tobytes()).hexdigest()
        else:
            rows=[r for r in legends if r['descriptor']==k and r['displayed_as_dominant']=='True']
            palette={int(r['dictionary_index']):r['color'] for r in rows};labels={int(r['dictionary_index']):r['display_label'] for r in rows}
            indices=np.array([np.argmax(v) if v is not None else -1 for v in d[k]])
            rgba=np.array([colors.to_rgba(palette[int(v)] if ok else v1plan['NA']) for v,ok in zip(indices,valid)])
            st.update(palette=palette,labels=labels,full=(rgba,None));color_hashes[k+'__full']=__import__('hashlib').sha256(rgba.tobytes()).hexdigest()
        styles[k]=st
    out.mkdir(parents=True,exist_ok=False);write_json(out/'preservation_snapshot.json',baseline)
    write_json(out/'layout_plan.json',{'viewports':WINDOWS,'axes_fraction_insets':INSETS,'coverage_QC_counts':counts,'main_points_occluded':occlusion,
        'viewport_choice':'Manual rounded viewport bounds enclosing all visible points with a small fixed margin; no clustering or analytical labels.',
        'point_size':POINT,'inset_point_size':INSET_POINT,'alpha':ALPHA,'full_limits':{k:s.get('limits') for k,s in styles.items()},
        'robust_limits_adopted_without_recalculation':robust_limits,'caveat':CAVEAT,'color_array_hashes':color_hashes,
        'all_coordinates_used_exactly_once_per_panel':True,'normalization_scope':'One shared RGBA array per descriptor/display mode, sliced for three windows; never normalized per viewport.'})
    font_manager.fontManager.addfont('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')
    plt.rcParams.update({'font.family':'Noto Sans CJK JP','font.size':9,'axes.titlesize':10,'axes.labelsize':8.5,'xtick.labelsize':8,'ytick.labelsize':8,'pdf.fonttype':42,'axes.linewidth':.55})
    meta={};v1meta=json.loads((V1/'figure_metadata.json').read_text())['figures'];checks=[]

    def panel(fig,bounds,k,label,robust=False,overview=False):
        ax=fig.add_axes(bounds['plot']);lg=fig.add_axes(bounds['legend']);lg.axis('off');st=styles[k];desc=byid[k]
        rgba,norm=st['robust' if robust else 'full']
        box=WINDOWS['main'];ax.set(xlim=box[:2],ylim=box[2:],aspect='equal',xlabel='UMAP 1',ylabel='UMAP 2')
        ax.spines[['top','right']].set_visible(False);ax.xaxis.set_major_locator(ticker.MaxNLocator(4));ax.yaxis.set_major_locator(ticker.MaxNLocator(4))
        ax.set_title(f'({label}) '+title(desc).replace('landcover','land cover'),loc='left',fontsize=8 if overview else 10,pad=6)
        main=ax.scatter(xy[masks['main'],0],xy[masks['main'],1],c=rgba[masks['main']],s=POINT,alpha=ALPHA,linewidths=0)
        local=[]
        for i,name in enumerate(['sw','east']):
            ia=ax.inset_axes(INSETS[name]);box=WINDOWS[name]
            ia.set(xlim=box[:2],ylim=box[2:],aspect='equal',xticks=[],yticks=[])
            for spine in ia.spines.values():spine.set(linewidth=.5,color='#777777')
            sc=ia.scatter(xy[masks[name],0],xy[masks[name],1],c=rgba[masks[name]],s=INSET_POINT,alpha=ALPHA,linewidths=0)
            ia.text(.04,.97,'i' if name=='sw' else 'ii',transform=ia.transAxes,va='top',fontsize=5.5,color='#555555')
            # Assert actual scatter offsets and colors are source slices, with no transform of data.
            assert np.array_equal(np.asarray(sc.get_offsets()),xy[masks[name]])
            expected=rgba[masks[name]].copy();expected[:,3]=ALPHA
            assert np.array_equal(sc.get_facecolors(),expected)
            local.append(int(len(sc.get_offsets())))
        expected=rgba[masks['main']].copy();expected[:,3]=ALPHA
        assert np.array_equal(main.get_facecolors(),expected) and np.array_equal(np.asarray(main.get_offsets()),xy[masks['main']])
        checks.append({'descriptor':k,'mode':'robust' if robust else 'full','main':len(main.get_offsets()),'insets':local,'scene_total':9000,'exact_coordinate_color_slices':True})
        if desc['kind']=='scalar':
            cax=lg.inset_axes([.10,.66,.78,.12]);cb=fig.colorbar(plt.cm.ScalarMappable(norm=norm,cmap='viridis'),cax=cax,orientation='horizontal',extend='both' if robust else 'neither')
            cb.locator=ticker.MaxNLocator(4);cb.update_ticks();cb.ax.tick_params(labelsize=6 if overview else 8,pad=1);cb.set_label(UNITS[desc['units']],fontsize=7 if overview else 8.5,labelpad=1)
            if robust:lg.text(.5,-.08,'Visualization scale: 5th–95th percentile',ha='center',fontsize=7,transform=lg.transAxes)
        else:
            handles=[Line2D([],[],marker='o',ls='',color=st['palette'][j],label=st['labels'][j],markersize=3.4) for j in sorted(st['palette'])]
            lg.legend(handles=handles,ncols=2 if len(handles)>8 else 1,loc='upper center',frameon=False,fontsize=5.7 if overview else 9,handletextpad=.25,columnspacing=.6,borderaxespad=0,labelspacing=.16)

    def legend_heights(keys,cols,robust=False,overview=False):
        heights=[]
        for start in range(0,len(keys),cols):
            h=.60 if robust else .45
            for k in keys[start:start+cols]:
                if byid[k]['kind']=='compositional':
                    n=len(styles[k]['palette']);rows=math.ceil(n/2) if n>8 else n
                    h=max(h,.07+rows*(.10 if overview else .148))
            heights.append(h)
        return heights

    def footer(fig,height,small=False):
        fig.text(.5,.25/height,FOOTER,ha='center',fontsize=6.5 if small else 7)
        fig.text(.5,.10/height,'i: SW   ii: East   •   Gray: undefined   •   Dominant categories: visualization only; full-vector analysis unchanged',ha='center',fontsize=6.5 if small else 7)

    def save(fig,name,keys,robust=False,overview=False,base_name=None):
        fig.canvas.draw()
        bbox=fig.get_tightbbox(fig.canvas.get_renderer())
        assert bbox.x0>=-.01 and bbox.y0>=-.01 and bbox.x1<=fig.get_figwidth()+.01 and bbox.y1<=fig.get_figheight()+.01,('FIGURE_TEXT_CLIPPING',name,bbox.bounds)
        fig.savefig(out/(name+'.pdf'),metadata={'CreationDate':None,'ModDate':None});fig.savefig(out/(name+'.png'),dpi=240 if overview else 300);plt.close(fig)
        base_name=base_name or name.removesuffix('_v2');base_meta=copy.deepcopy(v1meta[base_name])
        meta[name]=dict(base_meta,layout_version='inset_v2',viewports=WINDOWS,inset_placement=INSETS,layout_caveat=CAVEAT,
            caption=base_meta['caption']+' '+FOOTER+' '+CAVEAT,
            descriptor_order=keys,color_array_hashes={k:color_hashes[k+('__robust' if robust else '__full')] for k in keys},
            V1_reference=str(V1/(base_name+'.pdf')),main_point_size=POINT,inset_point_size=INSET_POINT,alpha=ALPHA)
        print('Rendered '+name,flush=True)

    def grid(name,keys,heading,robust=False):
        cols=min(3,len(keys));lh=legend_heights(keys,cols,robust);rowh=[3.25+h+.72 for h in lh]
        width=3.35*cols;height=sum(rowh)+.95;fig=plt.figure(figsize=(width,height));fig.suptitle(heading,fontsize=13,y=1-.16/height);footer(fig,height)
        for i,k in enumerate(keys):
            row,col=divmod(i,cols);bottom=.49+sum(rowh[row+1:]);x0=3.35*col
            b={'plot':[(x0+.60)/width,(bottom+lh[row]+.42)/height,2.46/width,3.25/height],
               'legend':[(x0+.05)/width,bottom/height,3.25/width,lh[row]/height]}
            panel(fig,b,k,chr(97+i),robust)
        save(fig,name,keys,robust)
    grid('main_six_panels_v2',PRIMARY,'FM representation space')
    for fam,heading in FAMILIES.items():grid('family_'+fam+'_v2',[d['id'] for d in dictionary if d['family']==fam],heading)
    grid('robust_scalar_supplement_v2',ROBUST,'Scalar descriptors — robust display supplement',True)
    grid('semantic_environment_supplement_v2',INTERPRETIVE,'Interpretive supplementary panels')
    # Overview: compact family-separated rows. Fine print is intended for large-format pages.
    blocks=[]
    for fam,heading in FAMILIES.items():
        keys=[d['id'] for d in dictionary if d['family']==fam];lh=legend_heights(keys,3,overview=True);heights=[2.4+h+.55 for h in lh]
        blocks.append((heading,keys,lh,heights,sum(heights)+.30))
    width=10.5;height=sum(b[-1] for b in blocks)+1.0;fig=plt.figure(figsize=(width,height));fig.suptitle('All 22 descriptors — overview',fontsize=13,y=1-.18/height);footer(fig,height,True)
    top=height-.60
    for heading,keys,lh,rowh,total in blocks:
        fig.text(.025,(top-.12)/height,heading,fontsize=11,weight='bold');top-=.30
        for i,k in enumerate(keys):
            row,col=divmod(i,3);bottom=top-sum(rowh[:row+1]);x=col*3.5
            panel(fig,{'plot':[(x+.60)/width,(bottom+lh[row]+.38)/height,1.818/width,2.4/height],
                       'legend':[(x+.13)/width,bottom/height,3.22/width,lh[row]/height]},k,chr(97+list(byid).index(k)),overview=True)
        top-=sum(rowh)
    save(fig,'all_22_overview_v2',list(byid),overview=True)
    run('pdfunite',*[out/('family_'+fam+'_v2.pdf') for fam in FAMILIES],out/'all_22_large_format_v2.pdf')
    meta['all_22_large_format_v2']=dict(copy.deepcopy(v1meta['all_22_large_format']),layout_version='inset_v2',viewports=WINDOWS,layout_caveat=CAVEAT,pages=6)
    for name in ['main_umap_ai.pdf','main_umap_ai.png','scene_mapping_a_i.csv']:
        shutil.copyfile(V1/name,out/name);assert sha(out/name)==baseline[str(V1/name)]
    meta['main_umap_ai']=dict(copy.deepcopy(v1meta['main_umap_ai']),unchanged_copy_of=str(V1/'main_umap_ai.pdf'),copy_sha256=sha(out/'main_umap_ai.pdf'))
    write_json(out/'render_validation.json',{'panels':checks,'viewport_counts':counts,'uncovered_scenes':0,'duplicate_scenes':0,'occluded_main_points':occlusion,'shared_color_mapping':True})
    write_json(out/'figure_metadata.json',{'figures':meta,'caveat':CAVEAT,'source_V1_metadata_sha256':sha(V1/'figure_metadata.json')})
    lines=['# V2 caption-ready notes','',FOOTER,'',CAVEAT,'','Inset locator i is SW; ii is East. Manual display windows are not scientific clusters. Gray = undefined. Observed zero uses the unchanged scalar color scale.','']
    for name,m in meta.items():lines+=['## '+name,'',m.get('caption',CAVEAT),'','Scale: '+m['visualization_scale']+'.','']
    (out/'figure_captions.md').write_text('\n'.join(lines))
    # Vector print-placement proofs at identical page margins, V1/V2 separately.
    proof_dir=out/'placement_proofs';proof_dir.mkdir();proofs=[]
    for version,path in [('V1',V1/'main_six_panels.pdf'),('V2',out/'main_six_panels_v2.pdf')]:
        run('pdftocairo','-svg',path,proof_dir/(version+'.svg'))
    proof_records=[]
    for paper,W,H in [('A4 portrait',595.276,841.89),('A4 landscape',841.89,595.276),('Letter portrait',612.,792.),('Letter landscape',792.,612.)]:
        for version in ['V1','V2']:
            orig=ET.parse(proof_dir/(version+'.svg')).getroot();bounds=list(map(float,orig.attrib['viewBox'].split()));ow,oh=bounds[2:]
            scale=min((W-60)/ow,(H-88)/oh);x=(W-ow*scale)/2;y=45+(H-88-oh*scale)/2
            svg=ET.Element('{'+NS+'}svg',width=f'{W}pt',height=f'{H}pt',viewBox=f'0 0 {W} {H}')
            ET.SubElement(svg,'{'+NS+'}rect',x='0',y='0',width=str(W),height=str(H),fill='white')
            t=ET.SubElement(svg,'{'+NS+'}text',x='30',y='24',**{'font-size':'11','font-family':'sans-serif'});t.text=f'{paper} — {version}, fixed 30 pt margins'
            nested=ET.SubElement(svg,'{'+NS+'}svg',x=str(x),y=str(y),width=str(ow*scale),height=str(oh*scale),viewBox=orig.attrib['viewBox'])
            for child in orig:nested.append(copy.deepcopy(child))
            font=7 if version=='V1' else 9
            t=ET.SubElement(svg,'{'+NS+'}text',x='30',y=str(H-20),**{'font-size':'8','font-family':'sans-serif'});t.text=f'Display scale {scale:.3f}; {font} pt source legend becomes {font*scale:.2f} pt. No data change.'
            n=f'{paper.lower().replace(" ","_")}_{version.lower()}';sp=proof_dir/(n+'.svg');ET.ElementTree(svg).write(sp,encoding='utf-8',xml_declaration=True)
            pp=proof_dir/(n+'.pdf');run('rsvg-convert','--format=pdf','--output',pp,sp);proofs.append(pp)
            proof_records.append({'paper':paper,'version':version,'scale':scale,'source_legend_points':font,'effective_legend_points':font*scale,'path':str(pp)})
    run('pdfunite',*proofs,out/'V1_vs_V2_placement_proofs.pdf');write_json(out/'placement_review.json',proof_records)
    # Preview files for direct side-by-side/readability audit; no alternate scientific rendering.
    for version in ['v1','v2']:
        run('pdftoppm','-singlefile','-png','-r','150',proof_dir/('a4_portrait_'+version+'.pdf'),proof_dir/('a4_portrait_'+version))
        run('pdftoppm','-singlefile','-png','-r','150',proof_dir/('a4_landscape_'+version+'.pdf'),proof_dir/('a4_landscape_'+version))
    for p in out.glob('*.png'):
        with Image.open(p) as im:im.verify()
    for p in out.glob('*.pdf'):
        count=int(re.search(r'Pages:\s+(\d+)',run('pdfinfo',p)).group(1));assert count==(6 if 'large_format' in p.name else 8 if 'placement' in p.name else 1)
    unchanged(baseline)
    write_json(out/'visualization_manifest.json',{'status':'PASS','scope':'layout only','created_at':datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
        'scientific_inputs_unchanged':True,'S11_receipt_payloads':1352,'S12_files':27427,'previous_directories':[str(PREVIOUS),str(V1)],
        'preserved_file_count':len(baseline),'descriptor_count':22,'viewports':WINDOWS,'coverage_QC':counts,'coordinates_and_colors_exact':True,
        'robust_limits_recomputed':False,'main_umap_ai_byte_identical':True,'new_scientific_analysis':False,'dissertation_unchanged':True,
        'source_script':str(Path(__file__).resolve()),'source_script_sha256':sha(__file__),
        'payload_sha256':snapshot(p for p in out.rglob('*') if p.is_file())})
    print('PASS '+str(out),flush=True)

if __name__=='__main__':main()
