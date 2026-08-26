"""No nav skeleton + PG overview footer gap."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "app/web/static/panel.css"
JS = ROOT / "app/web/static/panel.js"
BASE = ROOT / "app/web/templates/base.html"
PG_HOME = ROOT / "app/web/templates/pg_home.html"
PG_DASH = ROOT / "app/web/templates/_pg_dash_body.html"
PG_LIVE = ROOT / "app/web/templates/_pg_live_metrics_script.html"


class NoNavSkeletonTests(unittest.TestCase):
    def test_no_skeleton_intercept_in_js(self):
        js = JS.read_text(encoding="utf-8")
        self.assertNotIn("page-loading", js)
        self.assertNotIn("armSkeleton", js)
        self.assertNotIn("SKELETON_WAIT_MS", js)

    def test_base_has_no_loading_classes(self):
        html = BASE.read_text(encoding="utf-8")
        self.assertNotIn("page-loading", html)
        self.assertNotIn("__pgPageReveal", html)


class PgOverviewFooterGapTests(unittest.TestCase):
    def test_home_panels_last_child_zero_margin(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn(".main-body > .home-panels:last-child {\n  margin-bottom: 0;\n}", css)

    def test_home_panel_hugs_content(self):
        css = CSS.read_text(encoding="utf-8")
        block = css.split(".home-panel {\n", 1)[1].split("}", 1)[0]
        self.assertIn("height: auto;", block)

    def test_pg_metrics_script_outside_main_body(self):
        html = PG_HOME.read_text(encoding="utf-8")
        content = html.split("{% block content %}", 1)[1].split("{% endblock %}", 1)[0]
        self.assertNotIn("<script>", content)
        self.assertIn("{% block page_scripts %}", html)
        live = PG_LIVE.read_text(encoding="utf-8")
        self.assertIn("panel-widgets-ready", live)


if __name__ == "__main__":
    unittest.main()
