"""Guardrails against UI regressions that keep coming back."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "app/web/static/panel.css"
JS = ROOT / "app/web/static/panel.js"
LOGIN = ROOT / "app/web/templates/login.html"
SECURITY = ROOT / "app/web/templates/security.html"


class NoZoomCssGuardTests(unittest.TestCase):
    def test_control_font_size_token_is_16px(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertRegex(css, r"--control-fs:\s*16px")

    def test_inputs_do_not_use_title_size(self):
        css = CSS.read_text(encoding="utf-8")
        # The global form-control block must not shrink below 16px via --title-size.
        bad = re.findall(
            r"(?ms)^(input(?:,\s*select,\s*textarea)?\s*\{[^}]*font-size:\s*var\(--title-size\))",
            css,
        )
        self.assertEqual(bad, [], msg="input/select/textarea must not use --title-size (causes iOS zoom)")

    def test_control_fs_enforced_with_important(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn("font-size: var(--control-fs) !important", css)

    def test_js_has_no_zoom_enforcer(self):
        js = JS.read_text(encoding="utf-8")
        self.assertIn("Permanent no-zoom", js)
        self.assertIn("fontSize", js)


class LoginUsernameGuardTests(unittest.TestCase):
    def test_login_username_not_hardcoded_admin(self):
        src = LOGIN.read_text(encoding="utf-8")
        self.assertNotRegex(src, r'name="username"[^>]*value="admin"')
        self.assertNotRegex(src, r"value=\{\{\s*username\s+or\s+['\"]admin['\"]")
        self.assertIn('value="{{ username or \'\' }}"', src)

    def test_security_username_fields_not_prefilled(self):
        src = SECURITY.read_text(encoding="utf-8")
        self.assertIn('name="old_username"', src)
        self.assertIn('name="new_username"', src)
        self.assertNotIn('value="{{ current_username }}"', src)
        self.assertNotIn('placeholder="{{ current_username }}"', src)


class PwToggleCssTests(unittest.TestCase):
    def test_pw_toggle_uses_margin_auto_centering(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn(".pw-field input", css)
        self.assertIn("margin-top: 0", css)
        block = re.search(r"(?ms)\.pw-toggle\s*\{([^}]+)\}", css)
        self.assertIsNotNone(block)
        body = block.group(1)
        self.assertIn("margin-block: auto", body)
        self.assertIn("top: 0", body)
        self.assertIn("bottom: 0", body)


class FieldHintAndPlaceholderTests(unittest.TestCase):
    def test_placeholder_is_rtl_right_aligned(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn("input::placeholder", css)
        block = re.search(r"(?ms)input::placeholder,\s*textarea::placeholder\s*\{([^}]+)\}", css)
        self.assertIsNotNone(block)
        body = block.group(1)
        self.assertIn("text-align: right", body)
        self.assertIn("direction: rtl", body)

    def test_field_help_ordered_below_control(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn("order: 10", css)
        self.assertIn(".form-field > small.muted", css)

    def test_settings_field_help_after_control(self):
        src = (ROOT / "app/web/templates/_settings_field.html").read_text(encoding="utf-8")
        # help must appear after the control close for text fields
        self.assertIn("</select>\n    {% if help %}<small class=\"muted\">{{ help }}</small>{% endif %}", src)
        self.assertRegex(src, r"<input name=\"s_\{\{ key \}\}\" value=\"\{\{ val \}\}\" />\s*\{% if help %\}")


class DeleteButtonAndKebabTests(unittest.TestCase):
    def test_btn_danger_matches_soft_tint_style(self):
        css = CSS.read_text(encoding="utf-8")
        block = re.search(r"(?ms)^\.btn-danger\s*\{([^}]+)\}", css)
        self.assertIsNotNone(block)
        body = block.group(1)
        self.assertIn("background: rgba(239, 68, 68, 0.12)", body)
        self.assertIn("color: var(--destructive-fg)", body)
        self.assertNotIn("0.92", body)

    def test_btn_ok_matches_soft_tint_style(self):
        css = CSS.read_text(encoding="utf-8")
        block = re.search(r"(?ms)^\.btn-ok\s*\{([^}]+)\}", css)
        self.assertIsNotNone(block)
        body = block.group(1)
        self.assertIn("background: rgba(34, 197, 94, 0.12)", body)
        self.assertIn("color: var(--ok-fg)", body)

    def test_btn_warn_matches_soft_tint_style(self):
        css = CSS.read_text(encoding="utf-8")
        block = re.search(r"(?ms)^\.btn-warn\s*\{([^}]+)\}", css)
        self.assertIsNotNone(block)
        body = block.group(1)
        self.assertIn("background: rgba(234, 179, 8, 0.12)", body)
        self.assertIn("color: var(--warn-fg)", body)

    def test_modal_above_chrome(self):
        css = CSS.read_text(encoding="utf-8")
        block = re.search(r"(?ms)^\.ui-modal\s*\{([^}]+)\}", css)
        self.assertIsNotNone(block)
        self.assertIn("z-index: 4000", block.group(1))
        js = JS.read_text(encoding="utf-8")
        self.assertIn("document.body.appendChild(el)", js)
        self.assertIn("modalHomes", js)

    def test_select_has_up_down_chevron_opposite_title(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn("M4.5 6L8 3l3.5 3", css)
        self.assertIn("M4.5 10L8 13l3.5-3", css)
        self.assertIn("background-position: left 12px center", css)
        self.assertIn("background-color: #09090b", css)
        # light theme must not wipe the chevron via background shorthand
        self.assertRegex(css, r"html\[data-theme=\"light\"\]\s+select\s*\{[^}]*background-image:")

    def test_kebab_covers_tablet_and_overflow(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn("@media (max-width: 1100px)", css)
        self.assertIn(".table-wrap.force-kebab .row-actions-toggle", css)
        self.assertIn(".row-actions-menu.is-ported", css)
        js = JS.read_text(encoding="utf-8")
        self.assertIn("refreshForceKebab", js)
        self.assertIn("force-kebab", js)
        self.assertIn("is-ported", js)
        self.assertIn("rowMenuHomes", js)

    def test_footer_is_compact(self):
        css = CSS.read_text(encoding="utf-8")
        foot = re.search(r"(?ms)^\.site-footer\s*\{([^}]+)\}", css)
        self.assertIsNotNone(foot)
        body = foot.group(1)
        self.assertIn("margin-top: 16px", body)
        self.assertIn("padding-top: 10px", body)
        star = re.search(r"(?ms)^a\.btn\.btn-star\s*,\s*\.btn-star\s*\{|^\.btn-star,\s*\na\.btn\.btn-star\s*\{|^\.btn-star,\s*a\.btn\.btn-star\s*\{([^}]+)\}", css)
        # star button should be shorter than primary --btn-h
        self.assertIn("min-height: 28px", css)

    def test_block_button_is_warn_update_is_ok(self):
        users = (ROOT / "app/web/templates/users.html").read_text(encoding="utf-8")
        self.assertIn("btn-warn", users)
        home = (ROOT / "app/web/templates/home.html").read_text(encoding="utf-8")
        self.assertRegex(home, r'btn-ok[^>]*>\s*آپدیت\s*<')
        upd = (ROOT / "app/web/templates/_settings_update.html").read_text(encoding="utf-8")
        self.assertIn('id="upd-start"', upd)
        self.assertIn("btn-ok", upd)

    def test_pg_admins_uses_row_actions_macro(self):
        src = (ROOT / "app/web/templates/pg_admins.html").read_text(encoding="utf-8")
        self.assertIn("row_actions", src)
        self.assertIn("{% call row_actions() %}", src)
        self.assertIn("btn-danger", src)
        self.assertIn("row-actions-toggle", (ROOT / "app/web/templates/macros.html").read_text(encoding="utf-8"))

    def test_pg_templates_uses_kebab(self):
        src = (ROOT / "app/web/templates/pg_templates.html").read_text(encoding="utf-8")
        self.assertIn("{% call row_actions() %}", src)
        self.assertIn("btn-danger", src)

    def test_common_delete_buttons_are_danger(self):
        for rel in (
            "app/web/templates/pg_users.html",
            "app/web/templates/plans.html",
            "app/web/templates/_settings_backup.html",
        ):
            src = (ROOT / rel).read_text(encoding="utf-8")
            self.assertIn("btn-danger", src)
            self.assertNotRegex(src, r'btn-ghost[^>]*>\s*حذف\s*<')


if __name__ == "__main__":
    unittest.main()
