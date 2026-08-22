# Authoritative Building Area and I19-I20 Completion

## 판정

- 최종 판정: **READY**
- 실행 시각: 2026-08-22 Asia/Seoul
- 범위: authoritative Building area reference, I14-I17 재승인, 320-scene no-op gate, I18, 40-worker I19 determinism campaign, I20 deterministic plan
- I21 actual training: 선언하거나 실행하지 않음

## Git 및 입력 감사

- Fuse 시작 commit: `d48b3d268668d5f6106d8aeb4025aeae81bc5505`
- Fuse 구현 commit: `11d35dd` (`Complete deterministic augmentation and training plan`)
- branch/push: `feature/research-scene-index` -> `origin/feature/research-scene-index`, 성공
- dissertation 시작/최종 commit: `0a251da679ef0e65967cca5e24e6b276988e28db`
- 두 저장소 모두 fetch 당시 local/remote divergence 0/0; dissertation worktree clean
- Fuse dirty worktree는 이전 topology/precision/I19 partial source였으며 runtime artifact, credential, checkpoint는 commit에 포함하지 않음
- 최신 Appendix B, model-training, training configuration, hyperparameter-study의 Building geometry-derived attributes와 Road lane 계약을 재확인함

## Root Cause 및 수정

I12 selected-host ordering과 I15 Building standardization은 I10 `building_observed.parquet`의 float64 `observed_area_m2`를 사용했다. 동일 absolute geometry를 Python/GEOS에서 다시 면적 계산하면 연산 순서 차이가 생겨 5개 POI host ordering과 한 Building의 float32 standardized value가 달라졌다.

- `geometry.safetensors`에 `building_observed_area_m2_reference` `[NB] float64`를 추가함.
- source: I10 vector observation `observed_area_m2`; I13 accepted dictionary와 I14 verified vector manifest를 통한 정식 dependency 전달.
- manifest provenance: source path, size, SHA-256, dataset identity, source column/dtype/unit/CRS, extraction algorithm.
- original, nonperturbed, identical candidate, fallback geometry는 reference area를 유지함.
- 실제로 변경된 accepted augmented geometry만 float64 geometry area로 상태 전환함.
- scientific reference는 encoder input에서 금지하며 model float32 namespace와 분리함.

## Identity 및 Payload

| Stage | Old | New |
|---|---|---|
| I12 | `pre_0a6fb2ee7cadd33aa0ae20dd` | unchanged |
| I13 | `psa_c2155cf081312a31edfdb191` | unchanged |
| I14 plan/dataset | `psp_70e4643f51eae59f804ec30a` / `psd_70e4643f51eae59f804ec30a` | `psp_72c5e4e5c3e4c84eb47aad85` / `psd_72c5e4e5c3e4c84eb47aad85` |
| I16 | `ptd_e147a97abd4669cf209dcbaa` | `ptd_cee61a525ca92f1b7951c40d` |
| I17 | `pdl_e2dbc8f4e95d295df61a7020` | `pdl_4037d275d729c82ea9b19d97` |
| no-op gate | prior failed lineage | `pgr_fb3209bda9fb0fa9a0e15bd1` |
| I18 | prior lineage | `pea_5784252434798d9dfa05d796` |
| I19 | none accepted | `paa_8d73a94e574dcdbc5c5106d2` |
| I20 | none | `ptp_8a862b669ae917bcddda9e28` |

- I14 estimated bytes: 410,952,111; authoritative area increment: 653,544 bytes (81,693 Buildings x 8).
- I15 actual payload: 429,871,747 bytes; tar bytes: 431,616,000.
- Counts unchanged: 320 scenes, split 256/32/32, 237,121 entities, 2,756,444 ordered relations, 794,540 coordinates, 59 empty-edge scenes, 51 serialization branches.
- I17 preserved float64 coordinate/center/reference-area dtype and ragged Building alignment across batch/unbatch, workers 0/4, shuffle, and corruption propagation tests.

## Cross-Runtime Area QC

- Shapely 2.1.2 / GEOS 3.14.1; 81,693 Buildings.
- exact geometry/reference area equality: 8.
- absolute difference median 9.328005e-11, p95 4.083162e-10, p99 8.142615e-10, max 9.236828e-09 m2.
- relative difference max 7.698838e-09.
- selected-host 영향 POI: 5; reference ordering으로 모두 expected host local 439, forbidden host 415 제외.
- source-reference transform -> stored float32: bit-exact 81,693, mismatch 0, max ULP 0.

## 320-Scene No-Op Gate

- missing/extra `CNT/WIT/INT/CON`: 모두 0/0.
- dangling/self/duplicate: 0/0/0.
- invalid geometry, coordinate/offset, reference-center, reference-area alignment mismatch: 모두 0.
- Building standardized-area bit mismatch: 0; failed scenes: 0.
- 네 prior INT scenes, selected-host scene/5 POIs, prior 2-ULP entity 및 extra-host regression set 모두 PASS.

## I18

- PASS; architecture identity와 float32 model semantics 유지.
- trainable parameters 1,996,534; parameter tensors 231.
- missing/invalid/zero-gradient tensors: 0/0/0.
- sparse, zero-node, dense, edge-heavy, topology-heavy/geometry-heavy representatives 검증.
- NVIDIA RTX A6000; elapsed 13.8846 s; peak allocated/reserved 20,310,951,936 / 20,724,056,064 bytes.
- scientific float64 tensors는 encoder computation에 사용되지 않음.

