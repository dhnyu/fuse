# targets dependency network

이 도구는 `_targets.R`을 정적으로 읽어 dependency graph를 HTML로 저장한다.
`tar_make()`나 개별 target command는 실행하지 않는다. `targets::tar_network()`의
vertex/edge metadata를 사용하고 `visNetwork`로 검색, 확대·이동, 인접 node 강조,
기능 그룹 색상을 제공한다.

필요 패키지는 현재 환경에 설치된 `targets`, `visNetwork`, `htmlwidgets`, `yaml`이다.
기본 store는 `config/research_paths.yml`의 `targets.research_store`다.

## 전체 graph

```bash
Rscript tools/targets-network/render_targets_network.R
```

출력: `artifacts/targets-network/targets-network.html`

## 특정 target 중심 graph

```bash
Rscript tools/targets-network/render_targets_network.R \
  --focus=spatial_scene_index \
  --degree=1
```

`--degree`는 선택 target에서 양방향으로 포함할 dependency hop 수다. 위 명령은
전체 graph와 `targets-network-focus-spatial_scene_index.html`을
함께 생성한다. 다른 출력 위치는 `--output-dir=/path/to/output`으로 지정한다.
다른 store를 검사할 때는 `--store=/absolute/store/path`를 사용한다.

HTML은 self-contained이며 `artifacts/targets-network/`는 `.gitignore`에 포함된다.
