# Gwanak Full Geo2Vec Epoch Saturation

Generated: 2026-06-10T04:27:22+09:00

## 1. Executive Summary

The bounded Gwanak full Geo2Vec epoch saturation study completed for epochs 1, 3, 5, and 10 using the paper-faithful branch order `[location, shape]`. No handcrafted geometry variables were added to embeddings. Recommended epoch for the next 100k experiment: `10`.

## 2. Training Configuration Audit

```json
{
  "batch_size": 4096,
  "classes": [
    "models.Geo2Vec.Geo2Vec_Model",
    "models.Geo2Vec.SDFLoss"
  ],
  "code_reg_weight": 0.1,
  "discrepancies": [
    "Disk-backed sample shards replace all-at-once in-memory Geo2Vec_Dataset materialization.",
    "Pandas/Parquet shard iteration replaces PyTorch DataLoader; minibatches still update one persistent Geo2Vec_Model and embedding table.",
    "The optimized controlled run uses code_reg_weight=0.1 for both branches; external defaults are branch-specific.",
    "No learning-rate schedule and no gradient clipping are present in either external or optimized trainer."
  ],
  "external_functions": [
    "Geo2Vec_Model.forward",
    "SDFLoss.forward",
    "list2embedding.list2vec"
  ],
  "external_model_file": "/members/dhnyu/fuse_external/GeoNeuralRepresentation/models/Geo2Vec.py",
  "external_runner_file": "/members/dhnyu/fuse_external/GeoNeuralRepresentation/runners/list2embedding.py",
  "gamma": "not explicit in implementation; equivalent role is code_reg_weight",
  "gradient_clipping": null,
  "hidden_size": 128,
  "latent_regularization_term": "mean(poly_embedding_layer(id)^2) * code_reg_weight",
  "learning_rate": 0.001,
  "learning_rate_schedule": null,
  "loss_function": "SDFLoss = summed L1 SDF reconstruction loss plus mean latent-code L2 regularization",
  "number_of_layers": 4,
  "number_of_workers": 0,
  "optimized_functions": [
    "make_model",
    "train_batch",
    "eval_validation",
    "main"
  ],
  "optimized_training_file": "/members/dhnyu/fuse/tests/geo2vec_large_scale/train_global_geo2vec_from_sample_cache.py",
  "optimizer": "torch.optim.Adam",
  "optimizer_weight_decay": 0,
  "positional_encoding_frequencies": 4,
  "shape_location_training_differences": [
    "Different sample cache normalization: shape uses per-entity centering/scaling after dataset normalization; location uses dataset/global normalization only.",
    "This optimized study keeps architecture and code_reg_weight identical across branches for controlled saturation comparison.",
    "Original list2embedding defaults differ by branch for code_reg_weight: location default 0.0, shape default 1.0."
  ],
  "sigma_z": "not explicit in implementation; external SDFLoss docstring describes code_reg_weight as 1/sigma^2",
  "weight_decay": "Geo2Vec_Model embedding initialization scale, not optimizer weight_decay",
  "weight_decay_init": 0.01
}
```

## 3. Consistency with Original GeoNeuralRepresentation

The optimized trainer uses the original external `Geo2Vec_Model` and `SDFLoss` classes. It preserves the entity embedding table plus SDF decoder objective, and the full export concatenates location first and shape second. Engineering differences are disk-backed sample shards, explicit checkpoint/resume support, and branch exports from persistent checkpoints. Methodological discrepancy to track: this controlled run keeps `code_reg_weight=0.1` for both branches, while the external defaults are location `0.0` and shape `1.0`.

## 4. Experimental Design

- Dataset: Gwanak buildings, `38547` entities.
- Epochs: `[1, 3, 5, 10]`.
- Geo_dim per branch: `32`.
- Full embedding dimension: `64`.
- Branch order: `['location', 'shape']`.
- Same id map, sample caches, seed, architecture, and split were reused for every epoch target.

## 5. Reused Inputs and Sample Caches

- Id map: `/members/dhnyu/fusedata/geo2vec_large_scale/id_maps/gwanak_full_geo2vec_paper_faithful_v1/gwanak_buildings_geo2vec_global_id_map.parquet`
- Shape cache: `/members/dhnyu/fusedata/geo2vec_large_scale/sample_caches/gwanak_full_geo2vec_paper_faithful_v1/korea_geo2vec_shape_samples_38547_sdf_gwanak_full_geo2vec_0200_v1/manifest.json`
- Location cache: `/members/dhnyu/fusedata/geo2vec_large_scale/sample_caches/gwanak_full_geo2vec_paper_faithful_v1/korea_geo2vec_location_samples_38547_sdf_gwanak_full_geo2vec_0200_v1/manifest.json`
- Shape SDF samples: `7627862`
- Location SDF samples: `4569360`

