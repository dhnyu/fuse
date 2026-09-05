# Retrieval Inspector 10K Current Artifact Promotion

## Verdict and Scope

**RETRIEVAL_INSPECTOR_10K_CURRENT_ARTIFACT_PROMOTION_PASS**

Report created 20260906_0150, Asia/Seoul. Commit/push and origin synchronization follow
the completed gates; their outcome and SHA are reported in the completion message.

Prompt summary: preserve the old 1,600-only inspector as immutable legacy,
promote a complete repo-local 10K-capable application to current/default,
default to Expanded 10,000 while retaining canonical comparison, change default
CLI behavior, validate actual local HTML, and commit/push reduced. This is
presentation packing and artifact promotion, not scientific production.

Starting Fuse: reduced, clean, commit
20824c6f5c8cfce6f5e3f82abf22f27af3b0a43a.
Implementation authority remains retrag_29e75a5e81df82e0c3d93783 and acceptance
retr10k_0672df44ea0fb5adceafbec9. No dissertation changes.

## Initial Audit and Classification

| Files or location | Classification and handling |
|---|---|
| P9/P10/P11, scene indices/caches, embeddings, union, ranking Parquets, diagnostic JSON, scientific acceptance | Immutable scientific evidence; read/hash only |
| External authority/inspector/manifest.json and assets | Accepted inspector evidence bound by the supplemental acceptance; unchanged |
| External authority/inspector/index.html and presentations/retrview_* | Existing external presentation; retained unchanged, available through compatibility CLI |
| artifacts/retrieval-inspector/retrieval_inspector_c612a074a9211c222eb9a811 | Generated untracked 1,600-only legacy application; original files unchanged |
| tools/retrieval_inspector/example_output.json | Historical legacy pointer; unchanged to preserve existing consumers |
| tools/retrieval_inspector/supplemental_output.json | Scientific supplemental acceptance binding; unchanged |
| New artifacts/retrieval-inspector/current/<id> | Current repo-local presentation package, not scientific ranking output |
| current.json, legacy.json, directory README, legacy alias | Small explicit artifact-discovery metadata |
| Source tools and tests | Presentation/packaging implementation |

The artifact directory was ignored by Git, and the old generated application
had no tracked files. It was not moved or deleted. A relative legacy alias and
hash-bound legacy pointer provide an explicit namespace while preserving old
links and byte identity.

The existing identity convention is retrieval_inspector_<content digest>.
The new current identity follows this convention and differs from the legacy
identity. Filesystem timestamps are not used as identity.

## Exact Current and Legacy Paths

### Current

ID: **retrieval_inspector_dafc174b9997c59198b3d121**

[Current 10K HTML](/members/dhnyu/fuse/artifacts/retrieval-inspector/current/retrieval_inspector_dafc174b9997c59198b3d121/index.html)

Exact entry:
/members/dhnyu/fuse/artifacts/retrieval-inspector/current/retrieval_inspector_dafc174b9997c59198b3d121/index.html

Entry SHA-256:
4eee083b0e84746c71bc47caa364e90ef3013e28aca9c69ae91de2366a5dfe4c

Current manifest SHA-256:
fe450d22026b16403392b8bf80a78e2c66c1c10c8d3a830ff958fcd308ff3a54

Artifact manifest SHA-256:
0bab776414eef3e30ab32775b0a9f87b35b7185ce50f4bf70fa1995218404477

### Legacy

ID: **retrieval_inspector_c612a074a9211c222eb9a811**

[Explicit legacy 1,600 HTML](/members/dhnyu/fuse/artifacts/retrieval-inspector/legacy/retrieval_inspector_c612a074a9211c222eb9a811/index.html)

Legacy alias:
/members/dhnyu/fuse/artifacts/retrieval-inspector/legacy/retrieval_inspector_c612a074a9211c222eb9a811/index.html

Original path, still accessible:
/members/dhnyu/fuse/artifacts/retrieval-inspector/retrieval_inspector_c612a074a9211c222eb9a811/index.html

Both legacy paths resolve to the same existing files. Entry SHA-256:
a5ef0616e8c9097493947a8e460f2cdbfee3cfc638cb46b2b10eca376c08c9d7

