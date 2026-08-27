"""The ?vp=1 viewport diagnostic must be opt-in and must not perturb the page.

It reports the numbers that decide the iOS-only bottom-strip question, so it is
worthless if its own markup changes the geometry it measures, and dangerous if it
ships to every request or blocks the menu button.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from css_blocks import rule


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "app/web/templates/base.html"
PROBE = ROOT / "app/web/templates/_viewport_probe.html"


class ViewportProbeTests(unittest.TestCase):
    def setUp(self):
        self.base = BASE.read_text(encoding="utf-8")
        self.probe = PROBE.read_text(encoding="utf-8")
        # css_blocks matches braces, so hand it the stylesheet only — the Jinja
        # comment and the script around it are full of unbalanced braces.
        self.css = self.probe.split("<style>", 1)[1].split("</style>", 1)[0]

    def test_opt_in_only(self):
        self.assertIn(
            '{% if request.query_params.get(\'vp\') %}'
            '{% include "_viewport_probe.html" %}{% endif %}',
            self.base,
        )
        # Exactly one include site — no second, unguarded one.
        self.assertEqual(self.base.count("_viewport_probe.html"), 1)

    def test_unit_probes_cannot_add_scroll_height(self):
        """Four 100vh boxes in the flow would add ~4 viewports of scrollHeight.

        That would falsify the scrollH/maxScroll readings and hand Safari a
        scrollable page it otherwise would not have — changing the very toolbar
        behaviour under investigation.
        """
        units = rule(self.css, "#vp-units")
        self.assertIn("position: fixed;", units)
        self.assertNotIn("position: absolute;", units)
        self.assertIn("visibility: hidden;", units)
        for unit in ("100vh", "100svh", "100lvh", "100dvh"):
            self.assertIn(f"height: {unit};", self.probe)
        safe = rule(self.css, "#vp-safe")
        self.assertIn("position: fixed;", safe)

    def test_overlay_never_swallows_taps(self):
        """The drawer has to be opened while the probe is on screen."""
        overlay = rule(self.css, "#vp-probe")
        self.assertIn("pointer-events: none;", overlay)
        self.assertIn("pointer-events: auto;", rule(self.css, "#vp-probe button"))

    def test_reports_the_deciding_numbers(self):
        for needle in (
            "window.innerHeight",
            "de.clientHeight",
            "visualViewport",
            "display-mode: standalone",
            "safe-area-inset-top",
            "safe-area-inset-bottom",
            ".side-backdrop",
            ".site-footer",
        ):
            self.assertIn(needle, self.probe, needle)


if __name__ == "__main__":
    unittest.main()
