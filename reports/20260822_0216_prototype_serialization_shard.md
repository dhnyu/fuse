# Prototype Serialization Shard Implementation Report

## 판정과 범위

- 최종 판정: **PASS**
- 실행 시각: 2026-08-22 01:30--02:16 KST
- 요청 시작 commit: `0a3c77f`; 실제 시작 HEAD: `5ffaa0b` (I14 보고서만 추가된 commit)
- I15 구현 commit: `c951282` (`origin/feature/research-scene-index` push PASS)
- dissertation source of truth: `73c7f5a65ae18960ac1990af035bca9076210f69`
- I13 spatial dataset: `psa_4e43932fc998fed94385addc`
- I14 plan: `psp_c3f6659d47486417567d55c1`
- I15 serialization dataset: `psd_c3f6659d47486417567d55c1`

I15 `prototype_serialization_shard`와 필요한 scoped contract, Python serializer, R
wrapper, fixture 및 global validation script만 구현했다. 51개 prototype branch 전체를
실행했지만 I16 aggregate target, DataLoader, model, augmentation, training 및 full
production은 구현하지 않았다.

## 선행 감사와 Dependency

시작 branch와 remote는 정렬되어 있었고 dissertation HEAD/working tree도 요청 기준과
일치했다. Fuse HEAD가 요청의 `0a3c77f`가 아니라 `5ffaa0b`였던 이유는 최신 I14
보고서 commit 한 개뿐이며 code/scientific artifact 차이는 없었다. I13/I14
manifest, QC, ID와 checksum을 재확인했다.

Research store의 최초 `tar_outdated()`는 빈 집합이었다. I15 선언 뒤 실행 직전에는
새 `serialization_shard_contract_files`와 `prototype_serialization_shard`만 outdated였고
I09--I14는 없었다. 최종 `tar_outdated()`도 빈 집합이다. Target direct edge는 정확히
다음 두 개다.

- `prototype_serialization_plan -> prototype_serialization_shard`
- `serialization_shard_contract_files -> prototype_serialization_shard`

I10/I11/I12 직접 edge, I16/C01/maintenance/model/augmentation/training edge는 추가하지
않았다. I15는 `pattern=map(prototype_serialization_plan)`, `format="file"`,
`controller_10`, branch 내부 1 worker x 1 thread, GPU 0이다.

## Serialization Schema

한 scene은 WebDataset tar의 논리 sample이며 I14 spec scene order를 유지한다. Member
순서는 `meta.json`, `entities.safetensors`, `geometry.safetensors`,
`edges.safetensors`, `rasters.safetensors`로 고정했다. Tar는 USTAR, mtime/uid/gid 0,
빈 uname/gname, mode 0644다. JSON은 sorted-key compact UTF-8+LF, index는
`scenes-{branch}.idx`, scene sidecar는 deterministic Parquet다.

| Tensor group | 주요 key, dtype와 shape | 전체 count |
|---|---|---:|
| entities | local ID `int64[N]`, type `uint8[N]`, relative XY `float32[N,2]` | N=237,121 |
| entity context | object raster `float32[N,26]`, DEM missing `uint8[N,2]` | 6,165,146 values |
| Building | row `int64[NB]`, category `int32[NB,2]`, numerical `float32[NB,2]`, missing `uint8[NB,2]` | NB=81,693 |
| Road | row `int64[NR]`, category `int32[NR,2]`, numerical `float32[NR,1]`, missing `uint8[NR,1]` | NR=7,898 |
| POI | row `int64[NP]`, category `int32[NP,6]` | NP=147,530 |
| geometry | intrinsic XY `float32[C,2]`, type/availability `uint8[N]`, entity/component/part/ring topology `int64` offsets | C=794,540 |
| edges | `edge_index int64[2,E]`, `relation_mask uint8[E]` | E=2,756,444 |
| LC raster/scene | fraction `float32[22,100,100]`, support `float32[100,100]`, mask `uint8[100,100]` | 320 scenes |
| DEM raster/scene | standardized mean `float32[17,17]`, support `float32[17,17]`, mask `uint8[17,17]` | 320 scenes |

