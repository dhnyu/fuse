# S10 common geometry Fourier cache

Created: 2026-09-16T12:07:14.766069+09:00

## 1. FINAL STATUS

**PASS — bounded implementation, exact equivalence and validation.** Production S10 was not executed. Commit/push is authorized for this result; final commit identity is reported separately after publication.

Scope/input prompt: retain batch=1, extract checkpoint-independent deterministic GPU Fourier features into one immutable S10 artifact shared by 25 configurations; preserve S09, relation math, precision and retrieval protocol. Revalidate the pre-existing reader proposal separately. Maximum real benchmark population: 100 evaluation originals, never 9,000. No training or S11 execution/repair.

## 2. REPOSITORY STATE

Repository: `/members/dhnyu/fuse` (`~/fuse`); branch `reduced`; starting HEAD and last pushed implementation: `ecc6651313fff68f4090629cc934ee0a72759abe`. Fetched origin; divergence 0 ahead / 0 behind at audit. No branch switch or reset.

Starting worktree was intentionally dirty: prior reader proposal in `python/retrieval_pipeline.py`, blueprint, and untracked `python/retrieval_originals.py`, `scripts/benchmark_retrieval_visualization.py`, `tests/python/test_retrieval_originals.py`. These changes were preserved, reviewed and included only after revalidation. Previous report `reports/20260916_1121_s10_performance_audit.md` was read, not rewritten.

Authority: current reduced blueprint and dissertation `sections/chapters/methodology/02-object-modal-embeddings.typ` (magnitude/phase and geometry embedding), plus current accepted S09 lineage. No mathematical conflict found. Canonical parent remains `s09camp_d2f6749da19ad6aa56c2d303` PASS, preprocessing `ppc_603236bfd673bda81a56d7c3`, original cache identity `oscache_75a543f656ab777aada74fbd`.

## 3. FOURIER CACHEABILITY PROOF

Original S10 call: `retrieval_inference.infer` -> `scene_model.geometry_fourier_features` re-export -> `scene_encoder.geometry_fourier_features(..., implementation="vectorized")`. New common target calls that exact same function with `collate([original_sample], vocabulary)` and the routed geometry configuration, on cuda:0. No CPU replacement or approximation is introduced.

The function reads `batch.geometry`, `entities.entity_type` and fixed frequency/scale settings. It does not read model/checkpoint weights, optimizer, hidden dimension, augmentation profile, relation graph edges, query/gallery role or family parameters. Therefore F(ordered original geometry, fixed geometry configuration, bound implementation/device/runtime) is reusable. Source coordinates and entity order remain exact. Model-family projection is still applied *after* raw Fourier retrieval with unchanged `project`/`project_fourier`.

Roads use the existing segment integral. Buildings preserve exterior/hole, component and triangulation ordering, with the same float64 CPU Triangle preprocessing (`pYQ`) inside the accepted function and float32/complex64 GPU integral path. Coordinates are scaled by 500 m. Magnitude is log1p(abs(response)); phase concatenates cosine/sine of the existing angle. POI rows stay zero; empty entity tensors and empty non-POI response behavior are unchanged. The existing frequency memo depends only on device/frequency settings.

Cache boundary is magnitude [N,128] and phase [N,256], float32, before learned `magnitude_encoder`, `phase_encoder`, `geometry_fusion` or any checkpoint-dependent projection. Those learned layers and `RelationAwareLayer` are unchanged. Inference mode, eval mode, deterministic algorithms, dropout disabling and batch=1 remain in effect.

## 4. GEOMETRY CONFIG IDENTITY

All 28 routed accepted scientific configurations were inspected, not inferred from filenames. All share these geometry settings; exactly 25 consume them.

| Setting | Value |
|---|---:|
| normalization_length_m | 500.0 |
| radial_frequencies | 8 |
| angular_orientations | 16 |
| minimum_radial_frequency | 0.5 |
| maximum_radial_frequency | 50.0 |
| output dtype / widths | float32 / 128 magnitude, 256 phase |
| device / batch / threads | cuda:0 / 1 / 1 |

Configuration SHA256: `375399289d43db57211ad6ff7e5817a670a4aa736e43edbc8db3cb3477c253cc`.

