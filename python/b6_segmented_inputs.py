"""Post-bank S50 tensor adapter and full-source G/Ppre graphs (experimental only).

Dissertation: bbox-center positions, geometry Fourier rows, receiver semantics,
relation masks and induced B6 family projection. No new encoder or augmentation.
"""
from collections import defaultdict
import copy
import numpy as np
import shapely
from shapely.strtree import STRtree
import torch
from augmentation_bank import selected_hosts
from b6_con_lift import select_child,POLICY,POLICY_HASH
from b6_postbank_adapter import digest
from training_family_inputs import project,check_sample
from model_data import validate_geometry_layout


def full_source_graphs(original_entities, delta, children, con_pairs):
    removed={int(r['local_entity_id']) for r in delta['removals']}
    entities={int(r['local_entity_id']):r for r in original_entities if r['entity_type']!='R' and int(r['local_entity_id']) not in removed}
    geometry={i:shapely.from_wkb(bytes(r['observed_geometry'])) for i,r in entities.items()}
    for r in delta['geometry']:
        i=int(r['local_entity_id'])
        if i in geometry:geometry[i]=shapely.from_wkb(bytes(r['geometry_wkb']))
    start=1+max([int(r['local_entity_id']) for r in original_entities]+[-1])
    children=sorted(children,key=lambda x:(x['receiver'],x['source_parent'],x['component'],x['ordinal'],x['child_id']))
    for offset,c in enumerate(children):
        c['local_id']=start+offset;entities[start+offset]={'entity_type':'R','source_entity_id':c['child_id']};geometry[start+offset]=c['geometry']
    ids=sorted(entities);cnt,wit=selected_hosts(entities,geometry,set(ids));contained={p for _,p in cnt}
    eligible=[i for i in ids if i not in contained]
    geoms=np.asarray([geometry[i] for i in eligible],dtype=object);tree=STRtree(geoms)
    owner={c['local_id']:c['source_parent'] for c in children}
    sn={'G':set(),'Ppre':set()}
    for begin in range(0,len(eligible),128):
        block=geoms[begin:begin+128];ix=tree.query(block,predicate='dwithin',distance=100.)
        src,dst=ix;distance=shapely.distance(block[src],geoms[dst]);keys=np.rint(distance/1e-9)
        order=np.lexsort((np.asarray(eligible,dtype=np.int64)[dst],keys,src));src,dst=src[order],dst[order]
        offsets=np.searchsorted(src,np.arange(len(block)+1))
        for k in range(len(block)):
            a=eligible[begin+k];neighbors=[eligible[int(j)] for j in dst[offsets[k]:offsets[k+1]] if eligible[int(j)]!=a]
            for b in neighbors[:16]:sn['G'].add((a,b));sn['G'].add((b,a))
            if a in owner:neighbors=[b for b in neighbors if b not in owner or owner[a]!=owner[b]]
            for b in neighbors[:16]:sn['Ppre'].add((a,b));sn['Ppre'].add((b,a))
    physical=[i for i in ids if entities[i]['entity_type'] in ('B','R')]
    pg=np.asarray([geometry[i] for i in physical],dtype=object);inter=STRtree(pg).query(pg,predicate='intersects')
    intr={(physical[int(a)],physical[int(b)]) for a,b in inter.T if a!=b}
    childid={c['child_id']:c['local_id'] for c in children};con=set()
    for a,b in con_pairs:con.add((childid[a],childid[b]));con.add((childid[b],childid[a]))
    common=defaultdict(int)
    for bit,pairs in [(2,cnt),(4,wit),(8,intr),(16,con)]:
        for p in pairs:common[p]|=bit
    graphs={};summaries={}
    road_rows={c['local_id']:i for i,c in enumerate(children)}
    for policy in sn:
        masks=common.copy()
        for p in sn[policy]:masks[p]|=1
        rr=sorted((road_rows[a],road_rows[b],m) for (a,b),m in masks.items() if a in road_rows and b in road_rows)
        graphs[policy]={'edge_index':torch.tensor([(a,b) for a,b,m in rr],dtype=torch.int64).T.contiguous() if rr else torch.empty((2,0),dtype=torch.int64),
                        'relation_mask':torch.tensor([m for a,b,m in rr],dtype=torch.uint8)}
        summaries[policy]={'full_pairs':len(masks),'road_pairs':len(rr),'full_sn':len(sn[policy]),'full_int':len(intr),'con':len(con),
            'road_sn':sum(bool(m&1) for a,b,m in rr),'road_int':sum(bool(m&8) for a,b,m in rr),'road_con':sum(bool(m&16) for a,b,m in rr)}
    for bit in [8,16]:
        sets=[]
        for g in graphs.values():sets.append({tuple(p) for p,m in zip(g['edge_index'].T.tolist(),g['relation_mask'].tolist()) if m&bit})
        assert sets[0]==sets[1]
    for g in graphs.values():
        pairs=set(map(tuple,g['edge_index'].T.tolist()));assert all(a!=b for a,b in pairs);assert pairs=={(b,a) for a,b in pairs}
    return children,graphs,summaries


