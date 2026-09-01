"""Footer one-path: side-foot and site-footer share separator Y on all viewports."""

from __future__ import annotations

import unittest
from pathlib import Path

from css_blocks import at_rule, rule

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")

LOCKED = "min-height: calc(var(--footer-bar-h) + var(--bottom-inset));"
LOCKED_MAX = "max-height: calc(var(--footer-bar-h) + var(--bottom-inset));"
PAD = "padding-bottom: var(--bottom-inset);"


class FooterOnePathTests(unittest.TestCase):
    def test_parents_do_not_own_bottom_inset(self):
        """Dual path (.side/.main padding-bottom + footer pad) split separators."""
        side = rule(CSS, ".side")
        main = rule(CSS, ".main")
        self.assertIn("padding: var(--space-2) var(--space-2) 0;", side)
        self.assertNotIn("var(--bottom-inset)", side)
        self.assertIn("padding: var(--page-title-gap) var(--space-4) 0;", main)
        self.assertNotIn("var(--bottom-inset)", main)

    def test_both_footers_lock_same_box(self):
        site = rule(CSS, ".site-footer")
        side_foot = rule(CSS, ".side-foot")
        for body in (site, side_foot):
            self.assertIn(PAD, body)
            self.assertIn(LOCKED, body)
            self.assertIn(LOCKED_MAX, body)
            self.assertIn("overflow: hidden;", body)
            self.assertIn("padding-top: var(--page-title-gap);", body)

    def test_side_foot_stays_single_row(self):
        user = rule(CSS, ".side-foot-user")
        self.assertIn("flex-wrap: nowrap;", user)
        # Multi-line identity must not inflate the locked footer height
        self.assertIn(".side-foot .identity-chips,", CSS)
        self.assertIn(".side-foot .identity-pg-role {", CSS)
        hide = CSS.split(".side-foot .identity-chips,", 1)[1].split("}", 1)[0]
        self.assertIn("display: none;", hide)

    def test_mobile_reinforces_same_path(self):
        mobile = at_rule(CSS, "@media (max-width: 900px)")
        self.assertIn(PAD, rule(mobile, ".side .side-foot"))
        self.assertIn(PAD, rule(mobile, ".site-footer"))
        self.assertIn(LOCKED, rule(mobile, ".side .side-foot"))
        self.assertIn(LOCKED, rule(mobile, ".site-footer"))
        self.assertIn(
            "padding: var(--page-title-gap) var(--space-2) 0;",
            rule(mobile, ".main"),
        )
        self.assertIn("padding-bottom: 0;", rule(mobile, ".shell"))


if __name__ == "__main__":
    unittest.main()
