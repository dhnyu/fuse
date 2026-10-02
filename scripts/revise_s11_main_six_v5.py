#!/usr/bin/env python
"""Presentation-only six-panel revision and accepted FM Table B row selection.
No scientific kernels, percentile calculation, P3 read, or scientific reanalysis.
"""
from pathlib import Path
import argparse,csv,json,hashlib,re,shutil,subprocess,copy
from datetime import datetime
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET
import numpy as np
import pyarrow.parquet as pq
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import colors,ticker
from PIL import Image
from revisualize_s11_publication import ROOT,RECEIPT,sha,write_json,snapshot,unchanged,run

V4=Path('/mnt/hdd002/dhnyu/fusedata/analysis_data/reduced/s11_visualization_only/20260923_1518_publication_v4_lcdem_compactlegend')
TABLES=Path('/mnt/hdd002/dhnyu/fusedata/analysis_data/reduced/s11_report_support/20260923_2107_fm_ch54_tables')
KEYS=['building_coverage','road_orientation_dispersion','building_use_composition','mean_relational_degree','poi_density','landcover_composition']
TITLES=['Building coverage','Road orientation dispersion','Dominant building use','Mean relational degree','POI density','Dominant land cover']
RATIONALES=[
'Scene-composition representative.',
'Intrinsic-geometry representative; inspect visible variation against compactness without exaggerating weak quantitative alignment.',
'Semantic variation from building-use dominance rather than the strong POI-L2 category imbalance; quantitative full-vector composition remains unchanged.',
'Relational-structure representative.',
'Additional scene-composition / activity-intensity observable: continuous POI density, not a newly derived activity metric.',
'Environmental-context representative.']
UNITS={'fraction':'fraction','1':'dimensionless','neighbors/entity':'neighbors/entity','entities/km2':'entities/km²'}
TITLE='Geographic characteristics across the FM representation space.'
DETAIL='The 9,000 evaluation-scene representations are colored by (a) building coverage, (b) road-orientation dispersion, (c) dominant building-use category, (d) mean relational degree, (e) POI density, and (f) dominant land-cover class. Two spatially separated portions of the UMAP projection are shown as insets using their original coordinates and the same descriptor scales. Dominant categories are used only for visualization; quantitative analyses use the complete composition vectors.'
CAVEAT='These are user-requested representative descriptive panels, not a strongest-descriptor selection or a one-panel-per-family design. Spatial configuration has no panel; scene composition has two. Original frozen scientific D6 and accepted artifacts remain unchanged. Inset-to-main distances are not visually preserved; quantitative similarity belongs to the original 256-dimensional representation space.'

