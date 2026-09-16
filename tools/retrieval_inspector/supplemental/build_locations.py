#!/usr/bin/env python3
"""Metadata-only supplemental publication from immutable viewer bytes.

No scientific execution imports. Existing band rows and assets are byte-reused.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
SOURCE_FILES = ["config/s10_viewer_locations.json", "R/viewer_locations.R",
                "scripts/build_viewer_locations.R", "tools/retrieval_inspector/supplemental/build_locations.py",
                "tools/retrieval_inspector/supplemental/bands_app.js",
                "tools/retrieval_inspector/supplemental/locations.js",
                "tools/retrieval_inspector/supplemental/locations.css"]


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def file_hash(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("LOCATION_DUPLICATE_JSON_KEY:" + key)
            result[key] = value
        return result
    return json.loads(Path(path).read_text(), object_pairs_hook=unique)


def require(condition, message):
    if not condition:
        raise ValueError("LOCATION_" + message)


def pinned(record):
    require(file_hash(record["path"]) == record["sha256"], "SOURCE_CHECKSUM_MISMATCH:" + record["path"])
    return Path(record["path"])


def envelope(value):
    require(digest({k: v for k, v in value.items() if k not in ("artifact_id", "sha256")}) == value["sha256"], "ENVELOPE_HASH")
    require(value["artifact_id"] == "s10_" + value["kind"] + "_" + value["sha256"][:24], "ENVELOPE_ID")


def safe_path(root, name):
    p = Path(name)
    require(not p.is_absolute() and ".." not in p.parts, "UNSAFE_PATH")
    path = root / p
    require(path.resolve().is_relative_to(root.resolve()), "PATH_ESCAPE")
    return path


def validate_gallery(gallery, expected_count=9000):
    rows = gallery["body"]["rows"]
    require(gallery["body"]["crs"] == "EPSG:5186" and gallery["body"]["units"] == "metres", "GALLERY_CRS")
    require(len(rows) == expected_count and len({r["scene_id"] for r in rows}) == expected_count, "GALLERY_MEMBERSHIP")
    require(all(r["epsg"] == 5186 and r["split"] == "evaluation" and
                all(isinstance(r[k], (float, int)) and math.isfinite(r[k]) for k in ("center_x", "center_y")) for r in rows), "GALLERY_CENTERS")
    return {r["scene_id"]: r for r in rows}


def make_metadata(gallery, assignments, provenance, expected_count=9000):
    centers = validate_gallery(gallery, expected_count)
    rows = assignments["rows"]
    require(len(rows) == len(centers) and len({r["scene_id"] for r in rows}) == len(rows) and
            {r["scene_id"] for r in rows} == set(centers), "ASSIGNMENT_MEMBERSHIP")
    scenes = {}
    counts = {"total_scenes": len(rows), "lonlat_finite_count": 0, "hierarchy_mismatch_count": 0}
    for raw in sorted(rows, key=lambda r: r["scene_id"]):
        row = dict(raw); center = centers[row["scene_id"]]
        row.update(center_x=center["center_x"], center_y=center["center_y"], source_crs="EPSG:5186",
                   longitude=float(row["longitude"]), latitude=float(row["latitude"]),
                   admin_kind="administrative_dong", boundary_date="2025-06-30")
        require(math.isfinite(row["longitude"]) and math.isfinite(row["latitude"]) and
                -180 <= row["longitude"] <= 180 and -90 <= row["latitude"] <= 90, "NONFINITE_LONLAT")
        counts["lonlat_finite_count"] += 1
        for level, prefix in [("sigungu", "sigungu"), ("dong", "eupmyeondong")]:
            status = row[level + "_join_status"]
            codes = row[level + "_candidate_codes"]; names = row[level + "_candidate_names"]
            require(isinstance(codes, list) and isinstance(names, list) and len(codes) == len(names) and
                    codes == sorted(set(codes)) and all(isinstance(n, str) and n for n in names), "CANDIDATES")
            expected = "no_polygon_match" if not codes else "unique_match" if len(codes) == 1 else "boundary_ambiguous"
            require(status == expected, "JOIN_STATUS")
            require((row[prefix+"_code"] == codes[0] and row[prefix+"_name"] == names[0]) if status == "unique_match"
                    else (row[prefix+"_code"] is None and row[prefix+"_name"] is None), "JOIN_LABEL")
        if row["sigungu_join_status"] == row["dong_join_status"] == "unique_match":
            require(row["eupmyeondong_code"][:5] == row["sigungu_code"] and row["hierarchy_status"] == "consistent", "HIERARCHY_MISMATCH")
        else:
            require(row["hierarchy_status"] == "not_comparable", "HIERARCHY_STATUS")
        scenes[row["scene_id"]] = row
    for level in ["sigungu", "dong"]:
        c = Counter(r[level+"_join_status"] for r in scenes.values())
        for status in ["unique_match", "no_polygon_match", "boundary_ambiguous"]:
            counts[level+"_"+status+"_count"] = c[status]
    counts["unique_sigungu_count"] = len({r["sigungu_code"] for r in scenes.values() if r["sigungu_code"]})
    counts["unique_dong_count"] = len({r["eupmyeondong_code"] for r in scenes.values() if r["eupmyeondong_code"]})
    content = dict(schema_version="1.0.0", kind="supplemental_scene_locations", scenes=scenes,
                   qc=counts, provenance=provenance, transform=assignments["transform"],
                   scientific_mutation=False, ranking_recomputation=False, inference=False)
    return {**content, "artifact_id": "s10_locations_"+digest(content)[:24]}


def bind_scene(scene, centers):
    require(scene["scene_id"] in centers and scene["center"] ==
            [centers[scene["scene_id"]]["center_x"], centers[scene["scene_id"]]["center_y"]], "SCENE_CENTER_BINDING")


def publish_file(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw)


def validate_existing(output, expected):
    actual = read(output/"viewer_receipt.json")
    require(actual == expected, "IMMUTABLE_RECEIPT_COLLISION")
    actual_files = {str(p.relative_to(output)) for p in output.rglob("*") if p.is_file()}
    require(actual_files == set(expected["files"]) | {"viewer_receipt.json"}, "IMMUTABLE_FILE_SET")
    for name, h in expected["files"].items():
        require(file_hash(safe_path(output, name)) == h, "IMMUTABLE_FILE_COLLISION:"+name)


def build(output_root, settings_path=ROOT/"config/s10_viewer_locations.json"):
    settings_path = Path(settings_path); settings = read(settings_path)
    source_hashes = {name: file_hash(ROOT/name) for name in SOURCE_FILES}
    pinned_inputs = [settings[k] for k in ["parent_acceptance", "parent_viewer", "band_evidence", "gallery"]]
    pinned_inputs += [r for b in settings["boundaries"].values() for r in b["components"].values()]
    for record in pinned_inputs:
        pinned(record)
    require(settings["boundary_date"] == "2025-06-30", "BOUNDARY_DATE")
    parent = Path(settings["parent_viewer"]["path"]).parent
    require(parent.name == settings["parent_viewer"]["id"], "PARENT_VIEWER_ID")
    receipt = read(parent/"viewer_receipt.json"); acceptance = read(settings["parent_acceptance"]["path"])
    gallery = read(settings["gallery"]["path"]); evidence = read(settings["band_evidence"]["path"])
    envelope(acceptance); envelope(gallery)
    require(acceptance["body"]["status"] == "PASS" and acceptance["artifact_id"] == settings["parent_acceptance"]["id"] == receipt["parent"], "ACCEPTANCE_PARENT")
    require(acceptance["body"]["artifacts"][settings["gallery"]["path"]] == gallery["artifact_id"] == settings["gallery"]["id"], "GALLERY_PARENT")
    require(evidence["evidence_id"] == settings["band_evidence"]["id"] == receipt["band_evidence_id"], "BAND_PARENT")
    centers = validate_gallery(gallery)
    config = read(parent/"config.json")
    require(len(config["models"]) == 28 and len(config["queries"]) == 30 and config["gallery_count"] == 9000, "VIEWER_COUNTS")
    require(config["acceptance"] == acceptance["artifact_id"] and config["evidence_id"] == evidence["evidence_id"], "CONFIG_PARENT")
    require(all(receipt["files"].get(n) == h for n,h in config["files"].items()), "CONFIG_FILE_BINDING")
    # One complete byte audit of existing display assets, never model/science payloads.
    for i,(name,h) in enumerate(receipt["files"].items()):
        require(file_hash(safe_path(parent,name)) == h, "PARENT_FILE_HASH:"+name)
        if name.startswith("scenes/") and name.endswith(".json"):
            bind_scene(read(parent/name), centers)
        if i and i % 3000 == 0:
            print(f"Verified {i} immutable parent display files", flush=True)
    print("Parent display byte audit passed; joining 9,000 centers with R sf", flush=True)
    provenance = {k: settings[k] for k in ["parent_acceptance", "parent_viewer", "band_evidence", "gallery", "boundaries", "boundary_date"]}
    provenance["implementation_sha256"] = source_hashes
    output_root = Path(output_root); output_root.mkdir(parents=True, exist_ok=True)
    # Staging never inside a published viewer; only this task's temporary directory is removed.
    with tempfile.TemporaryDirectory(prefix=".locations-stage-", dir=output_root) as temporary:
        stage = Path(temporary); computed = stage/"assignments.json"
        subprocess.run(["Rscript", str(ROOT/"scripts/build_viewer_locations.R"), str(ROOT), settings["gallery"]["path"],
                        settings["boundaries"]["sigungu"]["components"][".shp"]["path"],
                        settings["boundaries"]["dong"]["components"][".shp"]["path"], str(computed)],
                       check=True, env={**os.environ, "PROJ_NETWORK":"OFF", "OMP_NUM_THREADS":"1", "OPENBLAS_NUM_THREADS":"1"})
        metadata = make_metadata(gallery, read(computed), provenance)
        # Explicit exceptions are represented by the schema, but this publication
        # requires complete Seoul assignment and never fills a missing label.
        require(metadata["qc"]["sigungu_unique_match_count"] == metadata["qc"]["dong_unique_match_count"] == 9000, "INCOMPLETE_SEOUL_ASSIGNMENT:"+str(metadata["qc"]))
        computed.unlink()
        location_bytes = encoded(metadata); location_sha = hashlib.sha256(location_bytes).hexdigest()
        identity = {"metadata_id":metadata["artifact_id"], "metadata_sha256":location_sha,
                    "parent_viewer_sha256":settings["parent_viewer"]["sha256"], "sources":source_hashes}
        viewer_id = "viewer_"+digest(identity)[:24]; output = output_root/viewer_id
        files = {}; replaced = {"config.json", "bands_app.js", "index.html"} | {f"query_{i:02d}.html" for i in range(1,31)}
        for name,h in receipt["files"].items():
            if name in replaced:
                continue
            destination = stage/name; destination.parent.mkdir(parents=True, exist_ok=True)
            # Byte copy: no hard links that could allow a future write into the parent.
            shutil.copyfile(parent/name, destination); files[name] = h
        def put(name, raw):
            publish_file(stage/name, raw); files[name] = hashlib.sha256(raw).hexdigest()
        for name in ["bands_app.js", "locations.js", "locations.css"]:
            put(name, (HERE/name).read_bytes())
        put("location_metadata.json", location_bytes)
        config = {**config, "files":files.copy(), "location_metadata":{"path":"location_metadata.json", "artifact_id":metadata["artifact_id"], "sha256":location_sha}}
        put("config.json", encoded(config))
        for name in ["index.html"]+[f"query_{i:02d}.html" for i in range(1,31)]:
            html = (parent/name).read_text()
            require(html.count(receipt["files"]["config.json"]) == 1, "HTML_CONFIG_BINDING")
            html = html.replace(receipt["files"]["config.json"], files["config.json"])
            require('<script src="bands_app.js"></script>' in html and '</head>' in html, "HTML_ANCHORS")
            html = html.replace('</head>', '<link rel="stylesheet" href="locations.css"></head>')
            html = html.replace('<script src="bands_app.js"></script>', '<script src="locations.js"></script><script src="bands_app.js"></script>')
            put(name, html.encode())
        new_receipt = dict(schema_version="1.0.0", viewer_id=viewer_id, identity=identity,
                           scope="supplemental metadata-only scene-center locations", parent=receipt["parent"],
                           parent_sha256=settings["parent_acceptance"]["sha256"],
                           parent_viewer=settings["parent_viewer"], band_evidence=settings["band_evidence"],
                           band_evidence_id=evidence["evidence_id"], gallery=settings["gallery"],
                           location_metadata=config["location_metadata"], boundary_sources=settings["boundaries"],
                           boundary_date=settings["boundary_date"], transform=metadata["transform"],
                           code=source_hashes, files=files, qc=metadata["qc"], output=str(output),
                           reused_files={n:h for n,h in receipt["files"].items() if n not in replaced},
                           scientific_mutation=False, ranking_recomputation=False, inference=False)
        # Verify copies and unchanged parents before the immutable publication boundary.
        for name,h in files.items():
            require(file_hash(stage/name) == h, "STAGED_HASH:"+name)
        for name,h in receipt["files"].items():
            require(file_hash(parent/name) == h, "PARENT_CHANGED:"+name)
        for record in pinned_inputs:
            pinned(record)
        require(source_hashes == {name:file_hash(ROOT/name) for name in SOURCE_FILES}, "IMPLEMENTATION_CHANGED")
        publish_file(stage/"viewer_receipt.json", encoded(new_receipt))
        if output.exists():
            validate_existing(output, new_receipt)
        else:
            # mkdir reservation prevents overwriting a colliding generation. Receipt last.
            output.mkdir()
            try:
                for child in list(stage.iterdir()):
                    if child.name != "viewer_receipt.json":
                        os.rename(child, output/child.name)
                os.rename(stage/"viewer_receipt.json", output/"viewer_receipt.json")
            except BaseException:
                # Do not destroy an incomplete output; absence of receipt rejects serving it.
                raise
    print(json.dumps({"status":"PASS", "viewer":str(output), "qc":metadata["qc"]}, ensure_ascii=False), flush=True)
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", default="/mnt/hdd002/dhnyu/fusedata/retrieval_data/reduced/s10_viewers")
    args = parser.parse_args()
    build(args.output_root)
