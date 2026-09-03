# P9 Ablation Completion and Held-out Readiness Audit

## Verdict

`P9_ABLATION_COMPLETION_AND_HELDOUT_READINESS_AUDIT_PASS_PUSHED`

Held-out readiness: `HELDOUT_EVALUATION_READY`.

This was a read-only completion and integrity audit. It did not run training,
validation, held-out evaluation, P10, or P11, and it did not publish or mutate
scientific artifacts.

## Scope and lineage

- Audit time: 2026-09-04 02:16 Asia/Seoul
- Fuse branch/start: `reduced` / `bfa2dd8cc7ef824688238e3cd5473769d89518a7`
- Dissertation: `reduced` / `ad8c8b5c17c5ca72dce7f30c2eb283f6041dbc9a`
- Active P9-B plan: `p9bplan_e36f7c9c5069a504eb31a9ef`
- Fixed full model: `cfg_d128`, acceptance
  `p9accv2_a1c00e32a882ddc4b7e2677b`
- Final eligibility snapshot: `p9elig_250e0140d593f360f1368ef1`
- Machine-readable chain details and aligned trajectories:
  [20260904_0216_p9_ablation_trajectories.json](20260904_0216_p9_ablation_trajectories.json)

## DS-like completion

The cached replacement trajectory is canonically complete:

- Cache: `p9ds_1e26585c61122cf7c758088a`
- Authority: `p9authv2_8610966f649fa6ae8b806afc`
- Run: `p9runv2_c63dfaa65295f1a2727b15a6`
- Bundle: `p9rb_b98d354c193bf5009befe00f`
- Finalization: `p9fin_13f50ef19a0d8b437c316b84`
- Acceptance: `p9accv2_f4194b7c74f8dedb4c867e6b`
- Eligibility: `p9elig_250e0140d593f360f1368ef1`
- Selected checkpoint: `p9ck_65cc78a1a97330f3af05fba4`
- Selected/stopping boundary: epoch 200, update 15,200
- Selected retrieval loss: `0.4145002365`
- Selected margin: `0.2472607940`
- Validation/checkpoint events: 40/40
- Evaluation consumption: 0

Bundle validation, pure finalization, acceptance validation, eligibility lookup,
and full resolver-chain validation all passed. The training ledger itself ends in
scientific `COMPLETE`; finalization and acceptance are separate immutable
artifacts, as required by the V2 plane separation.

## Dynamic/cache equivalence

The abandoned dynamic-raster run remains immutable and noncanonical for model
selection. Its last durable checkpoint is epoch 75/update 5,700. For all 15
overlapping boundaries, cached-raster loss and margin are bit-identical to the
dynamic path. Selector state is also identical after normalizing the expected
lineage-specific checkpoint IDs to their completed epochs: the current boundary
is selected, patience is zero, and the decision is
`retrieval_loss_improved` at each boundary.

| Epoch | Update | Retrieval loss | Margin | Selector/patience match |
|---:|---:|---:|---:|:---:|
| 5 | 380 | 2.4139604568 | 0.0583648384 | exact |
| 10 | 760 | 1.6738936901 | 0.0894584954 | exact |
| 15 | 1,140 | 1.2039667368 | 0.1212927848 | exact |
| 20 | 1,520 | 1.0120649338 | 0.1407609582 | exact |
| 25 | 1,900 | 0.8980486393 | 0.1560929716 | exact |
| 30 | 2,280 | 0.8172449470 | 0.1681413651 | exact |
| 35 | 2,660 | 0.7522854805 | 0.1762357950 | exact |
| 40 | 3,040 | 0.6476706862 | 0.1892819852 | exact |
| 45 | 3,420 | 0.6187748909 | 0.1945217252 | exact |
| 50 | 3,800 | 0.5670741796 | 0.2028100193 | exact |
| 55 | 4,180 | 0.5470731854 | 0.2073675096 | exact |
| 60 | 4,560 | 0.5350110531 | 0.2088247240 | exact |
| 65 | 4,940 | 0.5087287426 | 0.2155608237 | exact |
| 70 | 5,320 | 0.5033189058 | 0.2171713263 | exact |
| 75 | 5,700 | 0.4761040211 | 0.2237681001 | exact |

## Final comparison

All seven P9-B configurations are canonically complete and resolve through the
active plan. Deltas are ablation minus `cfg_d128`; positive loss delta is worse.

