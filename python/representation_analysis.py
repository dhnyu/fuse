"""S11 bounded numerical primitives; dissertation 5.3/5.4, approved D1-D7.

No model loading, inference, training, targets execution, or production publisher.
Average Spearman ties and lexical retrieval ties deliberately have different roles.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.spatial.distance import cdist
from scipy.stats import rankdata
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]


def file_sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_frozen_contract(root=ROOT, verify_dissertation=True):
    """Reject even schema-valid edits unless the explicit frozen lock also matches."""
    import jsonschema
    root = Path(root)
    path = root / "config/s11_representation_analysis.json"
    lock = json.loads((root / "config/s11_representation_analysis.lock.json").read_text())
    if file_sha256(path) != lock["contract_sha256"]:
        raise ValueError("S11_FROZEN_CONTRACT_HASH")
    contract = json.loads(path.read_text())
    schema = json.loads((root / "config/schemas/s11_representation_analysis.schema.json").read_text())
    jsonschema.validate(contract, schema)
    if verify_dissertation:
        for name, checksum in lock["dissertation_sources"].items():
            if file_sha256(Path(lock["dissertation_root"]) / "template" / name) != checksum:
                raise ValueError("S11_DISSERTATION_CHANGED:" + name)
    return contract, lock


def cosine_block(vectors, positions):
    """eq:spatial-scene-similarity; C-level batched GEMV, no Python query loop.

    Broadcast the matrix (do not tile/copy it). Exact legacy parity is a runtime
    acceptance gate, not a portable BLAS guarantee. No renormalization/clipping.
    """
    x = np.asarray(vectors)
    q = np.asarray(positions, dtype=np.int64)
    if x.dtype != np.float32 or x.ndim != 2 or not x.flags.c_contiguous:
        raise ValueError("S11_FLOAT32_CONTIGUOUS_MATRIX")
    if q.ndim != 1 or not 0 < len(q) <= 32 or len(set(q)) != len(q):
        raise ValueError("S11_BOUNDED_QUERY_BLOCK")
    if np.any(q < 0) or np.any(q >= len(x)) or not np.isfinite(x).all():
        raise ValueError("S11_INVALID_EMBEDDING_OR_QUERY")
    with threadpool_limits(limits=1, user_api="blas"):
        return np.matmul(x[None, :, :], x[q, :, None])[..., 0]


def eligibility(centers, positions):
    """D7 / 5.3: float64 center differences; exactly 2000 m remains eligible."""
    c = np.asarray(centers, dtype=np.float64)
    q = np.asarray(positions, dtype=np.int64)
    if c.ndim != 2 or c.shape[1] != 2 or not np.isfinite(c).all():
        raise ValueError("S11_CENTERS")
    distance = np.linalg.norm(c[None, :, :] - c[q, None, :], axis=2)
    standard = np.arange(len(c))[None, :] != q[:, None]
    return distance, {"standard": standard, "nonlocal": standard & (distance >= 2000.0)}


def band_positions(counts):
    """D7: 1-based legacy bands, including lower-centered middle rounding."""
    m = np.asarray(counts, dtype=np.int64)
    start = (m - 10) // 2 + 1
    bands = {
        "rank1": np.ones((len(m), 1), dtype=np.int64),
        "upper": np.broadcast_to(np.arange(2, 12), (len(m), 10)),
        "middle": start[:, None] + np.arange(10),
        "lower": m[:, None] - 9 + np.arange(10),
    }
    flat = np.concatenate(list(bands.values()), axis=1)
    if np.any(m < 31) or np.any(np.diff(np.sort(flat, axis=1), axis=1) == 0):
        raise ValueError("S11_INSUFFICIENT_OR_OVERLAPPING_BANDS")
    return bands


def band_indices(scores, eligible):
    """Only BxN workspace; sorting is vectorized, the tiny loop is over 31 slots."""
    s = np.asarray(scores)
    mask = np.asarray(eligible, dtype=bool)
    if s.shape != mask.shape or not np.isfinite(s).all():
        raise ValueError("S11_SCORE_MASK")
    order = np.argsort(-s, kind="stable", axis=1)
    ordered_mask = np.take_along_axis(mask, order, axis=1)
    ranks = np.cumsum(ordered_mask, axis=1)
    positions = band_positions(mask.sum(axis=1))
    result = {}
    for band, slots in positions.items():
        columns = []
        for slot in slots.T:
            offset = (ordered_mask & (ranks == slot[:, None])).argmax(axis=1)
            columns.append(np.take_along_axis(order, offset[:, None], axis=1)[:, 0])
        result[band] = np.stack(columns, axis=1)
    return result


def descriptor_differences(values, positions, valid, composition_tolerance=1e-12):
    """D4/5.4.2: direct Euclidean avoids cancellation and BxNxK temporaries.

    Invalid rows may have zero-filled transport payloads; the validity mask is
    authoritative. They are never treated as real zero-valued descriptors.
    """
    v = np.asarray(values, dtype=np.float64)
    ok = np.asarray(valid, dtype=bool)
    q = np.asarray(positions, dtype=np.int64)
    if v.ndim not in (1, 2) or ok.shape != (len(v),) or not np.isfinite(v[ok]).all():
        raise ValueError("S11_DESCRIPTOR_SHAPE_OR_VALIDITY")
    if composition_tolerance not in (1e-12, 1e-6):
        raise ValueError("S11_UNAPPROVED_COMPOSITION_TOLERANCE")
    if v.ndim == 2 and (np.any(v[ok] < 0) or not np.allclose(v[ok].sum(axis=1), 1, atol=composition_tolerance, rtol=0)):
        raise ValueError("S11_INVALID_COMPOSITION")
    clean = np.where(ok.reshape((-1,) + (1,) * (v.ndim - 1)), v, 0)
    if v.ndim == 1:
        differences = np.abs(clean[q, None] - clean[None, :])
    else:
        differences = cdist(clean[q], clean, metric="euclidean")
    return differences, ok[q, None] & ok[None, :]


def spearman_rows(scores, differences, eligible, pair_valid):
    """D4: ranks are recomputed on EACH mode/descriptor valid candidate subset."""
    s, d = np.asarray(scores), np.asarray(differences)
    eligible, pair_valid = np.asarray(eligible, bool), np.asarray(pair_valid, bool)
    if not (s.shape == d.shape == eligible.shape == pair_valid.shape) or s.ndim != 2:
        raise ValueError("S11_ALIGNMENT_SHAPE")
    mask = eligible & pair_valid
    if not np.isfinite(s).all() or not np.isfinite(d[mask]).all():
        raise ValueError("S11_ALIGNMENT_NONFINITE")
    n = mask.sum(axis=1)
    # NaN is only an internal masked-array sentinel, never a serialized result.
    rs = rankdata(np.where(mask, s, np.nan), axis=1, method="average", nan_policy="omit")
    rd = rankdata(np.where(mask, d, np.nan), axis=1, method="average", nan_policy="omit")
    mean = (n + 1)[:, None] / 2
    cs = np.where(mask, rs - mean, 0)
    cd = np.where(mask, rd - mean, 0)
    vs, vd = np.sum(cs * cs, axis=1), np.sum(cd * cd, axis=1)
    denominator = np.sqrt(vs * vd)
    rho = np.divide(np.sum(cs * cd, axis=1), denominator,
                    out=np.zeros(len(n), dtype=np.float64), where=denominator > 0)
    records = []
    # Serialization only: all ranking/difference/correlation arithmetic is batched.
    for i in range(len(n)):
        reason = ("fewer_than_two_valid_pairs" if n[i] < 2 else
                  "constant_similarity" if vs[i] == 0 else
                  "constant_difference" if vd[i] == 0 else None)
        total = int(eligible[i].sum())
        records.append({"rho": None if reason else float(rho[i]), "null_reason": reason,
                        "total_count": total, "valid_count": int(n[i]),
                        "invalid_count": total - int(n[i])})
    return records


def summarize_bands(differences, pair_valid, indices):
    """D7: never refill a missing descriptor slot with a neighboring rank."""
    result = {}
    for band, index in indices.items():
        d = np.take_along_axis(differences, index, axis=1)
        valid = np.take_along_axis(pair_valid, index, axis=1)
        if not np.isfinite(d[valid]).all():
            raise ValueError("S11_BAND_NONFINITE")
        n = valid.sum(axis=1)
        means = np.divide(np.where(valid, d, 0).sum(axis=1), n,
                          out=np.zeros(len(n)), where=n > 0)
        result[band] = [{"mean_difference": float(mean) if count else None,
                         "null_reason": None if count else "no_valid_band_pairs",
                         "total_count": index.shape[1], "valid_count": int(count),
                         "invalid_count": index.shape[1] - int(count)}
                        for mean, count in zip(means, n, strict=True)]
    return result


def query_summary(values):
    """D7: equal query weight, NumPy linear == R quantile type 7."""
    v = np.array([x for x in values if x is not None], dtype=np.float64)
    if not np.isfinite(v).all():
        raise ValueError("S11_SUMMARY_NONFINITE")
    q1, median, q3 = np.quantile(v, [0.25, 0.5, 0.75], method="linear") if len(v) else (None,) * 3
    return {"q1": q1, "median": median, "q3": q3, "iqr": q3-q1 if len(v) else None,
            "total_count": len(values), "valid_count": len(v), "invalid_count": len(values)-len(v),
            "null_reason": None if len(v) else "no_valid_queries"}


def select_illustrations(coordinates, scene_ids, seed=20260904):
    """D6: fixed quantile cells, minimum hash, no scene-quality filtering."""
    xy = np.asarray(coordinates, dtype=np.float64)
    if xy.shape != (len(scene_ids), 2) or len(set(scene_ids)) != len(scene_ids) or not np.isfinite(xy).all() or not len(xy):
        raise ValueError("S11_ILLUSTRATION_INPUT")
    cuts = np.quantile(xy, [1/3, 2/3], axis=0, method="linear")
    cells = np.stack([np.searchsorted(cuts[:, axis], xy[:, axis], side="right") for axis in (0, 1)], axis=1)
    records = []
    for i, scene in enumerate(scene_ids):
        digest = hashlib.sha256((str(seed) + scene).encode("utf-8")).hexdigest()
        records.append({"scene_id": scene, "cell_x": int(cells[i, 0]), "cell_y": int(cells[i, 1]), "selection_sha256": digest})
    selected = {}
    for row in sorted(records, key=lambda r: (r["selection_sha256"], r["scene_id"])):
        selected.setdefault((row["cell_x"], row["cell_y"]), row)
    return {"cutpoints": cuts.tolist(), "scenes": [selected[k] for k in sorted(selected)]}
