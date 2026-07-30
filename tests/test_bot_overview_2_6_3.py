"""2.6.3 — bot overview is not web /home; RAM meta muted + right-aligned."""

from __future__ import annotations

import unittest
from pathlib import Path


class BotOverviewDashboardTests(unittest.TestCase):
    def test_admin_dashboard_does_not_redirect_to_home(self):
        src = Path("app/api/app.py").read_text(encoding="utf-8")
        start = src.find("async def dashboard(")
        self.assertGreater(start, 0)
        end = src.find("async def plans_page(", start)
        chunk = src[start:end] if end > start else src[start : start + 4000]
        self.assertIn("is_platform_admin(staff)", chunk)
        self.assertIn("bot_panel_summary", chunk)
        self.assertIn("dashboard.html", chunk)
        self.assertNotIn('RedirectResponse("/home"', chunk)
        self.assertNotIn('return RedirectResponse("/home"', chunk)

    def test_sidebar_bot_overview_links_dashboard(self):
        src = Path("app/web/templates/base.html").read_text(encoding="utf-8")
        bot = src[src.find("پنل ربات") : src.find("پنل پاسارگارد")]
        self.assertIn(">نمای کلی</span>", bot)
        self.assertIn('href="/dashboard"', bot)
        # Web panel home stays separate for admin
        self.assertIn('href="/home"', src)
        self.assertIn(">داشبورد</span>", src)


class RamMetaStyleTests(unittest.TestCase):
    def test_ram_hint_matches_cpu_cores_muted(self):
        home = Path("app/web/templates/home.html").read_text(encoding="utf-8")
        cpu = home.split('data-metric="cpu"')[1].split("data-metric=")[0]
        mem = home.split('data-metric="mem"')[1].split("</article>")[0]
        self.assertIn('class="muted"', cpu)
        self.assertIn('class="muted" id="home-mem-hint"', mem)
        self.assertNotIn("home-gauge-amount", mem)
        self.assertNotIn("<strong", mem.split("home-gauge-meta")[1])

    def test_ram_ltr_forced_right_on_desktop(self):
        css = Path("app/web/static/panel.css").read_text(encoding="utf-8")
        self.assertIn('.home-gauge-meta [dir="ltr"]', css)
        block = css.split('.home-gauge-meta [dir="ltr"]')[1].split("}")[0]
        self.assertIn("text-align: right", block)
        self.assertIn("width: 100%", block)


if __name__ == "__main__":
    unittest.main()
