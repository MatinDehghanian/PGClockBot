# PGClockBot v6.1.1 — Release Notes

**Tag:** `v6.1.1`
**App version:** `6.1.1`

---

## Test-suite maintenance (no functional or security changes)

This release contains **no behavior, security, or UI changes** to the bot or
web panel. It cleans up long-standing technical debt in the automated test
suite so `pytest tests/` and CI stay a trustworthy, always-green signal for
future patches.

Before this release the full suite reported 48 failing tests and 1 error —
all pre-existing and unrelated to the v6.0.0/v6.1.0 security hardening work.
They fell into three categories, all now fixed:

### 1. Stale exact-version pins (~31 tests)

Older test files hard-pinned `__version__` (and the `VERSION` file) to the
exact release string in effect when the test was written (mostly
`"4.10.9"`), which broke on every subsequent release bump even though the
underlying behavior was untouched. Converted to
`is_same_or_newer(__version__, "<version>")` (already used elsewhere for
update-check comparisons) so these stay green permanently.

### 2. Incomplete raw-SQL seed data (2 tests)

`bot_users.points_balance` is `NOT NULL` with only an ORM-level Python
default; two test helpers seeding rows via raw `INSERT` statements omitted
the column and hit a constraint failure. Added it to both statements.

### 3. Stale template/CSS/source snapshot assertions (~14 tests)

These tests asserted exact strings from templates, CSS, or source files that
had since changed through legitimate, intentional refactors (e.g. the
ticket-answered dashboard banner being generalized into the Action Center
work-queue card, orders+payments sidebar links merging into a single
"مدیریت مالی" item, icon border-radius moving to a shared design token).
Updated each assertion to match current behavior while preserving the
original test's intent. One trivial, purely cosmetic-neutral source fix rode
along: a raw `4px` inline style in `finance.html` was replaced with the
equivalent `--space-0` design token (identical rendered result).

## Compatibility

- No breaking changes, no database migrations, no config changes.
- Purely test-suite and CI reliability maintenance.

## Deploy

In-panel update to `6.1.1` (or deploy this tag). No manual steps required.
