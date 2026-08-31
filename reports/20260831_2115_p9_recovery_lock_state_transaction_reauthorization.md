# P9 Recovery Lock And State Transaction Reauthorization

## Verdict

`P9_RECOVERY_LOCK_STATE_TRANSACTION_IMPLEMENTATION_AND_REAUTHORIZATION_PASS_PUSHED`

## Corrected Boundary

The former recovery lineage `p9ra_8e32bacc3917acd1a91921c4` /
`p9rres_63586f0a27e1402f54bfa32b` lacked a kernel-owned recovery transaction
lock. It is preserved and superseded by
`p9rsup_d2c160d5a8bacc41e70f5417`; it remains unstarted and ineligible.

## Lock And Transaction

`python/p9_recovery_transaction.py` implements a recovery-only nonblocking
`fcntl.flock()` namespace under
`/mnt/hdd002/dhnyu/fusedata/runtime/p9_recovery_locks/<duplicate-key>.lock`.
Owner and heartbeat JSON are atomically published evidence, not ownership; the
live descriptor owns the kernel lock. The duplicate key binds authority,
reservation, operation, failed formal lineage, immutable candidate/selection
inputs, runtime/DAG digests, and terminal target.

The terminal controller uses states `ACQUIRING_LOCK`, `STARTING`,
`DERIVING_CANDIDATES`, `SELECTING_CHECKPOINT`,
`STAGING_TERMINAL_RECOVERY`, `STAGING_ACCEPTANCE`, `COMMITTING`,
`RECOVERY_ACCEPTED`, and `RECOVERY_FAILED_NONMUTATING`. It stages the terminal
and acceptance pair plus a transaction manifest on one filesystem and commits
with one directory rename. It never opens formal-training locks.

Focused process-level lock testing produced one winner and one
`DUPLICATE_OPERATION_ACTIVE` loser. The winner released the kernel lock on
exit. No production recovery target was selected.

## New Recovery Lineage

- Supersession: `p9rsup_d2c160d5a8bacc41e70f5417`
- Authority: `p9ra_7de9e3bb263c254eb070c8ef`
- Reservation: `p9rres_05b0790d0b3110784b6e8bbf` (`AUTHORIZED_NOT_STARTED`)
- Operation: `p9rop_c8c3e9fec074ec2170e0fa2b`
- Authorization acceptance: `p9rxacc_a12cdc5aa622770a2130663b`
- Runtime digest: `e420ae7da4a7f3be4b233385fde4f35396bfbefd11ced0cd93737f0fa8d821b7`
- DAG digest: `9df62892796b01365a61ba2c5ff10605ebb2b51d64406e1461bb11264205d602`
- Store: `/mnt/hdd002/dhnyu/fusedata/targets/fuse-p9-recovery-lockstate-20260831`

The immutable source remains the failed formal run at epoch 125/update 9,500,
with 25/25 exact joins. The deterministic selector remains
`p9ck_42f7957d2ea998ac9e8ff705`.

## Prohibitions And Validation

Focused recovery tests (3), Python compilation, R parsing, recovery
`tar_validate()`, and authorization publication passed. Production recovery
operations/acceptances, optimizer/EMA/scheduler updates, validation,
evaluation, checkpoint writes, DDP, GPU work, and historical mutations were
all zero.

## Future Command

```bash
FUSE_P9_RECOVERY_RESERVATION_ID=p9rres_05b0790d0b3110784b6e8bbf \
Rscript -e 'targets::tar_make(
  script = "_targets_p9_recovery.R",
  names = p9_cfg_main_recovery_acceptance,
  shortcut = FALSE,
  store = "/mnt/hdd002/dhnyu/fusedata/targets/fuse-p9-recovery-lockstate-20260831"
)'
```
