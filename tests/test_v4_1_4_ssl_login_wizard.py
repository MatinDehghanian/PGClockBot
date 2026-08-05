"""v4.1.4 — SSL auto-enable, login flash, wizard HTTP redirect."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class SslAutoEnableTests(unittest.TestCase):
    def test_issue_or_renew_calls_enable_https(self):
        src = (ROOT / "app/services/ssl_certs.py").read_text(encoding="utf-8")
        block = src[src.find("def issue_or_renew") : src.find("def enable_https")]
        self.assertIn("enable_https(restart=True)", block)
        self.assertNotIn("needs_enable", block)

    def test_ssl_template_no_enable_confirm(self):
        html = (ROOT / "app/web/templates/_settings_ssl.html").read_text(encoding="utf-8")
        self.assertNotIn("panelConfirm", html)
        self.assertIn("data-confirm", html)
        self.assertIn("value=\"disable\"", html)
        self.assertNotIn("data-confirm-reason", html)


class LoginFlashTests(unittest.TestCase):
    def test_login_no_yellow_restart_flash(self):
        html = (ROOT / "app/web/templates/login.html").read_text(encoding="utf-8")
        self.assertNotIn("flash warn", html)
        self.assertIn("auth-restart-hint", html)
        self.assertIn("restarting') != '1'", html)


class WizardFinishUrlTests(unittest.TestCase):
    def test_setup_finish_uses_http_login_url(self):
        src = (ROOT / "app/api/app.py").read_text(encoding="utf-8")
        self.assertIn("setup_finish_login_url()", src)
        self.assertNotIn('RedirectResponse("/login?restarting=1"', src)

    def test_setup_finish_login_url_http_when_ssl_off(self):
        from app.services.setup_wizard import setup_finish_login_url

        with patch("app.services.ssl_certs.read_meta", return_value={"ssl_enabled": False}), patch(
            "app.services.ssl_certs.cert_files_exist", return_value=False
        ), patch("app.services.setup_wizard.detect_server_ip", return_value="203.0.113.10"), patch(
            "app.config.get_settings"
        ) as gs:
            gs.return_value.web_port = 9000
            url = setup_finish_login_url()
        self.assertEqual(url, "http://203.0.113.10:9000/login")

    def test_wizard_panel_url_is_http_ip(self):
        from app.services.setup_wizard import wizard_panel_url_hint

        with patch("app.services.setup_wizard.detect_server_ip", return_value="10.0.0.5"), patch(
            "app.config.get_settings"
        ) as gs:
            gs.return_value.web_port = 9000
            url = wizard_panel_url_hint("9000")
        self.assertEqual(url, "http://10.0.0.5:9000/")


if __name__ == "__main__":
    unittest.main()
