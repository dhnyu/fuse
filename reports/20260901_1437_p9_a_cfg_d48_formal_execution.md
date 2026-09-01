# P9-A `cfg_d48` Formal Execution

## 1. Verdict

`P9_A_CFG_D48_FORMAL_EXECUTION_PASS_PUSHED`

- Work unit: the first native P9 v2 formal production training run, restricted to `cfg_d48`.
- Execution date: 2026-09-01 Asia/Seoul.
- Starting Fuse lineage: `f3edb2964ee0ad675771fc7578c3609c375b6661` on `reduced`.
- Dissertation lineage: `ad8c8b5c17c5ca72dce7f30c2eb283f6041dbc9a`, unchanged.
- Prompt scope: one `cfg_d48` run through training, bundle, finalization, acceptance, eligibility, and resolver; no other scientific execution.

## 2. Repository And Preflight

The starting Fuse and dissertation trees were clean and synchronized with origin at 0/0. The V2-H remediation report and implementation, P8 experiment plan, current P9 v2 blueprint, V2-G/V2-I evidence, and active dissertation methodology were read before authority publication.

Pre-authority checks passed for the `reduced` branch, exact dissertation commit, V1 retirement manifest `p9ret_7921290e923f5d879e6d84c1`, P8 acceptance, production-cache acceptance, fixed validation identities, augmentation identities, zero evaluation ancestry, two RTX A6000 devices, NCCL initialization, writable runtime space, and the isolated nine-target closure. No prior canonical `cfg_d48` acceptance existed.

One clean-tree preflight initially rejected generated Python bytecode before any run ledger or optimizer update existed. The bytecode was removed and the same content-addressed authority/run was invoked with bytecode writing disabled. This was a fail-closed startup retry, not a second scientific run.

## 3. Scientific Contract

- P8 configuration: `cfg_d48`
- P8 scientific hash: `c155d758c8e03f8635874bb259a7d4ab15f1c4280a773112c7c4e5d0ef8d625e`
- Factor: latent dimension only
- `d = 48`, `d_c = 48`, heads `4`, head dimension `12`
- `K = 8`, main augmentation, EMA `0.999`, `lambda_IP = 1`, peak LR `1e-3`
- Global/per-rank batch: `32 / 16`; world size `2`
- Maximum trajectory: 200 epochs; 76 updates per epoch
- Validation cadence: every 5 completed epochs
- Selection: `p9-selection-v2.1.0`; patience 4 retrieval-loss non-improvements

The OFAT comparison against `cfg_main` differed only in `d`, `d_c`, and their derived FFN/per-head dimensions. The production original-scene, K=8 augmentation, geometry, preprocessing, and fixed-validation artifacts were reused. No bulk cache was generated.

## 4. Authority And Run

| Artifact | Identity / hash |
|---|---|
| Authority | `p9authv2_d3ba1eb1b8204953e4f9292c` |
| Authority SHA-256 | `d3ba1eb1b8204953e4f9292c0d1e1761ea38a5a36985f28230660e33abb6d84e` |
| Run | `p9runv2_79ab1abc43fb8e2ea13b8ce6` |
| Scientific run key | `93d6c8f487e1dee6851cd09734e1592e8787329686aec126fb69bdc80e9f92e0` |
| V2 scientific config SHA-256 | `ae39d906d886990aef77ead976ccb72a6fe05969159c9a30b1fe848abb4ef05d` |
| Implementation SHA-256 | `975a90f8e029fd8690e9cf9ad025bf379e7cdbcffdf82d5f6d84a3789b75835a` |
| Root seed | `537571499` |

Exactly one formal authority and one deterministic production run identity were created. The worker/controller path used two-rank NCCL/DDP, FP32, deterministic algorithms, AdamW, the accepted scheduler, EMA, queue, sampler, validation, and the controller-owned request/commit/ACK protocol.

## 5. Training Execution And Runtime

