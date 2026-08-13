# PGClockBot v6.0.0 — Release Notes

**Tag:** `v6.0.0`
**App version:** `6.0.0`

---

## Security hardening (2026-08 audit)

This release closes every issue found in the 2026-08 security audit of the bot
and web panel, focused on tenant isolation (resellers/users must never see or
touch data or permissions that don't belong to them) and secret handling.

### High severity

- **Cross-shop payment leak** — `suggest_receipt_matches` no longer lets a
  reseller see other shops' pending payments/orders when matching a receipt.
- **X-Forwarded-For spoofing** — client-IP resolution (used by the login
  lockout and the local-IP setup-wizard gate) now reads the trusted hop
  counted from the right (`TRUST_PROXY_HOPS`), instead of blindly trusting the
  left-most, attacker-controlled entry.

### Medium severity

- `pg_staff` accounts without a shop can no longer see platform-wide settings
  or counters on the `/inbox` page.
- Toggling a gift/charge code now requires real shop authorization; a
  shopless `pg_staff` can no longer flip platform-level codes.
- A temporary PasarGuard outage no longer gets misclassified as "admin
  deleted" and permanently revoking a legitimate staff member's web access.
- Hybrid Owner setups (platform `.env` PasarGuard account with a *limited*
  admin) now have their own group/template restriction enforced in the web
  panel, instead of being treated as fully unrestricted.
- The bot's PasarGuard node/user action buttons now enforce the same
  create/update/delete/reconnect action matrix as the web panel.
- Four pre-existing security regression tests that only asserted on raw
  source-code strings were rewritten as real behavioral tests.

### Low severity

- The setup wizard no longer echoes `BOT_TOKEN` / `PG_PASSWORD` into the
  rendered HTML source; re-running the wizard no longer requires re-entering
  secrets that were already saved.
- The one-time setup-wizard URL (which carries a live gate token) is no
  longer written to logs.
- Reseller PasarGuard passwords are now encrypted with a key derived from
  `WEB_SECRET` via HKDF (domain-separated from session-cookie signing),
  with transparent backward-compatible decryption of previously encrypted
  secrets — no data migration needed.
- The SQLite database file (and its WAL/SHM/journal siblings) is now pinned
  to `0600` permissions.
- `/setup/bot` now rejects placeholder/example bot tokens.
- `POST /pg/groups` now validates submitted inbound tags against the
  admin's own PasarGuard inbounds instead of trusting raw form input.
- Fixed a stale PasarGuard client-cache key that could keep authenticating
  as a reseller's *previous* PasarGuard admin after re-linking.

### New: automated security regression suite

- `scripts/security_test_manifest.txt` lists every security-relevant test
  file from this audit.
- `scripts/run_security_tests.sh` runs exactly that curated suite.
- `.github/workflows/security-tests.yml` runs the suite on every push and
  pull request, so a future patch can never silently reintroduce one of
  these issues.

## Compatibility

- No database migration required. Existing encrypted PasarGuard passwords
  keep decrypting correctly under the new key-derivation scheme.
- No breaking changes to panel UI or bot menus/flows — every fix is either
  an additional authorization/validation check or a bug fix in existing
  scoping logic.

## Deploy

In-panel update to `6.0.0` (or deploy this tag). No manual migration steps
are required.
