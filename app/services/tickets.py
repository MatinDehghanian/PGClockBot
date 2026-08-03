from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import BotUser, Ticket, TicketMessage, TicketStatus
from app.services.users import current_shop_reseller_id


async def create_ticket(
    session: AsyncSession,
    user_id: int,
    subject: str,
    body: str,
    sender_tg: int,
    *,
    reseller_id: int | None = None,
) -> Ticket:
    """Create a support ticket scoped to the current shop bot (or platform)."""
    shop_rid = reseller_id if reseller_id is not None else current_shop_reseller_id()
    ticket = Ticket(
        user_id=user_id,
        subject=subject[:250],
        status=TicketStatus.OPEN.value,
        reseller_id=int(shop_rid) if shop_rid else None,
    )
    session.add(ticket)
    await session.flush()
    session.add(
        TicketMessage(
            ticket_id=ticket.id,
            sender_id=sender_tg,
            is_staff=False,
            body=body,
        )
    )
    await session.commit()
    await session.refresh(ticket)
    return ticket


async def reply_ticket(
    session: AsyncSession,
    ticket: Ticket,
    body: str,
    sender_tg: int,
    *,
    is_staff: bool,
) -> Ticket:
    if ticket.status == TicketStatus.CLOSED.value:
        raise ValueError("تیکت بسته شده است")
    session.add(
        TicketMessage(
            ticket_id=ticket.id,
            sender_id=sender_tg,
            is_staff=is_staff,
            body=body,
        )
    )
    ticket.status = TicketStatus.ANSWERED.value if is_staff else TicketStatus.OPEN.value
    await session.commit()
    await session.refresh(ticket)
    return ticket


async def close_ticket(session: AsyncSession, ticket: Ticket) -> Ticket:
    ticket.status = TicketStatus.CLOSED.value
    await session.commit()
    await session.refresh(ticket)
    return ticket


async def list_user_tickets(session: AsyncSession, user_id: int) -> list[Ticket]:
    result = await session.execute(
        select(Ticket).where(Ticket.user_id == user_id).order_by(Ticket.id.desc())
    )
    return list(result.scalars().all())


async def get_ticket(session: AsyncSession, ticket_id: int) -> Ticket | None:
    result = await session.execute(
        select(Ticket)
        .where(Ticket.id == ticket_id)
        .options(selectinload(Ticket.messages))
    )
    return result.scalar_one_or_none()


async def list_open_tickets(
    session: AsyncSession,
    limit: int = 50,
    *,
    platform_only: bool = False,
    reseller_id: int | None = None,
) -> list[Ticket]:
    """List open tickets scoped by Ticket.reseller_id (with legacy sticky fallback)."""
    base = Ticket.status != TicketStatus.CLOSED.value
    if platform_only:
        q = (
            select(Ticket)
            .outerjoin(BotUser, BotUser.id == Ticket.user_id)
            .where(
                base,
                Ticket.reseller_id.is_(None),
                BotUser.reseller_id.is_(None),
            )
        )
    elif reseller_id is not None:
        rid = int(reseller_id)
        q = (
            select(Ticket)
            .outerjoin(BotUser, BotUser.id == Ticket.user_id)
            .where(
                base,
                or_(
                    Ticket.reseller_id == rid,
                    (Ticket.reseller_id.is_(None)) & (BotUser.reseller_id == rid),
                ),
            )
        )
    else:
        q = select(Ticket).where(base)
    result = await session.execute(q.order_by(Ticket.id.desc()).limit(limit))
    return list(result.scalars().all())
