# Korea Geo2Vec Large-Scale Pipeline 1M Report

Generated: `2026-06-08 KST`

## Summary

The directory reorganization succeeded, and the 1M engineering stress test succeeded. Future nationwide Geo2Vec outputs are now separated from `gwanak_test` under:

`/members/dhnyu/fusedata/geo2vec_large_scale/`

The 1M run used deterministic 8-worker CPU SDF sampling, validated the disk-backed sample cache, passed a 60-shard overlap checksum check against the copied 300k cache, trained one persistent global `Geo2Vec_Model(n_poly=1000000)` with one global embedding table, retained only the latest 3 checkpoints, passed a no-op resume smoke test without overwriting `training_summary.json`, and exported 1,000,000 finite 32D embeddings.

No 5M or full Korea training was run.

## Reorganization

New output root:

`/members/dhnyu/fusedata/geo2vec_large_scale/`

Subdirectories:

- `id_maps/`
- `sample_caches/`
- `training_runs/`
- `embeddings/`
- `reports/`
- `metadata/`
- `logs/`

The existing 50k, 100k, and 300k nationwide prototype outputs were copied from:

`/members/dhnyu/fusedata/gwanak_test/validation/`

to the new root. The old `gwanak_test` outputs were left in place as legacy copies.

Reorganization manifest:

`/members/dhnyu/fusedata/geo2vec_large_scale/metadata/geo2vec_large_scale_reorganization_manifest.json`

Reorganization report:

`/members/dhnyu/fusedata/geo2vec_large_scale/reports/geo2vec_large_scale_reorganization_report.md`

Validation:

- All expected source paths were found.
- All destination paths exist.
- Source and destination sizes match.
- File checksums match where computed.
- Id-map parquet row counts were recorded.
- No files were deleted from `gwanak_test`.

## Code Hardening

Code remains under:

`/members/dhnyu/fuse/tests/geo2vec_large_scale/`

Changes before 1M:

- Central output paths were added in `geo2vec_large_scale_common.py`.
- Future defaults now use `/members/dhnyu/fusedata/geo2vec_large_scale/`.
- Trainer refuses to start if sample manifests are incomplete, failed, missing, or internally inconsistent.
- Added `check_sample_cache_overlap.py`.
- Monitor reports checkpoint retention policy.
- No-op resume smoke tests write `resume_smoke_summary.json` and do not overwrite `training_summary.json`.

## 1M Settings

- Buildings: `1,000,000`
- `Geo_dim`: `32`
- Batch size: `4096`
- Hidden size: `128`
- Num layers: `4`
- Num freqs: `4`
- `samples_per_unit`: `4`
- `point_sample`: `1`
- `uniform_grid`: `2`
- Validation ratio: `0.1`
- Base seed: `20260608`
- Sample config version: `sdf_proto_v1`
- SDF workers: `8`
- Buildings per shard: `5,000`
- Checkpoint frequency: every `1000` steps
- Checkpoint retention: latest `3`

## Id Map

Output:

`/members/dhnyu/fusedata/geo2vec_large_scale/id_maps/korea_buildings_geo2vec_global_id_map_1000k.parquet`

Metadata:

`/members/dhnyu/fusedata/geo2vec_large_scale/id_maps/korea_buildings_geo2vec_global_id_map_1000k_metadata.json`

Result:

- Rows: `1,000,000`
- Internal ids: contiguous `0..999,999`
- Missing `building_id`: `0`
- Duplicate `building_id`: `0`
- Build time: `24.60 s`
- Deterministic ordering: `building_id` ascending

## SDF Cache

Output:

`/members/dhnyu/fusedata/geo2vec_large_scale/sample_caches/korea_geo2vec_sdf_samples_1000k_sdf_proto_v1/`

Manifest:

`/members/dhnyu/fusedata/geo2vec_large_scale/sample_caches/korea_geo2vec_sdf_samples_1000k_sdf_proto_v1/manifest.json`

Results:

- Shards: `200`
- Buildings: `1,000,000`
- Total samples: `24,044,361`
- Cache bytes: `352,859,575`, about `336.51 MiB`
- Generation time: `255.73 s`
- Overall throughput: `94,023 samples/sec`
- Worker count: `8`
- CPU RSS after generation: about `1161 MB`
- Peak maxrss: about `1218 MB`
- Failed/invalid building count: `0`

Cache validation:

- Valid: `true`
- Total rows: `24,044,361`
- Train rows: `21,640,329`
- Validation rows: `2,404,032`
- Observed validation ratio: `0.09998`
- Buildings with samples: `1,000,000`
- Missing building count: `0`
- Sample count median per building: `22`
- Sample count range per building: `17..1208`
- Required columns/dtypes, finite values, and checksums passed.

## Overlap Check

Overlap audit:

`/members/dhnyu/fusedata/geo2vec_large_scale/metadata/sample_cache_overlap_300k_vs_1m_60_shards.json`

Result:

- Compared first `60` overlapping shards against the copied 300k cache.
- All shard checksums matched.
- All shard row counts matched.

Deterministic parallel SDF sampling remained stable.

## SDF Throughput Scaling

| Stage | Workers | Buildings | Samples | Time | Samples/sec | Cache size |
|---:|---:|---:|---:|---:|---:|---:|
| 100k | 8 | 100,000 | 2,408,418 | 25.54 s | 94,296 | 33.72 MiB |
| 300k | 8 | 300,000 | 7,220,527 | 75.17 s | 96,058 | 101.06 MiB |
| 1M | 8 | 1,000,000 | 24,044,361 | 255.73 s | 94,023 | 336.51 MiB |

