from __future__ import annotations

import secrets
import string
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import BotUser, Role, Setting


def _referral_code() -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(8))


async def get_or_create_user(
    session: AsyncSession,
    telegram_id: int,
    *,
    username: str | None = None,
    full_name: str | None = None,
    referred_by_code: str | None = None,
) -> BotUser:
    result = await session.execute(
        select(BotUser).where(BotUser.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()
    settings = get_settings()
    is_admin = telegram_id in settings.admin_ids

    if user:
        changed = False
        if username and user.username != username:
            user.username = username
            changed = True
        if full_name and user.full_name != full_name:
            user.full_name = full_name
            changed = True
        if is_admin and user.role != Role.ADMIN.value:
            user.role = Role.ADMIN.value
            changed = True
        if changed:
            await session.commit()
            await session.refresh(user)
        return user

    referred_by_id = None
    if referred_by_code:
        ref = await session.execute(
            select(BotUser).where(BotUser.referral_code == referred_by_code.upper())
        )
        referrer = ref.scalar_one_or_none()
        if referrer and referrer.telegram_id != telegram_id:
            referred_by_id = referrer.id

    user = BotUser(
        telegram_id=telegram_id,
        username=username,
        full_name=full_name,
        role=Role.ADMIN.value if is_admin else Role.USER.value,
        referral_code=_referral_code(),
        referred_by_id=referred_by_id,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def get_user_by_tg(session: AsyncSession, telegram_id: int) -> Optional[BotUser]:
    result = await session.execute(
        select(BotUser).where(BotUser.telegram_id == telegram_id)
    )
    return result.scalar_one_or_none()


async def get_setting(session: AsyncSession, key: str, default: str = "") -> str:
    result = await session.execute(select(Setting).where(Setting.key == key))
    row = result.scalar_one_or_none()
    return row.value if row else default


async def set_setting(session: AsyncSession, key: str, value: str) -> None:
    result = await session.execute(select(Setting).where(Setting.key == key))
    row = result.scalar_one_or_none()
    if row:
        row.value = value
    else:
        session.add(Setting(key=key, value=value))
    await session.commit()


DEFAULT_SETTINGS = {
    "shop_title": "فروشگاه Clock",
    "welcome_text": (
        "سلام {name} 👋\n"
        "به ربات فروش پاسارگارد خوش آمدید.\n"
        "از اینجا می‌توانید سرویس بخرید، تمدید کنید و پشتیبانی بگیرید."
    ),
    "card_number": "",
    "card_holder": "",
    "support_text": "پیام خود را بنویسید؛ پشتیبانی پاسخ می‌دهد.",
    "force_join_channel": "",
    "force_join_enabled": "0",
    "trial_enabled": "0",
    "referral_bonus": "0",
    "faq_text": "سوالات متداول به‌زودی تکمیل می‌شود.",
    "guide_text": "برای اتصال، لینک سابسکریپشن را در کلاینت خود وارد کنید.",
}


async def ensure_default_settings(session: AsyncSession) -> None:
    for key, value in DEFAULT_SETTINGS.items():
        result = await session.execute(select(Setting).where(Setting.key == key))
        if result.scalar_one_or_none() is None:
            session.add(Setting(key=key, value=value))
    await session.commit()
