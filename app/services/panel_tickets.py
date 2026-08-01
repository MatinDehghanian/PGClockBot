"""Internal web-panel tickets: reseller / pg_staff ↔ platform admin."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import (
    PanelTicket,
    PanelTicketMessage,
    PanelTicketPriority,
    PanelTicketStatus,
    ResellerProfile,
)

STATUS_LABELS = {
    PanelTicketStatus.OPEN.value: "باز",
    PanelTicketStatus.IN_PROGRESS.value: "در حال بررسی",
    PanelTicketStatus.ANSWERED.value: "پاسخ‌داده‌شده",
    PanelTicketStatus.CLOSED.value: "بسته",
}

PRIORITY_LABELS = {
    PanelTicketPriority.LOW.value: "کم",
    PanelTicketPriority.NORMAL.value: "عادی",
    PanelTicketPriority.HIGH.value: "بالا",
    PanelTicketPriority.URGENT.value: "فوری",
}

STATUS_BADGE = {
    PanelTicketStatus.OPEN.value: "open",
    PanelTicketStatus.IN_PROGRESS.value: "info",
    PanelTicketStatus.ANSWERED.value: "answered",
    PanelTicketStatus.CLOSED.value: "neutral",
}

PRIORITY_BADGE = {
    PanelTicketPriority.LOW.value: "neutral",
    PanelTicketPriority.NORMAL.value: "info",
    PanelTicketPriority.HIGH.value: "warn",
    PanelTicketPriority.URGENT.value: "danger",
}

OWNER_STATUSES = (
    PanelTicketStatus.OPEN.value,
    PanelTicketStatus.IN_PROGRESS.value,
    PanelTicketStatus.ANSWERED.value,
    PanelTicketStatus.CLOSED.value,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def status_label(code: str) -> str:
    return STATUS_LABELS.get(code, code or "نامشخص")


def priority_label(code: str) -> str:
    return PRIORITY_LABELS.get(code, code or "نامشخص")


def normalize_priority(raw: str | None) -> str:
    v = (raw or PanelTicketPriority.NORMAL.value).strip().lower()
    if v in PRIORITY_LABELS:
        return v
    return PanelTicketPriority.NORMAL.value


def normalize_status(raw: str | None) -> str | None:
    v = (raw or "").strip().lower()
    if v in STATUS_LABELS:
        return v
    return None


def actor_from_staff(staff: dict) -> dict[str, Any]:
    """Resolve panel principal for ticket actions."""
    role = staff.get("role") or ""
    if role == "admin":
        return {
            "role": "admin",
            "label": staff.get("username") or "مدیر",
            "reseller_user_id": None,
            "pg_staff_id": None,
            "is_owner": True,
            "is_opener": False,
        }
    if role == "reseller":
        rid = staff.get("bot_user_id")
        return {
            "role": "reseller",
            "label": staff.get("username") or f"نماینده #{rid or '—'}",
            "reseller_user_id": int(rid) if rid else None,
            "pg_staff_id": None,
            "is_owner": False,
            "is_opener": True,
        }
    if role == "pg_staff":
        sid = staff.get("pg_staff_id")
        return {
            "role": "pg_staff",
            "label": staff.get("username") or staff.get("pg_admin_username") or f"ادمین فرعی #{sid or '—'}",
            "reseller_user_id": None,
            "pg_staff_id": int(sid) if sid else None,
            "is_owner": False,
            "is_opener": True,
        }
    raise PermissionError("نقش برای تیکت پنل مجاز نیست")


def can_access_panel_tickets(staff: dict) -> bool:
    role = staff.get("role")
    if role == "admin":
        return True
    if role == "pg_staff":
        return True
    if role == "reseller":
        return True  # core support channel for shop owners
    return False


def _scope_query(actor: dict) -> Select[tuple[PanelTicket]]:
    q = select(PanelTicket).options(selectinload(PanelTicket.messages))
    if actor["is_owner"]:
        return q.order_by(PanelTicket.updated_at.desc(), PanelTicket.id.desc())
    if actor["role"] == "reseller" and actor["reseller_user_id"]:
        return q.where(PanelTicket.opener_reseller_user_id == int(actor["reseller_user_id"])).order_by(
            PanelTicket.updated_at.desc(), PanelTicket.id.desc()
        )
    if actor["role"] == "pg_staff" and actor["pg_staff_id"]:
        return q.where(PanelTicket.opener_pg_staff_id == int(actor["pg_staff_id"])).order_by(
            PanelTicket.updated_at.desc(), PanelTicket.id.desc()
        )
    return q.where(PanelTicket.id == -1)


async def list_tickets(session: AsyncSession, staff: dict, *, limit: int = 100) -> list[PanelTicket]:
    actor = actor_from_staff(staff)
    q = _scope_query(actor).limit(limit)
    return list((await session.execute(q)).scalars().unique().all())


async def get_ticket(
    session: AsyncSession, staff: dict, ticket_id: int
) -> Optional[PanelTicket]:
    actor = actor_from_staff(staff)
    row = (
        await session.execute(
            select(PanelTicket)
            .options(selectinload(PanelTicket.messages))
            .where(PanelTicket.id == int(ticket_id))
        )
    ).scalar_one_or_none()
    if not row:
        return None
    if actor["is_owner"]:
        return row
    if actor["role"] == "reseller" and row.opener_reseller_user_id == actor["reseller_user_id"]:
        return row
    if actor["role"] == "pg_staff" and row.opener_pg_staff_id == actor["pg_staff_id"]:
        return row
    return None


async def create_ticket(
    session: AsyncSession,
    staff: dict,
    *,
    subject: str,
    body: str,
    priority: str | None = None,
) -> PanelTicket:
    actor = actor_from_staff(staff)
    if not actor["is_opener"]:
        raise PermissionError("فقط نماینده / ادمین فرعی می‌تواند تیکت جدید بسازد")
    sub = (subject or "").strip()
    msg = (body or "").strip()
    if len(sub) < 3:
        raise ValueError("موضوع حداقل ۳ کاراکتر باشد")
    if len(msg) < 3:
        raise ValueError("متن پیام حداقل ۳ کاراکتر باشد")
    if actor["role"] == "reseller" and not actor["reseller_user_id"]:
        raise PermissionError("شناسه نماینده مشخص نیست")
    if actor["role"] == "pg_staff" and not actor["pg_staff_id"]:
        raise PermissionError("شناسه ادمین فرعی مشخص نیست")

    ticket = PanelTicket(
        subject=sub[:255],
        status=PanelTicketStatus.OPEN.value,
        priority=normalize_priority(priority),
        opener_role=actor["role"],
        opener_reseller_user_id=actor["reseller_user_id"],
        opener_pg_staff_id=actor["pg_staff_id"],
        opener_label=str(actor["label"])[:128],
        answered_unread=False,
    )
    session.add(ticket)
    await session.flush()
    session.add(
        PanelTicketMessage(
            ticket_id=ticket.id,
            sender_role=actor["role"],
            sender_label=str(actor["label"])[:128],
            body=msg,
        )
    )
    await session.commit()
    return await get_ticket(session, staff, int(ticket.id))  # type: ignore[return-value]


async def reply_ticket(
    session: AsyncSession,
    staff: dict,
    ticket_id: int,
    *,
    body: str,
) -> PanelTicket:
    actor = actor_from_staff(staff)
    ticket = await get_ticket(session, staff, ticket_id)
    if not ticket:
        raise PermissionError("تیکت پیدا نشد")
    if ticket.status == PanelTicketStatus.CLOSED.value:
        raise ValueError("تیکت بسته است")
    msg = (body or "").strip()
    if len(msg) < 1:
        raise ValueError("متن پیام خالی است")

    session.add(
        PanelTicketMessage(
            ticket_id=ticket.id,
            sender_role=actor["role"],
            sender_label=str(actor["label"])[:128],
            body=msg,
        )
    )
    if actor["is_owner"]:
        ticket.status = PanelTicketStatus.ANSWERED.value
        ticket.answered_unread = True
    else:
        # Opener followed up — waiting for owner again
        ticket.status = PanelTicketStatus.OPEN.value
        ticket.answered_unread = False
    ticket.updated_at = _utcnow()
    await session.commit()
    return await get_ticket(session, staff, ticket_id)  # type: ignore[return-value]


async def set_status(
    session: AsyncSession,
    staff: dict,
    ticket_id: int,
    *,
    status: str,
) -> PanelTicket:
    actor = actor_from_staff(staff)
    ticket = await get_ticket(session, staff, ticket_id)
    if not ticket:
        raise PermissionError("تیکت پیدا نشد")
    new_status = normalize_status(status)
    if not new_status:
        raise ValueError("وضعیت نامعتبر است")

    if actor["is_owner"]:
        if new_status not in OWNER_STATUSES:
            raise ValueError("وضعیت نامعتبر است")
    else:
        # Opener may only close
        if new_status != PanelTicketStatus.CLOSED.value:
            raise PermissionError("شما فقط می‌توانید تیکت را ببندید")

    ticket.status = new_status
    ticket.updated_at = _utcnow()
    if new_status == PanelTicketStatus.CLOSED.value:
        ticket.closed_at = _utcnow()
        ticket.answered_unread = False
    elif new_status == PanelTicketStatus.ANSWERED.value and actor["is_owner"]:
        ticket.answered_unread = True
    elif new_status in (PanelTicketStatus.OPEN.value, PanelTicketStatus.IN_PROGRESS.value):
        if actor["is_owner"]:
            ticket.answered_unread = False
    await session.commit()
    return await get_ticket(session, staff, ticket_id)  # type: ignore[return-value]


async def mark_viewed(session: AsyncSession, staff: dict, ticket_id: int) -> None:
    """Clear answered_unread when opener opens the ticket."""
    actor = actor_from_staff(staff)
    if actor["is_owner"]:
        return
    ticket = await get_ticket(session, staff, ticket_id)
    if not ticket or not ticket.answered_unread:
        return
    ticket.answered_unread = False
    await session.commit()


async def count_answered_unread(session: AsyncSession, staff: dict) -> int:
    actor = actor_from_staff(staff)
    if actor["is_owner"] or not actor["is_opener"]:
        return 0
    conds = [PanelTicket.answered_unread.is_(True)]
    if actor["role"] == "reseller" and actor["reseller_user_id"]:
        conds.append(PanelTicket.opener_reseller_user_id == int(actor["reseller_user_id"]))
    elif actor["role"] == "pg_staff" and actor["pg_staff_id"]:
        conds.append(PanelTicket.opener_pg_staff_id == int(actor["pg_staff_id"]))
    else:
        return 0
    from sqlalchemy import func

    n = (
        await session.execute(select(func.count()).select_from(PanelTicket).where(*conds))
    ).scalar_one()
    return int(n or 0)


async def first_answered_unread_id(session: AsyncSession, staff: dict) -> Optional[int]:
    actor = actor_from_staff(staff)
    if actor["is_owner"] or not actor["is_opener"]:
        return None
    q = select(PanelTicket.id).where(PanelTicket.answered_unread.is_(True))
    if actor["role"] == "reseller" and actor["reseller_user_id"]:
        q = q.where(PanelTicket.opener_reseller_user_id == int(actor["reseller_user_id"]))
    elif actor["role"] == "pg_staff" and actor["pg_staff_id"]:
        q = q.where(PanelTicket.opener_pg_staff_id == int(actor["pg_staff_id"]))
    else:
        return None
    q = q.order_by(PanelTicket.updated_at.desc()).limit(1)
    return (await session.execute(q)).scalar_one_or_none()


async def count_owner_waiting(session: AsyncSession, staff: dict) -> int:
    """Open / in-progress panel tickets awaiting platform admin attention."""
    actor = actor_from_staff(staff)
    if not actor["is_owner"]:
        return 0
    from sqlalchemy import func

    n = (
        await session.execute(
            select(func.count())
            .select_from(PanelTicket)
            .where(
                PanelTicket.status.in_(
                    [
                        PanelTicketStatus.OPEN.value,
                        PanelTicketStatus.IN_PROGRESS.value,
                    ]
                )
            )
        )
    ).scalar_one()
    return int(n or 0)


async def enrich_opener_label(session: AsyncSession, ticket: PanelTicket) -> str:
    if ticket.opener_label:
        return ticket.opener_label
    if ticket.opener_reseller_user_id:
        prof = (
            await session.execute(
                select(ResellerProfile).where(
                    ResellerProfile.user_id == int(ticket.opener_reseller_user_id)
                )
            )
        ).scalar_one_or_none()
        if prof and prof.web_username:
            return prof.web_username
        return f"نماینده #{ticket.opener_reseller_user_id}"
    if ticket.opener_pg_staff_id:
        return f"ادمین فرعی #{ticket.opener_pg_staff_id}"
    return "—"
