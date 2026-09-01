# P9 V2-H Production Worker Remediation

## 1. Verdict

`P9_V2_H_PRODUCTION_WORKER_REMEDIATION_PASS_PUSHED`

This work completed the production science-worker, durable checkpoint handshake,
exact-resume, and terminal V2-B/C/E lifecycle that were missing at the prior
`cfg_d48` preflight. It did not issue a formal authority or start a formal run.

Execution time: 2026-09-01 Asia/Seoul. Starting Fuse lineage:
`ae7ea2553233a5b9a9e749f29197abebd8bcf255` on `reduced`, initially clean and
synchronized 0/0. Dissertation lineage remained
`ad8c8b5c17c5ca72dce7f30c2eb283f6041dbc9a` on `reduced`.

## 2. Original Blocking Defect

The read-only preflight reported
`CONTROLLER_INFRASTRUCTURE_FAILURE_PREAUTHORITY`: the V2-H controller could
validate authority and append proposals, but no independent production worker
could perform updates, no worker/controller checkpoint ACK existed, no actual
state restore existed, and the target graph accepted externally supplied
post-training artifacts instead of producing them.

## 3. Audit

| Boundary | Before | Remediation |
|---|---|---|
| controller to worker | arbitrary external command | repository-owned two-rank worker entry point |
| progress | one-way JSON proposals | versioned request/ACK protocol |
| checkpoint | no worker staging handshake | controller-only atomic commit and ledger linkage |
| durable ACK | absent | ACK only after committed event; deterministic retry |
| resume | eligibility decision only | full science-state restoration |
| ledger to bundle | library existed | native V2-B adapter and executable target |
| bundle to finalizer | library existed | V2-C target using `p9-selection-v2.1.0` |
| acceptance to resolver | injected paths | existing publisher, eligibility, and resolver targets |

The worker reuses numerical/model/data helpers only. It does not import the
retired v1 formal runner, v1 authority/recovery code, acceptance code, resolver,
or `targets`. The controller remains PyTorch-free.

## 4. Production Worker Architecture

`python/p9_v2_training_worker.py` implements accepted P8 configuration routing,
the fixed production cache, two-rank NCCL DDP, FM model/EMA, AdamW, exact
scheduler, 8,192-entry queue, rotating-padding sampler, deterministic RNG,
forward/backward, clipping, optimizer/EMA/queue updates, fixed validation,
checkpoint state construction, patience, and terminal proposals.
`scripts/p9_v2_training_worker.py` is its production entry point.

Formal cadence remains 200 epochs maximum, 76 global updates per epoch,
validation every five epochs, and patience four. Selection and patience use the
existing V2-C v2.1.0 implementation; no selector was added. Held-out evaluation
is absent from source and closure.

## 5. Worker/Controller IPC

`config/schemas/p9_v2_worker_ipc.schema.json` defines canonical JSON-line
`EVENT_PROPOSAL`, `CHECKPOINT_COMMIT_REQUEST`, `FAILURE_REPORT`, `ACK`, and
`NACK` messages. Requests have deterministic `p9req_` IDs. Only rank zero talks
to the controller; all ranks block on its broadcast ACK. NACK terminates the
worker. Duplicate delivery returns the already committed event.

## 6. Checkpoint Commit Handshake

Rank zero fsyncs opaque `checkpoint.pt` below the controller-provided staging
root, submits its normalized relative path and complete metadata, and stops.
The controller validates schema, containment, run/epoch/update semantics,
state-presence contract, hashes the payload, derives `p9ck_`, atomically
publishes payload and manifest, appends `VALIDATION_CHECKPOINT_COMMITTED`, then
ACKs. Only that event makes a candidate eligible. Staging debris is not evidence.

## 7. Exact Resume

Restore covers online and EMA parameters, optimizer, scheduler, queue contents
and counters, next sampler boundary, Python/NumPy/CPU/CUDA RNG for both ranks,
training and validation traces, update count, patience, and best-state
convenience evidence. Only the latest controller-committed checkpoint can be
used. Configuration, run, parents, and world size are checked before restore.