| Configuration | Acceptance | Checkpoint | Selected | Stop/update | Loss | Margin | Delta loss | Delta margin | Wall h | Update med/p95 s | Scenes/s | V/C |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| cfg_d128 | `p9accv2_a1c00e32a882ddc4b7e2677b` | `p9ck_56195e9ea3cd45d80cf5e23c` | 85 | 105/7,980 | 0.1765069515 | 0.3754689395 | 0 | 0 | 1.609 | 0.714/0.725 | 44.83 | 21/21 |
| cmp_a1_geometric_core | `p9accv2_9a207a914e17fbdc663f738a` | `p9ck_37979e7a36f6b189ecf674d0` | 70 | 90/6,840 | 0.2201937288 | 0.4141666889 | +0.0436867774 | +0.0386977494 | 1.103 | 0.572/0.580 | 55.94 | 18/18 |
| cmp_a2_semantic_enriched | `p9accv2_b603f92e47f7ffe6bdf3a5d3` | `p9ck_74cc9b14a7d294463bfd5a9c` | 75 | 95/7,220 | 0.2305538952 | 0.3897022903 | +0.0540469438 | +0.0142333508 | 1.248 | 0.614/0.621 | 52.16 | 19/19 |
| cmp_a3_object_context_enriched | `p9accv2_90763f5a22a6aab791c42290` | `p9ck_c0784d438146deeaee04fd34` | 95 | 115/8,740 | 0.2446398735 | 0.3784501553 | +0.0681329221 | +0.0029812157 | 1.531 | 0.621/0.627 | 51.53 | 23/23 |
| cmp_a4_raster_complete_non_relational | `p9accv2_b25055427137c88c820dcc51` | `p9ck_a71bec2d0fae827ee7c97879` | 90 | 110/8,360 | 0.1861187816 | 0.3722944260 | +0.0096118301 | -0.0031745136 | 1.473 | 0.624/0.633 | 51.27 | 22/22 |
| cmp_a5_relation_type_agnostic | `p9accv2_0a4ac70cbf2ebcba233c6084` | `p9ck_0ee547be5473315d457bf104` | 110 | 130/9,880 | 0.2058894932 | 0.3557559252 | +0.0293825418 | -0.0197130144 | 1.992 | 0.715/0.724 | 44.78 | 26/26 |
| cmp_ssv_like | `p9accv2_93c296bec0ffe6f1a3ccb8ee` | `p9ck_388bce700e35c96012e77b1a` | 100 | 120/9,120 | 0.2236431092 | 0.3982822299 | +0.0471361578 | +0.0228132904 | 1.392 | 0.544/0.553 | 58.87 | 24/24 |
| cmp_ds_like | `p9accv2_f4194b7c74f8dedb4c867e6b` | `p9ck_65cc78a1a97330f3af05fba4` | 200 | 200/15,200 | 0.4145002365 | 0.2472607940 | +0.2379932851 | -0.1282081455 | 2.244 | 0.523/0.533 | 61.19 | 40/40 |

Wall time is measured from `RUN_STARTED` to `TRAINING_COMPLETED`. Per-update
median/p95 and throughput are ledger-derived estimates from non-validation epoch
intervals divided by 76 updates; they are diagnostic, not direct profiler
samples. The companion JSON retains every aligned five-epoch mean total, scene,
raw IP, weighted IP and validation observation. The older cfg_d128 trace lacks
explicit IP components; because lambda_IP is one, those values are marked as
deterministically derived from total minus scene loss.

## Interpretation

`cfg_d128` remains the fixed P9-A-selected full model. No P9-B variant has lower
primary validation retrieval loss. A1, A2, A3, and SSV-like have higher margins,
which is reported above, but the selection contract considers margin only for
loss-equivalent candidates; their losses are not equivalent to cfg_d128.

A1-A5 retain the declared cumulative architecture interpretation. SSV-like and
DS-like remain controlled baselines, not claims of exact external-method
reproduction. The P9-B observations do not reopen P9-A selection.

## Held-out readiness

All gates pass:

- P9-A is complete and all 13 canonical acceptances resolve.
- The final model is fixed at cfg_d128.
- P9-B is 7/7 complete under the active cfg_d128 plan.
- The final eligibility snapshot contains and resolves all 20 P9-A/P9-B entries.
- Every bundle/finalization/acceptance/checkpoint chain validates.
- Evaluation consumption is exactly zero throughout the evidence.
- The held-out interface accepted the cfg_d128 acceptance identity and resolved
  the canonical checkpoint without a path, latest token, v1 fallback, or target
  metadata.
- No unresolved scientific or infrastructure blocker remains.

This verdict authorizes no evaluation by itself. A separate explicit work unit
is still required.

## Validation

- Focused completion, resolver, and DS equivalence: 90 passed.
- Full P9/V2 Python suite: 559 passed, 58 skipped.
- Relevant R tests: 38 passed, 0 failed.
- `tar_validate()`: main, formal, recovery, and isolated V2 training scripts pass.
- R parsing: four target scripts pass.
- Draft 2020-12/schema checks: covered by the full Python suite.
- Canonical resolver validation: cfg_d128 plus seven comparisons pass; final
  eligibility resolves 20/20 P9-A/P9-B entries.
- `git diff --check`, JSON parsing, Markdown parsing/link checks, and immutable
  post-readback: pass before publication.

## Immutability and prohibited work

Pre/post digests for cfg_d128, completed A1-A5, SSV-like, the abandoned dynamic
DS ledger/checkpoints, v1 selected payload/manifest, retirement manifest, and
historical inventory match. The dissertation remains clean at its required
commit. The cached DS canonical chain was only read.

| Activity | Count |
|---|---:|
| Training or scientific rerun | 0 |
| Validation execution | 0 |
| Held-out evaluation execution/consumption | 0 |
| P10/P11 execution | 0 |
| Cache generation/regeneration | 0 |
| Canonical publication or mutation | 0 |
| Historical/V1 mutation | 0 |
| Dissertation mutation | 0 |
| Manual/latest/v1 checkpoint resolution | 0 |

## Next work unit

`P9_HELDOUT_EVALUATION_EXECUTION`

The next unit must separately authorize and execute held-out evaluation through
the canonical cfg_d128 acceptance resolver. It was not started here.
