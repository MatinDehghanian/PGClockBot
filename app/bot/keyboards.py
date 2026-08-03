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
# guide/faq removed from keyboard — keep texts available via /help if needed
DEFAULT_MENU_ORDER = [
    "shop",
    "services",
    "wallet",
    "support",
    "referral",
    "reseller_apply",
    "miniapp",
]

# Legacy keys stripped from saved menu_order so old installs drop them from the keyboard
REMOVED_MENU_KEYS = frozenset({"guide", "faq", "restart", "help"})


def _t(ui: dict | None, key: str) -> str:
    if ui and key in ui and ui[key]:
        return ui[key]
    return DEFAULT_SETTINGS.get(key, key)


def chunk_buttons(
    buttons: list[InlineKeyboardButton],
    *,
    cols: int = 2,
) -> list[list[InlineKeyboardButton]]:
    """Pack inline buttons into N-column rows."""
    if cols < 1:
        cols = 1
    rows: list[list[InlineKeyboardButton]] = []
    for i in range(0, len(buttons), cols):
        rows.append(buttons[i : i + cols])
    return rows


def _resolve_ui(ui: dict | None) -> dict | None:
    if ui is not None:
        return ui
    try:
        from app.services.users import current_ui_snapshot

        return current_ui_snapshot()
    except Exception:
        return None


def _menu_layout(ui: dict | None) -> str:
    resolved = _resolve_ui(ui)
    return (_t(resolved, "menu_layout") or "compact").strip()


def layout_rows(
    buttons: list[InlineKeyboardButton],
    ui: dict | None = None,
    *,
    full_width: list[InlineKeyboardButton] | None = None,
) -> list[list[InlineKeyboardButton]]:
    """Apply panel menu_layout: compact = 2-col, classic = 1-col; append full-width rows."""
    layout = _menu_layout(ui)
    if layout == "compact":
        rows = chunk_buttons(buttons, cols=2)
    else:
        rows = [[b] for b in buttons]
    for b in full_width or []:
        rows.append([b])
    return rows


def _menu_order(ui: dict | None) -> list[str]:
    """Active menu keys from menu_order only (no re-inject of removed items)."""
    raw = _t(ui, "menu_order")
    parts = [p.strip() for p in (raw or "").split(",") if p.strip()]
    known = set(DEFAULT_MENU_ORDER)
    ordered = [p for p in parts if p in known and p not in REMOVED_MENU_KEYS]
    # shop always present
    if "shop" not in ordered:
        ordered.insert(0, "shop")
    return ordered


MENU_SHOW_KEYS = (
    "wallet",
    "support",
    "referral",
    "reseller_apply",
    "miniapp",
    "services",
)


def sync_show_flags_for_order(order: list[str]) -> dict[str, str]:
    """Map menu_order → show_* flags (for persistence / legacy readers)."""
    active = set(order)
    return {f"show_{key}": ("1" if key in active else "0") for key in MENU_SHOW_KEYS}


