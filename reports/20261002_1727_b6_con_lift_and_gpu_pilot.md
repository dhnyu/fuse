# Accepted-CON child lift and bounded B6 update pilot

Created 2026-10-02 17:27 Asia/Seoul. Entry branch `B6`, HEAD `1172a79ea35a9cb0fb5253e27d34ebfec4eff6df`, upstream `origin/B6`, ahead/behind 0/0, clean. Input request: close the off-support CON gate under the explicitly supplied source-chain policy, validate the complete S50 paired inputs, then run five engineering updates per arm on two GPUs only after input acceptance. Full training remains unauthorized.

## Method and authority

Only `B6-original`, `B6-S50-G`, `B6-S50-Ppre` are present. Accepted d=d_c=256, heads=4, relation layers=3, dropout=.2, K_aug=8, intensity=1, EMA=.999, peak LR=.001, global batch=32, world size=2, queue=8192, temperature=.1, negative exclusion=750 m and modality masking=.30 remain fixed. Optimizer, scheduler, objective, fixed population, shared root seed 1629790839, and accepted checkpoint-selection contract are inherited from the previous method contract. No scale or arm is retuned.

Latest dissertation methodology and targets blueprint were inspected read-only. The dissertation's visible-node CON description differs from accepted P4 outside-node behavior; the user explicitly authorized preserving accepted connectivity through **logical inheritance**, not changing canonical CON or asserting physical child incidence. Original retains accepted relations byte-for-byte. The experimental extension is therefore explicit.

Policy: **`accepted_parent_con_nearest_chain_child_v1`**. Full text and SHA256 reside in `python/b6_con_lift.py` and each new method contract. CON, input, prepared and pilot identities bind this policy; no old identity is relabeled.

## Exact chain rule

`source_run` reads the original source geometry WKB already preserved in accepted P3. All occurrences of observed part endpoints on the original polyline are enumerated. A source run is accepted only if directed length, support and **ordered Fréchet distance** match within 1e-7 m (length additionally permits 1e-10 relative tolerance). This resolves closed-run direction without guessing from nearest Euclidean distance. A genuinely ambiguous run fails closed. F/T coordinates must match original source endpoints.

`materialized_chainages` preserves recorded jitter vertex correspondence or requires a unique monotone original-vertex subsequence for simplification. Accepted geometry itself is certified by the previous post-bank replay adapter. Chainage at a materialized cut is interpolated between its certified original-source vertex positions using the fractional distance along the materialized segment. This is a provenance mapping, not a claim that jittered points physically lie on the original source line.

`subdivide_receiver` cuts within each accepted materialized part, preserving bends and positive residuals, with a 50 m maximum to numerical tolerance. True source-node contacts are cut before regular subdivision. Every child retains receiver semantic ownership, exact original source parent/component, source chain interval, materialized chain interval, ordinal, deterministic child ID and RNG ID. No component or distinct source link is bridged. Length and Hausdorff support preservation are checked for every part.

`select_child` first restricts to the exact original parent. If a source node touches materialized support, only touching children qualify; ties prefer the source-direction terminal endpoint, then lower source chainage/component/ordinal/stable ID. For off-support nodes, minimize along-source distance from node chainage to the child's source interval; ties use component/visible-run order, lower chainage, ordinal and stable ID. The observed inventory has no unresolved or initial distance ties; boundary-tie fixtures explicitly test the terminal rule. Euclidean distances are used only to certify geometric support, never to replace source-chain ranking.

`lift_accepted_parent_con_to_children` enumerates accepted receiver-pair/shared-original-node/source-parent-pair causes. Each cause selects exactly one child per side, emits the child pair in both directions, then collapses duplicate pairs into relation masks. Donor parts cannot steal another original parent's CON. Synthetic cuts have no node identity and cannot generate CON. Logical incidence is recorded separately from physical support in compact cause tables and prepared-payload incidence metadata.

## Complete census

