"""Role-based Mini App — auth, persona, and UI wiring."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import unittest
import unittest.mock
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]


def _sign_init_data(bot_token: str, user: dict, *, auth_date: int | None = None) -> str:
    auth_date = int(auth_date if auth_date is not None else time.time())
    fields = {
        "auth_date": str(auth_date),
        "user": json.dumps(user, separators=(",", ":"), ensure_ascii=False),
    }
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


class MiniAppAuthUnitTests(unittest.TestCase):
    def test_validate_accepts_fresh_signed_payload(self):
        from app.services.miniapp_auth import validate_webapp_init_data

        token = "123456:ABC-DEF"
        init = _sign_init_data(token, {"id": 42, "first_name": "A"})
        user = validate_webapp_init_data(init, bot_token=token)
        self.assertEqual(user["id"], 42)

    def test_validate_rejects_bad_hash(self):
        from fastapi import HTTPException

        from app.services.miniapp_auth import validate_webapp_init_data

        token = "123456:ABC-DEF"
        init = _sign_init_data(token, {"id": 1}) + "dead"
        with self.assertRaises(HTTPException) as ctx:
            validate_webapp_init_data(init, bot_token=token)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_persona_matrix(self):
        from types import SimpleNamespace

        from app.services.miniapp_auth import resolve_mini_persona

        admin = SimpleNamespace(role="admin", telegram_id=1)
        reseller = SimpleNamespace(role="reseller", telegram_id=2)
        user = SimpleNamespace(role="user", telegram_id=3)
        with unittest.mock.patch(
            "app.services.miniapp_auth.is_bot_platform_admin",
            side_effect=lambda u: getattr(u, "role", None) == "admin",
        ):
            self.assertEqual(resolve_mini_persona(admin), "admin")
            self.assertEqual(resolve_mini_persona(reseller), "reseller")
            self.assertEqual(resolve_mini_persona(user), "user")


class MiniAppSourceTests(unittest.TestCase):
    def test_static_js_escapes_and_safe_url(self):
        src = (ROOT / "app/web/static/miniapp.js").read_text(encoding="utf-8")
        self.assertIn("function esc(", src)
        self.assertIn("createTextNode", src)
        self.assertIn("function safeUrl(", src)
        self.assertNotIn("onclick=\"showSvc(", src)
        self.assertNotIn("tg.openLink(data.service.url)", src)

    def test_template_loads_panel_like_assets(self):
        html = (ROOT / "app/web/templates/miniapp.html").read_text(encoding="utf-8")
        self.assertIn("/static/miniapp.css", html)
        self.assertIn("/static/miniapp.js", html)
        self.assertIn("ma-nav", html)
        self.assertIn("role-badge", html)

    def test_css_matches_panel_brand_tokens(self):
        css = (ROOT / "app/web/static/miniapp.css").read_text(encoding="utf-8")
        self.assertIn("--brand: #f97316", css)
        self.assertIn("--background: #09090b", css)
        self.assertIn("Vazirmatn", css)

    def test_api_registered_via_module(self):
        app_src = (ROOT / "app/api/app.py").read_text(encoding="utf-8")
        self.assertIn("register_miniapp_pages", app_src)
        pages = (ROOT / "app/api/miniapp_pages.py").read_text(encoding="utf-8")
        self.assertIn("persona", pages)
        self.assertIn("_admin_ops_payload", pages)
        self.assertIn("_reseller_ops_payload", pages)

    def test_deep_link_helper(self):
        from app.config import Settings

        s = Settings.model_construct(
            public_base_url="https://bot.example.com",
            bot_token="",
        )
        self.assertTrue(s.miniapp_url.endswith("/miniapp/"))
        self.assertEqual(s.miniapp_deep_url("ops"), s.miniapp_url + "#ops")

    def test_csp_allows_telegram_for_miniapp(self):
        src = (ROOT / "app/api/app.py").read_text(encoding="utf-8")
        self.assertIn('path.startswith("/miniapp")', src)
        self.assertIn("https://telegram.org", src)
        self.assertIn("web.telegram.org", src)

    def test_admin_resellers_hub_offers_miniapp(self):
        src = (ROOT / "app/bot/handlers/reply_nav.py").read_text(encoding="utf-8")
        self.assertIn('view="ops"', src)
        self.assertIn("miniapp_inline_keyboard", src)

    def test_menu_button_webapp_sync(self):
        src = (ROOT / "app/bot/chat_menu.py").read_text(encoding="utf-8")
        self.assertIn("MenuButtonWebApp", src)
        self.assertIn("sync_telegram_menu_button", src)
        main = (ROOT / "app/main.py").read_text(encoding="utf-8")
        self.assertIn("sync_telegram_menu_button", main)


if __name__ == "__main__":
    unittest.main()
