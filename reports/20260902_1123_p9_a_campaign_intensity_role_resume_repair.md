# P9-A Campaign Intensity Role And Resume Repair

## Verdict

`P9_A_CAMPAIGN_INTENSITY_ROLE_AND_RESUME_REPAIR_PASS_PUSHED`

Execution time: 2026-09-02 Asia/Seoul. This report covers the source repair,
read-only restoration audit, bounded GPU pilots, and pre-launch validation. The
formal continuation is launched only after this report and source commit are
pushed from a clean `reduced` branch.

## Scope And Starting State

- Fuse started at `reduced@84be55cfda1cb1fa77739f736f98281c3c27c31d`, origin 0/0 and clean.
- Dissertation remained `reduced@ad8c8b5c17c5ca72dce7f30c2eb283f6041dbc9a`, origin 0/0 and clean.
- The active methodology confirms five-epoch validation, validation-only
  selection, loss equivalence below `1e-4`, loss-only patience reset, patience
  four, and zero held-out evaluation consumption.
- Accepted campaign prefix: `cfg_d128`, `cfg_k2`, `cfg_k4`, `cfg_k16`.
- Preserved failed evidence: authority `p9authv2_f0983f076aebdcfed0f13198`
  and run `p9runv2_ed3ad2b3ab84c99de1c46181`.

The failed ledger still replays as `INCOMPLETE / BLOCKED / RESTART_REQUIRED`,
with no completed epoch, optimizer update, validation, or checkpoint.

## Root Cause And Repair

The immutable cache stores the main profile as physical role `training`, weak
as `training:weak_0.5x`, and strong as `training:strong_2.0x`. The old worker
and pilot filtered and sampled only physical `training`, yielding zero weak or
strong scenes. A second lookup defect used logical `training` against the
profile-keyed geometry cache.

`python/p9_v2_prepared_cache.py` now provides the one shared read-only adapter.
It selects exactly one requested profile, projects that profile to logical
`training`, retains the original physical row unchanged for payload validation,
and exposes its physical role for geometry lookup. No cache file was modified
or regenerated. Both worker and pilot import this adapter.

The production training trace now retains aligned `total_loss`, `scene_loss`,
raw `ip_loss`, weighted IP loss, learning rate, and optimizer update. These are
diagnostic and are not selection inputs.

## Cache Regression

| Profile | Physical role | Scenes | Physical views | Logical K8 views | Payload lookup |
|---|---|---:|---:|---:|---|
| main 1.0x | `training` | 2,421 | 38,736 | 19,368 | pass |
| weak 0.5x | `training:weak_0.5x` | 2,421 | 19,368 | 19,368 | pass |
| strong 2.0x | `training:strong_2.0x` | 2,421 | 19,368 | 19,368 | pass |

Tests also reject leakage from nonselected profiles and unrelated roles. The
cache plan SHA-256 remained
`5aa419def82356a8e69867de3bb7439a224fac553c210be0cae0c6e33fd1a528`.

## Bounded Two-GPU Pilots

The noncanonical pilot root was
`/tmp/p9-v2-intensity-role-pilot-20260902-2`. Each accepted intensity row ran
one actual two-rank NCCL global update using the production cache.

| Configuration | Profile | Global updates | Queue count/pointer | Sampler cursor | Validation | Evaluation |
|---|---|---:|---:|---:|---:|---:|
| `cfg_intensity_05` | weak 0.5x | 1 | 64 / 64 | 1 | 0 | 0 |
| `cfg_intensity_20` | strong 2.0x | 1 | 64 / 64 | 1 | 0 | 0 |

Both pilots materialized the production batch, completed forward/backward,
optimizer, EMA, and queue progression with finite loss. Formal authority, run,
checkpoint, acceptance, and eligibility publication counts were zero.

## Campaign Resume Contract

`restore_campaign_progress()` accepts only an exact planned prefix. For every
completed row it validates the canonical authority, P8 and V2 configuration
hashes, original implementation lineage, lifecycle eligibility/resolution
handoffs, cumulative eligibility entry, resolver chain, checkpoint bytes, and
exact scientific configuration. Any inconsistency stops the campaign.

The current status restored exactly four rows and cumulative eligibility
`p9elig_76f891b4a1072237a90a50d7`. The old failed authority used implementation
hash `975a90f8...`; the repaired source derives a different content-addressed
authority and run. Therefore the old authority/run are preserved but never
reused, and the continuation begins `cfg_intensity_05` from update zero.

## Validation

- Focused cache/campaign tests: 13 passed, 0 failed.
- Relevant V2/P7/P8/P9 Python regression: 425 passed, 49 skipped, 0 failed.
- Main/weak/strong payload and population checks: passed against the accepted cache.
- Weak/strong two-GPU update pilots: 2 passed, 0 failed.
- Campaign canonical-prefix restoration and corrupted-skip rejection: passed.
- R P9: 55 passed, 2 failed, 0 errors. The two failures are the unchanged,
  documented v1 formal-generation string assertions; active V2 tests passed.
- `tar_validate()`: main, v1 formal, v1 recovery, and V2 training passed with
  temporary stores and no target execution.
- Python compile/import and `git diff --check`: passed.

## Immutability And Prohibited Work

The four completed authorities and acceptances were resolver-validated and not
rewritten. The failed authority file SHA-256 remained
`adda4e2e743a71e7e5dfdef74835ed42672910adb5d19e59ed453e510050169e`.
Historical cfg_main payload and manifest remained respectively
`fdac720bff12fb25747f69977bc69c5fb28adbc4a73cabd879b1b57c47cc06b6`
and `87010ce01ad74fc7b2652bf0e5a7e56baea2bef88400f6f23748d1e39f9227bc`.

| Activity before formal continuation | Count |
|---|---:|
| New formal authority / run | 0 / 0 |
| Cache regeneration or mutation | 0 |
| Held-out evaluation | 0 |
| P9-B / P10 / P11 | 0 / 0 / 0 |
| Historical or dissertation mutation | 0 |
| Bounded noncanonical global updates | 2 |

## Exact Next Action

After push and clean synchronization, launch one detached tmux continuation of
the same campaign root. It must restore the four accepted configurations,
derive a new authority for `cfg_intensity_05`, and proceed sequentially only
after each canonical resolver check. Stop on the first failure.

## Prompt Summary

Repair weak/main/strong role interpretation without cache changes, prove weak
and strong with bounded two-GPU updates, make campaign restart canonical-prefix
aware, preserve all prior accepted and failed evidence, push the repair, then
resume at `cfg_intensity_05` in one detached tmux session.