CON design ID: `b6con_032b560f2d826f3177854e91`. The full inventory contains 19,368 training views, 2,000 validation queries and 1,000 original validation galleries. Counts below are aggregate unordered parent/child pairs or causes over scene/view identities, unless labelled endpoints.

| Measurement | Value |
|---|---:|
| Input views | 22,368 |
| Accepted parent CON pairs | 1,150,947 |
| Accepted receiver-pair/source-node causes | 1,151,817 |
| Receiver-node causes: physical / logical | 1,126,988 / 24,829 |
| Refined original-source-parent-pair/node causes | 1,186,019 |
| Both endpoints physically on support | 1,161,189 causes |
| At least one logical off-support endpoint | 24,830 causes |
| On-support endpoint mappings | 2,322,378 |
| Off-support endpoint mappings | 49,660 |
| Unique child CON pairs | 1,185,949 unordered / 2,371,898 ordered |
| Causes collapsed onto an existing child pair | 70 |
| Ambiguity / missing-lineage failures | 0 / 0 |
| Ties before / after deterministic resolution in census | 0 / 0 |
| Same-original-parent CON / synthetic-node CON / false broadcast cliques | 0 / 0 / 0 |
| Original-source-parent pairs with distinct nodes and >1 child pair | 471 |
| Receiver pairs with distinct nodes and >1 child pair | 807 |
| Off-support chain distance min / max | 0.017020446 / 622.754336540 m |
| Segmented child entities | 1,523,834 |
| Zero-road inputs | 3,136, unchanged |

The 870 receiver pairs with multiple distinct node IDs include 63 whose causes collapse onto one child pair; 807 actually produce multiple child pairs from distinct nodes. The 1,151,817 accepted receiver-pair/node causes expand to 1,186,019 distinct original-source-parent-pair/node causes. Of the receiver/node causes, 33,253 map to more than one child pair because different absorbed original parents retain their own real-node lineage. Minimality is one pair per **exact original-source-parent pair and original node**, not broadcasting to sibling children. This preserves the requested independent parent ownership under absorption; these are distinct source-parent incidences, not extra synthetic-node causes. Do not sum relation-bit counts to obtain graph edge count.

The first implementation used undirected Hausdorff support alone and correctly refused 111 views with two apparent source runs. Inspection showed closed/retracing geometry where original ordered vertices resolved direction. Ordered Fréchet verification was added with a fixture; the complete rerun passed. The first blocked content identity remains a diagnostic artifact and is not an accepted method. No S50 input or GPU execution used it.

## Required counterexample

View `augv_2bf305fd65d508a89be664e8`, scene `scn_997807ff7272323d5174a1e6`, source node `1020026002`, receiver roads local262/local267 retain their accepted CON. Both source nodes are off observed support. Source parents `1020011902` and `1020040300` select respectively:

- `b6ch_ecd8cc0ef4ee227c56c2c0dda59eb6bd`, along-chain distance **185.134274080 m**;
- `b6ch_97cddb0134e74c06cb22d6d32329652c`, along-chain distance **185.407132266 m**.

Exactly one unordered logical child pair (two ordered rows) is emitted for this cause. There is no broadcast clique. These distances intentionally differ from the earlier 182–184 m Euclidean distances.

## Input/cache operation order

Accepted post-bank geometry/attributes → certified receiver/source-part lineage → S50 children → full-source B/P/R graph → minimal accepted-CON lift → G/Ppre SN selection → mask collapse → induced road-only tensors. Original uses the accepted prepared reader and canonical B6 projection unchanged.

`python/b6_segmented_inputs.py::full_source_graphs` retains materialized B/P geometry and contained-POI rules during top-16 competition. SN uses exact distance ≤100 m, 1e-9 m quantization, destination local-ID tie-break and either-direction symmetrization. Ppre excludes same-original-parent road candidates before top-k. Child IDs/order, bbox-center positions, geometry, receiver semantic tensors, availability, INT and lifted CON are shared. Only SN changes. Tests include full-source building competition consuming all road SN slots; road-only recomputation would fail that fixture.

