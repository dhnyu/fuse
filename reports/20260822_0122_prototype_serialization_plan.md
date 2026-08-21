# Prototype Serialization Plan Implementation Report

## 판정과 범위

- 최종 판정: **READY**
- 실행 시각: 2026-08-22 01:02--01:22 KST
- Fuse 시작 commit: `a9e6ae07511e899ce63b2babf1907252607b9782`
- 구현 commit: `0a3c77f` (`origin/feature/research-scene-index` push PASS)
- dissertation source of truth: `73c7f5a65ae18960ac1990af035bca9076210f69`
- I13 spatial dataset: `psa_4e43932fc998fed94385addc`
- I14 plan / serialization dataset: `psp_c3f6659d47486417567d55c1` / `psd_c3f6659d47486417567d55c1`

I14 `prototype_serialization_plan`만 구현·실행했다. WebDataset, safetensors,
tensor 생성, DataLoader, I15 target, full production, model 및 training은 구현하거나
실행하지 않았다.

## 선행 조건과 I13 검증

branch와 local/remote HEAD는 요청 기준과 일치했고 시작 worktree는 clean이었다.
dissertation HEAD도 요청 기준과 일치했다. research store
`/mnt/hdd002/dhnyu/fusedata/targets/fuse-research`의 `tar_outdated()`는 빈 집합이었고
I09--I13은 재실행되지 않았다.

I13 manifest/QC status는 PASS였다. Manifest가 기록한 6 scientific output의 실제
size/SHA-256을 재계산한 결과 mismatch는 0이었다. I14는 I13 entity dictionary가
참조하는 vector/raster/relation branch manifest 각 15개의 I13-recorded checksum을
확인하고, 그 manifest가 기록한 file output checksum도 전수 확인했다.

I13 scene statistics에는 join 결과로 count 열과 `i.*` count 열이 함께 존재한다.
I14는 두 값이 모두 있을 때 exact equality를 요구하고, 0-node scene에서만
authoritative `i.*=0`으로 앞쪽 NULL을 보완한다. 불일치 또는 NULL/negative resource는
hard failure다.

## Cost Estimator

Estimator는 compression ratio를 가정하지 않고 uncompressed bytes를 hard budget으로
사용한다. Machine-readable 계약은 `config/serialization_plan.yml`에 기록했다.

- node type `uint8`, categorical index `int32`, numerical `float32`, missing indicator `uint8`
- object-raster 26 values/node, `float32`
- entity/component/ring offsets `int64`, geometry type `uint8`, XY coordinate `float32`
- edge index `[2,E]` `int64`, relation mask `uint8`
- scene raster: LC class/support/mask와 DEM mean/support/mask의 실제 shape/dtype 기준
- scene fixed metadata overhead: 16 KiB

Accepted GeoParquet의 observed WKB를 직접 순회해 Point, LineString, Polygon exterior와
interior ring, MultiPoint, MultiLineString, MultiPolygon의 coordinate/component/ring/hole을
계산했다. Stored I10 counters와 exact match를 강제했다. Unsupported geometry는 0이었다.

## Resource 분포와 Cap

분포 순서는 min / median / p90 / p95 / p99 / max다.

| Resource | Distribution | Cap |
|---|---:|---:|
| nodes | 0 / 74 / 2,366.5 / 3,044.2 / 4,141.97 / 5,056 | 13,000 |
| ordered edges | 0 / 1,054 / 27,482.6 / 33,474.4 / 42,670.2 / 58,366 | 140,000 |
| coordinates | 0 / 321 / 8,695.5 / 10,270.35 / 12,389.38 / 13,331 | 50,000 |
| uncompressed bytes | 949,009 / 980,932 / 1,858,637.2 / 2,071,133.05 / 2,380,205.16 / 2,511,634 | 8,388,608 |

Cap은 실제 p95의 4배를 nodes 1,000, edges 10,000, coordinates 10,000,
bytes 1 MiB 단위로 보수적으로 올림했다. 전체 coordinate tuple은 794,540,
observed WKB는 14,586,326 bytes, estimated uncompressed serialization은
393,493,986 bytes다. System feasibility limit 초과 scene과 oversize singleton은 0이다.

## Sharding 결과

Deterministic decreasing maximum-normalized-cost 순서와 stable scene ID tie-break를
사용했다. Eligible shard는 current maximum normalized load, total normalized load,
stable scene key 순으로 선택했다. Scene은 atomic이며 split을 섞지 않았다.