Active: all 11 OFAT configurations; cmp_FM, cmp_A2, cmp_A3, cmp_A4, cmp_A5, cmp_B1–cmp_B9. Inactive: cmp_A1, cmp_SSV, cmp_DS. Dimension 64/128/256 does not enter F. Different geometry configurations would receive separate deterministic hash-keyed groups; no forced equivalence.

Accepted configuration/checkpoint payload audit (all 28 SHA256 rechecked after benchmarks):

| Configuration | Payload SHA256 |
|---|---|

| main | `ff2711306b071c55b5dad01dc654e5079de19ece8ba7fa4001f8b66b9dd79248` |

| ofat_d_64 | `8dec75ed88831219b1ad9e4cd78f654f611f8aef442683540fa11aab2d05ac28` |

| ofat_d_256 | `3e94d954b8a0a0578716976f98c4eb5466c289a0118ec3b40ac9824a0a771f1b` |

| ofat_K_aug_4 | `3ac8209fa7908c5ae9eee90ef8c1d7545ef6766b97107d3e450d3982d65ebfd6` |

| ofat_K_aug_16 | `b2f71f0ae539c41dd457b967a7b3fcc5658e7569c3169ca3a9dc98d3bd752509` |

| ofat_augmentation_intensity_0.5 | `6a5688bd3120347fbb1e35a5c2fcd87ae05d281426918eabbe169f12e65562e5` |

| ofat_augmentation_intensity_2.0 | `f42693ab7369071347538be8ddd671b33e37ab0090aa99bcd3487316ed992e0c` |

| ofat_ema_momentum_0.99 | `9d0175606c4aaba777840e678e79ff34df9f958b882659d559a89bf5f8319d86` |

| ofat_peak_learning_rate_0.002 | `52c7fc2fcce3c5125d14ab19e2afe5712bd4266087642b2ae27a102cccf4ae23` |

| ofat_peak_learning_rate_0.003 | `15c9207fa63a681374a26c800b5c8649538e097dcb9f0962184773bb1de7ade1` |

| ofat_peak_learning_rate_0.005 | `6c4c04fc07b5492ad90d98e16e9f0f06e2ac8b62732d77bd4217953e0d37c187` |

| cmp_FM | `b4a8e6f224536525679d83c574d5458f4887ed262b5914bcafbf9446304fed22` |

| cmp_A1 | `8a00f264293ce8a571a4ab909b50ba24a85065d3b2217ec6d8bb8e38b080b54c` |

| cmp_A2 | `2494e3bfad839b3ff022e3e7cf70558fbedb971f17303678df9e780833332ae7` |

| cmp_A3 | `a07e60b1f792acbc355d12183a1dac3b219883ae5914fcf9af4d5b4d98a2f040` |

| cmp_A4 | `28df238b89ed74a0e3b389ca62ca661812eb8ec0da1addb446520f8d104b5a1c` |

| cmp_A5 | `06e6fdd7a98db8caa24fdd4bb41d835fb12299351be5e79c2b21e0bc429e4614` |

| cmp_SSV | `f1bb1d2d6d424cb377fb21a193e0a60186dbcb669a0b6a476b8a26971e568040` |

| cmp_DS | `8f1033dbe02a1a6dd9d2cda84ad6cb673bfbe8f652bc75d8c9a438dadf2e45ad` |

| cmp_B1 | `84f7dcb76f13373486aacd35592e3d85fbe5238771846d34229b2c6928b9dc97` |

| cmp_B2 | `3d1b83c566ea9713e8f3dfc420d2d2acdbd97f0ddc7d8df1c6451e9376cf0eb4` |

| cmp_B3 | `30a68f9ae54b85642b3351351e4277033111cc31f430bef174e34ff3c6054417` |

| cmp_B4 | `c693b98fcd50c8b2879fb74068ba78405177da64d3086db61c1b91759adcfe4e` |

| cmp_B5 | `8e348bc8567d808a06f1801ce88309f85787360d2b26e1b9d2000b1a0eed6260` |

| cmp_B6 | `c7657eb5f7ca3f24fa0a61cc7a688f224f3bca149178f45bbb85a6d1338c3e6a` |

| cmp_B7 | `e9530d8641848b7889575714aa2c219f2f870bd6252349e314892c8d3071d5ed` |

