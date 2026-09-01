# P9 v2 Architecture and Migration Blueprint

Status: `IMPLEMENTED_THROUGH_V2_I_V1_RETIREMENT`

This directory defines the proposed P9 v2 control and artifact contracts. It does not authorize execution, alter dissertation methodology, or form part of any production runtime digest.

## Verdict

`P9_V2_ARCHITECTURE_AND_MIGRATION_BLUEPRINT_PASS`

The historical run `p9run_6887930091dd2f2bfedc3c96` is `MIGRATION_ELIGIBLE_WITHOUT_RETRAINING`. Its immutable v1 state remains `FAILED_NONRESUMABLE`; v2 represents the imported evidence independently as scientific `COMPLETE`, operational `FINALIZATION_FAILED`, and resumability `NOT_APPLICABLE_SCIENTIFICALLY_COMPLETE`.

V2-G canonically imported that evidence under the bounded authority
`p9authv2_47f350372bf94162db8f9142` and committed acceptance
`p9accv2_d93b01ef13c3f26a22287ce7`. This is a v2 acceptance of immutable
scientific evidence, not a rewrite or success claim for the v1 controller run.

V2-I retires every active v1 target, CLI, recovery controller, and downstream
resolver boundary with stable error `P9_V1_EXECUTION_RETIRED`. The 12 legacy
authorities and six target-store generations remain byte-preserved historical
evidence. Downstream consumption is exclusively through the canonical V2
acceptance above and `resolve_accepted_checkpoint()`.

## Authority and methodology

- Fuse starting lineage: `reduced@e84fc1943beee33a4299472369e2c976e6baa7e6`.
- Dissertation lineage: `reduced@ad8c8b5c17c5ca72dce7f30c2eb283f6041dbc9a`.
- Methodology read: `template/sections/chapters/04-methodology-training.typ`, `template/sections/chapters/results/03-representation-analysis.typ`, and the active implementation blueprint.
- No methodology conflict was found. The v2 design preserves validation every five epochs, retrieval-loss selection with the `1e-4` equivalence rule, margin then earlier-epoch tie breaking, and patience four.

## Design in one view

```text
accepted parents + authority
              |
              v
     coarse run controller  [training lock]
              |
              v
 scientific executor -> committed artifacts
              |              |
              +-> append-only ledger
                             |
                             v
                 immutable run bundle
                             |
              pure deterministic finalizer
                             |
                             v
                   finalization result
                             |
                acceptance publisher [short lock]
                             |
                             v
                  canonical acceptance
                             |
              resolve_accepted_checkpoint()
          P9-B / selected-FM / evaluation / P10 / P11
```

The scientific plane may consume data and cache, update model state, validate, create checkpoint payloads, and propose scientific events. It may not decide authority validity, `targets` currentness, acceptance, supersession, or downstream resolution. The control plane may authorize, lock, supervise, append events, finalize, publish acceptance, and report operational failures. It may not modify parameters, metrics, checkpoint payloads, sampler results, or scientific configuration.

## Canonical components

| Component | Count | Responsibility |
|---|---:|---|
| Run ledger | 1 | Canonical append-only scientific and operational event history. |
| Training controller | 1 | Own one duplicate-run lock and supervise the executor. |
| Run-bundle builder/validator | 1 | Publish and validate immutable evidence independent of `targets`. |
| Pure finalizer | 1 | Reconstruct completion, stopping, and deterministic selection. |
| Acceptance publisher | 1 | Commit one canonical acceptance idempotently. |
| Resolver | 1 | Return a validated checkpoint and full provenance to every consumer. |
| Lock classes | 2 | Long training lock and short acceptance-publication lock. |
| Identity types | 5 | Authority, run, run bundle, finalization, acceptance. |

## Minimal `targets` boundary

The implemented isolated script is `_targets_p9_v2_training.R` with an authority-explicit external store. It contains eight targets and seven target-to-target edges:

