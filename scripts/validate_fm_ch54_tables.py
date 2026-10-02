#!/usr/bin/env python
"""Independent cell-by-cell comparison of compiled Typst tables with accepted FM rows."""
from pathlib import Path
import json,sys,math,subprocess
import pyarrow.parquet as pq
OUT=Path(sys.argv[1]);ROOT=Path('/mnt/hdd002/dhnyu/fusedata/analysis_data/reduced/s11_representation/df3b397b64b6aeebde547b2e')
source=pq.read_table(ROOT/'alignment_summaries/summaries/summary.parquet').to_pylist()
lookup={(r['descriptor'],r['mode'],r['region']):r for r in source}
dictionary=json.loads((ROOT/'descriptor_acceptance/accepted/dictionary.json').read_text())
meta=json.loads((OUT/'fm_descriptor_support.json').read_text());display={r['descriptor']:r['display_name'] for r in meta}
units={'fraction':'fraction','km/km2':'km/km²','entities/km2':'entities/km²','m2':'m²','m':'m','1':'dimensionless','neighbors/entity':'neighbors/entity','proportion':'dimensionless L2','lanes':'lanes'}
compiled=json.loads((OUT/'compiled_table_cells.json').read_text());assert len(compiled)==14

def txt(node):
    if isinstance(node,list):return ''.join(txt(n) for n in node)
    if not isinstance(node,dict):return ''
    if node.get('func')=='space':return ' '
    if 'text' in node:return node['text']
    return txt(node.get('body',node.get('children',[])))

def display_num(v):return '—' if v is None else f'{v:.3f}'.replace('-','−')

checks=0
# Table A: verify actual compiled text by descriptor, mode and column.
children=compiled[0]['children'];assert children[0]['func']=='header';i=1
families=list(dict.fromkeys(d['family'] for d in dictionary))
for fam in families:
    assert children[i]['colspan']==4;i+=1
    for d in (d for d in dictionary if d['family']==fam):
        k=d['id'];assert txt(children[i])==display[k];checks+=1;i+=1
        for mode in ('standard','nonlocal'):
            r=lookup[k,mode,'rho'];expected=f'{display_num(r["query_median"])} [{display_num(r["query_iqr"])}]'
            assert txt(children[i])==expected,(k,mode,txt(children[i]),expected);i+=1;checks+=1
        assert txt(children[i])==f'{lookup[k,"standard","rho"]["query_valid_count"]:,} / 9000';i+=1;checks+=1
assert i==len(children)
# Table B-main: six frozen representatives, explicitly not selected by numeric outcome.
primary=['building_coverage','mean_building_compactness','building_location_dispersion','mean_relational_degree','poi_l2_composition','landcover_composition']
byid={d['id']:d for d in dictionary};children=compiled[1]['children'];i=1
for k in primary:
    for mi,mode in enumerate(('standard','nonlocal')):
        assert txt(children[i])==(display[k]+' ('+units[byid[k]['units']]+')' if mi==0 else '');i+=1
        assert txt(children[i])==('Standard' if mi==0 else 'Non-local');i+=1;checks+=2
        for b in ['rank1','upper','middle','lower']:
            assert txt(children[i])==display_num(lookup[k,mode,b]['query_median']);i+=1;checks+=1
assert i==len(children)
# Each family/mode supplementary table carries all four statistics and both query counts.
table_index=2
for fam in families:
    for mode in ('standard','nonlocal'):
        children=compiled[table_index]['children'];table_index+=1;i=1
        for d in (d for d in dictionary if d['family']==fam):
            k=d['id'];assert children[i]['rowspan']==4
            assert txt(children[i])==display[k]+' ('+units[d['units']]+')';i+=1;checks+=1
            for b,label in [('rank1','Rank 1'),('upper','Upper'),('middle','Middle'),('lower','Lower')]:
                r=lookup[k,mode,b];assert txt(children[i])==label;i+=1;checks+=1
                for field in ['query_median','query_q1','query_q3','query_iqr']:
                    assert txt(children[i])==display_num(r[field]),(k,mode,b,field);i+=1;checks+=1
                assert txt(children[i])==f'{r["query_valid_count"]:,} / {r["query_invalid_count"]:,}';i+=1;checks+=1
        assert i==len(children)
lock=json.loads(Path('config/s11_representation_analysis.lock.json').read_text())
embedding=json.loads(Path(lock['parents']['fm_embedding_manifest']['path']).read_text())['body']
assert embedding['model']['configuration_id']=='cmp_FM'
checkpoint=json.loads(Path(lock['parents']['checkpoint_manifest']['path']).read_text())
assert checkpoint['completed_epoch']==60 and checkpoint['checkpoint_id']==embedding['model']['checkpoint_id']
pop=pq.read_table(ROOT/'accepted_parents/parents/population.parquet')['scene_id'].to_pylist();assert pop==embedding['scene_ids']
result={'status':'PASS','compiled_tables':14,'compiled_data_cells_checked':checks,'exact_accepted_source_keys':220,'direct_compiled_Typst_readback':True,'checkpoint_epoch':60,'configuration_id':'cmp_FM','population_order_matches_accepted_embedding':True,'recomputed_statistics':False}
(OUT/'independent_table_validation.json').write_text(json.dumps(result,indent=2)+'\n');print(result)
