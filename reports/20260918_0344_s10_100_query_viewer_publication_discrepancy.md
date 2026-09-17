# S10 100-query viewer publication discrepancy audit

## 1. FINAL STATUS

**Production audit PASS; reported 30-query discrepancy NOT REPRODUCED; user-session root-cause diagnosis BLOCKED pending client evidence.**

- 보고서 최초 생성: 2026-09-18T03:44:37.120684+09:00 (Asia/Seoul).
- 목적/범위: 지정된 production root의 실제 files → 직접 HTTP responses → fresh Chromium DOM을 authority로 삼아 30-query 표시 제보를 조사한다. 기존 validation root 및 formal 100-query artifacts를 읽기 전용으로 대조한다.
- 입력 prompt 요약: production에서 30개만 보인다는 제보에 대해 추측 없이 root/count/hash/DOM을 감사하고, publication 결함이 입증될 때에만 scientific artifacts를 재사용한 immutable display-only fix를 수행한다. 기존 보고서/production overwrite 및 ranking recomputation/inference/checkpoint loading/S10·S11 실행은 금지.
- 입력 Git: branch `reduced`, HEAD `8e1832009ea6b2269201cbf9a3b6c73ba8d8db88`; 작업 전후 tracked worktree clean.
- 조사 대상 root: `/mnt/hdd002/dhnyu/fusedata/retrieval_data/reduced/s10_viewers/viewer_eb2cd9af73816e89b1390ded`. `Path.resolve()`도 동일하여 다른 root로 연결된 symlink가 아니다.
- 결과: filesystem config **100**, HTTP config **100**, DOM options **100**. 사용자 서버 8765에서도 fresh DOM **100**.
- 새 viewer, production/source fix, commit/push를 수행하지 않았다. Publication 결함 및 사용자 관찰의 원인이 규명되지 않았으므로 “원인 규명 및 fix PASS” 조건을 충족했다고 보고하지 않는다.
- 사용자에게 실제 browser URL과 DOM count/last option의 Console 결과를 요청했다. 보고서 작성 시점까지 해당 세션의 증거는 제공되지 않았다. Cache, forwarding, 잘못된 root 또는 native dropdown viewport를 원인으로 단정하지 않는다.

## 2. Observed user issue

사용자는 아래 명령으로 정확한 production directory를 serve했지만 browser dropdown에 30개만 표시되었다고 보고했다.

```sh
python -m http.server 8765 --bind 127.0.0.1 --directory /mnt/hdd002/dhnyu/fusedata/retrieval_data/reduced/s10_viewers/viewer_eb2cd9af73816e89b1390ded
```

실제 현재 서버 process를 read-only 조사했다: PID **1821919**, 시작 **2026-09-18 03:31:40 KST**, argv가 위 directory를 지정하고 127.0.0.1:8765를 listen한다. 이 process를 종료·재시작·변경하지 않았다. 이 서버의 현재 config/index/app/bands_app GET bytes도 production bytes와 일치했다.

이 사실은 현재 서버 상태에 관한 증거이며, 사용자의 이전 browser session이 같은 bytes를 표시했다는 추정은 하지 않는다.

## 3. Production file counts

| Production bytes에서 확인한 항목 | 결과 |
|---|---:|
| `queries/*.json` | 100 |
| `query_*.html` | 100 |
| index 포함 전체 HTML | 101 |
| `config.json: queries.length` | 100 |
| `config.json: models.length` | 28 |
| `viewer_receipt.json: query_count` | **필드 없음** |
| `band_evidence_receipt.json: query_count` | **필드 없음** |
| band evidence `band_rows` | 173,600 |
| receipt에 기록된 payload files checksum 검증 | 9,211개 PASS |

두 receipt의 query_count 필드 부재를 100이라는 값으로 대체하여 보고하지 않는다. 실제 query population은 config의 100개 rows 및 100개의 band query JSON에서 직접 확인했고 formal query manifest rows와 정확히 일치했다. UI는 receipt의 query_count 필드를 읽지 않으므로 그 필드 부재가 30-option 표시를 만들지는 않는다.

`index.html`은 `window.S10_BANDS=true`를 설정한 뒤 상대 경로 `app.js`, `locations.js`, `bands_app.js`를 load한다. Body의 `data-config-sha`는 **01b4761f95e5be8ba526985105f3dd54c6f2922795d6ba061b1a05de61e7772c**다. 모든 101 HTML에서 같은 config checksum 및 query_index 0–99 binding을 확인했다.

