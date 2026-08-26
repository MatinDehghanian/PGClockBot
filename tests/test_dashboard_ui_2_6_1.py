"""UI polish 2.6.1 — PG counts, footer align, RAM ring, sidebar hover."""

from __future__ import annotations

import unittest
from pathlib import Path


class PgDashboardCountsTests(unittest.TestCase):
    def test_pg_home_users_admins_first(self):
        # pg_home.html now renders a fast chrome shell and defers the actual
        # stat widgets (users/admins/groups counts) to _pg_dash_body.html,
        # included directly on full page loads or swapped in async via
        # /pg/body — same markup, just no longer inlined in pg_home.html.
        src = Path("app/web/templates/_pg_dash_body.html").read_text(encoding="utf-8")
        users_i = src.find(">کاربران</span>")
        admins_i = src.find(">ادمین‌ها</span>")
        groups_i = src.find(">گروه‌ها</span>")
        self.assertGreater(users_i, 0)
        self.assertGreater(admins_i, users_i)
        self.assertGreater(groups_i, admins_i)
        self.assertNotIn(">تمپلیت‌ها</span>", src)
        self.assertIn("counts.admins", src)
        self.assertIn("counts.users", src)

    def test_overview_fetches_admins(self):
        src = Path("app/services/home_overview.py").read_text(encoding="utf-8")
        self.assertIn("get_admins_simple", src)
        self.assertIn('"admins"', src)
        self.assertNotIn("get_user_templates_simple", src)

    def test_pg_pages_counts_admins(self):
        src = Path("app/api/pg_pages.py").read_text(encoding="utf-8")
        self.assertIn('counts = {"admins": 0', src)
        self.assertIn("get_admins_simple()", src)


class FooterAndMobileTests(unittest.TestCase):
    def test_site_footer_matches_side_foot_padding(self):
        css = Path("app/web/static/panel.css").read_text(encoding="utf-8")
        self.assertIn(".site-footer {\n  margin-top: auto;\n  padding-top: var(--page-title-gap);", css)
        self.assertIn(
            "padding: var(--page-title-gap) var(--space-4) calc(var(--foot-gap) + var(--safe-bottom));",
            css,
        )

    def test_mobile_main_top_gap_increased(self):
        css = Path("app/web/static/panel.css").read_text(encoding="utf-8")
        mobile = css.split("@media (max-width: 900px)", 1)[1]
        self.assertIn(
            "padding: var(--page-title-gap) var(--space-2) var(--foot-gap);",
            mobile,
        )
        self.assertIn("padding-bottom: var(--safe-bottom);", mobile.split(".shell {", 1)[1])


class SidebarHoverTests(unittest.TestCase):
    def test_section_hovers_use_box_tints(self):
        css = Path("app/web/static/panel.css").read_text(encoding="utf-8")
        bot_hover = css.split(".nav-item-bot:hover {", 1)[1].split("}", 1)[0]
        pg_hover = css.split(".nav-item-pg:hover {", 1)[1].split("}", 1)[0]
        self.assertIn("var(--bot-line)", bot_hover)
        self.assertIn("var(--pg-line)", pg_hover)
        self.assertIn("color-mix(in srgb, var(--bot-line)", bot_hover)
        self.assertIn("color-mix(in srgb, var(--pg-line)", pg_hover)


class RamRingTests(unittest.TestCase):
    def test_percent_centered_in_ring(self):
        gauges = Path("app/web/templates/_host_resource_gauges.html").read_text(encoding="utf-8")
        css = Path("app/web/static/panel.css").read_text(encoding="utf-8")
        center = gauges.split('data-metric="mem"')[1].split("home-gauge-meta")[0]
        self.assertIn("data-host-mem-val", center)
        self.assertIn("home-gauge-center", center)
        self.assertNotIn("home-gauge-center-quiet", gauges)
        self.assertIn(".home-gauge-center strong", css)
        dash = Path("app/web/templates/dashboard.html").read_text(encoding="utf-8")
        self.assertIn("_host_resource_gauges.html", dash)
        self.assertIn("/dashboard/metrics", dash)
        home = Path("app/web/templates/_home_dash_body.html").read_text(encoding="utf-8")
        self.assertNotIn("home-gauge", home)


if __name__ == "__main__":
    unittest.main()