def main_menu(
    role: str,
    *,
    has_services: bool = False,
    ui: dict | None = None,
    as_user: bool = False,
    show_reseller_creds: bool = False,
) -> InlineKeyboardMarkup:
    """
    Legacy/preview inline main menu (also used for admin «پیش‌نمایش»).
    Live home navigation uses ``main_reply_keyboard`` instead.
    """
    if role == Role.ADMIN.value and not as_user:
        return admin_main_menu(ui)

    settings = get_settings()
    buttons: list[InlineKeyboardButton] = []

    for key in _menu_order(ui):
        if key == "shop":
            buttons.append(
                InlineKeyboardButton(text=_t(ui, "btn_shop"), callback_data="shop:list")
            )
        elif key == "services" and has_services:
            buttons.append(
                InlineKeyboardButton(text=_t(ui, "btn_services"), callback_data="svc:list")
            )
        elif key == "wallet":
            buttons.append(
                InlineKeyboardButton(text=_t(ui, "btn_wallet"), callback_data="wallet:home")
            )
        elif key == "support":
            contacts = active_support_contacts(
                parse_support_contacts((ui or {}).get("support_contacts"))
            )
            if len(contacts) == 1:
                url = support_chat_url(contacts[0].get("telegram") or "")
                if url:
                    buttons.append(
                        InlineKeyboardButton(text=_t(ui, "btn_support"), url=url)
                    )
                else:
                    buttons.append(
                        InlineKeyboardButton(
                            text=_t(ui, "btn_support"), callback_data="support:home"
                        )
                    )
            else:
                buttons.append(
                    InlineKeyboardButton(
                        text=_t(ui, "btn_support"), callback_data="support:home"
                    )
                )
        elif key == "guide":
            buttons.append(
                InlineKeyboardButton(text=_t(ui, "btn_guide"), callback_data="help:guide")
            )
        elif key == "faq":
            buttons.append(
                InlineKeyboardButton(text=_t(ui, "btn_faq"), callback_data="help:faq")
            )
        elif key == "referral":
            buttons.append(
                InlineKeyboardButton(text=_t(ui, "btn_referral"), callback_data="ref:home")
            )
        elif key == "reseller_apply" and role == Role.USER.value and not show_reseller_creds:
            buttons.append(
                InlineKeyboardButton(
                    text=_t(ui, "btn_reseller_apply"),
                    callback_data="resapply:home",
                )
            )
        elif key == "miniapp" and settings.miniapp_enabled:
            buttons.append(
                InlineKeyboardButton(
                    text=_t(ui, "btn_miniapp"),
                    web_app=WebAppInfo(url=settings.miniapp_url),
                )
            )

    # compact = pair left-to-right like the web-panel live preview; classic = one per row
    full_width: list[InlineKeyboardButton] = []
    if role == Role.RESELLER.value:
        # Full shop panel — only on the dedicated reseller bot
        full_width.append(
            InlineKeyboardButton(text=_t(ui, "btn_reseller"), callback_data="res:home")
        )
    elif show_reseller_creds:
        # Main bot: credentials / deep-link only — no panel ops here
        full_width.append(
            InlineKeyboardButton(
                text=_t(ui, "btn_reseller_creds"),
                callback_data="res:creds",
            )
        )
    if role == Role.ADMIN.value and as_user:
        full_width.append(
            InlineKeyboardButton(text=_t(ui, "btn_admin"), callback_data="adm:home")
        )
    rows = layout_rows(buttons, ui, full_width=full_width)
    return InlineKeyboardMarkup(inline_keyboard=rows)


# Reply-keyboard action keys (text labels resolved from settings)
REPLY_ACTION_HOME = "home"
REPLY_ACTION_SHOP = "shop"
REPLY_ACTION_SERVICES = "services"
REPLY_ACTION_WALLET = "wallet"
REPLY_ACTION_WALLET_TOPUP = "wallet_topup"
REPLY_ACTION_WALLET_TX = "wallet_tx"
REPLY_ACTION_SUPPORT = "support"
REPLY_ACTION_SUPPORT_NEW = "support_new"
REPLY_ACTION_SUPPORT_LIST = "support_list"
REPLY_ACTION_REFERRAL = "referral"
REPLY_ACTION_RESELLER_APPLY = "reseller_apply"
REPLY_ACTION_RESELLER = "reseller"
REPLY_ACTION_CREDS = "reseller_creds"
REPLY_ACTION_ADMIN = "admin"
REPLY_ACTION_ADMIN_ORDERS = "adm_orders"
REPLY_ACTION_ADMIN_PAYMENTS = "adm_payments"
REPLY_ACTION_ADMIN_TICKETS = "adm_tickets"
REPLY_ACTION_ADMIN_PLANS = "adm_plans"
REPLY_ACTION_ADMIN_PG = "adm_pg"
REPLY_ACTION_ADMIN_PREVIEW = "adm_preview"
REPLY_ACTION_ADMIN_USERS = "adm_users"
REPLY_ACTION_ADMIN_SETTINGS = "adm_settings"
REPLY_ACTION_ADMIN_BROADCAST = "adm_broadcast"

# Submenu context keys stored implicitly by which reply labels are shown
REPLY_SUBMENU_WALLET = "wallet"
REPLY_SUBMENU_SUPPORT = "support"
REPLY_SUBMENU_ADMIN = "admin"
REPLY_SUBMENU_RESELLER = "reseller"


def _home_label(ui: dict | None = None) -> str:
    return (_t(ui, "btn_menu_home") or "🏠 منوی اصلی").strip() or "🏠 منوی اصلی"


