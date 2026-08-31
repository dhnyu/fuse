# P9 cfg_main isolated formal execution

## Verdict

`P9_CFG_MAIN_ISOLATED_FORMAL_EXECUTION_FAILED_NONRESUMABLE`

The isolated execution pipeline passed repository, lineage, cache, runtime-tree,
reservation, and closure preflight. The formal controller then created the
preassigned run and started two DDP ranks. Both ranks failed before model
construction completed and before the first optimizer update because the formal
runner expected a vocabulary wrapper that the accepted category loader does not
return. The durable lock record classifies the attempt as
`FAILED_NONRESUMABLE`. This attempt was not retried, resumed, accepted, or
replaced in this work unit.

## Purpose and scope

- Execution date: 2026-08-31 (Asia/Seoul)
- Repository: `/members/dhnyu/fuse`
- Branch: `reduced`
- Actual launch commit: `f6fd8f470a4b5397dc67965ff46bac2f0fffabc5`
- Implementation commit: `c330e227dfe224a1c654526f62a9ad7165d88a69`
- Isolated pipeline: `_targets_p9_formal.R`
- Isolated store: `/mnt/hdd002/dhnyu/fusedata/targets/fuse-p9-formal`
- Main research pipeline/store execution: 0
- Prompt scope: execute only the authorized isolated `cfg_main` formal attempt,
  monitor it to a terminal state, and publish only after all acceptance gates.

## Canonical lineage

| Item | Identity |
|---|---|
| Formal authority | `p9a_2c67a3971b785f7049cb3d65` |
| Reservation | `p9res_0ab5e0235bc36811d8855050` |
| Preassigned attempt | `p9attempt_074b247e347f851387606da0` |
| Derived run | `p9run_f592f6b25fb56be8807c16cb` |
| Authorization acceptance | `p9xacc_12d457b5127e3fd242d07b3d` |
| Runtime digest | `b0395143a364d26bb1e121524e69c75cc0f98ce12aa5ecdefacab0f9af58f9f6` |
| Production cache | `p9cache_f8b16c49f2c63216609b013b` |
| Cache acceptance | `p9ca_99725ef4c56f8b11b4d71935` |
| P8 acceptance | `p8acc_c9f16a07275aadfae928d329` |
| P7 runtime acceptance | `p7rta_c780441a553abe26772827d0` |
| P9 readiness | `p9ready_521c12a65d9b2984fac2cf11` |
| Dissertation | `ad8c8b5c17c5ca72dce7f30c2eb283f6041dbc9a` |

All immutable roots and the accepted `cfg_main` row passed canonical readback.
The formal validator accepted the authority, reservation, launch descendant,
runtime digest, cache acceptance, and scientific configuration before launch.

## Pre-launch gates

- Fuse and dissertation: `reduced`, clean, synchronized `0/0`.
- Fuse HEAD: exact expected launch commit.
- Runtime digest: exact.
- Reservation before launch: `AUTHORIZED_NOT_STARTED`.
- Existing run/output/duplicate attempt: 0.
- Active formal controller/DDP/GPU process/lock: 0.
- GPUs: two RTX A6000 devices visible, each with approximately 48.5 GiB free.
- Filesystem: approximately 19 TiB free; inode use 1%.
- Cache: 314,695 files and 391,466,804,516 bytes.
- Six canonical cache manifests: size and SHA-256 exact.
- Cache entry contract: 78,672 entries.

The full isolated pipeline declares 25 targets and 48 edges because it includes
one disconnected current inventory leaf. The terminal target's complete
transitive closure is the authoritative 24 targets and 47 edges. Exactly the six
Layer C formal targets were outdated. Unexpected scientific producers, cache
builders, other P9 configurations, P9-B, P10/P11, evaluation, maintenance, and
main-store dependencies in the closure were all zero.

Machine-readable closure evidence:
`/mnt/hdd002/dhnyu/fusedata/tmp/fuse/p9_cfg_main_isolated_formal_20260831_142932/prelaunch_closure_audit.json`.

## Launch

- tmux session: `p9_cfg_main_isolated_formal`
- log: `/mnt/hdd002/dhnyu/fusedata/logs/p9_cfg_main_isolated_formal/20260831_143159_p9_cfg_main_isolated_formal.log`
- tmux pane PID: `1000384`
- formal controller PID: `1000602`
- rank 0 PID: `1000797`
- rank 1 PID: `1000798`
- host: `songlab`
- launch time: 2026-08-31 14:31:59 KST
- failure recorded: 2026-08-31 14:32:10 KST
- target wall: 10.3 seconds

Command:

```bash
FUSE_P9_FORMAL_RESERVATION_ID=p9res_0ab5e0235bc36811d8855050 \
Rscript -e 'targets::tar_make(
  script = "_targets_p9_formal.R",
  names = p9_cfg_main_attempt_acceptance,
  shortcut = FALSE,
  store = "/mnt/hdd002/dhnyu/fusedata/targets/fuse-p9-formal"
)'
```

