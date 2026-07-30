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
    def test_btn_danger_is_solid_red(self):
        css = CSS.read_text(encoding="utf-8")
        block = re.search(r"(?ms)^\.btn-danger\s*\{([^}]+)\}", css)
        self.assertIsNotNone(block)
        self.assertIn("background: rgba(220, 38, 38, 0.92)", block.group(1))

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
