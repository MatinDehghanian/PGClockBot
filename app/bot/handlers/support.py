from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards as kb
from app.config import get_settings
from app.db.models import BotUser, Ticket
from app.services.tickets import create_ticket, get_ticket, list_user_tickets, reply_ticket
from app.services.users import get_all_settings, get_setting

router = Router(name="support")


class SupportStates(StatesGroup):
    subject = State()
    body = State()
    reply = State()


@router.callback_query(F.data == "support:home")
async def support_home(callback: CallbackQuery, session: AsyncSession):
    await callback.answer()
    ui = await get_all_settings(session)
    text = ui.get("support_text") or await get_setting(session, "support_text")
    if callback.message:
        await callback.message.edit_text(
            f"🎧 <b>پشتیبانی</b>\n\n{text}",
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
    if (message.text or "").strip() == "انصراف":
        await state.clear()
        await message.answer("لغو شد.", reply_markup=kb.back_home())
        return
    await state.update_data(subject=message.text.strip())
    await state.set_state(SupportStates.body)
    await message.answer("متن پیام را بنویسید:")


@router.message(SupportStates.body)
async def support_body(message: Message, state: FSMContext, session: AsyncSession, db_user: BotUser):
    if (message.text or "").strip() == "انصراف":
        await state.clear()
        await message.answer("لغو شد.", reply_markup=kb.back_home())
        return
    data = await state.get_data()
    await state.clear()
    ticket = await create_ticket(
        session,
        db_user.id,
        data.get("subject") or "پشتیبانی",
        message.text or "",
        db_user.telegram_id,
    )
    await message.answer(f"تیکت #{ticket.id} ثبت شد ✅", reply_markup=kb.back_home())
    for admin_id in get_settings().admin_ids:
        try:
            await message.bot.send_message(
                admin_id,
                f"🎫 تیکت جدید #{ticket.id}\nاز: {db_user.full_name}\n{ticket.subject}",
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
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        rows = [
            [InlineKeyboardButton(text=f"#{t.id} — {t.status} — {t.subject[:20]}", callback_data=f"support:view:{t.id}")]
            for t in tickets[:20]
        ]
        rows.append([InlineKeyboardButton(text="⬅️ بازگشت", callback_data="support:home")])
        text = "📋 تیکت‌های شما:"
        markup = InlineKeyboardMarkup(inline_keyboard=rows)
    if callback.message:
        await callback.message.edit_text(text, reply_markup=markup)


@router.callback_query(F.data.startswith("support:view:"))
async def support_view(callback: CallbackQuery, session: AsyncSession, db_user: BotUser, state: FSMContext):
    await callback.answer()
    ticket_id = int(callback.data.split(":")[-1])
    ticket = await get_ticket(session, ticket_id)
    if not ticket or ticket.user_id != db_user.id:
        await callback.answer("یافت نشد", show_alert=True)
        return
    lines = [f"🎫 تیکت #{ticket.id} — {ticket.status}", f"<b>{ticket.subject}</b>", ""]
    for m in ticket.messages[-10:]:
        who = "پشتیبانی" if m.is_staff else "شما"
        lines.append(f"<b>{who}:</b> {m.body}")
    await state.set_state(SupportStates.reply)
    await state.update_data(ticket_id=ticket.id)
    if callback.message:
        await callback.message.edit_text("\n".join(lines))
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
