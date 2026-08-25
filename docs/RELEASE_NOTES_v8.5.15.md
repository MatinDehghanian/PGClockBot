# PGClockBot v8.5.15 — Release Notes

**Tag:** `v8.5.15`
**App version:** `8.5.15`
**Restore point:** tag `v8.5.14`

## Context

User confirmed **v8.2.8** had correct iPhone bottom layout. Reverting mobile shell/footer CSS did not fix the bug → root cause is **outside** that section.

Git diff shows mobile `@media (max-width: 900px)` shell/main/footer was **identical** from v8.2.8 through v8.2.12 and unchanged until v8.5.4+ hack cascade.

## Fixes

1. **Full revert of `panel.css` + `panel.js` to v8.2.12** (commit `f3d06a1`)

2. **Service worker stale cache** (`app/services/pwa.py`)
   - Bump cache to `pgclock-shell-v5`
   - Remove unversioned `panel.css` / `fonts.css` from precache
   - **Network-first** for `/static/panel.css` and `/static/panel.js` (versioned URLs)
   - Explains why layout reverts had no effect: broken CSS from v8.5.4–8.5.12 stayed cached

3. **Safari 26 tab bar sampling** (minimal, no layout dimension changes)
   - `html.ios-safari`: transparent `.shell`, bg on `.main` only
   - Closed drawer: `visibility: hidden` (fixed dark `.side` off-screen was still sampled)
   - Single `meta-theme-color`, `transparent` on ios-safari

## Deploy

1. Update to **8.5.15**
2. **Important:** Clear Safari site data OR unregister service worker once (Settings → Safari → Advanced → Website Data, or reinstall PWA)
3. Reopen site and verify bottom bar

Without step 2, old cached CSS may persist until SW updates.
