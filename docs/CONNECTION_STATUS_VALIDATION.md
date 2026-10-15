# Connection status validation

The implementation is reviewed against `upstream/dev` at
`3ffdffe291334ec54c34be2ca9352b1aa196d8e2`. The tested feature code is
`a7732b945d8f4efd26606daa245e65b980ad5eee`; subsequent documentation changes do not
change runtime behavior. The original [stage-zero baseline](CONNECTION_STATUS_BASELINE.md)
describes an earlier dev revision and is retained as historical evidence.

Live server testing and deployment are **skipped for this delivery**. No real
subscription, CONNECT relay, production resource budget or server restart result
is claimed. The feature and publication default to off. The PR remains Draft.

## Automated checks

Counts below are main tests; pytest subtests are reported separately, not added to
the passed-test count. Both full suites use the same local Python environment and
isolated checkouts. Tests do not use real credentials or network requests.

| Check | Clean dev | Feature code |
| --- | --- | --- |
| Full suite | 4269 passed, 78 failed, 11 skipped; 223 subtests passed | 4469 passed, 78 failed, 11 skipped; 338 subtests passed |
| Security manifest | 1758 passed; 207 subtests passed | 1958 passed; 322 subtests passed |
| Monitoring, Xray lifecycle and scheduler | — | 207 passed; 115 subtests passed |
| Existing scheduler, live-info and customer-feature tests | 114 passed; 11 subtests passed | 115 passed; 11 subtests passed |
| Lint ratchet against dev | — | 64 changed Python files; no added findings |
| Whitespace check | — | `git diff --check` passed |

JUnit test identities were compared, not just totals: the feature has **zero new
failures**, zero resolved baseline failures and exactly the same 11 skipped test
identities. All 78 full-suite failures also occur on clean dev. The full suite
therefore remains red for pre-existing failures; the security suite is green.

The unchanged 11 full-suite skips comprise eight missing Playwright prerequisites
and three pre-existing optional PostgreSQL prerequisites in `test_phase_a_database.py`.
The monitoring PostgreSQL job runs separately with its database available and has
no skips. Existing migration reflection warnings about a SQLite expression index
are not suppressed; the identity-index regression and EXPLAIN checks pass.

The monitoring suite covers account setup and encryption, nested panel Owner roles,
customer-account exclusion by ID and case-insensitive legacy username, main-bot
Owner authorization, shop isolation, active-host selection, capacity, native-route
validation, process cancellation, response cleanup, deadlines, health transitions,
leases, duplicate and late completion, manual cooldown, FSM/callback handling,
escaping, pagination and public reads without network or writes. These tests are
included in the security manifest. Existing tests were not weakened or skipped.

Migrations are `0055_connection_monitor` followed by
`0056_monitor_account_identity`, based on `0054_panel_alert_states`. Upgrade of
existing rows, repeated upgrade and downgrade preserving commerce rows pass on
SQLite and PostgreSQL. Alembic has one head, `0056_monitor_account_identity`.

Commands:

```bash
python -m pytest tests/test_connection_*.py tests/test_xray_probe.py tests/test_scheduler_background_jobs.py -q -p no:cacheprovider
bash scripts/run_security_tests.sh
bash scripts/lint_changed.sh upstream/dev --details
python -m pytest tests -q -p no:cacheprovider
alembic heads
git diff --check
```

Local versions: Python 3.12.5, HTTPX 0.28.1, SQLAlchemy 2.1.4, Alembic 1.20.0,
aiogram 3.31.0, FastAPI 0.143.1, Pydantic 2.13.5, APScheduler 3.11.3, pytest 9.1.1
and Ruff 0.17.0. `pip check` passed. No browser JavaScript changed. No new Python
dependency or copied third-party implementation was introduced; HTTPX and
APScheduler receive compatibility upper bounds.

## CI and official core