`bands_app.js:initBands()`는 `verified('config.json', document.body.dataset.configSha)`로 checksum 검증한 config를 읽고 **`config.queries.map(...)` 전체**로 dropdown을 만든다. Label은 `${q.query_index} / ${config.queries.length} · ${q.scene_id}`. Navigation upper bound도 `config.queries.length-1`이다.

## 4. HTTP counts

최초 probe의 temporary localhost port는 **42273**였고, 최종 확장 regression server는 **http://127.0.0.1:46571/**였다. 둘 다 **위 production root 자체**를 `SimpleHTTPRequestHandler(directory=production_root)`로 serve했다. Viewer를 local copy/staging/temporary directory로 복사하지 않았다. 아래 hash는 직접 HTTP response body와 filesystem bytes가 일치한 값이다.

| HTTP path | Bytes | SHA256 | Filesystem equality |
|---|---:|---|---|
| config.json | 1036671 | `01b4761f95e5be8ba526985105f3dd54c6f2922795d6ba061b1a05de61e7772c` | PASS |
| index.html | 2659 | `9e4e96d61ac6797fafc296236d78e3a7d192abec7ed393b2264449b99d9f863f` | PASS |
| app.js | 10566 | `88e38e2610b0b571edbe7b4f4e21944bf7e1e27efaeae006b44939f578e567bb` | PASS |
| locations.js | 1933 | `bf97288c8cd81ccc87923ae8391db3a42d1009ae4156d2fcf064f0ab8b794d46` | PASS |
| bands_app.js | 8753 | `360968153d720171950ca75055e55f0a4e8007087a75ab4bffdeb83046b1783b` | PASS |

HTTP config의 실제 queries 길이는 **100**이다. 최종 browser가 실제 load한 JS/config response body도 request-finished 시점에 읽어서 filesystem bytes와 대조했다: **24개 기록**, 모두 일치. HTTP response, 실제 loaded responses, served root, receipt hash는 `/mnt/hdd002/dhnyu/fusedata/tmp/fuse/s10-publication-discrepancy-20260918/browser_verified/validation.json`의 `network`에 저장했다.

별도로 사용자 서버 `http://127.0.0.1:8765/`의 현재 GET 응답을 비교했고 동일 hash였다. 그 서버에 대한 fresh browser 검사도 **100 options, 28 models, UI error 없음**이다. 증거: `/mnt/hdd002/dhnyu/fusedata/tmp/fuse/s10-publication-discrepancy-20260918/existing_8765_browser.json`.

## 5. DOM counts

Playwright Chromium을 새로 실행하고 explicit fresh context, `service_workers='block'`, CDP `Network.setCacheDisabled(true)`, `Network.setBypassServiceWorker(true)`를 사용했다. 최종 HTTP response events **1555건** 중 disk cache 응답 **0**, service worker 응답 **0**이다.

- filesystem query count: **100**
- HTTP config query count: **100**
- DOM `#query option` count: **100**
- 31st option 존재: **true**

| Option | 실제 DOM text |
|---|---|
| 1 | 1 / 100 · scn_28d2cb1e58601426259844e3 |
| 30 | 30 / 100 · scn_d98bae7d9aad582ad675c412 |
| 31 | 31 / 100 · scn_393afbf52ad5f9afc351d52e |
| 50 | 50 / 100 · scn_a1572fa0cee3813779f245ab |
| 100 | 100 / 100 · scn_8d90cc0a32f275618d6927a1 |

단순 옵션 수뿐 아니라 query **1 / 30 / 31 / 50 / 100** 각각의 production HTML을 직접 load했고, dropdown으로 해당 query 사이를 이동해 표시 scene/제목이 변경됨을 확인했다.

## 6. Root cause

**현재 production publication/UI binding defect는 발견되지 않았다. 사용자에게 30개만 보였던 근본 원인은 미확정이다.**

검사 결과:

