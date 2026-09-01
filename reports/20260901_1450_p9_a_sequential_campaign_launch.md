# P9-A Sequential Campaign Launch

## Purpose And Verdict

This work unit normalizes the human-facing name of the historical main
configuration, audits the first native V2 result, and authorizes the exact
remaining P8 hyperparameter rows as one fail-stop sequential campaign.

Launch verdict: `P9_A_SEQUENTIAL_CAMPAIGN_AUTHORIZED`.

This is a launch report, not the final P9-A result report. Factor selection,
selected-FM determination, and P9-B materialization remain blocked until the
campaign has terminated and all resulting validation evidence has been audited.

## Starting State

- Fuse: `reduced@4f8f2b1066e6bfa1ed5f0273b087989c79bbf4e1`, clean, origin 0/0.
- Dissertation: `reduced@ad8c8b5c17c5ca72dce7f30c2eb283f6041dbc9a`, clean, origin 0/0.
- Canonical cfg_main acceptance: `p9accv2_d93b01ef13c3f26a22287ce7`.
- Canonical cfg_d48 acceptance: `p9accv2_15d9fb568e794b7efd0cfa8c`.
- Held-out evaluation consumption: zero.
- Prompt scope: alias normalization, post-cfg_d48 audit, detached sequential
  campaign launch, and later validation-only selection preparation.

## cfg_main To cfg_d64 Alias

`cfg_main` is scientifically the `d=64, d_c=64` OFAT observation and is shown
as `cfg_d64` in all new reporting interfaces. `cfg_main` remains the immutable
P8 configuration ID and historical provenance value. The alias function does
not modify the P8 row, scientific hash, authority, imported run, bundle,
checkpoint, finalization, acceptance, eligibility, or report.

## Post-cfg_d48 Audit

The first native V2 trajectory passed 30/30 validation-checkpoint linkage,
scientific completion replay, V2-B validation, pure V2-C finalization,
idempotent acceptance, eligibility publication, and resolver readback. Its
no-op graph rerun performed zero optimizer updates and rewrote no artifact.
Median update wall was 0.6499 s with 48.60 scenes/s and no OOM, nonfinite state,
or DDP skew issue. This evidence does not reveal a production-scaling blocker
for a sequential campaign. cfg_d64 and cfg_d48 are two valid P9-A observations.

## Authorized Campaign

Only these ordered configurations are authorized:

1. `cfg_d128`
2. `cfg_k2`
3. `cfg_k4`
4. `cfg_k16`
5. `cfg_intensity_05`
6. `cfg_intensity_20`
7. `cfg_ema_990`
8. `cfg_ip_0`
9. `cfg_lr_2`
10. `cfg_lr_3`
11. `cfg_lr_10`

The runner builds and preflights one content-addressed authority, publishes it
only after preflight, runs the existing isolated nine-target lifecycle, requires
resolver completion, and carries the resulting immutable eligibility snapshot
to the next row. Any nonzero lifecycle result marks the campaign blocked and no
next row starts. Configuration stores and logs are external to Git.

## tmux Launch Contract

- Session: `p9a_campaign_20260901`
- Campaign root:
  `/mnt/hdd002/dhnyu/fusedata/runtime/p9_a_campaigns/20260901_1450`
- Aggregate log:
  `/mnt/hdd002/dhnyu/fusedata/runtime/p9_a_campaigns/20260901_1450/campaign.log`
- Status:
  `/mnt/hdd002/dhnyu/fusedata/runtime/p9_a_campaigns/20260901_1450/campaign_status.json`
- Per-configuration logs: `<campaign-root>/<configuration>/targets.log`
- Reattach: `tmux attach -t p9a_campaign_20260901`

Launch command:

```bash
tmux new-session -d -s p9a_campaign_20260901 \
  "cd /members/dhnyu/fuse && exec env PYTHONDONTWRITEBYTECODE=1 \
  python scripts/p9_a_campaign.py \
  --campaign-root /mnt/hdd002/dhnyu/fusedata/runtime/p9_a_campaigns/20260901_1450 \
  >> /mnt/hdd002/dhnyu/fusedata/runtime/p9_a_campaigns/20260901_1450/campaign.log 2>&1"
```

## Current P9-A Observations

| Reporting configuration | Historical ID | Selected epoch | Loss | Margin | Status |
|---|---|---:|---:|---:|---|
| `cfg_d64` | `cfg_main` | 105 | 0.3806893528 | 0.2876026034 | canonical accepted |
| `cfg_d48` | `cfg_d48` | 130 | 0.5484582782 | 0.2382205427 | canonical accepted |
| `cfg_d128` | same | pending | pending | pending | queued first |
| Remaining ten campaign rows | same | pending | pending | pending | queued sequentially |

No factor winner can yet be derived. Runtime efficiency is diagnostic and is
not a selection criterion.

## Selected-FM And P9-B Gate

After campaign termination, selection uses only validation retrieval loss,
the `1e-4` equivalence rule, margin, and the declared factor-wise protocol. An
observed configuration winner is distinct from the combination of factor-wise
values. If that combined configuration lacks a canonical executed run, exactly
one selected-FM confirmation is required. Only after this gate may the seven P8
comparison templates be materialized against the selected FM. There is no
cfg_d64 fallback and no P9-B execution in this launch unit.

## Prohibited Work Accounting At Launch

| Activity | Count |
|---|---:|
| Held-out evaluation | 0 |
| P9-B execution | 0 |
| P10/P11 | 0 / 0 |
| Manual/latest resolver use | 0 |
| V1 execution | 0 |
| Historical/cfg_main artifact mutation | 0 |
| Dissertation mutation | 0 |
| Unauthorized hyperparameter rows | 0 |

## Validation And Immutability Gate

- Focused campaign/controller/variant/remediation Python: 40 passed.
- Full relevant P9/P8 Python: 487 passed, 58 skipped, 0 failed.
- Relevant R P9: 55 passed, 2 failed, 0 errors. The two failures are the
  unchanged stale v1 formal-generation assertions documented by V2-G through
  the cfg_d48 report; campaign code and active V2 targets passed.
- Main, v1 formal, v1 recovery, and V2 training `tar_validate()`: passed with
  no target execution.
- Python AST: 159 files; Draft 2020-12 schema check: 124 schemas.
- Isolated V2 graph: 9 targets, 20 edges, one component; network regenerated.
- `git diff --check`: passed.

Immutable readback before campaign launch:

| Evidence | SHA-256 |
|---|---|
| cfg_d64 historical payload | `fdac720bff12fb25747f69977bc69c5fb28adbc4a73cabd879b1b57c47cc06b6` |
| cfg_d64 historical manifest | `87010ce01ad74fc7b2652bf0e5a7e56baea2bef88400f6f23748d1e39f9227bc` |
| cfg_d64 V2 acceptance file | `ad1fe493610f92fe97aa6f4b40048ff8d56e54d9e074cff74c43fe243df0a713` |
| V1 retirement manifest file | `4fd252ecfefa7436b0665b97cabe5976f3000a827d8ad229d8f0a17b161aac91` |

The alias test recomputed the unmodified P8 `cfg_main` row hash before and
after reporting-name resolution and found byte-identical scientific evidence.

## Next Audit

When the detached session terminates, read the campaign status and every
canonical resolver chain, then produce the final 12-row P9-A comparison,
factor-wise selection, selected-FM requirement, and P9-B reference plan. Do not
use held-out evaluation.
