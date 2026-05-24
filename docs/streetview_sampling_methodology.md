# Street View Image Sampling Methodology

## Purpose and Scope

This document reverse-engineers the current Street View sampling workflow implemented in the FUSE repository. It describes how road-network sample points are produced, how they are linked to Google Street View metadata, how panoramas are acquired and converted into directional crops, and how the resulting artifacts are validated and stored. The emphasis is methodological rather than file-oriented: the goal is to make the implemented research workflow reproducible and interpretable before scaling beyond the current pilot and benchmark stages.

The system is currently prototype-scale for Street View imagery. The spatial sample is Seoul-scale, but only the first 1,000 sampled points have been queried through the metadata pilot, and only a 100-panorama benchmark subset has been processed for cached panorama imagery and directional crops.

## 1. Overall Pipeline Overview

The Street View workflow is downstream of a road-network sampling pipeline. The project first constructs reproducible spatial sampling locations along Seoul roads. These point locations are then used as query coordinates for the Google Street View metadata endpoint. Metadata responses determine whether imagery exists near each sampled point and provide the stable `pano_id` used to identify panoramas. Image acquisition is deliberately panorama-first: the code downloads or reuses a complete equirectangular panorama once per unique panorama ID and then generates front/right/rear/left perspective crops locally.

This design separates three concerns:

- spatial sampling: where in Seoul to query;
- metadata auditing: whether Google Street View imagery exists and what panorama/date is returned;
- image materialization: downloading panoramas and deriving reproducible crops for visual modeling.

### Workflow Diagram

```text
Seoul boundary + OSM road network
        |
        v
500 m grid in EPSG:5186
        |
        v
non-tunnel road sampling network
        |
        v
regular road candidates every 10 m
        |
        v
seeded greedy Poisson-style thinning
        |
        v
40,000 road-constrained sample points
        |
        v
first 1,000 points sent to Google Street View metadata endpoint
        |
        v
metadata parquet + summary + duplication + capture-year diagnostics
        |
        v
first 100 unique valid pano_id values
        |
        v
cached panorama JPGs
        |
        v
front/right/rear/left 512 x 512 perspective crops
        |
        v
manifest, logs, crop diagnostics, contact sheets
```

The most important relational key is `pano_id`. The road sample table identifies source sample points by `point_id`; the metadata table links each `point_id` to a returned `pano_id`; the image cache and crop filenames are organized by `pano_id`. This makes it possible to study both point-level coverage and panorama-level duplication.

## 2. Sampling Point Generation

### Spatial Origin of Sampling Locations

Street View locations originate from the road-network sampling pipeline in `R/road_environment_sampling.R` and `scripts/streetview/10_run_road_network_sampling_global.R`. They are not sampled directly from grid-cell centroids and they are not one point per grid cell. Instead, points are sampled globally along the operational Seoul road network and assigned to grid cells only after sampling.

The road data source is OpenStreetMap via Geofabrik, accessed through `osmextract`. The implementation stores a canonical road archive and then constructs an operational sampling network. The canonical archive retains road attributes such as `tunnel`; the sampling network excludes tunnel roads because underground or covered road segments are undesirable for Street View scene sampling.

### Boundary, Grid, and CRS

The Seoul grid is a 500 m square grid built in projected coordinates. The implementation uses:

- projected CRS: EPSG:5186 in the code (`PROJECTED_CRS <- 5186`);
- geographic CRS: EPSG:4326 for longitude/latitude output (`LONLAT_CRS <- 4326`);
- grid resolution: 500 m;
- current grid cells: 2,631;
- current sampling-network road features: 75,532;
- current sampling-network length: approximately 10,105,709 m.

The boundary is read, made valid, transformed to EPSG:5186, and used to filter the grid and clip the road network. The road downloader uses the grid bounding box buffered by 250 m, transformed back to longitude/latitude for the OSM extraction boundary.

### Road Hierarchy and Candidate Generation

The workflow retains a defined set of OSM `highway` classes and assigns each a numeric rank:

