# Korea Geo2Vec Large-Scale Pipeline 100k Report

Generated: `2026-06-08 KST`

## Summary

The 100k prototype succeeded. It used deterministic parallel SDF sampling with 8 CPU workers, validated the disk-backed sample cache, trained one persistent global `Geo2Vec_Model(n_poly=100000)` with one global embedding table, passed a true mid-shard interruption/resume test, exported 100,000 embeddings incrementally, and produced monitoring outputs.

No 300k, 1M, 5M, or full Korea training was run.

## Code Review

All files in `/members/dhnyu/fuse/tests/geo2vec_large_scale/` passed `py_compile`.

CUDA-synchronized timing is active in `train_global_geo2vec_from_sample_cache.py` via `synchronize_if_cuda()` around shard timing. The 100k run used distinct `100k` paths and did not overwrite 50k outputs.

## Parallel SDF Sampling

Updated sampler:

`/members/dhnyu/fuse/tests/geo2vec_large_scale/generate_disk_backed_sdf_samples.py`

Changes:

- Added `--workers`.
- Uses `ProcessPoolExecutor` with deterministic per-building seeds.
- Does not use Python `hash()`.
- Collects worker results in arbitrary completion order but sorts by `geo2vec_internal_id` before writing.
- Writes each shard atomically with `.tmp` then rename.
- Records worker count, shard elapsed time, samples/sec, buildings/sec, CPU RSS, maxrss, shard bytes, checksum, and invalid/failed building counts.
- Resume skips already completed shards.

Determinism check:

- The first 10 shards of the 100k cache were compared against the prior 50k cache.
- All 10 overlapping shard checksums matched exactly.
- This confirms that parallel output order did not change sample values for overlapping buildings.

## 100k Settings

- Buildings: `100,000`
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

## Id Map

Output:

`/members/dhnyu/fusedata/gwanak_test/validation/korea_buildings_geo2vec_global_id_map_100k.parquet`

Result:

- Rows: `100,000`
- Internal ids: contiguous `0..99,999`
- Missing `building_id`: `0`
- Duplicate `building_id`: `0`
- Build time: `24.38 s`

## Sample Cache Validation

Sample cache:

`/members/dhnyu/fusedata/gwanak_test/validation/korea_geo2vec_sdf_samples_100k_sdf_proto_v1/`

Manifest:

`/members/dhnyu/fusedata/gwanak_test/validation/korea_geo2vec_sdf_samples_100k_sdf_proto_v1/manifest.json`

Validation:

`/members/dhnyu/fusedata/gwanak_test/validation/korea_geo2vec_sdf_samples_100k_sdf_proto_v1/sample_cache_validation.json`

Results:

- Shards: `20`
- Buildings: `100,000`
- Total samples: `2,408,418`
- Train rows: `2,167,930`
- Validation rows: `240,488`
- Observed validation ratio: `0.09985`
- Buildings with samples: `100,000`
- Missing building count: `0`
- Sample count median per building: `22`
- Sample count range per building: `17..1208`
- Required columns and dtypes: passed
- Finite `x`, `y`, `sdf`: passed
- Checksum validation: passed
- Cache size: `35,354,412` bytes, about `33.72 MiB`

## SDF Sampling Throughput

50k single-process baseline:

- Samples: `1,202,704`
- Time: `45.88 s`
- Throughput: `26,216 samples/sec`
- Cache size: about `16.83 MiB`

100k 8-worker run:

- Samples: `2,408,418`
- Time: `25.54 s`
- Throughput: `94,296 samples/sec`
- Cache size: about `33.72 MiB`

The 8-worker 100k run generated about `2.0x` the samples in about `0.56x` the wall time of the 50k single-process run. Throughput improved by about `3.6x`. CPU sampling is still the main engineering bottleneck because it dominates wall time relative to validation, training, and export at this prototype scale.

## Global Training

Run directory:

`/members/dhnyu/fusedata/gwanak_test/validation/korea_geo2vec_global_train_100k_sdf_proto_v1_32d_resume_audit/`