- Ledger start: `2026-09-01T03:14:37.987401Z`
- Scientific completion: `2026-09-01T05:21:59.315081Z`
- Training wall: `7,641.33 s` (`2:07:21.3`)
- Whole target invocation: approximately `2:07:39.9`
- Terminal boundary: epoch `150`, optimizer update `11,400`
- Terminal reason: `EARLY_STOPPING_PATIENCE`
- Validation/checkpoint commits: `30 / 30`
- Median/p95 update wall: `0.6499 / 0.8137 s`
- Median throughput: `48.60 scenes/s`
- Median/p95 validation wall: `2.7152 / 2.7672 s`
- Median/p95 checkpoint request-to-durable-ACK wall: `0.2896 / 0.4645 s`
- Peak PyTorch allocated VRAM: `4,402,956,288 bytes`
- Observed NVIDIA memory maximum: GPU0 `9,265 MiB`, GPU1 `9,187 MiB`
- Peak rank RSS: `7,381,315,584 bytes`
- Median rank wall skew: `0.00069 s`
- Sampled GPU utilization mean/p95: GPU0 `30.1% / 90%`, GPU1 `28.6% / 94%`

The 30-second utilization sampler includes data/validation/checkpoint idle intervals, so its mean is not a kernel-only utilization estimate. No OOM, NaN/Inf, infrastructure interruption, or exact resume occurred in the formal trajectory.

## 6. Five-Epoch Validation History

`Selected` records the runtime selector replacement at that boundary. Patience resets only for retrieval loss improvement of at least `1e-4`; a margin-only replacement would not reset it.

| Epoch | Update | Train total | Scene | IP | Retrieval | Margin | Selected | Patience |
|---:|---:|---:|---:|---:|---:|---:|:---:|---:|
| 5 | 380 | 5.874668 | 5.637589 | 0.237079 | 2.3110129833 | 0.0774579644 | yes | 0 |
| 10 | 760 | 4.455186 | 4.392276 | 0.062909 | 1.6773893833 | 0.1142845899 | yes | 0 |
| 15 | 1,140 | 3.603820 | 3.562877 | 0.040943 | 1.2689809799 | 0.1437174678 | yes | 0 |
| 20 | 1,520 | 3.057189 | 3.020271 | 0.036918 | 1.0726681948 | 0.1629546732 | yes | 0 |
| 25 | 1,900 | 2.722409 | 2.690622 | 0.031787 | 0.9001287818 | 0.1822690070 | yes | 0 |
| 30 | 2,280 | 2.490439 | 2.460976 | 0.029463 | 0.8747909069 | 0.1873893738 | yes | 0 |
| 35 | 2,660 | 2.315463 | 2.286675 | 0.028788 | 0.7776857018 | 0.1975992322 | yes | 0 |
| 40 | 3,040 | 2.167284 | 2.138823 | 0.028461 | 0.7279496789 | 0.2045740485 | yes | 0 |
| 45 | 3,420 | 2.058086 | 2.032307 | 0.025778 | 0.6891576648 | 0.2115189731 | yes | 0 |
| 50 | 3,800 | 1.961989 | 1.937829 | 0.024161 | 0.6849166751 | 0.2114378810 | yes | 0 |
| 55 | 4,180 | 1.882341 | 1.856735 | 0.025606 | 0.6631388068 | 0.2166058123 | yes | 0 |
| 60 | 4,560 | 1.806824 | 1.782291 | 0.024534 | 0.6385428905 | 0.2195238471 | yes | 0 |
| 65 | 4,940 | 1.745297 | 1.721553 | 0.023744 | 0.6399623156 | 0.2203908116 | no | 1 |
| 70 | 5,320 | 1.679881 | 1.657071 | 0.022809 | 0.6328658462 | 0.2216129303 | yes | 0 |
| 75 | 5,700 | 1.632022 | 1.609355 | 0.022667 | 0.6014658213 | 0.2270084620 | yes | 0 |
| 80 | 6,080 | 1.585356 | 1.563097 | 0.022259 | 0.5953714848 | 0.2288372666 | yes | 0 |
| 85 | 6,460 | 1.538535 | 1.516702 | 0.021833 | 0.5885448456 | 0.2310981899 | yes | 0 |
| 90 | 6,840 | 1.508079 | 1.486171 | 0.021907 | 0.5859056115 | 0.2301737219 | yes | 0 |
| 95 | 7,220 | 1.478109 | 1.456950 | 0.021158 | 0.5854843855 | 0.2301930636 | yes | 0 |
| 100 | 7,600 | 1.435041 | 1.413796 | 0.021244 | 0.5727306604 | 0.2345868051 | yes | 0 |
| 105 | 7,980 | 1.421935 | 1.402279 | 0.019656 | 0.5629427433 | 0.2344382852 | yes | 0 |
| 110 | 8,360 | 1.396455 | 1.375545 | 0.020910 | 0.5730585456 | 0.2348367572 | no | 1 |
| 115 | 8,740 | 1.383863 | 1.363337 | 0.020526 | 0.5624440908 | 0.2345623076 | yes | 0 |
| 120 | 9,120 | 1.363052 | 1.342796 | 0.020256 | 0.5596585274 | 0.2357739508 | yes | 0 |
| 125 | 9,500 | 1.336172 | 1.315991 | 0.020181 | 0.5642539263 | 0.2349743396 | no | 1 |
| 130 | 9,880 | 1.320138 | 1.299838 | 0.020301 | 0.5484582782 | 0.2382205427 | yes | 0 |
| 135 | 10,260 | 1.297105 | 1.276997 | 0.020109 | 0.5545305014 | 0.2375020832 | no | 1 |
| 140 | 10,640 | 1.292231 | 1.272237 | 0.019994 | 0.5612845421 | 0.2366741896 | no | 2 |
| 145 | 11,020 | 1.283279 | 1.263748 | 0.019531 | 0.5603138208 | 0.2372743785 | no | 3 |
| 150 | 11,400 | 1.263206 | 1.243274 | 0.019932 | 0.5574666858 | 0.2364426255 | no | 4 |