| Highway class | Rank |
| --- | ---: |
| motorway | 1 |
| trunk | 2 |
| primary | 3 |
| secondary | 4 |
| tertiary | 5 |
| residential | 6 |
| service | 7 |
| living_street | 8 |
| unclassified | 9 |

The current implementation does not explicitly weight selection by road hierarchy. The rank is preserved as `sampled_rank`, but it is not used as a probability weight in the thinning step. Road hierarchy affects the final sample indirectly because different road classes have different total mapped lengths and spatial distributions. Longer and denser classes generate more candidate points, and candidate points compete spatially during thinning.

Candidate points are generated every 10 m along eligible road geometries by `line_candidate_points()` and `generate_road_candidates()`. A road segment shorter than half the candidate spacing is ignored. For all other segments, candidate distances start at `spacing_m / 2` and proceed at regular 10 m intervals along each linestring. This means the initial candidate pool is approximately line-length weighted: more road length produces more candidates.

### Randomization and Determinism

The final sample is generated by `poisson_disk_thin_candidates()`, a seeded greedy thinning algorithm:

1. Set the random seed (`SEOUL_SAMPLE_SEED`, default `20260517`).
2. Randomly permute all candidate points.
3. Visit candidates in that random order.
4. Accept a candidate only if it is at least 50 m from all previously accepted points.
5. Stop once the target count is reached (`SEOUL_TARGET_SAMPLE_COUNT`, default 40,000).

The thinning algorithm uses a grid index in projected meter coordinates to avoid all-pairs distance checks. The result is deterministic for a fixed input network and seed. The nearest-neighbor distance recorded in the output is computed after acceptance and confirms the minimum spacing rule. In the current output, the minimum nearest-neighbor distance is exactly 50 m, the median is about 64.1 m, and the maximum is about 422.1 m.

### Grid Assignment and Empty Cells

Grid assignment occurs after sample selection. The accepted projected points are spatially joined to the 500 m grid using `st_within`. If a point lacks a containing cell after the join, the implementation assigns the nearest grid feature. This fallback handles boundary precision and geometry edge cases.

The current 40,000-point sample covers 2,245 of 2,631 grid cells. Therefore, the workflow does not force coverage of every grid cell. Cells with no eligible road candidates, cells where candidates lose during the global thinning process, and low-road-density cells may have zero points. Among covered cells, the current output ranges from 1 to 41 points per grid cell, with a mean of 17.8 points.

### Current Sample Composition

| Quantity | Current value |
| --- | ---: |
| Sample points | 40,000 |
| Grid cells | 2,631 |
| Grid cells with sampled points | 2,245 |
| Minimum spacing | 50 m |
| Candidate spacing | 10 m |
| Seed | 20260517 |
| Output CRS for coordinates | EPSG:4326 lon/lat |

| Highway class | Sampled points |
| --- | ---: |
| residential | 19,314 |
| service | 10,109 |
| primary | 3,059 |
| secondary | 2,969 |
| tertiary | 2,446 |
| trunk | 1,113 |
| living_street | 497 |
| unclassified | 308 |
| motorway | 185 |

The dominance of residential and service roads follows from the line-length-weighted candidate pool and the road network structure. It should not be interpreted as an explicit class quota.

## 3. Street View Metadata Collection

### Metadata Request Logic

The metadata pilot is implemented in `tests/test_gsv_metadata_pilot.py`. It reads the first `GSV_METADATA_PILOT_SIZE` rows from the global sample parquet, defaulting to 1,000 rows. For each point, it sends a request to:

```text
https://maps.googleapis.com/maps/api/streetview/metadata
```

The request parameters are:

- `location`: formatted as `lat,lon` from the sampled point;
- `source`: `outdoor`;
- `key`: `GOOGLE_MAPS_API_KEY`.

The key is never stored in output. The workflow stores a key-free `metadata_url_without_key` field for reproducibility and debugging.

The pilot is intentionally metadata-first. It estimates coverage, temporal range, panorama uniqueness, and point-to-panorama offsets before attempting large image downloads.

