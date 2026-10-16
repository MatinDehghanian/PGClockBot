"""In-menu editor: switch edit mode, list a menu's buttons, change text or color.

``owner_router`` (platform owner, behind the owner-principal middleware) and
``shop_router`` (shop owner, own shop only, shop bot only) share the views.
Callback data ``ed:<a|r>:<view>[:<screen>[:<button>[:<color>]]]``:
``h`` switches, ``f1``/``f0`` feature on/off (owner), ``m1``/``m0`` my edit
mode, ``o`` a menu's buttons, ``b`` one button, ``t`` new text, ``c`` color.
Button numbers are positions in ``screen_buttons``; every step rebuilds the
real menu and re-checks the position and permissions before acting.
"""

from __future__ import annotations

import html
import logging
from dataclasses import dataclass

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards as kb
from app.bot.edit_mode import EDIT_CALLBACK_ROOT, audience_code
from app.bot.handlers.button_colors import shop_settings_shop_id
from app.bot.screen_registry import SCREENS, ScreenButton, ScreenContext, ScreenSpec, screen_buttons
from app.bot.tg_utils import safe_edit_text
from app.db.models import BotUser
from app.services import bot_feedback_texts as feedback
from app.services.button_color_editor import (
    COLOR_NAMES,
    COLOR_SWATCHES,
    ColorItem,
    find_color_item,
    reset_button_color,
    set_button_color,
    shared_button_count,
)
from app.services.resellers import get_reseller_profile
from app.services.rich_text import pack_setting_from_message
from app.services.screen_editor import (
    EDIT_MODE_MINUTES,
    LABEL_MAX_LENGTH,
    EditorActor,
    can_edit_label,
    edit_mode_store,
    is_editor_enabled,
    save_button_label,
    set_editor_enabled,
    validate_button_label,
)
from app.services.users import get_all_settings

logger = logging.getLogger(__name__)

owner_router = Router(name="screen_editor_owner")
shop_router = Router(name="screen_editor_shop")

_CODE_TO_COLOR = {"w": "", "p": "primary", "s": "success", "d": "danger"}
_RESET_CODE = "x"
# Where «⬅️ بازگشت» leads from the switches: the owner opened them from the admin home.
_SETTINGS_BACK = {"a": "nv:adm:home", "r": "res:st:sec:menu"}
_CANCEL_WORDS = ["انصراف", "لغو", "cancel"]

BTN_ENTRY = "✏️ حالت ویرایش منوها"
BTN_BACK = "⬅️ بازگشت"
BTN_BACK_TO_MENU = "↩️ بازگشت به منو"
BTN_EDIT_MAIN_MENU = "✏️ ویرایش منوی اصلی"
BTN_EDIT_TEXT = "✏️ تغییر متن"
BTN_RESET = "↺ رنگ پیش‌فرض"
BTN_CONTINUE = "✏️ ادامهٔ ویرایش"
TEXT_FEATURE_OFF_FOR_SHOP = "✏️ <b>حالت ویرایش منوها</b>\n\nاین قابلیت فعلاً توسط مدیر سیستم خاموش است."
TEXT_FEATURE_OFF = "قابلیت ویرایش منوها خاموش است."
TEXT_SHOP_BOT_ONLY = "حالت ویرایش فروشگاه فقط داخل ربات فروشگاه کار می‌کند."
TEXT_LABEL_SAVED = "✅ متن دکمه ذخیره شد."
TEXT_MENU_CHANGED = "این منو تغییر کرده؛ دوباره باز کنید."


class EditorStates(StatesGroup):
    owner_label = State()
    shop_label = State()


@dataclass(frozen=True, slots=True)
class EditRequest:
    audience: str
    view: str
    screen_id: str = ""
    index: int = -1
    code: str = ""


def entry_button(*, for_reseller: bool) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=BTN_ENTRY, callback_data=f"{EDIT_CALLBACK_ROOT}:{'r' if for_reseller else 'a'}:h")