At epoch 5, MRR/HIT@1/HIT@5/HIT@10 were `0.999375 / 0.998750 / 1 / 1`; from epoch 10 onward all four diagnostics were `1`. These metrics did not participate in checkpoint selection.

## 7. Selection And Early Stopping

The selected checkpoint emerged independently from the pure V2-C replay:

| Field | Result |
|---|---|
| Checkpoint | `p9ck_3704be6c57323160fd0365e9` |
| Completed/resume epoch | `130 / 131` |
| Optimizer update | `9,880` |
| Retrieval loss | `0.5484582781791687` |
| Mean source-separation margin | `0.23822054266929626` |
| Payload SHA-256 | `d83fba2d693fcac22998d2d43adecb7d75a39e8d243e6dfcf5a9ff964d2a67e2` |
| Manifest SHA-256 | `46684b3254775725243ece842939666c5719c1365170bc7072e074dd7d2484a4` |

Epochs 135, 140, 145, and 150 were four consecutive retrieval-loss non-improvements after epoch 130. The stopping boundary is therefore epoch 150/update 11,400. Runtime convenience state and pure finalizer replay agreed.

## 8. Bundle, Finalization, Acceptance, Eligibility, Resolver

| Artifact | Identity | Content SHA-256 |
|---|---|---|
| Run bundle | `p9rb_f71a1da232e6ee98e40f08a3` | `f71a1da232e6ee98e40f08a33828f51f859827aa7e05684587f421480d30fe6f` |
| Finalization | `p9fin_5cf12c1192801566abecaf7d` | `5cf12c1192801566abecaf7d7dda33b75108dfdceb9bbded5024b72219d2fc43` |
| Acceptance | `p9accv2_15d9fb568e794b7efd0cfa8c` | `15d9fb568e794b7efd0cfa8c5486af331002ea08b5ebbca9f04ba8c12ef58c5d` |
| Eligibility | `p9elig_ff80795511cc8cd146417f2d` | content-addressed immutable snapshot |

The closed 364-event ledger replayed to scientific `COMPLETE`; bundle validation returned `SCIENTIFICALLY_COMPLETE`; finalization succeeded; acceptance validation succeeded; and the accepted-checkpoint resolver reproduced the authority, bundle, finalization, checkpoint locator/hashes, selected metrics, configuration, stopping summary, and provenance. The eligibility snapshot contains independent `ELIGIBLE` entries for cfg_main and cfg_d48.

## 9. Idempotency

