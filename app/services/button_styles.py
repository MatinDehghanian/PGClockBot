"""Telegram Bot API 9.4 button colors — catalog, defaults, and lookups.

Telegram only supports: primary (blue), success (green), danger (red),
or omit style for the client default (white/gray).
"""

from __future__ import annotations

from typing import Any

# value, label, UI tone class (for colors tab selects)
STYLE_OPTIONS: list[tuple[str, str, str]] = [
    ("", "سفید", "default"),
    ("primary", "آبی", "primary"),
    ("success", "سبز", "success"),
    ("danger", "قرمز", "danger"),
]

# Reply review actions that share global confirm / reject chrome.
STYLE_ALIASES: dict[str, str] = {
    "rev_ok": "confirm",
    "rev_no": "reject",
    "referral": "loy_referral",
    "shop_custom": "shop_kind_custom",
    "shop_wholesale": "shop_kind_wholesale",
    "adm_plans_kind_users_fixed": "shop_kind_fixed",
    "adm_plans_kind_users_custom": "shop_kind_custom",
    "adm_plans_kind_users_wholesale": "shop_kind_wholesale",
    "adm_plans_kind_res_fixed": "plan_res_fixed",
    "adm_plans_kind_res_payg": "plan_res_payg",
    "adm_plans_kind_users_trial": "shop_kind_trial",
    "adm_plan_add": "adm_plans_add",
    "adm_plan_custom": "shop_kind_custom",
    "adm_plan_trial": "shop_kind_trial",
}

