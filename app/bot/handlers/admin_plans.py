"""Platform admin — plans hub (parity with web /plans modal)."""

from __future__ import annotations

import html
import json

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, ReplyKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards as kb
from app.bot.auth import is_platform_admin as _is_admin
from app.bot.handlers.admin_settings import CUSTOM_PRICE
from app.config import get_settings
from app.db.models import BotUser, Plan, ResellerPlan
from app.services.formatting import format_toman
from app.services.orders import parse_wholesale_tiers, wholesale_description
from app.services.pasarguard import get_pg
from app.services.resellers import (
    DEFAULT_FEATURE_PERMS,
    FEATURE_PERMS,
    format_reseller_plan_apply_detail,
    list_reseller_plans,
    parse_perms,
    reseller_plan_mode_of,
)
from app.bot import menu_nav as nav
from app.services.users import get_all_settings, get_setting, on, set_setting

router = Router(name="admin_plans")

# Kind hub (reply keyboard step) — not the same-kind screen
BACK_USERS_KIND = "adm:plans:aud:users"
BACK_RESELLERS_KIND = "adm:plans:aud:resellers"
# Re-open a specific kind list/detail screen
BACK_USERS_FIXED_LIST = "adm:plans:kind:users:fixed"


class AdminPlansStates(StatesGroup):
    edit_value = State()
    res_plan_name = State()
    res_plan_price = State()
    res_plan_commission = State()
    res_plan_rate_gb = State()
    res_plan_edit_field = State()
    trial_name = State()
    trial_days = State()
    trial_gb = State()
    wholesale_tier_min = State()
    wholesale_tier_pct = State()


async def _plans_reply_markup(
    session: AsyncSession,
    state: FSMContext,
) -> ReplyKeyboardMarkup:
    data = await state.get_data()
    aud = data.get("_adm_plans_aud")
    ui = await get_all_settings(session)
    if aud in {"users", "resellers"}:
        return kb.admin_plans_kind_reply_keyboard(aud, ui)
    return kb.admin_plans_audience_reply_keyboard(ui)


async def sync_plans_reply_keyboard(
    message: Message,
    session: AsyncSession,
    db_user: BotUser,
    state: FSMContext,
    *,
    audience: str | None = None,
    add_type: bool = False,
) -> None:
    """Keep reply keyboard aligned after inline «back» on plans screens."""
    if add_type and audience in {"users", "resellers"}:
        await state.update_data(_adm_plans_aud=audience, _adm_plans_kind=None)
        await nav.set_nav_level(state, nav.NAV_ADMIN_PLANS_ADD_TYPE, push=False)
        level = nav.NAV_ADMIN_PLANS_ADD_TYPE
    elif audience in {"users", "resellers"}:
        await state.update_data(_adm_plans_aud=audience, _adm_plans_kind=None)
        await nav.set_nav_level(state, nav.NAV_ADMIN_PLANS_KIND, push=False)
        level = nav.NAV_ADMIN_PLANS_KIND
    else:
        await state.update_data(_adm_plans_aud=None, _adm_plans_kind=None)
        await nav.set_nav_level(state, nav.NAV_ADMIN_PLANS_AUDIENCE, push=False)
        level = nav.NAV_ADMIN_PLANS_AUDIENCE
    ui = await get_all_settings(session)
    if level == nav.NAV_ADMIN_PLANS_ADD_TYPE:
        aud = str((await state.get_data()).get("_adm_plans_aud") or "users")
        markup = kb.admin_plans_add_type_reply_keyboard(aud, ui)
    elif level == nav.NAV_ADMIN_PLANS_KIND:
        aud = str((await state.get_data()).get("_adm_plans_aud") or "users")
        markup = kb.admin_plans_kind_reply_keyboard(aud, ui)
    else:
        markup = kb.admin_plans_audience_reply_keyboard(ui)
    await message.answer("⬇️", reply_markup=markup)


async def _answer_plans_cancel(message: Message, state: FSMContext, session: AsyncSession) -> None:
    await state.set_state(None)
    markup = await _plans_reply_markup(session, state)
    await message.answer("لغو شد.", reply_markup=markup)


async def _answer_plans_saved(message: Message, state: FSMContext, session: AsyncSession, text: str) -> None:
    markup = await _plans_reply_markup(session, state)
    await message.answer(text, reply_markup=markup)


