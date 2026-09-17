# S10 100-query sparse-constraint implementation

## 1. FINAL STATUS

**PASS — audit, separately authorized implementation, immutable publication and validation completed.**

- 보고서 최초 생성: 2026-09-18T03:18:09.879482+09:00 (Asia/Seoul).
- 목적/입력 프롬프트 요약: S10 query를 30→100개로 확대하고 canonical 객체 수 `<10`인 query를 최대 5개로 제한한다. Gallery 9,000, 모델 28개, ranking/mode/band semantics와 S09/S11을 보존하고 새 generation/acceptance/viewer를 생성한다. PASS 후 reduced commit 및 origin/reduced push 요청.
- 입력 저장소: `/members/dhnyu/fuse`, branch `reduced`, 작업 전 commit `fd3701f5da435a35902a566c8c9f959f22efa1c3`; 최초 worktree clean. Fetch 후 origin/reduced와 0/0 divergence.
- 최신 로컬 논문 commit: `0f48542d16912d66631a3a27c38f478ac90910b3`; `methodology/01-scene-construction.typ`, `results/02-spatial-scene-retrieval.typ`와 blueprint 확인.
- 논문 10 queries와 기존 S10 30 queries의 차이를 먼저 보고했다. 사용자가 **“별도 100-query 계약 신설 승인”**으로 명시 승인했다. 논문 파일과 기존 30-query 계약을 수정하지 않고 blueprint에 별도 승인된 정책을 추가했다.
- 구현/검증 PASS에 따라 이번 코드·보고서·dependency HTML만 commit/push한다. 실제 commit SHA 및 push 결과는 최종 응답에 기록한다.

## 2. Current 30-query audit

기존 immutable parent:

- Generation: `s10gen_a24b979d4c1557387cbbec35`
- Acceptance: `s10_acceptance_5471f74031f267c4253df231`
- Query manifest: `s10_queries_be96426f20a6fc04c4a43fb1` (새 query manifest의 `source_manifest_ids.parent_query`에도 바인딩).
- Gallery: `s10_gallery_16e80b03246c193969aad9b5`
- Models: `s10_models_22d6f477bf3d2d7f2b591804`
- Full-band viewer: `viewer_f33db05a1507064733ee8702`
- 위치 메타데이터를 포함한 후속 display parent: `viewer_59c5653e6a27d4e89581e943`

`config/retrieval_visualization.yml` → `targets/s10_retrieval_visualization.R:s10_retrieval_query_manifest` → `python/retrieval_pipeline.py:query_manifest()` → `retrieval_ranking.sample_queries()` 순서다. Population은 accepted P3/P1에 바인딩된 evaluation original 9,000개이며, scene_id lexical 정렬 후 **PCG64 seed 20260916**, `choice(..., replace=False)`를 사용하고 draw order를 보존한다. 기존 30개를 재추출하여 manifest와 정확히 일치함을 확인했다.

Query 선택은 formal acceptance의 `common()` 재추출 검증에 직접 포함된다. 기존 schema의 `query_count: const 30`, acceptance의 `(28,9000,30,50)` 검사도 고정되어 있다. Original inputs, geometry, embeddings, rankings, renders, pages, summary와 acceptance가 query/generation/runtime에 바인딩된다. 기존 config만 수정하면 이 연결된 산출물들의 새 identity/재검증이 필요하며, 기존 manifest의 query ID만 바꾸는 것은 허용되지 않는다.

Supplemental viewer는 formal acceptance를 소비하고 별도 full-order band evidence를 만든다. 기존 publishers도 acceptance ID와 30-query 수를 고정하고 있어 그대로 100개에 적용하지 않았다. 별도 revision graph/publisher를 추가했다. 기존 S10 runtime에 기록된 모든 source checksum은 작업 후에도 일치한다.

기존 query의 `<10` 비율은 **5/30 = 16.67%**, 전체 gallery는 **938/9000 = 10.42%**다. 기존 query 중 정확히 0개 객체인 scene은 **0개**다. 따라서 실제 문제는 literal empty scene만이 아니라 low-object scene의 과대표집이며, 기존 query median 276.5도 gallery median 660보다 낮다.

## 3. Object-count definition

`object_count = |B^(l)| + |R^(l)| + |P^(l)| = n_buildings + n_roads + n_pois`.

