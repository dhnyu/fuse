# P9 cfg_main formal attempt execution

## Verdict

`P9_CFG_MAIN_FORMAL_ATTEMPT_BLOCKED`

The authorized terminal target did not reach the formal runner. No formal attempt started and no optimizer update occurred.

## Scope and time

- Work unit: execute exactly one formal P9-A `cfg_main` attempt.
- Preflight start: 2026-08-31 13:39 KST.
- Launch attempt: 2026-08-31 13:41:08 KST.
- Fail-closed termination: 2026-08-31 13:41:11 KST.
- Host: `songlab`.
- Durable session: `p9_cfg_main_formal`.
- Execution log: `/mnt/hdd002/dhnyu/fusedata/logs/p9_cfg_main_formal/20260831_133926_p9_cfg_main_formal.log`.
- Evidence root: `/mnt/hdd002/dhnyu/fusedata/tmp/fuse/p9_cfg_main_formal_20260831_133926/`.

## Canonical lineage

- Launch commit: `95be285cfd7eac1c5672b4e3c67f5fbb8bfa45aa`.
- Implementation commit: `c40c1adb302698195d111f48376644fcbef08e31`.
- Runtime digest: `d8379196a400bc590575c00b6953d046ae50dc3878cd37bbeb98aa1f6d7dff55`.
- Authority: `p9a_b295be97717efbd2305dd5a6`.
- Reservation: `p9res_51ed9e4731c21bda28d4d7a2`.
- Attempt: `p9attempt_f153ff8e7831effbf2f2d68a`.
- Production cache: `p9cache_f8b16c49f2c63216609b013b`.
- Cache acceptance: `p9ca_99725ef4c56f8b11b4d71935`.
- P8 parent: `p8acc_c9f16a07275aadfae928d329`.
- P7 runtime parent: `p7rta_c780441a553abe26772827d0`.
- P9 readiness: `p9ready_521c12a65d9b2984fac2cf11`.

## Preflight

All execution preflight gates passed before invoking `targets`:

- Fuse and dissertation were on `reduced`, clean, and synchronized at ahead/behind `0/0`.
- Fuse HEAD was the intended launch commit.
- The launch commit was a descendant of the implementation commit.
- The formal validator accepted the authority, reservation, `cfg_main` matrix row, production cache plan, categories, and the byte-identical descendant runtime tree.
- All 24 runtime files reproduced the authorized digest.
- The publication-only descendant changes were the corrected binding configuration, report, tests, and regenerated target-network HTML; no authorized runtime file differed.
- Reservation state was `AUTHORIZED_NOT_STARTED`; formal attempt started was false; optimizer updates, formal validations, checkpoints, and evaluation consumption were all zero.
- No output directory, partial run, duplicate attempt, active formal lock, P9 controller, DDP rank, or GPU compute process existed.
- Both RTX A6000 GPUs were visible and had approximately 48.5 GiB free each.
- The production cache plan and accepted indexes were readable.
- Filesystem headroom was approximately 19 TiB and inode utilization was 1%.
- Superseded authority `p9a_c16721ffbce259df3f723cdd` and reservation `p9res_c0f73b80e4f90ed3cc8a3346` remained preserved, unexecuted, and ineligible.

The accepted `cfg_main` row was read directly from `p8hm_f34f1666b62255babab0ae08`: d/d_c 64, four heads, K8 main profile, EMA 0.999, lambda_IP 1, dropout 0.2, AdamW, and peak learning rate 1e-3. The authority supplied the remaining formal trajectory contract: world size 2, global/per-rank batch 32/16, float32, 76 updates per epoch, at most 200 epochs/15,200 updates, validation every five epochs, and patience four.

## Exact launch

The command was executed inside the durable tmux session and not from an ephemeral executor:

```bash
FUSE_P9_FORMAL_RESERVATION_ID=p9res_51ed9e4731c21bda28d4d7a2 \
Rscript -e 'targets::tar_make(
  names = p9_cfg_main_attempt_acceptance,
  shortcut = TRUE,
  store = "/mnt/hdd002/dhnyu/fusedata/targets/fuse-research"
)'
```