The same isolated graph was requested again after acceptance. All nine targets were skipped in 68 ms. Direct create-or-validate calls for bundle, finalization, acceptance, eligibility, and resolver also returned the existing valid objects. A pre/post inventory of all 815 cfg_d48 lineage files was byte-identical: training restarts `0`, optimizer updates `0`, checkpoint rewrites `0`, bundle rewrites `0`, acceptance rewrites `0`.

## 10. Comparison With cfg_main

| Metric | cfg_main d64 | cfg_d48 |
|---|---:|---:|
| d / d_c | 64 / 64 | 48 / 48 |
| Training scenes | 2,421 | 2,421 |
| Global batch | 32 | 32 |
| Stopping epoch | 125 | 150 |
| Selected epoch | 105 | 130 |
| Total updates | 9,500 | 11,400 |
| Retrieval loss | 0.3806893528 | 0.5484582782 |
| Margin | 0.2876026034 | 0.2382205427 |
| Median update wall | 0.6756 s | 0.6499 s |
| Total worker wall | about 1:46:34.6 | 2:07:21.3 |
| Approx. throughput from median | 47.36 scenes/s | 48.60 scenes/s |
| Observed GPU memory high-water | about 10.2/13.2 GiB | 9.05/8.97 GiB |

The d48 median update was about `3.96%` faster and median-derived throughput about `3.96%` higher. Its trajectory ran 20% more epochs, so total wall was about `19.50%` longer. Validation retrieval loss was `0.1677689254` higher (`44.07%`) and margin `0.0493820607` lower (`17.17%`). These are configuration results, not a hyperparameter-winner decision.

## 11. Validation Results

- Focused V2-H/remediation gate before training: `33 passed`.
- Final relevant Python regression: `480 passed`, `0 failed` in 226.99 s.
- Relevant R P9 suite: `54 passed`, `2 failed`, `0 errors`. Both failures are the pre-existing documented stale-generation expectations in `test-p9-formal-isolated-pipeline.R`; they expect `p9gen_acb...` rather than the preserved `p9gen_batchuniq_20260831`. No unrelated R code was changed.
- `targets::tar_validate()` passed independently for main, formal, recovery, and V2 training scripts without scientific target execution.
- The V2 training graph contained 9 targets with an isolated single-configuration closure and no P9-B, evaluation, P10, P11, maintenance, V1, or recovery target.
- Python/R parse, Draft 2020-12 schemas, Markdown paths, target network, and `git diff --check` were checked after report creation.

## 12. Evaluation Leakage And Prohibited Work

| Activity | Count |
|---|---:|
| cfg_d48 formal authority | 1 |
| cfg_d48 formal run | 1 |
| cfg_d48 optimizer updates | 11,400 |
| Other P9-A training | 0 |
| P9-B training | 0 |
| Held-out evaluation query/gallery loads | 0 / 0 |
| Held-out evaluation embeddings/metrics | 0 / 0 |
| P10/P11 execution | 0 / 0 |
| Maintenance execution | 0 |
| V1 execution/recovery | 0 / 0 |
| cfg_main retraining | 0 |
| Scientific divergence | 0 |

## 13. Immutability

The canonical pre/post inventory excluded transient lock files and contained 239 existing files before the run. Afterward it contained 627 files: 388 additions, 0 removals, and 0 changed pre-existing files. Additions were restricted to the cfg_d48 authority/run/ledger/checkpoints/bundle/finalization/acceptance and the new immutable eligibility evidence.

The cfg_main selected payload and manifest remained:

- `fdac720bff12fb25747f69977bc69c5fb28adbc4a73cabd879b1b57c47cc06b6`
- `87010ce01ad74fc7b2652bf0e5a7e56baea2bef88400f6f23748d1e39f9227bc`

The cfg_main acceptance, V1 retirement manifest, V1 evidence, accepted P1-P8 parents, other variant namespaces, and dissertation were unchanged.

## 14. Remaining Work And Exact Next Action

- Remaining P9-A configurations: `11`
- Remaining P9-B configurations: `7`
- Held-out evaluation: not started

Exact next work unit:

`P9-A post-cfg_d48 production audit — compare the first native V2 formal trajectory with cfg_main, verify controller/runtime scaling and determine whether the remaining 11 P9-A configurations may be safely authorized as a bounded sequential execution campaign.`

No additional variant is authorized or executed by this report.
