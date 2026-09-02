# P9-A Campaign Completion And Selection Audit

## Verdict

`P9_A_CAMPAIGN_COMPLETION_AND_SELECTION_AUDIT_PASS_PUSHED`

- Audit time: 2026-09-02 23:58 through 2026-09-03 Asia/Seoul.
- Fuse input: `reduced@f7afba5983bfd42bb98b717a68dd361296bd9665`, initially clean and origin 0/0.
- Dissertation: `reduced@ad8c8b5c17c5ca72dce7f30c2eb283f6041dbc9a`, unchanged.
- Campaign root: `/mnt/hdd002/dhnyu/fusedata/runtime/p9_a_campaigns/20260901_1450`.
- Campaign log: `/mnt/hdd002/dhnyu/fusedata/runtime/p9_a_campaigns/20260901_1450/campaign.log`.
- The `p9a_campaign_resume_20260902` tmux session had exited before this audit; no process was interrupted or restarted.

The campaign status is `COMPLETE`. All 13 planned P9-A configurations have one
canonical eligible acceptance. The selection audit uses validation evidence only;
held-out evaluation consumption remains zero.

## Campaign Completeness And Canonical Chains

The cumulative immutable snapshot is
`p9elig_8d017288b37c7c7a08734fa7`, with 13 distinct `ELIGIBLE` entries. Every
entry was resolved through acceptance, finalization, bundle, checkpoint locator,
payload bytes, and manifest bytes. All ledgers replayed scientifically `COMPLETE`;
validation/checkpoint cardinalities matched exactly. Historical `cfg_main` is
reported as `cfg_d64 (historical cfg_main)` without changing any source identity.

| Configuration | Acceptance | Checkpoint | Selected / stop | Loss | Margin | Wall h | Update median / p95 s | Scenes/s | V/C |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| `cfg_d64 (historical cfg_main)` | `p9accv2_d93b01ef13c3f26a22287ce7` | `p9ck_42f7957d2ea998ac9e8ff705` | 105 / 125 | 0.3806893528 | 0.2876026034 | 1.78 | 0.6560 / 0.8269 | 48.78 | 25/25 |
| `cfg_d48` | `p9accv2_15d9fb568e794b7efd0cfa8c` | `p9ck_3704be6c57323160fd0365e9` | 130 / 150 | 0.5484582782 | 0.2382205427 | 2.12 | 0.6499 / 0.8137 | 48.60 | 30/30 |
| `cfg_d128` | `p9accv2_a1c00e32a882ddc4b7e2677b` | `p9ck_56195e9ea3cd45d80cf5e23c` | 85 / 105 | 0.1765069515 | 0.3754689395 | 1.61 | 0.7109 / 0.8971 | 44.81 | 21/21 |
| `cfg_k2` | `p9accv2_e7c406083c6722a2ccf78920` | `p9ck_c102332d5bc4513f6293cadb` | 110 / 130 | 0.3644936383 | 0.2913429141 | 1.81 | 0.6361 / 0.7965 | 49.84 | 26/26 |
| `cfg_k4` | `p9accv2_e5195740f5411f57271ba080` | `p9ck_dcf5f947b5830925d3ba6096` | 100 / 120 | 0.3520698845 | 0.2908249199 | 1.71 | 0.6585 / 0.8266 | 48.48 | 24/24 |
| `cfg_k16` | `p9accv2_039dec13e82ccb86f4cee20e` | `p9ck_feb73bf6ab7c8bf0ab4d1dfa` | 95 / 110 | 0.3772826791 | 0.2881452441 | 1.58 | 0.6608 / 0.8153 | 47.94 | 22/22 |
| `cfg_intensity_05` | `p9accv2_9cf610131a5a18c55e1ecfd7` | `p9ck_a5c91b47650941ce260bdf76` | 160 / 180 | 0.3233415484 | 0.2999751866 | 2.65 | 0.6786 / 0.8491 | 46.87 | 36/36 |
| `cfg_intensity_20` | `p9accv2_8eb8718344da89701b156a90` | `p9ck_c5877cfd5fa2e028c0154c9a` | 140 / 160 | 0.3833094537 | 0.2840979695 | 2.20 | 0.6320 / 0.7834 | 50.27 | 32/32 |
| `cfg_ema_990` | `p9accv2_0a6fc8990ef1b1a67ba75358` | `p9ck_b2c40f9a1f6ea34788134cb7` | 50 / 70 | 0.4489240944 | 0.2509890795 | 1.00 | 0.6590 / 0.8236 | 47.90 | 14/14 |
| `cfg_ip_0` | `p9accv2_b7351959991cdb537163eec8` | `p9ck_4320508baca7ed3c7ebd52b8` | 115 / 135 | 0.3672296405 | 0.2956995964 | 1.93 | 0.6578 / 0.8233 | 48.25 | 27/27 |
| `cfg_lr_2` | `p9accv2_6bd7e6e70b3c3bedec4f79b4` | `p9ck_eeb57924381792bdf99eb31c` | 105 / 125 | 0.3432392776 | 0.2889378965 | 1.79 | 0.6573 / 0.8162 | 48.13 | 25/25 |
| `cfg_lr_3` | `p9accv2_1c42f030d852fa1a76722198` | `p9ck_c261a142002c18c898a77e6b` | 110 / 130 | 0.3318019807 | 0.2893958390 | 1.90 | 0.6753 / 0.8289 | 47.12 | 26/26 |
| `cfg_lr_10` | `p9accv2_e1f12dc82f991b6cbe3bb818` | `p9ck_0a031fbdfb82362c105d8d7b` | 35 / 55 | 0.5059423447 | 0.2291457355 | 0.79 | 0.6581 / 0.8342 | 48.18 | 11/11 |