Accepted P3 original shard의 `vector/building_observed.parquet`, `vector/road_observed.parquet`, `vector/poi_observed.parquet`에서 해당 scene_id에 속하는 **observed entity row 수**를 합산한다. Scene 내 `(entity_type, source_entity_id)`와 `local_entity_id`의 고유성을 검사한다. Count source는 P3 index 및 payload SHA-256에 바인딩하며 gallery 전체를 두 번 읽어 동일한 canonical count를 검증했다. Viewer count를 selection 입력으로 사용하지 않았다.

- Building: canonical `building_feature_id`의 scene 내 관측 entity.
- Road: canonical `links` layer의 **LINK_ID 하나당 scene 내 road entity 하나**. Clipped MULTILINESTRING의 여러 part, source topology node/chain position, relation edge는 추가 객체가 아니다. 링크를 재분할·병합하지 않는다.
- POI: canonical `NF_ID`의 scene 내 point entity.
- P2 membership은 B/R에 positive retained area/length (`DE-9IM T********`), POI에 closed-window `st_intersects`를 적용한다. B/R geometry는 window로 clip되고 POI는 원래 point를 유지한다.
- Accepted observation 계약은 empty/invalid/zero-measure geometry에서 branch를 실패시키므로, 새 count가 empty geometry를 임의 제거하거나 새 공간 필터를 적용하지 않는다. 이미 acceptance를 통과한 observed rows를 센다.
- 근거: `config/membership.yml`, `R/spatial_membership.R:exact_membership_pairs`, `R/vector_observations.R:clip_geometry_by_scene` 및 observation 검증, `python/retrieval_originals.py:OriginalReader.read`, `python/model_data.py:tensorize_scene`.
- 공통 original tensor는 이 entity population을 그대로 보존한다. 모델별 ablation/family projection **이전** count를 써서 28개 모델에 공통 query set을 유지한다. Raster cell과 raster-only 표현은 entity count에 포함하지 않는다.
- Viewer summary는 tensor의 building/road/poi row index 길이다. 새 viewer의 모든 8,999개 display scene에서 canonical P3 count와 정확히 일치함을 별도 검사했다.
- Sparse 판정은 엄격하게 **`object_count < 10`**: 9는 sparse, 10은 regular.

## 4. 9,000-scene object-count distribution

Quantile은 NumPy percentile의 기본 linear interpolation이다.

| 통계 | Evaluation 9,000 | 기존 query 30 | 새 query 100 |
|---|---:|---:|---:|
| min | 0 | 1 | 0 |
| median | 660 | 276.5 | 851 |
| mean | 974.1154 | 635.8 | 1,016.52 |
| p10 | 8 | 2.8 | 58.3 |
| p25 | 116 | 70.25 | 266.75 |
| p75 | 1,655 | 871.25 | 1,694.5 |
| p90 | 2,367 | 2,060.5 | 2,205.3 |
| max | 6,547 | 2,586 | 3,768 |
| object_count = 0 | 373 | 0 | 1 |
| object_count < 5 | 714 | 5 | 3 |
| object_count < 10 | 938 | 5 | 5 |
| object_count >= 10 | 8,062 | 25 | 95 |

## 5. New 100-query sampling protocol

정책: `s10-100-query-sparse-v1`, `config/s10_query_revision.json`.

1. 결과/ranking을 보기 전에 seed **20260916**을 고정했다. 이후 변경하지 않았다.
2. Accepted gallery를 scene_id lexical 순으로 정렬하고 `<10` / `>=10` strata로 나눈다.
3. 하나의 `numpy.random.Generator(PCG64(20260916))` stream으로 sparse에서 `min(5, available_sparse)`개, 이어 regular에서 나머지를 비복원 추출한다.
4. Sparse draw 다음 regular draw 순서로 query_index 1–100을 부여한다. 따라서 처음 5개가 sparse인 정해진 표시 순서이며, 결과를 본 뒤 shuffle하거나 seed를 조정하지 않았다.
5. Regular population이 부족하면 fail closed. Sparse 부족 시 available sparse 전부와 regular 보충을 unit test했다.
6. 모든 28개 모델과 Standard/Non-local은 동일한 immutable query rows를 사용한다.