- Generated config/HTML/app/bands_app에 `query_count = 30`, `slice(0, 30)`, first-30 truncation, hard-coded 30 navigation bound, `viewer_f33...` URL/config 참조가 없다.
- `python/s10_query_viewer.py`는 새 formal query manifest의 `q['body']['rows']`로 config queries를 구성한다. Parent viewer의 config에서 재사용하는 것은 **palette**이며 query list가 아니다.
- 이전 `tools/retrieval_inspector/supplemental/build_bands.py:build_bands()`에는 old 30-query gate가 존재한다. 새 publisher는 그 함수가 아닌 **`legacy_css()`만 재사용**한다. 그 old gate가 production dropdown을 30개로 자르는 실행 경로는 없다.
- Generated `app.js`의 이전 UI initializer는 `window.S10_BANDS` guard로 실행하지 않는다. 활성 `bands_app.js`는 실제 100-row config를 사용한다.
- Generated query list는 `s10_queries_d8875a530a769040d5ec7fb3`의 100 rows와 같으며 stale old query manifest를 사용하는 흔적이 없다.

비교용으로 읽은 30-query 부모들은 첫 query가 `scn_804d625229e303af92739d3f`이며 config SHA가 각각 `6789287ab1371c75c94b8735164131e605a4d805b865e3f0d35a3c41b11d34a9` (f33), `ef19348e347b6ef2c3940b9a191a9672944301d21aff1018e38b02059a941bdc` (59c)이다. 현재 production 첫 query와 checksum은 모두 다르다. 이는 사용자 세션의 bytes가 제공되면 대조할 fingerprint일 뿐, 사용자가 이 부모 root에 접속했다는 증거는 아니다.

추가로 필요한 사용자 세션 증거:

```js
JSON.stringify({
  url: location.href,
  count: document.querySelector('#query')?.options.length,
  last: document.querySelector('#query')?.options[document.querySelector('#query').options.length-1]?.text
})
```

현재 정상인 production을 다시 publish하는 것으로 미확정 사용자 세션 원인을 해결했다고 주장할 수 없다.

## 7. Previous validation root comparison

| Evidence | 확인된 root / 의미 |
|---|---|
| `logs/20260918_0307_s10_query_browser.log` 결과 JSON | `/mnt/hdd002/dhnyu/fusedata/retrieval_data/reduced/s10_viewers/viewer_eb2cd9af73816e89b1390ded` |
| `logs/20260918_0307_s10_query_browser_final.log` 결과 JSON | 같은 final published root |
| 기존 `browser/validation.json`, `browser_final/validation.json`의 `viewer` | 같은 final published root |
| 기존 `viewer_path.txt` | 같은 final published root |
| 기존 screenshots | `/mnt/hdd002/dhnyu/fusedata/tmp/fuse/s10-query-audit-20260918/browser{,_final}/query_{1,50,100}.png`; **증거 저장 경로**이지 served viewer root가 아님 |
| Validator HTTP handler | `directory=str(viewer)`; local viewer copy/staging을 만들지 않음 |
| Publisher staging | `.s10-100-viewer-*`에서 생성 후 final root로 이동, receipt-last publish; validator에 staging path를 반환하지 않음 |
| 현재 final receipt SHA256 | `8b9649325f48e0e042e315e283d36848d898a7455fb1dbe72bacaeb1ec48fd46` |

이전 두 validation JSON은 query 1/50/100 × 4 models × 2 modes = 24 cases, 72 thumbnail clicks, JS errors 0을 기록한다. 현재 committed validator에는 실제 dropdown 0→49→99 navigation 검사도 있다. 따라서 기존 validation이 temporary viewer만 검사했다는 증거는 발견하지 못했다.

**이전 증거의 한계:** 당시 validation JSON에는 served URL/port, HTTP body checksum, receipt SHA, explicit cache-disabled 상태를 저장하지 않았다. 현재 읽은 receipt hash를 당시 로그가 저장했던 hash라고 주장하지 않는다. 이번 감사에서는 이 필드를 모두 추가 기록했다. 기존 보고서의 100-option 주장과 현재 production bytes/DOM은 일치하므로 해당 주장을 사실 오류로 조용히 교체하지 않았다. 기존 보고서가 committed bytes와 동일함도 검사했다.

## 8. Fix

Production/UI fix 및 republish는 수행하지 않았다. 이유는 publication-layer 결함이 입증되지 않았고 과학 artifact 및 display bindings가 정상임이 확인되었기 때문이다. 기존 root나 config/JS/receipt를 수정하지 않았다.

감사 증거 수집기의 오류 1건은 별도로 처리했다. 처음 확장 audit에서 40 browser cases를 통과한 뒤 과거 페이지의 `Response.body()`를 늦게 읽다가 Chromium의 `No resource with given identifier found` 오류가 발생했다. 이는 response-body 보관 시점의 **audit instrumentation 오류**였으며 viewer UI 오류로 분류하지 않는다. `requestfinished` 즉시 body/hash를 저장하도록 감사 전용 외부 script를 고쳐 전체 검증을 재수행했고 최종 PASS했다. 실패 로그도 보존했다.

