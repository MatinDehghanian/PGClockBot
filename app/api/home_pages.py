"""Top-level overall dashboard (outside Bot / PasarGuard menus)."""

from __future__ import annotations

import asyncio
import logging

from fastapi import Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BotUser, Order, Payment, PaymentStatus, Plan, Ticket, UserService
from app.services.host_gauges import gauges_json, local_host_gauges
from app.services.home_overview import build_home_overview
from app.services.shop_scope import empty_shop_stats, is_platform_admin, shop_owner_id

logger = logging.getLogger(__name__)

_EMPTY_FUNNEL = {
    "shop_open": 0,
    "plan_view": 0,
    "pay_start": 0,
    "receipt": 0,
    "delivered": 0,
}
# Probe not run — templates must show «—» / neutral, never fake «قطع».
_UNCHECKED_CONN = {"ok": None, "error": None, "version": None, "unchecked": True}


def _unchecked_overview():
    from app.services.home_overview import empty_home_overview

    ov = empty_home_overview()
    ov["bot"] = {
        "ok": None,
        "error": None,
        "username": None,
        "name": None,
        "unchecked": True,
    }
    ov["nodes"] = {
        "ok": None,
        "error": None,
        "nodes": [],
        "total": 0,
        "connected": 0,
        "warn": 0,
        "error_count": 0,
        "overall": "neutral",
        "unchecked": True,
    }
    ov["pg_summary"] = {
        "ok": None,
        "error": None,
        "admins": 0,
        "groups": 0,
        "hosts": 0,
        "nodes": 0,
        "users": None,
        "version": None,
        "unchecked": True,
    }
    return ov


_EMPTY_ACTION = {
    "pending": 0,
    "tickets": 0,
    "failures": 0,
    "expiring": 0,
    "entries": [],
    "has_items": False,
}


async def _safe_funnel(session: AsyncSession, *, reseller_id: int | None):
    from app.services.db_safe import rollback_quiet
    from app.services.ux20 import funnel_summary

    try:
        return await funnel_summary(session, reseller_id=reseller_id, days=7)
    except Exception:
        logger.exception("funnel_summary failed reseller_id=%s", reseller_id)
        await rollback_quiet(session)
        return dict(_EMPTY_FUNNEL)


async def _safe_periods(session: AsyncSession, *, reseller_id: int | None):
    from app.services.db_safe import rollback_quiet
    from app.services.home_overview import empty_period_stats, shop_period_stats

    try:
        return await shop_period_stats(session, reseller_id=reseller_id)
    except Exception:
        logger.exception("shop_period_stats failed reseller_id=%s", reseller_id)
        await rollback_quiet(session)
        return empty_period_stats()


async def _safe_action_center(session: AsyncSession, *, reseller_id: int | None, expire_days: int = 3):
    from app.services.db_safe import rollback_quiet
    from app.services.ux20 import build_action_center

    try:
        return await build_action_center(
            session, reseller_id=reseller_id, expire_days=expire_days
        )
    except Exception:
        logger.exception("action_center failed reseller_id=%s", reseller_id)
        await rollback_quiet(session)
        return dict(_EMPTY_ACTION)


async def _safe_pg_health(*, reseller_user_id: int | None = None, session: AsyncSession | None = None):
    from app.services.db_safe import rollback_quiet
    from app.services.ux20 import check_pg_connection

    try:
        return await check_pg_connection(
            reseller_user_id=reseller_user_id, session=session
        )
    except Exception:
        logger.exception("pg_health failed reseller_user_id=%s", reseller_user_id)
        await rollback_quiet(session)
        return {"ok": False, "error": "بررسی اتصال ناموفق", "version": None}


