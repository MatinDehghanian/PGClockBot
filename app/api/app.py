from __future__ import annotations

import hashlib
import hmac
import json
import time
from collections import defaultdict
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qsl, quote

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from itsdangerous import BadSignature, URLSafeSerializer
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import DATA_DIR, get_settings
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
from app.services.setup_wizard import (
    begin_setup,
    current_setup_values,
    ensure_web_secret,
    is_setup_complete,
    mark_setup_complete,
    panel_url_hint,
    parse_admin_ids,
    update_env_keys,
)
from app.services.updates import check_github_update, local_version
from app.services.users import (
    IMAGE_KEYS,
    SETTING_GROUPS,
    SETTINGS_TABS,
    TAB_SETTING_GROUPS,
    get_all_settings,
    set_setting,
)
from app.services.web_auth import (
    load_web_admin,
    save_web_admin,
    validate_password_strength,
    verify_web_admin,
)
from app.api.pg_pages import register_pg_pages

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))

from app.services.formatting import format_bytes, format_gb, format_number, order_status_fa, ticket_status_fa

templates.env.filters["bytes"] = format_bytes
templates.env.filters["gb"] = format_gb
templates.env.filters["num"] = format_number
templates.env.filters["order_status"] = order_status_fa
templates.env.filters["ticket_status"] = ticket_status_fa
templates.env.globals["app_version"] = local_version()
templates.env.globals["order_status_fa"] = order_status_fa
templates.env.globals["ticket_status_fa"] = ticket_status_fa

# Login brute-force tracking: ip -> list of failure timestamps
_LOGIN_FAILURES: dict[str, list[float]] = defaultdict(list)
_LOGIN_WINDOW_SEC = 15 * 60
_LOGIN_MAX_FAILURES = 8


class NotAuthenticated(Exception):
    pass


class NotAdmin(Exception):
    pass


def render(request: Request, name: str, context: dict | None = None, status_code: int = 200):
    ctx = dict(context or {})
    ctx.setdefault("flash_ok", None)
    ctx.setdefault("flash_err", None)
    ctx.setdefault("app_version", local_version())
    return templates.TemplateResponse(request, name, ctx, status_code=status_code)


def _redirect_msg(path: str, *, ok: str | None = None, err: str | None = None) -> RedirectResponse:
    q = []
    if ok:
        q.append(f"ok={quote(ok)}")
    if err:
        q.append(f"err={quote(err)}")
    url = path if not q else f"{path}?{'&'.join(q)}"
    return RedirectResponse(url, status_code=303)


def _client_ip(request: Request) -> str:
    fwd = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    if fwd:
        return fwd
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _login_blocked(ip: str) -> bool:
    now = time.time()
    stamps = [t for t in _LOGIN_FAILURES.get(ip, []) if now - t < _LOGIN_WINDOW_SEC]
    _LOGIN_FAILURES[ip] = stamps
    return len(stamps) >= _LOGIN_MAX_FAILURES


def _login_fail(ip: str) -> None:
    now = time.time()
    stamps = [t for t in _LOGIN_FAILURES.get(ip, []) if now - t < _LOGIN_WINDOW_SEC]
    stamps.append(now)
    _LOGIN_FAILURES[ip] = stamps


def _login_success(ip: str) -> None:
    _LOGIN_FAILURES.pop(ip, None)


def _cookie_secure(request: Request) -> bool:
    fwd = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
    return request.url.scheme == "https" or fwd == "https"


