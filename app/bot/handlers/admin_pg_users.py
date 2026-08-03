"""Admin PasarGuard VPN users — list/search/create/edit/actions (panel parity)."""

from __future__ import annotations

import html
import re
import time
from typing import Any

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.bot import keyboards as kb
from app.bot.auth import is_platform_admin as _is_admin
from app.bot.tg_utils import safe_edit_text
from app.db.models import BotUser
from app.services.formatting import format_message, service_card
from app.services.pasarguard import (
    as_list,
    build_user_create_payload,
    build_user_modify_payload,
    get_pg,
    user_group_ids,
    user_subscription_url,
)

router = Router(name="admin_pg_users")

PAGE_SIZE = 10
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,32}$")


class PgUserStates(StatesGroup):
    search = State()
    create_username = State()
    create_gb = State()
    create_days = State()
    edit_username = State()
    edit_gb = State()
    edit_days = State()


def _user_label(u: dict) -> str:
    uname = str(u.get("username") or "—")
    status = str(u.get("status") or "")
    mark = ""
    if status in {"disabled", "limited", "expired"}:
        mark = "⛔ "
    elif status == "on_hold":
        mark = "⏸ "
    uid = u.get("id")
    return f"{mark}{uname}"[:48] if uid is not None else uname[:48]


def _user_actions_kb(uid: int, *, back: str = "adm:pg:users") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="♻️ ریست حجم", callback_data=f"adm:pg:reset:{uid}"),
                InlineKeyboardButton(text="🚫 غیرفعال", callback_data=f"adm:pg:dis:{uid}"),
            ],
            [
                InlineKeyboardButton(text="✅ فعال", callback_data=f"adm:pg:en:{uid}"),
                InlineKeyboardButton(text="🔏 باطل ساب", callback_data=f"adm:pg:rev:{uid}"),
            ],
            [
                InlineKeyboardButton(text="🔗 لینک ساب", callback_data=f"adm:pg:u:{uid}:link"),
                InlineKeyboardButton(text="✏️ ویرایش", callback_data=f"adm:pg:u:{uid}:edit"),
            ],
            [
                InlineKeyboardButton(text="🗑 حذف", callback_data=f"adm:pg:u:{uid}:delask"),
            ],
            [InlineKeyboardButton(text="⬅️ بازگشت", callback_data=back)],
        ]
    )


def _edit_menu_kb(uid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👤 تغییر نام کاربری", callback_data=f"adm:pg:u:{uid}:ed:name")],
            [InlineKeyboardButton(text="📦 تغییر حجم (GB)", callback_data=f"adm:pg:u:{uid}:ed:gb")],
            [InlineKeyboardButton(text="📅 تغییر مدت (روز)", callback_data=f"adm:pg:u:{uid}:ed:days")],
            [InlineKeyboardButton(text="📁 تغییر گروه‌ها", callback_data=f"adm:pg:u:{uid}:ed:grps")],
            [InlineKeyboardButton(text="⬅️ کارت کاربر", callback_data=f"adm:pg:u:{uid}")],
        ]
    )


async def _fetch_users_page(
    page: int,
    *,
    username: str | None = None,
) -> tuple[list[dict], int | None]:
    page = max(0, int(page))
    params: dict[str, Any] = {"offset": page * PAGE_SIZE, "limit": PAGE_SIZE}
    q = (username or "").strip()
    if q:
        params["username"] = q
    data = await get_pg().get_users(**params)
    if isinstance(data, list):
        users = [u for u in data if isinstance(u, dict)]
        total = None
    else:
        users = as_list(data, "users")
        total = None
        if isinstance(data, dict):
            for key in ("total", "count", "total_count"):
                if data.get(key) is not None:
                    try:
                        total = int(data[key])
                        break
                    except (TypeError, ValueError):
                        pass
    return users, total


