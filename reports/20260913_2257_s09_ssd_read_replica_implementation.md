# S09 SSD Read Replica Implementation

## Result

Implementation and qualification PASS. Full SSD replica creation is still pending.

- Created: 2026-09-13 22:57 Asia/Seoul.
- Repository: `/members/dhnyu/fuse`, branch `reduced`.
- Input HEAD: `1516bb98328b9838b012441afba6c443a7f66a57`.
- Request: implement and validate an independent SSD read path without bind mounts; current campaign reuse is not required.
- No commit or push was requested or performed. Implementation changes remain uncommitted.

## Campaign Stop

The active S09 torchrun was sent SIGTERM before implementation. The canonical controller recorded an operational interruption; no unrelated Huimori process was stopped.

- Interrupted configuration: `ofat_augmentation_intensity_0.5`.
- Run: `p9runv2_3e0993713f1dacd8ed329dc6`.
- Durable checkpoint: `p9ck_e60d9e45d4830042bb4bab90`, epoch 35/update 2660.
- Checkpoint payload SHA-256 remained `bdf638b29f12ca8047616ad00e73df866beefab4c062f2f8f7a920cbdfb2492f`.
- Existing history was preserved. Only normal interruption evidence was appended by the controller; historical logs were not manually rewritten.
- No formal campaign was restarted. The next campaign must use fresh runtime-bound identities, not this checkpoint.

## Read-Path Contract

`FUSE_S09_CACHE_READ_ROOT` selects a verified physical replica. Without it, canonical reads remain unchanged. An explicitly empty, missing, corrupt, mismatched or symlinked replica fails closed, without HDD fallback.

Canonical artifact identity and paths remain on HDD. The replica contains identical prepared, geometry/Fourier and DS payloads. Scene-center lineage resolution still uses the exact accepted canonical P1 evidence. Training and validation share the same production reader assembly.

`python/training_cache_storage.py` defines one manifest-based inventory and deterministic verification receipt. It rejects path traversal and source/destination aliasing. Sequential copying verifies SHA-256 before publication, never overwrites existing files, and preserves interrupted partial files for investigation. Existing complete files are reusable only after checksum verification. A receipt is written only after every inventory file passes.

Startup verifies the exact receipt, all inventory sizes and metadata hashes. Prepared payloads are checksum-checked before deserialization when using the replica; geometry and DS readers retain their payload checks. Full `verify` explicitly rehashes every replica file. Controller startup and run paths share the resolver and record placement in separate per-run cache-read evidence.

## Files

- New production helper: `python/training_cache_storage.py`.
- New operational CLI: `scripts/s09_cache_replica.py` (`plan`, `copy`, `verify`).
- Reader integration: `python/training_worker.py`, `python/training_prepared_cache.py`.
- Startup/read-root evidence: `scripts/training_controller.py`.
- Provenance registration: `config/s09_runtime_provenance.yml`.
- Tests: `tests/python/test_training_cache_storage.py`, `tests/python/test_cache_replica_real.py`, `tests/testthat/test-training-targets.R`.
- Operator documentation: `README.md`, S09 SSD read replica section.
- No target declarations or graph structure changed.

## Cache and Real SSD Qualification

- Cache: `s09cache_dc4e9e271e40ffe8ae17967c`.
- Acceptance: `s09ca_e2a1882eb206e1b5c930ddd5`.
- Prepared entries: 80,472.
- Complete replica inventory: 241,422 files, 316,304,040,996 bytes (approximately 294.6 GiB).
- Inventory SHA-256: `b62b68806b9e2633025195d9b4f9203dbe25c07d0db9b2169fcd6b30ac031b0f`.
- DS identity: `s09ds_3a46fc8888a324bd4297feb7`.

Real-data qualification copied 21 files (approximately 416 MiB) into `/members/dhnyu/.cache/fuse_ssd_qualification_20260913_2245`. The five selected records cover weak/main/strong training profiles and validation query/gallery. Prepared entity IDs matched, Fourier outputs were finite, and DS tensors were finite with shape 26 x 100 x 100. Source/copy checksums matched.

This is a test-only subset, not an activatable replica. Its reduced inventory was injected only inside the test; the unmodified production resolver rejects its receipt. No full 294.6 GiB copy was attempted, and no performance speedup or formal training throughput claim is made.

## Currentness and Provenance

- S08 remains `s08plan_7cd58ffb65db3d43fd3fa234`.
- Serialized S08 SHA-256: `74ae70958b96dd663d300c6f7441a0653b1a7c5066d6e1bfe9b4b459d7781789`.
- Fresh main research-store `tar_outdated()` was empty after implementation. S01-S08 do not become outdated from this independent read-path feature in the inspected current state.
- Training graph remains 29 targets / 80 edges / acyclic.
- Broad prepared-reader source tracking makes S09 cache source/acceptance/resolved-contract targets eligible for reevaluation. This is not physical payload regeneration: the unchanged builder resolves the same existing destination and validates/reuses its acceptance. That validation can still read HDD payload bytes and may be slow under contention. No target execution or metadata manipulation was used here.
- Previous runtime SHA: `b8d4230b54228c7db3ad9be87a3f579d5fafb188c5d38f5130ab2f73cdabbf4f`.
- New runtime SHA: `a2bbddf036e4a9a023caa32cbf7a10927d7b35450318121c47f9b3a6c2ecb06a`.
- Runtime registration now includes the storage resolver. Fresh OFAT authorities, fresh winner and all fresh comparisons are required. No legacy reuse or provenance rewriting is introduced.

## Validation

- `git diff --check`: PASS.
- Changed Python compilation, changed R test parse and YAML parse: PASS.
- `python -m pytest -q tests/python/test_training_cache_storage.py`: 18 PASS.
- Focused storage/prepared/dedup suite: 36 PASS, 660.07 seconds.
- Opt-in real SSD test (`FUSE_TEST_REAL_CACHE_REPLICA=1`, `tests/python/test_cache_replica_real.py`): 1 PASS, 148.18 seconds.
- `python -m pytest -q`: 661 PASS, 1 SKIP, 776.93 seconds. The default skip is the opt-in real-cache test, separately executed successfully above.
- `Rscript tests/testthat.R`: PASS.
- Main and training `tar_manifest()` / `tar_validate()`: PASS; main currentness empty; training DAG acyclic.
- Actual accepted-input resolution and complete manifest inventory planning: PASS.
- Final process inspection: no S09 controller/worker/torchrun; no GPU compute process. Canonical GPU locks were successfully acquired/released during availability verification.

Existing historical checkpoint/hash reads dominated slow regression runtime on the contended HDD. This is not an SSD throughput benchmark.

## Remaining Activation Work

Use the documented CLI to copy the full accepted cache into a separate SSD parent, then run full verification. This is a substantial read of the shared HDD and requires roughly 295 GiB plus safety headroom on SSD. Keep the canonical HDD source unchanged.

Only a complete verified replica may be selected with `FUSE_S09_CACHE_READ_ROOT`. A future formal launch additionally requires repository synchronization and fresh-runtime preflight, under separate authorization. Startup lineage metadata and possible cache acceptance revalidation still depend on HDD; this feature relocates bulk runtime payload reads, not the whole research store.

- Physical cache rebuild: NO.
- Full SSD replica created: NO.
- Formal training restarted: NO.
- New checkpoint/authority/acceptance publication: NO.
- Target-store manual edits: NO.
- S10: NO.
- Commit/push: NOT REQUESTED / NOT PERFORMED.

Final decision: SSD read-replica implementation and validation PASS; full copy and activation remain pending.
