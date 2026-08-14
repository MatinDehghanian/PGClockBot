"""Short-page footer/sidebar jump-on-first-scroll fix — take 2.

Bug: `.shell` / `.main` / `.side` sized their height off `100dvh` (dynamic
viewport height) alone. Many mobile browsers/WebViews still have their chrome
(address bar etc.) expanded on first paint and only collapse it after the
user's first scroll — `dvh` reports the smaller pre-collapse value on first
paint, so:
  - the footer (pinned to the bottom of `.main` via `margin-top: auto`) sits
    higher than the real screen bottom on short pages, and
  - `.side`'s background falls short of the real screen bottom, exposing the
    darker `body` background underneath.
Both self-correct the moment the user scrolls and the browser recomputes
`dvh` — the "fixes itself after one scroll" symptom the user originally
reported.

First (WRONG) attempted fix: layering a static `100svh` declaration after
every `100dvh` declaration. `svh` (small viewport height) always reports the
SMALLEST possible viewport (chrome maximally expanded) and — unlike `dvh` —
never recomputes afterwards. Being last in the cascade, it permanently
overrode `dvh`'s self-correcting behavior, turning the original *transient*
first-paint glitch into a *permanent* one (confirmed by user report: "قبلا با
اسکرول از بین میرفت ولی الان ثابت مونده"). That regression must never
reappear — see ``test_no_static_svh_unit_used`` below.

Actual fix: measure the real viewport with JS (``window.innerHeight``, which
always reflects the browser's current actual layout viewport on every engine,
unlike the newer/inconsistently-supported dvh/svh/lvh CSS units) and publish
it as the ``--vh`` custom property from an inline ``<script>`` in
``base.html``'s ``<head>`` — before first paint, so there's no flash — with
resize/orientationchange/visualViewport listeners so it *keeps* self-
correcting (device rotation, chrome collapsing later, on-screen keyboard,
etc.) instead of ever locking to one static value. CSS falls back
`100vh` → `100dvh` → `calc(var(--vh, 1vh) * 100)` so no-JS clients still get
the old (imperfect but self-correcting) dvh behavior instead of anything
worse.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
BASE_HTML = (ROOT / "app/web/templates/base.html").read_text(encoding="utf-8")


def _block(css: str, selector: str) -> str:
    return css.split(selector, 1)[1].split("}", 1)[0]


class ViewportVhVarTests(unittest.TestCase):
    def test_desktop_shell_uses_vh_var_after_dvh(self):
        shell = _block(CSS, "\n.shell {\n")
        self.assertIn("height: 100dvh;", shell)
        self.assertIn("height: calc(var(--vh, 1vh) * 100);", shell)
        self.assertIn("max-height: calc(var(--vh, 1vh) * 100);", shell)
        # --vh must win the cascade (declared after dvh).
        self.assertLess(
            shell.find("height: 100dvh;"),
            shell.find("height: calc(var(--vh, 1vh) * 100);"),
        )

    def test_desktop_side_and_main_have_vh_var_max_height(self):
        side = _block(CSS, "\n.side {\n")
        self.assertIn("max-height: 100dvh;", side)
        self.assertIn("max-height: calc(var(--vh, 1vh) * 100);", side)
        self.assertLess(
            side.find("max-height: 100dvh;"),
            side.find("max-height: calc(var(--vh, 1vh) * 100);"),
        )

        main = _block(CSS, "\n.main {\n")
        self.assertIn("max-height: 100dvh;", main)
        self.assertIn("max-height: calc(var(--vh, 1vh) * 100);", main)
        self.assertLess(
            main.find("max-height: 100dvh;"),
            main.find("max-height: calc(var(--vh, 1vh) * 100);"),
        )

    def test_mobile_breakpoint_uses_vh_var(self):
        mobile = CSS.split("@media (max-width: 900px) {", 1)[1]
        shell = _block(mobile, ".shell {\n")
        self.assertIn("min-height: 100dvh;", shell)
        self.assertIn("min-height: calc(var(--vh, 1vh) * 100);", shell)

        side = _block(mobile, ".side {\n")
        self.assertIn("height: calc(100dvh - var(--topbar-h) - var(--safe-top));", side)
        self.assertIn(
            "height: calc((var(--vh, 1vh) * 100) - var(--topbar-h) - var(--safe-top));", side
        )
        self.assertIn("max-height: calc(100dvh - var(--topbar-h) - var(--safe-top));", side)
        self.assertIn(
            "max-height: calc((var(--vh, 1vh) * 100) - var(--topbar-h) - var(--safe-top));", side
        )

        main = _block(mobile, ".main {\n")
        self.assertIn("min-height: calc(100dvh - var(--topbar-h) - var(--safe-top));", main)
        self.assertIn(
            "min-height: calc((var(--vh, 1vh) * 100) - var(--topbar-h) - var(--safe-top));", main
        )

    def test_auth_wrap_uses_vh_var(self):
        auth = _block(CSS, "\n.auth-wrap {\n")
        self.assertIn("min-height: 100dvh;", auth)
        self.assertIn("min-height: calc(var(--vh, 1vh) * 100);", auth)

    def test_no_static_svh_unit_used(self):
        """Regression guard: svh is a STATIC unit (always the smallest possible
        viewport, never recomputes) — using it as a dvh fallback previously made
        the transient first-paint glitch permanent instead of fixing it."""
        no_comments = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)
        self.assertNotIn("svh", no_comments)

    def test_footer_stays_non_fixed_not_re_pinned(self):
        # Regression guard against the *other* previously-tried fix for this
        # same bug report (pinning the footer instead of stabilizing the
        # viewport height), which made the .side height gap permanent.
        footer = _block(CSS, "\n.site-footer {\n")
        self.assertNotIn("position: fixed", footer)
        self.assertIn("margin-top: auto;", footer)

    def test_base_html_sets_vh_var_before_first_paint(self):
        # Must run in <head>, before the closing </head>, so there's no flash.
        head, _, _rest = BASE_HTML.partition("</head>")
        self.assertIn('setProperty("--vh"', head)
        self.assertIn("window.innerHeight", head)

    def test_base_html_keeps_vh_var_in_sync(self):
        head, _, _rest = BASE_HTML.partition("</head>")
        self.assertIn('addEventListener("resize"', head)
        self.assertIn('addEventListener("orientationchange"', head)


if __name__ == "__main__":
    unittest.main()
