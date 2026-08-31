# P9 cfg_main Read-Only Terminal Recovery: Blocked Preflight

## Verdict

`P9_CFG_MAIN_READ_ONLY_TERMINAL_RECOVERY_BLOCKED_PUSHED`

## Preflight

Fuse was `reduced` at `139f5ed6805d2e0fca7cb68dcf7a6cf3d0212f75` and
dissertation was `reduced` at `ad8c8b5c17c5ca72dce7f30c2eb283f6041dbc9a`;
both were clean and synchronized. The recovery runtime manifest reproduced
`3b17670f7ad2a806e1acef67cd3e90d610b31ba04fb489621745651ec95423f4` with
zero file mismatches. The isolated recovery manifest declares 11 targets,
including `p9_cfg_main_recovery_acceptance`.

## Blocking Defect

The authorized runtime accepts the exact recovery reservation token but does
not implement the required recovery-operation lock: no kernel lock, durable
owner record, heartbeat, duplicate-operation identity, atomic acquisition, or
release evidence exists. Therefore it cannot prove that exactly one recovery
operation owns the terminal publication path.

This violates the explicit execution contract. The terminal target was not
selected or invoked.

## Preserved State

The source formal run remains `FAILED_NONRESUMABLE`:
`p9a_9d6f0554553ac43371b47efd`,
`p9res_0f5492c80e7c152e6c543012`,
`p9attempt_a754afd14ac87287afb04029`, and
`p9run_6887930091dd2f2bfedc3c96`.

The recovery authority/reservation/operation remain unchanged:
`p9ra_8e32bacc3917acd1a91921c4`,
`p9rres_63586f0a27e1402f54bfa32b` (`AUTHORIZED_NOT_STARTED`), and
`p9rop_1e1db7e73e8101739a960df9`.

No recovery operation, acceptance, optimizer/EMA/scheduler update, validation,
evaluation, checkpoint write, DDP launch, GPU process, cache write, or source
artifact mutation occurred.

## Required Next Authorization

A new work unit must implement and authorize a recovery-specific lock and
durable state transaction, then issue a new recovery runtime digest, authority,
reservation, and operation. It must not reuse the current reservation.

Prompt summary: execute one read-only terminal recovery only after preflight
confirms all authorization, isolation, immutability, and locking gates.
