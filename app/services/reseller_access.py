"""Who may operate a reseller shop panel on the current bot."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BotUser, ResellerProfile, Role
from app.services.resellers import get_reseller_profile


def parse_telegram_ids(raw: str | None) -> set[int]:
    """Parse CSV / whitespace / semicolon list of Telegram user IDs."""
    if not raw:
        return set()
    out: set[int] = set()
    for part in str(raw).replace(";", ",").replace("\n", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.add(int(part))
        except ValueError:
            continue
    return out


def normalize_telegram_ids_csv(raw: str | None) -> str | None:
    ids = sorted(parse_telegram_ids(raw))
    if not ids:
        return None
    return ",".join(str(i) for i in ids)


def is_bot_admin_id(profile: ResellerProfile | None, telegram_id: int) -> bool:
    if not profile:
        return False
    return int(telegram_id) in parse_telegram_ids(profile.bot_admin_ids)


async def resolve_reseller_owner_id(
    session: AsyncSession,
    db_user: BotUser,
    *,
    is_reseller_bot: bool = False,
    reseller_owner_id: int | None = None,
) -> int | None:
    """
    Return the shop owner user_id if this Telegram user may open the reseller panel
    in the current bot context.

    - Dedicated reseller bot only: owner OR configured bot_admin_ids → that shop.
    - Main (platform) bot: never — panel ops live on the shop's own bot.
      On the main bot, resellers only see credentials / deep-link info.
    """
    if not is_reseller_bot or not reseller_owner_id:
        return None
    if db_user.id == reseller_owner_id:
        return int(reseller_owner_id)
    profile = await get_reseller_profile(session, int(reseller_owner_id))
    if is_bot_admin_id(profile, db_user.telegram_id):
        return int(reseller_owner_id)
    return None


async def load_reseller_actor(
    session: AsyncSession,
    db_user: BotUser,
    *,
    is_reseller_bot: bool = False,
    reseller_owner_id: int | None = None,
) -> tuple[int | None, ResellerProfile | None]:
    owner_id = await resolve_reseller_owner_id(
        session,
        db_user,
        is_reseller_bot=is_reseller_bot,
        reseller_owner_id=reseller_owner_id,
    )
    if not owner_id:
        return None, None
    profile = await get_reseller_profile(session, owner_id)
    if not profile or not profile.is_active:
        return None, None
    return owner_id, profile


async def effective_menu_role(
    session: AsyncSession,
    db_user: BotUser,
    *,
    is_reseller_bot: bool = False,
    reseller_owner_id: int | None = None,
) -> str:
    """Role used for Telegram main menus on the current bot."""
    owner_id, profile = await load_reseller_actor(
        session,
        db_user,
        is_reseller_bot=is_reseller_bot,
        reseller_owner_id=reseller_owner_id,
    )
    if owner_id and profile:
        return Role.RESELLER.value
    # Dedicated shop bot: platform staff / foreign resellers shop as customers
    if is_reseller_bot:
        return Role.USER.value
    # Main bot: shop owners see the user menu (+ credentials button), not a second panel
    if db_user.role == Role.RESELLER.value:
        return Role.USER.value
    return db_user.role


def is_shop_owner_on_main_bot(
    db_user: BotUser,
    *,
    is_reseller_bot: bool = False,
) -> bool:
    """True when a reseller opens the platform bot (credentials-only surface)."""
    return (not is_reseller_bot) and db_user.role == Role.RESELLER.value