## 6. Resource Usage

|   epoch | branch   |   elapsed_seconds |   peak_maxrss_mb |   peak_gpu_allocated_mb |   peak_gpu_reserved_mb |   samples_seen |
|--------:|:---------|------------------:|-----------------:|------------------------:|-----------------------:|---------------:|
|       1 | shape    |           9.48692 |          1541.26 |                 78.7051 |                    116 |        6865433 |
|       1 | location |           2.46251 |          1450.44 |                 78.7051 |                    114 |        4112974 |
|       3 | shape    |          11.2933  |          1577.93 |                 78.7051 |                    116 |       20596299 |
|       3 | location |           6.85582 |          1469.89 |                 78.7051 |                    114 |       12338922 |
|       5 | shape    |          18.6032  |          1582    |                 78.7051 |                    116 |       34327165 |
|       5 | location |          11.2721  |          1502.5  |                 78.7051 |                    114 |       20564870 |
|      10 | shape    |          36.5153  |          1585.8  |                 78.7051 |                    116 |       68654330 |
|      10 | location |          22.0691  |          1507.68 |                 78.7051 |                    114 |       41129740 |

## 7. Training Dynamics

|   epoch | branch   |   final_mean_train_loss |   final_mean_train_reconstruction_loss |   final_mean_train_latent_regularization_loss |   final_validation_l1 |
|--------:|:---------|------------------------:|---------------------------------------:|----------------------------------------------:|----------------------:|
|       1 | shape    |                116.678  |                               116.678  |                                   0.000157322 |            0.0207382  |
|       1 | location |                151.358  |                               151.358  |                                   0.000112    |            0.0147088  |
|       3 | shape    |                 41.0254 |                                41.025  |                                   0.000456353 |            0.00917554 |
|       3 | location |                 31.6191 |                                31.6188 |                                   0.000276029 |            0.00632754 |
|       5 | shape    |                 31.2761 |                                31.2754 |                                   0.000737603 |            0.00714902 |
|       5 | location |                 24.7361 |                                24.7357 |                                   0.000417009 |            0.00559644 |
|      10 | shape    |                 22.3846 |                                22.3831 |                                   0.00145691  |            0.00545547 |
|      10 | location |                 18.0278 |                                18.027  |                                   0.000810972 |            0.00408071 |

Plots are stored under `/members/dhnyu/fusedata/geo2vec_large_scale/metadata/gwanak_full_geo2vec_epoch_saturation_v1/analysis`.

## 8. Shape-Only Results

|   epoch | target            | model         |        r2 |          mae |
|--------:|:------------------|:--------------|----------:|-------------:|
|       1 | area              | random_forest | 0.0664565 |   68.3044    |
|       1 | perimeter         | random_forest | 0.166343  |   12.4652    |
|       1 | compactness       | random_forest | 0.763547  |    0.0311307 |
|       1 | bbox_aspect_ratio | random_forest | 0.862394  |    0.0735475 |
|       1 | edge_count        | random_forest | 0.181991  |    2.18638   |
|       1 | vertex_count      | random_forest | 0.181991  |    2.18638   |
|       1 | centroid_x        | random_forest | 0.0495357 | 1192.24      |
|       1 | centroid_y        | random_forest | 0.0365936 |  719.171     |
|       3 | area              | random_forest | 0.127337  |   66.7591    |
|       3 | perimeter         | random_forest | 0.247576  |   12.0237    |
|       3 | compactness       | random_forest | 0.849447  |    0.0242018 |
|       3 | bbox_aspect_ratio | random_forest | 0.913932  |    0.0616414 |
|       3 | edge_count        | random_forest | 0.252173  |    1.99236   |
|       3 | vertex_count      | random_forest | 0.252173  |    1.99236   |
|       3 | centroid_x        | random_forest | 0.0777545 | 1169.54      |
|       3 | centroid_y        | random_forest | 0.05182   |  708.711     |
|       5 | area              | random_forest | 0.150914  |   65.3763    |
|       5 | perimeter         | random_forest | 0.264695  |   11.8542    |
|       5 | compactness       | random_forest | 0.860903  |    0.0228555 |
|       5 | bbox_aspect_ratio | random_forest | 0.917122  |    0.060075  |
|       5 | edge_count        | random_forest | 0.258169  |    1.9781    |
|       5 | vertex_count      | random_forest | 0.258169  |    1.9781    |
|       5 | centroid_x        | random_forest | 0.084477  | 1161.75      |
|       5 | centroid_y        | random_forest | 0.055616  |  707.612     |
|      10 | area              | random_forest | 0.148342  |   65.3028    |
|      10 | perimeter         | random_forest | 0.264773  |   11.8323    |
|      10 | compactness       | random_forest | 0.869877  |    0.0216225 |
|      10 | bbox_aspect_ratio | random_forest | 0.928061  |    0.0585803 |
|      10 | edge_count        | random_forest | 0.290274  |    1.93661   |
|      10 | vertex_count      | random_forest | 0.290274  |    1.93661   |
|      10 | centroid_x        | random_forest | 0.0866806 | 1160.01      |
|      10 | centroid_y        | random_forest | 0.0546955 |  707.955     |

