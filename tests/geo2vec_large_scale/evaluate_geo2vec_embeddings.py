#!/usr/bin/env python3
"""Evaluate shape, location, and full Geo2Vec embeddings with proxy labels."""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pyogrio
from sklearn.decomposition import PCA
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.neighbors import NearestNeighbors
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from geo2vec_large_scale_common import current_rss_mb, maxrss_mb, path_size_mb, seed_everything, write_json_atomic


TARGETS = [
    "area",
    "perimeter",
    "compactness",
    "bbox_aspect_ratio",
    "edge_count",
    "vertex_count",
    "centroid_x",
    "centroid_y",
]
SHAPE_PROXY_COLUMNS = ["area", "perimeter", "compactness", "bbox_aspect_ratio", "edge_count", "vertex_count"]
LOCATION_PROXY_COLUMNS = ["centroid_x", "centroid_y"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shape-embedding-dir", type=Path, required=True)
    parser.add_argument("--location-embedding-dir", type=Path, required=True)
    parser.add_argument("--full-embedding-dir", type=Path, required=True)
    parser.add_argument("--geometry", type=Path, required=True)
    parser.add_argument("--layer", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260610)
    parser.add_argument("--test-size", type=float, default=0.25)
    parser.add_argument("--rf-trees", type=int, default=200)
    parser.add_argument("--retrieval-sample", type=int, default=25)
    parser.add_argument("--max-umap-rows", type=int, default=10000)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def read_embedding_dir(path: Path) -> pd.DataFrame:
    parts_path = path / "embedding_export_parts.parquet"
    if not parts_path.exists():
        raise RuntimeError(f"Missing embedding parts manifest: {parts_path}")
    parts = pd.read_parquet(parts_path).sort_values("part_index")
    frames = [pd.read_parquet(p) for p in parts["path"]]
    if not frames:
        raise RuntimeError(f"No embedding parts found under {path}")
    df = pd.concat(frames, ignore_index=True)
    if not df["building_id"].is_unique:
        raise RuntimeError(f"Embedding directory has duplicate building_id values: {path}")
    return df


def embedding_columns(df: pd.DataFrame, prefix: str | None = None) -> list[str]:
    cols = [c for c in df.columns if c.startswith("geo2vec_")]
    if prefix is not None:
        cols = [c for c in cols if c.startswith(prefix)]
    if not cols:
        raise RuntimeError(f"No embedding columns found for prefix={prefix!r}")
    return sorted(cols)


def ring_vertex_count(geom: Any) -> int:
    if geom is None or geom.is_empty:
        return 0
    if geom.geom_type == "Polygon":
        rings = [geom.exterior, *geom.interiors]
        return int(sum(max(0, len(r.coords) - 1) for r in rings))
    if geom.geom_type == "MultiPolygon":
        return int(sum(ring_vertex_count(g) for g in geom.geoms))
    if geom.geom_type == "GeometryCollection":
        return int(sum(ring_vertex_count(g) for g in geom.geoms))
    return 0


def edge_count(geom: Any) -> int:
    return ring_vertex_count(geom)


def build_proxy_labels(geometry: Path, layer: str, building_ids: pd.Series) -> pd.DataFrame:
    gdf = pyogrio.read_dataframe(geometry, layer=layer, columns=["building_id"])
    gdf["building_id"] = gdf["building_id"].astype(str)
    wanted = pd.DataFrame({"building_id": building_ids.astype(str)})
    gdf = wanted.merge(gdf, on="building_id", how="left", validate="one_to_one")
    if gdf["geometry"].isna().any():
        raise RuntimeError("Some embedding building_ids were not found in the geometry layer.")
    geom = gdf["geometry"]
    area = pd.Series([float(g.area) for g in geom], dtype="float64")
    perimeter = pd.Series([float(g.length) for g in geom], dtype="float64")
    compactness = np.where(perimeter > 0, 4.0 * math.pi * area / np.square(perimeter), np.nan)
    bounds = pd.DataFrame([g.bounds for g in geom], columns=["minx", "miny", "maxx", "maxy"])
    bbox_w = (bounds["maxx"] - bounds["minx"]).astype(float)
    bbox_h = (bounds["maxy"] - bounds["miny"]).astype(float)
    short = np.minimum(bbox_w, bbox_h)
    long = np.maximum(bbox_w, bbox_h)
    centroid_x = [float(g.centroid.x) for g in geom]
    centroid_y = [float(g.centroid.y) for g in geom]
    labels = pd.DataFrame(
        {
            "building_id": gdf["building_id"],
            "area": area,
            "perimeter": perimeter,
            "compactness": compactness,
            "bbox_aspect_ratio": np.where(short > 0, long / short, np.nan),
            "edge_count": [edge_count(g) for g in geom],
            "vertex_count": [ring_vertex_count(g) for g in geom],
            "centroid_x": centroid_x,
            "centroid_y": centroid_y,
        }
    )
    labels = labels.replace([np.inf, -np.inf], np.nan)
    if labels[TARGETS].isna().any().any():
        labels = labels.dropna(subset=TARGETS).reset_index(drop=True)
    return labels


def regression_metrics(
    name: str,
    X: np.ndarray,
    labels: pd.DataFrame,
    seed: int,
    test_size: float,
    rf_trees: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    train_idx, test_idx = train_test_split(np.arange(len(labels)), test_size=test_size, random_state=seed)
    models = {
        "linear_regression": make_pipeline(StandardScaler(), LinearRegression()),
        "ridge_regression": make_pipeline(StandardScaler(), Ridge(alpha=1.0)),
        "random_forest": RandomForestRegressor(
            n_estimators=rf_trees,
            max_depth=12,
            min_samples_leaf=3,
            random_state=seed,
            n_jobs=-1,
        ),
    }
    for target in TARGETS:
        y = labels[target].to_numpy(dtype=np.float64)
        for model_name, model in models.items():
            model.fit(X[train_idx], y[train_idx])
            pred = model.predict(X[test_idx])
            rows.append(
                {
                    "embedding": name,
                    "target": target,
                    "model": model_name,
                    "r2": float(r2_score(y[test_idx], pred)),
                    "mae": float(mean_absolute_error(y[test_idx], pred)),
                    "train_rows": int(len(train_idx)),
                    "test_rows": int(len(test_idx)),
                }
            )
    return rows


def pca_outputs(name: str, X: np.ndarray, ids: pd.Series, labels: pd.DataFrame, output_dir: Path) -> dict[str, Any]:
    pca = PCA(n_components=2, random_state=0)
    coords = pca.fit_transform(StandardScaler().fit_transform(X))
    out = pd.DataFrame(
        {
            "building_id": ids.to_numpy(),
            "pc1": coords[:, 0],
            "pc2": coords[:, 1],
            "area": labels["area"].to_numpy(),
            "centroid_x": labels["centroid_x"].to_numpy(),
            "centroid_y": labels["centroid_y"].to_numpy(),
        }
    )
    parquet_path = output_dir / f"{name}_pca_coordinates.parquet"
    pq.write_table(pa.Table.from_pandas(out, preserve_index=False), parquet_path, compression="zstd")
    fig_path = output_dir / f"{name}_pca_area.png"
    plt.figure(figsize=(7, 5))
    sc = plt.scatter(out["pc1"], out["pc2"], c=np.log1p(out["area"]), s=3, alpha=0.55, cmap="viridis")
    plt.colorbar(sc, label="log1p(area)")
    plt.xlabel("PC1")
    plt.ylabel("PC2")
    plt.tight_layout()
    plt.savefig(fig_path, dpi=180)
    plt.close()
    return {
        "coordinates": str(parquet_path),
        "figure": str(fig_path),
        "explained_variance_ratio": [float(x) for x in pca.explained_variance_ratio_],
    }


def umap_outputs(name: str, X: np.ndarray, ids: pd.Series, labels: pd.DataFrame, output_dir: Path, seed: int, max_rows: int) -> dict[str, Any]:
    try:
        import umap  # type: ignore
    except Exception as exc:
        return {
            "available": False,
            "optional": True,
            "error": f"{type(exc).__name__}: {exc}",
            "note": "Python UMAP is optional; R evaluation with uwot is the preferred path when available.",
        }
    if len(X) > max_rows:
        rng = np.random.default_rng(seed)
        idx = np.sort(rng.choice(len(X), size=max_rows, replace=False))
    else:
        idx = np.arange(len(X))
    reducer = umap.UMAP(n_components=2, random_state=seed, n_neighbors=30, min_dist=0.1)
    coords = reducer.fit_transform(StandardScaler().fit_transform(X[idx]))
    out = pd.DataFrame(
        {
            "building_id": ids.iloc[idx].to_numpy(),
            "umap1": coords[:, 0],
            "umap2": coords[:, 1],
            "area": labels["area"].iloc[idx].to_numpy(),
            "centroid_x": labels["centroid_x"].iloc[idx].to_numpy(),
            "centroid_y": labels["centroid_y"].iloc[idx].to_numpy(),
        }
    )
    parquet_path = output_dir / f"{name}_umap_coordinates.parquet"
    pq.write_table(pa.Table.from_pandas(out, preserve_index=False), parquet_path, compression="zstd")
    fig_path = output_dir / f"{name}_umap_area.png"
    plt.figure(figsize=(7, 5))
    sc = plt.scatter(out["umap1"], out["umap2"], c=np.log1p(out["area"]), s=3, alpha=0.55, cmap="viridis")
    plt.colorbar(sc, label="log1p(area)")
    plt.xlabel("UMAP1")
    plt.ylabel("UMAP2")
    plt.tight_layout()
    plt.savefig(fig_path, dpi=180)
    plt.close()
    return {"available": True, "coordinates": str(parquet_path), "figure": str(fig_path), "row_count": int(len(out))}


def retrieval_outputs(name: str, X: np.ndarray, ids: pd.Series, labels: pd.DataFrame, output_dir: Path, seed: int, sample_n: int) -> dict[str, Any]:
    sample_n = min(sample_n, len(X))
    rng = np.random.default_rng(seed)
    query_idx = np.sort(rng.choice(len(X), size=sample_n, replace=False))
    Xs = StandardScaler().fit_transform(X)
    nn = NearestNeighbors(n_neighbors=6, metric="euclidean")
    nn.fit(Xs)
    dist, ind = nn.kneighbors(Xs[query_idx])
    rows = []
    label_lookup = labels.set_index("building_id")
    for qpos, qidx in enumerate(query_idx):
        qid = ids.iloc[qidx]
        qlab = label_lookup.loc[qid]
        for rank, (neighbor_idx, d) in enumerate(zip(ind[qpos], dist[qpos])):
            nid = ids.iloc[int(neighbor_idx)]
            nlab = label_lookup.loc[nid]
            rows.append(
                {
                    "embedding": name,
                    "query_building_id": qid,
                    "neighbor_rank": int(rank),
                    "neighbor_building_id": nid,
                    "embedding_distance": float(d),
                    "query_area": float(qlab["area"]),
                    "neighbor_area": float(nlab["area"]),
                    "abs_log_area_delta": float(abs(np.log1p(qlab["area"]) - np.log1p(nlab["area"]))),
                    "centroid_distance": float(
                        math.hypot(float(qlab["centroid_x"] - nlab["centroid_x"]), float(qlab["centroid_y"] - nlab["centroid_y"]))
                    ),
                }
            )
    out = pd.DataFrame(rows)
    parquet_path = output_dir / f"{name}_retrieval_neighbors.parquet"
    pq.write_table(pa.Table.from_pandas(out, preserve_index=False), parquet_path, compression="zstd")
    summary = (
        out.loc[out["neighbor_rank"] > 0]
        .groupby("embedding", as_index=False)
        .agg(mean_abs_log_area_delta=("abs_log_area_delta", "mean"), mean_centroid_distance=("centroid_distance", "mean"))
    )
    return {"neighbors": str(parquet_path), "summary": summary.to_dict(orient="records")[0]}


def main() -> None:
    args = parse_args()
    manifest_path = args.output_dir / "evaluation_manifest.json"
    if manifest_path.exists() and not args.overwrite:
        print(manifest_path.read_text())
        return
    args.output_dir.mkdir(parents=True, exist_ok=True)
    seed_everything(args.seed)
    start = time.time()

    shape = read_embedding_dir(args.shape_embedding_dir)
    location = read_embedding_dir(args.location_embedding_dir)
    full = read_embedding_dir(args.full_embedding_dir)
    base_ids = shape[["building_id", "geo2vec_internal_id"]].copy()
    for label, df in [("location", location), ("full", full)]:
        if not base_ids.equals(df[["building_id", "geo2vec_internal_id"]].reset_index(drop=True)):
            raise RuntimeError(f"{label} embeddings do not align with shape embeddings.")

    labels = build_proxy_labels(args.geometry, args.layer, base_ids["building_id"])
    merged_ids = base_ids.merge(labels[["building_id"]], on="building_id", how="inner")
    if len(merged_ids) != len(base_ids):
        keep = set(merged_ids["building_id"])
        shape = shape.loc[shape["building_id"].isin(keep)].reset_index(drop=True)
        location = location.loc[location["building_id"].isin(keep)].reset_index(drop=True)
        full = full.loc[full["building_id"].isin(keep)].reset_index(drop=True)
        labels = labels.loc[labels["building_id"].isin(keep)].reset_index(drop=True)

    sets = {
        "shape": (shape, embedding_columns(shape, "geo2vec_shp")),
        "location": (location, embedding_columns(location, "geo2vec_loc")),
        "full_geo2vec": (full, embedding_columns(full)),
    }
    metrics: list[dict[str, Any]] = []
    pca: dict[str, Any] = {}
    umap_info: dict[str, Any] = {}
    retrieval: dict[str, Any] = {}
    dims: dict[str, int] = {}
    for name, (df, cols) in sets.items():
        dims[name] = len(cols)
        X = df[cols].to_numpy(dtype=np.float32)
        ids = df["building_id"].astype(str)
        metrics.extend(regression_metrics(name, X, labels, args.seed, args.test_size, args.rf_trees))
        pca[name] = pca_outputs(name, X, ids, labels, args.output_dir)
        umap_info[name] = umap_outputs(name, X, ids, labels, args.output_dir, args.seed, args.max_umap_rows)
        retrieval[name] = retrieval_outputs(name, X, ids, labels, args.output_dir, args.seed, args.retrieval_sample)

    metrics_df = pd.DataFrame(metrics)
    metrics_path = args.output_dir / "recoverability_metrics.parquet"
    pq.write_table(pa.Table.from_pandas(metrics_df, preserve_index=False), metrics_path, compression="zstd")
    labels_path = args.output_dir / "evaluation_proxy_labels.parquet"
    pq.write_table(pa.Table.from_pandas(labels, preserve_index=False), labels_path, compression="zstd")

    best_rows = (
        metrics_df.sort_values(["target", "model", "r2"], ascending=[True, True, False])
        .groupby(["target", "model"], as_index=False)
        .first()
    )
    summary_table_path = args.output_dir / "recoverability_best_by_target_model.parquet"
    pq.write_table(pa.Table.from_pandas(best_rows, preserve_index=False), summary_table_path, compression="zstd")

    manifest = {
        "script": Path(__file__).name,
        "complete": True,
        "shape_embedding_dir": str(args.shape_embedding_dir),
        "location_embedding_dir": str(args.location_embedding_dir),
        "full_embedding_dir": str(args.full_embedding_dir),
        "geometry": str(args.geometry),
        "layer": args.layer,
        "output_dir": str(args.output_dir),
        "row_count": int(len(labels)),
        "embedding_dimensions": dims,
        "targets": TARGETS,
        "shape_proxy_columns_evaluation_only": SHAPE_PROXY_COLUMNS,
        "location_proxy_columns_evaluation_only": LOCATION_PROXY_COLUMNS,
        "geometry_proxies_in_embedding": False,
        "preferred_evaluation_path": "R",
        "python_xgboost_umap_required": False,
        "optional_python_packages_skipped_are_pipeline_problems": False,
        "recoverability_metrics": str(metrics_path),
        "recoverability_best_by_target_model": str(summary_table_path),
        "evaluation_proxy_labels": str(labels_path),
        "pca": pca,
        "umap": umap_info,
        "retrieval": retrieval,
        "elapsed_seconds": float(time.time() - start),
        "cpu_rss_mb": current_rss_mb(),
        "peak_maxrss_mb": maxrss_mb(),
        "output_size_mb": path_size_mb(args.output_dir),
    }
    write_json_atomic(manifest_path, manifest)
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
