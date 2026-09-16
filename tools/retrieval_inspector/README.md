# S10 Retrieval Visualization consumer

This viewer reads immutable formal S10 rankings and scene-render artifacts.
It does not load checkpoints, infer embeddings, calculate similarity, rank,
filter geographically or fall back to scientific computation. Missing or corrupt
artifacts fail. Historical inspector implementations/caches are not authority.

Open the accepted generation's `pages/index.html`, then a query page. Each page
shows the same query with all OFAT and comparison models, Top 5 by default and
standard/non-local controls. Maps are fixed 500 m north-up vector scene views:
gray buildings, amber roads and pink POIs. Metadata shows the published rank,
scene ID, cosine score, distance and mode. Scene thumbnails share a cache bound
to scene payload, renderer source and parameter hashes. The initial thumbnail
view is vector-only; it does not purport to display all model modalities.

Scientific computation belongs to `python/retrieval_*` and the dedicated
`_targets_retrieval_visualization.R` graph. Pinned scientific parents come from
S09 campaign `s09camp_d2f6749da19ad6aa56c2d303`, never stale evaluation config.
The primary comparison key is configuration_id, including distinct OFAT models
whose family is FM. Query seed is explicit PCG64 **20260916**, not stage-derived.

Canonical artifacts: 28 models, 30 queries, 9,000 gallery scenes; Top 50 for each
model/query/mode, exactly 84,000 rows. Ranking ties use scene ID ascending.
Distance is Euclidean between EPSG:5186 centers in metres; exactly 2,000 m remains
eligible. Insufficient Top 50 candidates fail acceptance. Rerun publication
requires identical bytes under the same runtime and scientific identities.

S10 is qualitative inspection only: no model/winner selection, checkpoint changes,
hyperparameter retuning, special selection of B8/B9, or changes to S11 queries,
gallery or evaluation protocol. S11 stays blocked pending separate lineage repair.

Validation smoke (temporary noncanonical outputs are automatically removed):

```sh
PYTHONDONTWRITEBYTECODE=1 python scripts/smoke_retrieval_visualization.py
```

After separate full-inference approval, the command would be:

```sh
Rscript scripts/run_retrieval_visualization.R --authorize-full-inference
```

It targets `s10_retrieval_visualization_acceptance` in the dedicated S10 store.
It does not execute S09 or S11. Running this command is not part of implementation
validation. GPU locks are shared with S09; worker/thread budgets remain explicit.