### Retry and Error Handling

Metadata requests use a `requests.Session`, a default timeout of 30 seconds, and up to three attempts (`GSV_METADATA_MAX_RETRIES`). Server errors, connection errors, and timeouts trigger exponential backoff capped at 2 seconds. Non-JSON responses are captured as `NON_JSON_RESPONSE`; invalid JSON is captured as `INVALID_JSON`; repeated request failure is captured as `REQUEST_FAILED`. Normal no-imagery responses from Google appear as `ZERO_RESULTS`.

The pilot writes four parquet outputs:

- row-level metadata: `gsv_metadata_pilot_1000.parquet`;
- one-row summary: `gsv_metadata_pilot_summary.parquet`;
- panorama duplication counts: `gsv_pano_duplication_counts.parquet`;
- capture-year counts: `gsv_capture_year_distribution.parquet`.

### Metadata Variables

| Variable | Description | Data type | Spatial meaning | Downstream use |
| --- | --- | --- | --- | --- |
| `point_id` | Deterministic sample-point identifier from the road sampler | integer | Identifies the sampled road point | Joins metadata back to sample table |
| `grid_id` | 500 m grid cell assigned after sampling | integer | Spatial aggregation unit | Grid-level coverage and later fusion |
| `source_lon` | Sample point longitude | float | Query coordinate in EPSG:4326 | Metadata request coordinate; distance calculation |
| `source_lat` | Sample point latitude | float | Query coordinate in EPSG:4326 | Metadata request coordinate; distance calculation |
| `highway_class` | OSM road class at sampled point | string | Road-network context | Bias diagnostics and stratified analysis |
| `sampled_rank` | Numeric road hierarchy rank | integer | Encoded class hierarchy | Retained for modeling and diagnostics |
| `status` | Google metadata response status | string | Availability indicator | Filters valid imagery (`OK`) vs missing imagery (`ZERO_RESULTS`) |
| `pano_id` | Google panorama identifier | string or null | Stable panorama-level key | Image cache key, crop filename stem, duplication analysis |
| `pano_lat` | Returned panorama latitude | float or null | Actual panorama location | Offset and spatial QA |
| `pano_lon` | Returned panorama longitude | float or null | Actual panorama location | Offset and spatial QA |
| `capture_date` | Date string returned by metadata | string or null | Temporal metadata for imagery | Time-period diagnostics |
| `capture_year` | Parsed year from `capture_date` | integer or null | Temporal metadata | Capture-year distribution |
| `copyright` | Copyright string from API | string or null | Non-spatial provenance | Metadata preservation |
| `point_to_pano_distance_m` | Haversine distance between query point and panorama location | float or null | Query-to-imagery spatial offset | Spatial quality control |
| `retrieval_timestamp` | UTC timestamp when the row was generated | string | Audit time, not spatial | Reproducibility and provenance |
| `http_status_code` | HTTP status for metadata request | integer or null | Request diagnostic | Error auditing |
| `content_type` | Response content type | string or null | Request diagnostic | Detects non-JSON responses |
| `metadata_url_without_key` | Reconstructed request URL excluding API key | string | Query coordinate audit | Reproducible request trace |
| `error_message` | Error detail when present | string or null | Request diagnostic | Failure review |
| `raw_metadata_json` | Full metadata response serialized as JSON | string | Full provenance | Future re-parsing without rerunning requests |

### Heading, Yaw, and Pitch

The current metadata pilot does not collect a road-facing heading, camera yaw, or camera pitch from the metadata endpoint. The Google metadata endpoint used here returns panorama identity, location, status, date, and copyright, but not the viewing orientation needed to align crops with road direction. Directional crops therefore use fixed panorama-coordinate headings rather than road-bearing-aware headings.

This is an important methodological limitation. The current labels `front`, `right`, `rear`, and `left` mean fixed equirectangular headings of 0, 90, 180, and 270 degrees within the panorama coordinate system, not necessarily forward/right/rear/left relative to vehicle travel direction or sampled road bearing.