Layer A/B targets remained skipped. `targets` dispatched only
`p9_cfg_main_formal_run`; no downstream formal artifact target completed.

## Failure boundary

The controller acquired the single duplicate-attempt lock, created run
`p9run_f592f6b25fb56be8807c16cb`, persisted `STARTING` and `RUNNING`, and
launched exactly two DDP ranks. Both ranks failed in `model_state()` before the
model, optimizer, scheduler, or queue was constructed:

```text
KeyError: 'fields'
scripts/p9_formal_training.py:116
sizes = {key: len(value["values"]) + 1
         for key, value in values["vocabulary"]["fields"].items()}
```

`build_vocabulary()` in `python/p6_data.py` returns a direct mapping from each
accepted categorical attribute to `keys`, `mapping`, `missing`, `mask`, and
`size`; it has no top-level `fields` member and no per-field `values` member.
The accepted `spatial_categories.json` itself contains `entries`,
`missing_markers`, `oov_policy`, `ordering`, `reserved_tokens`, `schema_version`,
and `sources`. Thus the failure is a formal-runner interface defect, not missing
accepted vocabulary data or cache corruption.

The pre-execution `validate` mode did not construct the model and therefore did
not exercise this interface. Existing tests likewise did not gate this exact
production model-construction path.

## Formal state

| Measure | Result |
|---|---:|
| Formal attempt starts | 1 |
| Run identities | 1 |
| DDP ranks launched | 2 |
| Optimizer updates | 0 |
| Formal validation events | 0 |
| Validation queries consumed | 0 |
| Evaluation queries consumed | 0 |
| Checkpoints | 0 |
| Acceptance artifacts | 0 |

The durable owner and heartbeat records both end in
`FAILED_NONRESUMABLE` and record lock release at 14:32:09 KST. No controller,
DDP rank, GPU compute process, or active kernel lock remains. The zero-byte lock
path and durable owner/heartbeat evidence were intentionally preserved and were
not deleted.

`running_state.json` remains at `RUNNING`; the exception path updates only the
lock owner and heartbeat records. This inconsistent persisted state is a second
infrastructure defect. The immutable reservation publication still says
`AUTHORIZED_NOT_STARTED`; it is an authorization artifact rather than a mutable
run ledger and was not modified. Neither file was rewritten in this work unit.

Exact resume is not authorized: the durable terminal state is
`FAILED_NONRESUMABLE`, no checkpoint exists, and the accepted contract prohibits
restarting this attempt from update zero.

## Scientific execution results

Training and validation trajectories do not exist. Completed epochs and
optimizer updates are zero; there is no selected or terminal checkpoint, no
retrieval loss or margin, and no early-stopping decision. Peak VRAM and update
latency are not reportable because the failure occurred before model allocation
and the first update. No held-out evaluation identity was accessed.

## Immutability audit

- Production cache: all 314,695 paths, sizes, and mtimes unchanged; total bytes
  remain 391,466,804,516; all six canonical manifest SHA-256 values unchanged.
- Existing model and accepted artifact payload hashes: unchanged.
- Main research target-store objects: unchanged.
- Dissertation tracked files: unchanged and clean.
- Fuse tracked files: unchanged before creation of this report. Python bytecode
  produced by imports was restored/removed using the clean preflight inventory.
- Expected external additions: one `running_state.json`, durable terminal lock
  provenance, isolated target error metadata/workspace, and the runtime log.
- Production cache construction, P1-P8 rebuild, other P9-A/P9-B work,
  selected-FM, P10/P11, evaluation, and maintenance: 0.

Evidence inventory root:
`/mnt/hdd002/dhnyu/fusedata/tmp/fuse/p9_cfg_main_isolated_formal_20260831_142932`.

## Validation and no-op disposition

- Formal preflight validator: PASS.
- Isolated closure audit: PASS.
- Cache canonical readback: PASS.
- Formal target: ERROR before optimizer initialization.
- Terminal artifact/schema readback: not possible; artifacts were not produced.
- `shortcut = TRUE` no-op replay: not run because no acceptance exists and a
  second launch under a failed non-resumable attempt is prohibited.
- Post-acceptance Python/R/full validation: not run because the acceptance gate
  was not reached.

The isolated target store records `p9_cfg_main_formal_run` as errored. This is
preserved as evidence; no target metadata was fabricated or forced current.

## Required next step

Do not rerun or resume `p9attempt_074b247e347f851387606da0`. A separate
authorized infrastructure-correction work unit must:

1. correct the formal runner to consume the canonical vocabulary mapping;
2. add a production-shaped, optimizer-free model-construction gate that exercises
   the same accepted category file and model path;
3. persist a coherent failed terminal state outside only the lock record;
4. audit the lack of `destroy_process_group()` cleanup on initialization failure;
5. publish a new runtime digest, authority, reservation, and attempt after tests.

The accepted production cache and P7/P8 scientific lineage do not require
republication based on this failure.
