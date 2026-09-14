"""Phase 2 — evolutionary web panel IA (work modes, Persian chrome)."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "app/web/templates/base.html"
CSS = ROOT / "app/web/static/panel-nav-modes.css"
JS = ROOT / "app/web/static/panel.js"
PRINCIPALS = ROOT / "app/web/templates/principals.html"


class Phase2NavWorkModesTests(unittest.TestCase):
    def test_base_has_work_mode_switcher(self):
        html = BASE.read_text(encoding="utf-8")
        self.assertIn('data-nav-modes', html)
        self.assertIn('data-nav-mode-tab="system"', html)
        self.assertIn('data-nav-mode-tab="shop"', html)
        self.assertIn('data-nav-mode-tab="pg"', html)
        self.assertIn(">سیستم</button>", html)
        self.assertIn(">فروش</button>", html)
        self.assertIn(">پاسارگارد</button>", html)
        self.assertIn('data-nav-mode="system"', html)
        self.assertIn('data-nav-mode="shop"', html)
        self.assertIn('data-nav-mode="pg"', html)
        self.assertIn('data-nav-mode="help"', html)
        # Keep established section labels for IA continuity / existing tests
        self.assertIn("پنل ربات", html)
        self.assertIn("پنل پاسارگارد", html)
        self.assertIn("وب پنل", html)

    def test_sections_are_collapsible(self):
        html = BASE.read_text(encoding="utf-8")
        self.assertIn("nav-label-toggle", html)
        self.assertIn('data-nav-collapse="system"', html)
        self.assertIn('data-nav-collapse="shop"', html)
        self.assertIn('data-nav-collapse="pg"', html)
        self.assertIn('data-nav-collapse="help"', html)
        self.assertIn("nav-empty", html)

    def test_additive_css_and_js_wired(self):
        html = BASE.read_text(encoding="utf-8")
        self.assertIn("/static/panel-nav-modes.css?v={{ app_version }}", html)
        self.assertTrue(CSS.is_file())
        css = CSS.read_text(encoding="utf-8")
        self.assertIn(".nav-modes", css)
        self.assertIn("data-active-mode", css)
        self.assertIn(".nav-section.is-collapsed", css)
        js = JS.read_text(encoding="utf-8")
        self.assertIn("initNavWorkModes", js)
        self.assertIn("panel-nav-mode", js)
        self.assertIn("panel-nav-collapsed", js)

    def test_persian_pg_role_chrome(self):
        html = BASE.read_text(encoding="utf-8")
        self.assertNotIn("PG Role:", html)
        self.assertIn("نقش پاسارگارد:", html)
        principals = PRINCIPALS.read_text(encoding="utf-8")
        self.assertNotIn("PG Role:", principals)
        self.assertIn("نقش پاسارگارد:", principals)

    def test_owner_gates_remain(self):
        html = BASE.read_text(encoding="utf-8")
        self.assertIn("{% if is_owner %}", html)
        users_idx = html.find('href="/users"')
        self.assertGreater(users_idx, 0)
        window = html[max(0, users_idx - 120) : users_idx]
        self.assertIn("is_owner", window)


if __name__ == "__main__":
    unittest.main()