Geometry XY는 observed entity center 기준 `(xy - center) / 500 m`다. Component/part
offset과 polygon ring의 component index, absolute coordinate start/end, hole indicator를
함께 저장해 multipart와 interior ring을 보존한다. POI observed point coordinate도
round-trip을 위해 저장하되 geometry modality availability는 0이다. Strings, source
entity IDs와 provenance는 safetensors가 아니라 canonical meta/index/manifest에 둔다.

## Categorical, Numerical, Raster

Entity 순서는 I13 `(scene_id, local_entity_id)`와 exact match하며 relation endpoint는
명시적인 local-ID-to-row map으로 변환한다. Relation은 source/destination/mask canonical
order이고 multi-relation bit mask를 보존한다.

- I13 vocabulary index를 그대로 사용한다. `MISSING`만 결측에 사용하고 raw `MASK`,
  invalid/OOV/UNKNOWN/UNK는 hard failure다.
- Building `블록구조`는 dictionary의 official A11 key `12`, index 2만 허용한다.
- Building observed area/gross floor area는 `log1p`, Road lanes는 identity 후 I13
  training population mean/applied SD로 표준화한다.
- Object DEM mean/SD와 valid scene DEM pixel은 I13 training statistics로 표준화한다.
  Missing numerical value와 invalid DEM pixel은 standardized 0, indicator/mask 1 계약을
  사용한다.
- 22 LC composition, LC/DEM support ratio는 표준화하지 않는다. LC/DEM nodata와
  support mask는 source shape/value와 exact 대응한다.
- 59 empty-edge scene은 `edge_index [2,0]`, `relation_mask [0]`이며 node/geometry/raster와
  meta/index의 `empty_edge=true`는 정상 보존된다.

## Pilot과 Concurrency

고정 selector로 zero-edge node-only, estimated-byte median, maximum-node dense,
maximum-edge-utilization branch를 선택했다.

| Branch | 역할 | Serializer wall s | External wall s | Peak RSS MiB | Estimate / payload / tar bytes |
|---|---|---:|---:|---:|---:|
| `psb_b7541dd51ce393df23082f3b` | empty/sparse | 0.605 | 1.41 | 347.2 | 7,593,564 / 7,487,827 / 7,526,400 |
| `psb_53d261be841302f89239d782` | median | 0.746 | 1.54 | 428.8 | 7,855,721 / 7,806,190 / 7,843,840 |
| `psb_201b1fd0ef95683c55898e36` | dense | 16.617 | 17.51 | 585.3 | 8,320,810 / 9,350,178 / 9,369,600 |
| `psb_41127d71c97f2ddbca25dfd4` | edge-heavy | 2.210 | 3.10 | 588.3 | 8,231,883 / 9,271,589 / 9,287,680 |

Pilot filesystem input counter는 warm page cache로 모두 0이었고 output counter는
14,808--18,400 512-byte blocks였다. 기존 I11 accepted raster source의 5/10-worker
pilot에서 10 workers가 더 빠르고 contention 증가가 없었으며, 이번 peak branch RSS
약 0.59 GiB와 실행 시 available RAM 743 GiB를 함께 근거로 concurrency 10을 유지했다.
Worker 수는 scientific identity에 넣지 않았다.

## 51 Branch와 Global QC

최종 target 실행은 52 completed(I15 contract 1 + dynamic branches 51), 72 skipped로
upstream 재실행이 없었다. Pipeline wall은 24.7초, branch compute 합은 143.917초,
branch min/median/max는 1.237/2.967/5.783초다. `tar_meta()` error/warning은 0/0이다.
Production RSS/I/O는 deterministic artifact에 기록하지 않았고 위 pilot external
measurement만 사용했다.

| Split | Scenes | Shards | Empty-edge scenes | Empty-edge containing shards |
|---|---:|---:|---:|---:|
| training | 256 | 40 | 46 | 8 |
| validation | 32 | 6 | 8 | 2 |
| evaluation | 32 | 5 | 5 | 1 |
| total | 320 | 51 | 59 | 11 |

Global validator는 51 tar와 모든 sidecar checksum을 확인하고 320 scene의 모든
safetensors를 다시 열어 key/dtype/shape, finite float, offsets, category/missing range,
edge mask, empty-edge shape와 raster shape를 검사했다.

- scenes/splits: 320, 256/32/32
- entities/edges/coordinates: 237,121 / 2,756,444 / 794,540
- duplicate/missing scenes: 0/0
- tensor schema/dtype mismatch: 0
- dangling edge/category/normalization/raster error: 0/0/0/0
- checksum mismatch/I13 artifact forwarding error: 0/0
- branch QC: 51/51 PASS; round-trip scene count 320

