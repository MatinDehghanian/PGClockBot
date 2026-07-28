from __future__ import annotations

"""Reseller setup wizard — bot token registration (web creds may already be provisioned)."""

from urllib.parse import quote

from fastapi import Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.resellers import complete_reseller_setup, get_profile_by_setup_token
from app.services.web_auth import hash_password, validate_password_strength


def _q(msg: str) -> str:
    return quote(str(msg), safe="")


async def _validate_bot_token(token: str) -> tuple[str, int]:
    from aiogram import Bot

    bot = Bot(token=token)
    try:
        me = await bot.get_me()
        return (me.username or str(me.id), int(me.id))
    finally:
        await bot.session.close()


def register_reseller_setup(app, *, render, get_db):
    @app.get("/rsetup/{token}", response_class=HTMLResponse)
    async def reseller_setup_page(
        token: str,
        request: Request,
        session: AsyncSession = Depends(get_db),
    ):
        profile = await get_profile_by_setup_token(session, token)
        if not profile:
            return render(
                request,
                "reseller_setup.html",
                {
                    "invalid": True,
                    "error": "لینک نامعتبر یا منقضی شده است. از ادمین لینک جدید بخواهید.",
                    "token": token,
                    "bot_only": False,
                },
            )
        bot_only = bool(profile.web_username and profile.web_password_hash)
        return render(
            request,
            "reseller_setup.html",
            {
                "invalid": False,
                "token": token,
                "bot_only": bot_only,
                "web_username": profile.web_username,
                "error": request.query_params.get("err"),
                "flash_ok": request.query_params.get("ok"),
            },
        )

    @app.post("/rsetup/{token}")
    async def reseller_setup_submit(
        token: str,
        request: Request,
        username: str = Form(""),
        password: str = Form(""),
        password2: str = Form(""),
        bot_token: str = Form(""),
        session: AsyncSession = Depends(get_db),
    ):
        profile = await get_profile_by_setup_token(session, token)
        if not profile:
            return RedirectResponse(
                f"/rsetup/{token}?err={_q('لینک نامعتبر یا منقضی')}",
                status_code=303,
            )

        bot_only = bool(profile.web_username and profile.web_password_hash)
        bot_token = (bot_token or "").strip()
        if not bot_token:
            return RedirectResponse(
                f"/rsetup/{token}?err={_q('توکن ربات الزامی است — از @BotFather یک ربات بسازید')}",
                status_code=303,
            )
        try:
            bot_username, bot_telegram_id = await _validate_bot_token(bot_token)
        except Exception:
            return RedirectResponse(
                f"/rsetup/{token}?err={_q('توکن ربات نامعتبر است')}",
                status_code=303,
            )

        try:
            if bot_only:
                profile = await complete_reseller_setup(
                    session,
                    profile,
                    bot_token=bot_token,
                    bot_username=bot_username,
                    bot_telegram_id=bot_telegram_id,
                    bot_only=True,
                )
            else:
                if password != password2:
                    return RedirectResponse(
                        f"/rsetup/{token}?err={_q('تکرار رمز مطابقت ندارد')}",
                        status_code=303,
                    )
                ok, err = validate_password_strength(password)
                if not ok:
                    return RedirectResponse(f"/rsetup/{token}?err={_q(err)}", status_code=303)
                profile = await complete_reseller_setup(
                    session,
                    profile,
                    web_username=username.strip(),
                    password_hash=hash_password(password),
                    bot_token=bot_token,
                    bot_username=bot_username,
                    bot_telegram_id=bot_telegram_id,
                )
        except ValueError as e:
            return RedirectResponse(f"/rsetup/{token}?err={_q(str(e))}", status_code=303)

        # Hot-start the reseller bot without requiring a full process restart
        try:
            from app.services.reseller_bots import start_reseller_bot_for_profile

            await start_reseller_bot_for_profile(profile.id)
        except Exception:
            pass

        return RedirectResponse(
            f"/login?ok={_q('راه‌اندازی کامل شد — با یوزر خود وارد شوید')}",
            status_code=303,
        )
