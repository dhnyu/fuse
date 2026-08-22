# I23 Prototype Model Validation

## Verdict

`READY`

I23 `prototype_model_validation` was implemented, executed, and published. I24 and later targets were not declared or executed. No optimizer, scheduler, EMA, queue, masking, training checkpoint, or scientific upstream artifact was mutated.

## Purpose and scope

The task resolved the I23 retrieval contract by separating:

- qualitative self-excluding retrieval among 320 original prototype scenes, without relevance metrics;
- quantitative fixed-I19-augmentation source-scene retrieval, with the unaugmented source as the unique relevant candidate.

The accepted best checkpoint's online encoder produced L2-normalized 128-dimensional scene embeddings before the projection head. The scientific float64 reference namespace was excluded from the encoder path.

Prompt summary: audit current Git and accepted I20/I22 lineage, implement only I23, validate deterministic dual-GPU/40-worker inference, checkpoint state and immutable publication, then commit and push only after all gates pass.

## Execution

- Date: 2026-08-23 KST
- Final I23 target elapsed time: 634 seconds
- Full inference campaigns: 2
- CPU workers: 40 total, 20 per GPU
- Native threads per worker: 1
- GPUs: 2 x NVIDIA RTX A6000
- Peak allocated VRAM: 2,100,992,512 bytes / 1,824,288,768 bytes
- Small worker parity fixture: 8 scenes, 1 worker, GPU 0

The first accepted implementation run was superseded after adding a direct read-only controlled-checkpoint reload. Its immutable artifact was preserved. The final source produced a separate identity.

## Git audit

### Fuse

- Branch: `feature/research-scene-index`
- Starting local/remote HEAD: `63e582726de749be54aaf51d4b9aac6c4f6fa337`
- Starting divergence: 0 ahead / 0 behind
- Starting worktree: clean

### Dissertation

- Branch: `main`
- Local/remote HEAD: `0a251da679ef0e65967cca5e24e6b276988e28db`
- Divergence: 0 ahead / 0 behind
- Worktree: clean

Both remotes were fetched before implementation. The dissertation inference, spatial-scene retrieval, and augmented-source retrieval sections were audited.

## Parent and checkpoint validation

- I20 plan: `ptp_3b100622bdb733351db6e458`
- I20 run: `ptr_473911a4828ae5540a9d4eb9`
- I22: `pta_cf6bc4679a06305fb1185a8e`
- I16: `ptd_cee61a525ca92f1b7951c40d`
- I05: `pro_17040a91f3aee12b91c0bcd4`
- I19: `paa_8d73a94e574dcdbc5c5106d2`
- Best checkpoint: `epoch-005.pt`, epoch 5, optimizer step 40
- Best checkpoint SHA-256 before/after I23: `a17477a647d68024cb59ce6c3ce66a703e12143f37340b90c82cd3549b303704`
- Controlled checkpoint SHA-256: `2449f5c0491538e3e7fda4212f40ef289493ea7eaec0db8a863062efc7aeebd2`
- Controlled resume direct/replay digest: `1304777d4d8b52fc59668a112d5d9235edfbe00472972d7df094712d0af56216`
- Checkpoint rank-state count: 2
- Queue pointer/occupancy: 2,560 / 2,560
- Additional optimizer steps: 0

I22 outputs, I16 outputs, I05 index, I19 manifest, best checkpoint, checkpoint catalog, and controlled checkpoint were verified using recorded path, size, and SHA-256. The best and controlled checkpoints were loaded read-only on CPU. Previous single-GPU and failed-DDP lineage was rejected by exact plan/run/parent checks.

## I23 results

- Final identity: `pmv_1d5412a7b035635a4187fbf6`
- Original scene count/dimension: 320 / 128
- Finite and L2-normalized embeddings: 320 / 320
- Original embedding digest: `dfd450f3eb784eac2bb6b51c37491bd6d1dbba381cb08db4f171d53a2bee64a6`
- Original candidate count per query: 319
- Original ranking rows: 102,080
- Original ranking digest: `9ca1e7408e9a5fe562c15c2e074767395e594c0f449e8fa75b8147edc2495ae2`
- Original self-candidate count: 0
- Original MRR/HIT: not computed because relevance ground truth is absent

Fixed I19 epoch 0/view 0 augmented-source retrieval:

- Query/candidate count: 320 / 320
- MRR: 0.904732
- HIT@1: 0.859375
- HIT@5: 0.965625
- HIT@10: 0.984375
- Query embedding digest: `67960b740ae32e2d32a0c03f4a0bd78a7f88c9584c2a48687a9e01eca1734cb8`
- Ranking digest: `81f5df2815a2d75077c5403f6f156f0b80d145297c0c572c5583d3ca43a4d9d9`
- Augmentation digest: `040aa90193d0b9d14e8d849c94c4be97cf463d6654a131718c84612b44827d9e`

Fresh-process checkpoint reload, canonical versus deterministic shuffled input order, alternate GPU partition, 40-worker repeat, canonical scene merge, and the small 1-worker parity subset were exact.

## Publication and validation

- Atomic immutable publication: PASS
- Identical rebuild reuse: PASS
- Same-ID/different-content hard failure: PASS
- Python tests: 38 PASS
- Full `Rscript tests/testthat.R`: PASS
- Python/R/YAML/JSON/schema parsing: PASS
- Output schema, checksum and Parquet QC: PASS
- `tar_manifest()`: PASS; I23 declared, I24 absent
- `tar_network()`: direct I23 parents are I22, I16, I05, and the scoped contract target
- `tar_validate()`: PASS
- Scoped `tar_make()`: PASS; final repeat skipped all 144 targets
- Dependency HTML: regenerated
- Final `tar_outdated()`: empty

Scoped I16/I22/I23 metadata contains no warning or error. The global store retains seven historical diagnostic metadata rows, including the superseded failed I21 execution; these were preserved deliberately and are not part of the accepted I23 lineage.

## Limitations and next boundary

- The 320-scene prototype is a correctness smoke, not final scientific performance evidence.
- Original-scene rankings have no relevance ground truth and therefore intentionally have no MRR/HIT metrics.
- Quantitative metrics apply only to fixed augmented-source retrieval.
- I24 and all downstream stages remain undeclared and unexecuted.

## Git result

Commit SHA and push result are appended in the final response after the audited source/test/documentation commit succeeds. Runtime data, target store, checkpoints, caches, and logs are excluded from Git.
