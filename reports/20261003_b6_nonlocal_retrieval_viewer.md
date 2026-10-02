# B6 evaluation Non-local viewer correction

Created 2026-10-03 07:06 Asia/Seoul. Source branch B6, entry HEAD
`9bf47a0888626c8c420dea8192e3cb8f6b15d6bc`, origin/B6 0/0. Expected local
validation-viewer source/report changes were inspected and preserved.

## Scope correction

It visualized formal validation retrieval rather than the intended evaluation
Non-local retrieval and used a newly designed comparison interface instead of
directly reusing the established reduced/S10 viewer presentation.

The historical validation output
`/mnt/hdd002/dhnyu/fusedata/experiments/b6_retrieval_viewer/b6viewer_72c45bffa43538a714743ff5/`
remains intact. Its source and report are retained as a clearly separate tool.
This task authorizes selected-checkpoint evaluation inference/export, not training,
model selection, formal-result revision or any canonical S09/S10 campaign.

## Exact visual authority discovered

The former URL `https://technologies-ata-neither-periodic.trycloudflare.com/`
was traced through `reports/20260922_variant_c_cloudflare_publication.md` and
`logs/20260922_composite_c_cloudflare.log` to:

`/mnt/hdd002/dhnyu/fusedata/retrieval_data/reduced/s10_all_model_viewers/viewer_composite_c_e067ad37b57973b09f35349b`

This is the **Composite C** all-model, all-9,000-query viewer, not the initial
30-/100-query S10 viewer and not the newly designed B6 validation viewer.
Its publication code is `scripts/build_retrieval_composite_c_viewer.py`, template
source `tools/retrieval_inspector/composite_c/{index.html,runtime.js,prototype.css}`.
The generated files, not an inferred design, are the visual authority.

Its parent is `viewer_models_ca8e9bba52741dd6a0ff563b`, built by
`scripts/build_s10_all_model_viewer.py`; shared scene displays derive from
`viewer_all_57226fcbe9128cdd90b40f59`. Composite assets are
`s10_composite_c/s10composite_c_webp_5c397eb3bb44e7717771447b`.
The prior URL report recorded intermittent public Chromium network failures;
that historical limitation is not treated as proof of current public readiness.

Direct reuse: augmentation/style/legacy-bands/bands/locations/prototype CSS;
app/helpers/location JS; original query index and metadata; original full composite
maps, thumbnails, layer assets, detailed vector/LC/DEM/attribute views and palette.
No CSS or renderer reimplementation. Query, Rank 1, Upper, Middle, Lower remain
five columns for one active dropdown-selected model. Header controls, ordering,
scene/location search, zoom, layer toggles, details and thumbnail strips are retained.

Minimal template/runtime substitutions: three B6 labels/checkpoint epochs, model
registry cardinality, Original model default, Non-local default, context-only label,
zero-road flag, and one road-containing-first query-order option. The latter preserves
all 9,000 queries and changes navigation only. All contextual B/P/LC/DEM displays
remain visible by default, with the explicit notice that B6 uses roads only.

## Verified retrieval contract

- Authority: accepted S10 generation `s10gen_a24b979d4c1557387cbbec35`, gallery
  `s10_gallery_16e80b03246c193969aad9b5`; exact old viewer index matches its rows.
- 9,000 evaluation **original** scene representations, one per scene, used both
  as queries and as the 9,000-scene gallery. No augmented validation query bank.
- Query/global order is lexical scene ID, shared by every arm.
- S10 `python/retrieval_inference.py`: normalized scene embedding, not contrastive
  projection-head output; eval/inference mode; float32; batch one; seed 20260916;
  TF32 off; deterministic algorithms; same accepted vocabulary/preprocessing.
- `python/retrieval_ranking.py::rank`, `python/s10_all_query.py::select`:
  float32 matrix-vector cosine; NumPy stable descending sort over lexical IDs.
- Both Standard and Non-local exclude the query's own scene index. Non-local
  additionally excludes Euclidean center distance **< 2000.0 m**, computed from
  float64 EPSG:5186 center coordinates with `np.linalg.norm`. Exactly 2000 m is
  included. This is not geographic degrees, geodesic distance or bbox separation.
- Rank indexing is 1-based within each eligible candidate list.
- Band function reused directly: `most=[1]`; `top=2..11`;
  `middle=floor((N-10)/2)+1` through the next nine ranks; `bottom=N-9..N`, where
  N is that query/mode's eligible candidate count. It is not a fixed 491/991 band.
- Binary records, shard decoder and query ordering reuse `python/s10_all_models.py`.
  Rank-1 cosine asc/desc affects navigation, not retrieval. Exact query-score ties
  retain lexical query order. Standard remains available; Non-local is default.

## Selected models and inference adapter

| Arm | Epoch | Authority |
|---|---:|---|
| B6-original | 90 | b6formalauth_3167ba3d10e3b8c8a0528d18 |
| B6-S50-G | 135 | b6formalauth_6503d6bc57e53ffe18aae3b8 |
| B6-S50-Ppre | 130 | b6formalauth_7b782341aceb31d2437eeaa6 |

