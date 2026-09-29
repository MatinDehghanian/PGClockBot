"""SSL helpers regression tests."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class SslDomainTests(unittest.TestCase):
    def test_normalize_and_validate(self):
        from app.services.ssl_certs import is_valid_domain, is_valid_ipv4, is_valid_tls_host, normalize_domain

        self.assertEqual(normalize_domain("https://Bot.Example.com/x"), "bot.example.com")
        self.assertTrue(is_valid_domain("bot.example.com"))
        self.assertFalse(is_valid_domain("localhost"))
        self.assertFalse(is_valid_domain(""))
        self.assertFalse(is_valid_domain("1.2.3.4"))
        self.assertTrue(is_valid_ipv4("1.2.3.4"))
        self.assertFalse(is_valid_ipv4("999.1.1.1"))
        self.assertTrue(is_valid_tls_host("bot.example.com"))
        self.assertTrue(is_valid_tls_host("203.0.113.10"))


class SslSelfSignedIpTests(unittest.TestCase):
    def test_issue_self_signed_ip_writes_cert_and_meta(self):
        from app.services import ssl_certs

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cert_dir = root / "certs"
            with patch.object(ssl_certs, "CERT_DIR", cert_dir), patch.object(
                ssl_certs, "META_PATH", cert_dir / "meta.json"
            ), patch.object(ssl_certs, "PROGRESS_PATH", cert_dir / "progress.json"), patch.object(
                ssl_certs, "LIVE_CERT", cert_dir / "fullchain.pem"
            ), patch.object(ssl_certs, "LIVE_KEY", cert_dir / "privkey.pem"), patch.object(
                ssl_certs, "WEBROOT_DIR", root / "acme-www"
            ), patch(
                "app.services.setup_wizard.update_env_keys", return_value=Path(tmp) / ".env"
            ), patch(
                "app.services.ssl_certs.get_settings"
            ) as gs:
                class _S:
                    web_port = 9443

                gs.return_value = _S()
                gs.cache_clear = lambda: None

                result = ssl_certs.issue_self_signed_ip("203.0.113.50", enable=True, restart=False)
                self.assertTrue(result.get("ok"), result)
                self.assertTrue(ssl_certs.cert_files_exist())
                meta = json.loads((cert_dir / "meta.json").read_text(encoding="utf-8"))
                self.assertTrue(meta.get("ssl_enabled"))
                self.assertTrue(meta.get("self_signed"))
                self.assertEqual(meta.get("mode"), "self_signed_ip")
                self.assertEqual(meta.get("domain"), "203.0.113.50")
                self.assertIn("https://203.0.113.50:9443", result.get("public_https") or "")


class SslConfigureInstallTests(unittest.TestCase):
    def test_configure_none(self):
        from app.services import ssl_certs

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cert_dir = root / "certs"
            with patch.object(ssl_certs, "CERT_DIR", cert_dir), patch.object(
                ssl_certs, "META_PATH", cert_dir / "meta.json"
            ), patch.object(ssl_certs, "PROGRESS_PATH", cert_dir / "progress.json"), patch.object(
                ssl_certs, "LIVE_CERT", cert_dir / "fullchain.pem"
            ), patch.object(ssl_certs, "LIVE_KEY", cert_dir / "privkey.pem"), patch.object(
                ssl_certs, "WEBROOT_DIR", root / "acme-www"
            ):
                result = ssl_certs.configure_for_install(mode="none")
                self.assertTrue(result.get("ok"))
                self.assertEqual(result.get("mode"), "none")
                meta = json.loads((cert_dir / "meta.json").read_text(encoding="utf-8"))
                self.assertFalse(meta.get("ssl_enabled"))


class SslUiWiredTests(unittest.TestCase):
    def test_settings_tab_and_template(self):
        from app.services.users import PANEL_SETTINGS_TABS, SETTINGS_TABS, TAB_SETTING_GROUPS

        self.assertNotIn(("ssl", "SSL"), SETTINGS_TABS)
        self.assertIn(("ssl", "SSL"), PANEL_SETTINGS_TABS)
        self.assertEqual(TAB_SETTING_GROUPS.get("ssl"), [])
        self.assertTrue(Path("app/web/templates/_settings_ssl.html").is_file())
        self.assertTrue(Path("app/services/ssl_certs.py").is_file())
        src = Path("app/api/app.py").read_text(encoding="utf-8")
        self.assertIn("/settings/ssl/progress", src)
        self.assertIn("PANEL_SETTINGS", src)
        self.assertIn("start_issue_job", src)
        self.assertIn("enable_https", src)
        main = Path("app/main.py").read_text(encoding="utf-8")
        self.assertIn("uvicorn_ssl_kwargs", main)
        ssl_src = Path("app/services/ssl_certs.py").read_text(encoding="utf-8")
        self.assertIn("enable_https", ssl_src)
        self.assertIn("auto_enabled", ssl_src)
        self.assertIn("_start_acme_http", ssl_src)
        self.assertIn("issue_self_signed_ip", ssl_src)
        self.assertIn("configure_for_install", ssl_src)
        self.assertIn("secp256r1", ssl_src)

    def test_install_script_prompts_port_and_ssl(self):
        src = Path("pgclock.sh").read_text(encoding="utf-8")
        self.assertIn("prompt_install_port_and_ssl", src)
        self.assertIn("apply_install_ssl", src)
        self.assertIn("PGCLOCK_SSL_MODE", src)
        self.assertIn("PGCLOCK_WEB_PORT", src)
        self.assertIn("Temporary self-signed", src)
        self.assertIn("configure_for_install", src)
        self.assertIn("probe_panel_health", src)
        self.assertIn("verify_tls_material", src)
        # Setup URL must still print when /health fails (v11.0.8 regression).
        self.assertIn("Setup URL (one-time, 15 min) — open after", src)
        self.assertIn("ALWAYS print Setup URL", src)
        ctl = Path("scripts/pgclockbot-ctl").read_text(encoding="utf-8")
        self.assertIn("--key-type ecdsa", ctl)
        main = Path("app/main.py").read_text(encoding="utf-8")
        self.assertIn("TLS cert not loadable", main)
        self.assertIn("verify_tls_material", main)


class UpdateCopyTests(unittest.TestCase):
    def test_update_template_has_progress_ui(self):
        src = Path("app/web/templates/_settings_update.html").read_text(encoding="utf-8")
        self.assertIn("upd-start", src)
        self.assertIn("rollback-version", src)
        self.assertIn("progress-wrap", src)
        self.assertNotIn("update-details", src)
        self.assertNotIn("get.sh", src)


if __name__ == "__main__":
    unittest.main()
