"""Experimental accepted-CON lift. Dissertation spatial relations / Appendix B.

User-approved exception: accepted outside-node connectivity is logical inheritance,
not physical incidence. No canonical relation or augmentation implementation changes.
"""
from collections import defaultdict
import hashlib
import json
import numpy as np
import shapely
from shapely.geometry import LineString, Point
from shapely.ops import substring
from b6_postbank_adapter import parts, digest, child_rng_identity

POLICY = 'accepted_parent_con_nearest_chain_child_v1'
TOL = 1e-7
POLICY_TEXT = '''Preserve each accepted unordered receiver-pair/shared-original-node/source-parent-pair cause by one child pair. Restrict candidates to exact original source-parent lineage. On materialized support select the containing child; boundary ties prefer the child terminating there in F-to-T source direction, then lower source chainage, component/visible run, ordinal, stable ID. Off support minimize distance from original node chainage to child original-source interval, then component/visible-run order, lower child source chainage, ordinal and stable ID. Source-run and augmented-vertex correspondence must be uniquely certified. No Euclidean substitute, no synthetic node, no incidence broadcast. Emit both directions and collapse masks. Original is unchanged.'''
POLICY_HASH = hashlib.sha256(POLICY_TEXT.encode()).hexdigest()

class ChainMappingError(ValueError):
    pass

def cumulative(coords):
    a=np.asarray(coords,dtype=float)
    return np.r_[0., np.cumsum(np.linalg.norm(np.diff(a,axis=0),axis=1))]

def point_chainages(line, point):
    """All exact-support occurrences, never nearest-point guessing on loops."""
    a=np.asarray(line.coords); v=np.diff(a,axis=0); den=np.sum(v*v,axis=1)
    t=np.divide(np.sum((np.asarray(point)-a[:-1])*v,axis=1),den,out=np.zeros(len(v)),where=den>0)
    t=np.clip(t,0,1); distance=np.linalg.norm(a[:-1]+t[:,None]*v-np.asarray(point),axis=1)
    c=cumulative(a); out=[]
    for x in c[:-1][distance<=TOL]+t[distance<=TOL]*np.sqrt(den[distance<=TOL]):
        if not any(abs(x-y)<=TOL for y in out):out.append(float(x))
    return sorted(out)

def source_run(source, observed):
    if source.geom_type!='LineString' or source.length<=0:
        raise ChainMappingError('missing unique ordered source LineString')
    options=[]
    for a in point_chainages(source,observed.coords[0]):
        for b in point_chainages(source,observed.coords[-1]):
            if abs(abs(b-a)-observed.length)>TOL+1e-10*source.length:continue
            run=substring(source,a,b)
            if run.geom_type=='LineString' and shapely.hausdorff_distance(run,observed)<=TOL and shapely.frechet_distance(run,observed)<=TOL:
                options.append((a,b))
    if len(options)!=1:raise ChainMappingError(f'ambiguous source visible run: {len(options)} matches')
    a,b=options[0]
    return a+np.sign(b-a)*cumulative(observed.coords)

def materialized_chainages(original, materialized, source_positions, operation):
    old=np.asarray(original.coords); new=np.asarray(materialized.coords)
    if operation in ('JITTER','FALLBACK'):
        if len(old)!=len(new):raise ChainMappingError('vertex correspondence changed')
        return source_positions
    if operation!='SIMPLIFY':raise ChainMappingError('unknown geometry operation')
    # Simplification only removes vertices. Require unique monotone subsequence.
    choices=[np.flatnonzero(np.linalg.norm(old-p,axis=1)<=TOL).tolist() for p in new]
    paths=[[]]
    for options in choices:
        paths=[p+[i] for p in paths for i in options if not p or i>p[-1]]
        if len(paths)>1000:raise ChainMappingError('ambiguous simplification correspondence')
    paths=[p for p in paths if p[0]==0 and p[-1]==len(old)-1]
    if len(paths)!=1:raise ChainMappingError('ambiguous simplification source positions')
    return source_positions[paths[0]]

