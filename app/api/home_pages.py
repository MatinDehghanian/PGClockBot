"""Top-level overall dashboard (outside Bot / PasarGuard menus)."""

from __future__ import annotations

import asyncio
import logging

from fastapi import Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BotUser, Order, Payment, PaymentStatus, Plan, Ticket, UserService
from app.services.host_metrics import host_metrics
from app.services.home_overview import _tone_class, build_home_overview
from app.services.shop_scope import empty_shop_stats, is_platform_admin, shop_owner_id

logger = logging.getLogger(__name__)

_EMPTY_FUNNEL = {
    "shop_open": 0,
    "plan_view": 0,
    "pay_start": 0,
    "receipt": 0,
    "delivered": 0,
}
_EMPTY_ACTION_CENTER = {"items": [], "has_items": False}


async def _payg_risk_strip(session: AsyncSession) -> dict:
    """Platform-admin strip: suspended + low-balance PAYG resellers."""
    from app.db.models import ResellerProfile
    from app.services.billing import (
        BILLING_MODE_PAYG,
        get_low_balance_threshold,
        payg_available_balance,
    )

    out: dict = {
        "suspended": [],
        "low": [],
        "threshold": 0,
        "has_items": False,
    }
    try:
        threshold = await get_low_balance_threshold(session)
    except Exception:
        threshold = 0
    out["threshold"] = int(threshold or 0)
    try:
        profiles = list(
            (
                await session.execute(
                    select(ResellerProfile).where(
                        ResellerProfile.is_active.is_(True),
                        ResellerProfile.billing_mode == BILLING_MODE_PAYG,
                    )
                )
            ).scalars().all()
        )
    except Exception:
        logger.exception("payg risk: list profiles failed")
        return out

    user_ids = [int(p.user_id) for p in profiles if p.user_id]
    users = {}
    if user_ids:
        users = {
            int(u.id): u
            for u in (
                await session.execute(select(BotUser).where(BotUser.id.in_(user_ids)))
            ).scalars().all()
        }

    for profile in profiles:
        uid = int(profile.user_id)
        user = users.get(uid)
        label = (
            (user.full_name or user.username or str(uid)) if user else str(uid)
        )
        item = {"user_id": uid, "label": label, "balance": 0}
        if getattr(profile, "billing_suspended_at", None):
            try:
                item["balance"] = await payg_available_balance(session, profile)
            except Exception:
                item["balance"] = int(getattr(profile, "billing_balance", 0) or 0)
            out["suspended"].append(item)
            continue
        try:
            bal = await payg_available_balance(session, profile)
        except Exception:
            bal = int(getattr(profile, "billing_balance", 0) or 0)
        item["balance"] = bal
        if out["threshold"] > 0 and bal <= out["threshold"]:
            out["low"].append(item)

    out["suspended"].sort(key=lambda x: x["balance"])
    out["low"].sort(key=lambda x: x["balance"])
    out["has_items"] = bool(out["suspended"] or out["low"])
    return out


async def _safe_funnel(session: AsyncSession, *, reseller_id: int | None):
    from app.services.ux20 import funnel_summary

    try:
        return await funnel_summary(session, reseller_id=reseller_id, days=7)
    except Exception:
        logger.exception("funnel_summary failed reseller_id=%s", reseller_id)
        return dict(_EMPTY_FUNNEL)


async def _safe_action_center(session: AsyncSession, *, reseller_id: int | None, expire_days: int):
    from app.services.ux20 import build_action_center

    try:
        return await build_action_center(
            session, reseller_id=reseller_id, expire_days=expire_days
        )
    except Exception:
        logger.exception("action_center failed reseller_id=%s", reseller_id)
        return dict(_EMPTY_ACTION_CENTER)


async def _safe_pg_health(*, reseller_user_id: int | None = None, session: AsyncSession | None = None):
    from app.services.ux20 import check_pg_connection

    try:
        return await check_pg_connection(
            reseller_user_id=reseller_user_id, session=session
        )
    except Exception:
        logger.exception("pg_health failed reseller_user_id=%s", reseller_user_id)
        return {"ok": False, "error": "بررسی اتصال ناموفق", "version": None}

