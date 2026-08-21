# Prototype DataLoader Smoke Report

## 판정과 범위

- 최종 판정: **READY**
- 실행 시각: 2026-08-22 02:43--03:14 KST
- 요청 시작 commit: `d174e96`; 실제 시작 HEAD: `b8f071c` (I16 최종 ID/보고서 보정 포함)
- I17 구현 commit: `3fdc494dcc3966da9a300a621678b96915ed4cfe`
- branch/push: `feature/research-scene-index`, `origin/feature/research-scene-index` push PASS
- dissertation source of truth: `73c7f5a65ae18960ac1990af035bca9076210f69`
- accepted training dataset: `ptd_140215eef2c1fa6da8304c6e`
- final targets smoke execution ID: `pdl_a402b7ac668ddabfb6ba50f0`

I16 accepted manifest, dataset index와 global scene index만 dataset entry point로 사용했다.
I15 branch directory나 manifest를 탐색하지 않았고 I15/I16 artifact는 read-only로
열었다. I18, model, augmentation, training 및 full production은 구현하지 않았다.

## Dataset, DataLoader와 Collate 계약

`AcceptedPrototypeDataset`은 split sequential access, scene-ID random access와 I16 global/
split-local order를 제공한다. Global index의 `.idx` offset에서 USTAR member를 direct seek해
다섯 member를 checksum 검증한 뒤 safetensors와 canonical meta JSON을 복원한다. Missing,
corrupted 또는 unexpected member는 즉시 실패한다.

`DeterministicBudgetBatchSampler`는 PCG64(`seed=20260822`, epoch 포함) 순서를 사용하며
scene을 분할하지 않는 five-resource greedy hard budget을 적용한다. `ragged_collate`는
entity/edge/coordinate/part/ring pointer, type별 global row index, rebased edge index,
scene-local inverse mapping과 raster stack을 반환한다. Empty node/edge scene과 `[2,0]` /
`[0]` edge tensor도 보존한다.

I17은 static `format="file"`, `controller_05`, 내부 1 worker x 1 thread, CPU-only target이다.
Direct target parent는 `prototype_training_dataset_acceptance`와
`dataloader_smoke_contract_files` 두 개뿐이다.

## Coordinate Meter-unit 검증

I15 `relative_position_m`은 그대로 meter로 반환하고, I15 intrinsic geometry
`coordinates_xy`는 checksum-verified tensor contract의 scale 500을 정확히 곱해 entity
center 기준 meter인 `coordinates_xy_m`으로 반환한다. I13 dictionary가 전달한 모든 I10
metric geometry를 320 scene, 237,121 entity, 794,540 coordinate에 대해 독립 재구성했다.

- relative-position 최대 오차: `0 m`
- intrinsic-geometry 최대 오차: `1.52587890625e-5 m`
- 허용오차: `0.001 m`
- 중복 scaling 및 scale metadata/checksum mismatch: 0

## Budget와 Batch 통계

Training 실제 분포의 p95는 node 3,088.5, edge 34,237, coordinate 9,946.5,
payload 2,354,717 bytes였다. 약 4 x p95를 반올림하고 모든 단일 scene이 각 cap 이하임을
확인해 다음 hard budget을 사용했다.

| Resource | Budget |
|---|---:|
| scenes | 8 |
| nodes | 14,000 |
| ordered edges | 140,000 |
| coordinates | 50,000 |
| actual payload bytes | 10,485,760 |

Training 256 scene은 37 batch로 구성됐고 batch scene 수 min/median/max는 4/8/8이다.
Oversize singleton은 0이며 모든 batch가 다섯 cap을 만족했다. Effective batch 32를 위한
optimizer accumulation은 training 단계 범위이므로 적용하지 않았다.

## Correctness와 대표 Scene

| 항목 | 결과 |
|---|---:|
| scenes / split | 320 / 256, 32, 32 |
| entities / ordered edges / coordinates | 237,121 / 2,756,444 / 794,540 |
| empty-edge scenes | 59 |
| missing / duplicate / split leakage | 0 / 0 / 0 |
| sequential/random equality | PASS |
| worker 0/4 logical equality | PASS |
| batch offset 및 unbatch round-trip | PASS |
| fixed-seed repeated shuffle | PASS |
| retained FD leak | 0 |

Sparse/empty 대표는 `scn_015f7a3b152d404b44344aa2`(0 node, 0 edge), maximum-node는
`scn_f3846db0c003205f137b3d97`(5,056 node), maximum-edge는
`scn_51560f37ff4f293e156f83a7`(58,366 edge), geometry-heavy는
`scn_457a5e422e1a26667a3c086b`(13,331 coordinate)였다. 모든 scene에서 I15 key/dtype/
shape, finite float, local entity/type order, category/MISSING 범위, raw MASK 금지, binary
missing/raster mask, geometry offsets, edge endpoint/relation bits와 raster shape를 검사했다.