Wall time is ledger `RUN_STARTED` to `TRAINING_COMPLETED` for native runs; the
historical value is the audited worker wall. Native update summaries are medians
of equal-sized five-epoch diagnostic intervals. Runtime is diagnostic and did
not enter selection.

The original zero-update `cfg_intensity_05` authority
`p9authv2_f0983f076aebdcfed0f13198` and run
`p9runv2_ed3ad2b3ab84c99de1c46181` remain preserved as
`INCOMPLETE / BLOCKED / RESTART_REQUIRED`; they are not the accepted corrected
trajectory and were not reused.

## Five-Epoch Trajectories

The aligned 319-row appendix is
`reports/20260903_0000_p9_a_campaign_5_epoch_trajectories.csv` (SHA-256
`afaa0c75eafd70a4b85b519fcd0109d64094a8696f1a3cca84dab40ee2590082`).
For every five-epoch boundary it records mean total, scene, and IP training loss,
ending LR, optimizer update, validation retrieval loss, margin, patience, and
whether the boundary is the final selected checkpoint. Training loss is
diagnostic only. Pre-remediation traces expose weighted IP; post-remediation
traces expose raw IP, and the appendix labels this distinction instead of
silently conflating them.

## Scientific Comparability

All 13 observations bind the accepted 2,421-scene population, fixed P5
validation acceptance `fqsa_27565de68d9432e47fe7b99d`, global/per-rank batch
`32/16`, world size 2, five-epoch cadence, `p9-selection-v2.1.0`, and zero
evaluation ancestry/consumption. Each P8 row differs from `cfg_d64` only in its
declared factor group.

Native implementation digests are `975a90f8...` before the intensity repair and
`8fede8c7...` afterward. The intervening scientific-source change normalizes the
selected cache profile to logical role `training` and adds diagnostic IP trace
fields. Existing tests prove the main physical role is unchanged; weak/strong
profiles use their predeclared immutable cache rows. Model, objective, sampler,
optimizer, validation, selector, batch, and parent contracts are unchanged.
The historical `cfg_d64` trajectory was separately imported and accepted under
the same scientific contract. No unintended scientifically relevant divergence
was found, so factor selection is not blocked.

## Validation-Only Selection

The dissertation/P8 rule was applied within each OFAT factor: lower validation
retrieval loss, differences below `1e-4` treated as equivalent, larger margin,
then earlier selected epoch. Training loss, runtime, MRR/HIT, and held-out
evaluation were excluded.

| Factor | Compared values | Preferred value | Winning observation |
|---|---|---|---|
| latent dimension | 48, 64, 128 | `128` | `cfg_d128` |
| effective K | 2, 4, 8, 16 | `4` | `cfg_k4` |
| intensity | weak 0.5x, main 1.0x, strong 2.0x | `weak_0.5x` | `cfg_intensity_05` |
| EMA | .990, .999 | `.999` | `cfg_d64` baseline value |
| lambda IP | 0, 1 | `0` | `cfg_ip_0` |
| peak LR | 1e-3, 2e-3, 3e-3, 1e-2 | `3e-3` | `cfg_lr_3` |

The best actually executed configuration is `cfg_d128`, selected at epoch 85
with loss `0.17650695145130157` and margin `0.3754689395427704`. This is not the
same scientific claim as the factor-wise combined configuration.

## Selected-FM Requirement

The combined configuration is `d=d_c=128`, heads 4, head dimension 32, FFN
dimension 256, `K=4`, weak 0.5x intensity, EMA `.999`, `lambda_IP=0`, and peak
LR `3e-3`; all other accepted settings remain unchanged. No executed P9-A row
matches it. Exactly one formal confirmation is therefore required.

