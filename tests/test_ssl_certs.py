"""SSL helpers regression tests."""

from __future__ import annotations

import unittest
from pathlib import Path


class SslDomainTests(unittest.TestCase):
    def test_normalize_and_validate(self):
        from app.services.ssl_certs import is_valid_domain, normalize_domain

        self.assertEqual(normalize_domain("https://Bot.Example.com/x"), "bot.example.com")
        self.assertTrue(is_valid_domain("bot.example.com"))
        self.assertFalse(is_valid_domain("localhost"))
        self.assertFalse(is_valid_domain(""))


class SslUiWiredTests(unittest.TestCase):
    def test_settings_tab_and_template(self):
        from app.services.users import SETTINGS_TABS, TAB_SETTING_GROUPS

        self.assertIn(("ssl", "SSL"), SETTINGS_TABS)
        self.assertEqual(TAB_SETTING_GROUPS.get("ssl"), [])
        self.assertTrue(Path("app/web/templates/_settings_ssl.html").is_file())
        self.assertTrue(Path("app/services/ssl_certs.py").is_file())
        src = Path("app/api/app.py").read_text(encoding="utf-8")
        self.assertIn("/settings/ssl/progress", src)
        self.assertIn("start_issue_job", src)
        main = Path("app/main.py").read_text(encoding="utf-8")
        self.assertIn("uvicorn_ssl_kwargs", main)


if __name__ == "__main__":
    unittest.main()
