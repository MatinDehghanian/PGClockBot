# v8.5.38 — Revert broken Liquid Glass experiments

## What went wrong (v8.5.35–37)

Transparent `shell` / `main` / `.side.open` + `::before` “glass” paint made the
open drawer see-through (dashboard bled through the menu) and left a white strip
under dark-theme pages in Safari (`html`/`body` transparent → browser default).

## This release

- **Remove** all of those paint hacks (transparent shell/main/side, closed
  `height:0`, gutter-clipped backdrop, transparent `theme-color`).
- **Restore** opaque v8.5.34 surfaces: `.side` / `.main` / `html`/`body` use
  normal theme backgrounds again.
- **Keep** instant sidebar close before nav clock (`side-nav-closing`).
- Backdrop is full-width `rgba(0,0,0,0.55)` again — same in Safari and PWA.

SW: `pgclock-shell-v29`. Restore: `v8.5.34`.
