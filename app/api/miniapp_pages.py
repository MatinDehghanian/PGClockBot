"""Telegram Mini App pages + JSON API (role-aware shells)."""

from __future__ import annotations

import asyncio
import base64
import logging
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import Plan, ResellerProfile, UserService
from app.services.db_safe import rollback_quiet
from app.services.formatting import (
    expire_remaining_days,
    format_bytes_ratio,
    format_expire_short,
    status_label,
)
from app.services.miniapp_auth import (
    load_mini_user,
    load_reseller_profile,
    resolve_mini_persona,
)
from app.services.pasarguard import get_pg
from app.services.users import get_all_settings, on

log = logging.getLogger(__name__)


def _no_store(payload: dict) -> JSONResponse:
    resp = JSONResponse(payload)
    resp.headers["Cache-Control"] = "no-store, private"
    return resp


def _nav_for(persona: str) -> list[dict[str, str]]:
    # Shared customer tabs + ops for staff personas
    base = [
        {"id": "home", "label": "خانه", "icon": "home"},
        {"id": "services", "label": "سرویس", "icon": "svc"},
        {"id": "shop", "label": "خرید", "icon": "shop"},
        {"id": "wallet", "label": "کیف پول", "icon": "wallet"},
    ]
    if persona == "admin":
        return base + [{"id": "ops", "label": "عملیات", "icon": "ops"}]
    if persona == "reseller":
        return base + [{"id": "ops", "label": "پنل", "icon": "ops"}]
    return base


def _traffic_pct(used, limit) -> int | None:
    try:
        lim = float(limit or 0)
        if lim <= 0:
            return None
        u = float(used or 0)
        return int(min(100, max(0, round(100.0 * u / lim))))
    except (TypeError, ValueError):
        return None


async def _fetch_pg_info(token: str | None) -> dict:
    if not (token or "").strip():
        return {}
    try:
        return await asyncio.wait_for(get_pg().subscription_info(token), timeout=5.0)
    except Exception:
        return {"error": "upstream_unavailable"}


def _serialize_service(svc: UserService, info: dict | None = None) -> dict:
    info = info or {}
    used = info.get("used_traffic")
    limit = info.get("data_limit")
    expire = info.get("expire")
    status_raw = (info.get("status") or "").strip() or None
    days = expire_remaining_days(expire) if "error" not in info else None
    return {
        "id": svc.id,
        "username": svc.pg_username or "",
        "subscription_url": svc.subscription_url or "",
        "plan_id": svc.plan_id,
        "status": status_raw or "—",
        "status_fa": status_label(status_raw) if status_raw else ("—" if not info else "نامشخص"),
        "traffic": format_bytes_ratio(used, limit, joiner=" از ")
        if "error" not in info
        else "—",
        "traffic_pct": _traffic_pct(used, limit) if "error" not in info else None,
        "expire": format_expire_short(expire) if "error" not in info else "—",
        "expire_days": days,
        "online_at": format_expire_short(info.get("online_at"))
        if info.get("online_at") and "error" not in info
        else None,
        "error": info.get("error"),
    }


async def _enrich_services(services: list[UserService]) -> list[dict]:
    if not services:
        return []
    infos = await asyncio.gather(
        *[_fetch_pg_info(s.subscription_token) for s in services[:20]]
    )
    out = [_serialize_service(s, info) for s, info in zip(services[:20], infos)]
    # Cap — avoid hammering PG for huge accounts
    for s in services[20:]:
        out.append(_serialize_service(s, {}))
    return out


