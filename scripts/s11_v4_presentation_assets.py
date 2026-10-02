"""Read-only accepted observations -> display backgrounds/codebooks, S11 5.4.1.
No descriptors, learned features, alignments or scientific outputs are computed.
"""
from pathlib import Path
import base64,copy,csv,hashlib,io,json,math,tarfile,tempfile,textwrap
import xml.etree.ElementTree as ET
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pyarrow.compute as pc
import zarr
from PIL import Image
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.backends.backend_pdf import PdfPages
from revisualize_s11_publication import sha,write_json,run,FAMILIES,ROOT
NS='{http://www.w3.org/2000/svg}';XL='{http://www.w3.org/1999/xlink}'
ET.register_namespace('',NS[1:-1]);ET.register_namespace('xlink',XL[1:-1])


def write_codebooks(out,byid,mapping):
    lock=json.loads(Path('config/s11_representation_analysis.lock.json').read_text())
    pin=lock['parents']['categories'];assert sha(pin['path'])==pin['sha256']
    entries=json.loads(Path(pin['path']).read_text())['entries']
    attrs={'building_use_composition':'A9','building_structure_composition':'A11','road_type_composition':'ROAD_TYPE','road_hierarchy_composition':'ROAD_RANK','poi_l2_composition':'CLASS_L2'}
    official={str(r['internal']):r for r in json.loads(Path('config/retrieval_lc_official_palette.json').read_text())['rows']}
    rows=[]
    for m in mapping:
        k=m['descriptor'];key=m['category_key'];source=key;meaning=m['accepted_label'];note=m['code_origin']
        if k in attrs:
            e=next(e for e in entries if e['attribute']==attrs[k] and e['category_key']==key)
            source=' / '.join(e['source_codes']);meaning=e['source_label']
            if k.startswith('road_'):note+='; accepted source label is code-only, no unsupported expansion added'
        elif k=='landcover_composition':
            e=official[key];source=str(e['official']);meaning=e['category'];note='accepted internal LC code; official source code listed separately'
        elif k=='relation_composition':
            meaning={'SN':'Spatial neighborhood','INC':'Inclusion (CNT/WIT merged)','INT':'Intersection','CON':'Connectivity'}[key]
            note='frozen relation event code'+('; CNT/WIT merged' if key=='INC' else '')
        rows.append({'panel_family':FAMILIES[byid[k]['family']],'descriptor':k,'display_code':m['code_label'],'accepted_category_key':key,'original_source_codes':source,'source_label':meaning,'code_note':note,'dictionary_index':m['dictionary_index'],'displayed_dominant':m['displayed_as_dominant'],'color':m['color']})
    assert len(rows)==sum(len(d['category_keys']) for d in byid.values() if d['kind']=='compositional')
    font_manager.fontManager.addfont('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')
    for name,selection in [('categorical_codebook_all',rows),('family_semantics_codebook',[r for r in rows if r['panel_family']=='Semantic attributes'])]:
        with (out/(name+'.csv')).open('w') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(selection)
        with plt.rc_context({'font.family':'Noto Sans CJK JP','pdf.fonttype':42}), PdfPages(out/(name+'.pdf'),metadata={'CreationDate':None,'ModDate':None}) as pdf:
            page=0
            for k in dict.fromkeys(r['descriptor'] for r in selection):
                rs=[r for r in selection if r['descriptor']==k]
                for start in range(0,len(rs),20):
                    page+=1;part=rs[start:start+20];fig=plt.figure(figsize=(11.69,8.27));ax=fig.add_axes([.035,.10,.93,.78]);ax.axis('off')
                    fig.text(.035,.955,part[0]['panel_family']+' / '+k,fontsize=11)
                    fig.text(.035,.92,'Complete frozen dictionary; BU = display alias, not official source code. Blank color = never dominant.',fontsize=8)
                    cells=[]
                    for r in part:
                        origin='BU alias' if r['display_code'].startswith('BU') else ('LC internal' if k=='landcover_composition' else 'Accepted code')
                        cells.append([r['display_code'],'\n'.join(textwrap.wrap(r['original_source_codes'],22)),r['source_label'],origin,r['color'] or '—'])
                    table=ax.table(cellText=cells,colLabels=['Display code','Original source code(s)','Accepted label / meaning','Code type','Color'],colWidths=[.13,.24,.40,.13,.10],bbox=[0,1-len(part)/20,1,len(part)/20],cellLoc='left')
                    table.auto_set_font_size(False);table.set_fontsize(8)
                    for (i,j),cell in table.get_celld().items():
                        cell.set_edgecolor('#cccccc');cell.set_linewidth(.3)
                        if i==0:cell.set_facecolor('#eeeeee')
                        elif j==1 and cells[i-1][1].count('\n')>=2:cell.get_text().set_fontsize(6.5)
                    fig.text(.035,.04,'CSV retains accepted category keys, all aliases, dictionary order and provenance notes. Road labels are code-only in the accepted dictionary.',fontsize=7)
                    fig.text(.94,.04,str(page),fontsize=8);pdf.savefig(fig);plt.close(fig)
    write_json(out/'codebook_validation.json',{'complete_categories':len(rows),'descriptors':7,'accepted_categories_sha256':pin['sha256'],'all_v3_aliases_unchanged':True,'road_label_limitation':'Accepted source label is numeric code; meanings not invented.'})


