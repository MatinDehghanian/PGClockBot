from __future__ import annotations

"""Reseller plans, applications, and staff management pages."""

from urllib.parse import quote

from fastapi import Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import BotUser, ResellerPlan, ResellerProfile, Role
from app.services.pasarguard import get_pg
from app.services.resellers import (
    BOT_PERM_OPTIONS,
    DEFAULT_BOT_PERMS,
    DEFAULT_WEB_PERMS,
    WEB_PERM_OPTIONS,
    approve_application,
    format_credentials_message,
    get_application,
    join_perms,
    list_applications,
    list_reseller_plans,
    parse_perms,
    provision_reseller,
    reject_application,
)
from app.services.web_auth import hash_password


def _q(msg: str) -> str:
    return quote(str(msg), safe="")


def _perm_from_form(form, prefix: str, options: list[tuple[str, str]]) -> str:
    selected = []
    for key, _ in options:
        if form.get(f"{prefix}_{key}"):
            selected.append(key)
    return join_perms(selected)


def register_reseller_pages(app, *, render, require_admin, get_db, get_bot=None):
    def _tabs(active: str) -> list[dict]:
        return [
            {"href": "/resellers", "label": "لیست", "id": "list"},
            {"href": "/resellers/plans", "label": "پلن‌ها", "id": "plans"},
            {"href": "/resellers/applications", "label": "درخواست‌ها", "id": "apps"},
        ]

    @app.get("/resellers", response_class=HTMLResponse)
    async def resellers_page(
        request: Request,
        staff: dict = Depends(require_admin),
        session: AsyncSession = Depends(get_db),
    ):
        result = await session.execute(
            select(BotUser, ResellerProfile)
            .join(ResellerProfile, ResellerProfile.user_id == BotUser.id)
            .order_by(ResellerProfile.id.desc())
        )
        rows = result.all()
        roles = []
        try:
            roles = await get_pg().get_admin_roles()
        except Exception:
            roles = []
        return render(
            request,
            "resellers.html",
            {
                "staff": staff,
                "rows": rows,
                "tabs": _tabs("list"),
                "tab": "list",
                "web_perm_options": WEB_PERM_OPTIONS,
                "bot_perm_options": BOT_PERM_OPTIONS,
                "pg_roles": roles,
                "flash_ok": request.query_params.get("ok"),
                "flash_err": request.query_params.get("err"),
            },
        )

    @app.post("/resellers")
    async def reseller_create(
        request: Request,
        staff: dict = Depends(require_admin),
        session: AsyncSession = Depends(get_db),
    ):
        form = await request.form()
        try:
            telegram_id = int(str(form.get("telegram_id") or "0"))
        except ValueError:
            return RedirectResponse(f"/resellers?err={_q('آیدی تلگرام نامعتبر')}", status_code=303)
        result = await session.execute(select(BotUser).where(BotUser.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        if not user:
            return RedirectResponse(
                f"/resellers?err={_q('کاربر با این آیدی در ربات پیدا نشد — اول باید استارت زده باشد')}",
                status_code=303,
            )
        try:
            commission = int(str(form.get("commission_percent") or "10"))
        except ValueError:
            commission = 10
        web_perms = _perm_from_form(form, "web", WEB_PERM_OPTIONS) or DEFAULT_WEB_PERMS
        bot_perms = _perm_from_form(form, "bot", BOT_PERM_OPTIONS) or DEFAULT_BOT_PERMS
        can_approve = "approve_receipts" in parse_perms(bot_perms) or bool(form.get("can_approve"))
        create_pg = bool(form.get("create_pg_admin"))
        create_web = bool(form.get("create_web_access"))
        pg_role_raw = str(form.get("pg_role_id") or "").strip()
        pg_role_id = int(pg_role_raw) if pg_role_raw.isdigit() else None
        panel_url = str(get_settings().public_base_url or "").strip()
        try:
            creds = await provision_reseller(
                session,
                user=user,
                commission_percent=commission,
                can_approve_receipts=can_approve,
                web_permissions=web_perms,
                bot_permissions=bot_perms,
                create_pg_admin=create_pg,
                create_web_access=create_web,
                pg_role_id=pg_role_id,
                panel_base_url=panel_url,
            )
        except Exception as e:
            return RedirectResponse(f"/resellers?err={_q(str(e))}", status_code=303)

        # Deliver credentials in Telegram if possible
        try:
            from app.bot import create_bot

            bot = create_bot()
            try:
                await bot.send_message(
                    user.telegram_id,
                    format_credentials_message(creds),
                    parse_mode="HTML",
                )
            finally:
                await bot.session.close()
        except Exception:
            pass
        return RedirectResponse(f"/resellers?ok={_q('نماینده ساخته شد و اطلاعات ارسال شد')}", status_code=303)

    @app.get("/resellers/{user_id}/edit", response_class=HTMLResponse)
    async def reseller_edit_page(
        user_id: int,
        request: Request,
        staff: dict = Depends(require_admin),
        session: AsyncSession = Depends(get_db),
    ):
        user = await session.get(BotUser, user_id)
        profile = (
            await session.execute(select(ResellerProfile).where(ResellerProfile.user_id == user_id))
        ).scalar_one_or_none()
        if not user or not profile:
            return RedirectResponse(f"/resellers?err={_q('نماینده یافت نشد')}", status_code=303)
        roles = []
        try:
            roles = await get_pg().get_admin_roles()
        except Exception:
            roles = []
        return render(
            request,
            "reseller_edit.html",
            {
                "staff": staff,
                "user": user,
                "profile": profile,
                "web_perm_options": WEB_PERM_OPTIONS,
                "bot_perm_options": BOT_PERM_OPTIONS,
                "web_perms": parse_perms(profile.web_permissions) or parse_perms(DEFAULT_WEB_PERMS),
                "bot_perms": parse_perms(profile.bot_permissions) or parse_perms(DEFAULT_BOT_PERMS),
                "pg_roles": roles,
                "flash_ok": request.query_params.get("ok"),
                "flash_err": request.query_params.get("err"),
            },
        )

    @app.post("/resellers/{user_id}/edit")
    async def reseller_edit_save(
        user_id: int,
        request: Request,
        staff: dict = Depends(require_admin),
        session: AsyncSession = Depends(get_db),
    ):
        form = await request.form()
        user = await session.get(BotUser, user_id)
        profile = (
            await session.execute(select(ResellerProfile).where(ResellerProfile.user_id == user_id))
        ).scalar_one_or_none()
        if not user or not profile:
            return RedirectResponse(f"/resellers?err={_q('نماینده یافت نشد')}", status_code=303)
        try:
            profile.commission_percent = int(str(form.get("commission_percent") or "10"))
        except ValueError:
            pass
        web_perms = _perm_from_form(form, "web", WEB_PERM_OPTIONS)
        bot_perms = _perm_from_form(form, "bot", BOT_PERM_OPTIONS)
        profile.web_permissions = web_perms or DEFAULT_WEB_PERMS
        profile.bot_permissions = bot_perms or DEFAULT_BOT_PERMS
        profile.can_approve_receipts = "approve_receipts" in parse_perms(profile.bot_permissions)
        profile.is_active = bool(form.get("is_active"))
        pg_role_raw = str(form.get("pg_role_id") or "").strip()
        profile.pg_role_id = int(pg_role_raw) if pg_role_raw.isdigit() else None
        pg_user = str(form.get("pg_admin_username") or "").strip()
        profile.pg_admin_username = pg_user or None
        new_web_pass = str(form.get("web_password") or "").strip()
        if new_web_pass:
            if not profile.web_username:
                profile.web_username = f"web_{user.telegram_id}"
            profile.web_password_hash = hash_password(new_web_pass)
        if not profile.web_username and bool(form.get("ensure_web")):
            from app.services.resellers import _rand_password, _rand_username

            plain = _rand_password()
            profile.web_username = _rand_username("web")
            profile.web_password_hash = hash_password(plain)
            try:
                from app.bot import create_bot

                bot = create_bot()
                try:
                    url = str(get_settings().public_base_url or "").rstrip("/")
                    await bot.send_message(
                        user.telegram_id,
                        "🌐 دسترسی وب‌پنل به‌روز شد\n"
                        + (f"آدرس: {url}\n" if url else "")
                        + f"نام کاربری: <code>{profile.web_username}</code>\n"
                        f"رمز: <code>{plain}</code>",
                        parse_mode="HTML",
                    )
                finally:
                    await bot.session.close()
            except Exception:
                pass
        user.role = Role.RESELLER.value if profile.is_active else Role.USER.value
        await session.commit()
        return RedirectResponse(
            f"/resellers/{user_id}/edit?ok={_q('ذخیره شد')}", status_code=303
        )

    # ---- plans ----
    @app.get("/resellers/plans", response_class=HTMLResponse)
    async def reseller_plans_page(
        request: Request,
        staff: dict = Depends(require_admin),
        session: AsyncSession = Depends(get_db),
    ):
        plans = await list_reseller_plans(session)
        roles = []
        try:
            roles = await get_pg().get_admin_roles()
        except Exception:
            roles = []
        return render(
            request,
            "reseller_plans.html",
            {
                "staff": staff,
                "plans": plans,
                "tabs": _tabs("plans"),
                "tab": "plans",
                "web_perm_options": WEB_PERM_OPTIONS,
                "bot_perm_options": BOT_PERM_OPTIONS,
                "pg_roles": roles,
                "flash_ok": request.query_params.get("ok"),
                "flash_err": request.query_params.get("err"),
            },
        )

    @app.post("/resellers/plans")
    async def reseller_plan_create(
        request: Request,
        staff: dict = Depends(require_admin),
        session: AsyncSession = Depends(get_db),
    ):
        form = await request.form()
        name = str(form.get("name") or "").strip()
        if not name:
            return RedirectResponse(f"/resellers/plans?err={_q('نام الزامی است')}", status_code=303)
        try:
            price = int(str(form.get("price") or "0").replace(",", "").replace("٬", ""))
        except ValueError:
            price = 0
        try:
            commission = int(str(form.get("commission_percent") or "10"))
        except ValueError:
            commission = 10
        web_perms = _perm_from_form(form, "web", WEB_PERM_OPTIONS) or DEFAULT_WEB_PERMS
        bot_perms = _perm_from_form(form, "bot", BOT_PERM_OPTIONS) or DEFAULT_BOT_PERMS
        pg_role_raw = str(form.get("pg_role_id") or "").strip()
        plan = ResellerPlan(
            name=name,
            description=str(form.get("description") or "").strip() or None,
            price=max(0, price),
            commission_percent=commission,
            can_approve_receipts="approve_receipts" in parse_perms(bot_perms),
            web_permissions=web_perms,
            bot_permissions=bot_perms,
            create_pg_admin=bool(form.get("create_pg_admin")),
            create_web_access=bool(form.get("create_web_access")),
            pg_role_id=int(pg_role_raw) if pg_role_raw.isdigit() else None,
            is_active=bool(form.get("is_active", "1")),
            sort_order=int(str(form.get("sort_order") or "0") or "0"),
        )
        session.add(plan)
        await session.commit()
        return RedirectResponse(f"/resellers/plans?ok={_q('پلن ذخیره شد')}", status_code=303)

    @app.post("/resellers/plans/{plan_id}/toggle")
    async def reseller_plan_toggle(
        plan_id: int,
        staff: dict = Depends(require_admin),
        session: AsyncSession = Depends(get_db),
    ):
        plan = await session.get(ResellerPlan, plan_id)
        if plan:
            plan.is_active = not plan.is_active
            await session.commit()
        return RedirectResponse("/resellers/plans", status_code=303)

    @app.post("/resellers/plans/{plan_id}/delete")
    async def reseller_plan_delete(
        plan_id: int,
        staff: dict = Depends(require_admin),
        session: AsyncSession = Depends(get_db),
    ):
        plan = await session.get(ResellerPlan, plan_id)
        if plan:
            await session.delete(plan)
            await session.commit()
        return RedirectResponse(f"/resellers/plans?ok={_q('حذف شد')}", status_code=303)

    # ---- applications ----
    @app.get("/resellers/applications", response_class=HTMLResponse)
    async def reseller_apps_page(
        request: Request,
        staff: dict = Depends(require_admin),
        session: AsyncSession = Depends(get_db),
    ):
        apps = await list_applications(session)
        return render(
            request,
            "reseller_applications.html",
            {
                "staff": staff,
                "apps": apps,
                "tabs": _tabs("apps"),
                "tab": "apps",
                "flash_ok": request.query_params.get("ok"),
                "flash_err": request.query_params.get("err"),
            },
        )

    @app.post("/resellers/applications/{app_id}/approve")
    async def reseller_app_approve(
        app_id: int,
        staff: dict = Depends(require_admin),
        session: AsyncSession = Depends(get_db),
    ):
        app = await get_application(session, app_id)
        if not app:
            return RedirectResponse(f"/resellers/applications?err={_q('یافت نشد')}", status_code=303)
        try:
            creds = await approve_application(
                session,
                app,
                reviewer_tg=0,
                panel_base_url=str(get_settings().public_base_url or ""),
            )
            user = await session.get(BotUser, app.user_id)
            if user:
                from app.bot import create_bot

                bot = create_bot()
                try:
                    await bot.send_message(
                        user.telegram_id,
                        format_credentials_message(creds),
                        parse_mode="HTML",
                    )
                finally:
                    await bot.session.close()
        except Exception as e:
            return RedirectResponse(
                f"/resellers/applications?err={_q(str(e))}", status_code=303
            )
        return RedirectResponse(
            f"/resellers/applications?ok={_q('تأیید شد و اطلاعات برای کاربر ارسال شد')}",
            status_code=303,
        )

    @app.post("/resellers/applications/{app_id}/reject")
    async def reseller_app_reject(
        app_id: int,
        staff: dict = Depends(require_admin),
        session: AsyncSession = Depends(get_db),
    ):
        app = await get_application(session, app_id)
        if not app:
            return RedirectResponse(f"/resellers/applications?err={_q('یافت نشد')}", status_code=303)
        try:
            await reject_application(session, app, reviewer_tg=0)
            user = await session.get(BotUser, app.user_id)
            if user:
                from app.bot import create_bot

                bot = create_bot()
                try:
                    await bot.send_message(
                        user.telegram_id,
                        "❌ درخواست نمایندگی شما رد شد.\nدر صورت نیاز با پشتیبانی در ارتباط باشید.",
                    )
                finally:
                    await bot.session.close()
        except Exception as e:
            return RedirectResponse(
                f"/resellers/applications?err={_q(str(e))}", status_code=303
            )
        return RedirectResponse(f"/resellers/applications?ok={_q('رد شد')}", status_code=303)
