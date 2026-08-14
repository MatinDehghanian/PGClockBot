"""Short-page footer/sidebar jump-on-first-scroll fix.

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
`dvh` — which is exactly the "fixes itself after one scroll" symptom.

Fix: layer a `100svh` (stable viewport height — always the smallest possible,
never changes with chrome visibility) declaration after every `100dvh`
declaration in the shell/main/side/auth-wrap height rules, so layout is
correct from the very first frame with no jump.

Guard against regressing to the OTHER previously-tried "fix": pinning
`.site-footer` with `position: fixed` (see test_footer_restore_3_1_3.py) —
that stopped the footer from jumping but made the `.side` height mismatch
(and its black gap) permanent instead of a transient first-paint glitch.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")


def _block(css: str, selector: str) -> str:
    return css.split(selector, 1)[1].split("}", 1)[0]


class StableViewportHeightTests(unittest.TestCase):
    def test_desktop_shell_has_stable_height_fallback(self):
        shell = _block(CSS, "\n.shell {\n")
        self.assertIn("height: 100dvh;", shell)
        self.assertIn("height: 100svh;", shell)
        self.assertIn("max-height: 100dvh;", shell)
        self.assertIn("max-height: 100svh;", shell)
        # svh must be declared after dvh so it wins the cascade.
        self.assertLess(shell.find("height: 100dvh;"), shell.find("height: 100svh;"))
        self.assertLess(
            shell.find("max-height: 100dvh;"), shell.find("max-height: 100svh;")
        )

    def test_desktop_side_and_main_have_stable_max_height(self):
        side = _block(CSS, "\n.side {\n")
        self.assertIn("max-height: 100dvh;", side)
        self.assertIn("max-height: 100svh;", side)
        self.assertLess(side.find("max-height: 100dvh;"), side.find("max-height: 100svh;"))

        main = _block(CSS, "\n.main {\n")
        self.assertIn("max-height: 100dvh;", main)
        self.assertIn("max-height: 100svh;", main)
        self.assertLess(main.find("max-height: 100dvh;"), main.find("max-height: 100svh;"))

    def test_mobile_breakpoint_has_stable_heights(self):
        mobile = CSS.split("@media (max-width: 900px) {", 1)[1]
        shell = _block(mobile, ".shell {\n")
        self.assertIn("min-height: 100dvh;", shell)
        self.assertIn("min-height: 100svh;", shell)
        self.assertLess(shell.find("min-height: 100dvh;"), shell.find("min-height: 100svh;"))

        side = _block(mobile, ".side {\n")
        self.assertIn("height: calc(100dvh - var(--topbar-h) - var(--safe-top));", side)
        self.assertIn("height: calc(100svh - var(--topbar-h) - var(--safe-top));", side)
        self.assertIn("max-height: calc(100dvh - var(--topbar-h) - var(--safe-top));", side)
        self.assertIn("max-height: calc(100svh - var(--topbar-h) - var(--safe-top));", side)

        main = _block(mobile, ".main {\n")
        self.assertIn("min-height: calc(100dvh - var(--topbar-h) - var(--safe-top));", main)
        self.assertIn("min-height: calc(100svh - var(--topbar-h) - var(--safe-top));", main)

    def test_auth_wrap_has_stable_min_height(self):
        auth = _block(CSS, "\n.auth-wrap {\n")
        self.assertIn("min-height: 100dvh;", auth)
        self.assertIn("min-height: 100svh;", auth)

    def test_footer_stays_non_fixed_not_re_pinned(self):
        # Regression guard against the *other* previously-tried fix for this
        # same bug report (pinning the footer instead of stabilizing the
        # viewport unit), which made the .side height gap permanent.
        footer = _block(CSS, "\n.site-footer {\n")
        self.assertNotIn("position: fixed", footer)
        self.assertIn("margin-top: auto;", footer)

    def test_svh_count_matches_dvh_count(self):
        # Every dvh declaration in the shell/main/side/auth-wrap chain must
        # have a matching svh fallback layered right after it — catches a
        # future dvh addition that forgets the svh companion. Strip comments
        # first so prose mentioning "dvh"/"svh" doesn't skew the count.
        no_comments = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)
        dvh = len(re.findall(r"\bdvh\b", no_comments))
        svh = len(re.findall(r"\bsvh\b", no_comments))
        self.assertEqual(dvh, svh, "every 100dvh/calc(...dvh...) needs a matching svh fallback")


if __name__ == "__main__":
    unittest.main()
