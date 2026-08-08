"""Finance hub: orders + payments tabs and domain settings modal."""

from __future__ import annotations

from urllib.parse import quote, urlencode

from fastapi import Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import BotUser, Order, Payment
from app.services.authz import authz_from_staff, can_shop
from app.services.list_query import filter_by_search, normalize_search_q
from app.services.shop_scope import is_platform_admin, shop_owner_id
from app.services.users import SETTING_GROUPS, TAB_SETTING_GROUPS, get_all_settings


def _groups_for_tab(tab: str) -> tuple[list[str], dict]:
    tab_groups = TAB_SETTING_GROUPS.get(tab, [])
    groups = {name: SETTING_GROUPS[name] for name in tab_groups if name in SETTING_GROUPS}
    return tab_groups, groups


def register_finance_pages(app, *, render, require_staff, get_db):
    @app.get("/finance", response_class=HTMLResponse)
    async def finance_page(
        request: Request,
        staff: dict = Depends(require_staff),
        session: AsyncSession = Depends(get_db),
    ):
        authz = authz_from_staff(staff)
        can_orders = can_shop(authz, "orders")
        can_payments = can_shop(authz, "payments")
        if not (can_orders or can_payments):
            return RedirectResponse("/home", status_code=303)

        can_finance_settings = staff.get("role") == "admin" or can_shop(authz, "shop_settings")
        can_billing_settings = staff.get("role") == "admin"

        tab = (request.query_params.get("tab") or "").strip()
        if tab not in {"orders", "payments"}:
            tab = "orders" if can_orders else "payments"
        if tab == "orders" and not can_orders:
            tab = "payments"
        if tab == "payments" and not can_payments:
            tab = "orders"

        search_q = normalize_search_q(request.query_params.get("q"))
        open_settings = (request.query_params.get("settings") or "").strip()
        if open_settings not in {"payment", "billing"}:
            open_settings = ""
        if open_settings == "billing" and not can_billing_settings:
            open_settings = "payment" if can_finance_settings else ""
        if open_settings and not can_finance_settings:
            open_settings = ""

        ctx: dict = {
            "staff": staff,
            "finance_tab": tab,
            "can_orders": can_orders,
            "can_payments": can_payments,
            "can_finance_settings": can_finance_settings,
            "can_billing_settings": can_billing_settings and can_finance_settings,
            "can_pending_orders": staff.get("role") == "admin",
            "open_finance_settings": open_settings,
            "q": search_q,
            "orders": [],
            "payments_by_order": {},
            "payments": [],
            "payers": {},
            "flash_ok": request.query_params.get("ok")
            or ("ذخیره شد." if request.query_params.get("saved") == "1" else None),
            "flash_err": request.query_params.get("err"),
            "values": {},
            "payment_tab_groups": [],
            "payment_groups": {},
            "billing_tab_groups": [],
            "billing_groups": {},
            "payment_settings_action": "",
            "billing_settings_action": "",
            "finance_pending_action": "",
        }

        if can_finance_settings:
            rid = None if staff.get("role") == "admin" else shop_owner_id(staff)
            values = await get_all_settings(session, reseller_id=rid)
            ctx["values"] = values
            pay_groups_names, pay_groups = _groups_for_tab("payment")
            bill_groups_names, bill_groups = _groups_for_tab("billing")
            ctx["payment_tab_groups"] = pay_groups_names
            ctx["payment_groups"] = pay_groups
            ctx["billing_tab_groups"] = bill_groups_names
            ctx["billing_groups"] = bill_groups
            next_base = f"/finance?tab={tab}"
            if staff.get("role") == "admin":
                ctx["payment_settings_action"] = (
                    f"/settings?tab=payment&next={quote(next_base + '&settings=payment')}"
                )
                ctx["billing_settings_action"] = (
                    f"/settings?tab=billing&next={quote(next_base + '&settings=billing')}"
                )
                ctx["finance_pending_action"] = (
                    "/settings/cancel-pending-orders?next="
                    + quote(next_base + "&settings=payment")
                )
            else:
                ctx["payment_settings_action"] = (
                    f"/shop-settings?tab=payment&next={quote(next_base + '&settings=payment')}"
                )
                ctx["can_billing_settings"] = False
                ctx["can_pending_orders"] = True
                ctx["finance_pending_action"] = (
                    "/shop-settings/cancel-pending-orders?next="
                    + quote(next_base + "&settings=payment")
                )

        fetch_limit = 500 if search_q else 100

        if tab == "orders" and can_orders:
            q = (
                select(Order)
                .options(selectinload(Order.plan), selectinload(Order.user))
                .order_by(Order.id.desc())
                .limit(fetch_limit)
            )
            if is_platform_admin(staff):
                q = q.where(Order.reseller_id.is_(None))
            else:
                rid = shop_owner_id(staff)
                if not rid:
                    ctx["flash_err"] = ctx["flash_err"] or "محدوده فروشگاه مشخص نیست"
                    return render(request, "finance.html", ctx)
                q = q.where(Order.reseller_id == rid)
            orders = list((await session.execute(q)).scalars().all())
            if search_q:
                orders = filter_by_search(
                    orders,
                    search_q,
                    lambda o: (
                        o.id,
                        o.status,
                        o.payment_method,
                        o.amount,
                        o.note,
                        o.user_id,
                        (o.user.username if o.user else None),
                        (o.user.full_name if o.user else None),
                        (o.user.telegram_id if o.user else None),
                        (o.plan.name if o.plan else None),
                        o.plan_id,
                    ),
                )
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
            ctx["orders"] = orders
            ctx["payments_by_order"] = payments_by_order

        elif tab == "payments" and can_payments:
            if is_platform_admin(staff):
                q = (
                    select(Payment)
                    .outerjoin(Order, Order.id == Payment.order_id)
                    .where(
                        or_(
                            Payment.is_wallet_topup.is_(True),
                            Order.reseller_id.is_(None),
                        )
                    )
                    .order_by(Payment.id.desc())
                    .limit(fetch_limit)
                )
            else:
                rid = shop_owner_id(staff)
                if not rid:
                    ctx["flash_err"] = ctx["flash_err"] or "محدوده فروشگاه مشخص نیست"
                    return render(request, "finance.html", ctx)
                q = (
                    select(Payment)
                    .join(Order, Order.id == Payment.order_id)
                    .where(
                        Order.reseller_id == rid,
                        Payment.is_wallet_topup.is_(False),
                    )
                    .order_by(Payment.id.desc())
                    .limit(fetch_limit)
                )
            payments = list((await session.execute(q)).scalars().all())
            payer_ids = {int(p.user_id) for p in payments if p.user_id}
            payers: dict[int, BotUser] = {}
            if payer_ids:
                payers = {
                    int(u.id): u
                    for u in (
                        await session.execute(select(BotUser).where(BotUser.id.in_(payer_ids)))
                    ).scalars().all()
                }
            if search_q:
                payments = filter_by_search(
                    payments,
                    search_q,
                    lambda p: (
                        p.id,
                        p.user_id,
                        p.order_id,
                        p.amount,
                        p.status,
                        p.method,
                        p.review_note,
                        "شارژ" if p.is_wallet_topup else "خرید",
                        (payers.get(int(p.user_id)).username if payers.get(int(p.user_id)) else None),
                        (payers.get(int(p.user_id)).full_name if payers.get(int(p.user_id)) else None),
                        (payers.get(int(p.user_id)).telegram_id if payers.get(int(p.user_id)) else None),
                    ),
                )
            ctx["payments"] = payments
            ctx["payers"] = payers

        return render(request, "finance.html", ctx)

    def _legacy_finance_redirect(tab: str):
        async def _redir(request: Request):
            params = {"tab": tab}
            for k in ("q", "ok", "err", "saved", "settings"):
                v = request.query_params.get(k)
                if v:
                    params[k] = v
            return RedirectResponse(f"/finance?{urlencode(params)}", status_code=303)

        return _redir

    app.add_api_route("/orders", _legacy_finance_redirect("orders"), methods=["GET"], response_class=HTMLResponse)
    app.add_api_route("/payments", _legacy_finance_redirect("payments"), methods=["GET"], response_class=HTMLResponse)
