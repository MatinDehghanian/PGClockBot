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

    def _err(msg: str) -> RedirectResponse:
        return RedirectResponse("/security?err=" + quote(msg), status_code=303)

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
            },
        )

    @app.post("/security/credentials")
    async def security_change_credentials(
        request: Request,
        staff: dict = Depends(require_staff),
        session: AsyncSession = Depends(get_db),
        old_username: str = Form(""),
        current_password: str = Form(""),
        new_username: str = Form(""),
        new_password: str = Form(""),
    ):
        role = staff.get("role")
        old_u = (old_username or "").strip()
        new_u = (new_username or "").strip()
        cur_pass = current_password or ""
        new_pass = new_password or ""

        if not old_u or not cur_pass or not new_u or not new_pass:
            return _err("همه فیلدها الزامی هستند")

        ok, err = validate_password_strength(new_pass)
        if not ok:
            return _err(err)

        if role == "admin":
            admin = load_web_admin()
            stored_user = (admin.get("username") or "").strip()
            session_user = (staff.get("username") or "").strip()
            if old_u not in {stored_user, session_user} or not verify_web_admin(stored_user, cur_pass):
                return _err("یوزر یا رمز قدیم اشتباه است")

            cleaned, uerr = validate_web_username(new_u, lowercase=False)
            if uerr:
                return _err(uerr)

            try:
                if cleaned != stored_user:
                    saved = change_web_admin_username(cleaned)
                    update_env_keys({"WEB_ADMIN_USER": saved})
                    get_settings.cache_clear()
                else:
                    saved = stored_user
                if new_pass:
                    change_web_admin_password(new_pass)
            except ValueError as e:
                return _err(str(e))
            return _refresh_session(request, staff, username=saved)

        if role != "reseller":
            return RedirectResponse("/logout", status_code=303)

        rid = int(staff.get("bot_user_id") or 0)
        result = await session.execute(
            select(ResellerProfile).where(ResellerProfile.user_id == rid)
        )
        profile = result.scalar_one_or_none()
        current_u = (profile.web_username if profile else "") or (staff.get("username") or "")
        if (
            not profile
            or old_u.lower() != str(current_u).lower()
            or not verify_password_hash(cur_pass, profile.web_password_hash)
        ):
            return _err("یوزر یا رمز قدیم اشتباه است")

        cleaned, uerr = validate_web_username(new_u, lowercase=True)
        if uerr:
            return _err(uerr)

        if cleaned != profile.web_username:
            clash = await session.execute(
                select(ResellerProfile).where(
                    ResellerProfile.web_username == cleaned,
                    ResellerProfile.id != profile.id,
                )
            )
            if clash.scalar_one_or_none():
                return _err("این نام کاربری قبلاً گرفته شده")
            admin_u = (load_web_admin().get("username") or "").strip().lower()
            if cleaned == admin_u:
                return _err("این نام کاربری برای ادمین اصلی رزرو است")
            profile.web_username = cleaned

        profile.web_password_hash = hash_password(new_pass)
        await session.commit()
        return _refresh_session(
            request,
            staff,
            username=profile.web_username or cleaned,
            pv=(profile.web_password_hash or "")[:24],
        )

    # Back-compat aliases — redirect into the unified credentials flow semantics
    @app.post("/security/username")
    async def security_change_username_legacy(
        request: Request,
        staff: dict = Depends(require_staff),
        session: AsyncSession = Depends(get_db),
        current_password: str = Form(""),
        new_username: str = Form(""),
    ):
        # Keep old password unchanged: require new_password empty path via credentials is not possible;
        # preserve previous username-only behavior.
        role = staff.get("role")
        if role == "admin":
            if not verify_web_admin(load_web_admin().get("username") or "", current_password):
                if not verify_web_admin(staff.get("username") or "", current_password):
                    return _err("رمز فعلی اشتباه است")
            cleaned, err = validate_web_username(new_username, lowercase=False)
            if err:
                return _err(err)
            try:
                saved = change_web_admin_username(cleaned)
                update_env_keys({"WEB_ADMIN_USER": saved})
                get_settings.cache_clear()
            except ValueError as e:
                return _err(str(e))
            return _refresh_session(request, staff, username=saved)

        if role != "reseller":
            return RedirectResponse("/logout", status_code=303)

        rid = int(staff.get("bot_user_id") or 0)
        result = await session.execute(
            select(ResellerProfile).where(ResellerProfile.user_id == rid)
        )
        profile = result.scalar_one_or_none()
        if not profile or not verify_password_hash(current_password, profile.web_password_hash):
            return _err("رمز فعلی اشتباه است")
        cleaned, err = validate_web_username(new_username, lowercase=True)
        if err:
            return _err(err)
        clash = await session.execute(
            select(ResellerProfile).where(
                ResellerProfile.web_username == cleaned,
                ResellerProfile.id != profile.id,
            )
        )
        if clash.scalar_one_or_none():
            return _err("این نام کاربری قبلاً گرفته شده")
        admin_u = (load_web_admin().get("username") or "").strip().lower()
        if cleaned == admin_u:
            return _err("این نام کاربری برای ادمین اصلی رزرو است")
        profile.web_username = cleaned
        await session.commit()
        return _refresh_session(
            request,
            staff,
            username=cleaned,
            pv=(profile.web_password_hash or "")[:24],
        )

    @app.post("/security/password")
    async def security_change_password_legacy(
        request: Request,
        staff: dict = Depends(require_staff),
        session: AsyncSession = Depends(get_db),
        current_password: str = Form(""),
        new_password: str = Form(""),
        new_password2: str = Form(""),
    ):
        if new_password != new_password2:
            return _err("تکرار رمز جدید مطابقت ندارد")
        ok, err = validate_password_strength(new_password)
        if not ok:
            return _err(err)

        role = staff.get("role")
        if role == "admin":
            if not verify_web_admin(load_web_admin().get("username") or "", current_password):
                return _err("رمز فعلی اشتباه است")
            try:
                change_web_admin_password(new_password)
            except ValueError as e:
                return _err(str(e))
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
            return _err("رمز فعلی اشتباه است")
        profile.web_password_hash = hash_password(new_password)
        await session.commit()
        return _refresh_session(
            request,
            staff,
            username=profile.web_username or staff.get("username") or "",
            pv=(profile.web_password_hash or "")[:24],
        )