def _kb(rows: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _back_row(label: str, cb: str) -> list[InlineKeyboardButton]:
    return [InlineKeyboardButton(text=label, callback_data=cb)]


async def _ensure_trial(session: AsyncSession) -> Plan:
    trial = (
        await session.execute(select(Plan).where(Plan.is_trial.is_(True)))
    ).scalar_one_or_none()
    if trial:
        return trial
    trial = Plan(
        name="تست رایگان",
        price=0,
        duration_days=1,
        is_trial=True,
        is_active=False,
        description="پلن تست رایگان",
    )
    session.add(trial)
    await session.flush()
    await session.refresh(trial)
    return trial


async def send_audience_hub(
    message: Message,
    session: AsyncSession,
    *,
    edit: bool = False,
) -> None:
    text = "💎 <b>پلن‌ها</b>\nمخاطب را از کیبورد پایین انتخاب کنید:"
    if edit and message.text:
        try:
            await message.edit_text(text, reply_markup=None)
            return
        except Exception:
            pass
    await message.answer(text)


async def send_kind_hub(
    message: Message,
    session: AsyncSession,
    audience: str,
    *,
    edit: bool = False,
) -> None:
    title = "کاربران" if audience == "users" else "نمایندگان"
    text = f"💎 <b>پلن‌های {title}</b>\nنوع پلن را از کیبورد پایین انتخاب کنید:"
    if edit:
        try:
            await message.edit_text(text, reply_markup=None)
            return
        except Exception:
            pass
    await message.answer(text)


async def send_users_plans_overview(message: Message, session: AsyncSession) -> None:
    """User plans list — mirrors web /plans user table; plans inline, add on reply keyboard."""
    ui = await get_all_settings(session)
    result = await session.execute(select(Plan).order_by(Plan.sort_order, Plan.id))
    plans = list(result.scalars().all())
    fixed = [p for p in plans if not p.is_trial]
    text = (
        "👥 <b>پلن‌های کاربران</b>\n"
        "━━━━━━━━━━━━\n"
        f"پلن‌های ثابت: <b>{len(fixed)}</b>\n"
        "روی هر پلن بزنید تا ویرایش/حذف — «افزودن پلن» از کیبورد پایین."
    )
    await message.answer(
        text,
        reply_markup=kb.admin_users_plans_overview_keyboard(plans, ui),
    )


async def send_resellers_plans_overview(message: Message, session: AsyncSession) -> None:
    """Reseller subscription plans — all rows inline like web /plans."""
    all_plans = await list_reseller_plans(session)
    fixed = [p for p in all_plans if reseller_plan_mode_of(p) == "fixed"]
    payg = [p for p in all_plans if reseller_plan_mode_of(p) == "payg"]
    text = (
        "🤝 <b>پلن‌های نمایندگان</b>\n"
        "━━━━━━━━━━━━\n"
        f"ثابت (کمیسیون): <b>{len(fixed)}</b> · PAYG: <b>{len(payg)}</b>\n"
        "روی هر پلن بزنید — «افزودن پلن» از کیبورد پایین."
    )
    await message.answer(
        text,
        reply_markup=kb.admin_resellers_plans_overview_keyboard(fixed, payg),
    )


async def send_add_plan_type_picker(
    message: Message,
    session: AsyncSession,
    db_user: BotUser,
    state: FSMContext,
    audience: str,
) -> None:
    """Step after «افزودن پلن» — type picker like web modal kind step."""
    title = "کاربران" if audience == "users" else "نمایندگان"
    ui = await get_all_settings(session)
    await state.update_data(_adm_plans_aud=audience, _adm_plans_kind=None)
    await nav.set_nav_level(state, nav.NAV_ADMIN_PLANS_ADD_TYPE, push=True)
    markup = kb.admin_plans_add_type_reply_keyboard(audience, ui)
    await message.answer(
        f"➕ <b>افزودن پلن — {title}</b>\n"
        "نوع پلن را از کیبورد پایین یا دکمه‌های زیر انتخاب کنید:",
        reply_markup=markup,
    )
    await message.answer(
        "نوع پلن:",
        reply_markup=kb.admin_plans_add_type_keyboard(audience, ui),
    )


async def send_users_fixed_list(message: Message, session: AsyncSession) -> None:
    from app.bot.handlers.admin import _plan_line

    result = await session.execute(select(Plan).order_by(Plan.sort_order, Plan.id))
    plans = list(result.scalars().all())
    fixed = [p for p in plans if not p.is_trial]
    if not fixed:
        body = "هنوز پلن ثابتی ثبت نشده است."
    else:
        body = "\n\n".join(_plan_line(p) for p in fixed[:20])
    await message.answer(
        f"📦 <b>پلن‌های ثابت</b>\n\n{body}",
        reply_markup=kb.admin_plans_list_keyboard(
            plans,
            back_callback=BACK_USERS_KIND,
        ),
    )


async def _build_custom_screen(session: AsyncSession) -> tuple[str, InlineKeyboardMarkup]:
    ui = await get_all_settings(session)
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=f"{'✅' if on(ui.get('custom_plan_enabled')) else '⬜️'} فعال در فروشگاه",
                callback_data="adm:plans:tog:custom_plan_enabled",
            )
        ],
    ]
    for key, label, kind in CUSTOM_PRICE:
        if kind == "toggle":
            mark = "✅" if on(ui.get(key)) else "⬜️"
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"{mark} {label}",
                        callback_data=f"adm:plans:tog:{key}",
                    )
                ]
            )
        else:
            rows.append(
                [InlineKeyboardButton(text=label, callback_data=f"adm:plans:edit:{key}")]
            )
    rows.append(
        [InlineKeyboardButton(text="🔗 اتصال پاسارگارد", callback_data="adm:plans:custom:pg")]
    )
    rows.append(_back_row("⬅️ پلن‌های کاربران", BACK_USERS_KIND))
    tpl = (ui.get("custom_plan_template_id") or "").strip()
    groups = (ui.get("custom_plan_group_ids") or "").strip()
    link = f"تمپلیت #{tpl}" if tpl else (f"گروه {groups}" if groups else "بدون اتصال")
    text = (
        "✨ <b>پلن دلخواه</b>\n"
        f"فروش: {'فعال' if on(ui.get('custom_plan_enabled')) else 'خاموش'}\n"
        f"پاسارگارد: {link}"
    )
    return text, _kb(rows)


async def send_users_custom(message: Message, session: AsyncSession) -> None:
    text, markup = await _build_custom_screen(session)
    await message.answer(text, reply_markup=markup)


async def _build_trial_screen(session: AsyncSession) -> tuple[str, InlineKeyboardMarkup]:
    trial = (
        await session.execute(select(Plan).where(Plan.is_trial.is_(True)))
    ).scalar_one_or_none()
    ui = await get_all_settings(session)
    if trial:
        gb = (
            f"{trial.data_limit_gb:g} گیگ"
            if trial.data_limit_gb is not None
            else "نامحدود"
        )
        if trial.pg_template_id:
            link = f"تمپلیت #{trial.pg_template_id}"
        elif trial.pg_group_ids:
            link = f"گروه {trial.pg_group_ids}"
        else:
            link = "بدون اتصال"
        body = (
            f"نام: <b>{trial.name}</b>\n"
            f"مدت: {trial.duration_days} روز · حجم: {gb}\n"
            f"اتصال: {link}"
        )
    else:
        body = "هنوز ساخته نشده."
    rows = [
        [
            InlineKeyboardButton(
                text=f"{'✅' if on(ui.get('trial_enabled')) else '⬜️'} نمایش در فروشگاه",
                callback_data="adm:plans:tog:trial_enabled",
            )
        ],
        [InlineKeyboardButton(text="نام", callback_data="adm:plans:trial:name")],
        [InlineKeyboardButton(text="مدت (روز)", callback_data="adm:plans:trial:days")],
        [InlineKeyboardButton(text="حجم (گیگ)", callback_data="adm:plans:trial:gb")],
        [InlineKeyboardButton(text="تمپلیت پاسارگارد", callback_data="adm:plans:trial:tpl")],
        [InlineKeyboardButton(text="گروه پاسارگارد", callback_data="adm:plans:trial:grp")],
        _back_row("⬅️ پلن‌های کاربران", BACK_USERS_KIND),
    ]
    return f"🧪 <b>پلن تست</b>\n\n{body}", _kb(rows)


async def send_users_trial(message: Message, session: AsyncSession) -> None:
    text, markup = await _build_trial_screen(session)
    await message.answer(text, reply_markup=markup)


async def _build_wholesale_screen(session: AsyncSession) -> tuple[str, InlineKeyboardMarkup]:
    ui = await get_all_settings(session)
    tiers = parse_wholesale_tiers(ui.get("wholesale_tiers"))
    tier_lines = (
        "\n".join(f"از {t['min']} عدد → {t['percent']}٪" for t in tiers)
        if tiers
        else "پله‌ای تعریف نشده"
    )
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=f"{'✅' if on(ui.get('wholesale_enabled')) else '⬜️'} فعال در فروشگاه",
                callback_data="adm:plans:tog:wholesale_enabled",
            )
        ],
        [
            InlineKeyboardButton(
                text="حداقل تعداد",
                callback_data="adm:plans:edit:wholesale_min_qty",
            )
        ],
        [
            InlineKeyboardButton(
                text="حداکثر تعداد",
                callback_data="adm:plans:edit:wholesale_max_qty",
            )
        ],
        [
            InlineKeyboardButton(
                text="متن دکمه ربات",
                callback_data="adm:plans:edit:btn_wholesale",
            )
        ],
        [InlineKeyboardButton(text="➕ پله تخفیف", callback_data="adm:plans:wholesale:add_tier")],
    ]
    for i, t in enumerate(tiers[:6]):
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"🗑 پله {t['min']}→{t['percent']}٪",
                    callback_data=f"adm:plans:wholesale:del:{i}",
                )
            ]
        )
    rows.append(_back_row("⬅️ پلن‌های کاربران", BACK_USERS_KIND))
    text = (
        "📦 <b>فروش عمده</b>\n"
        f"{wholesale_description(ui)}\n\n"
        f"<b>پله‌ها:</b>\n{tier_lines}"
    )
    return text, _kb(rows)


async def send_users_wholesale(message: Message, session: AsyncSession) -> None:
    text, markup = await _build_wholesale_screen(session)
    await message.answer(text, reply_markup=markup)


