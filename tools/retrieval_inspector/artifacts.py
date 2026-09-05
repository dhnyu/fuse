"""Promote presentation packages, never scientific retrieval artifacts."""
from pathlib import Path
import hashlib
import json
import os

from .inspector import InspectorError, _atomic_write, validate_output
from .presentation import accepted_evidence, digest, encoded, immutable, read, require_hash, validate_presentation
from .browser_validation import validate_browser


LEGACY_ID = "retrieval_inspector_c612a074a9211c222eb9a811"


def identity_hash(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def register_legacy(repository, root):
    repository, root = Path(repository), Path(root)
    example = read(repository / "tools/retrieval_inspector/example_output.json")
    original = (repository / example["output_path"]).parent
    if example["inspector_id"] != LEGACY_ID:
        raise InspectorError("Unexpected legacy authority")
    validate_output(original, LEGACY_ID)
    manifest = read(original / "manifest.json")
    if manifest["gallery_count"] != 1600 or "galleries" in manifest:
        raise InspectorError("Legacy application is not the accepted 1600-only inspector")
    alias = root / "legacy" / LEGACY_ID
    alias.parent.mkdir(parents=True, exist_ok=True)
    if alias.is_symlink():
        if alias.resolve() != original.resolve():
            raise InspectorError("Legacy alias points to another artifact")
    elif alias.exists():
        raise InspectorError("Refusing to replace existing legacy directory")
    else:
        alias.symlink_to(os.path.relpath(original, alias.parent), target_is_directory=True)
    pointer = {"role":"legacy", "inspector_id":LEGACY_ID,
        "path":str((alias / "index.html").relative_to(repository)),
        "original_path":example["output_path"], "gallery_count":1600,
        "acceptance_id":example["p10_acceptance_id"],
        "core_sha256":{n:digest(original / n) for n in ("index.html","app.js","style.css","manifest.js","manifest.json")},
        "scene_asset_count":len(manifest["scene_asset_sha256"]),
        "scene_asset_manifest_sha256":identity_hash(manifest["scene_asset_sha256"])}
    immutable(root / "legacy.json", encoded(pointer))
    return alias / "index.html"


def legacy_output(repository, root):
    repository, root = Path(repository), Path(root)
    if not (root / "legacy.json").exists():
        return register_legacy(repository, root)
    pointer = read(root / "legacy.json")
    entry = repository / pointer["path"]
    if pointer["role"] != "legacy" or pointer["inspector_id"] != LEGACY_ID:
        raise InspectorError("Invalid legacy pointer")
    for name, checksum in pointer["core_sha256"].items():
        require_hash(entry.parent / name, checksum)
    validate_output(entry.parent, LEGACY_ID)
    return entry


def validate_current(directory):
    directory = Path(directory)
    artifact = read(directory / "artifact.json")
    expected_id = "retrieval_inspector_" + identity_hash(artifact["identity"])[:24]
    if artifact["inspector_id"] != expected_id or expected_id == LEGACY_ID:
        raise InspectorError("Invalid current artifact identity")
    for name, checksum in artifact["files"].items():
        require_hash(directory / name, checksum)
    manifest = read(directory / "manifest.json")
    if (manifest["default_gallery"] != "supplemental" or manifest["artifact_role"] != "current"
            or manifest["galleries"]["supplemental"]["gallery_count"] != 10000
            or manifest["galleries"]["canonical"]["gallery_count"] != 1600):
        raise InspectorError("Current gallery default/count contract failed")
    validate_output(directory, expected_id)
    validation = read(directory / "browser_validation.json")
    if (validation["status"] != "PASS" or validation["desktop_states"] != 320
            or validation["mobile_states"] != 32 or validation["default_gallery"] != "supplemental"
            or validation["presentation_id"] != expected_id
            or any(validation[k] for k in ("console_errors","page_errors","failed_requests"))):
        raise InspectorError("Current browser gate failed")
    html = (directory / "index.html").read_text()
    if 'id="gallery"' not in html or "Expanded 10,000" not in html or 'id="stability"' not in html:
        raise InspectorError("Current HTML is missing required 10K controls")
    return artifact


def resolve_current(repository, root):
    repository, root = Path(repository), Path(root)
    if not (root / "current.json").exists():
        return build_current(repository, root)
    pointer = read(root / "current.json")
    entry = repository / pointer["path"]
    if (pointer["role"] != "current" or pointer["gallery_count"] != 10000
            or pointer["default_gallery"] != "expanded" or pointer["inspector_id"] == LEGACY_ID
            or entry.parent.parent.resolve() != (root / "current").resolve()):
        raise InspectorError("Current pointer resolves to legacy or an invalid location")
    if not entry.exists():
        return build_current(repository, root)
    require_hash(entry.parent / "artifact.json", pointer["artifact_manifest_sha256"])
    require_hash(entry.parent / "manifest.json", pointer["manifest_sha256"])
    artifact = validate_current(entry.parent)
    if artifact["inspector_id"] != pointer["inspector_id"]:
        raise InspectorError("Current pointer identity mismatch")
    return entry


def build_current(repository, root):
    repository, root = Path(repository), Path(root)
    root.mkdir(parents=True, exist_ok=True)
    register_legacy(repository, root)
    pointer = read(repository / "tools/retrieval_inspector/supplemental_output.json")
    external = Path(pointer["acceptance_path"]).parent.parent / "inspector"
    validate_presentation(external)
    evidence = accepted_evidence(repository, external)
    accepted = read(external / "manifest.json")
    source = repository / "tools/retrieval_inspector"
    identity = {"version":"current-inspector-package-v1", "authority_id":external.parent.name,
        "acceptance_id":pointer["acceptance_id"], "acceptance_sha256":pointer["acceptance_sha256"],
        "ranking_manifest_sha256":evidence["ranking_manifest_sha256"],
        "stability_diagnostics_sha256":evidence["stability_diagnostics_sha256"],
        "accepted_inspector_manifest_sha256":digest(external / "manifest.json"),
        "union_manifest_sha256":digest(external.parent / "union/union_manifest.json"),
        "embedding_manifest_sha256":digest(external.parent / "embeddings/embedding_manifest.json"),
        "query_contract_sha256":accepted["qualitative_contract_sha256"],
        "assets_manifest_sha256":identity_hash(accepted["scene_asset_sha256"]),
        "presentation_contract":{"default_gallery":"expanded", "manifest_gallery_key":"supplemental",
            "gallery_count":10000,"canonical_gallery_count":1600,"query_count":10,"model_count":8},
        "implementation":{n:digest(source / n) for n in ("index.html","app.js","style.css","artifacts.py","presentation.py","browser_validation.py")}}
    current_id = "retrieval_inspector_" + identity_hash(identity)[:24]
    directory = root / "current" / current_id
    directory.mkdir(parents=True, exist_ok=True)
    manifest = {**accepted,"inspector_id":current_id,"accepted_inspector_id":accepted["inspector_id"],
        "identity_preimage":identity,"artifact_role":"current","default_gallery":"supplemental"}
    immutable(directory / "accepted_manifest.json", (external / "manifest.json").read_bytes())
    immutable(directory / "manifest.json", encoded(manifest))
    immutable(directory / "manifest.js", b"window.RETRIEVAL_MANIFEST=" + encoded(manifest).replace(b"<",b"\\u003c") + b";\n")
    immutable(directory / "diagnostics.js", b"window.RETRIEVAL_PRESENTATION=" + encoded(evidence).replace(b"<",b"\\u003c") + b";\n")
    html = (source / "index.html").read_text().replace("<!-- presentation-data -->", '<script src="diagnostics.js"></script>')
    html = html.replace('<option value="canonical">Canonical 1,600</option><option value="supplemental">Expanded 10,000</option>',
        '<option value="supplemental" selected>Expanded 10,000</option><option value="canonical">Canonical 1,600</option>')
    immutable(directory / "index.html", html.encode())
    for name in ("app.js","style.css"):
        immutable(directory / name, (source / name).read_bytes())
    assets = directory / "assets"
    target = external / "assets"
    if assets.is_symlink():
        if assets.resolve() != target.resolve():
            raise InspectorError("Current asset indirection changed")
    elif assets.exists():
        raise InspectorError("Refusing to replace current scene assets")
    else:
        assets.symlink_to(os.path.relpath(target, directory), target_is_directory=True)
    immutable(directory / "asset_binding.json", encoded({"strategy":"validated-relative-directory-symlink",
        "relative_target":os.readlink(assets),"scene_asset_count":3622,
        "assets_manifest_sha256":identity["assets_manifest_sha256"]}))
    immutable(directory / "presentation.json", encoded({"presentation_id":current_id,"identity":identity,
        "evidence_validation":evidence["validation"]}))
    # The current pointer is not published until the actual local HTML passes.
    if not (directory / "browser_validation.json").exists():
        validation = validate_browser(directory, output=directory)
        immutable(directory / "browser_validation.json", encoded(validation))
    files = ("index.html","app.js","style.css","manifest.json","manifest.js","accepted_manifest.json",
             "diagnostics.js","presentation.json","asset_binding.json","browser_validation.json")
    artifact = {"inspector_id":current_id,"identity":identity,"files":{n:digest(directory / n) for n in files}}
    immutable(directory / "artifact.json", encoded(artifact))
    validate_current(directory)
    current = {"role":"current","inspector_id":current_id,"path":str((directory / "index.html").relative_to(repository)),
        "acceptance_id":pointer["acceptance_id"],"gallery_count":10000,"default_gallery":"expanded",
        "query_count":10,"model_count":8,"scene_asset_count":3622,
        "manifest_sha256":digest(directory / "manifest.json"),"artifact_manifest_sha256":digest(directory / "artifact.json")}
    _atomic_write(root / "current.json", encoded(current))
    return directory / "index.html"
