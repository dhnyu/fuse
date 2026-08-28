#!/usr/bin/env python3
"""Independent structural and scientific validator for a P4 delta branch."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import tarfile
import unicodedata
from pathlib import Path

import pyarrow.parquet as pq
import shapely


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument("--manifest",required=True); parser.add_argument("--output",required=True)
    args=parser.parse_args(); manifest_path=Path(args.manifest); manifest=json.loads(manifest_path.read_text()); payload=manifest_path.parent/manifest["payload"]["filename"]
    failures=[]
    if sha256_file(payload)!=manifest["payload"]["sha256"] or payload.stat().st_size!=manifest["payload"]["size_bytes"]: failures.append("payload_checksum")
    tables={}
    with tarfile.open(payload) as archive:
        names=archive.getnames()
        if len(names)!=len(set(names)): failures.append("duplicate_tar_member")
        for member in manifest["members"]:
            raw=archive.extractfile(member["path"]).read()
            if hashlib.sha256(raw).hexdigest()!=member["sha256"] or len(raw)!=member["size_bytes"]: failures.append("member_checksum")
            if member["path"].endswith(".parquet"): tables[Path(member["path"]).stem]=pq.read_table(io.BytesIO(raw)).to_pandas()
    candidates=tables.get("candidates")
    if candidates is None or len(candidates)!=manifest["candidate_count"] or candidates.candidate_id.duplicated().any(): failures.append("candidate_identity")
    if candidates is not None:
        if set(candidates.master_view_id.unique())-set(range(16)): failures.append("view_range")
        if (candidates.status!="PASS").any(): failures.append("candidate_status")
        if candidates.duplicated(["scene_id","profile_id","master_view_id"]).any(): failures.append("view_identity")
        expected_order=["entity_removal_and_road_link_absorption","geometry_perturbation","attribute_perturbation_and_geometry_dependent_updates","raster_perturbation","reconstruct_all_derived_observations"]
        for row in candidates.itertuples():
            if json.loads(row.operation_order_json)!=expected_order: failures.append("operation_order"); break
            seeds=json.loads(row.operation_seeds_json)
            expected={operation:hashlib.sha256("|".join(("p4-augmentation-v2","training-bank",unicodedata.normalize("NFC",row.profile_id),
                     unicodedata.normalize("NFC",row.scene_id),str(int(row.master_view_id)),operation,"NONE","NONE")).encode()).hexdigest()
                     for operation in ("entity_removal","landcover","dem")}
            if seeds!=expected: failures.append("seed_replay"); break
            if int(row.landcover_maximum_active_fronts) > 4: failures.append("landcover_active_fronts"); break
            if int(row.landcover_mask_count) < 0 or not row.landcover_mask_digest: failures.append("landcover_candidate_summary"); break
    mask_provenance=tables.get("landcover_mask_provenance")
    if mask_provenance is None or candidates is None or len(mask_provenance)!=len(candidates):
        failures.append("landcover_provenance_coverage")
    elif len(mask_provenance):
        if mask_provenance.duplicated(["candidate_id"]).any(): failures.append("landcover_provenance_duplicate")
        for row in mask_provenance.itertuples():
            seeds=json.loads(row.initial_seeds_json); reseeds=json.loads(row.reseeds_json)
            if row.algorithm!="eight_neighbor_round_robin_block_growth_v1": failures.append("landcover_algorithm"); break
            if int(row.maximum_concurrent_fronts)>4 or int(row.maximum_concurrent_fronts)<0: failures.append("landcover_active_fronts"); break
            if len(seeds)>4 or len(set(seeds))!=len(seeds): failures.append("landcover_initial_seeds"); break
            if int(row.target_mask_count)!=int(candidates.loc[candidates.candidate_id==row.candidate_id,"landcover_mask_count"].iloc[0]): failures.append("landcover_target_count"); break
            if int(row.target_mask_count)>int(row.valid_cell_count): failures.append("landcover_valid_support"); break
            if any(int(item["cell"]) in seeds for item in reseeds): failures.append("landcover_reseed_overlap"); break
            if not all(len(value)==64 for value in (row.selected_order_sha256,row.frontier_order_sha256)): failures.append("landcover_digest"); break
    geometry=tables.get("geometry")
    maximum_error=0.0
    if geometry is not None and len(geometry):
        if geometry.duplicated(["candidate_id","local_entity_id"]).any(): failures.append("duplicate_geometry")
        for row in geometry.itertuples():
            value=shapely.from_wkb(bytes(row.geometry_wkb)); center=((value.bounds[0]+value.bounds[2])/2,(value.bounds[1]+value.bounds[3])/2)
            error=max(abs(center[0]-row.center_x),abs(center[1]-row.center_y),abs(float(value.area)-row.area_m2),abs(float(value.length)-row.length_m))
            maximum_error=max(maximum_error,error)
            if value.is_empty or not value.is_valid or error>1e-9 or row.geometry_dtype!="float64_wkb": failures.append("geometry_consistency"); break
            attempts=json.loads(row.attempts_json)
            if not 1 <= len(attempts) <= 10 or [x["attempt"] for x in attempts] != list(range(1,len(attempts)+1)): failures.append("geometry_attempt_sequence"); break
    fallbacks=tables.get("fallbacks")
    if fallbacks is not None and len(fallbacks):
        if (fallbacks.attempt_count!=10).any() or (~fallbacks.fallback).any(): failures.append("fallback_contract")
        for value in fallbacks.attempts_json:
            attempts=json.loads(value)
            if len(attempts)!=10 or [x["attempt"] for x in attempts]!=list(range(1,11)): failures.append("fallback_provenance"); break
    removals=tables.get("removals")
    if removals is not None and len(removals) and removals.duplicated(["candidate_id","local_entity_id"]).any(): failures.append("duplicate_removal")
    absorption=tables.get("absorption")
    if absorption is not None and len(absorption):
        accepted=absorption[absorption.status=="ABSORBED"]
        if len(accepted) and (accepted.donor==accepted.receiver).any(): failures.append("self_absorption")
        if accepted.duplicated(["candidate_id","donor"]).any(): failures.append("duplicate_donor")
        for candidate, group in accepted.groupby("candidate_id"):
            donors=set(group.donor.astype(int)); receivers=set(group.receiver.astype(int))
            if donors & receivers: failures.append("donor_receiver_chain"); break
    relation=tables.get("relation_delta")
    if relation is None or set(relation.columns)!={"candidate_id","scene_id","profile_id","master_view_id","relation_type","source","destination","action"}:
        failures.append("relation_schema")
    elif len(relation):
        if not set(relation.relation_type).issubset({"SN","CNT","WIT","INT","CON"}): failures.append("relation_type")
        if not set(relation.action).issubset({"ADD","REMOVE"}): failures.append("relation_action")
        if (relation.source==relation.destination).any(): failures.append("relation_self_edge")
        if relation.duplicated(["candidate_id","relation_type","source","destination","action"]).any(): failures.append("relation_duplicate")
    topology=tables.get("topology")
    if topology is not None and len(topology):
        if topology.duplicated(["candidate_id","receiver_local_entity_id","source_node_offset"]).any(): failures.append("topology_offset_duplicate")
        for _, group in topology.groupby(["candidate_id","receiver_local_entity_id"],sort=False):
            offsets=sorted(group.source_node_offset.astype(int).tolist())
            if offsets!=list(range(len(offsets))): failures.append("topology_offset_gap"); break
            for _, chain in group.groupby("component_index",sort=False):
                positions=chain.sort_values("chain_position")
                if positions.chain_position.astype(int).tolist()!=list(range(len(positions))): failures.append("chain_position"); break
                if (positions.chain_offset_start.astype(int)!=int(positions.source_node_offset.min())).any() or (positions.chain_offset_end.astype(int)!=int(positions.source_node_offset.max())+1).any(): failures.append("chain_offsets"); break
    context=tables.get("context")
    if context is not None and len(context) and context.duplicated(["candidate_id","local_entity_id"]).any(): failures.append("duplicate_context")
    result={"schema_version":"1.0.0","status":"PASS" if not failures else "FAIL","branch_id":manifest["branch_id"],"candidate_count":manifest["candidate_count"],
            "maximum_geometry_derived_error":maximum_error,"failures":sorted(set(failures)),"independent_reader":True}
    Path(args.output).write_text(json.dumps(result,sort_keys=True,separators=(",", ":"))+"\n")
    if failures: raise SystemExit(";".join(sorted(set(failures))))


if __name__=="__main__": main()