| Split | Scenes | Shards | Nodes | Ordered edges | Coordinates | Estimated bytes |
|---|---:|---:|---:|---:|---:|---:|
| training | 256 | 40 | 187,513 | 2,189,832 | 610,078 | 313,986,846 |
| validation | 32 | 6 | 26,976 | 314,522 | 102,795 | 40,707,162 |
| evaluation | 32 | 5 | 22,632 | 252,090 | 81,667 | 38,799,978 |
| total | 320 | 51 | 237,121 | 2,756,444 | 794,540 | 393,493,986 |

Empty-edge scenes는 training 46, validation 8, evaluation 5의 총 59개이며 11개
branch에 정상 배정됐다. Byte utilization의 branch min/median/max는
0.1131/0.9365/1.0000, coefficient of variation은 0.1513이다. Node/edge/coordinate
utilization CV는 1.0494/1.0118/1.0204이며 zero-node scene과 raster-dominated fixed
cost 때문에 byte balance보다 크게 나타난다. Non-singleton cap violation은 0이다.

## Output과 결정성

Immutable atomic directory에는 plan manifest JSON, 320-row scene-to-shard Parquet,
51 branch spec JSON, planning QC JSON, 320-row resource diagnostics Parquet와 structured
log를 publish했다. Dynamic branch용 R list는 spec JSON과 동일한 51개 small list다.

- duplicate/missing scene: 0/0
- cross-split shard: 0
- duplicate branch/spec ID: 0
- spec JSON / plan Parquet / R list scene order: exact match
- I13 required artifact path/checksum 전달 누락: 0
- manifest-recorded output: 55, checksum mismatch 0
- reversed/shuffled 320-row input direct rebuild: same plan ID, branch IDs, assignment and bytes
- existing immutable output identical reuse: PASS
- same ID/different content fixture: hard failure PASS
- final immutable directory aggregate SHA-256: `6ad4d0cc2ec6fb30206d5b7ed7670a7412437914ac213e0f79894c640fb687bf`

## Tests와 Targets

- R/config/schema parse: PASS
- I14 fixture: PASS (empty-edge, coordinate/edge-heavy, multipart/hole, oversize,
  cap boundary, duplicate/missing/cross-split, checksum mismatch, shuffle, tie-break,
  feasibility overflow, immutable collision)
- 전체 `Rscript tests/testthat.R`: PASS
- `tar_manifest()`: 22 targets; I14 static `format=rds`, `iteration=list`, `controller_05`
- `tar_network()`: I14 incoming edge는 I13과 scoped contract 두 개만 존재
- `tar_validate()`: PASS
- actual selection: serialization contract + I14 2 completed, 70 skipped
- I14 target wall: 35.7 s
- global QC/checksum/determinism: PASS
- final research `tar_outdated()`: empty
- dependency HTML: regenerated; I14/scoped edge present, I15/C01/maintenance/model/training edge absent

## 실패 이력과 남은 위험

초기 `tar_outdated()`에서 `_targets.yaml`의 legacy default store를 사용해 전체 research
graph가 outdated처럼 보였으나, repository 실행 convention의 research store로 즉시
재확인해 빈 집합임을 확인했다. 전체 test 첫 실행에서는 manifest expected-order test에
새 contract target 위치가 반영되지 않아 실패했고 수정 후 전체 suite를 재실행했다.
독립 QC 요약에서 `data.table` 단일 logical-column filter 문법 오류가 한 번 발생했으며
명시 비교로 재실행했다. YAML EOF whitespace 검사와 manifest log checksum 누락도 commit
전에 수정하고 전체 validation과 I14를 다시 실행했다. Scientific artifact failure는 없다.

Estimator는 I15 actual serialization 측정치가 아니라 보수적 uncompressed planning
estimate다. Compression ratio, tar/container overhead, DataLoader RSS와 throughput은 아직
검증하지 않았다. 이것들은 다음 단계 I15 serialization branch 및 이후 acceptance에서
estimated/actual 차이와 함께 검증해야 한다. 이번 작업에서는 I15를 구현하지 않았다.

## 입력 프롬프트 요약

사용자는 승인된 I13 320 prototype scenes만 대상으로 deterministic serialization plan을
구현·실행·검증하고, actual node/edge/coordinate/raster/byte cost 기반 split-homogeneous
sharding, immutable outputs, global QC, shuffle/reuse/checksum 검증을 통과한 경우에만
commit/push하며 I15 이후는 구현하지 말라고 요청했다.
