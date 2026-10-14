"""JSON endpoints behind the «افزودن سرویس قبلی» settings tab: status, link test, recent tries."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.service_import import MAX_LINK_LENGTH
from app.services.service_import_admin import import_scope, recent_attempts, status_snapshot, test_link

STATUS_PATH = "/service-import/status"
TEST_PATH = "/service-import/test"
NO_ACCESS = {"ok": False, "error": "دسترسی ندارید"}


def register_service_import_pages(app: FastAPI, *, require_staff: Callable, get_db: Callable) -> None:
    @app.get(STATUS_PATH)
    async def service_import_status(
        request: Request,
        staff: dict = Depends(require_staff),
        session: AsyncSession = Depends(get_db),
    ) -> JSONResponse:
        try:
            scope = import_scope(staff)
        except PermissionError:
            return JSONResponse(NO_ACCESS, status_code=403)
        refresh = request.query_params.get("refresh") == "1"
        snapshot = await status_snapshot(session, scope, refresh=refresh)
        snapshot["attempts"] = await recent_attempts(session, scope)
        return JSONResponse(snapshot)

    @app.post(TEST_PATH)
    async def service_import_test(
        request: Request,
        staff: dict = Depends(require_staff),
        session: AsyncSession = Depends(get_db),
    ) -> JSONResponse:
        try:
            scope = import_scope(staff)
        except PermissionError:
            return JSONResponse(NO_ACCESS, status_code=403)
        form = await request.form()
        link = str(form.get("link") or "")[:MAX_LINK_LENGTH]
        return JSONResponse(await test_link(session, scope, link))
