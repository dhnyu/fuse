# Korea Geo2Vec Large-Scale Pipeline 300k Report

Generated: `2026-06-08 KST`

## Summary

The 300k engineering stability test succeeded. It used deterministic 8-worker CPU SDF sampling, validated the disk-backed sample cache, trained one persistent global `Geo2Vec_Model(n_poly=300000)` with one global embedding table, retained only the latest 3 checkpoints, passed a normal-checkpoint resume smoke test, exported 300,000 finite 32D embeddings, and produced monitoring outputs.

No 1M, 5M, or full Korea training was run.

## Pre-Run Checks

All files under `/members/dhnyu/fuse/tests/geo2vec_large_scale/` passed `py_compile`.

The 300k outputs used distinct paths containing `300k`, so the existing 50k and 100k outputs were not overwritten.

Checkpoint retention was added to `train_global_geo2vec_from_sample_cache.py` using `--keep-checkpoints`. For this run, `--keep-checkpoints 3` was used.

## Settings

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
- SDF workers: `8`
- Buildings per shard: `5,000`
- Checkpoint frequency: every `500` steps
- Checkpoint retention: latest `3`

## Id Map

Output:

`/members/dhnyu/fusedata/gwanak_test/validation/korea_buildings_geo2vec_global_id_map_300k.parquet`

Result:

- Rows: `300,000`
- Internal ids: contiguous `0..299,999`
- Missing `building_id`: `0`
- Duplicate `building_id`: `0`
- Build time: `24.61 s`
- Deterministic ordering: `building_id` ascending

## SDF Cache

Output:

`/members/dhnyu/fusedata/gwanak_test/validation/korea_geo2vec_sdf_samples_300k_sdf_proto_v1/`

Manifest:

`/members/dhnyu/fusedata/gwanak_test/validation/korea_geo2vec_sdf_samples_300k_sdf_proto_v1/manifest.json`

Results:

- Shards: `60`
- Buildings: `300,000`
- Total samples: `7,220,527`
- Cache bytes: `105,964,501`, about `101.06 MiB`
- Generation time: `75.17 s`
- Overall throughput: `96,058 samples/sec`
- Worker count: `8`
- CPU RSS after generation: about `536 MB`
- Peak maxrss: about `532 MB`
- Failed building count: `0`
- Invalid building count: `0`

Shard-level summary:

- Mean shard time: `1.25 s`
- Mean shard throughput: `96,195 samples/sec`
- Median shard throughput: `96,661 samples/sec`
- Mean buildings/sec: `3,997`
- Sample rows per shard: about `119,350..121,820`
- No shard failures.

## Cache Validation

Validation output:

`/members/dhnyu/fusedata/gwanak_test/validation/korea_geo2vec_sdf_samples_300k_sdf_proto_v1/sample_cache_validation.json`

Validation passed:

- Total rows: `7,220,527`
- Train rows: `6,499,615`
- Validation rows: `720,912`
- Observed validation ratio: `0.09984`
- Buildings with samples: `300,000`
- Missing building count: `0`
- Sample count median per building: `22`
- Sample count range per building: `17..1208`
- Required columns and dtypes: passed
- Finite `x`, `y`, `sdf`: passed
- Shard checksums: passed

## SDF Throughput Scaling

| Stage | Workers | Buildings | Samples | Time | Samples/sec | Cache size |
|---:|---:|---:|---:|---:|---:|---:|
| 50k | 1 | 50,000 | 1,202,704 | 45.88 s | 26,216 | 16.83 MiB |
| 100k | 8 | 100,000 | 2,408,418 | 25.54 s | 94,296 | 33.72 MiB |
| 300k | 8 | 300,000 | 7,220,527 | 75.17 s | 96,058 | 101.06 MiB |

The 300k run scaled well from 100k: about 3.0x the samples in about 2.94x the time, with very similar samples/sec. Deterministic parallel SDF sampling remained stable.

CPU-side SDF sampling remains the main bottleneck. At 300k, id-map generation plus SDF sampling took about `100 s`, while cache validation, training, and export were much shorter.

## Global Training

Run directory:

`/members/dhnyu/fusedata/gwanak_test/validation/korea_geo2vec_global_train_300k_sdf_proto_v1_32d/`

Training used one global model:

- `Geo2Vec_Model(n_poly=300000, z_size=32, hidden_size=128, num_layers=4, num_freqs=4)`
- One optimizer.
- One global embedding table.
- All 60 sample shards updated the same model.
- No separate shard models were trained.

Training metrics:

