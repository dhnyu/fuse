from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from prototype_training_runtime_mirror import prepare_runtime_mirror, validate_runtime_mirror


def write_archive(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value)


def test_atomic_runtime_mirror_copy_and_reuse(tmp_path: Path) -> None:
    source, runtime = tmp_path / "source", tmp_path / "runtime"
    write_archive(source / "branches/a/scenes.tar", b"tar")
    write_archive(source / "branches/a/scenes.idx", b"idx")
    write_archive(source / "branches/a/ignored.json", b"ignored")
    source_before = {
        path: (path.stat().st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest())
        for path in source.rglob("*") if path.is_file()
    }

    first = prepare_runtime_mirror(source, runtime)
    assert first["reuse"] is False
    assert first["file_count"] == 2
    assert validate_runtime_mirror(source, runtime) is not None
    second = prepare_runtime_mirror(source, runtime)
    assert second["reuse"] is True
    assert source_before == {
        path: (path.stat().st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest())
        for path in source.rglob("*") if path.is_file()
    }


def test_incomplete_or_colliding_runtime_mirror_is_rejected(tmp_path: Path) -> None:
    source, runtime = tmp_path / "source", tmp_path / "runtime"
    write_archive(source / "branches/a/scenes.tar", b"tar")
    runtime.mkdir()
    write_archive(runtime / "foreign.tar", b"foreign")
    with pytest.raises(ValueError, match="incomplete or colliding"):
        prepare_runtime_mirror(source, runtime)


def test_runtime_corruption_is_detected_without_overwrite(tmp_path: Path) -> None:
    source, runtime = tmp_path / "source", tmp_path / "runtime"
    write_archive(source / "branches/a/scenes.tar", b"tar")
    prepare_runtime_mirror(source, runtime)
    mirrored = runtime / "branches/a/scenes.tar"
    mirrored.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="incomplete or colliding"):
        prepare_runtime_mirror(source, runtime)
    assert mirrored.read_bytes() == b"corrupt"
