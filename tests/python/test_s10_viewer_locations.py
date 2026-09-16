"""Metadata-only fixtures: no accepted ranking/model execution."""
import ast
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / 'tools/retrieval_inspector/supplemental/build_locations.py'
spec = importlib.util.spec_from_file_location('s10_build_locations', MODULE)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def fixture(n=2):
    rows=[dict(scene_id=f's{i:05}',center_x=190294.72045749245+i,center_y=539681.6337786105,epsg=5186,split='evaluation') for i in range(n)]
    gallery={'body':{'crs':'EPSG:5186','units':'metres','rows':rows}}
    assignments={'transform':{'fixture':True},'rows':[dict(scene_id=r['scene_id'],longitude='126.89031234567891',latitude='37.456501234567891',sigungu_code='11180',sigungu_name='금천구',eupmyeondong_code='11180520',eupmyeondong_name='독산1동',sigungu_join_status='unique_match',dong_join_status='unique_match',sigungu_candidate_codes=['11180'],sigungu_candidate_names=['금천구'],dong_candidate_codes=['11180520'],dong_candidate_names=['독산1동'],hierarchy_status='consistent') for r in rows]}
    return gallery,assignments


def test_r_coordinate_boundary_fixtures():
    subprocess.run(['Rscript','tests/test_viewer_locations.R'],cwd=ROOT,check=True)


def test_exact_coordinates_full_gallery_unique_once_and_deterministic():
    g,a=fixture(9000)
    first=m.make_metadata(g,a,{})
    assert m.encoded(first)==m.encoded(m.make_metadata(g,a,{}))
    assert len(first['scenes'])==9000
    assert first['qc']['sigungu_unique_match_count']==first['qc']['dong_unique_match_count']==9000
    r=first['scenes']['s00000']
    assert r['center_x']==g['body']['rows'][0]['center_x']
    assert r['longitude']==float(a['rows'][0]['longitude']) and r['longitude']!=round(r['longitude'],5)
    assert r['eupmyeondong_name']=='독산1동'


@pytest.mark.parametrize('fault',['duplicate','missing','axis','nonfinite','hierarchy','false_unique','center'])
def test_bad_metadata_rejected(fault):
    g,a=fixture()
    if fault=='duplicate':g['body']['rows'][1]['scene_id']=g['body']['rows'][0]['scene_id']
    elif fault=='missing':a['rows'].pop()
    elif fault=='axis':g['body']['crs']='EPSG:5179'
    elif fault=='nonfinite':a['rows'][0]['latitude']='nan'
    elif fault=='hierarchy':
        a['rows'][0]['eupmyeondong_code']='99999520';a['rows'][0]['dong_candidate_codes']=['99999520']
    elif fault=='false_unique':a['rows'][0]['dong_candidate_codes']=[]
    elif fault=='center':
        with pytest.raises(ValueError,match='CENTER_BINDING'):m.bind_scene({'scene_id':'s00000','center':[0,0]},m.validate_gallery(g,2))
        return
    with pytest.raises(ValueError):m.make_metadata(g,a,{},2)


def test_zero_and_ambiguous_keep_no_arbitrary_label():
    g,a=fixture()
    for i,codes,names,status in [(0,[],[],'no_polygon_match'),(1,['11180520','11180530'],['독산1동','독산2동'],'boundary_ambiguous')]:
        a['rows'][i].update(eupmyeondong_code=None,eupmyeondong_name=None,dong_join_status=status,dong_candidate_codes=codes,dong_candidate_names=names,hierarchy_status='not_comparable')
    result=m.make_metadata(g,a,{},2)
    assert result['qc']['dong_no_polygon_match_count']==1
    assert result['qc']['dong_boundary_ambiguous_count']==1
    assert all(r['eupmyeondong_name'] is None for r in result['scenes'].values())


def test_checksum_mismatch_and_immutable_reuse(tmp_path):
    f=tmp_path/'source';f.write_text('first');record={'path':str(f),'sha256':m.file_hash(f)}
    assert m.pinned(record)==f
    f.write_text('mutated')
    with pytest.raises(ValueError,match='CHECKSUM'):m.pinned(record)
    receipt={'files':{'source':m.file_hash(f)}}
    (tmp_path/'viewer_receipt.json').write_bytes(m.encoded(receipt));m.validate_existing(tmp_path,receipt)
    f.write_text('collision')
    with pytest.raises(ValueError,match='COLLISION'):m.validate_existing(tmp_path,receipt)


def test_imports_and_invocation_cannot_execute_science():
    tree=ast.parse(MODULE.read_text());imports=set()
    for node in ast.walk(tree):
        if isinstance(node,ast.Import):imports.update(n.name for n in node.names)
        elif isinstance(node,ast.ImportFrom):imports.add(node.module)
    assert imports <= {'__future__','argparse','collections','hashlib','json','math','os','pathlib','shutil','subprocess','tempfile'}
    for forbidden in ['torch','numpy','reconstruct(','build_bands(','tar_make','training_controller','retrieval_inference']:
        assert forbidden not in MODULE.read_text()
    assert 'build_viewer_locations.R' in MODULE.read_text()
    r=(ROOT/'scripts/build_viewer_locations.R').read_text()+(ROOT/'R/viewer_locations.R').read_text()
    assert 'st_covered_by' in r and 'st_nearest' not in r and 'targets::' not in r


def test_ui_lookup_rounding_missing_and_ambiguous(tmp_path):
    g,a=fixture();metadata=m.make_metadata(g,a,{},2)
    # Browser contract is 9000: pad synthetic rows without running geospatial science.
    metadata['scenes'].update({f'extra{i}':{} for i in range(8998)})
    data=tmp_path/'metadata.json';data.write_text(json.dumps(metadata))
    js=r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const metadata=JSON.parse(fs.readFileSync(process.argv[1]));
const context={window:{},esc:s=>String(s),artifact:async()=>metadata};vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[2],'utf8'),context);
(async()=>{const api=context.window.S10Locations;await api.init({location_metadata:{path:'fixture',artifact_id:metadata.artifact_id}});
for(const id of ['s00000','s00001','s00000']){const r=metadata.scenes[id];const before=JSON.stringify(r);const html=api.block({scene_id:id,center:[r.center_x,r.center_y]});assert(html.includes(id));assert(html.includes('독산1동'));assert(html.includes('126.89031'));assert.equal(JSON.stringify(r),before)}
const r=metadata.scenes.s00000;r.dong_join_status='no_polygon_match';assert(api.block({scene_id:r.scene_id,center:[r.center_x,r.center_y]}).includes('행정동 확인 불가'));
r.dong_join_status='boundary_ambiguous';assert(api.block({scene_id:r.scene_id,center:[r.center_x,r.center_y]}).includes('행정동 경계 지점'));
assert.throws(()=>api.block({scene_id:'missing',center:[0,0]}));
assert.throws(()=>api.block({scene_id:r.scene_id,center:[0,0]}));
})().catch(e=>{console.error(e);process.exit(1)});
'''
    subprocess.run(['node','-e',js,str(data),str(ROOT/'tools/retrieval_inspector/supplemental/locations.js')],check=True)
