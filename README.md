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

- `_targets_training.R` for the s09 campaign in the dedicated
  `/mnt/hdd002/dhnyu/fusedata/targets/fuse-training-s09` store. The guarded
  operator command is `Rscript scripts/run_training_targets.R campaign`.
  Append-only campaign/per-run progress and separate worker streams are written
  under `logs/s09/`; `logs/s09/current_status.txt` is updated atomically.
- `_targets_retrieval_visualization.R` for S10 deterministic retrieval visualization
  over the 28 accepted S09 models (30 fixed queries, common 9,000-scene gallery).
- `_targets_evaluation.R` for S11 evaluation, currently fail-closed pending separate
  lineage repair. S10 does not select models or alter the S11 protocol.

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

### S09 SSD read replica

The canonical HDD cache remains the immutable authority. An optional SSD copy
changes only physical prepared/geometry/DS reads, for training and validation.
P1 scene centers and lineage metadata still resolve from current accepted parents.
No bind mount, symlink, targets-store editing, or scientific cache rebuild is needed.

```bash
CANONICAL=/mnt/hdd002/dhnyu/fusedata/models/reduced/formal_training/prepared_cache/s09cache_dc4e9e271e40ffe8ae17967c
REPLICA="$HOME/fuse-cache/s09cache_dc4e9e271e40ffe8ae17967c"
python scripts/s09_cache_replica.py plan --canonical-root "$CANONICAL"
python scripts/s09_cache_replica.py copy --canonical-root "$CANONICAL" --read-root "$REPLICA"
python scripts/s09_cache_replica.py verify --canonical-root "$CANONICAL" --read-root "$REPLICA"
```

Copy is sequential and verifies every destination byte against accepted hashes
before creating `replica_verified.json`. It preserves the HDD original. Existing
complete destination files are verified and reused, never overwritten. Corrupt
files or an interrupted `.copying` file stop the operation and remain evidence;
use a fresh destination parent or explicitly investigate before retrying. Space
checking reserves an additional 1 GiB. A full copy/verify is substantial HDD I/O;
schedule it separately from competing raster jobs.

Only after full replica verification and separate training authorization:

```bash
FUSE_S09_CACHE_READ_ROOT="$REPLICA" Rscript scripts/run_training_targets.R campaign
```

An unset variable preserves canonical reads; an explicitly empty, missing,
unverified or mismatched root fails closed before formal GPU launch. There is no
automatic HDD fallback. Startup verifies all inventory sizes and metadata hashes;
prepared payloads are hashed at consumption, and geometry/DS retain their existing
payload hash checks. The runtime records physical placement in per-run
`.cache_read.jsonl` evidence. `verify` explicitly rehashes the entire replica.

Placement does not change S08 or the accepted cache identity. The implementation
is S09 runtime-bound and requires fresh campaign authorities after this repair;
do not reuse the interrupted old campaign's results/checkpoints. No scientific
target declarations or S01-S08 paths change. Verify main-store currentness before
any future formal launch. Do not commit replica data, receipts or logs.

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