async def send_reseller_plans_list(
    message: Message,
    session: AsyncSession,
    kind: str,
) -> None:
    all_plans = await list_reseller_plans(session)
    plans = [p for p in all_plans if reseller_plan_mode_of(p) == kind]
    label = "Pay As You Go" if kind == "payg" else "ثابت (کمیسیون)"
    if not plans:
        body = "هنوز پلنی در این دسته نیست."
    else:
        cards = [
            format_reseller_plan_apply_detail(p, currency=get_settings().currency)
            for p in plans[:10]
        ]
        body = "\n\n".join(cards)
    await message.answer(
        f"🤝 <b>پلن‌های نماینده — {label}</b>\n\n{body}",
        reply_markup=kb.admin_reseller_plans_list_keyboard(
            plans,
            mode=kind,
            back_callback=BACK_RESELLERS_KIND,
            add_callback=f"adm:resplan:add:{kind}",
        ),
    )


async def open_kind_screen(
    message: Message,
    session: AsyncSession,
    audience: str,
    kind: str,
) -> None:
    if audience == "users" and kind == "fixed":
        await send_users_fixed_list(message, session)
    elif audience == "users" and kind == "custom":
        await send_users_custom(message, session)
    elif audience == "users" and kind == "trial":
        await send_users_trial(message, session)
    elif audience == "users" and kind == "wholesale":
        await send_users_wholesale(message, session)
    elif audience == "resellers" and kind in {"fixed", "payg"}:
        await send_reseller_plans_list(message, session, kind)
    else:
        await message.answer("نوع پلن نامعتبر است.")


async def open_add_kind_action(
    message: Message,
    session: AsyncSession,
    db_user: BotUser,
    state: FSMContext,
    audience: str,
    kind: str,
) -> None:
    """Route add-type selection — mirrors web modal submit for each kind."""
    from app.bot.handlers.admin import AdminStates

    await state.update_data(_adm_plans_aud=audience, _adm_plans_kind=kind)
    await nav.set_nav_level(state, nav.NAV_ADMIN_PLANS_KIND, push=False)
    ui = await get_all_settings(session)
    list_markup = kb.admin_plans_kind_reply_keyboard(audience, ui)
    if audience == "users" and kind == "fixed":
        await state.set_state(AdminStates.add_plan_name)
        await message.answer("➕ <b>پلن ثابت جدید</b>\nنام پلن را بفرستید:", reply_markup=kb.cancel_reply())
        await message.answer("⬇️", reply_markup=list_markup)
        return
    if audience == "resellers" and kind in {"fixed", "payg"}:
        label = "Pay As You Go" if kind == "payg" else "ثابت (کمیسیون)"
        await state.set_state(AdminPlansStates.res_plan_name)
        await state.update_data(res_plan_mode=kind)
        await message.answer(
            f"➕ <b>پلن {label}</b>\nنام پلن نمایندگی:",
            reply_markup=kb.cancel_reply(),
        )
        await message.answer("⬇️", reply_markup=list_markup)
        return
    # Settings-based kinds — open configure screen (same as web «تنظیم»)
    await message.answer("⬇️", reply_markup=list_markup)
    await open_kind_screen(message, session, audience, kind)


async def _rerender_plans_screen(
    callback: CallbackQuery,
    session: AsyncSession,
    aud: str,
    kind: str,
) -> None:
    if not callback.message:
        return
    if aud == "users" and kind == "custom":
        text, markup = await _build_custom_screen(session)
        await callback.message.edit_text(text, reply_markup=markup)
    elif aud == "users" and kind == "trial":
        text, markup = await _build_trial_screen(session)
        await callback.message.edit_text(text, reply_markup=markup)
    elif aud == "users" and kind == "wholesale":
        text, markup = await _build_wholesale_screen(session)
        await callback.message.edit_text(text, reply_markup=markup)
    elif aud == "users" and kind == "fixed":
        from app.bot.handlers.admin import _render_plans_list

        await _render_plans_list(callback, session)
    elif aud == "resellers" and kind in {"fixed", "payg"}:
        all_plans = await list_reseller_plans(session)
        plans = [p for p in all_plans if reseller_plan_mode_of(p) == kind]
        label = "Pay As You Go" if kind == "payg" else "ثابت (کمیسیون)"
        body = (
            "هنوز پلنی در این دسته نیست."
            if not plans
            else "\n\n".join(
                format_reseller_plan_apply_detail(p, currency=get_settings().currency)
                for p in plans[:10]
            )
        )
        await callback.message.edit_text(
            f"🤝 <b>پلن‌های نماینده — {label}</b>\n\n{body}",
            reply_markup=kb.admin_reseller_plans_list_keyboard(
                plans,
                mode=kind,
                back_callback=BACK_RESELLERS_KIND,
                add_callback=f"adm:resplan:add:{kind}",
            ),
        )


