# P9 Formal Execution DAG Isolation and Reauthorization

## Verdict

`P9_FORMAL_EXECUTION_DAG_ISOLATION_AND_REAUTHORIZATION_PASS_PUSHED`

The publication is complete at the artifact level. The final Git publication and
remote synchronization recorded below were performed only after all validation gates.

## Scope and inputs

- Execution time: 2026-08-31 14:00-14:21 KST
- Starting Fuse commit: `4f8c3f922f16635493861103260d9f6a3a8f839d`
- Dissertation binding: `ad8c8b5c17c5ca72dce7f30c2eb283f6041dbc9a`
- Scientific implementation: `eb90f6f667d1717684f47ddef30043992b70e788`
- Production cache: `p9cache_f8b16c49f2c63216609b013b`
- Cache acceptance: `p9ca_99725ef4c56f8b11b4d71935`
- P8 acceptance: `p8acc_c9f16a07275aadfae928d329`
- P7 runtime acceptance: `p7rta_c780441a553abe26772827d0`
- P9 readiness: `p9ready_521c12a65d9b2984fac2cf11`

The accepted scientific configuration, seed, P7/P8 lineage, 78,672-entry production
cache, and 391,466,804,516 cache bytes were not changed.

## Root cause and unsafe closure

The previous main-pipeline terminal closure was independently reconstructed from
`closure_audit.json` without executing it. It contained 100 targets and 283 internal
edges. Seventy-one closure targets were outdated, including 65 unexpected build
candidates outside the intended six-target formal chain; the main pipeline had 148
outdated targets overall. The unsafe ancestors included historical P0/P4/P5/P6/P7/P8
producers and production-cache materialization. Therefore `shortcut = FALSE` against
the main research store was correctly blocked.

The defect was structural: valid immutable acceptance payloads were represented as
dependencies on their historical producer symbols. Producer currentness was therefore
incorrectly coupled to formal execution eligibility.

## Isolated architecture

- Pipeline script: `_targets_p9_formal.R`
- Target declarations: `targets/research_p9_formal_execution.R`
- Shared orchestration: `R/research_p9_formal_execution_isolated.R`
- Store: `/mnt/hdd002/dhnyu/fusedata/targets/fuse-p9-formal`
- Main research store imported or depended upon: no
- Scientific payloads copied into the isolated store: no
- `tar_cue(mode = "never")`: not used

Layer A validates accepted external files by canonical absolute path, size, SHA-256,
schema version, identity, acceptance status, lineage, and cache-manifest accounting.
Layer B publishes content-addressed execution authorization artifacts. Layer C is the
six-target formal run, validation, checkpoint, terminal, and acceptance chain. Only
Layer A/B was selected in this work unit.

## Runtime identity and publication

- Implementation commit: `c330e227dfe224a1c654526f62a9ad7165d88a69`
- Authorized runtime files: 33
- Runtime tree SHA-256: `b0395143a364d26bb1e121524e69c75cc0f98ce12aa5ecdefacab0f9af58f9f6`
- Runtime publication configuration: `config/p9_formal_isolated_publication.yml`
- Report/publication commit: recorded in the final Git section

The runtime set includes the isolated script and declarations, immutable binding and
authorization code, formal runner, cache reader, model/data routing, optimizer,
scheduler, validation, checkpoint, lock/state machinery, and all runtime schemas.
Publication/report descendants are eligible only when these bytes reproduce the same
runtime digest and descend from the implementation commit.

## Immutable roots

The root inventory `p9root_4266c6b6b2c82019027f96ae` binds eight accepted JSON roots,
the category vocabulary, and six cache manifests. The cache manifests alone total
326.84 MB and were fully SHA-256 verified during Layer A. The production manifest binds
78,672 entries; the cache inventory remains 314,695 files and 391,466,804,516 bytes.

Missing file, size/hash mismatch, schema mismatch, identity mismatch, non-PASS parent,
cache identity mismatch, or entry/byte-count mismatch stops before authorization or
formal execution. A first Layer A attempt found and rejected an R 32-bit integer
coercion of the cache byte count; the implementation was corrected to exact decimal
comparison before any authorization artifact existed.

## Supersession and replacement identities

- Superseded authority: `p9a_b295be97717efbd2305dd5a6`
- Superseded reservation: `p9res_51ed9e4731c21bda28d4d7a2`
- Superseded attempt: `p9attempt_f153ff8e7831effbf2f2d68a`
- Supersession: `p9sup_93e2295935358c881c5fdfc5`
- New authority: `p9a_2c67a3971b785f7049cb3d65`
- New reservation: `p9res_0ab5e0235bc36811d8855050`
- New preassigned attempt: `p9attempt_074b247e347f851387606da0`
- Preassignment artifact: `p9pre_9a3d26c27cae271c6b50e87f`
- Authorization acceptance: `p9xacc_12d457b5127e3fd242d07b3d`

The old identities are preserved, scientifically valid but operationally unexecutable,
unstarted, superseded, and ineligible for future formal execution. Verified old counts:
formal starts 0, run identities 0, lock acquisitions 0, optimizer updates 0, formal
validation runs 0, checkpoints 0, evaluation queries 0.

