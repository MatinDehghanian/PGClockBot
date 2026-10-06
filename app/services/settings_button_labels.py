"""Button-label field groups for Telegram / web settings hubs.

Telegram settings keep ≤8 fields per screen; groups map to related IA
categories (main menu, wallet submenu, pay methods, admin keyboard, …).

``PLATFORM_ONLY_BTN_KEYS`` must never appear on reseller/shop settings
(bot or web) — platform apply / miniapp / admin keyboard labels.
"""

from __future__ import annotations

Field = tuple[str, str, str]

# Platform-only labels — shop/reseller must not edit these.
PLATFORM_ONLY_BTN_KEYS: frozenset[str] = frozenset(
    {
        "btn_reseller_apply",
        "btn_miniapp",
        "btn_admin",
        "btn_reseller_creds",
        "btn_adm_orders",
        "btn_adm_payments",
        "btn_adm_tickets",
        "btn_adm_plans",
        "btn_adm_pg",
        "btn_adm_users",
        "btn_adm_settings",
        "btn_adm_broadcast",
        "btn_adm_preview",
    }
)

# --- Shop / customer-facing button groups (Telegram subsection payloads) ---

BTN_MAIN_MENU: list[Field] = [
    ("btn_shop", "خرید", "text"),
    ("btn_services", "سرویس‌ها", "text"),
    ("btn_wallet", "کیف پول", "text"),
    ("btn_support", "پشتیبانی", "text"),
    ("btn_loyalty", "باشگاه مشتریان", "text"),
    ("btn_reseller_apply", "درخواست نمایندگی", "text"),
    ("btn_miniapp", "مینی‌اپ", "text"),
    ("btn_wholesale", "فروش عمده", "text"),
]

BTN_WALLET_SUB: list[Field] = [
    ("btn_wallet_topup", "شارژ کیف پول", "text"),
    ("btn_wallet_tx", "تراکنش‌ها", "text"),
]

BTN_SUPPORT_SUB: list[Field] = [
    ("btn_support_new", "تیکت جدید", "text"),
    ("btn_support_list", "تیکت‌های من", "text"),
]

BTN_LOYALTY_SUB: list[Field] = [
    ("btn_referral", "دعوت دوستان", "text"),
    ("btn_loy_points", "امتیاز من", "text"),
    ("btn_loy_rewards", "جوایز", "text"),
    ("btn_loy_wheel", "چرخ شانس", "text"),
    ("btn_loy_history", "تاریخچه باشگاه", "text"),
]

BTN_SERVICE_ACTIONS: list[Field] = [
    ("btn_renew", "تمدید", "text"),
    ("btn_svc_addon", "حجم / زمان", "text"),
    ("btn_sub_link", "لینک و QR", "text"),
    ("btn_cancel", "انصراف", "text"),
]

BTN_NAV: list[Field] = [
    ("btn_menu_home", "منوی اصلی", "text"),
    ("btn_back", "بازگشت", "text"),
    ("btn_guide", "راهنما", "text"),
    ("btn_faq", "سوالات", "text"),
]

BTN_ROLES: list[Field] = [
    ("btn_admin", "پنل ادمین", "text"),
    ("btn_reseller", "پنل نماینده", "text"),
    ("btn_reseller_creds", "اطلاعات ورود نماینده", "text"),
]

BTN_ADMIN_OPS: list[Field] = [
    ("btn_adm_orders", "سفارش‌ها", "text"),
    ("btn_adm_payments", "رسیدها", "text"),
    ("btn_adm_tickets", "تیکت‌ها", "text"),
    ("btn_adm_plans", "پلن‌ها", "text"),
    ("btn_adm_pg", "پاسارگارد", "text"),
]

BTN_ADMIN_SYS: list[Field] = [
    ("btn_adm_users", "کاربران", "text"),
    ("btn_adm_settings", "تنظیمات", "text"),
    ("btn_adm_broadcast", "پیام گروهی", "text"),
    ("btn_adm_preview", "پیش‌نمایش کاربر", "text"),
]

# Shared pay-method button labels (attached beside each method screen).
BTN_PAY_WALLET_DISCOUNT: list[Field] = [
    ("btn_pay_wallet", "پرداخت از کیف پول", "text"),
    ("btn_pay_discount", "کد تخفیف", "text"),
]

BTN_PAY_CARD: list[Field] = [("btn_pay_card", "متن دکمه کارت", "text")]
BTN_PAY_GATEWAY: list[Field] = [("btn_pay_gateway", "متن دکمه درگاه", "text")]
BTN_PAY_CRYPTO: list[Field] = [("btn_pay_crypto", "متن دکمه رمزارز", "text")]
BTN_PAY_STARS: list[Field] = [("btn_pay_stars", "متن دکمه استارز", "text")]
BTN_PAY_PSP: list[Field] = [("btn_pay_psp", "متن دکمه درگاه API", "text")]


def filter_btn_fields(
    fields: list[Field], *, include_platform: bool
) -> list[Field]:
    if include_platform:
        return list(fields)
    return [f for f in fields if f[0] not in PLATFORM_ONLY_BTN_KEYS]


def shop_button_subs(*, include_platform: bool) -> list[tuple]:
    """Telegram shop-section subsections for button label editing."""
    pairs: list[tuple[str, str, list[Field]]] = [
        ("btn_main", "دکمه‌های منوی اصلی", BTN_MAIN_MENU),
        ("btn_wallet_sub", "دکمه‌های کیف پول", BTN_WALLET_SUB),
        ("btn_support_sub", "دکمه‌های پشتیبانی", BTN_SUPPORT_SUB),
        ("btn_loyalty_sub", "دکمه‌های باشگاه", BTN_LOYALTY_SUB),
        ("btn_service", "دکمه‌های سرویس", BTN_SERVICE_ACTIONS),
        ("btn_nav", "دکمه‌های ناوبری", BTN_NAV),
        ("btn_roles", "دکمه‌های نقش‌ها", BTN_ROLES),
        ("btn_adm_ops", "دکمه‌های ادمین — عملیات", BTN_ADMIN_OPS),
        ("btn_adm_sys", "دکمه‌های ادمین — سیستم", BTN_ADMIN_SYS),
    ]
    out: list[tuple] = []
    for sub_id, title, fields in pairs:
        filtered = filter_btn_fields(fields, include_platform=include_platform)
        if filtered:
            out.append((sub_id, title, filtered))
    return out


def all_btn_field_keys(*, include_platform: bool) -> frozenset[str]:
    """Every btn_* label key exposed via shop_button_subs + pay button lists."""
    keys: set[str] = set()
    for _, _, fields in shop_button_subs(include_platform=include_platform):
        keys.update(f[0] for f in fields)
    for group in (
        BTN_PAY_WALLET_DISCOUNT,
        BTN_PAY_CARD,
        BTN_PAY_GATEWAY,
        BTN_PAY_CRYPTO,
        BTN_PAY_STARS,
        BTN_PAY_PSP,
    ):
        keys.update(
            f[0]
            for f in filter_btn_fields(group, include_platform=include_platform)
        )
    return frozenset(keys)
