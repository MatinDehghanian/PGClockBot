from __future__ import annotations

import hashlib
import hmac
import json
import time
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qsl

from fastapi import Depends, FastAPI, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from itsdangerous import BadSignature, URLSafeSerializer
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import (
    BotUser,
    Order,
    Payment,
    PaymentStatus,
    Plan,
    ResellerProfile,
    Role,
    Setting,
    Ticket,
    UserService,
)
from app.db.session import SessionLocal
from app.services.orders import approve_payment, reject_payment
from app.services.pasarguard import get_pg
from app.services.resellers import make_reseller
from app.services.users import (
    SETTING_GROUPS,
    ensure_default_settings,
    get_all_settings,
    get_setting,
    set_setting,
)

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))


def render(request: Request, name: str, context: dict | None = None, status_code: int = 200):
    ctx = dict(context or {})
    return templates.TemplateResponse(request, name, ctx, status_code=status_code)


def create_api_app(lifespan=None) -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="PGClockBot Panel", docs_url=None, redoc_url=None, lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")
    signer = URLSafeSerializer(settings.web_secret, salt="pgclock-session")

    async def get_db():
        async with SessionLocal() as session:
            yield session

    def get_session_user(request: Request) -> Optional[dict]:
        cookie = request.cookies.get("session")
        if not cookie:
            return None
        try:
            return signer.loads(cookie)
        except BadSignature:
            return None

    def require_staff(request: Request) -> dict:
        user = get_session_user(request)
        if not user or user.get("role") not in {"admin", "reseller"}:
            raise HTTPException(status_code=401, detail="unauthorized")
        return user

    def require_admin(request: Request) -> dict:
        user = require_staff(request)
        if user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="admin only")
        return user

    @app.get("/", response_class=HTMLResponse)
    async def root(request: Request):
        user = get_session_user(request)
        if not user:
            return RedirectResponse("/login", status_code=302)
        return RedirectResponse("/dashboard", status_code=302)

    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request):
        return render(request, "login.html", {"error": None},
        )

    @app.post("/login")
    async def login_submit(
        request: Request,
        username: str = Form(...),
        password: str = Form(...),
        session: AsyncSession = Depends(get_db),
    ):
        settings = get_settings()
        role = None
        display = username
        if username == settings.web_admin_user and password == settings.web_admin_password:
            role = "admin"
        else:
            # reseller login: username=telegram_id password=referral_code
            try:
                tg_id = int(username)
            except ValueError:
                tg_id = None
            if tg_id is not None:
                result = await session.execute(
                    select(BotUser).where(BotUser.telegram_id == tg_id, BotUser.role == Role.RESELLER.value)
                )
                ru = result.scalar_one_or_none()
                if ru and password == ru.referral_code:
                    role = "reseller"
                    display = ru.full_name or str(tg_id)
        if not role:
            return render(request, "login.html", {"error": "ورود نامعتبر"},
                status_code=400,
            )
        resp = RedirectResponse("/dashboard", status_code=302)
        resp.set_cookie(
            "session",
            signer.dumps({"role": role, "username": display}),
            httponly=True,
            samesite="lax",
        )
        return resp

    @app.get("/logout")
    async def logout():
        resp = RedirectResponse("/login", status_code=302)
        resp.delete_cookie("session")
        return resp

    @app.get("/dashboard", response_class=HTMLResponse)
    async def dashboard(
        request: Request,
        staff: dict = Depends(require_staff),
        session: AsyncSession = Depends(get_db),
    ):
        users_count = await session.scalar(select(func.count()).select_from(BotUser)) or 0
        orders_count = await session.scalar(select(func.count()).select_from(Order)) or 0
        pending_payments = await session.scalar(
            select(func.count()).select_from(Payment).where(
                Payment.status == PaymentStatus.PENDING.value,
                Payment.receipt_file_id.is_not(None),
            )
        ) or 0
        services_count = await session.scalar(select(func.count()).select_from(UserService)) or 0
        revenue = await session.scalar(
            select(func.coalesce(func.sum(Order.amount), 0)).where(Order.status == "delivered")
        ) or 0
        return render(request, "dashboard.html", {
                "staff": staff,
                "stats": {
                    "users": users_count,
                    "orders": orders_count,
                    "pending": pending_payments,
                    "services": services_count,
                    "revenue": revenue,
                },
            },
        )

    @app.get("/plans", response_class=HTMLResponse)
    async def plans_page(
        request: Request,
        staff: dict = Depends(require_admin),
        session: AsyncSession = Depends(get_db),
    ):
        result = await session.execute(select(Plan).order_by(Plan.sort_order, Plan.id))
        plans = list(result.scalars().all())
        return render(request, "plans.html", {"staff": staff, "plans": plans},
        )

    @app.post("/plans")
    async def plans_create(
        request: Request,
        name: str = Form(...),
        price: int = Form(...),
        duration_days: int = Form(30),
        data_limit_gb: str = Form(""),
        pg_template_id: str = Form(""),
        description: str = Form(""),
        staff: dict = Depends(require_admin),
        session: AsyncSession = Depends(get_db),
    ):
        gb = float(data_limit_gb) if data_limit_gb.strip() else None
        tpl = int(pg_template_id) if pg_template_id.strip() else None
        session.add(
            Plan(
                name=name,
                price=price,
                duration_days=duration_days,
                data_limit_gb=gb,
                pg_template_id=tpl,
                description=description or None,
                is_active=True,
            )
        )
        await session.commit()
        return RedirectResponse("/plans", status_code=302)

    @app.post("/plans/{plan_id}/toggle")
    async def plans_toggle(
        plan_id: int,
        staff: dict = Depends(require_admin),
        session: AsyncSession = Depends(get_db),
    ):
        plan = await session.get(Plan, plan_id)
        if plan:
            plan.is_active = not plan.is_active
            await session.commit()
        return RedirectResponse("/plans", status_code=302)

    @app.get("/orders", response_class=HTMLResponse)
    async def orders_page(
        request: Request,
        staff: dict = Depends(require_staff),
        session: AsyncSession = Depends(get_db),
    ):
        result = await session.execute(select(Order).order_by(Order.id.desc()).limit(100))
        orders = list(result.scalars().all())
        return render(request, "orders.html", {"staff": staff, "orders": orders},
        )

    @app.get("/payments", response_class=HTMLResponse)
    async def payments_page(
        request: Request,
        staff: dict = Depends(require_staff),
        session: AsyncSession = Depends(get_db),
    ):
        result = await session.execute(select(Payment).order_by(Payment.id.desc()).limit(100))
        payments = list(result.scalars().all())
        return render(request, "payments.html", {"staff": staff, "payments": payments},
        )

    @app.post("/payments/{payment_id}/approve")
    async def payment_approve(
        payment_id: int,
        staff: dict = Depends(require_staff),
        session: AsyncSession = Depends(get_db),
    ):
        payment = await session.get(Payment, payment_id)
        if payment:
            await approve_payment(session, payment, reviewer_tg=0)
        return RedirectResponse("/payments", status_code=302)

    @app.post("/payments/{payment_id}/reject")
    async def payment_reject(
        payment_id: int,
        staff: dict = Depends(require_staff),
        session: AsyncSession = Depends(get_db),
    ):
        payment = await session.get(Payment, payment_id)
        if payment:
            await reject_payment(session, payment, reviewer_tg=0, note="web reject")
        return RedirectResponse("/payments", status_code=302)

    @app.get("/users", response_class=HTMLResponse)
    async def users_page(
        request: Request,
        staff: dict = Depends(require_admin),
        session: AsyncSession = Depends(get_db),
    ):
        result = await session.execute(select(BotUser).order_by(BotUser.id.desc()).limit(200))
        users = list(result.scalars().all())
        return render(request, "users.html", {"staff": staff, "users": users},
        )

    @app.get("/resellers", response_class=HTMLResponse)
    async def resellers_page(
        request: Request,
        staff: dict = Depends(require_admin),
        session: AsyncSession = Depends(get_db),
    ):
        result = await session.execute(
            select(BotUser, ResellerProfile)
            .join(ResellerProfile, ResellerProfile.user_id == BotUser.id)
        )
        rows = result.all()
        return render(request, "resellers.html", {"staff": staff, "rows": rows},
        )

    @app.post("/resellers")
    async def reseller_create(
        telegram_id: int = Form(...),
        commission_percent: int = Form(10),
        can_approve: str = Form(""),
        staff: dict = Depends(require_admin),
        session: AsyncSession = Depends(get_db),
    ):
        result = await session.execute(select(BotUser).where(BotUser.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        if user:
            await make_reseller(
                session,
                user,
                commission_percent=commission_percent,
                can_approve_receipts=bool(can_approve),
            )
        return RedirectResponse("/resellers", status_code=302)

    @app.get("/settings", response_class=HTMLResponse)
    async def settings_page(
        request: Request,
        staff: dict = Depends(require_admin),
        session: AsyncSession = Depends(get_db),
    ):
        values = await get_all_settings(session)
        return render(
            request,
            "settings.html",
            {
                "staff": staff,
                "values": values,
                "groups": SETTING_GROUPS,
                "saved": request.query_params.get("saved") == "1",
            },
        )

    @app.post("/settings")
    async def settings_save(
        request: Request,
        staff: dict = Depends(require_admin),
        session: AsyncSession = Depends(get_db),
    ):
        form = await request.form()
        for key, value in form.items():
            if key.startswith("s_"):
                await set_setting(session, key[2:], str(value))
        return RedirectResponse("/settings?saved=1", status_code=302)

    @app.get("/tickets", response_class=HTMLResponse)
    async def tickets_page(
        request: Request,
        staff: dict = Depends(require_staff),
        session: AsyncSession = Depends(get_db),
    ):
        result = await session.execute(select(Ticket).order_by(Ticket.id.desc()).limit(100))
        tickets = list(result.scalars().all())
        return render(request, "tickets.html", {"staff": staff, "tickets": tickets},
        )

    # -------- Mini App pages & API --------
    @app.get("/miniapp/", response_class=HTMLResponse)
    async def miniapp_index(request: Request):
        return render(request, "miniapp.html", {})

    def _validate_init_data(init_data: str) -> dict:
        settings = get_settings()
        parsed = dict(parse_qsl(init_data, keep_blank_values=True))
        received_hash = parsed.pop("hash", None)
        if not received_hash:
            raise HTTPException(401, "missing hash")
        data_check = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
        secret = hmac.new(b"WebAppData", settings.bot_token.encode(), hashlib.sha256).digest()
        calc = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calc, received_hash):
            raise HTTPException(401, "bad initData")
        auth_date = int(parsed.get("auth_date", "0"))
        if time.time() - auth_date > 86400:
            raise HTTPException(401, "expired")
        user = json.loads(parsed.get("user", "{}"))
        return user

    @app.get("/api/mini/me")
    async def mini_me(request: Request, session: AsyncSession = Depends(get_db)):
        init_data = request.headers.get("X-Telegram-Init-Data") or request.query_params.get("initData", "")
        if not init_data:
            raise HTTPException(401, "no initData")
        tg_user = _validate_init_data(init_data)
        tg_id = tg_user.get("id")
        result = await session.execute(select(BotUser).where(BotUser.telegram_id == tg_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(404, "start the bot first")
        svc_result = await session.execute(
            select(UserService).where(UserService.bot_user_id == user.id)
        )
        services = list(svc_result.scalars().all())
        plans_result = await session.execute(
            select(Plan).where(Plan.is_active.is_(True)).order_by(Plan.sort_order)
        )
        plans = list(plans_result.scalars().all())
        return {
            "user": {
                "id": user.id,
                "name": user.full_name,
                "wallet": user.wallet_balance,
                "role": user.role,
            },
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
                    "price": p.price,
                    "days": p.duration_days,
                    "gb": p.data_limit_gb,
                }
                for p in plans
            ],
        }

    @app.get("/api/mini/service/{service_id}")
    async def mini_service(service_id: int, request: Request, session: AsyncSession = Depends(get_db)):
        init_data = request.headers.get("X-Telegram-Init-Data") or ""
        tg_user = _validate_init_data(init_data)
        result = await session.execute(select(BotUser).where(BotUser.telegram_id == tg_user.get("id")))
        user = result.scalar_one_or_none()
        svc = await session.get(UserService, service_id)
        if not user or not svc or svc.bot_user_id != user.id:
            raise HTTPException(404)
        info = {}
        if svc.subscription_token:
            try:
                info = await get_pg().subscription_info(svc.subscription_token)
            except Exception as e:
                info = {"error": str(e)}
        return {"service": {"id": svc.id, "username": svc.pg_username, "url": svc.subscription_url}, "info": info}

    return app
