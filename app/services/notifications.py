from __future__ import annotations

"""Admin Telegram notification preferences and dispatch."""

from typing import Any

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import BotUser, Order, Payment
from app.services.formatting import (
    format_bytes,
    format_expire,
    format_message,
    format_toman,
    info_block,
    kv_line,
)
from app.services.users import get_all_settings, on, set_settings_bulk


def ticket_action_markup(ticket_id: int) -> InlineKeyboardMarkup:
    """Reply / close buttons under ticket notification messages."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💬 پاسخ",
                    callback_data=f"tkt:reply:{int(ticket_id)}",
                ),
                InlineKeyboardButton(
                    text="🗃 بستن",
                    callback_data=f"tkt:close:{int(ticket_id)}",
                ),
            ]
        ]
    )


async def _ticket_reseller_chat_ids(session: AsyncSession, ticket_user_id: int) -> list[int]:
    """Telegram ids of the customer's reseller (if they may handle tickets)."""
    user = await session.get(BotUser, int(ticket_user_id))
    if not user or not user.reseller_id:
        return []
    from app.services.resellers import get_reseller_profile, has_bot_perm

    profile = await get_reseller_profile(session, int(user.reseller_id))
    if not profile or not has_bot_perm(profile, "tickets"):
        return []
    owner = await session.get(BotUser, int(user.reseller_id))
    if not owner or not owner.telegram_id:
        return []
    return [int(owner.telegram_id)]

# (setting_key, title, description, default "1"|"0")
NOTIFY_PREFS: list[tuple[str, str, str, str]] = [
    (
        "notify_new_subscription",
        "اشتراک جدید",
        "وقتی سرویس/اشتراک جدید تحویل شد (خرید کیف‌پول یا تأیید پرداخت)",
        "1",
    ),
    (
        "notify_pending_approval",
        "نیاز به تأیید",
        "رسید کارت‌به‌کارت یا شارژ کیف که باید تأیید/رد شود — با دکمه تأیید و رد",
        "1",
    ),
    (
        "notify_new_order",
        "سفارش جدید",
        "وقتی کاربر سفارش می‌سازد و روش پرداخت را انتخاب می‌کند",
        "0",
    ),
    (
        "notify_wallet_topup",
        "شارژ کیف پول",
        "اطلاع از شارژ موفق کیف پول (بعد از تأیید)",
        "1",
    ),
    (
        "notify_new_ticket",
        "تیکت پشتیبانی",
        "وقتی کاربر تیکت جدید ثبت می‌کند یا پیام می‌فرستد — با دکمه پاسخ و بستن",
        "1",
    ),
    (
        "notify_auto_approve",
        "تأیید خودکار",
        "وقتی رسید به‌صورت خودکار تأیید می‌شود",
        "1",
    ),
]


async def get_notify_prefs(session: AsyncSession) -> dict[str, bool]:
    ui = await get_all_settings(session)
    return {key: on(ui.get(key, default)) for key, _, _, default in NOTIFY_PREFS}


async def save_notify_prefs(session: AsyncSession, form: dict[str, Any]) -> None:
    payload = {
        key: ("1" if form.get(f"s_{key}") in {"1", "on", "true", True} else "0")
        for key, _, _, _ in NOTIFY_PREFS
    }
    await set_settings_bulk(session, payload)


async def notify_enabled(session: AsyncSession, key: str) -> bool:
    prefs = await get_notify_prefs(session)
    return bool(prefs.get(key, False))


async def _send_admins(
    bot: Bot,
    text: str,
    *,
    markup: InlineKeyboardMarkup | None = None,
    photo: str | None = None,
    extra_chat_ids: list[int] | None = None,
) -> None:
    import asyncio

    targets: list[int] = []
    seen: set[int] = set()
    for admin_id in list(get_settings().admin_ids) + list(extra_chat_ids or []):
        try:
            aid = int(admin_id)
        except (TypeError, ValueError):
            continue
        if aid in seen:
            continue
        seen.add(aid)
        targets.append(aid)

    async def _one(admin_id: int) -> None:
        try:
            if photo:
                await bot.send_photo(
                    admin_id, photo=photo, caption=text[:1024], reply_markup=markup
                )
            else:
                await bot.send_message(admin_id, text, reply_markup=markup)
        except Exception:
            if photo:
                try:
                    await bot.send_message(admin_id, text, reply_markup=markup)
                except Exception:
                    pass

    if not targets:
        return
    await asyncio.gather(
        *(_one(admin_id) for admin_id in targets),
        return_exceptions=True,
    )


async def _shop_owner_chat_ids(
    session: AsyncSession,
    *,
    order: Order | None = None,
    payment: Payment | None = None,
) -> list[int]:
    """Telegram ids of the reseller shop owner (if any) for this order/payment."""
    rid = None
    if order is not None and order.reseller_id:
        rid = int(order.reseller_id)
    elif payment is not None and payment.order_id:
        ord_row = await session.get(Order, payment.order_id)
        if ord_row and ord_row.reseller_id:
            rid = int(ord_row.reseller_id)
    if not rid:
        return []
    from app.db.models import BotUser, ResellerProfile

    profile = (
        await session.execute(select(ResellerProfile).where(ResellerProfile.user_id == rid))
    ).scalar_one_or_none()
    if profile is not None and not profile.is_active:
        return []
    owner = await session.get(BotUser, rid)
    if not owner or not owner.telegram_id:
        return []
    return [int(owner.telegram_id)]