Fixture는 empty node/edge, multipart/hole offset, multi-scene edge rebasing, coordinate scale,
oversize singleton/cap boundary, fixed-seed 및 worker-count determinism, corrupted `.idx`/tar/
member/safetensors, wrong split, FD 반복 검사와 worker exception propagation을 포함하며
7/7 PASS다. Production artifact는 corruption 검사에서 수정하지 않았다.

## Worker 0/4와 성능

측정은 page cache를 제거하지 않은 warm-cache 단일 반복이다. GPU는 subprocess에서
비가시화했다. CPU-only 환경에서는 pinned memory가 실제 적용되지 않으므로 요청값과
`pin_memory_effective=false`를 함께 기록했다.

| workers | pin 요청/적용 | persistent | first batch s | scene/s | p50/p95 batch s | main/worker peak RSS MiB | peak/retained FD |
|---:|---|---|---:|---:|---:|---:|---:|
| 0 | false/false | false | 0.021 | 324.26 | 0.0152 / 0.0176 | 663.4 / 0.0 | 15 / 0 |
| 4 | false/false | false | 5.168 | 44.86 | 0.0060 / 0.0120 | 660.9 / 600.6 | 125 / 2 |
| 0 | true/false | false | 0.021 | 321.93 | 0.0161 / 0.0190 | 690.9 / 0.0 | 17 / 0 |
| 4 | true/false | false | 5.059 | 45.90 | 0.0057 / 0.0152 | 692.0 / 599.3 | 170 / 0 |
| 4 | false/false | true | 5.083 | 46.01 | 0.0058 / 0.0195 | 692.0 / 601.0 | 215 / 0 |
| 4 | true/false | true | 5.101 | 45.66 | 0.0060 / 0.0207 | 692.0 / 600.7 | 170 / 0 |

Worker 0 baseline은 46.87 batch/s, 237,510 entity/s, 2,773,709 edge/s,
772,744 coordinate/s였다. Warm cache 때문에 measured read bytes는 0이었다. Prototype에서는
process startup과 IPC 비용이 커 worker 0, pin false, persistent false를 권장한다. Runtime
선택은 accepted scientific dataset identity에 포함하지 않는다.

## 결정성, Tests와 Targets

Worker 0/4의 scene order, batch boundary, tensor, offset, totals와 digest는 동일했다.
Target run과 최종 direct repeat의 logical result checksum은 모두
`3a84ca2c1851c1ef0f36ceecf8c3c422936ddacd46fde585822894dc58869ca3`였다. 성능과
환경 측정값을 포함하는 smoke execution ID는 반복마다 달라질 수 있으며 accepted dataset
scientific identity에는 영향을 주지 않는다.

- Python/R/YAML/JSON syntax 및 schema parse: PASS
- I17 Python fixtures: 7 PASS
- 전체 `Rscript tests/testthat.R`: PASS
- `tar_manifest()`: 28 targets; I17 static file target 확인
- `tar_network()`: I17 direct parent 두 개 exact match, I18/training edge 0
- `tar_validate()`: PASS
- execution selection: I17 contract + I17 smoke만 completed, upstream 126 skipped
- final target wall 47.3 s, warning/error 0/0
- dependency HTML: I17 두 node가 포함된 28-target graph로 갱신 PASS
- 최종 research `tar_outdated()`: empty

## 실패 이력과 남은 위험

첫 production 시도는 마지막 shared-memory batch 참조가 남아 FD가 10에서 57로 증가해
hard failure했다. Batch 참조를 worker shutdown 전에 해제했다. 다음 시도에서는
`pin_memory=true`가 CUDA runtime을 초기화해 `/dev/nvidia*` FD를 열어 12에서 50으로
증가했고 다시 hard failure했다. I17 subprocess에서 CUDA를 비가시화하고 CPU-only hard
check 및 requested/effective pin 상태를 분리한 뒤 retained FD leak 0으로 통과했다. EOF
whitespace 정리로 contract hash가 바뀐 뒤에는 I17 두 target과 direct repeat만 다시
실행했다. 모든 시도에서 I09--I16은 재실행되지 않았다.

측정은 warm cache, 단일 반복, prototype 크기이므로 cold-storage throughput이나 장시간
persistent-worker 성능을 대표하지 않는다. Worker CPU/I/O counter는 worker 종료 뒤 일부
플랫폼에서 회수되지 않아 보조 지표로만 해석해야 한다. 다음 단계는 I18이며 이번
작업에서는 선언하거나 구현하지 않았다.

## 입력 프롬프트 요약

사용자는 I16 accepted dataset만으로 reusable PyTorch Dataset/DataLoader, deterministic
multi-resource batch sampler와 ragged collate를 구현하고, meter 단위 좌표, worker 0/4,
sequential/random access, corruption, round-trip, 성능과 dependency를 검증한 뒤 모든
조건이 통과한 경우에만 commit/push하며 I18 이후를 구현하지 말라고 요청했다.
