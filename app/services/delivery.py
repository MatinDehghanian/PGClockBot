from __future__ import annotations

"""Send clean delivery messages (+ optional subscription QR photo) to users."""

from typing import Any

from aiogram import Bot
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Payment, UserService
from app.services.formatting import format_message, format_toman, info_block, kv_line, service_card
from app.bot import keyboards as kb
from app.config import get_settings
from app.services.pasarguard import get_pg
from app.services.qrcode_gen import make_subscription_qr
from app.services.users import get_all_settings, on


async def build_delivery_content(
    session: AsyncSession,
    payment: Payment | None,
    order,
) -> dict[str, Any]:
    """Build title/body/markup/url/info for a successful delivery."""
    ui = await get_all_settings(session)
    markup = kb.back_home(ui)
    title = ui.get("delivery_title") or "✅ سرویس آماده است"
    sub_url = None
    sub_info: dict | None = None
    body_parts: list[str] = []

    if order and order.service_id:
        svc = await session.get(UserService, order.service_id)
        try:
            success = (ui.get("purchase_success_text") or "").format(order_id=order.id)
        except Exception:
            success = f"سفارش #{order.id} با موفقیت فعال شد."
        if success.strip():
            body_parts.append(success.strip())

        if svc and svc.subscription_token:
            try:
                info = await get_pg().subscription_info(svc.subscription_token)
                sub_info = info if isinstance(info, dict) else None
                body_parts.append(service_card(info))
            except Exception:
                if svc.pg_username:
                    body_parts.append(f"👤 <b>{svc.pg_username}</b>")
            sub_url = svc.subscription_url
            if sub_url and on(ui.get("show_sub_link_in_text", "1")):
                body_parts.append(
                    info_block(
                        [
                            "🔗 <b>لینک اشتراک</b>",
                            f"<code>{sub_url}</code>",
                        ]
                    )
                )
            markup = kb.service_actions(svc.id, ui)
        body = "\n\n".join(body_parts)
        return {
            "title": title,
            "text": format_message(title, body),
            "markup": markup,
            "sub_url": sub_url,
            "sub_info": sub_info,
            "ui": ui,
        }

    if payment and payment.is_wallet_topup:
        title = ui.get("wallet_success_title") or "💰 شارژ کیف پول"
        body = (
            ui.get("wallet_success_text")
            or "✅ مبلغ {amount} به کیف پول شما اضافه شد."
        )
        try:
            body = body.format(
                amount=format_toman(payment.amount, get_settings().currency),
                payment_id=payment.id,
            )
        except Exception:
            body = f"✅ کیف پول شما {format_toman(payment.amount, get_settings().currency)} شارژ شد."
        return {
            "title": title,
            "text": format_message(title, body),
            "markup": markup,
            "sub_url": None,
            "sub_info": None,
            "ui": ui,
        }

    title = ui.get("payment_ok_title") or "✅ پرداخت تأیید شد"
    body = info_block(
        [
            kv_line("🧾", "پرداخت", f"#{payment.id if payment else '—'}"),
            kv_line("✅", "وضعیت", "تأیید شد"),
        ]
    )
    return {
        "title": title,
        "text": format_message(title, body),
        "markup": markup,
        "sub_url": None,
        "sub_info": None,
        "ui": ui,
    }


async def send_delivery_to_user(
    bot: Bot,
    chat_id: int,
    session: AsyncSession,
    payment: Payment | None,
    order,
) -> str:
    """
    Send delivery text to user; if subscription URL exists and QR is enabled,
    also send QR as a photo. Returns the HTML text that was sent.
    """
    payload = await build_delivery_content(session, payment, order)
    text = payload["text"]
    markup: InlineKeyboardMarkup | None = payload["markup"]
    ui = payload["ui"]
    sub_url = payload["sub_url"]
    sub_info = payload.get("sub_info")

    try:
        await bot.send_message(chat_id, text, reply_markup=markup)
    except Exception:
        try:
            await bot.send_message(chat_id, text)
        except Exception:
            pass

    if sub_url:
        await send_subscription_qr_photo(
            bot, chat_id, sub_url, ui, info=sub_info
        )

    return text


async def send_subscription_qr_photo(
    bot: Bot,
    chat_id: int,
    sub_url: str,
    ui: dict[str, str] | None = None,
    *,
    info: dict | None = None,
    data_limit: float | int | None = None,
    expire: Any = None,
    username: str | None = None,
) -> bool:
    """Send QR photo for a subscription URL with full caption. Returns True if sent."""
    if not sub_url:
        return False
    ui = ui or {}
    if ui and not on(ui.get("qr_enabled", "1")):
        return False
    try:
        from app.services.notifications import build_qr_caption

        buf = make_subscription_qr(
            sub_url,
            background=(ui.get("qr_background") if ui else None) or None,
        )
        caption = build_qr_caption(
            sub_url=sub_url,
            ui=ui,
            info=info,
            data_limit=data_limit,
            expire=expire,
            username=username,
        )
        await bot.send_photo(
            chat_id,
            photo=BufferedInputFile(buf.read(), filename="subscription_qr.png"),
            caption=caption[:1024],
            parse_mode="HTML",
        )
        return True
    except Exception:
        return False


# Back-compat for callers that only need text+markup
async def build_approved_user_text(
    session: AsyncSession, payment: Payment, order
) -> tuple[str, Any]:
    payload = await build_delivery_content(session, payment, order)
    return payload["text"], payload["markup"]
