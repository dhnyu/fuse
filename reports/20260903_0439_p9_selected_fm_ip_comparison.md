# P9 Selected-FM IP Comparison

## Verdict

`P9_SELECTED_FM_IP_COMPARISON_PASS_PUSHED`

The bounded sequential confirmation completed both planned runs. Validation-only
comparison selected `cfg_selected_fm_ip1`; no held-out evaluation, P9-B training,
P10/P11, v1 execution, cache regeneration, or additional search was performed.

## Scope and repository state

- Execution window: 2026-09-03 KST (ledger timestamps are RFC3339 UTC).
- Starting Fuse HEAD: `b7889c0dd16dbcb18d34f7806a14c5227353b5b8`.
- Campaign implementation HEAD: `7c893ea3655aa693015c56d302436c2855676cda`.
- Branch: `reduced`; dissertation remained at
  `ad8c8b5c17c5ca72dce7f30c2eb283f6041dbc9a`.
- Campaign root:
  `/mnt/hdd002/dhnyu/fusedata/runtime/p9_selected_fm_campaigns/20260903_0050`.
- tmux session `p9_selected_fm_ip_20260903` exited normally.

The prompt requested an exact two-run interaction check after the 13-run P9-A
OFAT study. The two confirmations shared the `cfg_selected_fm` seed namespace,
weak/K4 bank subset `p8abi_24471ee4574c585c98083b53`, fixed validation
acceptance, and every scientific setting except `lambda_IP`.

## Configurations and canonical lineage

| Field | IP0 | IP1 |
|---|---|---|
| Configuration | `cfg_selected_fm_ip0` | `cfg_selected_fm_ip1` |
| Source scientific hash | `961fac037720ab45a9e295598bdef41be59183a2fe3a2a5335d900217bb75bb7` | `cd0e6c835b4e788408e60a42ea516f7f0f00e3388a969fe1471f195dae02fb32` |
| V2 configuration hash | `3094d7a42d32b446df6a9612dd4c25680efd3624bc9cdc06cc51ad2bcf5cdafc` | `267db181952a6711c6fd9730ffc8784a73e0e35e5987d9a9043c2269b722a213` |
| `lambda_IP` | 0 | 1 |
| Authority | `p9authv2_c80cc4f0027db6bf46fbbfd8` | `p9authv2_9234d06aa9837ed0dcaa7fda` |
| Run | `p9runv2_c07e9ab75212103a4cd9180c` | `p9runv2_e540546cfd6d4d308ced3e0d` |
| Bundle | `p9rb_801bb2954c27d88752a636cb` | `p9rb_f36e53bf60ca705ef9e21a84` |
| Finalization | `p9fin_396b59f073c17212538a78e5` | `p9fin_2babc4235a06f9d86530d8eb` |
| Acceptance | `p9accv2_71cd4dbad4335da2389cf1d7` | `p9accv2_1e1e842ee66f169f189725aa` |
| Eligibility after run | `p9elig_cda8ebbc6cac0a20460bcf75` | `p9elig_aa74178012b5636c2f20c9f2` |

Both configurations use `d=d_c=128`, four heads, head dimension 32, FFN 256,
K=4, weak 0.5x, EMA 0.999, AdamW peak LR `3e-3`, the same root seed, and
selection contract `p9-selection-v2.1.0`. Evaluation ancestry and consumption
are zero.

## Selected results and stopping

| Metric | IP0 | IP1 |
|---|---:|---:|
| Selected checkpoint | `p9ck_f4c9e6dd3444ed5920486b1a` | `p9ck_7334de1c0ca1343473b9c3f6` |
| Selected epoch/update | 85 / 6,460 | 110 / 8,360 |
| Retrieval loss | 0.2012318373 | **0.1987979710** |
| Margin | **0.3530243039** | 0.3515348732 |
| Stopping epoch/update | 105 / 7,980 | 130 / 9,880 |
| Validation/checkpoint count | 21 / 21 | 26 / 26 |
| Terminal condition | patience 4 | patience 4 |

The loss difference is `0.0024338663`, greater than `1e-4`. IP1 therefore wins
at the primary criterion; margin and the IP0 simplicity tie-break are not
consulted. Pure finalizer replay reproduced every candidate, patience counter,
selected checkpoint, and stopping boundary.

