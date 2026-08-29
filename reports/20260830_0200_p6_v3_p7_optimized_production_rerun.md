# P6 Layout v3 Recovery and P7 Optimized Production Rerun

## 1. Verdict

`P6_V3_P7_OPTIMIZED_PRODUCTION_PASS_PUSHED`

The P6 geometry layout defect was corrected with an incompatible layout
`3.0.0`, the old layout `2.0.0` is rejected at the P6 batch-layout boundary,
and a new deterministic P7 authority was trained once from initialization on
two RTX A6000 GPUs. The run ended by the approved validation-only early
stopping rule at epoch 185 (1,480 optimizer updates). All acceptance,
determinism, schema, no-op, immutability, and non-execution gates passed.

## 2. Repository State

- Starting Fuse commit: `7b5005730a52a8e968e128231a1ff5cca461caf9`
- Branch: `reduced`
- Dissertation authority: `109355b3d744248ca14749c5f74511537970d660`
- P6 implementation commit: `9d4766b` (`Implement P6 geometry layout v3`)
- P7 production source commit: `2f1bc1405f2f56c11230079ef9b4150b7040fdd3`
  (`Implement optimized P7 production recovery`)
- Final report publication commit: the final pushed `reduced` HEAD containing
  this report; the terminal execution record reports its exact SHA.
- Source evidence patch SHA-256:
  `3752ae954d95a94b9bb99fc59efce527b6681afc9a60978a52dba51b8f0f43fe`
- Target network SHA-256:
  `58d2f2977adc912cede6b231f2f1a742e34c7e51fb0dce830a96ccfb3d5972e8`

No P3, P4, P5, superseded P6/P7, checkpoint, or user-owned artifact was
overwritten. Runtime payloads, caches, checkpoints, targets-store objects,
logs, and credentials are not tracked by Git.

## 3. P6 Geometry Layout 3.0.0

The defect came from storing road-part coordinates and duplicated polygon-ring
coordinates in one coordinate array while recording the part terminal offset
before appending rings. `ragged_collate()` treated that terminal as the full
sample terminal, allowing a preceding scene's ring tail to enter the next
scene's first road interval.

Layout `3.0.0` separates:

- `part_coordinates_xy_m[_scientific]` with `part_coordinate_offsets`;
- `ring_coordinates_xy_m[_scientific]` with explicit ring start/end pointers;
- per-sample part and ring terminals during collation;
- independent range validation for each storage.

Production validators enforce `0 <= start <= end <= corresponding storage
length`, source byte equality, collate/decollate byte equality, and context-
independent scene boundaries. The P6 reader raises an explicit incompatible-
layout error for `2.0.0`, missing versions, and unknown major versions. Old
caches are not converted or relabeled.

### Defect Evidence

- Candidate: `augv_0c7fb311e3c582cf84136d90`
- Scene: `scn_28a3bd91311d83e99834f532`
- Correct coordinate count: 28 total, including 6 coordinates in the first
  road part.
- Historical contaminated count: 33, caused by a preceding 5-coordinate ring.
- Production v3 result across canonical, reverse, random, rank, worker, and
  neighboring-scene contexts: 28 only.
- Historical 33-coordinate observations: 0.
- Wrong declared ranges: 0.
- Fourier-input corruption: 0.
- Candidate multi-content identities: 0.
- Input mutations: 0.

The production recheck covered the established 100-update,
6,400-materialization shape. P3/P4/P5 source bytes remained unchanged.

## 4. New P6 Lineage

| Artifact | Identity |
|---|---|
| Model authority | `dma_d1b7fb09b063740c38fdb7ac` |
| Preprocessing contract | `ppc_d09fd3a54fcef0e58769e894` |
| DataLoader acceptance | `dla_d7bcbaab25a9666256ce38ae` |
| CPU smoke | `dcs_c07e56c3c7fba40543aea7d4` |
| Aggregate acceptance | `mda_b07032bd970d101ec1da7a4b` |

The aggregate acceptance records `geometry_layout_version=3.0.0`,
`old_layout_2_rejected=true`, 12 CPU smoke cases, 934,420 trainable parameters,
0 non-trainable parameters, and the unchanged P3/P4/P5 parents.

The first explicit `model_data_acceptance` selection built six P6 targets and
skipped 999. The immediate repeat skipped all 1,005 reachable targets with
builds 0 and rewrites 0.

## 5. P7 Authority and Configuration

