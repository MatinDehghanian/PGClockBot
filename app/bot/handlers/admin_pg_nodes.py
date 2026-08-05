"""Admin PasarGuard nodes — list + ops parity with web /pg/nodes."""

from __future__ import annotations

import html

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.bot import keyboards as kb
from app.bot.auth import is_platform_admin as _is_admin
from app.bot.tg_utils import parse_bot_int, safe_edit_text
from app.db.models import BotUser
from app.services.formatting import node_status_fa
from app.services.pasarguard import PasarGuardError, get_pg

router = Router(name="admin_pg_nodes")


class PgNodeStates(StatesGroup):
    create_name = State()
    create_address = State()
    create_port = State()
    create_core = State()
    create_api_key = State()
    create_server_ca = State()


def _err_msg(exc: Exception) -> str:
    if isinstance(exc, PasarGuardError):
        return exc.user_message(fallback=str(exc))
    return str(exc) or "خطا"


def _nodes_list_kb(items: list) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(text="♻️ اتصال مجدد همه", callback_data="adm:pg:nreconall"),
            InlineKeyboardButton(text="➕ ساخت نود", callback_data="adm:pg:ncreate"),
        ]
    ]
    for n in items[:25]:
        if not isinstance(n, dict):
            continue
        nid = n.get("id")
        if nid is None:
            continue
        name = str(n.get("name") or n.get("address") or nid)[:28]
        status = node_status_fa(n.get("status") or n.get("connection_status"))
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"#{nid} {name} — {status}"[:60],
                    callback_data=f"adm:pg:n:{nid}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="⬅️ بازگشت", callback_data="adm:pg")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _node_detail_kb(nid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="♻️ اتصال مجدد", callback_data=f"adm:pg:recon:{nid}"),
                InlineKeyboardButton(text="🔄 همگام‌سازی", callback_data=f"adm:pg:nsync:{nid}"),
            ],
            [
                InlineKeyboardButton(text="🧹 ریست مصرف", callback_data=f"adm:pg:nresetask:{nid}"),
                InlineKeyboardButton(text="⏯ تغییر وضعیت", callback_data=f"adm:pg:ntog:{nid}"),
            ],
            [
                InlineKeyboardButton(text="🗑 حذف", callback_data=f"adm:pg:ndelask:{nid}"),
            ],
            [InlineKeyboardButton(text="⬅️ لیست نودها", callback_data="adm:pg:nodes")],
        ]
    )


def _node_detail_text(n: dict) -> str:
    nid = n.get("id")
    name = html.escape(str(n.get("name") or "—"))
    addr = html.escape(str(n.get("address") or n.get("host") or "—"))
    port = n.get("port")
    status = node_status_fa(n.get("status") or n.get("connection_status"))
    conn = html.escape(str(n.get("connection_type") or "—"))
    lines = [
        f"🕸 <b>نود #{html.escape(str(nid))}</b>",
        "",
        f"نام: <b>{name}</b>",
        f"آدرس: <code>{addr}{(':' + str(port)) if port else ''}</code>",
        f"وضعیت: <b>{html.escape(status)}</b>",
        f"اتصال: <code>{conn}</code>",
    ]
    core = n.get("core_config_id")
    if core is not None:
        lines.append(f"هسته: <code>{html.escape(str(core))}</code>")
    return "\n".join(lines)


async def _render_nodes_list(callback: CallbackQuery) -> None:
    try:
        nodes = await get_pg().get_nodes()
    except Exception as e:
        if callback.message:
            await safe_edit_text(callback.message, f"خطا: {_err_msg(e)}", reply_markup=None)
        return
    items = nodes if isinstance(nodes, list) else nodes.get("nodes", nodes.get("items", []))
    if not isinstance(items, list):
        items = []
    lines = ["🕸 <b>نودهای پاسارگارد</b>\n"]
    if not items:
        lines.append("نودی یافت نشد.")
    else:
        for n in items[:25]:
            if not isinstance(n, dict):
                continue
            nid = n.get("id")
            name = html.escape(str(n.get("name") or n.get("address") or nid))
            status = node_status_fa(n.get("status") or n.get("connection_status"))
            addr = html.escape(str(n.get("address") or n.get("host") or "—"))
            port = n.get("port")
            loc = f"{addr}{(':' + str(port)) if port else ''}"
            lines.append(f"#{nid} <b>{name}</b> — {html.escape(status)}\n<code>{loc}</code>")
    if callback.message:
        await safe_edit_text(
            callback.message,
            "\n\n".join(lines)[:3900],
            reply_markup=_nodes_list_kb(items),
        )


