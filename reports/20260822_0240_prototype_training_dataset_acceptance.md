# Prototype Training Dataset Acceptance Report

## 판정과 범위

- 최종 판정: **READY**
- 실행 시각: 2026-08-22 02:25--02:40 KST
- 요청 시작 commit: `c951282`; 실제 시작 HEAD: `ab57701` (I15 최종 보고서 commit 포함)
- I16 구현 commit: `d174e96` (`origin/feature/research-scene-index` push PASS)
- dissertation source of truth: `73c7f5a65ae18960ac1990af035bca9076210f69`
- I13 spatial dataset: `psa_4e43932fc998fed94385addc`
- I14 serialization plan: `psp_c3f6659d47486417567d55c1`
- I15 serialization dataset: `psd_c3f6659d47486417567d55c1`
- I16 accepted training dataset: `ptd_140215eef2c1fa6da8304c6e`

I16 static aggregate gate와 필요한 scoped contract/schema/validator/test만 구현했다.
I15 tar, safetensors 및 sidecar는 read-only로 검사했으며 새 tensor, shard, DataLoader,
model, augmentation, training 또는 full-production artifact는 만들지 않았다.

## Dependency와 Output

`prototype_training_dataset_acceptance`는 `controller_05`, 내부 1 worker x 1 thread,
GPU 0, static `format="file"` target이다. Direct target dependency는 다음 네 개뿐이다.

- `prototype_spatial_acceptance`
- `prototype_serialization_plan`
- `prototype_serialization_shard`의 51개 branch 전체
- `training_dataset_acceptance_contract_files`

I10/I11/I12, I17, model, augmentation, training, full production 및 maintenance edge는
추가하지 않았다. Immutable atomic accepted directory에는 manifest, 51-row shard catalog,
320-row global scene index, split-aware dataset index, aggregate QC, 55-row actual-byte
diagnostics와 structured JSONL log를 publish했다.

## Shard, Scene, Resource QC

| Split | Shards | Scenes | Entities | Ordered edges | Coordinates | Empty-edge scenes |
|---|---:|---:|---:|---:|---:|---:|
| training | 40 | 256 | 187,513 | 2,189,832 | 610,078 | 46 |
| validation | 6 | 32 | 26,976 | 314,522 | 102,795 | 8 |
| evaluation | 5 | 32 | 22,632 | 252,090 | 81,667 | 5 |
| total | 51 | 320 | 237,121 | 2,756,444 | 794,540 | 59 |

I14 spec와 I15 branch set/order는 exact match였다. Missing/extra/duplicate branch와
scene, cross-split shard 및 split leakage는 모두 0이다. 59개 empty-edge scene은
`edge_index [2,0]`, `relation_mask [0]`으로 확인됐고 node/geometry/raster는 정상이다.

## Global Index와 Random Access

Global index는 accepted dataset/shard/branch ID, scene/split, deterministic global 및
split-local order, source tar/`.idx` path와 SHA-256, sample key/member prefix, sample과
다섯 member의 offset/payload size, resource count, empty-edge flag와 I13/I14/I15 ID를
기록한다. Dataset index는 split별 global range와 ordered branch/shard ID를 제공한다.
따라서 I17은 I15 directory나 branch manifest를 다시 탐색하지 않고 이 두 index로
sequential 및 random access를 구성할 수 있다.

320개 scene 모두에 대해 `.idx` offset에서 512-byte USTAR header를 직접 읽고 member
name/size를 확인한 뒤 payload checksum과 safetensors를 검증했다. 별도 standalone
검사에서도 global order의 첫/중앙/마지막 scene direct seek/read가 PASS했다.

## Checksum, Member와 Tensor QC

51개 branch의 tar, `.idx`, scene-index Parquet, QC, log 및 manifest 존재를 확인했다.
Manifest-recorded size/SHA-256 mismatch, tar member duplicate/missing/unexpected,
`.idx` offset/size mismatch와 direct-seek checksum mismatch는 모두 0이다.

320개 scene의 다섯 member group을 전수 열어 I15 tensor key/dtype/shape, finite float,
geometry/entity/component/part/ring offset, categorical index/MISSING 범위, raw MASK 금지,
relation endpoint/mask bit, empty-edge shape와 LC/DEM raster shape/mask를 검사했다.
Tensor/category/offset/nonfinite/raster/dangling-edge/unknown-mask 오류는 모두 0이다.
I13 vocabulary, normalization, missing mapping, alias, dictionary, scene statistics와
manifest의 path/size/SHA-256 전달도 완전했다.