- Device: CUDA
- Epochs: `1`
- Global steps: `1,620`
- Training samples seen: `6,499,615`
- Validation rows evaluated: `720,912`
- Last validation L1: `0.03606`
- Metrics rows: `60`
- Sum of shard timing: `5.36 s`
- Mean training throughput: `1.27M samples/sec`
- Median training throughput: `1.32M samples/sec`
- Max CPU RSS in metrics: about `1330 MB`
- Peak maxrss in metrics: about `1359 MB`
- Max GPU allocated in metrics: about `165.5 MB`
- Max GPU reserved in metrics: about `270 MB`

GPU VRAM was not a bottleneck.

Note: the later resume smoke test rewrote `training_summary.json`, so the authoritative full-run training timing for this 300k run comes from `training_metrics.jsonl` and `monitor_status.json`. After the 300k run, the trainer was patched so future no-op resume smoke tests write `resume_smoke_summary.json` instead of overwriting `training_summary.json`.

## Checkpoint Retention

Checkpoint retention worked. After the run and resume smoke test, only the latest 3 checkpoints remained:

- `checkpoint_step_00001000.pt`
- `checkpoint_step_00001500.pt`
- `checkpoint_step_00001620.pt`

Each checkpoint is about `111.98 MiB`. Run directory size after retention is about `335.96 MiB`.

This is acceptable at 300k. At 1M, checkpoint size will grow, so retention should remain enabled.

## Resume Smoke Test

Resume audit:

`/members/dhnyu/fusedata/gwanak_test/validation/korea_geo2vec_global_train_300k_sdf_proto_v1_32d/resume_smoke_audit.json`

The 300k stage used a normal-checkpoint resume smoke test rather than repeating the heavier controlled mid-shard stop, because a true mid-shard interruption already passed at 100k.

Verified:

- Latest checkpoint loaded.
- Id-map checksum was present and matched the run config.
- Sample-manifest checksum was present and matched the run config.
- Model state loaded.
- Optimizer state loaded.
- RNG states restored.
- Resume did not restart from zero.
- Checkpoint retention kept the latest 3 checkpoints.

Result: resume smoke test passed.

## Embedding Export

Output:

`/members/dhnyu/fusedata/gwanak_test/validation/korea_geo2vec_global_train_300k_sdf_proto_v1_32d_embeddings/`

Result:

- Rows: `300,000`
- Expected rows: `300,000`
- Geo_dim: `32`
- Parts: `30`
- Finite values: passed
- Row count validation: passed
- `building_id` joined through the id map.
- Output size: about `53.53 MiB`
- Export time: `0.64 s`

## Monitoring

Monitor output:

- `monitor_status.json`
- `monitor_status.md`

Key monitor values:

- Checkpoints: `3`
- Latest checkpoint size: about `111.98 MiB`
- Run directory size: about `335.96 MiB`
- Sample cache size: about `101.06 MiB`
- Embedding output size: about `53.53 MiB`
- Last validation L1: `0.03606`
- Mean training samples/sec: about `1.27M`
- Max CPU RSS: about `1330 MB`
- Max GPU allocated: about `165.5 MB`
- Max GPU reserved: about `270 MB`

## Did 300k Succeed?

Yes. The 300k engineering stability test succeeded.

The strongest evidence:

- Deterministic 8-worker SDF sampling completed all 60 shards without failures.
- Sample cache validation passed.
- One global model and one global embedding table trained across all shards.
- GPU VRAM was far below capacity.
- Checkpoint retention worked.
- Resume smoke test passed.
- Embeddings exported incrementally and validated.

## Is It Safe To Proceed To 1M?

Yes, with conservative settings and two small fixes before launch.

The observed 300k behavior scales predictably from 100k, and the main bottleneck remains CPU-side SDF generation rather than GPU memory. A 1M run with the same sample density should be an engineering stress test, not a final production-quality run.

## Recommended 1M Settings

Use the same model and sample density:

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
- SDF workers: start with `8`
- Buildings per shard: `5,000`
- Checkpoint every `1000` steps
- Keep latest `3` checkpoints
- Run one normal checkpoint resume smoke test after completion

Do not increase sample density for 1M. Do not raise workers beyond 8 until the first 100-200 shards complete safely. If the first 100-200 shards are stable and CPU utilization is low, test `12` workers only on a separate bounded run or a small shard group.

## Must Fix Before 1M

1. Add a pre-training validation that refuses to train if the sample manifest has failed or incomplete shards.
2. Consider adding a direct deterministic overlap checksum check between 300k and prior 100k manifests as a standard validation step.
3. Keep checkpoint retention enabled; full optimizer checkpoints will grow with `n_poly`.
4. Add checkpoint retention metadata to monitor output so retention policy is visible without opening the training summary.

Already fixed after the 300k run:

- No-op resume smoke tests now write `resume_smoke_summary.json` instead of overwriting the main `training_summary.json`.
- Training summaries now record `checkpoint_retention_keep`.

These are workflow hardening tasks, not blockers to the core one-global-model design.
