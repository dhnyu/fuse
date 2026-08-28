#!/usr/bin/env python3
"""Synthetic P4 receiver and entity-fallback gates."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from shapely.geometry import LineString, Polygon

ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"python"))
import p4_fixed_augmentation as p4


def road_smoke():
    entities={0:{"entity_type":"R","source_entity_id":"receiver","ROAD_TYPE":"A","ROAD_RANK":"1"},
              1:{"entity_type":"R","source_entity_id":"donor-a","ROAD_TYPE":"A","ROAD_RANK":"1"},
              2:{"entity_type":"R","source_entity_id":"donor-b","ROAD_TYPE":"A","ROAD_RANK":"1"},
              3:{"entity_type":"R","source_entity_id":"bad","ROAD_TYPE":"B","ROAD_RANK":"1"}}
    scene={"scene_id":"fixture-road","entities":entities,
           "geometries":{0:LineString([(0,0),(1,0)]),1:LineString([(1,0),(2,0)]),2:LineString([(1,0),(1,1)]),3:LineString([(1,0),(0,1)])},
           "road_nodes":{0:[[('n0',0,0),('n1',1,0)]],1:[[('n1',1,0),('n2',2,0)]],2:[[('n1',1,0),('n3',1,1)]],3:[[('n1',1,0),('n4',0,1)]]}}
    absorbed,mapping,provenance,geometry,nodes=p4.compose_absorption(scene,{1,2},"main_1.0x",0)
    assert absorbed=={1,2} and mapping=={1:0,2:0}
    assert geometry[0].geom_type=="MultiLineString" and len(geometry[0].geoms)==3
    assert [chain[0][0] for chain in nodes[0]]==["n0","n1","n1"]
    assert all(row["status"]=="ABSORBED" for row in provenance)
    return {"status":"PASS","absorbed_donors":2,"receiver_groups":1,"component_count":3,"cycle_count":0}


def fallback_smoke():
    polygon=Polygon([(1,1),(9,1),(9,9),(1,9),(1,1)])
    entity={"entity_type":"B","source_entity_id":"building","local_entity_id":0,"observed_geometry":polygon.wkb,
            "observed_area_m2":64.0,"observed_gross_floor_area_m2":128.0,"A9":"a","A11":"b"}
    scene={"scene_id":"fixture-fallback","entities":{0:entity},"geometries":{0:polygon},"road_nodes":{},
           "edges":pd.DataFrame(columns=["source_local_entity_id","destination_local_entity_id","has_sn","has_cnt","has_wit","has_int","has_con"]),
           "bounds":(0.,0.,10.,10.),"center":(5.,5.),"lc":np.ones((22,100,100),dtype=np.float32)/22,
           "lc_valid":np.ones((100,100),dtype=np.float32),"lc_mask":np.ones((100,100),dtype=np.uint8),
           "dem":np.ones((17,17),dtype=np.float32),"dem_valid":np.ones((17,17),dtype=np.float32),"dem_mask":np.ones((17,17),dtype=np.uint8)}
    profile={"profile_id":"main_1.0x","removal_fraction":0.0,"jitter_probability":1.0,"jitter_displacement_m":2.0,
             "simplification_tolerance_m":2.0,"categorical_mask_probability":0.0,"categorical_replacement_probability":0.0,
             "lane_probability":0.0,"landcover_mask_fraction":0.0,"dem_noise_sd_m":0.0}
    resources={"complexity_thresholds":{"B":999.,"R":999.},"poi_hierarchy_branches":{},"cache_id":"fixture","implementation_hash":"fixture"}
    original=p4.jitter_geometry
    p4.jitter_geometry=lambda *args,**kwargs: Polygon([(0,0),(1,1),(1,0),(0,1),(0,0)])
    try: result=p4.augment_scene(scene,profile,resources,0)
    finally: p4.jitter_geometry=original
    assert len(result["fallbacks"])==1 and result["fallbacks"][0]["attempt_count"]==10
    assert result["candidates"][0]["status"]=="PASS" and result["candidates"][0]["retained_entity_count"]==1
    assert len(json.loads(result["fallbacks"][0]["attempts_json"]))==10
    return {"status":"PASS","entity_fallbacks":1,"attempts":10,"candidate_retained":True}


def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--mode",choices=["road","geometry"],required=True); parser.add_argument("--output",required=True); args=parser.parse_args()
    value=road_smoke() if args.mode=="road" else fallback_smoke(); Path(args.output).write_text(json.dumps(value,sort_keys=True,separators=(",",":"))+"\n")


if __name__=="__main__": main()