## Actual Byte Diagnostics

I15 actual bytes를 authoritative value로 사용했고 요청 기준과 재계산값이 정확히
일치했다.

| Scope | Estimate bytes | Payload bytes | Tar bytes | Estimate error | Tar overhead |
|---|---:|---:|---:|---:|---:|
| training | 313,986,846 | 328,133,202 | 329,349,120 | +4.5054% | +0.3706% |
| validation | 40,707,162 | 42,913,525 | 43,079,680 | +5.4201% | +0.3872% |
| evaluation | 38,799,978 | 40,522,403 | 40,683,520 | +4.4392% | +0.3976% |
| total | 393,493,986 | 411,569,130 | 413,112,320 | +4.5935% | +0.3750% |

Branch estimate error min/median/max는 -1.4083% / +1.7966% / +13.5312%이고 tar
overhead min/median/max는 0.1736% / 0.3879% / 0.6878%다. Branch payload
min/median/max는 935,646 / 8,111,079 / 9,350,178 bytes다.

## 결정성 및 Immutable Reuse

Accepted ID는 I13 accepted identity/checksum, I14 51 spec checksum, I15 51 branch
manifest checksum과 tensor identity, I16 config/schema/implementation, archive/order
contract의 canonical SHA-256으로 생성했다. Runtime, worker 수, wall time 및 RSS는
scientific identity에서 제외했다.

정방향과 역순으로 전달한 spec/branch/I13 input을 서로 다른 directory에 direct
rebuild한 결과 accepted dataset ID, shard catalog, global/split order와 7개 output
checksum이 모두 byte-identical했다. 기존 동일 output directory 재실행은 identical
reuse PASS였고 same ID/different content fixture는 hard failure PASS였다. Accepted
manifest SHA-256은 `2614028e4f5e5f111e4f8d074576adf49acc60c64a6e2f4f33580c1954492945`다.

## Tests와 Targets

- R/Python/YAML/JSON syntax 및 schema parse: PASS
- I16 Python fixtures: 5 PASS
- 전체 `Rscript tests/testthat.R`: PASS
- `tar_manifest()`: 26 targets; I16 static file target 확인
- `tar_network()`: 565 edges; I16 direct parent 네 개 exact match
- `tar_validate()`: PASS
- actual selection: I16 contract + I16 aggregate 2 completed, 124 skipped
- I16 aggregate target wall: 1.7 s; target warning/error 0/0
- 51-shard/320-scene global QC와 standalone random seek: PASS
- shuffled direct rebuild와 immutable reuse: PASS
- dependency HTML: 현재 26-target graph로 갱신 PASS
- 최종 research `tar_outdated()`: empty

## 실패 이력과 남은 위험

전체 test 첫 실행에서 기존 manifest expected-order fixture의 raster/relation 두 target
순서가 새 topological manifest와 반대로 기록되어 한 건 실패했다. 실제 graph를 기준으로
fixture를 수정한 뒤 전체 suite를 재실행해 PASS했다. EOF whitespace 정리로 scoped
contract target만 한 번 재실행했고 content-addressed accepted ID도 최종 contract hash로
갱신한 뒤 shuffle/reuse를 다시 검증했다. I09--I15는 모든 실행에서 skipped였다.
Scientific artifact, checksum, tensor 또는 random-access failure는 없었다.

검사는 warm page cache에서 수행되어 cold-storage random I/O 성능을 의미하지 않는다.
실제 DataLoader worker 수, batching, throughput과 RSS는 다음 I17 smoke의 범위다. 다음
단계는 I17 `prototype_dataloader_smoke`이며 이번 작업에서는 선언하거나 구현하지 않았다.

## 입력 프롬프트 요약

사용자는 I15의 51개 immutable serialization shard와 320개 scene을 전수검사해 하나의
공식 prototype training dataset으로 승인하고, split/resource/byte 총계, tar/`.idx`
random access, tensor/checksum, I13 identity 전달, shuffled determinism과 immutable reuse가
모두 통과한 경우에만 commit/push하며 I17 이후는 구현하지 말라고 요청했다.