# id must match reply action keys where applicable (shop, services, …).
BUTTON_STYLE_CATALOG: list[dict[str, str]] = [
    # Global chrome — one place for consistent nav / confirm / cancel
    {
        "id": "home",
        "label": "منوی اصلی / صفحه اصلی",
        "group": "دکمه‌های سراسری",
        "default": "",
    },
    {
        "id": "back",
        "label": "بازگشت",
        "group": "دکمه‌های سراسری",
        "default": "",
    },
    {
        "id": "cancel",
        "label": "انصراف / لغو",
        "group": "دکمه‌های سراسری",
        "default": "danger",
    },
    {
        "id": "confirm",
        "label": "تأیید",
        "group": "دکمه‌های سراسری",
        "default": "success",
    },
    {
        "id": "reject",
        "label": "رد",
        "group": "دکمه‌های سراسری",
        "default": "danger",
    },
    # Main menu
    {"id": "shop", "label": "خرید اشتراک", "group": "منوی اصلی", "default": "primary"},
    {"id": "services", "label": "سرویس‌های من", "group": "منوی اصلی", "default": "primary"},
    {"id": "wallet", "label": "کیف پول", "group": "منوی اصلی", "default": "primary"},
    {"id": "support", "label": "پشتیبانی", "group": "منوی اصلی", "default": "primary"},
    {"id": "loyalty", "label": "باشگاه مشتریان", "group": "منوی اصلی", "default": "success"},
    {"id": "reseller_apply", "label": "درخواست نمایندگی", "group": "منوی اصلی", "default": ""},
    {"id": "reseller", "label": "پنل نماینده", "group": "منوی اصلی", "default": ""},
    {"id": "reseller_creds", "label": "اطلاعات ورود نماینده", "group": "منوی اصلی", "default": ""},
    {"id": "admin", "label": "پنل ادمین", "group": "منوی اصلی", "default": ""},
    # Wallet / support sub
    {"id": "wallet_topup", "label": "شارژ کیف پول", "group": "زیرمنوها", "default": "primary"},
    {"id": "support_new", "label": "تیکت جدید", "group": "زیرمنوها", "default": "primary"},
    {"id": "svc_renew", "label": "تمدید سرویس", "group": "زیرمنوها", "default": "primary"},
    {"id": "svc_link", "label": "لینک و QR", "group": "زیرمنوها", "default": ""},
    {"id": "wallet_tx", "label": "تراکنش‌های کیف پول", "group": "زیرمنوها", "default": ""},
    {"id": "support_list", "label": "تیکت‌های من", "group": "زیرمنوها", "default": ""},
    {"id": "svc_refresh", "label": "رفرش وضعیت سرویس", "group": "زیرمنوها", "default": ""},
    {"id": "miniapp", "label": "مینی‌اپ (منوی اصلی)", "group": "زیرمنوها", "default": "primary"},
    # Shop flow (inline)
    {"id": "shop_kind_fixed", "label": "نوع پلن کاربر: ثابت", "group": "فروشگاه", "default": "primary"},
    {"id": "shop_kind_custom", "label": "نوع پلن کاربر: دلخواه", "group": "فروشگاه", "default": "primary"},
    {"id": "shop_kind_wholesale", "label": "نوع پلن کاربر: عمده", "group": "فروشگاه", "default": "primary"},
    {"id": "shop_kind_trial", "label": "نوع پلن کاربر: تست", "group": "فروشگاه", "default": "primary"},
    {"id": "buy_continue", "label": "ادامه خرید / تأیید پلن", "group": "فروشگاه", "default": "primary"},
    {"id": "force_join_check", "label": "عضو شدم (کانال اجباری)", "group": "فروشگاه", "default": "primary"},
    {"id": "one_tap_renew", "label": "تمدید یک‌ضربی (هشدار انقضا)", "group": "فروشگاه", "default": "primary"},
    # Reseller audience plans (admin)
    {
        "id": "plan_res_fixed",
        "label": "پلن نمایندگی: ثابت",
        "group": "پلن نمایندگی",
        "default": "primary",
    },
    {
        "id": "plan_res_payg",
        "label": "پلن نمایندگی: PAYG",
        "group": "پلن نمایندگی",
        "default": "primary",
    },
    # Payment
    {"id": "pay_wallet", "label": "پرداخت با کیف پول", "group": "پرداخت", "default": "success"},
    {"id": "pay_card", "label": "کارت به کارت", "group": "پرداخت", "default": "primary"},
    {"id": "pay_gateway", "label": "درگاه پرداخت", "group": "پرداخت", "default": "primary"},
    {"id": "pay_crypto", "label": "رمزارز", "group": "پرداخت", "default": "primary"},
    {"id": "pay_stars", "label": "استارز تلگرام", "group": "پرداخت", "default": "primary"},
    {"id": "pay_discount", "label": "کد تخفیف", "group": "پرداخت", "default": ""},
    {"id": "topup_card", "label": "شارژ — کارت", "group": "پرداخت", "default": "primary"},
    {"id": "topup_gateway", "label": "شارژ — درگاه", "group": "پرداخت", "default": "primary"},
    {"id": "topup_crypto", "label": "شارژ — رمزارز", "group": "پرداخت", "default": "primary"},
    # Customer loyalty sub
    {"id": "loy_referral", "label": "دعوت دوستان", "group": "باشگاه مشتریان", "default": "primary"},
    {"id": "loy_points", "label": "امتیاز من", "group": "باشگاه مشتریان", "default": ""},
    {"id": "loy_rewards", "label": "جوایز باشگاه", "group": "باشگاه مشتریان", "default": ""},
    {"id": "loy_history", "label": "تاریخچه باشگاه", "group": "باشگاه مشتریان", "default": ""},
    # Admin menu highlights
    {"id": "adm_dash", "label": "داشبورد ادمین", "group": "منوی ادمین", "default": "success"},
    {"id": "adm_orders", "label": "سفارش‌ها (ادمین)", "group": "منوی ادمین", "default": "success"},
    {"id": "adm_payments", "label": "رسیدها (ادمین)", "group": "منوی ادمین", "default": "success"},
    {"id": "res_orders", "label": "سفارش‌ها (نماینده)", "group": "منوی ادمین", "default": "success"},
    {"id": "res_payments", "label": "رسیدها (نماینده)", "group": "منوی ادمین", "default": "success"},
    {"id": "res_renew", "label": "تمدید ظرفیت نماینده", "group": "منوی ادمین", "default": "primary"},
    {"id": "res_buy_gb", "label": "خرید حجم نماینده", "group": "منوی ادمین", "default": "primary"},
    {"id": "res_buy_users", "label": "خرید کاربر نماینده", "group": "منوی ادمین", "default": "primary"},
    {"id": "adm_tickets", "label": "تیکت‌ها (ادمین)", "group": "منوی ادمین", "default": "success"},
    {"id": "adm_plans", "label": "پلن‌ها (ادمین)", "group": "منوی ادمین", "default": "success"},
    {"id": "adm_users", "label": "کاربران (ادمین)", "group": "منوی ادمین", "default": "success"},
    {"id": "adm_resellers", "label": "نمایندگان (ادمین)", "group": "منوی ادمین", "default": "success"},
    {"id": "adm_loyalty", "label": "باشگاه مشتریان (ادمین)", "group": "منوی ادمین", "default": "success"},
    {"id": "adm_pg", "label": "پاسارگارد (ادمین)", "group": "منوی ادمین", "default": "success"},
    {"id": "adm_settings", "label": "تنظیمات (ادمین)", "group": "منوی ادمین", "default": ""},
    {"id": "adm_broadcast", "label": "پیام همگانی (ادمین)", "group": "منوی ادمین", "default": ""},
    {"id": "adm_backup", "label": "بکاپ / ریستور (ادمین)", "group": "منوی ادمین", "default": ""},
    {"id": "adm_preview", "label": "پیش‌نمایش منوی کاربر (ادمین)", "group": "منوی ادمین", "default": ""},
    {"id": "adm_users_list", "label": "لیست کاربران", "group": "منوی ادمین", "default": ""},
    {"id": "adm_users_search", "label": "جستجوی کاربر", "group": "منوی ادمین", "default": ""},
    {"id": "adm_users_web", "label": "مدیریت کاربران در وب", "group": "منوی ادمین", "default": ""},
    {"id": "adm_res_list", "label": "لیست نمایندگان", "group": "منوی ادمین", "default": ""},
    {"id": "adm_res_apps", "label": "درخواست‌های نمایندگی", "group": "منوی ادمین", "default": ""},
    {"id": "adm_res_add", "label": "افزودن نماینده", "group": "منوی ادمین", "default": "primary"},
    {"id": "adm_plans_aud_users", "label": "پلن‌های کاربران", "group": "منوی ادمین", "default": "primary"},
    {"id": "adm_plans_aud_resellers", "label": "پلن‌های نمایندگان", "group": "منوی ادمین", "default": "primary"},
    {"id": "adm_plans_add", "label": "افزودن پلن", "group": "منوی ادمین", "default": "primary"},
    # Admin loyalty sub
    {"id": "adm_loy_overview", "label": "نمای کلی باشگاه", "group": "باشگاه ادمین", "default": "success"},
    {"id": "adm_loy_rules", "label": "قوانین امتیاز", "group": "باشگاه ادمین", "default": ""},
    {"id": "adm_loy_rewards", "label": "جوایز باشگاه (ادمین)", "group": "باشگاه ادمین", "default": ""},
    {"id": "adm_loy_tiers", "label": "سطوح باشگاه", "group": "باشگاه ادمین", "default": ""},
    {"id": "adm_loy_settings", "label": "تنظیمات باشگاه", "group": "باشگاه ادمین", "default": ""},
    {"id": "adm_loy_ref_text", "label": "متن دعوت باشگاه", "group": "باشگاه ادمین", "default": ""},
    # PasarGuard sub
    {"id": "pg_stats", "label": "نمای کلی پاسارگارد", "group": "پاسارگارد", "default": "success"},
    {"id": "pg_users", "label": "کاربران پاسارگارد", "group": "پاسارگارد", "default": ""},
    {"id": "pg_create", "label": "ساخت کاربر پاسارگارد", "group": "پاسارگارد", "default": "primary"},
    {"id": "pg_search", "label": "جستجوی کاربر پاسارگارد", "group": "پاسارگارد", "default": ""},
    {"id": "pg_nodes", "label": "نودهای پاسارگارد", "group": "پاسارگارد", "default": ""},
    {"id": "pg_group", "label": "ساخت گروه پاسارگارد", "group": "پاسارگارد", "default": "primary"},
    {"id": "pg_template", "label": "ساخت تمپلیت پاسارگارد", "group": "پاسارگارد", "default": "primary"},
    # Admin settings sub
    {"id": "adm_st_shop", "label": "تنظیمات: فروشگاه و متون", "group": "تنظیمات ادمین", "default": ""},
    {"id": "adm_st_menu", "label": "تنظیمات: کیبورد اصلی", "group": "تنظیمات ادمین", "default": ""},
    {"id": "adm_st_pay", "label": "تنظیمات: پرداخت", "group": "تنظیمات ادمین", "default": ""},
    {"id": "adm_st_support", "label": "تنظیمات: پشتیبان‌ها", "group": "تنظیمات ادمین", "default": ""},
    {"id": "adm_st_service", "label": "تنظیمات: سرویس و دسترسی", "group": "تنظیمات ادمین", "default": ""},
    {"id": "adm_st_notify", "label": "تنظیمات: اعلان‌ها", "group": "تنظیمات ادمین", "default": ""},
    # Backup sub
    {"id": "backup_create", "label": "ساخت بکاپ کامل", "group": "بکاپ", "default": "primary"},
    {"id": "backup_create_noenv", "label": "بکاپ بدون .env", "group": "بکاپ", "default": "primary"},
    {"id": "backup_upload", "label": "آپلود فایل بکاپ", "group": "بکاپ", "default": ""},
    {"id": "backup_refresh", "label": "تازه‌سازی لیست بکاپ", "group": "بکاپ", "default": ""},
    # Broadcast audience
    {"id": "bc_aud_all", "label": "همگانی: همه", "group": "پیام همگانی", "default": ""},
    {"id": "bc_aud_users", "label": "همگانی: کاربران", "group": "پیام همگانی", "default": ""},
    {"id": "bc_aud_resellers", "label": "همگانی: نمایندگان", "group": "پیام همگانی", "default": ""},
    {"id": "bc_aud_admins", "label": "همگانی: ادمین‌ها", "group": "پیام همگانی", "default": ""},
    # Reseller hub
    {"id": "res_dash", "label": "خانه نماینده", "group": "منوی نماینده", "default": "success"},
    {"id": "res_users", "label": "مشتریان نماینده", "group": "منوی نماینده", "default": "success"},
    {"id": "res_billing", "label": "کیف پول PAYG", "group": "منوی نماینده", "default": "success"},
    {"id": "res_stats", "label": "آمار و کمیسیون", "group": "منوی نماینده", "default": "success"},
    {"id": "res_plans", "label": "پلن‌های فروش", "group": "منوی نماینده", "default": "primary"},
    {"id": "res_plan_add", "label": "افزودن پلن نماینده", "group": "منوی نماینده", "default": "primary"},
    {"id": "res_tickets", "label": "تیکت‌های مشتریان", "group": "منوی نماینده", "default": "success"},
    {"id": "res_loyalty", "label": "باشگاه مشتریان (نماینده)", "group": "منوی نماینده", "default": "success"},
    {"id": "res_settings", "label": "تنظیمات فروشگاه", "group": "منوی نماینده", "default": ""},
    {"id": "res_preview", "label": "پیش‌نمایش منوی کاربر", "group": "منوی نماینده", "default": ""},
    # Reseller settings sub
    {"id": "res_st_shop", "label": "تنظیمات نماینده: فروشگاه", "group": "تنظیمات نماینده", "default": ""},
    {"id": "res_st_menu", "label": "تنظیمات نماینده: کیبورد", "group": "تنظیمات نماینده", "default": ""},
    {"id": "res_st_pay", "label": "تنظیمات نماینده: پرداخت", "group": "تنظیمات نماینده", "default": ""},
    {"id": "res_st_support", "label": "تنظیمات نماینده: پشتیبانی", "group": "تنظیمات نماینده", "default": ""},
    {"id": "res_st_access", "label": "تنظیمات نماینده: دسترسی", "group": "تنظیمات نماینده", "default": ""},
    {"id": "res_st_bot", "label": "تنظیمات نماینده: ربات", "group": "تنظیمات نماینده", "default": ""},
    {"id": "res_st_notify", "label": "تنظیمات نماینده: اعلان‌ها", "group": "تنظیمات نماینده", "default": ""},
]

