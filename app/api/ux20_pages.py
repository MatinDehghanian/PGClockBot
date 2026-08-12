"""UX20 web routes: delivery queue, gift codes, export/import, notes, magic links."""

from __future__ import annotations

import json
from urllib.parse import quote

from fastapi import Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import BotUser, ChargeCode, DeliveryFailure, Order
from app.services.authz import authz_from_staff, can_shop
from app.services.shop_scope import is_platform_admin, shop_owner_id
from app.services.users import get_all_settings, get_setting, on, set_setting
from app.services.ux20 import (
    bot_deep_link,
    create_charge_code,
    export_shop_bundle,
    import_shop_bundle,
    list_open_delivery_failures,
    retry_delivery,
    shop_bundle_to_json,
)


def register_ux20_pages(app, *, render, require_staff, require_admin, get_db):
    @app.post("/plans/{plan_id}/clone")
    async def plans_clone(
        plan_id: int,
        request: Request,
        staff: dict = Depends(require_staff),
        session: AsyncSession = Depends(get_db),
    ):
        authz = authz_from_staff(staff)
        if not (is_platform_admin(staff) or can_shop(authz, "plans")):
            return RedirectResponse("/home", status_code=303)
        from app.services.ux20 import clone_plan

        rid = None if is_platform_admin(staff) else shop_owner_id(staff)
        try:
            copy = await clone_plan(session, plan_id, owner_reseller_id=rid)
            return RedirectResponse(
                f"/plans/{copy.id}/edit?ok={quote('کپی پلن ساخته شد — فعلاً خاموش است')}",
                status_code=303,
            )
        except Exception as exc:
            return RedirectResponse(
                f"/plans?err={quote(str(exc) or 'خطا در کپی پلن')}",
                status_code=303,
            )

    @app.post("/orders/{order_id}/retry-delivery")
    async def orders_retry_delivery(
        order_id: int,
        staff: dict = Depends(require_staff),
        session: AsyncSession = Depends(get_db),
    ):
        authz = authz_from_staff(staff)
        if not (is_platform_admin(staff) or can_shop(authz, "orders")):
            return RedirectResponse("/home", status_code=303)
        order = (
            await session.execute(select(Order).where(Order.id == int(order_id)))
        ).scalar_one_or_none()
        if not order:
            return RedirectResponse(
                f"/finance?tab=delivery&err={quote('سفارش پیدا نشد')}", status_code=303
            )
        rid = shop_owner_id(staff)
        if not is_platform_admin(staff):
            if not rid or int(order.reseller_id or 0) != int(rid):
                return RedirectResponse("/home", status_code=303)
        try:
            await retry_delivery(session, int(order_id))
            return RedirectResponse(
                f"/finance?tab=delivery&ok={quote('تحویل دوباره انجام شد')}",
                status_code=303,
            )
        except Exception as exc:
            return RedirectResponse(
                f"/finance?tab=delivery&err={quote(str(exc) or 'تلاش مجدد ناموفق')}",
                status_code=303,
            )

    @app.post("/orders/{order_id}/staff-note")
    async def orders_staff_note(
        order_id: int,
        note: str = Form(""),
        staff: dict = Depends(require_staff),
        session: AsyncSession = Depends(get_db),
    ):
        authz = authz_from_staff(staff)
        if not (is_platform_admin(staff) or can_shop(authz, "orders")):
            return RedirectResponse("/home", status_code=303)
        order = (
            await session.execute(select(Order).where(Order.id == int(order_id)))
        ).scalar_one_or_none()
        if not order:
            return RedirectResponse("/finance?tab=orders", status_code=303)
        if not is_platform_admin(staff):
            rid = shop_owner_id(staff)
            if not rid or int(order.reseller_id or 0) != int(rid):
                return RedirectResponse("/home", status_code=303)
        order.staff_note = (note or "").strip()[:2000] or None
        await session.commit()
        return RedirectResponse(
            f"/finance?tab=orders&ok={quote('یادداشت ذخیره شد')}", status_code=303
        )

    @app.post("/users/{user_id}/staff-note")
    async def users_staff_note(
        user_id: int,
        note: str = Form(""),
        risk_manual: str = Form(""),
        staff: dict = Depends(require_staff),
        session: AsyncSession = Depends(get_db),
    ):
        from app.services.ux20 import parse_risk_flags, refresh_user_risk, serialize_risk_flags

        if not is_platform_admin(staff) and not can_shop(authz_from_staff(staff), "users"):
            return RedirectResponse("/home", status_code=303)
        user = (
            await session.execute(select(BotUser).where(BotUser.id == int(user_id)))
        ).scalar_one_or_none()
        if not user:
            return RedirectResponse("/users", status_code=303)
        if not is_platform_admin(staff):
            rid = shop_owner_id(staff)
            if not rid or int(user.reseller_id or 0) != int(rid):
                return RedirectResponse("/home", status_code=303)
        user.staff_note = (note or "").strip()[:2000] or None
        flags = [f for f in parse_risk_flags(user.risk_flags) if f != "manual"]
        if (risk_manual or "").strip() in {"1", "on", "true", "yes"}:
            flags.append("manual")
        user.risk_flags = serialize_risk_flags(flags)
        await refresh_user_risk(session, user)
        await session.commit()
        return RedirectResponse(
            f"/users/{user_id}?ok={quote('یادداشت و ریسک ذخیره شد')}", status_code=303
        )

    @app.get("/tools/gift-codes", response_class=HTMLResponse)
    async def gift_codes_page(
        request: Request,
        staff: dict = Depends(require_staff),
        session: AsyncSession = Depends(get_db),
    ):
        authz = authz_from_staff(staff)
        if not (is_platform_admin(staff) or can_shop(authz, "orders") or can_shop(authz, "payments")):
            return RedirectResponse("/home", status_code=303)
        rid = None if is_platform_admin(staff) else shop_owner_id(staff)
        q = select(ChargeCode).order_by(ChargeCode.id.desc()).limit(200)
        if rid is None:
            q = q.where(ChargeCode.reseller_id.is_(None))
        else:
            q = q.where(ChargeCode.reseller_id == int(rid))
        codes = list((await session.execute(q)).scalars().all())
        return render(
            request,
            "gift_codes.html",
            {
                "staff": staff,
                "codes": codes,
                "flash_ok": request.query_params.get("ok"),
                "flash_err": request.query_params.get("err"),
            },
        )

    @app.post("/tools/gift-codes")
    async def gift_codes_create(
        amount: int = Form(...),
        max_uses: int = Form(1),
        code: str = Form(""),
        note: str = Form(""),
        staff: dict = Depends(require_staff),
        session: AsyncSession = Depends(get_db),
    ):
        authz = authz_from_staff(staff)
        if not (is_platform_admin(staff) or can_shop(authz, "orders")):
            return RedirectResponse("/home", status_code=303)
        rid = None if is_platform_admin(staff) else shop_owner_id(staff)
        try:
            row = await create_charge_code(
                session,
                amount=int(amount),
                max_uses=int(max_uses) if max_uses else None,
                reseller_id=rid,
                note=note,
                code=code or None,
            )
            return RedirectResponse(
                f"/tools/gift-codes?ok={quote('کد ساخته شد: ' + row.code)}",
                status_code=303,
            )
        except Exception as exc:
            return RedirectResponse(
                f"/tools/gift-codes?err={quote(str(exc) or 'خطا')}",
                status_code=303,
            )

    @app.post("/tools/gift-codes/{code_id}/toggle")
    async def gift_codes_toggle(
        code_id: int,
        staff: dict = Depends(require_staff),
        session: AsyncSession = Depends(get_db),
    ):
        rid = None if is_platform_admin(staff) else shop_owner_id(staff)
        row = (
            await session.execute(select(ChargeCode).where(ChargeCode.id == int(code_id)))
        ).scalar_one_or_none()
        if not row:
            return RedirectResponse("/tools/gift-codes", status_code=303)
        if rid is None and row.reseller_id is not None:
            return RedirectResponse("/tools/gift-codes", status_code=303)
        if rid is not None and int(row.reseller_id or 0) != int(rid):
            return RedirectResponse("/tools/gift-codes", status_code=303)
        row.is_active = not bool(row.is_active)
        await session.commit()
        return RedirectResponse("/tools/gift-codes?ok=1", status_code=303)

    @app.get("/tools/export")
    async def shop_export(
        staff: dict = Depends(require_staff),
        session: AsyncSession = Depends(get_db),
    ):
        if not (is_platform_admin(staff) or can_shop(authz_from_staff(staff), "shop_settings")):
            return RedirectResponse("/home", status_code=303)
        rid = None if is_platform_admin(staff) else shop_owner_id(staff)
        data = await export_shop_bundle(session, reseller_id=rid)
        body = shop_bundle_to_json(data).encode("utf-8")
        return Response(
            content=body,
            media_type="application/json; charset=utf-8",
            headers={
                "Content-Disposition": 'attachment; filename="pgclock-shop-bundle.json"'
            },
        )

    @app.post("/tools/import")
    async def shop_import(
        request: Request,
        file: UploadFile = File(...),
        replace_plans: str = Form(""),
        staff: dict = Depends(require_staff),
        session: AsyncSession = Depends(get_db),
    ):
        if not (is_platform_admin(staff) or can_shop(authz_from_staff(staff), "shop_settings")):
            return RedirectResponse("/home", status_code=303)
        rid = None if is_platform_admin(staff) else shop_owner_id(staff)
        try:
            raw = await file.read()
            payload = json.loads(raw.decode("utf-8"))
            stats = await import_shop_bundle(
                session,
                payload,
                reseller_id=rid,
                replace_plans=(replace_plans or "").strip() in {"1", "on", "true"},
            )
            msg = f"وارد شد: {stats.get('settings', 0)} تنظیمات، {stats.get('plans', 0)} پلن"
            return RedirectResponse(
                f"/settings?tab=welcome&ok={quote(msg)}",
                status_code=303,
            )
        except Exception as exc:
            return RedirectResponse(
                f"/settings?tab=welcome&err={quote(str(exc) or 'خطای ایمپورت')}",
                status_code=303,
            )

    @app.get("/tools/magic-links", response_class=HTMLResponse)
    async def magic_links_page(
        request: Request,
        staff: dict = Depends(require_staff),
        session: AsyncSession = Depends(get_db),
    ):
        from app.config import get_settings
        from app.db.models import ResellerProfile
        from app.services.home_overview import check_bot_connection

        rid = None if is_platform_admin(staff) else shop_owner_id(staff)
        bot_username = None
        if rid:
            profile = (
                await session.execute(
                    select(ResellerProfile).where(ResellerProfile.user_id == int(rid))
                )
            ).scalar_one_or_none()
            bot_username = (profile.bot_username if profile else None) or None
            if not bot_username and profile and profile.bot_token:
                st = await check_bot_connection(profile.bot_token)
                bot_username = st.get("username")
        else:
            st = await check_bot_connection(get_settings().bot_token)
            bot_username = st.get("username")
        links = {
            "renew": bot_deep_link(bot_username, "renew"),
            "wallet": bot_deep_link(bot_username, "wallet"),
            "support": bot_deep_link(bot_username, "support"),
            "config": bot_deep_link(bot_username, "config"),
            "gift": bot_deep_link(bot_username, "gift"),
        }
        return render(
            request,
            "magic_links.html",
            {"staff": staff, "bot_username": bot_username, "links": links},
        )

    @app.get("/home/pg-health")
    async def home_pg_health(
        staff: dict = Depends(require_staff),
        session: AsyncSession = Depends(get_db),
    ):
        from app.services.ux20 import check_pg_connection

        rid = None if is_platform_admin(staff) else shop_owner_id(staff)
        if is_platform_admin(staff):
            data = await check_pg_connection()
        else:
            data = await check_pg_connection(reseller_user_id=rid, session=session)
        return JSONResponse(data)

    @app.get("/tools/funnel")
    async def funnel_page(
        request: Request,
        staff: dict = Depends(require_staff),
        session: AsyncSession = Depends(get_db),
    ):
        from app.services.ux20 import funnel_summary

        rid = None if is_platform_admin(staff) else shop_owner_id(staff)
        summary = await funnel_summary(session, reseller_id=rid, days=7)
        return render(
            request,
            "funnel.html",
            {"staff": staff, "funnel": summary, "days": 7},
        )

    @app.post("/backup/verify-last")
    async def backup_verify_last(staff: dict = Depends(require_admin), session: AsyncSession = Depends(get_db)):
        from pathlib import Path

        from app.services.backup import list_backups, validate_backup_archive

        backups = list_backups()
        if not backups:
            return RedirectResponse(
                f"/settings?tab=backup&err={quote('بکاپی نیست')}", status_code=303
            )
        path = Path(str(backups[0].get("path") or ""))
        ok, err, _ = validate_backup_archive(path)
        await set_setting(session, "backup_last_verify_ok", "1" if ok else "0")
        await session.commit()
        if ok:
            return RedirectResponse(
                f"/settings?tab=backup&ok={quote('آخرین بکاپ سالم است')}",
                status_code=303,
            )
        return RedirectResponse(
            f"/settings?tab=backup&err={quote(err or 'بکاپ معیوب')}",
            status_code=303,
        )