Legacy binds P10 p10acc_6e5071beee7616750dec7907 and retains 1,342 scene assets.
Its HTML, JS, CSS, manifest JS/JSON, scene summaries and assets are byte-identical.

## CLI and Naming Contract

Current/default:

    python tools/render_retrieval_inspector.py

The command resolves and validates the current repo-local package. If the
package is missing, it builds from accepted evidence and publishes current.json
only after the actual HTML passes browser validation.

Explicit current repacking:

    python tools/render_retrieval_inspector.py --build-current

Explicit legacy access, without any ranking regeneration:

    python tools/render_retrieval_inspector.py --legacy-canonical

Explicit validation remains supported:

    python tools/render_retrieval_inspector.py --validate <package-directory>

--supplemental remains a compatibility option for the external accepted
presentation, with a warning that the normal current workflow needs no flag.
--refresh-supplemental retains the previous explicit external refresh behavior;
it was not run in this task. --overwrite is rejected to prevent deleting
immutable packages. --output-root now selects a repo-local package container,
not a canonical ranking generator.

Terminology is documented consistently:
- Current: the 10K-capable dual-gallery application.
- Expanded: the 10,000 gallery mode in current.
- Canonical: the 1,600 comparison mode in current.
- Legacy: the old 1,600-only application.

The internal manifest/hash key supplemental is retained for backward-compatible
expanded URLs. It is not a hidden secondary application. The visible default
is Expanded 10,000. Scientific wording still accurately says the expanded
population is supplementary to canonical P10 evaluation.

## Artifact Structure and Identity

    artifacts/retrieval-inspector/
      README.md
      current.json
      legacy.json
      current/retrieval_inspector_dafc174b9997c59198b3d121/
        index.html
        app.js
        style.css
        manifest.json
        manifest.js
        accepted_manifest.json
        diagnostics.js
        presentation.json
        artifact.json
        asset_binding.json
        browser_validation.json
        assets/ -> validated relative external asset directory
        browser screenshots
      legacy/retrieval_inspector_c612a074a9211c222eb9a811/
        -> ../retrieval_inspector_c612a074a9211c222eb9a811
      retrieval_inspector_c612a074a9211c222eb9a811/
        original immutable legacy files

The new HTML is a real local application, not an external HTML redirect or
a placeholder pointer. Core scripts, styles, both gallery manifests, accepted
diagnostic display data and binding metadata are local.

Identity binds implementation hashes, authority and acceptance, accepted
inspector manifest, ranking manifest, diagnostic hash, union/embedding manifests,
fixed query contract, asset manifest and the Expanded default contract.
It contains no timestamps, temporary paths or browser execution order.
Placement-specific asset-link metadata is separate from the identity preimage.
A repeat --build-current resolved to the same final identity and reused the
browser-validated package.

current.json includes role, current ID, relative entry path, acceptance ID,
10,000 gallery count, expanded default, ten queries, eight models, 3,622 assets
and manifest hashes. Its SHA-256 is
bfc3fac3c2a09552a69635463735bf5843b6f29d8c8c5be411fe4afcfe3c7447.

legacy.json records legacy ID, alias/original paths, acceptance and every core
file hash. Its SHA-256 is
f512ec66d0a810c29a45643254c3a33c62708e5fcdf82f4cbec14c790a5f6e26.

A preliminary local package was superseded during implementation by the final
version after adding missing-package reconstruction. Only current.json selects
the final ID; earlier generated versions do not change scientific evidence.

## Asset and Storage Policy

The current package has **18,646,269 local bytes**, including browser screenshots.
It reuses **3,622 accepted scene assets**, totaling **1,349,618,705 bytes**, through
a relative directory symlink. Each asset is validated against the accepted hash.
No scene asset was copied, rewritten or rendered. Browser loading remains lazy
and deduplicated by scene ID.

The local assets/ link resolves to:
/mnt/hdd002/dhnyu/fusedata/retrieval_data/reduced/retrag_29e75a5e81df82e0c3d93783/inspector/assets

No tensors, geometry cache, full scene cache, embedding arrays or full ranking
Parquets were copied. Only browser-needed manifest/rank-band/diagnostic data
were packed. accepted_manifest.json preserves the original scientific inspector
manifest bytes separately from the current presentation manifest.

