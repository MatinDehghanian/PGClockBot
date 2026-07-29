"""Aggregate data for the top-level admin home dashboard."""

from __future__ import annotations

from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    BotUser,
    Order,
    Payment,
    PaymentStatus,
    Plan,
    ResellerProfile,
    Ticket,
    UserService,
)
from app.services.host_metrics import host_metrics
from app.services.pasarguard import get_pg
from app.services.setup_wizard import current_setup_values


def _node_tone(status: str) -> str:
    st = (status or "").strip().lower()
    if st in {"connected", "online", "healthy", "active"}:
        return "ok"
    if "connect" in st or st in {"pending", "waiting"}:
        return "warn"
    if st in {"error", "offline", "unhealthy", "disabled", "disconnected"}:
        return "err"
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
    token = (token or current_setup_values().get("BOT_TOKEN") or "").strip()
    if not token:
        return {"ok": False, "error": "توکن تنظیم نشده", "username": None, "name": None}
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
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
            "error": f"عدم اتصال به تلگرام",
            "detail": str(exc),
            "username": None,
            "name": None,
        }


async def load_nodes_status() -> dict[str, Any]:
    try:
        nodes = await get_pg().get_nodes_simple()
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc) or "خطا در دریافت نودها",
            "nodes": [],
            "total": 0,
            "connected": 0,
            "warn": 0,
            "error_count": 0,
        }
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
    users = await session.scalar(select(func.count()).select_from(BotUser)) or 0
    orders = await session.scalar(select(func.count()).select_from(Order)) or 0
    services = await session.scalar(select(func.count()).select_from(UserService)) or 0
    pending = (
        await session.scalar(
            select(func.count())
            .select_from(Payment)
            .where(
                Payment.status == PaymentStatus.PENDING.value,
                Payment.receipt_file_id.is_not(None),
            )
        )
        or 0
    )
    revenue = (
        await session.scalar(
            select(func.coalesce(func.sum(Order.amount), 0)).where(Order.status == "delivered")
        )
        or 0
    )
    tickets = (
        await session.scalar(
            select(func.count()).select_from(Ticket).where(Ticket.status == "open")
        )
        or 0
    )
    plans = (
        await session.scalar(
            select(func.count())
            .select_from(Plan)
            .where(Plan.is_active.is_(True), Plan.owner_reseller_id.is_(None))
        )
        or 0
    )
    resellers = (
        await session.scalar(
            select(func.count())
            .select_from(ResellerProfile)
            .where(ResellerProfile.is_active.is_(True))
        )
        or 0
    )
    return {
        "users": int(users),
        "orders": int(orders),
        "services": int(services),
        "pending": int(pending),
        "revenue": int(revenue),
        "tickets": int(tickets),
        "plans": int(plans),
        "resellers": int(resellers),
    }


async def pg_panel_summary() -> dict[str, Any]:
    out: dict[str, Any] = {
        "ok": False,
        "error": None,
        "templates": 0,
        "groups": 0,
        "hosts": 0,
        "nodes": 0,
        "users": None,
        "version": None,
    }
    try:
        pg = get_pg()
        templates = await pg.get_user_templates_simple()
        groups = await pg.get_groups_simple()
        hosts = await pg.get_hosts()
        nodes = await pg.get_nodes_simple()
        out.update(
            {
                "ok": True,
                "templates": len(templates or []),
                "groups": len(groups or []),
                "hosts": len(hosts or []),
                "nodes": len(nodes or []),
            }
        )
        try:
            raw = await pg.get_system_stats()
            if isinstance(raw, dict):
                for key in ("total_user", "users_active", "users", "total_users"):
                    if key in raw and isinstance(raw[key], (int, float)):
                        out["users"] = int(raw[key])
                        break
                ver = raw.get("version")
                if ver:
                    out["version"] = str(ver)
        except Exception:
            pass
    except Exception as exc:
        out["error"] = str(exc) or "اتصال به پاسارگارد برقرار نشد"
    return out


async def build_home_overview(session: AsyncSession) -> dict[str, Any]:
    metrics = host_metrics(wait_cpu=0.12)
    bot = await check_bot_connection()
    nodes = await load_nodes_status()
    bot_sum = await bot_panel_summary(session)
    pg_sum = await pg_panel_summary()

    cpu = metrics.get("cpu_percent")
    mem_pct = metrics.get("memory_percent")
    return {
        "host": {
            **metrics,
            "cpu_tone": _tone_class(cpu if isinstance(cpu, (int, float)) else None),
            "mem_tone": _tone_class(mem_pct if isinstance(mem_pct, (int, float)) else None),
        },
        "bot": bot,
        "nodes": nodes,
        "bot_summary": bot_sum,
        "pg_summary": pg_sum,
    }