def _reply_user_entries(
    role: str,
    *,
    has_services: bool,
    ui: dict | None,
    show_reseller_creds: bool = False,
) -> list[tuple[str, str]]:
    """Ordered (action_key, button_text) for the customer/reseller reply keyboard."""
    entries: list[tuple[str, str]] = []
    for key in _menu_order(ui):
        if key == "shop":
            entries.append((REPLY_ACTION_SHOP, _t(ui, "btn_shop")))
        elif key == "services" and has_services:
            entries.append((REPLY_ACTION_SERVICES, _t(ui, "btn_services")))
        elif key == "wallet":
            entries.append((REPLY_ACTION_WALLET, _t(ui, "btn_wallet")))
        elif key == "support":
            entries.append((REPLY_ACTION_SUPPORT, _t(ui, "btn_support")))
        elif key == "referral":
            entries.append((REPLY_ACTION_REFERRAL, _t(ui, "btn_referral")))
        elif key == "reseller_apply" and role == Role.USER.value and not show_reseller_creds:
            entries.append((REPLY_ACTION_RESELLER_APPLY, _t(ui, "btn_reseller_apply")))
        elif key == "miniapp":
            # WebApp requires inline buttons — shown separately under welcome
            continue
        elif key == "services" and not has_services:
            continue
    if role == Role.RESELLER.value:
        entries.append((REPLY_ACTION_RESELLER, _t(ui, "btn_reseller")))
    elif show_reseller_creds:
        entries.append((REPLY_ACTION_CREDS, _t(ui, "btn_reseller_creds")))
    if role == Role.ADMIN.value:
        entries.append((REPLY_ACTION_ADMIN, _t(ui, "btn_admin")))
    return entries


def _reply_admin_entries(ui: dict | None = None) -> list[tuple[str, str]]:
    return [
        (REPLY_ACTION_ADMIN, _t(ui, "btn_admin")),
        (REPLY_ACTION_ADMIN_ORDERS, _t(ui, "btn_adm_orders")),
        (REPLY_ACTION_ADMIN_PAYMENTS, _t(ui, "btn_adm_payments")),
        (REPLY_ACTION_ADMIN_TICKETS, _t(ui, "btn_adm_tickets")),
        (REPLY_ACTION_ADMIN_PLANS, _t(ui, "btn_adm_plans")),
        (REPLY_ACTION_ADMIN_USERS, _t(ui, "btn_adm_users")),
        (REPLY_ACTION_ADMIN_PG, _t(ui, "btn_adm_pg")),
        (REPLY_ACTION_ADMIN_SETTINGS, _t(ui, "btn_adm_settings")),
        (REPLY_ACTION_ADMIN_BROADCAST, _t(ui, "btn_adm_broadcast")),
        (REPLY_ACTION_ADMIN_PREVIEW, _t(ui, "btn_adm_preview")),
    ]


def _wallet_submenu_entries(ui: dict | None = None) -> list[tuple[str, str]]:
    return [
        (REPLY_ACTION_WALLET_TOPUP, "🟢➕ شارژ کیف پول"),
        (REPLY_ACTION_WALLET_TX, "🟡📜 تراکنش‌ها"),
    ]


def _support_submenu_entries(ui: dict | None = None) -> list[tuple[str, str]]:
    return [
        (REPLY_ACTION_SUPPORT_NEW, "🟣✉️ تیکت جدید"),
        (REPLY_ACTION_SUPPORT_LIST, "📋 تیکت‌های من"),
    ]


def _pack_reply_rows(
    entries: list[tuple[str, str]],
    ui: dict | None,
    *,
    footer: list[str] | None = None,
) -> list[list[KeyboardButton]]:
    layout = _menu_layout(ui)
    texts = [t for _, t in entries if (t or "").strip()]
    rows: list[list[KeyboardButton]] = []
    if layout == "compact":
        for i in range(0, len(texts), 2):
            chunk = texts[i : i + 2]
            rows.append([KeyboardButton(text=x) for x in chunk])
    else:
        for t in texts:
            rows.append([KeyboardButton(text=t)])
    for label in footer or []:
        if label:
            rows.append([KeyboardButton(text=label)])
    return rows


