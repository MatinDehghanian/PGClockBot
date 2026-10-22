"""Settlement return pages use the branded panel status stage."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

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
            "primary_href": "https://t.me/shopbot",
            "primary_label": "بازگشت به ربات",
            "secondary_href": "",
            "secondary_label": "",
            "guide_heading": "",
            "guide_steps": [],
            "code_block": "",
            "guide_note": "",
            "body_html": "",
            "show_close_button": False,
            "close_button_label": "بستن",
            "footer": "برای ادامه به ربات برگردید.",
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

    def test_payment_page_uses_bot_return_link_not_close(self) -> None:
        html = self.render()
        self.assertNotIn("panel-status-kicker", html)
        self.assertNotIn("panel-status-close-btn", html)
        self.assertNotIn("Telegram.WebApp.close", html)
        self.assertIn("بازگشت به ربات", html)
        self.assertIn('href="https://t.me/shopbot"', html)
        self.assertIn("panel-status-actions--single", html)

    def test_ascii_kicker_keeps_ltr(self) -> None:
        html = self.render(
            kicker="HTTP 404",
            kicker_ltr=True,
            primary_href="",
            primary_label="",
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


class ShopBotChatUrlTests(unittest.IsolatedAsyncioTestCase):
    async def test_shop_username_wins_over_platform(self) -> None:
        from app.services.ux20 import shop_bot_chat_url

        profile = MagicMock(bot_username="ShopBot")
        result = MagicMock()
        result.scalar_one_or_none.return_value = profile
        session = AsyncMock()
        session.execute = AsyncMock(return_value=result)

        with patch("app.config.get_settings") as gs:
            gs.return_value = MagicMock(bot_username="platformbot")
            url = await shop_bot_chat_url(session, shop_owner_id=42)
        self.assertEqual(url, "https://t.me/ShopBot")

    async def test_platform_fallback_when_shop_has_no_username(self) -> None:
        from app.services.ux20 import shop_bot_chat_url

        result = MagicMock()
        result.scalar_one_or_none.return_value = MagicMock(bot_username=None)
        session = AsyncMock()
        session.execute = AsyncMock(return_value=result)

        with patch("app.config.get_settings") as gs:
            gs.return_value = MagicMock(bot_username="@MainBot")
            url = await shop_bot_chat_url(session, shop_owner_id=7)
        self.assertEqual(url, "https://t.me/MainBot")

    async def test_platform_shop_uses_settings_username(self) -> None:
        from app.services.ux20 import shop_bot_chat_url

        session = AsyncMock()
        with patch("app.config.get_settings") as gs:
            gs.return_value = MagicMock(bot_username="MainBot")
            url = await shop_bot_chat_url(session, shop_owner_id=None)
        self.assertEqual(url, "https://t.me/MainBot")
        session.execute.assert_not_called()

    async def test_missing_username_returns_none(self) -> None:
        from app.services.ux20 import shop_bot_chat_url

        session = AsyncMock()
        with patch("app.config.get_settings") as gs:
            gs.return_value = MagicMock(bot_username="")
            url = await shop_bot_chat_url(session, shop_owner_id=None)
        self.assertIsNone(url)


if __name__ == "__main__":
    unittest.main()
