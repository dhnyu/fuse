# Current reduced configuration

The configuration tree contains current scientific/runtime contracts and schemas.
The dissertation `reduced` branch and `config/current_methodology.yml` define the
scientific contract; stage configs bind implementation and publication details.

## Current stage configs

- `p0_authority.yml`: fail-closed dissertation authority publication.
- `p1_scene_index.yml`: 10,000 off-grid scenes, split 1,000/9,000.
- `p2_base_spatial.yml`: production membership, observation, and relation plan.
- `p3_original_scene_cache.yml`: deterministic original-scene cache.
- `p4_augmentation.yml`: fixed scene-specific augmentation bank.
- `p5_fixed_queries.yml`: 2,000 validation and 18,000 evaluation queries.
- `model_inputs.yml`: model-ready cache and `d = d_c = 128` architecture.
- `current_experiment_plan.yml`: 11 OFAT and 17 comparison configurations.
- `training.yml` and `training_controller.yml`: current contrastive lifecycle.
- `evaluation.yml`: held-out evaluation contract.
- `p11_*.yml`: current downstream contracts or explicit recomputation gates.

Stage configs marked `RECOMPUTE_REQUIRED` intentionally reject predecessor-bound
artifacts until the corresponding current-lineage production stage is executed.
Historical paths may remain only as explicit immutable inputs or fail-closed
evidence; they are not current scientific authority.

Runtime worker/controller settings do not alter scientific identities unless they
change numerical execution semantics. Large artifacts are written outside Git,
validated in staging, and atomically published.
