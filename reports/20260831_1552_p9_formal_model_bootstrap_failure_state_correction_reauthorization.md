# P9 Formal Model Bootstrap Failure-State Correction and Reauthorization

## Verdict

`P9_FORMAL_MODEL_BOOTSTRAP_FAILURE_STATE_CORRECTION_AND_REAUTHORIZATION_PASS_PUSHED`

This report records the runtime correction and immutable reauthorization. The
formal `cfg_main` attempt was not executed. The verdict becomes effective with
the publication commit containing this report and its successful push to
`origin/reduced`.

## Scope and Inputs

- Execution time: 2026-08-31 KST
- Fuse starting HEAD: `5a3f623cf7e1f60ca327a07ae93e4b28277d8ece`
- Formal-runner implementation commit: `45bbd556434f9c610933ba3b54df918f437a2f2e`
- Dissertation binding: `ad8c8b5c17c5ca72dce7f30c2eb283f6041dbc9a`
- P7 runtime acceptance: `p7rta_c780441a553abe26772827d0`
- P8 acceptance: `p8acc_c9f16a07275aadfae928d329`
- P9 readiness: `p9ready_521c12a65d9b2984fac2cf11`
- Production-cache acceptance: `p9ca_99725ef4c56f8b11b4d71935`
- Production cache: `p9cache_f8b16c49f2c63216609b013b`
- Cache inventory: 314,695 files; 391,466,804,516 physical bytes
- Evidence root: `/mnt/hdd002/dhnyu/fusedata/tmp/fuse/p9_formal_bootstrap_correction_20260831_144336`

The dissertation methodology and accepted P7/P8 scientific identities were
read before implementation. No methodology conflict was found. The scientific
`cfg_main` configuration, seed, data membership, cache subset, optimizer,
validation, and selection contracts are unchanged.

## Failed Attempt Classification

The preserved identity set is terminal and nonresumable:

- Authority: `p9a_2c67a3971b785f7049cb3d65`
- Reservation: `p9res_0ab5e0235bc36811d8855050`
- Attempt: `p9attempt_074b247e347f851387606da0`
- Run: `p9run_f592f6b25fb56be8807c16cb`
- Authorization acceptance: `p9xacc_12d457b5127e3fd242d07b3d`
- Runtime digest: `b0395143a364d26bb1e121524e69c75cc0f98ce12aa5ecdefacab0f9af58f9f6`
- Classification: `FAILED_NONRESUMABLE`

It formally started once and launched two DDP ranks, then failed during model
construction. It completed 0 epochs, 0 optimizer updates, 0 validation events,
0 validation/evaluation queries, 0 checkpoints, and 0 acceptances. No exact
resume is authorized. The historical `running_state.json` disagreement was
preserved, not rewritten; the new supersession record records that defect and
the durable failure evidence.

## Root Cause and Vocabulary Contract

`build_vocabulary()` returns a direct field mapping. Each field contract
contains `keys`, `mapping`, `missing`, `mask`, and canonical `size`. The failed
runner instead expected the obsolete wrapper
`values["vocabulary"]["fields"]` and a per-field `values` array.

The corrected runner consumes the direct mapping and takes embedding sizes only
from canonical `field_contract["size"]`. Strict validation rejects missing or
unexpected fields, non-positive/non-integer sizes, non-integer or out-of-range
mapping indices, and inconsistent missing/mask/reserved-token semantics. The
accepted category file and category ordering were not changed.

Validated production sizes were:

| Field | Size | Field | Size |
|---|---:|---|---:|
| A11 | 24 | A9 | 511 |
| CLASS_L1 | 6 | CLASS_L2 | 19 |
| CLASS_L3 | 360 | CLASS_L4 | 1,001 |
| CLASS_L5 | 1,400 | CLASS_L6 | 150 |
| ROAD_RANK | 9 | ROAD_TYPE | 7 |

Bounded construction coverage included FM, A1-A5, SSV, and DS at dimensions
48, 64, and 128. No registered family retains the obsolete wrapper assumption.

## Runtime Corrections

- Added canonical vocabulary validation and direct size routing.
- Added the P9 FM adapter with the P7-compatible parameter namespace and the
  P9 generic input contract.
- Corrected queue construction, production geometry-manifest reading, prepared
  cache-envelope validation, and mask routing.
- Added a mandatory production-shaped, optimizer-free startup gate.
- Added atomic `FAILED_NONRESUMABLE` state publication with failure stage/class,
  sanitized message, traceback digest, rank exits, counters, cleanup, and lock
  release fields.
- Ensured initialized process groups are destroyed from rank `finally` paths;
  controller failure collection terminates/joins sibling ranks coherently.
- Added strict state/owner/heartbeat consistency validation.
- Tightened validation-event schemas to reject undeclared fields.

Synthetic failure injection covered invalid wrappers, missing fields, invalid
sizes and mapping indices, rank 0/rank 1/both-rank model-construction failures,
post-DDP and pre-update failures, nonzero rank exits, atomic failure state,
lock release, cleanup, and nonresumable classification.

## Production-Shaped Startup Gate

- Gate ID: `p9sg_6bc30ca673e6e09b7699c93d`
- Evidence SHA-256: `7d2a80ac497f91f994a9839f9bcf3d720bfea69cd4fff2d3ec69b9bfc3fa68e3`
- Runtime digest: `1e044fe16378c957592fc408ce5e7af65c7bad697f44c48ab3cd817790254497`
- World size: 2, production cache reader, production `cfg_main` routing
- Rank status: 2/2 PASS; process-group cleanup 2/2 CONFIRMED
- Batch identity digest: identical on both ranks
- Initial online/EMA/optimizer/scheduler/queue state digests: identical
- Finite loss: rank 0 `4.944131374359131`; rank 1 `4.981851577758789`
- Production training samples loaded: 32 per rank
- Optimizer/EMA/scheduler updates: 0/0/0
- Parameter mutations: 0
- Backward passes: 0
- Formal attempts/validations/evaluations/checkpoints: 0/0/0/0
- Bounded non-formal GPU executions: 1