async def _reseller_shop_stats(session: AsyncSession, rid: int) -> dict[str, int]:
    """Single round-trip aggregate counts for a reseller shop dashboard."""
    users_expr = (
        select(func.count()).select_from(BotUser).where(BotUser.reseller_id == rid).scalar_subquery()
    )
    orders_expr = (
        select(func.count()).select_from(Order).where(Order.reseller_id == rid).scalar_subquery()
    )
    pending_expr = (
        select(func.count())
        .select_from(Payment)
        .join(BotUser, BotUser.id == Payment.user_id)
        .where(
            Payment.status == PaymentStatus.PENDING.value,
            Payment.receipt_file_id.is_not(None),
            BotUser.reseller_id == rid,
        )
        .scalar_subquery()
    )
    services_expr = (
        select(func.count())
        .select_from(UserService)
        .join(BotUser, BotUser.id == UserService.bot_user_id)
        .where(BotUser.reseller_id == rid)
        .scalar_subquery()
    )
    revenue_expr = (
        select(func.coalesce(func.sum(Order.amount), 0))
        .where(Order.status == "delivered", Order.reseller_id == rid)
        .scalar_subquery()
    )
    plans_expr = (
        select(func.count())
        .select_from(Plan)
        .where(Plan.is_active.is_(True), Plan.owner_reseller_id == rid)
        .scalar_subquery()
    )
    tickets_expr = (
        select(func.count())
        .select_from(Ticket)
        .join(BotUser, BotUser.id == Ticket.user_id)
        .where(Ticket.status == "open", BotUser.reseller_id == rid)
        .scalar_subquery()
    )
    row = (
        await session.execute(
            select(
                users_expr,
                orders_expr,
                pending_expr,
                services_expr,
                revenue_expr,
                plans_expr,
                tickets_expr,
            )
        )
    ).one()
    return {
        "users": int(row[0] or 0),
        "orders": int(row[1] or 0),
        "pending": int(row[2] or 0),
        "services": int(row[3] or 0),
        "revenue": int(row[4] or 0),
        "plans": int(row[5] or 0),
        "tickets": int(row[6] or 0),
    }


