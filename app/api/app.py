from __future__ import annotations

import hashlib
import hmac
import json
import time
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qsl

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from itsdangerous import BadSignature, URLSafeSerializer
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.db.models import (
    BotUser,
    Order,
    OrderStatus,
    Payment,
    PaymentStatus,
    Plan,
    ResellerProfile,
    Role,
    Ticket,
    UserService,
)
from app.db.session import SessionLocal
from app.services.orders import approve_payment, deliver_order, reject_payment
from app.services.pasarguard import get_pg, parse_group_ids
from app.services.resellers import make_reseller
from app.services.users import (
    SETTING_GROUPS,
    get_all_settings,
    set_setting,
)
from app.services.web_auth import load_web_admin, verify_web_admin
from app.api.pg_pages import register_pg_pages

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))

from app.services.formatting import format_bytes, format_gb, format_number, order_status_fa, ticket_status_fa

templates.env.filters["bytes"] = format_bytes
templates.env.filters["gb"] = format_gb
templates.env.filters["num"] = format_number
templates.env.filters["order_status"] = order_status_fa
templates.env.filters["ticket_status"] = ticket_status_fa


class NotAuthenticated(Exception):
    pass


class NotAdmin(Exception):
    pass


def render(request: Request, name: str, context: dict | None = None, status_code: int = 200):
    ctx = dict(context or {})
    return templates.TemplateResponse(request, name, ctx, status_code=status_code)