## 4. Street View Image Acquisition

### One-Point Prototype

`tests/test_obtain_gsv_one.py` validates the end-to-end image path on the first sampled point. It can either call the official metadata endpoint with `GOOGLE_MAPS_API_KEY` or bypass metadata with `GSV_PANO_ID` for panorama-stage debugging. The cached one-point output currently records `point_id = 1`, `grid_id = 958`, `pano_id = z_3m1MPKrsDvaRndk5YKlQ`, and a zero-meter point-to-panorama distance because the stored debug record used the sample coordinates as the panorama coordinates.

The one-point script tries multiple tile endpoints (`geo_cpk`, `streetviewpixels`, and `cbk`) and zoom candidates beginning at `GSV_PANORAMA_ZOOM` and falling back to 2 and 1. It logs non-image tile responses and writes sidecar `.json` and `.body` files when endpoints return HTTP errors or non-image content.

### 100-Panorama Benchmark

The current benchmark workflow is implemented in `tests/test_obtain_gsv_100.py`. It consumes the metadata pilot output and selects the first 100 unique rows with `status == "OK"` and non-empty `pano_id`. The benchmark has two modes:

- normal acquisition mode: download missing panoramas by stitched tiles;
- cached mode (`GSV_EXISTING_PANOS_ONLY=true`): reuse existing panorama JPGs and regenerate/validate crops without network downloads.

The available manifest shows the current benchmark was run in cached mode: all 100 benchmark panoramas were reused from local files, all generated crops succeeded, and `zoom_used` is null because no new tile download occurred during that run.

### Panorama Downloading

The benchmark tile downloader uses the `geo0.ggpht.com/cbk` tile endpoint. For a zoom level `z`, tile dimensions are:

- horizontal tile count: `2^z`;
- vertical tile count: `2^(z - 1)`;
- tile size: 512 x 512 pixels.

The cached benchmark panoramas are 2048 x 1024 pixels, consistent with zoom level 2. Downloaded panoramas are saved as JPEG with quality 95 under:

```text
fusedata/streetview/panoramas/raw/{pano_id}.jpg
```

The implementation validates cached or downloaded panoramas by checking file existence, minimum byte size, and PIL image validity. If the metadata `pano_id` cannot be downloaded from the tile endpoint, the script attempts to use the optional `streetview` Python package to search nearby panoramas and select the nearest tile-compatible alternate. The manifest distinguishes the original `pano_id` from `acquisition_pano_id` for this reason.

### Directional Crop Generation

Each panorama is converted into four square crops:

| Label | Heading in panorama coordinates | Output path |
| --- | ---: | --- |
| `front` | 0 degrees | `streetview/crops/front/{pano_id}_front.jpg` |
| `right` | 90 degrees | `streetview/crops/right/{pano_id}_right.jpg` |
| `rear` | 180 degrees | `streetview/crops/rear/{pano_id}_rear.jpg` |
| `left` | 270 degrees | `streetview/crops/left/{pano_id}_left.jpg` |

The benchmark uses `py360convert.e2p()` to project from the equirectangular panorama to a perspective view. Current crop parameters are:

- output size: 512 x 512 pixels;
- horizontal and vertical field of view: 90 degrees;
- pitch: 15 degrees in the 100-panorama benchmark;
- JPEG quality: 92.

The one-point prototype also generates four 512 x 512 crops, but its current `py360convert` call uses pitch 0 degrees. This discrepancy should be resolved before scaling so crop semantics are consistent.

Example documentation images are available in `docs/assets/`:

![Raw Street View panorama](assets/streetview_panorama_example.jpg)

| Front | Left | Rear | Right |
| --- | --- | --- | --- |
| ![Front crop](assets/streetview_crop_front.jpg) | ![Left crop](assets/streetview_crop_left.jpg) | ![Rear crop](assets/streetview_crop_rear.jpg) | ![Right crop](assets/streetview_crop_right.jpg) |

### Duplicate Handling and Naming

