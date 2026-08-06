"""4.3.11 — mobile floating header, button chrome, flash/modal polish."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
BASE = (ROOT / "app/web/templates/base.html").read_text(encoding="utf-8")
USERS = (ROOT / "app/web/templates/users.html").read_text(encoding="utf-8")
RESELLERS = (ROOT / "app/web/templates/resellers.html").read_text(encoding="utf-8")
SETTINGS = (ROOT / "app/web/templates/settings.html").read_text(encoding="utf-8")
SHOP = (ROOT / "app/web/templates/shop_settings.html").read_text(encoding="utf-8")
SECURITY = (ROOT / "app/web/templates/security.html").read_text(encoding="utf-8")


class RadiusAndTableHeadTests(unittest.TestCase):
    def test_radius_increased(self):
        root = CSS.split(":root {", 1)[1].split("}", 1)[0]
        self.assertIn("--radius: 12px;", root)
        self.assertIn("--r-sm: 8px;", root)
        self.assertIn("--table-head-bg:", root)

    def test_th_uses_mild_table_head_token(self):
        th = CSS.split("th {\n", 1)[1].split("}", 1)[0]
        self.assertIn("background: var(--table-head-bg);", th)
        self.assertNotIn("background: var(--muted);", th)


class StickyActionsChromeTests(unittest.TestCase):
    def test_sticky_actions_has_no_box(self):
        block = CSS.split(".sticky-actions {", 1)[1].split("}", 1)[0]
        self.assertIn("position: static", block)
        self.assertIn("background: transparent", block)
        self.assertIn("border: none", block)
        self.assertNotIn("border: 1px solid var(--border)", block)


class MobileTopbarTests(unittest.TestCase):
    def test_topbar_is_fixed(self):
        block = CSS.split("/* Topbar + hamburger", 1)[1].split(".topbar-brand {", 1)[0]
        self.assertIn("position: fixed;", block)
        self.assertNotIn("position: sticky;", block)

    def test_shell_pads_for_fixed_topbar(self):
        mobile = CSS.split("@media (max-width: 900px) {", 1)[1]
        self.assertIn("padding-top: calc(var(--topbar-h) + var(--safe-top));", mobile)


class MobileFullWidthActionsTests(unittest.TestCase):
    def test_page_head_stacks_actions_on_mobile(self):
        mobile = CSS.split("@media (max-width: 900px) {", 1)[1]
        self.assertIn(".page-head:has(> .actions),", mobile)
        self.assertIn("flex-wrap: wrap;", mobile)
        self.assertIn(".page-head > .actions,", mobile)
        self.assertIn("width: 100%;", mobile)
        self.assertIn(".search-bar {", mobile)
        self.assertIn("flex-direction: column;", mobile)
        self.assertIn(".user-edit-inline-row {", mobile)


class FlashSingleRenderTests(unittest.TestCase):
    def test_base_hides_page_flash_when_modal_reopens(self):
        self.assertIn("flash_ok and not open_edit", BASE)
        self.assertIn("flash_err and not open_edit", BASE)

    def test_users_no_duplicate_flash(self):
        self.assertNotIn('{% if flash_ok %}<div class="flash ok">{{ flash_ok }}</div>{% endif %}', USERS)
        self.assertIn("encodeURIComponent(flashOk)", USERS)

    def test_resellers_forwards_flash_into_modal(self):
        self.assertIn("encodeURIComponent(flashOk)", RESELLERS)
        self.assertIn("encodeURIComponent(flashErr)", RESELLERS)

    def test_settings_shop_security_no_below_title_flash(self):
        self.assertNotIn("{% if saved %}", SETTINGS)
        self.assertNotIn("request.query_params.get('ok')", SETTINGS)
        self.assertNotIn("{% if saved %}", SHOP)
        self.assertNotIn("{% if ok %}", SECURITY)
        self.assertNotIn("{% if err %}", SECURITY)


class ConfirmReasonDeleteOnlyTests(unittest.TestCase):
    def test_block_has_no_reason_delete_has_reason(self):
        block = USERS.split('action="/users/{{ u.id }}/block"', 1)[1].split("</form>", 1)[0]
        delete = USERS.split('action="/users/{{ u.id }}/delete"', 1)[1].split("</form>", 1)[0]
        self.assertNotIn("data-confirm-reason", block)
        self.assertIn('data-confirm-reason="1"', delete)


class VersionBumpTests(unittest.TestCase):
    def test_version_at_least_4_3_11(self):
        from app.version import __version__

        self.assertGreaterEqual(
            tuple(int(x) for x in __version__.split(".")), (4, 3, 11)
        )
        notes = (ROOT / "app/services/release_notes.py").read_text(encoding="utf-8")
        self.assertIn('"4.3.11"', notes)


if __name__ == "__main__":
    unittest.main()
