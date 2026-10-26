# Integration API review sequence

The large [candidate #967](https://github.com/Mrclocks/PGClockBot/pull/967) remains
Draft and is superseded for review by the six pull requests below. All target
`dev`. At the operator's request, all six are open now: **#971 is ready for review**;
**#978–#982 remain Draft** until their immediate prerequisite has merged.

Each branch contains its predecessors. Its GitHub diff against dev is therefore
cumulative until those predecessors merge; use the isolated comparisons below to
review one logical part at a time. Merge in the listed order. After each merge,
incorporate current upstream dev into the next published branch with a normal
merge, resolve any conflicts, recheck migration numbers, run focused/security/lint
and full-suite checks, and mark that next PR ready. This also handles squash
merges without force-pushing published history. Merging remains a maintainer action;
marking a PR ready does not deploy or activate integration.

| Part / PR | Prerequisite / state | Branch | Scope | Migration head |
|---|---|---|---|---|
| [1 — #971](https://github.com/Mrclocks/PGClockBot/pull/971) | None; **Ready** | `codex/integration-customer-foundation` | Canonical/fixed-shop identity and retained schemas; automatic startup backfill; legacy deletion compatibility. No routes, workers or delivery adapters. | `0076_customer_telegram_links` |
| [2 — #978](https://github.com/Mrclocks/PGClockBot/pull/978) | #971; **Draft** | `codex/integration-read-api` | Default-off GET endpoints, backend authentication/admission, scoped catalog/customer/service readers and snapshots. No HTTP mutation, consent or operation routes. | `0077_integration_read_snapshots` |
| [3 — #979](https://github.com/Mrclocks/PGClockBot/pull/979) | #978; **Draft** | `codex/integration-technical-operations` | Customer registration; durable provision/renew/add-on intents; private access; native ownership/fencing adapters and capacity accounting. No outbox or consent delivery. | `0079_integration_private_delivery` |
| [4 — #980](https://github.com/Mrclocks/PGClockBot/pull/980) | #979; **Draft** | `codex/integration-webhooks-outbox` | Transactional signed outbox, protected retries/transport, retained evidence and dual-proof Telegram consent. | `0080_integration_event_outbox` |
| [5 — #981](https://github.com/Mrclocks/PGClockBot/pull/981) | #980; **Draft** | `codex/integration-management-pages` | Authorized administration/customer/audit pages and CSRF/action-ticket controls; integration import grouping. | unchanged |
| [6 — #982](https://github.com/Mrclocks/PGClockBot/pull/982) | #981; **Draft** | `codex/integration-documentation` | Actual generated OpenAPI enrichment/export, backend example, compatibility/operation/rollback guides and this review index. | unchanged |

Each part has a separate review comparison:

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

The published branches incorporate dev 0.5.5 (`98749f49`) through normal merges.
After that synchronization, the foundation migration/import/branding/frontend
checks passed **106 tests, no skips, 19 subtests**, and the assembled
disabled/settings/API/management/scheduler/branding checks passed **73 tests and
19 subtests**. The lint ratchet passed for 25 foundation and 166 assembled changed
Python files; inherited Mini App branding Node checks passed all 8 cases. These
focused checks do not relabel earlier broad results as new-head verification.
The
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
panel behavior. Keep dependent parts Draft until their prerequisites merge. Before merging the
mutating parts, obtain the separate live acceptance evidence; marking them ready
for review does not establish it. Runtime activation remains disabled. No
deployment or production activation was performed.

The [Persian rollback guide](INTEGRATION_API_ROLLBACK_FA.md) separates installations
that never activated integration from those that may have sent a panel request.
Retain mappings, targets, tombstones, guards, commitments, consent, outbox, root and
signing keys, and execution history. A pre-feature binary is not a safe fallback
once website services or uncertain effects exist.
