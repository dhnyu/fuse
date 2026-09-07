#!/usr/bin/env python3
import argparse
import json
import numpy as np
import zarr


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", required=True)
    parser.add_argument("--array", required=True)
    parser.add_argument("--index", type=int, required=True)
    parser.add_argument("--expected", required=True)
    parser.add_argument("--shape", required=True)
    parser.add_argument("--atol", type=float, required=True)
    args = parser.parse_args()
    shape = tuple(int(value) for value in args.shape.split(","))
    expected = np.fromfile(args.expected, dtype="<f4").reshape(shape)
    observed = np.asarray(zarr.open_group(args.store, mode="r")[args.array][args.index])
    difference = np.abs(observed.astype(np.float64) - expected.astype(np.float64))
    finite = np.isfinite(observed) == np.isfinite(expected)
    passed = observed.shape == expected.shape and finite.all() and np.allclose(observed, expected, atol=args.atol, rtol=0, equal_nan=True)
    print(json.dumps({"status": "PASS" if passed else "FAIL", "shape": list(observed.shape), "maximum_absolute_error": float(np.nanmax(difference)) if difference.size else 0.0}, sort_keys=True))
    raise SystemExit(0 if passed else 2)


if __name__ == "__main__":
    main()