async def _render_users_list(
    target: Message,
    *,
    page: int = 0,
    query: str | None = None,
    edit: bool = True,
) -> None:
    query = (query or "").strip() or None
    try:
        users, total = await _fetch_users_page(page, username=query)
    except Exception as e:
        text = format_message("❌ خطا", str(e))
        markup = None  # navigation is on reply keyboard (pg_reply_keyboard)
        if edit:
            await safe_edit_text(target, text, reply_markup=markup)
        else:
            await target.answer(text, reply_markup=markup)
        return

    rows: list[list[InlineKeyboardButton]] = []
    buttons: list[InlineKeyboardButton] = []
    for u in users:
        uid = u.get("id")
        if uid is None:
            continue
        buttons.append(
            InlineKeyboardButton(
                text=_user_label(u),
                callback_data=f"adm:pg:u:{int(uid)}",
            )
        )
    rows = kb.chunk_buttons(buttons, cols=2)

    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️ قبل", callback_data=f"adm:pg:users:p:{page - 1}"))
    has_next = False
    if total is not None:
        has_next = (page + 1) * PAGE_SIZE < total
        page_label = f"{page + 1}/{(max(total - 1, 0) // PAGE_SIZE) + 1}"
    else:
        has_next = len(users) >= PAGE_SIZE
        page_label = f"{page + 1}"
    if has_next:
        nav.append(InlineKeyboardButton(text="بعد ▶️", callback_data=f"adm:pg:users:p:{page + 1}"))
    if nav:
        rows.append(nav)

    if query:
        rows.append(
            [InlineKeyboardButton(text="🧹 پاک کردن جستجو", callback_data="adm:pg:users:clear")]
        )
    # Hub actions (search/create/back) live on the reply keyboard — not inline

    title = "👥 کاربران پاسارگارد"
    bits = [f"صفحه {page_label}"]
    if total is not None:
        bits.append(f"جمع: {total}")
    if query:
        bits.append(f"جستجو: <code>{html.escape(query)}</code>")
    body = " · ".join(bits)
    if not users:
        body += "\n\nکاربری یافت نشد."
    else:
        body += f"\n\n{len(users)} کاربر در این صفحه — برای جزئیات انتخاب کنید."

    text = format_message(title, body)
    markup = InlineKeyboardMarkup(inline_keyboard=rows)
    if edit:
        await safe_edit_text(target, text, reply_markup=markup)
    else:
        await target.answer(text, reply_markup=markup)


async def _show_user_card(
    target: Message,
    uid: int,
    *,
    edit: bool = True,
    notice: str | None = None,
) -> None:
    try:
        user = await get_pg().get_user_by_id(uid)
    except Exception as e:
        text = format_message("❌ خطا", str(e))
        if edit:
            await safe_edit_text(target, text, reply_markup=None)
        else:
            await target.answer(text, reply_markup=kb.pg_reply_keyboard())
        return
    text = service_card(user if isinstance(user, dict) else {})
    if notice:
        text = f"{notice}\n\n{text}"
    markup = _user_actions_kb(uid)
    if edit:
        await safe_edit_text(target, text, reply_markup=markup)
    else:
        await target.answer(text, reply_markup=markup)


# ----- list / search -----


