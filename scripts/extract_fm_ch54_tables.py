#!/usr/bin/env python
"""S11 accepted-result transcription only, dissertation 5.4.
No scientific kernel imports, quantile/correlation calls, or model computations.
"""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from collections import Counter
import argparse,csv,json,math,shutil,subprocess,hashlib
import pyarrow as pa
import pyarrow.parquet as pq
import pyarrow.compute as pc
from revisualize_s11_publication import snapshot,unchanged,sha,write_json,ROOT,RECEIPT,DISS,FAMILIES,PRIMARY

ORDER=['building_coverage','road_density','poi_density','mean_building_footprint_size','mean_building_compactness','building_orientation_dispersion','road_orientation_dispersion','mean_road_segment_length','building_location_dispersion','road_location_dispersion','poi_location_dispersion','relation_composition','mean_relational_degree','building_use_composition','building_structure_composition','road_type_composition','road_hierarchy_composition','mean_lane_count','poi_l2_composition','landcover_composition','mean_elevation','elevation_variability']
NAMES=['Building coverage','Road density','POI density','Mean building footprint size','Mean building compactness','Building orientation dispersion','Road orientation dispersion','Mean road segment length','Building location dispersion','Road location dispersion','POI location dispersion','Relation composition','Mean relational degree','Building-use composition','Building-structure composition','Road-type composition','Road-hierarchy composition','Mean lane count','POI L2 composition','Land-cover composition','Mean elevation','Elevation variability']
MODES={'standard':'Standard','nonlocal':'Non-local'}
REGIONS={'rho':'rho','rank1':'Rank 1','upper':'Upper','middle':'Middle','lower':'Lower'}
UNITS={'fraction':'fraction','km/km2':'km/km²','entities/km2':'entities/km²','m2':'m²','m':'m','1':'dimensionless','neighbors/entity':'neighbors/entity','proportion':'dimensionless L2','lanes':'lanes'}
COLS={'median':'query_median','Q1':'query_q1','Q3':'query_q3','IQR':'query_iqr','total_queries':'query_total_count','valid_queries':'query_valid_count','undefined_queries':'query_invalid_count','summary_null_reason':'query_null_reason','candidate_total_support':'candidate_total_count','candidate_valid_support':'candidate_valid_count','candidate_invalid_support':'candidate_invalid_count'}

def write_csv(path,rows):
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader()
        for r in rows:w.writerow({k:'null' if v is None else json.dumps(v,ensure_ascii=False,sort_keys=True) if isinstance(v,(list,dict)) else v for k,v in r.items()})

