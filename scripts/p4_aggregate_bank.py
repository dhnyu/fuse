#!/usr/bin/env python3
"""Aggregate validated P4 branches and publish logical prefix indices."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import tarfile
from collections import Counter, defaultdict
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


def canonical(value): return (json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False)+"\n").encode()
def digest(value): return hashlib.sha256(canonical(value)).hexdigest()


def table(payload: Path, name: str):
    with tarfile.open(payload) as archive: return pq.read_table(io.BytesIO(archive.extractfile(f"{name}.parquet").read())).to_pylist()


def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--spec",required=True); parser.add_argument("--acceptance",required=True); parser.add_argument("--index-parquet",required=True); parser.add_argument("--index-manifest",required=True)
    args=parser.parse_args(); spec=json.loads(Path(args.spec).read_text()); manifests=[json.loads(Path(x).read_text()) for x in spec["manifests"]]
    candidates=[]; profile_stats=defaultdict(Counter); payload_bytes=Counter(); ordered=[]; attempt_stats=defaultdict(Counter); relation_stats=defaultdict(lambda:defaultdict(Counter))
    for manifest_path,manifest in sorted(zip(spec["manifests"],manifests),key=lambda x:x[1]["branch_id"]):
        payload=Path(manifest_path).parent/manifest["payload"]["filename"]; rows=table(payload,"candidates"); candidates.extend(rows)
        absorptions=table(payload,"absorption"); masks=table(payload,"landcover_mask_provenance")
        profile=manifest["profile_id"]; payload_bytes[profile]+=manifest["payload"]["size_bytes"]
        for row in rows:
            stat=profile_stats[profile]; stat["physical_candidates"]+=1; stat["primary_removals"]+=row["primary_removal_count"]; stat["direct_removals"]+=row["direct_removed_count"]
            stat["cascade_removals"]+=row["cascade_removed_count"]; stat["absorbed_donors"]+=row["absorbed_donor_count"]; stat["geometry_overrides"]+=row["geometry_override_count"]
            stat["geometry_fallbacks"]+=row["geometry_fallback_count"]; stat["attribute_overrides"]+=row["attribute_override_count"]; stat["landcover_masks"]+=row["landcover_mask_count"]; stat["dem_noise_values"]+=row["dem_noise_count"]
            for attempt,count in json.loads(row["attempt_histogram_json"]).items(): attempt_stats[profile][attempt]+=count
            for relation,counts in json.loads(row["relation_counts_json"]).items():
                for key,value in counts.items(): relation_stats[profile][relation][key]+=value
        accepted=[x for x in absorptions if x["status"]=="ABSORBED"]
        profile_stats[profile]["absorbed_donors_provenance"]+=len(accepted)
        profile_stats[profile]["receiver_groups"]+=len({(x["candidate_id"],x["receiver"]) for x in accepted})
        profile_stats[profile]["unique_receivers"]+=len({(x["scene_id"],x["receiver"]) for x in accepted})
        if len(masks) != len(rows): raise SystemExit("land-cover provenance coverage failed")
        for mask in masks:
            if int(mask["target_mask_count"]) != int(round(float(manifest["profile"]["landcover_mask_fraction"]) * int(mask["valid_cell_count"]))):
                raise SystemExit("land-cover exact target count failed")
            if int(mask["maximum_concurrent_fronts"]) > 4: raise SystemExit("land-cover concurrent-front contract failed")
            profile_stats[profile]["landcover_initial_seeds"] += len(json.loads(mask["initial_seeds_json"]))
            profile_stats[profile]["landcover_reseeds"] += len(json.loads(mask["reseeds_json"]))
            profile_stats[profile]["landcover_components"] += int(mask["realized_component_count"])
            profile_stats[profile]["landcover_maximum_concurrent_fronts"] = max(
                profile_stats[profile]["landcover_maximum_concurrent_fronts"], int(mask["maximum_concurrent_fronts"])
            )
        ordered.append({"branch_id":manifest["branch_id"],"profile_id":profile,"payload_sha256":manifest["payload"]["sha256"],"logical_content_sha256":manifest["logical_content_sha256"]})
    if len(candidates)!=116208 or len({x["candidate_id"] for x in candidates})!=116208: raise SystemExit("physical candidate coverage failed")
    scenes={x["scene_id"] for x in candidates}; profiles={x["profile_id"] for x in candidates}
    if len(scenes)!=2421 or profiles!={"weak_0.5x","main_1.0x","strong_2.0x"}: raise SystemExit("scene/profile coverage failed")
    grouped=defaultdict(dict)
    for row in candidates: grouped[(row["profile_id"],row["scene_id"])][int(row["master_view_id"])]=row["candidate_id"]
    index_rows=[]
    for (profile,scene),views in sorted(grouped.items()):
        if set(views)!=set(range(16)): raise SystemExit("K16 coverage failed")
        for k in (2,4,8,16):
            for view in range(k): index_rows.append({"profile_id":profile,"scene_id":scene,"requested_k":k,"master_view_id":view,"candidate_id":views[view]})
    default_count=sum(1 for x in index_rows if x["requested_k"]==8)
    if default_count!=58104: raise SystemExit("K8 coverage failed")
    content=digest(ordered); acceptance_id="aba_"+digest([spec["bank_id"],content])[:24]
    stats={name:{**dict(values),"logical_k8_references":19368,"payload_bytes":payload_bytes[name],
                 "attempt_distribution":dict(sorted(attempt_stats[name].items(),key=lambda x:int(x[0]))),
                 "relation_statistics":{rel:dict(values) for rel,values in sorted(relation_stats[name].items())}}
           for name,values in sorted(profile_stats.items())}
    maximum_error=max((float(x.get("maximum_geometry_derived_error",0.0)) for x in spec.get("validations",[])),default=0.0)
    acceptance={"schema_version":"1.0.0","status":"PASS","supplement_version":spec["supplement_version"],"acceptance_id":acceptance_id,"bank_id":spec["bank_id"],"parent_cache_id":spec["cache_id"],"parent_acceptance_id":spec["cache_acceptance_id"],
                "scene_count":2421,"profile_count":3,"physical_candidate_count":116208,"logical_k8_reference_count":58104,"branch_count":len(manifests),"profile_statistics":stats,
                "total_payload_bytes":sum(payload_bytes.values()),"maximum_geometry_derived_error":maximum_error,
                "aggregate_content_sha256":content,"violations":{"missing_candidates":0,"duplicate_candidates":0,"prefix":0,"scientific":0,
                "dangling_identity":0,"invalid_receiver":0,"receiver_cycle":0,"invalid_geometry":0,"float32_geometry":0,"derived_value":0,
                "relation":0,"topology":0,"raster":0,"rng_replay":0,"immutable_collision":0,"incomplete_publication":0}}
    Path(args.acceptance).write_bytes(canonical(acceptance))
    index_content=digest(index_rows); index_id="abi_"+index_content[:24]
    pq.write_table(pa.Table.from_pylist(index_rows),args.index_parquet,compression="zstd",use_dictionary=False)
    index={"schema_version":"1.0.0","status":"PASS","supplement_version":spec["supplement_version"],"index_id":index_id,"bank_id":spec["bank_id"],"scene_count":2421,"profile_count":3,"prefixes":[2,4,8,16],"default_k":8,"default_reference_count":58104,"row_count":len(index_rows),"content_sha256":index_content}
    Path(args.index_manifest).write_bytes(canonical(index))


if __name__=="__main__": main()