## Bytes와 Load

I14 estimate 합은 393,493,986 bytes, actual safetensors+meta payload는 411,569,130
bytes로 actual이 4.5935% 컸다. Branch estimate error min/median/p95/max는
-1.408% / +1.797% / +12.630% / +13.531%다. USTAR archive 합은 413,112,320
bytes이고 payload 대비 1.00375다. Compression은 사용하지 않았으므로 이는 압축률이
아니라 tar header/padding overhead다.

Branch estimated-byte CV는 0.1498, actual payload CV는 0.1717이고 actual max/mean은
1.1586이다. Nodes/edges/coordinates CV는 1.0391/1.0018/1.0103으로 raster-dominated
zero-node shard 영향이 크다. Actual 최대 branch payload 9,350,178 bytes는 I14의
1 GiB system feasibility limit보다 충분히 작다.

## 결정성, Checksum, Immutable Reuse

Serializer는 dictionary/entity rows, relation rows와 safetensors key를 canonical order로
정렬하므로 input row/file order와 worker 수에 독립적이다. Fixture에서 shuffled tensor
key와 edge rows가 동일 bytes/order임을 확인했다. Dense representative branch를 별도
directory에 direct rebuild한 결과 tar, `.idx`, Parquet, manifest, QC, log 6개가
production과 모두 byte-identical했다. 같은 directory 재실행은
`immutable_reuse=true`였다. Same branch ID/different content는 hard failure fixture가
PASS했다.

Scientific identity에는 I13 ID와 accepted artifact checksums, I14 spec/scientific
identity, tensor contract, manifest schema, serializer implementation, pinned requirements,
algorithm/tar/safetensors assumptions을 포함한다. Wall/RSS/I/O와 controller concurrency는
제외했다.

## Tests와 Dependency 결과

- R/Python syntax, YAML/JSON schema parse: PASS
- Python fixtures: 8 PASS (0-node/node-only, `[2,0]`, multipart/hole, missing/alias/invalid,
  standardized zero, multi-mask/dangling, shuffle, deterministic/corrupted tensor/tar,
  checksum mismatch, immutable reuse/conflict)
- 전체 `Rscript tests/testthat.R`: PASS
- `tar_manifest()`: 24 targets; I15 dynamic pattern/file format 확인
- `tar_network()`: I14 plan + scoped contract target edge만 존재
- `tar_validate()`: PASS
- dependency HTML: regenerated and current manifest/edge와 일치
- 최종 `tar_outdated()`: empty

## 실패 이력과 남은 위험

개발 중 YAML bare `N` shape가 boolean으로 parse된 문제, vector entity label과 I13 code
차이, POI vocabulary attribute 이름, non-contiguous global ring offset 설계, runtime
metadata에 의한 nondeterministic sidecar, `.idx.json` filename을 발견해 각각 quoted
shape, accepted code mapping, I13 attribute, absolute ring interval topology, deterministic
log/relative manifest path, blueprint `.idx`로 수정했다. Manifest order test의 expected
target 위치도 실제 topological order에 맞췄다. 완료 전 제가 생성한 I15 branch만
invalidate/정리 후 재생성했으며 기존 I13/I14 immutable artifact는 수정하거나
재실행하지 않았다. 최종 scientific artifact failure는 없다.

I14 estimator는 aggregate로 4.59%, 일부 dense branch에서 최대 13.53% 낮게 추정했다.
Prototype feasibility에는 영향이 없지만 I16 acceptance에서 actual byte diagnostics를
authoritative하게 전달해야 한다. Cold-cache I/O와 DataLoader throughput은 아직
측정하지 않았다. 다음 단계는 I16 `prototype_training_dataset_acceptance`이며 이번
작업에서는 구현하지 않았다.

## 입력 프롬프트 요약

사용자는 승인된 I14 51 spec으로 320 prototype scene을 deterministic
WebDataset+safetensors cache로 직렬화하고, 모든 scene source round-trip, tensor 및
raster contract, pilot/concurrency, global completeness, checksum/determinism/immutable
reuse와 targets dependency를 검증한 뒤에만 commit/push하며 I16 이후를 구현하지
말라고 요청했다.
