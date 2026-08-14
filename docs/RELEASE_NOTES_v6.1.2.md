# PGClockBot v6.1.2 — Release Notes

**Tag:** `v6.1.2`  
**App version:** `6.1.2`

---

## UI — Viewport height

On short pages (footer visible on first paint), mobile browsers often report a
smaller `dvh` while chrome is still expanded. That made the footer sit too high
and exposed a dark strip under the sidebar until the first scroll.

Fix: layer `100svh` (stable viewport height) after every `100dvh` on
`.shell` / `.main` / `.side` and `.auth-wrap`. Layout is correct from the first
frame. Footer is **not** re-pinned with `position: fixed`.

## Restore point

Branch `cursor/restore-before-viewport-svh-5b2d` @ `54a0736` (v6.1.1).

## Deploy

In-panel update to `6.1.2` (or deploy this tag). Hard-refresh the panel.
