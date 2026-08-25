# PGClockBot v8.5.13 — Release Notes

**Tag:** `v8.5.13`
**App version:** `8.5.13`
**Restore point:** tag `v8.5.12`

## Fixes

1. **Mobile black bar — revert to pre-v8.5.4 layout**
   - Symptom: Persistent black strip at the bottom on iPhone when entering pages (regression since v8.5.4–v8.5.12 fix attempts).
   - Root: Recent changes (`position:fixed` shell, `--vvh`/`visualViewport` hacks, `ios-safari` CSS, sticky footer with `margin-top:auto`, sidebar `bottom:0`) altered the mobile layout from the working v8.5.3 pattern.
   - Fix: Restore v8.5.3 mobile shell — flex column with `100dvh`, no fixed shell, no `--vvh` script, `main-body { flex: 0 0 auto }`, footer `margin-top: 0`, sidebar explicit `100dvh` height calc.

2. **Mobile header height & padding**
   - `--topbar-h` increased from 52px to 58px.
   - Equal top/bottom content padding via `--topbar-pad-y`.

## Deploy

In-panel update to `8.5.13`. Hard-refresh Safari (or close tab and reopen) to reload `panel.css`.