The final production-shaped pilot produced identical complete scientific-state
digests after four uninterrupted updates and after two updates, committed
interruption, fresh process group, restore, and two further updates:
`94b3d1101bd4d344f2a52b7bbf46154337fe746e697302eaea89a52653a92896`.

## 8. Executable Target Lifecycle

`_targets_p9_v2_training.R` now has nine coarse targets and 20 edges:
contract, explicit authority, full startup preflight, training execution,
bundle, finalization, acceptance, immutable eligibility, and resolver
verification. The closure has one configuration and no v1, recovery, P9-B,
evaluation, P10, P11, or maintenance target. No bundle, finalization, or
acceptance path is accepted from an environment variable. Post-ledger targets
publish only below the explicit `canonical_publication` root, while writable
runtime records remain separate. The regenerated
network is `artifacts/targets-network-p9-v2-training/targets-network.html`.

## 9. V2-B Handoff

`python/p9_v2_training_lifecycle.py` builds existing `RunBundleInputs` from the
closed V2-A ledger, controller checkpoint inventory, exact authority, accepted
P8 row, cache acceptance, sampler/selection contracts, and ordered source
inventory. It uses the existing V2-B builder, locator, publisher, and validator.
Native authority binds both the source P8 scientific hash and the V2 canonical
bound-document hash because their approved numeric encodings differ.

## 10. V2-C Handoff

The adapter calls the existing pure finalizer with the existing selection
contract hash and validates its result. Worker best-state is never selection
authority. Finalization failure can be retried from the immutable bundle without
training.

## 11. Acceptance, Eligibility, and Resolver Handoff

The adapter calls the existing atomic/idempotent acceptance publisher, creates
the existing immutable eligibility document, then resolves the full accepted
checkpoint chain. The pilot's temporary noncanonical chain was:

- bundle: `p9rb_7265cb0b225c00f0078b511f`;
- finalization: `p9fin_0096fdb7fed0245857b67599`;
- acceptance: `p9accv2_9257f5113ae4659c57d6ae4e`;
- eligibility: `p9elig_9fe7a3a43044c8807d57f8ba`;
- resolved checkpoint: `p9ck_76889f4865fe48d6a2b84f40`.

These exist only under `/tmp/p9v2-remediation-20260901-3` and are ineligible for
production resolution.

## 12. Crash and Retry Matrix

| Scenario | Result |
|---|---|
| worker crash before request | prior ledger boundary only |
| staged payload without request | ignored noncanonical debris |
| checkpoint staging/payload/manifest crash | zero canonical checkpoint |
| directory published before event | immutable ineligible artifact; retry links once |
| event committed before/lost ACK | replay and duplicate request return same event |
| ledger append crash boundaries | previous state or exactly one event |
| duplicate controller | kernel lock rejection |
| stale owner-like bytes | harmless when kernel lock is free |
| finalization failure | deterministic retry, no training |
| acceptance failure | idempotent retry, no training |

Focused tests cover all ledger append boundaries, three checkpoint precommit
boundaries, post-publication retry, pre/post ledger linkage, lost ACK, staging
escape, duplicate request, and duplicate controller behavior.

## 13. Bounded Production-Shaped Pilot

The final pilot used the accepted real `cfg_d48` row (`d=d_c=48`, four heads,
head dimension 12, K=8, main augmentation, EMA 0.999, lambda-IP 1, LR 1e-3),
the production cache, two A6000 GPUs, NCCL, and global/per-rank batch 32/16.
It ran four uninterrupted updates and a logically equivalent 2+2 resumed
trajectory with a durable checkpoint at each bounded validation boundary.
There was no formal authority, formal run, or canonical cfg_d48 artifact.

Across remediation diagnostics, 22 temporary global optimizer-update boundaries
were executed: six in the initial pilot that exposed and led to correction of a
CUDA RNG restore issue, eight in the first successful equivalence run, and eight
in the final current-code evidence run. The final evidence run's scientific
trajectory contains four unique updates; rank-local `optimizer.step()` calls are
two per global boundary. All activity was noncanonical under `/tmp`.

## 14. Performance Sanity

