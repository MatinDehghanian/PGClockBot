"""Telegram Mini App pages + JSON API (role-aware shells)."""

from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import Plan, ResellerProfile, UserService
from app.services.db_safe import rollback_quiet
from app.services.miniapp_auth import (
    load_mini_user,
    load_reseller_profile,
    resolve_mini_persona,
)
from app.services.pasarguard import get_pg


def _no_store(payload: dict) -> JSONResponse:
    resp = JSONResponse(payload)
    resp.headers["Cache-Control"] = "no-store, private"
    return resp


def _nav_for(persona: str) -> list[dict[str, str]]:
    if persona == "admin":
        return [
            {"id": "home", "label": "خانه"},
            {"id": "ops", "label": "عملیات"},
            {"id": "support", "label": "پشتیبانی"},
        ]
    if persona == "reseller":
        return [
            {"id": "home", "label": "خانه"},
            {"id": "shop", "label": "فروشگاه"},
            {"id": "support", "label": "پشتیبانی"},
        ]
    return [
        {"id": "home", "label": "خانه"},
        {"id": "services", "label": "سرویس‌ها"},
        {"id": "shop", "label": "خرید"},
    ]


async def _user_shop_payload(session: AsyncSession, user) -> dict:
    svc_result = await session.execute(
        select(UserService).where(UserService.bot_user_id == user.id)
    )
    services = list(svc_result.scalars().all())
    plans_q = select(Plan).where(Plan.is_active.is_(True), Plan.owner_reseller_id.is_(None))
    if user.reseller_id:
        plans_q = select(Plan).where(
            Plan.is_active.is_(True),
            Plan.owner_reseller_id == user.reseller_id,
        )
    plans_result = await session.execute(plans_q.order_by(Plan.sort_order))
    plans = list(plans_result.scalars().all())
    return {
        "wallet": int(user.wallet_balance or 0),
        "services": [
            {
                "id": s.id,
                "username": s.pg_username,
                "subscription_url": s.subscription_url,
            }
            for s in services
        ],
        "plans": [
            {
                "id": p.id,
                "name": p.name,
                "price": int(p.price or 0),
                "days": p.duration_days,
                "gb": p.data_limit_gb,
            }
            for p in plans
        ],
    }


async def _admin_ops_payload(session: AsyncSession) -> dict:
    from app.services.home_overview import bot_panel_summary

    try:
        summary = await bot_panel_summary(session)
    except Exception:
        await rollback_quiet(session)
        summary = {
            "users": 0,
            "orders": 0,
            "services": 0,
            "pending": 0,
            "revenue": 0,
            "tickets": 0,
            "resellers": 0,
        }
    settings = get_settings()
    base = (settings.public_base_url or "").rstrip("/")
    return {
        "stats": {
            "users": int(summary.get("users") or 0),
            "orders": int(summary.get("orders") or 0),
            "services": int(summary.get("services") or 0),
            "pending": int(summary.get("pending") or 0),
            "revenue": int(summary.get("revenue") or 0),
            "tickets": int(summary.get("tickets") or 0),
            "resellers": int(summary.get("resellers") or 0),
        },
        "panel_links": [
            {"id": "resellers", "label": "نمایندگان", "path": "/resellers"},
            {"id": "finance", "label": "مالی", "path": "/finance"},
            {"id": "users", "label": "کاربران", "path": "/users"},
            {"id": "tickets", "label": "تیکت‌ها", "path": "/tickets"},
            {"id": "dashboard", "label": "نمای کلی وب", "path": "/dashboard"},
        ]
        if base
        else [],
        "panel_base": base,
    }


async def _reseller_ops_payload(session: AsyncSession, profile: ResellerProfile | None) -> dict:
    from app.api.home_pages import _reseller_shop_stats

    stats = {
        "users": 0,
        "orders": 0,
        "pending": 0,
        "services": 0,
        "revenue": 0,
        "plans": 0,
        "tickets": 0,
    }
    if profile is not None:
        try:
            stats = await _reseller_shop_stats(session, int(profile.id))
        except Exception:
            await rollback_quiet(session)
    settings = get_settings()
    base = (settings.public_base_url or "").rstrip("/")
    billing = None
    if profile is not None and (profile.billing_mode or "") == "payg":
        billing = {
            "balance": int(profile.billing_balance or 0),
            "suspended": bool(getattr(profile, "billing_suspended_at", None)),
        }
    return {
        "stats": stats,
        "shop": {
            "bot_username": (profile.bot_username if profile else None) or "",
            "active": bool(profile.is_active) if profile else False,
            "billing": billing,
        },
        "panel_links": [
            {"id": "home", "label": "داشبورد وب", "path": "/home"},
            {"id": "finance", "label": "مالی", "path": "/finance"},
            {"id": "tickets", "label": "پشتیبانی", "path": "/tickets"},
            {"id": "shop", "label": "تنظیمات فروشگاه", "path": "/shop-settings"},
        ]
        if base
        else [],
        "panel_base": base,
    }


def register_miniapp_pages(app: FastAPI, *, render, get_db) -> None:
    @app.get("/miniapp/", response_class=HTMLResponse)
    @app.get("/miniapp", response_class=HTMLResponse)
    async def miniapp_index(request: Request):
        return render(request, "miniapp.html", {})

    @app.get("/api/mini/me")
    async def mini_me(request: Request, session: AsyncSession = Depends(get_db)):
        user = await load_mini_user(session, request)
        persona = resolve_mini_persona(user)
        payload: dict = {
            "persona": persona,
            "nav": _nav_for(persona),
            "user": {
                "id": user.id,
                "name": user.full_name or "",
                "role": user.role,
                "wallet": int(user.wallet_balance or 0),
            },
            "currency": get_settings().currency or "تومان",
            "panel_base": (get_settings().public_base_url or "").rstrip("/"),
        }
        # Customer surfaces always available (admin/reseller can still buy as user)
        payload["customer"] = await _user_shop_payload(session, user)
        if persona == "admin":
            payload["ops"] = await _admin_ops_payload(session)
        elif persona == "reseller":
            profile = await load_reseller_profile(session, user)
            payload["ops"] = await _reseller_ops_payload(session, profile)
        return _no_store(payload)

    @app.get("/api/mini/service/{service_id}")
    async def mini_service(
        service_id: int, request: Request, session: AsyncSession = Depends(get_db)
    ):
        user = await load_mini_user(session, request)
        svc = await session.get(UserService, service_id)
        if not svc or svc.bot_user_id != user.id:
            raise HTTPException(404)
        info: dict = {}
        if svc.subscription_token:
            try:
                info = await get_pg().subscription_info(svc.subscription_token)
            except Exception:
                info = {"error": "upstream_unavailable"}
        return _no_store(
            {
                "service": {
                    "id": svc.id,
                    "username": svc.pg_username,
                    "url": svc.subscription_url,
                },
                "info": info,
            }
        )
