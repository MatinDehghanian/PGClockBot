"""Periodic sync of panel-only (external) volume allocation per gated shop."""

from __future__ import annotations

import logging

from app.db.session import SessionLocal
from app.services.volume_allocation_external import run_external_allocation_sync

logger = logging.getLogger(__name__)


async def run_volume_external_sync() -> None:
    """APScheduler entry: refresh external allocation; never opens selling on failure."""
    try:
        async with SessionLocal() as session:
            results = await run_external_allocation_sync(session)
        ok = sum(1 for r in results if r.error is None)
        stale = sum(1 for r in results if r.stale)
        logger.info(
            "volume external sync done shops=%s ok=%s stale_or_failed=%s",
            len(results),
            ok,
            stale,
        )
    except Exception:
        logger.exception("volume external sync batch failed")
