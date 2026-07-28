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
    "shop_title": "کلاک بات",
    "welcome_text": (
        "سلام {name} 👋\n\n"
        "به فروشگاه کلاک خوش آمدید.\n"
        "از منوی زیر می‌توانید سرویس بخرید، وضعیت را ببینید و پشتیبانی بگیرید."
    ),
    "card_number": "",
    "card_holder": "",
    "support_text": "پیام خود را بنویسید؛ تیم پشتیبانی پاسخ می‌دهد.",
    "force_join_channel": "",
    "force_join_enabled": "0",
    "trial_enabled": "0",
    "referral_bonus": "0",
    "auto_approve_payments": "0",
    "faq_text": (
        "❓ حجم تمام شد چه کنم؟\nاز بخش سرویس‌ها → تمدید.\n\n"
        "❓ لینک کار نمی‌کند؟\nQR یا لینک را دوباره از سرویس‌های من بگیرید."
    ),
    "guide_text": (
        "۱) سرویس را بخرید و پرداخت را انجام دهید\n"
        "۲) لینک یا QR اشتراک را دریافت کنید\n"
        "۳) در کلاینت (v2rayNG / Streisand / …) لینک را Import کنید"
    ),
    "purchase_success_text": "پرداخت شما تأیید شد و سرویس فعال است.\nشماره سفارش: #{order_id}",
    "delivery_title": "✅ سرویس آماده است",
    "wallet_success_title": "💰 شارژ کیف پول",
    "wallet_success_text": "مبلغ {amount} به کیف پول شما اضافه شد.",
    "payment_ok_title": "✅ پرداخت تأیید شد",
    "payment_reject_text": "پرداخت شما رد شد. اگر اشتباهی رخ داده با پشتیبانی در تماس باشید.",
    "card_pay_text": (
        "مبلغ قابل پرداخت: <b>{amount}</b>\n"
        "شماره کارت: <code>{card}</code>\n"
        "به نام: {holder}\n\n"
        "پس از واریز، عکس رسید را در همین گفتگو ارسال کنید."
    ),
    "referral_text": (
        "با دعوت دوستان پاداش بگیرید.\n\n"
        "کد دعوت شما: <code>{code}</code>\n"
        "لینک دعوت:\n{link}"
    ),
    "empty_services_text": "هنوز سرویسی ندارید.\nاز بخش «خرید سرویس» شروع کنید.",
    "shop_empty_text": "در حال حاضر پلنی برای فروش فعال نیست.",
    "qr_enabled": "1",
    "qr_caption": "📱 QR اشتراک\nبا دوربین گوشی اسکن کنید یا در کلاینت Import کنید.",
    "qr_background": "",
    "show_sub_link_in_text": "1",
    # Admin Telegram notification toggles (also managed on /notifications)
    "notify_new_subscription": "1",
    "notify_pending_approval": "1",
    "notify_new_order": "0",
    "notify_wallet_topup": "1",
    "notify_new_ticket": "1",
    "notify_auto_approve": "1",

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
    "btn_sub_link": "🔗 لینک و QR",
    "show_guide": "1",
    "show_faq": "1",
    "show_referral": "1",
    "show_wallet": "1",
    "show_support": "1",
    "show_miniapp": "1",
    "menu_layout": "classic",
    "menu_order": "shop,services,wallet,support,guide,faq,referral,miniapp",
    "pg_username_prefix": "clk",
    "pg_username_suffix": "",
    "pg_username_pattern": "{prefix}_{random}{suffix}",
    "custom_plan_enabled": "0",
    "custom_plan_price_per_gb": "1000",
    "custom_plan_price_per_day": "500",
    "custom_plan_min_gb": "1",
    "custom_plan_max_gb": "500",
    "custom_plan_min_days": "1",
    "custom_plan_max_days": "365",
    "custom_plan_template_id": "",
    "custom_plan_group_ids": "",
}