def tensorize_children(accepted,children,graphs,scene_center,method_id):
    out,_=project(accepted,'B6');e=out['entities'];n=len(children)
    parent_index={int(x):i for i,x in enumerate(e['local_entity_id'])}
    ix=torch.tensor([parent_index[c['receiver']] for c in children],dtype=torch.int64)
    for key in ('entity_type','relative_position_m','object_raster','modality_available'):
        e[key]=e[key][ix].clone()
    for suffix in ('category','numerical','missing'):e['road_'+suffix]=e['road_'+suffix][ix].clone()
    e['local_entity_id']=torch.tensor([c['local_id'] for c in children],dtype=torch.int64);e['road_row_index']=torch.arange(n)
    centers=np.asarray([[(c['geometry'].bounds[0]+c['geometry'].bounds[2])/2,(c['geometry'].bounds[1]+c['geometry'].bounds[3])/2] for c in children]).reshape(-1,2)
    e['relative_position_m']=torch.tensor(centers-np.asarray(scene_center),dtype=torch.float32)
    coords=[];offset=[0]
    for c,center in zip(children,centers):coords.extend((np.asarray(c['geometry'].coords)-center).tolist());offset.append(len(coords))
    g=out['geometry'];xy=torch.tensor(coords,dtype=torch.float64).reshape(-1,2);off=torch.tensor(offset,dtype=torch.int64);ep=torch.arange(n+1)
    g.update(part_coordinates_xy_m=xy.float(),part_coordinates_xy_m_scientific=xy,
        geometry_type=torch.full((n,),2,dtype=torch.int64),geometry_available=torch.ones(n,dtype=torch.uint8),
        entity_coordinate_offsets=off,entity_part_offsets=ep,part_coordinate_offsets=off,
        entity_component_offsets=ep.clone(),component_coordinate_offsets=off.clone(),entity_ring_offsets=torch.zeros(n+1,dtype=torch.int64))
    # Empty ring tensors already belong to the canonical road-only projection.
    nodes=defaultdict(list);by_parent=defaultdict(list)
    for i,c in enumerate(children):by_parent[c['source_parent']].append(c)
    lookup={c['child_id']:i for i,c in enumerate(children)};logical=[]
    for parent,group in by_parent.items():
        for node in sorted({str(x['source_node_id']) for x in group[0]['nodes']}):
            child,diagnostic=select_child(group,parent,node)
            row=next(x for x in child['nodes'] if str(x['source_node_id'])==node)
            nodes[lookup[child['child_id']]].append((node,row['source_node_x_5186'],row['source_node_y_5186']))
            logical.append({'node_id':node,'child_id':child['child_id'],'source_parent':parent,**diagnostic})
    indices=[];node_ids=[];positions=[];node_offsets=[0]
    for i in sorted(nodes):
        indices.append(i)
        for node,x,y in nodes[i]:node_ids.append(node);positions.append([x,y])
        node_offsets.append(len(node_ids))
    out['topology']={'source_chain_offsets':torch.tensor(node_offsets),'source_chain_road_index':torch.tensor(indices,dtype=torch.int64),
                     'source_node_xy_5186':torch.tensor(positions,dtype=torch.float64).reshape(-1,2),'source_node_ids':node_ids}
    out['edges']=graphs['G'];out['resources']={'nodes':n,'ordered_edges':len(graphs['G']['relation_mask']),'coordinates':len(coords),'part_coordinates':len(coords),'ring_coordinates':0,'source_nodes':len(node_ids)}
    out['lineage']={**out['lineage'],'b6_method':method_id,'con_policy':POLICY,'con_policy_hash':POLICY_HASH,'child_ids':[c['child_id'] for c in children]}
    check_sample(out);validate_geometry_layout(out)
    other=copy.deepcopy(out);other['edges']=graphs['Ppre'];other['resources']['ordered_edges']=len(graphs['Ppre']['relation_mask'])
    check_sample(other)
    assert all(int(x)==1 for x in out['entities']['entity_type'])
    # One base payload makes all non-edge scientific tensors identical by construction.
    # Validate both concrete arm samples as well as their non-SN edge sets.
    return out,other,[c['rng_id'] for c in children],logical
