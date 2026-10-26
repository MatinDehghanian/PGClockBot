"""Panel forms that save a Mini App's brand colour and notice (platform and each shop)."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import Depends, FastAPI, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.miniapp_branding import ACCENT_SETTING, NOTICE_SETTING, save_mini_brand
from app.services.shop_scope import is_platform_admin, shop_owner_id

PLATFORM_BACK = "/settings?tab=appearance"
SHOP_BACK = "/shop-settings?tab=appearance"
DEFAULT_ACCENT_FIELD = "miniapp_accent_default"
SAVED_MESSAGE = "ظاهر مینی‌اپ ذخیره شد"
NO_SHOP = "فروشگاه شما پیدا نشد"


def _form_values(form) -> tuple[str, str]:
    """The submitted accent ("" when «default colour» is ticked) and notice."""
    use_default = str(form.get(DEFAULT_ACCENT_FIELD) or "") in {"1", "on", "true", "yes"}
    accent = "" if use_default else str(form.get(ACCENT_SETTING) or "")
    return accent, str(form.get(NOTICE_SETTING) or "")


async def _save(session: AsyncSession, request: Request, *, shop_id: int | None, back: str) -> RedirectResponse:
    accent, notice = _form_values(await request.form())
    try:
        await save_mini_brand(session, shop_id=shop_id, accent=accent, notice=notice)
    except ValueError as exc:
        return RedirectResponse(f"{back}&err={quote(str(exc))}", status_code=303)
    return RedirectResponse(f"{back}&saved=1&msg={quote(SAVED_MESSAGE)}", status_code=303)


def register_miniapp_brand_pages(app: FastAPI, *, require_admin, require_shop_settings, get_db) -> None:
    @app.post("/settings/miniapp-brand")
    async def platform_miniapp_brand_save(
        request: Request,
        staff: dict = Depends(require_admin),
        session: AsyncSession = Depends(get_db),
    ) -> RedirectResponse:
        return await _save(session, request, shop_id=None, back=PLATFORM_BACK)

    @app.post("/shop-settings/miniapp-brand")
    async def shop_miniapp_brand_save(
        request: Request,
        staff: dict = Depends(require_shop_settings),
        session: AsyncSession = Depends(get_db),
    ) -> RedirectResponse:
        """The shop always comes from the signed-in staff, never from the form."""
        if is_platform_admin(staff) or staff.get("role") == "admin":
            return RedirectResponse(PLATFORM_BACK, status_code=303)
        shop_id = shop_owner_id(staff)
        if not shop_id:
            return RedirectResponse(f"{SHOP_BACK}&err={quote(NO_SHOP)}", status_code=303)
        return await _save(session, request, shop_id=int(shop_id), back=SHOP_BACK)