| cmp_B8 | `49be63a3272f676069df968bc877aa4ae35204267a4a0e0d3f30af7b786ce3dc` |

| cmp_B9 | `f32cf794865ccce0f6a50b8e1c479ff9e9cc57d56bbcb7e39a85343d55ae484f` |

## 5. CACHE ARTIFACT DESIGN

S10-only `geometry_features/<geometry_config_sha256>/<six-digit-shard>.pt` plus `manifest.json` beneath its generation root. PyTorch shards contain at most 100 scenes, sorted by scene_id, each holding the source record and two contiguous CPU float32 tensors copied from the unchanged GPU computation. One shard is retained by the reader at a time. Copy/storage/readback is byte-exact, not a CPU recomputation.

Kind `geometry_features`, schema `s10-fourier-v1`. Envelope includes artifact ID, payload paths/size/SHA256, body identity and immutable create-or-validate publication. Record key includes scene ID, exact original manifest and payload SHA256, preprocessing ID/hash, category hash, geometry configuration SHA, implementation SHA, geometry layout version, entity-order hash, dtype, shapes, generation and runtime ID. Manifest includes source model/query/gallery bindings, scene count/order, configuration groups, per-tensor SHA256 and deterministic creation metadata. Implementation identity hashes scene_encoder, scene_model, model_data, training_support, training_family_inputs and the S10 cache implementation. Runtime additionally binds source closure, Torch/NumPy/Arrow/Shapely/Zarr/Triangle versions, CUDA/cuDNN, GPU identity, seed, threads, dtype and determinism settings.

No timestamps/wall timings enter scientific identity. They live in benchmark telemetry. Same identity + different bytes fails without overwrite. Missing/corrupt/stale config, implementation, source, scene order, shape or tensor hashes fail without recomputation fallback. Full-scope generation requires explicit authorization. Noncanonical builder scope is limited to 100 and forbidden under the formal publication root. Failed/OOM generation cannot publish a completion manifest; already published immutable shards can be validated during a later retry.

Historical S09 geometry cache is not adopted: it does not contain this evaluation population. The prepared S09 input cache has training/validation views, not reusable canonical evaluation originals. Accepted P3 originals and the exact current S09 preprocessing/category bindings remain the input authority.

## 6. TARGET GRAPH CHANGE

`original_inputs -> geometry_features -> embeddings -> rankings -> renders/pages/summary/acceptance`.

New `s10_retrieval_geometry_features` is explicit in `targets/s10_retrieval_visualization.R`, with the existing GPU controller and device lock. Independent S10 entrypoint/store remains unchanged. All dynamic embedding branches wait for the common target, but inactive branches never load its manifest or payload. Active branches require the cache and bind its artifact ID into embedding artifacts. Final acceptance validates the source/config/model-group bindings and includes the geometry manifest identity.

S10 manifest/network: **16 targets, 49 edges**, one component; controller/resources, no training target, no S11 target and `tar_validate()` all PASS. The default network renderer and S10 definition-only renderer ran. S10 HTML is refreshed at `artifacts/targets-network/s10/targets-network.html`; definition-only status is all outdated because no formal targets have been run. The unrelated main graph remains 61 targets / 212 edges.

## 7. EXACT EQUIVALENCE RESULTS

100 originals were chosen without model results: the existing six geographically spread smoke scenes, then 94 fixed-PCG64-20260916 originals. All comparisons use canonical scene-ID order. Original selection receipt and all scalar telemetry are retained in the local task log; tensor/cache/checkpoint data are not committed.

A. Reader only: legacy originals vs optimized originals are identical serialized `.pt` bytes for all 100; original manifest bytes also match. For each representative model, legacy-on-the-fly and reader-on-the-fly full forward-argument hashes, embeddings, cosines and rankings match.

B. Fourier only: the same optimized originals feed on-the-fly vs cached Fourier. Independently computed GPU features and cached readback match raw tensor bytes for all 100. All 25 family projections match exact dtype/shape/bytes. Main, A4 and d256 full forward-argument traces, final embeddings and cosine matrices are exact.

C. Combined: legacy reader + on-the-fly versus optimized reader + cache matches the same strict checks for all four representative models. Tolerance is not used. The benchmark initially used exact numeric equality for arrays; a separate saved-output postcheck additionally verified dtype, shape and raw bytes, including signed-zero distinctions. Forward input tracing already hashed raw tensor bytes.

For every path/model: 30 fixed queries × two modes × Top50 = 3,000 pilot ranking rows, identical scores, candidate ordering and scene-ID tie breaking. Existing ranking implementation is unchanged. Formal expected 84,000 rows and the distance >=2000 m rule are unchanged. Pilot candidates remain noncanonical subsets.

## 8. EDGELESS SCENE VALIDATION

Both `scn_40cc5ee26478726df91243a6` and `scn_709daf6833f15dfc32609f81` occur in the 100-scene population. Their complete model inputs and embeddings match in all four model comparisons. Both were also explicitly used as queries in an additional standard/non-local Top50 comparison (200 rows/model/path): exact equality PASS.

No graph batch-context fix was attempted. No relation bias, branch, architecture or frozen scientific source changed. Batch>1 is rejected at S10 configuration/inference boundaries and was not benchmarked in this task. DS consumed a deliberately nonexistent geometry-cache path without opening it; Fourier calls/read time remained zero.

## 9. STORAGE BENCHMARK

100 scenes, same independently computed GPU tensors; /tmp storage, warm OS cache. All three layouts additionally passed strict raw-byte readback comparison. Peak RAM includes the Python process and resident prototype tensors; it is not incremental format overhead.

| Layout | Write s | Read s | Files | Bytes | Peak write/read RAM GB |
|---|---:|---:|---:|---:|---:|
| Per-scene .pt | 0.214 | 0.081 | 100 | 123,732,148 | 1.467 / 1.348 |
| 100-scene .pt shard | 0.119 | 0.069 | 1 | 123,607,791 | 1.473 / 1.473 |
| Contiguous NumPy + index | 0.159 | 0.060 | 3 | 123,556,928 | 1.510 / 1.443 |

Choose the simple existing PyTorch representation in 100-scene shards: modest measured improvement and 100× fewer files, without offset/mmap complexity. Approximately 90 payload files / 11.1 GB at this sample's density for 9,000 scenes; actual density changes size. No original-input storage format migration.

## 10. 6/25/50/100 CACHE BENCHMARK

Fresh output per run; same nested source subsets. Includes verified original loads, unchanged GPU F, CPU copy, serialization, payload hashing and manifest publication. CPU % is process CPU / wall (100% = one core); I/O wait is host-wide, not causal attribution.

| Scenes | Wall s | scenes/s | CPU % | GPU mean % | GPU peak MiB | Peak RAM GB | Read/write bytes |
|---|---:|---:|---:|---:|---:|---:|---:|

| 6 | 2.490 | 2.410 | 99.2 | 33.4 | 439 | 1.266 | 0 / 8,531,968 |

| 25 | 11.897 | 2.101 | 100.0 | 40.5 | 441 | 1.361 | 4,096 / 40,857,600 |

| 50 | 19.883 | 2.515 | 100.0 | 39.8 | 441 | 1.408 | 4,096 / 64,798,720 |

| 100 | 38.154 | 2.621 | 100.0 | 39.8 | 443 | 1.527 | 8,192 / 123,793,408 |

A second fresh 100-scene cache took 38.020 s. Manifest bytes, payload bytes, ordering and tensors all matched. Artifact ID: `s10_geometry_features_47d1c8eca88994a076f55997`. Runtime ID: `97784e95f7ca4a7a535caa44f9ee6778ec42265867fd59a93ebc31b669ff8954`.

Read-byte counters near zero reflect the OS page cache; they do not mean no logical I/O. Raw read_chars/write_chars, host I/O wait, process and CUDA memory are preserved in telemetry. Partial shards (6/25/50) passed the same reader contract.

## 11. 100-SCENE MODEL INFERENCE BENCHMARK

All runs on cuda:0, NVIDIA RTX A6000, batch=1, one internal CPU thread, float32, deterministic algorithms, TF32 off. Model construction/checkpoint loading, source/cache verification and tracing are included in total wall. Model-forward and cache-read subtimers are subsets, not additive to unrelated setup costs.

| Model | Path | Wall s | scenes/s | Forward s | Fourier s | Cache read s | CPU % | GPU mean % | GPU peak MiB | RAM GB |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|