def create_api_app(lifespan=None) -> FastAPI:
    app = FastAPI(title="PGClockBot Panel", docs_url=None, redoc_url=None, lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "uploads").mkdir(parents=True, exist_ok=True)
    app.mount("/media", StaticFiles(directory=str(DATA_DIR)), name="media")

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

    @app.middleware("http")
    async def setup_gate(request: Request, call_next):
        path = request.url.path
        complete = is_setup_complete()

        if complete:
            if path == "/setup" or path.startswith("/setup/"):
                return RedirectResponse("/", status_code=303)
            return await call_next(request)

        # First-run: only wizard + static/health. Everything else → /
        allowed = (
            path == "/"
            or path == "/setup"
            or path.startswith("/setup/")
            or path.startswith("/static")
            or path == "/health"
        )
        if allowed:
            return await call_next(request)
        return RedirectResponse("/", status_code=303)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        # Panel pages only; keep CSP moderate so inline preview/scripts still work
        if not request.url.path.startswith("/static") and not request.url.path.startswith("/media"):
            response.headers.setdefault(
                "Content-Security-Policy",
                "default-src 'self'; img-src 'self' data: blob:; "
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                "script-src 'self' 'unsafe-inline'; "
                "font-src 'self' data: https://fonts.gstatic.com; connect-src 'self'; "
                "frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
            )
        if _cookie_secure(request):
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response

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
            "setup_complete": is_setup_complete(),
        }

    # -------- Setup wizard --------
    def _setup_page(request: Request, *, step: int = 0, err: str | None = None, ok: str | None = None, show_done: bool = False):
        begin_setup()
        values = current_setup_values()
        return render(
            request,
            "setup.html",
            {
                "values": values,
                "initial_step": step,
                "show_done": show_done,
                "flash_err": err or request.query_params.get("err"),
                "flash_ok": ok or request.query_params.get("ok"),
                "panel_url": panel_url_hint(values.get("PUBLIC_BASE_URL", ""), values.get("WEB_PORT", "9000")),
                "bot_username": (values.get("BOT_USERNAME") or "").lstrip("@"),
            },
        )

    @app.get("/setup", response_class=HTMLResponse)
    async def setup_page(request: Request):
        if is_setup_complete():
            return RedirectResponse("/", status_code=303)
        step = 0
        try:
            step = int(request.query_params.get("step") or "0")
        except ValueError:
            step = 0
        show_done = step >= 4
        return _setup_page(request, step=step if step < 4 else 4, show_done=show_done)

    @app.post("/setup/admin")
    async def setup_admin(
        request: Request,
        username: str = Form(...),
        password: str = Form(...),
        password_confirm: str = Form(...),
    ):
        if is_setup_complete():
            return RedirectResponse("/", status_code=303)
        begin_setup()
        user = (username or "").strip() or "admin"
        p1 = password or ""
        p2 = password_confirm or ""
        if p1 != p2:
            return _setup_page(request, step=1, err="رمز عبور و تکرار آن یکسان نیستند.")
        ok, msg = validate_password_strength(p1)
        if not ok:
            return _setup_page(request, step=1, err=msg)
        try:
            save_web_admin(user, p1)
        except ValueError as e:
            return _setup_page(request, step=1, err=str(e))
        ensure_web_secret()
        update_env_keys({"WEB_ADMIN_USER": user})
        return RedirectResponse("/setup?step=2", status_code=303)

    @app.post("/setup/bot")
    async def setup_bot(
        request: Request,
        bot_token: str = Form(...),
        bot_username: str = Form(""),
        admin_ids: str = Form(...),
    ):
        if is_setup_complete():
            return RedirectResponse("/", status_code=303)
        begin_setup()
        token = (bot_token or "").strip()
        uname = (bot_username or "").strip().lstrip("@")
        ids_raw = (admin_ids or "").strip()
        if not token:
            return _setup_page(request, step=2, err="توکن ربات الزامی است.")
        if not uname:
            return _setup_page(request, step=2, err="نام کاربری ربات الزامی است.")
        try:
            ids = parse_admin_ids(ids_raw)
        except ValueError:
            return _setup_page(request, step=2, err="آیدی ادمین‌ها باید عدد باشد (با کاما جدا کنید).")
        if not ids:
            return _setup_page(request, step=2, err="حداقل یک آیدی ادمین وارد کنید.")
        update_env_keys(
            {
                "BOT_TOKEN": token,
                "BOT_USERNAME": uname,
                "ADMIN_IDS": ",".join(str(i) for i in ids),
            }
        )
        ensure_web_secret()
        return RedirectResponse("/setup?step=3", status_code=303)

    @app.post("/setup/other")
    async def setup_other(
        request: Request,
        pg_base_url: str = Form(...),
        pg_username: str = Form(""),
        pg_password: str = Form(""),
        web_port: str = Form("9000"),
        public_base_url: str = Form(""),
        currency: str = Form("تومان"),
    ):
        if is_setup_complete():
            return RedirectResponse("/", status_code=303)
        begin_setup()
        base = (pg_base_url or "").strip()
        if not base:
            return _setup_page(request, step=3, err="آدرس پاسارگارد الزامی است.")
        if not (pg_username or "").strip():
            return _setup_page(request, step=3, err="نام کاربری پاسارگارد الزامی است.")
        if not (pg_password or "").strip():
            return _setup_page(request, step=3, err="رمز پاسارگارد الزامی است.")
        port = (web_port or "9000").strip()
        try:
            port_n = int(port)
            if port_n < 1 or port_n > 65535:
                raise ValueError
        except ValueError:
            return _setup_page(request, step=3, err="پورت وب نامعتبر است.")
        ensure_web_secret()
        update_env_keys(
            {
                "PG_BASE_URL": base,
                "PG_USERNAME": (pg_username or "").strip(),
                "PG_PASSWORD": (pg_password or "").strip(),
                "WEB_PORT": str(port_n),
                "PUBLIC_BASE_URL": (public_base_url or "").strip().rstrip("/"),
                "CURRENCY": (currency or "").strip() or "تومان",
            }
        )
        return RedirectResponse("/setup?step=4", status_code=303)

    @app.post("/setup/finish")
    async def setup_finish():
        mark_setup_complete()
        ensure_web_secret()
        from app.services.service_control import schedule_panel_restart

        schedule_panel_restart(delay_sec=2.5, reason="setup wizard finished")
        return RedirectResponse("/login?restarting=1", status_code=303)

    @app.get("/", response_class=HTMLResponse)
    async def root(request: Request):
        """Single entry URL: first-run → setup wizard, otherwise login/dashboard."""
        if not is_setup_complete():
            step = 0
            try:
                step = int(request.query_params.get("step") or "0")
            except ValueError:
                step = 0
            show_done = step >= 4
            return _setup_page(request, step=step if step < 4 else 4, show_done=show_done)
        user = get_session_user(request)
        if not user:
            return RedirectResponse("/login", status_code=303)
        return RedirectResponse("/dashboard", status_code=303)

    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request):
        if not is_setup_complete():
            return RedirectResponse("/", status_code=303)
        if get_session_user(request):
            return RedirectResponse("/dashboard", status_code=303)
        creds = load_web_admin()
        hint = creds.get("username") or "admin"
        return render(
            request,
            "login.html",
            {
                "error": None,
                "hint_user": hint,
                "flash_ok": request.query_params.get("ok"),
            },
        )

    @app.post("/login")
    async def login_submit(
        request: Request,
        username: str = Form(...),
        password: str = Form(...),
        session: AsyncSession = Depends(get_db),
    ):
        if not is_setup_complete():
            return RedirectResponse("/", status_code=303)

        ip = _client_ip(request)
        if _login_blocked(ip):
            return render(
                request,
                "login.html",
                {
                    "error": "تعداد تلاش‌های ناموفق زیاد است. ۱۵ دقیقه دیگر دوباره تلاش کنید.",
                    "hint_user": load_web_admin().get("username") or "admin",
                },
                status_code=429,
            )

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
            _login_fail(ip)
            return render(
                request,
                "login.html",
                {
                    "error": "نام کاربری یا رمز عبور اشتباه است. اگر تازه نصب کرده‌اید: python scripts/set_web_password.py",
                    "hint_user": load_web_admin().get("username") or "admin",
                },
                status_code=400,
            )

        _login_success(ip)
        resp = RedirectResponse("/dashboard", status_code=303)
        resp.set_cookie(
            "session",
            get_signer().dumps({"role": role, "username": display}),
            httponly=True,
            samesite="lax",
            secure=_cookie_secure(request),
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
        update = await check_github_update()
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
                "update": update,
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

    async def _plans_context(session: AsyncSession, request: Request, staff: dict, extra: dict | None = None):
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
        ctx = {
            "staff": staff,
            "plans": plans,
            "templates": templates,
            "groups": groups,
            "pg_error": pg_error,
            "flash_err": request.query_params.get("err"),
            "flash_ok": request.query_params.get("ok"),
        }
        if extra:
            ctx.update(extra)
        return ctx

    @app.get("/plans/{plan_id}/edit", response_class=HTMLResponse)
    async def plans_edit_page(
        plan_id: int,
        request: Request,
        staff: dict = Depends(require_admin),
        session: AsyncSession = Depends(get_db),
    ):
        plan = await session.get(Plan, plan_id)
        if not plan:
            return RedirectResponse("/plans?err=" + quote("پلن یافت نشد"), status_code=303)
        ctx = await _plans_context(session, request, staff, {"plan": plan})
        return render(request, "plan_edit.html", ctx)

    @app.post("/plans/{plan_id}/edit")
    async def plans_edit_save(
        plan_id: int,
        request: Request,
        name: str = Form(...),
        price: int = Form(...),
        duration_days: int = Form(30),
        data_limit_gb: str = Form(""),
        pg_template_id: str = Form(""),
        description: str = Form(""),
        mode: str = Form("custom"),
        sort_order: int = Form(0),
        staff: dict = Depends(require_admin),
        session: AsyncSession = Depends(get_db),
    ):
        plan = await session.get(Plan, plan_id)
        if not plan:
            return RedirectResponse("/plans?err=" + quote("پلن یافت نشد"), status_code=303)

        form = await request.form()
        gb = float(data_limit_gb) if str(data_limit_gb).strip() else None
        tpl = None
        group_csv = None

        if mode == "template":
            tpl = int(pg_template_id) if str(pg_template_id).strip() else None
            if not tpl:
                return RedirectResponse(
                    f"/plans/{plan_id}/edit?err={quote('تمپلیت پاسارگارد را انتخاب کنید')}",
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
                    f"/plans/{plan_id}/edit?err={quote('حداقل یک گروه پاسارگارد انتخاب کنید')}",
                    status_code=303,
                )
            group_csv = ",".join(str(i) for i in ids)

        plan.name = name.strip()
        plan.price = price
        plan.duration_days = duration_days
        plan.data_limit_gb = gb
        plan.description = description or None
        plan.sort_order = sort_order
        plan.pg_template_id = tpl
        plan.pg_group_ids = group_csv
        await session.commit()
        return RedirectResponse(
            f"/plans?ok={quote('پلن به‌روزرسانی شد')}",
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
                selectinload(Order.plan),
                selectinload(Order.user),
            )
            .order_by(Order.id.desc())
            .limit(100)
        )
        orders = list(result.scalars().all())
        payments_by_order: dict[int, Payment] = {}
        if orders:
            ids = [o.id for o in orders]
            pay_rows = (
                await session.execute(
                    select(Payment)
                    .where(Payment.order_id.in_(ids))
                    .order_by(Payment.id.desc())
                )
            ).scalars().all()
            for p in pay_rows:
                if p.order_id is not None and p.order_id not in payments_by_order:
                    payments_by_order[p.order_id] = p
        return render(
            request,
            "orders.html",
            {
                "staff": staff,
                "orders": orders,
                "payments_by_order": payments_by_order,
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

            from app.services.delivery import send_delivery_to_user
            from app.services.notifications import notify_new_subscription, notify_wallet_topup_ok

            bot = Bot(token=get_settings().bot_token)
            try:
                await send_delivery_to_user(
                    bot, user.telegram_id, session, payment, order
                )
                if payment.is_wallet_topup:
                    await notify_wallet_topup_ok(bot, session, payment, user.telegram_id)
                elif order:
                    plan = await session.get(Plan, order.plan_id) if order.plan_id else None
                    await notify_new_subscription(
                        bot,
                        session,
                        order=order,
                        user_tg_id=user.telegram_id,
                        user_name=user.full_name or user.username,
                        plan_name=plan.name if plan else None,
                        needs_approval=False,
                    )
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
            return _redirect_msg("/orders", err="سفارش یافت نشد")
        if order.status == OrderStatus.DELIVERED.value:
            return _redirect_msg("/orders", ok="قبلاً تحویل شده")

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
                return _redirect_msg("/orders", err="این سفارش هنوز قابل تأیید نیست (رسید لازم است)")
        except Exception as e:
            return _redirect_msg("/orders", err=str(e))
        return _redirect_msg("/orders", ok="سفارش تأیید و تحویل شد")

    @app.post("/orders/{order_id}/reject")
    async def order_reject(
        order_id: int,
        staff: dict = Depends(require_staff),
        session: AsyncSession = Depends(get_db),
    ):
        order = await session.get(Order, order_id)
        if not order:
            return _redirect_msg("/orders", err="سفارش یافت نشد")
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
        return _redirect_msg("/orders", ok="سفارش رد شد")

    @app.get("/payments", response_class=HTMLResponse)
    async def payments_page(
        request: Request,
        staff: dict = Depends(require_staff),
        session: AsyncSession = Depends(get_db),
    ):
        result = await session.execute(select(Payment).order_by(Payment.id.desc()).limit(100))
        payments = list(result.scalars().all())
        return render(
            request,
            "payments.html",
            {
                "staff": staff,
                "payments": payments,
                "flash_ok": request.query_params.get("ok"),
                "flash_err": request.query_params.get("err"),
            },
        )

    @app.get("/payments/{payment_id}/approve")
    async def payment_approve_get(payment_id: int):
        return _redirect_msg("/payments", err="برای تأیید از دکمه داخل صفحه پرداخت‌ها استفاده کنید")

    @app.post("/payments/{payment_id}/approve")
    async def payment_approve(
        payment_id: int,
        staff: dict = Depends(require_staff),
        session: AsyncSession = Depends(get_db),
    ):
        payment = await session.get(Payment, payment_id)
        if not payment:
            return _redirect_msg("/payments", err="پرداخت یافت نشد")
        if payment.status != PaymentStatus.PENDING.value:
            return _redirect_msg("/payments", err="این پرداخت قابل تأیید نیست")
        try:
            order = await approve_payment(session, payment, reviewer_tg=0)
        except Exception as e:
            return _redirect_msg("/payments", err=str(e))
        user = await session.get(BotUser, payment.user_id)
        if user:
            try:
                from aiogram import Bot

                from app.services.delivery import send_delivery_to_user
                from app.services.notifications import notify_new_subscription, notify_wallet_topup_ok

                bot = Bot(token=get_settings().bot_token)
                try:
                    await send_delivery_to_user(
                        bot, user.telegram_id, session, payment, order
                    )
                    if payment.is_wallet_topup:
                        await notify_wallet_topup_ok(bot, session, payment, user.telegram_id)
                    elif order:
                        plan = await session.get(Plan, order.plan_id) if order.plan_id else None
                        await notify_new_subscription(
                            bot,
                            session,
                            order=order,
                            user_tg_id=user.telegram_id,
                            user_name=user.full_name or user.username,
                            plan_name=plan.name if plan else None,
                            needs_approval=False,
                        )
                finally:
                    await bot.session.close()
            except Exception:
                pass
        return _redirect_msg("/payments", ok="پرداخت تأیید شد")

    @app.post("/payments/{payment_id}/reject")
    async def payment_reject(
        payment_id: int,
        staff: dict = Depends(require_staff),
        session: AsyncSession = Depends(get_db),
    ):
        payment = await session.get(Payment, payment_id)
        if not payment:
            return _redirect_msg("/payments", err="پرداخت یافت نشد")
        try:
            await reject_payment(session, payment, reviewer_tg=0, note="web reject")
        except Exception as e:
            return _redirect_msg("/payments", err=str(e))
        user = await session.get(BotUser, payment.user_id)
        if user:
            try:
                from aiogram import Bot

                from app.services.formatting import format_message

                ui = await get_all_settings(session)
                body = ui.get("payment_reject_text") or (
                    "پرداخت شما رد شد. اگر اشتباهی رخ داده با پشتیبانی در تماس باشید."
                )
                bot = Bot(token=get_settings().bot_token)
                try:
                    await bot.send_message(
                        user.telegram_id,
                        format_message("❌ پرداخت رد شد", body),
                    )
                finally:
                    await bot.session.close()
            except Exception:
                pass
        return _redirect_msg("/payments", ok="پرداخت رد شد")

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
    async def menu_layout_page(staff: dict = Depends(require_admin)):
        return RedirectResponse("/settings?tab=menu", status_code=303)

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
        for key in ("wallet", "support", "guide", "faq", "referral", "miniapp", "services"):
            await set_setting(session, f"show_{key}", "1" if key in order else "0")
        return RedirectResponse("/settings?tab=menu&saved=1", status_code=303)

    @app.get("/update", response_class=HTMLResponse)
    async def update_page(
        request: Request,
        staff: dict = Depends(require_admin),
    ):
        q = "tab=update"
        if request.query_params.get("force") == "1":
            q += "&force=1"
        return RedirectResponse(f"/settings?{q}", status_code=303)

    @app.get("/update/status")
    async def update_status(staff: dict = Depends(require_admin)):
        from app.services.panel_update import read_status
        from app.services.updates import local_version

        st = read_status()
        st["current_version"] = local_version()
        return st

    @app.post("/update/start")
    async def update_start(
        request: Request,
        staff: dict = Depends(require_admin),
    ):
        from app.services.panel_update import start_update
        from app.services.updates import check_github_update, clear_update_cache

        body = {}
        try:
            body = await request.json()
        except Exception:
            body = {}
        clear_update_cache()
        info = await check_github_update(force=True)
        target = (body or {}).get("target") or info.get("remote_version")
        if not info.get("update_available") and not (body or {}).get("force"):
            from app.services.panel_update import read_status

            st = read_status()
            if st.get("state") != "error":
                return {"ok": False, "error": "نسخه جدیدی برای آپدیت نیست", "info": info}
        result = start_update(target_version=target)
        return result

    @app.post("/update/rollback")
    async def update_rollback(
        request: Request,
        staff: dict = Depends(require_admin),
    ):
        from app.services.panel_update import start_rollback

        body = {}
        try:
            body = await request.json()
        except Exception:
            body = {}
        snapshot_id = str((body or {}).get("snapshot_id") or "").strip()
        if not snapshot_id:
            return {"ok": False, "error": "نقطه بازگشت مشخص نشده"}
        return start_rollback(snapshot_id)

    @app.get("/notifications", response_class=HTMLResponse)
    async def notifications_page(staff: dict = Depends(require_admin)):
        return RedirectResponse("/settings?tab=notifications", status_code=303)

    @app.post("/notifications")
    async def notifications_save(
        request: Request,
        staff: dict = Depends(require_admin),
        session: AsyncSession = Depends(get_db),
    ):
        from app.services.notifications import save_notify_prefs

        form = await request.form()
        await save_notify_prefs(session, dict(form))
        return RedirectResponse("/settings?tab=notifications&saved=1", status_code=303)

    def _menu_tab_context(values: dict) -> dict:
        from app.bot.keyboards import DEFAULT_MENU_ORDER

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
        items = []
        for key in order:
            meta = catalog_meta[key]
            items.append(
                {
                    "key": key,
                    "label": meta["label"],
                    "btn": values.get(f"btn_{key}", meta["label"]),
                    "required": meta["required"],
                }
            )
        pool = []
        for key in DEFAULT_MENU_ORDER:
            if key not in order and key != "shop":
                meta = catalog_meta[key]
                pool.append(
                    {
                        "key": key,
                        "label": meta["label"],
                        "btn": values.get(f"btn_{key}", meta["label"]),
                        "required": False,
                    }
                )
        return {"items": items, "pool": pool, "order_csv": ",".join(order)}

    @app.get("/settings", response_class=HTMLResponse)
    async def settings_page(
        request: Request,
        staff: dict = Depends(require_admin),
        session: AsyncSession = Depends(get_db),
    ):
        from app.services.notifications import NOTIFY_PREFS, get_notify_prefs
        from app.services.panel_update import update_page_context
        from app.services.updates import check_github_update, clear_update_cache

        tab = (request.query_params.get("tab") or "welcome").strip()
        valid = {t[0] for t in SETTINGS_TABS}
        if tab not in valid:
            tab = "menu"

        values = await get_all_settings(session)
        tab_groups = TAB_SETTING_GROUPS.get(tab, [])
        groups = {name: SETTING_GROUPS[name] for name in tab_groups if name in SETTING_GROUPS}

        ctx: dict = {
            "staff": staff,
            "values": values,
            "groups": groups,
            "tab_groups": tab_groups,
            "tabs": SETTINGS_TABS,
            "tab": tab,
            "saved": request.query_params.get("saved") == "1",
            "saved_msg": request.query_params.get("msg") or "",
        }

        if tab == "menu":
            ctx.update(_menu_tab_context(values))
        elif tab == "notifications":
            prefs = await get_notify_prefs(session)
            ctx["notify_prefs"] = prefs
            ctx["notify_items"] = NOTIFY_PREFS
        elif tab == "update":
            if request.query_params.get("force") == "1":
                clear_update_cache()
                await check_github_update(force=True)
            ctx.update(await update_page_context())
        elif tab == "bot":
            from app.services.setup_wizard import current_setup_values

            env_values = current_setup_values()
            ctx["env_values"] = env_values
            ctx["bot_status"] = await _bot_token_status(env_values.get("BOT_TOKEN") or "")

        return render(request, "settings.html", ctx)

    async def _bot_token_status(token: str) -> dict:
        token = (token or "").strip()
        if not token:
            return {"ok": False, "error": "توکن تنظیم نشده"}
        try:
            import httpx

            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(f"https://api.telegram.org/bot{token}/getMe")
                data = resp.json()
            if data.get("ok") and isinstance(data.get("result"), dict):
                me = data["result"]
                return {
                    "ok": True,
                    "username": me.get("username"),
                    "id": me.get("id"),
                    "name": me.get("first_name"),
                }
            return {"ok": False, "error": data.get("description") or "توکن نامعتبر"}
        except Exception as exc:
            return {"ok": False, "error": f"عدم اتصال به تلگرام: {exc}"}

    @app.post("/settings")
    async def settings_save(
        request: Request,
        staff: dict = Depends(require_admin),
        session: AsyncSession = Depends(get_db),
    ):
        import uuid

        from starlette.datastructures import UploadFile

        from app.services.users import TOGGLE_KEYS

        tab = (request.query_params.get("tab") or "welcome").strip()
        form = await request.form()

        if tab == "bot":
            from app.services.service_control import schedule_panel_restart
            from app.services.setup_wizard import parse_admin_ids

            token = str(form.get("BOT_TOKEN") or "").strip()
            uname = str(form.get("BOT_USERNAME") or "").strip().lstrip("@")
            ids_raw = str(form.get("ADMIN_IDS") or "").strip()
            pg_base = str(form.get("PG_BASE_URL") or "").strip()
            pg_user = str(form.get("PG_USERNAME") or "").strip()
            pg_pass = str(form.get("PG_PASSWORD") or "").strip()
            web_port = str(form.get("WEB_PORT") or "9000").strip()
            public_base = str(form.get("PUBLIC_BASE_URL") or "").strip().rstrip("/")
            currency = str(form.get("CURRENCY") or "").strip() or "تومان"
            if not token or not uname or not ids_raw or not pg_base or not pg_user or not pg_pass:
                return RedirectResponse(
                    "/settings?tab=bot&err=" + quote("همه فیلدهای الزامی را پر کنید"),
                    status_code=303,
                )
            try:
                ids = parse_admin_ids(ids_raw)
            except ValueError:
                return RedirectResponse(
                    "/settings?tab=bot&err=" + quote("آیدی ادمین‌ها نامعتبر است"),
                    status_code=303,
                )
            if not ids:
                return RedirectResponse(
                    "/settings?tab=bot&err=" + quote("حداقل یک آیدی ادمین لازم است"),
                    status_code=303,
                )
            try:
                port_n = int(web_port)
                if port_n < 1 or port_n > 65535:
                    raise ValueError
            except ValueError:
                return RedirectResponse(
                    "/settings?tab=bot&err=" + quote("پورت نامعتبر است"),
                    status_code=303,
                )
            update_env_keys(
                {
                    "BOT_TOKEN": token,
                    "BOT_USERNAME": uname,
                    "ADMIN_IDS": ",".join(str(i) for i in ids),
                    "PG_BASE_URL": pg_base,
                    "PG_USERNAME": pg_user,
                    "PG_PASSWORD": pg_pass,
                    "WEB_PORT": str(port_n),
                    "PUBLIC_BASE_URL": public_base,
                    "CURRENCY": currency,
                }
            )
            ensure_web_secret()
            schedule_panel_restart(delay_sec=2.5, reason="bot settings saved")
            return RedirectResponse(
                "/settings?tab=bot&restarting=1",
                status_code=303,
            )

        known = {item[0] for fields in SETTING_GROUPS.values() for item in fields}
        for key in TOGGLE_KEYS:
            if key in known:
                await set_setting(session, key, "1" if form.get(f"s_{key}") else "0")
        for key in known:
            if key in TOGGLE_KEYS or key in IMAGE_KEYS:
                continue
            raw = form.get(f"s_{key}")
            if raw is not None and not isinstance(raw, UploadFile):
                await set_setting(session, key, str(raw))
        uploads = DATA_DIR / "uploads"
        uploads.mkdir(parents=True, exist_ok=True)
        for key in IMAGE_KEYS:
            if key not in known:
                continue
            if form.get(f"s_{key}_clear"):
                await set_setting(session, key, "")
                continue
            upload = form.get(f"s_{key}")
            if isinstance(upload, UploadFile) and upload.filename:
                name = upload.filename.lower()
                ext = Path(name).suffix
                if ext not in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
                    continue
                dest_name = f"{key}_{uuid.uuid4().hex[:10]}{ext}"
                dest = uploads / dest_name
                content = await upload.read()
                if content:
                    dest.write_bytes(content)
                    await set_setting(session, key, f"uploads/{dest_name}")
        return RedirectResponse(f"/settings?tab={tab}&saved=1", status_code=303)

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