The target process failed before scheduling `p9_cfg_main_formal_run`:

```text
cannot bootstrap target p9_cfg_main_formal_run because there is no record of
p9_cfg_main_formal_run the metadata. Run the pipeline with shortcut = FALSE to create it.
```

Exit status was 1. The tmux session ended normally after persisting the error and exit status.

## Root blocking condition

`shortcut = TRUE` cannot bootstrap the newly declared formal-run target because that target has no prior metadata record. The authorized command selects only the terminal acceptance target, so the missing upstream formal-run record blocks traversal before the R target command calls `p9_execute_reserved_formal_run()`.

This is an execution-boundary/targets-bootstrap defect, not a scientific training failure. The work-unit instructions prohibited changing the target graph or retrying with `shortcut = FALSE`, so no repair or alternate invocation was attempted.

## Formal state after termination

- Reservation: unchanged `AUTHORIZED_NOT_STARTED`.
- Formal run identity: not created.
- State transitions to `STARTING` or `RUNNING`: 0.
- Lock acquisitions: 0.
- Controller/DDP processes: 0.
- Optimizer updates: 0.
- Formal validation queries/galleries consumed: 0/0.
- Held-out evaluation consumption: 0.
- Checkpoints and checkpoint candidates: 0.
- Terminal execution or attempt acceptance artifacts: 0.
- Other P9-A/P9-B, P10/P11, evaluation, and maintenance executions: 0.
- Remaining GPU processes: 0.
- Remaining formal locks: 0.
- Exact resume eligibility: not applicable because no run began.

`targets::tar_meta()` contains the corrected reservation record only. It contains no record for the formal run, validation trace, checkpoint candidates, selected checkpoint, terminal execution, or attempt acceptance.

## Immutability audit

- Pre-existing P1-P8/model authorization files: 2,426/2,426 SHA-256 exact.
- Pre-existing target-store objects: 1,266/1,266 SHA-256 exact.
- Production-cache inventory: 314,695/314,695 path/size/mtime records exact.
- Fuse tracked files before the report: 533/533 exact.
- Dissertation tracked files: 63/63 exact.
- Production-cache mutation: 0.
- Existing checkpoint mutation: 0.
- Superseded authorization artifact mutation: 0.
- Unrelated target-store object mutation: 0.

The only runtime outputs are the untracked execution log and read-only inventory evidence. No cache, checkpoint, lock, credential, target-store object, or temporary scientific artifact is tracked by Git.

## Tests and checks

The formal validator passed immediately before launch and proved the intended launch commit's runtime-tree compatibility. Full suites were not rerun after the bootstrap failure because terminal acceptance never occurred and no tracked runtime code or scientific artifact changed. The immediately preceding reauthorization publication at this exact launch commit had passed 84 Python tests, the full R suite with exactly three documented skips, schemas, AST/R/YAML/JSON parsing, `tar_validate()`, target-network validation, and read-only Typst compilation.

Post-failure checks performed in this work unit:

- reservation canonical readback: unchanged;
- process/GPU/lock inspection: zero formal processes and locks;
- formal target metadata inspection: no run/downstream records;
- model, target-store, cache, Fuse, and dissertation inventory comparisons: exact;
- worktrees: clean before this report.

## Publication and remaining work

This report is a non-runtime publication descendant of the actual launch commit. It does not alter the authorized 24-file runtime digest.

Before `cfg_main` can be attempted again, a separately authorized correction work unit must resolve the formal target bootstrap contract and revalidate the exact allowed invocation. It must decide whether the approved execution command should use `shortcut = FALSE` for this explicit allowlisted target or whether the DAG needs a safe metadata/bootstrap target that does not start training. The current reservation must remain `AUTHORIZED_NOT_STARTED`; no replacement attempt or seed is warranted because no formal attempt started.