| main | legacy_onfly | 39.132 | 2.56 | 0.770 | 37.537 | 0.000 | 100.1 | 39.7 | 645 | 2.086 |

| main | reader_onfly | 38.999 | 2.56 | 0.487 | 37.706 | 0.000 | 100.1 | 40.1 | 651 | 2.105 |

| main | reader_cached | 1.478 | 67.68 | 0.474 | 0.000 | 0.198 | 100.8 | 30.0 | 657 | 2.215 |

| cmp_A4 | legacy_onfly | 38.914 | 2.57 | 0.469 | 37.690 | 0.000 | 100.1 | 40.2 | 989 | 2.172 |

| cmp_A4 | reader_onfly | 38.844 | 2.57 | 0.459 | 37.633 | 0.000 | 100.1 | 40.6 | 1005 | 2.180 |

| cmp_A4 | reader_cached | 1.378 | 72.59 | 0.442 | 0.000 | 0.176 | 100.2 | 31.7 | 1019 | 2.221 |

| ofat_d_256 | legacy_onfly | 39.434 | 2.54 | 0.538 | 38.044 | 0.000 | 100.1 | 39.7 | 1041 | 2.197 |

| ofat_d_256 | reader_onfly | 39.742 | 2.52 | 0.543 | 38.332 | 0.000 | 100.1 | 39.7 | 1059 | 2.197 |

| ofat_d_256 | reader_cached | 1.550 | 64.53 | 0.515 | 0.000 | 0.172 | 100.7 | 30.0 | 1075 | 2.234 |

| cmp_DS | legacy_onfly | 11.434 | 8.75 | 0.046 | 0.000 | 0.000 | 100.1 | 1.6 | 1075 | 2.220 |

| cmp_DS | reader_onfly | 11.426 | 8.75 | 0.045 | 0.000 | 0.000 | 100.1 | 0.5 | 1075 | 2.221 |

| cmp_DS | reader_cached | 11.433 | 8.75 | 0.045 | 0.000 | 0.000 | 100.1 | 0.2 | 1075 | 2.222 |

All output-equality checks PASS. Cached active paths make zero Fourier calls. Cached GPU utilization has only three 0.5-second samples, so it is not a reliable steady-state estimate. GPU peak is nvidia-smi process-era usage, affected by retained Torch allocator memory from earlier models; raw CUDA allocated peaks are logged separately. All model runs reported physical read/write bytes 0/0 due to warm cache/no publication within the timed infer call.

## 12. READER OPTIMIZATION STATUS

Adopted independently after exact equivalence. Arrow filtering before Python conversion and shard-local reuse remove whole-shard Python materialization per scene. Spatial/tensorization mathematics and canonical source hashes are unchanged. Rendering uses the same vector scene content without loading unused rasters/relations. Per-validation-call common-input hash memo avoids repeated identical verification within a single validation; subsequent calls recheck bytes.

100-scene preparation: 43.912 s first / 47.406 s immediate rerun, 100 files, 142,753,564 output bytes, peak RAM 1.735 / 1.749 GB. 68 distinct source shards: relation table filtering ~23–25 s, vector reads ~7–8 s, raster tables ~3 s, extraction/arrays ~3–4 s, tensorization ~3 s. The legacy exact-input fixture took 375.920 s with four CPU workers × one thread (bounded equivalence fixture only, not a production concurrency proposal). Every legacy payload matched optimized bytes.

The original 6 scenes / 84 s bottleneck was whole-shard conversion/repeated I/O, not a scientific requirement. The old 35-hour preparation extrapolation is invalid after this reader fix and was already rejected in the prior audit. Full original preparation is estimated separately from Fourier and model forward.

## 13. NEW FULL-S10 RUNTIME ESTIMATE

Planning estimates, not production measurements. Single GPU worker, batch=1, CPU threads=1; no production execution performed. Current configurations require exactly **one Fourier evaluation per scene**, rather than 25: **225,000 -> 9,000** calls, with all 25 active embedding branches making zero calls. Additional bounded validation reruns are separate from that production graph count.

