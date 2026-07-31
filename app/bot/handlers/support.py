from __future__ import annotations

import html

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards as kb
from app.bot.tg_utils import safe_edit_text
from app.db.models import BotUser, Ticket
from app.services.formatting import format_message, ticket_status_fa
from app.services.support_contacts import (
    active_support_contacts,
    parse_support_contacts,
    support_chat_url,
)
from app.services.tickets import create_ticket, get_ticket, list_user_tickets, reply_ticket
from app.services.users import get_all_settings

router = Router(name="support")


class SupportStates(StatesGroup):
    subject = State()
    body = State()
    reply = State()


def _active_contacts_from_ui(ui: dict) -> list[dict]:
    return active_support_contacts(parse_support_contacts(ui.get("support_contacts")))


@router.callback_query(F.data == "support:home")
async def support_home(callback: CallbackQuery, session: AsyncSession):
    await callback.answer()
    ui = await get_all_settings(session)
    contacts = _active_contacts_from_ui(ui)
    if len(contacts) == 1:
        url = support_chat_url(contacts[0].get("telegram") or "")
        title = contacts[0].get("title") or "پشتیبان"
        rows: list[list[InlineKeyboardButton]] = []
        if url:
            rows.append([InlineKeyboardButton(text=f"💬 گفتگو با {title}", url=url)])
        rows.append([InlineKeyboardButton(text="🟣✉️ تیکت پشتیبانی", callback_data="support:tickets")])
        rows.append([InlineKeyboardButton(text=ui.get("btn_back") or "بازگشت", callback_data="menu:home")])
        text = format_message(
            "🎧 پشتیبانی",
            f"برای ارتباط مستقیم روی دکمه زیر بزنید:\n<b>{title}</b>",
        )
        if callback.message:
            await safe_edit_text(callback.message, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
        return
    if len(contacts) > 1:
        text = format_message(
            "🎧 پشتیبانی",
            "یکی از پشتیبان‌ها را انتخاب کنید:",
        )
        if callback.message:
            await safe_edit_text(callback.message, 
                text,
                reply_markup=kb.support_contacts_keyboard(contacts, ui),
            )
        return
    # No contacts → classic ticket UI
    text = ui.get("support_text") or "پیام خود را بنویسید؛ تیم پشتیبانی پاسخ می‌دهد."
    if callback.message:
        await safe_edit_text(callback.message, 
            format_message("🎧 پشتیبانی", text),
            reply_markup=kb.support_keyboard(ui),
        )


@router.callback_query(F.data == "support:tickets")
async def support_tickets_home(callback: CallbackQuery, session: AsyncSession):
    await callback.answer()
    ui = await get_all_settings(session)
    text = ui.get("support_text") or "پیام خود را بنویسید؛ تیم پشتیبانی پاسخ می‌دهد."
    if callback.message:
        await safe_edit_text(callback.message, 
            format_message("🎧 پشتیبانی — تیکت", text),
            reply_markup=kb.support_keyboard(ui),
        )


@router.callback_query(F.data == "support:new")
async def support_new(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(SupportStates.subject)
    if callback.message:
        await callback.message.answer("موضوع تیکت را بنویسید:", reply_markup=kb.cancel_reply())


@router.message(SupportStates.subject)
async def support_subject(message: Message, state: FSMContext):
    if kb.is_cancel_text(message.text):
        from app.bot.tg_utils import clear_fsm_with_reply

        await clear_fsm_with_reply(message, state)
        return
    subject = (message.text or "").strip()
    if not subject:
        await message.answer("موضوع را به‌صورت متن بفرستید.")
        return
    await state.update_data(subject=subject)
    await state.set_state(SupportStates.body)
    await message.answer("متن پیام را بنویسید:")


@router.message(SupportStates.body)
async def support_body(message: Message, state: FSMContext, session: AsyncSession, db_user: BotUser):
    if kb.is_cancel_text(message.text):
        from app.bot.tg_utils import clear_fsm_with_reply

        await clear_fsm_with_reply(message, state)
        return
    body = (message.text or "").strip()
    if not body:
        await message.answer("متن پیام را به‌صورت متن بفرستید.")
        return
    data = await state.get_data()
    await state.clear()
    ticket = await create_ticket(
        session,
        db_user.id,
        data.get("subject") or "پشتیبانی",
        body,
        db_user.telegram_id,
    )
    await message.answer(
        format_message("✅ تیکت ثبت شد", f"تیکت <b>#{ticket.id}</b> با موفقیت ثبت شد.\nبه‌زودی پاسخ می‌دهیم."),
        reply_markup=kb.back_home(),
    )
    try:
        from app.services.notifications import notify_new_ticket

        await notify_new_ticket(
            message.bot,
            session,
            ticket_id=ticket.id,
            subject=ticket.subject,
            user_name=db_user.full_name or db_user.username,
        )
    except Exception:
        pass


@router.callback_query(F.data == "support:list")
async def support_list(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    await callback.answer()
    tickets = await list_user_tickets(session, db_user.id)
    if not tickets:
        text = "تیکتی ندارید."
        markup = kb.support_keyboard()
    else:
        rows = [
            [
                InlineKeyboardButton(
                    text=f"#{t.id} — {ticket_status_fa(t.status)} — {t.subject[:20]}",
                    callback_data=f"support:view:{t.id}",
                )
            ]
            for t in tickets[:20]
        ]
        rows.append([InlineKeyboardButton(text="⬅️ بازگشت", callback_data="support:tickets")])
        text = "📋 تیکت‌های شما:"
        markup = InlineKeyboardMarkup(inline_keyboard=rows)
    if callback.message:
        await safe_edit_text(callback.message, text, reply_markup=markup)


@router.callback_query(F.data.startswith("support:view:"))
async def support_view(callback: CallbackQuery, session: AsyncSession, db_user: BotUser, state: FSMContext):
    ticket_id = int(callback.data.split(":")[-1])
    ticket = await get_ticket(session, ticket_id)
    if not ticket or ticket.user_id != db_user.id:
        await callback.answer("یافت نشد", show_alert=True)
        return
    await callback.answer()
    lines = [
        f"🎫 تیکت #{ticket.id} — {ticket_status_fa(ticket.status)}",
        f"<b>{html.escape(ticket.subject or '')}</b>",
        "",
    ]
    for m in ticket.messages[-10:]:
        who = "پشتیبانی" if m.is_staff else "شما"
        lines.append(f"<b>{who}:</b> {html.escape(m.body or '')}")
    await state.set_state(SupportStates.reply)
    await state.update_data(ticket_id=ticket.id)
    if callback.message:
        await safe_edit_text(callback.message, "\n".join(lines))
        await callback.message.answer("برای پاسخ، پیام بفرستید یا انصراف بزنید:", reply_markup=kb.cancel_reply())


@router.message(SupportStates.reply)
async def support_reply(message: Message, state: FSMContext, session: AsyncSession, db_user: BotUser):
    if (message.text or "").strip() == "انصراف":
        await state.clear()
        await message.answer("بسته شد.", reply_markup=kb.back_home())
        return
    data = await state.get_data()
    ticket = await session.get(Ticket, data.get("ticket_id"))
    if not ticket or ticket.user_id != db_user.id:
        await state.clear()
        await message.answer("تیکت نامعتبر")
        return
    await reply_ticket(session, ticket, message.text or "", db_user.telegram_id, is_staff=False)
    await state.clear()
    await message.answer("پاسخ ثبت شد.", reply_markup=kb.back_home())
