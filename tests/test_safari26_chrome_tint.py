"""Browser-chrome tint: no overlay may colour Safari's own toolbars.

Safari 26+ (iOS 26 Liquid Glass) picks the colour of its status bar and its
bottom tab bar from `position: fixed` boxes that touch a viewport edge, reading
their `background-color` / `backdrop-filter` — and it does NOT re-sample when
such a box disappears. The drawer backdrop used to carry its dim on the fixed
box itself, so opening the drawer painted the bottom bar solid dark and closing
the drawer left it that way: the "black bar that never turns transparent again".

The rule this file locks in: a full-viewport fixed overlay keeps its own box
transparent and paints on an absolute child, so the bottom bar always falls back
to the (opaque) html/body background and is identical in every overlay state.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from css_blocks import declarations, has_rule, rule


ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "app/web/static/panel.css"
BASE = ROOT / "app/web/templates/base.html"

TRANSPARENT = "background: transparent;"


class ChromeTintSourceTests(unittest.TestCase):
    def setUp(self):
        # utf-8-sig: the stylesheet starts with a BOM, which would otherwise be
        # part of the first selector (":root") and hide that block.
        self.css = CSS.read_text(encoding="utf-8-sig")

    def test_drawer_backdrop_dim_is_not_on_the_fixed_box(self):
        back = declarations(rule(self.css, ".side-backdrop"))
        self.assertIn("position: fixed;", back)
        self.assertIn("inset: 0;", back)
        self.assertIn(TRANSPARENT, back)
        self.assertNotIn("rgba(0, 0, 0, 0.55)", back)
        self.assertNotIn("backdrop-filter", back)

        dim = declarations(rule(self.css, ".side-backdrop::before"))
        self.assertIn("position: absolute;", dim)
        self.assertIn("inset: 0;", dim)
        self.assertIn("background: var(--side-dim);", dim)

    def test_dim_has_one_owner_per_theme(self):
        self.assertIn("--side-dim: rgba(0, 0, 0, 0.55);", rule(self.css, ":root"))
        self.assertIn(
            "--side-dim: rgba(0, 0, 0, 0.32);",
            rule(self.css, 'html[data-theme="light"]'),
        )
        # The light theme must retint the token, never repaint the fixed box.
        for selector in (
            'html[data-theme="light"] .side-backdrop',
            'html[data-theme="light"] .side-backdrop.show',
        ):
            self.assertFalse(has_rule(self.css, selector), selector)

    def test_loading_matte_is_not_on_the_fixed_box(self):
        clock = declarations(rule(self.css, ".panel-nav-clock"))
        self.assertIn("position: fixed;", clock)
        self.assertIn(TRANSPARENT, clock)
        self.assertNotIn("color-mix", clock)

        matte = declarations(rule(self.css, ".panel-nav-clock::before"))
        self.assertIn("position: absolute;", matte)
        self.assertIn("inset: 0;", matte)
        self.assertIn("color-mix(in srgb, var(--background, #09090b) 72%, transparent)", matte)
        # Positioned boxes paint above in-flow siblings, so the matte needs a
        # negative index or it would veil the clock dial it sits behind.
        self.assertIn("z-index: -1;", matte)

    def test_modal_backdrop_stays_an_absolute_child(self):
        modal = declarations(rule(self.css, ".ui-modal"))
        self.assertIn("position: fixed;", modal)
        self.assertNotIn("background", modal)
        self.assertNotIn("backdrop-filter", modal)
        self.assertIn("position: absolute;", declarations(rule(self.css, ".ui-modal-backdrop")))

    def test_drawer_never_covers_the_sampling_width(self):
        """A fixed box wider than ~80% of the viewport is a tint candidate too.

        The drawer is fixed to the bottom edge and cannot move its background to
        an absolute child (it scrolls its own content), so it stays narrower
        than the threshold on every phone width instead.
        """
        self.assertIn("--drawer-w: min(300px, 78vw);", rule(self.css, ":root"))

    def test_root_background_is_the_opaque_fallback(self):
        """With no candidate, Safari samples the root — it must not be transparent."""
        root = declarations(rule(self.css, "html, body"))
        self.assertIn("background-color: var(--background);", root)
        self.assertIn('viewport-fit=cover', BASE.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