def _approval_markup(*, order_id: int | None = None, payment_id: int | None = None) -> InlineKeyboardMarkup:
    if order_id:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ تأیید",
                        callback_data=f"ordrev:ok:{order_id}",
                    ),
                    InlineKeyboardButton(
                        text="❌ رد",
                        callback_data=f"ordrev:no:{order_id}",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text="📋 جزئیات سفارش",
                        callback_data=f"adm:order:{order_id}",
                    )
                ],
            ]
        )
    assert payment_id is not None
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ تأیید",
                    callback_data=f"payrev:ok:{payment_id}",
                ),
                InlineKeyboardButton(
                    text="❌ رد",
                    callback_data=f"payrev:no:{payment_id}",
                ),
            ]
        ]
    )


async def notify_new_subscription(
    bot: Bot,
    session: AsyncSession,
    *,
    order: Order,
    user_tg_id: int | None,
    user_name: str | None = None,
    plan_name: str | None = None,
    needs_approval: bool = False,
) -> None:
    """Inform admins that a subscription was purchased / delivered."""
    if not await notify_enabled(session, "notify_new_subscription"):
        return
    settings = get_settings()
    lines = [
        kv_line("🧾", "سفارش", f"#{order.id}"),
        kv_line("👤", "کاربر", user_name or (str(user_tg_id) if user_tg_id else "—")),
        kv_line("💰", "مبلغ", format_toman(order.amount, settings.currency)),
    ]
    if plan_name:
        lines.append(kv_line("💎", "پلن", plan_name))
    if order.payment_method:
        method = "کیف پول" if order.payment_method == "wallet" else "کارت به کارت"
        lines.append(kv_line("💳", "پرداخت", method))
    lines.append(kv_line("📌", "وضعیت", "نیاز به تأیید" if needs_approval else "تحویل‌شده"))
    text = format_message("🆕 اشتراک جدید", info_block(lines))
    markup = None
    if needs_approval:
        markup = _approval_markup(order_id=order.id)
    extra = await _shop_owner_chat_ids(session, order=order)
    await _send_admins(bot, text, markup=markup, extra_chat_ids=extra)


async def notify_pending_approval(
    bot: Bot,
    session: AsyncSession,
    payment: Payment,
    user_tg_id: int | None,
    *,
    user_name: str | None = None,
) -> None:
    if not await notify_enabled(session, "notify_pending_approval"):
        return
    settings = get_settings()
    kind = "شارژ کیف پول" if payment.is_wallet_topup else "خرید اشتراک"
    lines = [
        kv_line("🧾", "پرداخت", f"#{payment.id}"),
        kv_line("💰", "مبلغ", format_toman(payment.amount, settings.currency)),
        kv_line("👤", "کاربر", user_name or (str(user_tg_id) if user_tg_id else "—")),
        kv_line("📦", "نوع", kind),
    ]
    if payment.order_id and not payment.is_wallet_topup:
        lines.append(kv_line("🛒", "سفارش", f"#{payment.order_id}"))
    text = format_message("⏳ نیاز به تأیید", info_block(lines) + "\n\nاز دکمه‌های زیر تأیید یا رد کنید.")
    if payment.order_id and not payment.is_wallet_topup:
        markup = _approval_markup(order_id=payment.order_id)
    else:
        markup = _approval_markup(payment_id=payment.id)
    extra = await _shop_owner_chat_ids(session, payment=payment)
    await _send_admins(bot, text, markup=markup, photo=payment.receipt_file_id, extra_chat_ids=extra)


async def notify_new_order(
    bot: Bot,
    session: AsyncSession,
    *,
    order: Order,
    user_tg_id: int | None,
    plan_name: str | None = None,
    user_name: str | None = None,
) -> None:
    if not await notify_enabled(session, "notify_new_order"):
        return
    settings = get_settings()
    lines = [
        kv_line("🧾", "سفارش", f"#{order.id}"),
        kv_line("👤", "کاربر", user_name or (str(user_tg_id) if user_tg_id else "—")),
        kv_line("💰", "مبلغ", format_toman(order.amount, settings.currency)),
    ]
    if plan_name:
        lines.append(kv_line("💎", "پلن", plan_name))
    text = format_message("🛒 سفارش جدید", info_block(lines))
    extra = await _shop_owner_chat_ids(session, order=order)
    await _send_admins(bot, text, extra_chat_ids=extra)


