"""Admin settings hub — mirror web panel settings inside Telegram."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards as kb
from app.config import get_settings
from app.db.models import BotUser, Plan, Role
from app.services.notifications import NOTIFY_PREFS
from app.services.pasarguard import get_pg
from app.services.support_contacts import (
    delete_support_contact,
    get_support_contacts,
    support_chat_url,
    upsert_support_contact,
)
from app.services.users import (
    SETTING_GROUPS,
    TAB_SETTING_GROUPS,
    get_all_settings,
    get_setting,
    on,
    set_setting,
)

router = Router(name="admin_settings")

# Tabs editable from bot (skip ops-heavy / sensitive)
BOT_SETTINGS_TABS: list[tuple[str, str, str]] = [
    ("welcome", "🏠 خوش‌آمد", "نام فروشگاه و پیام استارت"),
    ("messages", "📝 متن پیام‌ها", "راهنما، FAQ، تحویل و …"),
    ("buttons", "🔘 متن دکمه‌ها", "برچسب دکمه‌های منو"),
    ("menu", "📋 منوی بات", "نمایش آیتم‌ها و چیدمان"),
    ("qr", "📱 QR اشتراک", "ارسال و کپشن QR"),
    ("payment", "💳 پرداخت", "روش‌ها، کارت، درگاه، رمزارز، استارز"),
    ("supports", "🎧 پشتیبان‌ها", "لیست پشتیبان‌های تلگرام"),
    ("naming", "🏷 نام‌گذاری", "پیشوند/پسوند یوزرنیم پاسارگارد"),
    ("forcejoin", "📣 کانال اجباری", "عضویت اجباری"),
    ("notifications", "🔔 نوتیفیکیشن", "اعلان‌های ادمین"),
    ("plancfg", "✨ پلن تست/دلخواه", "کانفیگ تست و قیمت پلن دلخواه"),
]

# Extra fields for custom plan pricing (managed on /plans in web)
CUSTOM_PLAN_FIELDS: list[tuple[str, str, str]] = [
    ("custom_plan_price_per_gb", "قیمت هر گیگ", "number"),
    ("custom_plan_price_per_day", "قیمت هر روز", "number"),
    ("custom_plan_min_gb", "حداقل گیگ", "number"),
    ("custom_plan_max_gb", "حداکثر گیگ", "number"),
    ("custom_plan_min_days", "حداقل روز", "number"),
    ("custom_plan_max_days", "حداکثر روز", "number"),
]


class SettingsStates(StatesGroup):
    edit_value = State()
    support_title = State()
    support_telegram = State()
    trial_name = State()
    trial_days = State()
    trial_gb = State()


def _is_admin(user: BotUser) -> bool:
    return user.role == Role.ADMIN.value or user.telegram_id in get_settings().admin_ids


def _field_map() -> dict[str, tuple]:
    """key -> field tuple from SETTING_GROUPS."""
    out: dict[str, tuple] = {}
    for fields in SETTING_GROUPS.values():
        for item in fields:
            out[item[0]] = item
    for item in CUSTOM_PLAN_FIELDS:
        out[item[0]] = item
    return out


FIELD_MAP = _field_map()


def _preview(value: str | None, *, limit: int = 40) -> str:
    text = (value or "").replace("\n", " ").strip()
    if not text:
        return "—"
    if len(text) > limit:
        return text[: limit - 1] + "…"
    return text


def _hub_keyboard() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for tab_id, title, _ in BOT_SETTINGS_TABS:
        row.append(InlineKeyboardButton(text=title, callback_data=f"adm:st:tab:{tab_id}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append(
        [InlineKeyboardButton(text="ℹ️ ربات/آپدیت (فقط وب)", callback_data="adm:st:webonly")]
    )
    rows.append([InlineKeyboardButton(text="⬅️ بازگشت", callback_data="adm:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _render_hub(callback: CallbackQuery) -> None:
    lines = [
        "⚙️ <b>تنظیمات بات</b>",
        "",
        "همان تنظیمات وب‌پنل — از دسته‌بندی زیر انتخاب کنید:",
    ]
    for _, title, help_text in BOT_SETTINGS_TABS:
        lines.append(f"• {title} — <i>{help_text}</i>")
    if callback.message:
        await callback.message.edit_text("\n".join(lines), reply_markup=_hub_keyboard())


def _fields_for_tab(tab: str) -> list[tuple]:
    names = TAB_SETTING_GROUPS.get(tab) or []
    fields: list[tuple] = []
    for name in names:
        fields.extend(SETTING_GROUPS.get(name, []))
    return fields


def _value_label(kind: str, value: str | None) -> str:
    if kind == "toggle":
        return "✅" if on(value) else "⬜️"
    return _preview(value, limit=28)


async def _tab_keyboard(session: AsyncSession, tab: str) -> InlineKeyboardMarkup:
    ui = await get_all_settings(session)
    rows: list[list[InlineKeyboardButton]] = []

    if tab == "supports":
        contacts = await get_support_contacts(session)
        rows.append([InlineKeyboardButton(text="➕ افزودن پشتیبان", callback_data="adm:st:sup:add")])
        for c in contacts[:15]:
            mark = "✅" if c.get("enabled", True) else "⏸"
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"{mark} {c['title']}"[:60],
                        callback_data=f"adm:st:sup:v:{c['id']}",
                    )
                ]
            )
    elif tab == "notifications":
        for key, title, _, default in NOTIFY_PREFS:
            val = ui.get(key, default)
            mark = "✅" if on(val) else "⬜️"
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"{mark} {title}"[:60],
                        callback_data=f"adm:st:tog:{key}",
                    )
                ]
            )
    elif tab == "menu":
        layout = ui.get("menu_layout") or "classic"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"چیدمان: {'فشرده' if layout == 'compact' else 'کلاسیک'}",
                    callback_data="adm:st:menu:layout",
                )
            ]
        )
        for key, label in [
            ("show_wallet", "کیف پول"),
            ("show_support", "پشتیبانی"),
            ("show_guide", "راهنما"),
            ("show_faq", "سوالات"),
            ("show_referral", "دعوت"),
            ("show_miniapp", "مینی‌اپ"),
        ]:
            mark = "✅" if on(ui.get(key)) else "⬜️"
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"{mark} {label}",
                        callback_data=f"adm:st:tog:{key}",
                    )
                ]
            )
        # order controls
        order = [p for p in (ui.get("menu_order") or "").split(",") if p.strip()]
        rows.append(
            [InlineKeyboardButton(text="↕️ ترتیب منو:", callback_data="adm:st:noop")]
        )
        for i, key in enumerate(order[:10]):
            rows.append(
                [
                    InlineKeyboardButton(text=f"{i + 1}. {key}", callback_data="adm:st:noop"),
                    InlineKeyboardButton(text="⬆️", callback_data=f"adm:st:menu:up:{i}"),
                    InlineKeyboardButton(text="⬇️", callback_data=f"adm:st:menu:dn:{i}"),
                ]
            )
    elif tab == "plancfg":
        trial_on = on(ui.get("trial_enabled"))
        custom_on = on(ui.get("custom_plan_enabled"))
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{'✅' if trial_on else '⬜️'} نمایش پلن تست",
                    callback_data="adm:st:tog:trial_enabled",
                )
            ]
        )
        rows.append(
            [InlineKeyboardButton(text="🧪 ویرایش پلن تست", callback_data="adm:st:trial")]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{'✅' if custom_on else '⬜️'} پلن دلخواه",
                    callback_data="adm:st:tog:custom_plan_enabled",
                )
            ]
        )
        for key, label, _kind in CUSTOM_PLAN_FIELDS:
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"✏️ {label}: {_preview(ui.get(key), limit=12)}",
                        callback_data=f"adm:st:edit:{key}",
                    )
                ]
            )
        rows.append(
            [
                InlineKeyboardButton(
                    text="🔗 اتصال پاسارگارد پلن دلخواه",
                    callback_data="adm:custom",
                )
            ]
        )
    else:
        # group fields; skip image kinds
        current_group = None
        for item in _fields_for_tab(tab):
            key, label, kind = item[0], item[1], item[2]
            if kind == "image":
                rows.append(
                    [
                        InlineKeyboardButton(
                            text=f"🖼 {label} (فقط وب)",
                            callback_data="adm:st:webonly",
                        )
                    ]
                )
                continue
            # find group name for section headers
            for gname, gfields in SETTING_GROUPS.items():
                if any(f[0] == key for f in gfields):
                    if gname != current_group and tab == "payment":
                        current_group = gname
                        rows.append(
                            [
                                InlineKeyboardButton(
                                    text=f"— {gname} —",
                                    callback_data="adm:st:noop",
                                )
                            ]
                        )
                    break
            if kind == "toggle":
                mark = _value_label(kind, ui.get(key))
                rows.append(
                    [
                        InlineKeyboardButton(
                            text=f"{mark} {label}"[:60],
                            callback_data=f"adm:st:tog:{key}",
                        )
                    ]
                )
            elif kind == "select":
                options = item[4] if len(item) > 4 else []
                cur = ui.get(key) or ""
                cur_label = next((lb for ov, lb in options if ov == cur), cur or "—")
                rows.append(
                    [
                        InlineKeyboardButton(
                            text=f"↕️ {label}: {_preview(cur_label, limit=20)}",
                            callback_data=f"adm:st:sel:{key}",
                        )
                    ]
                )
            else:
                rows.append(
                    [
                        InlineKeyboardButton(
                            text=f"✏️ {label}: {_value_label(kind, ui.get(key))}"[:60],
                            callback_data=f"adm:st:edit:{key}",
                        )
                    ]
                )

    rows.append([InlineKeyboardButton(text="⬅️ دسته‌ها", callback_data="adm:settings")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _render_tab(callback: CallbackQuery, session: AsyncSession, tab: str) -> None:
    title = next((t[1] for t in BOT_SETTINGS_TABS if t[0] == tab), tab)
    help_text = next((t[2] for t in BOT_SETTINGS_TABS if t[0] == tab), "")
    text = f"{title}\n<i>{help_text}</i>\n\nروی هر مورد بزنید تا تغییر دهید."
    if callback.message:
        await callback.message.edit_text(
            text, reply_markup=await _tab_keyboard(session, tab)
        )


@router.callback_query(F.data == "adm:st:noop")
async def settings_noop(callback: CallbackQuery):
    await callback.answer()


@router.callback_query(F.data == "adm:settings")
async def settings_hub(callback: CallbackQuery, state: FSMContext, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    await state.clear()
    await callback.answer()
    await _render_hub(callback)


@router.callback_query(F.data == "adm:st:webonly")
async def settings_webonly(callback: CallbackQuery, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    await callback.answer(
        "آپلود عکس، توکن ربات، اتصال پاسارگارد و آپدیت پنل فقط از وب‌پنل قابل تغییرند.",
        show_alert=True,
    )


@router.callback_query(F.data.startswith("adm:st:tab:"))
async def settings_tab(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    tab = callback.data.split(":")[-1]
    await callback.answer()
    await _render_tab(callback, session, tab)


@router.callback_query(F.data.startswith("adm:st:tog:"))
async def settings_toggle(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    key = callback.data.split(":", 3)[-1]
    cur = await get_setting(session, key)
    new_val = "0" if on(cur) else "1"
    await set_setting(session, key, new_val)
    if key == "trial_enabled":
        trial = (
            await session.execute(select(Plan).where(Plan.is_trial.is_(True)))
        ).scalar_one_or_none()
        if trial:
            trial.is_active = new_val == "1"
            await session.commit()
    await callback.answer("بروز شد")
    tab = _tab_for_key(key)
    if tab:
        await _render_tab(callback, session, tab)
    else:
        await _render_hub(callback)


def _tab_for_key(key: str) -> str | None:
    if key == "trial_enabled" or key.startswith("custom_plan_"):
        return "plancfg"
    if key.startswith("notify_"):
        return "notifications"
    if key.startswith("show_") or key in {"menu_layout", "menu_order"}:
        return "menu"
    for tab, groups in TAB_SETTING_GROUPS.items():
        for gname in groups:
            for item in SETTING_GROUPS.get(gname, []):
                if item[0] == key:
                    return tab
    return None


@router.callback_query(F.data.startswith("adm:st:edit:"))
async def settings_edit_ask(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, db_user: BotUser
):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    key = callback.data.split(":", 3)[-1]
    meta = FIELD_MAP.get(key)
    label = meta[1] if meta else key
    kind = meta[2] if meta else "text"
    cur = await get_setting(session, key)
    await callback.answer()
    await state.set_state(SettingsStates.edit_value)
    await state.update_data(edit_key=key, edit_tab=_tab_for_key(key) or "welcome")
    hint = "عدد بفرستید." if kind == "number" else "متن جدید را بفرستید (یا انصراف)."
    if callback.message:
        await callback.message.answer(
            f"✏️ <b>{label}</b>\nمقدار فعلی:\n<code>{_preview(cur, limit=200)}</code>\n\n{hint}",
            reply_markup=kb.cancel_reply(),
        )


@router.message(SettingsStates.edit_value)
async def settings_edit_save(message: Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    key = data.get("edit_key")
    tab = data.get("edit_tab") or "welcome"
    text = (message.text or "").strip()
    if text == "انصراف" or not key:
        await state.clear()
        await message.answer("لغو شد.", reply_markup=kb.admin_home())
        return
    meta = FIELD_MAP.get(key)
    kind = meta[2] if meta else "text"
    if kind == "number":
        try:
            float(text.replace(",", "").replace("٬", ""))
        except ValueError:
            await message.answer("عدد معتبر بفرستید")
            return
        text = text.replace(",", "").replace("٬", "")
    await set_setting(session, key, text)
    await state.clear()
    await message.answer(f"ذخیره شد ✅\n<code>{key}</code>", reply_markup=kb.admin_home())
    # also offer jump back
    await message.answer(
        "بازگشت به دسته:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📂 همان دسته", callback_data=f"adm:st:tab:{tab}")],
                [InlineKeyboardButton(text="⚙️ تنظیمات", callback_data="adm:settings")],
            ]
        ),
    )


@router.callback_query(F.data.startswith("adm:st:sel:"))
async def settings_select_menu(
    callback: CallbackQuery, session: AsyncSession, db_user: BotUser
):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    key = callback.data.split(":", 3)[-1]
    meta = FIELD_MAP.get(key)
    if not meta or meta[2] != "select":
        await callback.answer("نامعتبر", show_alert=True)
        return
    options = meta[4] if len(meta) > 4 else []
    cur = await get_setting(session, key)
    rows = []
    for ov, olabel in options:
        mark = "✅ " if ov == cur else ""
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{mark}{olabel}"[:60],
                    callback_data=f"adm:st:setsel:{key}:{ov}",
                )
            ]
        )
    tab = _tab_for_key(key) or "menu"
    rows.append([InlineKeyboardButton(text="⬅️ بازگشت", callback_data=f"adm:st:tab:{tab}")])
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(
            f"انتخاب «{meta[1]}»:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )


@router.callback_query(F.data.startswith("adm:st:setsel:"))
async def settings_select_set(
    callback: CallbackQuery, session: AsyncSession, db_user: BotUser
):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    # adm:st:setsel:{key}:{value} — value may contain colon? use rsplit
    rest = callback.data[len("adm:st:setsel:") :]
    key, _, value = rest.partition(":")
    await set_setting(session, key, value)
    await callback.answer("ذخیره شد")
    tab = _tab_for_key(key) or "menu"
    await _render_tab(callback, session, tab)


@router.callback_query(F.data == "adm:st:menu:layout")
async def menu_layout_toggle(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    cur = await get_setting(session, "menu_layout") or "classic"
    await set_setting(session, "menu_layout", "compact" if cur == "classic" else "classic")
    await callback.answer("بروز شد")
    await _render_tab(callback, session, "menu")


@router.callback_query(
    F.data.startswith("adm:st:menu:up:") | F.data.startswith("adm:st:menu:dn:")
)
async def menu_reorder(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    parts = callback.data.split(":")
    direction = parts[3]  # up | dn
    idx = int(parts[4])
    raw = await get_setting(session, "menu_order")
    order = [p.strip() for p in (raw or "").split(",") if p.strip()]
    if idx < 0 or idx >= len(order):
        await callback.answer()
        return
    swap = idx - 1 if direction == "up" else idx + 1
    if swap < 0 or swap >= len(order):
        await callback.answer("انتهای لیست")
        return
    order[idx], order[swap] = order[swap], order[idx]
    await set_setting(session, "menu_order", ",".join(order))
    for key in ("wallet", "support", "guide", "faq", "referral", "miniapp", "services"):
        await set_setting(session, f"show_{key}", "1" if key in order else "0")
    await callback.answer("جابه‌جا شد")
    await _render_tab(callback, session, "menu")


# ----- Supports CRUD -----


@router.callback_query(F.data == "adm:st:sup:add")
async def support_add_start(callback: CallbackQuery, state: FSMContext, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    await callback.answer()
    await state.set_state(SettingsStates.support_title)
    await state.update_data(support_edit_id=None)
    if callback.message:
        await callback.message.answer(
            "عنوان پشتیبان را بفرستید (مثلاً پشتیبان ربات):",
            reply_markup=kb.cancel_reply(),
        )


@router.message(SettingsStates.support_title)
async def support_title_msg(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if text == "انصراف":
        await state.clear()
        await message.answer("لغو شد.", reply_markup=kb.admin_home())
        return
    await state.update_data(support_title=text)
    await state.set_state(SettingsStates.support_telegram)
    await message.answer("آیدی یا یوزرنیم تلگرام (@user یا عدد):")


@router.message(SettingsStates.support_telegram)
async def support_telegram_msg(message: Message, state: FSMContext, session: AsyncSession):
    text = (message.text or "").strip()
    if text == "انصراف":
        await state.clear()
        await message.answer("لغو شد.", reply_markup=kb.admin_home())
        return
    data = await state.get_data()
    await state.clear()
    item, err = await upsert_support_contact(
        session,
        contact_id=data.get("support_edit_id"),
        title=data.get("support_title") or "پشتیبان",
        telegram=text,
        enabled=True,
    )
    if err:
        await message.answer(f"❌ {err}", reply_markup=kb.admin_home())
        return
    await message.answer(
        f"ذخیره شد ✅ — {item['title']} ({item['telegram']})",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🎧 پشتیبان‌ها", callback_data="adm:st:tab:supports")],
                [InlineKeyboardButton(text="⚙️ تنظیمات", callback_data="adm:settings")],
            ]
        ),
    )


@router.callback_query(F.data.startswith("adm:st:sup:v:"))
async def support_view(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    cid = callback.data.split(":")[-1]
    contacts = await get_support_contacts(session)
    c = next((x for x in contacts if x["id"] == cid), None)
    if not c:
        await callback.answer("یافت نشد", show_alert=True)
        return
    await callback.answer()
    url = support_chat_url(c["telegram"]) or "—"
    text = (
        f"🎧 <b>{c['title']}</b>\n"
        f"تلگرام: <code>{c['telegram']}</code>\n"
        f"لینک: {url}\n"
        f"وضعیت: {'فعال' if c.get('enabled', True) else 'خاموش'}\n"
        f"ترتیب: {c.get('sort', 0)}"
    )
    rows = [
        [
            InlineKeyboardButton(
                text="⏸ خاموش" if c.get("enabled", True) else "▶️ روشن",
                callback_data=f"adm:st:sup:tog:{cid}",
            )
        ],
        [
            InlineKeyboardButton(text="✏️ ویرایش", callback_data=f"adm:st:sup:edit:{cid}"),
            InlineKeyboardButton(text="🗑 حذف", callback_data=f"adm:st:sup:del:{cid}"),
        ],
        [InlineKeyboardButton(text="⬅️ لیست", callback_data="adm:st:tab:supports")],
    ]
    if callback.message:
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("adm:st:sup:tog:"))
async def support_toggle(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    cid = callback.data.split(":")[-1]
    contacts = await get_support_contacts(session)
    c = next((x for x in contacts if x["id"] == cid), None)
    if not c:
        await callback.answer("یافت نشد", show_alert=True)
        return
    await upsert_support_contact(
        session,
        contact_id=cid,
        title=c["title"],
        telegram=c["telegram"],
        sort=int(c.get("sort") or 0),
        enabled=not c.get("enabled", True),
    )
    await callback.answer("بروز شد")
    contacts = await get_support_contacts(session)
    c = next((x for x in contacts if x["id"] == cid), None)
    if not c or not callback.message:
        return
    url = support_chat_url(c["telegram"]) or "—"
    text = (
        f"🎧 <b>{c['title']}</b>\n"
        f"تلگرام: <code>{c['telegram']}</code>\n"
        f"لینک: {url}\n"
        f"وضعیت: {'فعال' if c.get('enabled', True) else 'خاموش'}\n"
        f"ترتیب: {c.get('sort', 0)}"
    )
    rows = [
        [
            InlineKeyboardButton(
                text="⏸ خاموش" if c.get("enabled", True) else "▶️ روشن",
                callback_data=f"adm:st:sup:tog:{cid}",
            )
        ],
        [
            InlineKeyboardButton(text="✏️ ویرایش", callback_data=f"adm:st:sup:edit:{cid}"),
            InlineKeyboardButton(text="🗑 حذف", callback_data=f"adm:st:sup:del:{cid}"),
        ],
        [InlineKeyboardButton(text="⬅️ لیست", callback_data="adm:st:tab:supports")],
    ]
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data.startswith("adm:st:sup:edit:"))
async def support_edit_start(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, db_user: BotUser
):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    cid = callback.data.split(":")[-1]
    contacts = await get_support_contacts(session)
    c = next((x for x in contacts if x["id"] == cid), None)
    if not c:
        await callback.answer("یافت نشد", show_alert=True)
        return
    await callback.answer()
    await state.set_state(SettingsStates.support_title)
    await state.update_data(support_edit_id=cid)
    if callback.message:
        await callback.message.answer(
            f"عنوان جدید (فعلی: {c['title']}):",
            reply_markup=kb.cancel_reply(),
        )


@router.callback_query(F.data.startswith("adm:st:sup:del:"))
async def support_delete(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    cid = callback.data.split(":")[-1]
    await delete_support_contact(session, cid)
    await callback.answer("حذف شد")
    await _render_tab(callback, session, "supports")


# ----- Trial plan -----


@router.callback_query(F.data == "adm:st:trial")
async def trial_menu(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    result = await session.execute(select(Plan).where(Plan.is_trial.is_(True)))
    trial = result.scalar_one_or_none()
    ui = await get_all_settings(session)
    if trial:
        gb = f"{trial.data_limit_gb:g}گ" if trial.data_limit_gb is not None else "∞"
        link = (
            f"تمپلیت #{trial.pg_template_id}"
            if trial.pg_template_id
            else (f"گروه {trial.pg_group_ids}" if trial.pg_group_ids else "⚠️ بدون اتصال")
        )
        body = (
            f"نام: {trial.name}\n"
            f"مدت: {trial.duration_days} روز\n"
            f"حجم: {gb}\n"
            f"اتصال: {link}\n"
            f"نمایش: {'✅' if on(ui.get('trial_enabled')) else '⬜️'}"
        )
    else:
        body = "هنوز پلن تست ساخته نشده — از دکمه‌های زیر بسازید/ویرایش کنید."
    await callback.answer()
    rows = [
        [InlineKeyboardButton(text="✏️ نام", callback_data="adm:st:trial:name")],
        [InlineKeyboardButton(text="📅 مدت (روز)", callback_data="adm:st:trial:days")],
        [InlineKeyboardButton(text="📦 حجم (گیگ، 0=نامحدود)", callback_data="adm:st:trial:gb")],
        [
            InlineKeyboardButton(
                text="📋 تمپلیت پاسارگارد", callback_data="adm:st:trial:tpl"
            )
        ],
        [
            InlineKeyboardButton(
                text="📁 گروه پاسارگارد", callback_data="adm:st:trial:grp"
            )
        ],
        [InlineKeyboardButton(text="⬅️ بازگشت", callback_data="adm:st:tab:plancfg")],
    ]
    if callback.message:
        await callback.message.edit_text(
            f"🧪 <b>پلن تست</b>\n\n{body}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )


async def _ensure_trial(session: AsyncSession) -> Plan:
    result = await session.execute(select(Plan).where(Plan.is_trial.is_(True)))
    trial = result.scalar_one_or_none()
    if trial:
        return trial
    trial = Plan(
        name="تست رایگان",
        price=0,
        duration_days=1,
        data_limit_gb=1,
        is_trial=True,
        is_active=True,
        description="پلن تست رایگان",
    )
    session.add(trial)
    await session.commit()
    await session.refresh(trial)
    return trial


@router.callback_query(F.data == "adm:st:trial:name")
async def trial_ask_name(callback: CallbackQuery, state: FSMContext, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    await callback.answer()
    await state.set_state(SettingsStates.trial_name)
    if callback.message:
        await callback.message.answer("نام پلن تست:", reply_markup=kb.cancel_reply())


@router.message(SettingsStates.trial_name)
async def trial_save_name(message: Message, state: FSMContext, session: AsyncSession):
    text = (message.text or "").strip()
    if text == "انصراف":
        await state.clear()
        await message.answer("لغو شد.", reply_markup=kb.admin_home())
        return
    trial = await _ensure_trial(session)
    trial.name = text[:128]
    await session.commit()
    await state.clear()
    await message.answer(
        "ذخیره شد ✅",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🧪 پلن تست", callback_data="adm:st:trial")]
            ]
        ),
    )


@router.callback_query(F.data == "adm:st:trial:days")
async def trial_ask_days(callback: CallbackQuery, state: FSMContext, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    await callback.answer()
    await state.set_state(SettingsStates.trial_days)
    if callback.message:
        await callback.message.answer("مدت به روز:", reply_markup=kb.cancel_reply())


@router.message(SettingsStates.trial_days)
async def trial_save_days(message: Message, state: FSMContext, session: AsyncSession):
    text = (message.text or "").strip()
    if text == "انصراف":
        await state.clear()
        await message.answer("لغو شد.", reply_markup=kb.admin_home())
        return
    try:
        days = max(1, int(text))
    except ValueError:
        await message.answer("عدد معتبر")
        return
    trial = await _ensure_trial(session)
    trial.duration_days = days
    await session.commit()
    await state.clear()
    await message.answer(
        "ذخیره شد ✅",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🧪 پلن تست", callback_data="adm:st:trial")]
            ]
        ),
    )


@router.callback_query(F.data == "adm:st:trial:gb")
async def trial_ask_gb(callback: CallbackQuery, state: FSMContext, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    await callback.answer()
    await state.set_state(SettingsStates.trial_gb)
    if callback.message:
        await callback.message.answer(
            "حجم به گیگ (۰ = نامحدود):", reply_markup=kb.cancel_reply()
        )


@router.message(SettingsStates.trial_gb)
async def trial_save_gb(message: Message, state: FSMContext, session: AsyncSession):
    text = (message.text or "").strip()
    if text == "انصراف":
        await state.clear()
        await message.answer("لغو شد.", reply_markup=kb.admin_home())
        return
    try:
        gb = float(text)
    except ValueError:
        await message.answer("عدد معتبر")
        return
    trial = await _ensure_trial(session)
    trial.data_limit_gb = None if gb <= 0 else gb
    await session.commit()
    await state.clear()
    await message.answer(
        "ذخیره شد ✅",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🧪 پلن تست", callback_data="adm:st:trial")]
            ]
        ),
    )


@router.callback_query(F.data == "adm:st:trial:tpl")
async def trial_pick_tpl(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    await callback.answer()
    try:
        templates = await get_pg().get_user_templates_simple()
    except Exception:
        templates = []
    rows: list[list[InlineKeyboardButton]] = []
    for t in templates[:20]:
        tid = t.get("id")
        if tid is None:
            continue
        name = t.get("name") or f"تمپلیت {tid}"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"#{tid} — {name}"[:60],
                    callback_data=f"adm:st:trial:settpl:{tid}",
                )
            ]
        )
    if not rows:
        rows.append(
            [InlineKeyboardButton(text="تمپلیتی نیست", callback_data="adm:st:trial")]
        )
    rows.append([InlineKeyboardButton(text="⬅️ بازگشت", callback_data="adm:st:trial")])
    if callback.message:
        await callback.message.edit_text(
            "تمپلیت پلن تست را انتخاب کنید:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )


@router.callback_query(F.data.startswith("adm:st:trial:settpl:"))
async def trial_set_tpl(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    tid = int(callback.data.split(":")[-1])
    trial = await _ensure_trial(session)
    trial.pg_template_id = tid
    trial.pg_group_ids = None
    await session.commit()
    await callback.answer("ذخیره شد")
    # re-open trial menu without double-answer
    result = await session.execute(select(Plan).where(Plan.is_trial.is_(True)))
    trial = result.scalar_one_or_none()
    ui = await get_all_settings(session)
    gb = f"{trial.data_limit_gb:g}گ" if trial and trial.data_limit_gb is not None else "∞"
    link = (
        f"تمپلیت #{trial.pg_template_id}"
        if trial and trial.pg_template_id
        else (f"گروه {trial.pg_group_ids}" if trial and trial.pg_group_ids else "⚠️ بدون اتصال")
    )
    body = (
        f"نام: {trial.name}\nمدت: {trial.duration_days} روز\nحجم: {gb}\nاتصال: {link}\n"
        f"نمایش: {'✅' if on(ui.get('trial_enabled')) else '⬜️'}"
    )
    rows = [
        [InlineKeyboardButton(text="✏️ نام", callback_data="adm:st:trial:name")],
        [InlineKeyboardButton(text="📅 مدت (روز)", callback_data="adm:st:trial:days")],
        [InlineKeyboardButton(text="📦 حجم (گیگ، 0=نامحدود)", callback_data="adm:st:trial:gb")],
        [InlineKeyboardButton(text="📋 تمپلیت پاسارگارد", callback_data="adm:st:trial:tpl")],
        [InlineKeyboardButton(text="📁 گروه پاسارگارد", callback_data="adm:st:trial:grp")],
        [InlineKeyboardButton(text="⬅️ بازگشت", callback_data="adm:st:tab:plancfg")],
    ]
    if callback.message:
        await callback.message.edit_text(
            f"🧪 <b>پلن تست</b>\n\n{body}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )

@router.callback_query(F.data == "adm:st:trial:grp")
async def trial_pick_grp(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, db_user: BotUser
):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    trial = await _ensure_trial(session)
    selected: list[int] = []
    if trial.pg_group_ids:
        for part in str(trial.pg_group_ids).split(","):
            if part.strip().isdigit():
                selected.append(int(part.strip()))
    await state.update_data(trial_groups=selected)
    await callback.answer()
    await _show_trial_groups(callback, state)


async def _show_trial_groups(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    selected = [int(x) for x in (data.get("trial_groups") or [])]
    try:
        groups = await get_pg().get_groups_simple()
    except Exception:
        groups = []
    rows: list[list[InlineKeyboardButton]] = []
    for g in groups[:25]:
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
                    callback_data=f"adm:st:trial:toggrp:{gid}",
                )
            ]
        )
    if rows:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"✅ تأیید ({len(selected)})",
                    callback_data="adm:st:trial:grpdone",
                )
            ]
        )
    else:
        rows.append(
            [InlineKeyboardButton(text="گروهی نیست", callback_data="adm:st:trial")]
        )
    rows.append([InlineKeyboardButton(text="⬅️ بازگشت", callback_data="adm:st:trial")])
    if callback.message:
        await callback.message.edit_text(
            "گروه‌های پلن تست را انتخاب کنید:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )


@router.callback_query(F.data.startswith("adm:st:trial:toggrp:"))
async def trial_tog_grp(callback: CallbackQuery, state: FSMContext, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    gid = int(callback.data.split(":")[-1])
    data = await state.get_data()
    selected = [int(x) for x in (data.get("trial_groups") or [])]
    if gid in selected:
        selected = [x for x in selected if x != gid]
    else:
        selected.append(gid)
    await state.update_data(trial_groups=selected)
    await callback.answer()
    await _show_trial_groups(callback, state)


@router.callback_query(F.data == "adm:st:trial:grpdone")
async def trial_grp_done(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext, db_user: BotUser
):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    data = await state.get_data()
    selected = [int(x) for x in (data.get("trial_groups") or [])]
    if not selected:
        await callback.answer("حداقل یک گروه", show_alert=True)
        return
    trial = await _ensure_trial(session)
    trial.pg_group_ids = ",".join(str(x) for x in selected)
    trial.pg_template_id = None
    await session.commit()
    await state.update_data(trial_groups=[])
    await callback.answer("ذخیره شد")
    result = await session.execute(select(Plan).where(Plan.is_trial.is_(True)))
    trial = result.scalar_one_or_none()
    ui = await get_all_settings(session)
    gb = f"{trial.data_limit_gb:g}گ" if trial and trial.data_limit_gb is not None else "∞"
    link = (
        f"تمپلیت #{trial.pg_template_id}"
        if trial and trial.pg_template_id
        else (f"گروه {trial.pg_group_ids}" if trial and trial.pg_group_ids else "⚠️ بدون اتصال")
    )
    body = (
        f"نام: {trial.name}\nمدت: {trial.duration_days} روز\nحجم: {gb}\nاتصال: {link}\n"
        f"نمایش: {'✅' if on(ui.get('trial_enabled')) else '⬜️'}"
    )
    rows = [
        [InlineKeyboardButton(text="✏️ نام", callback_data="adm:st:trial:name")],
        [InlineKeyboardButton(text="📅 مدت (روز)", callback_data="adm:st:trial:days")],
        [InlineKeyboardButton(text="📦 حجم (گیگ، 0=نامحدود)", callback_data="adm:st:trial:gb")],
        [InlineKeyboardButton(text="📋 تمپلیت پاسارگارد", callback_data="adm:st:trial:tpl")],
        [InlineKeyboardButton(text="📁 گروه پاسارگارد", callback_data="adm:st:trial:grp")],
        [InlineKeyboardButton(text="⬅️ بازگشت", callback_data="adm:st:tab:plancfg")],
    ]
    if callback.message:
        await callback.message.edit_text(
            f"🧪 <b>پلن تست</b>\n\n{body}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )
