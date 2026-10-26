"""Mini App brand: each shop shows only its own name, photo, colour and notice; panel saves stay in scope."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlencode

import httpx
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.miniapp_brand_pages import register_miniapp_brand_pages
from app.api.miniapp_pages import register_miniapp_pages
from app.db.models import Base, BotUser, ResellerProfile
from app.services.miniapp_branding import (
    ACCENT_SETTING,
    NOTICE_MAX,
    NOTICE_SETTING,
    brand_from_settings,
    normalize_accent,
    normalize_notice,
    save_mini_brand,
)
from app.services.miniapp_shop import PLATFORM_SWITCH, SHOP_SWITCH, new_shop_key
from app.services.secret_box import seal_bot_token
from app.services.users import clear_settings_cache, get_all_settings, set_settings_bulk

ROOT = Path(__file__).resolve().parents[1]
MAIN_TOKEN = "111111:main-bot-token"
SHOP_TOKEN = "222222:shop-bot-token"
OTHER_SHOP_TOKEN = "333333:other-shop-token"
SHOP, OTHER_SHOP = 5, 6
KEY, OTHER_KEY = new_shop_key(), new_shop_key()
PERMS = '["orders","payments","miniapp","shop_settings"]'
PLATFORM_CUSTOMER, CUSTOMER, OTHER_CUSTOMER = 1011, 1010, 1012
PLATFORM_BRAND = {
    "bot_tg_name": "Platform Net", "bot_tg_short_description": "platform caption",
    "bot_tg_photo": "uploads/main_bot_tg_photo_aaaa.jpg", ACCENT_SETTING: "#111111", NOTICE_SETTING: "platform sale",
}
SHOP_BRAND = {
    "bot_tg_name": "Nova", "bot_tg_short_description": "always on",
    "bot_tg_photo": "uploads/r5_bot_tg_photo_bbbb.jpg", ACCENT_SETTING: "#2563eb", NOTICE_SETTING: "shop sale",
}


def signed(token: str, telegram_id: int) -> str:
    fields = {"auth_date": str(int(time.time())), "user": json.dumps({"id": telegram_id}, separators=(",", ":"))}
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


class BrandValueTests(unittest.TestCase):
    def test_accent_must_be_a_six_digit_hex_colour(self) -> None:
        self.assertEqual(normalize_accent(" #2563EB "), "#2563eb")
        self.assertEqual(normalize_accent(""), "")
        for bad in ("red", "#fff", "#12345g", "#1234567", "url(x)", "#123456;color:red", "javascript:1"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                normalize_accent(bad)

    def test_notice_is_one_bounded_line(self) -> None:
        self.assertEqual(normalize_notice("  20%\n off \t now "), "20% off now")
        with self.assertRaises(ValueError):
            normalize_notice("x" * (NOTICE_MAX + 1))

    def test_only_a_saved_profile_photo_becomes_the_logo(self) -> None:
        cases = {
            "uploads/r5_bot_tg_photo_ab12.jpg": "/media/uploads/r5_bot_tg_photo_ab12.jpg",
            "uploads/../bot.db": "", "uploads/tickets/x.jpg": "", "https://evil.example/x.jpg": "",
            "uploads/x.png": "", "/etc/passwd": "", "": "",
        }
        for stored, expected in cases.items():
            with self.subTest(stored=stored):
                self.assertEqual(brand_from_settings({"bot_tg_photo": stored}, name="n").logo_url, expected)

    def test_a_bad_stored_colour_falls_back_to_the_default(self) -> None:
        brand = brand_from_settings({ACCENT_SETTING: "expression(alert(1))"}, name="n")
        self.assertEqual(brand.accent, "")


class BrandFormTemplateTests(unittest.TestCase):
    def render(self, values: dict[str, str]) -> str:
        env = Environment(loader=FileSystemLoader(ROOT / "app/web/templates"), autoescape=select_autoescape())
        return env.get_template("_miniapp_brand_form.html").render(
            values=values, miniapp_brand_action="/shop-settings/miniapp-brand", csrf_token="tok",
        )

    def test_form_shows_saved_values_escaped_with_csrf(self) -> None:
        html = self.render({ACCENT_SETTING: "#2563eb", NOTICE_SETTING: "<script>x</script>"})
        self.assertIn('action="/shop-settings/miniapp-brand"', html)
        self.assertIn('name="csrf_token" value="tok"', html)
        self.assertIn('value="#2563eb"', html)
        self.assertIn("&lt;script&gt;x&lt;/script&gt;", html)
        self.assertNotIn("<script>x", html)
        self.assertNotRegex(html, r'name="miniapp_accent_default" value="1"\s+checked')

    def test_default_colour_switch_is_on_without_a_saved_colour(self) -> None:
        html = self.render({})
        self.assertRegex(html, r'name="miniapp_accent_default" value="1"\s+checked')
        self.assertIn('value="#f97316"', html)


class BrandScopeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        clear_settings_cache()
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.Session = async_sessionmaker(self.engine, expire_on_commit=False)
        now = datetime.now(timezone.utc)
        async with self.Session() as session:
            session.add_all([
                BotUser(id=SHOP, telegram_id=5005, referral_code="o5", role="reseller"),
                BotUser(id=OTHER_SHOP, telegram_id=6006, referral_code="o6", role="reseller"),
                BotUser(id=10, telegram_id=CUSTOMER, referral_code="c10", role="user", reseller_id=SHOP),
                BotUser(id=11, telegram_id=PLATFORM_CUSTOMER, referral_code="c11", role="user"),
                BotUser(id=12, telegram_id=OTHER_CUSTOMER, referral_code="c12", role="user", reseller_id=OTHER_SHOP),
                ResellerProfile(id=1, user_id=SHOP, is_active=True, setup_completed_at=now,
                                bot_token=seal_bot_token(SHOP_TOKEN), miniapp_key=KEY, web_permissions=PERMS),
                ResellerProfile(id=2, user_id=OTHER_SHOP, is_active=True, setup_completed_at=now,
                                bot_token=seal_bot_token(OTHER_SHOP_TOKEN), miniapp_key=OTHER_KEY,
                                web_permissions=PERMS, bot_username="other_shop_bot"),
            ])
            await session.commit()
            await set_settings_bulk(session, {PLATFORM_SWITCH: "1", **PLATFORM_BRAND})
            await set_settings_bulk(session, {SHOP_SWITCH: "1", **SHOP_BRAND}, reseller_id=SHOP)
            await set_settings_bulk(session, {SHOP_SWITCH: "1"}, reseller_id=OTHER_SHOP)
        clear_settings_cache()
        settings = SimpleNamespace(miniapp_enabled=True, bot_token=MAIN_TOKEN, currency="تومان")
        self.patches = [
            patch("app.services.miniapp_auth.get_settings", return_value=settings),
            patch("app.services.miniapp_auth.assert_mini_force_join", return_value=None),
        ]
        for p in self.patches:
            p.start()

        async def get_db():
            async with self.Session() as session:
                yield session

        self.staff: dict = {}

        async def current_staff() -> dict:
            return self.staff

        app = FastAPI()
        register_miniapp_pages(app, render=lambda *_a, **_k: HTMLResponse("page"), get_db=get_db)
        register_miniapp_brand_pages(app, require_admin=current_staff, require_shop_settings=current_staff, get_db=get_db)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        for p in reversed(self.patches):
            p.stop()
        clear_settings_cache()
        await self.engine.dispose()

    async def me(self, token: str, telegram_id: int, key: str | None = None) -> dict:
        headers = {"X-Telegram-Init-Data": signed(token, telegram_id)}
        if key:
            headers["X-Mini-Shop"] = key
        response = await self.client.get("/api/mini/me", headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["brand"]

    async def settings(self, shop_id: int | None) -> dict[str, str]:
        clear_settings_cache()
        async with self.Session() as session:
            return await get_all_settings(session, reseller_id=shop_id)

    async def test_each_mini_app_shows_only_its_own_brand(self) -> None:
        self.assertEqual(await self.me(MAIN_TOKEN, PLATFORM_CUSTOMER), {
            "name": "Platform Net", "tagline": "platform caption",
            "logo_url": "/media/uploads/main_bot_tg_photo_aaaa.jpg", "accent": "#111111", "notice": "platform sale",
        })
        self.assertEqual(await self.me(SHOP_TOKEN, CUSTOMER, KEY), {
            "name": "Nova", "tagline": "always on",
            "logo_url": "/media/uploads/r5_bot_tg_photo_bbbb.jpg", "accent": "#2563eb", "notice": "shop sale",
        })

    async def test_a_shop_without_a_brand_never_inherits_the_platform_or_another_shop(self) -> None:
        brand = await self.me(OTHER_SHOP_TOKEN, OTHER_CUSTOMER, OTHER_KEY)
        self.assertEqual(brand, {"name": "other_shop_bot", "tagline": "", "logo_url": "", "accent": "", "notice": ""})

    async def test_a_shop_owner_saves_only_their_own_shop(self) -> None:
        self.staff = {"role": "reseller", "bot_user_id": OTHER_SHOP}
        response = await self.client.post("/shop-settings/miniapp-brand", data={
            ACCENT_SETTING: "#16A34A", NOTICE_SETTING: "new\nnotice", "reseller_id": str(SHOP), "shop_id": str(SHOP),
        })
        self.assertEqual(response.status_code, 303)
        self.assertIn("saved=1", response.headers["location"])
        other = await self.settings(OTHER_SHOP)
        self.assertEqual((other[ACCENT_SETTING], other[NOTICE_SETTING]), ("#16a34a", "new notice"))
        shop = await self.settings(SHOP)
        self.assertEqual((shop[ACCENT_SETTING], shop[NOTICE_SETTING]), ("#2563eb", "shop sale"))
        platform = await self.settings(None)
        self.assertEqual((platform[ACCENT_SETTING], platform[NOTICE_SETTING]), ("#111111", "platform sale"))

    async def test_the_default_colour_switch_clears_the_custom_colour(self) -> None:
        self.staff = {"role": "reseller", "bot_user_id": SHOP}
        await self.client.post("/shop-settings/miniapp-brand", data={
            ACCENT_SETTING: "#16a34a", "miniapp_accent_default": "1", NOTICE_SETTING: "",
        })
        shop = await self.settings(SHOP)
        self.assertEqual((shop[ACCENT_SETTING], shop[NOTICE_SETTING]), ("", ""))

    async def test_invalid_input_is_refused_and_nothing_changes(self) -> None:
        self.staff = {"role": "reseller", "bot_user_id": SHOP}
        for data in ({ACCENT_SETTING: "red", NOTICE_SETTING: "ok"},
                     {ACCENT_SETTING: "#16a34a", NOTICE_SETTING: "x" * (NOTICE_MAX + 1)}):
            with self.subTest(data=data[ACCENT_SETTING]):
                response = await self.client.post("/shop-settings/miniapp-brand", data=data)
                self.assertIn("err=", response.headers["location"])
        shop = await self.settings(SHOP)
        self.assertEqual((shop[ACCENT_SETTING], shop[NOTICE_SETTING]), ("#2563eb", "shop sale"))

    async def test_staff_without_a_shop_cannot_save_shop_branding(self) -> None:
        for staff in ({"role": "admin"}, {"role": "pg_staff"}, {"role": "reseller", "bot_user_id": 0}):
            with self.subTest(staff=staff):
                self.staff = staff
                response = await self.client.post("/shop-settings/miniapp-brand", data={ACCENT_SETTING: "#000000"})
                self.assertEqual(response.status_code, 303)
                self.assertNotIn("saved=1", response.headers["location"])
        platform = await self.settings(None)
        self.assertEqual(platform[ACCENT_SETTING], "#111111")

    async def test_the_platform_form_saves_platform_settings_only(self) -> None:
        self.staff = {"role": "admin"}
        response = await self.client.post("/settings/miniapp-brand", data={ACCENT_SETTING: "#9333ea", NOTICE_SETTING: "hi"})
        self.assertIn("saved=1", response.headers["location"])
        self.assertEqual((await self.settings(None))[ACCENT_SETTING], "#9333ea")
        self.assertEqual((await self.settings(SHOP))[ACCENT_SETTING], "#2563eb")

    async def test_save_rejects_bad_values_at_the_service(self) -> None:
        async with self.Session() as session:
            with self.assertRaises(ValueError):
                await save_mini_brand(session, shop_id=SHOP, accent="#zzzzzz", notice="")
        self.assertEqual((await self.settings(SHOP))[ACCENT_SETTING], "#2563eb")


if __name__ == "__main__":
    unittest.main()
