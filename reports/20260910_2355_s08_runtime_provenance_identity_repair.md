# S08 runtime provenance identity repair

## Scope

- Execution: 2026-09-10 23:46-23:55 KST
- Input HEAD: `fd5e53a3997e64f513d5d3dea8e9d6a4ad323abb`
- Implementation commit: `2057e8ae33ead9dbf593cbda1ad89fbe9a3a6f74`
- Branch: `reduced`
- Purpose: separate S08 scientific-plan identity from mutable S09 runtime implementation provenance while retaining fail-closed scientific and lineage validation.
- Prompt summary: keep accepted S08 plan `s08plan_7cd58ffb65db3d43fd3fa234` byte-compatible, move runtime traceability to S09 authorities, preserve the prepared cache, validate comprehensively, commit, push, and do not train.

## Original defect

`s08_contract_hashes()` included `python/training_worker.py`, `python/training_support.py`, and `python/training_finalization.py` in the serialized S08 `contract_hashes.implementation_sha256`. The S09 scene-center/profile runtime repair therefore changed the S08 candidate from:

- accepted: `s08plan_7cd58ffb65db3d43fd3fa234`
- incorrect runtime-drift candidate: `s08plan_ebaaa36be6782e5f24a14905`

The only recursive difference was the implementation digest changing from `039611df994d9d1663441d6eba0cf0e55131f974b20de6ba18258f4ebc8510b8` to `769dd2917c0c7fa19c5f51ee38c9d473f43223e93937ef2778e93642025b65c9`. The immutable publisher correctly refused to overwrite the existing artifact.

## Identity input classification

| Input | Classification | Resulting treatment |
|---|---|---|
| scientific revision token and P0 authority/hash | `LINEAGE_IDENTITY_BEARING` | retained in S08 digest |
| P1/P2/P3/P4/P5/P6 acceptance IDs and P3 cache ID | `LINEAGE_IDENTITY_BEARING` | retained in S08 digest |
| 11 OFAT rows | `SCIENTIFIC_IDENTITY_BEARING` | retained and exact-validated |
| 17 comparison definitions | `SCIENTIFIC_IDENTITY_BEARING` | retained and exact-validated |
| serialized training inheritance contract | `SCIENTIFIC_IDENTITY_BEARING` | retained with independent canonical hash |
| serialized checkpoint-selection contract | `SCIENTIFIC_IDENTITY_BEARING` | retained with independent canonical hash |
| `python/current_methodology.py` | `SCIENTIFIC_IDENTITY_BEARING` | remains an S08 source because it constructs experiment definitions |
| `python/training_worker.py` | `OPERATIONAL_PROVENANCE_ONLY` | removed from S08 identity; retained in S09 runtime hash |
| scene-center/profile routing | `OPERATIONAL_PROVENANCE_ONLY` | S09 authority/run provenance only |
| training progress logging | `OPERATIONAL_PROVENANCE_ONLY` | S09 authority/operator provenance only |
| GPU locks and controller/operator | `OPERATIONAL_PROVENANCE_ONLY` | S09 execution provenance only |
| prepared-cache reader/runtime routing | `OPERATIONAL_PROVENANCE_ONLY` | S09 cache/runtime provenance only |
| unrelated evaluation/downstream/maintenance code | `IRRELEVANT_TO_S08` | excluded |

## Repair

Added `config/s08_plan_identity.yml`, which declares the current v3 scientific-plan compatibility contract and its accepted implementation digest. `s08_contract_hashes()` now:

1. fail-closed validates that configuration;
2. hashes the fully serialized training inheritance contract;
3. hashes the fully serialized selection protocol;
4. uses the stable v3 scientific-plan compatibility digest for the existing `implementation_sha256` schema field.

The S08 source registry no longer includes S09 worker/support/finalization runtime modules. Mutable operational provenance is not serialized into the immutable S08 artifact, avoiding bytes that change while a plan ID remains fixed.

