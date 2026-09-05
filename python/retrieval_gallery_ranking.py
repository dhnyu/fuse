"""Exact query-only supplementary ranking, without held-out metric computation."""
from __future__ import annotations

import numpy as np


def rank_gallery(scene_ids, centers, embeddings, query_ids, exclusion_m=2000.0, *, already_normalized=False):
    ids = np.asarray(scene_ids, dtype=str)
    xy = np.asarray(centers, dtype=np.float64)
    values = np.asarray(embeddings)
    if len(set(ids)) != len(ids) or xy.shape != (len(ids), 2):
        raise ValueError("Gallery identity/center shape mismatch")
    if values.dtype != np.float32 or values.shape != (len(ids), 128):
        raise ValueError("Gallery requires float32 N x 128 embeddings")
    if not np.isfinite(values).all() or not np.isfinite(xy).all():
        raise ValueError("Nonfinite gallery input")
    norm = np.linalg.norm(values, axis=1, keepdims=True)
    if np.any(norm == 0):
        raise ValueError("Zero embedding norm")
    if already_normalized and not np.allclose(norm, 1, rtol=0, atol=1e-6):
        raise ValueError("Accepted normalized embedding contract failed")
    # Frozen P10 rows already underwent torch F.normalize. Do not normalize twice.
    normalized = values if already_normalized else values / norm
    lookup = {scene_id: i for i, scene_id in enumerate(ids)}
    positions = np.asarray([lookup[q] for q in query_ids])
    if len(set(query_ids)) != len(query_ids):
        raise ValueError("Duplicate query identity")
    # Both matrices are Q x N, never N x N.
    scores = normalized[positions] @ normalized.T
    distances = np.sqrt(np.sum((xy[positions, None, :] - xy[None, :, :]) ** 2, axis=2))
    rankings = {}
    for qi, query in enumerate(query_ids):
        rankings[query] = {}
        for setting in ("standard", "nonlocal"):
            mask = ids != query
            if setting == "nonlocal":
                mask &= distances[qi] >= exclusion_m
            eligible = np.flatnonzero(mask)
            order = eligible[np.lexsort((ids[eligible], -scores[qi, eligible]))]
            rankings[query][setting] = {
                "indices": order, "similarities": scores[qi, order], "distances": distances[qi, order]}
    return rankings


def stability(old, new, scene_ids, canonical_ids):
    ids = np.asarray(scene_ids)
    old_ids = ids[old["indices"]]
    new_ids = ids[new["indices"]]
    positions = {scene_id: i + 1 for i, scene_id in enumerate(new_ids)}
    if not len(old_ids) or not len(new_ids):
        raise ValueError("Empty ranking cannot support paired diagnostics")
    result = {"old_best_new_rank": positions[old_ids[0]],
              "new_best_scene_id": str(new_ids[0]),
              "new_best_source": "canonical" if new_ids[0] in canonical_ids else "supplemental",
              "new_best_similarity": float(new["similarities"][0]),
              "new_best_distance_m": float(new["distances"][0]),
              "similarity_quantiles": dict(zip(("q0", "q25", "q50", "q75", "q100"),
                  np.quantile(new["similarities"], [0, .25, .5, .75, 1]).tolist()))}
    for k in (10, 100):
        size = min(k, len(old_ids), len(new_ids))
        overlap = len(set(old_ids[:size]) & set(new_ids[:size]))
        result[f"top{k}_overlap_count"] = overlap
        result[f"top{k}_overlap_fraction"] = overlap / size
        result[f"old_best_in_top{k}"] = positions[old_ids[0]] <= k
    result["rank1_rank10_similarity_gap"] = (
        float(new["similarities"][0] - new["similarities"][9]) if len(new_ids) >= 10 else None)
    return result