The metadata pilot computes panorama duplication by counting `pano_id` values. In the current 1,000-point pilot, all 928 successful metadata responses have unique panorama IDs; the reuse ratio is 0.0. The image benchmark also deduplicates before acquisition by selecting unique `pano_id` values. This avoids downloading the same panorama multiple times when multiple sample points map to the same image.

Filename conventions are deliberately panorama-centered:

- raw panorama: `{pano_id}.jpg`;
- crop: `{pano_id}_{direction}.jpg`;
- debug contact sheet: `{pano_id}_projection_validation.jpg`;
- one-point contact sheet: `{pano_id}_contact_sheet.jpg`.

This convention preserves a stable link between metadata rows, image files, and later visual embeddings.

## 5. Metadata Distribution and Diagnostics

### Metadata Pilot Summary

The current metadata pilot covers the first 1,000 road sample points.

| Metric | Value |
| --- | ---: |
| Total queried points | 1,000 |
| Metadata successes (`OK`) | 928 |
| Metadata failures / no imagery | 72 |
| Missing panorama fraction | 0.072 |
| Unique panorama IDs | 928 |
| Panorama reuse ratio | 0.000 |
| Mean sample-to-panorama distance | 9.26 m |
| Median sample-to-panorama distance | 5.01 m |
| 95th percentile sample-to-panorama distance | 35.75 m |
| Maximum sample-to-panorama distance | 115.25 m |

The metadata log shows an initial failed run without `GOOGLE_MAPS_API_KEY`, followed by a successful 1,000-point run on 2026-05-18. Progress logging occurred every 50 points, ending with 928 successes and 72 failures.

### Status by Road Class

| Highway class | OK | ZERO_RESULTS |
| --- | ---: | ---: |
| living_street | 11 | 1 |
| motorway | 7 | 1 |
| primary | 81 | 0 |
| residential | 474 | 17 |
| secondary | 82 | 0 |
| service | 196 | 51 |
| tertiary | 56 | 2 |
| trunk | 19 | 0 |
| unclassified | 2 | 0 |

The largest source of missing imagery is the `service` class. This may reflect private roads, alleys, internal roads, or mapped service links with weaker Street View coverage. This is a potential sampling bias if the final image dataset overrepresents roads with public vehicle-accessible imagery.

### Capture-Year Distribution

| Capture year | Count |
| --- | ---: |
| 2009 | 43 |
| 2010 | 10 |
| 2013 | 1 |
| 2014 | 27 |
| 2015 | 84 |
| 2016 | 1 |
| 2017 | 7 |
| 2018 | 720 |
| 2019 | 6 |
| 2020 | 12 |
| 2021 | 11 |
| 2022 | 5 |
| 2025 | 1 |

The pilot is temporally concentrated in 2018: 720 of 928 successful metadata rows have capture year 2018. This is likely a major temporal bias for any downstream urban representation model unless explicitly modeled, filtered, or balanced.

### Image Cache and Crop Diagnostics

Current local image inventory:

| Artifact | Count | Dimensions | Total size | Mean size |
| --- | ---: | --- | ---: | ---: |
| Raw panoramas | 101 | 2048 x 1024 | 51.9 MB | 513 KB |
| Front crops | 101 | 512 x 512 | 8.1 MB | 80 KB |
| Right crops | 101 | 512 x 512 | 8.1 MB | 80 KB |
| Rear crops | 101 | 512 x 512 | 7.6 MB | 75 KB |
| Left crops | 101 | 512 x 512 | 7.8 MB | 77 KB |
| Projection debug sheets | 100 | 1024 x 1536 | 43.7 MB | 437 KB |
| One-point preview sheet | 1 | 1024 x 1024 | 0.23 MB | 226 KB |

The benchmark manifest contains 100 rows. All 100 benchmark panoramas have `download_success = TRUE`, `crops_generated = TRUE`, `download_skipped = TRUE`, and `retry_count = 0`. The extra cached panorama and four extra crops come from the separate one-point prototype.

The benchmark manifest also records two simple crop diagnostics:

