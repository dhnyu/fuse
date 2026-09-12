# S09 Generation-Aware Accepted-Run Deduplication Repair

## Verdict and Scope

PASS_S09_GENERATION_AWARE_DEDUP_REPAIRED

Created: 2026-09-12 13:52 Asia/Seoul.
Input HEAD: a4fc4b1ade11adaf7fd5a398c8eb69fff98d4236.
Implementation HEAD: d809bc3c1b13d17b959eaa34033fc4383ef4d81d.
Branch: reduced.

Request: repair accepted-run startup deduplication for explicitly required fresh runtime generations, without weakening same-generation protection, changing historical evidence, or executing training. Authoritative failure evidence: reports/20260912_1330_s09_fresh_formal_training_blocked_preflight.md.

## Original Blocker

Historical accepted main:
- authority: s09auth_6446cd16ebc90b8d29a07d8a
- run: p9runv2_1a7e1c84f3ee97d3d2dda4c3
- acceptance: p9accv2_da4a9fb15672bca5176ee25a
- runtime: 0479d8ae41fb22a4c3c2f82360fa2d12cd0f59fd73d8a50ef0868d2eff1cf66d

Fresh main blocked before NCCL, epoch/update 0/0, no checkpoint:
- authority: s09auth_4d2bb6e9c91c5e716897a7c9
- run: p9runv2_dd31b0e48cfb912868895c3b
- runtime: baf19aa078973c19e19ed55c8ea6ee2f733db9d9b94a33b0c8e03e74fc695c9a

Both bind configuration ID main and configuration hash
1b62f3adfa01096de5bcb3309b5db2cbe89a823ae4c86e706870da80ba364be1.
The old resolver returned unscoped configuration ID/hash sets. validate_startup independently appended SCIENTIFIC_CONFIGURATION_ALREADY_ACCEPTED for either match. Runtime and authority identity were ignored at both preflight and run call sites.

## Canonical Scope and Generation Semantics

Duplicate domain = (experiment_plan_id, scientific_implementation_hash, phase).
Within that domain, matching configuration ID OR matching configuration hash is a duplicate.

Phase separates OFAT from COMPARISON without allowing alternate seeds or authority IDs to evade accepted-configuration protection. The existing CampaignProgress.ensure_generation contract uses runtime SHA as the generation key. This repair preserves that contract; a timestamp alone does not authorize another accepted run under the same runtime. No independent generation schema was invented.

Historical evidence with a different valid runtime belongs to another domain. Evidence whose internal plan/runtime/configuration bindings disagree fails validation rather than being filtered away.

## Eligibility Resolution and Fail-Closed Behavior

The existing eligibility v2 snapshot remains unchanged:
- /mnt/hdd002/dhnyu/fusedata/models/reduced/training/canonical/eligibility/current.json
- p9elig_16576fdec2ec46237a4fa0a8

Every ELIGIBLE entry is validated before runtime filtering:
1. Canonical eligibility schema, content hash, identity and uniqueness validation.
2. Referenced immutable acceptance and bundled authority validation.
3. Exact agreement between eligibility, acceptance and authority IDs/hashes.
4. Recomputed scientific run key and deterministic run ID.
5. Native checkpoint namespace derived from run ID; physical checkpoint root derived from configured writable root and scientific run key.
6. Existing canonical validate_acceptance verifies the bundle, ledger, checkpoint manifests/payload hashes, finalization, selection and parent/configuration bindings.
7. Duplicate accepted entries with inconsistent or ambiguous same-domain configuration membership are rejected.

Missing snapshots now fail closed instead of silently returning empty sets. Missing/corrupt authorities, inconsistent runtime/plan/configuration, corrupt acceptance/checkpoint evidence, invalid snapshot hashes and duplicate entries fail. No directory discovery or historical fallback is used.

No eligibility schema migration is needed: v2 rows resolve their missing runtime/plan fields through the referenced immutable authority. Unsupported extra fields remain rejected by the existing schema. No historical snapshot was rewritten.

Both startup-preflight and actual run call the same validate_formal_startup helper, which obtains validated records and calls validate_startup. AST parity regression ensures neither site retains an independent rule.

## Regression Evidence

All 11 historical OFAT accepted chains validated read-only. The originally requested fresh baf19aa runtime authorities all pass scoped startup checks against those historical records, including the exact main authority/run above. All 11 authorities computed for the repaired runtime also pass. Injecting a same-domain accepted record blocks each.

FM comparison fixtures prove old-runtime allowance and same-runtime rejection. Config-ID and config-hash-only collisions are tested independently. Production branch/clean checks remain enabled in normal execution; real-evidence tests explicitly permit the implementation worktree and supply a device-count fixture without initializing GPUs.

No authority, ledger, acceptance, result or checkpoint was published by these tests.

