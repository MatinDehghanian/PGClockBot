"""Remove an order from the failed-delivery list (single row; the bulk bar uses the shared service)."""

from __future__ import annotations

from collections.abc import Callable
from urllib.parse import quote

from fastapi import Depends, FastAPI
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.delivery_failure_queue import NOTHING_TO_DISMISS, dismiss_delivery_failures

LIST_URL = "/finance?tab=delivery"
DISMISSED_NOTICE = "از لیست تحویل ناموفق حذف شد"


def register_delivery_failure_pages(app: FastAPI, *, require_orders: Callable, get_db: Callable) -> None:
    @app.post("/orders/{order_id}/dismiss-delivery-failure")
    async def dismiss_delivery_failure(
        order_id: int,
        staff: dict = Depends(require_orders),
        session: AsyncSession = Depends(get_db),
    ) -> RedirectResponse:
        dismissed, _skipped = await dismiss_delivery_failures(session, staff, [order_id])
        key, text = ("ok", DISMISSED_NOTICE) if dismissed else ("err", NOTHING_TO_DISMISS)
        return RedirectResponse(f"{LIST_URL}&{key}={quote(text)}", status_code=303)
