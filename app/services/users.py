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
    # texts
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
    "purchase_success_text": "✅ پرداخت موفق و سرویس فعال شد.\nسفارش #{order_id}",
    "card_pay_text": (
        "💳 کارت به کارت\n\n"
        "مبلغ: {amount}\n"
        "کارت: {card}\n"
        "به نام: {holder}\n\n"
        "پس از واریز، عکس رسید را همینجا ارسال کنید."
    ),
    "referral_text": "🎁 دعوت دوستان\n\nکد شما: {code}\nلینک دعوت:\n{link}",
    # button labels
    "btn_shop": "🛒 خرید سرویس",
    "btn_services": "📦 سرویس‌های من",
    "btn_wallet": "👛 کیف پول",
    "btn_support": "🎧 پشتیبانی",
    "btn_guide": "📘 راهنما",
    "btn_faq": "❓ FAQ",
    "btn_referral": "🎁 دعوت دوستان",
    "btn_miniapp": "📱 مینی‌اپ",
    "btn_reseller": "🤝 پنل نماینده",
    "btn_admin": "🛠 پنل ادمین",
    "btn_back": "⬅️ بازگشت",
    "btn_pay_wallet": "👛 پرداخت از کیف پول",
    "btn_pay_card": "💳 کارت به کارت",
    "btn_pay_discount": "🏷 کد تخفیف",
    "btn_cancel": "❌ انصراف",
    "btn_renew": "🔄 تمدید",
    "btn_sub_link": "🔗 لینک ساب",
    # visibility / layout (1=on 0=off)
    "show_guide": "1",
    "show_faq": "1",
    "show_referral": "1",
    "show_wallet": "1",
    "show_support": "1",
    "show_miniapp": "1",
    "menu_layout": "classic",  # classic | compact
}


SETTING_GROUPS = {
    "عمومی و متن‌ها": [
        ("shop_title", "عنوان فروشگاه"),
        ("welcome_text", "متن خوش‌آمد ({name})"),
        ("support_text", "متن پشتیبانی"),
        ("faq_text", "متن FAQ"),
        ("guide_text", "متن راهنما"),
        ("purchase_success_text", "متن موفقیت خرید ({order_id})"),
        ("card_pay_text", "متن کارت‌به‌کارت ({amount} {card} {holder})"),
        ("referral_text", "متن دعوت ({code} {link})"),
    ],
    "پرداخت و کانال": [
        ("card_number", "شماره کارت"),
        ("card_holder", "صاحب کارت"),
        ("force_join_channel", "کانال اجباری (@channel یا لینک)"),
        ("force_join_enabled", "عضویت اجباری (1/0)"),
        ("trial_enabled", "تست رایگان (1/0)"),
        ("referral_bonus", "پاداش دعوت (تومان)"),
    ],
    "برچسب دکمه‌ها": [
        ("btn_shop", "دکمه خرید"),
        ("btn_services", "دکمه سرویس‌ها"),
        ("btn_wallet", "دکمه کیف پول"),
        ("btn_support", "دکمه پشتیبانی"),
        ("btn_guide", "دکمه راهنما"),
        ("btn_faq", "دکمه FAQ"),
        ("btn_referral", "دکمه دعوت"),
        ("btn_miniapp", "دکمه مینی‌اپ"),
        ("btn_reseller", "دکمه نماینده"),
        ("btn_admin", "دکمه ادمین"),
        ("btn_back", "دکمه بازگشت"),
        ("btn_pay_wallet", "دکمه پرداخت کیف پول"),
        ("btn_pay_card", "دکمه کارت‌به‌کارت"),
        ("btn_pay_discount", "دکمه کد تخفیف"),
        ("btn_cancel", "دکمه انصراف"),
        ("btn_renew", "دکمه تمدید"),
        ("btn_sub_link", "دکمه لینک ساب"),
    ],
    "چیدمان منو": [
        ("menu_layout", "چیدمان (classic یا compact)"),
        ("show_guide", "نمایش راهنما (1/0)"),
        ("show_faq", "نمایش FAQ (1/0)"),
        ("show_referral", "نمایش دعوت (1/0)"),
        ("show_wallet", "نمایش کیف پول (1/0)"),
        ("show_support", "نمایش پشتیبانی (1/0)"),
        ("show_miniapp", "نمایش مینی‌اپ (1/0)"),
    ],
}


async def ensure_default_settings(session: AsyncSession) -> None:
    for key, value in DEFAULT_SETTINGS.items():
        result = await session.execute(select(Setting).where(Setting.key == key))
        if result.scalar_one_or_none() is None:
            session.add(Setting(key=key, value=value))
    await session.commit()


async def get_all_settings(session: AsyncSession) -> dict[str, str]:
    await ensure_default_settings(session)
    result = await session.execute(select(Setting))
    rows = result.scalars().all()
    data = dict(DEFAULT_SETTINGS)
    data.update({r.key: r.value for r in rows})
    return data


def on(value: str | None) -> bool:
    return (value or "").strip() in {"1", "true", "yes", "on", "True"}