The non-authorizing plan is `blueprint/p9_v2/p9_a_selection_plan.json`. Its
configuration ID is `cfg_selected_fm`; its P8-style canonical scientific payload
SHA-256 is
`961fac037720ab45a9e295598bdef41be59183a2fe3a2a5335d900217bb75bb7`.
The weak/K4 nested bank subset is `p8abi_24471ee4574c585c98083b53`.
This document is neither an execution authority nor an acceptance. The next work
unit must bind it through the existing V2 controller and run exactly one
validation-only selected-FM confirmation.

## P9-B Basis

P9-B's future full-model reference is the accepted `cfg_selected_fm`, never
`cfg_main`/`cfg_d64`. The seven current P8 templates remain
`UNRESOLVED_UNTIL_P9_A_SELECTION` and inherit every selected-FM setting except
their declared transformation:

| Template | Intended transformation audit |
|---|---|
| `cmp_a1_geometric_core` | Retains relative position/intrinsic geometry; removes the declared semantic/context/raster/relation components only. |
| `cmp_a2_semantic_enriched` | Extends A1 only with the declared semantic modalities and IP term. |
| `cmp_a3_object_context_enriched` | Extends A2 only with object environmental background. |
| `cmp_a4_raster_complete_non_relational` | Extends A3 only with the scene raster branch while relations remain absent. |
| `cmp_a5_relation_type_agnostic` | Preserves exact FM edge support and maps only relation labels to one generic embedding. |
| `cmp_ssv_like` | Applies only the declared controlled-baseline removals; it is not a direct reproduction. |
| `cmp_ds_like` | Applies only the declared raster controlled-baseline representation and `lambda_IP=0`; it is not a direct reproduction. |

All templates prohibit `cfg_main` substitution, `latest`, old P7 lineage, and
evaluation identity. They cannot be materialized until selected-FM acceptance;
P9-B execution count in this work unit is zero.

## Validation

- Canonical campaign/selection assertions: complete 11-row campaign suffix plus
  `cfg_d48` and historical `cfg_d64`; 13/13 resolver chains passed.
- Canonical validation/checkpoint links: 319/319 exact; all payload and manifest
  hashes verified through V2-B/E validation.
- Focused/wider Python P9 regression: 439 passed, 1 failed. The sole failure is
  stale live-state test `test_blocked_campaign_restores_four_canonical_acceptances_and_latest_eligibility`,
  which assumes the old four-row blocked campaign and one implementation digest.
  It does not indicate canonical or scientific evidence failure and was not
  altered in this documentation-only work unit.
- Relevant R P9 tests: 54 passed, 2 failed. Both are the previously documented
  v1 generation string assertions (`p9gen_acb...` versus preserved
  `p9gen_batchuniq_20260831`).
- `tar_validate()`: main, formal, recovery, and isolated V2 training scripts
  passed using temporary stores, without target execution.
- Draft 2020-12 P9 v2 schemas: 17/17 parsed and validated.
- Selection-plan JSON parse, Python compile, and `git diff --check`: passed.

The stale Python live-state test should be updated in the selected-FM work unit
to validate a completed campaign with the explicitly audited repair lineage
transition. It is not used to weaken or bypass canonical selection checks.

## Immutability And Prohibited Work

| Activity | Count |
|---|---:|
| Training / resume / recovery | 0 / 0 / 0 |
| New authority / run / checkpoint / bundle / finalization / acceptance | 0 / 0 / 0 / 0 / 0 / 0 |
| Held-out evaluation / P9-B / P10 / P11 | 0 / 0 / 0 / 0 |
| Metric recomputation | 0 |
| Historical/canonical evidence mutation | 0 |
| Dissertation mutation | 0 |

Readback hashes remained: historical payload
`fdac720bff12fb25747f69977bc69c5fb28adbc4a73cabd879b1b57c47cc06b6`,
manifest `87010ce01ad74fc7b2652bf0e5a7e56baea2bef88400f6f23748d1e39f9227bc`,
cfg_main acceptance file
`ad1fe493610f92fe97aa6f4b40048ff8d56e54d9e074cff74c43fe243df0a713`,
and retirement manifest file
`4fd252ecfefa7436b0665b97cabe5976f3000a827d8ad229d8f0a17b161aac91`.

## Exact Next Work Unit

`P9_SELECTED_FM_FORMAL_CONFIRMATION`

Do not execute P9-B or held-out evaluation before that one confirmation has a
canonical acceptance and resolver verification.

## Prompt Summary

Wait for the sequential P9-A campaign, audit all planned configurations and
their aligned training/validation evidence, verify comparability, perform the
predeclared validation-only factor selection, decide whether selected-FM is
required, and prepare but do not execute the seven selected-model P9-B variants.
