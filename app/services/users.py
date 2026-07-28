from __future__ import annotations

import secrets
import string

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
    "support_contacts": "[]",
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
    # Admin Telegram notification toggles (settings → اعلان‌ها)
    "notify_new_subscription": "1",
    "notify_pending_approval": "1",
    "notify_new_order": "0",
    "notify_wallet_topup": "1",
    "notify_new_ticket": "1",
    "notify_auto_approve": "1",
    # User low-remaining alerts (volume / time)
    "user_alert_low_enabled": "0",
    "user_alert_low_traffic_pct": "20",
    "user_alert_low_time_pct": "20",
    # Reseller panel base URL (setup links). Empty = PUBLIC_BASE_URL
    "reseller_panel_base_url": "",

    "btn_shop": "🟢🛒 خرید سرویس",
    "btn_services": "🔵📦 سرویس‌های من",
    "btn_wallet": "🟡👛 کیف پول",
    "btn_support": "🟣🎧 پشتیبانی",
    "btn_guide": "📘 راهنما",
    "btn_faq": "❓ سوالات متداول",
    "btn_referral": "🎁 دعوت دوستان",
    "btn_reseller_apply": "🤝 درخواست نمایندگی",
    "btn_miniapp": "📱 مینی‌اپ",
    "btn_reseller": "🤝 پنل نماینده",
    "btn_admin": "🛠 پنل ادمین",
    "btn_back": "⬅️ بازگشت",
    "btn_pay_wallet": "🟢👛 پرداخت از کیف پول",
    "btn_pay_card": "🔵💳 کارت به کارت",
    "btn_pay_gateway": "🟢🌐 درگاه پرداخت",
    "btn_pay_crypto": "🟡💎 رمزارز",
    "btn_pay_stars": "⭐ استارز تلگرام",
    "btn_pay_discount": "🏷 کد تخفیف",
    "btn_cancel": "❌ انصراف",
    "btn_renew": "🔄 تمدید",
    "btn_sub_link": "🔗 لینک و QR",
    "show_guide": "1",
    "show_faq": "1",
    "show_referral": "1",
    "show_reseller_apply": "1",
    "show_wallet": "1",
    "show_support": "1",
    "show_miniapp": "1",
    "menu_layout": "classic",
    "menu_order": "shop,services,wallet,support,guide,faq,referral,reseller_apply,miniapp",
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
    # Payment methods
    "pay_wallet_enabled": "1",
    "pay_card_enabled": "1",
    "pay_gateway_enabled": "0",
    "pay_crypto_enabled": "0",
    "pay_stars_enabled": "0",
    "pay_discount_enabled": "1",
    "gateway_name": "درگاه پرداخت",
    "gateway_link": "",
    "gateway_pay_text": (
        "مبلغ قابل پرداخت: <b>{amount}</b>\n"
        "از دکمه زیر وارد درگاه شوید و پرداخت را انجام دهید.\n"
        "سپس عکس رسید را در همین گفتگو بفرستید."
    ),
    "crypto_asset": "USDT",
    "crypto_network": "TRC20",
    "crypto_address": "",
    "crypto_pay_text": (
        "مبلغ تقریبی سفارش: <b>{amount}</b>\n"
        "رمزارز: <b>{asset}</b> ({network})\n"
        "آدرس ولت:\n<code>{address}</code>\n\n"
        "پس از واریز، عکس رسید/هش تراکنش را در همین گفتگو بفرستید."
    ),
    "stars_toman_per_star": "500",
    "stars_title": "خرید سرویس",
    "stars_description": "پرداخت سفارش با استارز تلگرام",
}