def main_reply_keyboard(
    role: str,
    *,
    has_services: bool = False,
    ui: dict | None = None,
    as_user: bool = False,
    show_reseller_creds: bool = False,
) -> ReplyKeyboardMarkup:
    """Persistent reply keyboard — primary navigation (Telegram shows ☰ when minimized)."""
    home_label = _home_label(ui)
    if role == Role.ADMIN.value and not as_user:
        entries = _reply_admin_entries(ui)
        rows = _pack_reply_rows(entries, ui, footer=[home_label])
    else:
        entries = _reply_user_entries(
            role,
            has_services=has_services,
            ui=ui,
            show_reseller_creds=show_reseller_creds,
        )
        rows = _pack_reply_rows(entries, ui, footer=[home_label])
    return ReplyKeyboardMarkup(
        keyboard=rows or [[KeyboardButton(text=home_label)]],
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True,
        input_field_placeholder="از منوی پایین انتخاب کنید…",
    )


def wallet_reply_keyboard(ui: dict | None = None) -> ReplyKeyboardMarkup:
    home = _home_label(ui)
    rows = _pack_reply_rows(_wallet_submenu_entries(ui), ui, footer=[home])
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True,
        input_field_placeholder="کیف پول — یک گزینه را انتخاب کنید…",
    )


def support_reply_keyboard(ui: dict | None = None) -> ReplyKeyboardMarkup:
    home = _home_label(ui)
    rows = _pack_reply_rows(_support_submenu_entries(ui), ui, footer=[home])
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True,
        input_field_placeholder="پشتیبانی — یک گزینه را انتخاب کنید…",
    )


def reseller_reply_keyboard(profile=None, ui: dict | None = None) -> ReplyKeyboardMarkup:
    """Reply-keyboard mirror of reseller panel sections."""
    from app.services.resellers import has_bot_perm

    entries: list[tuple[str, str]] = []
    if profile is None or has_bot_perm(profile, "dashboard"):
        entries.append(("res_dash", "🏠 خانه نماینده"))
        entries.append(("res_users", "👥 مشتریان من"))
    if profile is None or has_bot_perm(profile, "stats"):
        entries.append(("res_stats", "📊 آمار و کمیسیون"))
    if profile is not None and has_bot_perm(profile, "plans"):
        entries.append(("res_plans", "💎 پلن‌های فروش"))
    if profile is not None and has_bot_perm(profile, "orders"):
        entries.append(("res_orders", "🛒 سفارش‌های مشتریان"))
    if profile is not None and has_bot_perm(profile, "payments"):
        entries.append(("res_payments", "🧾 رسیدهای در انتظار"))
    if profile is not None and has_bot_perm(profile, "tickets"):
        entries.append(("res_tickets", "🎫 تیکت‌های مشتریان"))
    if profile is not None and has_bot_perm(profile, "shop_settings"):
        entries.append(("res_settings", "⚙️ تنظیمات فروشگاه"))
    home = _home_label(ui)
    rows = _pack_reply_rows(entries, ui, footer=[home])
    return ReplyKeyboardMarkup(
        keyboard=rows or [[KeyboardButton(text=home)]],
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True,
        input_field_placeholder="پنل نماینده…",
    )


def reply_action_map(
    role: str,
    *,
    has_services: bool = False,
    ui: dict | None = None,
    as_user: bool = False,
    show_reseller_creds: bool = False,
    include_submenus: bool = True,
) -> dict[str, str]:
    """Map button label → action key for the current role/settings."""
    home_label = _home_label(ui)
    mapping: dict[str, str] = {home_label: REPLY_ACTION_HOME}
    # Legacy aliases that old cancel keyboards may still show
    mapping[BTN_RESTART] = REPLY_ACTION_HOME
    mapping["شروع مجدد"] = REPLY_ACTION_HOME
    mapping["🏠 شروع مجدد"] = REPLY_ACTION_HOME
    if role == Role.ADMIN.value and not as_user:
        for key, text in _reply_admin_entries(ui):
            mapping[(text or "").strip()] = key
    else:
        for key, text in _reply_user_entries(
            role,
            has_services=has_services,
            ui=ui,
            show_reseller_creds=show_reseller_creds,
        ):
            mapping[(text or "").strip()] = key
        if role == Role.ADMIN.value and as_user:
            mapping[(_t(ui, "btn_admin") or "").strip()] = REPLY_ACTION_ADMIN
    if include_submenus:
        for key, text in _wallet_submenu_entries(ui):
            mapping[(text or "").strip()] = key
        for key, text in _support_submenu_entries(ui):
            mapping[(text or "").strip()] = key
        # Reseller submenu labels (static)
        for key, text in (
            ("res_dash", "🏠 خانه نماینده"),
            ("res_users", "👥 مشتریان من"),
            ("res_stats", "📊 آمار و کمیسیون"),
            ("res_plans", "💎 پلن‌های فروش"),
            ("res_orders", "🛒 سفارش‌های مشتریان"),
            ("res_payments", "🧾 رسیدهای در انتظار"),
            ("res_tickets", "🎫 تیکت‌های مشتریان"),
            ("res_settings", "⚙️ تنظیمات فروشگاه"),
        ):
            mapping[text] = key
    return {k: v for k, v in mapping.items() if k}