Measured bases: 38.154 s / 100 cache generation gives 0.954 h / 9,000; active cached mean ~1.468 s / 100 gives ~0.918 h / (25 × 9,000) before larger-manifest/HDD overhead; DS 11.433 s / 100 gives 0.858 h if conservatively used as a proxy for all three inactive configurations. A1/SSV full inference was not benchmarked. Prior 6/25/50/100 reader fit accounts for 96 total source shards; naive current sparse-100 preparation extrapolation is ~1.1–1.2 h and is covered by the conservative bound. Prior rendering pilot was 100 scenes / 11.986 s; current viewer smoke reconfirms compatibility.

| Phase (hours) | Optimistic | Likely | Conservative |
|---|---:|---:|---:|
| Common original preparation | 0.17 | 0.35 | 1.50 |
| One-time GPU Fourier cache | 0.85 | 1.05 | 1.50 |
| 25 active cached inference configurations | 0.80 | 1.25 | 2.50 |
| 3 inactive configurations | 0.30 | 0.86 | 1.20 |
| Ranking | 0.01 | 0.05 | 0.20 |
| Rendering/pages | 0.10 | 0.25 | 0.60 |
| Final acceptance verification | 0.03 | 0.15 | 0.40 |
| Process startup/repeated hash/schema/I/O allowance | 0.10 | 0.30 | 0.75 |
| **Total** | **2.36** | **4.26** | **8.65** |

Use **about 4.3 hours likely, roughly 2.4–8.7 hours planning range**, versus previous 28.55 h likely. These are scenario allowances, not statistical confidence intervals. Geometry density outside 100 scenes, cold HDD throughput, large manifest/schema verification, original/cache rereads, and unmeasured families can shift runtime. Temporary benchmarks use warm /tmp storage; do not equate it to cold formal HDD throughput.

Remaining costs are one-time exact GPU Fourier construction, repeated verified input/cache reading and family projection (especially DS: ~11.4 s total versus ~0.045 s model forward), plus rendering/acceptance. No further model/data algorithm changes were made to chase those costs.

## 14. TEST RESULTS

**206 Python tests PASS** (existing 188 maintained plus 18 cache contract tests; 16.10 s). Tests cover config grouping/active status, stale config/source/implementation rejection, tensor/payload corruption, missing scene/index/order, immutable collisions, deterministic reruns, exact empty/nonempty plumbing, DS never reading cache, OOM with no completion manifest, batch-one schema/runtime enforcement and no training/S11 execution dependency. Existing viewer/checkpoint/ranking/reader and frozen family tests remain intact. Real GPU final-embedding and edgeless proofs are the 100-scene integration benchmark, not mocked unit claims.

Changed Python syntax and R parse PASS; schemas exercised on all generated manifests. R target tests: 13 assertions, zero failure/warning/skip; tar_manifest, tar_network and tar_validate PASS. Both dependency HTML render commands succeeded. No formal tar_make was run.

Validation commands:

```sh
PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 pytest -q \
  tests/python/test_retrieval_visualization.py tests/python/test_retrieval_originals.py \
  tests/python/test_retrieval_geometry.py tests/python/test_evaluation.py \
  tests/python/test_checkpoint_resolution.py tests/python/test_training_family_projection.py \
  tests/python/test_training_family_encoder.py
python scripts/smoke_retrieval_visualization.py
Rscript tools/targets-network/render_targets_network.R
Rscript tools/targets-network/render_targets_network.R --definition-only \
  --script=_targets_retrieval_visualization.R --phases=tools/targets-network/retrieval_phases.yml \
  --output-dir=artifacts/targets-network/s10 --store=/mnt/hdd002/dhnyu/fusedata/targets/fuse-retrieval-s10
```

The existing evaluation unit tests only check contracts/rejections; no evaluation stage execution occurs. Benchmark entrypoints are `scripts/benchmark_retrieval_visualization.py` and `scripts/benchmark_retrieval_geometry.py`, using a new task-owned /tmp workdir. The Fourier benchmark consumes initialized context, optimized/legacy originals and the independently generated storage prototype; the exact pilot helper source and telemetry are saved in the local evidence log.

Real native-checkpoint smoke result:

```json

{
  "acceptance_id": "s10_smoke_acceptance_25a3a418af455de2a024866c",
  "accepted_models_validated": 28,
  "cleanup": "PASS",
  "elapsed_seconds": 103.67119955876842,
  "gallery": 6,
  "geometry_seconds": 2.9943619831465185,
  "inference_models": [
    "main",
    "cmp_DS"
  ],
  "inference_seconds_two_passes": 2.4643342727795243,
  "preparation_seconds": 4.1458745719864964,
  "queries": 2,
  "rerun_byte_equality": true,
  "rows": 16,
  "scope": "NONCANONICAL",
  "status": "PASS",
  "temporary_directory": "/tmp/fuse-s10-smoke-donsz8og",
  "viewer_browser": "PASS"
}

```

Smoke re-generated the common cache twice and embeddings twice, verified immutable publication, standard/non-local rankings, formal pipeline binding checks, HTML links, Chromium desktop/mobile mode switching and image loading. Temporary smoke artifacts were automatically removed.

Warnings/limitations: the four-worker legacy reader fixture emitted a resource_tracker warning about four semaphore objects at shutdown; all four were confirmed cleaned, no worker remained. An initial final-safety assertion expected the S10 store directory to be absent; read-only inspection showed pre-existing metadata from 10:34–10:46, no objects. The check was corrected to verify absence of formal publication and target objects; existing metadata was preserved. Neither observation is a scientific output mismatch. No other validation failure remains. Full 9,000-scene coverage and all-28 full inference intentionally remain unexecuted.

## 15. FILES CHANGED

- `python/retrieval_geometry.py`: common exact GPU feature writer, grouped identity and strict reader.
- `python/retrieval_inference.py`: batch-one enforcement, identical deterministic initialization, optional cache input; inactive bypass.
- `python/retrieval_pipeline.py`: common geometry orchestration/bindings/acceptance; prior reader proposal and per-call verification reuse.
- `python/retrieval_originals.py`: accepted-shard reader optimization (prior proposal revalidated).
- `python/retrieval_artifacts.py`, `python/retrieval_lineage.py`: schema/runtime binding.
- `config/retrieval_visualization.yml`, three retrieval schemas (artifact, visualization, new geometry): cache and batch contracts.
- `targets/s10_retrieval_visualization.R`, `scripts/retrieval_visualization.py`: explicit GPU target/CLI wiring.
- `scripts/smoke_retrieval_visualization.py`: cache rerun and integrated smoke.
- `scripts/benchmark_retrieval_geometry.py`, `scripts/benchmark_retrieval_visualization.py`: bounded telemetry/equivalence; latter retains batch=1 only.
- `tests/python/test_retrieval_geometry.py`, `tests/python/test_retrieval_originals.py`, `tests/testthat/test-retrieval-targets.R`.
- `blueprint/targets_implementation_blueprint.md`: common cache/reader contracts and batch constraint.
- This new report; refreshed S10 dependency HTML. Main graph HTML is unchanged after regeneration.

No checkpoint, data payload, targets store, raw log or temporary artifact is staged. The new report and S10 graph HTML are intentional small review artifacts despite generated-directory ignore rules.

## 16. SCIENTIFIC SAFETY

Training **NO**; S09 artifact/checkpoint mutation **NO**; S11 execution/repair **NO**; full S10 production **NO**. Source pins, campaign SHA and all 28 checkpoint payload SHA values passed post-benchmark checks. Frozen scene_encoder/scene_model/model_data/training_support/training_family_inputs and evaluation files have no diff. Architecture/relation math, precision, seeds, query/gallery, standard/nonlocal Top50, normalization and ranking code are unchanged.

Scope remains qualitative interpretation, never model selection. No B8/B9 special treatment, winner revision, hyperparameter retuning or S11 sample/protocol adjustment. Existing blocked S11 lineage lifecycle remains untouched. Full publication root and S10 target objects are absent; pre-existing store metadata is preserved. Task-owned temporary tensors/caches are removed after telemetry preservation, and smoke cleanup PASS. Data/log/store/checkpoint files are excluded from commit.

## 17. NEXT AUTHORIZED ACTION

Current authorization covers committing/pushing this PASS implementation, not production. Following a separate explicit full-execution approval, the operator command WOULD be:

```sh
Rscript scripts/run_retrieval_visualization.R --authorize-full-inference
```

**Not executed.** It would publish one common 9,000-scene geometry cache, 28 embedding/ranking branches, 84,000 Top50 rows, shared renders, 30 query pages and final acceptance under the new runtime-bound S10 generation. Expected planning duration is about 4.3 h likely with the range above. No S11 work is implied.