Manifest에 query_count, seed, population, without-replacement, exact count definition, threshold/max/actual sparse·regular 수, scene IDs/centers/type별 counts, parent manifest IDs, P3 source checksums, ordering/RNG 정책을 포함한다.

## 6. Selected query statistics

정확히 **100 unique queries = sparse 5 + regular 95**. 빈 scene은 1개, `<5` scene은 3개다. 위 표에 전체 분포를 제시했다.

| Regular 객체 수 구간 | Gallery regular | 기존 query | 새 query |
|---|---:|---:|---:|
| 10–24 | 419 | 0 | 5 |
| 25–49 | 341 | 1 | 0 |
| 50–99 | 432 | 2 | 5 |
| 100–249 | 854 | 6 | 9 |
| >=250 | 6016 | 16 | 76 |

Regular 95개 중 >=250은 76개(80.0%); 전체 regular population의 해당 비율은 약 74.6%다. 25–49 구간은 이번 고정 표본에 없다. 이를 공개하지만 추가 stratification/강제 구간 할당을 도입하지 않았다. 세부 count-range coverage를 보장할 필요가 생기면 별도 정책 승인 후 검토해야 하며, 이번 seed나 결과를 교체할 사유로 사용하지 않는다.

## 7. Old/new query overlap

**1개**: `scn_545daea680e8cb398013678f`.

기존 30개는 sparse가 정확히 5개이므로 보존 자체가 constraint와 충돌하지는 않는다. 그러나 요청의 기본 권장대로 강제 보존하지 않고 전체에서 새로 추출했다. 겹치는 query의 28×2×50 = **2,800행**에서 기존/새 ranking의 scene ID, 순서, cosine, 거리, checkpoint identity가 모두 정확히 일치했다.

## 8. S10 lineage impact

기존 generation/acceptance/viewer를 overwrite하지 않았다. 기존 30-query config/schema/code/targets/store도 유지한다. 새 정책에는 새 query manifest, ranking artifacts 및 acceptance가 필요하며, 단순 viewer UI 수정만으로는 충분하지 않다.

- 새 generation: `s10gen_fdff84a5dd8b3565f7c39f58`
- 새 count manifest: `s10_summary_23f3f3f85170560c12b5277a`
- 새 query manifest: `s10_queries_d8875a530a769040d5ec7fb3`
- 새 acceptance: `s10_acceptance_e41bb7c33d2ae4171a1f2c59`
- 기존 model/gallery manifests는 **원래 ID와 경로로 참조**한다. Gallery population·centers·CRS를 재생성하지 않는다.
- Embedding manifest의 기존 query/generation/runtime binding을 변경하지 않는다. 새 ranking에는 새 query ID와 original accepted embedding ID/parent acceptance를 함께 기록한다.
- 별도 graph: `_targets_s10_query_revision.R`; store `/mnt/hdd002/dhnyu/fusedata/targets/fuse-s10-query-revision`.

## 9. Ranking/reuse implementation

28개 normalized float32 embedding payload의 SHA-256, shape, 9,000개 scene ID 순서, model identity, 원래 query/gallery/model/generation/runtime binding을 확인했다. 모두 finite/unit-normalized였으며 query는 gallery 안에 있으므로 해당 vector row를 사용했다.

**Checkpoint loading 0, inference 0, training 0, 새 Fourier/전처리 실행 0.** Ranking 함수는 기존 `retrieval_ranking.rank`를 그대로 호출한다. Cosine descending, exact tie에서 lexical scene ID ascending, self 제외, Non-local에서 거리 `<2000m`만 제외하며 정확히 2000m는 유지한다. Ranking read-back을 재계산 결과와 exact equality로 검증했다.

새 실행 모듈은 `python/s10_query_revision.py`, 표시 모듈은 `python/s10_query_viewer.py`, orchestration은 `scripts/s10_query_revision.py`, `R/s10_query_revision.R`, `targets/s10_query_revision.R`에 둔다. Ranking-only 경로에는 training/checkpoint/inference/S11 import가 없다. Viewer가 새로 읽은 `.pt`는 이미 저장된 original scene tensor이며 checkpoint가 아니다.

## 10. New acceptance

`/mnt/hdd002/dhnyu/fusedata/retrieval_data/reduced/s10_query_revisions/s10gen_fdff84a5dd8b3565f7c39f58/acceptance.json`