The [PostgreSQL compatibility job](https://github.com/Mrclocks/PGClockBot/actions/runs/38725293565/job/116389506537)
runs the complete monitoring suite against a disposable PostgreSQL 16 service.
The [Linux core job](https://github.com/Mrclocks/PGClockBot/actions/runs/38725293565/job/116389506216)
checks the pinned official Xray 26.3.27 archive, starts three synthetic routes,
observes child readiness and waits for process cleanup. Both jobs passed on the
tested feature commit. CI uses Python 3.12.15.

The [security job](https://github.com/Mrclocks/PGClockBot/actions/runs/38725293615/job/116389506381)
passed 1958 tests and 322 subtests on the same feature commit. The PostgreSQL job
passed 207 tests and 115 subtests, without skips.

The [compatibility matrix](CONNECTION_STATUS_COMPATIBILITY.md) records archive and
executable digests, supported static VLESS Reality/TCP and VLESS TLS/WebSocket
settings, and lifecycle limitations. Synthetic startup measurements:

| Environment | Routes | Startup | Cleanup | Peak child RSS | Child reaped |
| --- | --- | --- | --- | --- | --- |
| macOS / arm64 | 3 | 0.0924 s | 0.0025 s | 29664 KiB | yes |
| Linux / amd64 | 3 | 0.049 s | 0.0007 s | 35612 KiB | yes |

These numbers measure synthetic startup, not proxy throughput or live relay.
Cancellation, failed startup, bounded output, bind retry, checksum/version checks
and terminate/kill/wait have offline regression coverage. A parent's SIGKILL
cannot execute Python cleanup; the server's systemd cgroup behavior was not tested.

## Public-read measurements and query plans

An isolated database was seeded with 5000 synthetic historical targets and their
snapshots, including 12 public entries. One hundred first-page reads returned a
bounded page using exactly **300 SELECTs**, no writes, no panel calls, no HTTP
clients and no core starts. A subsequent page used four SELECTs. Measurements
include service execution and local DB access; they exclude Telegram and network
latency and are not production latency promises.

| Local database | 100 refreshes total | Median per refresh | p95 per refresh |
| --- | --- | --- | --- |
| SQLite | 208.82 ms | 1.95 ms | 2.50 ms |
| PostgreSQL | 467.48 ms | 3.79 ms | 7.06 ms |

EXPLAIN of the actual captured statements after ANALYZE showed:

- SQLite uses `ix_monitor_target_public` for ordered public pages,
  `ix_monitor_snapshot_scope_target` for snapshot lookup and `ix_monitor_target_due`
  for due candidates. Snapshot ordering sorts only the bounded candidate result.
- PostgreSQL uses `ix_monitor_target_public` for public pages and due candidate
  filtering, the target primary key for the update join and
  `uq_monitor_snapshot_endpoint` for snapshot lookup. The optimizer chooses a small
  result sort for ordering; no monitor-table scan was selected in this fixture.
- A separate 5000-row customer-service fixture proves both databases can use
  `ix_user_services_pg_user_id` and `ix_user_services_pg_username_lower` for the
  exclusion check. No customer record or credential leaves that check.

The 12-endpoint worker regression observes a peak of four concurrent fake probes
and zero active probes after completion. Deadline tests cancel pending work without
counting unobserved endpoints as failures. Separate-session races prove one global
worker winner and reject stale lease tokens; this is DB concurrency coverage,
not evidence of production CPU/RAM capacity.

## Deferred live acceptance

Live acceptance was removed from this delivery's execution scope. No production
service was changed. The following remain unverified in a real environment:

- A valid dedicated account relaying HTTPS through each supported transport, and
  invalid UUID or blocked-route failures despite successful direct control.
- Target fallback, account expiry, three failed rounds, two recovery rounds and
  stale results across real scheduler cycles and UI interactions.
- CPU/RAM/process/port/file use with 12 real endpoints, restart behavior and hard
  parent termination under the destination server's systemd unit.

The [operations guide](CONNECTION_STATUS_OPERATIONS.md) describes setup and gradual
activation. Public status reports the bot server's observation point; it does not
establish reachability from inside Iran. Remote probes, reseller management,
history, speed tests, notifications, Mini App and new web pages remain out of scope.