| Artifact | Identity |
|---|---|
| Supplement | `p7-deterministic-training-v1` |
| Training authority | `p7a_99b71dcd4fc17e00b1cad76e` |
| Run | `p7run_d5947018e270c55ae60f2696` |
| Training trace | `p7tr_d6357680f0f808ebde0eaaf5` |
| Selector | `p7sel_6d88dcb2061f7551e743ba82` |
| Execution | `p7exe_f7fd5c2530b8b481f0fccea1` |
| Acceptance | `p7acc_3c78cc0e85b93aec6a0cc02c` |

The authority binds source commit `2f1bc140...`, P6 acceptance
`mda_b07032bd970d101ec1da7a4b`, P3 cache
`oscache_c89fa07e3d6cb1819a7994a6`, revised P4 bank/K8
`augbank_252ce67e6d74679b02871e57` / `abi_66dfe52602ffe442336685e0`,
and P5 authority/acceptance `fqa_89741b3e7b3ff7e44597ca67` /
`fqaac_9151e9e0a34525ac8ecdb444`.

Scientific settings remained unchanged: prototype train/validation 256/32,
global/rank batch 32/16, world size 2, FP32, deterministic algorithms,
AdamW, exact warm-up/cosine scheduler, clipping 1.0, EMA 0.999, queue 8,192,
temperature 0.1, exclusion distance 750 m, and modality masking 0.30.

The selected exact execution path used immutable corrected geometry cache,
packed evidence materialization, deterministic one-batch CPU look-ahead,
`find_unused_parameters=False`, DDP bucket 50 MiB, disjoint CPU affinity, and
exact distributed validation. `gradient_as_bucket_view`, static graph, B3
collective packing, branch elision, static InfoNCE, GPU LRU, AMP, TF32, and
compile were not enabled.

## 6. Geometry Cache

- Cache ID: `p7gc_4de4a140d54765f01a30e656`
- Schema/layout: `3.0.0` / `3.0.0`
- Entries: 2,144 (2,048 training, 64 validation queries, 32 galleries)
- Raw tensor bytes: 2,083,895,808
- Disk bytes: 2,093,395,680
- Cold build worker wall: 2,176.04 s (36 min 16.0 s)
- Cache target wall: 36 min 30.9 s
- Manifest SHA-256:
  `0f0cc30ae6f74007ef50e1b3802cd2affb477646f98db3a62a6f07c12d2b3bc3`
- Entry payload size/SHA mismatches: 0/2,144
- Problem-candidate checks: 1 occurrence, 0 wrong observations
- Production rank-0 cache stats: 47,040 hits, 2,096 misses, 0 evictions,
  2,048,921,088 resident bytes.

Every cache entry binds layout, P4/P6 identities, scene/view/profile/role,
source lineage, corrected part/ring content digests, entity order,
configuration, implementation, dtype, shape, and raw tensor checksums. Cache
construction used the corrected online geometry implementation and required
byte-exact readback.

## 7. GPU Gates and Resume

| Gate | Result | Target wall |
|---|---|---:|
| Two-rank DDP initialization | PASS | 12.8 s |
| Single update/optimizer/EMA/queue/checkpoint | PASS | 3 min 29.2 s |
| Two-rank loss/gradient reference | PASS | 11.9 s |
| Exact interrupted/resumed trajectory | PASS | 18 min 22.3 s |

Resume compared uninterrupted four updates with two updates, a full-state
checkpoint, a new two-rank process, and two resumed updates. Scientific trace,
model/EMA, optimizer, scheduler, queue, rank RNG states, and canonical state
digest were exact. Serialization-container bytes were excluded as
non-scientific, as declared before execution.

## 8. Full Training Result

- Full run count: exactly 1
- Termination: validation-only early stopping
- Final epoch/update: 185 / 1,480
- Best epoch/update: 165 / 1,320
- Best validation retrieval loss: 0.04124793782830238
- Best validation margin: 0.4428796172142029
- Latest final step total/scene/IP loss:
  1.659475189 / 1.631376743 / 0.028098445
- Final learning rate: 0.000015299867030334813
- Final queue: valid 8,192, pointer 4,608, enqueue count 94,720
- EMA update count: 1,480
- Best checkpoint: `p7ck_7d25fec7944dc108c5849cd7`
  - payload SHA-256:
    `90cb3b3d819f1cd545df09e20877b8ff832b3f0bf3eea0b77f5bfea496564f6a`
