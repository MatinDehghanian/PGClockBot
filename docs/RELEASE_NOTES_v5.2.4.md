# PGClockBot v5.2.4 — Release Notes

**Tag:** `v5.2.4`  
**App version:** `5.2.4`

---

## Why one server was still 500 after v5.2.3

The custom Persian 500 page meant v5.2.3 was deployed, but login could still die **before** `/home` fail-soft ran:

1. **`_panel_redirect`** (used on successful login and “already logged in” → dashboard) could raise if SSL/public-URL helpers failed on that host.
2. **`ensure_web_secret` / cookie signing** could raise if `.env` was not writable when generating `WEB_SECRET`.
3. **`get_session_user`** only caught bad signatures — other signer failures became 500.

## Fixes

- `_panel_redirect`, `https_is_active`, `public_panel_base_url`, `ensure_web_secret` — never raise; safe fallbacks.
- Login cookie sign failure → friendly login error (not blank 500).
- `/home` wrapped in outer fail-soft shell for admin and reseller.
- 500 page shows opaque `ref ……` matching server logs (no secrets/traces). Links go to `/login` + `/logout`.

## Deploy

1. Backup.
2. Deploy `main` / tag `v5.2.4` on the **broken** server.
3. If login still fails, check panel logs for `unhandled error ref=` or `persisting WEB_SECRET failed` / `_panel_redirect`.
4. Ensure `.env` is writable by the panel user and `WEB_SECRET` is set to a long random value.