@router.callback_query(F.data == "adm:pg:nodes")
async def pg_nodes(callback: CallbackQuery, db_user: BotUser, state: FSMContext | None = None):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    if state is not None:
        await state.set_state(None)
    await callback.answer()
    await _render_nodes_list(callback)


@router.callback_query(F.data.regexp(r"^adm:pg:n:\d+$"))
async def pg_node_detail(callback: CallbackQuery, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    nid = int(callback.data.rsplit(":", 1)[-1])
    await callback.answer()
    try:
        n = await get_pg().get_node(nid)
    except Exception as e:
        await callback.answer(_err_msg(e), show_alert=True)
        return
    if not isinstance(n, dict):
        await callback.answer("یافت نشد", show_alert=True)
        return
    if callback.message:
        await safe_edit_text(
            callback.message,
            _node_detail_text(n),
            reply_markup=_node_detail_kb(nid),
        )


@router.callback_query(F.data.startswith("adm:pg:recon:"))
async def pg_recon(callback: CallbackQuery, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    try:
        node_id = int(callback.data.split(":")[-1])
    except ValueError:
        await callback.answer("نامعتبر", show_alert=True)
        return
    try:
        await get_pg().reconnect_node(node_id)
        await callback.answer("درخواست اتصال مجدد ارسال شد ✅", show_alert=True)
    except Exception as e:
        await callback.answer(_err_msg(e), show_alert=True)


@router.callback_query(F.data == "adm:pg:nreconall")
async def pg_recon_all(callback: CallbackQuery, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    try:
        await get_pg().reconnect_all_nodes()
        await callback.answer("اتصال مجدد همه نودها ارسال شد ✅", show_alert=True)
    except Exception as e:
        await callback.answer(_err_msg(e), show_alert=True)


@router.callback_query(F.data.startswith("adm:pg:nsync:"))
async def pg_node_sync(callback: CallbackQuery, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    try:
        node_id = int(callback.data.split(":")[-1])
    except ValueError:
        await callback.answer("نامعتبر", show_alert=True)
        return
    try:
        await get_pg().sync_node(node_id)
        await callback.answer("همگام‌سازی انجام شد ✅", show_alert=True)
    except Exception as e:
        await callback.answer(_err_msg(e), show_alert=True)


@router.callback_query(F.data.regexp(r"^adm:pg:nresetask:\d+$"))
async def pg_node_reset_ask(callback: CallbackQuery, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    nid = int(callback.data.split(":")[-1])
    await callback.answer()
    if callback.message:
        await safe_edit_text(
            callback.message,
            f"🧹 مصرف نود <b>#{nid}</b> ریست شود؟",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="✅ بله، ریست",
                            callback_data=f"adm:pg:nreset:{nid}",
                        )
                    ],
                    [InlineKeyboardButton(text="⬅️ انصراف", callback_data=f"adm:pg:n:{nid}")],
                ]
            ),
        )


@router.callback_query(F.data.regexp(r"^adm:pg:nreset:\d+$"))
async def pg_node_reset(callback: CallbackQuery, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    node_id = int(callback.data.split(":")[-1])
    try:
        await get_pg().reset_node(node_id)
        await callback.answer("مصرف نود ریست شد ✅", show_alert=True)
    except Exception as e:
        await callback.answer(_err_msg(e), show_alert=True)
        return
    if callback.message:
        try:
            n = await get_pg().get_node(node_id)
            await safe_edit_text(
                callback.message,
                _node_detail_text(n) if isinstance(n, dict) else f"نود #{node_id}",
                reply_markup=_node_detail_kb(node_id),
            )
        except Exception:
            pass


@router.callback_query(F.data.regexp(r"^adm:pg:ntog:\d+$"))
async def pg_node_toggle(callback: CallbackQuery, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    node_id = int(callback.data.split(":")[-1])
    try:
        pg = get_pg()
        node = await pg.get_node(node_id)
        st = str((node or {}).get("status") or "").lower()
        new_status = "connected" if st in {"disabled", "error", "limited"} else "disabled"
        await pg.modify_node(node_id, {"status": new_status})
        await callback.answer("وضعیت نود تغییر کرد ✅", show_alert=True)
        if callback.message:
            n = await pg.get_node(node_id)
            await safe_edit_text(
                callback.message,
                _node_detail_text(n) if isinstance(n, dict) else f"نود #{node_id}",
                reply_markup=_node_detail_kb(node_id),
            )
    except Exception as e:
        await callback.answer(_err_msg(e), show_alert=True)


@router.callback_query(F.data.regexp(r"^adm:pg:ndelask:\d+$"))
async def pg_node_del_ask(callback: CallbackQuery, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    nid = int(callback.data.split(":")[-1])
    await callback.answer()
    if callback.message:
        await safe_edit_text(
            callback.message,
            f"🗑 نود <b>#{nid}</b> حذف شود؟\nاین عمل برگشت‌ناپذیر است.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🗑 بله، حذف کن",
                            callback_data=f"adm:pg:ndel:{nid}",
                        )
                    ],
                    [InlineKeyboardButton(text="⬅️ انصراف", callback_data=f"adm:pg:n:{nid}")],
                ]
            ),
        )


