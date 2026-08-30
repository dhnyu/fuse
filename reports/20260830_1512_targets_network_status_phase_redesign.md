# Targets network status and Phase redesign

## Verdict

`TARGETS_NETWORK_STATUS_PHASE_REDESIGN_PASS`

The renderer now presents current target validity, explicit research Phase, target type,
and directed lineage through independent visual channels. The generated graph is a
deterministic, self-contained HTML document and does not execute target commands.

## Scope and execution time

- Work unit: visualization and metadata only
- Executed: 2026-08-30 14:54-15:12 Asia/Seoul
- Repository: `/members/dhnyu/fuse`
- Branch: `reduced`
- Starting HEAD: `eb90f6f667d1717684f47ddef30043992b70e788`
- Final implementation HEAD before publication: `eb90f6f667d1717684f47ddef30043992b70e788`
- Final publication HEAD: the commit containing this report; verified against
  `origin/reduced` after push because a commit cannot contain its own SHA.

## Pre-existing network modification

The worktree initially contained only a tracked modification to
`artifacts/targets-network/targets-network.html`. Inspection showed three random
htmlwidgets DOM identifiers changing with no graph or metadata change. It was preserved
before regeneration at:

- Patch: `/tmp/targets_network_preexisting_20260830.patch`
- Persistent evidence root:
  `/mnt/hdd002/dhnyu/fusedata/tmp/fuse/targets_network_redesign_20260830_1454`
- Pre-existing patch SHA-256:
  `1c76a506e3129fa9c8570cf2a8522cc59a7f9729d6443715f5de88505e2b4ab3`
- Initial worktree HTML SHA-256:
  `1f15f8709ad8929e2ab242c78a5db6494abccaa1df896f68c38c823aa19aa1ad`
- Initial HEAD HTML SHA-256:
  `fa6a49fcbc6f0202df06e26365d1f089fd5b85eef6eabdf10718023726c75934`

The new renderer embeds the installed vis-network assets directly with stable element
identifiers, deterministic ordering, and atomic write-if-changed publication.

## Status semantics

Installed versions were `targets 1.12.0`, `visNetwork 2.1.4`, `htmlwidgets 1.6.4`,
`yaml 2.3.12`, and `igraph 2.2.3`. The renderer uses public APIs supported by this
environment:

- `tar_outdated()` for current outdated membership;
- `tar_progress()` for currently dispatched/running targets;
- `tar_errored()` for unresolved errors;
- `tar_meta()` for branch-to-stem mapping and target details;
- `tar_manifest()` and `tar_network()` for current nodes and dependency edges.

Status precedence is `error > running > outdated > up_to_date`. The previous
`queued`/`skipped` rendering came from the most recent execution progress record. In the
current store it reports two skipped targets, while `tar_outdated()` independently reports
124 targets. It therefore describes past scheduling activity rather than current validity
and is not used as the primary node state.

## Graph results

- Nodes: 164
- Directed edges: 526
- Edge direction: dependency to dependent
- DAG: yes
- Cycles: 0
- Weakly connected components: 3
- Unmapped current targets: 0
- Duplicate Phase assignments: 0

### Current status counts

| Status | Count |
|---|---:|
| error | 0 |
| running | 0 |
| outdated | 124 |
| up to date | 40 |

The rendered outdated count exactly equals an independent `tar_outdated()` readback from
the same script, store, and metadata snapshot.

### Target counts by Phase

| Phase/category | Count |
|---|---:|
| Foundation / Shared | 4 |
| P0 | 14 |
| P1 | 8 |
| P2 | 38 |
| P3 | 20 |
| P4 | 13 |
| P5 | 13 |
| P6 | 20 |
| P7 | 21 |
| P8 | 11 |
| P9 | 2 |
| P10 | 0 |
| P11 | 0 |
| Maintenance | 0 |

`target_phases.yml` explicitly maps every current target exactly once. Future P10, P11,
and Maintenance rules are marked as future rules; all non-future rules must match.

## Visual and interaction contract

- Fill color: current status, using dark green, light blue, orange, and red.
- Border color and `[Phase]` label line: Phase/category.
- Shape: stem or file target; function shape remains reserved if functions are rendered.
- Default placement: ordered left-to-right Phase levels with compact within-Phase spacing.
- Edges: subdued directed arrows; selected transitive upstream is blue and downstream is
  pink.
- Controls: target search, Phase filter, status filter, All/Outdated/Running/Error quick
  filters, reset/fit, pan, zoom, and node selection.
- Details: target name, status, Phase, type, direct dependency/dependent counts, elapsed
  seconds, bytes, latest error, and latest successful build where recorded.
- Labels and metadata are escaped before HTML/JSON/DOM insertion.

Browser validation used headless Google Chrome at 1600 x 1000. It loaded one canvas with
164 nodes and 526 edges, P8 count 11, P9 count 2, and outdated count 124. Search/filter
controls and reset were exercised. Console errors, page errors, and captured JavaScript
errors were all zero. The desktop screenshot is
`artifacts/targets-network/targets-network-desktop.png`.

## Determinism

Two consecutive renders from unchanged metadata produced:

- HTML SHA-256: `f11224e64346df667995b2ebf1726d237364ee793c2ab18e8bfe96f0e0971c5e`
- HTML size: 994,258 bytes
- Second-render content difference: 0
- Second-render mtime change: 0
- Second-render rewrite: 0

Nodes, edges, status cards, Phase options, and legends are sorted deterministically. The
tracked HTML contains no uncontrolled render timestamp or random htmlwidgets identifier.

## Validation

- R parse: PASS
- YAML parse: PASS
- Focused target-network tests: PASS
- Full R/testthat suite: PASS
- Documented legacy skips: exactly 3
- `targets::tar_validate()`: PASS
- Current node and edge count checks: PASS
- DAG and weak-component checks: PASS
- Every target exactly once: PASS
- Independent outdated-count parity: PASS
- Browser JavaScript and interaction smoke: PASS
- `git diff --check`: PASS

No `tar_make()` or target command was run. The renderer and tests performed read-only
metadata access only.

## Immutability and non-execution

Pre/post inventories were compared by path, size, mtime, and SHA-256:

- Research target-store stat inventory: 1,602/1,602 identical
- Target-store object SHA checks: 1,266/1,266 PASS
- Model artifact/manifest SHA checks: 154/154 PASS
- Scene artifact/manifest SHA checks: 3,091/3,091 PASS
- Scientific target/artifact mutations: 0
- Optimizer updates: 0
- Formal P9 attempts: 0
- Checkpoints created or modified: 0
- Evaluation queries consumed: 0
- GPU executions: 0
- Maintenance executions: 0

Existing unrelated tmux sessions were observed but not accessed or modified. No GPU
compute process was present during the final check.

## Changed files

- `tools/targets-network/render_targets_network.R`
- `tools/targets-network/target_phases.yml`
- `tools/targets-network/README.md`
- `tests/testthat/test-target-network.R`
- `artifacts/targets-network/targets-network.html`
- `artifacts/targets-network/targets-network-desktop.png`
- `reports/20260830_1512_targets_network_status_phase_redesign.md`

## Prompt summary

Redesign the Fuse targets dependency visualization without changing scientific execution,
using current validity status, explicit Phase authority, target-type shapes, directed and
selectable lineage, deterministic output, focused tests, artifact immutability checks, and
commit/push publication on `reduced`.
