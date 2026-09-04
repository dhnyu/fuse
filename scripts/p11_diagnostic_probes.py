#!/usr/bin/env python3
"""Execute or validate the immutable P11-G diagnostic probe matrix."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from p11_diagnostic_probes import (
    materialize_p11_diagnostic_matrix,
    run_cpu_gpu_equivalence_pilot,
    run_gpu_throughput_pilot,
    run_mlp_determinism_pilot,
    validate_p11_diagnostic_acceptance,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/p11_diagnostic_probe_matrix.yml")
    parser.add_argument("--pilot", action="store_true")
    parser.add_argument("--gpu-pilot", action="store_true")
    parser.add_argument("--gpu-benchmark", type=int, choices=(1, 2))
    parser.add_argument("--validate")
    args = parser.parse_args()
    if args.validate:
        result = validate_p11_diagnostic_acceptance(Path(args.validate), args.config)
    elif args.gpu_pilot:
        result = run_cpu_gpu_equivalence_pilot(args.config)
    elif args.gpu_benchmark:
        result = run_gpu_throughput_pilot(args.config, args.gpu_benchmark)
    elif args.pilot:
        result = run_mlp_determinism_pilot(args.config)
    else:
        result = materialize_p11_diagnostic_matrix(args.config)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
