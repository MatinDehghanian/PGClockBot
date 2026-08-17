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

_EMPTY_WALLET = {
    "kind": "none",
    "title": "کیف پول",
    "balance": None,
    "balance_fa": None,
    "wallet_pay": False,
    "pending": 0,
    "suspended": False,
    "href": "/finance",
    "hint": "",
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


async def _safe_wallet_card(
    session: AsyncSession,
    *,
    staff: dict,
    profile=None,
    billing_card: dict | None = None,
    ui: dict | None = None,
    reseller_id: int | None = None,
) -> dict:
    from app.services.formatting import format_toman
    from app.services.users import on

    ui = ui or {}
    wallet_pay = on(ui.get("pay_wallet_enabled", "1"))
    try:
        if is_platform_admin(staff):
            pending = int(
                (
                    await session.execute(
                        select(func.count())
                        .select_from(Payment)
                        .where(
                            Payment.status == PaymentStatus.PENDING.value,
                            Payment.is_wallet_topup.is_(True),
                            Payment.receipt_file_id.is_not(None),
                        )
                    )
                ).scalar()
                or 0
            )
            return {
                "kind": "platform",
                "title": "کیف پول فروشگاه",
                "balance": None,
                "balance_fa": None,
                "wallet_pay": wallet_pay,
                "pending": pending,
                "suspended": False,
                "href": "/finance?tab=payments",
                "hint": "پرداخت با کیف پول برای مشتری "
                + ("فعال است" if wallet_pay else "خاموش است"),
            }
        if billing_card:
            return {
                "kind": "payg",
                "title": "کیف پول فروشگاهی",
                "balance": billing_card.get("balance"),
                "balance_fa": billing_card.get("balance_fa"),
                "wallet_pay": True,
                "pending": 0,
                "suspended": bool(billing_card.get("suspended")),
                "href": "/shop-settings",
                "hint": "مصرف ترافیک از همین موجودی کسر می‌شود",
            }
        bal = 0
        if reseller_id:
            u = await session.get(BotUser, int(reseller_id))
            if u is not None:
                bal = int(getattr(u, "wallet_balance", 0) or 0)
        return {
            "kind": "shop",
            "title": "کیف پول",
            "balance": bal,
            "balance_fa": format_toman(bal),
            "wallet_pay": wallet_pay,
            "pending": 0,
            "suspended": False,
            "href": "/shop-settings",
            "hint": "موجودی فروشگاه شما",
        }
    except Exception:
        logger.exception("wallet card failed")
        from app.services.db_safe import rollback_quiet

        await rollback_quiet(session)
        return dict(_EMPTY_WALLET)


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
        from app.services.home_overview import build_home_pulse

        pulse = build_home_pulse(periods=periods, action_center=action)
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
                    "wallet_card": dict(_EMPTY_WALLET),
                    "pulse": pulse,
                    "dashboard_degraded": True,
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
                "wallet_card": dict(_EMPTY_WALLET),
                "pulse": pulse,
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
            from app.services.home_overview import (
                build_home_pulse,
                build_home_shell,
                empty_home_overview,
            )

            await recover_session(session)
            try:
                overview = await build_home_shell(session)
            except Exception:
                logger.exception("build_home_shell failed")
                await rollback_quiet(session)
                overview = empty_home_overview()
                overview["bot"] = {
                    "ok": None,
                    "error": None,
                    "username": None,
                    "name": None,
                    "unchecked": True,
                }
                overview["nodes"] = {
                    **(overview.get("nodes") or {}),
                    "unchecked": True,
                    "overall": "neutral",
                }
            from app.services.users import get_all_settings, on

            try:
                ui = await get_all_settings(session, reseller_id=None)
            except Exception:
                logger.exception("home get_all_settings failed")
                await rollback_quiet(session)
                ui = {}
            funnel_enabled = on(ui.get("funnel_tracking_enabled", "1"))
            try:
                expire_days = int(ui.get("action_center_expire_days") or 3)
            except (TypeError, ValueError):
                expire_days = 3
            periods = await _safe_periods(session, reseller_id=None)
            action_center = await _safe_action_center(
                session, reseller_id=None, expire_days=expire_days
            )
            wallet_card = await _safe_wallet_card(session, staff=staff, ui=ui)
            funnel = (
                await _safe_funnel(session, reseller_id=None)
                if funnel_enabled
                else dict(_EMPTY_FUNNEL)
            )
            pulse = build_home_pulse(periods=periods, action_center=action_center)
            return (
                "home.html",
                {
                    "staff": staff,
                    "overview": overview,
                    "pg_health": dict(_UNCHECKED_CONN),
                    "funnel_enabled": funnel_enabled,
                    "funnel": funnel,
                    "periods": periods,
                    "action_center": action_center,
                    "wallet_card": wallet_card,
                    "pulse": pulse,
                    "dashboard_degraded": False,
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
        from app.services.home_overview import build_home_pulse
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
        bot = {
            "ok": None,
            "error": None,
            "username": None,
            "name": None,
            "unchecked": True,
        }
        bot_token = ((profile.bot_token if profile else None) or "").strip()
        main_token = (get_settings().bot_token or "").strip()
        if not bot_token or (main_token and bot_token == main_token):
            bot = {
                "ok": False,
                "error": "توکن تنظیم نشده" if not bot_token else "توکن نامعتبر",
                "username": None,
                "name": None,
            }

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
        funnel_enabled = on(ui.get("funnel_tracking_enabled", "1"))
        try:
            expire_days = int(ui.get("action_center_expire_days") or 3)
        except (TypeError, ValueError):
            expire_days = 3
        async def _stats_job():
            if bot_setup_needed:
                return empty_shop_stats()
            try:
                return await _reseller_shop_stats(session, int(rid))
            except Exception:
                logger.exception("reseller home stats failed rid=%s", rid)
                from app.services.db_safe import rollback_quiet as _rb

                await _rb(session)
                return empty_shop_stats()

        stats = await _stats_job()
        periods = await _safe_periods(session, reseller_id=int(rid))
        action_center = await _safe_action_center(
            session, reseller_id=int(rid), expire_days=expire_days
        )
        wallet_card = await _safe_wallet_card(
            session,
            staff=staff,
            profile=profile,
            billing_card=billing_card,
            ui=ui,
            reseller_id=int(rid),
        )
        funnel = (
            await _safe_funnel(session, reseller_id=int(rid))
            if funnel_enabled
            else dict(_EMPTY_FUNNEL)
        )
        pulse = build_home_pulse(periods=periods, action_center=action_center)
        return (
            "reseller_home.html",
            {
                "staff": staff,
                "stats": stats,
                "pg_limits": None,
                "bot_setup_needed": bot_setup_needed,
                "bot": bot,
                "billing_card": billing_card,
                "wallet_card": wallet_card,
                "pulse": pulse,
                "pg_health": dict(_UNCHECKED_CONN),
                "funnel_enabled": funnel_enabled,
                "funnel": funnel,
                "periods": periods,
                "action_center": action_center,
                "dashboard_degraded": False,
            },
        )

    @app.get("/home/live")
    async def home_live(
        staff: dict = Depends(require_staff),
        session: AsyncSession = Depends(get_db),
    ):
        """Hydrate connection tiles after HTML — never block first paint."""
        from app.config import get_settings
        from app.services.home_overview import check_bot_connection, pg_home_bundle
        from app.services.setup_wizard import current_setup_values

        payload: dict = {
            "bot": dict(_UNCHECKED_CONN),
            "pg_health": dict(_UNCHECKED_CONN),
            "nodes": {
                "ok": None,
                "error": None,
                "total": 0,
                "connected": 0,
                "overall": "neutral",
                "unchecked": True,
            },
            "pg_limits": None,
        }
        if is_platform_admin(staff):
            token = current_setup_values().get("BOT_TOKEN")
            bot, pg_health, pg_pair = await asyncio.gather(
                check_bot_connection(token),
                _safe_pg_health(),
                pg_home_bundle(),
                return_exceptions=True,
            )
            if isinstance(bot, dict):
                payload["bot"] = bot
            elif isinstance(bot, Exception):
                payload["bot"] = {"ok": False, "error": "بررسی ربات ناموفق"}
            if isinstance(pg_health, dict):
                payload["pg_health"] = pg_health
            if isinstance(pg_pair, tuple) and len(pg_pair) == 2:
                _summary, nodes = pg_pair
                if isinstance(nodes, dict):
                    payload["nodes"] = nodes
            return JSONResponse(payload)

        rid = shop_owner_id(staff)
        from app.db.models import ResellerProfile

        profile = None
        if rid:
            profile = (
                await session.execute(
                    select(ResellerProfile).where(ResellerProfile.user_id == int(rid))
                )
            ).scalar_one_or_none()
        bot_token = ((profile.bot_token if profile else None) or "").strip()
        main_token = (get_settings().bot_token or "").strip()
        if not bot_token or (main_token and bot_token == main_token):
            payload["bot"] = {
                "ok": False,
                "error": "توکن تنظیم نشده" if not bot_token else "توکن نامعتبر",
                "username": None,
                "name": None,
            }
        else:
            try:
                bot_res = await check_bot_connection(bot_token)
                if isinstance(bot_res, dict):
                    payload["bot"] = bot_res
            except Exception:
                payload["bot"] = {"ok": False, "error": "بررسی ربات ناموفق"}
        if rid and staff.get("pg_admin_username"):
            payload["pg_health"] = await _safe_pg_health(
                reseller_user_id=int(rid), session=session
            )
            try:
                from app.services.pg_overview import build_reseller_pg_overview

                result = await build_reseller_pg_overview(staff, session=session)
                if isinstance(result, dict) and result.get("ready"):
                    payload["pg_limits"] = {
                        "ready": True,
                        "username": result.get("username"),
                        "status_label": result.get("status_label"),
                        "status_badge": result.get("status_badge"),
                        "lifetime_text": result.get("lifetime_text"),
                        "users": result.get("users"),
                        "traffic": result.get("traffic"),
                    }
            except Exception:
                logger.exception("home live pg limits failed")
        return JSONResponse(payload)

    @app.get("/home/metrics")
    async def home_metrics_json(staff: dict = Depends(require_admin)):
        """Kept for older clients; gauges now live on bot overview (/dashboard/metrics)."""
        host = await asyncio.to_thread(local_host_gauges, wait_cpu=0.0)
        if host.get("cpu_percent") is None:
            host = await asyncio.to_thread(local_host_gauges, wait_cpu=0.12)
        return JSONResponse(gauges_json(host))
