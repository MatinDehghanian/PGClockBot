"""Bulk table action routes — preserve tab/query; eligible-only semantics on server."""

from __future__ import annotations

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession


def register_bulk_pages(app, *, require_admin, require_perm, get_db):
    @app.post("/users/bulk-action")
    async def users_bulk_action(
        request: Request,
        staff: dict = Depends(require_perm("dashboard")),
        session: AsyncSession = Depends(get_db),
    ):
        from app.services.platform_identity import is_explicit_owner_staff
        from app.services.table_bulk import (
            bulk_delete_users,
            bulk_renew_users,
            bulk_toggle_block,
            parse_bulk_ids,
            redirect_bulk,
            sanitize_return_to,
        )

        form = await request.form()
        action = str(form.get("action") or "").strip()
        ids = parse_bulk_ids(form.getlist("ids"))
        return_to = sanitize_return_to(
            str(form.get("return_to") or "/users"), default="/users"
        )
        if not ids:
            return redirect_bulk(return_to, err="هیچ کاربری انتخاب نشده")

        manage = is_explicit_owner_staff(staff)
        if action in {"block", "unblock", "delete"} and not manage:
            return redirect_bulk(return_to, err="اجازه این عملیات را ندارید")

        if action == "block":
            ok, fail = await bulk_toggle_block(session, staff, ids, block=True)
            noun = "کاربر مسدود شد"
        elif action == "unblock":
            ok, fail = await bulk_toggle_block(session, staff, ids, block=False)
            noun = "رفع مسدودی"
        elif action == "renew":
            ok, fail = await bulk_renew_users(session, staff, ids)
            noun = "تمدید"
        elif action == "delete":
            reason = str(form.get("reason") or "").strip()
            if len(reason) < 3:
                return redirect_bulk(return_to, err="علت حذف الزامی است (حداقل ۳ کاراکتر)")
            ok, fail = await bulk_delete_users(session, staff, ids, reason=reason)
            noun = "حذف"
        else:
            return redirect_bulk(return_to, err="عملیات نامعتبر")

        if ok == 0 and fail:
            return redirect_bulk(return_to, err=f"هیچ موردی انجام نشد · {fail} نامعتبر")
        msg = f"{ok} {noun}"
        if fail:
            msg += f" · {fail} رد شد"
        return redirect_bulk(return_to, ok=msg)

    @app.post("/finance/orders/bulk-action")
    async def finance_orders_bulk_action(
        request: Request,
        staff: dict = Depends(require_perm("orders")),
        session: AsyncSession = Depends(get_db),
    ):
        from app.services.table_bulk import (
            bulk_order_action,
            parse_bulk_ids,
            redirect_bulk,
            sanitize_return_to,
        )

        form = await request.form()
        action = str(form.get("action") or "").strip()
        ids = parse_bulk_ids(form.getlist("ids"))
        return_to = sanitize_return_to(
            str(form.get("return_to") or "/finance?tab=orders"),
            default="/finance?tab=orders",
        )
        if not ids:
            return redirect_bulk(return_to, err="هیچ سفارشی انتخاب نشده")
        if action not in {"approve", "reject", "cancel"}:
            return redirect_bulk(return_to, err="عملیات نامعتبر")
        ok, fail = await bulk_order_action(session, staff, ids, action)
        labels = {"approve": "تأیید", "reject": "رد", "cancel": "لغو"}
        if ok == 0 and fail:
            return redirect_bulk(return_to, err=f"هیچ سفارشی {labels[action]} نشد · {fail} نامعتبر")
        msg = f"{ok} سفارش {labels[action]} شد"
        if fail:
            msg += f" · {fail} رد شد"
        return redirect_bulk(return_to, ok=msg)

    @app.post("/finance/payments/bulk-action")
    async def finance_payments_bulk_action(
        request: Request,
        staff: dict = Depends(require_perm("payments")),
        session: AsyncSession = Depends(get_db),
    ):
        from app.services.table_bulk import (
            bulk_payment_action,
            parse_bulk_ids,
            redirect_bulk,
            sanitize_return_to,
        )

        form = await request.form()
        action = str(form.get("action") or "").strip()
        ids = parse_bulk_ids(form.getlist("ids"))
        return_to = sanitize_return_to(
            str(form.get("return_to") or "/finance?tab=payments"),
            default="/finance?tab=payments",
        )
        if not ids:
            return redirect_bulk(return_to, err="هیچ پرداختی انتخاب نشده")
        if action not in {"approve", "reject"}:
            return redirect_bulk(return_to, err="عملیات نامعتبر")
        ok, fail = await bulk_payment_action(session, staff, ids, action)
        labels = {"approve": "تأیید", "reject": "رد"}
        if ok == 0 and fail:
            return redirect_bulk(return_to, err=f"هیچ پرداختی {labels[action]} نشد · {fail} نامعتبر")
        msg = f"{ok} پرداخت {labels[action]} شد"
        if fail:
            msg += f" · {fail} رد شد"
        return redirect_bulk(return_to, ok=msg)

    @app.post("/finance/delivery/bulk-action")
    async def finance_delivery_bulk_action(
        request: Request,
        staff: dict = Depends(require_perm("orders")),
        session: AsyncSession = Depends(get_db),
    ):
        from app.services.table_bulk import (
            bulk_retry_delivery,
            parse_bulk_ids,
            redirect_bulk,
            sanitize_return_to,
        )

        form = await request.form()
        action = str(form.get("action") or "").strip()
        ids = parse_bulk_ids(form.getlist("ids"))
        return_to = sanitize_return_to(
            str(form.get("return_to") or "/finance?tab=delivery"),
            default="/finance?tab=delivery",
        )
        if not ids:
            return redirect_bulk(return_to, err="هیچ سفارشی انتخاب نشده")
        if action != "retry":
            return redirect_bulk(return_to, err="عملیات نامعتبر")
        ok, fail = await bulk_retry_delivery(session, staff, ids)
        if ok == 0 and fail:
            return redirect_bulk(return_to, err=f"هیچ تحویلی تکرار نشد · {fail} نامعتبر")
        msg = f"{ok} تحویل دوباره تلاش شد"
        if fail:
            msg += f" · {fail} رد شد"
        return redirect_bulk(return_to, ok=msg)

    @app.post("/tickets/bot/bulk-action")
    async def tickets_bot_bulk_action(
        request: Request,
        staff: dict = Depends(require_perm("tickets")),
        session: AsyncSession = Depends(get_db),
    ):
        from app.services.table_bulk import (
            bulk_close_bot_tickets,
            parse_bulk_ids,
            redirect_bulk,
            sanitize_return_to,
        )

        form = await request.form()
        action = str(form.get("action") or "").strip()
        ids = parse_bulk_ids(form.getlist("ids"))
        return_to = sanitize_return_to(
            str(form.get("return_to") or "/tickets"), default="/tickets"
        )
        if not ids:
            return redirect_bulk(return_to, err="هیچ تیکتی انتخاب نشده")
        if action != "close":
            return redirect_bulk(return_to, err="عملیات نامعتبر")
        ok, fail = await bulk_close_bot_tickets(session, staff, ids)
        if ok == 0 and fail:
            return redirect_bulk(return_to, err=f"هیچ تیکتی بسته نشد · {fail} نامعتبر")
        msg = f"{ok} تیکت بسته شد"
        if fail:
            msg += f" · {fail} رد شد"
        return redirect_bulk(return_to, ok=msg)