The 1M SDF throughput scaled consistently from 300k. CPU-side SDF generation remains the main bottleneck in the pipeline, although the 8-worker implementation is stable.

## Global Training

Run directory:

`/members/dhnyu/fusedata/geo2vec_large_scale/training_runs/korea_geo2vec_global_train_1000k_sdf_proto_v1_32d/`

Training used one global model:

- `Geo2Vec_Model(n_poly=1000000, z_size=32, hidden_size=128, num_layers=4, num_freqs=4)`
- One optimizer.
- One global embedding table.
- All 200 sample shards updated the same model.
- No separate shard models were trained.

Training metrics:

- Device: CUDA
- Epochs: `1`
- Global steps: `5,400`
- Training samples seen: `21,640,329`
- Validation rows evaluated: `2,404,032`
- Last validation L1: `0.03554`
- Metrics rows: `200`
- Sum of shard timing: `34.15 s`
- Training summary elapsed time: `36.69 s`
- Mean training throughput: about `652,779 samples/sec`
- Median training throughput: about `665,202 samples/sec`
- Max CPU RSS in metrics: about `1330 MB`
- Max peak maxrss in metrics: about `1442 MB`
- Max GPU allocated in metrics: about `507 MB`
- Max GPU reserved in metrics: about `700 MB`
- Training summary peak GPU allocated: about `632 MB`

GPU VRAM was not a bottleneck.

## Checkpointing

Checkpoint retention worked. Only the latest 3 checkpoints remain:

- `checkpoint_step_00004000.pt`
- `checkpoint_step_00005000.pt`
- `checkpoint_step_00005400.pt`

Each checkpoint is about `368.33 MiB`. Run directory size is about `1105.06 MiB`.

Monitor output:

`/members/dhnyu/fusedata/geo2vec_large_scale/training_runs/korea_geo2vec_global_train_1000k_sdf_proto_v1_32d/monitor_status.json`

Monitor records `checkpoint_retention_keep = 3`.

## Resume Smoke Test

Resume smoke summary:

`/members/dhnyu/fusedata/geo2vec_large_scale/training_runs/korea_geo2vec_global_train_1000k_sdf_proto_v1_32d/resume_smoke_summary.json`

Result:

- Loaded checkpoint `checkpoint_step_00005400.pt`.
- Id-map checksum matched.
- Sample-manifest checksum matched.
- Model state loaded.
- Optimizer state loaded.
- RNG states restored.
- `training_steps_this_invocation = 0`.
- `samples_seen_this_invocation = 0`.
- `training_summary.json` timestamp and size were unchanged.
- No-op resume did not overwrite the main training summary.

Resume smoke test passed.

## Embedding Export

Output:

`/members/dhnyu/fusedata/geo2vec_large_scale/embeddings/korea_geo2vec_global_train_1000k_sdf_proto_v1_32d_embeddings/`

Result:

- Rows: `1,000,000`
- Expected rows: `1,000,000`
- Geo_dim: `32`
- Parts: `100`
- Finite values: passed
- Row count validation: passed
- `building_id` joined through the id map.
- Output size: about `178.21 MiB`
- Export time: `2.05 s`

## Did 1M Succeed?

Yes. The 1M engineering stress test succeeded.

The strongest evidence:

- New output root is active and separated from `gwanak_test`.
- 1M id map is valid and contiguous.
- 1M SDF cache is complete and valid.
- 60-shard overlap checksum check against 300k passed.
- One global model and one global embedding table trained across all shards.
- GPU memory use remained far below A6000 capacity.
- Checkpoint retention worked.
- Resume smoke test worked without overwriting `training_summary.json`.
- 1M embeddings exported incrementally and validated.

## Is It Safe To Proceed To 5M?

Yes, but as another engineering stress test with conservative settings. The 1M stage shows the architecture is stable at this scale. The next risks are longer sampling time, larger checkpoint size, and larger retained run directories rather than GPU VRAM.

## Recommended 5M Settings

Use the same model and sample density:

- Buildings: `5,000,000`
- `Geo_dim`: `32`
- Batch size: `4096`
- Hidden size: `128`
- Num layers: `4`
- Num freqs: `4`
- `samples_per_unit`: `4`
- `point_sample`: `1`
- `uniform_grid`: `2`
- Validation ratio: `0.1`
- Base seed: `20260608`
- Sample config version: `sdf_proto_v1`
- SDF workers: start with `8`
- Buildings per shard: `5,000`
- Checkpoint every `2500` or `5000` steps
- Keep latest `3` checkpoints
- Run normal checkpoint resume smoke test after completion
- Run overlap checksum check against the first 200 shards of the 1M cache

Do not increase sample density for 5M. Do not increase workers beyond 8 unless a separate bounded shard-group test shows stable memory and higher throughput.

## Must Fix Before 5M

1. Add checkpoint write timing to training metrics, because 5M optimizer checkpoints will be materially larger.
2. Add optional checkpoint retention cleanup before training starts, so stale checkpoints from failed attempts do not accumulate.
3. Add shard-level cache validation summaries to monitor output.
4. Add a standard deterministic overlap check command to the stage runner/reporting checklist.
5. Consider writing training logs under `logs/` in addition to JSONL metrics in the run directory.

These are workflow hardening tasks. They do not change the core one-global-model design.
