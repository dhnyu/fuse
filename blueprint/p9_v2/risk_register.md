# P9 v2 Risk Register

Status: `DRAFT_NON_RUNTIME_NON_AUTHORIZING`

| ID | Risk | Likelihood/impact | Mitigation and acceptance evidence |
|---|---|---|---|
| R1 | Filesystem rename or durability assumptions differ across mounts. | Medium/high | V2-A uses same-filesystem staging, file and directory `fsync`, and 11 synthetic fault boundaries. Production-filesystem power-loss testing remains for V2-H. |
| R2 | Deterministic JSON differs by language/runtime. | Medium/high | V2-A fixes exact binary64 decimal, safe numeric range, NFC UTF-8, and golden Python vectors. Independent-language golden vectors remain required before adding a second writer. |
| R3 | Ledger event volume harms training I/O. | Medium/medium | V2-A uses one bounded segment per durable event and permits progress batching. Benchmark cadence before controller authority in V2-H. |
| R4 | A validation metric exists without a durable checkpoint. | Medium/high | Candidate schema requires checkpoint hashes and atomic marker; finalizer ignores all other validation records. |
| R5 | Legacy checkpoint deserialization executes unsafe code. | Low/high | Import in isolated trusted environment, hash first, no network/GPU, allowlisted types, and record loader version. Investigate conversion in V2-D without rewriting source. |
| R6 | Content-addressed external locator becomes mutable. | Medium/high | Resolver requires immutable namespace plus hash/size verification; path alone is invalid. |
| R7 | Two publishers race. | Medium/medium | Acceptance-scoped kernel lock plus atomic create-or-validate and collision failure. |
| R8 | Finalizer implementation changes output for same contract. | Medium/high | Bind implementation hash/version in finalization identity and golden tests; migration acceptance pins version. |
| R9 | Authority revocation/supersession semantics are underspecified. | Medium/high | Define a small immutable eligibility index before V2-E; resolver fails closed on ambiguity. |
| R10 | Historical source evidence changes before import. | Low/high | V2-D and V2-G recompute full ordered source inventory; exact pre-approved hashes required. |
| R11 | “Scientific complete” is mistaken for historical run success. | Medium/high | Preserve v1 state verbatim and display both dimensions with legacy annotation in every imported result. |
| R12 | Evaluation data leaks into migration/finalization. | Low/critical | No evaluation loader imports; require consumption zero in event, bundle, finalizer, acceptance and resolver tests. |
| R13 | Downstream code retains manual checkpoint fallback. | High/high | V2-E removes path parameters and adds rejection tests for all five consumers. |
| R14 | V1 remains executable after v2 adoption. | Medium/high | V2-I fail-closed entry points and retirement manifest; preserve inspection tools only. |
| R15 | Scientific/controller plane imports regress. | Medium/high | Static dependency tests and package/module boundaries; control cannot import parameter-mutating functions and science cannot import acceptance/targets APIs. |
