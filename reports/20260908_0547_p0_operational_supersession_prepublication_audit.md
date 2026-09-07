# P0 operational supersession prepublication audit

## Purpose and scope

This prepublication audit authorizes an operational-only P0 methodology authority supersession for the current-lineage source cleanup. It covers implementation source-path and filename normalization only. It does not authorize any dissertation, methodology, scientific contract, parameter, artifact-content, or target-execution change.

## Execution context

- Audit time (Asia/Seoul): 2026-09-08 05:47
- Fuse input commit: `60f6b4affce9a46c1d6c06104571bc27bb3f0889`
- Fuse branch: `reduced`
- Dissertation commit: `cbb824f19be8355296603f8426ac241ce587ddcc`
- Predecessor authority: `mta_03e8d7f42fe2018237f3fcde`
- Predecessor aggregate record hash: `45c7d018a8d6b959e30a9b8ca5c5279c2fe9177f397dd9b5e872e12a434fd5e8`

## Required publication checks

Publication is permitted only when all of the following checks pass:

1. The dissertation commit remains exactly `cbb824f19be8355296603f8426ac241ce587ddcc`.
2. The ordered set of ten module names is unchanged.
3. Every module's canonical scientific SHA-256 is byte-for-byte identical to the predecessor.
4. The aggregate scientific-contract SHA-256, computed only from ordered module names and hashes, is identical before and after.
5. `changed_modules` is empty and all ten modules are declared unchanged.
6. The predecessor authority remains immutable.
7. Only implementation provenance, source paths, schemas, and cleanup metadata may differ.

Any failure is a publication blocker.

## Scientific invariants

The cleanup preserves the current dissertation contract: 10,000 off-grid scenes split into 1,000 validation and 9,000 evaluation scenes; `D_off = 50 m`; `d = d_c = 128`; symmetric scene-level contrastive training without information-preservation loss or reconstruction decoders; 11 OFAT configurations; 17 compared models; and the current A1-A5, B1-B9, augmentation, relation, evaluation, and downstream semantics.

## Operational changes under review

- Responsibility-oriented R and Python filenames replace historical P-number and prototype filenames.
- A canonical source registry replaces duplicate target/test source-order lists.
- Obsolete executable prototype, recovery, P8, and P9-v1 source is removed.
- Retirement evidence is detached from obsolete executable source-file hashes.
- P0 records a dedicated scientific-contract hash separate from implementation provenance.

## Verdict

`APPROVED_CONDITIONALLY_FOR_OPERATIONAL_ONLY_PUBLICATION`

The authority publisher must fail closed unless dissertation identity and all scientific module hashes match the predecessor exactly.

## Input prompt summary

Retire the audited 60 legacy-bound main-DAG targets, remove obsolete current-source execution paths, normalize the current reduced-lineage source layout, preserve immutable historical evidence, and publish an operational-only P0 supersession only after proving that every scientific module hash is unchanged.
