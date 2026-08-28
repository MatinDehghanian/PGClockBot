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


async def _parallel_home_ops(*, reseller_id: int | None, funnel_enabled: bool, expire_days: int):
    """Run funnel / periods / action-center on isolated sessions (safe gather)."""
    from app.db.session import SessionLocal
    from app.services.home_overview import empty_period_stats

    async def _funnel():
        if not funnel_enabled:
            return dict(_EMPTY_FUNNEL)
        async with SessionLocal() as s:
            return await _safe_funnel(s, reseller_id=reseller_id)

    async def _periods():
        async with SessionLocal() as s:
            return await _safe_periods(s, reseller_id=reseller_id)

    async def _action():
        async with SessionLocal() as s:
            return await _safe_action_center(
                s, reseller_id=reseller_id, expire_days=expire_days
            )

    funnel, periods, action = await asyncio.gather(_funnel(), _periods(), _action())
    if not isinstance(periods, dict):
        periods = empty_period_stats()
    if not isinstance(action, dict):
        action = dict(_EMPTY_ACTION)
    if not isinstance(funnel, dict):
        funnel = dict(_EMPTY_FUNNEL)
    return funnel, periods, action


async def _safe_pg_health(*, reseller_user_id: int | None = None, session: AsyncSession | None = None):
    """Display-only PG reachability — never used for allow/deny."""
    from app.services.db_safe import rollback_quiet
    from app.services.panel_display_timeout import display_await
    from app.services.ux20 import check_pg_connection

    async def _probe():
        try:
            return await check_pg_connection(
                reseller_user_id=reseller_user_id, session=session
            )
        except Exception:
            logger.exception("pg_health failed reseller_user_id=%s", reseller_user_id)
            if session is not None:
                await rollback_quiet(session)
            # Unchecked — never paint a false «قطع» for a probe failure.
            return dict(_UNCHECKED_CONN)

    return await display_await(
        _probe(),
        fallback=dict(_UNCHECKED_CONN),
        label="pg_health",
    )


