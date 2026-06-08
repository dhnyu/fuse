# SDF Worker Scaling Benchmark Report

Generated: `2026-06-08 KST`

## Summary

The SDF worker-count benchmark completed successfully on a fixed 100k-building subset using the same deterministic SDF sample configuration as the 1M run. All worker counts produced valid sample caches, no failed or invalid buildings, and exactly matching shard checksums against the 8-worker baseline.

Recommendation for the 5M run: **use 8 SDF workers**.

Reason: 16 workers was the highest-throughput run, but it improved over 8 workers by only about `1.0%`, which is not meaningful enough to justify changing the already-proven 8-worker setting for a 5M stress test. Worker counts `24`, `32`, and `40` were slower.

## Benchmark Design

Benchmark subset:

- Buildings: `100,000`
- Id map: `/members/dhnyu/fusedata/geo2vec_large_scale/id_maps/korea_buildings_geo2vec_global_id_map_100k.parquet`
- Buildings per shard: `5,000`
- Shards per run: `20`

Sample config:

- `samples_per_unit`: `4`
- `point_sample`: `1`
- `uniform_grid`: `2`
- Validation ratio: `0.1`
- Base seed: `20260608`
- Sample config version: `sdf_proto_v1`

Worker counts:

- `8`
- `16`
- `24`
- `32`
- `40`

Output root:

`/members/dhnyu/fusedata/geo2vec_large_scale/sample_caches/worker_scaling_benchmark_100k/`

Summary tables:

- `/members/dhnyu/fusedata/geo2vec_large_scale/sample_caches/worker_scaling_benchmark_100k/worker_scaling_summary.csv`
- `/members/dhnyu/fusedata/geo2vec_large_scale/sample_caches/worker_scaling_benchmark_100k/worker_scaling_summary.parquet`

## Results

| Workers | Valid | Samples | Elapsed s | Samples/sec | Buildings/sec | CPU RSS MB | MaxRSS MB | I/O wait % | Failed | Invalid | Cache MiB | Checksum match |
|---:|:---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---:|
| 8 | true | 2,408,418 | 25.94 | 92,848 | 3,855 | 387.3 | 380.3 | 0.027 | 0 | 0 | 33.72 | true |
| 16 | true | 2,408,418 | 25.67 | 93,816 | 3,895 | 383.9 | 376.0 | 0.028 | 0 | 0 | 33.72 | true |
| 24 | true | 2,408,418 | 28.96 | 83,150 | 3,452 | 384.1 | 376.6 | 0.030 | 0 | 0 | 33.72 | true |
| 32 | true | 2,408,418 | 31.28 | 76,989 | 3,197 | 387.8 | 381.2 | 0.025 | 0 | 0 | 33.72 | true |
| 40 | true | 2,408,418 | 33.98 | 70,875 | 2,943 | 380.8 | 372.7 | 0.020 | 0 | 0 | 33.72 | true |

Validation was identical across all worker counts:

- Total samples: `2,408,418`
- Train rows: `2,167,930`
- Validation rows: `240,488`
- Observed validation ratio: `0.09985`
- Buildings with samples: `100,000`
- Missing building count: `0`
- Sample count median: `22`
- Sample count range: `17..1208`

## Determinism

All worker-count outputs were compared against the 8-worker baseline by shard checksum and row count.

Result:

- All shard checksums matched.
- All shard row counts matched.
- Multiprocessing output order did not affect sample values.

This confirms that the stable per-building seed logic is working for the tested worker counts.

## I/O Wait

Measured system I/O wait was very low for all runs:

- Range: about `0.020%..0.030%`

I/O wait was not excessive and was not the limiting factor in this benchmark.

## Interpretation

The bottleneck is not improved by increasing workers beyond 8 for this shard design. The likely reason is a combination of process scheduling overhead, Shapely geometry serialization overhead, per-shard task management overhead, and the relatively small 5,000-building shard size.

The 16-worker run was technically fastest:

- 16 workers: `93,816 samples/sec`
- 8 workers: `92,848 samples/sec`
- Improvement: about `1.0%`

That improvement is too small to be meaningful for a 5M stress test, especially because 8 workers has already been validated at 100k, 300k, and 1M.

Worker counts above 16 were slower:

- 24 workers was about `10.4%` slower than 16.
- 32 workers was about `17.9%` slower than 16.
- 40 workers was about `24.5%` slower than 16.

## Recommendation For 5M

Use:

- SDF workers: `8`
- Buildings per shard: `5,000`
- Same sample config as 1M
- Same deterministic seed configuration

Do not use 24, 32, or 40 workers for the 5M run.

16 workers can remain an optional future tuning candidate, but it should not be used for the 5M run because its measured improvement over 8 workers was only about `1%`.

## Required 5M Safety Checks

Before launching 5M:

- Keep the 8-worker setting.
- Keep checkpoint retention enabled.
- Run overlap checksum check against the first 200 shards of the 1M cache after 5M sample generation.
- Continue validating every sample cache before training.
- Do not increase sample density.