async def _staff_wallet_card(session: AsyncSession, staff: dict) -> dict | None:
    """Shop wallet for the signed-in staff BotUser, if one is linked."""
    from app.db.models import BotUser, OrgPrincipal
    from app.services.formatting import format_toman

    uid = staff.get("bot_user_id")
    if not uid:
        pid = staff.get("org_principal_id")
        if pid:
            try:
                principal = await session.get(OrgPrincipal, int(pid))
            except Exception:
                principal = None
            if principal is not None and principal.bot_user_id:
                uid = principal.bot_user_id
    if not uid and is_platform_admin(staff):
        from app.config import get_settings

        raw_ids = getattr(get_settings(), "admin_ids", None) or ()
        tids = []
        for x in raw_ids:
            try:
                tids.append(int(x))
            except (TypeError, ValueError):
                continue
        if tids:
            row = (
                await session.execute(select(BotUser).where(BotUser.telegram_id == int(tids[0])))
            ).scalar_one_or_none()
            if row is not None:
                uid = row.id
    if not uid:
        return None
    user = await session.get(BotUser, int(uid))
    if user is None:
        return None
    bal = int(user.wallet_balance or 0)
    return {"balance": bal, "balance_fa": format_toman(bal)}


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
    @app.get("/inbox", response_class=HTMLResponse)
    async def inbox_page(
        request: Request,
        staff: dict = Depends(require_staff),
        session: AsyncSession = Depends(get_db),
    ):
        from app.services.panel_inbox import build_inbox_context

        ctx = await build_inbox_context(session, request, staff)
        return render(request, "inbox.html", ctx)

    @app.get("/home", response_class=HTMLResponse)
    async def home_dashboard(
        request: Request,
        staff: dict = Depends(require_staff),
        session: AsyncSession = Depends(get_db),
    ):
        """Build context fail-soft; render outside so template bugs stay diagnosable 500s.

        Never invent «قطع» for Bot/PG/Nodes when data load failed — use unchecked
        + dashboard_degraded banner instead (false-disconnected regression).
        """
        from app.services.db_safe import rollback_quiet
        from app.services.identity_chrome import resolve_staff_home

        dest_kind, dest_target = resolve_staff_home(staff)
        if dest_kind == "redirect":
            return RedirectResponse(dest_target, status_code=303)

        try:
            result = await _home_dashboard_context(request, staff, session)
        except Exception:
            logger.exception("home_dashboard data build failed; serving degraded shell")
            await rollback_quiet(session)
            result = _degraded_home_shell(staff)
        if isinstance(result, RedirectResponse):
            return result
        template, ctx = result
        # Render is intentionally outside the data try/except: Jinja/KeyError must
        # hit the global handler with a ref=, not paint fake connection failures.
        return render(request, template, ctx)

    def _degraded_home_shell(staff: dict):
        from app.services.home_overview import empty_period_stats
        from app.services.identity_chrome import resolve_staff_home

        dest_kind, dest_target = resolve_staff_home(staff)
        if dest_kind == "redirect":
            return RedirectResponse(dest_target, status_code=303)

        periods = empty_period_stats()
        action = dict(_EMPTY_ACTION)
        if dest_target == "home.html" or is_platform_admin(staff):
            return (
                "home.html",
                {
                    "staff": staff,
                    "overview": _unchecked_overview(),
                    "pg_health": dict(_UNCHECKED_CONN),
                    "funnel_enabled": False,
                    "funnel": dict(_EMPTY_FUNNEL),
                    "periods": periods,
                    "action_center": action,
                    "dashboard_degraded": True,
                    "pg_limits": None,
                    "wallet_card": None,
                },
            )
        return (
            "reseller_home.html",
            {
                "staff": staff,
                "stats": empty_shop_stats(),
                "pg_limits": None,
                "bot_setup_needed": False,
                "bot": {
                    "ok": None,
                    "error": None,
                    "username": None,
                    "name": None,
                    "unchecked": True,
                },
                "billing_card": None,
                "pg_health": dict(_UNCHECKED_CONN),
                "funnel_enabled": False,
                "funnel": dict(_EMPTY_FUNNEL),
                "periods": periods,
                "action_center": action,
                "dashboard_degraded": True,
            },
        )

    async def _home_dashboard_context(request, staff, session):
        # Platform admin: server + both panels.
        if is_platform_admin(staff):
            from app.services.db_safe import recover_session, rollback_quiet
            from app.services.home_overview import empty_home_overview

            await recover_session(session)
            show_pg_nodes = "pg_nodes" in (staff.get("pg_permissions") or [])
            try:
                overview = await build_home_overview(session, include_nodes=show_pg_nodes)
            except Exception:
                logger.exception("build_home_overview failed")
                await rollback_quiet(session)
                overview = empty_home_overview()
            from app.services.users import get_all_settings, on

            try:
                ui = await get_all_settings(session, reseller_id=None)
            except Exception:
                logger.exception("home get_all_settings failed")
                await rollback_quiet(session)
                ui = {}
            pg_health = await _safe_pg_health()
            funnel_enabled = on(ui.get("funnel_tracking_enabled", "1"))
            funnel = (
                await _safe_funnel(session, reseller_id=None)
                if funnel_enabled
                else dict(_EMPTY_FUNNEL)
            )
            try:
                expire_days = int(ui.get("action_center_expire_days") or 3)
            except (TypeError, ValueError):
                expire_days = 3
            periods = await _safe_periods(session, reseller_id=None)
            action_center = await _safe_action_center(
                session, reseller_id=None, expire_days=expire_days
            )
            pg_limits = None
            wallet_card = None
            if staff.get("pg_is_owner") is False:
                from app.services.pg_overview import build_reseller_pg_overview

                try:
                    ov = await build_reseller_pg_overview(staff, session=session)
                    if ov.get("ready"):
                        pg_limits = ov
                except Exception:
                    logger.exception("hybrid owner home pg limits failed")
                    await rollback_quiet(session)
                    pg_limits = None
                try:
                    wallet_card = await _staff_wallet_card(session, staff)
                except Exception:
                    logger.exception("hybrid owner home wallet failed")
                    await rollback_quiet(session)
                    wallet_card = None
            return (
                "home.html",
                {
                    "staff": staff,
                    "overview": overview,
                    "pg_health": pg_health,
                    "funnel_enabled": funnel_enabled,
                    "funnel": funnel,
                    "periods": periods,
                    "action_center": action_center,
                    "dashboard_degraded": False,
                    "pg_limits": pg_limits,
                    "wallet_card": wallet_card,
                    "show_pg_nodes": show_pg_nodes,
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
        from app.services.db_safe import recover_session, rollback_quiet
        from app.services.home_overview import check_bot_connection
        from app.services.resellers import bot_needs_setup

        await recover_session(session)

        try:
            profile = (
                await session.execute(
                    select(ResellerProfile).where(ResellerProfile.user_id == int(rid))
                )
            ).scalar_one_or_none()
        except Exception:
            logger.exception("reseller home profile load failed rid=%s", rid)
            await rollback_quiet(session)
            profile = None

        bot_setup_needed = bot_needs_setup(profile)
        try:
            stats = (
                await _reseller_shop_stats(session, int(rid))
                if not bot_setup_needed
                else empty_shop_stats()
            )
        except Exception:
            logger.exception("reseller home stats failed rid=%s", rid)
            await rollback_quiet(session)
            stats = empty_shop_stats()
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
            try:
                bot = await check_bot_connection(bot_token)
            except Exception:
                logger.exception("reseller home bot probe failed rid=%s", rid)
                bot = {
                    "ok": False,
                    "error": "بررسی ربات ناموفق",
                    "username": None,
                    "name": None,
                }

        pg_limits = None
        if staff.get("pg_admin_username"):
            from app.services.pg_overview import build_reseller_pg_overview

            try:
                ov = await build_reseller_pg_overview(staff, session=session)
                if ov.get("ready"):
                    pg_limits = ov
                    try:
                        from app.services.ux20 import maybe_warn_reseller_capacity

                        await maybe_warn_reseller_capacity(session, profile, pg_limits)
                    except Exception:
                        await rollback_quiet(session)
            except Exception:
                logger.exception("reseller home pg overview failed rid=%s", rid)
                await rollback_quiet(session)
                pg_limits = None

        billing_card = None
        if profile is not None:
            from app.services.billing import is_billing_enabled, is_payg
            from app.services.formatting import format_toman

            try:
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
            except Exception:
                logger.exception("reseller home billing card failed rid=%s", rid)
                await rollback_quiet(session)
                billing_card = None
        from app.services.users import get_all_settings, on

        try:
            ui = await get_all_settings(session, reseller_id=int(rid))
        except Exception:
            logger.exception("reseller home get_all_settings failed rid=%s", rid)
            await rollback_quiet(session)
            ui = {}
        pg_health = await _safe_pg_health(
            reseller_user_id=int(rid) if staff.get("pg_admin_username") else None,
            session=session if staff.get("pg_admin_username") else None,
        )
        funnel_enabled = on(ui.get("funnel_tracking_enabled", "1"))
        funnel = (
            await _safe_funnel(session, reseller_id=int(rid))
            if funnel_enabled
            else dict(_EMPTY_FUNNEL)
        )
        try:
            expire_days = int(ui.get("action_center_expire_days") or 3)
        except (TypeError, ValueError):
            expire_days = 3
        periods = await _safe_periods(session, reseller_id=int(rid))
        action_center = await _safe_action_center(
            session, reseller_id=int(rid), expire_days=expire_days
        )
        return (
            "reseller_home.html",
            {
                "staff": staff,
                "stats": stats,
                "pg_limits": pg_limits,
                "bot_setup_needed": bot_setup_needed,
                "bot": bot,
                "billing_card": billing_card,
                "pg_health": pg_health,
                "funnel_enabled": funnel_enabled,
                "funnel": funnel,
                "periods": periods,
                "action_center": action_center,
                "dashboard_degraded": False,
            },
        )

    @app.get("/home/metrics")
    async def home_metrics_json(staff: dict = Depends(require_admin)):
        """Kept for older clients; gauges now live on bot overview (/dashboard/metrics)."""
        host = await asyncio.to_thread(local_host_gauges, wait_cpu=0.0)
        if host.get("cpu_percent") is None:
            host = await asyncio.to_thread(local_host_gauges, wait_cpu=0.12)
        return JSONResponse(gauges_json(host))
