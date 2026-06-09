# Documentation Refactor Report

Generated: 2026-06-09

## Files Modified

- `README.md`
- `research_vision.md`
- `CONTEXT.md`
- `docs/documentation_refactor_report.md`

`AGENTS.md` was not modified.

## Sections Added

`README.md`:

- Added `Further Reading` section that points to:
  - `research_vision.md`
  - `CONTEXT.md`
  - `AGENTS.md`
- Revised project overview to state that spatial scene similarity evaluation is
  the long-term goal and object/building embeddings are intermediate
  representations.

`research_vision.md`:

- Added a navigation note in `Overview` pointing to `CONTEXT.md` for
  implementation history, experiments, design decisions, and current status.

`CONTEXT.md`:

- Added `Executive Summary`.
- Added `Relationship to Research Vision`.
- Added `Project Memory Frame`.
- Added a future-priority section for scene embeddings and similarity
  evaluation.

## Sections Removed or Reduced

`README.md`:

- Reduced theoretical motivation and detailed conceptual discussion that now
  belongs in `research_vision.md`.
- Kept only a concise architecture diagram, major datasets, current status, and
  repository layout.

`CONTEXT.md`:

- Reduced the duplicated research-vision opening that previously framed fused
  building embeddings as the final target.
- Reframed building/object embeddings as intermediate infrastructure for
  scene-level representation.
- Preserved experimental findings, implementation history, data asset summaries,
  design decisions, open questions, and future milestones.

## Rationale

The documentation now follows a clearer responsibility hierarchy:

- `README.md`: short project landing page.
- `research_vision.md`: dissertation-level motivation, theoretical framing,
  research questions, object-to-scene hierarchy, and long-term scientific
  vision.
- `CONTEXT.md`: long-term project memory, completed work, experimental findings,
  design decisions, infrastructure evolution, unresolved issues, and current
  status.
- `AGENTS.md`: operational rules and working conventions.

The main consistency correction was to align all three documents around the
same scientific target:

- the ultimate goal is spatial scene similarity evaluation;
- object embeddings are intermediate representations;
- scene embeddings are the higher-level target;
- geometry, semantics, and visual context are the multimodal foundation.

## Remaining Documentation Issues

- Some older Street View documents still describe image acquisition as not yet
  launched, even though the 40,000-panorama acquisition has completed and passed
  validation.
- Some large-scale Geo2Vec reports and READMEs still refer to older output roots
  rather than `~/fusedata/geo2vec_large_scale`.
- Epoch-saturation Geo2Vec artifacts exist, but no final report was recovered.
- The semantic embedding and visual embedding plans remain conceptual and need
  production reports once implemented.

## Recommendations for Future Maintenance

- Update `research_vision.md` only when the theoretical framing, research
  questions, or dissertation-level direction changes.
- Update `CONTEXT.md` whenever an experiment changes project status, a major
  dataset becomes canonical, or a design decision changes.
- Keep `README.md` short and avoid turning it into a method report.
- Add links from future experiment reports back to `CONTEXT.md` when they change
  the project memory.
- When a final semantic graph, visual embedding table, fused object embedding,
  or scene embedding is created, update all three top-level documents for
  consistency.
