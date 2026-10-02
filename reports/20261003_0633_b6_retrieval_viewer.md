# B6 selected-checkpoint retrieval viewer

Created: 2026-10-03 06:33 Asia/Seoul.

## Purpose and provenance

Temporary same-query qualitative comparison requested after the formal three-arm
Stage B experiment. No new inference, training, selection or scientific metric
acceptance. Branch B6, entry/source HEAD
`9bf47a0888626c8c420dea8192e3cb8f6b15d6bc`, origin/B6 0/0, clean at entry.
Viewer source/report additions remain local: this task did not request commit/push.

| Arm | Selected epoch | Authority |
|---|---:|---|
| B6-original | 90 | b6formalauth_3167ba3d10e3b8c8a0528d18 |
| B6-S50-G | 135 | b6formalauth_6503d6bc57e53ffe18aae3b8 |
| B6-S50-Ppre | 130 | b6formalauth_7b782341aceb31d2437eeaa6 |

Inputs are the saved normalized validation scene embeddings at those selected
epochs under formal design `b6formal_e593d0bb2f2f6acd77056c76`. The selected
checkpoint SHA and vector SHA are checked against their accepted boundary
receipts; comparison and final-audit manifests pass readback. All three arms use
exactly 2,000 fixed queries (two per source scene) and the unchanged 1,000-scene
validation gallery. Sorting is descending cosine with stable accepted gallery
order for exact ties, matching formal validation. No candidate exclusion.

## Export and implementation

Immutable output (~61 MiB):

`/mnt/hdd002/dhnyu/fusedata/experiments/b6_retrieval_viewer/b6viewer_72c45bffa43538a714743ff5/`

Includes catalog, per-query rank data, HTML/CSS/JS, road SVGs, optional land-cover
context PNGs, acceptance and SHA-256 manifest. Generated through external staging,
validated, then renamed to the content-derived final directory. Reruns validate
an existing directory; they do not overwrite it.

Source files:

- `scripts/build_b6_retrieval_viewer.py`
- `scripts/validate_b6_retrieval_viewer.py`
- `tools/retrieval_inspector/b6/index.html`
- `tools/retrieval_inspector/b6/style.css`
- `tools/retrieval_inspector/b6/app.js`

Direct display-export entrypoint, following existing `build_s10_*_viewer.py`
patterns. No research target/DAG changes, so tar_make/tar_validate and dependency
network regeneration are not applicable. No R source changed.

Rendering reuses `python/retrieval_render.py`: north up, 500 m frame, orange roads.
Road parts reconstruct from accepted scientific float64 local coordinates plus
model bbox-relative positions; the latter retain their accepted float32 precision.
No disconnected parts are bridged. Each query shows its **actual accepted
augmented road geometry**, alongside its unaugmented positive gallery scene.
Road geometry is common across segmentation policies, so it is shown once.
Gallery panels show original scene support. Land-cover context reuses the prior
supplemental viewer's fraction-weighted palette and PNG helper; it is clearly
labelled context only, not a B6 model input. All 3,000 prepared samples are read
with their accepted checksums and view IDs verified.

## Features

- Same query in all three columns, checkpoint epoch/hash visible.
- Previous/next/random; jump by 1-based index, query ID, or source scene ID.
  A scene-ID jump opens its first query view.
- Bookmark URL fragment preserves query, filter, sort, depth and map mode.
- Top 1/5/10/50; middle ranks 491–500; lower ranks 991–1000.
- Rank, cosine, source correctness, original road count/mean parent length per card.
- Query flags, original count/length strata, density, orientation and location
  dispersion from existing original-parent descriptors.
- Delta table: source rank, rank-1 scene, source cosine, hardest incorrect cosine,
  margin/loss and differences relative to Original.
- Filters: all/nonempty/zero; count 1–8/9–49/50+; mean parent length
  0–50/50–100/100–250/250–500/500+; rank-1 disagreement; Original wrong and G/Ppre
  right; Original right and segmented wrong; G/Ppre top-10 differences;
  loss improved with unchanged source rank; G or Ppre loss/rank gains.
- Sorting: original order, query ID, disagreement first, road count, mean parent
  length, each arm's source rank (worst first) or source cosine (lowest first).
- Presets: nonempty, high-road-count, G/Ppre gain candidates, G/Ppre top-10
  differences, rank failures and zero-road ties.

Rank-1 disagreement: 2 queries. Original wrong/G right: 1; Original wrong/Ppre
right: 1; Original right/segmented wrong: 1. G/Ppre top-10 ordering differs for
1,712 queries. These labels describe existing rankings, not new result acceptance.

## Serving

Local: http://127.0.0.1:18775/

Temporary public URL: https://eat-incidents-deposit-drain.trycloudflare.com/

Dedicated tmux sessions: `b6-viewer-http`, `b6-viewer-tunnel`.
Port 18775 was free. Existing viewer servers/tunnels were not changed.

Stop only this viewer:

```bash
tmux kill-session -t b6-viewer-tunnel
tmux kill-session -t b6-viewer-http
```

Restart after stopping:

```bash
tmux new-session -d -s b6-viewer-http '/members/dhnyu/.conda/envs/rgeo/bin/python -u -m http.server 18775 --bind 127.0.0.1 --directory /mnt/hdd002/dhnyu/fusedata/experiments/b6_retrieval_viewer/b6viewer_72c45bffa43538a714743ff5 > /members/dhnyu/fuse/logs/20261003_b6_viewer_http.log 2>&1'
tmux new-session -d -s b6-viewer-tunnel '/members/dhnyu/.local/bin/cloudflared tunnel --no-autoupdate --url http://127.0.0.1:18775 > /members/dhnyu/fuse/logs/20261003_b6_viewer_tunnel.log 2>&1'
```

A restarted quick tunnel normally gets a new URL; read the tunnel log. The URL
is temporary and unauthenticated. The server exposes only this static display
export, not the experiment's checkpoint/cache directories.

## Validation and limitations

PASS: Python compile, JS syntax, all output checksums, all 420,000 exported
rank/score rows compared exactly with selected vectors, query/gallery alignment,
selected epochs, aggregate HIT@1 reproduction, 144 zero-road scenes / 288 queries.
Headless Chromium checks cover filters, all sorting choices, random/previous/next,
query-ID/index jumps, depth/bands, bookmark reload, image loading and no JS errors.
Manual screenshot review covered road-nonempty, land-cover and zero-road displays.
Local HTTP and public HTML readback match the immutable export.

This is validation retrieval, not evaluation/S10 or a new nonlocal experiment.
Positive source scenes dominate rank 1; inspect ranks 2–10/50 for morphological
comparisons. Numeric gain presets are candidates for inspection, not curated
qualitative wins. A zero-road rank-1 match can arise solely from gallery-order
tie-breaking. Cross-arm score differences near float precision are not meaningful
visual improvements. Land-cover patterns must not be attributed to B6 input.
No building/POI overlays, geographic basemap/address labels, child-boundary or
relation-edge overlays are included. Rendering is road-support focused.

Formal results/checkpoints and canonical artifacts unchanged. Dissertation remains
clean; reduced remains `851efd0c94120ff250f34502fceba73a45080281`. No retraining,
checkpoint changes, numerical acceptance changes or canonical publication.

Final verdict: **READY FOR VISUAL INSPECTION**.