def miniapp_inline_keyboard(ui: dict | None = None) -> InlineKeyboardMarkup | None:
    """WebApp can only live on inline keyboards."""
    settings = get_settings()
    if not settings.miniapp_enabled:
        return None
    if "miniapp" not in _menu_order(ui):
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_t(ui, "btn_miniapp"),
                    web_app=WebAppInfo(url=settings.miniapp_url),
                )
            ]
        ]
    )


def admin_main_menu(ui: dict | None = None) -> InlineKeyboardMarkup:
    """Primary home for bot owner — management tools only."""
    buttons = [
        InlineKeyboardButton(text=_t(ui, "btn_admin"), callback_data="adm:home"),
        InlineKeyboardButton(text="🛒 سفارش‌ها", callback_data="adm:orders"),
        InlineKeyboardButton(text="🧾 رسیدها", callback_data="adm:payments"),
        InlineKeyboardButton(text="🎫 تیکت‌ها", callback_data="adm:tickets"),
        InlineKeyboardButton(text="📦 پلن‌ها", callback_data="adm:plans"),
        InlineKeyboardButton(text="🖥 پاسارگارد", callback_data="adm:pg"),
    ]
    preview = InlineKeyboardButton(
        text="👁 پیش‌نمایش منوی کاربر",
        callback_data="menu:as_user",
    )
    return InlineKeyboardMarkup(
        inline_keyboard=layout_rows(buttons, ui, full_width=[preview])
    )