@router.callback_query(F.data == "adm:pg:users")
@router.callback_query(F.data == "adm:pg:users:clear")
async def pg_users_list(callback: CallbackQuery, state: FSMContext, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    await callback.answer()
    await state.update_data(pg_list_q=None, pg_list_page=0)
    if callback.message:
        await _render_users_list(callback.message, page=0, query=None)


@router.callback_query(F.data.startswith("adm:pg:users:p:"))
async def pg_users_page(callback: CallbackQuery, state: FSMContext, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    try:
        page = int(callback.data.rsplit(":", 1)[-1])
    except ValueError:
        await callback.answer("صفحه نامعتبر", show_alert=True)
        return
    await callback.answer()
    data = await state.get_data()
    query = data.get("pg_list_q")
    await state.update_data(pg_list_page=page)
    if callback.message:
        await _render_users_list(callback.message, page=page, query=query)


@router.callback_query(F.data == "adm:pg:search")
async def pg_search_start(callback: CallbackQuery, state: FSMContext, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    await callback.answer()
    await state.set_state(PgUserStates.search)
    if callback.message:
        await callback.message.answer(
            "نام کاربری پاسارگارد را برای جستجو بفرستید:\n"
            "(جستجو در لیست فیلتر می‌شود؛ برای انصراف «انصراف» بزنید)",
            reply_markup=kb.cancel_reply(),
        )


@router.message(PgUserStates.search)
async def pg_search_query(message: Message, state: FSMContext, db_user: BotUser):
    if not _is_admin(db_user):
        await state.clear()
        return
    if kb.is_cancel_text(message.text):
        await state.clear()
        await message.answer("لغو شد.", reply_markup=kb.pg_reply_keyboard())
        return
    q = (message.text or "").strip()
    if not q:
        await message.answer("نام کاربری را به‌صورت متن بفرستید.")
        return
    await state.set_state(None)
    await state.update_data(pg_list_q=q, pg_list_page=0)
    # Exact match → open card; otherwise filtered list
    try:
        exact = await get_pg().get_user_by_username(q)
        if isinstance(exact, dict) and exact.get("id") is not None:
            await state.clear()
            await _show_user_card(message, int(exact["id"]), edit=False)
            return
    except Exception:
        pass
    await _render_users_list(message, page=0, query=q, edit=False)


# ----- user detail + actions -----


@router.callback_query(F.data.regexp(r"^adm:pg:u:\d+$"))
async def pg_user_detail(callback: CallbackQuery, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    uid = int(callback.data.rsplit(":", 1)[-1])
    await callback.answer()
    if callback.message:
        await _show_user_card(callback.message, uid)


@router.callback_query(F.data.regexp(r"^adm:pg:u:\d+:link$"))
async def pg_user_link(callback: CallbackQuery, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    uid = int(callback.data.split(":")[3])
    try:
        user = await get_pg().get_user_by_id(uid)
        url = user_subscription_url(user if isinstance(user, dict) else None)
        if not url:
            await callback.answer("لینک یافت نشد", show_alert=True)
            return
        await callback.answer()
        uname = (user or {}).get("username") if isinstance(user, dict) else ""
        await callback.message.answer(
            format_message(
                "🔗 لینک اشتراک",
                f"کاربر: <code>{html.escape(str(uname or uid))}</code>\n\n<code>{html.escape(url)}</code>",
            ),
            reply_markup=_user_actions_kb(uid),
        )
    except Exception as e:
        await callback.answer(str(e), show_alert=True)


@router.callback_query(F.data.startswith("adm:pg:reset:"))
async def pg_reset(callback: CallbackQuery, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    uid = int(callback.data.split(":")[-1])
    try:
        user = await get_pg().reset_user_by_id(uid)
        await callback.answer("ریست شد ✅", show_alert=True)
        if callback.message:
            if isinstance(user, dict) and user.get("id") is not None:
                text = "♻️ حجم ریست شد\n\n" + service_card(user)
                await safe_edit_text(callback.message, text, reply_markup=_user_actions_kb(uid))
            else:
                await _show_user_card(callback.message, uid, notice="♻️ حجم ریست شد")
    except Exception as e:
        await callback.answer(str(e), show_alert=True)


@router.callback_query(F.data.startswith("adm:pg:dis:"))
async def pg_dis(callback: CallbackQuery, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    uid = int(callback.data.split(":")[-1])
    try:
        user = await get_pg().set_disabled_by_id(uid, True)
        await callback.answer("غیرفعال شد", show_alert=True)
        if callback.message:
            if isinstance(user, dict) and user.get("id") is not None:
                text = "🚫 کاربر غیرفعال شد\n\n" + service_card(user)
                await safe_edit_text(callback.message, text, reply_markup=_user_actions_kb(uid))
            else:
                await _show_user_card(callback.message, uid, notice="🚫 کاربر غیرفعال شد")
    except Exception as e:
        await callback.answer(str(e), show_alert=True)


@router.callback_query(F.data.startswith("adm:pg:en:"))
async def pg_en(callback: CallbackQuery, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    uid = int(callback.data.split(":")[-1])
    try:
        user = await get_pg().set_disabled_by_id(uid, False)
        await callback.answer("فعال شد", show_alert=True)
        if callback.message:
            if isinstance(user, dict) and user.get("id") is not None:
                text = "✅ کاربر فعال شد\n\n" + service_card(user)
                await safe_edit_text(callback.message, text, reply_markup=_user_actions_kb(uid))
            else:
                await _show_user_card(callback.message, uid, notice="✅ کاربر فعال شد")
    except Exception as e:
        await callback.answer(str(e), show_alert=True)


@router.callback_query(F.data.startswith("adm:pg:rev:"))
async def pg_rev(callback: CallbackQuery, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    uid = int(callback.data.split(":")[-1])
    try:
        user = await get_pg().revoke_sub_by_id(uid)
        await callback.answer("ساب باطل شد", show_alert=True)
        if callback.message:
            if isinstance(user, dict) and user.get("id") is not None:
                text = "🔏 سابسکریپشن باطل شد\n\n" + service_card(user)
                await safe_edit_text(callback.message, text, reply_markup=_user_actions_kb(uid))
            else:
                await _show_user_card(callback.message, uid, notice="🔏 سابسکریپشن باطل شد")
    except Exception as e:
        await callback.answer(str(e), show_alert=True)


@router.callback_query(F.data.regexp(r"^adm:pg:u:\d+:delask$"))
async def pg_user_del_ask(callback: CallbackQuery, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    uid = int(callback.data.split(":")[3])
    await callback.answer()
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🗑 بله، حذف شود", callback_data=f"adm:pg:u:{uid}:del"),
                InlineKeyboardButton(text="انصراف", callback_data=f"adm:pg:u:{uid}"),
            ]
        ]
    )
    if callback.message:
        await safe_edit_text(
            callback.message,
            format_message("⚠️ حذف کاربر", f"کاربر #{uid} برای همیشه حذف شود؟"),
            reply_markup=markup,
        )


@router.callback_query(F.data.regexp(r"^adm:pg:u:\d+:del$"))
async def pg_user_del(callback: CallbackQuery, state: FSMContext, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    uid = int(callback.data.split(":")[3])
    try:
        await get_pg().delete_user_by_id(uid)
        await callback.answer("حذف شد", show_alert=True)
        data = await state.get_data()
        if callback.message:
            await _render_users_list(
                callback.message,
                page=int(data.get("pg_list_page") or 0),
                query=data.get("pg_list_q"),
            )
    except Exception as e:
        await callback.answer(str(e), show_alert=True)


# ----- create -----


@router.callback_query(F.data == "adm:pg:create")
async def pg_create_menu(callback: CallbackQuery, state: FSMContext, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    await callback.answer()
    await state.clear()
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 از تمپلیت", callback_data="adm:pg:create:tpl")],
            [InlineKeyboardButton(text="🛠 سفارشی (گروه + حجم + روز)", callback_data="adm:pg:create:custom")],
            [InlineKeyboardButton(text="⬅️ بازگشت", callback_data="adm:pg:users")],
        ]
    )
    if callback.message:
        await safe_edit_text(
            callback.message,
            format_message("➕ ساخت کاربر VPN", "نوع ساخت را انتخاب کنید:"),
            reply_markup=markup,
        )


@router.callback_query(F.data == "adm:pg:create:tpl")
async def pg_create_tpl_pick(callback: CallbackQuery, state: FSMContext, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    await callback.answer()
    await state.update_data(pg_create_mode="template", pg_template_id=None, pg_selected_groups=[])
    try:
        templates = await get_pg().get_user_templates_simple()
    except Exception:
        templates = []
    rows: list[list[InlineKeyboardButton]] = []
    for t in templates[:25]:
        if not isinstance(t, dict):
            continue
        tid = t.get("id")
        if tid is None:
            continue
        name = t.get("name") or f"تمپلیت {tid}"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"#{tid} — {name}"[:60],
                    callback_data=f"adm:pg:settpl:{int(tid)}",
                )
            ]
        )
    if not rows:
        rows.append(
            [InlineKeyboardButton(text="تمپلیتی نیست", callback_data="adm:pg:create")]
        )
    rows.append([InlineKeyboardButton(text="⬅️ بازگشت", callback_data="adm:pg:create")])
    if callback.message:
        await safe_edit_text(
            callback.message,
            "📋 تمپلیت را انتخاب کنید:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )


@router.callback_query(F.data.startswith("adm:pg:settpl:"))
async def pg_create_tpl_chosen(callback: CallbackQuery, state: FSMContext, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    tid = int(callback.data.split(":")[-1])
    await callback.answer()
    await state.update_data(pg_create_mode="template", pg_template_id=tid)
    await state.set_state(PgUserStates.create_username)
    if callback.message:
        await callback.message.answer(
            f"تمپلیت #{tid} انتخاب شد.\nنام کاربری جدید را بفرستید (۳–۳۲ حرف انگلیسی/عدد/_):",
            reply_markup=kb.cancel_reply(),
        )


@router.callback_query(F.data == "adm:pg:create:custom")
async def pg_create_custom_groups(callback: CallbackQuery, state: FSMContext, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    await callback.answer()
    await state.update_data(pg_create_mode="custom", pg_template_id=None, pg_selected_groups=[])
    await _show_create_group_picker(callback, state)


async def _show_create_group_picker(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    selected = [int(x) for x in (data.get("pg_selected_groups") or [])]
    edit_uid = data.get("pg_edit_uid")
    groups = data.get("pg_groups_cache")
    if not isinstance(groups, list):
        try:
            groups = await get_pg().get_groups_simple()
        except Exception:
            groups = []
        await state.update_data(pg_groups_cache=groups)
    rows: list[list[InlineKeyboardButton]] = []
    prefix = "adm:pg:edgrp" if edit_uid else "adm:pg:toggrp"
    for g in groups[:25]:
        if not isinstance(g, dict):
            continue
        gid = g.get("id")
        if gid is None:
            continue
        gid = int(gid)
        mark = "✅ " if gid in selected else ""
        name = g.get("name") or f"گروه {gid}"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{mark}#{gid} — {name}"[:60],
                    callback_data=f"{prefix}:{gid}",
                )
            ]
        )
    done_cb = "adm:pg:edgrpdone" if edit_uid else "adm:pg:grpdone"
    back_cb = f"adm:pg:u:{edit_uid}:edit" if edit_uid else "adm:pg:create"
    if rows:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"✅ تأیید ({len(selected)})",
                    callback_data=done_cb,
                )
            ]
        )
    else:
        rows.append([InlineKeyboardButton(text="گروهی نیست", callback_data=back_cb)])
    rows.append([InlineKeyboardButton(text="⬅️ بازگشت", callback_data=back_cb)])
    text = (
        "📁 گروه‌ها را انتخاب کنید (چندتایی):\n"
        f"انتخاب‌شده: {', '.join(str(x) for x in selected) or '—'}"
    )
    if callback.message:
        await safe_edit_text(
            callback.message,
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )


@router.callback_query(F.data.startswith("adm:pg:toggrp:"))
async def pg_create_toggrp(callback: CallbackQuery, state: FSMContext, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    gid = int(callback.data.split(":")[-1])
    data = await state.get_data()
    selected = [int(x) for x in (data.get("pg_selected_groups") or [])]
    if gid in selected:
        selected = [x for x in selected if x != gid]
    else:
        selected.append(gid)
    await state.update_data(pg_selected_groups=selected)
    await callback.answer()
    await _show_create_group_picker(callback, state)


@router.callback_query(F.data == "adm:pg:grpdone")
async def pg_create_grpdone(callback: CallbackQuery, state: FSMContext, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    data = await state.get_data()
    selected = [int(x) for x in (data.get("pg_selected_groups") or [])]
    if not selected:
        await callback.answer("حداقل یک گروه انتخاب کنید", show_alert=True)
        return
    await callback.answer()
    await state.set_state(PgUserStates.create_username)
    if callback.message:
        await callback.message.answer(
            "نام کاربری جدید را بفرستید (۳–۳۲ حرف انگلیسی/عدد/_):",
            reply_markup=kb.cancel_reply(),
        )


@router.message(PgUserStates.create_username)
async def pg_create_username(message: Message, state: FSMContext, db_user: BotUser):
    if not _is_admin(db_user):
        await state.clear()
        return
    if kb.is_cancel_text(message.text):
        await state.clear()
        await message.answer("لغو شد.", reply_markup=kb.pg_reply_keyboard())
        return
    uname = (message.text or "").strip()
    if not _USERNAME_RE.fullmatch(uname):
        await message.answer("نام کاربری باید ۳ تا ۳۲ کاراکتر انگلیسی، عدد یا _ باشد.")
        return
    data = await state.get_data()
    mode = data.get("pg_create_mode") or "template"
    await state.update_data(pg_create_username=uname)
    if mode == "template":
        tid = data.get("pg_template_id")
        if not tid:
            await state.clear()
            await message.answer("تمپلیت انتخاب نشده.", reply_markup=kb.pg_reply_keyboard())
            return
        try:
            user = await get_pg().create_user_from_template(
                {
                    "username": uname,
                    "user_template_id": int(tid),
                    "note": f"telegram admin · {db_user.telegram_id}",
                }
            )
        except Exception as e:
            await message.answer(f"خطا در ساخت: {e}")
            return
        await state.clear()
        uid = int((user or {}).get("id") or 0) if isinstance(user, dict) else 0
        if uid:
            await _show_user_card(message, uid, edit=False, notice="✅ کاربر ساخته شد")
        else:
            await message.answer("✅ کاربر ساخته شد.", reply_markup=kb.pg_reply_keyboard())
        return
    await state.set_state(PgUserStates.create_gb)
    await message.answer(
        "حجم به گیگابایت را بفرستید (عدد؛ برای نامحدود ۰ بفرستید):",
        reply_markup=kb.cancel_reply(),
    )


@router.message(PgUserStates.create_gb)
async def pg_create_gb(message: Message, state: FSMContext, db_user: BotUser):
    if not _is_admin(db_user):
        await state.clear()
        return
    if kb.is_cancel_text(message.text):
        await state.clear()
        await message.answer("لغو شد.", reply_markup=kb.pg_reply_keyboard())
        return
    raw = (message.text or "").strip().replace(",", ".")
    try:
        gb = float(raw)
        if gb < 0:
            raise ValueError
    except ValueError:
        await message.answer("عدد معتبر بفرستید (مثلاً ۱۰ یا ۰).")
        return
    await state.update_data(pg_create_gb=gb)
    await state.set_state(PgUserStates.create_days)
    await message.answer(
        "مدت به روز را بفرستید (عدد؛ برای بدون انقضا ۰ بفرستید):",
        reply_markup=kb.cancel_reply(),
    )


@router.message(PgUserStates.create_days)
async def pg_create_days(message: Message, state: FSMContext, db_user: BotUser):
    if not _is_admin(db_user):
        await state.clear()
        return
    if kb.is_cancel_text(message.text):
        await state.clear()
        await message.answer("لغو شد.", reply_markup=kb.pg_reply_keyboard())
        return
    raw = (message.text or "").strip()
    try:
        days = int(float(raw))
        if days < 0:
            raise ValueError
    except ValueError:
        await message.answer("عدد روز معتبر بفرستید.")
        return
    data = await state.get_data()
    uname = data.get("pg_create_username")
    groups = [int(x) for x in (data.get("pg_selected_groups") or [])]
    gb = float(data.get("pg_create_gb") or 0)
    if not uname or not groups:
        await state.clear()
        await message.answer("داده ناقص است — دوباره شروع کنید.", reply_markup=kb.pg_reply_keyboard())
        return
    data_limit = int(gb * (1024**3)) if gb > 0 else 0
    expire_ts = int(time.time()) + days * 86400 if days > 0 else 0
    payload = build_user_create_payload(
        username=uname,
        group_ids=groups,
        data_limit=data_limit if gb > 0 else 0,
        expire_ts=expire_ts if days > 0 else 0,
        note=f"telegram admin · {db_user.telegram_id}",
    )
    # Unlimited: omit or send 0 — panel uses 0 for unlimited on edit; create may omit
    if gb <= 0:
        payload["data_limit"] = 0
    if days <= 0:
        payload["expire"] = 0
    try:
        user = await get_pg().create_user(payload)
    except Exception as e:
        await message.answer(f"خطا در ساخت: {e}")
        return
    await state.clear()
    uid = int((user or {}).get("id") or 0) if isinstance(user, dict) else 0
    if uid:
        await _show_user_card(message, uid, edit=False, notice="✅ کاربر ساخته شد")
    else:
        await message.answer("✅ کاربر ساخته شد.", reply_markup=kb.pg_reply_keyboard())


# ----- edit -----


@router.callback_query(F.data.regexp(r"^adm:pg:u:\d+:edit$"))
async def pg_user_edit_menu(callback: CallbackQuery, state: FSMContext, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    uid = int(callback.data.split(":")[3])
    await callback.answer()
    await state.update_data(pg_edit_uid=uid)
    if callback.message:
        await safe_edit_text(
            callback.message,
            format_message("✏️ ویرایش کاربر", f"#{uid} — چه چیزی تغییر کند؟"),
            reply_markup=_edit_menu_kb(uid),
        )


@router.callback_query(F.data.regexp(r"^adm:pg:u:\d+:ed:name$"))
async def pg_edit_name_ask(callback: CallbackQuery, state: FSMContext, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    uid = int(callback.data.split(":")[3])
    await callback.answer()
    await state.update_data(pg_edit_uid=uid)
    await state.set_state(PgUserStates.edit_username)
    if callback.message:
        await callback.message.answer(
            "نام کاربری جدید را بفرستید:",
            reply_markup=kb.cancel_reply(),
        )


@router.message(PgUserStates.edit_username)
async def pg_edit_name_save(message: Message, state: FSMContext, db_user: BotUser):
    if not _is_admin(db_user):
        await state.clear()
        return
    if kb.is_cancel_text(message.text):
        await state.clear()
        await message.answer("لغو شد.", reply_markup=kb.pg_reply_keyboard())
        return
    uname = (message.text or "").strip()
    if not _USERNAME_RE.fullmatch(uname):
        await message.answer("نام کاربری نامعتبر است.")
        return
    data = await state.get_data()
    uid = int(data.get("pg_edit_uid") or 0)
    if not uid:
        await state.clear()
        return
    try:
        current = await get_pg().get_user_by_id(uid)
        groups = user_group_ids(current if isinstance(current, dict) else {})
        payload = build_user_modify_payload(
            username=uname,
            group_ids=groups or None,
            status=str((current or {}).get("status") or "") or None if isinstance(current, dict) else None,
        )
        await get_pg().modify_user_by_id(uid, payload)
    except Exception as e:
        await message.answer(f"خطا: {e}")
        return
    await state.clear()
    await _show_user_card(message, uid, edit=False, notice="✅ نام کاربری به‌روز شد")


@router.callback_query(F.data.regexp(r"^adm:pg:u:\d+:ed:gb$"))
async def pg_edit_gb_ask(callback: CallbackQuery, state: FSMContext, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    uid = int(callback.data.split(":")[3])
    await callback.answer()
    await state.update_data(pg_edit_uid=uid)
    await state.set_state(PgUserStates.edit_gb)
    if callback.message:
        await callback.message.answer(
            "حجم جدید به گیگابایت (۰ = نامحدود):",
            reply_markup=kb.cancel_reply(),
        )


@router.message(PgUserStates.edit_gb)
async def pg_edit_gb_save(message: Message, state: FSMContext, db_user: BotUser):
    if not _is_admin(db_user):
        await state.clear()
        return
    if kb.is_cancel_text(message.text):
        await state.clear()
        await message.answer("لغو شد.", reply_markup=kb.pg_reply_keyboard())
        return
    raw = (message.text or "").strip().replace(",", ".")
    try:
        gb = float(raw)
        if gb < 0:
            raise ValueError
    except ValueError:
        await message.answer("عدد معتبر بفرستید.")
        return
    data = await state.get_data()
    uid = int(data.get("pg_edit_uid") or 0)
    if not uid:
        await state.clear()
        return
    try:
        current = await get_pg().get_user_by_id(uid)
        groups = user_group_ids(current if isinstance(current, dict) else {})
        uname = (current or {}).get("username") if isinstance(current, dict) else None
        payload = build_user_modify_payload(
            username=str(uname) if uname else None,
            group_ids=groups or None,
            data_limit=int(gb * (1024**3)) if gb > 0 else 0,
            status=str((current or {}).get("status") or "") or None if isinstance(current, dict) else None,
        )
        await get_pg().modify_user_by_id(uid, payload)
    except Exception as e:
        await message.answer(f"خطا: {e}")
        return
    await state.clear()
    await _show_user_card(message, uid, edit=False, notice="✅ حجم به‌روز شد")


@router.callback_query(F.data.regexp(r"^adm:pg:u:\d+:ed:days$"))
async def pg_edit_days_ask(callback: CallbackQuery, state: FSMContext, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    uid = int(callback.data.split(":")[3])
    await callback.answer()
    await state.update_data(pg_edit_uid=uid)
    await state.set_state(PgUserStates.edit_days)
    if callback.message:
        await callback.message.answer(
            "مدت باقی‌مانده از الان به روز (۰ = بدون انقضا):",
            reply_markup=kb.cancel_reply(),
        )


@router.message(PgUserStates.edit_days)
async def pg_edit_days_save(message: Message, state: FSMContext, db_user: BotUser):
    if not _is_admin(db_user):
        await state.clear()
        return
    if kb.is_cancel_text(message.text):
        await state.clear()
        await message.answer("لغو شد.", reply_markup=kb.pg_reply_keyboard())
        return
    raw = (message.text or "").strip()
    try:
        days = int(float(raw))
        if days < 0:
            raise ValueError
    except ValueError:
        await message.answer("عدد روز معتبر بفرستید.")
        return
    data = await state.get_data()
    uid = int(data.get("pg_edit_uid") or 0)
    if not uid:
        await state.clear()
        return
    expire_ts = int(time.time()) + days * 86400 if days > 0 else 0
    try:
        current = await get_pg().get_user_by_id(uid)
        groups = user_group_ids(current if isinstance(current, dict) else {})
        uname = (current or {}).get("username") if isinstance(current, dict) else None
        payload = build_user_modify_payload(
            username=str(uname) if uname else None,
            group_ids=groups or None,
            expire_ts=expire_ts,
            status=str((current or {}).get("status") or "") or None if isinstance(current, dict) else None,
        )
        await get_pg().modify_user_by_id(uid, payload)
    except Exception as e:
        await message.answer(f"خطا: {e}")
        return
    await state.clear()
    await _show_user_card(message, uid, edit=False, notice="✅ انقضا به‌روز شد")


@router.callback_query(F.data.regexp(r"^adm:pg:u:\d+:ed:grps$"))
async def pg_edit_groups_start(callback: CallbackQuery, state: FSMContext, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    uid = int(callback.data.split(":")[3])
    await callback.answer()
    try:
        current = await get_pg().get_user_by_id(uid)
        selected = user_group_ids(current if isinstance(current, dict) else {})
    except Exception:
        selected = []
    await state.update_data(pg_edit_uid=uid, pg_selected_groups=selected)
    await _show_create_group_picker(callback, state)


@router.callback_query(F.data.startswith("adm:pg:edgrp:"))
async def pg_edit_toggrp(callback: CallbackQuery, state: FSMContext, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    gid = int(callback.data.split(":")[-1])
    data = await state.get_data()
    selected = [int(x) for x in (data.get("pg_selected_groups") or [])]
    if gid in selected:
        selected = [x for x in selected if x != gid]
    else:
        selected.append(gid)
    await state.update_data(pg_selected_groups=selected)
    await callback.answer()
    await _show_create_group_picker(callback, state)


@router.callback_query(F.data == "adm:pg:edgrpdone")
async def pg_edit_grpdone(callback: CallbackQuery, state: FSMContext, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    data = await state.get_data()
    uid = int(data.get("pg_edit_uid") or 0)
    selected = [int(x) for x in (data.get("pg_selected_groups") or [])]
    if not uid:
        await callback.answer("کاربر نامعتبر", show_alert=True)
        return
    if not selected:
        await callback.answer("حداقل یک گروه انتخاب کنید", show_alert=True)
        return
    try:
        current = await get_pg().get_user_by_id(uid)
        uname = (current or {}).get("username") if isinstance(current, dict) else None
        payload = build_user_modify_payload(
            username=str(uname) if uname else None,
            group_ids=selected,
            status=str((current or {}).get("status") or "") or None if isinstance(current, dict) else None,
        )
        await get_pg().modify_user_by_id(uid, payload)
        await callback.answer("گروه‌ها ذخیره شد ✅", show_alert=True)
        await state.clear()
        if callback.message:
            await _show_user_card(callback.message, uid, notice="✅ گروه‌ها به‌روز شد")
    except Exception as e:
        await callback.answer(str(e), show_alert=True)