def subdivide_receiver(scene, view, mapped, original_roads, geometry_row, topology, length=50.):
    children=[]
    for part in mapped:
        parent=original_roads[part['source_local_id']]
        source=shapely.from_wkb(bytes(parent['source_geometry_wkb']))
        original=parts(shapely.from_wkb(bytes(parent['observed_geometry'])))[part['source_part_index']]
        g=part['geometry']; node_rows=[x for x in topology if int(x['road_local_entity_id'])==part['source_local_id']]
        if len(node_rows)!=2:raise ChainMappingError('missing F/T source chain')
        node_rows=sorted(node_rows,key=lambda x:int(x['source_node_position']))
        for index,row in enumerate(node_rows):
            xy=(row['source_node_x_5186'],row['source_node_y_5186'])
            if Point(source.coords[0 if index==0 else -1]).distance(Point(xy))>TOL:
                raise ChainMappingError('source direction/node endpoint mismatch')
        positions=source_run(source,original)
        positions=materialized_chainages(original,g,positions,'FALLBACK' if geometry_row['fallback'] else geometry_row['geometry_operation'])
        mc=cumulative(g.coords)
        if g.length<=0:raise ChainMappingError('zero length materialized part')
        true_cuts=[]
        for row in node_rows:
            true_cuts.extend(point_chainages(g,(row['source_node_x_5186'],row['source_node_y_5186'])))
        anchors=sorted(set([0.,g.length]+[x for x in true_cuts if TOL<x<g.length-TOL]))
        cuts=[0.]
        for a,b in zip(anchors[:-1],anchors[1:]):
            cuts.extend(np.arange(a+length,b-TOL,length).tolist());cuts.append(b)
        for ordinal,(a,b) in enumerate(zip(cuts[:-1],cuts[1:])):
            child=substring(g,a,b)
            if child.geom_type!='LineString' or child.length<=0:raise ChainMappingError('nonpositive child')
            ca,cb=np.interp([a,b],mc,positions)
            identity={'policy':POLICY,'L':length,'scene':scene,'view':view,'parent':part['source_road_id'],
                      'component':part['source_part_index'],'ordinal':ordinal,'start':float(a).hex(),'end':float(b).hex()}
            children.append({'child_id':'b6ch_'+digest(identity)[:32], 'rng_id':child_rng_identity(scene,view,part['source_road_id'],part['source_part_index'],a,b),
              'receiver':part['receiver_local_id'],'source_parent':part['source_road_id'],'source_local':part['source_local_id'],
              'component':part['source_part_index'],'ordinal':ordinal,'start':a,'end':b,
              'chain_start':float(ca),'chain_end':float(cb),'geometry':child,'nodes':node_rows,
              'source_length':source.length,'semantic_owner':part['receiver_local_id']})
        out=[x for x in children if x['source_local']==part['source_local_id'] and x['component']==part['source_part_index']]
        if abs(sum(x['geometry'].length for x in out)-g.length)>TOL+1e-10*g.length:raise ChainMappingError('length preservation')
        if shapely.hausdorff_distance(shapely.union_all([x['geometry'] for x in out]),g)>TOL:raise ChainMappingError('support preservation')
    return children

def select_child(children, parent, node_id):
    candidates=[x for x in children if x['source_parent']==parent]
    if not candidates:raise ChainMappingError('missing exact source-parent children')
    node_rows=[r for r in candidates[0]['nodes'] if str(r['source_node_id'])==str(node_id)]
    if not node_rows:raise ChainMappingError('missing source-node lineage')
    positions=[0. if int(r['source_node_position'])==0 else candidates[0]['source_length'] for r in node_rows]
    point=Point(node_rows[0]['source_node_x_5186'],node_rows[0]['source_node_y_5186'])
    physical=[x for x in candidates if x['geometry'].distance(point)<=TOL]
    mode='physical_on_support' if physical else 'logical_off_support'
    eligible=physical or candidates
    def distance(x):
        lo,hi=sorted([x['chain_start'],x['chain_end']])
        return min(max(lo-p,0.,p-hi) for p in positions)
    minimum=min(distance(x) for x in eligible)
    tied=[x for x in eligible if abs(distance(x)-minimum)<=TOL]
    def terminal(x):
        # Terminal in original F-to-T direction, even if observed part is reversed.
        terminal_xy=x['geometry'].coords[-1 if x['chain_end']>=x['chain_start'] else 0]
        return Point(terminal_xy).distance(point)<=TOL
    if physical:
        key=lambda x:(not terminal(x), min(x['chain_start'],x['chain_end']), x['component'],x['ordinal'],x['child_id'])
    else:
        key=lambda x:(x['component'],min(x['chain_start'],x['chain_end']),x['ordinal'],x['child_id'])
    chosen=min(tied,key=key)
    if len({x['child_id'] for x in eligible})!=len(eligible):raise ChainMappingError('duplicate child identity')
    return chosen,{'mode':mode,'chain_distance_m':distance(chosen),'ties_before':len(tied),'ties_after':1,
                   'physical_terminal_preference':bool(physical and terminal(chosen))}

def lift_accepted_parent_con_to_children(parent_pairs, children):
    by_receiver=defaultdict(list)
    for x in children:by_receiver[x['receiver']].append(x)
    records=[];pairs=set()
    for a,b in sorted({tuple(sorted(p)) for p in parent_pairs if p[0]!=p[1]}):
        owners=[]
        for receiver in (a,b):
            nodes=defaultdict(set)
            for x in by_receiver[receiver]:
                for n in x['nodes']:nodes[str(n['source_node_id'])].add(x['source_parent'])
            owners.append(nodes)
        shared=set(owners[0])&set(owners[1])
        if not shared:raise ChainMappingError('accepted CON lacks shared original-node cause')
        for node in sorted(shared):
            for pa in sorted(owners[0][node]):
                for pb in sorted(owners[1][node]):
                    x,dx=select_child(by_receiver[a],pa,node);y,dy=select_child(by_receiver[b],pb,node)
                    if x['child_id']==y['child_id']:raise ChainMappingError('self CON')
                    pair=tuple(sorted([x['child_id'],y['child_id']]))
                    records.append({'receiver_a':a,'receiver_b':b,'parent_a':pa,'parent_b':pb,'node_id':node,
                        'child_a':x['child_id'],'child_b':y['child_id'],'a':dx,'b':dy,'collapsed_existing_pair':pair in pairs})
                    pairs.add(pair)
    return pairs,records