```text
p9v2_training_contract + p9v2_training_authority
  -> p9v2_closed_ledger
  -> p9v2_run_bundle
  -> p9v2_finalization_result
  -> p9v2_acceptance_commit
  -> p9v2_eligibility_snapshot
  -> p9v2_accepted_checkpoint
```

The controller target is coarse grained. Mutable controller transitions are ledger events, not targets. A historical import uses the same bundle validator, finalizer, publisher, and resolver but substitutes a read-only importer for the run controller. No old target metadata is a scientific input.

## Documents

- [v1_inventory.md](v1_inventory.md): files, components, DAGs, stores, identities, locks, mutable state, reports, tests, and consumers.
- [failure_taxonomy.md](failure_taxonomy.md): chronological failures and structural v2 preventions.
- [state_model.md](state_model.md): independent scientific, operational, and resumability dimensions.
- [event_ledger.md](event_ledger.md): ledger format, events, batching, hashing, and atomic append.
- [run_bundle.md](run_bundle.md): immutable bundle layout, identity, completeness, and validation.
- [finalization_acceptance_resolver.md](finalization_acceptance_resolver.md): pure finalizer, idempotent publisher, locks, and resolver.
- [legacy_migration.md](legacy_migration.md): field mapping, importer, feasibility evidence, criteria, and retirement.
- [roadmap.md](roadmap.md): bounded V2-A through V2-I work units and complexity targets.
- [risk_register.md](risk_register.md): risks and mitigations.
- [decision_log.md](decision_log.md): architecture decisions and unresolved choices.
- `schemas/`: non-runtime architecture drafts. V2-A through V2-F runtime schemas are versioned under `config/schemas/p9_v2_*.schema.json`.

## Prohibited dependencies

1. Scientific code must not read target metadata, authority state, acceptance state, publication locks, or downstream resolver output.
2. Finalization must not import the trainer, CUDA, validation loaders, evaluation loaders, optimizer, or checkpoint writer.
3. Acceptance must not mutate the bundle or finalization result.
4. Downstream consumers must not accept a manual checkpoint path, a v1 recovery artifact, an uncommitted result, or "latest checkpoint" fallback.
5. Evaluation identities and evaluation data must not enter the run ledger, bundle selection evidence, finalizer, or acceptance publication except for the audited scalar `evaluation_consumption_count = 0`.

## V2-H production controller implementation

V2-H implements the future-run control boundary in `python/p9_v2_training_controller.py` and keeps the science-plane construction/pilot in `python/p9_v2_training_pilot.py`. The controller imports no PyTorch code. It consumes exactly one immutable `p9authv2_` authority, derives one `p9runv2_` identity, owns the V2-A ledger writer, and holds one duplicate-run `flock`. Science workers submit canonical event proposals; they cannot publish acceptance or eligibility.

The V2-H controller foundation pilot used actual `cfg_d48`, two GPUs, one global production batch, and zero scientific mutation. The subsequent production-worker remediation adds `python/p9_v2_training_worker.py`, a blocking canonical request/ACK protocol, controller-owned checkpoint publication, full exact restore, and `python/p9_v2_training_lifecycle.py`. The worker contains the production DDP update and validation trajectory but cannot write the ledger, canonical checkpoint namespace, bundle, acceptance, or eligibility.

The active isolated graph is `_targets_p9_v2_training.R`: nine coarse targets from explicit authority and full startup preflight through training, V2-B bundle construction, V2-C finalization/acceptance, immutable eligibility, and resolver verification. No bundle/finalization/acceptance path is injected from the environment. It remains inert without `P9_V2_TRAINING_AUTHORITY`; v1 graphs remain retired. A noncanonical two-GPU pilot executed four bounded updates both uninterrupted and as two updates plus fresh-process exact resume, then validated the complete temporary V2-B/C/E chain. No formal authority or canonical cfg_d48 artifact was created.
