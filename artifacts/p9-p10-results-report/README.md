# P9-P10 Results Consolidation

Current report: [Comprehensive model results](../../reports/20260906_0244_p9_p10_comprehensive_model_results.md).

Artifact: `p9p10report_cd410155ce55a1658adf01fd/`.
This is a derived summary of accepted evidence, not a replacement scientific acceptance.

- Exactly 20 primary configurations: 13 P9-A and seven P9-B variants.
- FM (`cfg_d128`) is included once in the primary population.
- Two joint-interaction diagnostic runs are stored separately.
- 186,580 primary training-update rows; 491 primary validation rows; eight canonical held-out metric rows.
- MRR/HIT validation trajectories exist for 19 primary models, not historical `cfg_d64`.
- All 8,473 source hashes matched before and after generation.
- Final focused validation: 81 tests passed; Python/JSON/YAML parse checks passed.

Validate the committed derived package without running models:

```bash
python python/p9_p10_results_report.py --validate artifacts/p9-p10-results-report/p9p10report_cd410155ce55a1658adf01fd
```

The read-only generator is `python python/p9_p10_results_report.py`.
Generation requires the accepted data mount and validates the P9 v2 resolver chains before reading
CPU checkpoint traces. It refuses to overwrite an existing content-addressed report package.
It never constructs a model, executes inference, or publishes a selection/acceptance.

Parquet preserves stored numeric precision. Missing numeric values are null, with explicit
`NA_NOT_RECORDED` status columns where applicable; CSV uses that literal marker. Training rows
without a validation event also carry `NOT_A_VALIDATION_INTERVAL`. Summary training losses are
selected-epoch arithmetic means, not validation metrics. Figures use observed points without smoothing.

Run the focused readback tests:

```bash
PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
PYTHONPATH=python \
P9_P10_REPORT_DIR=artifacts/p9-p10-results-report/p9p10report_cd410155ce55a1658adf01fd \
pytest -q tests/python/test_p9_p10_results_report.py tests/python/test_p9_v2_finalization.py \
  tests/python/test_p9_v2_acceptance_resolver.py tests/python/test_p10_evaluation.py
```

No checkpoint, scene cache, or embedding payload is packaged here. The 60-file package is about
20.7 MB and contains tables, 14 figures, per-model validation CSVs, provenance and validation metadata.