def uri(im):
    b=io.BytesIO();im.save(b,format='PNG');return 'data:image/png;base64,'+base64.b64encode(b.getvalue()).decode()


def display_layers(f,valid,z,dvalid):
    assert f.shape==(22,100,100) and valid.shape==(100,100) and z.shape==dvalid.shape==(17,17)
    assert np.isfinite(f).all() and np.isfinite(z[dvalid]).all()
    palette=np.array([r['rgb'] for r in json.loads(Path('config/retrieval_lc_official_palette.json').read_text())['rows']],dtype=float)
    # Same pixelwise fraction-weighted official RGB as the S10 inspector; no class aggregation.
    rgb=np.clip(np.einsum('cyx,ck->yxk',f.astype(float),palette),0,255).astype('uint8')
    lc=Image.fromarray(np.concatenate([rgb,(valid.astype('uint8')*255)[...,None]],axis=2)).resize((500,500),Image.Resampling.NEAREST)
    dz_south,dz_east=np.gradient(np.where(dvalid,z,0.).astype(float),500/17,500/17)
    az=math.radians(315);alt=math.radians(45);nx=-dz_east;ny=dz_south
    h=(nx*math.sin(az)*math.cos(alt)+ny*math.cos(az)*math.cos(alt)+math.sin(alt))/np.sqrt(nx*nx+ny*ny+1)
    good=dvalid.copy();good[1:]&=dvalid[:-1];good[:-1]&=dvalid[1:];good[:,1:]&=dvalid[:,:-1];good[:,:-1]&=dvalid[:,1:]
    h=np.where(good,np.clip(h,0,1),math.sin(alt))
    h=np.asarray(Image.fromarray(h.astype('float32')).resize((500,500),Image.Resampling.BILINEAR))
    tone=np.clip(.94+.18*(h-math.sin(alt)),0,1)
    shade=Image.fromarray(np.repeat(np.rint(tone*255).astype('uint8')[...,None],3,axis=2))
    return shade,lc