S09 traceability remains intact. `training_campaign.scientific_implementation_hash()` still hashes the current model/training runtime implementation, including `training_runtime_inputs.py` and `training_worker.py`. Current hash:

`b433a0236f58226330333bf0b34353a686c911dada074a78183389c35fe81876`

Tests prove changing this runtime hash changes both S09 authority and run identities.

## Existing artifact compatibility

A disposable S08 publication was built from the current production-store P0-P6 targets and current source tree.

- plan ID: `s08plan_7cd58ffb65db3d43fd3fa234`
- content SHA-256: `7cd58ffb65db3d43fd3fa234fb5c6b7489640ea7e1e2a1bda76082f3ac3e81e3`
- serialized file SHA-256: `74ae70958b96dd663d300c6f7441a0653b1a7c5066d6e1bfe9b4b459d7781789`
- OFAT configurations: 11
- comparison definitions: 17
- no IP/reconstruction: PASS
- current P0-P6 lineage: exact
- selection protocol: exact
- byte comparison with existing production S08 artifact: identical

The production artifact was not overwritten or modified. A subsequent separately authorized normal S08 refresh will evaluate the changed source target, discover identical bytes, and reuse the existing immutable artifact without collision. The expected post-refresh main-store outdated set is empty.

## Scientific invalidation protection

Focused regression tests retain fail-closed behavior for:

- scientific revision or any P0-P6 lineage identity change;
- training objective/queue/gradient/masking/IP/reconstruction changes;
- selection primary metric, threshold, tie-break, patience/minimum-delta contract changes;
- OFAT inventory/content changes;
- comparison inventory/content changes.

Separate tests prove S09 worker runtime changes do not affect S08 contract hashes or plan identity.

## Prepared cache preservation

- cache ID: `s09cache_dc4e9e271e40ffe8ae17967c`
- acceptance ID: `s09ca_e2a1882eb206e1b5c930ddd5`
- entries: 80,472
- manifest SHA-256: `269f05b255cfaa0df8b21b17914d3475c65f4f3e2d672fd2669b927a00699370`
- acceptance file SHA-256: `201a79ddc9f858d7829518bcd96dc84d5bcfa85dea6cecef345534dda8fc7bf4`
- cache rebuilt: NO

S08 scientific identity and cache parent identity remain unchanged.

## Validation

- `git diff --check`: PASS
- R parse: PASS, 57 files
- Python compile: PASS
- config/schema parse: PASS
- focused S08 tests: PASS, 36 expectations
- focused S09 campaign tests: PASS, 10 tests
- full Python pytest: PASS, 447 tests
- `_targets.R` manifest/validate: PASS, 61 targets
- `_targets_training.R` manifest/validate: PASS, 27 targets
- disposable S08 build/schema/contract validation: PASS
- production S08 executed after repair: NO
- formal training/GPU/DDP executed: NO
- production cache rebuilt: NO
- target-store metadata manually edited: NO

The full R suite passed all implementation/scientific tests but reported one environment-dependent network-status assertion: the retained failed `s08_current_experiment_plan` error record is also currently outdated, while network rendering gives `error` precedence and the assertion compares that display count with raw `tar_outdated()`. The isolated target-network test reproduces only this status-overlap failure. The store was not edited to hide it. It will naturally disappear from live currentness after the separately authorized successful S08 refresh.

## Repository

- implementation commit: `2057e8ae33ead9dbf593cbda1ad89fbe9a3a6f74`
- implementation push to `origin/reduced`: PASS
- source hot-patch during training: NO; no training was running

## Final verdict

`PASS_S08_RUNTIME_PROVENANCE_IDENTITY_REPAIRED`

Next separately authorized action: refresh only `s08_current_experiment_plan`, verify the accepted ID remains `s08plan_7cd58ffb65db3d43fd3fa234`, verify main-store `tar_outdated()` is empty, and only then resume the guarded S09 campaign.
