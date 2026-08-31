# P9 Post-Training Checkpoint Candidate Linkage Recovery Authorization

## Verdict

`P9_POSTTRAINING_CHECKPOINT_CANDIDATE_LINKAGE_CORRECTION_AND_RECOVERY_AUTHORIZATION_PASS_PUSHED`

The failed formal trajectory is scientifically complete through its authorized
early-stopping boundary, but its original `FAILED_NONRESUMABLE` record remains
immutable. This publication authorizes only a separate, read-only terminal
recovery lineage. It does not authorize training, resume, DDP, validation,
evaluation, checkpoint writes, or GPU execution.

## Immutable Failed Lineage

- Authority/reservation/attempt/run: `p9a_9d6f0554553ac43371b47efd`,
  `p9res_0f5492c80e7c152e6c543012`,
  `p9attempt_a754afd14ac87287afb04029`, `p9run_6887930091dd2f2bfedc3c96`.
- Runtime digest: `219e8007b9d07e222c481eb28fe09ade5d58607db5a6351a9383be158941b2df`.
- Durable progress: epoch 125, update 9,500, 25 validation events and 25
  atomic checkpoints. Evaluation consumption was zero.
- The failed `attempt_state.json`, terminal record, checkpoints, traces, logs,
  stores, cache, P1--P8 artifacts, and dissertation were read-only inputs.

## Stopping Boundary

The canonical validation trace reconstructs best epoch 105: loss
`0.3806893528`, margin `0.2876026034`, checkpoint
`p9ck_42f7957d2ea998ac9e8ff705`.

Epochs 110, 115, 120, and 125 were four consecutive non-improvements. With
patience 4, early stopping at epoch 125/update 9,500 is exact; maximum-epoch
termination was not involved. The epoch-105 checkpoint payload SHA-256 is
`fdac720bff12fb25747f69977bc69c5fb28adbc4a73cabd879b1b57c47cc06b6` and its
manifest SHA-256 is retained in the external join audit.

## Linkage Defect And Correction

The original controller compared the best validation epoch directly to
`checkpoint_manifest.epoch`. A checkpoint created after validation epoch `N`
stores `progress.epoch = N + 1` as its resume cursor. Thus best validation
epoch 105 could not match the complete epoch-105 checkpoint, whose manifest
epoch is 106.

`scripts/p9_formal_training.py` now explicitly maps resume epoch to validation
epoch (`manifest_epoch - 1`) and rejects multiple candidates. The read-only
recovery implementation joins validation events to manifests using that
contract, payload/manifest hashes, exact lineage, state validation trace, and
update consistency; it does not infer from filenames or choose an epoch by
hand.

The immutable join produced 25/25 `EXACT_MATCH` rows, deterministic candidate
selection chose the epoch-105 checkpoint above, and repeated authorization
target execution skipped with zero builds.

## Recovery Lineage

- Recovery contract: `p9rec_d25c5db916ba77f8f9b08395`
- Recovery authority: `p9ra_2b5e0dc9eebb81c028fefedf`
- Recovery reservation: `p9rres_9a80e602179eb5b9c8321f46`
  (`AUTHORIZED_NOT_STARTED`)
- Recovery operation: `p9rop_3f91e67af1d45ff1e6209f6d`
- Recovery authorization acceptance: `p9rxacc_35b04a02e9188cd0f5e1361a`
- Recovery runtime digest: `e000245971a3dba7bc759bbfe8c14d0adc3b8e09c1c82573eda3154dfb43a5b6`
- Recovery-only script/store: `_targets_p9_recovery.R` and
  `/mnt/hdd002/dhnyu/fusedata/targets/fuse-p9-recovery-20260831`.

The recovery DAG contains authorization and read-only recovery artifacts only;
it has no import or invocation path to the formal trainer, `torchrun`, DDP,
optimizer, validation, cache construction, evaluation, or the main store.

## Validation And Immutability

- Focused recovery tests: 2 passed.
- Full Python suite: 290 passed.
- Python compilation, R parse, and recovery `tar_validate()`: passed.
- Recovery authorization first build: 2 targets; shortcut replay: 0 builds,
  0 rewrites.
- Production optimizer updates, validations, evaluation queries, checkpoint
  writes, DDP launches, and GPU processes during this work unit: all 0.
- Failed-run and production-cache pre/post inventory paths were preserved; no
  historical payload was modified.

## Next Authorized Command

The future recovery authorization must execute only the recovery terminal
target defined by the recovery DAG, after a separate work-unit preflight. It
must not invoke the formal training pipeline or reuse the failed reservation.

Prompt summary: audit a completed cfg_main trajectory, correct only its
post-training checkpoint-candidate linkage, and authorize deterministic
read-only terminal recovery without retraining.