@router.callback_query(F.data == "adm:plans:noop")
async def plans_noop(callback: CallbackQuery, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    await callback.answer("از کیبورد «افزودن پلن» استفاده کنید", show_alert=True)


@router.callback_query(F.data.startswith("adm:plans:add:"))
async def plans_add_kind_cb(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: BotUser,
    state: FSMContext,
):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    parts = callback.data.split(":")
    if len(parts) < 5:
        await callback.answer("نامعتبر", show_alert=True)
        return
    aud, kind = parts[3], parts[4]
    if aud not in {"users", "resellers"}:
        await callback.answer("نامعتبر", show_alert=True)
        return
    await callback.answer()
    if callback.message:
        try:
            await callback.message.delete()
        except Exception:
            pass
        await open_add_kind_action(callback.message, session, db_user, state, aud, kind)


@router.callback_query(F.data == "adm:plans")
async def plans_hub(callback: CallbackQuery, session: AsyncSession, db_user: BotUser, state: FSMContext):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    await state.clear()
    await callback.answer()
    if callback.message:
        try:
            await callback.message.edit_text(
                "💎 <b>پلن‌ها</b>\n"
                "«پلن‌های کاربران» یا «پلن‌های نمایندگان» را از کیبورد پایین بزنید.",
                reply_markup=None,
            )
        except Exception:
            pass
        await sync_plans_reply_keyboard(callback.message, session, db_user, state)


@router.callback_query(F.data.startswith("adm:plans:aud:"))
async def plans_aud_inline_back(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: BotUser,
    state: FSMContext,
):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    aud = callback.data.rsplit(":", 1)[-1]
    if aud not in {"users", "resellers"}:
        await callback.answer("نامعتبر", show_alert=True)
        return
    await state.update_data(_adm_plans_aud=aud, _adm_plans_kind=None)
    await callback.answer()
    title = "کاربران" if aud == "users" else "نمایندگان"
    if callback.message:
        try:
            await callback.message.edit_text(f"💎 <b>پلن‌های {title}</b>", reply_markup=None)
        except Exception:
            pass
        await sync_plans_reply_keyboard(callback.message, session, db_user, state, audience=aud)
        if aud == "users":
            await send_users_plans_overview(callback.message, session)
        else:
            await send_resellers_plans_overview(callback.message, session)


@router.callback_query(F.data.startswith("adm:plans:kind:"))
async def plans_kind_cb(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: BotUser,
    state: FSMContext,
):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    parts = callback.data.split(":")
    if len(parts) < 5:
        await callback.answer("نامعتبر", show_alert=True)
        return
    aud, kind = parts[3], parts[4]
    await state.update_data(_adm_plans_aud=aud, _adm_plans_kind=kind)
    await callback.answer()
    if callback.message:
        await callback.message.edit_text("⏳")
        await open_kind_screen(callback.message, session, aud, kind)
        try:
            await callback.message.delete()
        except Exception:
            pass


@router.callback_query(F.data.startswith("adm:plans:tog:"))
async def plans_toggle(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: BotUser,
    state: FSMContext,
):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    key = callback.data.split("adm:plans:tog:", 1)[-1]
    cur = await get_setting(session, key)
    new_val = "0" if on(cur) else "1"
    await set_setting(session, key, new_val)
    if key == "trial_enabled":
        trial = await _ensure_trial(session)
        trial.is_active = new_val == "1"
    await callback.answer("ذخیره شد")
    data = await state.get_data()
    aud = data.get("_adm_plans_aud") or "users"
    kind = data.get("_adm_plans_kind") or (
        "custom" if key.startswith("custom_plan") else "trial" if key == "trial_enabled" else "wholesale"
    )
    if key.startswith("custom_plan"):
        kind = "custom"
    if key.startswith("wholesale"):
        kind = "wholesale"
    await _rerender_plans_screen(callback, session, aud, kind)


@router.callback_query(F.data.startswith("adm:plans:edit:"))
async def plans_edit_ask(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    db_user: BotUser,
):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    key = callback.data.split("adm:plans:edit:", 1)[-1]
    cur = await get_setting(session, key)
    await callback.answer()
    await state.set_state(AdminPlansStates.edit_value)
    await state.update_data(plans_edit_key=key, _adm_plans_aud="users")
    kind = "wholesale" if key.startswith("wholesale") or key == "btn_wholesale" else "custom"
    await state.update_data(_adm_plans_kind=kind)
    if callback.message:
        await callback.message.answer(
            f"مقدار جدید برای <b>{key}</b>\nفعلی: <code>{html.escape((cur or '')[:200])}</code>",
            reply_markup=kb.cancel_reply(),
        )


@router.message(AdminPlansStates.edit_value)
async def plans_edit_save(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    db_user: BotUser,
):
    if not _is_admin(db_user):
        await state.clear()
        return
    if kb.is_cancel_text(message.text):
        await state.set_state(None)
        await _answer_plans_cancel(message, state, session)
        return
    data = await state.get_data()
    key = data.get("plans_edit_key")
    text = (message.text or "").strip()
    if not key:
        await state.clear()
        return
    if key in {
        "wholesale_min_qty",
        "wholesale_max_qty",
        "custom_plan_price_per_gb",
        "custom_plan_price_per_day",
        "custom_plan_min_gb",
        "custom_plan_max_gb",
        "custom_plan_min_days",
        "custom_plan_max_days",
    }:
        try:
            float(text.replace(",", "").replace("٬", ""))
        except ValueError:
            await message.answer("عدد معتبر بفرستید.", reply_markup=kb.cancel_reply())
            return
    await set_setting(session, key, text.replace(",", "").replace("٬", ""))
    await state.set_state(None)
    aud = data.get("_adm_plans_aud") or "users"
    kind = data.get("_adm_plans_kind") or "custom"
    await _answer_plans_saved(message, state, session, "ذخیره شد ✅")
    bubble = await message.answer("⏳")
    await open_kind_screen(bubble, session, aud, kind)


@router.callback_query(F.data == "adm:plans:wholesale:add_tier")
async def wholesale_add_tier_ask(callback: CallbackQuery, state: FSMContext, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    await callback.answer()
    await state.set_state(AdminPlansStates.wholesale_tier_min)
    await state.update_data(_adm_plans_aud="users", _adm_plans_kind="wholesale")
    if callback.message:
        await callback.message.answer(
            "حداقل تعداد برای پله جدید:",
            reply_markup=kb.cancel_reply(),
        )


@router.message(AdminPlansStates.wholesale_tier_min)
async def wholesale_tier_min_entered(
    message: Message, state: FSMContext, db_user: BotUser
):
    if not _is_admin(db_user):
        await state.clear()
        return
    if kb.is_cancel_text(message.text):
        await state.set_state(None)
        await _answer_plans_cancel(message, state, session)
        return
    try:
        mn = int((message.text or "").strip())
    except ValueError:
        await message.answer("عدد معتبر بفرستید.")
        return
    await state.update_data(tier_min=mn)
    await state.set_state(AdminPlansStates.wholesale_tier_pct)
    await message.answer("درصد تخفیف (۰–۱۰۰):", reply_markup=kb.cancel_reply())


@router.message(AdminPlansStates.wholesale_tier_pct)
async def wholesale_tier_pct_entered(
    message: Message, state: FSMContext, session: AsyncSession, db_user: BotUser
):
    if not _is_admin(db_user):
        await state.clear()
        return
    if kb.is_cancel_text(message.text):
        await state.set_state(None)
        await _answer_plans_cancel(message, state, session)
        return
    try:
        pct = int((message.text or "").strip())
        pct = max(0, min(100, pct))
    except ValueError:
        await message.answer("عدد معتبر بفرستید.")
        return
    data = await state.get_data()
    mn = int(data.get("tier_min") or 1)
    ui = await get_all_settings(session)
    tiers = parse_wholesale_tiers(ui.get("wholesale_tiers"))
    tiers.append({"min": mn, "percent": pct})
    tiers.sort(key=lambda t: t["min"])
    await set_setting(session, "wholesale_tiers", json.dumps(tiers, ensure_ascii=False))
    await state.set_state(None)
    await _answer_plans_saved(message, state, session, "پله ذخیره شد ✅")
    bubble = await message.answer("⏳")
    await send_users_wholesale(bubble, session)


@router.callback_query(F.data.startswith("adm:plans:wholesale:del:"))
async def wholesale_del_tier(
    callback: CallbackQuery, session: AsyncSession, db_user: BotUser, state: FSMContext
):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    idx = int(callback.data.rsplit(":", 1)[-1])
    ui = await get_all_settings(session)
    tiers = parse_wholesale_tiers(ui.get("wholesale_tiers"))
    if 0 <= idx < len(tiers):
        tiers.pop(idx)
    await set_setting(session, "wholesale_tiers", json.dumps(tiers, ensure_ascii=False))
    await state.update_data(_adm_plans_aud="users", _adm_plans_kind="wholesale")
    await callback.answer("حذف شد")
    await _rerender_plans_screen(callback, session, "users", "wholesale")


# —— Trial (plans context) ——


@router.callback_query(F.data == "adm:plans:trial:name")
async def trial_ask_name(callback: CallbackQuery, state: FSMContext, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    await callback.answer()
    await state.set_state(AdminPlansStates.trial_name)
    await state.update_data(_adm_plans_aud="users", _adm_plans_kind="trial")
    if callback.message:
        await callback.message.answer("نام پلن تست:", reply_markup=kb.cancel_reply())


@router.message(AdminPlansStates.trial_name)
async def trial_save_name(message: Message, state: FSMContext, session: AsyncSession, db_user: BotUser):
    if not _is_admin(db_user) or kb.is_cancel_text(message.text):
        await state.set_state(None)
        await _answer_plans_cancel(message, state, session)
        return
    trial = await _ensure_trial(session)
    trial.name = (message.text or "").strip()[:128]
    await state.set_state(None)
    await _answer_plans_saved(message, state, session, "ذخیره شد ✅")
    bubble = await message.answer("⏳")
    await send_users_trial(bubble, session)


@router.callback_query(F.data == "adm:plans:trial:days")
async def trial_ask_days(callback: CallbackQuery, state: FSMContext, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    await callback.answer()
    await state.set_state(AdminPlansStates.trial_days)
    await state.update_data(_adm_plans_aud="users", _adm_plans_kind="trial")
    if callback.message:
        await callback.message.answer("مدت به روز:", reply_markup=kb.cancel_reply())


@router.message(AdminPlansStates.trial_days)
async def trial_save_days(message: Message, state: FSMContext, session: AsyncSession, db_user: BotUser):
    if not _is_admin(db_user) or kb.is_cancel_text(message.text):
        await state.set_state(None)
        await _answer_plans_cancel(message, state, session)
        return
    try:
        days = max(1, int((message.text or "").strip()))
    except ValueError:
        await message.answer("عدد معتبر بفرستید.")
        return
    trial = await _ensure_trial(session)
    trial.duration_days = days
    await state.set_state(None)
    await _answer_plans_saved(message, state, session, "ذخیره شد ✅")
    bubble = await message.answer("⏳")
    await send_users_trial(bubble, session)


@router.callback_query(F.data == "adm:plans:trial:gb")
async def trial_ask_gb(callback: CallbackQuery, state: FSMContext, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    await callback.answer()
    await state.set_state(AdminPlansStates.trial_gb)
    await state.update_data(_adm_plans_aud="users", _adm_plans_kind="trial")
    if callback.message:
        await callback.message.answer("حجم گیگ (۰ = نامحدود):", reply_markup=kb.cancel_reply())


@router.message(AdminPlansStates.trial_gb)
async def trial_save_gb(message: Message, state: FSMContext, session: AsyncSession, db_user: BotUser):
    if not _is_admin(db_user) or kb.is_cancel_text(message.text):
        await state.set_state(None)
        await _answer_plans_cancel(message, state, session)
        return
    try:
        gb = float((message.text or "").replace(",", ".").strip())
    except ValueError:
        await message.answer("عدد معتبر بفرستید.")
        return
    trial = await _ensure_trial(session)
    trial.data_limit_gb = None if gb <= 0 else gb
    await state.set_state(None)
    await _answer_plans_saved(message, state, session, "ذخیره شد ✅")
    bubble = await message.answer("⏳")
    await send_users_trial(bubble, session)


@router.callback_query(F.data == "adm:plans:trial:tpl")
async def trial_pick_tpl(callback: CallbackQuery, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    try:
        templates = await get_pg().get_user_templates_simple()
    except Exception:
        templates = []
    rows: list[list[InlineKeyboardButton]] = []
    for t in templates[:20]:
        tid = t.get("id")
        if tid is None:
            continue
        rows.append(
            [
                InlineKeyboardButton(
                    text=str(t.get("name") or tid)[:40],
                    callback_data=f"adm:plans:trial:settpl:{tid}",
                )
            ]
        )
    if not rows:
        rows.append(
            [InlineKeyboardButton(text="تمپلیتی نیست", callback_data=BACK_USERS_KIND)]
        )
    rows.append(_back_row("⬅️ بازگشت", BACK_USERS_KIND))
    await callback.answer()
    if callback.message:
        await callback.message.edit_text("تمپلیت را انتخاب کنید:", reply_markup=_kb(rows))


@router.callback_query(F.data.startswith("adm:plans:trial:settpl:"))
async def trial_set_tpl(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    tid = int(callback.data.rsplit(":", 1)[-1])
    trial = await _ensure_trial(session)
    trial.pg_template_id = tid
    trial.pg_group_ids = None
    await callback.answer("ذخیره شد")
    bubble = await callback.message.answer("⏳") if callback.message else None
    if bubble:
        await send_users_trial(bubble, session)


@router.callback_query(F.data == "adm:plans:trial:grp")
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
    await state.update_data(trial_groups=selected, _adm_plans_kind="trial")
    await callback.answer()
    await _show_trial_groups_plans(callback, state)


async def _show_trial_groups_plans(callback: CallbackQuery, state: FSMContext) -> None:
    selected = [int(x) for x in ((await state.get_data()).get("trial_groups") or [])]
    try:
        groups = await get_pg().get_groups_simple()
    except Exception:
        groups = []
    rows: list[list[InlineKeyboardButton]] = []
    for g in groups[:20]:
        gid = g.get("id")
        if gid is None:
            continue
        gid = int(gid)
        mark = "✅ " if gid in selected else ""
        name = g.get("name") or f"گروه {gid}"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{mark}{name}"[:40],
                    callback_data=f"adm:plans:trial:toggrp:{gid}",
                )
            ]
        )
    if rows:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"تأیید ({len(selected)})",
                    callback_data="adm:plans:trial:grpdone",
                )
            ]
        )
    else:
        rows.append([InlineKeyboardButton(text="گروهی نیست", callback_data=BACK_USERS_KIND)])
    rows.append(_back_row("⬅️ بازگشت", BACK_USERS_KIND))
    if callback.message:
        await callback.message.edit_text("گروه(ها) را انتخاب کنید:", reply_markup=_kb(rows))


@router.callback_query(F.data.startswith("adm:plans:trial:toggrp:"))
async def trial_tog_grp_plans(callback: CallbackQuery, state: FSMContext, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    gid = int(callback.data.split(":")[-1])
    selected = [int(x) for x in ((await state.get_data()).get("trial_groups") or [])]
    if gid in selected:
        selected = [x for x in selected if x != gid]
    else:
        selected.append(gid)
    await state.update_data(trial_groups=selected)
    await callback.answer()
    await _show_trial_groups_plans(callback, state)


@router.callback_query(F.data == "adm:plans:trial:grpdone")
async def trial_grp_done_plans(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext, db_user: BotUser
):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    selected = [int(x) for x in ((await state.get_data()).get("trial_groups") or [])]
    if not selected:
        await callback.answer("حداقل یک گروه", show_alert=True)
        return
    trial = await _ensure_trial(session)
    trial.pg_group_ids = ",".join(str(x) for x in selected)
    trial.pg_template_id = None
    await state.update_data(trial_groups=[])
    await callback.answer("ذخیره شد")
    if callback.message:
        text, markup = await _build_trial_screen(session)
        await callback.message.edit_text(text, reply_markup=markup)


# —— Custom PG (plans context) ——


async def _custom_pg_summary(session: AsyncSession) -> tuple[str, InlineKeyboardMarkup]:
    ui = await get_all_settings(session)
    enabled = on(ui.get("custom_plan_enabled"))
    tpl = (ui.get("custom_plan_template_id") or "").strip()
    groups = (ui.get("custom_plan_group_ids") or "").strip()
    if tpl:
        link = f"تمپلیت #{tpl}"
    elif groups:
        link = f"گروه‌ها: {groups}"
    else:
        link = "⚠️ بدون اتصال"
    text = (
        "🔗 <b>اتصال پلن دلخواه</b>\n\n"
        f"فروش: {'فعال' if enabled else 'خاموش'}\n"
        f"پاسارگارد: {link}"
    )
    rows = [
        [
            InlineKeyboardButton(
                text="خاموش کردن فروش" if enabled else "روشن کردن فروش",
                callback_data="adm:plans:custom:toggle",
            )
        ],
        [InlineKeyboardButton(text="تمپلیت", callback_data="adm:plans:custom:picktpl")],
        [InlineKeyboardButton(text="گروه", callback_data="adm:plans:custom:pickgrp")],
    ]
    if tpl or groups:
        rows.append(
            [InlineKeyboardButton(text="حذف اتصال", callback_data="adm:plans:custom:clearlink")]
        )
    rows.append(_back_row("⬅️ پلن دلخواه", BACK_USERS_KIND))
    return text, _kb(rows)


@router.callback_query(F.data == "adm:plans:custom:pg")
async def custom_pg_hub(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    await callback.answer()
    text, markup = await _custom_pg_summary(session)
    if callback.message:
        await callback.message.edit_text(text, reply_markup=markup)


@router.callback_query(F.data == "adm:plans:custom:toggle")
async def custom_pg_toggle(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    cur = await get_setting(session, "custom_plan_enabled")
    await set_setting(session, "custom_plan_enabled", "0" if on(cur) else "1")
    await callback.answer("بروز شد")
    text, markup = await _custom_pg_summary(session)
    if callback.message:
        await callback.message.edit_text(text, reply_markup=markup)


@router.callback_query(F.data == "adm:plans:custom:clearlink")
async def custom_pg_clear(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    await set_setting(session, "custom_plan_template_id", "")
    await set_setting(session, "custom_plan_group_ids", "")
    await callback.answer("حذف شد")
    text, markup = await _custom_pg_summary(session)
    if callback.message:
        await callback.message.edit_text(text, reply_markup=markup)


@router.callback_query(F.data == "adm:plans:custom:picktpl")
async def custom_pick_tpl(callback: CallbackQuery, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    try:
        templates = await get_pg().get_user_templates_simple()
    except Exception:
        templates = []
    rows: list[list[InlineKeyboardButton]] = []
    for t in templates[:20]:
        tid = t.get("id")
        if tid is None:
            continue
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"#{tid} — {(t.get('name') or tid)}"[:60],
                    callback_data=f"adm:plans:custom:settpl:{tid}",
                )
            ]
        )
    if not rows:
        rows.append([InlineKeyboardButton(text="تمپلیتی نیست", callback_data="adm:plans:custom:pg")])
    rows.append(_back_row("⬅️ بازگشت", "adm:plans:custom:pg"))
    await callback.answer()
    if callback.message:
        await callback.message.edit_text("تمپلیت:", reply_markup=_kb(rows))


@router.callback_query(F.data.startswith("adm:plans:custom:settpl:"))
async def custom_set_tpl(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    tpl_id = callback.data.rsplit(":", 1)[-1]
    await set_setting(session, "custom_plan_template_id", tpl_id)
    await set_setting(session, "custom_plan_group_ids", "")
    await callback.answer("ذخیره شد")
    text, markup = await _custom_pg_summary(session)
    if callback.message:
        await callback.message.edit_text(text, reply_markup=markup)


@router.callback_query(F.data == "adm:plans:custom:pickgrp")
async def custom_pick_grp(callback: CallbackQuery, state: FSMContext, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    await state.update_data(custom_selected_groups=[])
    await callback.answer()
    await _show_custom_groups_plans(callback, state)


async def _show_custom_groups_plans(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    selected = [int(x) for x in (data.get("custom_selected_groups") or [])]
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
                    callback_data=f"adm:plans:custom:toggrp:{gid}",
                )
            ]
        )
    if rows:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"✅ تأیید ({len(selected)})",
                    callback_data="adm:plans:custom:grpdone",
                )
            ]
        )
    else:
        rows.append([InlineKeyboardButton(text="گروهی نیست", callback_data="adm:plans:custom:pg")])
    rows.append(_back_row("⬅️ بازگشت", "adm:plans:custom:pg"))
    if callback.message:
        await callback.message.edit_text(
            f"گروه‌ها:\nانتخاب: {', '.join(str(x) for x in selected) or '—'}",
            reply_markup=_kb(rows),
        )


