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
    "miniapp",
]


def _t(ui: dict | None, key: str) -> str:
    if ui and key in ui and ui[key]:
        return ui[key]
    return DEFAULT_SETTINGS.get(key, key)


def _menu_order(ui: dict | None) -> list[str]:
    raw = _t(ui, "menu_order")
    parts = [p.strip() for p in (raw or "").split(",") if p.strip()]
    if not parts:
        return list(DEFAULT_MENU_ORDER)
    # keep known keys, append any missing defaults at end
    known = set(DEFAULT_MENU_ORDER)
    ordered = [p for p in parts if p in known]
    for key in DEFAULT_MENU_ORDER:
        if key not in ordered:
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
            add_mid(InlineKeyboardButton(text=_t(ui, "btn_support"), callback_data="support:home"))
        elif key == "guide" and on(_t(ui, "show_guide")):
            add_mid(InlineKeyboardButton(text=_t(ui, "btn_guide"), callback_data="help:guide"))
        elif key == "faq" and on(_t(ui, "show_faq")):
            add_mid(InlineKeyboardButton(text=_t(ui, "btn_faq"), callback_data="help:faq"))
        elif key == "referral" and on(_t(ui, "show_referral")):
            add_full(InlineKeyboardButton(text=_t(ui, "btn_referral"), callback_data="ref:home"))
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
            [
                InlineKeyboardButton(text=_t(ui, "btn_admin"), callback_data="adm:home"),
            ],
            [
                InlineKeyboardButton(text="🧾 رسیدها", callback_data="adm:payments"),
                InlineKeyboardButton(text="🎫 تیکت‌ها", callback_data="adm:tickets"),
            ],
            [
                InlineKeyboardButton(text="📦 پلن‌ها", callback_data="adm:plans"),
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


def plans_keyboard(plans: list[Plan], ui: dict | None = None) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{'🎁' if p.is_trial else '💎'} {p.name} — {p.price:,} ت".replace(",", "٬"),
                callback_data=f"shop:plan:{p.id}",
            )
        ]
        for p in plans
    ]
    rows.append(
        [InlineKeyboardButton(text=_t(ui, "btn_back"), callback_data="menu:home")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def plan_actions(plan_id: int, ui: dict | None = None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ ادامه خرید", callback_data=f"shop:buy:{plan_id}")],
            [InlineKeyboardButton(text=_t(ui, "btn_back"), callback_data="shop:list")],
        ]
    )


def pay_methods(order_id: int, ui: dict | None = None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_t(ui, "btn_pay_wallet"),
                    callback_data=f"pay:wallet:{order_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text=_t(ui, "btn_pay_card"),
                    callback_data=f"pay:card:{order_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text=_t(ui, "btn_pay_discount"),
                    callback_data=f"pay:discount:{order_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text=_t(ui, "btn_cancel"),
                    callback_data="menu:home",
                )
            ],
        ]
    )


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
            [InlineKeyboardButton(text="➕ شارژ کیف پول", callback_data="wallet:topup")],
            [InlineKeyboardButton(text="📜 تراکنش‌ها", callback_data="wallet:tx")],
            [InlineKeyboardButton(text=_t(ui, "btn_back"), callback_data="menu:home")],
        ]
    )


def support_keyboard(ui: dict | None = None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✉️ تیکت جدید", callback_data="support:new")],
            [InlineKeyboardButton(text="📋 تیکت‌های من", callback_data="support:list")],
            [InlineKeyboardButton(text=_t(ui, "btn_back"), callback_data="menu:home")],
        ]
    )


def admin_home() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📦 پلن‌ها", callback_data="adm:plans"),
                InlineKeyboardButton(text="🧾 رسیدها", callback_data="adm:payments"),
            ],
            [
                InlineKeyboardButton(text="🎫 تیکت‌ها", callback_data="adm:tickets"),
                InlineKeyboardButton(text="👥 کاربران", callback_data="adm:users"),
            ],
            [
                InlineKeyboardButton(text="🤝 نمایندگان", callback_data="adm:resellers"),
                InlineKeyboardButton(text="⚙️ تنظیمات", callback_data="adm:settings"),
            ],
            [
                InlineKeyboardButton(text="🖥 پاسارگارد", callback_data="adm:pg"),
            ],
            [InlineKeyboardButton(text="⬅️ بازگشت", callback_data="menu:home")],
        ]
    )


def pg_admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔎 جستجوی یوزر", callback_data="adm:pg:search")],
            [InlineKeyboardButton(text="📊 آمار سیستم", callback_data="adm:pg:stats")],
            [InlineKeyboardButton(text="🕸 نودها", callback_data="adm:pg:nodes")],
            [InlineKeyboardButton(text="⬅️ بازگشت", callback_data="adm:home")],
        ]
    )


def reseller_home() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 وضعیت نماینده", callback_data="res:stats")],
            [InlineKeyboardButton(text="🧾 رسیدهای در انتظار", callback_data="res:payments")],
            [InlineKeyboardButton(text="⬅️ بازگشت", callback_data="menu:home")],
        ]
    )


def payment_review(payment_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ تأیید", callback_data=f"payrev:ok:{payment_id}"),
                InlineKeyboardButton(text="❌ رد", callback_data=f"payrev:no:{payment_id}"),
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
