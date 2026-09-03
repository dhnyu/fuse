# P9-B DS Raster Cache Optimization and Restart

## Verdict

`P9_B_DS_RASTER_CACHE_OPTIMIZATION_PASS_PUSHED`

`P9_B_DS_LIKE_RESTARTED_WITH_DETERMINISTIC_CACHE`

- Executed at: `2026-09-03T23:45:54+09:00`
- Starting Fuse commit: `c4e50c7ed1f262c6ea6ad1c4eabd965b3bc1bfb9`
- Optimization commit: `07ac7715eb617e9b0f0eece62f9e73433fada1ff`
- Branch: `reduced`; optimization commit pushed at ahead/behind `0/0`
- Dissertation: unchanged at `ad8c8b5c17c5ca72dce7f30c2eb283f6041dbc9a`

## Purpose and scope

The running dynamic-raster DS-like trajectory was intentionally abandoned because
online Shapely rasterization made its median epoch about 9 times slower than the
preceding P9-B families. This unit preserved that evidence, routed DS through the
already accepted deterministic raster cache, proved scientific equivalence, ran a
bounded two-GPU update pilot, committed and pushed the optimization, and launched
one fresh epoch-zero DS-like run. It did not execute held-out evaluation.

## Abandoned dynamic-raster trajectory

- Authority: `p9authv2_aa53f2804acb367809fc2961`
- Run: `p9runv2_d5de7de9e82ab7852a20a2dc`
- Replay: `IN_PROGRESS / BLOCKED / FORBIDDEN_POLICY`
- Terminal reason:
  `OPERATOR_REQUESTED_PERFORMANCE_REMEDIATION_DYNAMIC_DS_RASTERIZATION`
- Last observed progress: epoch 76 complete, update 5,776; epoch 77 had started.
- Latest durable checkpoint: completed epoch 75, resume epoch 76, update 5,700.
- Validation/checkpoint pairs: 15/15.
- Best at interruption: `p9ck_17223b27361d4e2a710f07c8`, epoch 75,
  retrieval loss `0.4761040211`, margin `0.2237681001`.
- Median epoch wall: `397.5630 s`; last-ten median: `396.5431 s`; p95:
  `474.8862 s`.

The controller appended one immutable `TRAINING_INTERRUPTED` event and closed the
ledger only after the worker/controller processes had exited. Existing events,
checkpoints, validation records, and payloads were not rewritten. Resume is
explicitly forbidden because the implementation hash changed.

### Validation trajectory at abandonment

| Epoch | Update | Retrieval loss | Margin | Checkpoint |
|---:|---:|---:|---:|---|
| 5 | 380 | 2.4139604568 | 0.0583648384 | `p9ck_8c889b4196c2107c71b44642` |
| 10 | 760 | 1.6738936901 | 0.0894584954 | `p9ck_2e130ad79d37e73988651868` |
| 15 | 1,140 | 1.2039667368 | 0.1212927848 | `p9ck_96659e5585a4b27c36641fd8` |
| 20 | 1,520 | 1.0120649338 | 0.1407609582 | `p9ck_7ddb2df6f479561a42b8fdff` |
| 25 | 1,900 | 0.8980486393 | 0.1560929716 | `p9ck_a98cb6cfdfe507503db30c37` |
| 30 | 2,280 | 0.8172449470 | 0.1681413651 | `p9ck_238dfc65c4ef0b8bf2a0901c` |
| 35 | 2,660 | 0.7522854805 | 0.1762357950 | `p9ck_33f99f55831feb4831cec24c` |
| 40 | 3,040 | 0.6476706862 | 0.1892819852 | `p9ck_8c169a25d6de13127e0f3e05` |
| 45 | 3,420 | 0.6187748909 | 0.1945217252 | `p9ck_05373da35458ec7b65e4dea5` |
| 50 | 3,800 | 0.5670741796 | 0.2028100193 | `p9ck_1eb3b7dd57a2d5e6c43e1063` |
| 55 | 4,180 | 0.5470731854 | 0.2073675096 | `p9ck_0ba3800cbfb3661c866f0db5` |
| 60 | 4,560 | 0.5350110531 | 0.2088247240 | `p9ck_e6c878d64690ed79c5e07643` |
| 65 | 4,940 | 0.5087287426 | 0.2155608237 | `p9ck_3dc4ef5692b5a0afb8cfa9fa` |
| 70 | 5,320 | 0.5033189058 | 0.2171713263 | `p9ck_51f061c4cbadc503154dead4` |
| 75 | 5,700 | 0.4761040211 | 0.2237681001 | `p9ck_17223b27361d4e2a710f07c8` |