## Runtime diagnostics

| Metric | IP0 | IP1 |
|---|---:|---:|
| Ledger training wall | 5,952.00 s (99.20 min) | 7,337.46 s (122.29 min) |
| Median update wall | 0.7332 s | 0.7292 s |
| P95 update wall | 0.7458 s | 0.7414 s |
| Median throughput | 43.45 scenes/s | 43.68 scenes/s |
| Median validation+checkpoint boundary | 3.260 s | 3.304 s |
| P95 validation+checkpoint boundary | 3.348 s | 3.483 s |

The ledger contract does not timestamp validation and checkpoint publication as
separate sub-events, so the last two rows report their combined durable-boundary
gap. Runtime did not participate in selection.

## IP0 five-epoch trajectory

| Epoch | Update | Total | Scene | Raw IP | Weighted IP | LR | Retrieval | Margin | Patience | Selected |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---:|
| 5 | 380 | 4.536996 | 4.536996 | 1.400983 | 0.000000 | 0.00150000 | 1.0033764839 | 0.1765048951 | 0 | yes |
| 10 | 760 | 3.185524 | 3.185524 | 1.384977 | 0.000000 | 0.00300000 | 0.5357857347 | 0.2416434735 | 0 | yes |
| 15 | 1140 | 2.328904 | 2.328904 | 1.385767 | 0.000000 | 0.00299488 | 0.3529330194 | 0.2847079933 | 0 | yes |
| 20 | 1520 | 1.867358 | 1.867358 | 1.402987 | 0.000000 | 0.00297954 | 0.2683488131 | 0.3121918738 | 0 | yes |
| 25 | 1900 | 1.615563 | 1.615563 | 1.374792 | 0.000000 | 0.00295410 | 0.2493346334 | 0.3230423033 | 0 | yes |
| 30 | 2280 | 1.442576 | 1.442576 | 1.369264 | 0.000000 | 0.00291873 | 0.2356619835 | 0.3294134438 | 0 | yes |
| 35 | 2660 | 1.340422 | 1.340422 | 1.408850 | 0.000000 | 0.00287366 | 0.2280324996 | 0.3338534236 | 0 | yes |
| 40 | 3040 | 1.240161 | 1.240161 | 1.365025 | 0.000000 | 0.00281921 | 0.2159658968 | 0.3415374756 | 0 | yes |
| 45 | 3420 | 1.176449 | 1.176449 | 1.391592 | 0.000000 | 0.00275575 | 0.2163481861 | 0.3403319418 | 1 | no |
| 50 | 3800 | 1.115274 | 1.115274 | 1.434913 | 0.000000 | 0.00268371 | 0.2143600136 | 0.3434523344 | 0 | yes |
| 55 | 4180 | 1.068900 | 1.068900 | 1.381981 | 0.000000 | 0.00260359 | 0.2078329623 | 0.3464072347 | 0 | yes |
| 60 | 4560 | 1.030771 | 1.030771 | 1.415746 | 0.000000 | 0.00251592 | 0.2152750641 | 0.3444272280 | 1 | no |
| 65 | 4940 | 0.991079 | 0.991079 | 1.391531 | 0.000000 | 0.00242132 | 0.2062364072 | 0.3483313620 | 0 | yes |
| 70 | 5320 | 0.957430 | 0.957430 | 1.370791 | 0.000000 | 0.00232042 | 0.2084945142 | 0.3498245478 | 1 | no |
| 75 | 5700 | 0.935906 | 0.935906 | 1.352490 | 0.000000 | 0.00221392 | 0.2020879239 | 0.3503408730 | 0 | yes |
| 80 | 6080 | 0.902135 | 0.902135 | 1.439733 | 0.000000 | 0.00210254 | 0.2046134770 | 0.3509947956 | 1 | no |
| 85 | 6460 | 0.876680 | 0.876680 | 1.391266 | 0.000000 | 0.00198705 | 0.2012318373 | 0.3530243039 | 0 | yes |
| 90 | 6840 | 0.859127 | 0.859127 | 1.410910 | 0.000000 | 0.00186823 | 0.2030550390 | 0.3502408862 | 1 | no |
| 95 | 7220 | 0.831074 | 0.831074 | 1.340423 | 0.000000 | 0.00174689 | 0.2036700398 | 0.3516630530 | 2 | no |
| 100 | 7600 | 0.813910 | 0.813910 | 1.328578 | 0.000000 | 0.00162387 | 0.2020144612 | 0.3536225557 | 3 | no |
| 105 | 7980 | 0.794022 | 0.794022 | 1.366579 | 0.000000 | 0.00150000 | 0.2016594112 | 0.3534125388 | 4 | no |

