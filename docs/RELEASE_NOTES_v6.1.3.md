# PGClockBot v6.1.3 — Release Notes

**Tag:** `v6.1.3`
**App version:** `6.1.3`

---

## Fixes a regression introduced in v6.1.2

v6.1.2 tried to fix the short-page footer/sidebar first-paint glitch by
layering a static `100svh` declaration after every `100dvh` declaration.
That was the wrong fix: `svh` (small viewport height) always reports the
**smallest** possible viewport (browser chrome fully expanded) and, unlike
`dvh`, **never recomputes afterwards**. Being last in the CSS cascade, it
permanently overrode `dvh`'s self-correcting behavior — turning the original
**transient** first-paint glitch (which used to fix itself after one scroll)
into a **permanent** one.

## Actual fix

Measure the real viewport with JavaScript instead of guessing with a
CSS-only unit:

- An inline `<script>` in `base.html`'s `<head>` (runs before first paint —
  no flash) reads `window.innerHeight` and publishes it as a `--vh` custom
  property.
- Listens on `resize`, `orientationchange`, and `visualViewport`'s `resize`
  event, so it keeps self-correcting on device rotation, chrome
  collapsing/expanding later, or the on-screen keyboard opening — it never
  locks to one static reading.
- The height cascade for `.shell`, `.side`, `.main` (desktop + mobile) and
  `.auth-wrap` is now `100vh` (universal fallback) → `100dvh` (self-correcting
  fallback for the rare no-JS case) → `calc(var(--vh, 1vh) * 100)`
  (authoritative once JS runs).
- No static `svh` unit is used anywhere — guarded by a regression test.

The footer remains **not** re-pinned with `position: fixed` (that was a
separate, previously-tried approach that also made the `.side` height gap
permanent — see `tests/test_footer_restore_3_1_3.py`).

## Tests

- `tests/test_viewport_svh_stable_layout.py` removed (asserted the wrong
  fix from v6.1.2).
- `tests/test_viewport_vh_var_stable_layout.py` added: verifies the
  `--vh` cascade in all four layout blocks, verifies the inline `<head>`
  script, and asserts no static `svh` unit is present anywhere.
- `tests/test_ux20_features.py::Ux20VersionTests` made forward-compatible
  (`is_same_or_newer`) instead of pinning an exact version string, so it
  stops breaking on every release bump.

## Compatibility

No breaking changes, no database migrations, no config changes.

## Deploy

In-panel update to `6.1.3` (or deploy this tag). Hard-refresh the panel.