# field kinds: text | textarea | toggle | select | number | image
# (key, label, kind, help?, options?)
# Tabs for /settings?tab=... (order matches product IA)
SETTINGS_TABS: list[tuple[str, str]] = [
    ("welcome", "خوش‌آمد و هویت"),
    ("messages", "متن پیام‌ها"),
    ("buttons", "متن دکمه‌ها"),
    ("menu", "منوی بات"),
    ("qr", "QR اشتراک"),
    ("payment", "پرداخت"),
    ("supports", "پشتیبان‌ها"),
    ("naming", "نام‌گذاری سرویس"),
    ("forcejoin", "کانال اجباری"),
    ("reseller", "نمایندگی"),
    ("notifications", "نوتیفیکیشن"),
    ("update", "آپدیت"),
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
    ],
    "متن دکمه‌های منو": [
        ("btn_shop", "دکمه خرید", "text", ""),
        ("btn_services", "دکمه سرویس‌ها", "text", ""),
        ("btn_wallet", "دکمه کیف پول", "text", ""),
        ("btn_support", "دکمه پشتیبانی", "text", ""),
        ("btn_guide", "دکمه راهنما", "text", ""),
        ("btn_faq", "دکمه سوالات", "text", ""),
        ("btn_referral", "دکمه دعوت", "text", ""),
        ("btn_reseller_apply", "دکمه درخواست نمایندگی", "text", ""),
        ("btn_miniapp", "دکمه مینی‌اپ", "text", ""),
        ("btn_reseller", "دکمه نماینده", "text", ""),
        ("btn_admin", "دکمه ادمین", "text", ""),
        ("btn_back", "دکمه بازگشت", "text", ""),
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
    "نمایندگی": [
        (
            "show_reseller_apply",
            "نمایش درخواست نمایندگی",
            "toggle",
            "دکمه درخواست نمایندگی در منوی کاربران عادی",
        ),
        (
            "reseller_panel_base_url",
            "آدرس وب‌پنل نماینده",
            "text",
            "لینک راه‌اندازی بعد از تأیید روی این آدرس ساخته می‌شود. خالی = آدرس پیش‌فرض پنل (PUBLIC_BASE_URL)",
        ),
    ],
    "هشدار سرویس کاربر": [
        (
            "user_alert_low_enabled",
            "ارسال خودکار هشدار کمبود",
            "toggle",
            "وقتی حجم یا زمان باقی‌مانده کمتر از حد تعیین‌شده باشد، به کاربر پیام می‌رود",
        ),
        (
            "user_alert_low_traffic_pct",
            "آستانه حجم باقی‌مانده (٪)",
            "number",
            "مثلاً ۲۰ یعنی وقتی کمتر از ۲۰٪ حجم مانده پیام بفرست",
        ),
        (
            "user_alert_low_time_pct",
            "آستانه زمان باقی‌مانده (٪)",
            "number",
            "مثلاً ۲۰ یعنی وقتی کمتر از ۲۰٪ از مدت سرویس مانده پیام بفرست",
        ),
    ],
    "QR اشتراک": [
        ("qr_enabled", "ارسال خودکار QR", "toggle", "بعد از تحویل سرویس، QR لینک اشتراک فرستاده می‌شود"),
        ("show_sub_link_in_text", "نمایش لینک در کپشن QR", "toggle", "لینک متنی هم در کپشن QR باشد"),
        ("qr_caption", "کپشن عکس QR", "textarea", "جزئیات لینک/حجم/زمان خودکار اضافه می‌شود. متغیر: {url}"),
        ("qr_background", "عکس پس‌زمینه QR", "image", "اختیاری — PNG/JPG"),
    ],
    "روش‌های پرداخت": [
        ("pay_wallet_enabled", "کیف پول داخلی", "toggle", "پرداخت از موجودی کیف پول کاربر"),
        ("pay_card_enabled", "کارت به کارت", "toggle", ""),
        ("pay_gateway_enabled", "درگاه پرداخت", "toggle", "لینک درگاه خارجی + ارسال رسید"),
        ("pay_crypto_enabled", "رمزارز", "toggle", ""),
        ("pay_stars_enabled", "استارز تلگرام", "toggle", "پرداخت درون‌برنامه‌ای با ⭐"),
        ("pay_discount_enabled", "کد تخفیف", "toggle", "نمایش دکمه کد تخفیف هنگام پرداخت"),
        ("auto_approve_payments", "تأیید خودکار رسید", "toggle", "روشن = بلافاصله بعد از رسید، سرویس تحویل می‌شود"),
        ("referral_bonus", "پاداش دعوت (تومان)", "number", "هدیه به معرف بعد از خرید موفق دعوت‌شده"),
        ("payment_reject_text", "متن رد پرداخت", "textarea", "وقتی ادمین رسید را رد می‌کند"),
    ],
    "کارت به کارت": [
        ("card_number", "شماره کارت", "text", "۱۶ رقم"),
        ("card_holder", "نام صاحب کارت", "text", ""),
        ("card_pay_text", "راهنمای کارت‌به‌کارت", "textarea", "متغیرها: {amount} {card} {holder}"),
        ("btn_pay_card", "متن دکمه کارت به کارت", "text", ""),
    ],
    "درگاه پرداخت": [
        ("gateway_name", "نام درگاه", "text", "مثلاً زرین‌پال"),
        ("gateway_link", "لینک درگاه / صفحه پرداخت", "text", "می‌تواند شامل {amount} یا {order_id} باشد"),
        ("gateway_pay_text", "راهنمای درگاه", "textarea", "متغیرها: {amount} {order_id} {name}"),
        ("btn_pay_gateway", "متن دکمه درگاه", "text", ""),
    ],
    "رمزارز": [
        ("crypto_asset", "رمزارز", "text", "مثلاً USDT"),
        ("crypto_network", "شبکه", "text", "مثلاً TRC20"),
        ("crypto_address", "آدرس ولت", "text", ""),
        ("crypto_pay_text", "راهنمای رمزارز", "textarea", "متغیرها: {amount} {asset} {network} {address}"),
        ("btn_pay_crypto", "متن دکمه رمزارز", "text", ""),
    ],
    "استارز تلگرام": [
        (
            "stars_toman_per_star",
            "هر استارز چند تومان؟",
            "number",
            "مثال: اگر ۵۰۰ باشد، سفارش ۱۰۰٬۰۰۰ تومانی = ۲۰۰ استارز",
        ),
        ("stars_title", "عنوان فاکتور", "text", ""),
        ("stars_description", "توضیح فاکتور", "text", ""),
        ("btn_pay_stars", "متن دکمه استارز", "text", ""),
    ],
    "متن دکمه‌های پرداخت": [
        ("btn_pay_wallet", "پرداخت با کیف پول", "text", ""),
        ("btn_pay_discount", "کد تخفیف", "text", ""),
    ],
    "نام‌گذاری سرویس در پاسارگارد": [
        ("pg_username_prefix", "پیشوند ثابت", "text", "مثلاً clk — اول نام کاربر ساخته‌شده"),
        ("pg_username_suffix", "پسوند ثابت", "text", "اختیاری — ته نام"),
        (
            "pg_username_pattern",
            "الگوی نام",
            "text",
            "متغیرها: {prefix} {random} {suffix} {id} — پیش‌فرض: {prefix}_{random}{suffix}",
        ),
    ],
    "کانال اجباری": [
        ("force_join_enabled", "عضویت اجباری کانال", "toggle", "قبل از استفاده از ربات"),
        ("force_join_channel", "آدرس کانال", "text", "@channel یا لینک عمومی"),
    ],
}

# Map tab id → which SETTING_GROUPS cards to show (menu/notifications/update/naming special)
TAB_SETTING_GROUPS: dict[str, list[str]] = {
    "menu": ["نمایش منو"],
    "welcome": ["خوش‌آمد و هویت"],
    "messages": ["متن پیام‌ها"],
    "buttons": ["متن دکمه‌های منو"],
    "qr": ["QR اشتراک"],
    "payment": [
        "روش‌های پرداخت",
        "کارت به کارت",
        "درگاه پرداخت",
        "رمزارز",
        "استارز تلگرام",
        "متن دکمه‌های پرداخت",
    ],
    "supports": [],
    "naming": ["نام‌گذاری سرویس در پاسارگارد"],
    "forcejoin": ["کانال اجباری"],
    "reseller": ["نمایندگی", "هشدار سرویس کاربر"],
    "notifications": [],
    "update": [],
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


def keys_for_tab(tab: str) -> set[str]:
    """Setting keys that belong to a settings tab (prevents wiping other tabs on save)."""
    names = TAB_SETTING_GROUPS.get(tab) or []
    keys: set[str] = set()
    for name in names:
        for item in SETTING_GROUPS.get(name, []):
            keys.add(item[0])
    return keys


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
