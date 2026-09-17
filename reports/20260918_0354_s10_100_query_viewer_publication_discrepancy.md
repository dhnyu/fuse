# S10 100-query viewer discrepancy: confirmed stale document

## 1. FINAL STATUS

**PASS — root cause identified from user-session evidence; correct production endpoint independently verified.**

- 최초 생성: 2026-09-18T03:54:52.176770+09:00 (Asia/Seoul).
- 작업 목적: 사용자 브라우저의 실제 DOM 30개를 authoritative evidence로 받아 8765 process/root/HTTP와 대조하고 불일치 지점을 규명한다.
- 입력 prompt 요약: PID/cmdline/cwd/serve root/curl을 확인하고 기존 listener 때문에 새 server가 bind하지 못했는지 조사한다. 사용자 브라우저에서 제공한 no-store same-origin fetch 결과도 대조하며 필요하면 새 포트에서 현재 100-query viewer를 검증한다. Ranking/inference/checkpoint/S10/S11 실행 금지 유지.
- 입력 Git: `/members/dhnyu/fuse`, `reduced`, `8e1832009ea6b2269201cbf9a3b6c73ba8d8db88`.
- 결론: **열린 사용자 문서가 이전 30-query location viewer에 바인딩되어 있었다. 같은 브라우저의 현재 HTTP 응답은 정상적인 새 100-query config다.** Production publication 오류 또는 현재 serve-root 오류가 아니다.
- 조치: 같은 immutable production root를 별도 localhost **18765**에서 serve하고 fresh browser의 DOM 100개와 query 1/30/31/50/100을 검증했다. 사용자 쪽에서는 현재 페이지를 새 문서로 load해야 한다.
- 한계: 오래 열린 탭의 문서가 유지된 것인지, 이전 HTML을 browser cache에서 재사용한 것인지는 이 증거만으로 구분되지 않는다. 이를 확정된 특정 cache mechanism으로 과장하지 않는다. 새 주소에서의 사용자 직접 재로드 결과는 아직 별도로 전달받지 않았다.
- 이 보고서는 앞선 `20260918_0344_s10_100_query_viewer_publication_discrepancy.md`의 원인 미확정 상태를 새 사용자 증거로 해소한다. 기존 보고서들은 수정하지 않는다.

## 2. Observed user issue

사용자가 직접 읽은 DOM:

```json
{"url":"http://127.0.0.1:8765/?model=main&mode=standard","count":30,"last":"30. scn_3630fa4b21edbe5a8918b00a"}
```

같은 페이지에서 cache를 우회한 `fetch('/config.json?probe=s10_8765_0348', {cache:'no-store'})` 결과:

```json
{
  "url": "http://127.0.0.1:8765/?model=main&mode=standard",
  "domCount": 30,
  "documentConfigSHA": "ef19348e347b6ef2c3940b9a191a9672944301d21aff1018e38b02059a941bdc",
  "httpCount": 100,
  "httpLast": "scn_8d90cc0a32f275618d6927a1",
  "acceptance": "s10_acceptance_e41bb7c33d2ae4171a1f2c59"
}
```

사용자 DOM count=30은 실제 관찰이며 부정하지 않는다. 동시에 같은 사용자 origin의 새 응답 count=100도 실제 관찰이다. 서로 다른 시점의 loaded document와 current HTTP response를 비교한 것이므로 두 관찰은 양립한다.

## 3. Production file counts

정확한 production root:

`/mnt/hdd002/dhnyu/fusedata/retrieval_data/reduced/s10_viewers/viewer_eb2cd9af73816e89b1390ded`

