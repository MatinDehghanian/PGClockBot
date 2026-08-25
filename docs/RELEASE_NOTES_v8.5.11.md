# PGClockBot v8.5.11 — Release Notes

**Tag:** `v8.5.11`
**App version:** `8.5.11`
**Restore point:** tag `v8.5.10`

## Fixes

1. **iOS Safari in-browser black bar (not Home Screen PWA)**
   - Root: In Safari, `position: fixed` anchors to the **layout viewport**, but the visible area is `visualViewport` — offset and shorter when the address/tab bars are shown. v8.5.10 sized `.shell` with `innerHeight` / layout metrics, so the shell painted **above** the visible bottom → dead black strip and clipped content.
   - Fix: detect `html.ios-safari` (iOS + not standalone). `--vvh` = `visualViewport.height`, `--vv-top` = `visualViewport.offsetTop`. Mobile `.shell`, `.topbar`, `.side`, and `.side-backdrop` use `top: var(--vv-top)`. Re-sync on `visualViewport.resize` and `orientationchange` only (no scroll listener — avoids jitter).

## Deploy

In-panel update to `8.5.11`. Hard-refresh in Safari (or close tab and reopen).
