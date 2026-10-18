"""Read-only service preview endpoint for the users page."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.shop_scope import ShopScopeError
from app.services.user_service_preview import load_user_service_preview


def register_user_service_preview_pages(
    app: FastAPI, *, require_staff: Callable, get_db: Callable
) -> None:
    @app.get("/users/{customer_id}/services/{service_id}/preview")
    async def user_service_preview(
        customer_id: int,
        service_id: int,
        staff: dict = Depends(require_staff),
        session: AsyncSession = Depends(get_db),
    ) -> JSONResponse:
        try:
            preview = await load_user_service_preview(
                session, staff, customer_id=customer_id, service_id=service_id
            )
        except (PermissionError, ShopScopeError) as exc:
            raise HTTPException(status_code=403, detail="دسترسی مجاز نیست") from exc
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="سرویس یافت نشد") from exc
        return JSONResponse(asdict(preview), headers={"Cache-Control": "no-store"})