The accepted data mount remains a runtime requirement for scene assets.
Moving the workspace/mount can require rebinding the placement-specific link.
On another checkout, rebuilding also requires the preserved legacy application
and accepted mounted evidence; missing inputs fail closed.

Heavy generated packages and external data remain untracked. Only small
current/legacy metadata, legacy alias, documentation, source/tests and this
report are committed.

## Actual Local Browser and Regression Validation

Chromium 148.0.7778.96 opened the actual new repo-local index.html.

| Check | Result |
|---|---|
| Desktop default Expanded 10,000 / 9,999 standard candidates | PASS |
| Mobile default Expanded 10,000 | PASS |
| Canonical toggle / 1,599 standard candidates | PASS |
| Expanded query/model/setting states | 160 PASS |
| Canonical comparison query/model/setting states | 160 PASS |
| Additional mobile states | 32 PASS |
| Rank/ID/similarity/distance/source/candidate-count readback | PASS, accepted Parquets and manifests |
| Band entries across both galleries | 9,920 checked |
| Diagnostic record bindings | 160 PASS |
| Required scene assets | 3,622 present, missing 0 |
| Console errors / page errors / failed requests | 0 / 0 / 0 |
| Broken links | 0 |
| URL/hash restore and gallery state retention | PASS |
| Model/query/non-local changes and selected bands | PASS |
| Vector/raster controls and common DEM scale | PASS |
| Legacy actual browser: 1,600-only, 1,599 candidates, no gallery selector | PASS |
| Python tests | 19 passed in 13.18 seconds |
| Python parse / JavaScript syntax | PASS, four Python files and node --check |
| JSON validation | PASS, eight local JSON files |
| git diff --check | PASS |

Desktop 1600x1100 and mobile 390x844 default screenshots were visually inspected.
The stability panel, source labels and five-column maps are present and readable.
Mobile retains horizontal scrolling. Screenshots and browser_validation.json
are in the current package, including default_desktop.png, default_mobile.png,
canonical_desktop.png and supplemental_desktop.png.

The regression suite specifically rejects a default CLI resolving to legacy,
current.json pointing to legacy or carrying a canonical default, identical
legacy/current IDs, missing 10K controls, and a non-expanded current manifest.
It also checks the real local files, local core scripts, asset indirection and
legacy alias. Existing canonical drawing/summary and URL tests pass.

Test invocation:

    PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=python:tools pytest -q tests/python/test_retrieval_inspector.py tests/python/test_retrieval_gallery_browser.py tests/python/test_retrieval_inspector_presentation.py tests/python/test_retrieval_gallery_ranking.py tests/python/test_retrieval_inspector_current.py

No R or target definitions changed. Scientific targets, tar_make, and dependency
network regeneration were not run or required. This task did not refresh the
external presentation.

## Scientific Preservation

Before/after audit: **22,604 protected files byte-identical; changed files 0**.
This covers the historical protection set, original legacy application and
external accepted retrieval/presentation evidence included in the snapshot.

Evidence receipts under /mnt/hdd002/dhnyu/fusedata/runtime/retrieval_gallery:
- current_promotion_before_20260906.json
- current_promotion_preservation_20260906.json

Baseline receipt SHA-256:
223a993f36ad50b8d4cdad5ac1887247829ffbb1cb86233d035e8f3934b202a6.

P9/P10/P11 acceptances, 10K ranking order, embeddings, scene IDs/cache, query
identities, similarity definition and 2 km threshold remain unchanged.
Dissertation status remains clean.

## Prohibited-Work Counts

| Activity | Actual |
|---|---:|
| Training | 0 |
| Fine-tuning | 0 |
| New scene generation | 0 |
| New embedding inference | 0 |
| Scientific reranking | 0 |
| Checkpoint reselection | 0 |
| Model reselection | 0 |
| P9/P10/P11 rerun | 0 |
| Downstream fitting | 0 |
| Dissertation mutation | 0 |

Also zero: scientific acceptance mutation, new scene rendering, canonical metric
recomputation and qualitative analysis. Synthetic unit tests do not publish
scientific rankings.

## Completion Boundary

All promotion gates passed. The current command and pointer resolve to the
actual repo-local Expanded-default application; explicit legacy access preserves
the old application. Commit/push includes only this work's source, tests,
documentation and small discovery metadata. No qualitative analysis or
dissertation writing is executed.