def parse_request(data: str | None) -> EditRequest | None:
    parts = (data or "").split(":")
    if len(parts) < 3 or parts[0] != EDIT_CALLBACK_ROOT or parts[1] not in _SETTINGS_BACK:
        return None
    audience, view, rest = parts[1], parts[2], parts[3:]
    try:
        if view in {"h", "f1", "f0", "m1", "m0"} and not rest:
            return EditRequest(audience, view)
        if view == "o" and len(rest) == 1 and rest[0] in SCREENS:
            return EditRequest(audience, view, screen_id=rest[0])
        if view in {"b", "t"} and len(rest) == 2 and rest[0] in SCREENS:
            return EditRequest(audience, view, screen_id=rest[0], index=int(rest[1]))
        if view == "c" and len(rest) == 3 and rest[0] in SCREENS:
            return EditRequest(audience, view, screen_id=rest[0], index=int(rest[1]), code=rest[2])
    except ValueError:
        return None
    return None


def _cb(actor: EditorActor, *parts: object) -> str:
    return ":".join([EDIT_CALLBACK_ROOT, audience_code(actor), *map(str, parts)])


def _button(text: str, data: str, *, style: str | None = None) -> InlineKeyboardButton:
    if style:
        return InlineKeyboardButton(text=text, callback_data=data, style=style)
    return InlineKeyboardButton(text=text, callback_data=data)


def _swatch(color: str) -> str:
    return f"{COLOR_SWATCHES.get(color, '⚪')} {COLOR_NAMES.get(color, color)}"


# ── Views ────────────────────────────────────────────────────────────────────


def switches_view(actor: EditorActor, *, feature_on: bool, minutes_left: int) -> tuple[str, InlineKeyboardMarkup]:
    rows: list[list[InlineKeyboardButton]] = []
    lines = ["✏️ <b>حالت ویرایش منوها</b>", ""]
    if not actor.for_reseller:
        state = "روشن ✅" if feature_on else "خاموش"
        lines.append(f"قابلیت برای همه: {state}")
        rows.append([_button(f"🔓 قابلیت ویرایش: {state}", _cb(actor, "f0" if feature_on else "f1"))])
    if feature_on:
        mine = f"روشن ({minutes_left} دقیقه)" if minutes_left else "خاموش"
        lines.append(f"حالت ویرایش شما: {mine}")
        lines.extend(["", f"وقتی روشن است، زیر هر منو «✏️ ویرایش این منو» می‌آید و بعد از {EDIT_MODE_MINUTES} دقیقه خاموش می‌شود."])
        rows.append([_button(f"✏️ حالت ویرایش من: {mine}", _cb(actor, "m0" if minutes_left else "m1"))])
        rows.append([_button(BTN_EDIT_MAIN_MENU, _cb(actor, "o", "c.main"))])
    rows.append([_button(BTN_BACK, _SETTINGS_BACK[audience_code(actor)])])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


def panel_view(
    actor: EditorActor, spec: ScreenSpec, buttons: list[ScreenButton], ui: dict[str, str]
) -> tuple[str, InlineKeyboardMarkup]:
    rows = [
        [_button(f"{_button_marker(actor, button, ui)} {button.text}", _cb(actor, "b", spec.id, index))]
        for index, button in enumerate(buttons)
        if _editable_parts(actor, button, ui) != (False, False)
    ]
    rows.append([_button(BTN_BACK_TO_MENU, spec.reopen_callback)])
    text = f"✏️ <b>ویرایش: {html.escape(spec.title)}</b>\nروی دکمه‌ای بزنید تا متن یا رنگش را عوض کنید."
    if len(rows) == 1:
        text = f"✏️ <b>ویرایش: {html.escape(spec.title)}</b>\nدر این منو چیزی برای ویرایش شما نیست."
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


