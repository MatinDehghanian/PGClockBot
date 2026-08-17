"""Aggregate data for the top-level admin home dashboard."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    BotUser,
    Order,
    Payment,
    PaymentStatus,
    ResellerProfile,
    Ticket,
    UserService,
)
from app.services.pasarguard import get_pg
from app.services.setup_wizard import current_setup_values

_TEHRAN = ZoneInfo("Asia/Tehran")

_ERR_NODE = frozenset({"error", "offline", "unhealthy", "disabled", "disconnected"})
_OK_NODE = frozenset({"connected", "online", "healthy", "active"})
_WARN_NODE = frozenset({"pending", "waiting", "connecting"})


def _node_tone(status: str) -> str:
    st = (status or "").strip().lower()
    if st in _OK_NODE:
        return "ok"
    if st in _ERR_NODE or "disconnect" in st or "offline" in st:
        return "err"
    if st in _WARN_NODE or "connect" in st:
        return "warn"
    return "neutral"


def _tone_class(pct: float | None) -> str:
    if pct is None:
        return "neutral"
    if pct >= 90:
        return "err"
    if pct >= 75:
        return "warn"
    return "ok"


async def check_bot_connection(token: str | None = None) -> dict[str, Any]:
    """Probe Telegram getMe for the given token only.

    Never falls back to the platform admin BOT_TOKEN. Callers that need the
    main bot must pass that token explicitly — empty/missing means unset.
    """
    token = (token or "").strip()
    if not token:
        return {"ok": False, "error": "توکن تنظیم نشده", "username": None, "name": None}
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            resp = await client.get(f"https://api.telegram.org/bot{token}/getMe")
            data = resp.json()
        if data.get("ok") and isinstance(data.get("result"), dict):
            me = data["result"]
            return {
                "ok": True,
                "error": None,
                "username": me.get("username"),
                "name": me.get("first_name"),
                "id": me.get("id"),
            }
        return {
            "ok": False,
            "error": data.get("description") or "توکن نامعتبر",
            "username": None,
            "name": None,
        }
    except Exception as exc:
        return {
            "ok": False,
            "error": "عدم اتصال به تلگرام",
            "detail": str(exc),
            "username": None,
            "name": None,
        }


def _summarize_nodes(nodes: list | None) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    connected = warn = err = 0
    for n in nodes or []:
        if not isinstance(n, dict):
            continue
        st = str(n.get("status") or n.get("connection_status") or "")
        tone = _node_tone(st)
        if tone == "ok":
            connected += 1
        elif tone == "warn":
            warn += 1
        elif tone == "err":
            err += 1
        rows.append(
            {
                "id": n.get("id"),
                "name": n.get("name") or n.get("address") or "—",
                "status": st or "—",
                "tone": tone,
            }
        )
    overall = "ok"
    if err:
        overall = "err"
    elif warn or not rows:
        overall = "warn" if rows else "neutral"
    if rows and connected == len(rows):
        overall = "ok"
    return {
        "ok": True,
        "error": None,
        "nodes": rows,
        "total": len(rows),
        "connected": connected,
        "warn": warn,
        "error_count": err,
        "overall": overall,
    }


async def bot_panel_summary(session: AsyncSession) -> dict[str, Any]:
    """Single round-trip aggregate counts for the bot dashboard.

    Platform-scoped only: shop-tenant orders/payments/tickets are excluded
    (hard shop isolation — match web payments/orders lists).
    """
    from sqlalchemy import or_

    pending_expr = (
        select(func.count())
        .select_from(Payment)
        .outerjoin(Order, Order.id == Payment.order_id)
        .where(
            Payment.status == PaymentStatus.PENDING.value,
            Payment.receipt_file_id.is_not(None),
            or_(
                Payment.is_wallet_topup.is_(True),
                Order.reseller_id.is_(None),
            ),
        )
        .scalar_subquery()
    )
    revenue_expr = (
        select(func.coalesce(func.sum(Order.amount), 0))
        .where(Order.status == "delivered", Order.reseller_id.is_(None))
        .scalar_subquery()
    )
    tickets_expr = (
        select(func.count())
        .select_from(Ticket)
        .join(BotUser, BotUser.id == Ticket.user_id)
        .where(Ticket.status == "open", BotUser.reseller_id.is_(None))
        .scalar_subquery()
    )
    resellers_expr = (
        select(func.count())
        .select_from(ResellerProfile)
        .where(ResellerProfile.is_active.is_(True))
        .scalar_subquery()
    )
    orders_expr = (
        select(func.count()).select_from(Order).where(Order.reseller_id.is_(None)).scalar_subquery()
    )
    row = (
        await session.execute(
            select(
                select(func.count()).select_from(BotUser).scalar_subquery(),
                orders_expr,
                select(func.count()).select_from(UserService).scalar_subquery(),
                pending_expr,
                revenue_expr,
                tickets_expr,
                resellers_expr,
            )
        )
    ).one()
    return {
        "users": int(row[0] or 0),
        "orders": int(row[1] or 0),
        "services": int(row[2] or 0),
        "pending": int(row[3] or 0),
        "revenue": int(row[4] or 0),
        "tickets": int(row[5] or 0),
        "resellers": int(row[6] or 0),
    }


async def pg_home_bundle() -> tuple[dict[str, Any], dict[str, Any]]:
    """Fetch PasarGuard summary + node status in one pass (shared nodes call)."""
    nodes_status = {
        "ok": False,
        "error": None,
        "nodes": [],
        "total": 0,
        "connected": 0,
        "warn": 0,
        "error_count": 0,
        "overall": "neutral",
    }
    summary: dict[str, Any] = {
        "ok": False,
        "error": None,
        "admins": 0,
        "groups": 0,
        "hosts": 0,
        "nodes": 0,
        "users": None,
        "version": None,
    }
    try:
        pg = get_pg()
        admins, groups, hosts, nodes, stats = await asyncio.gather(
            pg.get_admins_simple(),
            pg.get_groups_simple(),
            pg.get_hosts(),
            pg.get_nodes_simple(),
            pg.get_system_stats(),
            return_exceptions=True,
        )
        if isinstance(nodes, Exception):
            nodes_status["error"] = str(nodes) or "خطا در دریافت نودها"
            nodes_status["overall"] = "err"
            nodes = []
        else:
            nodes_status = _summarize_nodes(nodes if isinstance(nodes, list) else [])

        if any(isinstance(x, Exception) for x in (admins, groups, hosts)):
            errs = [str(x) for x in (admins, groups, hosts) if isinstance(x, Exception)]
            summary["error"] = errs[0] if errs else "خطا در دریافت آمار پاسارگارد"
        else:
            summary.update(
                {
                    "ok": True,
                    "admins": len(admins or []),
                    "groups": len(groups or []),
                    "hosts": len(hosts or []),
                    "nodes": nodes_status["total"],
                }
            )
            if isinstance(stats, dict):
                for key in ("total_user", "users_active", "users", "total_users"):
                    if key in stats and isinstance(stats[key], (int, float)):
                        summary["users"] = int(stats[key])
                        break
                ver = stats.get("version")
                if ver:
                    summary["version"] = str(ver)
            elif isinstance(stats, Exception):
                # counts still usable even if /system fails
                pass
    except Exception as exc:
        summary["error"] = str(exc) or "اتصال به پاسارگارد برقرار نشد"
        nodes_status["error"] = summary["error"]
        nodes_status["overall"] = "err"
    return summary, nodes_status


def _empty_host() -> dict[str, Any]:
    return {
        "ok": False,
        "cpu_percent": None,
        "cpu_cores": None,
        "memory_percent": None,
        "memory_used": None,
        "memory_total": None,
        "memory_used_text": "—",
        "memory_total_text": "—",
        "memory_ratio_text": "—",
        "cpu_tone": "neutral",
        "mem_tone": "neutral",
    }


def _empty_bot() -> dict[str, Any]:
    return {"ok": False, "error": None, "username": None, "name": None}


def empty_period_bucket() -> dict[str, int]:
    return {
        "orders": 0,
        "delivered": 0,
        "revenue": 0,
        "new_users": 0,
    }


def empty_period_stats() -> dict[str, Any]:
    return {
        "day": empty_period_bucket(),
        "week": empty_period_bucket(),
        "month": empty_period_bucket(),
    }


def _period_since_utc() -> dict[str, datetime]:
    """Today / last-7-days / last-30-days anchored on Asia/Tehran midnight."""
    now_local = datetime.now(_TEHRAN)
    day_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = day_start - timedelta(days=6)
    month_start = day_start - timedelta(days=29)
    return {
        "day": day_start.astimezone(timezone.utc),
        "week": week_start.astimezone(timezone.utc),
        "month": month_start.astimezone(timezone.utc),
    }


def _delta(cur: int, prev: int) -> dict[str, Any] | None:
    cur_i = int(cur or 0)
    prev_i = int(prev or 0)
    if prev_i <= 0:
        if cur_i <= 0:
            return None
        return {"pct": 100, "dir": "up"}
    pct = int(round((cur_i - prev_i) * 100 / prev_i))
    if pct == 0:
        return {"pct": 0, "dir": "flat"}
    return {"pct": abs(pct), "dir": "up" if pct > 0 else "down"}


def _bucket(orders: int, delivered: int, revenue: int, new_users: int, *, delta=None) -> dict[str, Any]:
    row = {
        "orders": int(orders or 0),
        "delivered": int(delivered or 0),
        "revenue": int(revenue or 0),
        "new_users": int(new_users or 0),
    }
    if delta is not None:
        row["delta"] = delta
    return row


async def shop_period_stats(
    session: AsyncSession, *, reseller_id: int | None = None
) -> dict[str, Any]:
    """Sales-ish totals for امروز / ۷ روز / ۳۰ روز (shop-scoped, two round-trips)."""
    starts = _period_since_utc()
    day = starts["day"]
    week = starts["week"]
    month = starts["month"]
    prev_day = day - timedelta(days=1)
    prev_week = week - timedelta(days=7)
    prev_month = month - timedelta(days=30)
    if reseller_id is None:
        scope_orders = Order.reseller_id.is_(None)
        scope_users = BotUser.reseller_id.is_(None)
    else:
        rid = int(reseller_id)
        scope_orders = Order.reseller_id == rid
        scope_users = BotUser.reseller_id == rid

    delivered = Order.status == "delivered"
    order_row = (
        await session.execute(
            select(
                func.coalesce(func.sum(case((Order.created_at >= day, 1), else_=0)), 0),
                func.coalesce(func.sum(case((Order.created_at >= week, 1), else_=0)), 0),
                func.coalesce(func.sum(case((Order.created_at >= month, 1), else_=0)), 0),
                func.coalesce(
                    func.sum(case(((Order.created_at >= day) & delivered, 1), else_=0)), 0
                ),
                func.coalesce(
                    func.sum(case(((Order.created_at >= week) & delivered, 1), else_=0)), 0
                ),
                func.coalesce(
                    func.sum(case(((Order.created_at >= month) & delivered, 1), else_=0)), 0
                ),
                func.coalesce(
                    func.sum(case(((Order.created_at >= day) & delivered, Order.amount), else_=0)),
                    0,
                ),
                func.coalesce(
                    func.sum(case(((Order.created_at >= week) & delivered, Order.amount), else_=0)),
                    0,
                ),
                func.coalesce(
                    func.sum(case(((Order.created_at >= month) & delivered, Order.amount), else_=0)),
                    0,
                ),
                func.coalesce(
                    func.sum(
                        case(
                            ((Order.created_at >= prev_day) & (Order.created_at < day) & delivered, Order.amount),
                            else_=0,
                        )
                    ),
                    0,
                ),
                func.coalesce(
                    func.sum(
                        case(
                            ((Order.created_at >= prev_week) & (Order.created_at < week) & delivered, Order.amount),
                            else_=0,
                        )
                    ),
                    0,
                ),
                func.coalesce(
                    func.sum(
                        case(
                            ((Order.created_at >= prev_month) & (Order.created_at < month) & delivered, Order.amount),
                            else_=0,
                        )
                    ),
                    0,
                ),
            ).where(scope_orders, Order.created_at >= prev_month)
        )
    ).one()
    user_row = (
        await session.execute(
            select(
                func.coalesce(func.sum(case((BotUser.created_at >= day, 1), else_=0)), 0),
                func.coalesce(func.sum(case((BotUser.created_at >= week, 1), else_=0)), 0),
                func.coalesce(func.sum(case((BotUser.created_at >= month, 1), else_=0)), 0),
            ).where(scope_users, BotUser.created_at >= month)
        )
    ).one()
    return {
        "day": _bucket(
            order_row[0],
            order_row[3],
            order_row[6],
            user_row[0],
            delta=_delta(order_row[6], order_row[9]),
        ),
        "week": _bucket(
            order_row[1],
            order_row[4],
            order_row[7],
            user_row[1],
            delta=_delta(order_row[7], order_row[10]),
        ),
        "month": _bucket(
            order_row[2],
            order_row[5],
            order_row[8],
            user_row[2],
            delta=_delta(order_row[8], order_row[11]),
        ),
    }


def _empty_bot_summary() -> dict[str, Any]:
    return {
        "users": 0,
        "orders": 0,
        "services": 0,
        "pending": 0,
        "revenue": 0,
        "tickets": 0,
        "resellers": 0,
    }


def _empty_pg_summary() -> dict[str, Any]:
    return {
        "ok": False,
        "error": None,
        "admins": 0,
        "groups": 0,
        "hosts": 0,
        "nodes": 0,
        "users": None,
        "version": None,
    }


def _empty_nodes() -> dict[str, Any]:
    return {
        "ok": False,
        "error": None,
        "nodes": [],
        "total": 0,
        "connected": 0,
        "warn": 0,
        "error_count": 0,
        "overall": "neutral",
    }


def empty_home_overview() -> dict[str, Any]:
    """Fail-soft shell so ``home.html`` never sees missing keys / Undefined."""
    return {
        "host": _empty_host(),
        "bot": _empty_bot(),
        "nodes": _empty_nodes(),
        "bot_summary": _empty_bot_summary(),
        "pg_summary": _empty_pg_summary(),
    }


async def build_home_overview(session: AsyncSession) -> dict[str, Any]:
    """Build admin home payloads; never raise — partial failures return defaults.

    Host CPU/RAM live on bot/PG overviews now — skipped here for a faster /home.
    """
    import logging

    from app.services.db_safe import rollback_quiet

    log = logging.getLogger(__name__)
    out = empty_home_overview()
    # Platform admin overview only — pass main token explicitly (no silent fallback).
    bot_task = check_bot_connection(current_setup_values().get("BOT_TOKEN"))
    bot_sum_task = bot_panel_summary(session)
    pg_task = pg_home_bundle()

    bot, bot_sum, pg_pair = await asyncio.gather(
        bot_task, bot_sum_task, pg_task, return_exceptions=True
    )

    if isinstance(bot, Exception):
        log.exception("home bot probe failed: %s", bot)
        out["bot"] = {**_empty_bot(), "error": "بررسی ربات ناموفق"}
    elif isinstance(bot, dict):
        out["bot"] = bot

    if isinstance(bot_sum, Exception):
        log.exception("home bot_panel_summary failed: %s", bot_sum)
        await rollback_quiet(session)
        out["bot_summary"] = _empty_bot_summary()
    elif isinstance(bot_sum, dict):
        out["bot_summary"] = bot_sum

    if isinstance(pg_pair, Exception):
        log.exception("home pg_home_bundle failed: %s", pg_pair)
        out["pg_summary"] = {
            **_empty_pg_summary(),
            "error": "اتصال به پاسارگارد برقرار نشد",
        }
        out["nodes"] = {**_empty_nodes(), "overall": "err", "error": out["pg_summary"]["error"]}
    elif isinstance(pg_pair, tuple) and len(pg_pair) == 2:
        pg_sum, nodes = pg_pair
        if isinstance(pg_sum, dict):
            out["pg_summary"] = pg_sum
        if isinstance(nodes, dict):
            out["nodes"] = nodes

    return out


def build_home_pulse(*, periods: dict[str, Any] | None, action_center: dict[str, Any] | None) -> dict[str, Any]:
    """One-line business status for /home (no live probes)."""
    day = (periods or {}).get("day") or {}
    ac = action_center or {}
    delivered = int(day.get("delivered") or 0)
    revenue = int(day.get("revenue") or 0)
    tickets = int(ac.get("tickets") or 0)
    pending = int(ac.get("pending") or 0)
    expiring = int(ac.get("expiring") or 0)
    has_work = bool(ac.get("has_items"))
    items = [
        {"n": delivered, "label": "خرید موفق امروز"},
        {"n": tickets, "label": "تیکت باز"},
        {"n": pending, "label": "رسید معلق"},
    ]
    if expiring:
        items.append({"n": expiring, "label": "نزدیک انقضا"})
    if has_work:
        lead = "کار در صف مانده"
        tone = "warn"
    elif delivered:
        lead = "امروز فروش فعال بوده"
        tone = "ok"
    else:
        lead = "صف کار خالی است"
        tone = "neutral"
    return {
        "lead": lead,
        "tone": tone,
        "items": items,
        "revenue": revenue,
        "delivered": delivered,
    }


async def build_home_shell(session: AsyncSession) -> dict[str, Any]:
    """DB-only /home overview — live Telegram/PG probes stay unchecked."""
    import logging

    from app.services.db_safe import rollback_quiet

    log = logging.getLogger(__name__)
    out = empty_home_overview()
    out["bot"] = {**_empty_bot(), "unchecked": True}
    out["nodes"] = {**_empty_nodes(), "unchecked": True, "overall": "neutral"}
    out["pg_summary"] = {**_empty_pg_summary(), "unchecked": True}
    try:
        out["bot_summary"] = await bot_panel_summary(session)
    except Exception:
        log.exception("home shell bot_panel_summary failed")
        await rollback_quiet(session)
        out["bot_summary"] = _empty_bot_summary()
    return out
