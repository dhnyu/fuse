# I21 Acceptance Publication Recovery

## 목적과 범위

- 실행 시각: 2026-08-22 22:51--2026-08-23 05:05 KST
- 복구 감사/발행 시각: 2026-08-23 04:54--05:05 KST
- 목적: 정상 완료된 dual-GPU I21 학습을 재실행하지 않고 publication-only schema 오류를 복구한다.
- 입력 프롬프트 요약: completed run과 checkpoint를 읽기 전용으로 감사하고, 현재 I20 ID와 네 개의 논리 output을 고정한 별도 acceptance publisher로 I21을 atomic publish한다.
- 최종 판정: `READY`

## Git과 Scientific Parents

- Fuse 시작 HEAD/remote: `7f48cb56bf08c92df999d1336769342dc43e760e` / 동일, divergence `0/0`
- Dissertation HEAD/remote: `0a251da679ef0e65967cca5e24e6b276988e28db` / 동일, clean, divergence `0/0`
- 구현 commit: `ddf8b6ad08888a482248842476860f9cf895ef8c`
- push: `origin/feature/research-scene-index`, `7f48cb5..ddf8b6a`, 성공
- I20 plan: `ptp_3b100622bdb733351db6e458`
- I20 run: `ptr_473911a4828ae5540a9d4eb9`
- Joint model: `pjm_056c0d32b223808fd8dabc75`
- DDP joint acceptance: `pjd_13aff4a58d3d6022ee2dd62f`
- I21 acceptance: `pta_cf6bc4679a06305fb1185a8e`

## 완료 Run 감사

- 종료: epoch 55 validation에서 strict-MRR patience 10에 도달한 `early_stopping`
- optimizer/EMA steps: 440/440
- training scene consumptions: 14,080 = 55 epochs x 256 scenes
- logical groups: 각 epoch group 0--7이 정확히 한 번씩 존재
- global effective batch: 각 step 32 scenes
- queue: final occupancy 8,192, canonical FIFO pointer 3,584
- final rank-state digest: `c1f8428a1ee3167ce7d5b71f69668aa865cefe4ba13303af9ad798efe9cefdaa`
- final sampler state: 양 rank 모두 epoch index 54, group position 8, permutation length 256 및 동일 permutation
- controlled resume: step 1 checkpoint에서 step 2 replay, direct/replay digest 모두 `1304777d4d8b52fc59668a112d5d9235edfbe00472972d7df094712d0af56216`
- 추가 optimizer/forward/backward/CUDA operations: 모두 0

모든 13개 checkpoint는 CPU에서 load되었고 online/target model, projection/decoder, optimizer, scheduler, EMA count, queue tensors/pointer/occupancy, Python/NumPy/Torch CPU/Torch CUDA RNG, rank sampler와 accumulation state를 포함했다. 모든 floating tensor는 finite였다. Checkpoint의 run ID, seed, scientific-parent checksum과 world size는 최신 I20 lineage와 일치했다. 이전 single-GPU 및 실패한 DDP run 경로의 artifact는 입력 집합에서 거부했다.

## Validation과 Checkpoint

- validation cadence: epochs 5, 10, ..., 55, 총 11회
- 모든 validation: MRR/HIT@1/HIT@5/HIT@10 = `1.0/1.0/1.0/1.0`, population 32
- patience replay: epoch 5에서 0, 이후 strict improvement가 없어 epoch 55에서 10
- selection replay: MRR, HIT@1, earliest epoch 규칙에 따라 epoch 5
- reloaded-best validation: 기존 runner가 best checkpoint reload 후 metric/embedding/retrieval digest exact 비교를 통과한 뒤 staging을 생성했다. Recovery는 이 control-flow evidence, staged QC, final checkpoint history와 source hash를 함께 검증했으며 새 forward를 실행하지 않았다.
- best checkpoint: `epoch-005.pt`, 44,745,909 bytes, SHA-256 `a17477a647d68024cb59ce6c3ce66a703e12143f37340b90c82cd3549b303704`
- final checkpoint: `epoch-055.pt`, 44,749,557 bytes, SHA-256 `601fe896865582d859706dbf5c12009a3133e21a9240a438dec24f00bc12c55c`
- optimizer ledger: 245,373 bytes, SHA-256 `2c0c31576705cf1f49b8b6a3986f530bcc2785d499b0243e71c07a9d1e7f9c3f`
- telemetry ledger: 186,242 bytes, SHA-256 `26811041c480f3fdd6b773420447d9631d0d42c79da5ac28212f530f8ea02d34`
- 13개 checkpoint의 publication 전/후 SHA-256 map: exact identical

