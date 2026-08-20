# PGClockBot v8.1.9 — Release Notes

**Tag:** `v8.1.9`  
**App version:** `8.1.9`  
**Restore point:** branch `cursor/restore-before-panel-safe-speed-ffcf` / tag `restore/pre-panel-safe-speed-v8.1.8` (@ `v8.1.8`)

---

## Panel safe speed

- Request timing for panel pages (`Server-Timing` + logs) — observation only; auth/ACL untouched.
- `/home` shell-first after `require_staff`; decorative widgets load from `/home/body` with the same server authz.
- Escape hatch: `/home?full=1`. No SPA / `panelNavigate`.
- 3s timeouts only for display probes (unchecked on timeout — never Allow).
- `/pg`: short display-probe timeout; full HTML kept so live-metrics scripts still run.

## Deploy

In-panel update to `8.1.9` (no new migration vs `v8.1.8`). Hard-refresh the panel after update.