- Latest checkpoint: `p7ck_294f2e926ed88ee63e0bb267`
  - payload SHA-256:
    `ac094723cdaf8fdef9ae3c783552d389a1f71c540be1dab97fa9b7101da23e6c`

All 37 checkpoint manifests passed JSON Schema, size, and SHA validation.
Best/latest checkpoint canonical state digests match their manifests. Each
contains two rank RNG states, full online/EMA/optimizer/scheduler state, queue,
sampler progress, selector state, trace, and parent lineage.

### Five-Epoch Metrics

Training losses are means over the 40 updates ending at each validation event.
Elapsed times are measured between immutable checkpoint publication mtimes;
the first interval includes cold process/cache/view preparation.

| Epoch | Total | Scene | IP | Retrieval | Margin | Elapsed s | Selected | Patience |
|---:|---:|---:|---:|---:|---:|---:|:---:|---:|
| 5 | 6.614596 | 5.365998 | 1.248598 | 0.688088 | 0.131646 | 1859.8 | Y | 0 |
| 10 | 6.440279 | 5.825500 | 0.614779 | 0.542601 | 0.166673 | 189.0 | Y | 0 |
| 15 | 6.009037 | 5.760766 | 0.248271 | 0.364016 | 0.203954 | 87.0 | Y | 0 |
| 20 | 5.675309 | 5.521290 | 0.154019 | 0.276480 | 0.246337 | 50.6 | Y | 0 |
| 25 | 5.251680 | 5.149544 | 0.102137 | 0.241366 | 0.255551 | 35.6 | Y | 0 |
| 30 | 4.903981 | 4.830456 | 0.073525 | 0.176449 | 0.289682 | 29.0 | Y | 0 |
| 35 | 4.617573 | 4.557078 | 0.060495 | 0.140800 | 0.308515 | 23.4 | Y | 0 |
| 40 | 4.354278 | 4.300877 | 0.053401 | 0.139075 | 0.310013 | 22.5 | Y | 0 |
| 45 | 4.115134 | 4.066703 | 0.048430 | 0.124968 | 0.313436 | 18.4 | Y | 0 |
| 50 | 3.906065 | 3.860368 | 0.045697 | 0.094926 | 0.345435 | 21.2 | Y | 0 |
| 55 | 3.698638 | 3.655570 | 0.043068 | 0.092032 | 0.348638 | 18.7 | Y | 0 |
| 60 | 3.527440 | 3.485983 | 0.041457 | 0.084189 | 0.356513 | 18.2 | Y | 0 |
| 65 | 3.377670 | 3.336857 | 0.040813 | 0.079190 | 0.362783 | 18.4 | Y | 0 |
| 70 | 3.243897 | 3.205368 | 0.038529 | 0.068115 | 0.389477 | 20.1 | Y | 0 |
| 75 | 3.094369 | 3.057695 | 0.036674 | 0.067690 | 0.388457 | 17.9 | Y | 0 |
| 80 | 2.974125 | 2.938193 | 0.035932 | 0.066169 | 0.390713 | 20.3 | Y | 0 |
| 85 | 2.869378 | 2.834175 | 0.035203 | 0.070331 | 0.386598 | 18.5 | N | 1 |
| 90 | 2.768660 | 2.734734 | 0.033926 | 0.059461 | 0.408562 | 18.3 | Y | 0 |
| 95 | 2.661344 | 2.627750 | 0.033593 | 0.051108 | 0.417238 | 18.2 | Y | 0 |
| 100 | 2.574333 | 2.541237 | 0.033096 | 0.047734 | 0.429323 | 18.3 | Y | 0 |
| 105 | 2.502573 | 2.469199 | 0.033374 | 0.050771 | 0.423976 | 18.4 | N | 1 |
| 110 | 2.415492 | 2.383106 | 0.032385 | 0.047454 | 0.428663 | 18.3 | Y | 0 |
| 115 | 2.341879 | 2.309734 | 0.032145 | 0.048196 | 0.424442 | 19.7 | N | 1 |
| 120 | 2.281343 | 2.249761 | 0.031582 | 0.050281 | 0.423020 | 19.6 | N | 2 |
| 125 | 2.213096 | 2.182301 | 0.030795 | 0.046241 | 0.428680 | 18.8 | Y | 0 |
| 130 | 2.154294 | 2.123838 | 0.030456 | 0.045368 | 0.435186 | 18.2 | Y | 0 |
| 135 | 2.105713 | 2.075454 | 0.030259 | 0.046962 | 0.433523 | 18.3 | N | 1 |
| 140 | 2.048406 | 2.018566 | 0.029840 | 0.044710 | 0.440662 | 18.4 | Y | 0 |
| 145 | 2.000913 | 1.971076 | 0.029837 | 0.046516 | 0.432544 | 18.3 | N | 1 |
| 150 | 1.955756 | 1.926009 | 0.029747 | 0.045651 | 0.436987 | 18.2 | N | 2 |
| 155 | 1.910278 | 1.880772 | 0.029506 | 0.043226 | 0.439792 | 18.6 | Y | 0 |
| 160 | 1.869285 | 1.840028 | 0.029256 | 0.042365 | 0.442214 | 20.4 | Y | 0 |
| 165 | 1.838604 | 1.809579 | 0.029025 | 0.041248 | 0.442880 | 20.1 | Y | 0 |
| 170 | 1.798282 | 1.769147 | 0.029135 | 0.042585 | 0.440166 | 18.3 | N | 1 |
| 175 | 1.771647 | 1.742661 | 0.028986 | 0.041984 | 0.440971 | 18.3 | N | 2 |
| 180 | 1.741066 | 1.712455 | 0.028611 | 0.043104 | 0.438496 | 18.9 | N | 3 |
| 185 | 1.711033 | 1.682115 | 0.028918 | 0.041951 | 0.441794 | 18.4 | N | 4 |

