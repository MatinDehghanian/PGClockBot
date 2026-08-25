# PGClockBot v8.5.14 — Release Notes

**Tag:** `v8.5.14`
**App version:** `8.5.14`
**Restore point:** tag `v8.5.13`

## Fixes

1. **Mobile bottom layout — restore v8.2.8 (user-confirmed good version)**
   - User confirmed **v8.2.8** had correct bottom-of-page behavior on iPhone.
   - Diff vs v8.5.13: only footer flex pattern differed — v8.2.8 uses classic sticky footer:
     - `.main-body { flex: 1 0 auto }`
     - `.site-footer { margin-top: auto }` (desktop + mobile)
   - v8.5.13 had incorrectly reverted to v8.5.3's content-sized footer (`flex: 0 0 auto`, `margin-top: 0`).
   - Shell/mobile layout otherwise matches v8.2.8: flex column + `100dvh`, no `--vvh` hacks.

2. **Mobile header** (unchanged from v8.5.13)
   - `--topbar-h: 58px`, equal content padding via `--topbar-pad-y`.

## Deploy

In-panel update to `8.5.14`. Hard-refresh Safari to reload `panel.css`.