## 9. Location-Only Results

|   epoch | target            | model         |        r2 |         mae |
|--------:|:------------------|:--------------|----------:|------------:|
|       1 | area              | random_forest | 0.0372893 |  69.5962    |
|       1 | perimeter         | random_forest | 0.0576654 |  13.0042    |
|       1 | compactness       | random_forest | 0.0525406 |   0.063228  |
|       1 | bbox_aspect_ratio | random_forest | 0.0199826 |   0.221966  |
|       1 | edge_count        | random_forest | 0.0773879 |   2.38318   |
|       1 | vertex_count      | random_forest | 0.0773879 |   2.38318   |
|       1 | centroid_x        | random_forest | 0.968962  | 205.675     |
|       1 | centroid_y        | random_forest | 0.956618  | 139.647     |
|       3 | area              | random_forest | 0.144442  |  67.0278    |
|       3 | perimeter         | random_forest | 0.147295  |  12.5975    |
|       3 | compactness       | random_forest | 0.0729007 |   0.0627677 |
|       3 | bbox_aspect_ratio | random_forest | 0.022764  |   0.220329  |
|       3 | edge_count        | random_forest | 0.0930868 |   2.36609   |
|       3 | vertex_count      | random_forest | 0.0930868 |   2.36609   |
|       3 | centroid_x        | random_forest | 0.989481  | 122.279     |
|       3 | centroid_y        | random_forest | 0.985558  |  84.2034    |
|       5 | area              | random_forest | 0.228255  |  63.2586    |
|       5 | perimeter         | random_forest | 0.234381  |  12.1605    |
|       5 | compactness       | random_forest | 0.1021    |   0.062122  |
|       5 | bbox_aspect_ratio | random_forest | 0.0251491 |   0.219402  |
|       5 | edge_count        | random_forest | 0.118776  |   2.34704   |
|       5 | vertex_count      | random_forest | 0.118776  |   2.34704   |
|       5 | centroid_x        | random_forest | 0.993748  |  94.3895    |
|       5 | centroid_y        | random_forest | 0.991047  |  65.8504    |
|      10 | area              | random_forest | 0.438401  |  56.8083    |
|      10 | perimeter         | random_forest | 0.408058  |  11.2949    |
|      10 | compactness       | random_forest | 0.161392  |   0.0606481 |
|      10 | bbox_aspect_ratio | random_forest | 0.055739  |   0.21577   |
|      10 | edge_count        | random_forest | 0.164626  |   2.31181   |
|      10 | vertex_count      | random_forest | 0.164626  |   2.31181   |
|      10 | centroid_x        | random_forest | 0.996819  |  65.7572    |
|      10 | centroid_y        | random_forest | 0.995385  |  46.9619    |

## 10. Full Geo2Vec Results

