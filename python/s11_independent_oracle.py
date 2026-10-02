"""Independent acceptance arithmetic for frozen S11 Euclidean distances.

The coordinate order is scientific dictionary order. Candidate operations may
be batched, but accumulation across coordinates is sequential binary64. This
module deliberately imports neither the production distance helper nor SciPy.
"""
import numpy as np


def independent_difference(values, query):
    """Scalar absolute difference or ordered-binary64 Euclidean distance.

    Null transport values must be excluded by the caller's validity mask before
    ranks are computed. No renormalization, rounding, or epsilon ties.
    """
    values = np.asarray(values)
    if values.dtype != np.float64 or values.ndim not in (1, 2):
        raise ValueError("S11_ORACLE_FLOAT64_SHAPE")
    if not 0 <= query < len(values) or not np.isfinite(values).all():
        raise ValueError("S11_ORACLE_QUERY_FINITE")
    if values.ndim == 1:
        return np.abs(values - values[query])
    if values.shape[1] == 0:
        raise ValueError("S11_ORACLE_EMPTY_COMPOSITION")
    accumulator = np.zeros(len(values), dtype=np.float64)
    for coordinate in range(values.shape[1]):
        difference = np.subtract(values[query, coordinate], values[:, coordinate])
        squared = np.multiply(difference, difference)
        accumulator = np.add(accumulator, squared)
    return np.sqrt(accumulator)