S50 tensor construction repeats accepted receiver semantic tensors, never donor semantic values. For fully vector-empty accepted scenes, the exact accepted P1 scene-center index is used; no scene is dropped and no pseudo entity is introduced. Both concrete G and Ppre samples are validated and their non-edge scientific content compared. Common physical payloads contain separate G/Ppre edge masks and one shared Fourier pair; separate immutable per-arm identities bind the edge policy.

`python/b6_s50_cache.py` verifies each accepted prepared payload hash and its Original projected tensor digest against all 22,368 prior parity receipts. New Fourier rows use unchanged `scene_encoder.geometry_fourier_features`, 500 m normalization, 128 frequencies, float32 magnitude plus cosine/sine phase features. Fourier IDs bind child geometry, order, encoder implementation/config, CON policy and parent payload. G/Ppre share exactly the same feature bytes. Each branch's first sample is independently recalculated and serialized twice to check bit/content stability; all payload checksums are read back before publication.

No canonical cache is overwritten. External roots are `/mnt/hdd002/dhnyu/fusedata/experiments/b6_con_lift/`, `b6_s50_inputs/`, and `b6_bounded_updates/`, each under content-derived identities. Staging directories publish by rename only after acceptance. Dedicated targets store: `/mnt/hdd002/dhnyu/fusedata/targets/fuse-b6-con-gpu-pilot`.

## Bounded runner and interpretation

`python/b6_bounded_pilot.py` calls the actual `training_worker.training_update` with canonical `create_state`, `assemble_family_batch`, scheduler, objective, clipping, optimizer, EMA and FIFO enqueue. The only input adapters are the experimental paired reader and source-child masking identity. CPU/GPU timing hooks surround existing operations; canonical source files are unmodified. The same canonical epoch-1 scene sampler and view selector supply batch indices 0–4 to every arm. Update 1 is a real warmup update in the same state trajectory; updates 2–5 provide timing observations. No update is discarded from scheduler/EMA/queue state.

The pilot-only authority declares `scientific_metric=false`, `bounded_engineering_pilot=true`, `checkpoint_publication=false`, `formal_training=false`. GPU pair locks and canonical NCCL transport settings are used. The dedicated GPU controller has one orchestration worker; world size remains two and each rank receives 16 scenes. No gradient accumulation, truncation, smaller dimension or scene dropping is available.

Timing observations include instrumentation synchronization and warm filesystem caches. Per-rank rows are retained; p95 across four measured updates is descriptive and not a reliable tail-latency estimate. No pilot loss is a retrieval-quality result. Whole-population validation/checkpoint selection is unchanged and is not run here; road-nonempty and parent descriptors remain later diagnostic strata only.

## Final acceptance and identities

Final CON census: **PASS**. Original parity: **22,368/22,368 PASS**. S50-G and S50-Ppre model-ready, paired SN-only comparison, prepared cache and shared Fourier: **PASS**. Input ID `b6s50_a37a4debfbbde575348e5470`; G `b6prepared_76dd087e86c3adcb6067e76d`; Ppre `b6prepared_21e3681ce766ef1bf35db3b6`; shared Fourier `b6shared_e8ff824e161eacf7075b5f16`. Final pilot `b6pilot_4b63bd096bcf68cfa07aa4d1`.

Complete prepared payload size: **3,636,873,120 bytes**, 22,368 files, shared by logical arm identities. The full 40-worker/one-thread-per-worker build took **331.9 s**; maximum worker RSS **5,072,314,368 bytes**. The one-worker pilot took 72.894 s / 4,617,158,656 bytes. These are measured CPU costs, not projected training duration.

All measured pilot updates retain global batch **32**, world size **2**. Both ranks have 133 active parameter tensors with finite gradients; losses, EMA parameters and queue values are finite. Each update executes one optimizer step, one scheduler set/advance, and one EMA update. Queue valid count and pointer advance 64→128→192→256→320. Queue ID/center hashes and batch identities agree across all three arms for every update/rank; G/Ppre masking identity and assignments agree exactly.