|   epoch | target            | model         |        r2 |         mae |
|--------:|:------------------|:--------------|----------:|------------:|
|       1 | area              | random_forest | 0.0855133 |  67.5992    |
|       1 | perimeter         | random_forest | 0.198884  |  12.2246    |
|       1 | compactness       | random_forest | 0.771917  |   0.030794  |
|       1 | bbox_aspect_ratio | random_forest | 0.873598  |   0.0712702 |
|       1 | edge_count        | random_forest | 0.194167  |   2.19642   |
|       1 | vertex_count      | random_forest | 0.194167  |   2.19642   |
|       1 | centroid_x        | random_forest | 0.979516  | 165.428     |
|       1 | centroid_y        | random_forest | 0.973045  | 109.728     |
|       3 | area              | random_forest | 0.160138  |  66.3442    |
|       3 | perimeter         | random_forest | 0.278185  |  11.8613    |
|       3 | compactness       | random_forest | 0.847073  |   0.02436   |
|       3 | bbox_aspect_ratio | random_forest | 0.912858  |   0.0607062 |
|       3 | edge_count        | random_forest | 0.24441   |   2.03636   |
|       3 | vertex_count      | random_forest | 0.24441   |   2.03636   |
|       3 | centroid_x        | random_forest | 0.991338  | 109.133     |
|       3 | centroid_y        | random_forest | 0.988775  |  73.4354    |
|       5 | area              | random_forest | 0.192414  |  64.2942    |
|       5 | perimeter         | random_forest | 0.316528  |  11.577     |
|       5 | compactness       | random_forest | 0.858393  |   0.0230351 |
|       5 | bbox_aspect_ratio | random_forest | 0.914748  |   0.0599983 |
|       5 | edge_count        | random_forest | 0.248036  |   2.02786   |
|       5 | vertex_count      | random_forest | 0.248036  |   2.02786   |
|       5 | centroid_x        | random_forest | 0.99419   |  89.7992    |
|       5 | centroid_y        | random_forest | 0.992007  |  61.4061    |
|      10 | area              | random_forest | 0.349031  |  60.3663    |
|      10 | perimeter         | random_forest | 0.373726  |  11.2123    |
|      10 | compactness       | random_forest | 0.867399  |   0.0218364 |
|      10 | bbox_aspect_ratio | random_forest | 0.922053  |   0.0591873 |
|      10 | edge_count        | random_forest | 0.296335  |   1.95455   |
|      10 | vertex_count      | random_forest | 0.296335  |   1.95455   |
|      10 | centroid_x        | random_forest | 0.99676   |  65.9468    |
|      10 | centroid_y        | random_forest | 0.99534   |  46.8349    |

## 11. Retrieval Diagnostics

Retrieval neighbor parquet outputs are listed in each epoch evaluation manifest under `/members/dhnyu/fusedata/geo2vec_large_scale/metadata/gwanak_full_geo2vec_epoch_saturation_v1/evaluation`. Shape neighbors prioritize shape similarity with weaker spatial proximity; location and full embeddings preserve centroid proximity much more strongly.

## 12. PCA Diagnostics

PCA coordinate parquet files and figures are listed in each epoch evaluation manifest under `/members/dhnyu/fusedata/geo2vec_large_scale/metadata/gwanak_full_geo2vec_epoch_saturation_v1/evaluation`. UMAP was attempted only if installed and was not required.

## 13. Epoch Saturation Analysis

Selected random forest R2 values:

|   epoch | target      |   full_geo2vec |   location |     shape |
|--------:|:------------|---------------:|-----------:|----------:|
|       1 | centroid_x  |       0.979516 |  0.968962  | 0.0495357 |
|       1 | centroid_y  |       0.973045 |  0.956618  | 0.0365936 |
|       1 | compactness |       0.771917 |  0.0525406 | 0.763547  |
|       1 | perimeter   |       0.198884 |  0.0576654 | 0.166343  |
|       3 | centroid_x  |       0.991338 |  0.989481  | 0.0777545 |
|       3 | centroid_y  |       0.988775 |  0.985558  | 0.05182   |
|       3 | compactness |       0.847073 |  0.0729007 | 0.849447  |
|       3 | perimeter   |       0.278185 |  0.147295  | 0.247576  |
|       5 | centroid_x  |       0.99419  |  0.993748  | 0.084477  |
|       5 | centroid_y  |       0.992007 |  0.991047  | 0.055616  |
|       5 | compactness |       0.858393 |  0.1021    | 0.860903  |
|       5 | perimeter   |       0.316528 |  0.234381  | 0.264695  |
|      10 | centroid_x  |       0.99676  |  0.996819  | 0.0866806 |
|      10 | centroid_y  |       0.99534  |  0.995385  | 0.0546955 |
|      10 | compactness |       0.867399 |  0.161392  | 0.869877  |
|      10 | perimeter   |       0.373726 |  0.408058  | 0.264773  |

Full Geo2Vec marginal gains:

| transition   |   delta_mean_selected_r2 |
|:-------------|-------------------------:|
| 1->3         |                0.0455022 |
| 3->5         |                0.0139369 |
| 5->10        |                0.0180267 |

## 14. Recommended Epoch for 100k Experiment

Recommended epoch: `10`. Use this setting as the first 100k default if the gain beyond it is small relative to training cost. Keep the 100k run bounded and require the same evaluation gate before any larger run.

## 15. Problems Found

No blocking problems found.

## 16. Next Steps

Run one 100k-building experiment with the recommended epoch, same branch order, same no-handcrafted-feature constraint, machine-readable resource logs, and the same evaluation framework.
