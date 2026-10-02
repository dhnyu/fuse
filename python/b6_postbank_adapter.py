"""Isolated post-bank provenance adapter; never writes accepted P3/P4/P5.

Methods: accepted augmentation operation order and scene-clipped observations.
Replay here verifies the *recorded accepted* geometry result. It does not sample
removals, receiver choices, attempts, queries, or a new augmentation bank.
"""
from __future__ import annotations
import copy
import hashlib
import json
from collections import defaultdict
import shapely
from shapely.geometry import MultiLineString, Point
from augmentation_bank import canonical_road_key, jitter_geometry, simplify_geometry

class AmbiguousLineage(ValueError):
    pass

class OutsideNodeMethodDecision(ValueError):
    pass

def parts(g):
    if g.geom_type == 'LineString': return [g]
    if g.geom_type == 'MultiLineString': return list(g.geoms)
    raise AmbiguousLineage('non-lineal materialized road')

def digest(value):
    return hashlib.sha256((json.dumps(value,sort_keys=True,separators=(',',':'))+'\n').encode()).hexdigest()

def receiver_semantics(parent, attributes):
    result={k:parent.get(k) for k in ('ROAD_RANK','ROAD_TYPE','LANES')}
    masked=[]
    for row in attributes:
        if int(row['local_entity_id'])==int(parent['local_entity_id']) and row['field'] in result:
            result[row['field']]=None if row['augmented']=='MASK' else row['augmented']
            if row['augmented']=='MASK': masked.append(row['field'])
    return result,sorted(masked)

def resolve_receiver(original_roads, topology, absorption, geometry_row, attributes, profile, bounds):
    """Expand P3 parts using the verified absorption recipe, not output ordinals.

    Exact full WKB replay validates correspondence through jitter/simplification.
    Source chain IDs remain distinct from expanded geometric part indices.
    """
    receiver=int(geometry_row['local_entity_id'])
    if receiver not in original_roads: raise AmbiguousLineage('receiver absent from P3')
    donors=[int(r['donor']) for r in absorption if r['status']=='ABSORBED' and int(r['receiver'])==receiver]
    if len(set(donors))!=len(donors) or receiver in donors: raise AmbiguousLineage('duplicate/cyclic donor ownership')
    owners=[receiver]+sorted(donors,key=lambda i:canonical_road_key(original_roads[i]['source_entity_id']))
    source_parts=[];recipe=[];protected=set();chains=defaultdict(list)
    for row in topology:
        if int(row['road_local_entity_id']) in owners:
            chains[int(row['road_local_entity_id'])].append(row)
            protected.add((float(row['source_node_x_5186']),float(row['source_node_y_5186'])))
    for owner in owners:
        for part_index,g in enumerate(parts(shapely.from_wkb(bytes(original_roads[owner]['observed_geometry'])))):
            source_parts.append(g)
            recipe.append({'source_local_id':owner,'source_road_id':str(original_roads[owner]['source_entity_id']),
                           'source_part_index':part_index,'source_part_sha256':hashlib.sha256(g.wkb).hexdigest(),
                           'role':'RECEIVER' if owner==receiver else 'DONOR'})
    if not source_parts: raise AmbiguousLineage('empty recipe')
    composed=MultiLineString(source_parts) if donors or shapely.from_wkb(bytes(original_roads[receiver]['observed_geometry'])).geom_type=='MultiLineString' else source_parts[0]
    if geometry_row['fallback']:
        expected=composed
    elif geometry_row['geometry_operation']=='JITTER':
        seed=geometry_row.get('accepted_attempt_seed')
        if not seed: raise AmbiguousLineage('accepted jitter seed absent')
        expected=jitter_geometry(composed,bytes.fromhex(seed),profile,protected,bounds)
    elif geometry_row['geometry_operation']=='SIMPLIFY':
        tolerance=geometry_row.get('sampled_simplification_tolerance_m')
        if tolerance is None: raise AmbiguousLineage('accepted simplification tolerance absent')
        expected=simplify_geometry(composed,float(tolerance),protected)
    else: raise AmbiguousLineage('unknown accepted geometry operation')
    observed=shapely.from_wkb(bytes(geometry_row['geometry_wkb']))
    if expected.wkb!=observed.wkb: raise AmbiguousLineage('accepted geometry replay mismatch; ownership cannot be certified')
    actual_parts=parts(observed)
    if len(actual_parts)!=len(recipe): raise AmbiguousLineage('part count mismatch')
    semantics,masked=receiver_semantics(original_roads[receiver],attributes)
    out=[]
    for index,(g,provenance) in enumerate(zip(actual_parts,recipe,strict=True)):
        nodes=chains[provenance['source_local_id']]
        on=[];off=[]
        for row in nodes:
            point=Point(float(row['source_node_x_5186']),float(row['source_node_y_5186']))
            record={'node_id':str(row['source_node_id']),'x':point.x,'y':point.y,'distance_m':g.distance(point),
                    'source_node_position':int(row['source_node_position'])}
            (on if record['distance_m']<=1e-7 else off).append(record)
        out.append({**provenance,'receiver_local_id':receiver,'receiver_source_id':str(original_roads[receiver]['source_entity_id']),
                    'materialized_part_index':index,'materialized_geometry_sha256':hashlib.sha256(g.wkb).hexdigest(),
                    'geometry':g,'semantic_owner_local_id':receiver,'semantics':semantics,'masked_fields':masked,
                    'true_nodes_on_support':on,'source_chain_nodes_off_part':off,
                    'recipe_verified':True,'synthetic_part_boundary_is_network_node':False})
    return out

def require_physical_node_lift(lineage, required_node):
    """Fail closed rather than invent a child CON endpoint for an outside node."""
    hits=[r for r in lineage if any(n['node_id']==required_node for n in r['true_nodes_on_support'])]
    if not hits:
        raise OutsideNodeMethodDecision('accepted source node has no materialized support: explicit logical-incidence policy required')
    return hits

def original_adapter(prepared_sample):
    # Accepted payload + canonical family projection is the exact control path.
    from training_family_inputs import project
    return project(copy.deepcopy(prepared_sample),'B6')

def shared_training_config(base, authority):
    result=copy.deepcopy(base)
    result['training']['root_seed']=int(authority['content']['scientific']['root_seed'])
    result['training']['logical_k']=8
    return result

def child_rng_identity(scene,view,parent,part,start,end):
    # Policy/configuration labels are deliberately absent, pairing G with P-pre.
    key={'version':'b6-postbank-child-v1','scene':scene,'view':view,'parent':str(parent),
         'part':int(part),'start':float(start).hex(),'end':float(end).hex()}
    return int(digest(key)[:16],16)&((1<<63)-1)

def paired_modality_assignments(batch,config,epoch,view_role,global_rank=0,child_rng_ids=None):
    """Experimental RNG adapter; never change canonical batch or graph local IDs."""
    from training_family_inputs import family_modality_assignments
    import torch
    if child_rng_ids is None:
        return family_modality_assignments(batch,config,epoch,view_role,global_rank)
    if len(child_rng_ids)!=len(batch['entities']['local_entity_id']):
        raise ValueError('child RNG identity count mismatch')
    shadow={**batch,'entities':{**batch['entities'],'local_entity_id':torch.tensor(child_rng_ids,dtype=torch.int64)}}
    return family_modality_assignments(shadow,config,epoch,view_role,global_rank)
