"""Versioned inspector presentation over immutable accepted retrieval evidence.

No scene rendering, embedding loading, ranking computation, or scientific target
execution is exposed here. Only the explicitly requested HTML entry is replaced.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile

import pyarrow.compute as pc
import pyarrow.parquet as pq

from .inspector import MODEL_IDS, InspectorError, band_ranks, validate_output


ACCEPTANCE_ID = "retr10k_0672df44ea0fb5adceafbec9"


def read(path):
    return json.loads(Path(path).read_text())


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def immutable(path, raw):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != raw:
            raise InspectorError(f"Presentation identity collision: {path}")
        return
    with path.open("xb") as handle:
        handle.write(raw)


def require_hash(path, expected):
    if digest(path) != expected:
        raise InspectorError(f"Accepted evidence checksum mismatch: {path}")


def accepted_evidence(repository, output):
    """Read back both galleries and all expanded bands, without reranking."""
    repository, output = Path(repository), Path(output)
    pointer = read(repository / "tools/retrieval_inspector/supplemental_output.json")
    acceptance_path = Path(pointer["acceptance_path"])
    require_hash(acceptance_path, pointer["acceptance_sha256"])
    acceptance = read(acceptance_path)
    if (acceptance["acceptance_id"] != ACCEPTANCE_ID or pointer["acceptance_id"] != ACCEPTANCE_ID
            or acceptance["status"] != "PASS" or not acceptance["canonical_p10_unchanged"]
            or not acceptance["canonical_p11_unchanged"] or acceptance["union_count"] != 10000
            or output.resolve() != (acceptance_path.parent.parent / "inspector").resolve()):
        raise InspectorError("Supplemental authority/output mismatch")
    root = output.parent
    parents = {"methodology":"methodology.json", "sampling_index":"index/supplemental_scene_index.parquet",
        "spatial_truth":"spatial_manifest.json", "scene_cache":"cache/cache_manifest.json",
        "prepared_input":"prepared/prepared_manifest.json", "geometry":"geometry/geometry_manifest.json",
        "embeddings":"embeddings/embedding_manifest.json", "union_gallery":"union/union_manifest.json",
        "rankings":"rankings/ranking_manifest.json", "inspector":"inspector/manifest.json",
        "validation":"validation/validation.json"}
    for key, relative in parents.items():
        require_hash(root / relative, acceptance["parents_sha256"][key])
    validate_output(output)
    manifest, ranking = read(output / "manifest.json"), read(root / "rankings/ranking_manifest.json")
    diagnostics_path = root / "rankings/stability_diagnostics.json"
    require_hash(diagnostics_path, ranking["identity"]["diagnostics_sha256"])
    example = read(repository / "tools/retrieval_inspector/example_output.json")
    old_path = (repository / example["output_path"]).parent / "manifest.json"
    require_hash(old_path, manifest["identity_preimage"]["canonical_inspector_manifest_sha256"])
    old = read(old_path)
    canonical, expanded = manifest["galleries"]["canonical"], manifest["galleries"]["supplemental"]
    if (canonical["gallery_count"] != 1600 or expanded["gallery_count"] != 10000
            or canonical["models"] != old["models"] or canonical["queries"] != old["queries"]
            or expanded["models"] != ranking["models"] or expanded["queries"] != canonical["queries"]
            or set(expanded["models"]) != set(MODEL_IDS) or len(canonical["queries"]) != 10):
        raise InspectorError("Canonical/expanded inspector evidence differs")
    union = read(root / "union/union_manifest.json")
    require_hash(root / "union/gallery.parquet", union["gallery_sha256"])
    rows = pq.read_table(root / "union/gallery.parquet").to_pylist()
    sources = {r["scene_id"]: r["source"] for r in rows}
    if (len(rows) != 10000 or len(sources) != 10000
            or sum(s == "canonical" for s in sources.values()) != 1600):
        raise InspectorError("Gallery population mismatch")
    records = read(diagnostics_path)
    lookup = {(d["model"], d["query"], d["setting"]): d for d in records}
    query_ids = {q["scene_id"] for q in canonical["queries"]}
    expected = {(m, q, s) for m in MODEL_IDS for q in query_ids for s in ("standard", "nonlocal")}
    if len(records) != 160 or set(lookup) != expected:
        raise InspectorError("Diagnostic state coverage mismatch")
    display, band_count = {}, 0
    for file in ranking["ranking_files"]:
        path = root / "rankings" / file["filename"]
        require_hash(path, file["sha256"])
        table = pq.read_table(path)
        model, setting = file["model"], file["setting"]
        for query in query_ids:
            candidates = table.filter(pc.equal(table["query_scene_id"], query)).to_pylist()
            view = expanded["models"][model]["queries"][query][setting]
            if len(candidates) != view["candidate_count"] or (setting == "standard" and len(candidates) != 9999):
                raise InspectorError("Candidate count readback mismatch")
            if [r["rank"] for r in candidates] != list(range(1, len(candidates) + 1)):
                raise InspectorError("Stored rank ordinals are not contiguous")
            if (len({r["candidate_scene_id"] for r in candidates}) != len(candidates)
                    or any(r["candidate_scene_id"] == query or r["source"] != sources[r["candidate_scene_id"]]
                           or (setting == "nonlocal" and r["distance_m"] < 2000) for r in candidates)):
                raise InspectorError("Stored self/source/non-local gate failed")
            for gallery in (canonical, expanded):
                group = gallery["models"][model]["queries"][query][setting]
                if gallery is canonical and setting == "standard" and group["candidate_count"] != 1599:
                    raise InspectorError("Canonical candidate count changed")
                for band, ranks in band_ranks(group["candidate_count"]).items():
                    if [x["rank"] for x in group["bands"][band]] != ranks:
                        raise InspectorError("Rank-band definition mismatch")
                    for item in group["bands"][band]:
                        if item["scene_id"] not in manifest["scene_asset_sha256"]:
                            raise InspectorError("Required band asset missing")
                        if gallery is expanded:
                            stored = candidates[item["rank"] - 1]
                            if any(item[a] != stored[b] for a, b in (("scene_id","candidate_scene_id"),
                                ("similarity","similarity"), ("distance_m","distance_m"), ("source","source"))):
                                raise InspectorError("Band rank/similarity/distance/source readback mismatch")
                        elif sources[item["scene_id"]] != "canonical":
                            raise InspectorError("Noncanonical scene in canonical gallery")
                        band_count += 1
            d = lookup[(model, query, setting)]
            old_best = canonical["models"][model]["queries"][query][setting]["bands"]["most"][0]
            best = candidates[0]
            if (not 1 <= d["old_best_new_rank"] <= len(candidates)
                    or candidates[d["old_best_new_rank"] - 1]["candidate_scene_id"] != old_best["scene_id"]
                    or d["new_best_scene_id"] != best["candidate_scene_id"]
                    or d["new_best_similarity"] != best["similarity"]
                    or d["new_best_distance_m"] != best["distance_m"] or d["new_best_source"] != best["source"]):
                raise InspectorError("Authoritative diagnostic binding mismatch")
            display.setdefault(model, {}).setdefault(query, {})[setting] = {"diagnostic":d,"old_best":old_best}
    return {"acceptance_id":ACCEPTANCE_ID, "acceptance_sha256":digest(acceptance_path),
        "inspector_manifest_sha256":digest(output / "manifest.json"),
        "ranking_manifest_sha256":digest(root / "rankings/ranking_manifest.json"),
        "stability_diagnostics_sha256":digest(diagnostics_path), "diagnostics":display,
        "validation":{"canonical_states":160,"expanded_states":160,"band_items_checked":band_count,
            "asset_count":len(manifest["scene_asset_sha256"]),"canonical_assets_unchanged":len(old["scene_asset_sha256"]),
            "status":"PASS"}}


def prepare_update(repository, output):
    repository, output = Path(repository), Path(output)
    evidence = accepted_evidence(repository, output)
    source = repository / "tools/retrieval_inspector"
    implementation = {name:digest(source / name) for name in ("index.html","app.js","style.css","presentation.py","browser_validation.py")}
    identity = {"version":"inspector-presentation-v2", "evidence_sha256":hashlib.sha256(encoded(evidence)).hexdigest(),
                "implementation":implementation}
    revision = "retrview_" + hashlib.sha256(encoded(identity)).hexdigest()[:24]
    directory = output / "presentations" / revision
    html = (source / "index.html").read_text()
    prefix = f"presentations/{revision}/"
    html = html.replace('href="style.css"', f'href="{prefix}style.css"').replace('src="app.js"', f'src="{prefix}app.js"')
    html = html.replace("<!-- presentation-data -->", f'<script src="{prefix}diagnostics.js"></script>')
    immutable(directory / "entry.html", html.encode())
    immutable(directory / "index.html", html.replace("<head>", '<head>\n  <base href="../../">').encode())
    for name in ("app.js","style.css"):
        immutable(directory / name, (source / name).read_bytes())
    immutable(directory / "diagnostics.js", b"window.RETRIEVAL_PRESENTATION=" + encoded(evidence).replace(b"<",b"\\u003c") + b";\n")
    manifest = {"presentation_id":revision,"identity":identity,"evidence_validation":evidence["validation"],
                "files":{name:digest(directory / name) for name in ("entry.html","index.html","app.js","style.css","diagnostics.js")}}
    immutable(directory / "presentation.json", encoded(manifest))
    return directory


def publish_update(output, directory, browser_validation):
    output, directory = Path(output), Path(directory)
    manifest = read(directory / "presentation.json")
    if (browser_validation.get("status") != "PASS" or browser_validation.get("desktop_states") != 320
            or browser_validation.get("presentation_id") != manifest["presentation_id"]
            or any(browser_validation.get(k) != 0 for k in ("console_errors","page_errors","failed_requests"))):
        raise InspectorError("Complete presentation browser validation required")
    for name, checksum in manifest["files"].items():
        require_hash(directory / name, checksum)
    previous = output / "index.html"
    old_hash = digest(previous)
    accepted_hash = read(output / "manifest.json")["identity_preimage"]["implementation"]["index.html"]
    current_receipt = output / "presentation.json"
    allowed = {accepted_hash, manifest["files"]["entry.html"]}
    if current_receipt.exists():
        allowed.add(read(current_receipt)["entry_sha256"])
    if old_hash not in allowed:
        raise InspectorError("Refusing to replace an unrecognized inspector entry")
    immutable(output / "presentation_history" / old_hash / "index.html", previous.read_bytes())
    immutable(directory / "browser_validation.json", encoded(browser_validation))
    receipt = {"presentation_id":manifest["presentation_id"],"entry_sha256":manifest["files"]["entry.html"],
        "presentation_manifest_sha256":digest(directory / "presentation.json"),
        "accepted_inspector_manifest_sha256":digest(output / "manifest.json"),"acceptance_id":ACCEPTANCE_ID,
        "browser_validation_sha256":digest(directory / "browser_validation.json"),"previous_entry_sha256":old_hash}
    # Only these two explicitly mutable presentation pointers are replaced.
    for destination, raw in ((current_receipt,encoded(receipt)),(previous,(directory / "entry.html").read_bytes())):
        with tempfile.NamedTemporaryFile(dir=output, delete=False) as handle:
            handle.write(raw)
            temporary = Path(handle.name)
        os.replace(temporary, destination)
    return previous


def validate_presentation(output):
    output = Path(output)
    receipt = read(output / "presentation.json")
    revision = receipt["presentation_id"]
    if not revision.startswith("retrview_") or len(revision) != 33 or any(c not in "0123456789abcdef" for c in revision[9:]):
        raise InspectorError("Invalid presentation identity")
    directory = output / "presentations" / revision
    require_hash(output / "index.html", receipt["entry_sha256"])
    require_hash(output / "manifest.json", receipt["accepted_inspector_manifest_sha256"])
    require_hash(directory / "presentation.json", receipt["presentation_manifest_sha256"])
    require_hash(directory / "browser_validation.json", receipt["browser_validation_sha256"])
    for name, checksum in read(directory / "presentation.json")["files"].items():
        require_hash(directory / name, checksum)
    original = read(output / "manifest.json")["identity_preimage"]["implementation"]["index.html"]
    require_hash(output / "presentation_history" / original / "index.html", original)
    return {"status":"PASS","presentation_id":revision}