@router.callback_query(F.data.startswith("adm:plans:custom:toggrp:"))
async def custom_tog_grp(callback: CallbackQuery, state: FSMContext, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    gid = int(callback.data.rsplit(":", 1)[-1])
    data = await state.get_data()
    selected = [int(x) for x in (data.get("custom_selected_groups") or [])]
    if gid in selected:
        selected = [x for x in selected if x != gid]
    else:
        selected.append(gid)
    await state.update_data(custom_selected_groups=selected)
    await callback.answer()
    await _show_custom_groups_plans(callback, state)


@router.callback_query(F.data == "adm:plans:custom:grpdone")
async def custom_grp_done(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext, db_user: BotUser
):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    selected = [int(x) for x in ((await state.get_data()).get("custom_selected_groups") or [])]
    if not selected:
        await callback.answer("حداقل یک گروه", show_alert=True)
        return
    await set_setting(session, "custom_plan_group_ids", ",".join(str(x) for x in selected))
    await set_setting(session, "custom_plan_template_id", "")
    await state.update_data(custom_selected_groups=[])
    await callback.answer("ذخیره شد")
    text, markup = await _custom_pg_summary(session)
    if callback.message:
        await callback.message.edit_text(text, reply_markup=markup)


# —— Reseller subscription plans ——


def _resplan_detail_text(plan: ResellerPlan) -> str:
    return format_reseller_plan_apply_detail(plan, currency=get_settings().currency)


def _resplan_detail_keyboard(plan: ResellerPlan) -> InlineKeyboardMarkup:
    mode = reseller_plan_mode_of(plan)
    back = f"adm:plans:kind:resellers:{mode}"
    pid = plan.id
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="✏️ نام", callback_data=f"adm:resplan:edit:name:{pid}")],
        [InlineKeyboardButton(text="✏️ قیمت ورود", callback_data=f"adm:resplan:edit:price:{pid}")],
    ]
    if mode == "payg":
        rows.append(
            [InlineKeyboardButton(text="✏️ نرخ / گیگ", callback_data=f"adm:resplan:edit:rate:{pid}")]
        )
        rows.append(
            [InlineKeyboardButton(text="📁 گروه PG", callback_data=f"adm:resplan:edit:grp:{pid}")]
        )
    else:
        rows.append(
            [InlineKeyboardButton(text="✏️ کمیسیون", callback_data=f"adm:resplan:edit:comm:{pid}")]
        )
    rows.extend(
        [
            [InlineKeyboardButton(text="✏️ توضیح", callback_data=f"adm:resplan:edit:desc:{pid}")],
            [InlineKeyboardButton(text="🔐 دسترسی‌ها", callback_data=f"adm:resplan:perms:{pid}")],
            [
                InlineKeyboardButton(
                    text="⏸ خاموش" if plan.is_active else "▶️ روشن",
                    callback_data=f"adm:resplan:toggle:{pid}",
                )
            ],
            [InlineKeyboardButton(text="🗑 حذف", callback_data=f"adm:resplan:delask:{pid}")],
            _back_row("⬅️ لیست", back),
        ]
    )
    return _kb(rows)


