# PGClockBot v8.2.4 — Release Notes

**Tag:** `v8.2.4`  
**App version:** `8.2.4`  
**Restore point:** tag `restore/pre-unify-load-veil-v8.2.3` (@ `v8.2.3`)

## What changed

**One loading UI only** — the global matte clock veil (`#page-load-veil`).

- Removed in-page clock placeholders from deferred `/home`, reseller home, and `/pg`
- While `/home/body` or `/pg/body` is fetching, the same matte veil stays up (early `page-ready` is held)
- Soft navigation still uses the same veil after ~150ms

## What this does *not* change

- Shell-first authz / body re-auth unchanged
- No migrations

## Update

In-panel update to `8.2.4` (no new migration). Hard-refresh the panel after update.
