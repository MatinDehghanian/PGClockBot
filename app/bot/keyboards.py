from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

from app.config import get_settings
from app.db.models import Plan, Role
from app.services.support_contacts import (
    active_support_contacts,
    parse_support_contacts,
    support_chat_url,
)
from app.services.users import DEFAULT_SETTINGS, on

# Default order for user menu items (drag-and-drop in web panel edits menu_order)
DEFAULT_MENU_ORDER = [
    "shop",
    "services",
    "wallet",
    "support",
    "guide",
    "faq",
    "referral",
    "reseller_apply",
    "miniapp",
]


def _t(ui: dict | None, key: str) -> str:
    if ui and key in ui and ui[key]:
        return ui[key]
    return DEFAULT_SETTINGS.get(key, key)


def _menu_order(ui: dict | None) -> list[str]:
    raw = _t(ui, "menu_order")
    parts = [p.strip() for p in (raw or "").split(",") if p.strip()]
    known = set(DEFAULT_MENU_ORDER)
    ordered = [p for p in parts if p in known]
    # shop always present
    if "shop" not in ordered:
        ordered.insert(0, "shop")
    # Older saved menu_order may omit newly added keys — inject before miniapp/end
    for key in DEFAULT_MENU_ORDER:
        if key in ordered or key == "shop":
            continue
        if key == "reseller_apply" and not on(_t(ui, "show_reseller_apply")):
            continue
        if key == "miniapp" and not on(_t(ui, "show_miniapp")):
            continue
        if "miniapp" in ordered:
            ordered.insert(ordered.index("miniapp"), key)
        else:
            ordered.append(key)
    return ordered