def create_api_app(lifespan=None) -> FastAPI:
    app = FastAPI(title="PGClockBot Panel", docs_url=None, redoc_url=None, lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")

    def get_signer() -> URLSafeSerializer:
        settings = get_settings()
        return URLSafeSerializer(settings.web_secret or "pgclock-secret", salt="pgclock-session")

    async def get_db():
        async with SessionLocal() as session:
            yield session

    def get_session_user(request: Request) -> Optional[dict]:
        cookie = request.cookies.get("session")
        if not cookie:
            return None
        try:
            return get_signer().loads(cookie)
        except BadSignature:
            return None

    def require_staff(request: Request) -> dict:
        user = get_session_user(request)
        if not user or user.get("role") not in {"admin", "reseller"}:
            raise NotAuthenticated()
        return user

    def require_admin(request: Request) -> dict:
        user = require_staff(request)
        if user.get("role") != "admin":
            raise NotAdmin()
        return user

    @app.exception_handler(NotAuthenticated)
    async def _unauth(request: Request, exc: NotAuthenticated):
        return RedirectResponse("/login", status_code=303)

    @app.exception_handler(NotAdmin)
    async def _not_admin(request: Request, exc: NotAdmin):
        return RedirectResponse("/dashboard", status_code=303)

    register_pg_pages(app, render=render, require_admin=require_admin, get_db=get_db)

    @app.get("/health")
    async def health():
        creds = load_web_admin()
        return {
            "ok": True,
            "web_panel": True,
            "admin_user_configured": bool(creds.get("username") and creds.get("password")),
            "admin_username": creds.get("username") or None,
        }

    @app.get("/", response_class=HTMLResponse)
    async def root(request: Request):
        user = get_session_user(request)
        if not user:
            return RedirectResponse("/login", status_code=303)
        return RedirectResponse("/dashboard", status_code=303)

    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request):
        if get_session_user(request):
            return RedirectResponse("/dashboard", status_code=303)
        creds = load_web_admin()
        hint = creds.get("username") or "admin"
        return render(request, "login.html", {"error": None, "hint_user": hint})

    @app.post("/login")
    async def login_submit(
        request: Request,
        username: str = Form(...),
        password: str = Form(...),
        session: AsyncSession = Depends(get_db),
    ):
        role = None
        display = (username or "").strip()
        u = display
        p = password or ""

        if verify_web_admin(u, p):
            role = "admin"
            display = load_web_admin()["username"]
        else:
            try:
                tg_id = int(u)
            except ValueError:
                tg_id = None
            if tg_id is not None:
                result = await session.execute(
                    select(BotUser).where(
                        BotUser.telegram_id == tg_id,
                        BotUser.role == Role.RESELLER.value,
                    )
                )
                ru = result.scalar_one_or_none()
                if ru and p == (ru.referral_code or ""):
                    role = "reseller"
                    display = ru.full_name or str(tg_id)

        if not role:
            return render(
                request,
                "login.html",
                {
                    "error": "نام کاربری یا رمز عبور اشتباه است. اگر تازه نصب کرده‌اید: python scripts/set_web_password.py",
                    "hint_user": load_web_admin().get("username") or "admin",
                },
                status_code=400,
            )

        resp = RedirectResponse("/dashboard", status_code=303)
        resp.set_cookie(
            "session",
            get_signer().dumps({"role": role, "username": display}),
            httponly=True,
            samesite="lax",
            max_age=60 * 60 * 24 * 7,
            path="/",
        )
        return resp

    @app.get("/logout")
    async def logout():
        resp = RedirectResponse("/login", status_code=303)
        resp.delete_cookie("session", path="/")
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
        plans_count = await session.scalar(
            select(func.count()).select_from(Plan).where(Plan.is_active.is_(True))
        ) or 0
        open_tickets = await session.scalar(
            select(func.count()).select_from(Ticket).where(Ticket.status == "open")
        ) or 0
        recent_payments = list(
            (
                await session.execute(
                    select(Payment).order_by(Payment.id.desc()).limit(6)
                )
            ).scalars().all()
        )
        recent_orders = list(
            (
                await session.execute(select(Order).order_by(Order.id.desc()).limit(6))
            ).scalars().all()
        )
        return render(
            request,
            "dashboard.html",
            {
                "staff": staff,
                "stats": {
                    "users": users_count,
                    "orders": orders_count,
                    "pending": pending_payments,
                    "services": services_count,
                    "revenue": revenue,
                    "plans": plans_count,
                    "tickets": open_tickets,
                },
                "recent_payments": recent_payments,
                "recent_orders": recent_orders,
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
        templates: list = []
        groups: list = []
        pg_error = None
        try:
            pg = get_pg()
            templates = await pg.get_user_templates_simple()
            full = await pg.get_user_templates()
            from app.services.pasarguard import as_list

            if isinstance(full, list) and full:
                templates = full
            else:
                templates = as_list(full, "templates") or templates
            groups = await pg.get_groups_simple()
        except Exception as e:
            pg_error = str(e)
        return render(
            request,
            "plans.html",
            {
                "staff": staff,
                "plans": plans,
                "templates": templates,
                "groups": groups,
                "pg_error": pg_error,
                "flash_err": request.query_params.get("err"),
                "flash_ok": request.query_params.get("ok"),
            },
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
        mode: str = Form("custom"),
        also_create_template: str = Form(""),
        staff: dict = Depends(require_admin),
        session: AsyncSession = Depends(get_db),
    ):
        from urllib.parse import quote

        form = await request.form()
        gb = float(data_limit_gb) if str(data_limit_gb).strip() else None
        tpl = None
        group_csv = None

        if mode == "template":
            tpl = int(pg_template_id) if str(pg_template_id).strip() else None
            if not tpl:
                return RedirectResponse(
                    f"/plans?err={quote('تمپلیت پاسارگارد را انتخاب کنید')}",
                    status_code=303,
                )
        else:
            ids = [
                int(v)
                for k, v in form.items()
                if str(k).startswith("group_") and str(v).isdigit()
            ]
            if not ids:
                return RedirectResponse(
                    f"/plans?err={quote('حداقل یک گروه پاسارگارد انتخاب کنید')}",
                    status_code=303,
                )
            group_csv = ",".join(str(i) for i in ids)
            if also_create_template:
                try:
                    created = await get_pg().create_user_template(
                        {
                            "name": name.strip(),
                            "group_ids": ids,
                            "expire_duration": duration_days * 86400,
                            "data_limit": int(gb * (1024**3)) if gb is not None else None,
                            "status": "active",
                        }
                    )
                    if isinstance(created, dict) and created.get("id"):
                        tpl = int(created["id"])
                except Exception as e:
                    return RedirectResponse(
                        f"/plans?err={quote(f'ساخت تمپلیت در پاسارگارد ناموفق: {e}')}",
                        status_code=303,
                    )

        session.add(
            Plan(
                name=name.strip(),
                price=price,
                duration_days=duration_days,
                data_limit_gb=gb,
                pg_template_id=tpl,
                pg_group_ids=group_csv,
                description=description or None,
                is_active=True,
            )
        )
        await session.commit()
        return RedirectResponse(
            f"/plans?ok={quote('پلن ذخیره شد')}",
            status_code=303,
        )

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
        return RedirectResponse("/plans", status_code=303)

    @app.post("/plans/{plan_id}/delete")
    async def plans_delete(
        plan_id: int,
        staff: dict = Depends(require_admin),
        session: AsyncSession = Depends(get_db),
    ):
        plan = await session.get(Plan, plan_id)
        if plan:
            await session.delete(plan)
            await session.commit()
        return RedirectResponse("/plans", status_code=303)

    @app.get("/orders", response_class=HTMLResponse)
    async def orders_page(
        request: Request,
        staff: dict = Depends(require_staff),
        session: AsyncSession = Depends(get_db),
    ):
        result = await session.execute(
            select(Order)
            .options(
                selectinload(Order.payment),
                selectinload(Order.plan),
                selectinload(Order.user),
            )
            .order_by(Order.id.desc())
            .limit(100)
        )
        orders = list(result.scalars().all())
        return render(
            request,
            "orders.html",
            {
                "staff": staff,
                "orders": orders,
                "flash_ok": request.query_params.get("ok"),
                "flash_err": request.query_params.get("err"),
            },
        )

    async def _notify_order_user(session: AsyncSession, payment: Payment, order: Order | None) -> None:
        user = await session.get(BotUser, payment.user_id)
        if not user:
            return
        try:
            from aiogram import Bot

            from app.services.receipts import build_approved_user_text

            text, markup = await build_approved_user_text(session, payment, order)
            bot = Bot(token=get_settings().bot_token)
            try:
                await bot.send_message(user.telegram_id, text, reply_markup=markup)
            finally:
                await bot.session.close()
        except Exception:
            pass

    @app.post("/orders/{order_id}/approve")
    async def order_approve(
        order_id: int,
        staff: dict = Depends(require_staff),
        session: AsyncSession = Depends(get_db),
    ):
        order = await session.get(Order, order_id)
        if not order:
            return RedirectResponse("/orders?err=سفارش یافت نشد", status_code=303)
        if order.status == OrderStatus.DELIVERED.value:
            return RedirectResponse("/orders?ok=قبلاً تحویل شده", status_code=303)

        result = await session.execute(
            select(Payment)
            .where(Payment.order_id == order_id)
            .order_by(Payment.id.desc())
            .limit(1)
        )
        payment = result.scalar_one_or_none()
        try:
            if payment and payment.status == PaymentStatus.PENDING.value:
                delivered = await approve_payment(session, payment, reviewer_tg=0)
                await _notify_order_user(session, payment, delivered or order)
            elif order.status == OrderStatus.PAID.value:
                delivered = await deliver_order(session, order)
                if payment:
                    await _notify_order_user(session, payment, delivered)
            elif payment and payment.status == PaymentStatus.APPROVED.value and order.status != OrderStatus.DELIVERED.value:
                delivered = await deliver_order(session, order)
                await _notify_order_user(session, payment, delivered)
            else:
                return RedirectResponse(
                    "/orders?err=این سفارش هنوز قابل تأیید نیست (رسید لازم است)",
                    status_code=303,
                )
        except Exception as e:
            return RedirectResponse(f"/orders?err={e}", status_code=303)
        return RedirectResponse("/orders?ok=سفارش تأیید و تحویل شد", status_code=303)

    @app.post("/orders/{order_id}/reject")
    async def order_reject(
        order_id: int,
        staff: dict = Depends(require_staff),
        session: AsyncSession = Depends(get_db),
    ):
        order = await session.get(Order, order_id)
        if not order:
            return RedirectResponse("/orders?err=سفارش یافت نشد", status_code=303)
        result = await session.execute(
            select(Payment)
            .where(Payment.order_id == order_id)
            .order_by(Payment.id.desc())
            .limit(1)
        )
        payment = result.scalar_one_or_none()
        if payment and payment.status == PaymentStatus.PENDING.value:
            await reject_payment(session, payment, reviewer_tg=0, note="web order reject")
            user = await session.get(BotUser, payment.user_id)
            if user:
                try:
                    from aiogram import Bot

                    from app.services.formatting import format_message

                    bot = Bot(token=get_settings().bot_token)
                    try:
                        await bot.send_message(
                            user.telegram_id,
                            format_message("❌ سفارش رد شد", f"سفارش #{order_id} رد شد."),
                        )
                    finally:
                        await bot.session.close()
                except Exception:
                    pass
        else:
            order.status = OrderStatus.REJECTED.value
            await session.commit()
        return RedirectResponse("/orders?ok=سفارش رد شد", status_code=303)

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
        if payment and payment.status == PaymentStatus.PENDING.value:
            order = await approve_payment(session, payment, reviewer_tg=0)
            user = await session.get(BotUser, payment.user_id)
            if user:
                try:
                    from aiogram import Bot

                    from app.services.receipts import build_approved_user_text

                    text, markup = await build_approved_user_text(session, payment, order)
                    bot = Bot(token=get_settings().bot_token)
                    try:
                        await bot.send_message(user.telegram_id, text, reply_markup=markup)
                    finally:
                        await bot.session.close()
                except Exception:
                    pass
        return RedirectResponse("/payments", status_code=303)

    @app.post("/payments/{payment_id}/reject")
    async def payment_reject(
        payment_id: int,
        staff: dict = Depends(require_staff),
        session: AsyncSession = Depends(get_db),
    ):
        payment = await session.get(Payment, payment_id)
        if payment:
            await reject_payment(session, payment, reviewer_tg=0, note="web reject")
            user = await session.get(BotUser, payment.user_id)
            if user:
                try:
                    from aiogram import Bot

                    from app.services.formatting import format_message

                    bot = Bot(token=get_settings().bot_token)
                    try:
                        await bot.send_message(
                            user.telegram_id,
                            format_message("❌ پرداخت رد شد", f"پرداخت #{payment.id} رد شد."),
                        )
                    finally:
                        await bot.session.close()
                except Exception:
                    pass
        return RedirectResponse("/payments", status_code=303)

    @app.get("/users", response_class=HTMLResponse)
    async def users_page(
        request: Request,
        staff: dict = Depends(require_admin),
        session: AsyncSession = Depends(get_db),
    ):
        result = await session.execute(select(BotUser).order_by(BotUser.id.desc()).limit(200))
        users = list(result.scalars().all())
        return render(
            request,
            "users.html",
            {
                "staff": staff,
                "users": users,
                "flash_ok": request.query_params.get("ok"),
                "flash_err": request.query_params.get("err"),
            },
        )

    @app.post("/users/{user_id}/role")
    async def users_set_role(
        user_id: int,
        role: str = Form(...),
        staff: dict = Depends(require_admin),
        session: AsyncSession = Depends(get_db),
    ):
        from urllib.parse import quote

        user = await session.get(BotUser, user_id)
        if not user:
            return RedirectResponse(f"/users?err={quote('کاربر یافت نشد')}", status_code=303)
        if role not in {Role.USER.value, Role.RESELLER.value, Role.ADMIN.value}:
            return RedirectResponse(f"/users?err={quote('نقش نامعتبر')}", status_code=303)
        if role == Role.RESELLER.value:
            await make_reseller(session, user, commission_percent=10, can_approve_receipts=False)
        else:
            user.role = role
            await session.commit()
        return RedirectResponse(f"/users?ok={quote('نقش به‌روز شد')}", status_code=303)

    @app.post("/users/{user_id}/block")
    async def users_toggle_block(
        user_id: int,
        staff: dict = Depends(require_admin),
        session: AsyncSession = Depends(get_db),
    ):
        from urllib.parse import quote

        user = await session.get(BotUser, user_id)
        if user:
            user.is_blocked = not user.is_blocked
            await session.commit()
        return RedirectResponse(f"/users?ok={quote('وضعیت مسدودی تغییر کرد')}", status_code=303)

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
        pg_admin_username: str = Form(""),
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
                pg_admin_username=(pg_admin_username.strip() or None),
            )
        return RedirectResponse("/resellers", status_code=303)

    @app.get("/menu-layout", response_class=HTMLResponse)
    async def menu_layout_page(
        request: Request,
        staff: dict = Depends(require_admin),
        session: AsyncSession = Depends(get_db),
    ):
        from app.bot.keyboards import DEFAULT_MENU_ORDER

        values = await get_all_settings(session)
        order_raw = values.get("menu_order") or ",".join(DEFAULT_MENU_ORDER)
        order = [p.strip() for p in order_raw.split(",") if p.strip()]
        order = [k for k in order if k in DEFAULT_MENU_ORDER]
        if "shop" not in order:
            order.insert(0, "shop")

        catalog_meta = {
            "shop": {"label": "خرید سرویس", "required": True},
            "services": {"label": "سرویس‌های من", "required": False},
            "wallet": {"label": "کیف پول", "required": False},
            "support": {"label": "پشتیبانی", "required": False},
            "guide": {"label": "راهنما", "required": False},
            "faq": {"label": "سوالات متداول", "required": False},
            "referral": {"label": "دعوت دوستان", "required": False},
            "miniapp": {"label": "مینی‌اپ", "required": False},
        }
        catalog = {}
        for key, meta in catalog_meta.items():
            catalog[key] = {
                "label": meta["label"],
                "btn": values.get(f"btn_{key}", meta["label"]),
                "required": meta["required"],
            }

        items = []
        for key in order:
            items.append(
                {
                    "key": key,
                    "label": catalog[key]["label"],
                    "btn": catalog[key]["btn"],
                    "required": catalog[key]["required"],
                }
            )
        pool = []
        for key in DEFAULT_MENU_ORDER:
            if key not in order and key != "shop":
                pool.append(
                    {
                        "key": key,
                        "label": catalog[key]["label"],
                        "btn": catalog[key]["btn"],
                        "required": False,
                    }
                )
        return render(
            request,
            "menu_layout.html",
            {
                "staff": staff,
                "values": values,
                "items": items,
                "pool": pool,
                "catalog": catalog,
                "order_csv": ",".join(order),
                "saved": request.query_params.get("saved") == "1",
            },
        )

    @app.post("/menu-layout")
    async def menu_layout_save(
        request: Request,
        staff: dict = Depends(require_admin),
        session: AsyncSession = Depends(get_db),
    ):
        from app.bot.keyboards import DEFAULT_MENU_ORDER

        form = await request.form()
        order = [p.strip() for p in str(form.get("menu_order") or "").split(",") if p.strip()]
        order = [k for k in order if k in DEFAULT_MENU_ORDER]
        if "shop" not in order:
            order.insert(0, "shop")
        layout = str(form.get("menu_layout") or "classic").strip()
        await set_setting(session, "menu_order", ",".join(order))
        if layout in {"classic", "compact"}:
            await set_setting(session, "menu_layout", layout)
        # visibility follows presence in active menu
        for key in ("wallet", "support", "guide", "faq", "referral", "miniapp", "services"):
            await set_setting(session, f"show_{key}", "1" if key in order else "0")
        return RedirectResponse("/menu-layout?saved=1", status_code=303)

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
        from app.services.users import TOGGLE_KEYS

        form = await request.form()
        known = {item[0] for fields in SETTING_GROUPS.values() for item in fields}
        for key in TOGGLE_KEYS:
            if key in known:
                await set_setting(session, key, "1" if form.get(f"s_{key}") else "0")
        for key in known:
            if key in TOGGLE_KEYS:
                continue
            raw = form.get(f"s_{key}")
            if raw is not None:
                await set_setting(session, key, str(raw))
        return RedirectResponse("/settings?saved=1", status_code=303)

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
