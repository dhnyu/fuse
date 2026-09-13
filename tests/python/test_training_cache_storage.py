from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))
from artifact_protocol import canonical_json_bytes, canonical_sha256, sha256_file
from training_cache_storage import (CacheStorageError, READ_ROOT_ENV, RECEIPT,
    cache_inventory, copy_replica, member, resolve_cache_read_root, verify_replica)


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(data))


@pytest.fixture
def cache(tmp_path):
    root = tmp_path / "hdd" / "s09cache_fixture"
    root.mkdir(parents=True)
    (root / "prepared").mkdir()
    (root / "prepared/000000.pt").write_bytes(b"immutable-payload")
    write(root / "canonical_cache_plan.json", {"entries": [], "entry_count": 1})
    bindings = {}
    for kind, name in (("geometry", "geometry_cache_manifest.json"), ("ds", "ds_cache_manifest.json")):
        payload = root / kind / "entries/key.pt"
        payload.parent.mkdir(parents=True)
        payload.write_bytes(b"geometry-or-ds")
        manifest = {"cache_id": kind, "status": "PASS", "entry_count": 1,
                    "entries": [{"relative_path": "entries/key.pt", "payload_size_bytes": payload.stat().st_size,
                                 "payload_sha256": sha256_file(payload)}]}
        write(root / kind / name, manifest)
        bindings[kind] = {"cache_id": kind, "manifest_sha256": sha256_file(root / kind / name)}
    write(root / "geometry/COMPLETE.json", bindings["geometry"])
    p = root / "prepared/000000.pt"
    production = {"status": "PASS", "parents": {"p1": "accepted"}, "entry_count": 1,
                  "plan_sha256": sha256_file(root / "canonical_cache_plan.json"), **bindings,
                  "entries": [{"global_index": 0, "prepared_size": p.stat().st_size, "prepared_sha256": sha256_file(p)}]}
    production.update(cache_id=root.name, content_sha256=canonical_sha256(production))
    write(root / "production_cache_manifest.json", production)
    a = {"cache_id": root.name, "parents": production["parents"], "entry_count": 1,
         "status": "PASS", "manifest_sha256": sha256_file(root / "production_cache_manifest.json")}
    digest = canonical_sha256(a)
    a.update(acceptance_id="s09ca_" + digest[:24], content_sha256=digest)
    write(root / "acceptance.json", a)
    return root, tmp_path / "ssd" / root.name


def test_copy_resolve_and_source_preservation(cache):
    source, dest = cache
    before = {str(p): sha256_file(p) for p in source.rglob("*") if p.is_file()}
    receipt = copy_replica(source, dest)
    assert receipt["status"] == "VERIFIED"
    assert receipt["file_count"] == 9
    assert resolve_cache_read_root(source, {}) == source
    assert resolve_cache_read_root(source, {READ_ROOT_ENV: str(dest)}) == dest
    assert verify_replica(source, dest, full=True)["cache_id"] == source.name
    assert copy_replica(source, dest)["status"] == "VERIFIED"
    assert before == {str(p): sha256_file(p) for p in source.rglob("*") if p.is_file()}


@pytest.mark.parametrize("relative", ["../escape", "/etc/passwd", "geometry/../../escape", "./foo", "a//b"])
def test_traversal_rejected(cache, relative):
    with pytest.raises(CacheStorageError): member(cache[0], relative)


def test_no_silent_fallback_missing_or_empty(cache):
    source, dest = cache
    with pytest.raises(FileNotFoundError): resolve_cache_read_root(source, {READ_ROOT_ENV: str(dest)})
    with pytest.raises(CacheStorageError): resolve_cache_read_root(source, {READ_ROOT_ENV: ""})


def test_symlink_rejected(cache, tmp_path):
    source, dest = cache
    link = tmp_path / "link"
    link.symlink_to(source, target_is_directory=True)
    with pytest.raises(CacheStorageError): resolve_cache_read_root(source, {READ_ROOT_ENV: str(link)})
    copy_replica(source, dest)
    p = dest / "prepared/000000.pt"
    p.unlink(); p.symlink_to(source / "prepared/000000.pt")
    with pytest.raises(CacheStorageError): verify_replica(source, dest)


