from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Ticket, TicketMessage, TicketStatus


async def create_ticket(
    session: AsyncSession,
    user_id: int,
    subject: str,
    body: str,
    sender_tg: int,
) -> Ticket:
    ticket = Ticket(user_id=user_id, subject=subject[:250], status=TicketStatus.OPEN.value)
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


async def list_open_tickets(session: AsyncSession, limit: int = 50) -> list[Ticket]:
    result = await session.execute(
        select(Ticket)
        .where(Ticket.status != TicketStatus.CLOSED.value)
        .order_by(Ticket.id.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
