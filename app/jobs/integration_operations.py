"""Default-off scheduling adapters for durable execution and signed notifications."""

from __future__ import annotations

from app.config import get_settings
from app.db.session import SessionLocal
from app.services.integration_workers import run_operation_batch


async def run_integration_operations() -> None:
    await run_operation_batch(SessionLocal, execute=get_settings().integration_execution_enabled)