## Acceptance Outputs

Schema는 기존 임의의 `outputs >= 4` 대신 다음 네 role을 각각 정확히 한 번 요구한다.

| Role | File | SHA-256 |
|---|---|---|
| run completion | `run_completion.json` | `c566fc902d5447b0c974618082ac9450b5ce1e56f8c85ca137d756ab96eaaf12` |
| validation/early stopping | `validation_history.json` | `afca0e1f595799de1ec19e198b0dfd0e941b595b52c7b0e03c6ff8f16bbf36a9` |
| checkpoint catalog | `checkpoint_catalog.json` | `efa1860313ca068089d7c6d66a32f3636b254d82f28daca3baa1c278fa8fd4c6` |
| recovery QC | `publication_recovery_qc.json` | `fda2ae572ca98161f05fb3741bd5aaa34bcadb4849f18e29e3255def67169097` |

Acceptance는 branch-local staging에서 schema/checksum validation 후 atomic rename으로 publish됐다. 동일 direct rebuild는 `identical_reuse`; 임시 fixture의 same-ID/different-content publication은 hard failure였다. Missing, duplicate, foreign-role/path output과 old plan/run ID도 fixture에서 거부됐다.

## Numerical과 Resource Evidence

- training elapsed evidence: 21,343.51 seconds
- total loss first/final/min/max: 3.27809 / 3.87213 / 3.27809 / 6.33128
- gradient norm min/max: 2.82159 / 14.93213, 모두 finite
- LR first/peak/final: `1.25e-6` / `1e-4` / `8.68561e-5`
- peak allocated VRAM rank 0/1: 20,839,079,936 / 17,817,260,544 bytes
- peak reserved VRAM rank 0/1: 50,241,470,464 / 48,576,331,776 bytes
- peak per-rank process-tree RSS: 28,688,457,728 / 28,695,506,944 bytes
- accepted DDP smoke speedup: 1.8489x

## 검증 결과

- Python `py_compile`: PASS
- Python unit tests: 33 PASS
- JSON/YAML/Draft 2020-12 schema parse: PASS
- full `Rscript tests/testthat.R`: PASS
- `tar_manifest()`: 42 static targets
- `tar_network()`: 344 vertices, 653 edges
- `tar_validate()`: PASS
- scoped recovery target: 3 completed, 139 skipped; GPU/optimizer execution 없음
- recovery target `tar_meta()` warning/error: 0/0
- dependency HTML: regenerated
- final research-store `tar_outdated()`: empty

Research store에는 보존 정책에 따른 과거 실패 target metadata가 남아 있지만 현재 graph의 recovery targets에는 warning/error가 없다. Failed publication staging과 original logs는 diagnostic evidence로 보존했다. Runtime checkpoints, logs, target store, caches와 credentials는 Git에 포함하지 않았다.

## 남은 위험과 다음 단계

- Prototype validation population이 32로 작고 epoch 5부터 retrieval metric이 포화됐다. 이 acceptance는 실행·resume·publication 정확성을 검증하며 최종 scientific performance를 주장하지 않는다.
- 다음 안전 단계는 blueprint의 accepted prototype model gate이며, 별도 승인 없이 full experimental campaign을 시작하지 않는다.
