"""Dissertation spatial-scene retrieval: cosine order and center-distance exclusion.

S10 extends inspection to 30 queries; it does not evaluate or select models.
"""
import numpy as np
from retrieval_artifacts import require

OFAT = ("main", "ofat_d_64", "ofat_d_256", "ofat_K_aug_4", "ofat_K_aug_16",
        "ofat_augmentation_intensity_0.5", "ofat_augmentation_intensity_2.0",
        "ofat_ema_momentum_0.99", "ofat_peak_learning_rate_0.002",
        "ofat_peak_learning_rate_0.003", "ofat_peak_learning_rate_0.005")
COMPARISON = ("FM", "A1", "A2", "A3", "A4", "A5", "SSV", "DS",
              "B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B9")


def sample_queries(rows, seed, count=30, population=9000):
    ids = [r["scene_id"] for r in rows]
    require(len(ids) == population and len(set(ids)) == population and ids == sorted(ids), "GALLERY_POPULATION")
    require(0 < count <= population, "QUERY_COUNT")
    positions = np.random.Generator(np.random.PCG64(seed)).choice(population, count, replace=False)
    return [{**rows[int(i)], "query_index": j + 1, "sampling_seed": seed}
            for j, i in enumerate(positions)]


def check_embeddings(vectors, count):
    require(vectors.ndim == 2 and vectors.shape[0] == count and vectors.shape[1] > 0, "EMBEDDING_SHAPE")
    require(np.isfinite(vectors).all(), "EMBEDDING_NONFINITE")
    require(np.allclose(np.linalg.norm(vectors, axis=1), 1, rtol=0, atol=2e-6), "EMBEDDING_NOT_NORMALIZED")


def rank(vectors, gallery, queries, model, bindings, top_k=50):
    ids = [r["scene_id"] for r in gallery]
    require(ids == sorted(set(ids)), "GALLERY_IDENTITY")
    require(len({q["scene_id"] for q in queries}) == len(queries), "DUPLICATE_QUERY")
    check_embeddings(vectors, len(ids))
    centers = np.array([[r["center_x"], r["center_y"]] for r in gallery], dtype=np.float64)
    require(np.isfinite(centers).all(), "CENTER_NONFINITE")
    index = {s: i for i, s in enumerate(ids)}
    output = []
    for query in queries:
        require(query["scene_id"] in index, "QUERY_NOT_IN_GALLERY")
        qi = index[query["scene_id"]]
        scores = vectors @ vectors[qi]
        require(np.isfinite(scores).all(), "SCORE_NONFINITE")
        distances = np.linalg.norm(centers - centers[qi], axis=1)
        # Gallery is sorted by scene ID: stable sorting implements exact tie break.
        ordered = np.argsort(-scores, kind="stable")
        for mode in ("standard", "nonlocal"):
            candidates = [int(i) for i in ordered if i != qi and (mode == "standard" or distances[i] >= 2000.0)]
            require(len(candidates) >= top_k, "INSUFFICIENT_CANDIDATES")
            for position, i in enumerate(candidates[:top_k], 1):
                output.append({**bindings, "model_id": model["configuration_id"],
                    "model_group": model["group"], "checkpoint_id": model["checkpoint_id"],
                    "query_id": query["scene_id"], "retrieval_mode": mode, "rank": position,
                    "gallery_scene_id": ids[i], "similarity": float(scores[i]),
                    "geographic_distance_m": float(distances[i]),
                    "excluded_by_nonlocal": bool(distances[i] < 2000.0)})
    return output