def window(xy,b):return (xy[:,0]>=b[0])&(xy[:,0]<=b[1])&(xy[:,1]>=b[2])&(xy[:,1]<=b[3])
def textof(n):
    if isinstance(n,list):return ''.join(textof(x) for x in n)
    if not isinstance(n,dict):return ''
    if n.get('func')=='space':return ' '
    return n.get('text',textof(n.get('body',n.get('children',[]))))

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);out=ap.parse_args().output;assert not out.exists()
    baseline=json.loads((TABLES/'preservation_snapshot.json').read_text());unchanged(baseline)
    baseline.update(snapshot(p for p in TABLES.rglob('*') if p.is_file()))
    receipt=json.loads(RECEIPT.read_text());assert receipt['status']=='PASS' and receipt['receipt_id']=='s11rv_12475d91074d68a9d1a5436c'
    for p,h in receipt['verified_payload_hashes'].items():assert sha(p)==h
    print('Preserved scientific and earlier presentation inputs PASS',flush=True)
    coords=pq.read_table(ROOT/'umap/coordinates/coordinates.parquet').to_pydict();d=pq.read_table(ROOT/'descriptor_acceptance/accepted/descriptors.parquet').to_pydict()
    ids=coords['scene_id'];assert ids==d['scene_id']==pq.read_table(ROOT/'accepted_parents/parents/population.parquet')['scene_id'].to_pylist() and len(ids)==len(set(ids))==9000
    xy=np.column_stack([coords['x'],coords['y']]);assert np.isfinite(xy).all()
    registry={r['id']:r for r in json.loads((ROOT/'descriptor_acceptance/accepted/dictionary.json').read_text())};assert len(registry)==22
    validity={(r['scene_id'],r['descriptor']):r['valid'] for r in pq.read_table(ROOT/'descriptor_acceptance/accepted/validity.parquet').to_pylist()}
    plan=json.loads((V4/'layout_plan.json').read_text());windows=plan['viewports'];insets=plan['axes_fraction_insets'];masks={k:window(xy,b) for k,b in windows.items()}
    assert np.array_equal(sum(masks.values()),np.ones(9000,dtype=int))
    for u,v,w,h in insets.values():
        x0,x1,y0,y1=windows['main'];assert not window(xy,[x0+u*(x1-x0),x0+(u+w)*(x1-x0),y0+v*(y1-y0),y0+(v+h)*(y1-y0)]).any()
    labels=list(csv.DictReader((V4/'category_code_mapping.csv').open()))
    metadata=json.loads((V4/'figure_metadata.json').read_text())['figures']['main_six_panels_v4_compactlegend'];na='#b0b0b0'
    out.mkdir(parents=True);write_json(out/'preservation_snapshot.json',baseline)
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'axes.labelsize':8.5,'xtick.labelsize':8,'ytick.labelsize':8,'pdf.fonttype':42,'axes.linewidth':.55})
    width=10.05;lh=.45;rowh=3.25+lh+.72;shared=.67;height=2*rowh+.95+shared
    fig=plt.figure(figsize=(width,height));fig.suptitle(TITLE.removesuffix('.'),fontsize=13,y=1-.16/height)
    checks=[];category_refs={};norms={};colorhash={}
    for i,k in enumerate(KEYS):
        row,col=divmod(i,3);bottom=.49+shared+(rowh if row==0 else 0);x0=3.35*col
        ax=fig.add_axes([(x0+.60)/width,(bottom+lh+.42)/height,2.46/width,3.25/height]);lg=fig.add_axes([(x0+.05)/width,bottom/height,3.25/width,lh/height]);lg.axis('off')
        box=windows['main'];ax.set(xlim=box[:2],ylim=box[2:],aspect='equal',xlabel='UMAP 1',ylabel='UMAP 2')
        ax.spines[['top','right']].set_visible(False);ax.xaxis.set_major_locator(ticker.MaxNLocator(4));ax.yaxis.set_major_locator(ticker.MaxNLocator(4));ax.set_title(f'({chr(97+i)}) '+TITLES[i],loc='left',fontsize=10,pad=6)
        valid=np.array([v is not None for v in d[k]]);assert all(bool(v)==validity[(sid,k)] for sid,v in zip(ids,valid))
        if registry[k]['kind']=='scalar':
            values=np.array([v if v is not None else np.nan for v in d[k]],dtype=float);norm=colors.Normalize(*plan['full_limits'][k],clip=False)
            rgba=plt.get_cmap('viridis')(norm(np.nan_to_num(values)));rgba[~valid]=colors.to_rgba(na);norms[k]=plan['full_limits'][k]
            ca=lg.inset_axes([.10,.66,.78,.12]);cb=fig.colorbar(plt.cm.ScalarMappable(norm=norm,cmap='viridis'),cax=ca,orientation='horizontal');cb.locator=ticker.MaxNLocator(4);cb.update_ticks();cb.ax.tick_params(labelsize=8,pad=1);cb.set_label(UNITS[registry[k]['units']],fontsize=8.5,labelpad=1)
        else:
            rows=[r for r in labels if r['descriptor']==k and r['displayed_as_dominant']=='True'];palette={int(r['dictionary_index']):r['color'] for r in rows}
            indices=np.array([np.argmax(v) if v is not None else -1 for v in d[k]])
            rgba=np.array([colors.to_rgba(palette[int(v)] if ok else na) for v,ok in zip(indices,valid)])
            assert all(re.fullmatch(r'[A-Za-z0-9/]+',r['code_label']) for r in rows)
            category_refs[k]=[{'code':r['code_label'],'dictionary_index':int(r['dictionary_index']),'color':r['color']} for r in rows]
        h=hashlib.sha256(rgba.tobytes()).hexdigest();assert h==plan['color_array_hashes'][k+'__full'];colorhash[k]=h
        for name in ['main','sw','east']:
            if name=='main':a=ax;s=plan['point_size']
            else:
                a=ax.inset_axes(insets[name]);b=windows[name];a.set(xlim=b[:2],ylim=b[2:],aspect='equal',xticks=[],yticks=[])
                for spine in a.spines.values():spine.set(linewidth=.5,color='#777777')
                a.text(.04,.97,'i' if name=='sw' else 'ii',transform=a.transAxes,va='top',fontsize=5.5,color='#555555');s=plan['inset_point_size']
            sc=a.scatter(xy[masks[name],0],xy[masks[name],1],c=rgba[masks[name]],s=s,alpha=plan['alpha'],linewidths=0)
            expected=rgba[masks[name]].copy();expected[:,3]=plan['alpha']
            assert np.array_equal(np.asarray(sc.get_offsets()),xy[masks[name]]) and np.array_equal(sc.get_facecolors(),expected)
        checks.append({'descriptor':k,'rendered_scenes':9000,'source_coordinate_color_slices_exact':True,'full_range':True})
    for i,label in enumerate(['Building use','Land cover']):
        la=fig.add_axes([.04,(.49+shared-.07-(i+1)*.30)/height,.92,.29/height]);la.axis('off');la.text(0,.55,label,fontsize=7,va='center');la.text(.29,.55,'Codes: external codebook',fontsize=7,va='center')
    fig.text(.5,.25/height,'Insets: original coordinates, shared scales; spacing not preserved.',ha='center',fontsize=7)
    fig.text(.5,.10/height,'i: SW   ii: East   |   Gray: NA   |   Category codes: external codebook',ha='center',fontsize=7)
    fig.canvas.draw();texts=[t.get_text() for t in fig.findobj(matplotlib.text.Text) if t.get_visible() and t.get_text()]
    assert not any(re.search(r'[\u1100-\u11ff\u3130-\u318f\uac00-\ud7ff]',t) for t in texts)
    bbox=fig.get_tightbbox(fig.canvas.get_renderer());assert bbox.x0>=0 and bbox.y0>=0 and bbox.x1<=width and bbox.y1<=height
    fig.savefig(out/'main_six_panels_v5.pdf',metadata={'CreationDate':None,'ModDate':None});fig.savefig(out/'main_six_panels_v5.png',dpi=300);plt.close(fig)
    with Image.open(out/'main_six_panels_v5.png') as im:im.verify()
    assert not re.search(r'[\uac00-\ud7ff]',run('pdftotext',out/'main_six_panels_v5.pdf','-'))
    # A4 vector placement proof, no rerender or alternate color mapping.
    run('pdftocairo','-svg',out/'main_six_panels_v5.pdf',out/'main_six_panels_v5.svg')
    ns='{http://www.w3.org/2000/svg}';ET.register_namespace('',ns[1:-1]);original=ET.parse(out/'main_six_panels_v5.svg').getroot();ow,oh=map(float,original.attrib['viewBox'].split()[2:]);W,H=595.276,841.89;margin=18*72/25.4;scale=min((W-2*margin)/ow,(H-2*margin)/oh)
    root=ET.Element(ns+'svg',width=f'{W}pt',height=f'{H}pt',viewBox=f'0 0 {W} {H}');child=ET.SubElement(root,ns+'svg',x=str((W-ow*scale)/2),y=str(margin),width=str(ow*scale),height=str(oh*scale),viewBox=original.attrib['viewBox'])
    for node in original:child.append(copy.deepcopy(node))
    ET.ElementTree(root).write(out/'a4_portrait_proof.svg',encoding='utf-8',xml_declaration=True);run('rsvg-convert','--format=pdf','--output',out/'a4_portrait_proof.pdf',out/'a4_portrait_proof.svg')
    # Table B: select existing full-precision rows, preserve every accepted summary/support field.
    old_rows=json.loads((TABLES/'fm_rank_region_summary.json').read_text());old={(r['descriptor'],r['mode'],r['region']):r for r in old_rows}
    accepted=pq.read_table(ROOT/'alignment_summaries/summaries/summary.parquet').to_pylist();src={(r['descriptor'],r['mode'],r['region']):r for r in accepted}
    columns={'median':'query_median','Q1':'query_q1','Q3':'query_q3','IQR':'query_iqr','total_queries':'query_total_count','valid_queries':'query_valid_count','undefined_queries':'query_invalid_count','candidate_total_support':'candidate_total_count','candidate_valid_support':'candidate_valid_count','candidate_invalid_support':'candidate_invalid_count','summary_null_reason':'query_null_reason'}
    selected=[old[k,m,b] for k in KEYS for m in ['standard','nonlocal'] for b in ['rank1','upper','middle','lower']];assert len(selected)==48
    for row in selected:
        raw=src[row['descriptor'],row['mode'],row['region']]
        assert all(row[a]==raw[b] for a,b in columns.items())
    write_json(out/'fm_rank_region_main_v2.json',selected)
    with (out/'fm_rank_region_main_v2.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(selected[0]));w.writeheader()
        for r in selected:w.writerow({k:'null' if v is None else json.dumps(v,ensure_ascii=False,sort_keys=True) if isinstance(v,(dict,list)) else v for k,v in r.items()})
    shutil.copytree(TABLES/'style',out/'style');s=(TABLES/'fm_rank_region_main.typ').read_text();start=s.index('      [Building coverage');end=s.index('    ),',start);body=[]
    for k in KEYS:
        for mi,m in enumerate(['standard','nonlocal']):
            rs=[old[k,m,b] for b in ['rank1','upper','middle','lower']];label=rs[0]['display_name']+' ('+rs[0]['difference_units']+')' if mi==0 else ''
            body.append('      ['+label+'], ['+rs[0]['mode_display']+'], '+', '.join(f'[{r["median"]:.3f}]' for r in rs)+',')
    s=s[:start]+'\n'.join(body)+'\n'+s[end:];s=s.replace('fm-rank-region-main','fm-rank-region-main-v2').replace('fixed FM representatives','revised FM descriptive representatives').replace('Representatives are the six descriptors fixed for the main UMAP, without result-based selection.','This table follows the user-requested six-panel presentation revision; it is not a strongest-descriptor selection or one-per-family design.')
    (out/'fm_rank_region_main_v2.typ').write_text(s)
    (out/'fm_rank_region_main_v2_preview.typ').write_text('#set page(width: 190mm, height: 260mm, margin: (left: 30mm, right: 30mm, top: 20mm, bottom: 15mm))\n#set text(font: "New Computer Modern", size: 10pt)\n#set figure(numbering: "1", placement: none)\n#set figure.caption(position: top)\n#import "fm_rank_region_main_v2.typ": fm-rank-region-main-v2\n#fm-rank-region-main-v2 <tab:fm-rank-region-alignment>\n')
    typst='/snap/typst/current/bin/typst';run(typst,'compile',out/'fm_rank_region_main_v2_preview.typ',out/'fm_rank_region_main_v2_preview.pdf')
    compiled=json.loads(run(typst,'eval','query(table)','--in',out/'fm_rank_region_main_v2_preview.typ'));assert len(compiled)==1;children=compiled[0]['children'];i=1
    for k in KEYS:
        for mi,m in enumerate(['standard','nonlocal']):
            ref=old[k,m,'rank1'];assert textof(children[i])==(ref['display_name']+' ('+ref['difference_units']+')' if mi==0 else '');i+=1
            assert textof(children[i])==ref['mode_display'];i+=1
            for b in ['rank1','upper','middle','lower']:assert textof(children[i])==f'{src[k,m,b]["query_median"]:.3f}';i+=1
    assert i==len(children);write_json(out/'compiled_table_cells.json',compiled)
    reread=list(csv.DictReader((out/'fm_rank_region_main_v2.csv').open()))
    for row,orig in zip(reread,selected,strict=True):
        for k,v in orig.items():
            got=row[k]
            if v is None:assert got=='null'
            elif isinstance(v,(dict,list)):assert json.loads(got)==v
            elif isinstance(v,float):assert float(got)==v and np.isfinite(float(got))
            elif isinstance(v,int):assert int(got)==v
            else:assert got==v
    assert json.loads((out/'fm_rank_region_main_v2.json').read_text())==selected
    refs={str(V4/n):sha(V4/n) for n in ['categorical_codebook_all.csv','categorical_codebook_all.pdf','family_semantics_codebook.csv','family_semantics_codebook.pdf']}
    (out/'external_codebook_reference.md').write_text('# Existing immutable codebooks\n\nBU codes remain display aliases, not official source codes. Numeric land-cover codes are accepted internal classes. No category is regrouped or recolored.\n\n'+'\n'.join(f'- [{Path(p).name}]({p}) — SHA256 `{h}`' for p,h in refs.items())+'\n')
    md={'title':TITLE,'caption_detail':DETAIL,'caveat':CAVEAT,'presentation_descriptor_order':KEYS,'panels':[{'label':chr(97+i),'descriptor':k,'title':TITLES[i],'rationale':RATIONALES[i]} for i,k in enumerate(KEYS)],'scientific_contract_unchanged':True,'original_D6_replaced_only_in_this_presentation':True,
        'accepted_receipt':str(RECEIPT),'accepted_receipt_id':receipt['receipt_id'],'accepted_receipt_sha256':sha(RECEIPT),'coordinate_manifest_sha256':sha(ROOT/'umap/coordinates/manifest.json'),'coordinates_sha256':sha(ROOT/'umap/coordinates/coordinates.parquet'),'descriptors_sha256':sha(ROOT/'descriptor_acceptance/accepted/descriptors.parquet'),'validity_sha256':sha(ROOT/'descriptor_acceptance/accepted/validity.parquet'),'dictionary_sha256':sha(ROOT/'descriptor_acceptance/accepted/dictionary.json'),
        'viewports':windows,'inset_placement':insets,'point_size':plan['point_size'],'inset_point_size':plan['inset_point_size'],'alpha':plan['alpha'],'NA':na,'scalar_full_range_limits':norms,'RGBA_sha256':colorhash,'categorical_codes':category_refs,'external_codebooks':refs,'dominance_rule':'Argmax over stored composition vector; ties follow frozen dictionary order; visualization only.',
        'normalization':'Full-range V4 limits, shared across main and both insets. No robust scaling, percentile recalculation or per-panel rescaling.','robust_supplement_reference':str(V4/'robust_scalar_supplement_v4_compactlegend.pdf'),
        'table_source_manifest':str(ROOT/'alignment_summaries/summaries/manifest.json'),'table_source_manifest_sha256':sha(ROOT/'alignment_summaries/summaries/manifest.json'),'table_source_summary_sha256':sha(ROOT/'alignment_summaries/summaries/summary.parquet'),'A4_proof':{'margin_mm':18,'scale':scale,'plot_title_points':10*scale,'axis_label_points':8.5*scale},'scientific_recomputation':False}
    write_json(out/'figure_metadata.json',md);write_json(out/'validation.json',{'status':'PASS','panels':checks,'population':9000,'viewport_counts':{k:int(v.sum()) for k,v in masks.items()},'inset_occlusion':0,'code_only_text':True,'table_source_rows':48,'compiled_table_cells_checked':72,'CSV_JSON_readback':True,'all_six_RGBA_hashes_match_V4':True})
    (out/'caption.md').write_text('# '+TITLE+'\n\n'+DETAIL+'\n\n'+CAVEAT+'\n')
    unchanged(baseline)
    write_json(out/'visualization_manifest.json',{'status':'PASS','scope':'presentation selection revision and accepted Table B row extraction','created_at':datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),'descriptor_order':KEYS,'scientific_recomputation':False,'S11_receipt_files_unchanged':1352,'S12_files_unchanged':27427,'all_prior_snapshot_files_unchanged':len(baseline),'dissertation_unchanged':True,'source_script':str(Path(__file__).resolve()),'source_script_sha256':sha(__file__),'payload_sha256':snapshot(p for p in out.rglob('*') if p.is_file())})
    print('PASS '+str(out),flush=True)

if __name__=='__main__':main()