def button_view(
    actor: EditorActor, spec: ScreenSpec, index: int, button: ScreenButton, ui: dict[str, str]
) -> tuple[str, InlineKeyboardMarkup]:
    label_ok, color_ok = _editable_parts(actor, button, ui)
    lines = [f"✏️ <b>{html.escape(spec.title)}</b> › {html.escape(button.text)}", ""]
    rows: list[list[InlineKeyboardButton]] = []
    if label_ok:
        rows.append([_button(BTN_EDIT_TEXT, _cb(actor, "t", spec.id, index))])
    if color_ok:
        item = find_color_item(ui, button.style_id, for_reseller=actor.for_reseller)
        lines.append(f"رنگ فعلی: {_swatch(item.color)} · پیش‌فرض: {_swatch(item.default)}")
        shared = shared_button_count(item.style_id)
        if shared > 1:
            lines.append(f"⚠️ این رنگ بین {shared} دکمه مشترک است و همه با هم عوض می‌شوند.")
        rows.extend(_color_rows(actor, spec.id, index, item))
    if not label_ok:
        lines.append("متن این دکمه از اینجا قابل ویرایش نیست.")
    rows.append([_button(BTN_BACK, _cb(actor, "o", spec.id))])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


def _color_rows(actor: EditorActor, screen_id: str, index: int, item: ColorItem) -> list[list[InlineKeyboardButton]]:
    buttons = [
        _button(f"{'✓ ' if color == item.color else ''}{_swatch(color)}", _cb(actor, "c", screen_id, index, code), style=color or None)
        for code, color in _CODE_TO_COLOR.items()
    ]
    return [buttons[0:2], buttons[2:4], [_button(BTN_RESET, _cb(actor, "c", screen_id, index, _RESET_CODE))]]


def _editable_parts(actor: EditorActor, button: ScreenButton, ui: dict[str, str]) -> tuple[bool, bool]:
    label_ok = can_edit_label(actor, button.label_key)
    color_ok = False
    if button.style_id:
        try:
            find_color_item(ui, button.style_id, for_reseller=actor.for_reseller)
            color_ok = True
        except ValueError:
            color_ok = False
    return label_ok, color_ok


def _button_marker(actor: EditorActor, button: ScreenButton, ui: dict[str, str]) -> str:
    _label_ok, color_ok = _editable_parts(actor, button, ui)
    if not color_ok:
        return "✏️"
    return COLOR_SWATCHES.get(find_color_item(ui, button.style_id, for_reseller=actor.for_reseller).color, "⚪")


# ── Shared handling ──────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class _Screen:
    spec: ScreenSpec
    buttons: list[ScreenButton]
    ui: dict[str, str]


async def _load_screen(session: AsyncSession, actor: EditorActor, screen_id: str) -> _Screen:
    spec = SCREENS.get(screen_id)
    if spec is None or spec.audience.value not in actor.audiences:
        raise ValueError(feedback.INVALID)
    ui = await get_all_settings(session, reseller_id=actor.settings_scope)
    profile = await get_reseller_profile(session, actor.shop_id) if actor.for_reseller else None
    return _Screen(spec, screen_buttons(screen_id, ScreenContext(ui=ui, profile=profile)), ui)


def _button_at(screen: _Screen, index: int) -> ScreenButton:
    if not 0 <= index < len(screen.buttons):
        raise ValueError(TEXT_MENU_CHANGED)
    return screen.buttons[index]


async def _show(callback: CallbackQuery, view: tuple[str, InlineKeyboardMarkup]) -> None:
    text, markup = view
    await safe_edit_text(callback.message, text, reply_markup=markup)


