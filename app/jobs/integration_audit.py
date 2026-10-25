"""Run one bounded administrative audit retention batch per scheduled invocation."""

from __future__ import annotations

import logging

from sqlalchemy.exc import SQLAlchemyError

from app.db.session import SessionLocal
from app.services.integration_admin_audit import prune_management_audit
from app.services.integration_security_retention import prune_security_records

logger = logging.getLogger(__name__)


async def run_integration_audit_retention() -> None:
    async with SessionLocal() as session:
        try:
            await prune_management_audit(session)
        except SQLAlchemyError as exc:
            await session.rollback()
            logger.warning("Integration audit retention failed type=%s", type(exc).__name__)


async def run_integration_security_retention() -> None:
    async with SessionLocal() as session:
        try:
            await prune_security_records(session)
        except SQLAlchemyError as exc:
            await session.rollback()
            logger.warning("Integration security retention failed type=%s", type(exc).__name__)
