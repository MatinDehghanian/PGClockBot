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
    "shop_title": "فروشگاه کلاک",
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
    "auto_approve_payments": "0",
    "faq_text": "سوالات متداول به‌زودی تکمیل می‌شود.",
    "guide_text": "برای اتصال، لینک اشتراک را در کلاینت خود وارد کنید.",
    "purchase_success_text": "✅ پرداخت موفق و سرویس فعال شد.\nسفارش #{order_id}",
    "card_pay_text": (
        "💳 کارت به کارت\n\n"
        "مبلغ: {amount}\n"
        "کارت: {card}\n"
        "به نام: {holder}\n\n"
        "پس از واریز، عکس رسید را همینجا ارسال کنید."
    ),
    "referral_text": "🎁 دعوت دوستان\n\nکد شما: {code}\nلینک دعوت:\n{link}",
    # button labels (emoji = رنگ بصری؛ تلگرام رنگ دکمه ندارد)
    "btn_shop": "🟢🛒 خرید سرویس",
    "btn_services": "🔵📦 سرویس‌های من",
    "btn_wallet": "🟡👛 کیف پول",
    "btn_support": "🟣🎧 پشتیبانی",
    "btn_guide": "📘 راهنما",
    "btn_faq": "❓ سوالات متداول",
    "btn_referral": "🎁 دعوت دوستان",
    "btn_miniapp": "📱 مینی‌اپ",
    "btn_reseller": "🤝 پنل نماینده",
    "btn_admin": "🛠 پنل ادمین",
    "btn_back": "⬅️ بازگشت",
    "btn_pay_wallet": "🟢👛 پرداخت از کیف پول",
    "btn_pay_card": "🔵💳 کارت به کارت",
    "btn_pay_discount": "🏷 کد تخفیف",
    "btn_cancel": "❌ انصراف",
    "btn_renew": "🔄 تمدید",
    "btn_sub_link": "🔗 لینک اشتراک",
    # visibility / layout (1=on 0=off)
    "show_guide": "1",
    "show_faq": "1",
    "show_referral": "1",
    "show_wallet": "1",
    "show_support": "1",
    "show_miniapp": "1",
    "menu_layout": "classic",  # classic | compact
    "menu_order": "shop,services,wallet,support,guide,faq,referral,miniapp",
}

# field kinds: text | textarea | toggle | select | number | note
# (key, label, kind, help?, options?)
SETTING_GROUPS = {
    "🛒 فروشگاه": [
        ("shop_title", "عنوان فروشگاه", "text", "نمایش در بالای منوی ربات"),
        ("welcome_text", "متن خوش‌آمد", "textarea", "متغیر: {name}"),
        ("trial_enabled", "تست رایگان", "toggle", "اگر روشن باشد پلن‌های تست در بات دیده می‌شوند"),
    ],
    "💳 پرداخت": [
        (
            "auto_approve_payments",
            "تأیید خودکار رسید",
            "toggle",
            "روشن = بلافاصله بعد از ارسال رسید تأیید و تحویل می‌شود. خاموش = تأیید دستی ادمین در بات یا وب‌پنل",
        ),
        ("card_number", "شماره کارت", "text", "برای کارت‌به‌کارت"),
        ("card_holder", "صاحب کارت", "text", "نام روی کارت"),
        ("card_pay_text", "متن راهنمای کارت‌به‌کارت", "textarea", "متغیرها: {amount} {card} {holder}"),
        ("purchase_success_text", "متن موفقیت خرید", "textarea", "متغیر: {order_id}"),
        ("referral_bonus", "پاداش دعوت (تومان)", "number", "مبلغ هدیه به معرف"),
    ],
    "📢 کانال و پشتیبانی": [
        ("force_join_enabled", "عضویت اجباری کانال", "toggle", ""),
        ("force_join_channel", "آدرس کانال", "text", "@channel یا لینک"),
        ("support_text", "متن پشتیبانی", "textarea", ""),
        ("faq_text", "متن سوالات متداول", "textarea", ""),
        ("guide_text", "متن راهنما", "textarea", ""),
        ("referral_text", "متن دعوت دوستان", "textarea", "متغیرها: {code} {link}"),
    ],
    "🎛 برچسب دکمه‌ها": [
        ("btn_shop", "خرید", "text", "تلگرام رنگ دکمه ندارد — از ایموجی رنگی استفاده کنید"),
        ("btn_services", "سرویس‌ها", "text", ""),
        ("btn_wallet", "کیف پول", "text", ""),
        ("btn_support", "پشتیبانی", "text", ""),
        ("btn_guide", "راهنما", "text", ""),
        ("btn_faq", "سوالات متداول", "text", ""),
        ("btn_referral", "دعوت", "text", ""),
        ("btn_miniapp", "مینی‌اپ", "text", ""),
        ("btn_reseller", "نماینده", "text", ""),
        ("btn_admin", "ادمین", "text", ""),
        ("btn_back", "بازگشت", "text", ""),
        ("btn_pay_wallet", "پرداخت کیف پول", "text", ""),
        ("btn_pay_card", "کارت‌به‌کارت", "text", ""),
        ("btn_pay_discount", "کد تخفیف", "text", ""),
        ("btn_cancel", "انصراف", "text", ""),
        ("btn_renew", "تمدید", "text", ""),
        ("btn_sub_link", "لینک اشتراک", "text", ""),
    ],
    "🗂 نمایش منو": [
        (
            "menu_layout",
            "حالت ردیف‌ها",
            "select",
            "از صفحه چیدمان منو هم قابل تنظیم است",
            [("classic", "کلاسیک — هر دکمه یک ردیف"), ("compact", "فشرده — دکمه‌ها جفتی")],
        ),
        ("show_wallet", "نمایش کیف پول", "toggle", ""),
        ("show_support", "نمایش پشتیبانی", "toggle", ""),
        ("show_guide", "نمایش راهنما", "toggle", ""),
        ("show_faq", "نمایش سوالات متداول", "toggle", ""),
        ("show_referral", "نمایش دعوت", "toggle", ""),
        ("show_miniapp", "نمایش مینی‌اپ", "toggle", ""),
    ],
}

TOGGLE_KEYS = {
    item[0]
    for fields in SETTING_GROUPS.values()
    for item in fields
    if len(item) >= 3 and item[2] == "toggle"
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
