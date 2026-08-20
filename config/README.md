# Research pipeline configuration

## Files

- `research_paths.yml`: read-only source paths, layer contracts, derived root와 분리된 research/maintenance targets store.
- `scene_construction.yml`: 논문에 고정된 scene/split/retrieval 값과 재현성 seed, prototype selection 설정.
- `schemas/methodology_contract.schema.json`: published `methodology_contract.json`의 JSON Schema 2020-12 계약.
- `membership.yml`: B/R/P exact membership predicate, source ID/layer, row schema와 cost-balanced shard 계약.
- `membership_runtime.yml`: controller, concurrency, retry, atomic publish와 native thread 상한. Runtime concurrency는 scientific ID에서 제외한다.
- `schemas/prototype_membership.schema.json`: I06 branch spec의 JSON Schema 2020-12 계약.
- `vector_observation.yml`: clipping, observed attributes, local IDs, numerical tolerance, GeoParquet 1.1 writer와 cost-balanced shard 계약.
- `vector_observation_runtime.yml`: I10 `controller_10`, 1x1 native threads, retry와 atomic publish 설정.
- `schemas/prototype_vector_observation.schema.json`: B/R/P observed row의 공통 field와 geometry 계약.
- `raster_observation.yml`: scene LC 100x100, DEM 17x17, observed-geometry object support, nodata와 Zarr/Parquet 저장 계약.
- `raster_observation_runtime.yml`: I11 `controller_10`, branch 1x1 thread, concurrency pilot와 atomic publish 설정.
- `schemas/prototype_raster_observation.schema.json`: scene raster index, object context, branch manifest/QC의 JSON Schema 계약.

`research_config_files`가 세 파일을 `format="file"`로 추적한다. 따라서 내용 변경은
`methodology_contract`와 필요한 downstream을 outdated시킨다. Thesis commit, dirty
status, PDF SHA-256과 mtime은 config나 scientific hash에 포함되지 않고
`methodology_provenance.json`에만 기록된다.

## Fixed methodology

- Processing CRS: EPSG:5186
- Official grid native CRS: EPSG:5179
- Scene: 500 m square
- Training stride: 250 m, official 500 m grid center phase preserved
- Off-lattice: nearest training center distance at least 50 m
- Split: validation 1,000, evaluation 2,000
- Retrieval: fixed evaluation query 10; self-only exclusion gives 1,999 candidates
- Prototype: training 256, validation 32, evaluation 32

Runtime worker/controller changes belong in environment or runtime config and must not alter
scientific IDs unless they change numeric execution semantics.

## Raster observations

- Land cover scene tensor: 22-class area composition `float32` `(scene, 22, 100, 100)` plus validity ratio/mask. Categorical interpolation, silent category `0`, padding은 금지한다.
- DEM scene tensor: raw metre area mean `float32` `(scene, 17, 17)` plus validity ratio/mask. normalization과 imputation은 training 단계로 미룬다.
- Object support: I10 observed Building area, Road length, POI containing cell만 사용한다. LC는 raw class support와 valid-normalized composition, DEM은 overlap-weighted mean/population SD를 저장한다.
- Zarr v2는 scene당 chunk, Blosc Zstd level 5 + bitshuffle, consolidated metadata를 사용한다. `zarr_member_manifest.json`은 staging 경로를 포함하지 않는 ordered member array와 SHA-256을 기록한다.

## Membership predicates

- Building: scene polygon과 DE-9IM interior/interior 관계가 있어 positive-area retained clip이 생길 때만 포함.
- Road: scene polygon과 DE-9IM interior/interior 관계가 있어 positive-length retained clip이 생길 때만 포함.
- POI: closed scene footprint와 intersect하면 포함하므로 boundary point도 포함.
- Multipart는 source entity 한 개로 유지한다. Invalid, empty, geometry collection과 duplicate source ID는 silent drop/repair하지 않고 branch를 실패시킨다.
