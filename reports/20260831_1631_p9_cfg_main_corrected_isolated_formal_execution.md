# P9 cfg_main corrected isolated formal execution

## Verdict

`P9_CFG_MAIN_CORRECTED_ISOLATED_FORMAL_EXECUTION_FAILED_NONRESUMABLE`

The corrected, isolated formal attempt started successfully and ran through
epoch 15. It failed on the first update of epoch 16 in the formal contrastive
objective with `ValueError: global scene identity lookup mismatch`. The attempt
is terminal, nonresumable, unaccepted, and must not be rerun under this
authority/reservation/attempt identity.

## Scope and Launch Lineage

- Launch commit: `039857c6ccfca136aa575be3a9ea04ca33f11d4b`
- Runtime implementation commit: `45bbd556434f9c610933ba3b54df918f437a2f2e`
- Dissertation binding: `ad8c8b5c17c5ca72dce7f30c2eb283f6041dbc9a`
- Authority: `p9a_b0c50c956d84a1c3664d7934`
- Reservation: `p9res_15556054a164595be7829160`
- Attempt: `p9attempt_25b780995291c86ce49b2182`
- Derived run: `p9run_f62cd1d3b2430cd1f0eccc9d`
- Authorization acceptance: `p9xacc_04fdacdfa9f195dae078517e`
- Runtime digest: `1e044fe16378c957592fc408ce5e7af65c7bad697f44c48ab3cd817790254497`
- Isolated store: `/mnt/hdd002/dhnyu/fusedata/targets/fuse-p9-formal-p9gen_acb72f05336e09451b4ac458`
- Production cache / acceptance: `p9cache_f8b16c49f2c63216609b013b` /
  `p9ca_99725ef4c56f8b11b4d71935`
- P8/P7 runtime/P9 readiness: `p8acc_c9f16a07275aadfae928d329` /
  `p7rta_c780441a553abe26772827d0` /
  `p9ready_521c12a65d9b2984fac2cf11`

The launch used exactly the authorized terminal target in tmux session
`p9_cfg_main_corrected_formal`, with the prescribed reservation token and
`shortcut = FALSE`. The main research pipeline/store, prior isolated stores,
P9-B, other P9-A configurations, P10/P11, evaluation, and maintenance were not
selected.

## Preflight and Closure

Fuse and dissertation were both `reduced`, clean, and synchronized at `0/0`.
The actual launch commit was a descendant of the implementation commit and all
authorized runtime files reproduced the required runtime digest. The formal
validator passed authority, reservation, acceptance, matrix row, cache,
categories, immutable roots, and runtime-tree checks.

The read-only closure audit found 26 declared targets and 50 internal edges;
the terminal closure contained 25 targets and 49 edges. Its only outdated
members were the six intended Layer C targets:

1. `p9_cfg_main_formal_run`
2. `p9_cfg_main_validation_trace`
3. `p9_cfg_main_checkpoint_candidates`
4. `p9_cfg_main_selected_checkpoint`
5. `p9_cfg_main_terminal_execution`
6. `p9_cfg_main_attempt_acceptance`

Unexpected P0-P8 producers, production-cache builders, unrelated P9-A, P9-B,
P10/P11, evaluation, maintenance, main-store, and old-store dependencies were
all 0. The outside-closure inventory leaf was not executable from the terminal
target. Evidence is under:

`/mnt/hdd002/dhnyu/fusedata/tmp/fuse/p9_cfg_main_corrected_formal_20260831_160332/prelaunch_closure_audit.json`

The required production-shaped startup-gate evidence was bound by the
authorization acceptance: vocabulary direct mapping, canonical field sizes,
model/EMA/optimizer/scheduler/queue construction, production-cache sample
loading, two-rank DDP initialization, finite forward loss, and cleanup all
passed with 0 optimizer updates.

## State Transitions and Failure

The controller acquired one duplicate lock and created the single authorized
run. `attempt_state.json` transitioned to `RUNNING`; the heartbeat stayed live.
Two DDP ranks ran with the accepted cache. No `KeyError: 'fields'` occurred.

At epoch 16, batch 0, both ranks raised the same error from
`p7_training.local_infonce_sum()`:

```text
ValueError: global scene identity lookup mismatch
```

The controller persisted matching terminal state, owner, and heartbeat records
with `FAILED_NONRESUMABLE`, both rank exit codes 1, process-group cleanup
`CONFIRMED`, and kernel-lock release `RELEASED`. GPU compute processes and lock
holders were 0 after failure. Exact resume is not authorized.