async def _switches(callback: CallbackQuery, session: AsyncSession, actor: EditorActor, request: EditRequest) -> None:
    if request.view in {"f1", "f0"}:
        if actor.for_reseller:
            raise ValueError(feedback.INVALID)
        await set_editor_enabled(session, request.view == "f1")
    feature_on = await is_editor_enabled(session)
    if request.view == "m1":
        if not feature_on:
            raise ValueError(TEXT_FEATURE_OFF)
        edit_mode_store.activate(actor)
    elif request.view == "m0" or not feature_on:
        edit_mode_store.deactivate(actor)
    await callback.answer()
    if actor.for_reseller and not feature_on:
        rows = [[_button(BTN_BACK, _SETTINGS_BACK["r"])]]
        await _show(callback, (TEXT_FEATURE_OFF_FOR_SHOP, InlineKeyboardMarkup(inline_keyboard=rows)))
        return
    await _show(callback, switches_view(actor, feature_on=feature_on, minutes_left=edit_mode_store.minutes_left(actor)))


async def _screen_views(
    callback: CallbackQuery, session: AsyncSession, actor: EditorActor, request: EditRequest, state: FSMContext
) -> None:
    if not await is_editor_enabled(session):
        raise ValueError(TEXT_FEATURE_OFF)
    screen = await _load_screen(session, actor, request.screen_id)
    if request.view == "o":
        await callback.answer()
        await _show(callback, panel_view(actor, screen.spec, screen.buttons, screen.ui))
        return
    button = _button_at(screen, request.index)
    if request.view == "t":
        await _ask_label(callback, actor, screen, request.index, button, state)
        return
    if request.view == "c":
        screen = await _save_color(session, actor, screen, button, request.code)
        button = _button_at(screen, request.index)
        await callback.answer(feedback.COLOR_SAVED)
    else:
        await callback.answer()
    await _show(callback, button_view(actor, screen.spec, request.index, button, screen.ui))


async def _save_color(
    session: AsyncSession, actor: EditorActor, screen: _Screen, button: ScreenButton, code: str
) -> _Screen:
    if not _editable_parts(actor, button, screen.ui)[1]:
        raise ValueError("رنگ این دکمه قابل ویرایش نیست.")
    if code == _RESET_CODE:
        await reset_button_color(session, style_id=button.style_id, for_reseller=actor.for_reseller, shop_id=actor.shop_id)
    elif code in _CODE_TO_COLOR:
        await set_button_color(
            session, style_id=button.style_id, color=_CODE_TO_COLOR[code], for_reseller=actor.for_reseller, shop_id=actor.shop_id
        )
    else:
        raise ValueError(feedback.INVALID)
    return await _load_screen(session, actor, screen.spec.id)


async def _ask_label(
    callback: CallbackQuery, actor: EditorActor, screen: _Screen, index: int, button: ScreenButton, state: FSMContext
) -> None:
    if not can_edit_label(actor, button.label_key):
        raise ValueError("متن این دکمه قابل ویرایش نیست.")
    await state.set_state(EditorStates.shop_label if actor.for_reseller else EditorStates.owner_label)
    await state.update_data(ed_screen=screen.spec.id, ed_index=index, ed_key=button.label_key)
    await callback.answer()
    prompt = (
        f"✏️ متن جدید دکمهٔ «{html.escape(button.text)}» را بفرستید.\n"
        f"یک خط، حداکثر {LABEL_MAX_LENGTH} کاراکتر.\n"
        "برای انصراف: انصراف"
    )
    rows = [[_button(BTN_BACK, _cb(actor, "b", screen.spec.id, index))]]
    await _show(callback, (prompt, InlineKeyboardMarkup(inline_keyboard=rows)))


async def _handle(
    callback: CallbackQuery, session: AsyncSession, actor: EditorActor, request: EditRequest, state: FSMContext
) -> None:
    try:
        if request.view in {"h", "f1", "f0", "m1", "m0"}:
            await _switches(callback, session, actor, request)
        else:
            await _screen_views(callback, session, actor, request, state)
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)