async def _user_shop_payload(session: AsyncSession, user) -> dict:
    from app.services.wallet import list_activity

    svc_result = await session.execute(
        select(UserService)
        .where(UserService.bot_user_id == user.id)
        .order_by(UserService.id.desc())
    )
    services = list(svc_result.scalars().all())
    plans_q = select(Plan).where(
        Plan.is_active.is_(True),
        Plan.is_trial.is_(False),
        Plan.owner_reseller_id.is_(None),
    )
    if user.reseller_id:
        plans_q = select(Plan).where(
            Plan.is_active.is_(True),
            Plan.is_trial.is_(False),
            Plan.owner_reseller_id == user.reseller_id,
        )
    plans_result = await session.execute(plans_q.order_by(Plan.sort_order, Plan.id))
    plans = list(plans_result.scalars().all())
    # Include one trial if available for this shop
    trial_q = select(Plan).where(
        Plan.is_active.is_(True),
        Plan.is_trial.is_(True),
        Plan.owner_reseller_id.is_(None)
        if not user.reseller_id
        else Plan.owner_reseller_id == user.reseller_id,
    )
    trial = (await session.execute(trial_q.limit(1))).scalar_one_or_none()

    ui = await get_all_settings(session)
    wallet_pay = on(ui.get("pay_wallet_enabled"))
    enriched = await _enrich_services(services)
    activity = await list_activity(session, user.id, limit=25)
    return {
        "wallet": int(user.wallet_balance or 0),
        "wallet_pay_enabled": wallet_pay,
        "services": enriched,
        "plans": [
            {
                "id": p.id,
                "name": p.name,
                "price": int(p.price or 0),
                "days": p.duration_days,
                "gb": p.data_limit_gb,
                "is_trial": bool(p.is_trial),
            }
            for p in (([trial] if trial else []) + plans)
        ],
        "activity": [
            {
                "amount": int(a.amount),
                "reason": a.reason or "",
                "created_at": a.created_at.astimezone(timezone.utc).isoformat()
                if isinstance(a.created_at, datetime)
                else None,
            }
            for a in activity
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
        info = await _fetch_pg_info(svc.subscription_token)
        return _no_store(
            {
                "service": _serialize_service(svc, info),
                "info": info,
            }
        )

    @app.get("/api/mini/service/{service_id}/qr")
    async def mini_service_qr(
        service_id: int, request: Request, session: AsyncSession = Depends(get_db)
    ):
        from app.services.qrcode_gen import make_subscription_qr

        user = await load_mini_user(session, request)
        svc = await session.get(UserService, service_id)
        if not svc or svc.bot_user_id != user.id:
            raise HTTPException(404)
        url = (svc.subscription_url or "").strip()
        if not url:
            raise HTTPException(404, "no subscription url")
        ui = await get_all_settings(session)
        if not on(ui.get("qr_enabled", "1")):
            raise HTTPException(403, "qr disabled")
        bg = (ui.get("qr_background") or "").strip() or None
        try:
            buf = make_subscription_qr(url, background=bg, box_size=8, border=2)
        except Exception:
            log.exception("miniapp qr failed service=%s", service_id)
            raise HTTPException(500, "qr failed")
        data = buf.getvalue()
        # Prefer JSON data-URL for easy Telegram WebView use (CORS/blob quirks)
        if request.query_params.get("format") == "png":
            return Response(
                content=data,
                media_type="image/png",
                headers={"Cache-Control": "no-store, private"},
            )
        b64 = base64.b64encode(data).decode("ascii")
        return _no_store({"png_base64": b64, "url": url})

    @app.post("/api/mini/buy")
    async def mini_buy(request: Request, session: AsyncSession = Depends(get_db)):
        from app.services.orders import create_order, get_catalog_plan, pay_with_wallet

        user = await load_mini_user(session, request)
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(400, "bad json")
        plan_id = body.get("plan_id")
        try:
            plan_id = int(plan_id)
        except (TypeError, ValueError):
            raise HTTPException(400, "plan_id required")
        ui = await get_all_settings(session)
        if not on(ui.get("pay_wallet_enabled")):
            raise HTTPException(403, "پرداخت با کیف پول غیرفعال است")
        plan = await get_catalog_plan(session, plan_id)
        if not plan or not plan.is_active:
            raise HTTPException(400, "پلن یافت نشد")
        await session.refresh(user)
        if int(plan.price or 0) > int(user.wallet_balance or 0):
            raise HTTPException(400, "موجودی کیف پول کافی نیست")
        try:
            order = await create_order(session, user_id=user.id, plan_id=plan_id)
            await session.refresh(user)
            order = await pay_with_wallet(session, order, user)
            await session.refresh(user)
        except ValueError as exc:
            await rollback_quiet(session)
            raise HTTPException(400, str(exc)) from exc
        except Exception as exc:
            await rollback_quiet(session)
            log.exception("mini buy failed user=%s plan=%s", user.id, plan_id)
            raise HTTPException(500, str(exc) or "خرید ناموفق") from exc
        return _no_store(
            {
                "ok": True,
                "order_id": order.id,
                "wallet": int(user.wallet_balance or 0),
                "message": "خرید با موفقیت انجام شد",
            }
        )

    @app.post("/api/mini/renew")
    async def mini_renew(request: Request, session: AsyncSession = Depends(get_db)):
        from app.services.orders import get_catalog_plan, pay_with_wallet, renew_service_with_plan

        user = await load_mini_user(session, request)
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(400, "bad json")
        try:
            service_id = int(body.get("service_id"))
            plan_id = int(body.get("plan_id"))
        except (TypeError, ValueError):
            raise HTTPException(400, "service_id and plan_id required")
        ui = await get_all_settings(session)
        if not on(ui.get("pay_wallet_enabled")):
            raise HTTPException(403, "پرداخت با کیف پول غیرفعال است")
        svc = await session.get(UserService, service_id)
        if not svc or svc.bot_user_id != user.id:
            raise HTTPException(404, "سرویس یافت نشد")
        plan = await get_catalog_plan(session, plan_id)
        if not plan or not plan.is_active or plan.is_trial:
            raise HTTPException(400, "پلن تمدید نامعتبر است")
        await session.refresh(user)
        if int(plan.price or 0) > int(user.wallet_balance or 0):
            raise HTTPException(400, "موجودی کیف پول کافی نیست")
        try:
            order = await renew_service_with_plan(
                session, user_id=user.id, service=svc, plan=plan
            )
            await session.refresh(user)
            order = await pay_with_wallet(session, order, user)
            await session.refresh(user)
        except ValueError as exc:
            await rollback_quiet(session)
            raise HTTPException(400, str(exc)) from exc
        except Exception as exc:
            await rollback_quiet(session)
            log.exception("mini renew failed user=%s svc=%s", user.id, service_id)
            raise HTTPException(500, str(exc) or "تمدید ناموفق") from exc
        return _no_store(
            {
                "ok": True,
                "order_id": order.id,
                "wallet": int(user.wallet_balance or 0),
                "message": "تمدید با موفقیت انجام شد",
            }
        )
