from __future__ import annotations

import secrets
import string
from contextvars import ContextVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import BotUser, Role, Setting

# When handling updates on a reseller-owned bot, settings read/write overlay
# that reseller's shop settings automatically.
_shop_reseller_id: ContextVar[int | None] = ContextVar("shop_reseller_id", default=None)


def set_shop_reseller_id(reseller_user_id: int | None):
    return _shop_reseller_id.set(reseller_user_id)


def reset_shop_reseller_id(token) -> None:
    _shop_reseller_id.reset(token)


def current_shop_reseller_id() -> int | None:
    return _shop_reseller_id.get()


def _effective_reseller_id(reseller_id: int | None) -> int | None:
    if reseller_id is not None:
        return reseller_id
    return _shop_reseller_id.get()


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
    reseller_owner_id: int | None = None,
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
        # Sticky first-touch attribution for reseller shop bots
        if (
            reseller_owner_id
            and user.reseller_id is None
            and user.id != reseller_owner_id
            and user.role == Role.USER.value
        ):
            user.reseller_id = reseller_owner_id
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

    assign_reseller = None
    if reseller_owner_id and not is_admin:
        assign_reseller = reseller_owner_id

    user = BotUser(
        telegram_id=telegram_id,
        username=username,
        full_name=full_name,
        role=Role.ADMIN.value if is_admin else Role.USER.value,
        referral_code=_referral_code(),
        referred_by_id=referred_by_id,
        reseller_id=assign_reseller,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    # Don't attribute the reseller owner to themselves
    if assign_reseller and user.id == assign_reseller:
        user.reseller_id = None
        await session.commit()
        await session.refresh(user)
    return user


async def get_setting(
    session: AsyncSession,
    key: str,
    default: str = "",
    *,
    reseller_id: int | None = None,
) -> str:
    rid = _effective_reseller_id(reseller_id)
    if rid:
        from app.db.models import ResellerSetting

        result = await session.execute(
            select(ResellerSetting).where(
                ResellerSetting.reseller_user_id == rid,
                ResellerSetting.key == key,
            )
        )
        row = result.scalar_one_or_none()
        if row is not None:
            return row.value
    result = await session.execute(select(Setting).where(Setting.key == key))
    row = result.scalar_one_or_none()
    if row:
        return row.value
    return DEFAULT_SETTINGS.get(key, default) if rid else default


async def set_setting(
    session: AsyncSession,
    key: str,
    value: str,
    *,
    reseller_id: int | None = None,
) -> None:
    rid = _effective_reseller_id(reseller_id)
    if rid:
        from app.db.models import ResellerSetting

        result = await session.execute(
            select(ResellerSetting).where(
                ResellerSetting.reseller_user_id == rid,
                ResellerSetting.key == key,
            )
        )
        row = result.scalar_one_or_none()
        if row:
            row.value = value
        else:
            session.add(
                ResellerSetting(reseller_user_id=rid, key=key, value=value)
            )
        await session.commit()
        return
    result = await session.execute(select(Setting).where(Setting.key == key))
    row = result.scalar_one_or_none()
    if row:
        row.value = value
    else:
        session.add(Setting(key=key, value=value))
    await session.commit()


async def set_settings_bulk(
    session: AsyncSession,
    values: dict[str, str],
    *,
    reseller_id: int | None = None,
) -> None:
    """Upsert many settings with a single commit (avoids lock storms on menu save)."""
    rid = _effective_reseller_id(reseller_id)
    if rid:
        from app.db.models import ResellerSetting

        for key, value in values.items():
            result = await session.execute(
                select(ResellerSetting).where(
                    ResellerSetting.reseller_user_id == rid,
                    ResellerSetting.key == key,
                )
            )
            row = result.scalar_one_or_none()
            if row:
                row.value = value
            else:
                session.add(
                    ResellerSetting(reseller_user_id=rid, key=key, value=value)
                )
        await session.commit()
        return
    for key, value in values.items():
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
    # Reseller panel URLs (setup links + messages). Empty = system defaults
    "reseller_panel_base_url": "",
    "reseller_pg_panel_base_url": "",
    # Cached Telegram bot profile (synced via appearance tab → Bot API)
    "bot_tg_name": "",
    "bot_tg_description": "",
    "bot_tg_short_description": "",
    "bot_tg_photo": "",
    "bot_cmd_start": "شروع / منو",
    "bot_cmd_help": "راهنما",

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
    ("appearance", "ظاهر ربات"),
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
    ("backup", "بکاپ"),
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
            "کلاسیک یا فشرده — از تب منوی بات تنظیم می‌شود",
            [("classic", "کلاسیک — هر دکمه یک ردیف"), ("compact", "فشرده — دکمه‌ها جفتی")],
        ),
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
            "اختیاری. خالی = پیش‌فرض سیستم (آی‌پی سرور + پورت پنل، معمولاً :9000). در پیام تأیید برای نماینده ارسال می‌شود.",
        ),
        (
            "reseller_pg_panel_base_url",
            "آدرس پنل پاسارگارد برای نماینده",
            "text",
            "اختیاری. خالی = دقیقاً همان PG_BASE_URL تنظیم‌شده در اتصال بات (با path کامل).",
        ),
    ],
    "هشدار سرویس کاربر": [
        (
            "user_alert_low_enabled",
            "ارسال خودکار هشدار کمبود به کاربر",
            "toggle",
            "وقتی حجم یا زمان باقی‌مانده سرویس کمتر از درصد تعیین‌شده شود، در تلگرام به کاربر پیام می‌رود",
        ),
        (
            "user_alert_low_traffic_pct",
            "کمتر از چند درصد حجم؟",
            "number",
            "۱ تا ۹۹ — مثلاً ۲۰ یعنی وقتی کمتر از ۲۰٪ حجم مانده پیام برود",
        ),
        (
            "user_alert_low_time_pct",
            "کمتر از چند درصد زمان؟",
            "number",
            "۱ تا ۹۹ — مثلاً ۲۰ یعنی وقتی کمتر از ۲۰٪ از مدت سرویس مانده پیام برود",
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
        ("auto_approve_payments", "تأیید خودکار رسید", "toggle", "روشن = بلافاصله بعد از رسید خرید، سرویس تحویل می‌شود. شارژ کیف‌پول هرگز خودکار تأیید نمی‌شود."),
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
    "menu": [],
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
    "reseller": ["نمایندگی"],
    "notifications": ["هشدار سرویس کاربر"],
    "backup": [],
    "update": [],
    "bot": [],
    "appearance": [],
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


_defaults_ready = False


async def ensure_default_settings(session: AsyncSession) -> None:
    """Insert missing default settings once per process (cheap after first call)."""
    global _defaults_ready
    if _defaults_ready:
        return
    result = await session.execute(select(Setting.key))
    existing = {row[0] for row in result.all()}
    missing = False
    for key, value in DEFAULT_SETTINGS.items():
        if key not in existing:
            session.add(Setting(key=key, value=value))
            missing = True
    if missing:
        await session.commit()
    _defaults_ready = True


async def get_all_settings(
    session: AsyncSession,
    *,
    reseller_id: int | None = None,
) -> dict[str, str]:
    # Defaults are seeded at startup — avoid N+1 writes on every read path.
    data = dict(DEFAULT_SETTINGS)
    rid = _effective_reseller_id(reseller_id)
    if rid:
        from app.db.models import ResellerSetting

        # Start from global (fallback), overlay reseller overrides
        result = await session.execute(select(Setting))
        data.update({r.key: r.value for r in result.scalars().all()})
        r_result = await session.execute(
            select(ResellerSetting).where(ResellerSetting.reseller_user_id == rid)
        )
        data.update({r.key: r.value for r in r_result.scalars().all()})
        # Reseller bots never show platform apply / admin buttons
        data["show_reseller_apply"] = "0"
        return data
    result = await session.execute(select(Setting))
    rows = result.scalars().all()
    data.update({r.key: r.value for r in rows})
    return data


def on(value: str | None) -> bool:
    return (value or "").strip() in {"1", "true", "yes", "on", "True"}


def clamp_alert_percent(raw: str | None, default: int = 20) -> str:
    """Keep user-alert thresholds in 1..99."""
    try:
        n = int(float(str(raw).strip()))
    except Exception:
        n = default
    return str(max(1, min(99, n)))


def is_protected_admin(user: BotUser) -> bool:
    """True for panel/bot admins that must not be blocked or deleted."""
    if user.role == Role.ADMIN.value:
        return True
    return user.telegram_id in get_settings().admin_ids


async def delete_bot_user(
    session: AsyncSession,
    user_id: int,
    *,
    delete_pg_services: bool = True,
    delete_pg_admin: bool = True,
    actor_user_id: int | None = None,
) -> dict:
    """Hard-delete a bot user and related rows. Refuses protected admins."""
    from sqlalchemy import delete, update

    from app.db.models import (
        Order,
        Payment,
        ResellerApplication,
        Ticket,
        TicketMessage,
        UserService,
        WalletTransaction,
    )
    from app.services.pasarguard import get_pg

    user = await session.get(BotUser, user_id)
    if not user:
        raise ValueError("کاربر یافت نشد")
    if actor_user_id is not None and user.id == actor_user_id:
        raise ValueError("نمی‌توانید خودتان را حذف کنید")
    if is_protected_admin(user):
        raise ValueError("حذف ادمین مجاز نیست")

    telegram_id = user.telegram_id
    name = user.full_name or user.username or str(telegram_id)

    # Revoke reseller first (profile + PG admin + unlink customers)
    from app.services.resellers import get_reseller_profile, revoke_reseller

    if await get_reseller_profile(session, user_id):
        await revoke_reseller(
            session,
            user_id,
            delete_pg_admin=delete_pg_admin,
            commit=False,
        )

    # Clear self-references pointing at this user
    await session.execute(
        update(BotUser).where(BotUser.referred_by_id == user_id).values(referred_by_id=None)
    )
    # reseller_id / order.reseller_id already cleared by revoke_reseller when applicable
    await session.execute(
        update(BotUser).where(BotUser.reseller_id == user_id).values(reseller_id=None)
    )
    await session.execute(
        update(Order).where(Order.reseller_id == user_id).values(reseller_id=None)
    )

    services = list(
        (
            await session.execute(select(UserService).where(UserService.bot_user_id == user_id))
        ).scalars().all()
    )
    svc_ids = [s.id for s in services]
    pg_services_deleted = 0
    if delete_pg_services:
        for svc in services:
            if not svc.pg_user_id:
                continue
            try:
                await get_pg().delete_user_by_id(int(svc.pg_user_id))
                pg_services_deleted += 1
            except Exception:
                try:
                    await get_pg().set_disabled_by_id(int(svc.pg_user_id), True)
                except Exception:
                    pass

    # Break orders ↔ services cycle
    await session.execute(
        update(Order).where(Order.user_id == user_id).values(service_id=None)
    )
    if svc_ids:
        await session.execute(
            update(Order).where(Order.service_id.in_(svc_ids)).values(service_id=None)
        )

    # Reseller applications (null order_id then delete)
    apps = list(
        (
            await session.execute(
                select(ResellerApplication).where(ResellerApplication.user_id == user_id)
            )
        ).scalars().all()
    )
    for app in apps:
        app.order_id = None
    await session.flush()
    await session.execute(
        delete(ResellerApplication).where(ResellerApplication.user_id == user_id)
    )

    await session.execute(delete(Payment).where(Payment.user_id == user_id))
    await session.execute(delete(Order).where(Order.user_id == user_id))
    await session.execute(delete(UserService).where(UserService.bot_user_id == user_id))

    ticket_ids = list(
        (
            await session.execute(select(Ticket.id).where(Ticket.user_id == user_id))
        ).scalars().all()
    )
    if ticket_ids:
        await session.execute(
            delete(TicketMessage).where(TicketMessage.ticket_id.in_(ticket_ids))
        )
        await session.execute(delete(Ticket).where(Ticket.id.in_(ticket_ids)))

    await session.execute(
        delete(WalletTransaction).where(WalletTransaction.user_id == user_id)
    )

    await session.delete(user)
    await session.commit()

    return {
        "user_id": user_id,
        "telegram_id": telegram_id,
        "name": name,
        "services_removed": len(svc_ids),
        "pg_services_deleted": pg_services_deleted,
    }