def add_raster_backgrounds(out,v1,v3,baseline):
    cfg=json.loads(Path('config/s11_execution.json').read_text())
    for pin in cfg['p3_pins'].values():
        assert sha(pin['path'])==pin['sha256'];baseline[pin['path']]=pin['sha256']
    index={r['scene_id']:r for r in pq.read_table(cfg['p3_pins']['index']['path']).to_pylist()}
    letters=list(csv.DictReader((v3/'scene_mapping_a_i.csv').open()));assert [r['label'] for r in letters]==list('ABCDEFGHI')
    selected={r['scene_id']:r for r in letters};grouped={}
    for sid in selected:grouped.setdefault(index[sid]['branch_id'],[]).append(sid)
    source= v1/'main_umap_ai.svg';doc=ET.parse(source);root=doc.getroot();prior=copy.deepcopy(root)
    nested=root.findall(NS+'svg');assert len(nested)==9
    page=next(e for e in root.iter() if e.get('id')=='acceptedIllustrationPage')
    # Preserve every existing non-background vector element byte-for-byte in XML.
    white=[e for e in list(page) if e.get('fill')=='rgb(100%, 100%, 100%)'];assert len(white)==10
    before_vector=[ET.tostring(e) for e in page if e not in white]
    for e in white:page.remove(e)
    assert [ET.tostring(e) for e in page]==before_vector
    records=[];assets=out/'illustration_backgrounds';assets.mkdir()
    zarr.config.set({'async.concurrency':1,'threading.max_workers':1})
    for branch,sids in grouped.items():
        spec=index[sids[0]];path=Path(cfg['p3_root'])/'shards'/branch/spec['payload_filename']
        assert sha(path)==spec['payload_sha256'];baseline[str(path)]=spec['payload_sha256']
        with tempfile.TemporaryDirectory(prefix='s11-v4-raster-') as temp,tarfile.open(path,'r:') as tar:
            table=pq.read_table(pa.BufferReader(tar.extractfile('raster/scene_raster_index.parquet').read()))
            rr=table.filter(pc.is_in(table['scene_id'],value_set=pa.array(sids))).to_pylist();assert len(rr)==len(sids)
            wanted={str(r['zarr_index']) for r in rr}
            for member in tar.getmembers():
                parts=Path(member.name).parts
                if len(parts)<3 or parts[0]!='raster' or parts[1] not in ('scene_landcover.zarr','scene_dem.zarr'):continue
                leaf=parts[-1]
                if not (leaf.startswith('.') or leaf.split('.')[0] in wanted):continue
                assert member.isfile() and '..' not in parts and not Path(member.name).is_absolute()
                dest=Path(temp)/member.name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(tar.extractfile(member).read())
            lc=zarr.open_group(str(Path(temp)/'raster/scene_landcover.zarr'),mode='r');dem=zarr.open_group(str(Path(temp)/'raster/scene_dem.zarr'),mode='r')
            for r in rr:
                sid=r['scene_id'];label=selected[sid]['label'];i=ord(label)-65;z=r['zarr_index']
                assert r['row_order']=='north_to_south' and r['column_order']=='west_to_east' and r['split']=='evaluation'
                assert r['xmax']-r['xmin']==r['ymax']-r['ymin']==500
                f=lc['class_fraction'][z];valid=lc['valid_mask'][z].astype(bool);raw=dem['raw_mean_m'][z];dv=dem['valid_mask'][z].astype(bool)
                shade,lci=display_layers(f,valid,raw,dv);shade.save(assets/(label+'_hillshade.png'));lci.save(assets/(label+'_landcover.png'))
                node=nested[i];x,y,w,h=map(float,node.get('viewBox').split())
                for order,(im,opacity) in enumerate([(shade,1),(lci,.50)]):
                    node.insert(order,ET.Element(NS+'image',{'x':str(x),'y':str(y),'width':str(w),'height':str(h),'preserveAspectRatio':'none','opacity':str(opacity),XL+'href':uri(im)}))
                records.append({'label':label,'scene_id':sid,'extent':[r['xmin'],r['ymin'],r['xmax'],r['ymax']],'source_shard':str(path),'source_sha256':spec['payload_sha256'],'raster_index':r,'LC_fraction_sha256':hashlib.sha256(f.tobytes()).hexdigest(),'raw_DEM_sha256':hashlib.sha256(raw.tobytes()).hexdigest(),'lc_valid_pixels':int(valid.sum()),'dem_valid_cells':int(dv.sum()),'vector_elements_unchanged':True,'viewport_attributes':node.attrib})
        print('A-I raster background '+','.join(selected[s]['label'] for s in sids),flush=True)
    # Only shared illustration white fills and nested raster children changed.
    for a,b in zip(list(prior),list(root),strict=True):
        if a.tag==NS+'svg':assert a.attrib==b.attrib
        elif any(e.get('id')=='acceptedIllustrationPage' for e in a.iter()):continue
        else:assert ET.tostring(a)==ET.tostring(b),'NON_ILLUSTRATION_SVG_CHANGE'
    output=out/'main_umap_ai_lc_dem.svg';doc.write(output,encoding='utf-8',xml_declaration=True)
    run('rsvg-convert','--format=pdf','--output',out/'main_umap_ai_lc_dem.pdf',output)
    run('pdftoppm','-singlefile','-png','-r','300',out/'main_umap_ai_lc_dem.pdf',out/'main_umap_ai_lc_dem')
    old=np.asarray(Image.open(v3/'main_umap_ai.png').convert('RGB'));new=np.asarray(Image.open(out/'main_umap_ai_lc_dem.png').convert('RGB'));assert old.shape==new.shape
    # Pixel differences must lie inside the nine pre-existing scene rectangles.
    allowed=np.zeros(old.shape[:2],bool)
    for e in nested:
        x,y,w,h=[float(e.get(k)) for k in ['x','y','width','height']];x0=int(x*300/72)-2;y0=int(y*300/72)-2;x1=math.ceil((x+w)*300/72)+2;y1=math.ceil((y+h)*300/72)+2
        allowed[y0:y1,x0:x1]=True
    assert np.array_equal(old[~allowed],new[~allowed]),'OUTSIDE_A_I_PIXELS_CHANGED'
    result={'scene_count':9,'scene_order':[r['scene_id'] for r in letters],'records':sorted(records,key=lambda r:r['label']),'outside_A_I_pixels_identical':True,'left_UMAP_identical':True,'existing_vectors_unchanged':True,'layer_order':['DEM hillshade','LC at opacity 0.50','accepted buildings','accepted roads','accepted POIs'],'hillshade':{'source':'17x17 original raw_mean_m in metres','azimuth':315,'altitude':45,'vertical_exaggeration':1,'gray_rule':'0.94 + 0.18 * (illumination - sin(45deg))','invalid_derivative_support':'neutral shade; no imputation','resampling':'bilinear shade, nearest LC'},'scientific_analysis':False}
    write_json(out/'illustration_layer_metadata.json',result)
    # New read-only sources added after initial snapshot remain in final preservation evidence.
    write_json(out/'preservation_snapshot.json',baseline)
    return result
