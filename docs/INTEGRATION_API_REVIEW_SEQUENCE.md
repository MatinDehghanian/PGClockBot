# Integration API review sequence

The large [candidate #967](https://github.com/Mrclocks/PGClockBot/pull/967) is Draft
and is superseded for review by the following sequence. The first replacement is
[PR #971](https://github.com/Mrclocks/PGClockBot/pull/971). All pull requests target
`dev`. Each later branch is based on its predecessor and stays queued until that
predecessor is merged; opening cumulative PRs against `dev` would recreate the
large diff. Merge the new upstream `dev` into a published queued branch, or create a fresh
review branch when a squash merge changes ancestry. Never force-push the published
queue. Recheck migration numbers and run the
applicable focused, security, lint and full-suite checks before opening each one.
Each reviewed part is merged through the maintainer workflow.

| Part | Branch | Scope | Migration head |
|---|---|---|---|
| 1 | `codex/integration-customer-foundation` | Canonical/fixed-shop identity and retained schemas; automatic startup backfill; legacy deletion compatibility. No routes, workers or delivery adapters. | `0076_customer_telegram_links` |
| 2 | `codex/integration-read-api` | Default-off GET endpoints, backend authentication/admission, scoped catalog/customer/service readers and snapshots. No HTTP mutation, consent or operation routes. | `0077_integration_read_snapshots` |
| 3 | `codex/integration-technical-operations` | Customer registration; durable provision/renew/add-on intents; private access; native ownership/fencing adapters and capacity accounting. No outbox or consent delivery. | `0079_integration_private_delivery` |
| 4 | `codex/integration-webhooks-outbox` | Transactional signed outbox, protected retries/transport, retained evidence and dual-proof Telegram consent. | `0080_integration_event_outbox` |
| 5 | `codex/integration-management-pages` | Authorized administration/customer/audit pages and CSRF/action-ticket controls; integration import grouping. | unchanged |
| 6 | `codex/integration-documentation` | Actual generated OpenAPI enrichment/export, backend example, compatibility/operation/rollback guides and this review index. | unchanged |

The branches are reviewable individually through these comparisons after push:

- [Read API](https://github.com/MatinDehghanian/PGClockBot/compare/codex%2Fintegration-customer-foundation...codex%2Fintegration-read-api)
- [Technical operations](https://github.com/MatinDehghanian/PGClockBot/compare/codex%2Fintegration-read-api...codex%2Fintegration-technical-operations)
- [Outbox and consent](https://github.com/MatinDehghanian/PGClockBot/compare/codex%2Fintegration-technical-operations...codex%2Fintegration-webhooks-outbox)
- [Management pages](https://github.com/MatinDehghanian/PGClockBot/compare/codex%2Fintegration-webhooks-outbox...codex%2Fintegration-management-pages)
- [Documentation and OpenAPI](https://github.com/MatinDehghanian/PGClockBot/compare/codex%2Fintegration-management-pages...codex%2Fintegration-documentation)

## Startup and disabled-path corrections

Ordinary `init_db` / `alembic upgrade head` now performs the 0075 backfill in
bounded batches before its ownership validation. There is no intermediate 0074
stop or manual backfill prerequisite. SQLite bulk parameters also remain within a
999-variable limit; repeated upgrades preserve stable IDs and blocked states.
The optional CLI remains available for maintenance. Contradictory canonical
associations still stop safely rather than guessing ownership.

Native fencing and canonical adapters activate only with both execution and the
global database API switch enabled. The cold platform wallet checkout regression
matches clean dev's 22-statement action/table signatures and its exact one panel POST
payload (only two adjacent independent owner/plan eager reads are normalized) for all three disabled combinations. Additive ORM fields naturally change
column lists. Native create/modify/delete paths open no integration sessions while
disabled. Fresh inactive workers open no integration sessions or queue scans.

A saved target also records the internal, monotonic `integration_execution_started`
setting. Existing startup settings-key loading observes that marker without a new
query. Previously used installations keep durable unknown-outcome capacity counted
even after execution is disabled; this safety accounting must not be removed to
optimize the inactive path. Committed platform switch changes update the activation
snapshot; unrelated settings and shop overrides cannot enable or disable it.
Restart every process after an external database/CLI switch change.

## Executed verification

The published queue incorporates current dev 0.5.4 through normal merges. The
explicit migration/concurrency matrix passes all 89 SQLite/PostgreSQL cases without
skips. The exact commands and aggregate results are recorded in the
[roadmap revision checkpoint](INTEGRATION_API_ROADMAP.md#review-revision-2026-10-26).
Matrices overlap and must not be added. A PostgreSQL skip is not a PostgreSQL pass.

A separately restored operator-provided PostgreSQL backup reproduced the original
coverage failure at revision 0067. Fixed ordinary startup reached the first part's
0076 head and the complete series' 0080 head on independent copies. Fingerprints
of original users, services, orders, payments and wallets were unchanged. No backup
content, credentials, row values or database dump is part of these branches.

Actual test-bot/PasarGuard creation and renewal, live Telegram/webhook delivery,
proxy retry/quiescence, TLS/DNS/egress, evidence restore and worker lifecycle proof
remain **not performed**. The operator currently has no staging panel available.
A restored database proves migration compatibility; it does not prove external
panel behavior. Keep the mutating parts Draft and disabled until that separate
verification is available. No deployment or production activation was performed.

The [Persian rollback guide](INTEGRATION_API_ROLLBACK_FA.md) separates installations
that never activated integration from those that may have sent a panel request.
Retain mappings, targets, tombstones, guards, commitments, consent, outbox, root and
signing keys, and execution history. A pre-feature binary is not a safe fallback
once website services or uncertain effects exist.
