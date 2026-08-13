# PGClockBot v5.2.5 — Release Notes

**Tag:** `v5.2.5`  
**App version:** `5.2.5`

---

## Bug

On servers where **مرکز اقدام امروز** had at least one item (pending receipts, open tickets, delivery failures, …), Jinja treated `ac.items` as `dict.items` (the method), not the action list. Template render raised `TypeError`, the v5.2.4 fail-soft shell kicked in, and the dashboard showed Bot / PasarGuard / Nodes as **قطع** with «بارگذاری ناقص» — even though connections were fine. CPU/RAM still updated via `/home/metrics`.

Servers with an empty action center looked healthy — which matched the “one server OK, one broken” report.

## Fix

- Action center payload key renamed to `entries` (avoids Jinja/dict method clash).
- `home.html` / `reseller_home.html` loop over `ac.entries`.
- Regression test covers the trap.

## Deploy

Deploy `v5.2.5` and hard-refresh `/home`. Connection status should reflect real bot/PG/node probes again whenever the action center has items.
