# P9 Final Model cfg_d128 And P9-B Materialization

## Verdict

`P9_FINAL_MODEL_CFG_D128_P9B_MATERIALIZATION_PASS_PUSHED`

- Audit and implementation time: 2026-09-03 05:19 KST onward.
- Starting Fuse lineage: `reduced@16b53d15cacc4b23b27a2308aeaab665002e83b4`.
- Dissertation: `reduced@ad8c8b5c17c5ca72dce7f30c2eb283f6041dbc9a`, unchanged.
- Scope: validation-only final-selection correction and deterministic P9-B
  materialization. No scientific execution was performed.

## Selection Interpretation

The 13-run P9-A OFAT study selected factor-wise values `d=128`, `K=4`, weak
0.5x, EMA .999, lambda_IP 0, and peak LR 3e-3. The two subsequent joint runs
tested lambda_IP 0 versus 1 within that combined configuration. IP1 won that
bounded pair, but neither joint run outperformed the already executed
`cfg_d128`. The factor-wise preferences therefore were not additive.

The overall comparison uses the dissertation-authoritative fixed validation
contract: lower retrieval loss, differences strictly below `1e-4` treated as
equivalent, then larger margin. Training loss, runtime, MRR/HIT, and held-out
evaluation were excluded.

## Complete Executed Evidence

Loss and margin are the pure-finalizer-selected validation checkpoint values.

| Configuration | Selected / stop epoch | Retrieval loss | Margin |
|---|---:|---:|---:|
| `cfg_d64` (historical `cfg_main`) | 105 / 125 | 0.3806893528 | 0.2876026034 |
| `cfg_d48` | 130 / 150 | 0.5484582782 | 0.2382205427 |
| **`cfg_d128`** | **85 / 105** | **0.1765069515** | **0.3754689395** |
| `cfg_k2` | 110 / 130 | 0.3644936383 | 0.2913429141 |
| `cfg_k4` | 100 / 120 | 0.3520698845 | 0.2908249199 |
| `cfg_k16` | 95 / 110 | 0.3772826791 | 0.2881452441 |
| `cfg_intensity_05` | 160 / 180 | 0.3233415484 | 0.2999751866 |
| `cfg_intensity_20` | 140 / 160 | 0.3833094537 | 0.2840979695 |
| `cfg_ema_990` | 50 / 70 | 0.4489240944 | 0.2509890795 |
| `cfg_ip_0` | 115 / 135 | 0.3672296405 | 0.2956995964 |
| `cfg_lr_2` | 105 / 125 | 0.3432392776 | 0.2889378965 |
| `cfg_lr_3` | 110 / 130 | 0.3318019807 | 0.2893958390 |
| `cfg_lr_10` | 35 / 55 | 0.5059423447 | 0.2291457355 |
| `cfg_selected_fm_ip0` | 85 / 105 | 0.2012318373 | 0.3530243039 |
| `cfg_selected_fm_ip1` | 110 / 130 | 0.1987979710 | 0.3515348732 |

All 15 acceptance-to-payload chains resolve through the canonical resolver.
Evaluation ancestry and consumption are zero.

## Final Full Model

- Configuration: `cfg_d128`.
- Authority: `p9authv2_8a0d04b815f566e65d65a2c9`.
- Run: `p9runv2_ae13c2259e3a73e1dfb209b6`.
- Acceptance: `p9accv2_a1c00e32a882ddc4b7e2677b`.
- Checkpoint: `p9ck_56195e9ea3cd45d80cf5e23c`.
- Selected epoch/update: 85 / 6,460.
- Stopping epoch/update: 105 / 7,980.
- Retrieval loss: `0.17650695145130157`.
- Margin: `0.3754689395427704`.
- Overall decision: `p9fms_389a0ce89992eee507d7c846`.
- Decision content SHA-256:
  `389a0ce89992eee507d7c84608a3d7c1e2e1d88d95b8d391fdcdd568e9f44b52`.

The existing `p9sfm_dca5569ef50bd9bfb1940032` remains valid only as the IP0/IP1
interaction decision. Its two acceptances, checkpoints, bundles, finalizations,
and eligibility records remain unchanged and eligible. The old IP1-based P9-B
plan is preserved as immutable historical planning evidence and is inactive.

## P9-B Materialization

The active non-executed plan is `p9bplan_e36f7c9c5069a504eb31a9ef`. It binds
`cfg_d128` acceptance and checkpoint plus each accepted P8 transformation.
The base science is d=d_c=128, four heads, K=8 main 1.0x bank, EMA .999,
lambda_IP 1, and peak LR 1e-3. DS alone changes lambda_IP to zero because that
change is declared by its transformation and it has no modality-specific IP
objective.

