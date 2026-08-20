#!/usr/bin/env python3
"""Write fixed-grid Methodology 3.5.2 observations as scene-chunked Zarr v2."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import numcodecs
import zarr
from numcodecs import Blosc


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_shape(value: str) -> tuple[int, ...]:
    return tuple(int(item) for item in value.split(","))


def create_store(args: argparse.Namespace) -> dict:
    output = Path(args.output)
    output.mkdir(parents=False, exist_ok=False)
    group = zarr.open_group(output, mode="w", zarr_format=2)
    compressor = Blosc(cname="zstd", clevel=args.compression_level, shuffle=Blosc.BITSHUFFLE)
    arrays = []
    for definition in args.array:
        name, raw_path, dtype, shape_text, fill_text = definition.split("::", 4)
        shape = parse_shape(shape_text)
        data = np.fromfile(raw_path, dtype=np.dtype(dtype)).reshape(shape)
        fill_value = np.array(fill_text, dtype=np.dtype(dtype)).item()
        chunks = (1, *shape[1:])
        array = group.create_array(
            name,
            data=data,
            chunks=chunks,
            compressor=compressor,
            fill_value=fill_value,
            overwrite=False,
        )
        arrays.append(
            {
                "name": name,
                "shape": list(array.shape),
                "dtype": str(array.dtype),
                "chunks": list(array.chunks),
                "fill_value": fill_value,
                "data_sha256": hashlib.sha256(data.tobytes(order="C")).hexdigest(),
            }
        )
    attributes = json.loads(Path(args.attributes).read_text(encoding="utf-8"))
    group.attrs.update(attributes)
    zarr.consolidate_metadata(output)
    result = inspect_store(output)
    result["arrays"] = arrays
    return result


def inspect_store(path: Path) -> dict:
    group = zarr.open_group(path, mode="r")
    arrays = []
    for name in sorted(group.array_keys()):
        array = group[name]
        values = array[:]
        arrays.append(
            {
                "name": name,
                "shape": list(array.shape),
                "dtype": str(array.dtype),
                "chunks": list(array.chunks),
                "fill_value": array.fill_value,
                "data_sha256": hashlib.sha256(values.tobytes(order="C")).hexdigest(),
            }
        )
    members = []
    for member in sorted(item for item in path.rglob("*") if item.is_file()):
        members.append(
            {
                "path": str(member.relative_to(path)),
                "size_bytes": member.stat().st_size,
                "sha256": sha256(member),
            }
        )
    return {
        "writer": "python_zarr_numcodecs",
        "zarr_python_version": zarr.__version__,
        "numcodecs_version": numcodecs.__version__,
        "numpy_version": np.__version__,
        "zarr_format": 2,
        "consolidated_metadata": (path / ".zmetadata").exists(),
        "attributes": dict(group.attrs),
        "arrays": arrays,
        "members": members,
        "size_bytes": sum(item["size_bytes"] for item in members),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    write = subparsers.add_parser("write")
    write.add_argument("--output", required=True)
    write.add_argument("--attributes", required=True)
    write.add_argument("--array", action="append", required=True)
    write.add_argument("--compression-level", type=int, default=5)
    inspect = subparsers.add_parser("inspect")
    inspect.add_argument("--input", required=True)
    args = parser.parse_args()
    result = create_store(args) if args.command == "write" else inspect_store(Path(args.input))
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))


if __name__ == "__main__":
    main()