## Files Changed

- python/training_controller.py: immutable accepted record, domain/key logic, canonical full-evidence resolver, scoped startup check.
- scripts/training_controller.py: one shared formal startup helper for both call sites.
- config/s09_runtime_provenance.yml: explicitly register the runtime-used Python controller/resolver.
- tests/python/test_training_dedup.py: focused scope, corruption, parity, current-evidence and cache-isolation regressions.
- tests/testthat/test-training-targets.R: require the additional runtime source and updated count.

## Runtime Provenance and Next Identities

Before:
baf19aa078973c19e19ed55c8ea6ee2f733db9d9b94a33b0c8e03e74fc695c9a

After:
b8d4230b54228c7db3ad9be87a3f579d5fafb188c5d38f5130ab2f73cdabbf4f

The controller script was already runtime-bound. The imported Python resolver is now explicitly registered too, giving 18 runtime sources. Hash stability was not forced. All fresh campaign authorities must bind the new hash.

Deterministically computed in memory, not published:
- main authority: s09auth_2ed0ddd6042ae8e5c13324a8
- main run: p9runv2_55d86411eb39b39b625cc53c

GLOBAL_RETRAIN_REQUIRED remains binding. Next separately authorized execution starts fresh OFAT main epoch 0 with no old checkpoint, then all 11 fresh OFAT, new winner and all 17 fresh comparisons. Neither the historical accepted campaign nor the baf19aa failed startup is resumed.

## S08, Cache and Currentness

S08 remains s08plan_7cd58ffb65db3d43fd3fa234.
Serialized SHA remains 74ae70958b96dd663d300c6f7441a0653b1a7c5066d6e1bfe9b4b459d7781789.

Cache remains s09cache_dc4e9e271e40ffe8ae17967c.
Acceptance remains s09ca_e2a1882eb206e1b5c930ddd5.
Read-only accepted-input resolution verified manifest/acceptance bindings and presence/size inventory of 80,472 payloads. No full 296 GiB rehash or payload rebuild was performed.

Main research tar_outdated is empty.
Read-only training-store currentness reports runtime provenance, authority and downstream lifecycle/winner/campaign work pending. Prepared-cache sources, prepared-cache acceptance and resolved contract are NOT outdated. The next run naturally reuses the cache and rematerializes authorities under the new runtime. No targets metadata was manually changed.

## Validation

- git diff --check: PASS.
- Python compile of changed modules/tests: PASS.
- Runtime YAML and eligibility schema parsing: PASS.
- R parse of changed test: PASS.
- Focused controller/campaign tests: 39 PASS.
- Focused dedup/controller/acceptance/checkpoint tests: 101 PASS.
- Final python -m pytest -q: 643 PASS in 152.37 seconds.
- Final Rscript tests/testthat.R: PASS.
- _targets.R manifest/validate/DAG: PASS, 61 targets / 212 edges.
- _targets_training.R manifest/validate/DAG: PASS, 29 targets / 80 edges.
- Main research-store currentness: empty.
- Training currentness inspection: read-only, cache current/reusable.

Initial test runs exposed test-fixture naming/permissions issues and the old expected runtime-source count; these were corrected before the final passing suites. No production defect was bypassed. No target declarations or graph structure changed, so no network HTML regeneration was required. GPU smoke was not rerun: this task prohibits GPU/DDP execution and does not alter worker science.

## Preservation and Execution Boundaries

Before/after SHA comparison: 2,708 protected files identical, including the previous audit evidence set, checkpoints, eligibility/acceptances, winner, formal logs and real training-store files. Baseline: /tmp/s09_dedup_preservation.json; checker: /tmp/s09_dedup_preserve.py. Cache payload protection uses accepted manifest/inventory evidence, not a redundant full payload-byte rehash.

Preflight confirmed synchronized reduced branch, no active S09/DDP processes, no GPU compute workload and available canonical GPU locks. Post-check found no GPU compute processes. No training workers or GPU contexts were started.

- training/GPU/DDP = NO
- checkpoint publication = NO
- production authority/result/acceptance publication = NO
- cache rebuild = NO
- historical evidence mutation = NO
- formal log mutation = NO
- target-store manual edit = NO
- source hot-patch during training = NO

## Commit and Push

Implementation commit d809bc3c1b13d17b959eaa34033fc4383ef4d81d:
fix(s09): scope accepted-run deduplication by runtime

Implementation push to origin/reduced: PASS.
This report is recorded in a subsequent report-only commit; its final SHA and synchronization result are reported in the task response.

## Next Action

Do not start training in this repair task. A separately authorized Rscript scripts/run_training_targets.R campaign must use the existing cache and the new runtime-bound main authority/run from epoch 0. Same-runtime accepted duplicates remain forbidden.