@router.callback_query(F.data.startswith("adm:resplan:view:"))
async def resplan_view(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    plan = await session.get(ResellerPlan, int(callback.data.rsplit(":", 1)[-1]))
    if not plan:
        await callback.answer("یافت نشد", show_alert=True)
        return
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(
            _resplan_detail_text(plan),
            reply_markup=_resplan_detail_keyboard(plan),
        )


@router.callback_query(F.data.startswith("adm:resplan:toggle:"))
async def resplan_toggle(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    plan = await session.get(ResellerPlan, int(callback.data.rsplit(":", 1)[-1]))
    if not plan:
        await callback.answer("یافت نشد", show_alert=True)
        return
    plan.is_active = not plan.is_active
    await callback.answer("بروز شد")
    if callback.message:
        await callback.message.edit_text(
            _resplan_detail_text(plan),
            reply_markup=_resplan_detail_keyboard(plan),
        )


@router.callback_query(F.data.startswith("adm:resplan:delask:"))
async def resplan_del_ask(callback: CallbackQuery, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    pid = int(callback.data.rsplit(":", 1)[-1])
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(
            "⚠️ این پلن نمایندگی حذف شود؟",
            reply_markup=_kb(
                [
                    [
                        InlineKeyboardButton(
                            text="🗑 تأیید حذف",
                            callback_data=f"adm:resplan:del:{pid}",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="انصراف",
                            callback_data=f"adm:resplan:view:{pid}",
                        )
                    ],
                ]
            ),
        )


@router.callback_query(F.data.startswith("adm:resplan:del:"))
async def resplan_del(callback: CallbackQuery, session: AsyncSession, db_user: BotUser, state: FSMContext):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    pid = int(callback.data.rsplit(":", 1)[-1])
    plan = await session.get(ResellerPlan, pid)
    if not plan:
        await callback.answer("یافت نشد", show_alert=True)
        return
    mode = reseller_plan_mode_of(plan)
    await session.delete(plan)
    await callback.answer("حذف شد")
    await state.update_data(_adm_plans_aud="resellers", _adm_plans_kind=mode)
    if callback.message:
        await _rerender_plans_screen(callback, session, "resellers", mode)


@router.callback_query(F.data.startswith("adm:resplan:edit:"))
async def resplan_edit_ask(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, db_user: BotUser
):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    parts = callback.data.split(":")
    if len(parts) < 5:
        await callback.answer("نامعتبر", show_alert=True)
        return
    field, pid_raw = parts[3], parts[4]
    plan = await session.get(ResellerPlan, int(pid_raw))
    if not plan:
        await callback.answer("یافت نشد", show_alert=True)
        return
    mode = reseller_plan_mode_of(plan)
    await state.update_data(
        resplan_edit_id=plan.id,
        resplan_edit_field=field,
        _adm_plans_aud="resellers",
        _adm_plans_kind=mode,
    )
    if field == "grp":
        selected: list[int] = []
        if plan.pg_group_ids:
            for part in str(plan.pg_group_ids).split(","):
                if part.strip().isdigit():
                    selected.append(int(part.strip()))
        await state.update_data(resplan_edit_groups=selected)
        await callback.answer()
        await _show_resplan_groups(callback, state, plan.id)
        return
    prompts = {
        "name": "نام جدید:",
        "price": "قیمت ورود (تومان):",
        "comm": "کمیسیون (۰–۱۰۰٪):",
        "rate": "نرخ هر گیگ (تومان):",
        "desc": "توضیح (خالی = حذف):",
    }
    if field not in prompts:
        await callback.answer("نامعتبر", show_alert=True)
        return
    await callback.answer()
    await state.set_state(AdminPlansStates.res_plan_edit_field)
    if callback.message:
        await callback.message.answer(prompts[field], reply_markup=kb.cancel_reply())


async def _show_resplan_groups(callback: CallbackQuery, state: FSMContext, plan_id: int) -> None:
    selected = [int(x) for x in ((await state.get_data()).get("resplan_edit_groups") or [])]
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
                    text=f"{mark}{name}"[:40],
                    callback_data=f"adm:resplan:edit:toggrp:{plan_id}:{gid}",
                )
            ]
        )
    if rows:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"تأیید ({len(selected)})",
                    callback_data=f"adm:resplan:edit:grpdone:{plan_id}",
                )
            ]
        )
    else:
        rows.append(
            [
                InlineKeyboardButton(
                    text="گروهی نیست",
                    callback_data=f"adm:resplan:view:{plan_id}",
                )
            ]
        )
    rows.append(_back_row("⬅️ پلن", f"adm:resplan:view:{plan_id}"))
    if callback.message:
        await callback.message.edit_text("گروه(ها) را انتخاب کنید:", reply_markup=_kb(rows))


