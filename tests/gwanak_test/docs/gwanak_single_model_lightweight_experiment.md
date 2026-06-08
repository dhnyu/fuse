# Gwanak Single-Model Lightweight Geo2Vec Experiment

Generated: 2026-06-08 02:40:09 KST

## Summary

- Single-model training status: `succeeded`
- Rows used: `38547`
- Runtime seconds: `37.225385665893555`
- Average training samples per entity: `52.00332062157885`
- Device: `cuda`
- CUDA_VISIBLE_DEVICES: `1`
- Peak GPU allocated MB: `78.98291015625`
- Peak GPU reserved MB: `116.0`
- Peak process max RSS MB: `1630.86328125`

## Configuration

Shape-only learning was used: `shape_learning=True`, `location_learning=False`.

```json
{
  "Geo_dim": 32,
  "num_epoch": 1,
  "seed": 20260608,
  "num_process": 8,
  "batch_size": 4096,
  "hidden_size_shape": 128,
  "num_layers_shape": 4,
  "num_freqs_shape": 4,
  "samples_perUnit_shape": 8,
  "point_sample_shape": 2,
  "sample_band_width_shape": 0.08,
  "uniformed_sample_perUnit_shape": 4,
  "training_ratio_shape": 0.9,
  "code_reg_weight_shape": 0.1,
  "weight_decay_shape": 0.01,
  "polar_fourier_shape": false,
  "log_sampling_shape": true
}
```

## Validation

- Output parquet: `/members/dhnyu/fusedata/gwanak_test/validation/gwanak_buildings_geo2vec_shape_single_model_lightweight.parquet`
- Metadata JSON: `/members/dhnyu/fusedata/gwanak_test/validation/gwanak_buildings_geo2vec_shape_single_model_lightweight_metadata.json`
- Validation succeeded: `True`
- Embedding shape: `38547x32`
- Error message: `None`

## UMAP

- UMAP succeeded: `True`
- UMAP parquet: `/members/dhnyu/fusedata/gwanak_test/validation/gwanak_single_model_umap.parquet`
- UMAP PNG: `/members/dhnyu/fusedata/gwanak_test/validation/gwanak_single_model_umap.png`

## Comparison With Chunked Embedding

- Chunked path: `/members/dhnyu/fusedata/embeddings/gwanak_buildings_geo2vec_shape_full.parquet`
- Chunked exists: `True`
- Single rows: `38547`
- Chunked rows: `38547`
- Matched building IDs: `38547`
- Single dimension: `32`
- Chunked dimension: `64`
- Note: Direct vector comparison is not meaningful because the previous output was trained chunk-by-chunk in separate latent spaces and has a different embedding dimension.

The important methodological difference is that this run learns one global latent space for all Gwanak buildings. The earlier full Gwanak output was generated chunk-by-chunk, so its vectors are not guaranteed to be mutually aligned across chunks.

## Scaling Implications

For Seoul, success here would justify a staged single-model feasibility study at larger deterministic samples before a full Seoul run. Monitor GPU reserved memory and sampled points per entity, not only final parquet size.

For nationwide Korea, even a successful Gwanak single-model run does not prove that a naive nationwide single model is practical. The nationwide strategy should still evaluate anchor-aligned chunks or a redesigned out-of-sample geometry encoder.