def fmt(x):return '—' if x is None else format(x,'.3f').replace('-','−')
def cell(s):return '['+s.replace('[','\\[').replace(']','\\]')+']'

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);out=ap.parse_args().output
    assert not out.exists(),'NEW_OUTPUT_ONLY'
    # Read-only preservation covers all scientific accepted products and earlier visualization inputs.
    previous=Path('/mnt/hdd002/dhnyu/fusedata/analysis_data/reduced/s11_visualization_only/20260923_1518_publication_v4_lcdem_compactlegend')
    baseline=json.loads((previous/'preservation_snapshot.json').read_text());unchanged(baseline)
    baseline.update(snapshot(p for p in previous.rglob('*') if p.is_file()))
    receipt=json.loads(RECEIPT.read_text());assert receipt['status']=='PASS' and receipt['receipt_id']=='s11rv_12475d91074d68a9d1a5436c'
    assert receipt['generation']==ROOT.name and receipt['scientific_payloads_unchanged']
    for p,h in receipt['verified_payload_hashes'].items():assert baseline[p]==h,(p,h)
    summary_dir=ROOT/'alignment_summaries/summaries';desc_dir=ROOT/'descriptor_acceptance/accepted'
    summary_path=summary_dir/'summary.parquet';manifest_path=summary_dir/'manifest.json';manifest=json.loads(manifest_path.read_text())
    assert manifest['context']['generation']==ROOT.name and manifest['context']['checkpoint_id']=='p9ck_8ff9d205b9ff93e4d985ab06'
    assert manifest['context']['embedding_manifest_id']=='s10_embeddings_f70b8dbb9eaf05657fca83d2'
    for f,h in manifest['files'].items():assert sha(summary_dir/f)==h==receipt['verified_payload_hashes'][str(summary_dir/f)]
    dictionary=json.loads((desc_dir/'dictionary.json').read_text());assert [d['id'] for d in dictionary]==ORDER
    byid={d['id']:d for d in dictionary};names=dict(zip(ORDER,NAMES))
    source=pq.read_table(summary_path).to_pylist();assert source==json.loads((summary_dir/'summary.json').read_text()) and len(source)==220
    lookup={(r['descriptor'],r['mode'],r['region']):r for r in source}
    assert set(lookup)=={(k,m,b) for k in ORDER for m in MODES for b in REGIONS}
    pop=pq.read_table(ROOT/'accepted_parents/parents/population.parquet')['scene_id'].to_pylist()
    descriptors=pq.read_table(desc_dir/'descriptors.parquet');assert descriptors['scene_id'].to_pylist()==pop and len(pop)==len(set(pop))==9000
    lock=json.loads(Path('config/s11_representation_analysis.lock.json').read_text())
    gallery=json.loads(Path(lock['parents']['gallery']['path']).read_text())['body']['rows']
    assert [r['scene_id'] for r in gallery]==pop and all(r['split']=='evaluation' for r in gallery)
    metrics=pq.read_table(summary_dir/'query_metrics.parquet');assert metrics.num_rows==1980000
    assert not any('s12' in str(p).lower() for p in [summary_path,manifest_path,desc_dir])
    coverage=receipt['checks']['descriptor']['coverage'];validity=pq.read_table(desc_dir/'validity.parquet')
    provenance={'configuration_id':'cmp_FM','model':'FM','checkpoint_id':manifest['context']['checkpoint_id'],'selected_epoch':60,
        'generation':ROOT.name,'accepted_receipt_id':receipt['receipt_id'],'accepted_receipt_sha256':sha(RECEIPT),
        'source_manifest':str(manifest_path),'source_manifest_sha256':sha(manifest_path),'source_parquet':str(summary_path),'source_parquet_sha256':sha(summary_path),
        'descriptor_dictionary_sha256':sha(desc_dir/'dictionary.json'),'query_metrics_sha256':sha(summary_dir/'query_metrics.parquet')}
    all_rows=[];supports=[];reason_inventory=[]
    for k in ORDER:
        v=validity.filter(pc.equal(validity['descriptor'],k));vr=v.to_pylist();assert len(vr)==9000 and {r['scene_id'] for r in vr}==set(pop)
        assert coverage[k]['valid']==sum(r['valid'] for r in vr)==len([x for x in descriptors[k].to_pylist() if x is not None])
        assert coverage[k]['undefined']==sum(not r['valid'] for r in vr)
        reasons=sorted({r['null_reason'] for r in vr if r['null_reason'] is not None})
        supports.append(dict(descriptor=k,display_name=names[k],family=FAMILIES[byid[k]['family']],family_key=byid[k]['family'],mode=None,region='descriptor_support',median=None,Q1=None,Q3=None,IQR=None,
            total_scenes=9000,defined_scenes=coverage[k]['valid'],undefined_scenes=coverage[k]['undefined'],null_reason_categories=reasons,
            source_field=byid[k]['source'],empty_definition=byid[k]['empty'],units=byid[k]['units'],kind=byid[k]['kind'],
            support_count_source='Per-scene support fields remain in accepted validity.parquet; no new descriptor aggregation',
            source_manifest=str(desc_dir/'manifest.json'),source_manifest_sha256=sha(desc_dir/'manifest.json'),source_parquet=str(desc_dir/'validity.parquet'),source_parquet_sha256=sha(desc_dir/'validity.parquet'),coverage_source=str(RECEIPT),accepted_receipt_sha256=sha(RECEIPT)))
        perdescriptor=metrics.filter(pc.equal(metrics['descriptor'],k))
        for mode in MODES:
            per_mode=perdescriptor.filter(pc.equal(perdescriptor['mode'],mode))
            for region in REGIONS:
                r=lookup[k,mode,region];part=per_mode.filter(pc.equal(per_mode['region'],region));assert part.num_rows==9000
                qi=part['query_index'].to_pylist();sid=part['query_scene_id'].to_pylist()
                assert sorted(qi)==list(range(9000)) and all(pop[i]==s for i,s in zip(qi,sid))
                assert part['value'].null_count==r['query_invalid_count'] and 9000-part['value'].null_count==r['query_valid_count']
                assert r['query_total_count']==9000
                # Support summation is validation only; exported counts are copied from accepted summary.
                for stem in ['total','valid','invalid']:assert pc.sum(part[stem+'_count']).as_py()==r['candidate_'+stem+'_count']
                assert r['candidate_valid_count']+r['candidate_invalid_count']==r['candidate_total_count']
                nrs=sorted(x for x in pc.unique(part['null_reason']).to_pylist() if x is not None)
                row=dict(descriptor=k,display_name=names[k],family=FAMILIES[byid[k]['family']],family_key=byid[k]['family'],kind=byid[k]['kind'],mode=mode,mode_display=MODES[mode],region=region,region_display=REGIONS[region],
                    units=byid[k]['units'],difference_units=UNITS[byid[k]['units']],statistic_units='dimensionless' if region=='rho' else UNITS[byid[k]['units']],
                    **{name:r[src] for name,src in COLS.items()},null_reason_categories=nrs,
                    null_reason_category_source='distinct stored query_metrics.null_reason; accepted summary does not provide reason frequencies',**provenance)
                assert all(not isinstance(v,float) or math.isfinite(v) for v in row.values())
                all_rows.append(row)
    out.mkdir(parents=True,exist_ok=False);write_json(out/'preservation_snapshot.json',baseline)
    align=[r for r in all_rows if r['region']=='rho'];bands=[r for r in all_rows if r['region']!='rho']
    for name,rows in [('fm_alignment_summary',align),('fm_rank_region_summary',bands),('fm_descriptor_support',supports)]:
        write_csv(out/(name+'.csv'),rows);write_json(out/(name+'.json'),rows);pq.write_table(pa.Table.from_pylist(rows),out/(name+'.parquet'))
    write_json(out/'source_provenance.json',dict(provenance,descriptor_order=ORDER,modes=MODES,regions=REGIONS,
        registry=[{k:v for k,v in d.items() if k not in ('category_keys','category_labels')} for d in dictionary],
        retrieval=json.loads(Path('config/s11_representation_analysis.json').read_text())['retrieval'],
        statement='Read-only transcription of accepted summaries. No ranks, correlations, quantiles, descriptors, UMAP or embeddings recomputed. Null reasons enumerated from stored records; count sums used only for validation.'))
    # Copy the exact current dissertation helpers into this isolated support directory.
    (out/'style').mkdir()
    for name in ['tables.typ','captions.typ']:shutil.copyfile(DISS/'src'/name,out/'style'/name);assert sha(out/'style'/name)==sha(DISS/'src'/name)
    cells=[]
    def add(file,key,field,value,text):
        cells.append({'file':file,'descriptor':key[0],'mode':key[1],'region':key[2],'field':field,'value':value,'display':text})
        return cell(text)
    def num(file,key,field):return add(file,key,field,lookup[key][COLS[field]],fmt(lookup[key][COLS[field]]))
    def nquery(file,key):
        r=lookup[key];return add(file,key,'valid_queries',r['query_valid_count'],f'{r["query_valid_count"]:,} / 9000')
    def begin(variable,columns,headers,font=8.5):
        return ['#import "style/tables.typ": thesis-table','// On authorized dissertation integration, import ../../../src/tables.typ instead.',f'#let {variable} = {{',f'  set text(size: {font}pt, number-type: "lining", number-width: "tabular")','  set par(leading: 0.25em)','  thesis-table(','    table(',f'      columns: ({columns}),', '      align: (left, '+', '.join(['right']*(len(headers)-1))+'),','      inset: (x: 3pt, y: 3pt),','      stroke: 0.3pt + luma(80%),','      table.header('+', '.join(cell('*'+x+'*') for x in headers)+'),']
    def end(lines,title,detail):return lines+['    ),',f'    caption-title: [{title}],',f'    caption-detail: [{detail}],','  )','}']
    # Main A: identical valid counts in both modes permit one clearly labelled support column.
    f='fm_alignment_summary.typ';lines=begin('fm-alignment-summary','2.05fr, 1.45fr, 1.45fr, 1.35fr',['Descriptor','Standard\nmedian ρ [IQR]','Non-local\nmedian ρ [IQR]','Valid queries\n(both modes)'])
    for fam,label in FAMILIES.items():
        lines.append(f'      table.cell(colspan: 4, fill: luma(95%), align: left)[*{label}*],')
        for k in ORDER:
            if byid[k]['family']!=fam:continue
            parts=[cell(names[k])]
            for mode in MODES:
                key=(k,mode,'rho');r=lookup[key];text=fmt(r['query_median'])+' ['+fmt(r['query_iqr'])+']'
                add(f,key,'median',r['query_median'],fmt(r['query_median']));add(f,key,'IQR',r['query_iqr'],fmt(r['query_iqr']));parts.append(cell(text))
            assert lookup[k,'standard','rho']['query_valid_count']==lookup[k,'nonlocal','rho']['query_valid_count']
            parts.append(nquery(f,(k,'standard','rho')));lines.append('      '+', '.join(parts)+',')
    lines=end(lines,'Geographic-characteristic alignment of FM','Median query-wise Spearman ρ with IQR width in brackets (not Q1–Q3 endpoints). More negative values indicate stronger descriptive alignment between representation similarity and smaller descriptor differences. Standard excludes self; Non-local additionally excludes centers less than 2 km away. Valid-query counts are identical across modes. Undefined queries are excluded, never assigned zero. These input-derived descriptors are not external ground truth.')
    (out/f).write_text('\n'.join(lines)+'\n// Suggested use: #fm-alignment-summary <tab:fm-geographic-alignment>\n')
    # Main B: fixed D6 representatives, full-vector compositions (never dominant classes).
    f='fm_rank_region_main.typ';lines=begin('fm-rank-region-main','2.5fr, 1.0fr, 1fr, 1fr, 1fr, 1fr',['Descriptor (unit)','Mode','Rank 1','Upper','Middle','Lower'])
    for k in PRIMARY:
        for mi,mode in enumerate(MODES):
            parts=[cell(names[k]+' ('+UNITS[byid[k]['units']]+')' if mi==0 else ''),cell(MODES[mode])]+[num(f,(k,mode,b),'median') for b in ['rank1','upper','middle','lower']]
            lines.append('      '+', '.join(parts)+',')
    lines=end(lines,'Rank-region geographic differences for the fixed FM representatives','Median across queries of each query’s arithmetic mean difference over valid candidates in a fixed band. Representatives are the six descriptors fixed for the main UMAP, without result-based selection. Scalar differences retain their units; composition differences use full-vector Euclidean distance (dimensionless L2). No invalid slots are refilled. Supports vary by descriptor and region; complete supports and quartiles accompany the supplementary tables. Nonmonotonic progression is not a failure.')
    (out/f).write_text('\n'.join(lines)+'\n// Suggested use: #fm-rank-region-main <tab:fm-rank-region-alignment>\n')
    full_calls=[]
    for fam,label in FAMILIES.items():
        for mode,mlabel in MODES.items():
            f=f'fm_rank_region_{fam}_{mode}.typ';var=f'fm-rank-region-{fam}-{mode}'
            lines=begin(var,'2.15fr, .8fr, 1fr, 1fr, 1fr, 1fr, 1.3fr',['Descriptor (unit)','Region','Median','Q1','Q3','IQR','Valid / undef.'],8)
            for k in ORDER:
                if byid[k]['family']!=fam:continue
                for bi,b in enumerate(['rank1','upper','middle','lower']):
                    key=(k,mode,b);r=lookup[key];parts=[]
                    if bi==0:parts.append(f'table.cell(rowspan: 4, align: left + horizon){cell(names[k]+" ("+UNITS[byid[k]["units"]]+")")}')
                    parts.append(cell(REGIONS[b]));parts += [num(f,key,x) for x in ['median','Q1','Q3','IQR']]
                    text=f'{r["query_valid_count"]:,} / {r["query_invalid_count"]:,}'
                    add(f,key,'valid_queries',r['query_valid_count'],f'{r["query_valid_count"]:,}');add(f,key,'undefined_queries',r['query_invalid_count'],f'{r["query_invalid_count"]:,}')
                    parts.append(cell(text));lines.append('      '+', '.join(parts)+',')
            lines=end(lines,f'FM rank-region differences: {label.lower()}, {mlabel}', 'Accepted query-level difference summaries; all 9,000 queries are retained in the population. Undefined query summaries are excluded from quartiles. IQR is Q3 minus Q1; full precision and candidate total/valid/invalid supports are preserved in the machine-readable companion. Scalar units are unchanged; L2 refers to the Euclidean distance between full proportion vectors, not dominant categories.')
            (out/f).write_text('\n'.join(lines)+'\n')
            full_calls += [f'#import "{f}": {var}',f'#{var} <tab:fm-rank-region-{fam}-{mode}>','#pagebreak()']
    (out/'fm_rank_region_full.typ').write_text('\n'.join(full_calls[:-1])+'\n')
    write_json(out/'typst_cell_audit.json',cells)
    preview=['#set page(width: 190mm, height: 260mm, margin: (left: 30mm, right: 30mm, top: 20mm, bottom: 15mm))','#set text(font: "New Computer Modern", size: 10pt)','#set figure(numbering: "1", placement: none)','#set figure.caption(position: top)','#import "fm_alignment_summary.typ": fm-alignment-summary','#import "fm_rank_region_main.typ": fm-rank-region-main','#fm-alignment-summary <tab:fm-geographic-alignment>','#pagebreak()','#fm-rank-region-main <tab:fm-rank-region-alignment>','#pagebreak()','#include "fm_rank_region_full.typ"']
    (out/'preview.typ').write_text('\n'.join(preview)+'\n')
    # Independent serialization read-back against source values, not recomputed statistics.
    csv_checks=0
    for name,expected in [('fm_alignment_summary',align),('fm_rank_region_summary',bands),('fm_descriptor_support',supports)]:
        j=json.loads((out/(name+'.json')).read_text());assert j==expected
        assert pq.read_table(out/(name+'.parquet')).to_pylist()==expected
        rows=list(csv.DictReader((out/(name+'.csv')).open()));assert len(rows)==len(expected)
        for row,ref in zip(rows,expected):
            for k,v in ref.items():
                got=row[k]
                if v is None:assert got=='null'
                elif isinstance(v,(list,dict)):assert json.loads(got)==v
                elif isinstance(v,float):assert float(got)==v and math.isfinite(float(got))
                elif isinstance(v,int):assert int(got)==v
                else:assert got==v
                csv_checks+=1
    fresh={(r['descriptor'],r['mode'],r['region']):r for r in pq.read_table(summary_path).to_pylist()}
    for row in json.loads((out/'fm_alignment_summary.json').read_text())+json.loads((out/'fm_rank_region_summary.json').read_text()):
        ref=fresh[row['descriptor'],row['mode'],row['region']]
        for k,v in COLS.items():assert row[k]==ref[v]
    for c in json.loads((out/'typst_cell_audit.json').read_text()):
        value=fresh[c['descriptor'],c['mode'],c['region']][COLS[c['field']]];assert c['value']==value
        assert c['display'] in (out/c['file']).read_text().replace('\\[','[').replace('\\]',']')
        if isinstance(value,float):assert c['display']==fmt(value)
    unchanged(baseline)
    write_json(out/'extraction_validation.json',{'status':'PASS','summary_rows':220,'rho_rows':44,'rank_region_rows':176,'descriptor_support_rows':22,'population':9000,'query_metric_records_checked':1980000,'CSV_cells_checked':csv_checks,'Typst_numeric_cells_checked':len(cells),'scientific_statistic_recomputation':False,'query_support_validation':'count/sum read-back of accepted records only','null_reason_inventory':'distinct stored categories only, not frequency analysis','S11_receipt_files_unchanged':1352,'S12_files_unchanged':27427,'preserved_files':len(baseline)})
    print('EXTRACTION PASS '+str(out),flush=True)

if __name__=='__main__':main()
