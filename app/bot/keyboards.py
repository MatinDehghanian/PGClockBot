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


def main_menu(role: str, *, has_services: bool = False) -> InlineKeyboardMarkup:
    settings = get_settings()
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="🛒 خرید سرویس", callback_data="shop:list")],
    ]
    if has_services:
        rows.append([InlineKeyboardButton(text="📦 سرویس‌های من", callback_data="svc:list")])
    rows.append(
        [
            InlineKeyboardButton(text="👛 کیف پول", callback_data="wallet:home"),
            InlineKeyboardButton(text="🎧 پشتیبانی", callback_data="support:home"),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(text="📘 راهنما", callback_data="help:guide"),
            InlineKeyboardButton(text="❓ FAQ", callback_data="help:faq"),
        ]
    )
    rows.append([InlineKeyboardButton(text="🎁 دعوت دوستان", callback_data="ref:home")])
    if settings.miniapp_enabled:
        rows.append(
            [
                InlineKeyboardButton(
                    text="📱 مینی‌اپ",
                    web_app=WebAppInfo(url=settings.miniapp_url),
                )
            ]
        )
    if role == Role.RESELLER.value:
        rows.append([InlineKeyboardButton(text="🤝 پنل نماینده", callback_data="res:home")])
    if role == Role.ADMIN.value:
        rows.append([InlineKeyboardButton(text="🛠 پنل ادمین", callback_data="adm:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def plans_keyboard(plans: list[Plan]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{'🎁' if p.is_trial else '💎'} {p.name} — {p.price:,} ت".replace(",", "٬"),
                callback_data=f"shop:plan:{p.id}",
            )
        ]
        for p in plans
    ]
    rows.append([InlineKeyboardButton(text="⬅️ بازگشت", callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def plan_actions(plan_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ ادامه خرید", callback_data=f"shop:buy:{plan_id}")],
            [InlineKeyboardButton(text="⬅️ بازگشت", callback_data="shop:list")],
        ]
    )


def pay_methods(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👛 پرداخت از کیف پول", callback_data=f"pay:wallet:{order_id}")],
            [InlineKeyboardButton(text="💳 کارت به کارت", callback_data=f"pay:card:{order_id}")],
            [InlineKeyboardButton(text="🏷 کد تخفیف", callback_data=f"pay:discount:{order_id}")],
            [InlineKeyboardButton(text="❌ انصراف", callback_data="menu:home")],
        ]
    )


def services_keyboard(services: list) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"🔹 {s.pg_username}",
                callback_data=f"svc:view:{s.id}",
            )
        ]
        for s in services
    ]
    rows.append([InlineKeyboardButton(text="⬅️ بازگشت", callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def service_actions(service_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔗 لینک ساب", callback_data=f"svc:link:{service_id}"),
                InlineKeyboardButton(text="🔄 تمدید", callback_data=f"svc:renew:{service_id}"),
            ],
            [
                InlineKeyboardButton(text="♻️ رفرش وضعیت", callback_data=f"svc:view:{service_id}"),
            ],
            [InlineKeyboardButton(text="⬅️ بازگشت", callback_data="svc:list")],
        ]
    )


def wallet_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ شارژ کیف پول", callback_data="wallet:topup")],
            [InlineKeyboardButton(text="📜 تراکنش‌ها", callback_data="wallet:tx")],
            [InlineKeyboardButton(text="⬅️ بازگشت", callback_data="menu:home")],
        ]
    )


def support_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✉️ تیکت جدید", callback_data="support:new")],
            [InlineKeyboardButton(text="📋 تیکت‌های من", callback_data="support:list")],
            [InlineKeyboardButton(text="⬅️ بازگشت", callback_data="menu:home")],
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


def back_home() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ منوی اصلی", callback_data="menu:home")]]
    )


def cancel_reply() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="انصراف")]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