## GPU measurements

Tables use global update rows: sum the two ranks for entity/relation/Fourier counts (both accepted views), maximum rank time and memory for a synchronized global update. Update 1 is warmup and excluded from summaries. RSS is a process high-water mark, not total host memory.

| Arm | Update | Road/Fourier rows | Relation rows | SN bits | INT bits | CON bits | Update seconds | Peak allocated GB | Peak reserved GB |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| B6-original | 1 (warmup) | 2,097 | 18,996 | 18,942 | 7,226 | 7,196 | 0.7028 | 0.369 | 0.417 |
| B6-original | 2 | 1,995 | 15,694 | 15,666 | 6,408 | 6,456 | 0.2469 | 0.397 | 0.451 |
| B6-original | 3 | 2,010 | 15,358 | 15,326 | 6,558 | 6,440 | 0.2435 | 0.378 | 0.457 |
| B6-original | 4 | 1,656 | 12,646 | 12,610 | 5,066 | 5,026 | 0.2403 | 0.354 | 0.470 |
| B6-original | 5 | 2,173 | 17,730 | 17,704 | 7,336 | 7,320 | 0.2510 | 0.438 | 0.472 |
| B6-S50-G | 1 (warmup) | 4,556 | 45,298 | 45,248 | 12,316 | 7,372 | 0.6222 | 0.688 | 0.761 |
| B6-S50-G | 2 | 4,372 | 39,544 | 39,514 | 11,376 | 6,666 | 0.1621 | 0.717 | 0.789 |
| B6-S50-G | 3 | 4,784 | 42,566 | 42,526 | 12,344 | 6,652 | 0.1682 | 0.725 | 0.803 |
| B6-S50-G | 4 | 3,976 | 37,514 | 37,478 | 9,900 | 5,232 | 0.1591 | 0.677 | 0.843 |
| B6-S50-G | 5 | 4,614 | 42,642 | 42,608 | 12,472 | 7,578 | 0.3006 | 0.753 | 0.881 |
| B6-S50-Ppre | 1 (warmup) | 4,556 | 46,286 | 41,480 | 12,316 | 7,372 | 0.6221 | 0.689 | 0.761 |
| B6-S50-Ppre | 2 | 4,372 | 40,298 | 35,736 | 11,376 | 6,666 | 0.1604 | 0.718 | 0.791 |
| B6-S50-Ppre | 3 | 4,784 | 43,022 | 37,626 | 12,344 | 6,652 | 0.1635 | 0.727 | 0.803 |
| B6-S50-Ppre | 4 | 3,976 | 38,200 | 33,744 | 9,900 | 5,232 | 0.1592 | 0.676 | 0.851 |
| B6-S50-Ppre | 5 | 4,614 | 43,492 | 38,794 | 12,472 | 7,578 | 0.2913 | 0.770 | 0.889 |

| Arm | Update time p50 / p95 / max (s) | Forward p50 (s) | Backward p50 (s) | Load/assembly p50 (s) | Peak RSS GB |
|---|---|---:|---:|---:|---:|
| B6-original | 0.2452 / 0.2504 / 0.2510 | 0.0247 | 0.0265 | 0.1656 | 3.229 |
| B6-S50-G | 0.1652 / 0.2808 / 0.3006 | 0.0209 | 0.0286 | 0.0739 | 2.719 |
| B6-S50-Ppre | 0.1619 / 0.2722 / 0.2913 | 0.0206 | 0.0285 | 0.0727 | 2.728 |

| Arm | Prepared bytes per measured global update p50 | Prepared read p50 s | Fourier read p50 s | Optimizer / scheduler / EMA p50 ms |
|---|---:|---:|---:|---|
| B6-original | 97,351,136 | 0.05183 | 0.05510 | 1.315 / 0.010 / 1.209 |
| B6-S50-G | 10,684,480 | 0.02818 | 0.00001 | 1.398 / 0.011 / 1.248 |
| B6-S50-Ppre | 10,684,480 | 0.02775 | 0.00001 | 1.343 / 0.011 / 1.213 |