Checkpoint payload hashes bind the formal selected boundary receipts. The formal
control reads the accepted S10 original-input tensors and applies unchanged B6
family projection. Additional evaluation embeddings are necessary; no historical
canonical B6 embedding or validation vector matrix is substituted for these models.

S50 inputs use existing `b6_con_census.build_children`,
`b6_con_lift.lift_accepted_parent_con_to_children`,
`b6_segmented_inputs.full_source_graphs` and `tensorize_children`. Evaluation is
unaugmented original-scene inference, so the materialized input here is the P3
observed original. S50, full-source competition, G/Ppre semantics, receiver attributes,
CON policy `accepted_parent_con_nearest_chain_child_v1`, bbox positions and Fourier
encoder are unchanged from Stage B. G/Ppre share geometry/Fourier/non-edge tensors;
only SN differs. Zero-road scenes are retained.

The canonical S10 resolver requires canonical authority identities and cannot accept
these experimental formal authorities without relabeling. Therefore an isolated
adapter loads their hash-bound online encoder state, but calls existing S10 inference
initialization/GPU lock, production model/family collation, and exact S10 rank/band
functions. No canonical resolver, config, publication root or checkpoint is changed.

## Reproducible isolated pipeline

New code: `python/b6_nonlocal_viewer.py`, `config/b6_nonlocal_viewer.yml`,
`R/b6_nonlocal_viewer.R`, `targets/b6_nonlocal_viewer.R`,
`_targets_b6_nonlocal_viewer.R`, focused tests and validation scripts.
Dedicated store: `/mnt/hdd002/dhnyu/fusedata/targets/fuse-b6-nonlocal-viewer`.

Target order: bound contract → 3-scene input pilot → repeated deterministic GPU
inference pilot → complete inputs → complete selected-model inference → S10 bands
→ cloned static viewer. GPU controller plus existing exclusive GPU0 lock; one
inference process, one thread, batch one. CPU preparation: 8 workers × 1 thread.
No optimizer, training, selection, S09 campaign, S10 canonical publication or
S11/S12 target is reachable.

All new products live under
`/mnt/hdd002/dhnyu/fusedata/experiments/b6_nonlocal_retrieval_viewer/b6nonlocal_0d8a53f9cdbf481b8a3c6296/`.
Contract binds code/config, accepted parent manifests, selected payload hashes and
old UI receipt. Products stage separately, validate, and publish by rename. Existing
outputs are checksum-readback only. Shared static assets are explicit read-only mounts.

## Pilot and initial validation

3 fixed cases: zero roads; sparse 2 parents → 10 children; highest-count original
162 parents → 244 children. Ownership ambiguity zero; no zero-road fallback.
All three selected models load strictly, produce finite normalized vectors and have
bitwise-equal repeated inference. Peak allocated GPU memory on these fixtures:
54.46 / 58.03 / 58.24 MiB (Original/G/Ppre). These are not full-export peak estimates.

Focused and relevant regressions: 88 tests PASS, including exact 2km boundary,
self exclusion, exact/near cosine ties, legacy band positions/binary roundtrip,
CON lifting, Stage B preparation, original readers and viewer server. Initial import
error in the new adapter was corrected before contract publication/execution.
Python compile, R parse, target manifest and tar_validate PASS.

## Final execution, browser validation and serving

Completed 2026-10-03 07:16 Asia/Seoul. **READY FOR VISUAL INSPECTION**.

All eight targets are up-to-date; DAG 8 vertices/12 edges is acyclic; final
`tar_validate` and `tar_outdated` checks PASS. Dependency HTML:
`artifacts/targets-network-b6-nonlocal-viewer/targets-network.html`.
A preliminary DAG inspection requested an unsupported `tar_manifest` field;
using the supported `tar_network` vertices/edges completed the check successfully.
No target execution failed.

Input acceptance: 9,000 scenes, 287,604 original roads, 607,443 children;
1,261 zero-road scenes unchanged; unresolved ownership ambiguity 0. Accepted CON
has 474,319 unordered source-node causes, including 93 with logical off-support
mapping under the unchanged approved policy. G/Ppre share all non-edge tensors
and have identical INT/CON; only SN may differ. Full inputs took 5m45s.

| Model | New evaluation embedding identity | Inference seconds | Peak allocated MiB |
|---|---|---:|---:|
| B6-original | b6eval_3eba905e2e3863aa259e1fb1 | 51.598 | 54.78 |
| B6-S50-G | b6eval_a320a051fb232e447676fa9f | 51.989 | 63.11 |
| B6-S50-Ppre | b6eval_4e68a665e0608b1a47e42a7d | 52.239 | 63.97 |

The inference target including initialization/readback took 2m41s. GPU0 RTX A6000,
exclusive existing GPU lock, one process, batch one; no backward or optimizer.
The band target took ~29s and publishes 1,674,000 records across two modes, three
models and 9,000 queries under the new design identity. Each arm independently
checks 100 deterministic random queries plus dense/sparse/zero-road cases against
lexical full sorting; all-query candidate counts, self/distance rules and band
positions are checked. No full 9,000² matrix is persisted.

Independent readback additionally checks actual nearest-to-2km pairs:
1,999.9969873813682 m excluded; 2,000.00084875343 m included. Synthetic fixtures
cover exactly 2,000 m, exact ties and one-ULP near ties. All 1,261 zero-road
embeddings are bitwise identical within each arm. Pilot/full-input bytes match
for all three pilot scenes; pilot/full-inference vectors are bitwise equal.
Selected checkpoints and all bound parent manifests remain unchanged.

Local Chromium: **27 exact band/score readbacks PASS**. Public Chromium: **27
exact band/score readbacks PASS**, no JS errors. Both runs exercise all three
models and both modes at global positions 1/4500/9000, navigation ordering,
road-containing-first navigation, next/previous/random, scene search, last
thumbnail in each band, five layer toggles, Details and deep-link reload.
All main images and 30 thumbnails load. Browser checks confirm Non-local default.

Old/new screenshot comparison uses the same scene, viewport and Non-local mode.
Five-column x positions and widths are exactly equal. All six CSS files plus
app/helpers/locations JS and original index are byte-identical. Main map and
thumbnail assets are the same immutable files, including original contextual
B/P/LC/hillshade and geographic metadata. Header wrapping changes naturally with
the shorter three-model dropdown; the underlying layout/styles are not redesigned.
The new screenshot was manually reviewed against the old stored-viewer screenshot.

Evidence directory:
`/mnt/hdd002/dhnyu/fusedata/tmp/fuse/b6_nonlocal_20261003/`
contains `export_validation.json`, `local/browser.json`, `local/old.png`,
`local/b6.png`, and `public/browser.json`, `public/b6.png`.

Viewer root:
`/mnt/hdd002/dhnyu/fusedata/experiments/b6_nonlocal_retrieval_viewer/b6nonlocal_0d8a53f9cdbf481b8a3c6296/viewer/`

Local URL: http://127.0.0.1:18775/

New public URL: https://rolling-webpage-publicly-enrolled.trycloudflare.com/

Road-containing-first entry:
https://rolling-webpage-publicly-enrolled.trycloudflare.com/?mode=nonlocal&order=roadfirst&pos=1

Only `b6-viewer-http` and `b6-viewer-tunnel` were replaced after validation on
port 18777. Other reduced/S10 servers and tunnels remain unchanged. The temporary
check server is stopped. Current tmux sessions retain those same B6 names.
Server reuses `scripts/serve_viewer_hub_fast.py`, explicit static-file allowlist,
loopback port 18775, gzip and HTTP cache validation. It exposes display assets and
rank bands only; embedding matrices, model-input cache and checkpoints are outside
the served root. Logs: `logs/20261003_b6_nonlocal_http.log` and
`logs/20261003_b6_nonlocal_tunnel.log`.

Stop:

```bash
tmux kill-session -t b6-viewer-tunnel
tmux kill-session -t b6-viewer-http
```

Restart (after stopping; the quick-tunnel URL will change):

```bash
tmux new-session -d -s b6-viewer-http '/members/dhnyu/.conda/envs/rgeo/bin/python -u /members/dhnyu/fuse/scripts/serve_viewer_hub_fast.py --root /mnt/hdd002/dhnyu/fusedata/experiments/b6_nonlocal_retrieval_viewer/b6nonlocal_0d8a53f9cdbf481b8a3c6296/viewer --test-port 18775 > /members/dhnyu/fuse/logs/20261003_b6_nonlocal_http.log 2>&1'
tmux new-session -d -s b6-viewer-tunnel '/members/dhnyu/.local/bin/cloudflared tunnel --no-autoupdate --url http://127.0.0.1:18775 > /members/dhnyu/fuse/logs/20261003_b6_nonlocal_tunnel.log 2>&1'
```

## Limitations and preservation

This is qualitative evaluation retrieval, not validation self-match accuracy.
Rank-1 cosine ordering is not a correctness or model-quality label. No scientific
improvement conclusion or checkpoint selection is made. Zero-road scenes remain
indistinguishable: choose road-containing-first for practical morphology inspection.
Card entity/relation counts are the **original full-source display context**, not
the segmented model's graph counts. Child-cut boundaries and child relations are
not overlaid; this deliberately retains the original Composite C presentation.
No new mean-parent-length control was added. The Cloudflare URL is temporary;
current public tests pass but are not a guarantee of uninterrupted future service.

The prior local validation viewer sources and report are included in the scoped
correction commit for provenance; their old immutable output is preserved. Generated
inputs (~2 GiB total new experiment), embeddings, rankings, scenes, logs, audit
screenshots and targets store are outside Git. Only source/config/tests/reports
and dependency-network HTML are committed.

Formal retraining = NO. Checkpoint selection changes = NO. Canonical artifacts
modified = NO. Dissertation modified = NO (clean at final check). Reduced modified
= NO (`851efd0c94120ff250f34502fceba73a45080281`). Formal B6 numerical result
acceptance and selected checkpoint bytes remain unchanged.