async def _save_label_message(message: Message, state: FSMContext, session: AsyncSession, actor: EditorActor) -> None:
    data = await state.get_data()
    screen_id, index, key = data.get("ed_screen"), data.get("ed_index"), data.get("ed_key")
    raw = message.text or ""
    if kb.is_cancel_text(raw.strip()) or not screen_id:
        await state.set_state(None)
        await message.answer(feedback.CANCELLED, reply_markup=_after_label_markup(actor, screen_id))
        return
    try:
        screen = await _load_screen(session, actor, screen_id)
        button = _button_at(screen, int(index))
        if button.label_key != key:
            raise ValueError(TEXT_MENU_CHANGED)
        label = validate_button_label(
            raw,
            other_labels=[b.text.strip() for i, b in enumerate(screen.buttons) if i != int(index)],
            reserved=[*_CANCEL_WORDS, kb._home_label(screen.ui), kb._back_label(screen.ui)],
        )
        stored = pack_setting_from_message(key, message) if message.entities and label == raw.strip() else label
        await save_button_label(session, actor, label_key=key, stored_value=stored)
    except ValueError as exc:
        await message.answer(str(exc))
        return
    await state.set_state(None)
    await message.answer(TEXT_LABEL_SAVED, reply_markup=_after_label_markup(actor, screen_id))


def _after_label_markup(actor: EditorActor, screen_id: str | None) -> InlineKeyboardMarkup | None:
    spec = SCREENS.get(screen_id or "")
    if spec is None:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[[_button(BTN_BACK_TO_MENU, spec.reopen_callback), _button(BTN_CONTINUE, _cb(actor, "o", spec.id))]]
    )


# ── Routers ──────────────────────────────────────────────────────────────────


@owner_router.callback_query(F.data.startswith(f"{EDIT_CALLBACK_ROOT}:a:"))
async def owner_editor(callback: CallbackQuery, session: AsyncSession, db_user: BotUser, state: FSMContext) -> None:
    # The owner-principal middleware on this router already admitted the actor.
    request = parse_request(callback.data)
    if request is None:
        await callback.answer(feedback.INVALID, show_alert=True)
        return
    await _handle(callback, session, EditorActor(user_id=int(db_user.id), shop_id=None), request, state)


@owner_router.message(EditorStates.owner_label)
async def owner_label_text(message: Message, state: FSMContext, session: AsyncSession, db_user: BotUser) -> None:
    await _save_label_message(message, state, session, EditorActor(user_id=int(db_user.id), shop_id=None))


async def _shop_actor(
    session: AsyncSession, db_user: BotUser, *, is_reseller_bot: bool, reseller_owner_id: int | None
) -> EditorActor | None:
    if not is_reseller_bot:
        return None
    shop_id = await shop_settings_shop_id(
        session, db_user, is_reseller_bot=is_reseller_bot, reseller_owner_id=reseller_owner_id
    )
    return EditorActor(user_id=int(db_user.id), shop_id=shop_id) if shop_id else None


@shop_router.callback_query(F.data.startswith(f"{EDIT_CALLBACK_ROOT}:r:"))
async def shop_editor(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: BotUser,
    state: FSMContext,
    is_reseller_bot: bool = False,
    reseller_owner_id: int | None = None,
) -> None:
    request = parse_request(callback.data)
    if request is None:
        await callback.answer(feedback.INVALID, show_alert=True)
        return
    actor = await _shop_actor(session, db_user, is_reseller_bot=is_reseller_bot, reseller_owner_id=reseller_owner_id)
    if actor is None:
        text = TEXT_SHOP_BOT_ONLY if not is_reseller_bot else feedback.NO_SHOP_SETTINGS_ACCESS
        await callback.answer(text, show_alert=True)
        return
    await _handle(callback, session, actor, request, state)


@shop_router.message(EditorStates.shop_label)
async def shop_label_text(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    db_user: BotUser,
    is_reseller_bot: bool = False,
    reseller_owner_id: int | None = None,
) -> None:
    actor = await _shop_actor(session, db_user, is_reseller_bot=is_reseller_bot, reseller_owner_id=reseller_owner_id)
    if actor is None:
        await state.set_state(None)
        await message.answer(feedback.NO_SHOP_SETTINGS_ACCESS)
        return
    await _save_label_message(message, state, session, actor)