The terminal failure state itself incorrectly reports 0 updates, 0 checkpoints,
and 0 validation events even though durable checkpoint evidence proves 1,140
updates, three validation events, and three checkpoints. This is a second
runtime-state accounting defect. It prevents terminal acceptance and must be
fixed only in a new correction/reauthorization work unit; the current attempt
must remain preserved unchanged.

## Actual Completed Scientific Work

| Epoch | Update | Retrieval loss | Margin | Checkpoint |
|---:|---:|---:|---:|---|
| 5 | 380 | 2.1492986679 | 0.0983494669 | `p9ck_2f721927220ff60f811352a2` |
| 10 | 760 | 1.3162351847 | 0.1493447274 | `p9ck_cec2f045e616be320752c1d8` |
| 15 | 1,140 | 0.9153134227 | 0.1881786585 | `p9ck_b8ab1f9dd7da1ea84ed3268d` |

All validation events used 800 queries and 400 galleries with missing/duplicate
identities `0/0` and held-out evaluation consumption 0. Before failure, the
selector best was epoch 15 and patience was 0. These checkpoints are resumable
payload evidence only, not selected or accepted P9 checkpoints.

Training trace evidence through update 1,140 was finite:

- total loss: first `4.9441313744`, last `3.6685721874`, min/max
  `2.7280907631`/`8.8080081940`
- gradient norm min/max: `2.7106256485`/`9.7170867920`
- update wall median/p95/max: `0.6756`/`0.8574`/`1.3369` seconds
- queue at checkpoint epoch 15: count 8,192, pointer 7,424

The failure is observed at the scene-identity lookup boundary. This report does
not infer a scientific cause or alter cache/model/queue semantics.

## Resources and Durable Evidence

- Formal launch: 2026-08-31 16:06:15 KST
- Terminal failure: 2026-08-31 16:23:57 KST
- Target wall: 17 minutes 41 seconds
- Observed VRAM high-water marks: approximately 10.2 GiB (GPU 0) and 13.2 GiB
  (GPU 1)
- Observed rank RSS high-water: approximately 6.85 GiB per rank
- No OOM, NaN, Inf, cache corruption, swap-out event, or surviving GPU process
  was observed.

Untracked durable evidence includes the tmux log, attempt state, rank failures,
lock owner/heartbeat, checkpoint manifests/payloads, targets error metadata,
and the pre/post inventories. None are tracked in Git.

## Immutability

Post-run comparison passed for all pre-existing immutable inputs:

- production cache: 314,695 files, path/size/mtime changes 0
- existing model/authorization artifacts: SHA-256 changes 0
- main research target-store objects: SHA-256 changes 0
- old isolated store: path/size/mtime changes 0
- dissertation tracked files: SHA-256 changes 0
- Fuse source files: SHA-256 changes 0

The external additions are limited to the authorized failed attempt directory,
three atomic checkpoints, rank-failure records, terminal failure state,
versioned-store error metadata, logs, and audit evidence. No P1-P8 artifact,
production cache, superseded attempt evidence, or dissertation payload was
modified.

## Post-acceptance Work Not Run

No terminal acceptance exists, so no `shortcut = TRUE` no-op replay,
post-acceptance schema chain, full test suites, or publication of a selected
checkpoint was run. Running them cannot make a failed nonresumable formal
attempt acceptable and would not be a substitute for the required new runtime
audit.

## Prohibited-Work Accounting

- Other P9-A attempts: 0
- P9-B materialization/training: 0
- Selected-FM operation: 0
- Held-out evaluation queries: 0
- P10/P11/maintenance: 0
- Production-cache construction: 0
- Main research target execution: 0
- Existing immutable artifact mutation: 0

## Next Step

Do not resume, rerun, or accept `p9attempt_25b780995291c86ce49b2182`.
The next task must audit the scene-identity/queue contract that fails after the
epoch-15 checkpoint, repair terminal failure accounting, add a bounded
production-shaped gate that reaches this lookup boundary, then issue a new
runtime digest, authority, reservation, and attempt before any further formal
training.

## Prompt Summary

This work unit was authorized to execute exactly one corrected isolated formal
`cfg_main` attempt. It was monitored to terminal failure without rerun or
runtime modification, and all accepted upstream artifacts were preserved.
