# P9 v2 Decision Log

Status: `DRAFT_NON_RUNTIME_NON_AUTHORIZING`

| ID | Decision | Rationale | Status |
|---|---|---|---|
| D1 | Separate scientific and operational state dimensions. | The epoch-125 trajectory is scientifically complete although controller finalization failed. | Accepted for blueprint. |
| D2 | Use one append-only hash-chained ledger per run. | Removes duplicated mutable counters and makes replay the state authority. | Accepted for blueprint. |
| D3 | Bind validation and checkpoint in one committed event. | Eliminates the v1 `N` versus `N+1` semantic join. | Accepted for blueprint. |
| D4 | Treat the run bundle, not target metadata, as finalizer input. | Makes evidence portable, immutable, and orchestration-independent. | Accepted for blueprint. |
| D5 | Make finalization pure and retryable. | Ordinary post-training failures do not justify a recovery state machine. | Accepted for blueprint. |
| D6 | Use one short acceptance publication lock. | Only canonical publication has a race; finalization is content-addressed. | Accepted for blueprint. |
| D7 | Retain five identity types. | Authority prevents unauthorized execution; run distinguishes trajectories; bundle binds evidence; finalization binds deterministic interpretation; acceptance is downstream commit. | Accepted for blueprint. |
| D8 | Remove reservation, preassigned attempt, operation, recovery authority/reservation, and authorization-acceptance identities. | Their distinguishing data are already bound by authority/run/bundle hashes and locks. | Accepted for blueprint. |
| D9 | Keep `targets` coarse grained with eight targets. | Target metadata is orchestration cache, not mutable scientific state. | Accepted for blueprint. |
| D10 | Permit read-only legacy import with explicit annotations. | Evidence is complete and retraining would add cost without repairing the original scientific trajectory. | Accepted for blueprint. |
| D11 | Preserve v1 `FAILED_NONRESUMABLE` unchanged. | Migration interpretation must not rewrite history or claim operational success. | Accepted for blueprint. |
| D12 | Require every downstream consumer to resolve a v2 acceptance identity. | Prevents manual-path, latest-checkpoint, and uncommitted-artifact use. | Accepted for blueprint. |
| D13 | Canonicalize finite binary64 numbers as exact exponent-free decimal, normalize both zero signs to `0`, and reject nonfinite or safe-range-exceeding numbers. | Gives an explicit language-independent byte contract without platform float formatting or negative-zero ambiguity. | Implemented in V2-A. |
| D14 | Require NFC UTF-8 strings and Unicode-scalar key ordering. | Prevents canonically equivalent Unicode spellings and locale/order differences from changing hashes. | Implemented in V2-A. |
| D15 | Store one event per immutable segment, capped at 1 MiB. | Closes cadence policy with the smallest crash-safe implementation; batching remains inside progress events. | Implemented in V2-A. |
| D16 | Define segment rename and manifest rename as logical commit points; staging and tail are non-authoritative. | Restart needs only ordinary validation/replay and cannot apply a half-published event. | Implemented in V2-A. |
| D17 | Accept runtime schema version `2.0.0` only and fail closed on unknown versions. | Compatibility must be an explicit future migration, not permissive interpretation. | Implemented in V2-A. |
| D18 | Use structured filesystem locators with namespace, normalized relative key, content-derived object identity, hash, size, role, and media type. | Separates physical root resolution from immutable logical evidence and rejects raw paths. | Implemented in V2-B. |
| D19 | Copy canonical ledger/metadata evidence but hash-reference large checkpoint payloads and manifests. | Preserves independent verification without multi-GB duplication or historical rewriting. | Implemented in V2-B. |
| D20 | Order internal inventory by relative path, validation checkpoints by epoch/identity, external objects by role/object/digest, and sources by logical path. | Makes identity independent of enumeration and caller insertion order. | Implemented in V2-B. |
| D21 | Derive `bundle_content_sha256` from the canonical commit-manifest preimage excluding only identity/hash, then derive `p9rb_` plus its first 24 hex. | Binds all scientific evidence while avoiding recursive identity fields. | Implemented in V2-B. |
| D22 | Publish a fully validated staging directory by atomic rename; the directory rename is the sole bundle commit point. | Partial staging remains non-authoritative and no recovery manager or third lock is needed. | Implemented in V2-B. |
| D23 | Existing identity paths use validate-and-return for exact content and fail closed otherwise. | Provides sequential/concurrent idempotency without overwriting collisions. | Implemented in V2-B. |
| D24 | Permit valid incomplete evidence bundles but label them `SCIENTIFICALLY_INCOMPLETE`; later finalization must reject them. | Preserves interrupted/failed evidence without confusing it with finalizable science. | Implemented in V2-B. |
| D25 | Exclude all `targets` metadata and physical root paths; verify external size/hash on every validation. | Makes bundles portable and detects mutation instead of trusting location. | Implemented in V2-B. |
| D26 | Encode the selection contract as `p9-selection-v2.0.0`, with strict binary64 absolute loss difference `< 0.0001`, margin then earlier-epoch tie breaks, and patience reset by a newly selected best. | This selected checkpoints correctly but incorrectly coupled margin selection to patience reset. | Superseded by D42 in V2-EF. |
| D27 | Replay candidates in committed ledger sequence and require exactly one matching early-stopping update for every validation-checkpoint event. | The ledger, not a stored best-checkpoint summary, remains selection authority. | Implemented in V2-C. |
| D28 | Derive `finalization_result_hash` from the complete canonical result preimage excluding identity/hash and bind the finalizer implementation version/hash; derive `p9fin_` from the first 24 hash hex. | Same interpretation is byte-identical while implementation or contract drift changes identity. | Implemented in V2-C. |
| D29 | Keep deterministic finalization failures in a stable invalid-evidence taxonomy; keep publication/IO failures outside scientific and training state. | Operational retry must not relabel completed science. | Implemented in V2-C. |
| D30 | Derive `p9accv2_` from authority, bundle, finalization, selected checkpoint hashes, schema, and zero evaluation consumption. | Publication metadata, clocks, hosts, and physical roots cannot alter scientific acceptance identity. | Implemented in V2-C. |
| D31 | Store `acceptance.json`, exact finalization bytes, and a commit manifest in staging; atomic directory rename exposing the manifest is the acceptance commit point. | A crash exposes either no canonical acceptance or one complete immutable acceptance. | Implemented in V2-C. |
| D32 | Use one blocking, short, acceptance-identity `flock` with no heartbeat and validate-or-return on duplicates. | Concurrent identical publishers converge without a recovery transaction or third lock class. | Implemented in V2-C. |
| D33 | Resolve only canonical acceptance identities and validate acceptance, finalization, bundle, checkpoint inventory, and external bytes on every resolution. | Raw paths, `latest`, legacy recovery artifacts, and mutable payload substitution fail closed. | Implemented in V2-C. |
| D34 | Defer authority eligibility and supersession/revocation indexing to V2-E and fail closed where that policy is required. | V2-C core must not invent a mutable authority subsystem outside its bounded scope. | Accepted for V2-E. |
| D35 | Inspect v1 PyTorch payloads only after manifest/source SHA-256 gates, with `weights_only=True`, CPU mapping, and a function-local five-type NumPy allowlist. | The installed PyTorch restricted loader can read all 25 immutable payloads without unrestricted pickle execution or global safety changes. | Implemented in V2-D. |
| D36 | Derive imported run/event identities from importer version, v1 run identity, ordered source-inventory digest, canonical event envelope, and deterministic source-time mapping. | Repeated and reversed-discovery imports produce byte-identical ledger and bundle identities without random or import-time values. | Implemented in V2-D. |
| D37 | Treat v1 authority, reservation, and attempt identities only as legacy provenance; use one nonauthorizing dry-run authority document to satisfy bundle binding. | Legacy governance identities must not become active V2 authority types or authorize execution. | Implemented in V2-D. |
| D38 | Represent v1 payload/manifest atomic publication as `AVAILABLE_WITH_LEGACY_ANNOTATION`, never as a native contemporaneous V2 commit. | This preserves equivalent durable evidence without rewriting history. | Implemented in V2-D. |
| D39 | Publish V2-D output only below `v2_d_noncanonical_dry_run/ineligible_for_acceptance`, with schema-required canonical and acceptance eligibility false. | Dry-run evidence cannot be mistaken for V2-G canonical publication. | Implemented in V2-D. |
| D40 | Fail closed on missing, duplicate, ambiguous, hash-inconsistent, state-incomplete, evaluation-contaminated, or unsupported legacy evidence; `MISSING_BLOCKING` means no unique lossless value is available from immutable sources. | Import must not repair, guess, use mtime/latest, or recompute science. | Implemented in V2-D. |
| D41 | Record the dissertation/V2-C patience-reset discrepancy without changing V2-C in V2-D. | The historical trace has no margin-only selected replacement, so the dry-run result is invariant; the general contract required correction before V2-G. | Closed by D42 in V2-EF. |
| D42 | Use `p9-selection-v2.1.0`: selection still uses loss-equivalence/margin/earlier epoch, but patience resets only for retrieval-loss decrease at least `1e-4`. | This exactly implements the dissertation and keeps checkpoint choice separate from early-stopping improvement. | Implemented in V2-EF; closes D41. |
| D43 | Configure one resolver with roots and an immutable content-addressed eligibility snapshot; consumer calls take only an acceptance identity. | Five consumers share full chain validation without path parameters, mutable registry state, or duplicated checks. | Implemented in V2-E. |
| D44 | Represent eligibility as a sorted immutable snapshot with `ELIGIBLE`, `SUPERSEDED`, or `REVOKED` entries bound to authority identity/hash. | Missing, ambiguous, or ineligible acceptance fails closed without inventing a new authority or publication state machine. | Implemented in V2-E. |
| D45 | Validate V2-A through consumer binding using temporary synthetic artifacts only. | Exercises interruption, failure, finalization retry, publication retry, bookkeeping failure, corruption, and fallback rejection without downstream science. | Implemented in V2-F. |

## Retained identity justification

| Identity | Race/ambiguity prevented | Creator | Immutable point | Binds | Consumers |
|---|---|---|---|---|---|
| Execution authority | Unauthorized or scientifically different launch | Authority publisher | Atomic authority publication | Scientific config, parents, runtime policy, allowed run key | Controller |
| Run identity | Confusion between independent trajectories/resumes | Controller deterministically from authority + run nonce/policy | `RUN_AUTHORIZED` | Authority, scientific config, seed, duplicate key | Ledger, bundle |
| Run-bundle identity | Evidence substitution | Bundle builder | Bundle atomic publication | Complete ordered evidence inventory | Finalizer, audit |
| Finalization identity | Selection interpretation drift | Pure finalizer | Result create-or-validate | Bundle, selection contract, finalizer version | Publisher, audit |
| Acceptance identity | Duplicate or ambiguous downstream commit | Publisher | Acceptance manifest atomic rename | Authority, bundle, finalization result | Resolver and all downstream consumers |

## Unresolved implementation decisions

These do not block the architecture verdict but must be closed in the named unit:

- V2-H: precise heartbeat interval, interruption policy, and configurable progress-summary cadence after I/O pilot.