@router.callback_query(F.data.regexp(r"^adm:pg:ndel:\d+$"))
async def pg_node_delete(callback: CallbackQuery, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    node_id = int(callback.data.split(":")[-1])
    try:
        await get_pg().delete_node(node_id)
        await callback.answer("نود حذف شد ✅", show_alert=True)
    except Exception as e:
        await callback.answer(_err_msg(e), show_alert=True)
        return
    await _render_nodes_list(callback)


# —— Create node wizard ——


@router.callback_query(F.data == "adm:pg:ncreate")
async def pg_node_create_start(callback: CallbackQuery, state: FSMContext, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    await state.set_state(PgNodeStates.create_name)
    await state.update_data(node_create={})
    await callback.answer()
    if callback.message:
        await safe_edit_text(
            callback.message,
            "➕ <b>ساخت نود</b>\n\nنام نود را بفرستید:",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="❌ انصراف", callback_data="adm:pg:nodes")]
                ]
            ),
        )
        await callback.message.answer("نام نود:", reply_markup=kb.cancel_reply())


@router.message(PgNodeStates.create_name)
async def pg_node_create_name(message: Message, state: FSMContext, db_user: BotUser):
    if not _is_admin(db_user) or kb.is_cancel_text(message.text):
        await state.set_state(None)
        await message.answer("انصراف.", reply_markup=kb.admin_reply_keyboard())
        return
    name = (message.text or "").strip()
    if not name:
        await message.answer("نام الزامی است.")
        return
    data = (await state.get_data()).get("node_create") or {}
    data["name"] = name
    await state.update_data(node_create=data)
    await state.set_state(PgNodeStates.create_address)
    await message.answer("آدرس نود (IP یا دامنه):", reply_markup=kb.cancel_reply())


@router.message(PgNodeStates.create_address)
async def pg_node_create_address(message: Message, state: FSMContext, db_user: BotUser):
    if not _is_admin(db_user) or kb.is_cancel_text(message.text):
        await state.set_state(None)
        await message.answer("انصراف.", reply_markup=kb.admin_reply_keyboard())
        return
    address = (message.text or "").strip()
    if not address:
        await message.answer("آدرس الزامی است.")
        return
    data = (await state.get_data()).get("node_create") or {}
    data["address"] = address
    await state.update_data(node_create=data)
    await state.set_state(PgNodeStates.create_port)
    await message.answer(
        "پورت (عدد — یا «-» برای رد کردن):",
        reply_markup=kb.cancel_reply(),
    )


@router.message(PgNodeStates.create_port)
async def pg_node_create_port(message: Message, state: FSMContext, db_user: BotUser):
    if not _is_admin(db_user) or kb.is_cancel_text(message.text):
        await state.set_state(None)
        await message.answer("انصراف.", reply_markup=kb.admin_reply_keyboard())
        return
    raw = (message.text or "").strip()
    data = (await state.get_data()).get("node_create") or {}
    if raw not in {"-", "—", ""}:
        try:
            data["port"] = parse_bot_int(raw)
        except ValueError:
            await message.answer("پورت نامعتبر — عدد بفرستید یا «-».")
            return
    await state.update_data(node_create=data)
    await state.set_state(None)
    await message.answer(
        "نوع اتصال را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="grpc", callback_data="adm:pg:nconn:grpc"),
                    InlineKeyboardButton(text="rest", callback_data="adm:pg:nconn:rest"),
                ],
                [InlineKeyboardButton(text="❌ انصراف", callback_data="adm:pg:nodes")],
            ]
        ),
    )