def plans_keyboard(
    plans: list[Plan],
    ui: dict | None = None,
    *,
    custom_enabled: bool = False,
    wholesale_enabled: bool = False,
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
    extras: list[InlineKeyboardButton] = []
    if custom_enabled:
        extras.append(
            InlineKeyboardButton(
                text="✨ پلن دلخواه",
                callback_data="shop:custom",
            )
        )
    if wholesale_enabled:
        extras.append(
            InlineKeyboardButton(
                text=_t(ui, "btn_wholesale") or "📦 فروش عمده",
                callback_data="shop:wholesale",
            )
        )
    if extras:
        rows.extend(layout_rows(extras, ui))
    rows.append(
        [InlineKeyboardButton(text=_t(ui, "btn_back"), callback_data="menu:home")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def wholesale_plans_keyboard(
    plans: list[Plan],
    ui: dict | None = None,
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"💎 {p.name} — {p.price:,} ت".replace(",", "٬"),
                callback_data=f"shop:wholesale:plan:{p.id}",
            )
        ]
        for p in plans
    ]
    rows.append([InlineKeyboardButton(text=_t(ui, "btn_back"), callback_data="shop:list")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def wholesale_qty_keyboard(
    qty: int,
    ui: dict | None = None,
    *,
    plan_id: int,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(text="➖", callback_data="shop:wholesale:qty:-"),
            InlineKeyboardButton(text=f"{qty} عدد", callback_data="shop:wholesale:noop"),
            InlineKeyboardButton(text="➕", callback_data="shop:wholesale:qty:+"),
        ],
        [InlineKeyboardButton(text="✏️ ورود دستی تعداد", callback_data="shop:wholesale:qty:input")],
        [InlineKeyboardButton(text="ادامه ← تأیید", callback_data="shop:wholesale:confirm")],
        [InlineKeyboardButton(text=_t(ui, "btn_back"), callback_data="shop:wholesale")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def wholesale_confirm_keyboard(
    ui: dict | None = None,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ تأیید و پرداخت", callback_data="shop:wholesale:buy")],
            [InlineKeyboardButton(text=_t(ui, "btn_back"), callback_data="shop:wholesale:qty")],
        ]
    )


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


def admin_home(ui: dict | None = None) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(text="🧾 رسیدها", callback_data="adm:payments"),
        InlineKeyboardButton(text="🛒 سفارش‌ها", callback_data="adm:orders"),
        InlineKeyboardButton(text="🎫 تیکت‌ها", callback_data="adm:tickets"),
        InlineKeyboardButton(text="📊 داشبورد", callback_data="adm:dash"),
        InlineKeyboardButton(text="💎 پلن‌ها", callback_data="adm:plans"),
        InlineKeyboardButton(text="👥 کاربران", callback_data="adm:users"),
        InlineKeyboardButton(text="🤝 نمایندگان", callback_data="adm:resellers"),
        InlineKeyboardButton(text="📢 پیام گروهی", callback_data="adm:broadcast"),
        InlineKeyboardButton(text="🖥 پاسارگارد", callback_data="adm:pg"),
        InlineKeyboardButton(text="⚙️ تنظیمات", callback_data="adm:settings"),
        InlineKeyboardButton(text="💾 بکاپ / ریستور", callback_data="adm:backup"),
    ]
    back = InlineKeyboardButton(text="⬅️ منوی اصلی", callback_data="menu:home")
    return InlineKeyboardMarkup(
        inline_keyboard=layout_rows(buttons, ui, full_width=[back])
    )


def admin_users_keyboard(ui: dict | None = None) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(text="📋 لیست کاربران", callback_data="adm:users:list:0"),
        InlineKeyboardButton(text="🔎 جستجو با آیدی تلگرام", callback_data="adm:users:search"),
        InlineKeyboardButton(
            text="🌐 مدیریت کامل در وب‌پنل",
            callback_data="adm:users:webhint",
        ),
    ]
    back = InlineKeyboardButton(text="⬅️ بازگشت", callback_data="adm:home")
    return InlineKeyboardMarkup(
        inline_keyboard=layout_rows(buttons, ui, full_width=[back])
    )


def admin_users_list_keyboard(
    *,
    page: int,
    has_prev: bool,
    has_next: bool,
    rows: list[list[InlineKeyboardButton]],
) -> InlineKeyboardMarkup:
    nav: list[InlineKeyboardButton] = []
    if has_prev:
        nav.append(InlineKeyboardButton(text="◀️ قبل", callback_data=f"adm:users:list:{page - 1}"))
    if has_next:
        nav.append(InlineKeyboardButton(text="بعد ▶️", callback_data=f"adm:users:list:{page + 1}"))
    # Flatten single-button rows then pack into 2 columns
    flat = [btn for row in rows for btn in row]
    kb_rows = chunk_buttons(flat, cols=2)
    if nav:
        kb_rows.append(nav)
    kb_rows.append([InlineKeyboardButton(text="🔎 جستجو", callback_data="adm:users:search")])
    kb_rows.append([InlineKeyboardButton(text="⬅️ بازگشت", callback_data="adm:users")])
    return InlineKeyboardMarkup(inline_keyboard=kb_rows)


def admin_resellers_menu(ui: dict | None = None) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(text="📋 لیست نمایندگان", callback_data="adm:resellers:list:0"),
        InlineKeyboardButton(text="📋 درخواست‌های منتظر", callback_data="adm:resapp:list"),
        InlineKeyboardButton(text="➕ افزودن دستی", callback_data="adm:resellers:add"),
    ]
    back = InlineKeyboardButton(text="⬅️ بازگشت", callback_data="adm:home")
    return InlineKeyboardMarkup(
        inline_keyboard=layout_rows(buttons, ui, full_width=[back])
    )


def admin_resellers_list_keyboard(
    *,
    page: int,
    has_prev: bool,
    has_next: bool,
    rows: list[list[InlineKeyboardButton]],
) -> InlineKeyboardMarkup:
    nav: list[InlineKeyboardButton] = []
    if has_prev:
        nav.append(InlineKeyboardButton(text="◀️ قبل", callback_data=f"adm:resellers:list:{page - 1}"))
    if has_next:
        nav.append(InlineKeyboardButton(text="بعد ▶️", callback_data=f"adm:resellers:list:{page + 1}"))
    flat = [btn for row in rows for btn in row]
    kb_rows = chunk_buttons(flat, cols=2)
    if nav:
        kb_rows.append(nav)
    kb_rows.append([InlineKeyboardButton(text="⬅️ بازگشت", callback_data="adm:resellers")])
    return InlineKeyboardMarkup(inline_keyboard=kb_rows)


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


