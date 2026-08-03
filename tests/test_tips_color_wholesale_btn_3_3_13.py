"""3.3.13 — tip-box text color + wholesale button label in settings."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")


class FlashSeverityColorRestoredTests(unittest.TestCase):
    def test_flash_ok_err_warn_keep_severity_text_colors(self):
        self.assertIn(
            ".flash.ok { background: rgba(34, 197, 94, 0.1); color: #86efac;",
            CSS,
        )
        self.assertIn(
            ".flash.err { background: rgba(239, 68, 68, 0.1); color: #fca5a5;",
            CSS,
        )
        self.assertIn(
            ".flash.warn { background: rgba(234, 179, 8, 0.1); color: #fde047;",
            CSS,
        )
        light_ok = CSS.split('html[data-theme="light"] .flash.ok {')[1].split("}")[0]
        self.assertIn("color: #15803d", light_ok)


class TipBoxTextColorTests(unittest.TestCase):
    def test_update_steps_done_matches_title_foreground(self):
        block = CSS.split(".update-steps li.done {")[1].split("}")[0]
        self.assertIn("color: var(--foreground)", block)
        self.assertNotIn("ok-fg", block)

    def test_backup_and_pwa_use_update_steps_tips(self):
        backup = (ROOT / "app/web/templates/_settings_backup.html").read_text(encoding="utf-8")
        pwa = (ROOT / "app/web/templates/_settings_pwa.html").read_text(encoding="utf-8")
        self.assertIn("نکات مهم", backup)
        self.assertIn('class="update-steps"', backup)
        self.assertIn('class="update-steps"', pwa)


class WholesaleButtonSettingsTests(unittest.TestCase):
    def test_web_buttons_tab_includes_btn_wholesale(self):
        from app.services.users import SETTING_GROUPS

        keys = [f[0] for f in SETTING_GROUPS["متن دکمه‌های منو"]]
        self.assertIn("btn_wholesale", keys)

    def test_admin_and_reseller_bot_settings_include_btn_wholesale(self):
        from app.bot.handlers.admin_settings import SECTIONS as admin_sections
        from app.bot.handlers.reseller_settings import SECTIONS as res_sections

        def _btn_keys(sections):
            for _k, sec in sections.items():
                for sub in sec.get("subs") or []:
                    if sub[0] == "btn_labels":
                        return [f[0] for f in sub[2]]
            return []

        self.assertIn("btn_wholesale", _btn_keys(admin_sections))
        self.assertIn("btn_wholesale", _btn_keys(res_sections))


class VersionBumpTests(unittest.TestCase):
    def test_version_is_3_3_13(self):
        from app.version import __version__

        self.assertEqual(__version__, "3.3.13")
        self.assertEqual((ROOT / "VERSION").read_text(encoding="utf-8").strip(), "3.3.13")
        notes = (ROOT / "app/services/release_notes.py").read_text(encoding="utf-8")
        self.assertIn('"3.3.13"', notes)


if __name__ == "__main__":
    unittest.main()
