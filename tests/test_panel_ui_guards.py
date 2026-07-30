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


if __name__ == "__main__":
    unittest.main()
