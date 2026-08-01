"""Internal panel ticketing pages: reseller / pg_staff ↔ platform admin."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import Depends, FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BotUser, Ticket
from app.services.panel_tickets import (
    PRIORITY_BADGE,
    PRIORITY_LABELS,
    STATUS_BADGE,
    STATUS_LABELS,
    can_access_panel_tickets,
    count_answered_unread,
    count_owner_unread,
    create_ticket,
    get_ticket,
    list_tickets,
    mark_viewed,
    reply_ticket,
    save_ticket_attachment,
    set_status,
    sidebar_unread_count,
)
from app.services.shop_scope import is_platform_admin, shop_owner_id

_OK_FLASH = {
    "created": "تیکت ثبت شد",
    "replied": "پاسخ ثبت شد",
    "status": "وضعیت تیکت به‌روز شد",
}


def register_panel_tickets_pages(app: FastAPI, *, render, require_staff, get_db) -> None:
    @app.get("/tickets", response_class=HTMLResponse)
    async def tickets_page(
        request: Request,
        staff: dict = Depends(require_staff),
        session: AsyncSession = Depends(get_db),
        view: int | None = None,
        new: int | None = None,
    ):
        if not can_access_panel_tickets(staff):
            return RedirectResponse("/home", status_code=303)

        panel_tickets = await list_tickets(session, staff, limit=150)
        tg_tickets: list[Ticket] = []
        show_tg = False
        if is_platform_admin(staff):
            show_tg = True
            tg_tickets = list(
                (await session.execute(select(Ticket).order_by(Ticket.id.desc()).limit(100))).scalars().all()
            )
        elif staff.get("role") == "reseller" and "tickets" in (staff.get("permissions") or []):
            show_tg = True
            rid = shop_owner_id(staff)
            if rid:
                tg_tickets = list(
                    (
                        await session.execute(
                            select(Ticket)
                            .join(BotUser, BotUser.id == Ticket.user_id)
                            .where(BotUser.reseller_id == rid)
                            .order_by(Ticket.id.desc())
                            .limit(100)
                        )
                    )
                    .scalars()
                    .all()
                )

        active_ticket = None
        if view is not None:
            active_ticket = await get_ticket(session, staff, int(view))
            if active_ticket is not None:
                await mark_viewed(session, staff, int(view))
                active_ticket = await get_ticket(session, staff, int(view))
                # Refresh list so unread badges match after mark_viewed
                panel_tickets = await list_tickets(session, staff, limit=150)

        ok_key = (request.query_params.get("ok") or "").strip()
        flash_ok = _OK_FLASH.get(ok_key, ok_key or None)
        # Recompute after mark_viewed so sidebar dot clears on this response
        tickets_unread = await sidebar_unread_count(session, staff)
        request.state.panel_tickets_unread = tickets_unread

        return render(
            request,
            "tickets.html",
            {
                "staff": staff,
                "panel_tickets": panel_tickets,
                "tg_tickets": tg_tickets,
                "show_tg": show_tg,
                "active_ticket": active_ticket,
                "open_new": bool(new),
                "status_labels": STATUS_LABELS,
                "priority_labels": PRIORITY_LABELS,
                "status_badge": STATUS_BADGE,
                "priority_badge": PRIORITY_BADGE,
                "is_owner": is_platform_admin(staff),
                "can_create": staff.get("role") in {"reseller", "pg_staff"},
                "flash_ok": flash_ok,
                "flash_err": request.query_params.get("err"),
                "tickets_unread": tickets_unread,
            },
        )

    @app.post("/tickets/panel/create")
    async def tickets_panel_create(
        request: Request,
        staff: dict = Depends(require_staff),
        session: AsyncSession = Depends(get_db),
        subject: str = Form(...),
        body: str = Form(""),
        priority: str = Form("normal"),
        attachment: UploadFile | None = File(None),
    ):
        if staff.get("role") not in {"reseller", "pg_staff"}:
            return RedirectResponse(
                "/tickets?err=" + quote("فقط نماینده / ادمین فرعی می‌تواند تیکت بسازد"),
                status_code=303,
            )
        try:
            att = await save_ticket_attachment(attachment)
            ticket = await create_ticket(
                session,
                staff,
                subject=subject,
                body=body,
                priority=priority,
                attachment=att,
            )
            return RedirectResponse(f"/tickets?ok=created&view={ticket.id}", status_code=303)
        except Exception as exc:
            return RedirectResponse(
                f"/tickets?err={quote(str(exc))}&new=1",
                status_code=303,
            )

    @app.post("/tickets/panel/{ticket_id}/reply")
    async def tickets_panel_reply(
        request: Request,
        ticket_id: int,
        staff: dict = Depends(require_staff),
        session: AsyncSession = Depends(get_db),
        body: str = Form(""),
        attachment: UploadFile | None = File(None),
    ):
        if not can_access_panel_tickets(staff):
            return RedirectResponse("/tickets?err=" + quote("دسترسی ندارید"), status_code=303)
        try:
            att = await save_ticket_attachment(attachment, ticket_id=ticket_id)
            await reply_ticket(session, staff, ticket_id, body=body, attachment=att)
            return RedirectResponse(f"/tickets?ok=replied&view={ticket_id}", status_code=303)
        except Exception as exc:
            return RedirectResponse(
                f"/tickets?err={quote(str(exc))}&view={ticket_id}",
                status_code=303,
            )

    @app.post("/tickets/panel/{ticket_id}/status")
    async def tickets_panel_status(
        request: Request,
        ticket_id: int,
        staff: dict = Depends(require_staff),
        session: AsyncSession = Depends(get_db),
        status: str = Form(...),
    ):
        if not can_access_panel_tickets(staff):
            return RedirectResponse("/tickets?err=" + quote("دسترسی ندارید"), status_code=303)
        try:
            await set_status(session, staff, ticket_id, status=status)
            return RedirectResponse(f"/tickets?ok=status&view={ticket_id}", status_code=303)
        except Exception as exc:
            return RedirectResponse(
                f"/tickets?err={quote(str(exc))}&view={ticket_id}",
                status_code=303,
            )


async def panel_ticket_dashboard_alert(session: AsyncSession, staff: dict) -> dict | None:
    """Banner data for dashboards — links to list only (no auto-open modal)."""
    from app.services.shop_scope import is_platform_admin

    if is_platform_admin(staff):
        n = await count_owner_unread(session, staff)
        if n <= 0:
            return None
        return {
            "title": f"{n} تیکت خوانده‌نشده" if n > 1 else "یک تیکت خوانده‌نشده",
            "detail": "نماینده یا ادمین فرعی پیام جدیدی فرستاده است.",
            "href": "/tickets",
            "count": n,
        }

    n = await count_answered_unread(session, staff)
    if n <= 0:
        return None
    if n == 1:
        title = "پاسخ جدید برای تیکت پشتیبانی"
        detail = "ادمین اصلی به تیکت شما پاسخ داده است."
    else:
        title = f"{n} تیکت پاسخ‌داده‌شده دارید"
        detail = "پاسخ‌های جدید در صفحه پشتیبانی منتظر مشاهده‌اند."
    return {"title": title, "detail": detail, "href": "/tickets", "count": n}