- `crop_distinctness_score`: minimum mean absolute pixel difference among pairs of the four directional crops after resizing to 128 x 128;
- `rear_edge_discontinuity_score`: mean absolute difference between the left and right edges of the rear crop.

Current benchmark values:

| Diagnostic | Min | Mean | Median | Max |
| --- | ---: | ---: | ---: | ---: |
| Crop distinctness score | 3.66 | 36.85 | 36.41 | 57.94 |
| Rear edge discontinuity score | 4.46 | 43.16 | 42.23 | 78.34 |

These diagnostics are not formal image-quality metrics, but they are useful smoke tests. Very low crop distinctness may indicate projection errors, duplicated views, or visually homogeneous scenes.

### Heading and Spatial Coverage Diagnostics

The current outputs do not contain camera heading distributions or road-bearing-aligned view directions. The only directional information is the fixed crop heading used during projection. Therefore, heading distributions cannot be analyzed from current metadata. Future versions should compute road bearing at each sample point and store intended camera headings if road-relative views are required.

Spatially, the available metadata pilot covers only the first 1,000 rows of the 40,000-point sample, not a stratified or randomized subset. Because `point_id` order is determined after the seeded thinning order, this is reproducible, but it should not automatically be treated as a spatially balanced 1,000-point survey without checking the map distribution.

## 6. Reproducibility and Computational Design

### Path Management

Path handling is centralized after the data-root migration:

- `config/paths.yml` documents the path contract;
- `config/paths.R` exposes R helpers such as `fuse_file()` and `fuse_dir()`;
- `src/fuse_paths.py` exposes Python `pathlib` helpers such as `data_file()` and `data_dir()`.

The resolution order is:

1. `FUSE_DATA_ROOT`, if set;
2. sibling `../fusedata`, if present;
3. legacy `./data`, if present;
4. create/use sibling `../fusedata`.

This avoids hardcoded machine-specific absolute paths while preserving compatibility with existing local data.

### Parallelization

The road sampling candidate generation can use `future.mirai` workers (`SEOUL_CANDIDATE_WORKERS`, default 40) and chunked road features (`SEOUL_CANDIDATE_CHUNK_SIZE`, default 2,000). The 100-panorama benchmark uses a Python `ThreadPoolExecutor` (`GSV_BENCHMARK_WORKERS`, default 6) because tile downloads and image I/O are network- and I/O-bound.

### Caching and Checkpointing

The current design uses file-level caching rather than a database-backed checkpoint system:

- road archives and sample parquet are reusable outputs;
- production metadata acceptance writes append-safe checkpoint, accepted, rejected, and summary parquet files;
- raw panoramas are reused if valid and above `GSV_MIN_VALID_PANO_BYTES`;
- crops are reused unless `GSV_OVERWRITE_CROPS=true`;
- `GSV_EXISTING_PANOS_ONLY=true` supports crop regeneration without network downloads;
- manifests record benchmark and production outcomes with basic diagnostics.

The production Street View scripts now provide resumable metadata checkpoints, pano-id deduplication, image manifests, and final validation. Full acquisition still requires deliberate quota and storage planning before launch.

### Safe and Expensive Stages