# field kinds: text | textarea | toggle | select | number | image
# (key, label, kind, help?, options?)
# Tabs for /settings?tab=... (order matches product IA)
SETTINGS_TABS: list[tuple[str, str]] = [
    ("menu", "منوی بات"),
    ("welcome", "خوش‌آمد و هویت"),
    ("messages", "متن پیام‌ها"),
    ("buttons", "متن دکمه‌ها"),
    ("qr", "QR اشتراک"),
    ("payment", "پرداخت"),
    ("forcejoin", "کانال اجباری"),
    ("notifications", "نوتیفیکیشن"),
    ("update", "آپدیت"),
    ("users", "کاربر و پلن"),
    ("bot", "ربات و اتصال"),
]

SETTING_GROUPS = {
    "خوش‌آمد و هویت": [
        ("shop_title", "نام فروشگاه", "text", "بالای منوی اصلی ربات دیده می‌شود"),
        (
            "welcome_text",
            "پیام خوش‌آمد (/start)",
            "textarea",
            "اولین پیامی که کاربر بعد از استارت می‌بیند. متغیر: {name}",
        ),
        ("trial_enabled", "نمایش پلن تست رایگان", "toggle", "اگر پلن تست ساخته‌اید، در فروشگاه دیده شود"),
    ],
    "متن پیام‌ها": [
        ("guide_text", "متن راهنما", "textarea", "دکمه راهنما در منوی کاربر"),
        ("faq_text", "متن سوالات متداول", "textarea", "دکمه سوالات متداول"),
        ("support_text", "متن صفحه پشتیبانی", "textarea", "بالای فرم تیکت نمایش داده می‌شود"),
        ("referral_text", "متن دعوت دوستان", "textarea", "متغیرها: {code} و {link}"),
        ("empty_services_text", "وقتی سرویسی ندارد", "textarea", "پیام بخش سرویس‌های من اگر لیست خالی باشد"),
        ("shop_empty_text", "وقتی پلنی نیست", "textarea", "پیام فروشگاه اگر پلن فعالی نباشد"),
        ("delivery_title", "عنوان پیام تحویل سرویس", "text", "مثلاً: ✅ سرویس آماده است"),
        ("purchase_success_text", "متن موفقیت خرید", "textarea", "متغیر: {order_id} — پیام کوتاه موفقیت (جزئیات روی QR است)"),
        ("wallet_success_text", "متن موفقیت شارژ کیف پول", "textarea", "متغیر: {amount}"),
        ("payment_reject_text", "متن رد پرداخت", "textarea", "وقتی ادمین رسید را رد می‌کند"),
    ],
    "متن دکمه‌های منو": [
        ("btn_shop", "دکمه خرید", "text", ""),
        ("btn_services", "دکمه سرویس‌ها", "text", ""),
        ("btn_wallet", "دکمه کیف پول", "text", ""),
        ("btn_support", "دکمه پشتیبانی", "text", ""),
        ("btn_guide", "دکمه راهنما", "text", ""),
        ("btn_faq", "دکمه سوالات", "text", ""),
        ("btn_referral", "دکمه دعوت", "text", ""),
        ("btn_miniapp", "دکمه مینی‌اپ", "text", ""),
        ("btn_reseller", "دکمه نماینده", "text", ""),
        ("btn_admin", "دکمه ادمین", "text", ""),
        ("btn_back", "دکمه بازگشت", "text", ""),
        ("btn_pay_wallet", "پرداخت با کیف پول", "text", ""),
        ("btn_pay_card", "پرداخت کارت‌به‌کارت", "text", ""),
        ("btn_pay_discount", "کد تخفیف", "text", ""),
        ("btn_cancel", "انصراف", "text", ""),
        ("btn_renew", "تمدید", "text", ""),
        ("btn_sub_link", "لینک و QR", "text", ""),
    ],
    "نمایش منو": [
        (
            "menu_layout",
            "حالت ردیف‌ها",
            "select",
            "کلاسیک یا فشرده",
            [("classic", "کلاسیک — هر دکمه یک ردیف"), ("compact", "فشرده — دکمه‌ها جفتی")],
        ),
        ("show_wallet", "نمایش کیف پول", "toggle", ""),
        ("show_support", "نمایش پشتیبانی", "toggle", ""),
        ("show_guide", "نمایش راهنما", "toggle", ""),
        ("show_faq", "نمایش سوالات متداول", "toggle", ""),
        ("show_referral", "نمایش دعوت", "toggle", ""),
        ("show_miniapp", "نمایش مینی‌اپ", "toggle", ""),
    ],
    "QR اشتراک": [
        ("qr_enabled", "ارسال خودکار QR", "toggle", "بعد از تحویل سرویس، QR لینک اشتراک فرستاده می‌شود"),
        ("show_sub_link_in_text", "نمایش لینک در کپشن QR", "toggle", "لینک متنی هم در کپشن QR باشد"),
        ("qr_caption", "کپشن عکس QR", "textarea", "جزئیات لینک/حجم/زمان خودکار اضافه می‌شود. متغیر: {url}"),
        ("qr_background", "عکس پس‌زمینه QR", "image", "اختیاری — PNG/JPG"),
    ],
    "پرداخت": [
        ("auto_approve_payments", "تأیید خودکار رسید", "toggle", "روشن = بلافاصله بعد از رسید، سرویس تحویل می‌شود"),
        ("card_number", "شماره کارت", "text", "۱۶ رقم — برای کارت‌به‌کارت"),
        ("card_holder", "نام صاحب کارت", "text", ""),
        ("card_pay_text", "راهنمای کارت‌به‌کارت", "textarea", "متغیرها: {amount} {card} {holder}"),
        ("referral_bonus", "پاداش دعوت (تومان)", "number", "هدیه به معرف بعد از خرید موفق دعوت‌شده"),
    ],
    "کاربر و پلن دلخواه": [
        ("pg_username_prefix", "پیشوند یوزرنیم سرویس", "text", "مثلاً clk"),
        ("pg_username_suffix", "پسوند یوزرنیم سرویس", "text", "اختیاری"),
        (
            "pg_username_pattern",
            "الگوی یوزرنیم",
            "text",
            "متغیرها: {prefix} {random} {suffix} {id} — مثال: {prefix}_{random}{suffix}",
        ),
        ("custom_plan_enabled", "فعال‌سازی پلن دلخواه کاربر", "toggle", "کاربر می‌تواند حجم و روز دلخواه بسازد"),
        ("custom_plan_price_per_gb", "قیمت هر گیگ (تومان)", "number", ""),
        ("custom_plan_price_per_day", "قیمت هر روز (تومان)", "number", ""),
        ("custom_plan_min_gb", "حداقل گیگ", "number", ""),
        ("custom_plan_max_gb", "حداکثر گیگ", "number", ""),
        ("custom_plan_min_days", "حداقل روز", "number", ""),
        ("custom_plan_max_days", "حداکثر روز", "number", ""),
        ("custom_plan_template_id", "تمپلیت پاسارگارد (اختیاری)", "text", "شناسه تمپلیت؛ خالی = ساخت سفارشی"),
        ("custom_plan_group_ids", "گروه‌های اینباند", "text", "شناسه‌ها با کاما"),
    ],
    "کانال اجباری": [
        ("force_join_enabled", "عضویت اجباری کانال", "toggle", "قبل از استفاده از ربات"),
        ("force_join_channel", "آدرس کانال", "text", "@channel یا لینک عمومی"),
    ],
}

# Map tab id → which SETTING_GROUPS cards to show (menu/notifications/update are special)
TAB_SETTING_GROUPS: dict[str, list[str]] = {
    "menu": ["نمایش منو"],
    "welcome": ["خوش‌آمد و هویت"],
    "messages": ["متن پیام‌ها"],
    "buttons": ["متن دکمه‌های منو"],
    "qr": ["QR اشتراک"],
    "payment": ["پرداخت"],
    "forcejoin": ["کانال اجباری"],
    "notifications": [],
    "update": [],
    "users": ["کاربر و پلن دلخواه"],
    "bot": [],
}

TOGGLE_KEYS = {
    item[0]
    for fields in SETTING_GROUPS.values()
    for item in fields
    if len(item) >= 3 and item[2] == "toggle"
}

IMAGE_KEYS = {
    item[0]
    for fields in SETTING_GROUPS.values()
    for item in fields
    if len(item) >= 3 and item[2] == "image"
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