The replacement reservation is `AUTHORIZED_NOT_STARTED`. Its configuration identity is
`9ca251b54d6f29379990ae35ffa743f1db2643cf671a8f468fad58becdfd07cb`, seed identity is
`787e77a3684eb832cdfab0bfd1bded526d5d42b390d7ed84e2663cb1817c2815`, and duplicate key
is `3d2f7499705cc9fd89e0a7ea2e4a6aaa4f06c500a0338a4a82b5fb4b00925971`.

## Production closure audit

- Pipeline targets: 25
- Pipeline edges: 48
- Terminal upstream closure: 24 targets
- Closure internal edges: 47
- Layer C formal targets: 6
- Current Layer A/B targets after publication: 19/19
- Outdated targets after publication: exactly the six Layer C targets
- P0-P8 producer targets: 0
- Production-cache construction/materialization targets: 0
- Unrelated P9-A targets: 0
- P9-B targets: 0
- P10/P11/evaluation/maintenance targets: 0
- Main-store dependencies: 0
- Optimizer/GPU-capable targets: 1 (`p9_cfg_main_formal_run`)

Machine-readable evidence:
`/mnt/hdd002/dhnyu/fusedata/tmp/fuse/p9_formal_dag_isolation_20260831_141842/production_closure_audit.json`.

## Bootstrap and no-op validation

A temporary synthetic store proved empty-store `shortcut = FALSE` bootstrap, Layer A/B
traversal, four CPU-only non-formal updates, downstream fixture completion, and
`shortcut = TRUE` no-op replay. This was below the eight-update limit and used no
production input, reservation, attempt, output, lock, cache write, validation identity,
GPU, or formal checkpoint. Root mutation removed the root's successful metadata and did
not rebuild downstream outputs.

Production Layer A/B publication completed 18 targets in 3.7 seconds. The separately
materialized inventory reference completed in 0.17 seconds. Immediate authorization
replay with `shortcut = TRUE` skipped the pipeline in 75 ms: builds 0, rewrites 0,
optimizer updates 0, GPU executions 0, and artifact path/size/mtime changes 0.

## Validation

- Focused Python: 12 passed
- Full Python: 87 passed
- Focused isolated R: 7 passed
- Full R/testthat: 812 passed, 3 documented legacy skips, failures 0
- Python compile/AST: PASS
- R parse: PASS
- YAML/JSON parse: PASS
- New artifact schemas: 6/6 PASS
- Canonical JSON readback: PASS
- Main `targets::tar_validate()`: PASS
- Isolated `targets::tar_validate(script = ...)`: PASS
- Isolated manifest/network: PASS
- Synthetic first-bootstrap/no-op: PASS
- Production closure audit: PASS
- `git diff --check`: PASS
- Dissertation Typst compile: PASS using the Snap payload binary with explicit project
  root; expected unavailable Korean font warnings were emitted, errors 0

## Immutability and prohibited execution

Exact before/after inventories proved:

- Existing P1-P8/model artifacts changed: 0/2,426
- Main target-store objects changed: 0/1,266
- Production-cache files changed: 0/314,695
- Dissertation tracked files changed: 0/63
- Existing checkpoints changed: 0
- New production formal attempts started: 0
- Optimizer updates: 0
- Formal validation/evaluation consumption: 0/0
- Checkpoints: 0
- DDP/GPU executions: 0
- P9-B/P10/P11/maintenance executions: 0
- Active attempt locks after publication: 0
- Remaining GPU training processes: 0

Expected external additions are limited to the six immutable authorization JSON files
under `p9a_2c67a3971b785f7049cb3d65` and isolated-store metadata. No cache, checkpoint,
store object, log, lock, credential, or temporary evidence is tracked in Git.

## Exact next task

Formal execution has not started. The sole authorized next command is:

```bash
FUSE_P9_FORMAL_RESERVATION_ID=p9res_0ab5e0235bc36811d8855050 \
Rscript -e 'targets::tar_make(
  script = "_targets_p9_formal.R",
  names = p9_cfg_main_attempt_acceptance,
  shortcut = FALSE,
  store = "/mnt/hdd002/dhnyu/fusedata/targets/fuse-p9-formal"
)'
```

It must be launched as a separate authorized work unit in a durable session. This report
does not authorize any other P9-A configuration, P9-B materialization, selected-FM
selection, held-out evaluation, P10, P11, or maintenance execution.

## Git publication

- Fuse branch: `reduced`
- Implementation commit: `c330e227dfe224a1c654526f62a9ad7165d88a69`
- Publication commit: the immutable commit containing this report and publication
  binding; its SHA is recorded by `git log` and in the final execution response
- Final Fuse HEAD: the same publication commit
- Required remote status after publication: local/`origin/reduced` exact, ahead/behind
  `0/0`
- Dissertation HEAD: `ad8c8b5c17c5ca72dce7f30c2eb283f6041dbc9a`
- Dissertation mutation: none

## Prompt summary

The work unit requested isolation of formal P9 execution from 65 unintended historical
build candidates, immutable accepted-file roots, a dedicated script/store, replacement
authorization with unchanged science, synthetic bootstrap/no-op validation, Layer A/B
publication only, complete immutability auditing, and no formal training.