| Stage | Script | Safe to rerun? | Cost profile |
| --- | --- | --- | --- |
| Path validation | `scripts/validation/validate_paths.R`, `scripts/validation/validate_paths.py` | Yes | Lightweight |
| Synthetic road sampling test | `tests/test_road_environment_sampling.R` | Yes | Lightweight |
| Leaflet rerender | `scripts/visualization/render_leaflet_global.R` | Usually | Moderate; no OSM or GSV requests |
| Metadata pilot | `tests/test_gsv_metadata_pilot.py` | With care | API requests, quota use |
| One-point image prototype | `tests/test_obtain_gsv_one.py` | With care | API/tile requests unless using cache/debug override |
| Existing-panorama crop regeneration | `tests/test_obtain_gsv_100.py` with `GSV_EXISTING_PANOS_ONLY=true` | Yes | Local CPU/I/O |
| 100-panorama acquisition | `tests/test_obtain_gsv_100.py` | With care | Network requests, tile endpoint fragility |
| Full road sampling | `scripts/streetview/10_run_road_network_sampling_global.R` | No, unless intentional | Expensive OSM/sampling/map workflow |
| GSV candidate pool | `scripts/streetview/20_build_gsv_candidate_pool.R` | With care | CPU/I/O; no Google requests |
| GSV metadata acceptance | `scripts/streetview/30_run_gsv_metadata_acceptance.py` | Resumable | Google API requests and quota use |
| GSV image materialization | `scripts/streetview/40_materialize_gsv_images.py` | Resumable with cache | Network, image I/O, storage |
| GSV finalization | `scripts/streetview/50_finalize_gsv_dataset.py` | Yes | Lightweight manifest build |
| GSV final validation | `scripts/streetview/60_validate_gsv_final_dataset.py` | Yes | Lightweight unless requiring image manifest checks |

## 7. File and Script Inventory

| File | Role | Importance |
| --- | --- | --- |
| `R/road_environment_sampling.R` | Builds grid, constructs road network, generates candidates, thins samples, assigns grid IDs, writes diagnostics | Core spatial sampling methodology |
| `scripts/streetview/10_run_road_network_sampling_global.R` | End-to-end road sampling driver and environment-variable interface | Produces the 40,000-point sample used by Street View |
| `scripts/streetview/20_build_gsv_candidate_pool.R` | Builds the oversampled candidate pool from the operational road network | Metadata-aware sampling input |
| `scripts/streetview/30_run_gsv_metadata_acceptance.py` | Queries Street View metadata, applies strict filters, and deduplicates `pano_id` | Production metadata acceptance |
| `scripts/streetview/40_materialize_gsv_images.py` | Downloads accepted panoramas and generates standardized crops | Production image materialization |
| `scripts/streetview/50_finalize_gsv_dataset.py` | Selects the exact final valid image-backed manifest | Final dataset contract |
| `scripts/streetview/60_validate_gsv_final_dataset.py` | Validates final metadata and optional image success | Final QA |
| `tests/test_gsv_metadata_pilot.py` | Metadata-only Street View pilot for sampled road points | Core metadata and availability audit |
| `tests/test_obtain_gsv_one.py` | One-point end-to-end panorama and crop prototype | Validates image acquisition mechanics |
| `tests/test_obtain_gsv_100.py` | 100-panorama benchmark, crop generation, manifest writing | Core current image workflow |
| `src/fuse_paths.py` | Python data-root and path helper | Reproducibility infrastructure |
| `config/paths.R` | R data-root and path helper | Reproducibility infrastructure |
| `config/paths.yml` | Human-readable path contract | Configuration documentation |
| `scripts/validation/validate_paths.py` / `scripts/validation/validate_paths.R` | Directory, write-permission, and expected-file checks | Lightweight reproducibility checks |
| `docs/assets/streetview_*.jpg` | Example panorama, crops, and debug contact sheet | Collaboration and reporting assets |
| `fusedata/streetview/metadata/*.parquet` | Metadata outputs and summaries | Empirical diagnostics |
| `fusedata/streetview/manifests/gsv_download_manifest_100.parquet` | Benchmark image acquisition manifest | Image workflow audit trail |
| `fusedata/streetview/logs/*.log` | Runtime logs for metadata and image acquisition | Failure and progress audit |

## 8. Future Scaling Considerations

Scaling from 100 panoramas to tens of thousands should use the numbered production scripts rather than increasing `GSV_BENCHMARK_N_PANOS`.

First, acquisition should remain explicitly batch-based. The production metadata checkpoint and image manifest track candidate IDs, `pano_id`, request status, file validation status, crop status, and failure class. Future improvements may move this from parquet files to a small task database if concurrent operators need stronger locking.

