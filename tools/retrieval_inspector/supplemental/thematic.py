"""Bind stored SVG entity order to stored categorical rows; change colour only.

Accepted retrieval_render serializes one SVG child per OriginalReader entity.
OriginalReader and tensorize_scene both preserve sorted local_entity_id order.
No geometry reconstruction, coordinate transforms, joins or attribute inference.
"""
from collections import Counter
import colorsys
import xml.etree.ElementTree as ET

from retrieval_artifacts import require, digest

SVG = '{http://www.w3.org/2000/svg}'
LAYER_COLORS = {0:'#667085',1:'#e4a11b',2:'#c83e63'}
ATTRIBUTES = {
    'POI categories · L1': ('poi',0,'CLASS_L1',2),
    'Building use': ('building',0,'A9',0),
    'Building structure': ('building',1,'A11',0),
    'Road rank': ('road',0,'ROAD_RANK',1),
}
LANE_UNAVAILABLE = 'ROAD LANE THEMATIC MAP NOT AVAILABLE FROM CURRENT ACCEPTED DISPLAY SOURCE'


def color(index, size):
    # Stable vocabulary-index palette across every query/model. Missing/masked neutral.
    if index >= size-2:
        return '#999999'
    rgb = colorsys.hls_to_rgb((index * .618033988749895) % 1, .43, .60)
    return '#' + ''.join(f'{round(c*255):02x}' for c in rgb)


def bind(sample, svg, render_record, names, original_sha):
    require(sample['lineage']['parent']['payload_sha256'] == render_record['source_scene_data_identity'], 'THEMATIC_SOURCE_BINDING')
    root = ET.fromstring(svg)
    groups = [e for e in root if e.tag == SVG+'g']
    require(len(groups)==1 and root.attrib.get('viewBox')=='0 0 500 500' and
            groups[0].attrib.get('transform')=='translate(0 500) scale(1 -1)', 'THEMATIC_FRAME')
    shapes = list(groups[0])
    e = sample['entities']
    ids = e['local_entity_id'].tolist()
    types = e['entity_type'].tolist()
    require(ids==sorted(set(ids)) and len(ids)==len(shapes)==len(types), 'THEMATIC_ENTITY_ORDER')
    for shape,typ in zip(shapes,types,strict=True):
        require(typ in LAYER_COLORS, 'THEMATIC_ENTITY_TYPE')
        # Nonempty entity subtrees retain the renderer's B/R/P colour identity.
        leaves = [n for n in shape.iter() if n.tag in {SVG+'path',SVG+'polyline',SVG+'circle'}]
        require(all(n.attrib.get('stroke' if typ==1 else 'fill')==LAYER_COLORS[typ] for n in leaves), 'THEMATIC_SVG_TYPE')
    maps = {}
    for title,(prefix,column,attr,typ) in ATTRIBUTES.items():
        indices = e[prefix+'_row_index'].tolist()
        values = e[prefix+'_category'][:,column].tolist()
        require(indices==[i for i,t in enumerate(types) if t==typ] and len(indices)==len(values), 'THEMATIC_ROW_BINDING')
        require(all(0<=v<len(names[attr]) for v in values), 'THEMATIC_CATEGORY_INDEX')
        counts = Counter(values)
        maps[title] = {
            'layer': {0:'B',1:'R',2:'P'}[typ],
            'entities':[{'svg_index':i,'entity_id':ids[i],'category_index':v,
                         'label':names[attr][v],'color':color(v,len(names[attr]))} for i,v in zip(indices,values,strict=True)],
            'legend':[{'category_index':v,'label':names[attr][v],'count':n,
                       'color':color(v,len(names[attr]))} for v,n in sorted(counts.items(),key=lambda kv:(-kv[1],kv[0]))],
        }
    return {'maps':maps,'road_lane':{'available':False,'reason':LANE_UNAVAILABLE,
                                   'stored_field':'entities.road_numerical[:,0] is standardized; raw LANES not present'},
            'binding':{'scene_id':sample['scene_id'],'p3_payload_sha256':render_record['source_scene_data_identity'],
                       'original_input_sha256':original_sha,'entity_ids_sha256':digest(ids),
                       'geometry':'unaltered accepted SVG child at stored entity row index',
                       'entity_count':len(ids),'frame_m':500,'north_up':True}}


def bind_lanes(sample, source):
    """Colour raw stored lanes only after exact parent and ordered-ID verification."""
    import math
    require(source['parent']==sample['lineage']['parent'], 'LANE_PARENT_BINDING')
    e=sample['entities'];indices=e['road_row_index'].tolist()
    ids=e['local_entity_id'][indices].tolist()
    rows=source['rows']
    require([r['local_entity_id'] for r in rows]==ids and len(set(ids))==len(ids), 'LANE_ENTITY_BINDING')
    require(all(r['scene_id']==sample['scene_id'] for r in rows), 'LANE_SCENE_BINDING')
    values=[]
    for row in rows:
        value=row['LANES']
        require(value is None or isinstance(value,(float,int)), 'LANE_VALUE_TYPE')
        values.append(None if value is None or not math.isfinite(value) else value)
    unique=sorted({v for v in values if v is not None})+([None] if None in values else [])
    category={v:i for i,v in enumerate(unique)}
    def label(v):
        return 'Unknown / unavailable' if v is None else f'{v:g} lane'+('' if v==1 else 's')
    def paint(v):
        if v is None:return '#999999'
        if v<=1:return '#9ecae1'
        if v<=2:return '#4292c6'
        if v<=3:return '#2171b5'
        return '#084594'
    counts=Counter(values)
    return {'layer':'R','entities':[{'svg_index':i,'entity_id':ids[j],
            'category_index':category[v],'raw_value':v,'label':label(v),'color':paint(v)} for j,(i,v) in enumerate(zip(indices,values,strict=True))],
            'legend':[{'category_index':category[v],'raw_value':v,'label':label(v),'count':counts[v],'color':paint(v)} for v in unique],
            'source_field':'accepted P3 vector/road_observed.parquet:LANES',
            'payload_sha256':source['parent']['payload_sha256']}
