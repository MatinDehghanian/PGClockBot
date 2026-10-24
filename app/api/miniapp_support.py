"""Mini App support: contacts, the customer's tickets, opening a ticket and replying.

Thin routes over ``app.services.customer_support``; the customer comes from initData
and every ticket id is re-checked against that customer and the platform scope.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.miniapp_pages import _no_store, _require_commerce
from app.db.models import BotUser, Ticket
from app.services.customer_support import (
    SupportActor,
    SupportError,
    customer_ticket_thread,
    list_customer_tickets,
    notify_staff,
    open_customer_ticket,
    reply_customer_ticket,
    support_overview,
)
from app.services.miniapp_auth import load_mini_user
from app.services.reseller_bots import open_notify_bot_for_user
from app.services.users import get_all_settings

_ID_MAX = 2**31 - 1


async def _json_object(request: Request) -> dict:
    try:
        body = await request.json()
    except ValueError:
        raise HTTPException(400, "درخواست نامعتبر است") from None
    if not isinstance(body, dict):
        raise HTTPException(400, "درخواست نامعتبر است")
    return body


def _ticket_id(value: int) -> int:
    if not 0 < value <= _ID_MAX:
        raise HTTPException(404, "تیکت پیدا نشد")
    return value


async def _alert_staff(session: AsyncSession, user: BotUser, actor: SupportActor, ticket: Ticket, body: str | None) -> None:
    bot, should_close = await open_notify_bot_for_user(session, user, shop_id=None)
    try:
        await notify_staff(bot, session, actor, ticket, body=body)
    finally:
        if should_close:
            await bot.session.close()


def register_miniapp_support(app: FastAPI, *, get_db) -> None:
    @app.get("/api/mini/support")
    async def mini_support(request: Request, session: AsyncSession = Depends(get_db)):
        user = await load_mini_user(session, request)
        _require_commerce(user)
        ui = await get_all_settings(session)
        return _no_store({**support_overview(ui), "tickets": await list_customer_tickets(session, int(user.id))})

    @app.get("/api/mini/support/tickets/{ticket_id}")
    async def mini_support_ticket(ticket_id: int, request: Request, session: AsyncSession = Depends(get_db)):
        user = await load_mini_user(session, request)
        _require_commerce(user)
        try:
            thread = await customer_ticket_thread(session, int(user.id), _ticket_id(ticket_id))
        except SupportError as exc:
            raise HTTPException(404, str(exc)) from None
        return _no_store({"ticket": thread})

    @app.post("/api/mini/support/tickets")
    async def mini_support_open(request: Request, session: AsyncSession = Depends(get_db)):
        user = await load_mini_user(session, request)
        _require_commerce(user)
        actor = SupportActor.of(user)
        body = await _json_object(request)
        try:
            ticket = await open_customer_ticket(session, actor, subject=body.get("subject"), body=body.get("body"))
        except SupportError as exc:
            raise HTTPException(400, str(exc)) from None
        await _alert_staff(session, user, actor, ticket, None)
        return _no_store({"ticket_id": int(ticket.id), "message": f"تیکت #{int(ticket.id)} ثبت شد"})

    @app.post("/api/mini/support/tickets/{ticket_id}/messages")
    async def mini_support_reply(ticket_id: int, request: Request, session: AsyncSession = Depends(get_db)):
        user = await load_mini_user(session, request)
        _require_commerce(user)
        actor = SupportActor.of(user)
        payload = await _json_object(request)
        try:
            ticket = await reply_customer_ticket(session, actor, _ticket_id(ticket_id), body=payload.get("body"))
        except SupportError as exc:
            raise HTTPException(400, str(exc)) from None
        await _alert_staff(session, user, actor, ticket, str(payload.get("body") or "").strip())
        return _no_store({"ticket_id": int(ticket.id), "message": "پیام ثبت شد"})