def main_menu(
    role: str,
    *,
    has_services: bool = False,
    ui: dict | None = None,
    as_user: bool = False,
) -> InlineKeyboardMarkup:
    """
    User/reseller: shop-style sales menu.
    Admin: management home only (no customer shop clutter), unless as_user=True.
    """
    if role == Role.ADMIN.value and not as_user:
        return admin_main_menu(ui)

    settings = get_settings()
    layout = _t(ui, "menu_layout")
    rows: list[list[InlineKeyboardButton]] = []
    pending_row: list[InlineKeyboardButton] = []

    def flush_pending() -> None:
        nonlocal pending_row
        if not pending_row:
            return
        if layout == "compact":
            for i in range(0, len(pending_row), 2):
                rows.append(pending_row[i : i + 2])
        else:
            for b in pending_row:
                rows.append([b])
        pending_row = []

    def add_full(btn: InlineKeyboardButton) -> None:
        flush_pending()
        rows.append([btn])

    def add_mid(btn: InlineKeyboardButton) -> None:
        pending_row.append(btn)

    for key in _menu_order(ui):
        if key == "shop":
            add_full(InlineKeyboardButton(text=_t(ui, "btn_shop"), callback_data="shop:list"))
        elif key == "services" and has_services:
            add_full(InlineKeyboardButton(text=_t(ui, "btn_services"), callback_data="svc:list"))
        elif key == "wallet" and on(_t(ui, "show_wallet")):
            add_mid(InlineKeyboardButton(text=_t(ui, "btn_wallet"), callback_data="wallet:home"))
        elif key == "support" and on(_t(ui, "show_support")):
            contacts = active_support_contacts(
                parse_support_contacts((ui or {}).get("support_contacts"))
            )
            if len(contacts) == 1:
                url = support_chat_url(contacts[0].get("telegram") or "")
                if url:
                    add_mid(
                        InlineKeyboardButton(text=_t(ui, "btn_support"), url=url)
                    )
                else:
                    add_mid(
                        InlineKeyboardButton(
                            text=_t(ui, "btn_support"), callback_data="support:home"
                        )
                    )
            else:
                add_mid(
                    InlineKeyboardButton(
                        text=_t(ui, "btn_support"), callback_data="support:home"
                    )
                )
        elif key == "guide" and on(_t(ui, "show_guide")):
            add_mid(InlineKeyboardButton(text=_t(ui, "btn_guide"), callback_data="help:guide"))
        elif key == "faq" and on(_t(ui, "show_faq")):
            add_mid(InlineKeyboardButton(text=_t(ui, "btn_faq"), callback_data="help:faq"))
        elif key == "referral" and on(_t(ui, "show_referral")):
            add_full(InlineKeyboardButton(text=_t(ui, "btn_referral"), callback_data="ref:home"))
        elif (
            key == "reseller_apply"
            and on(_t(ui, "show_reseller_apply"))
            and role == Role.USER.value
        ):
            add_full(
                InlineKeyboardButton(
                    text=_t(ui, "btn_reseller_apply"),
                    callback_data="resapply:home",
                )
            )
        elif key == "miniapp" and settings.miniapp_enabled and on(_t(ui, "show_miniapp")):
            add_full(
                InlineKeyboardButton(
                    text=_t(ui, "btn_miniapp"),
                    web_app=WebAppInfo(url=settings.miniapp_url),
                )
            )

    flush_pending()

    if role == Role.RESELLER.value:
        rows.append(
            [InlineKeyboardButton(text=_t(ui, "btn_reseller"), callback_data="res:home")]
        )
    if role == Role.ADMIN.value and as_user:
        rows.append(
            [InlineKeyboardButton(text=_t(ui, "btn_admin"), callback_data="adm:home")]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_main_menu(ui: dict | None = None) -> InlineKeyboardMarkup:
    """Primary home for bot owner — management tools only."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_t(ui, "btn_admin"), callback_data="adm:home")],
            [
                InlineKeyboardButton(text="🛒 سفارش‌ها", callback_data="adm:orders"),
                InlineKeyboardButton(text="🧾 رسیدها", callback_data="adm:payments"),
            ],
            [
                InlineKeyboardButton(text="🎫 تیکت‌ها", callback_data="adm:tickets"),
                InlineKeyboardButton(text="📦 پلن‌ها", callback_data="adm:plans"),
            ],
            [
                InlineKeyboardButton(text="🖥 پاسارگارد", callback_data="adm:pg"),
            ],
            [
                InlineKeyboardButton(
                    text="👁 پیش‌نمایش منوی کاربر",
                    callback_data="menu:as_user",
                )
            ],
        ]
    )


def plans_keyboard(
    plans: list[Plan],
    ui: dict | None = None,
    *,
    custom_enabled: bool = False,
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{'🎁' if p.is_trial else '💎'} {p.name} — {p.price:,} ت".replace(",", "٬"),
                callback_data=f"shop:plan:{p.id}",
            )
        ]
        for p in plans
    ]
    if custom_enabled:
        rows.append(
            [
                InlineKeyboardButton(
                    text="✨ پلن دلخواه",
                    callback_data="shop:custom",
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton(text=_t(ui, "btn_back"), callback_data="menu:home")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def custom_gb_keyboard(
    gb: int,
    ui: dict | None = None,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(text="➖", callback_data="shop:custom:gb:-"),
            InlineKeyboardButton(text=f"{gb} گیگ", callback_data="shop:custom:noop"),
            InlineKeyboardButton(text="➕", callback_data="shop:custom:gb:+"),
        ],
        [InlineKeyboardButton(text="✏️ ورود دستی حجم", callback_data="shop:custom:gb:input")],
        [InlineKeyboardButton(text="ادامه ← روزها", callback_data="shop:custom:gb:next")],
        [InlineKeyboardButton(text=_t(ui, "btn_back"), callback_data="shop:list")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def custom_days_keyboard(
    days: int,
    ui: dict | None = None,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="➖", callback_data="shop:custom:days:-"),
                InlineKeyboardButton(text=f"{days} روز", callback_data="shop:custom:noop"),
                InlineKeyboardButton(text="➕", callback_data="shop:custom:days:+"),
            ],
            [InlineKeyboardButton(text="✏️ ورود دستی روز", callback_data="shop:custom:days:input")],
            [InlineKeyboardButton(text="✅ مشاهده قیمت و تأیید", callback_data="shop:custom:confirm")],
            [InlineKeyboardButton(text=_t(ui, "btn_back"), callback_data="shop:custom")],
        ]
    )


def custom_confirm_keyboard(ui: dict | None = None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🟢✅ ادامه خرید", callback_data="shop:custom:buy")],
            [InlineKeyboardButton(text="✏️ تغییر روز", callback_data="shop:custom:gb:next")],
            [InlineKeyboardButton(text="✏️ تغییر حجم", callback_data="shop:custom")],
            [InlineKeyboardButton(text=_t(ui, "btn_back"), callback_data="shop:list")],
        ]
    )


def plan_actions(plan_id: int, ui: dict | None = None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🟢✅ ادامه خرید", callback_data=f"shop:buy:{plan_id}")],
            [InlineKeyboardButton(text=_t(ui, "btn_back"), callback_data="shop:list")],
        ]
    )


def any_checkout_method_enabled(ui: dict | None = None) -> bool:
    """True if at least one real checkout method (not just discount) is on."""
    return any(
        on(_t(ui, k))
        for k in (
            "pay_wallet_enabled",
            "pay_card_enabled",
            "pay_gateway_enabled",
            "pay_crypto_enabled",
            "pay_stars_enabled",
        )
    )


def pay_methods(order_id: int, ui: dict | None = None) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if on(_t(ui, "pay_wallet_enabled")):
        rows.append(
            [
                InlineKeyboardButton(
                    text=_t(ui, "btn_pay_wallet"),
                    callback_data=f"pay:wallet:{order_id}",
                )
            ]
        )
    if on(_t(ui, "pay_card_enabled")):
        rows.append(
            [
                InlineKeyboardButton(
                    text=_t(ui, "btn_pay_card"),
                    callback_data=f"pay:card:{order_id}",
                )
            ]
        )
    if on(_t(ui, "pay_gateway_enabled")):
        rows.append(
            [
                InlineKeyboardButton(
                    text=_t(ui, "btn_pay_gateway"),
                    callback_data=f"pay:gateway:{order_id}",
                )
            ]
        )
    if on(_t(ui, "pay_crypto_enabled")):
        rows.append(
            [
                InlineKeyboardButton(
                    text=_t(ui, "btn_pay_crypto"),
                    callback_data=f"pay:crypto:{order_id}",
                )
            ]
        )
    if on(_t(ui, "pay_stars_enabled")):
        rows.append(
            [
                InlineKeyboardButton(
                    text=_t(ui, "btn_pay_stars"),
                    callback_data=f"pay:stars:{order_id}",
                )
            ]
        )
    if on(_t(ui, "pay_discount_enabled")):
        rows.append(
            [
                InlineKeyboardButton(
                    text=_t(ui, "btn_pay_discount"),
                    callback_data=f"pay:discount:{order_id}",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=_t(ui, "btn_cancel"),
                callback_data="menu:home",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def topup_pay_methods(ui: dict | None = None) -> InlineKeyboardMarkup:
    """Payment methods for wallet top-up (no wallet method). Amount lives in FSM."""
    rows: list[list[InlineKeyboardButton]] = []
    if on(_t(ui, "pay_card_enabled")):
        rows.append(
            [InlineKeyboardButton(text=_t(ui, "btn_pay_card"), callback_data="wtop:card")]
        )
    if on(_t(ui, "pay_gateway_enabled")):
        rows.append(
            [
                InlineKeyboardButton(
                    text=_t(ui, "btn_pay_gateway"),
                    callback_data="wtop:gateway",
                )
            ]
        )
    if on(_t(ui, "pay_crypto_enabled")):
        rows.append(
            [
                InlineKeyboardButton(
                    text=_t(ui, "btn_pay_crypto"),
                    callback_data="wtop:crypto",
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton(text=_t(ui, "btn_cancel"), callback_data="wallet:home")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def services_keyboard(services: list, ui: dict | None = None) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"🔹 {s.pg_username}",
                callback_data=f"svc:view:{s.id}",
            )
        ]
        for s in services
    ]
    rows.append(
        [InlineKeyboardButton(text=_t(ui, "btn_back"), callback_data="menu:home")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def service_actions(service_id: int, ui: dict | None = None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_t(ui, "btn_sub_link"),
                    callback_data=f"svc:link:{service_id}",
                ),
                InlineKeyboardButton(
                    text=_t(ui, "btn_renew"),
                    callback_data=f"svc:renew:{service_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="♻️ رفرش وضعیت",
                    callback_data=f"svc:view:{service_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=_t(ui, "btn_back"),
                    callback_data="svc:list",
                )
            ],
        ]
    )


def wallet_keyboard(ui: dict | None = None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🟢➕ شارژ کیف پول", callback_data="wallet:topup")],
            [InlineKeyboardButton(text="🟡📜 تراکنش‌ها", callback_data="wallet:tx")],
            [InlineKeyboardButton(text=_t(ui, "btn_back"), callback_data="menu:home")],
        ]
    )


def support_keyboard(ui: dict | None = None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🟣✉️ تیکت جدید", callback_data="support:new")],
            [InlineKeyboardButton(text="📋 تیکت‌های من", callback_data="support:list")],
            [InlineKeyboardButton(text=_t(ui, "btn_back"), callback_data="menu:home")],
        ]
    )


def support_contacts_keyboard(contacts: list[dict], ui: dict | None = None) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for c in contacts:
        url = support_chat_url(c.get("telegram") or "")
        title = str(c.get("title") or "پشتیبان")[:64]
        if url:
            rows.append([InlineKeyboardButton(text=f"💬 {title}", url=url)])
    rows.append(
        [InlineKeyboardButton(text="🟣✉️ تیکت پشتیبانی", callback_data="support:tickets")]
    )
    rows.append([InlineKeyboardButton(text=_t(ui, "btn_back"), callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_home() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🧾 رسیدها", callback_data="adm:payments"),
                InlineKeyboardButton(text="🛒 سفارش‌ها", callback_data="adm:orders"),
            ],
            [
                InlineKeyboardButton(text="🎫 تیکت‌ها", callback_data="adm:tickets"),
                InlineKeyboardButton(text="📊 داشبورد", callback_data="adm:dash"),
            ],
            [InlineKeyboardButton(text="💎 پلن‌ها", callback_data="adm:plans")],
            [
                InlineKeyboardButton(text="👥 کاربران", callback_data="adm:users"),
                InlineKeyboardButton(text="🤝 نمایندگان", callback_data="adm:resellers"),
            ],
            [InlineKeyboardButton(text="📢 پیام گروهی", callback_data="adm:broadcast")],
            [InlineKeyboardButton(text="🖥 پاسارگارد", callback_data="adm:pg")],
            [InlineKeyboardButton(text="⚙️ تنظیمات", callback_data="adm:settings")],
            [InlineKeyboardButton(text="⬅️ منوی اصلی", callback_data="menu:home")],
        ]
    )


def admin_users_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔎 جستجو با آیدی تلگرام", callback_data="adm:users:search")],
            [
                InlineKeyboardButton(
                    text="🌐 مدیریت کامل در وب‌پنل",
                    callback_data="adm:users:webhint",
                )
            ],
            [InlineKeyboardButton(text="⬅️ بازگشت", callback_data="adm:home")],
        ]
    )


def admin_user_actions(
    user_id: int,
    *,
    is_blocked: bool,
    role: str | None = None,
    confirm_delete: bool = False,
) -> InlineKeyboardMarkup:
    block_label = "🔓 رفع مسدودی" if is_blocked else "🚫 مسدود کردن"
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text=block_label, callback_data=f"adm:users:block:{user_id}")],
    ]
    if role == "reseller":
        rows.append(
            [
                InlineKeyboardButton(
                    text="🤝 حذف نمایندگی",
                    callback_data=f"adm:users:unres:{user_id}",
                )
            ]
        )
    if confirm_delete:
        rows.append(
            [
                InlineKeyboardButton(
                    text="⚠️ تأیید حذف کامل کاربر",
                    callback_data=f"adm:users:del:{user_id}",
                )
            ]
        )
        rows.append(
            [InlineKeyboardButton(text="⬅️ انصراف", callback_data=f"adm:users:view:{user_id}")]
        )
    else:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🗑 حذف کامل کاربر",
                    callback_data=f"adm:users:delask:{user_id}",
                )
            ]
        )
        rows.append(
            [InlineKeyboardButton(text="🔎 جستجوی دیگر", callback_data="adm:users:search")]
        )
        rows.append([InlineKeyboardButton(text="⬅️ بازگشت", callback_data="adm:users")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def order_review(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🟢✅ تأیید سفارش", callback_data=f"ordrev:ok:{order_id}"),
                InlineKeyboardButton(text="🔴❌ رد", callback_data=f"ordrev:no:{order_id}"),
            ],
            [InlineKeyboardButton(text="⬅️ لیست سفارش‌ها", callback_data="adm:orders")],
        ]
    )


def pg_admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔎 جستجوی یوزر", callback_data="adm:pg:search")],
            [InlineKeyboardButton(text="📊 آمار سیستم", callback_data="adm:pg:stats")],
            [InlineKeyboardButton(text="🕸 نودها", callback_data="adm:pg:nodes")],
            [
                InlineKeyboardButton(text="📁 ساخت گروه", callback_data="adm:pg:group"),
                InlineKeyboardButton(text="📋 ساخت تمپلیت", callback_data="adm:pg:template"),
            ],
            [InlineKeyboardButton(text="⬅️ بازگشت", callback_data="adm:home")],
        ]
    )


def reseller_home(profile=None) -> InlineKeyboardMarkup:
    from app.services.resellers import has_bot_perm

    rows: list[list[InlineKeyboardButton]] = []
    if profile is None or has_bot_perm(profile, "dashboard"):
        rows.append([InlineKeyboardButton(text="🏠 خانه نماینده", callback_data="res:dash")])
    if profile is None or has_bot_perm(profile, "stats"):
        rows.append([InlineKeyboardButton(text="📊 آمار و کمیسیون", callback_data="res:stats")])
    if profile is not None and has_bot_perm(profile, "orders"):
        rows.append([InlineKeyboardButton(text="🛒 سفارش‌های مشتریان", callback_data="res:orders")])
    if profile is not None and has_bot_perm(profile, "payments"):
        rows.append(
            [InlineKeyboardButton(text="🧾 رسیدهای در انتظار", callback_data="res:payments")]
        )
    if profile is not None and has_bot_perm(profile, "tickets"):
        rows.append([InlineKeyboardButton(text="🎫 تیکت‌های مشتریان", callback_data="res:tickets")])
    rows.append([InlineKeyboardButton(text="⬅️ بازگشت", callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reseller_app_review(app_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🟢✅ تأیید", callback_data=f"adm:resapp:ok:{app_id}"),
                InlineKeyboardButton(text="🔴❌ رد", callback_data=f"adm:resapp:no:{app_id}"),
            ],
            [InlineKeyboardButton(text="⬅️ درخواست‌ها", callback_data="adm:resapp:list")],
        ]
    )


def admin_resellers_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 درخواست‌های در انتظار", callback_data="adm:resapp:list")],
            [InlineKeyboardButton(text="➕ افزودن دستی نماینده", callback_data="adm:resellers:add")],
            [InlineKeyboardButton(text="⬅️ بازگشت", callback_data="adm:home")],
        ]
    )


def payment_review(payment_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🟢✅ تأیید دستی", callback_data=f"payrev:ok:{payment_id}"),
                InlineKeyboardButton(text="🔴❌ رد", callback_data=f"payrev:no:{payment_id}"),
            ]
        ]
    )


def back_home(ui: dict | None = None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_t(ui, "btn_back"), callback_data="menu:home")]
        ]
    )


def cancel_reply() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="انصراف")]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