PASS checks: 100 unique evaluation queries, 동일한 9,000 gallery와 centers/EPSG:5186, canonical P3 count 재계산, sparse 5/regular 95, 입력 순서 반전에 불변인 deterministic sampling, 28개 모델×2 mode 공통 query, 정확히 **280,000 Top50 rows**, ranking 재계산/read-back, accepted embedding bindings/checksums, unchanged source/runtime, evaluation-only membership. Training/validation을 query/gallery에 추가하지 않는다.

Scientific acceptance는 query/ranking generation을 승인하고 viewer는 이 acceptance를 parent로 하는 별도 supplemental receipt를 가진다. 모든 파일은 staging/create-or-validate 방식으로 쓰고 acceptance/receipt를 마지막에 쓴다. Existing path에 다른 bytes를 덮어쓰지 않는다.

## 11. Viewer generation

- New viewer: `viewer_eb2cd9af73816e89b1390ded`
- 100 query JSON, query_01–query_100 HTML + index = **101 HTML**.
- 28 models, Standard/Non-local, legacy five-column layout, vector/raster controls, detailed summaries, location metadata 유지.
- Dropdown은 `1 / 100` … `100 / 100`을 표시한다.
- Rank1; Top 2–11; middle 시작 `floor((N-10)/2)+1`의 10개; bottom N−9..N 유지. Standard N=8,999. Non-local N은 query별로 다르다.
- Full order에서 선택한 **173,600 band rows = 100×28×2×31**. 모든 formal Top50와 일치 확인. 전체 order를 Top50 근사로 대체하지 않는다.
- Display union **8,999 scenes**. Parent scene JSON **8,627개 byte reuse**, missing **372개**만 accepted P3/tensor에서 display serialization. Gallery 자체는 9,000개다.
- Location metadata **9,000 rows byte reuse**, full-precision center binding 검사. 재공간조인/좌표변환 없음.
- 기존 상세 summary가 canonical building/road/poi counts를 보여 주므로 optional Objects header는 추가하지 않았다.

## 12. Tests

- 변경 R/Python parse/syntax PASS.
- 관련 6개 pytest module **117 passed (5.23s)**. Selection count/determinism/unique/stable-order, 9/10 threshold, sparse 부족/regular 부족, exact hash-bound P3 row count와 payload corruption rejection, original query binding 위조 rejection, no scientific execution imports, Standard/Non-local/ties/Top50 및 기존 viewer 회귀 포함.
- 실제 normalized gallery pilot: 1 model × 2 queries × 2 modes, 200 Top50 rows; full-order reconstruction exact match PASS, 계산 구간 약 0.030s.
- `tar_manifest`, dependency network, `tar_validate` PASS; **6 targets / 8 edges**. `tar_make` **6 completed, 0 skipped**, target errors/warnings 없음. `tar_outdated` empty.
- Full 280,000 ranking rows deterministic read-back; overlap 2,800행 independent exact comparison PASS.
- Chromium: query **1/50/100**, model **main/ofat_d_256/cmp_DS/cmp_B9**, 양 mode의 **24 cases**, **72 thumbnail clicks**, direct first/middle/last page loading, 실제 0→49→99 dropdown 이동, 28-model dropdown, vector/raster toggles, zoom/reset, detailed summaries, 위치 표시, 1800/1600/1200px layout PASS. JS errors **0**.
- All viewer file hashes, all query/model/mode band memberships/ranks와 173,600 rows 확인. 모든 8,999 display summary counts와 P3 count 일치.
- Dependency HTML: `artifacts/targets-network/s10-query-revision/targets-network.html`. 생성 HTML의 node IDs 6개와 edge 8개를 재확인, 모두 up_to_date.
- Browser evidence: `/mnt/hdd002/dhnyu/fusedata/tmp/fuse/s10-query-audit-20260918/browser_final/validation.json` 및 screenshots. Query 1 screenshot을 직접 확인해 five-column/위치/상세 summary 유지 확인.

초기 manifest inspection에서 기본 `tar_manifest()` 출력에 없는 `format` column을 요청한 검사 명령 오류 1건이 있었다. `fields=tidyselect::everything()`로 수정한 후 통과했다. Production target 실패나 미해결 경고는 없다. 첫 browser suite PASS 후 실제 dropdown navigation/zoom 검사를 보강해 최종 suite도 PASS했다.