def _wants_full_widgets(request: Request) -> bool:
    """Escape hatch: ?full=1 forces classic single-response render."""
    return (request.query_params.get("full") or "").strip() == "1"


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
        from app.services.panel_timing import mark

        mark(request, "handler")
        ctx = await build_inbox_context(session, request, staff)
        mark(request, "page_data")
        return render(request, "inbox.html", ctx)

    @app.post("/inbox/dismiss")
    async def inbox_dismiss(
        request: Request,
        staff: dict = Depends(require_staff),
        session: AsyncSession = Depends(get_db),
    ):
        from urllib.parse import quote

        from app.services.inbox_dismissals import upsert_dismissal
        from app.services.panel_inbox import invalidate_inbox_sidebar_cache

        form = await request.form()
        alert_key = str(form.get("alert_key") or "").strip()
        entity_id = str(form.get("entity_id") or "").strip()
        mode = str(form.get("mode") or "").strip()
        return_to = str(form.get("return_to") or "/inbox").strip()
        if not return_to.startswith("/") or return_to.startswith("//"):
            return_to = "/inbox"
        try:
            await upsert_dismissal(
                session,
                staff=staff,
                alert_key=alert_key,
                mode=mode,
                entity_id=entity_id,
            )
        except ValueError as e:
            return RedirectResponse(
                f"{return_to}?err={quote(str(e))}",
                status_code=303,
            )
        invalidate_inbox_sidebar_cache(staff)
        return RedirectResponse(
            f"{return_to}?ok={quote('اعلان مخفی شد')}",
            status_code=303,
        )

    @app.post("/inbox/dismiss/reset")
    async def inbox_dismiss_reset(
        request: Request,
        staff: dict = Depends(require_staff),
        session: AsyncSession = Depends(get_db),
    ):
        from urllib.parse import quote

        from app.services.inbox_dismissals import clear_staff_dismissals
        from app.services.panel_inbox import invalidate_inbox_sidebar_cache

        form = await request.form()
        return_to = str(form.get("return_to") or "/inbox").strip()
        if not return_to.startswith("/") or return_to.startswith("//"):
            return_to = "/inbox"
        removed = await clear_staff_dismissals(session, staff)
        invalidate_inbox_sidebar_cache(staff)
        msg = "اعلان‌های مخفی‌شده بازنشانی شدند" if removed else "اعلان مخفی‌شده‌ای نبود"
        return RedirectResponse(
            f"{return_to}?ok={quote(msg)}",
            status_code=303,
        )

    async def _render_home_result(request: Request, result, *, as_body_fragment: bool):
        if isinstance(result, RedirectResponse):
            return result
        template, ctx = result
        ctx = dict(ctx)
        # Body fragment must never re-trigger defer (no nested fetch loop).
        ctx["widgets_deferred"] = False
        if as_body_fragment:
            partial = (
                "_home_dash_body.html"
                if template == "home.html"
                else "_reseller_home_dash_body.html"
            )
            return render(request, partial, ctx)
        return render(request, template, ctx)

    @app.get("/home", response_class=HTMLResponse)
    async def home_dashboard(
        request: Request,
        staff: dict = Depends(require_staff),
        session: AsyncSession = Depends(get_db),
    ):
        """Auth/tenant/ACL complete via require_staff before any HTML.

        Default: fast shell with unchecked display widgets, then /home/body fills in.
        ``?full=1`` keeps classic single-response behavior.
        """
        from app.services.db_safe import rollback_quiet
        from app.services.identity_chrome import resolve_staff_home
        from app.services.panel_timing import mark

        mark(request, "handler")
        dest_kind, dest_target = resolve_staff_home(staff)
        if dest_kind == "redirect":
            return RedirectResponse(dest_target, status_code=303)

        want_full = _wants_full_widgets(request)
        if not want_full:
            try:
                result = await _fast_home_shell(staff, session)
            except Exception:
                logger.exception("home fast shell failed; serving degraded shell")
                await rollback_quiet(session)
                result = _degraded_home_shell(staff)
            mark(request, "page_data")
            if isinstance(result, RedirectResponse):
                return result
            template, ctx = result
            ctx = dict(ctx)
            ctx["widgets_deferred"] = True
            ctx["widgets_body_url"] = "/home/body"
            # Intentionally not dashboard_degraded — shell is planned, not failed.
            ctx["dashboard_degraded"] = False
            return render(request, template, ctx)

        try:
            result = await _home_dashboard_context(request, staff, session)
        except Exception:
            logger.exception("home_dashboard data build failed; serving degraded shell")
            await rollback_quiet(session)
            result = _degraded_home_shell(staff)
        mark(request, "page_data")
        # Render is intentionally outside the data try/except: Jinja/KeyError must
        # hit the global handler with a ref=, not paint fake connection failures.
        if isinstance(result, RedirectResponse):
            return result
        template, ctx = result
        ctx = dict(ctx)
        ctx["widgets_deferred"] = False
        return render(request, template, ctx)

    @app.get("/home/body", response_class=HTMLResponse)
    async def home_dashboard_body(
        request: Request,
        staff: dict = Depends(require_staff),
        session: AsyncSession = Depends(get_db),
    ):
        """Widget HTML only — re-runs the same require_staff authz as /home."""
        from app.services.db_safe import rollback_quiet
        from app.services.identity_chrome import resolve_staff_home
        from app.services.panel_timing import mark

        mark(request, "handler")
        dest_kind, dest_target = resolve_staff_home(staff)
        if dest_kind == "redirect":
            return RedirectResponse(dest_target, status_code=303)

        try:
            result = await _home_dashboard_context(request, staff, session)
        except Exception:
            logger.exception("home_dashboard body build failed; serving degraded shell")
            await rollback_quiet(session)
            result = _degraded_home_shell(staff)
        mark(request, "page_data")
        return await _render_home_result(request, result, as_body_fragment=True)

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

    async def _fast_home_shell(staff, session):
        """Post-auth shell: local flags only — no Telegram/PG decorative probes."""
        from app.services.home_overview import empty_period_stats
        from app.services.identity_chrome import resolve_staff_home

        dest_kind, dest_target = resolve_staff_home(staff)
        if dest_kind == "redirect":
            return RedirectResponse(dest_target, status_code=303)

        periods = empty_period_stats()
        action = dict(_EMPTY_ACTION)
        if dest_target == "home.html" or is_platform_admin(staff):
            show_pg_nodes = "pg_nodes" in (staff.get("pg_permissions") or [])
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
                    "dashboard_degraded": False,
                    "pg_limits": None,
                    "wallet_card": None,
                    "show_pg_nodes": show_pg_nodes,
                },
            )

        rid = shop_owner_id(staff)
        if not rid:
            if staff.get("pg_permissions"):
                return RedirectResponse("/pg", status_code=303)
            return RedirectResponse("/security", status_code=303)

        from app.db.models import ResellerProfile
        from app.services.db_safe import recover_session, rollback_quiet
        from app.services.resellers import bot_needs_setup

        await recover_session(session)
        try:
            profile = (
                await session.execute(
                    select(ResellerProfile).where(ResellerProfile.user_id == int(rid))
                )
            ).scalar_one_or_none()
        except Exception:
            logger.exception("reseller home shell profile load failed rid=%s", rid)
            await rollback_quiet(session)
            profile = None

        return (
            "reseller_home.html",
            {
                "staff": staff,
                "stats": empty_shop_stats(),
                "pg_limits": None,
                "bot_setup_needed": bot_needs_setup(profile),
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
                "dashboard_degraded": False,
            },
        )

    async def _home_dashboard_context(request, staff, session):
        # Platform admin: server + both panels.
        if is_platform_admin(staff):
            from app.services.db_safe import recover_session, rollback_quiet
            from app.services.home_overview import empty_home_overview
            from app.services.panel_display_timeout import display_await

            await recover_session(session)
            show_pg_nodes = "pg_nodes" in (staff.get("pg_permissions") or [])
            try:
                overview = await display_await(
                    build_home_overview(session, include_nodes=show_pg_nodes),
                    fallback=_unchecked_overview(),
                    label="home_overview",
                )
            except Exception:
                logger.exception("build_home_overview failed")
                await rollback_quiet(session)
                overview = empty_home_overview()
            from app.services.users import get_all_settings, on

            # settings uses session; pg_health (platform) does not — safe to gather.
            try:
                ui, pg_health = await asyncio.gather(
                    get_all_settings(session, reseller_id=None),
                    _safe_pg_health(),
                )
            except Exception:
                logger.exception("home settings/health gather failed")
                await rollback_quiet(session)
                ui = {}
                pg_health = dict(_UNCHECKED_CONN)
            if not isinstance(ui, dict):
                ui = {}
            funnel_enabled = on(ui.get("funnel_tracking_enabled", "1"))
            try:
                expire_days = int(ui.get("action_center_expire_days") or 3)
            except (TypeError, ValueError):
                expire_days = 3
            funnel, periods, action_center = await _parallel_home_ops(
                reseller_id=None,
                funnel_enabled=funnel_enabled,
                expire_days=expire_days,
            )
            try:
                from app.services.inbox_dismissals import filter_action_center_for_staff

                action_center = await filter_action_center_for_staff(
                    session, staff, action_center
                )
            except Exception:
                logger.exception("home action_center dismiss filter failed")
            pg_limits = None
            wallet_card = None
            if staff.get("pg_is_owner") is False:
                from app.services.pg_overview import build_reseller_pg_overview

                try:
                    ov = await display_await(
                        build_reseller_pg_overview(staff, session=session),
                        fallback=None,
                        label="hybrid_home_pg_limits",
                    )
                    if ov and ov.get("ready"):
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
        from app.services.panel_display_timeout import display_await
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

        async def _stats_task():
            if bot_setup_needed:
                return empty_shop_stats()
            try:
                return await _reseller_shop_stats(session, int(rid))
            except Exception:
                logger.exception("reseller home stats failed rid=%s", rid)
                await rollback_quiet(session)
                return empty_shop_stats()

        async def _bot_task():
            # Tenant bot only — never probe platform BOT_TOKEN.
            bot_token = ((profile.bot_token if profile else None) or "").strip()
            main_token = (get_settings().bot_token or "").strip()
            if not bot_token or (main_token and bot_token == main_token):
                return {
                    "ok": False,
                    "error": "توکن تنظیم نشده" if not bot_token else "توکن نامعتبر",
                    "username": None,
                    "name": None,
                }
            unchecked_bot = {
                "ok": None,
                "error": None,
                "username": None,
                "name": None,
                "unchecked": True,
            }
            return await display_await(
                check_bot_connection(bot_token),
                fallback=unchecked_bot,
                label="reseller_bot_probe",
            )

        # stats uses session; bot probe does not — safe to gather.
        stats, bot = await asyncio.gather(_stats_task(), _bot_task())

        pg_limits = None
        if staff.get("pg_admin_username"):
            from app.services.pg_overview import build_reseller_pg_overview

            try:
                ov = await display_await(
                    build_reseller_pg_overview(staff, session=session),
                    fallback=None,
                    label="reseller_home_pg_overview",
                )
                if ov and ov.get("ready"):
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
        # Reseller pg_health may use session — after settings, not gathered with it.
        pg_health = await _safe_pg_health(
            reseller_user_id=int(rid) if staff.get("pg_admin_username") else None,
            session=session if staff.get("pg_admin_username") else None,
        )
        funnel_enabled = on(ui.get("funnel_tracking_enabled", "1"))
        try:
            expire_days = int(ui.get("action_center_expire_days") or 3)
        except (TypeError, ValueError):
            expire_days = 3
        funnel, periods, action_center = await _parallel_home_ops(
            reseller_id=int(rid),
            funnel_enabled=funnel_enabled,
            expire_days=expire_days,
        )
        try:
            from app.services.inbox_dismissals import filter_action_center_for_staff

            action_center = await filter_action_center_for_staff(
                session, staff, action_center
            )
        except Exception:
            logger.exception("reseller home action_center dismiss filter failed")
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