def pg_admin_keyboard(ui: dict | None = None) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(text="🏠 نمای کلی", callback_data="adm:pg:stats"),
        InlineKeyboardButton(text="👥 کاربران VPN", callback_data="adm:pg:users"),
        InlineKeyboardButton(text="➕ ساخت کاربر", callback_data="adm:pg:create"),
        InlineKeyboardButton(text="🔎 جستجوی یوزر", callback_data="adm:pg:search"),
        InlineKeyboardButton(text="🕸 نودها", callback_data="adm:pg:nodes"),
        InlineKeyboardButton(text="📁 ساخت گروه", callback_data="adm:pg:group"),
        InlineKeyboardButton(text="📋 ساخت تمپلیت", callback_data="adm:pg:template"),
    ]
    back = InlineKeyboardButton(text="⬅️ بازگشت", callback_data="adm:home")
    return InlineKeyboardMarkup(
        inline_keyboard=layout_rows(buttons, ui, full_width=[back])
    )


def reseller_home(profile=None, ui: dict | None = None) -> InlineKeyboardMarkup:
    from app.services.resellers import has_bot_perm

    buttons: list[InlineKeyboardButton] = []
    if profile is None or has_bot_perm(profile, "dashboard"):
        buttons.append(InlineKeyboardButton(text="🏠 خانه نماینده", callback_data="res:dash"))
        buttons.append(InlineKeyboardButton(text="👥 مشتریان من", callback_data="res:users:0"))
    if profile is None or has_bot_perm(profile, "stats"):
        buttons.append(InlineKeyboardButton(text="📊 آمار و کمیسیون", callback_data="res:stats"))
    if profile is not None and has_bot_perm(profile, "plans"):
        buttons.append(InlineKeyboardButton(text="💎 پلن‌های فروش", callback_data="res:plans"))
    if profile is not None and has_bot_perm(profile, "orders"):
        buttons.append(InlineKeyboardButton(text="🛒 سفارش‌های مشتریان", callback_data="res:orders"))
    if profile is not None and has_bot_perm(profile, "payments"):
        buttons.append(
            InlineKeyboardButton(text="🧾 رسیدهای در انتظار", callback_data="res:payments")
        )
    if profile is not None and has_bot_perm(profile, "tickets"):
        buttons.append(InlineKeyboardButton(text="🎫 تیکت‌های مشتریان", callback_data="res:tickets"))
    if profile is not None and has_bot_perm(profile, "shop_settings"):
        buttons.append(
            InlineKeyboardButton(text="⚙️ تنظیمات فروشگاه", callback_data="res:st:hub")
        )
    back = InlineKeyboardButton(text="⬅️ بازگشت", callback_data="menu:home")
    return InlineKeyboardMarkup(
        inline_keyboard=layout_rows(buttons, ui, full_width=[back])
    )


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


BTN_CANCEL = "انصراف"
BTN_RESTART = "🏠 شروع مجدد"  # legacy alias only — no longer shown on cancel KB


def cancel_reply(ui: dict | None = None) -> ReplyKeyboardMarkup:
    """Thin cancel keyboard during text input — does not include home/restart."""
    label = (_t(ui, "btn_cancel") or "").strip()
    # Prefer plain انصراف so is_cancel_text keeps matching; strip emoji variants
    cancel_label = BTN_CANCEL
    if label and "انصراف" in label and label != BTN_CANCEL:
        # Still accept panel label if it contains انصراف, but show clean text
        cancel_label = BTN_CANCEL
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=cancel_label)]],
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True,
        input_field_placeholder="مقدار را بفرستید یا انصراف بزنید…",
    )


def persistent_reply_keyboard(ui: dict | None = None) -> ReplyKeyboardMarkup:
    """Fallback reply keyboard (home only) when role context is unavailable."""
    home = _home_label(ui)
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=home)]],
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True,
    )


def is_cancel_text(text: str | None) -> bool:
    t = (text or "").strip()
    return t in {BTN_CANCEL, "لغو", "cancel", "/cancel"} or t.endswith("انصراف")


def is_home_text(text: str | None, ui: dict | None = None) -> bool:
    """True for main-menu / legacy restart labels."""
    t = (text or "").strip()
    if not t:
        return False
    home = _home_label(ui)
    if t == home:
        return True
    return t in {BTN_RESTART, "شروع مجدد", "restart", "🏠 منوی اصلی"} or t.endswith(
        "شروع مجدد"
    ) or t.endswith("منوی اصلی")


def is_restart_text(text: str | None) -> bool:
    """Backward-compat alias — treats home + legacy restart as home navigation."""
    return is_home_text(text)