## 13. Performance

기존 30-query 실측: formal ranking 28 branches 합계 약 26.7s (process startup 포함), supplemental full-band viewer **304.65s**, query JSON **13,849,062 bytes**, display union 8,628, viewer **4,700,076,024 bytes**. 기존 전체 S10 10,593s는 inference/준비를 포함하므로 이번 작업에 재적용하지 않는다.

실행 전 추정: query/ranking 양은 100/30 = 3.33배, formal ranking 약 90s의 보수적 선형 추정, query JSON 약 46MB, band 173,600 rows, display union 최대 9,000, HTML 101개. Gallery display가 포화되므로 viewer 전체 bytes는 3.33배가 아니다. 재사용을 전제로 CPU1/thread1에서 generation+viewer 약 5–15분을 사용자에게 알렸다.

실제 별도 `tar_make`: **221.7s = 3분 41.7초**, 2026-09-18 **03:07:45.91–03:11:27.46 KST**.

| 단계/용량 | 실제 |
|---|---:|
| Canonical count target | 23.7s |
| Count 재검증 + 28 model ranking + acceptance | 43.8s |
| Full-order reconstruction + viewer/QC | 151.1s |
| New formal Parquet | 4,718,639 bytes |
| New query band JSON | 46,154,598 bytes |
| New viewer all files | 3,418,241,842 bytes |

New viewer는 scene JSON에 SVG를 포함하고 중복 standalone SVG를 남기지 않아 기존 full-band viewer보다 작다. Pure ranking/full-order 계산만의 별도 production timing은 계측하지 않았으며 위 수치는 QC/I/O를 포함한 target wall time이다. 최초 read-only 감사는 45.36s. Browser/test/report/git 소요는 221.7s에 포함하지 않는다. CPU worker 1, target당 BLAS/OpenMP thread 1; GPU 사용 없음.

## 14. Scientific safety

기존 S10 acceptance와 `viewer_f33db05a1507064733ee8702`는 immutable parent로 유지. Original S10 runtime source hash mismatches **0**. 작업 전후 S09/S11 관련 tracked source 및 parent receipt를 포함한 **126-file snapshot** unchanged. Checkpoint/embedding bytes에는 write하지 않는다. S09 winners/configurations/scientific model results와 S11 protocol/store는 수정/실행하지 않았다. S11의 기존 blocked 상태도 변경하지 않았다.

논문 원문은 여전히 10-query 설명이고 별도 승인된 qualitative extension임을 명시한다. 추가 object-count stratification, gallery filtering, model selection, seed tuning은 하지 않았다. 전체 research/training/maintenance/기존 S10/S11 pipeline `tar_make`는 이번 요청의 실행 대상이 아니므로 실행하지 않았다.

Raw data, staging, tensors, Parquet, viewers, targets store, browser captures와 logs는 Git에 넣지 않는다. Code/tests/config/blueprint와 요청 보고서 및 dependency HTML만 commit 대상이다. 최종 checksum/QC/browser gates 모두 PASS; 미해결 blocker 없음.

## 15. New viewer path

`/mnt/hdd002/dhnyu/fusedata/retrieval_data/reduced/s10_viewers/viewer_eb2cd9af73816e89b1390ded`

Local serving example:

```sh
python -m http.server 8765 --bind 127.0.0.1 --directory /mnt/hdd002/dhnyu/fusedata/retrieval_data/reduced/s10_viewers/viewer_eb2cd9af73816e89b1390ded
```

Open `http://localhost:8765/`. Browser checksum 검증을 위해 HTTP localhost로 열며 file:// 대신 이 경로를 사용한다. 서버를 자동 실행하지는 않았다.

Reproduce independent pipeline:

```sh
Rscript -e 'targets::tar_make(script="_targets_s10_query_revision.R", store="/mnt/hdd002/dhnyu/fusedata/targets/fuse-s10-query-revision")'
```

Logs: `logs/20260918_0307_s10_query_revision.log`, `logs/20260918_0307_s10_query_tests.log`, `logs/20260918_0307_s10_query_browser_final.log` (Git 제외).