def register_home_pages(app, *, render, require_admin, require_staff, get_db):
    @app.get("/home", response_class=HTMLResponse)
    async def home_dashboard(
        request: Request,
        staff: dict = Depends(require_staff),
        session: AsyncSession = Depends(get_db),
    ):
        # Platform admin: server + both panels.
        if is_platform_admin(staff):
            overview = await build_home_overview(session)
            update = None
            try:
                from app.services.updates import check_github_update

                update = await check_github_update(force=False)
            except Exception:
                update = None
            from app.api.panel_tickets_pages import panel_ticket_dashboard_alert

            ticket_alert = await panel_ticket_dashboard_alert(
                session,
                staff,
                unread=getattr(request.state, "panel_tickets_unread", None),
            )
            from app.services.users import get_all_settings, on

            try:
                ui = await get_all_settings(session, reseller_id=None)
            except Exception:
                logger.exception("home get_all_settings failed")
                ui = {}
            try:
                expire_days = int(ui.get("action_center_expire_days") or 3)
            except Exception:
                expire_days = 3
            action_center = await _safe_action_center(
                session, reseller_id=None, expire_days=expire_days
            )
            pg_health = await _safe_pg_health()
            funnel_enabled = on(ui.get("funnel_tracking_enabled", "1"))
            funnel = (
                await _safe_funnel(session, reseller_id=None)
                if funnel_enabled
                else dict(_EMPTY_FUNNEL)
            )
            try:
                payg_risk = await _payg_risk_strip(session)
            except Exception:
                logger.exception("payg risk strip failed")
                payg_risk = {"suspended": [], "low": [], "threshold": 0, "has_items": False}
            return render(
                request,
                "home.html",
                {
                    "staff": staff,
                    "overview": overview,
                    "update": update,
                    "ticket_alert": ticket_alert,
                    "action_center": action_center,
                    "pg_health": pg_health,
                    "shop_maintenance": on(ui.get("shop_maintenance_enabled")),
                    "funnel_enabled": funnel_enabled,
                    "funnel": funnel,
                    "payg_risk": payg_risk,
                },
            )

        # Reseller / sub-admin web dashboard: bot + PasarGuard summaries.
        rid = shop_owner_id(staff)
        if not rid:
            if staff.get("pg_permissions"):
                return RedirectResponse("/pg", status_code=303)
            return RedirectResponse("/security", status_code=303)

        from app.config import get_settings
        from app.db.models import ResellerProfile
        from app.services.home_overview import check_bot_connection
        from app.services.resellers import bot_needs_setup

        profile = (
            await session.execute(select(ResellerProfile).where(ResellerProfile.user_id == int(rid)))
        ).scalar_one_or_none()
        bot_setup_needed = bot_needs_setup(profile)
        stats = await _reseller_shop_stats(session, int(rid)) if not bot_setup_needed else empty_shop_stats()
        # Tenant bot only — never probe platform BOT_TOKEN (empty must stay unset).
        bot_token = ((profile.bot_token if profile else None) or "").strip()
        main_token = (get_settings().bot_token or "").strip()
        if not bot_token or (main_token and bot_token == main_token):
            bot = {
                "ok": False,
                "error": "توکن تنظیم نشده" if not bot_token else "توکن نامعتبر",
                "username": None,
                "name": None,
            }
        else:
            bot = await check_bot_connection(bot_token)

        pg_limits = None
        if staff.get("pg_admin_username"):
            from app.services.pg_overview import build_reseller_pg_overview

            ov = await build_reseller_pg_overview(staff, session=session)
            if ov.get("ready"):
                pg_limits = ov
                try:
                    from app.services.ux20 import maybe_warn_reseller_capacity

                    await maybe_warn_reseller_capacity(session, profile, pg_limits)
                except Exception:
                    pass

        from app.api.panel_tickets_pages import panel_ticket_dashboard_alert

        ticket_alert = await panel_ticket_dashboard_alert(
            session,
            staff,
            unread=getattr(request.state, "panel_tickets_unread", None),
        )
        billing_card = None
        if profile is not None:
            from app.services.billing import is_billing_enabled, is_payg
            from app.services.formatting import format_toman

            if is_payg(profile) and await is_billing_enabled(session):
                from app.services.billing import ensure_payg_shop_wallet

                _u, bal = await ensure_payg_shop_wallet(session, profile)
                await session.commit()
                billing_card = {
                    "balance": int(bal),
                    "balance_fa": format_toman(int(bal)),
                    "mode": "payg",
                    "suspended": profile.billing_suspended_at is not None,
                }
        from app.services.users import get_all_settings, on
        from app.services.ux20 import capacity_should_warn

        try:
            ui = await get_all_settings(session, reseller_id=int(rid))
        except Exception:
            logger.exception("reseller home get_all_settings failed rid=%s", rid)
            ui = {}
        try:
            expire_days = int(ui.get("action_center_expire_days") or 3)
        except Exception:
            expire_days = 3
        action_center = await _safe_action_center(
            session, reseller_id=int(rid), expire_days=expire_days
        )
        pg_health = await _safe_pg_health(
            reseller_user_id=int(rid) if staff.get("pg_admin_username") else None,
            session=session if staff.get("pg_admin_username") else None,
        )
        shop_maintenance = on(ui.get("shop_maintenance_enabled"))
        funnel_enabled = on(ui.get("funnel_tracking_enabled", "1"))
        funnel = (
            await _safe_funnel(session, reseller_id=int(rid))
            if funnel_enabled
            else dict(_EMPTY_FUNNEL)
        )
        capacity_warn = False
        try:
            thr = float(ui.get("capacity_warn_pct") or 80)
        except Exception:
            thr = 80.0
        if pg_limits:
            try:
                capacity_warn = capacity_should_warn(
                    [pg_limits.get("users"), pg_limits.get("traffic")], thr
                )
            except Exception:
                capacity_warn = False
        return render(
            request,
            "reseller_home.html",
            {
                "staff": staff,
                "stats": stats,
                "pg_limits": pg_limits,
                "bot_setup_needed": bot_setup_needed,
                "bot": bot,
                "ticket_alert": ticket_alert,
                "billing_card": billing_card,
                "action_center": action_center,
                "pg_health": pg_health,
                "shop_maintenance": shop_maintenance,
                "capacity_warn": capacity_warn,
                "funnel_enabled": funnel_enabled,
                "funnel": funnel,
            },
        )

    @app.get("/home/metrics")
    async def home_metrics_json(staff: dict = Depends(require_admin)):
        # Reuse prior CPU sample when polling (wait_cpu=0); sample off the event loop.
        metrics = await asyncio.to_thread(host_metrics, wait_cpu=0.0)
        if metrics.get("cpu_percent") is None:
            metrics = await asyncio.to_thread(host_metrics, wait_cpu=0.12)
        cpu = metrics.get("cpu_percent")
        mem_pct = metrics.get("memory_percent")
        return JSONResponse(
            {
                "cpu_percent": cpu,
                "memory_percent": mem_pct,
                "memory_used_text": metrics.get("memory_used_text"),
                "memory_total_text": metrics.get("memory_total_text"),
                "memory_ratio_text": metrics.get("memory_ratio_text"),
                "cpu_tone": _tone_class(cpu if isinstance(cpu, (int, float)) else None),
                "mem_tone": _tone_class(mem_pct if isinstance(mem_pct, (int, float)) else None),
            }
        )
