# PGClockBot v8.5.6 — Release Notes

**Tag:** `v8.5.6`
**App version:** `8.5.6`
**Restore point:** tag `v8.5.5`

## Fixes

1. **Mobile "black bar" — root cause fix**
   - Root: `.shell`/`.main`/`.side` sized themselves with `100dvh`. `dvh` is *supposed* to always track the browser's current toolbar (address bar) state, but several mobile engines settle on a stale/larger value for the first paint (before the toolbar's real state is "locked in"), so the shell was briefly taller than what was actually visible. The sticky-footer (`margin-top: auto`) then pinned the footer to the bottom of that too-tall box — below the real fold — leaving a gap of raw body background (near-black) at the bottom until a scroll forced a relayout.
   - Fix: an inline `<script>` in `<head>` (before any CSS/layout) measures `window.innerHeight` (falling back to `visualViewport.height` when available) synchronously and writes it to `--vvh` on `<html>`, updating on `resize`, `orientationchange`, `pageshow`, and `visualViewport` `resize`/`scroll`. `.shell`, `.side`, `.main`, and `.auth-wrap` now use `height: var(--vvh, 100dvh)` (falling back to `dvh` only if JS hasn't run). This is always accurate to the instantaneously visible viewport, so the footer never sits below the real fold — no more dependency on the browser's own `dvh` recompute timing. The previous JS `resize`-dispatch "nudge" (which didn't actually change any measured value) has been removed as it's now fully superseded.

2. **Bot users table — full redesign, service switching everywhere**
   - Previously, switching between a user's services (and seeing live volume/expiry per service, with a per-service alert dot) only worked on desktop — the whole `سرویس`/`حجم`/`انقضا` block was hidden below 1100px and mobile only got a static, non-interactive text summary of the *first* service.
   - Redesign: the three columns are merged into one `سرویس · حجم · انقضا` cell that is now **always visible** (desktop and mobile alike). It shows the service switcher (a `select` when a user has 2+ services) or a plain label (1 service), live volume + expiry text that updates instantly on switch, and an alert dot next to the switcher whenever the *currently selected* service has an active alert — matching exactly which service the alert is about, instead of a generic dot next to the user's name.
   - Mobile column widths were retuned (`table-layout: fixed` + explicit widths for name/service/status/actions) so the switcher stays reachable and the row-actions kebab never gets pushed off-screen, down to a 320px-wide viewport.

## Deploy

In-panel update to `8.5.6` (no new migration). Hard-refresh after update.