Epoch 165 remained selected. Epochs 170, 175, 180, and 185 were four
consecutive non-selected validation events, so early stopping triggered exactly
at epoch 185.

## 9. Runtime and Hardware

- GPUs: NVIDIA RTX A6000 x2
- Runtime: Python 3.14.0, PyTorch 2.12.0+cu130, CUDA 13.0,
  cuDNN 9.2.0, NCCL 2.29.7
- Backend/precision: NCCL / FP32
- Production worker wall: 2,841.22 s (47 min 21.2 s)
- `prototype_training_run` target wall: 47 min 37.1 s
- Median update: 0.4603 s
- p95 update: 2.5668 s
- Median throughput: 69.51 scenes/s
- Rank-0 peak allocated: 4,257,031,168 bytes
- NVML peak VRAM: GPU0 10,223 MiB; GPU1 9,595 MiB
- Full-worker time-weighted utilization: GPU0 18.72%; GPU1 23.71%
- Zero-utilization samples: GPU0 4,120/5,704; GPU1 3,874/5,704

The utilization average includes the long cold view/tensor materialization
period. After the first validation, the five-epoch wall fell from 1,859.8 s to
189.0 s, then converged to approximately 18-20 s after the working set became
resident. The bounded D6 experiment measured 0.082 s rank-wall imbalance,
backward/DDP mean 82.7 ms, and exact parity. Production did not persist
per-rank NCCL call counts or phase timers; this is a runtime-observability
limitation, not an acceptance failure. P2P and IB remained disabled.

Compared with the prior defective P7 worker wall of 4:42:15.6 (16,935.6 s),
the corrected production worker wall is 83.22% shorter (5.96x faster). Adding
the one-time 2,176.04 s cold cache build gives 5,017.27 s (1:23:37.3), still
70.37% shorter. Including all one-time GPU gates and target orchestration, the
two explicit production stages took about 1:46:55; these gate costs do not
repeat when the accepted targets are current.

## 10. Distributed Validation

Every event used exactly 64 fixed P5 v2 validation queries and 32 P3 gallery
originals. Records were deterministically sharded by batch index, embeddings
and IDs were gathered in fixed order, and selector inputs were computed once
from canonical order.

- Events: 37
- Coverage per event: 96
- Missing per event: 0
- Duplicate per event: 0
- Query/gallery mapping errors: 0
- Evaluation query/gallery executions: 0
- Selector: retrieval loss, then margin within the approved threshold, then
  earlier epoch
- MRR/HIT values: diagnostic only; never used by selector or patience

## 11. Explicit Target Execution and No-op

P6:

- First explicit final selection: 6 completed, 999 skipped.
- Immediate repeat: 1,005 skipped, builds 0, rewrites 0.

P7 cache:

- Explicit cache target: 1 cache target plus five required authority/reference
  targets completed, one skipped; cache target wall 36 min 30.9 s.