async def notify_wallet_topup_ok(
    bot: Bot,
    session: AsyncSession,
    payment: Payment,
    user_tg_id: int | None,
) -> None:
    if not await notify_enabled(session, "notify_wallet_topup"):
        return
    settings = get_settings()
    text = format_message(
        "💰 شارژ کیف پول",
        info_block(
            [
                kv_line("🧾", "پرداخت", f"#{payment.id}"),
                kv_line("💵", "مبلغ", format_toman(payment.amount, settings.currency)),
                kv_line("👤", "کاربر", str(user_tg_id) if user_tg_id else "—"),
                kv_line("✅", "وضعیت", "تأیید و واریز شد"),
            ]
        ),
    )
    await _send_admins(bot, text)


async def notify_new_ticket(
    bot: Bot,
    session: AsyncSession,
    *,
    ticket_id: int,
    subject: str,
    user_name: str | None,
    ticket_user_id: int | None = None,
) -> None:
    if not await notify_enabled(session, "notify_new_ticket"):
        return
    text = format_message(
        "🎫 تیکت جدید",
        info_block(
            [
                kv_line("🔢", "شماره", f"#{ticket_id}"),
                kv_line("👤", "از", user_name or "—"),
                kv_line("📝", "موضوع", subject),
            ]
        ),
    )
    extra: list[int] = []
    if ticket_user_id:
        extra = await _ticket_reseller_chat_ids(session, ticket_user_id)
    await _send_admins(
        bot,
        text,
        markup=ticket_action_markup(ticket_id),
        extra_chat_ids=extra,
    )


async def notify_ticket_message(
    bot: Bot,
    session: AsyncSession,
    *,
    ticket_id: int,
    subject: str | None,
    body: str,
    from_staff: bool,
    ticket_user_id: int,
    actor_name: str | None = None,
) -> None:
    """Notify the other party of a ticket reply — always with پاسخ / بستن buttons."""
    markup = ticket_action_markup(ticket_id)
    preview = (body or "").strip()
    if len(preview) > 500:
        preview = preview[:500] + "…"

    if from_staff:
        user = await session.get(BotUser, int(ticket_user_id))
        if not user or not user.telegram_id:
            return
        text = format_message(
            "💬 پاسخ پشتیبانی",
            info_block(
                [
                    kv_line("🔢", "تیکت", f"#{ticket_id}"),
                    kv_line("📝", "موضوع", subject or "—"),
                    kv_line("💬", "پیام", preview or "—"),
                ]
            ),
        )
        try:
            await bot.send_message(int(user.telegram_id), text, reply_markup=markup)
        except Exception:
            pass
        return

    if not await notify_enabled(session, "notify_new_ticket"):
        return
    text = format_message(
        "🎫 پیام جدید تیکت",
        info_block(
            [
                kv_line("🔢", "تیکت", f"#{ticket_id}"),
                kv_line("👤", "از", actor_name or "کاربر"),
                kv_line("📝", "موضوع", subject or "—"),
                kv_line("💬", "پیام", preview or "—"),
            ]
        ),
    )
    extra = await _ticket_reseller_chat_ids(session, ticket_user_id)
    await _send_admins(bot, text, markup=markup, extra_chat_ids=extra)


async def notify_auto_approve(
    bot: Bot,
    session: AsyncSession,
    payment: Payment,
) -> None:
    if not await notify_enabled(session, "notify_auto_approve"):
        return
    text = format_message(
        "⚡ تأیید خودکار",
        info_block([kv_line("🧾", "پرداخت", f"#{payment.id}"), kv_line("✅", "نتیجه", "خودکار تأیید شد")]),
    )
    await _send_admins(bot, text)


def build_qr_caption(
    *,
    sub_url: str,
    ui: dict[str, str] | None = None,
    info: dict | None = None,
    data_limit: float | int | None = None,
    expire: Any = None,
    username: str | None = None,
) -> str:
    """
    Full QR caption: custom template (optional) + link + volume + expire.
    Telegram caption limit is 1024 chars.
    """
    ui = ui or {}
    custom = (ui.get("qr_caption") or "").strip()
    if custom:
        try:
            custom = custom.format(url=sub_url)
        except Exception:
            pass

    used = None
    limit = data_limit
    exp = expire
    uname = username
    if info:
        used = info.get("used_traffic")
        if limit is None:
            limit = info.get("data_limit")
        if exp is None:
            exp = info.get("expire")
        if not uname:
            uname = info.get("username")

    lines: list[str] = []
    if custom:
        lines.append(custom)
    else:
        lines.append("📱 <b>QR اشتراک</b>")
        lines.append("<i>با دوربین اسکن کنید یا در کلاینت Import کنید</i>")

    lines.append("")
    if uname:
        lines.append(f"👤 <b>{uname}</b>")
    if used is not None or limit is not None:
        vol = f"{format_bytes(used)} از {format_bytes(limit)}" if used is not None else format_bytes(limit)
        lines.append(f"📦 حجم: <b>{vol}</b>")
    if exp is not None or info is not None:
        lines.append(f"⏱ زمان: <b>{format_expire(exp)}</b>")
    lines.append("")
    lines.append("🔗 لینک اشتراک:")
    lines.append(f"<code>{sub_url}</code>")
    caption = "\n".join(lines).strip()
    return caption[:1024]
