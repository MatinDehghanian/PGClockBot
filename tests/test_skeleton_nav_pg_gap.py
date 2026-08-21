"""Nav skeleton without forced delay + PG overview footer gap."""

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


class NavSkeletonNoDelayTests(unittest.TestCase):
    def test_no_forced_min_delay(self):
        js = JS.read_text(encoding="utf-8")
        self.assertNotIn("minMs", js)
        self.assertIn("SKELETON_WAIT_MS", js)
        self.assertIn("__pgPageReveal", js)
        # Reveal on DOM ready, not window.load wait
        self.assertIn("DOMContentLoaded", js)

    def test_nav_intercept_shows_skeleton(self):
        js = JS.read_text(encoding="utf-8")
        self.assertIn("armSkeleton", js)
        self.assertIn("html.classList.add('page-loading')", js)
        self.assertIn("addEventListener('click'", js)
        self.assertIn("addEventListener('submit'", js)
        self.assertNotIn("sessionStorage.setItem('pg-page-nav'", js)

    def test_head_carries_nav_flag(self):
        html = BASE.read_text(encoding="utf-8")
        self.assertNotIn('sessionStorage.getItem("pg-page-nav")', html)
        self.assertNotIn('classList.add("page-loading")', html)
        self.assertNotIn(", 280)", html)
        self.assertIn("__pgPageReveal", html)
        self.assertNotIn("page-was-slow", html)

    def test_content_visible_without_nav(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertNotIn("html.page-booting .page-surface", css)
        self.assertIn("html.page-loading .page-load-veil", css)
        self.assertIn("html.page-loading .page-skeleton", css)
        # Departing page stays painted under the matte veil (no blank flash).
        block = css.split("html.page-loading .page-surface {", 1)[1].split("}", 1)[0]
        self.assertIn("opacity: 1", block)
        self.assertIn("visibility: visible", block)


class PgOverviewFooterGapTests(unittest.TestCase):
    def test_home_panels_last_child_zero_margin(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn(".main-body > .home-panels:last-child {\n  margin-bottom: 0;\n}", css)

    def test_home_panel_hugs_content(self):
        css = CSS.read_text(encoding="utf-8")
        block = css.split(".home-panel {\n", 1)[1].split("}", 1)[0]
        self.assertIn("height: auto;", block)
        self.assertNotIn("height: 100%;", block)

    def test_pg_metrics_script_outside_main_body(self):
        html = PG_HOME.read_text(encoding="utf-8")
        content = html.split("{% block content %}", 1)[1].split("{% endblock %}", 1)[0]
        self.assertNotIn("<script>", content)
        self.assertIn("{% block page_scripts %}", html)
        self.assertIn("_pg_live_metrics_script.html", html)
        # Widget markup lives in dash body; live poller stays outside content.
        dash = PG_DASH.read_text(encoding="utf-8")
        self.assertIn("data-pg-node-grid", dash)
        self.assertNotIn("<script>", dash)
        live = PG_LIVE.read_text(encoding="utf-8")
        self.assertIn("tickNodes", live)
        self.assertIn("panel-widgets-ready", live)


if __name__ == "__main__":
    unittest.main()
