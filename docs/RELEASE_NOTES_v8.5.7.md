# PGClockBot v8.5.7 — Release Notes

**Tag:** `v8.5.7`
**App version:** `8.5.7`
**Restore point:** tag `v8.5.6`

## Fixes

1. **Mobile "black bar" — the actual root cause, found and fixed**
   - While preparing this release, code review caught a critical bug introduced alongside the previous (`8.5.6`) fix attempt: the HTML comment added to `base.html` to explain the `theme-color` meta tag was closed with a JS-style `*/` instead of `-->`. Because that file has no other `-->` anywhere, an HTML parser treats **everything after that point as one giant unterminated comment** — the whole rest of the document (every `<meta>`, script, and all page content in every template that extends `base.html`) would never become real DOM. This alone would have been catastrophic; it's fixed now, and a new regression test (`HtmlCommentBalanceGuardTests` in `tests/test_panel_ui_guards.py`) scans every template for unterminated HTML comments so this class of bug can never silently reappear.
   - Separately, the actual black-bar mechanism was root-caused: two conditional `<meta name="theme-color" media="...">` tags never both worked, because per the HTML spec the browser picks the *first* tag whose `media` matches (a tag with no `media` always matches), so the second tag was dead code — `theme-color` was never actually kept in sync with the resolved theme. Replaced both with a single tag (`id="meta-theme-color"`) whose `content` is set synchronously in `<head>`, before first paint, and kept in sync by the theme switcher in `panel.js`.
   - Beyond `--vvh` (window-measured viewport height, resampled several times after every load and on `visibilitychange`/`focus`), a real (not synthetic) 1–2px scroll-and-back "nudge" now runs on every full page load, `pageshow`, and tab-resume — the same trigger users found fixes it manually when they scroll — to work around the underlying Android/Chromium standalone-PWA gesture-navigation-bar repaint timing issue, which is a documented platform limitation (browsers largely don't guarantee bottom system-bar theming for installed PWAs, especially with gesture navigation) rather than something purely fixable from CSS/HTML. This is the most robust mitigation available at the web-platform level.

2. **Bot users table — redesigned again per explicit feedback: separate columns, no merging**
   - The single merged `سرویس · حجم · انقضا` cell from `8.5.6` is reverted. `سرویس`, `حجم`, and `انقضا` are three separate, always-visible `<th>`/`<td>` columns again — on both desktop and mobile, never hidden and never merged.
   - Mobile no longer forces `table-layout: fixed` with cramped widths to make everything fit; each column gets its own `min-width` for full legibility, and the table's existing `.table-wrap` horizontal-scroll behavior (the same fallback every other table in the panel already uses) takes over when the table is wider than the viewport — content stays clear at the cost of a horizontal scroll on narrow phones, exactly as requested.
   - The multi-service switcher (`select`, boxed dropdown rows) lives in the `سرویس` column and stays full-width and standard-sized — never cramped — so plan names are always fully readable. Switching services still instantly updates the sibling `حجم`/`انقضا` cells and the per-service alert dot/row highlight.

3. **Test suite — 15 outdated failing tests repaired**
   - All 15 pre-existing failures were fixed in place (none deleted) — they were asserting against template paths/structures that had moved during earlier refactors (dashboard widgets deferred into `_*_dash_body.html` partials, `pure_reseller` filtering moved into `app/services/users_ops.py`, plan-finish flow wrapped by `_pending_user_plan_finish`, etc.), a brittle hardcoded Alembic head revision, and one test with a global-state leak (`setup_complete.flag`) now properly isolated with mocks. Full suite: 2640 passed, 3 skipped.

## Deploy

In-panel update to `8.5.7` (no new migration). Hard-refresh after update.
