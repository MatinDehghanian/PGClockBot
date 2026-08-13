"""Shared DB session recovery helpers — never leave a poisoned session mid-request."""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def rollback_quiet(session: AsyncSession | None) -> None:
    """Roll back after a caught DB error so later queries on the same session can run.

    SQLAlchemy leaves the session in ``PendingRollbackError`` until rollback;
    swallowing an exception without this commonly 500s the rest of the request
    (e.g. sidebar unread fails → dashboard aggregates fail).
    """
    if session is None:
        return
    try:
        await session.rollback()
    except Exception:
        logger.debug("session rollback failed", exc_info=True)
