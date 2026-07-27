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


def _t(ui: dict | None, key: str) -> str:
    if ui and key in ui and ui[key]:
        return ui[key]
    return DEFAULT_SETTINGS.get(key, key)


def main_menu(
    role: str,
    *,
    has_services: bool = False,
    ui: dict | None = None,
) -> InlineKeyboardMarkup:
    settings = get_settings()
    layout = _t(ui, "menu_layout")
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text=_t(ui, "btn_shop"), callback_data="shop:list")],
    ]
    if has_services:
        rows.append(
            [InlineKeyboardButton(text=_t(ui, "btn_services"), callback_data="svc:list")]
        )

    mid: list[InlineKeyboardButton] = []
    if on(_t(ui, "show_wallet")):
        mid.append(InlineKeyboardButton(text=_t(ui, "btn_wallet"), callback_data="wallet:home"))
    if on(_t(ui, "show_support")):
        mid.append(InlineKeyboardButton(text=_t(ui, "btn_support"), callback_data="support:home"))
    if mid:
        if layout == "compact":
            # pair buttons on one row when possible
            for i in range(0, len(mid), 2):
                rows.append(mid[i : i + 2])
        else:
            for b in mid:
                rows.append([b])

    help_row: list[InlineKeyboardButton] = []
    if on(_t(ui, "show_guide")):
        help_row.append(InlineKeyboardButton(text=_t(ui, "btn_guide"), callback_data="help:guide"))
    if on(_t(ui, "show_faq")):
        help_row.append(InlineKeyboardButton(text=_t(ui, "btn_faq"), callback_data="help:faq"))
    if help_row:
        rows.append(help_row)

    if on(_t(ui, "show_referral")):
        rows.append(
            [InlineKeyboardButton(text=_t(ui, "btn_referral"), callback_data="ref:home")]
        )

    if settings.miniapp_enabled and on(_t(ui, "show_miniapp")):
        rows.append(
            [
                InlineKeyboardButton(
                    text=_t(ui, "btn_miniapp"),
                    web_app=WebAppInfo(url=settings.miniapp_url),
                )
            ]
        )
    if role == Role.RESELLER.value:
        rows.append(
            [InlineKeyboardButton(text=_t(ui, "btn_reseller"), callback_data="res:home")]
        )
    if role == Role.ADMIN.value:
        rows.append(
            [InlineKeyboardButton(text=_t(ui, "btn_admin"), callback_data="adm:home")]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


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
