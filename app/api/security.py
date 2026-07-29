"""Account security — change web panel username / password (admin + reseller)."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import ResellerProfile
from app.services.setup_wizard import update_env_keys
from app.services.web_auth import (
    change_web_admin_password,
    change_web_admin_username,
    hash_password,
    load_web_admin,
    validate_password_strength,
    validate_web_username,
    verify_password_hash,
    verify_web_admin,
)


def register_security_pages(app, *, render, require_staff, get_db, get_signer, cookie_secure):
    def _refresh_session(request: Request, staff: dict, *, username: str, pv: str | None = None) -> RedirectResponse:
        from app.services.web_auth import admin_session_version

        payload = dict(staff)
        payload["username"] = username
        if payload.get("role") == "admin":
            payload["sv"] = admin_session_version()
        if pv is not None:
            payload["pv"] = pv
        resp = RedirectResponse("/security?ok=" + quote("ذخیره شد"), status_code=303)
        resp.set_cookie(
            "session",
            get_signer().dumps(payload),
            httponly=True,
            samesite="lax",
            secure=cookie_secure(request),
            max_age=60 * 60 * 24 * 7,
            path="/",
        )
        return resp

    @app.get("/security", response_class=HTMLResponse)
    async def security_page(
        request: Request,
        staff: dict = Depends(require_staff),
    ):
        return render(
            request,
            "security.html",
            {
                "staff": staff,
                "current_username": staff.get("username") or "",
                "ok": request.query_params.get("ok"),
                "err": request.query_params.get("err"),
                "saved_user": request.query_params.get("user") == "1",
                "saved_pass": request.query_params.get("pass") == "1",
            },
        )

    @app.post("/security/username")
    async def security_change_username(
        request: Request,
        staff: dict = Depends(require_staff),
        session: AsyncSession = Depends(get_db),
        current_password: str = Form(""),
        new_username: str = Form(""),
    ):
        role = staff.get("role")
        if role == "admin":
            if not verify_web_admin(staff.get("username") or "", current_password):
                # Also accept if they typed the stored username differently — verify with form user
                if not verify_web_admin(load_web_admin().get("username") or "", current_password):
                    return RedirectResponse(
                        "/security?err=" + quote("رمز فعلی اشتباه است"),
                        status_code=303,
                    )
            cleaned, err = validate_web_username(new_username, lowercase=False)
            if err:
                return RedirectResponse("/security?err=" + quote(err), status_code=303)
            try:
                saved = change_web_admin_username(cleaned)
                update_env_keys({"WEB_ADMIN_USER": saved})
                get_settings.cache_clear()
            except ValueError as e:
                return RedirectResponse("/security?err=" + quote(str(e)), status_code=303)
            return _refresh_session(request, staff, username=saved)

        if role != "reseller":
            return RedirectResponse("/logout", status_code=303)

        rid = int(staff.get("bot_user_id") or 0)
        result = await session.execute(
            select(ResellerProfile).where(ResellerProfile.user_id == rid)
        )
        profile = result.scalar_one_or_none()
        if not profile or not verify_password_hash(current_password, profile.web_password_hash):
            return RedirectResponse(
                "/security?err=" + quote("رمز فعلی اشتباه است"),
                status_code=303,
            )
        cleaned, err = validate_web_username(new_username, lowercase=True)
        if err:
            return RedirectResponse("/security?err=" + quote(err), status_code=303)
        clash = await session.execute(
            select(ResellerProfile).where(
                ResellerProfile.web_username == cleaned,
                ResellerProfile.id != profile.id,
            )
        )
        if clash.scalar_one_or_none():
            return RedirectResponse(
                "/security?err=" + quote("این نام کاربری قبلاً گرفته شده"),
                status_code=303,
            )
        # Don't collide with main admin username
        admin_u = (load_web_admin().get("username") or "").strip().lower()
        if cleaned == admin_u:
            return RedirectResponse(
                "/security?err=" + quote("این نام کاربری برای ادمین اصلی رزرو است"),
                status_code=303,
            )
        profile.web_username = cleaned
        await session.commit()
        return _refresh_session(
            request,
            staff,
            username=cleaned,
            pv=(profile.web_password_hash or "")[:24],
        )

    @app.post("/security/password")
    async def security_change_password(
        request: Request,
        staff: dict = Depends(require_staff),
        session: AsyncSession = Depends(get_db),
        current_password: str = Form(""),
        new_password: str = Form(""),
        new_password2: str = Form(""),
    ):
        if new_password != new_password2:
            return RedirectResponse(
                "/security?err=" + quote("تکرار رمز جدید مطابقت ندارد"),
                status_code=303,
            )
        ok, err = validate_password_strength(new_password)
        if not ok:
            return RedirectResponse("/security?err=" + quote(err), status_code=303)

        role = staff.get("role")
        if role == "admin":
            if not verify_web_admin(load_web_admin().get("username") or "", current_password):
                return RedirectResponse(
                    "/security?err=" + quote("رمز فعلی اشتباه است"),
                    status_code=303,
                )
            try:
                change_web_admin_password(new_password)
            except ValueError as e:
                return RedirectResponse("/security?err=" + quote(str(e)), status_code=303)
            return _refresh_session(
                request, staff, username=load_web_admin().get("username") or staff.get("username") or "admin"
            )

        if role != "reseller":
            return RedirectResponse("/logout", status_code=303)

        rid = int(staff.get("bot_user_id") or 0)
        result = await session.execute(
            select(ResellerProfile).where(ResellerProfile.user_id == rid)
        )
        profile = result.scalar_one_or_none()
        if not profile or not verify_password_hash(current_password, profile.web_password_hash):
            return RedirectResponse(
                "/security?err=" + quote("رمز فعلی اشتباه است"),
                status_code=303,
            )
        profile.web_password_hash = hash_password(new_password)
        await session.commit()
        return _refresh_session(
            request,
            staff,
            username=profile.web_username or staff.get("username") or "",
            pv=(profile.web_password_hash or "")[:24],
        )
