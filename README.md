# fuse

`fuse` implements the current reduced-lineage spatial scene representation
pipeline. The dissertation `reduced` branch is the scientific authority.

## Layout

- `R/`: reusable R methodology and pipeline-support functions.
- `targets/`: thin stage-oriented target declarations.
- `python/`: current model, training, evaluation, and downstream libraries.
- `scripts/`: operator-facing entrypoints and explicit retirement guards.
- `config/`: current scientific, runtime, and schema contracts.
- `tests/`: current unit/contract tests and minimal fail-closed guard tests.
- `reports/`: audits and validation records.
- `blueprint/targets_implementation_blueprint.md`: current target architecture.

The main research graph is `_targets.R`, with stages s00-s08. It is separate
from the Seoul canonical-data maintenance graph in `_targets_maintenance.R` and
its independent targets store.

Dedicated current entrypoints are:

- `_targets_training.R` for s09 training.
- `_targets_evaluation.R` for s10 evaluation.
- `_targets_s11_diagnostics.R`, `_targets_s11_downstream.R`,
  `_targets_s11_readiness.R`, and `_targets_s11_ridge.R` for downstream work.

`_targets_p9_formal.R` and `_targets_p9_recovery.R` are intentional immediate
retirement guards. They do not define executable historical graphs.

## Current scientific contract

- Off-grid scenes: 10,000 total, 1,000 validation and 9,000 evaluation.
- Main model dimensions: `d = d_c = 128`.
- Objective: symmetric scene-level contrastive learning only.
- Formal study: 11 unique OFAT configurations and 17 compared models.
- Information-preservation and reconstruction subsystems are absent.

See `config/current_methodology.yml` and the current P0 methodology authority
for the complete machine-readable contract.

## Validation

Inspect a graph without executing targets:

```bash
Rscript -e 'targets::tar_manifest(script = "_targets.R")'
Rscript -e 'targets::tar_validate(script = "_targets.R")'
Rscript tools/targets-network/render_targets_network.R
```

Run unit tests:

```bash
Rscript -e 'testthat::test_dir("tests/testthat")'
pytest -q
```

Production execution is deliberately separate from validation. Do not run a
large or GPU target until its fixture/pilot checks and current authority gates
pass. Immutable artifacts are published only after staging and QC; historical
artifacts are never rewritten or relabeled.