## Rasterization contract and cache identity

The audited online function was `python/p9_model_families.py::ds_raster_from_batch()`.
For each exact augmented or fixed-validation view it deterministically builds a
contiguous `float32 [26,100,100]` tensor over `[-250,250] x [-250,250]` metres:

1. building polygon intersection area divided by the 25 square metre cell area,
   accumulated and clipped to one;
2. binary road/cell intersection;
3. `log1p` POI count in the containing cell;
4. 22 land-cover fractions, with invalid/intentional mask cells zeroed; and
5. complete-support 17x17 DEM resampled at 100x100 cell centres by bilinear
   interpolation.

Empty vector modalities produce zero channels. Entity and part/ring ordering comes
from the immutable prepared view; polygon holes and road intersections use the same
Shapely operations as cache construction. No approximation was introduced.

The production cache already contained the required materialization, so regeneration
and cache writes were both zero:

- Cache ID: `p9ds_1e26585c61122cf7c758088a`
- Contract: `p8ds_73137985bd6b172f6711a062`
- Manifest SHA-256:
  `8880399f947c512500b69391ca6a6eb8a64db040393e7ed09b16e2be1fad873a`
- Content SHA-256:
  `1e26585c61122cf7c758088a4af1b6e3f3c09b05655c46f9a066f5c7b8036e72`
- Entries: 78,672: main 38,736; weak 19,368; strong 19,368;
  validation query 800; validation gallery 400.

`DSRasterCacheReader` verifies the production binding, manifest identity, contract,
source cache key, physical role, scene/view identity, path containment, file size,
payload hash, internal manifest, raw tensor hash, shape, dtype, layout, and finite
values. Lookup is exact; missing/stale/corrupt evidence raises a stable error and
there is no online-raster fallback. Large payloads remain immutable external cache
objects and are loaded with restricted `weights_only=True` plus mmap/LRU reuse.

## Exact equivalence evidence

Production fixtures covered mixed scenes, no-road, building-only, POI-only,
all-empty vector channels, road-plus-POI, road-only, weak/main/strong views, and
fixed validation query/gallery inputs. Cached tensors were bitwise equal to the old
online output. Reordered batch lookup preserved exact requested order.

An identical batch also produced equal model inputs, forward output, loss, backward
gradients, one optimizer update, queue state, and sampler state. Corrupt payload,
stale contract, source mismatch, shape mismatch, duplicate identity, wrong role,
and missing lookup were rejected. The scientific configuration, root seed,
augmentation, model, objective, selector, and stopping contract did not change.

## Bounded two-GPU pilot

The noncanonical pilot used actual `cmp_ds_like`, production cache, two GPUs, global
batch 32, and four optimizer updates. It performed no validation, evaluation,
checkpoint publication, finalization, or acceptance.

| Measure | Result |
|---|---:|
| Global updates | 4 |
| Queue count/pointer | 256 / 256 |
| Sampler cursor | 4 |
| Cache misses per rank | 128 |
| Median update wall | 0.5431 s |
| p95 update wall | 1.1677 s including first cold update |
| Estimated epoch wall | 41.2817 s |
| Conservative throughput | 46.114 scenes/s |
| Peak allocated VRAM | 215,932,416 bytes |
| Peak rank RSS | 2,876,280,832 bytes |

The estimated cached epoch is about `9.6x` faster than the observed dynamic-raster
median. GPU monitoring sampled initialization and the short update window together:
mean utilization was 3.1%/3.7%, active-sample maximum was 100% on both GPUs, and
reported memory maxima were 743/755 MiB. The low whole-process mean is not presented
as steady-state utilization.

## Controller interruption correction

The operator stop exposed a bookkeeping defect: a newer `EPOCH_STARTED` event was
mistaken for an exact-resume boundary and lacked `completed_epoch`. The controller
now obtains resumability only from the latest committed
`VALIDATION_CHECKPOINT_COMMITTED` event. A regression proves that later progress and
epoch events cannot advance the restorable boundary past epoch 75/update 5,700.

## Fresh formal restart

- Authority: `p9authv2_8610966f649fa6ae8b806afc`
- Authority file SHA-256:
  `ef034a439732db5adbd6f414042f45c6b8b6b24d1f759688ed9875ab4e44a66b`
