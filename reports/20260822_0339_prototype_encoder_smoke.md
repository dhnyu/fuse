# Prototype Encoder Smoke Report

## 판정과 범위

- 최종 판정: **READY**
- 실행 시각: 2026-08-22 03:31--03:39 KST
- 시작 HEAD: `1ef578312a31dc4a505e5567d2a4aed6b4145fc5`
- I18 구현 commit: `7a375f8` (`Implement I18 prototype encoder smoke`)
- branch/push: `feature/research-scene-index`, `origin/feature/research-scene-index` PASS
- dissertation source: `73c7f5a65ae18960ac1990af035bca9076210f69`
- accepted dataset: `ptd_140215eef2c1fa6da8304c6e`
- DataLoader smoke: `pdl_a402b7ac668ddabfb6ba50f0`
- encoder acceptance ID: `pea_b638d0bae07c75824684e328`

I18만 구현했다. Augmentation, online/momentum pair, EMA, queue, InfoNCE training,
checkpoint/resume, AMP/DDP 및 I19 이후 target은 I18 실행 범위에 포함하지 않았다.

## Architecture 계약

논문 model dimension/structural/architecture 표와 object embedding, modality fusion,
relation, scene embedding 및 Fourier appendix를 contract target이 직접 추적한다.
구현은 float32, latent/scene/projection dimension 128, dropout 0.1이다.

- relative position: meter 입력, 10--1,000 m geometric wavelength 16개, 64차원
- intrinsic geometry: meter 입력을 500 m로 정규화, radial 8 x angular 16,
  magnitude/phase encoding, line arc-length 및 polygon area measure
- semantics: Building/Road/POI별 categorical/numerical encoder와 논문 hierarchy dimension
- object raster: 26차원 encoder
- fusion: 16차원 type embedding을 사용하는 4-modality type-aware gate
- relations: SN/CNT/WIT/INT/CON multi-mask embedding 합, 4 heads x 32, 3 layers
- pooling: type별 attention pooling, three 128-vector object summaries
- raster: LC embedding 16, LC/DEM 별도 64/128/128 CNN, GroupNorm(8), GELU, GAP
- final fusion: 640 -> 256 -> 128, projection 128 -> 256 -> 128

전체 trainable parameter는 1,996,534개, parameter tensor는 231개다.

## Empty와 Sparse 계약

논문은 entity type이 비어 있으면 해당 type summary를 zero vector로 정의한다. 따라서
0-node scene의 object branch는 three exact zero vectors이며 raster branches와 final
fusion으로 유효한 embedding을 만든다. Edge가 없는 node에는 relation message zero를
적용한 뒤 residual/normalization/feed-forward path를 유지한다. POI intrinsic geometry는
원래 unavailable이므로 gate availability가 0이고 geometry weight는 exact zero다.
학습 가능한 empty token 등 논문에 없는 선택은 추가하지 않았다.

## GPU Smoke 결과

대표 batch는 0-node/0-edge, node-only, median, maximum-node, maximum-edge,
geometry-heavy scene 6개를 포함했다. 별도 I17 variable-budget training batch도 6 scene으로
forward했다. Representative/general entity 수는 각각 11,782/9,370이다.

| 항목 | 결과 |
|---|---:|
| final/projection dimension | 128 / 128 |
| eval deterministic equality | PASS |
| dropout train/eval difference | PASS |
| forward/loss/backward finite | PASS |
| gradient coverage | 231/231 |
| missing/zero/NaN/Inf gradient tensor | 0/0/0/0 |
| scene/projection L2 max error | `5.96e-8` / `5.96e-8` |
| position CPU/GPU reference max error | `5.96e-8` |
| line Fourier reference max error | `5.26e-8` |
| multi-relation sum max error | `0` |
| deterministic scalar smoke loss | `1.0418457985` |

GPU는 physical index 0, UUID `GPU-76021239-303e-21e9-8f05-73670ea100fe`,
NVIDIA RTX A6000이다. Driver 595.45.04, CUDA runtime 13.0, PyTorch 2.12.0+cu130,
compute capability 8.6을 기록했다. Peak allocated/reserved VRAM은
20,266,232,320 / 20,703,084,544 bytes(18.87/19.28 GiB), 총 VRAM은 49,140 MiB다.
Smoke 내부 wall time은 21.03 s, target wall time은 33.6 s였다.

Launcher는 shared `gpu_pair.lock` 뒤 device exclusive `gpu0.lock`을 POSIX `flock`으로
획득하며 publish 완료까지 보유했다. Lock wait는 1.98 s였고 process exit의 descriptor
close로 해제했다. `CUDA_VISIBLE_DEVICES`는 torch import 전에 lock-selected physical GPU로
제한했다.

## Artifact와 결정성

Acceptance directory는 staging에서 QC 완료 후 atomic publish했다. Architecture manifest,
parameter/shape Parquet, QC JSON 및 structured JSONL log의 size/SHA-256을 manifest에
기록하고 실제 파일과 대조했다. Scientific identity는 accepted dataset/DataLoader ID와
checksum, 논문 commit, config/schema/tensor contract, model/smoke/launcher/requirements
hash 및 float32 precision을 포함하며 runtime/VRAM/lock wait는 제외한다.

Eval forward는 같은 tensor에서 bit-exact했고 numerical reference tolerance `1e-5`를 모두
충족했다. Acceptance manifest checksum은
`9709a6850e9f7b171bf228a019dee13101c888908f97e87fe165de243d062b66`이다.

## Tests, Targets와 Dependency

- Python parse 및 YAML/JSON schema parse: PASS
- I18 Python fixture 3/3: PASS
- I18 R target/contract fixture: PASS
- 전체 `Rscript tests/testthat.R`: PASS
- `tar_manifest()`: 30 targets, I18 static file target 확인
- `tar_network()`: I16, I17, scoped contract에서 I18로 향하는 3 edge만 존재
- `tar_validate()`: PASS
- execution: I18 contract + I18 target 2 completed, upstream 128 skipped
- final research-store `tar_outdated()`: empty

## 실패 이력과 남은 위험

첫 target 시도는 PyTorch 2.12 CUDA memory-stat API가 `torch.device` 인자를 거부해
실패했다. Local visible index 0을 명시했다. 두 번째 시도는 I15의 계약 dtype `uint8`
category/entity index를 CUDA embedding에 직접 전달해 실패했으며, embedding lookup
경계에서만 `int64`로 변환했다. 원본 tensor dtype와 과학 의미는 바꾸지 않았다. 이후
I18만 재실행했고 모든 시도에서 I09--I17은 재실행되지 않았다.

초기 확인 중 legacy `_targets.yaml` 기본 store를 사용한 `tar_outdated()`가 maintenance
metadata를 읽어 광범위한 false result를 보였다. 어떤 target도 그 store에서 실행하지
않았으며 이후 모든 감사/실행은 명시적 research store
`/mnt/hdd002/dhnyu/fusedata/targets/fuse-research`를 사용했다.

Peak VRAM은 이 대표 batch에 대한 float32 correctness 측정이며 training augmentation,
two-view online/momentum encoder, optimizer state 및 queue의 메모리를 포함하지 않는다.
따라서 I21 training feasibility를 직접 승인하지 않는다.

## 입력 프롬프트 요약

사용자는 I16/I17만 직접 dependency로 갖는 GPU-locked static I18 target에서 최신 논문의
encoder를 구현하고 empty/sparse/dense float32 forward/backward, gradient, reference,
VRAM 및 artifact 계약을 검증하되 augmentation/training은 구현하지 말라고 요청했다.