## IP1 five-epoch trajectory

| Epoch | Update | Total | Scene | Raw IP | Weighted IP | LR | Retrieval | Margin | Patience | Selected |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---:|
| 5 | 380 | 4.591416 | 4.547072 | 0.044344 | 0.044344 | 0.00150000 | 1.0594379902 | 0.1696982980 | 0 | yes |
| 10 | 760 | 3.234330 | 3.203305 | 0.031025 | 0.031025 | 0.00300000 | 0.5582094193 | 0.2374954671 | 0 | yes |
| 15 | 1140 | 2.374896 | 2.348739 | 0.026157 | 0.026157 | 0.00299488 | 0.3557258546 | 0.2799608111 | 0 | yes |
| 20 | 1520 | 1.914335 | 1.892214 | 0.022122 | 0.022122 | 0.00297954 | 0.2738275230 | 0.3086915612 | 0 | yes |
| 25 | 1900 | 1.652435 | 1.632234 | 0.020201 | 0.020201 | 0.00295410 | 0.2533346117 | 0.3185349405 | 0 | yes |
| 30 | 2280 | 1.468576 | 1.449244 | 0.019332 | 0.019332 | 0.00291873 | 0.2526828051 | 0.3204843998 | 0 | yes |
| 35 | 2660 | 1.357745 | 1.338654 | 0.019091 | 0.019091 | 0.00287366 | 0.2398109585 | 0.3262677491 | 0 | yes |
| 40 | 3040 | 1.264863 | 1.247259 | 0.017604 | 0.017604 | 0.00281921 | 0.2267556041 | 0.3342934549 | 0 | yes |
| 45 | 3420 | 1.188873 | 1.171078 | 0.017795 | 0.017795 | 0.00275575 | 0.2218803912 | 0.3371726274 | 0 | yes |
| 50 | 3800 | 1.131924 | 1.113907 | 0.018016 | 0.018016 | 0.00268371 | 0.2171127498 | 0.3416130543 | 0 | yes |
| 55 | 4180 | 1.080244 | 1.063852 | 0.016393 | 0.016393 | 0.00260359 | 0.2121498734 | 0.3417853117 | 0 | yes |
| 60 | 4560 | 1.045314 | 1.028559 | 0.016756 | 0.016756 | 0.00251592 | 0.2151595652 | 0.3410471976 | 1 | no |
| 65 | 4940 | 1.002125 | 0.986081 | 0.016044 | 0.016044 | 0.00242132 | 0.2147683501 | 0.3416011333 | 2 | no |
| 70 | 5320 | 0.974414 | 0.958276 | 0.016138 | 0.016138 | 0.00232042 | 0.2079340369 | 0.3455862403 | 0 | yes |
| 75 | 5700 | 0.944669 | 0.929148 | 0.015521 | 0.015521 | 0.00221392 | 0.2072244138 | 0.3456454873 | 0 | yes |
| 80 | 6080 | 0.916416 | 0.900437 | 0.015979 | 0.015979 | 0.00210254 | 0.2035828233 | 0.3474425077 | 0 | yes |
| 85 | 6460 | 0.894729 | 0.879379 | 0.015349 | 0.015349 | 0.00198705 | 0.2033873200 | 0.3491744697 | 0 | yes |
| 90 | 6840 | 0.872452 | 0.857322 | 0.015130 | 0.015130 | 0.00186823 | 0.2025976926 | 0.3476618528 | 0 | yes |
| 95 | 7220 | 0.844924 | 0.830064 | 0.014860 | 0.014860 | 0.00174689 | 0.2050934285 | 0.3483107090 | 1 | no |
| 100 | 7600 | 0.830025 | 0.815662 | 0.014363 | 0.014363 | 0.00162387 | 0.2049742937 | 0.3495914340 | 2 | no |
| 105 | 7980 | 0.808395 | 0.793939 | 0.014456 | 0.014456 | 0.00150000 | 0.2076727152 | 0.3474880457 | 3 | no |
| 110 | 8360 | 0.799126 | 0.784364 | 0.014763 | 0.014763 | 0.00137613 | 0.1987979710 | 0.3515348732 | 0 | yes |
| 115 | 8740 | 0.788839 | 0.774876 | 0.013963 | 0.013963 | 0.00125311 | 0.2035661489 | 0.3498443365 | 1 | no |
| 120 | 9120 | 0.766488 | 0.752707 | 0.013781 | 0.013781 | 0.00113177 | 0.1998812705 | 0.3505529761 | 2 | no |
| 125 | 9500 | 0.762961 | 0.748398 | 0.014563 | 0.014563 | 0.00101295 | 0.2032065243 | 0.3499347568 | 3 | no |
| 130 | 9880 | 0.755300 | 0.741143 | 0.014157 | 0.014157 | 0.00089746 | 0.2047266215 | 0.3506964445 | 4 | no |