| 항목 | 실제 값 |
|---|---:|
| queries/*.json | 100 |
| query_*.html | 100 |
| index 포함 HTML | 101 |
| config.queries.length | 100 |
| config.models.length | 28 |
| viewer_receipt.query_count | 필드 없음 |
| band receipt.query_count | 필드 없음 |
| band receipt.band_rows | 173,600 |

UI는 receipt의 query_count가 아니라 `config.queries.map(...)` 전체를 사용한다. Generated bands_app.js의 label은 `1 / 100` 형식이며 bounds는 `config.queries.length-1`이다. Slice-to-30이나 old viewer URL 참조는 없다. 모든 HTML은 현재 config SHA와 query_index 0–99에 바인딩된다.

## 4. HTTP counts and listener audit

`ss -ltnp | grep 8765`, PID process listing, `/proc/<PID>/cwd`, `/proc/<PID>/cmdline`을 직접 확인했다.

2026-09-18 03:47–03:49 KST의 **songlab** 상태:

| 항목 | 8765 listener |
|---|---|
| PID | **1839430** |
| Process 시작 | **2026-09-18 03:44:32 KST** |
| cwd | `/members/dhnyu/fuse` |
| `/proc/1839430/root` | `/` |
| cmdline | `python -m http.server 8765 --bind 127.0.0.1 --directory /mnt/hdd002/dhnyu/fusedata/retrieval_data/reduced/s10_viewers/viewer_eb2cd9af73816e89b1390ded` |
| 실제 LISTEN | `127.0.0.1:8765` |
| curl config count | **100** |

앞선 감사 때는 같은 정확한 root를 지정한 PID **1821919**, 시작 03:31:40이었다. 그 후 PID가 교체되었다. 1839430은 실제 listener이므로 **이 시점의 새 server가 기존 30-query server 때문에 bind에 실패했다는 가설은 성립하지 않는다.** Shell에서 과거 실패한 command가 별도로 있었는지는 전체 사용자 shell history를 조사하지 않았으므로 주장하지 않는다. 현재 HTTP bytes가 정상인 상황에서 그 가설로 사용자 DOM 30개를 설명할 수도 없다.

후속 조회에서는 8765 listener가 더 이상 보이지 않았다. 감사 작업은 이 사용자 server를 kill/restart하지 않았다. 따라서 PID 1839430은 위 관찰 시점의 상태로 기록하며 계속 실행 중이라고 보장하지 않는다.

직접 실행한 curl:

```sh
curl --noproxy '*' -sS http://127.0.0.1:8765/config.json
curl --noproxy '*' -sS http://127.0.0.1:8765/index.html
```

config response: 100 queries, 마지막 `scn_8d90cc0a32f275618d6927a1`, acceptance `s10_acceptance_e41bb7c33d2ae4171a1f2c59`.

| Resource | Filesystem = HTTP SHA256 |
|---|---|
| config.json | `01b4761f95e5be8ba526985105f3dd54c6f2922795d6ba061b1a05de61e7772c` |
| index.html | `9e4e96d61ac6797fafc296236d78e3a7d192abec7ed393b2264449b99d9f863f` |
| app.js | `88e38e2610b0b571edbe7b4f4e21944bf7e1e27efaeae006b44939f578e567bb` |
| bands_app.js | `360968153d720171950ca75055e55f0a4e8007087a75ab4bffdeb83046b1783b` |

Index body의 data-config-sha는 위 current config SHA다. `window.S10_BANDS=true`, 상대 경로 `app.js`, `locations.js`, `bands_app.js`를 load한다. `/proc/.../cwd`가 repository인 것은 문제가 아니다. Serve root는 절대 경로의 `--directory`가 결정한다.

## 5. DOM counts

| Context | Document / HTTP | DOM count |
|---|---|---:|
| 사용자 기존 8765 페이지 | document SHA `ef19348e…`, 새 HTTP config 100 | **30** |
| 감사 fresh browser 8765 | current document/current config | **100** |
| 최종 확장 감사 `http://127.0.0.1:46571/` | 같은 production root 직접 serve | **100** |
| 새 endpoint `http://127.0.0.1:18765/` | 같은 production root 직접 serve | **100** |

18765에서 직접 읽은 options:

| Position | Text |
|---|---|
| 1 | 1 / 100 · scn_28d2cb1e58601426259844e3 |
| 30 | 30 / 100 · scn_d98bae7d9aad582ad675c412 |
| 31 | 31 / 100 · scn_393afbf52ad5f9afc351d52e |
| 50 | 50 / 100 · scn_a1572fa0cee3813779f245ab |
| 100 | 100 / 100 · scn_8d90cc0a32f275618d6927a1 |

31st option 존재=true. Fresh context, cache disabled, service workers blocked 상태에서 각각 선택하여 실제 query title/scene까지 확인했다.

## 6. Root cause

사용자의 `documentConfigSHA`:

`ef19348e347b6ef2c3940b9a191a9672944301d21aff1018e38b02059a941bdc`

이 값은 **`viewer_59c5653e6a27d4e89581e943/config.json`의 실제 SHA256**과 정확히 일치한다. 해당 이전 location viewer는 30 queries이며 마지막 scene ID도 사용자가 보고한 `scn_3630fa4b21edbe5a8918b00a`다. 그 UI의 마지막 label 역시 `30. ...` 형식이다.

반면 같은 브라우저의 no-store HTTP fetch는 새 100-query acceptance와 새 마지막 scene ID를 받았다. 이로써 현재 동일 origin의 서버 응답이나 포트 연결이 이전 30-query root로 가고 있다는 설명은 배제된다. **현재 문서/JS state가 새 production 문서로 교체되지 않은 것이 불일치의 원인이다.** 서버의 root/process를 바꾸어도 이미 열린 브라우저 문서와 그 DOM이 자동으로 교체되지는 않는다.

확정 범위는 stale loaded document/session이다. Cached HTML revalidation 문제인지, 열린 탭을 그대로 사용한 것인지는 구분되지 않으며, 특정 browser cache bug나 VS Code forwarding bug를 주장하지 않는다.

## 7. Previous validation root comparison

앞선 browser evidence에 기록된 root는 모두 `/mnt/hdd002/dhnyu/fusedata/retrieval_data/reduced/s10_viewers/viewer_eb2cd9af73816e89b1390ded`였다. Screenshot 디렉터리의 `/tmp/.../browser_final`은 증거 저장 경로이며 serve root가 아니었다. Validator는 production root를 직접 `SimpleHTTPRequestHandler(directory=...)`로 serve했다.

- 최초 explicit probe URL: `http://127.0.0.1:42273/`.
- 최종 확장 fresh-context URL: **`http://127.0.0.1:46571/`**.
- 별도 기존 서버 직접 검사 URL: `http://127.0.0.1:8765/`.
- 새 사용 가능한 endpoint: `http://127.0.0.1:18765/`.
- 모두 감사 당시 current production root의 config/index/JS bytes와 일치했다.
- Final viewer receipt SHA: `8b9649325f48e0e042e315e283d36848d898a7455fb1dbe72bacaeb1ec48fd46`.

이전 100-query browser validation과 사용자의 stale 30-query document는 서로 다른 browser context였다는 점이 사용자 same-origin probe로 확인되었다. 임시 viewer만 검증하고 production에 30개를 publish했다는 증거는 없다. 이전 validation JSON의 URL/HTTP SHA/receipt SHA 기록 부족은 앞선 감사 보고서에서 이미 명시했고 이번 확장 evidence에 보완했다.

## 8. Fix

**새 scientific/viewer generation을 만들 필요 없이 새 문서를 load하면 된다.** 별도 포트 18765를 열어 기존 origin의 문서/리소스 상태를 공유하지 않는 접속 경로를 마련했고, actual production bytes로 100-query rendering을 확인했다.

- 새 server PID: **1843525**.
- Bind: `127.0.0.1:18765` on **songlab**.
- Serve root: `/mnt/hdd002/dhnyu/fusedata/retrieval_data/reduced/s10_viewers/viewer_eb2cd9af73816e89b1390ded`.
- 실행 명령: `python -u -m http.server 18765 --bind 127.0.0.1 --directory /mnt/hdd002/dhnyu/fusedata/retrieval_data/reduced/s10_viewers/viewer_eb2cd9af73816e89b1390ded`.
- Server log: `logs/20260918_0348_s10_viewer_18765.log`.
- User action: 새 페이지에서 `http://127.0.0.1:18765/?model=main&mode=standard`를 연다. VS Code Remote SSH 사용자라면 **18765를 포워딩한 실제 local address**를 사용한다. 같은 stale 문서에서 query만 바꾸는 것으로는 문서가 교체되지 않는다.

새 endpoint 검증 PASS는 auditor browser에서의 결과다. 사용자 본인의 새 탭에서 확인한 최종 count를 받았다고 주장하지 않는다. Production files와 기존 report는 변경하지 않았다. 코드 변경이 없으므로 새로운 단위 테스트나 targets/network regeneration은 적용 대상이 아니다. 기존/확장 실제 browser validation 및 read-only artifact checks를 검증 근거로 사용한다.

## 9. New viewer

**새 immutable viewer directory는 생성하지 않았다.** 원본 publication은 정상이며, 같은 `/mnt/hdd002/dhnyu/fusedata/retrieval_data/reduced/s10_viewers/viewer_eb2cd9af73816e89b1390ded`를 새 포트로 제공한다. 기존 broken viewer를 overwrite하는 수정은 없었다. 이 사례에서 “broken”은 production bytes가 아니라 사용자에게 남아 있던 old document/session 상태였다.

## 10. Browser evidence

- Final full regression: **40 cases / 120 band clicks**, query 1/30/31/50/100 × 4 models × both modes. 28-model dropdown, Rank1/Top/Middle/Bottom, vector/LC/DEM controls, location metadata, detailed summaries, zoom/reset, layout PASS; JS errors 0.
- Full validation: `/mnt/hdd002/dhnyu/fusedata/tmp/fuse/s10-publication-discrepancy-20260918/browser_verified/validation.json`. Recorded disk-cache/service-worker responses 0; actual JS/config body hash 비교 포함.
- 18765 live server validation: `/mnt/hdd002/dhnyu/fusedata/tmp/fuse/s10-publication-discrepancy-20260918/new_server_18765_browser.json`. DOM 100, 28 models, 1/30/31/50/100 navigation 및 current HTTP hashes PASS.
- 18765 screenshot: `/mnt/hdd002/dhnyu/fusedata/tmp/fuse/s10-publication-discrepancy-20260918/new_server_18765_query100.png`.
- Process/cwd/cmdline evidence: `/mnt/hdd002/dhnyu/fusedata/tmp/fuse/s10-publication-discrepancy-20260918/listener_followup.json`.
- Both-port HTTP evidence: `/mnt/hdd002/dhnyu/fusedata/tmp/fuse/s10-publication-discrepancy-20260918/listener_followup_http.json`.
- User authoritative probe: `/mnt/hdd002/dhnyu/fusedata/tmp/fuse/s10-publication-discrepancy-20260918/user_same_origin_probe.json`.

앞선 감사의 body-capture instrumentation 오류와 성공한 retry는 `20260918_0344_s10_100_query_viewer_publication_discrepancy.md`에 공개되어 있다. 이번 listener/probe attribution 검사에서는 실패가 없었다.

## 11. Scientific safety and delivery

Formal query manifest는 실제 100개, accepted Top50는 280,000 rows, stored supplemental bands는 173,600 rows다. 기존 band의 formal Top50 포함 부분 61,600 rows exact comparison, 9,211 viewer file SHA 검증이 PASS했다. Same-origin 사용자 probe도 정확한 새 acceptance를 확인한다.

**Ranking recomputation, embedding/checkpoint loading, inference, S10 rerun, S11 execution은 모두 0회.** 이번 단계 종료 전에도 scientific manifest/Parquet 58개 checksum unchanged를 확인했다. S09/S11 및 기존 production bytes/보고서 변경 없음.

이 단계는 진단과 endpoint 검증의 PASS다. 승인된 `reduced` commit/push에는 앞선 미확정 audit report와 이 확정 follow-up report만 포함한다. 데이터, viewer, logs, targets store, screenshot은 Git에 넣지 않는다. 실제 commit SHA는 최종 전달 응답에 기록한다.