@pytest.mark.parametrize("file", ["prepared/000000.pt", "geometry/entries/key.pt", "ds/entries/key.pt"])
def test_payload_corruption_fails_full_verification(cache, file):
    source, dest = cache
    copy_replica(source, dest)
    p = dest / file
    p.write_bytes(b"x" * p.stat().st_size)
    with pytest.raises(CacheStorageError): verify_replica(source, dest, full=True)


def test_missing_file_receipt_and_metadata_fail_closed(cache):
    source, dest = cache
    copy_replica(source, dest)
    p = dest / "acceptance.json"
    p.write_bytes(b"x" * p.stat().st_size)
    with pytest.raises(CacheStorageError): verify_replica(source, dest)
    (dest / RECEIPT).unlink()
    with pytest.raises(FileNotFoundError): verify_replica(source, dest)


def test_existing_bad_file_is_not_overwritten(cache):
    source, dest = cache
    p = dest / "prepared/000000.pt"
    p.parent.mkdir(parents=True)
    p.write_bytes(b"evidence")
    with pytest.raises(CacheStorageError): copy_replica(source, dest)
    assert p.read_bytes() == b"evidence"
    assert not (dest / RECEIPT).exists()


def test_interrupted_partial_preserved(cache):
    source, dest = cache
    p = dest / "acceptance.json.copying"
    p.parent.mkdir(parents=True); p.write_bytes(b"partial")
    with pytest.raises(FileExistsError): copy_replica(source, dest)
    assert p.read_bytes() == b"partial"
    assert not (dest / RECEIPT).exists()


def test_wrong_receipt_or_canonical_mutation_rejected(cache):
    source, dest = cache
    copy_replica(source, dest)
    write(dest / RECEIPT, {"status": "VERIFIED"})
    with pytest.raises(CacheStorageError): verify_replica(source, dest)
    write(source / "acceptance.json", {"status": "PASS"})
    with pytest.raises(CacheStorageError): cache_inventory(source)


def test_space_guard_and_root_guard(cache, monkeypatch):
    from collections import namedtuple
    import training_cache_storage as storage
    source, dest = cache
    with pytest.raises(CacheStorageError): copy_replica(source, source)
    monkeypatch.setattr(storage.shutil, "disk_usage", lambda _: namedtuple("Space", "free")(0))
    with pytest.raises(CacheStorageError, match="INSUFFICIENT_SPACE"): copy_replica(source, dest)


def test_worker_shared_reader_and_preflight_wiring():
    worker = ast.parse((ROOT / "python/training_worker.py").read_text())
    load = next(n for n in worker.body if isinstance(n, ast.FunctionDef) and n.name == "load_worker_values")
    text = ast.unparse(load)
    assert "resolve_cache_read_root(spec['cache_root'])" in text
    assert "ProductionPreparedData(read_root" in text
    assert "DSRasterCacheReader(read_root)" in text
    assert "GeometryCacheReader(read_root /" in text
    assert "SceneCenterIndex.from_current_contract(base_training, spec['cache_root'])" in text
    controller = (ROOT / "scripts/training_controller.py").read_text()
    assert 'resolve_cache_read_root(contract["roots"]["production_cache"])' in controller


def test_replica_prepared_reads_check_sha_before_deserialization(tmp_path):
    from training_prepared_cache import ProductionPreparedData, PreparedCacheError
    data = object.__new__(ProductionPreparedData)
    data.root = tmp_path
    data.index = {("training", "scene", 0): {"global_index": 0}}
    data.payload_checks = {0: {"prepared_size": 3, "prepared_sha256": "0" * 64}}
    (tmp_path / "prepared").mkdir(); (tmp_path / "prepared/000000.pt").write_bytes(b"bad")
    with pytest.raises(PreparedCacheError, match="CORRUPTION"): data.sample("training", "scene", 0)