P7 final acceptance:

- First explicit final selection: 9 completed, 7 skipped; total target wall
  1:10:08.2.
- Immediate repeat: 16 skipped, builds 0, GPU execution 0.
- No-op comparison: all 2,230 new cache/run/checkpoint/acceptance files had
  identical path, size, mtime, and key manifest checksums.
- Final accepted P7 ancestry outdated count: 0.
- Two legacy prototype plan/dataset targets outside the final ancestry remain
  outdated and were not executed.

## 12. Tests and Schema Validation

- Focused P6 layout tests: 16 passed.
- Pre-production full Python: 171 passed.
- Post-production full Python: 171 passed in 15.08 s.
- Full R suite: PASS with exactly three documented legacy skips.
- R parse: 6 changed files PASS.
- Python AST, YAML, JSON parse: 28 changed files PASS.
- Actual P7 JSON schemas: 6/6 PASS.
- Checkpoint schemas/checksums: 37/37 PASS.
- `targets::tar_validate()`: PASS before and after production.
- `git diff --check`: PASS.
- Staged `git diff --cached --check`: PASS at publication gate.
- Target-network tests: PASS.

The only R skips were the two documented legacy zero-compute recovery fixtures
and the superseded pre-reduced I19 augmentation contract fixture.

## 13. Immutability and Non-execution

The pre/post accepted-artifact inventory covered 4,035 files. Missing files: 0;
path/size/mtime/SHA changes: 0. The targets store retained the same 1,602 file
paths. No pre-existing object file changed; only the four expected active
metadata files (`crew`, `meta`, `process`, `progress`) changed through normal
targets execution.

- P3 payload mutations: 0
- Revised P4 payload/authority mutations: 0
- Revised P5 payload/authority mutations: 0
- Superseded P6/P7 artifact overwrites: 0
- P8/P9 target executions: 0
- Evaluation executions: 0
- Maintenance executions: 0
- Full 2,421-scene training executions: 0
- Unauthorized GPU operations: 0
- Remaining GPU processes/locks after completion: 0

## 14. Superseded P7

The former P7 authority `p7a_ee0cafa07978d7d2b168ef27`, acceptance
`p7acc_d9fa1683bbccd4de7f2636b2`, best checkpoint
`p7ck_9e557e1440253ac52fac4197`, and latest checkpoint
`p7ck_f01b68dde9837780feff5c98` remain immutable. Machine-readable authority
provenance marks them deterministic historical artifacts affected by P6
geometry layout `2.0.0`, superseded, blocked from research/evaluation/downstream
use, and prohibited as a resume or parent source for the new run.

## 15. Changed Files

The recovery changes are limited to P6/P7 source and orchestration, configs,
schemas, focused tests, blueprint evidence, regenerated target network, the
layout verifier, and this report. No runtime payload is tracked.

Key files include:

- `python/p6_data.py`, `python/prototype_encoder.py`
- `python/p7_geometry_cache.py`, `python/p7_training.py`
- `scripts/p6_model_dataloader.py`, `scripts/p7_prototype_training.py`
- `R/research_model_dataloader.R`, `R/research_prototype_training.R`
- `targets/research_prototype_training.R`
- `config/p6_model_dataloader.yml`, `config/p7_deterministic_training.yml`
- P6/P7 JSON schemas and focused Python/R tests
- `tools/verify_p6_geometry_layout_v3.py`
- `blueprint/targets_implementation_blueprint.md`
- `artifacts/targets-network/targets-network.html`

## 16. Warnings and Next Action

The main operational cost is cold process-local tensor/view materialization:
the first five epochs took 31 minutes, while the final five-epoch blocks took
about 18-20 seconds. The immutable Fourier cache is complete and effective,
but a future production-shape input-cache design should address this cold path
without changing scientific identity. Production-level per-rank phase and NCCL
timing should also be persisted in a later runtime-only observability update.

Single recommended next action: formally audit the new P6 v3/P7 acceptance as
the only admissible parent before authorizing any P8 representation analysis.

## 17. Prompt Summary

The approved work unit required formal integration of the verified P6 geometry
layout correction, publication of incompatible layout/schema `3.0.0`, exact
D6/O6 execution optimizations, new P6 acceptance, a new P7 authority and cold
cache, exactly one full two-GPU deterministic P7 run, independent acceptance,
no-op and immutability validation, then commit and push to `origin/reduced`.