CATALOG_BY_ID: dict[str, dict[str, str]] = {item["id"]: item for item in BUTTON_STYLE_CATALOG}
CATALOG_IDS: frozenset[str] = frozenset(CATALOG_BY_ID) | frozenset(STYLE_ALIASES)


def resolve_style_id(button_id: str) -> str:
    """Map aliased actions onto their global chrome setting id."""
    bid = (button_id or "").strip()
    return STYLE_ALIASES.get(bid, bid)


def setting_key(button_id: str) -> str:
    return f"btn_style_{resolve_style_id(button_id)}"


def normalize_style(raw: str | None) -> str:
    v = (raw or "").strip().lower()
    if v in {"primary", "success", "danger"}:
        return v
    return ""


def get_button_style(
    ui: dict | None,
    button_id: str,
    *,
    fallback: str | None = None,
) -> str:
    """Resolve style for a catalog button. Empty string = Telegram default (white)."""
    resolved = resolve_style_id(button_id)
    key = f"btn_style_{resolved}"
    if ui is not None and key in ui:
        return normalize_style(ui.get(key))
    if fallback is not None:
        return normalize_style(fallback)
    item = CATALOG_BY_ID.get(resolved)
    if item:
        return normalize_style(item["default"])
    return ""


def style_or_none(
    ui: dict | None,
    button_id: str,
    *,
    fallback: str | None = None,
) -> str | None:
    """Like get_button_style but None when white/default (omit Telegram ``style``)."""
    s = get_button_style(ui, button_id, fallback=fallback)
    return s or None


