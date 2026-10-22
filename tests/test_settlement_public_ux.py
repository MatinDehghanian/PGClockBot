"""Settlement return pages use the branded panel status stage."""

from __future__ import annotations

import unittest
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parents[1]


class SettlementStatusTemplateTests(unittest.TestCase):
    def render(self, **kwargs) -> str:
        env = Environment(
            loader=FileSystemLoader(str(ROOT / "app" / "web" / "templates")),
            autoescape=select_autoescape(["html", "xml"]),
        )
        base = {
            "code": "ok",
            "title": "پرداخت تأیید شد",
            "message": "می‌توانید به تلگرام برگردید.",
            "watermark": "OK",
            "kicker": "",
            "kicker_ltr": False,
            "ref": None,
            "primary_href": "",
            "primary_label": "",
            "secondary_href": "",
            "secondary_label": "",
            "guide_heading": "",
            "guide_steps": [],
            "code_block": "",
            "guide_note": "",
            "body_html": "",
            "show_close_button": True,
            "close_button_label": "بستن",
            "footer": "این صفحه را ببندید و به تلگرام برگردید.",
            "app_version": "0.0.0",
            "pwa_name": "MrClockBot",
        }
        base.update(kwargs)
        return env.get_template("panel_status.html").render(**base)

    def test_success_tone_uses_ok_status(self) -> None:
        html = self.render()
        self.assertIn('data-status="ok"', html)
        self.assertIn("پرداخت تأیید شد", html)
        self.assertIn("می‌توانید به تلگرام برگردید", html)

    def test_payment_page_omits_persian_kicker_and_has_full_width_close(self) -> None:
        html = self.render()
        self.assertNotIn("panel-status-kicker", html)
        self.assertIn("panel-status-close-btn", html)
        self.assertIn("بستن", html)
        self.assertIn("panel-status-actions--single", html)

    def test_ascii_kicker_keeps_ltr(self) -> None:
        html = self.render(
            kicker="HTTP 404",
            kicker_ltr=True,
            show_close_button=False,
            code="404",
            title="یافت نشد",
        )
        self.assertIn('dir="ltr"', html)
        self.assertIn("HTTP 404", html)

    def test_warn_and_error_tones(self) -> None:
        warn = self.render(code="warn", title="در حال بررسی", watermark="WARN")
        err = self.render(code="error", title="ناموفق", watermark="ERR")
        self.assertIn('data-status="warn"', warn)
        self.assertIn('data-status="error"', err)


if __name__ == "__main__":
    unittest.main()
