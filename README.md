# fuse

`fuse` implements the current reduced-lineage spatial scene representation
pipeline. The dissertation `reduced` branch is the scientific authority.

## Layout

- `R/`: reusable R methodology and pipeline-support functions.
- `targets/`: thin stage-oriented target declarations.
- `python/`: current model, training, and evaluation libraries.
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

The previous s11 downstream implementation is retired pending a from-scratch
redesign; no active s11 target entrypoint is retained. P9 v1 execution remains
fail-closed through the centralized R/Python retirement guards and the
operator-facing retirement CLIs. Obsolete root retirement entrypoints are not
retained as executable files.

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
