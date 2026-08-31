# P9 global batch uniqueness correction and reauthorization

## Verdict

`P9_PROVED_GLOBAL_BATCH_UNIQUENESS_CORRECTION_AND_REAUTHORIZATION_PASS_PUSHED`

## Proven Scope

The preserved historical epoch-16 failure remains unexplained and immutable.
Its operands were unavailable and its checkpoint replay did not reproduce the
exception. Separately, the prior full-horizon audit proved that legacy rotating
padding could append a scene already present in the final partial collective.
The correction only filters final-batch members from the deterministic padding
rotation before selecting eleven padding scenes.

The permutation, population (2,421), seed, PCG64 epoch RNG, global batch 32,
rank slices 16/16, 76 updates per epoch, cache, augmentation, model, loss,
queue capacity, optimizer, scheduler, validation, and checkpoint selection are
unchanged. Only padded-scene membership changes when collision avoidance is
necessary.

## Sampler Contract and Audit

Contract: `config/p9_global_batch_sampler_contract.json`.

- Former proved boundary: epoch 20, batch 75; legacy padding could collide with
  the final partial collective. It is not asserted to explain epoch 16.
- Corrected full horizon: 15,200 global batches and 486,400 positions.
- Batch-size, within-collective duplicate, missing/duplicate lookup, rank-size,
  rank-overlap, gather-order, cursor, queue-alignment, and out-of-population
  violations: all 0.
- Padding exposure over 200 epochs: min 0, max 2, mean .9087154, SD .4898078,
  median 1, p95/p99 2, range 2, never padded 411.
- External audit: `/mnt/hdd002/dhnyu/fusedata/tmp/fuse/p9_batchuniq_20260831_170053/corrected_full_horizon_audit.json`.

## New Execution Generation

- Runtime digest: `219e8007b9d07e222c481eb28fe09ade5d58607db5a6351a9383be158941b2df`
- Store: `/mnt/hdd002/dhnyu/fusedata/targets/fuse-p9-formal-p9gen_batchuniq_20260831`
- Supersession: `p9sup_6163ebef21b89336a249d08e`
- Authority: `p9a_9d6f0554553ac43371b47efd`
- Reservation: `p9res_0f5492c80e7c152e6c543012` (`AUTHORIZED_NOT_STARTED`)
- Attempt: `p9attempt_a754afd14ac87287afb04029`
- Authorization acceptance: `p9xacc_2b20655ebac81d058ecb4770`

The new runtime retains rank-scoped failure diagnostics and checkpoint-first
terminal accounting. The optimizer-free two-rank startup gate passed with zero
optimizer, EMA, scheduler, checkpoint, validation, and evaluation activity.
Layer A/B first publication completed; replay skipped with no builds.

## Non-execution and Preservation

No formal attempt/run identity was created, no production optimizer update,
formal validation, held-out evaluation, formal checkpoint, cache write, or
historical evidence mutation occurred. The historical failed attempt remains
nonresumable and ineligible.

## Future Formal Command

```bash
FUSE_P9_FORMAL_RESERVATION_ID=p9res_0f5492c80e7c152e6c543012 \
Rscript -e 'targets::tar_make(script = "_targets_p9_formal.R", names = p9_cfg_main_attempt_acceptance, shortcut = FALSE, store = "/mnt/hdd002/dhnyu/fusedata/targets/fuse-p9-formal-p9gen_batchuniq_20260831")'
```
