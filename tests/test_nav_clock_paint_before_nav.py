"""Nav clock must paint before MPA navigation (WebKit).

Closing the drawer during a default click (off-screen slide +
pointer-events:none on .side) cancelled or skipped the paint on iOS Safari, so
heavy targets like /plans often never showed the clock. Production must
preventDefault, arm the clock, then location.assign on the next animation frame.
"""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "app/web/static/panel.js"
BASE = ROOT / "app/web/templates/base.html"


class NavClockPaintBeforeNavTests(unittest.TestCase):
    def test_click_path_assigns_after_raf(self):
        js = JS.read_text(encoding="utf-8")
        self.assertIn("e.preventDefault()", js)
        self.assertIn("requestAnimationFrame", js)
        self.assertIn("location.assign", js)
        # Arm before the assign frame.
        arm_at = js.find("arm();")
        raf_at = js.find("requestAnimationFrame(function () {\n          window.location.assign")
        self.assertGreater(arm_at, 0)
        self.assertGreater(raf_at, arm_at)

    def test_panel_js_is_not_deferred(self):
        """defer raced the first tap after paint; sync at end-of-body is enough."""
        base = BASE.read_text(encoding="utf-8")
        self.assertIn('src="/static/panel.js?v={{ app_version }}"', base)
        self.assertNotIn('panel.js?v={{ app_version }}" defer', base)

    def test_critical_boot_hides_desk_brand_on_mobile(self):
        """Without panel.css, both brands used to show on a black void (image 3)."""
        base = BASE.read_text(encoding="utf-8")
        self.assertIn('id="panel-critical-boot"', base)
        self.assertIn(".desk-only { display: none !important; }", base)
        # No second drawer model — visibility/right:0 fought panel.css.
        boot = base.split('id="panel-critical-boot"', 1)[1].split("</style>", 1)[0]
        self.assertNotIn("visibility:", boot)
        self.assertNotIn(".side {", boot)
        self.assertIn('rel="preload"', base)
        self.assertIn("/static/panel.css?v={{ app_version }}", base)


if __name__ == "__main__":
    unittest.main()