| Boundary | Updates | Update wall | Median/update | Throughput | Peak VRAM | Rank skew | Commit ACK |
|---|---:|---:|---:|---:|---:|---:|---:|
| epoch 5 | 2 | 2.000 s | 1.000 s | 32.00 scenes/s | 2.71 GB | 0.0078 s | 0.0525 s |
| epoch 10 | 2 | 2.214 s | 1.107 s | 28.91 scenes/s | 3.29 GB | 0.0077 s | 0.0582 s |

No OOM, NaN/Inf, or material rank skew occurred. The bounded metric is explicitly
noncanonical and is not a replacement for the 800-query/400-gallery formal
validation implementation.

## 15. Evaluation Leakage

Evaluation query loads, gallery loads, embeddings, metrics, and consumption were
all zero. The temporary bundle records `evaluation_consumption_count = 0`.

## 16. Regression Validation

- Focused final worker/controller/ledger/replay tests: 57 passed, 0 failed.
- Comprehensive V2-A through V2-I and relevant P7/P8/P9 Python suite: 479
  passed, 0 failed in 232.77 seconds.
- Relevant R P9 suite: 54 passed, 2 failed, 0 errors. Both failures are the
  documented pre-existing isolated-formal generation assertions expecting
  `p9gen_acb72f...` rather than immutable `p9gen_batchuniq_20260831`; they were
  not changed.
- New V2 training graph R assertions: 8 passed, 0 failed (included above).
- `tar_validate()` passed for main, formal, recovery, and V2 training scripts
  using empty temporary stores; no target executed.
- 17 P9 V2 runtime schemas passed Draft 2020-12 checks; 12 Python files passed
  AST parsing, seven runtime modules imported, two YAML files parsed, and three
  R files parsed.
- Target network regeneration and `git diff --check` passed.

## 17. Immutability

| Evidence | Before | After |
|---|---|---|
| cfg_main payload | `fdac720bff12fb25747f69977bc69c5fb28adbc4a73cabd879b1b57c47cc06b6` | same |
| cfg_main manifest | `87010ce01ad74fc7b2652bf0e5a7e56baea2bef88400f6f23748d1e39f9227bc` | same |
| cfg_main acceptance file | `ad1fe493610f92fe97aa6f4b40048ff8d56e54d9e074cff74c43fe243df0a713` | same |
| V1 retirement manifest | `4fd252ecfefa7436b0665b97cabe5976f3000a827d8ad229d8f0a17b161aac91` | same |
| V1 source inventory | `282e8eb48ac5ae9efeabb5d535707e1e9273d3bfd803ec3b8c03f9b74063065c` | same, regression readback |
| dissertation HEAD | `ad8c8b5c17c5ca72dce7f30c2eb283f6041dbc9a` | same, clean |

Canonical files containing `cfg_d48`: zero before and after.

## 18. Prohibited-Work Accounting

| Activity | Count |
|---|---:|
| Formal production authority | 0 |
| Formal production run | 0 |
| Canonical cfg_d48 checkpoint | 0 |
| Canonical cfg_d48 acceptance | 0 |
| Other P9-A training | 0 |
| P9-B training | 0 |
| Held-out evaluation | 0 |
| P10/P11 | 0 |
| V1 execution | 0 |
| Historical mutation | 0 |
| Canonical cfg_main mutation | 0 |
| Temporary pilot global update boundaries | 22 |

## 19. Remaining State

The controller foundation and production-worker remediation are complete. Formal
P9-A execution has not started. Remaining P9-A configurations: 12. Remaining
P9-B comparisons: 7. Held-out evaluation remains not started.

## 20. Exact Next Work Unit

`P9-A cfg_d48 formal variant execution -- retry the same single variant using the now-complete V2 production lifecycle.`

No other variant should be authorized first.

## Prompt Summary

Implement the independent production V2 science worker, controller-owned
checkpoint request/ACK, complete exact resume, executable isolated V2-B/C/E
lifecycle, and a bounded update-capable two-GPU noncanonical pilot while keeping
formal authority, cfg_d48 canonical artifacts, evaluation, v1, and dissertation
mutations at zero.