## I19 40-Worker Campaign

미완료였던 full-population 1-worker process는 accepted immutable artifact를 publish하지 않았음을 확인한 뒤 SIGTERM으로 종료했다. 기존 process/targets diagnostics는 보존했으며 acceptance evidence로 사용하지 않았다.

- full pass A: canonical scene order, 40 process workers.
- full pass B: deterministic shuffled order, 40 process workers.
- canonicalization: `(scene_id, view_id)`; worker당 OMP/MKL/OpenBLAS/NumExpr/Torch native threads 1.
- full canonical digest: `ff03b2ddb9b20c9dd43e532d3a7eb31638461fd32f7f5bd98972b84b92c0a556`.
- aggregate digest: `b528490af57d469b1a9346ddf0a9e56a50ddaa1b6a55293f94cc248d48880eb3`.
- exact equality: tensors, geometry WKB, relation masks, categories, rasters, retries/fallback, QC, content digests 모두 PASS.
- adversarial 13 scenes: 1 worker vs 40 workers exact parity PASS.
- retry/rejection/fallback: 233,709 / 65,038 / 582; geometry changed 147,322.
- Building geometry-updated/reference-preserved: 143,055 / 11,815; max area consistency error 0.
- lanes: eligible 14,383; selected 1,494; -1/+1 753/741; lower-bound clamps 409; invalid/below-min/missing-changed 모두 0.
- p50/p95 per-scene latency: 0.0441 / 26.8719 s; campaign wall 491.939 s.
- manifest RSS evidence 6,076,977,152 bytes; external process audit의 40-worker aggregate RSS는 약 25-26 GB로 별도 관측됨.
- CUDA correctness PASS; RTX A6000; peak allocated/reserved 7,680 / 2,097,152 bytes.
- 동일 40-worker direct rebuild를 재실행하여 manifest checksum 불변 및 immutable identical reuse를 확인함.

## I20

- PASS; plan `ptp_8a862b669ae917bcddda9e28`, run `ptr_dc7d6b862dadd63d9b7f62d0`, run count 1, seed 20260822.
- AdamW, lr 1e-4, weight decay 1e-4, 200 epochs, 10-epoch warmup 후 cosine, EMA 0.999, queue 8192, temperature 0.1, geographic exclusion 750 m.
- effective batch 32 scenes; exact 32-scene optimizer group를 I17 hard-budget microbatch로 분할하는 accumulation contract.
- validation/checkpoint 5 epochs; primary MRR; tie-break HIT@1 then earliest epoch.
- exact resume includes online/target model, optimizer, scheduler, EMA, queue, Python/NumPy/Torch CPU/CUDA RNG, sampler, accumulation state.
- estimated wall 18,050.03 s; checkpoint 37,384,032 bytes; 11-40 checkpoints; max storage 1,495,361,280 bytes.
- direct rebuild checksum identical reuse PASS; optimizer step 0; I21 미선언/미실행.

## 검증 및 Target 실행

- Python AST/compile coverage, R parse, YAML 29/JSON 15/schema parse: PASS.
- Python unittest 30 tests: PASS; full `Rscript tests/testthat.R`: PASS.
- selected-host/R parity, float32 ULP, topology, serialization, acceptance, DataLoader, encoder, augmentation, I20 fixtures: PASS.
- `tar_manifest()` 35 targets; `tar_network()` 328 vertices/615 edges; `tar_validate()`: PASS.
- initial scoped `tar_make(prototype_training_plan)`: 135 skipped, 0 built. Commit 직전 EOF normalization 후 current I20 contract를 재승인한 final scoped run은 contract/I20 2 completed, 133 skipped; I09-I19 skipped 확인.
- research-store `tar_outdated()`: empty.
- current I14-I20 `tar_meta()` warning/error: 0. 2026-08-21 upstream retry에서 남은 historical I01/I10 branch records 6건은 current lineage와 무관.
- direct rebuild, immutable identical reuse, same-ID/different-content hard failure fixtures: PASS.
- dependency HTML 갱신: `artifacts/targets-network/targets-network.html`.

## 실패 이력 및 남은 위험

- 첫 full test에서 intentional payload 증가와 5개 새 target을 반영하지 않은 정적 기대값 3건이 실패했으며 accepted manifests/manifest order로 수정 후 전체 PASS.
- direct graph 검사에서 내부 function/file vertices를 target 수로 잘못 가정한 진단 assertion 1건을 바로잡았고 pipeline에는 영향 없음.
- commit 직전 I20 파일의 EOF normalization이 contract hash를 바꿔 final `tar_outdated()`에서 I20만 검출되었다. I14-I19를 재실행하지 않고 정상 graph로 I20만 재승인하여 최종 identity를 갱신했다.
- I19 p95는 대형 scene과 40-process 동시 실행의 tail을 포함한다. I20 wall/storage 값은 실제 training 결과가 아닌 승인된 deterministic planning estimate이다.
- 40-worker 합산 RSS 외부 관측과 runner resource field의 계측 범위가 다르므로 production capacity planning에서는 약 26 GB 관측치를 사용해야 한다.

## 입력 프롬프트 요약

Authoritative source-computed Building area를 float64 scientific reference로 직렬화하고 no-op parity를 strict하게 복원한 뒤, full-population 1-worker run 없이 canonical/shuffled 40-worker I19 두 pass와 adversarial 1-vs-40 parity를 수행하고, PASS 조건에서만 I18/I19/I20을 publish하도록 요청받았다.
