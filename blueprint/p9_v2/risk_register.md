# P9 v2 Risk Register

Status: `DRAFT_NON_RUNTIME_NON_AUTHORIZING`

| ID | Risk | Likelihood/impact | Mitigation and acceptance evidence |
|---|---|---|---|
| R1 | Filesystem rename or durability assumptions differ across mounts. | Medium/high | V2-A uses same-filesystem staging, file and directory `fsync`, and 11 synthetic fault boundaries. Production-filesystem power-loss testing remains for V2-H. |
| R2 | Deterministic JSON differs by language/runtime. | Medium/high | V2-A fixes exact binary64 decimal, safe numeric range, NFC UTF-8, and golden Python vectors. Independent-language golden vectors remain required before adding a second writer. |
| R3 | Ledger event volume harms training I/O. | Medium/medium | V2-A uses one bounded segment per durable event and permits progress batching. Benchmark cadence before controller authority in V2-H. |
| R4 | A validation metric exists without a durable checkpoint. | Medium/high | Candidate schema requires checkpoint hashes and atomic marker; finalizer ignores all other validation records. |
| R5 | Legacy checkpoint deserialization executes unsafe code. | Low/high | V2-D verifies source/payload hashes first and uses PyTorch `weights_only=True`, CPU mapping, and a function-local allowlist limited to five NumPy reconstruction types. It never uses unrestricted load or changes global safe globals. Restricted deserialization still parses untrusted binary structure, so canonical V2-G must retain the integrity gate and pinned environment. |
| R6 | Content-addressed external locator becomes mutable. | Medium/high | V2-B separates namespace/key from physical root and verifies object identity, size, payload hash, and associated manifest hash on every validation. Path alone is invalid. |
| R7 | Two publishers race. | Medium/medium | V2-C acceptance-scoped kernel lock, atomic directory publication, validate-or-return, collision rejection, and concurrent synthetic tests. |
| R8 | Finalizer implementation changes output for same contract. | Medium/high | V2-C binds implementation hash/version in finalization identity and tests deterministic and changed-version identities; migration acceptance must pin the version. |
| R9 | Authority revocation/supersession semantics are underspecified. | Resolved/high | V2-E uses a canonical content-addressed eligibility snapshot with sorted acceptance entries and exact authority binding. V2-G atomically published the authorized snapshot alongside canonical acceptance evidence; missing, ambiguous, superseded, or revoked entries fail closed. |
| R10 | Historical source evidence changes before import. | Low/high | V2-D and V2-G recompute full ordered source inventory; exact pre-approved hashes required. |
| R11 | “Scientific complete” is mistaken for historical run success. | Medium/high | Preserve v1 state verbatim and display both dimensions with legacy annotation in every imported result. |
| R12 | Evaluation data leaks into migration/finalization. | Low/critical | V2-C imports no evaluation/training stack, accepts only V2-B evidence with consumption zero, binds zero in finalization/acceptance, and rejects additional evaluation fields. |
| R13 | Downstream code retains manual checkpoint fallback. | High/high | V2-E removes path parameters and adds rejection tests for all five consumers. |
| R14 | V1 remains executable after v2 adoption. | Resolved/high | V2-I reduced all three active target graphs to fail-closed guards, retired eight CLIs plus the recovery controller/resolver, published a hash-bound retirement manifest, and retained only explicit read-only inspection. |
| R15 | Scientific/controller plane imports regress. | Medium/high | Static dependency tests and package/module boundaries; control cannot import parameter-mutating functions and science cannot import acceptance/targets APIs. |
| R16 | V2-C reset patience after a margin-only selected checkpoint, while the dissertation permits reset only for retrieval-loss decrease of at least `1e-4`. | Resolved/high | V2-EF introduced `p9-selection-v2.1.0`, separated selection from patience reset, added boundary/tie regressions, and reconfirmed the unchanged historical epoch-105 selection and epoch-125 stopping boundary. |