Second, storage should be planned around both panorama and crop artifacts. The current mean raw panorama size is about 513 KB and the four crops together average about 313 KB per panorama. At 40,000 unique panoramas, this implies roughly 20.5 GB for raw panoramas and 12.5 GB for four crops, before debug sheets, embeddings, and metadata. Debug sheets should probably be sampled rather than written for every panorama at scale.

Third, duplicate panorama management now happens before image acquisition. The current pilot had no duplication among 928 successes, but denser future samples may produce repeated `pano_id` values. A normalized design should continue to separate point-level metadata from panorama-level image assets:

- point table: `point_id`, sample attributes, query coordinates, returned `pano_id`;
- panorama table: `pano_id`, panorama coordinates, capture date, acquisition status, raw image path;
- crop table: `pano_id`, direction, heading, pitch, crop path, validation metrics;
- embedding table: `pano_id`, direction, model name, embedding path or vector ID.

Fourth, directional crop semantics need clarification. If the research question requires road-facing views, the pipeline should compute road bearing at each sample point and derive headings relative to that bearing. If the research question treats panoramas as unordered local visual context, fixed panorama-coordinate crops may be acceptable, but the document and downstream model naming should avoid implying travel-direction alignment.

Fifth, image preprocessing and embedding extraction should be separated from acquisition. Cached crops can be fed into a GPU workflow for CLIP/DINO/vision-transformer embeddings, with parquet metadata linking embeddings back to `pano_id`, direction, crop parameters, and model version.

Finally, future graph integration should treat the sample points as road-network observations. Potential graph keys include `source_road_id`, `grid_id`, `pano_id`, OSM POI neighborhoods, and adjacency along road segments. This would allow Street View imagery, OSM semantics, and spatial context to be fused without losing the sampling design.

## Current System Status

The current system has a reproducible Seoul-scale road sample, prototype Street View tests, and a production-oriented Street View acquisition architecture. The production scripts are organized under `scripts/streetview/` and implement candidate oversampling, metadata acceptance, pano-id deduplication, image materialization, final manifest creation, and validation.

The full 40,000-image acquisition has not been launched. The existing code is suitable for methodology validation, small pilot runs, crop QA, and deliberate production acquisition when quota and storage are available.

## Technical Debt

- The first 1,000 metadata queries are reproducible but not explicitly stratified by grid, road class, or geography.
- Direction labels are fixed panorama-coordinate headings, not road-relative headings.
- The one-point prototype uses pitch 0 degrees while the 100-panorama benchmark uses pitch 15 degrees.
- Logs and older manifests may contain legacy `data/` paths from before the `fusedata` migration.
- Metadata and image acquisition are checkpointed in parquet, but not yet backed by a transactional task database.
- Tile acquisition uses unofficial or implementation-specific tile endpoints for panoramas; these endpoints may change or reject requests.
- Debug sheets are useful but storage-heavy if produced for every panorama.

## Recommended Next Improvements

1. Add a normalized panorama-level metadata table separate from point-level metadata.
2. Add road-bearing calculation and store intended crop headings if direction-relative visual analysis is required.
3. Add stronger quota/rate-limit controls before scaling metadata or tile requests.
4. Add spatial diagnostics for accepted/rejected production metadata, including maps of rejection class and capture-year geography.
5. Add image-quality filters for corrupt, blank, overly dark, or low-distinctness crops.
6. Prepare an embedding pipeline that records model name, preprocessing version, crop parameters, and output vector location.

## Reproducibility Risks to Monitor

- Changes in Google Street View metadata responses, status codes, or tile endpoint behavior.
- Loss of `pano_id` compatibility between official metadata and tile acquisition endpoints.
- Accidental changes to `SEOUL_SAMPLE_SEED`, candidate spacing, minimum spacing, road filters, or tunnel handling.
- Inconsistent data roots across machines if `FUSE_DATA_ROOT` is not documented for collaborators.
- Temporal bias from the strong concentration of available imagery in 2018.
- Spatial bias from missing imagery on service roads and from using the first 1,000 sample rows for the pilot.
- Ambiguity in crop direction labels until road-relative heading is implemented.
