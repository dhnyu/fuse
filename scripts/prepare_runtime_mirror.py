#!/usr/bin/env python3
"""Create and validate the execution-only SSD mirror for prototype rebuilding."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import yaml


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def record(role: str, source: Path, expected_size: int | None = None, expected_sha: str | None = None) -> dict:
    if not source.is_file():
        raise FileNotFoundError(source)
    size = source.stat().st_size
    checksum = sha256_file(source)
    if expected_size is not None and size != int(expected_size):
        raise ValueError(f"source size mismatch for {role}")
    if expected_sha is not None and checksum != expected_sha:
        raise ValueError(f"source checksum mismatch for {role}")
    return {"role": role, "source_path": str(source.resolve()), "size_bytes": size, "sha256": checksum}


def source_records(config: dict) -> list[dict]:
    manifest_path = Path(config["source_manifest"])
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("status") != "PASS":
        raise ValueError("study manifest is not PASS")
    records = [record("study_manifest", manifest_path)]
    for role in config["study_roles"]:
        value = manifest["outputs"][role]
        records.append(record(role, Path(value["path"]), value["size_bytes"], value["sha256"]))
    for role, value in config["additional_files"].items():
        records.append(record(role, Path(value["path"]), value.get("size_bytes"), value.get("sha256")))
    return records


def filesystem_record(path: Path) -> str:
    output = subprocess.check_output(
        ["findmnt", "-T", str(path), "-n", "-o", "SOURCE,FSTYPE"], text=True
    ).strip()
    source, filesystem = output.split(maxsplit=1)
    device = Path(source).name
    rotational = subprocess.check_output(["lsblk", "-dn", "-o", "ROTA", f"/dev/{device}"], text=True).strip()
    kind = "rotating_hdd" if rotational == "1" else "ssd"
    return f"{source} {filesystem} {kind}"


def validate_ready(root: Path, records: list[dict], marker_name: str) -> dict | None:
    marker = root / marker_name
    if not marker.is_file():
        return None
    value = json.loads(marker.read_text())
    if value.get("status") != "READY" or len(value.get("files", [])) != len(records):
        return None
    expected = {item["role"]: item for item in records}
    for item in value["files"]:
        source = expected.get(item["role"])
        mirror = Path(item["mirror_path"])
        if source is None or not mirror.is_file() or mirror.stat().st_size != source["size_bytes"]:
            return None
        if item["sha256"] != source["sha256"] or sha256_file(mirror) != source["sha256"]:
            return None
    return value


def prepare(config_path: Path) -> dict:
    config = yaml.safe_load(config_path.read_text())
    records = source_records(config)
    root = Path(config["mirror_root"])
    existing = validate_ready(root, records, config["activation"]["marker"])
    if existing is not None:
        existing["reuse"] = True
        return existing
    if root.exists():
        raise ValueError(f"incomplete or invalid mirror exists: {root}")
    root.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{root.name}.stage-", dir=root.parent))
    started = time.monotonic()
    try:
        mirrored = []
        for item in records:
            directory_role = "official_grid" if item["role"].startswith("official_grid_") else item["role"]
            destination = stage / "files" / directory_role / Path(item["source_path"]).name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item["source_path"], destination)
            copied = record(item["role"], destination, item["size_bytes"], item["sha256"])
            mirrored.append({**item, "mirror_path": str((root / destination.relative_to(stage)).resolve()),
                             "mirror_size_bytes": copied["size_bytes"], "mirror_sha256": copied["sha256"]})
        value = {
            "schema_version": "1.0.0", "status": "READY", "scientific_identity": "excluded_execution_only",
            "source_filesystem": filesystem_record(Path(records[0]["source_path"])),
            "mirror_filesystem": filesystem_record(root.parent),
            "total_bytes": sum(item["size_bytes"] for item in mirrored),
            "copy_elapsed_seconds": time.monotonic() - started, "source_mutations": 0,
            "files": mirrored,
        }
        marker = stage / config["activation"]["marker"]
        marker.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
        with marker.open("rb") as stream:
            os.fsync(stream.fileno())
        os.rename(stage, root)
        result = validate_ready(root, records, config["activation"]["marker"])
        if result is None:
            raise ValueError("activated mirror failed validation")
        result["reuse"] = False
        return result
    except Exception as error:
        # Preserve incomplete copies as recovery evidence. Only the atomically
        # activated root can carry READY.json and become readable by targets.
        if stage.exists():
            (stage / "FAILED.json").write_text(
                json.dumps(
                    {"status": "FAILED", "error": str(error), "source_mutations": 0},
                    ensure_ascii=False,
                    sort_keys=True,
                    indent=2,
                )
                + "\n"
            )
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(args.config), ensure_ascii=False, sort_keys=True))