The gate used training-cache samples only. It created no production attempt/run
identity, acquired no production duplicate-attempt lock, and left no GPU process.

## Store Versioning and Reauthorization

- Preserved failed store: `/mnt/hdd002/dhnyu/fusedata/targets/fuse-p9-formal`
- New execution generation: `p9gen_acb72f05336e09451b4ac458`
- New versioned store: `/mnt/hdd002/dhnyu/fusedata/targets/fuse-p9-formal-p9gen_acb72f05336e09451b4ac458`
- New runtime digest: `1e044fe16378c957592fc408ce5e7af65c7bad697f44c48ab3cd817790254497`
- Supersession/failure lineage: `p9sup_24c99482be1a2788e7906b44`
- New authority: `p9a_b0c50c956d84a1c3664d7934`
- New reservation: `p9res_15556054a164595be7829160`
- New preassigned attempt: `p9attempt_25b780995291c86ce49b2182`
- Preassignment: `p9pre_cdc5d94561d1890acb0059ea`
- Authorization acceptance: `p9xacc_04fdacdfa9f195dae078517e`
- Duplicate key: `dd04db35ea7a2b8be5d5ba3cf54897a9750074541b4d3f2eab9d9b4a72b9af5e`
- Final reservation state: `AUTHORIZED_NOT_STARTED`

The old failed store and its six metadata/evidence files were byte/stat
unchanged. The new attempt has no run, checkpoint, validation, or terminal
artifact.

## Isolated Closure and No-Op

The corrected isolated pipeline declares 26 targets and 50 internal target
edges. The terminal closure contains 25 targets and 49 edges, including exactly
six Layer C targets. Unexpected P0-P8 producers, production-cache builders,
other P9-A, P9-B, P10/P11, evaluation, maintenance, and main-store dependencies
are all 0. Only the six Layer C targets are outdated in the terminal closure.

The unused derived inventory leaf `p9x_immutable_root_inventory` is outside the
terminal closure and remains outdated; it cannot enter or expand formal
execution. Machine-readable evidence is in
`corrected_isolated_closure_audit.json` under the evidence root.

Layer A/B publication built 19 authorization targets and no Layer C target.
Immediate `shortcut = TRUE` replay skipped the authorization terminal target:
builds 0, rewrites 0, GPU executions 0, optimizer updates 0, formal attempt
starts 0, validation/evaluation 0/0, checkpoints 0. Publication artifact
path/size/mtime/SHA values were unchanged.

## Validation

- Focused Python bootstrap/formal/model tests: 63 passed
- Full Python suite: 280 passed
- Full R/testthat suite: PASS with exactly 3 documented legacy skips
- Main and isolated `targets::tar_validate()`: PASS
- R parse: 87 files PASS
- Python compile/AST: PASS
- YAML/JSON parse and all new schemas: PASS
- Canonical artifact JSON readback: PASS
- Isolated manifest/closure validation: PASS
- `git diff --check`: PASS
- Target network: 190 targets, 577 edges, 1 weak component; deterministic
  repeat-render SHA-256 `fa42648d83dc1d6dc61fabbc95d2c3516a6f23c78c0b01bf185f1fb98a7c72dd`
- Dissertation read-only Typst compile: PASS; only existing unavailable Korean
  font warnings were emitted

Synthetic optimizer updates were 0. Production optimizer updates were 0.
Non-formal backward passes were 0. Formal attempt starts were 0.

## Immutability and Prohibited Work

Pre/post inventories verified:

- 2,433 pre-existing model/authorization artifact hashes unchanged
- 1,266 main target-store object hashes unchanged
- all 314,695 production-cache path/size/mtime records unchanged
- failed isolated-store inventory unchanged
- 63 dissertation tracked-file hashes unchanged
- P1-P8 artifacts, existing checkpoints, production cache, old authority and
  failed evidence mutations: 0
- production formal runs/optimizer updates: 0/0
- formal validation/evaluation queries: 0/0
- production checkpoints: 0
- P9-B/P10/P11/maintenance executions: 0
- remaining GPU processes/active kernel locks: 0/0

## Changed Files

The implementation commit changes the isolated execution R/Python modules,
formal runner, model/data adapters, runtime configuration, schemas, focused
tests, and blueprint. The publication commit adds the final runtime/startup-gate
binding, regenerated main target-network HTML, and this report. No cache,
checkpoint, log, lock, target-store object, credential, or temporary evidence
is tracked.

## Next Task

The next separately authorized task may start exactly the new `cfg_main` formal
attempt with:

```bash
FUSE_P9_FORMAL_RESERVATION_ID=p9res_15556054a164595be7829160 \
Rscript -e 'targets::tar_make(
  script = "_targets_p9_formal.R",
  names = p9_cfg_main_attempt_acceptance,
  shortcut = FALSE,
  store = "/mnt/hdd002/dhnyu/fusedata/targets/fuse-p9-formal-p9gen_acb72f05336e09451b4ac458"
)'
```

This command was not executed in this work unit.

## Prompt Summary

The requested work was to correct the production vocabulary bootstrap defect,
make failure-state persistence and DDP cleanup coherent, prove the real
production startup path without optimizer mutation, version the isolated store,
supersede the zero-update failed attempt, and issue a new executable but
unstarted authority/reservation/attempt.