Training losses are diagnostic only. IP0 records raw IP loss while its weighted
contribution remains exactly zero, as required.

## Final selected-FM and P9-B basis

- Decision: `p9sfm_dca5569ef50bd9bfb1940032`.
- Winner: `cfg_selected_fm_ip1`.
- Selected acceptance: `p9accv2_1e1e842ee66f169f189725aa`.
- Selected checkpoint: `p9ck_7334de1c0ca1343473b9c3f6`.
- Materialized P9-B plan: `p9bplan_747bbf5e1e12f831ea5fb101`.

All seven P9-B entries bind the winner acceptance and checkpoint, fixed
validation acceptance, zero evaluation ancestry, and their declared cumulative
A1-A5, SSV-like, or DS-like transformation. The plan is
`MATERIALIZED_NOT_EXECUTED`; it contains no historical full-model fallback.
The explicit `cfg_main_substitution` strings are prohibited-fallback tokens,
not baseline references.

## Validation

- Canonical resolver validation, including payload and manifest byte hashes:
  2/2 pass.
- Bundle/finalization/acceptance/eligibility chain: 2/2 pass.
- Decision and P9-B plan Draft 2020-12 schema/content hashes: pass.
- Selector/stopping replay: 47/47 candidates pass.
- Python V2/P9 regression: 446 passed, 0 failed.
- R P9 tests: 57 passed; two documented stale retired-v1 generation assertions
  failed unchanged (`p9gen_acb...` expectation versus preserved
  `p9gen_batchuniq_20260831`).
- `tar_validate()` for main, formal, recovery, and V2 training scripts: pass;
  no target execution.
- JSON/schema parsing and `git diff --check`: pass.

## Immutability and prohibited work

| Activity | Count |
|---|---:|
| Planned selected-FM formal runs | 2 |
| Extra/third selected-FM run | 0 |
| P9-B scientific execution | 0 |
| Held-out evaluation | 0 |
| P10/P11 | 0 / 0 |
| V1 execution | 0 |
| Cache regeneration | 0 |
| Historical mutation | 0 |
| Dissertation mutation | 0 |

Historical cfg_main payload and manifest remain
`fdac720bff12fb25747f69977bc69c5fb28adbc4a73cabd879b1b57c47cc06b6`
and `87010ce01ad74fc7b2652bf0e5a7e56baea2bef88400f6f23748d1e39f9227bc`.
Canonical cfg_main acceptance and V1 retirement evidence were unchanged.

## Next work unit

`P9_B_SELECTED_MODEL_ABLATION_EXECUTION`

Before issuing a comparison authority, that unit must close the plan's
`PLAN_VALIDATED_IMPLEMENTATION_REQUIRED_BEFORE_P9_B` gate with bounded
construction/update pilots for the seven declared transformations. It must not
silently route a template through the full-model worker unchanged.

## Input prompt summary

Run exactly two selected-FM confirmations differing only in `lambda_IP`, select
with validation loss/margin/IP0 simplicity, freeze one full-model acceptance,
materialize seven P9-B templates, and keep evaluation and downstream science at
zero.