@router.callback_query(F.data.startswith("adm:resplan:edit:toggrp:"))
async def resplan_edit_tog_grp(callback: CallbackQuery, state: FSMContext, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    parts = callback.data.split(":")
    plan_id = int(parts[4])
    gid = int(parts[5])
    selected = [int(x) for x in ((await state.get_data()).get("resplan_edit_groups") or [])]
    if gid in selected:
        selected = [x for x in selected if x != gid]
    else:
        selected.append(gid)
    await state.update_data(resplan_edit_groups=selected)
    await callback.answer()
    await _show_resplan_groups(callback, state, plan_id)


@router.callback_query(F.data.startswith("adm:resplan:edit:grpdone:"))
async def resplan_edit_grp_done(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext, db_user: BotUser
):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    plan_id = int(callback.data.rsplit(":", 1)[-1])
    plan = await session.get(ResellerPlan, plan_id)
    if not plan:
        await callback.answer("یافت نشد", show_alert=True)
        return
    selected = [int(x) for x in ((await state.get_data()).get("resplan_edit_groups") or [])]
    plan.pg_group_ids = ",".join(str(x) for x in selected) if selected else None
    from app.services.billing import sync_plan_billing_rate

    await sync_plan_billing_rate(session, plan)
    await state.update_data(resplan_edit_groups=[])
    await callback.answer("ذخیره شد")
    if callback.message:
        await callback.message.edit_text(
            _resplan_detail_text(plan),
            reply_markup=_resplan_detail_keyboard(plan),
        )


@router.callback_query(F.data.startswith("adm:resplan:perms:"))
async def resplan_perms_screen(
    callback: CallbackQuery, session: AsyncSession, db_user: BotUser
):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    plan_id = int(callback.data.rsplit(":", 1)[-1])
    plan = await session.get(ResellerPlan, plan_id)
    if not plan:
        await callback.answer("یافت نشد", show_alert=True)
        return
    active = set(parse_perms(plan.web_permissions or plan.bot_permissions))
    rows: list[list[InlineKeyboardButton]] = []
    for key, label in FEATURE_PERMS:
        mark = "✅" if key in active else "⬜️"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{mark} {label}",
                    callback_data=f"adm:resplan:togperm:{plan_id}:{key}",
                )
            ]
        )
    rows.append(_back_row("⬅️ پلن", f"adm:resplan:view:{plan_id}"))
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(
            "🔐 <b>دسترسی‌های پلن</b>\nوب و ربات نماینده یکسان است.",
            reply_markup=_kb(rows),
        )


