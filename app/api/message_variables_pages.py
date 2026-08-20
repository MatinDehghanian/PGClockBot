"""Message variables catalog page (پنل ربات — قبل از تنظیمات)."""

from __future__ import annotations

from fastapi import Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.message_variables import catalog_groups
from app.services.platform_identity import is_explicit_owner_staff


def register_message_variables_pages(
    app,
    *,
    render,
    require_perm,
    require_admin,
    get_db,
):
    """Read-only catalog — no secrets, no writes, shop_settings gated."""

    require_shop = require_perm("shop_settings")

    @app.get("/message-variables", response_class=HTMLResponse)
    async def message_variables_page(
        request: Request,
        staff: dict = Depends(require_shop),
        session: AsyncSession = Depends(get_db),
    ):
        _ = session
        is_owner = is_explicit_owner_staff(staff) or bool(staff.get("web_owner"))
        # Resellers / non-Owner staff: hide Owner-only naming vars (no capability leak).
        include_owner = is_owner
        settings_base = (
            "/settings" if is_owner or staff.get("role") == "admin" else "/shop-settings"
        )
        groups = catalog_groups(
            include_owner_only=include_owner,
            settings_base=settings_base,
        )
        return render(
            request,
            "message_variables.html",
            {
                "staff": staff,
                "groups": groups,
                "include_owner_only": include_owner,
            },
        )
