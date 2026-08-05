"""Bot-user management pages (platform admin)."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BotUser, Plan


def _q(msg: str) -> str:
    return quote(str(msg), safe="")


def _redirect_user(user_id: int, *, ok: str | None = None, err: str | None = None):
    if err:
        return RedirectResponse(
            f"/users/{user_id}/edit?err={_q(err)}", status_code=303
        )
    return RedirectResponse(
        f"/users/{user_id}/edit?ok={_q(ok or 'ذخیره شد')}", status_code=303
    )


def register_user_pages(app, *, render, require_admin, get_db) -> None:
    @app.get("/users/{user_id}/edit", response_class=HTMLResponse)
    async def user_edit_page(
        user_id: int,
        request: Request,
        staff: dict = Depends(require_admin),
        session: AsyncSession = Depends(get_db),
    ):
        from app.services.bot_user_admin import list_service_snapshots, list_wallet_txs
        from app.services.formatting import format_toman

        user = await session.get(BotUser, int(user_id))
        if not user:
            return RedirectResponse(f"/users?err={_q('کاربر یافت نشد')}", status_code=303)

        snaps = await list_service_snapshots(session, int(user_id))
        wallet_txs = await list_wallet_txs(session, int(user_id), limit=20)
        plans = list(
            (
                await session.execute(
                    select(Plan)
                    .where(Plan.is_active.is_(True), Plan.owner_reseller_id.is_(None))
                    .order_by(Plan.id.desc())
                    .limit(80)
                )
            ).scalars().all()
        )
        return render(
            request,
            "user_edit.html",
            {
                "staff": staff,
                "user": user,
                "services": snaps,
                "wallet_txs": wallet_txs,
                "plans": plans,
                "format_toman": format_toman,
                "flash_ok": request.query_params.get("ok"),
                "flash_err": request.query_params.get("err"),
            },
        )

    @app.post("/users/{user_id}/wallet-credit")
    async def user_wallet_credit(
        user_id: int,
        request: Request,
        staff: dict = Depends(require_admin),
        session: AsyncSession = Depends(get_db),
    ):
        from app.services.bot_user_admin import admin_credit_user_wallet
        from app.services.notifications import actor_label_from_staff

        user = await session.get(BotUser, int(user_id))
        if not user:
            return RedirectResponse(f"/users?err={_q('کاربر یافت نشد')}", status_code=303)
        form = await request.form()
        raw = str(form.get("amount") or "").strip().replace(",", "")
        note = str(form.get("note") or "").strip()
        try:
            amount = int(float(raw))
        except (TypeError, ValueError):
            return _redirect_user(user_id, err="مبلغ نامعتبر است")
        try:
            await admin_credit_user_wallet(
                session,
                user,
                amount,
                actor=actor_label_from_staff(staff),
                note=note or None,
            )
        except ValueError as e:
            return _redirect_user(user_id, err=str(e))
        return _redirect_user(user_id, ok=f"کیف پول {amount:,} تومان شارژ شد")

    @app.post("/users/{user_id}/services/{service_id}/renew")
    async def user_service_renew(
        user_id: int,
        service_id: int,
        request: Request,
        staff: dict = Depends(require_admin),
        session: AsyncSession = Depends(get_db),
    ):
        from app.services.bot_user_admin import admin_renew_service, get_owned_service

        form = await request.form()
        try:
            svc = await get_owned_service(
                session, bot_user_id=user_id, service_id=service_id
            )
        except ValueError as e:
            return _redirect_user(user_id, err=str(e))

        plan = None
        plan_raw = str(form.get("plan_id") or "").strip()
        if plan_raw.isdigit():
            plan = await session.get(Plan, int(plan_raw))
            if plan is None or not plan.is_active:
                return _redirect_user(user_id, err="پلن یافت نشد")

        days = None
        gb = None
        days_raw = str(form.get("days") or "").strip()
        gb_raw = str(form.get("data_limit_gb") or "").strip().replace(",", ".")
        if days_raw:
            try:
                days = int(days_raw)
            except ValueError:
                return _redirect_user(user_id, err="روز نامعتبر است")
        if gb_raw:
            try:
                gb = float(gb_raw)
            except ValueError:
                return _redirect_user(user_id, err="حجم نامعتبر است")
        reset = bool(form.get("reset_traffic"))

        if plan is None and days is None and gb is None:
            # Default: renew from attached plan if any
            if svc.plan_id:
                plan = await session.get(Plan, int(svc.plan_id))
            if plan is None:
                return _redirect_user(
                    user_id, err="پلن یا مقادیر روز/حجم را مشخص کنید"
                )

        try:
            await admin_renew_service(
                session,
                svc,
                days=days,
                data_limit_gb=gb,
                plan=plan,
                reset_traffic=reset if plan is None else True,
            )
        except ValueError as e:
            return _redirect_user(user_id, err=str(e))
        except Exception as e:
            return _redirect_user(user_id, err=f"تمدید ناموفق: {e}")
        return _redirect_user(user_id, ok=f"سرویس #{service_id} تمدید شد")

    @app.post("/users/{user_id}/services/{service_id}/extend")
    async def user_service_extend(
        user_id: int,
        service_id: int,
        request: Request,
        staff: dict = Depends(require_admin),
        session: AsyncSession = Depends(get_db),
    ):
        from app.services.bot_user_admin import admin_extend_service, get_owned_service

        form = await request.form()
        try:
            svc = await get_owned_service(
                session, bot_user_id=user_id, service_id=service_id
            )
        except ValueError as e:
            return _redirect_user(user_id, err=str(e))
        days_raw = str(form.get("extra_days") or "0").strip() or "0"
        gb_raw = str(form.get("extra_gb") or "0").strip().replace(",", ".") or "0"
        try:
            extra_days = int(days_raw)
            extra_gb = float(gb_raw)
        except ValueError:
            return _redirect_user(user_id, err="مقادیر افزایش نامعتبر است")
        try:
            await admin_extend_service(
                session, svc, extra_days=extra_days, extra_gb=extra_gb
            )
        except ValueError as e:
            return _redirect_user(user_id, err=str(e))
        except Exception as e:
            return _redirect_user(user_id, err=f"افزایش ناموفق: {e}")
        return _redirect_user(user_id, ok=f"سرویس #{service_id} افزایش یافت")

    @app.get("/users/{user_id}/services/{service_id}/link")
    async def user_service_link(
        user_id: int,
        service_id: int,
        staff: dict = Depends(require_admin),
        session: AsyncSession = Depends(get_db),
    ):
        from fastapi.responses import JSONResponse

        from app.services.bot_user_admin import get_owned_service, service_snapshot

        try:
            svc = await get_owned_service(
                session, bot_user_id=user_id, service_id=service_id
            )
            snap = await service_snapshot(session, svc)
            await session.commit()
        except ValueError as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=404)
        url = snap.subscription_url
        if not url:
            return JSONResponse({"ok": False, "error": "لینک موجود نیست"}, status_code=404)
        return JSONResponse(
            {
                "ok": True,
                "url": url,
                "service_id": service_id,
                "username": (snap.pg or {}).get("username") or svc.pg_username,
            }
        )
