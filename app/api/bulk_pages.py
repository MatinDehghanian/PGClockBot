"""Bulk table action routes."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession


def register_bulk_pages(app, *, require_admin, require_perm, get_db):
    @app.post("/users/bulk-action")
    async def users_bulk_action(
        request: Request,
        staff: dict = Depends(require_admin),
        session: AsyncSession = Depends(get_db),
    ):
        from app.services.table_bulk import bulk_toggle_block, parse_bulk_ids

        form = await request.form()
        action = str(form.get("action") or "").strip()
        ids = parse_bulk_ids(form.getlist("ids"))
        return_to = str(form.get("return_to") or "/users").strip()
        if not return_to.startswith("/") or return_to.startswith("//"):
            return_to = "/users"
        if not ids:
            return RedirectResponse(
                f"{return_to}?err={quote('هیچ کاربری انتخاب نشده')}",
                status_code=303,
            )
        if action == "block":
            ok, fail = await bulk_toggle_block(session, staff, ids, block=True)
        elif action == "unblock":
            ok, fail = await bulk_toggle_block(session, staff, ids, block=False)
        else:
            return RedirectResponse(
                f"{return_to}?err={quote('عملیات نامعتبر')}",
                status_code=303,
            )
        msg = f"{ok} مورد انجام شد"
        if fail:
            msg += f" · {fail} ناموفق"
        return RedirectResponse(f"{return_to}?ok={quote(msg)}", status_code=303)

    @app.post("/finance/orders/bulk-action")
    async def finance_orders_bulk_action(
        request: Request,
        staff: dict = Depends(require_perm("orders")),
        session: AsyncSession = Depends(get_db),
    ):
        from app.services.table_bulk import bulk_order_action, parse_bulk_ids

        form = await request.form()
        action = str(form.get("action") or "").strip()
        ids = parse_bulk_ids(form.getlist("ids"))
        return_to = str(form.get("return_to") or "/finance?tab=orders").strip()
        if not return_to.startswith("/") or return_to.startswith("//"):
            return_to = "/finance?tab=orders"
        if not ids:
            return RedirectResponse(
                f"{return_to}?err={quote('هیچ سفارشی انتخاب نشده')}",
                status_code=303,
            )
        if action not in {"approve", "reject", "cancel"}:
            return RedirectResponse(
                f"{return_to}?err={quote('عملیات نامعتبر')}",
                status_code=303,
            )
        ok, fail = await bulk_order_action(session, staff, ids, action)
        msg = f"{ok} سفارش"
        if fail:
            msg += f" · {fail} ناموفق"
        return RedirectResponse(f"{return_to}?ok={quote(msg)}", status_code=303)

    @app.post("/finance/payments/bulk-action")
    async def finance_payments_bulk_action(
        request: Request,
        staff: dict = Depends(require_perm("payments")),
        session: AsyncSession = Depends(get_db),
    ):
        from app.services.table_bulk import bulk_payment_action, parse_bulk_ids

        form = await request.form()
        action = str(form.get("action") or "").strip()
        ids = parse_bulk_ids(form.getlist("ids"))
        return_to = str(form.get("return_to") or "/finance?tab=payments").strip()
        if not return_to.startswith("/") or return_to.startswith("//"):
            return_to = "/finance?tab=payments"
        if not ids:
            return RedirectResponse(
                f"{return_to}?err={quote('هیچ پرداختی انتخاب نشده')}",
                status_code=303,
            )
        if action not in {"approve", "reject"}:
            return RedirectResponse(
                f"{return_to}?err={quote('عملیات نامعتبر')}",
                status_code=303,
            )
        ok, fail = await bulk_payment_action(session, staff, ids, action)
        msg = f"{ok} پرداخت"
        if fail:
            msg += f" · {fail} ناموفق"
        return RedirectResponse(f"{return_to}?ok={quote(msg)}", status_code=303)

    @app.post("/tickets/bot/bulk-action")
    async def tickets_bot_bulk_action(
        request: Request,
        staff: dict = Depends(require_perm("tickets")),
        session: AsyncSession = Depends(get_db),
    ):
        from app.services.table_bulk import bulk_close_bot_tickets, parse_bulk_ids

        form = await request.form()
        action = str(form.get("action") or "").strip()
        ids = parse_bulk_ids(form.getlist("ids"))
        return_to = str(form.get("return_to") or "/tickets").strip()
        if not return_to.startswith("/") or return_to.startswith("//"):
            return_to = "/tickets"
        if not ids:
            return RedirectResponse(
                f"{return_to}?err={quote('هیچ تیکتی انتخاب نشده')}",
                status_code=303,
            )
        if action != "close":
            return RedirectResponse(
                f"{return_to}?err={quote('عملیات نامعتبر')}",
                status_code=303,
            )
        ok, fail = await bulk_close_bot_tickets(session, staff, ids)
        msg = f"{ok} تیکت بسته شد"
        if fail:
            msg += f" · {fail} ناموفق"
        return RedirectResponse(f"{return_to}?ok={quote(msg)}", status_code=303)
