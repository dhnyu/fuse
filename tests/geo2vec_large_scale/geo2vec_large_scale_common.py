#!/usr/bin/env python3
"""Shared helpers for the large-scale Geo2Vec prototype."""

from __future__ import annotations

import hashlib
import json
import os
import random
import resource
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


ROOT = Path("/members/dhnyu/fuse")
PROTOTYPE_DIR = ROOT / "tests" / "geo2vec_large_scale"
OUTPUT_ROOT = Path("/members/dhnyu/fusedata/geo2vec_large_scale")
ID_MAP_DIR = OUTPUT_ROOT / "id_maps"
SAMPLE_CACHE_DIR = OUTPUT_ROOT / "sample_caches"
TRAINING_RUN_DIR = OUTPUT_ROOT / "training_runs"
EMBEDDING_DIR = OUTPUT_ROOT / "embeddings"
REPORT_DIR = OUTPUT_ROOT / "reports"
METADATA_DIR = OUTPUT_ROOT / "metadata"
LOG_DIR = OUTPUT_ROOT / "logs"
OUTPUT_DIR = OUTPUT_ROOT
GEOMETRY_PATH = Path("/members/dhnyu/fusedatalarge/processed/korea_buildings_vworld.gpkg")
GEOMETRY_LAYER = "buildings"
ATTRIBUTES_PATH = Path("/members/dhnyu/fusedatalarge/processed/korea_buildings_vworld_attributes.parquet")
EXTERNAL_REPO = Path("/members/dhnyu/fuse_external/GeoNeuralRepresentation")
BASE_SEED = 20260608
MAX_DEFAULT_PROTOTYPE_LIMIT = 100_000


def ensure_output_dir(path: Path = OUTPUT_DIR) -> None:
    path.mkdir(parents=True, exist_ok=True)


def ensure_standard_dirs() -> None:
    for path in [OUTPUT_ROOT, ID_MAP_DIR, SAMPLE_CACHE_DIR, TRAINING_RUN_DIR, EMBEDDING_DIR, REPORT_DIR, METADATA_DIR, LOG_DIR]:
        path.mkdir(parents=True, exist_ok=True)


def suffix_for_limit(limit: int | None) -> str:
    if limit is None:
        return "full"
    if limit % 1000 == 0:
        return f"{limit // 1000}k"
    return str(limit)


def refuse_unsafe_limit(limit: int | None, force: bool, max_limit: int = MAX_DEFAULT_PROTOTYPE_LIMIT) -> None:
    if limit is None and not force:
        raise SystemExit("--limit is required for prototype runs unless --force-large is supplied.")
    if limit is not None and limit > max_limit and not force:
        raise SystemExit(f"Refusing limit {limit:,}; use --force-large only after validating smaller stages.")


def stable_hash_int(*parts: Any, bits: int = 64) -> int:
    text = "|".join(str(part) for part in parts)
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return int.from_bytes(digest[: bits // 8], "little", signed=False)


def sha256_file(path: Path, chunk_size: int = 16 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def dataframe_checksum(df: pd.DataFrame, columns: Iterable[str]) -> str:
    h = hashlib.sha256()
    for row in df.loc[:, list(columns)].itertuples(index=False, name=None):
        h.update(("|".join("" if x is None else str(x) for x in row) + "\n").encode("utf-8"))
    return h.hexdigest()


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    ensure_output_dir(path.parent)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    os.replace(tmp, path)


def write_parquet_atomic(table_or_df: pa.Table | pd.DataFrame, path: Path, compression: str = "zstd") -> None:
    ensure_output_dir(path.parent)
    tmp = path.with_suffix(path.suffix + ".tmp")
    table = pa.Table.from_pandas(table_or_df, preserve_index=False) if isinstance(table_or_df, pd.DataFrame) else table_or_df
    pq.write_table(table, tmp, compression=compression)
    os.replace(tmp, path)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def current_rss_mb() -> float | None:
    try:
        import psutil

        return psutil.Process(os.getpid()).memory_info().rss / (1024 ** 2)
    except Exception:
        return None


def maxrss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def gpu_memory_mb() -> dict[str, float | None]:
    try:
        import torch

        if not torch.cuda.is_available():
            return {"gpu_allocated_mb": None, "gpu_reserved_mb": None}
        return {
            "gpu_allocated_mb": torch.cuda.memory_allocated() / (1024 ** 2),
            "gpu_reserved_mb": torch.cuda.memory_reserved() / (1024 ** 2),
        }
    except Exception:
        return {"gpu_allocated_mb": None, "gpu_reserved_mb": None}


@contextmanager
def timer() -> Iterable[dict[str, float]]:
    start = time.time()
    box: dict[str, float] = {"start": start, "elapsed_seconds": 0.0}
    try:
        yield box
    finally:
        box["elapsed_seconds"] = time.time() - start


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    ensure_output_dir(path.parent)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, sort_keys=True, default=str) + "\n")


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    try:
        import torch

        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
    except Exception:
        pass


def latest_checkpoint(run_dir: Path) -> Path | None:
    candidates = sorted(run_dir.glob("checkpoint_step_*.pt"))
    return candidates[-1] if candidates else None


def path_size_mb(path: Path) -> float:
    if path.is_file():
        return path.stat().st_size / (1024 ** 2)
    total = 0
    for p in path.rglob("*"):
        if p.is_file():
            total += p.stat().st_size
    return total / (1024 ** 2)