Training used one global model:

- `Geo2Vec_Model(n_poly=100000, z_size=32, hidden_size=128, num_layers=4, num_freqs=4)`
- One optimizer over the same model parameters.
- All sample shards updated the same model and same global embedding table.
- No separate shard models were trained.

Training result:

- Device: CUDA
- Epochs: `1`
- Global steps: `540`
- Training samples seen: `2,167,930`
- Latest validation L1: `0.03969`
- Latest checkpoint: `checkpoint_step_00000540.pt`
- Latest checkpoint size: about `38.74 MiB`
- Run directory size: about `309.91 MiB`
- Max CPU RSS in monitor: about `1351.68 MB`
- Peak GPU allocated in final summary: about `120.95 MB`
- Max GPU reserved: about `156 MB`

GPU VRAM was not a bottleneck.

CUDA-synchronized shard timing was active. The reported mean training throughput was about `1.49M train samples/sec`. This is credible for the small model and 100k cache, but it should be remeasured at 300k because checkpoint cadence, cache read patterns, and DataFrame conversion overhead may become more visible.

## Mid-Shard Resume Test

Controlled stop:

`/members/dhnyu/fusedata/gwanak_test/validation/korea_geo2vec_global_train_100k_sdf_proto_v1_32d_resume_audit/controlled_stop_audit.json`

Resume audit:

`/members/dhnyu/fusedata/gwanak_test/validation/korea_geo2vec_global_train_100k_sdf_proto_v1_32d_resume_audit/resume_audit.json`

Test design:

- Training started from the 100k cache.
- It stopped after `15` optimizer steps.
- Stop point was inside shard `0`, at `current_sample_offset = 61,440`.
- Resume loaded the latest checkpoint and continued to completion.

Verified:

- Id-map checksum matched.
- Sample-manifest checksum matched.
- Model state loaded.
- Optimizer state loaded.
- RNG states restored.
- Training continued without restarting from zero.
- Final checkpoint was produced.

Result: mid-shard resume worked.

## Embedding Export

Output:

`/members/dhnyu/fusedata/gwanak_test/validation/korea_geo2vec_global_train_100k_sdf_proto_v1_32d_resume_audit_embeddings/`

Result:

- Rows: `100,000`
- Expected rows: `100,000`
- Geo_dim: `32`
- Parts: `10`
- Finite values: passed
- Row count validation: passed
- `building_id` joined through the id map.
- Output size: about `17.85 MiB`
- Export time: about `0.21 s`

## Monitoring

Monitor output:

- `monitor_status.json`
- `monitor_status.md`

Key monitor values:

- Metrics rows: `20`
- Checkpoints: `8`
- Latest checkpoint size: about `38.74 MiB`
- Mean training samples/sec: about `1.49M`
- Max CPU RSS: about `1351.68 MB`
- Max GPU allocated in per-shard metrics: about `80.76 MB`
- Max GPU reserved: about `156 MB`
- Last validation L1: `0.03969`
- Sample cache size: about `33.72 MiB`
- Embedding output size: about `17.85 MiB`

## Is It Safe To Proceed To 300k?

Yes, with conservative settings. The 100k engineering prototype passed the required sample validation, deterministic parallel sampling check, one-global-model training requirement, mid-shard resume audit, and incremental export validation.

The main caution is checkpoint retention. The 100k resume-audit run kept 8 checkpoints and used about `310 MB` in the run directory. At 300k this is still manageable, but checkpoint retention should be configured intentionally before 1M+.

## Recommended 300k Settings

Use the same sample density and model size:

- Buildings: `300,000`
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
- SDF workers: start with `8`; only increase to `12` after one 300k shard group looks stable.
- Buildings per shard: `5,000` or `10,000`; keep `5,000` if prioritizing failure recovery granularity.
- Checkpoint every `250` or `500` steps for normal training.
- Keep latest `3` checkpoints, or manually clean older checkpoint files after confirming resume behavior.

Do not increase sample density for 300k. The next run should still be an engineering stability test, not a final representation-quality run.