- Scientific implementation hash:
  `07bb45b0ea1f57d7b968fba8acb9d25f6a3e6b91cd0a99f1ff3686a0e78c0e67`
- Run: `p9runv2_c63dfaa65295f1a2727b15a6`
- Duplicate-run key:
  `f645084387a95622e10bf907e3703c8ffd87e7edeab075919f25a4938def0bec`
- Launch observation: `RUNNING / IN_PROGRESS`, epoch 2/update 152, zero
  validation/checkpoints at that early observation.
- Cache activation: both worker process maps contained mmap-backed files under the
  exact accepted `ds/entries/` namespace.
- tmux session: `p9b_ds_cache_restart_20260903`
- Campaign root:
  `/mnt/hdd002/dhnyu/fusedata/runtime/p9_b_campaigns/20260903_0539_cfgd128`
- Log:
  `/mnt/hdd002/dhnyu/fusedata/runtime/p9_b_campaigns/20260903_0539_cfgd128/ds_cache_restart.log`
- Reattach: `tmux attach -t p9b_ds_cache_restart_20260903`

Launch command:

```bash
env PYTHONDONTWRITEBYTECODE=1 NCCL_P2P_DISABLE=1 NCCL_IB_DISABLE=1 \
  python -u scripts/p9_b_campaign.py \
  --campaign-root /mnt/hdd002/dhnyu/fusedata/runtime/p9_b_campaigns/20260903_0539_cfgd128 \
  --plan /mnt/hdd002/dhnyu/fusedata/models/reduced/p9_v2/canonical/p9_b_plans/p9bplan_e36f7c9c5069a504eb31a9ef.json \
  --contract config/p9_v2_training_controller.yml
```

The campaign restored and resolver-validated the six accepted-prefix results, did
not rerun A1-A5 or SSV-like, and generated the fresh authority/run only after the
optimization commit was pushed. The previous DS run is not a completed prefix and
was not resumed.

## Validation

- Focused DS cache/controller/remediation: 55 passed, 0 failed.
- Combined V2 and P9-B Python regression: 372 passed, 0 failed.
- Earlier broad P9 Python regression in this unit: 552 passed, 58 skipped, 0 failed.
- R target/retirement/infrastructure tests: 27 passed, 0 failed.
- `tar_validate()`: main, formal, recovery, and isolated V2 training scripts passed;
  no target execution was requested by validation.
- JSON schema documents: parse pass; Draft 2020-12 tests are included in the V2
  regression.
- YAML configuration parse: 52 passed.
- Modified Python compile and R parse: passed.
- `git diff --check`: passed before optimization commit.

## Immutability and prohibited work

The seven pre-restart acceptance-directory inventory hashes (full `cfg_d128` plus
six completed P9-B configurations) were recorded and remained unchanged during the
optimization and launch. The cfg_d128 acceptance inventory digest was
`8d0453acb66143011fefb9ac323cdf98045ef0853590aa0b255e934ec6f46499`.
The retirement manifest remained
`4fd252ecfefa7436b0665b97cabe5976f3000a827d8ad229d8f0a17b161aac91`.
The historical v1 source inventory remains
`282e8eb48ac5ae9efeabb5d535707e1e9273d3bfd803ec3b8c03f9b74063065c`.

| Activity | Count |
|---|---:|
| Existing production cache regeneration/write | 0 |
| A1-A5 or SSV-like reruns | 0 |
| Held-out evaluation | 0 |
| P10/P11 | 0 |
| New P9-A or selected-FM run | 0 |
| V1 execution | 0 |
| Historical/cfg_d128/completed-P9-B mutation | 0 |
| Dissertation mutation | 0 |
| Noncanonical pilot optimizer updates | 4 |
| Abandoned DS trajectory resumes | 0 |
| Fresh cached DS formal runs | 1 |

## Remaining risk and next action

The restarted DS-like trajectory is running and has not yet reached its first formal
validation boundary. Completion, bundle/finalization/acceptance publication, and
resolver verification remain pending and must be audited without starting held-out
evaluation. The exact next work unit after canonical DS completion is
`P9_ABLATION_COMPLETION_AND_HELDOUT_READINESS_AUDIT`.

## Input prompt summary

The work unit requested graceful isolation of the slow DS-like run, immutable
preservation of its evidence, exact deterministic per-view DS cache materialization,
online/cache scientific equivalence, a bounded two-GPU performance pilot, and a
fresh epoch-zero DS-like restart from a pushed implementation without held-out
evaluation.