Code/targets 변경이 없으므로 targets execution/network rebuild는 하지 않았다. 사용자 요청의 조건인 root cause/fix PASS가 충족되지 않아 commit/push도 하지 않았다. 기존 HEAD는 위 input commit과 동일하다.

## 9. New viewer

**새 viewer 생성 없음.** 검증된 현 production root는 `/mnt/hdd002/dhnyu/fusedata/retrieval_data/reduced/s10_viewers/viewer_eb2cd9af73816e89b1390ded`이며 DOM options는 100개다. Broken root라고 확정되지 않은 디렉터리를 수정하거나 새로운 과학 generation으로 우회하지 않았다.

Existing band evidence는 100 queries/28 models/2 modes에 대해 complete하고 checksum 검증을 통과하여, 향후 display-only 수정의 실제 필요성이 확인된다면 재사용 가능하다. 이번 감사에서는 재발행하지 않았다.

## 10. Browser evidence

최종 fresh/cache-disabled/SW-blocked production regression:

- **40 cases**: query 1/30/31/50/100 × main/ofat_d_256/cmp_DS/cmp_B9 × Standard/Non-local.
- 28 model dropdown entries 확인.
- Rank1 / Top / Middle / Bottom binding 및 실제 scene, **120 thumbnail clicks** PASS.
- Vector, LC/DEM dimensions/display/toggles, location labels/coordinates, detailed thematic summaries, zoom/reset, query navigation PASS.
- 1800/1600/1200px layout 검사 PASS. JavaScript errors **0**.
- Query JSON 전체의 model/mode/band identity와 stored band positions 확인. 모든 production file checksum PASS.
- Browser evidence: `/mnt/hdd002/dhnyu/fusedata/tmp/fuse/s10-publication-discrepancy-20260918/browser_verified/validation.json`.
- Screenshots: `/mnt/hdd002/dhnyu/fusedata/tmp/fuse/s10-publication-discrepancy-20260918/browser_verified`의 `query_1.png`, `query_30.png`, `query_31.png`, `query_50.png`, `query_100.png`.
- HTTP/DOM 측정은 screenshot을 읽어 추정하지 않고 response bytes와 DOM에서 직접 수집했다.
- 최초 instrumentation 실패 log: `logs/20260918_0340_s10_publication_discrepancy_browser.log`.
- 최종 PASS log: `logs/20260918_0340_s10_publication_discrepancy_browser_verified.log`.
- Read-only 감사 scripts 및 추가 inventory/hash 증거는 `/mnt/hdd002/dhnyu/fusedata/tmp/fuse/s10-publication-discrepancy-20260918`에 보존한다. 이 경로에는 viewer copy가 없다.

## 11. Scientific safety

Read-only verification 결과:

- Formal acceptance: **`s10_acceptance_e41bb7c33d2ae4171a1f2c59`**, manifest envelope/hash 및 accepted artifact IDs 확인.
- Formal queries: **`s10_queries_d8875a530a769040d5ec7fb3`**, 실제 **100 unique rows**.
- 28 ranking Parquet payload를 읽어 실제 **280,000 rows**, 모든 query×model×mode별 50 rows를 확인했다.
- Existing band JSON: **173,600 rows**, formal Top50 안에 속하는 stored band rows **61,600개**를 기존 Parquet rows와 exact equality로 비교했다. Ranking을 새로 계산하지 않았다.
- Viewer receipt files **9,211개**의 recorded SHA256 검증 PASS.
- 감사 시작/종료 사이 scientific manifest/Parquet **58개**와 production receipt hash unchanged.
- **Ranking recomputation 0, embedding loading 0, checkpoint loading 0, inference 0, S10 rerun 0, S11 execution 0.** Browser는 기존 display/ranking bytes만 읽었다.
- 기존 보고서 및 production root 변경 없음. Git에는 대용량 output/store/log/browser image를 stage/commit하지 않았다.

최종 판정/다음 단계: production 파일·HTTP·fresh DOM은 100개로 일치한다. 사용자 browser에서 30개로 보인 원인을 확정하려면 해당 세션의 URL/DOM 결과가 필요하다. 그 근거 없이 cache 문제 또는 publication 오류로 단정하지 않는다.
