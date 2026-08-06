"""4.4.1 — pill controls, no reason box, title actions, services redesign."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
BASE = (ROOT / "app/web/templates/base.html").read_text(encoding="utf-8")
USERS = (ROOT / "app/web/templates/users.html").read_text(encoding="utf-8")
RESELLERS = (ROOT / "app/web/templates/resellers.html").read_text(encoding="utf-8")
USER_BODY = (ROOT / "app/web/templates/_user_edit_body.html").read_text(encoding="utf-8")
SETTINGS = (ROOT / "app/web/templates/settings.html").read_text(encoding="utf-8")
SHOP = (ROOT / "app/web/templates/shop_settings.html").read_text(encoding="utf-8")
SECURITY = (ROOT / "app/web/templates/security.html").read_text(encoding="utf-8")
JS = (ROOT / "app/web/static/panel.js").read_text(encoding="utf-8")


class RadiusTokensTests(unittest.TestCase):
    def test_control_radius_pill(self):
        root = CSS.split(":root {", 1)[1].split("}", 1)[0]
        self.assertIn("--radius: 12px;", root)
        self.assertIn("--control-radius: 999px;", root)
        self.assertIn("--menu-item-radius: 8px;", root)

    def test_buttons_fields_tabs_use_control_radius(self):
        btn = CSS.split(".btn, a.btn, .btn-sm, a.btn-sm {", 1)[1].split("}", 1)[0]
        self.assertIn("border-radius: var(--control-radius);", btn)
        fields = CSS.split("input, select, textarea {", 1)[1].split("}", 1)[0]
        self.assertIn("border-radius: var(--control-radius);", fields)
        tabs = CSS.split(".section-tabs a {", 1)[1].split("}", 1)[0]
        self.assertIn("border-radius: var(--control-radius);", tabs)

    def test_cards_logo_hamburger_keep_box_radius(self):
        menu = CSS.split(".menu-toggle {", 1)[1].split("}", 1)[0]
        self.assertIn("border-radius: var(--radius);", menu)
        self.assertNotIn("control-radius", menu)
        logo = CSS.split(".brand-logo {", 1)[1].split("}", 1)[0]
        self.assertIn("border-radius: var(--radius);", logo)

    def test_dropdown_box_pill_items_keep_menu_item_radius(self):
        box = CSS.split(".ui-select-menu {", 1)[1].split("}", 1)[0]
        self.assertIn("border-radius: var(--control-radius);", box)
        item = CSS.split(".ui-select-menu button {", 1)[1].split("}", 1)[0]
        self.assertIn("border-radius: var(--menu-item-radius);", item)
        theme = CSS.split(".side-theme-menu {", 1)[1].split("}", 1)[0]
        self.assertIn("border-radius: var(--control-radius);", theme)
        theme_btn = CSS.split(".side-theme-menu button {", 1)[1].split("}", 1)[0]
        self.assertIn("border-radius: var(--menu-item-radius);", theme_btn)


class TitleActionsAlignTests(unittest.TestCase):
    def test_mobile_page_head_keeps_actions_inline(self):
        mobile = CSS.split("@media (max-width: 900px) {", 1)[1]
        # Title actions stay on the same row (not full-width under title)
        self.assertIn("Title actions stay on the same row", mobile)
        head_rules = mobile.split(".page-head:has(> .actions),", 1)[1].split(".pg-head {", 1)[0]
        self.assertIn("flex-wrap: nowrap;", head_rules)
        self.assertIn("width: auto;", head_rules)
        self.assertNotIn("flex: 1 1 100%;", head_rules)


class NoReasonBoxTests(unittest.TestCase):
    def test_reason_removed_everywhere_in_web(self):
        self.assertNotIn("confirm-reason", BASE)
        self.assertNotIn("data-confirm-reason", USERS)
        self.assertNotIn("data-confirm-reason", RESELLERS)
        self.assertNotIn("data-confirm-reason", USER_BODY)
        self.assertNotIn("data-confirm-reason", JS)
        self.assertNotIn("confirm-reason-wrap", JS)


class ServicesRedesignTests(unittest.TestCase):
    def test_user_edit_services_use_new_layout(self):
        self.assertIn("svc-list", USER_BODY)
        self.assertIn("svc-item", USER_BODY)
        self.assertIn("svc-stats", USER_BODY)
        self.assertIn("svc-op-row", USER_BODY)
        self.assertNotIn("svc-card-list", USER_BODY)
        self.assertIn(".svc-list {", CSS)
        self.assertIn(".svc-stat {", CSS)


class FlashSingleRenderTests(unittest.TestCase):
    def test_base_hides_page_flash_when_modal_reopens(self):
        self.assertIn("flash_ok and not open_edit", BASE)
        self.assertIn("flash_err and not open_edit", BASE)

    def test_users_no_duplicate_flash(self):
        self.assertNotIn('{% if flash_ok %}<div class="flash ok">{{ flash_ok }}</div>{% endif %}', USERS)

    def test_settings_shop_security_no_below_title_flash(self):
        self.assertNotIn("{% if saved %}", SETTINGS)
        self.assertNotIn("{% if saved %}", SHOP)
        self.assertNotIn("{% if ok %}", SECURITY)


class VersionBumpTests(unittest.TestCase):
    def test_version_at_least_4_4_1(self):
        from app.version import __version__

        self.assertGreaterEqual(
            tuple(int(x) for x in __version__.split(".")), (4, 4, 1)
        )
        self.assertEqual((ROOT / "VERSION").read_text(encoding="utf-8").strip(), "4.4.1")
        notes = (ROOT / "app/services/release_notes.py").read_text(encoding="utf-8")
        self.assertIn('"4.4.1"', notes)


if __name__ == "__main__":
    unittest.main()