@router.callback_query(F.data.startswith("adm:pg:nconn:"))
async def pg_node_create_conn(callback: CallbackQuery, state: FSMContext, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    conn = callback.data.rsplit(":", 1)[-1]
    if conn not in {"grpc", "rest"}:
        await callback.answer("نامعتبر", show_alert=True)
        return
    data = (await state.get_data()).get("node_create") or {}
    if not data.get("name") or not data.get("address"):
        await callback.answer("ابتدا ساخت نود را شروع کنید", show_alert=True)
        return
    data["connection_type"] = conn
    await state.update_data(node_create=data)
    await state.set_state(PgNodeStates.create_core)
    await callback.answer()
    if callback.message:
        await safe_edit_text(
            callback.message,
            f"نوع اتصال: <code>{conn}</code>\nشناسه هسته (core_config_id) را بفرستید یا «-»:",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="❌ انصراف", callback_data="adm:pg:nodes")]
                ]
            ),
        )
        await callback.message.answer("شناسه هسته یا «-»:", reply_markup=kb.cancel_reply())


@router.message(PgNodeStates.create_core)
async def pg_node_create_core(message: Message, state: FSMContext, db_user: BotUser):
    if not _is_admin(db_user) or kb.is_cancel_text(message.text):
        await state.set_state(None)
        await message.answer("انصراف.", reply_markup=kb.admin_reply_keyboard())
        return
    raw = (message.text or "").strip()
    data = (await state.get_data()).get("node_create") or {}
    if raw not in {"-", "—", ""}:
        try:
            data["core_config_id"] = parse_bot_int(raw)
        except ValueError:
            await message.answer("عدد معتبر یا «-» بفرستید.")
            return
    await state.update_data(node_create=data)
    await state.set_state(PgNodeStates.create_api_key)
    await message.answer("API Key (یا «-» برای رد):", reply_markup=kb.cancel_reply())


@router.message(PgNodeStates.create_api_key)
async def pg_node_create_api_key(message: Message, state: FSMContext, db_user: BotUser):
    if not _is_admin(db_user) or kb.is_cancel_text(message.text):
        await state.set_state(None)
        await message.answer("انصراف.", reply_markup=kb.admin_reply_keyboard())
        return
    raw = (message.text or "").strip()
    data = (await state.get_data()).get("node_create") or {}
    if raw not in {"-", "—", ""}:
        data["api_key"] = raw
    await state.update_data(node_create=data)
    await state.set_state(PgNodeStates.create_server_ca)
    await message.answer(
        "Server CA (گواهی — چندخطی مجاز؛ یا «-» برای رد):",
        reply_markup=kb.cancel_reply(),
    )


@router.message(PgNodeStates.create_server_ca)
async def pg_node_create_server_ca(message: Message, state: FSMContext, db_user: BotUser):
    if not _is_admin(db_user) or kb.is_cancel_text(message.text):
        await state.set_state(None)
        await message.answer("انصراف.", reply_markup=kb.admin_reply_keyboard())
        return
    raw = (message.text or "").strip()
    data = dict((await state.get_data()).get("node_create") or {})
    if raw not in {"-", "—", ""}:
        data["server_ca"] = raw
    name = str(data.get("name") or "").strip()
    address = str(data.get("address") or "").strip()
    if not name or not address:
        await state.set_state(None)
        await message.answer("اطلاعات ناقص — از ابتدا شروع کنید.", reply_markup=kb.admin_reply_keyboard())
        return
    payload: dict = {
        "name": name,
        "address": address,
        "connection_type": data.get("connection_type") or "grpc",
    }
    if data.get("port") is not None:
        payload["port"] = int(data["port"])
    if data.get("api_key"):
        payload["api_key"] = data["api_key"]
    if data.get("server_ca"):
        payload["server_ca"] = data["server_ca"]
    if data.get("core_config_id") is not None:
        payload["core_config_id"] = int(data["core_config_id"])
    await state.set_state(None)
    try:
        await get_pg().create_node(payload)
    except Exception as e:
        await message.answer(
            f"ساخت نود ناموفق: {_err_msg(e)}\n"
            "علت محتمل: فیلدهای الزامی ناقص (api_key/گواهی).",
            reply_markup=kb.admin_reply_keyboard(),
        )
        return
    await message.answer("نود ساخته شد ✅", reply_markup=kb.admin_reply_keyboard())
    try:
        nodes = await get_pg().get_nodes()
        items = nodes if isinstance(nodes, list) else nodes.get("nodes", nodes.get("items", []))
        if not isinstance(items, list):
            items = []
        await message.answer(
            "🕸 <b>نودهای پاسارگارد</b>\n\nلیست به‌روز شد.",
            reply_markup=_nodes_list_kb(items),
        )
    except Exception as e:
        await message.answer(f"نود ساخته شد — لیست: {_err_msg(e)}")
