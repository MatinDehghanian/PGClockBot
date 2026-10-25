"""Which shop a Mini App request belongs to, and whether that shop's Mini App may answer.

The platform Mini App is unchanged: a request without a shop key is the platform's and is
verified with the main bot token. A shop's Mini App sends the random key from its address
(``/miniapp/s/<key>/``) in ``X-Mini-Shop``. The key only names the shop; the request is then
verified with that shop bot's own token, so a changed key fails the signature check. The
shop is never taken from a request body or query string, and an unknown or switched-off
shop is refused, never answered as the platform.

A shop's Mini App answers only when the platform switch, the shop's ``miniapp`` permission
and the shop's own switch are all on, and only on the routes in ``SHOP_ROUTES``. That list
grows one phase at a time, after each route reads its data from ``MiniScope.shop_id``.
"""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass, field

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BotUser, ResellerProfile
from app.services.reseller_access import parse_telegram_ids
from app.services.resellers import has_perm
from app.services.secret_box import reveal_bot_token
from app.services.shop_membership import is_shop_customer
from app.services.users import get_setting, on

SHOP_KEY_HEADER = "X-Mini-Shop"
PLATFORM_SWITCH = "miniapp_shops_enabled"
SHOP_SWITCH = "miniapp_shop_enabled"
PERMISSION = "miniapp"
KEY_PATTERN = re.compile(r"^[A-Za-z0-9_-]{16,32}$")
KEY_BYTES = 16
# Route paths (as registered) a shop's Mini App may call. Empty until a phase opens routes.
SHOP_ROUTES: frozenset[str] = frozenset()

SHOP_UNAVAILABLE = "مینی‌اپ این فروشگاه فعال نیست"
ROUTE_UNAVAILABLE = "این بخش هنوز در مینی‌اپ این فروشگاه نیست"
NOT_A_CUSTOMER = "شما مشتری این فروشگاه نیستید؛ ابتدا ربات فروشگاه را استارت کنید"


@dataclass(frozen=True, slots=True)
class MiniScope:
    """The shop a Mini App request was verified for; ``shop_id`` None is the platform."""

    shop_id: int | None = None
    profile_id: int | None = None
    bot_admin_telegram_ids: frozenset[int] = frozenset()
    # Verifies the request; never logged or returned.
    bot_token: str = field(default="", repr=False)

    @property
    def is_shop(self) -> bool:
        return self.shop_id is not None


PLATFORM_SCOPE = MiniScope()


def new_shop_key() -> str:
    return secrets.token_urlsafe(KEY_BYTES)


def shop_key_from_request(request: Request) -> str | None:
    """The shop key the page sent, or None for the platform Mini App; a malformed key is refused."""
    raw = request.headers.get(SHOP_KEY_HEADER)
    if raw is None:
        return None
    key = raw.strip()
    if not KEY_PATTERN.fullmatch(key):
        raise HTTPException(404, SHOP_UNAVAILABLE)
    return key


async def shop_miniapp_open(session: AsyncSession, profile: ResellerProfile) -> bool:
    """All three switches on, and the shop is active with a set-up bot."""
    if not profile.is_active or profile.setup_completed_at is None or not profile.bot_token:
        return False
    if not on(await get_setting(session, PLATFORM_SWITCH, "0")):
        return False
    if not has_perm(profile, PERMISSION):
        return False
    return on(await get_setting(session, SHOP_SWITCH, "0", reseller_id=int(profile.user_id)))


async def resolve_shop_scope(session: AsyncSession, key: str) -> MiniScope:
    """The open shop named by ``key``; anything else is the same 404, so keys cannot be probed."""
    profile = await session.scalar(select(ResellerProfile).where(ResellerProfile.miniapp_key == key))
    if profile is None or not await shop_miniapp_open(session, profile):
        raise HTTPException(404, SHOP_UNAVAILABLE)
    token = reveal_bot_token(profile.bot_token or "")
    if not token:
        raise HTTPException(404, SHOP_UNAVAILABLE)
    return MiniScope(
        shop_id=int(profile.user_id),
        profile_id=int(profile.id),
        bot_admin_telegram_ids=frozenset(parse_telegram_ids(profile.bot_admin_ids)),
        bot_token=token,
    )


async def request_scope(session: AsyncSession, request: Request) -> MiniScope:
    key = shop_key_from_request(request)
    return PLATFORM_SCOPE if key is None else await resolve_shop_scope(session, key)


def is_shop_staff(scope: MiniScope, user: BotUser) -> bool:
    return scope.is_shop and (
        int(user.id) == scope.shop_id or int(user.telegram_id or 0) in scope.bot_admin_telegram_ids
    )


async def assert_shop_member(session: AsyncSession, scope: MiniScope, user: BotUser) -> None:
    """Only the shop's own customers and its owner or bot admins use its Mini App."""
    if not scope.is_shop or is_shop_staff(scope, user):
        return
    if not await is_shop_customer(session, user, scope.shop_id):
        raise HTTPException(403, NOT_A_CUSTOMER)


def assert_shop_route(scope: MiniScope, request: Request) -> None:
    """A shop's Mini App reaches only the routes opened for shops so far."""
    if not scope.is_shop:
        return
    route = request.scope.get("route")
    if getattr(route, "path", None) not in SHOP_ROUTES:
        raise HTTPException(404, ROUTE_UNAVAILABLE)


def mini_scope(request: Request) -> MiniScope:
    """The scope ``load_mini_user`` verified for this request (the platform before it ran)."""
    scope = getattr(request.state, "mini_scope", None)
    return scope if isinstance(scope, MiniScope) else PLATFORM_SCOPE
