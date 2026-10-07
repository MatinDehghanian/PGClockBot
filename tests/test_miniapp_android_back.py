"""Mini App Android/system back — Telegram.WebApp.BackButton wiring.

Telegram only routes the Android hardware back key into a Mini App when
``BackButton`` is visible. Without ``show()`` + ``onClick``, OS back closes
the WebApp instead of navigating (a common report vs other bots that wire it).
"""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "app/web/static/miniapp.js").read_text(encoding="utf-8")


class MiniAppBackButtonTests(unittest.TestCase):
    def test_binds_telegram_back_button(self):
        self.assertIn("function bindTelegramBackButton(", JS)
        self.assertIn("function syncTelegramBackButton(", JS)
        self.assertIn("function onTelegramBack(", JS)
        self.assertIn("tg.BackButton.show()", JS)
        self.assertIn("tg.BackButton.hide()", JS)
        self.assertIn("tg.BackButton.onClick(", JS)
        self.assertIn("backButtonClicked", JS)
        self.assertIn("bindTelegramBackButton()", JS)

    def test_back_closes_overlays_then_returns_home(self):
        self.assertIn("function closeOpenOverlays(", JS)
        self.assertIn("function hasOpenOverlay(", JS)
        self.assertIn("function homeViewId(", JS)
        # Handler priority: overlay → home view
        on_back = JS.split("function onTelegramBack(")[1].split("function bindTelegramBackButton(")[0]
        self.assertLess(
            on_back.find("closeOpenOverlays()"),
            on_back.find("homeViewId()"),
        )
        self.assertIn("setView(homeViewId())", on_back)

    def test_set_view_and_overlays_sync_back_visibility(self):
        set_view = JS.split("function setView(")[1].split("function openPanelPath(")[0]
        self.assertIn("syncTelegramBackButton()", set_view)
        self.assertIn("closeOpenOverlays()", set_view)
        show_qr = JS.split("async function showQr(")[1].split("function showRenew(")[0]
        self.assertIn("syncTelegramBackButton()", show_qr)
        show_renew = JS.split("function showRenew(")[1].split("async function doBuy(")[0]
        self.assertIn("syncTelegramBackButton()", show_renew)

    def test_documents_chat_bot_limitation(self):
        # Regression guard: keep the rationale so future edits don't drop the API.
        self.assertIn("Chat bots cannot intercept hardware back", JS)
        self.assertIn("BackButton is visible", JS)


if __name__ == "__main__":
    unittest.main()
