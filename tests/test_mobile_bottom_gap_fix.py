"""Mobile bottom-gap root fix — one scroll owner, one safe-area owner, no desktop bleed."""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "app/web/static/panel.css"
PROBE = ROOT / "tests/mobile_layout_probe.py"
FIXTURE_SHORT = ROOT / "tests/fixtures/mobile_shell_probe.html"
FIXTURE_LONG = ROOT / "tests/fixtures/mobile_shell_probe_long.html"


class MobileBottomGapCssTests(unittest.TestCase):
    def _mobile(self) -> str:
        return CSS.read_text(encoding="utf-8").split("@media (max-width: 900px)", 1)[1]

    def test_shell_owns_safe_bottom_once(self):
        mobile = self._mobile()
        shell = mobile.split(".shell {", 1)[1].split("  .topbar", 1)[0]
        self.assertIn("padding-bottom: var(--safe-bottom);", shell)
        self.assertNotIn("--safari-overlay", mobile)
        self.assertNotIn("--vvh", mobile)
        self.assertNotIn("100lvh", shell)

    def test_main_resets_desktop_height_cap(self):
        mobile = self._mobile()
        main = mobile.split("  .main {", 1)[1].split("  .main-body", 1)[0]
        self.assertIn("height: auto;", main)
        self.assertIn("max-height: none;", main)
        self.assertIn("flex: 1 1 0;", main)
        self.assertIn("padding: var(--page-title-gap) var(--space-2) var(--foot-gap);", main)
        self.assertNotIn("calc(var(--foot-gap) + var(--safe-bottom))", main)

    def test_side_stretches_with_bottom_zero_not_calc_dvh(self):
        mobile = self._mobile()
        side = mobile.split("  .side {", 1)[1].split("  .side.open", 1)[0]
        self.assertIn("bottom: 0;", side)
        self.assertIn("height: auto;", side)
        self.assertIn("max-height: none;", side)
        self.assertNotIn("100dvh - var(--topbar-h)", side)

    def test_no_document_lock_or_viewport_js(self):
        mobile = self._mobile()
        base = (ROOT / "app/web/templates/base.html").read_text(encoding="utf-8")
        js = (ROOT / "app/web/static/panel.js").read_text(encoding="utf-8")
        self.assertNotIn("html:has(.shell)", mobile)
        self.assertNotIn("visualViewport", base)
        self.assertNotIn("visualViewport", js)
        self.assertNotIn("--vvh", base)
        self.assertNotIn("html.ios-safari .shell", mobile)

    def test_desktop_main_still_has_safe_bottom(self):
        css = CSS.read_text(encoding="utf-8")
        desktop_main = css.split(".main {\n", 1)[1].split("\n}", 1)[0]
        self.assertIn("calc(var(--foot-gap) + var(--safe-bottom))", desktop_main)

    def test_auth_wrap_uses_dvh_not_lvh(self):
        css = CSS.read_text(encoding="utf-8")
        auth = css.split(".auth-wrap {", 1)[1].split("}", 1)[0]
        self.assertIn("min-height: 100dvh;", auth)
        self.assertNotIn("100lvh", auth)


@unittest.skipUnless(PROBE.exists(), "geometry probe script missing")
class MobileBottomGapGeometryTests(unittest.TestCase):
    def _run_probe(self, fixture: Path) -> dict:
        env = {"MOBILE_PROBE_FIXTURE": str(fixture)}
        proc = subprocess.run(
            [sys.executable, str(PROBE)],
            capture_output=True,
            text=True,
            cwd=ROOT,
            env={**dict(**__import__("os").environ), **env},
            check=False,
        )
        if proc.returncode != 0:
            self.fail(proc.stdout + "\n" + proc.stderr)
        return json.loads(proc.stdout)

    def test_short_page_geometry(self):
        out = self._run_probe(FIXTURE_SHORT)
        for key in (
            "main_fills_shell_content_box",
            "no_shell_viewport_gap",
            "footer_gap_is_foot_gap_only",
            "main_max_height_unbounded",
        ):
            self.assertTrue(out["checks"][key], f"failed {key}: {out}")

    def test_long_page_scrolled_bottom(self):
        out = self._run_probe(FIXTURE_LONG)
        for key in (
            "long_scroll_reaches_footer",
            "footer_gap_is_foot_gap_only",
            "no_extra_scroll_blank",
        ):
            self.assertTrue(out["checks"][key], f"failed {key}: {out}")


if __name__ == "__main__":
    unittest.main()