def style_kwargs(
    ui: dict | None,
    button_id: str,
    *,
    fallback: str | None = None,
) -> dict[str, str]:
    s = style_or_none(ui, button_id, fallback=fallback)
    return {"style": s} if s else {}


def default_settings() -> dict[str, str]:
    return {f"btn_style_{item['id']}": item["default"] for item in BUTTON_STYLE_CATALOG}


def setting_group_fields() -> list[tuple[Any, ...]]:
    """SETTING_GROUPS entries (select) so keys_for_tab / save stay in sync."""
    opts = [(value, label) for value, label, _tone in STYLE_OPTIONS]
    fields: list[tuple[Any, ...]] = []
    for item in BUTTON_STYLE_CATALOG:
        fields.append(
            (
                f"btn_style_{item['id']}",
                item["label"],
                "select",
                item["group"],
                opts,
            )
        )
    return fields


def grouped_catalog(*, for_reseller: bool = False) -> list[tuple[str, list[dict[str, str]]]]:
    """Preserve catalog order; group consecutive items by ``group``."""
    skip_groups = (
        {
            "منوی ادمین",
            "پلن نمایندگی",
            "پاسارگارد",
            "تنظیمات ادمین",
            "بکاپ",
            "پیام همگانی",
            "باشگاه ادمین",
        }
        if for_reseller
        else set()
    )
    skip_ids: set[str] = set()
    if for_reseller:
        skip_ids = {
            "admin",
            "reseller_apply",
            "reseller_creds",
            "plan_res_fixed",
            "plan_res_payg",
        }
        for item in BUTTON_STYLE_CATALOG:
            bid = item["id"]
            if bid.startswith("adm_"):
                skip_ids.add(bid)
    groups: list[tuple[str, list[dict[str, str]]]] = []
    current_name = ""
    current_items: list[dict[str, str]] = []
    for item in BUTTON_STYLE_CATALOG:
        if item["group"] in skip_groups or item["id"] in skip_ids:
            continue
        g = item["group"]
        if g != current_name:
            if current_items:
                groups.append((current_name, current_items))
            current_name = g
            current_items = []
        current_items.append(
            {
                "id": item["id"],
                "key": f"btn_style_{item['id']}",
                "label": item["label"],
                "default": item["default"],
            }
        )
    if current_items:
        groups.append((current_name, current_items))
    return groups
