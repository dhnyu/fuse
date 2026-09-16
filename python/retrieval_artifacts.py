"""S10 immutable artifacts. No model, inference, scoring or selection dependencies."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path


def require(condition, message):
    if not condition:
        raise ValueError("S10_" + message)


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "DUPLICATE_JSON_KEY")
            result[key] = value
        return result
    return json.loads(Path(path).read_text(), object_pairs_hook=unique)


def validate_envelope(value):
    if value.get("kind") != "fixture":
        from jsonschema import validate
        validate(value, read_json(Path(__file__).resolve().parents[1] / "config/schemas/retrieval_artifact.schema.json"))
        if value.get("kind") == "geometry_features":
            validate(value["body"], read_json(Path(__file__).resolve().parents[1] / "config/schemas/retrieval_geometry.schema.json"))


def publish_bytes(path, raw):
    """Stage then create-or-validate; never overwrite user/scientific files."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        require(path.read_bytes() == raw, "IMMUTABLE_COLLISION:" + str(path))
        return path
    fd, name = tempfile.mkstemp(prefix=".s10-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(name, path)
        except FileExistsError:
            require(path.read_bytes() == raw, "IMMUTABLE_COLLISION")
    finally:
        Path(name).unlink(missing_ok=True)
    return path


def publish(path, kind, body, files=()):
    path = Path(path)
    records = [{"path": os.path.relpath(p, path.parent), "sha256": file_hash(p),
                "bytes": Path(p).stat().st_size} for p in files]
    value = {"schema_version": "1.0.0", "kind": kind, "body": body, "files": records}
    value["sha256"] = digest(value)
    value["artifact_id"] = "s10_" + kind + "_" + value["sha256"][:24]
    validate_envelope(value)
    publish_bytes(path, encoded(value))
    load(path, kind)
    return str(path)


def load(path, kind=None):
    path = Path(path)
    value = read_json(path)
    validate_envelope(value)
    payload = {k: v for k, v in value.items() if k not in ("sha256", "artifact_id")}
    require(value.get("sha256") == digest(payload), "MANIFEST_HASH")
    require(value.get("artifact_id") == "s10_" + value["kind"] + "_" + value["sha256"][:24], "MANIFEST_ID")
    require(kind is None or value["kind"] == kind, "MANIFEST_KIND")
    for row in value["files"]:
        p = (path.parent / row["path"]).resolve()
        require(p.is_relative_to(path.parent.resolve()), "ARTIFACT_PATH_ESCAPE")
        require(p.is_file() and p.stat().st_size == row["bytes"] and file_hash(p) == row["sha256"], "ARTIFACT_HASH")
    return value


def output_paths(path):
    manifest = load(path)
    return [str(path), *[str(Path(path).parent / r["path"]) for r in manifest["files"]]]