Measured S50/Original ratios (median global update time; maximum allocated VRAM):

- B6-S50-G: **0.673× time**, **1.718× VRAM**.
- B6-S50-Ppre: **0.660× time**, **1.758× VRAM**.

**Timing limitation:** Original reuses the accepted full-source prepared/Fourier reader before induced B6 projection; S50 reads compact projected roads with colocated shared Fourier tensors. Lower S50 wall time is primarily an I/O/layout comparison, not evidence that segmentation speeds model computation. Prepared bytes are logical payload bytes requested, not physical disk traffic. S50 Fourier read time is near zero because those tensors were already loaded with its prepared payload. Raw per-rank receipts preserve all timings/counts; the acceptance JSON summarizes eight rank observations while this report summarizes four global updates.

An initial five-update pass per arm passed before adding explicit queue-order hashes, output-namespace guards and scheduler-set telemetry. The final five-update pass is the accepted measurement above. Thus this task executed **10 bounded updates per arm in total**, zero formal training updates, zero checkpoints. The initial pass had a substantially colder Original Fourier cache (median rank update ~1.049 s versus ~0.245 s in the final pass), reinforcing that these timings must not be extrapolated to full training.

## Validation, limitations and final verdict

Python compile and R parse passed. **182 Python tests** passed across CON fixtures, Stage B, augmentation/RNG, model-family/projection, prepared geometry, runtime inputs, transport and training support. **75 R expectations** passed across Stage A, Stage B and the new DAG. Config/schema validation, target manifest, DAG acyclicity and dedicated `tar_validate` passed. The final graph has four targets/five target edges and a dedicated GPU controller; source files are direct dependencies of every execution stage so code changes cannot be hidden by unchanged upstream receipts.

All **352 Stage A**, **7 prior Stage B preparation**, **98 CON census** and **11 final pilot** manifest payload references passed checksum readback, as did all **22,368 S50 prepared payloads**. A repeat of the dedicated graph skipped all four targets with payload checksums unchanged; no canonical producer is imported. Source/config, focused tests, reports and the generated dependency HTML are the only Git changes.

Remaining limitations: five updates do not estimate convergence, retrieval quality, long-run stability or worst-case full-population training memory. Queue capacity remains 8,192 but the bounded trajectory fills only 320 slots. No validation, model selection or checkpoint is performed. The zero-road finding (144/1,000 validation scenes; inferred 85.70% HIT@1 ceiling versus reported 85.65%) is unchanged; no new inference was needed. The CON extension is logical accepted-parent inheritance and does not correct historical outside-node semantics.

**Final verdict: READY_FOR_STAGE_B_TRAINING_AUTHORIZATION.** This authorizes no formal training by itself. The separately authorized next scientific block remains B6-original / B6-S50-G / B6-S50-Ppre with fixed accepted training and whole-validation checkpoint selection.

Full training executed = NO; bounded pilot updates executed = YES; formal checkpoints created = NO; canonical S09 campaign executed = NO; canonical artifacts modified = NO; dissertation modified = NO; reduced modified = NO.

Final preservation receipt: `reduced` remains `851efd0c94120ff250f34502fceba73a45080281`; dissertation remains clean at `6a43d30133db01a773f6b5d355fc1290b544072b`. After the skipped rerun, all **22,836 unique payloads** in the combined immutable readback retained their hashes. `git diff --check` passed. Policy-text SHA256: `1b9a8b5ab17ba751731e60e44719970b0378109ef84480919821e3391721a49b`.

Operational resource settings are isolated in `config/b6_con_execution.yml`: census 8 workers, cache 40 workers, one thread each, CPU budget 48, GPU world size 2. Changing orchestration resources does not relabel scientific data.