| Configuration | Family | Declared change | Scientific hash |
|---|---|---|---|
| `cmp_a1_geometric_core` | A1 | geometric core only | `72e33a3f3f335488ac3eeb2da3e5c6ba6812b20854a597674c0d4283f0d10367` |
| `cmp_a2_semantic_enriched` | A2 | add semantic modalities | `c0e17a7c5b93934fbd82327211f4435fb14696bff48797aaf49ff795065bfe72` |
| `cmp_a3_object_context_enriched` | A3 | add object environmental background | `64f716a956f6b244f3a9926c95606b7cc121fb00122bb6400c12c3e23691f501` |
| `cmp_a4_raster_complete_non_relational` | A4 | add scene raster, no relations | `6ecf6ef6a0f120f11b9c6c01f443dac79ba2580deeac31e102029d4f45ac0d76` |
| `cmp_a5_relation_type_agnostic` | A5 | generic relation labels on exact FM edges | `67225a5baefc08d33b2397b3e8c2ebdbb03567823d8bfe5a6b8dc70bb1f65f8e` |
| `cmp_ssv_like` | SSV | declared SSV-like retained modalities | `cc502acfc5b048f67419408b7aaf72a002a6e8422aba8b8fbf9bce5524c8c84c` |
| `cmp_ds_like` | DS | declared common-raster DS-like model | `d8a4687a26ea86dba1c6de43ed64db81ea5be85bd02b14144fbf4642c3a1aad7` |

The active matrix and authority contract use `full_model_acceptance_id`; they
reject the legacy selected-FM plan shape. The legacy schema remains readable so
the prior immutable plan can still be audited.

## Prior Interrupted P9-B Evidence

Before this work unit, the superseded IP1-based campaign had been interrupted
at A1. Authority `p9authv2_b23dfb42fb9a099e7611ae53` and run
`p9runv2_130260da09b367de31a8ccc6` are preserved. Its ledger contains only
`RUN_AUTHORIZED`, `RUN_STARTING`, and `RUN_STARTED`; it has no durable scientific
boundary, validation, or checkpoint. It was not resumed, rewritten, or used by
this materialization.

## Validation

- Focused final-selection/P9-B/selected-FM/controller tests: 40 passed.
- Full V2/P9 Python regression plus P8/P9 infrastructure: 598 passed,
  58 skipped, 0 failed (`PYTHONPATH=.`).
- The first combined invocation without `PYTHONPATH=.` stopped during
  collection on the repository-local `scripts` namespace; no test ran in that
  invocation. The corrected command above passed.
- R P9 tests: 57 passed; the two documented retired-v1 stale generation
  assertions remain unchanged (`p9gen_acb...` expected versus preserved
  `p9gen_batchuniq_20260831`).
- `tar_validate()`: main, formal, recovery, and V2 training scripts all pass;
  no targets were executed.
- Draft 2020-12 schemas, JSON/YAML parsing, Python compile/AST, R parsing, and
  `git diff --check`: pass.
- Historical selected checkpoint payload SHA-256:
  `fdac720bff12fb25747f69977bc69c5fb28adbc4a73cabd879b1b57c47cc06b6`.
- Historical selected manifest SHA-256:
  `87010ce01ad74fc7b2652bf0e5a7e56baea2bef88400f6f23748d1e39f9227bc`.

## Mutations And Prohibitions

Two new content-addressed planning artifacts were published: the overall final
decision and the cfg_d128-bound P9-B plan. Existing canonical artifacts were
not rewritten.

| Activity | Count |
|---|---:|
| P9-B training / optimizer updates | 0 / 0 |
| New P9-A or selected-FM run | 0 |
| Held-out evaluation | 0 |
| P10 / P11 | 0 / 0 |
| New training authority / run / checkpoint / acceptance | 0 / 0 / 0 / 0 |
| Historical or existing canonical mutation | 0 |
| Dissertation mutation | 0 |

## Next Work Unit

`P9_B_CFG_D128_ABLATION_EXECUTION`

That work unit must use only `p9bplan_e36f7c9c5069a504eb31a9ef`, handle the
preserved superseded A1 evidence explicitly, and execute the seven comparisons
sequentially without held-out evaluation.

## Input Prompt Summary

Rebase overall final-model selection on the best executed validation result,
preserve both selected-FM confirmations as scoped interaction evidence, and
materialize but do not execute seven cfg_d128-relative P9-B comparisons.