@router.callback_query(F.data.startswith("adm:resplan:togperm:"))
async def resplan_tog_perm(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    parts = callback.data.split(":")
    plan_id = int(parts[3])
    key = parts[4]
    plan = await session.get(ResellerPlan, plan_id)
    if not plan:
        await callback.answer("یافت نشد", show_alert=True)
        return
    perms = set(parse_perms(plan.web_permissions or plan.bot_permissions))
    if key in perms:
        perms.discard(key)
    else:
        perms.add(key)
    csv = ",".join(sorted(perms))
    plan.web_permissions = csv
    plan.bot_permissions = csv
    plan.can_approve_receipts = "payments" in perms
    await callback.answer("بروز شد")
    active = perms
    rows: list[list[InlineKeyboardButton]] = []
    for perm_key, label in FEATURE_PERMS:
        mark = "✅" if perm_key in active else "⬜️"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{mark} {label}",
                    callback_data=f"adm:resplan:togperm:{plan_id}:{perm_key}",
                )
            ]
        )
    rows.append(_back_row("⬅️ پلن", f"adm:resplan:view:{plan_id}"))
    if callback.message:
        await callback.message.edit_text(
            "🔐 <b>دسترسی‌های پلن</b>\nوب و ربات نماینده یکسان است.",
            reply_markup=_kb(rows),
        )


@router.message(AdminPlansStates.res_plan_edit_field)
async def resplan_edit_save(
    message: Message, state: FSMContext, session: AsyncSession, db_user: BotUser
):
    if not _is_admin(db_user):
        await state.clear()
        return
    if kb.is_cancel_text(message.text):
        await _answer_plans_cancel(message, state, session)
        return
    data = await state.get_data()
    plan_id = int(data.get("resplan_edit_id") or 0)
    field = data.get("resplan_edit_field")
    plan = await session.get(ResellerPlan, plan_id)
    if not plan or not field:
        await state.clear()
        return
    text = (message.text or "").strip()
    from app.services.billing import sync_plan_billing_rate

    try:
        if field == "name":
            if not text:
                await message.answer("نام خالی نیست.", reply_markup=kb.cancel_reply())
                return
            plan.name = text[:128]
        elif field == "price":
            plan.price = max(0, int(text.replace(",", "").replace("٬", "")))
        elif field == "comm":
            plan.commission_percent = max(0, min(100, int(text)))
        elif field == "rate":
            plan.price_per_gb = max(0, int(text.replace(",", "").replace("٬", "")))
        elif field == "desc":
            plan.description = text or None
        else:
            await state.clear()
            return
    except ValueError:
        await message.answer("عدد معتبر بفرستید.", reply_markup=kb.cancel_reply())
        return
    await sync_plan_billing_rate(session, plan)
    await state.set_state(None)
    await _answer_plans_saved(message, state, session, "ذخیره شد ✅")
    bubble = await message.answer(
        _resplan_detail_text(plan),
        reply_markup=_resplan_detail_keyboard(plan),
    )
    _ = bubble


@router.callback_query(F.data.startswith("adm:resplan:add:"))
async def resplan_add_start(callback: CallbackQuery, state: FSMContext, db_user: BotUser):
    if not _is_admin(db_user):
        await callback.answer("ادمین نیستید", show_alert=True)
        return
    mode = callback.data.rsplit(":", 1)[-1]
    if mode not in {"fixed", "payg"}:
        await callback.answer("نامعتبر", show_alert=True)
        return
    await callback.answer()
    await state.set_state(AdminPlansStates.res_plan_name)
    await state.update_data(res_plan_mode=mode, _adm_plans_aud="resellers", _adm_plans_kind=mode)
    if callback.message:
        await callback.message.answer("نام پلن نمایندگی:", reply_markup=kb.cancel_reply())


@router.message(AdminPlansStates.res_plan_name)
async def resplan_name(message: Message, state: FSMContext, session: AsyncSession, db_user: BotUser):
    if not _is_admin(db_user) or kb.is_cancel_text(message.text):
        await state.set_state(None)
        await _answer_plans_cancel(message, state, session)
        return
    await state.update_data(res_plan_name=(message.text or "").strip()[:128])
    await state.set_state(AdminPlansStates.res_plan_price)
    await message.answer("قیمت ورود (تومان، ۰ = رایگان):", reply_markup=kb.cancel_reply())


@router.message(AdminPlansStates.res_plan_price)
async def resplan_price(message: Message, state: FSMContext, session: AsyncSession, db_user: BotUser):
    if not _is_admin(db_user) or kb.is_cancel_text(message.text):
        await state.set_state(None)
        await _answer_plans_cancel(message, state, session)
        return
    try:
        price = int((message.text or "").replace(",", "").replace("٬", ""))
    except ValueError:
        await message.answer("عدد معتبر بفرستید.")
        return
    await state.update_data(res_plan_price=max(0, price))
    data = await state.get_data()
    if data.get("res_plan_mode") == "payg":
        await state.set_state(AdminPlansStates.res_plan_rate_gb)
        await message.answer("نرخ هر گیگ (تومان):", reply_markup=kb.cancel_reply())
    else:
        await state.set_state(AdminPlansStates.res_plan_commission)
        await message.answer("کمیسیون فروش (۰–۱۰۰٪):", reply_markup=kb.cancel_reply())


@router.message(AdminPlansStates.res_plan_commission)
async def resplan_commission(
    message: Message, state: FSMContext, session: AsyncSession, db_user: BotUser
):
    if not _is_admin(db_user) or kb.is_cancel_text(message.text):
        await state.set_state(None)
        await _answer_plans_cancel(message, state, session)
        return
    try:
        comm = max(0, min(100, int((message.text or "").strip())))
    except ValueError:
        await message.answer("عدد معتبر بفرستید.")
        return
    await _save_reseller_plan(session, state, commission_percent=comm)
    await state.set_state(None)
    await _answer_plans_saved(message, state, session, "پلن نمایندگی ذخیره شد ✅")
    data = await state.get_data()
    bubble = await message.answer("⏳")
    await send_reseller_plans_list(bubble, session, data.get("res_plan_mode") or "fixed")


@router.message(AdminPlansStates.res_plan_rate_gb)
async def resplan_rate_gb(
    message: Message, state: FSMContext, session: AsyncSession, db_user: BotUser
):
    if not _is_admin(db_user) or kb.is_cancel_text(message.text):
        await state.set_state(None)
        await _answer_plans_cancel(message, state, session)
        return
    try:
        rate = max(0, int((message.text or "").replace(",", "").replace("٬", "")))
    except ValueError:
        await message.answer("عدد معتبر بفرستید.")
        return
    await _save_reseller_plan(session, state, price_per_gb=rate)
    await state.set_state(None)
    await _answer_plans_saved(message, state, session, "پلن PAYG ذخیره شد ✅")
    data = await state.get_data()
    bubble = await message.answer("⏳")
    await send_reseller_plans_list(bubble, session, "payg")


async def _save_reseller_plan(
    session: AsyncSession,
    state: FSMContext,
    *,
    commission_percent: int | None = None,
    price_per_gb: int | None = None,
) -> ResellerPlan:
    from app.services.billing import sync_plan_billing_rate

    data = await state.get_data()
    mode = data.get("res_plan_mode") or "fixed"
    plan = ResellerPlan(
        name=data.get("res_plan_name") or "پلن نماینده",
        price=int(data.get("res_plan_price") or 0),
        billing_mode=mode,
        commission_percent=int(commission_percent or 0),
        price_per_gb=int(price_per_gb or 0) if mode == "payg" else 0,
        web_permissions=DEFAULT_FEATURE_PERMS,
        bot_permissions=DEFAULT_FEATURE_PERMS,
        create_pg_admin=True,
        create_web_access=True,
        is_active=True,
    )
    session.add(plan)
    await session.flush()
    await sync_plan_billing_rate(session, plan)
    return plan

