"""4.4.4 — search row on mobile, modal title size, service pills."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
BASE = (ROOT / "app/web/templates/base.html").read_text(encoding="utf-8")
USERS = (ROOT / "app/web/templates/users.html").read_text(encoding="utf-8")
RESELLERS = (ROOT / "app/web/templates/resellers.html").read_text(encoding="utf-8")
USER_BODY = (ROOT / "app/web/templates/_user_edit_body.html").read_text(encoding="utf-8")
RESELLER_BODY = (ROOT / "app/web/templates/_reseller_edit_body.html").read_text(
    encoding="utf-8"
)
SETTINGS = (ROOT / "app/web/templates/settings.html").read_text(encoding="utf-8")
SHOP = (ROOT / "app/web/templates/shop_settings.html").read_text(encoding="utf-8")
SECURITY = (ROOT / "app/web/templates/security.html").read_text(encoding="utf-8")
JS = (ROOT / "app/web/static/panel.js").read_text(encoding="utf-8")
API = (ROOT / "app/api/app.py").read_text(encoding="utf-8")
RESELLER_API = (ROOT / "app/api/reseller_pages.py").read_text(encoding="utf-8")


class RadiusTokensTests(unittest.TestCase):
    def test_control_radius_pill_menus_moderate(self):
        root = CSS.split(":root {", 1)[1].split("}", 1)[0]
        self.assertIn("--radius: 12px;", root)
        self.assertIn("--control-radius: 999px;", root)
        self.assertIn("--menu-radius: 10px;", root)
        self.assertIn("--menu-item-radius: 7px;", root)

    def test_buttons_fields_tabs_use_control_radius(self):
        btn = CSS.split(".btn, a.btn, .btn-sm, a.btn-sm {", 1)[1].split("}", 1)[0]
        self.assertIn("border-radius: var(--control-radius);", btn)
        fields = CSS.split("input, select, textarea {", 1)[1].split("}", 1)[0]
        self.assertIn("border-radius: var(--control-radius);", fields)
        tabs = CSS.split(".section-tabs a {", 1)[1].split("}", 1)[0]
        self.assertIn("border-radius: var(--control-radius);", tabs)
        shortcuts = CSS.split(".quick-links a {", 1)[1].split("}", 1)[0]
        self.assertIn("border-radius: var(--control-radius);", shortcuts)

    def test_multiline_editors_use_box_radius_not_pill(self):
        # Global override after the shared input/select/textarea rule
        block = CSS.split(
            "/* Wide / multi-line editors — same corner language as cards, never full pill */",
            1,
        )[1].split("textarea {", 1)[0]
        self.assertIn("border-radius: var(--radius);", block)
        self.assertIn("textarea,", block)
        self.assertIn("select[multiple],", block)
        self.assertNotIn("control-radius", block)
        ta = CSS.split(
            "/* Wide / multi-line editors — same corner language as cards, never full pill */",
            1,
        )[1]
        # textarea sizing block still present and inherits radius from override above
        self.assertIn("min-height: 96px;", ta)

    def test_cards_logo_hamburger_keep_box_radius(self):
        menu = CSS.split(".menu-toggle {", 1)[1].split("}", 1)[0]
        self.assertIn("border-radius: var(--radius);", menu)
        self.assertNotIn("control-radius", menu)
        logo = CSS.split(".brand-logo {", 1)[1].split("}", 1)[0]
        self.assertIn("border-radius: var(--radius);", logo)

    def test_dropdown_panels_use_menu_radius_not_pill(self):
        box = CSS.split(".ui-select-menu {", 1)[1].split("}", 1)[0]
        self.assertIn("border-radius: var(--menu-radius);", box)
        self.assertNotIn("control-radius", box)
        item = CSS.split(".ui-select-menu button {", 1)[1].split("}", 1)[0]
        self.assertIn("border-radius: var(--menu-item-radius);", item)
        theme = CSS.split(".side-theme-menu {", 1)[1].split("}", 1)[0]
        self.assertIn("border-radius: var(--menu-radius);", theme)
        self.assertNotIn("control-radius", theme)
        theme_btn = CSS.split(".side-theme-menu button {", 1)[1].split("}", 1)[0]
        self.assertIn("border-radius: var(--menu-item-radius);", theme_btn)
        ported = CSS.split(".row-actions-menu.is-ported {", 1)[1].split("}", 1)[0]
        self.assertIn("border-radius: var(--menu-radius);", ported)
        self.assertNotIn("control-radius", ported)


class TitleActionsAlignTests(unittest.TestCase):
    def test_mobile_page_head_keeps_actions_inline(self):
        mobile = CSS.split("@media (max-width: 900px) {", 1)[1]
        self.assertIn("Title actions stay on the same row", mobile)
        head_rules = mobile.split(".page-head:has(> .actions),", 1)[1].split(
            ".pg-head {", 1
        )[0]
        self.assertIn("flex-wrap: nowrap;", head_rules)
        self.assertIn("width: auto;", head_rules)
        self.assertNotIn("flex: 1 1 100%;", head_rules)

    def test_mobile_search_keeps_button_beside_field(self):
        mobile = CSS.split("@media (max-width: 900px) {", 1)[1]
        block = mobile.split(".search-bar {", 1)[1].split(".user-edit-inline-row {", 1)[0]
        self.assertIn("flex-direction: row;", block)
        self.assertNotIn("flex-direction: column;", block)
        self.assertIn("width: auto;", block)

    def test_modal_head_title_matches_page_title(self):
        head = CSS.split(
            "/* Modal chrome title matches page titles (not the tiny section --title-size) */",
            1,
        )[1].split(".ui-modal-panel p,", 1)[0]
        self.assertIn("font-size: 22px;", head)
        self.assertNotIn("var(--title-size)", head)
        page = CSS.split(".page-title h1 {", 1)[1].split("}", 1)[0]
        self.assertIn("font-size: 22px;", page)


class DeleteReasonBoxTests(unittest.TestCase):
    def test_confirm_reason_ui_present(self):
        self.assertIn('id="confirm-reason-wrap"', BASE)
        self.assertIn('id="confirm-reason"', BASE)
        self.assertIn("confirm-reason-wrap", JS)
        self.assertIn("data-confirm-reason", JS)

    def test_delete_forms_require_reason(self):
        self.assertIn("data-confirm-reason", USERS)
        self.assertIn("/users/{{ u.id }}/delete", USERS)
        self.assertIn("data-confirm-reason", RESELLERS)
        self.assertIn("/resellers/{{ u.id }}/delete", RESELLERS)
        self.assertIn("data-confirm-reason", RESELLER_BODY)
        # Role / block forms must not force reason box
        self.assertNotIn("data-confirm-reason", USER_BODY)
        block = USERS.split("/users/{{ u.id }}/block", 1)[1].split("</form>", 1)[0]
        self.assertNotIn("data-confirm-reason", block)

    def test_backend_enforces_delete_reason_min_length(self):
        self.assertIn("علت حذف کاربر الزامی است (حداقل ۳ کاراکتر)", API)
        self.assertIn("علت حذف نمایندگی الزامی است (حداقل ۳ کاراکتر)", RESELLER_API)
        self.assertIn("علت حذف کاربر الزامی است", RESELLER_API)


class ServicesRedesignTests(unittest.TestCase):
    def test_user_edit_services_wallet_style_pills(self):
        self.assertIn("svc-list", USER_BODY)
        self.assertIn("svc-item", USER_BODY)
        self.assertIn("svc-stat-row", USER_BODY)
        self.assertIn("svc-stat-pill", USER_BODY)
        self.assertIn("حجم / مانده", USER_BODY)
        self.assertIn("مانده زمان", USER_BODY)
        self.assertIn("user-edit-inline-row", USER_BODY)
        self.assertNotIn("svc-card-list", USER_BODY)
        self.assertNotIn("svc-item-meta", USER_BODY)
        self.assertNotIn("expire_text", USER_BODY)
        # Increase button uses primary (no ghost)
        extend = USER_BODY.split("/extend", 1)[1].split("</form>", 1)[0]
        self.assertIn("افزایش مانده", extend)
        self.assertNotIn("btn-ghost", extend)
        self.assertIn(".svc-stat-row {", CSS)
        self.assertIn("gap: var(--space-2);", CSS.split(".svc-item-ops .form-stack {", 1)[1].split("}", 1)[0])

    def test_panel_status_plain_no_emoji_dot(self):
        from app.services.formatting import status_label, status_label_plain

        self.assertIn("🟢", status_label("active"))
        self.assertEqual(status_label_plain("active"), "فعال")
        self.assertNotIn("🟢", status_label_plain("active"))
        admin = (ROOT / "app/services/bot_user_admin.py").read_text(encoding="utf-8")
        self.assertIn("status_label_plain", admin)
        self.assertIn("status_fa=status_label_plain(", admin)


class ResellersPlanColumnTests(unittest.TestCase):
    def test_plan_type_and_status_columns(self):
        self.assertIn("<th>نوع پلن</th>", RESELLERS)
        self.assertIn("<th>وضعیت</th>", RESELLERS)
        self.assertIn("badge info", RESELLERS)
        self.assertIn("PAYG", RESELLERS)
        self.assertIn("badge fixed", RESELLERS)
        # Name cell should not stack plan/status badges anymore
        name_cell = RESELLERS.split("{% for u, p in rows %}", 1)[1].split(
            "<td class=\"mono col-hide-sm\">{{ u.telegram_id }}</td>", 1
        )[0]
        self.assertNotIn("badge info", name_cell)
        self.assertNotIn("badge approved", name_cell)


class FlashSingleRenderTests(unittest.TestCase):
    def test_base_hides_page_flash_when_modal_reopens(self):
        self.assertIn("flash_ok and not open_edit", BASE)
        self.assertIn("flash_err and not open_edit", BASE)

    def test_users_no_duplicate_flash(self):
        self.assertNotIn(
            '{% if flash_ok %}<div class="flash ok">{{ flash_ok }}</div>{% endif %}',
            USERS,
        )

    def test_settings_shop_security_no_below_title_flash(self):
        self.assertNotIn("{% if saved %}", SETTINGS)
        self.assertNotIn("{% if saved %}", SHOP)
        self.assertNotIn("{% if ok %}", SECURITY)


class VersionBumpTests(unittest.TestCase):
    def test_version_at_least_4_4_4(self):
        from app.version import __version__

        self.assertGreaterEqual(
            tuple(int(x) for x in __version__.split(".")), (4, 4, 4)
        )
        self.assertEqual(
            (ROOT / "VERSION").read_text(encoding="utf-8").strip(), "4.4.4"
        )
        notes = (ROOT / "app/services/release_notes.py").read_text(encoding="utf-8")
        self.assertIn('"4.4.4"', notes)


if __name__ == "__main__":
    unittest.main()
