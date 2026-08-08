"""Telegram Referral + Loyalty / Points UX (customer + staff manage)."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards as kb
from app.bot.tg_utils import safe_edit_text
from app.config import get_settings
from app.db.models import BotUser, LoyaltyReward, LoyaltyTier, PointsRule, Role, UserService
from app.services.formatting import format_message, format_toman, kv_line
from app.services.loyalty import (
    EVENT_LABELS,
    REWARD_TYPE_LABELS,
    SETTING_LOYALTY_ENABLED,
    SETTING_POINTS_TO_WALLET_RATE,
    ensure_loyalty_defaults,
    get_tier_for_points,
    list_active_rewards,
    list_available_discounts,
    list_points_history,
    loyalty_enabled,
    month_earned_points,
    overview_metrics,
    redeem_reward,
    referral_link,
    referral_stats,
)
from app.services.safe_format import safe_format
from app.services.users import get_all_settings, get_setting, on, set_setting

router = Router(name="loyalty")


class LoyaltyManageStates(StatesGroup):
    edit_wallet_rate = State()
    edit_referral_text = State()


# ---------------------------------------------------------------------------
# Customer inline keyboards
# ---------------------------------------------------------------------------


def _ref_keyboard(*, share_url: str | None = None) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if share_url:
        rows.append(
            [InlineKeyboardButton(text="📤 اشتراک‌گذاری لینک", url=share_url)]
        )
    rows.append(
        [
            InlineKeyboardButton(text="📊 آمار دعوت", callback_data="ref:stats"),
            InlineKeyboardButton(text="⭐ امتیاز من", callback_data="loy:home"),
        ]
    )
    rows.append([InlineKeyboardButton(text="🎁 جوایز", callback_data="loy:rewards")])
    rows.append([InlineKeyboardButton(text="🏠 خانه", callback_data="menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _loy_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🎁 جوایز", callback_data="loy:rewards"),
                InlineKeyboardButton(text="📜 تاریخچه", callback_data="loy:hist:0"),
            ],
            [InlineKeyboardButton(text="🏷 تخفیف‌های من", callback_data="loy:discounts")],
            [InlineKeyboardButton(text="👥 دعوت دوستان", callback_data="ref:home")],
            [InlineKeyboardButton(text="🏠 خانه", callback_data="menu:home")],
        ]
    )


async def _bot_username(callback_or_message) -> str:
    bot = callback_or_message.bot
    me = await bot.get_me()
    return me.username or get_settings().bot_username or "bot"


async def build_referral_text(session: AsyncSession, db_user: BotUser, uname: str) -> tuple[str, str]:
    ui = await get_all_settings(session)
    link = referral_link(uname, db_user.referral_code)
    try:
        await ensure_loyalty_defaults(session, reseller_id=db_user.reseller_id)
    except Exception:
        pass
    stats = await referral_stats(session, db_user.id)
    try:
        body = safe_format(ui["referral_text"], code=db_user.referral_code, link=link)
    except Exception:
        body = f"کد دعوت: <code>{db_user.referral_code}</code>\n{link}"
    extra = "\n".join(
        [
            "",
            kv_line("👥", "دعوت‌های موفق", str(stats["qualified"] or stats["total"])),
            kv_line("⭐", "امتیاز از دعوت", str(stats["earned_points"])),
            "",
            f"لینک دعوت:\n<code>{link}</code>",
        ]
    )
    text = format_message("🎁 دعوت دوستان", body + extra)
    return text, link


async def build_loyalty_text(session: AsyncSession, db_user: BotUser) -> str:
    await session.refresh(db_user)
    try:
        await ensure_loyalty_defaults(session, reseller_id=db_user.reseller_id)
    except Exception:
        pass
    tier = await get_tier_for_points(session, int(db_user.points_balance or 0))
    stats = await referral_stats(session, db_user.id)
    month = await month_earned_points(session, db_user.id)
    lines = [
        kv_line("⭐", "امتیاز شما", f"<b>{int(db_user.points_balance or 0)}</b>"),
        kv_line("🏅", "سطح", tier.name),
    ]
    if tier.points_to_next is not None:
        lines.append(kv_line("📈", "تا سطح بعد", f"{tier.points_to_next} امتیاز"))
    lines.extend(
        [
            kv_line("👥", "دعوت‌های موفق", str(stats["qualified"] or stats["total"])),
            kv_line("📅", "امتیاز این ماه", str(month)),
        ]
    )
    return format_message("⭐ باشگاه مشتریان", "\n".join(lines))


# ---------------------------------------------------------------------------
# Staff ACL — fail closed; never use Owner PG from reseller path
# ---------------------------------------------------------------------------


async def resolve_loyalty_manage_scope(
    session: AsyncSession,
    db_user: BotUser,
    *,
    is_reseller_bot: bool = False,
    reseller_owner_id: int | None = None,
) -> tuple[int | None, bool] | None:
    """Return ``(scope_reseller_id, can_manage_tiers)`` or ``None`` if denied.

    - Platform admin on main bot → ``(None, True)``
    - Reseller actor on shop bot with loyalty perm → ``(owner_id, False)``
    - Anything else (incl. admin on reseller bot) → denied
    """
    if is_reseller_bot:
        from app.services.reseller_access import load_reseller_actor
        from app.services.resellers import has_bot_perm

        owner_id, profile = await load_reseller_actor(
            session,
            db_user,
            is_reseller_bot=is_reseller_bot,
            reseller_owner_id=reseller_owner_id,
        )
        if not owner_id or not profile:
            return None
        if not has_bot_perm(profile, "loyalty"):
            return None
        return int(owner_id), False

    if db_user.role == Role.ADMIN.value:
        return None, True
    return None


def _rule_in_scope(rule: PointsRule, scope: int | None) -> bool:
    if scope is None:
        return rule.reseller_id is None
    return rule.reseller_id is not None and int(rule.reseller_id) == int(scope)


def _reward_in_scope(reward: LoyaltyReward, scope: int | None) -> bool:
    if scope is None:
        return reward.reseller_id is None
    return reward.reseller_id is not None and int(reward.reseller_id) == int(scope)


# ---------------------------------------------------------------------------
# Customer reply-keyboard openers
# ---------------------------------------------------------------------------


async def open_loyalty_home_message(
    message: Message,
    session: AsyncSession,
    db_user: BotUser,
    state: FSMContext | None = None,
    *,
    push: bool = True,
) -> None:
    from app.bot import menu_nav as nav

    if not await loyalty_enabled(session, reseller_id=db_user.reseller_id):
        await nav.show_nav_keyboard(
            message,
            session,
            db_user,
            nav.NAV_LOYALTY,
            text=format_message("⭐ باشگاه مشتریان", "این بخش فعلاً غیرفعال است."),
            state=state,
            push=push,
        )
        return
    text = await build_loyalty_text(session, db_user)
    await nav.show_nav_keyboard(
        message,
        session,
        db_user,
        nav.NAV_LOYALTY,
        text=text + "\n\nاز کیبورد پایین بخش مورد نظر را انتخاب کنید.",
        state=state,
        push=push,
    )
    await message.answer("گزینه‌های سریع:", reply_markup=_loy_keyboard())


async def open_loyalty_referral_message(
    message: Message,
    session: AsyncSession,
    db_user: BotUser,
    state: FSMContext | None = None,
    *,
    push: bool = True,
) -> None:
    from app.bot import menu_nav as nav

    uname = await _bot_username(message)
    text, link = await build_referral_text(session, db_user, uname)
    share = f"https://t.me/share/url?url={link}&text="
    await nav.show_nav_keyboard(
        message,
        session,
        db_user,
        nav.NAV_LOYALTY,
        text=text,
        state=state,
        push=push,
    )
    await message.answer(
        "گزینه‌ها:",
        reply_markup=_ref_keyboard(share_url=share),
    )


async def open_loyalty_points_message(
    message: Message, session: AsyncSession, db_user: BotUser
) -> None:
    ui = await get_all_settings(session)
    if not await loyalty_enabled(session, reseller_id=db_user.reseller_id):
        await message.answer(
            format_message("⭐ باشگاه مشتریان", "این بخش فعلاً غیرفعال است."),
            reply_markup=kb.loyalty_reply_keyboard(ui),
        )
        return
    text = await build_loyalty_text(session, db_user)
    await message.answer(text, reply_markup=kb.loyalty_reply_keyboard(ui))
    await message.answer("گزینه‌های سریع:", reply_markup=_loy_keyboard())


async def open_loyalty_rewards_message(
    message: Message, session: AsyncSession, db_user: BotUser
) -> None:
    ui = await get_all_settings(session)
    await session.refresh(db_user)
    rewards = await list_active_rewards(session, reseller_id=db_user.reseller_id)
    lines = [kv_line("⭐", "امتیاز فعلی", f"<b>{int(db_user.points_balance or 0)}</b>"), ""]
    rows: list[list[InlineKeyboardButton]] = []
    if not rewards:
        lines.append("هنوز جایزه‌ای تعریف نشده است.")
    else:
        for r in rewards:
            type_label = REWARD_TYPE_LABELS.get(r.reward_type, r.reward_type)
            desc = (r.description or "").strip()
            lines.append(
                f"• <b>{r.name}</b>\n"
                f"  {type_label}: {r.reward_value} · هزینه: {r.points_cost} امتیاز"
                + (f"\n  <i>{desc}</i>" if desc else "")
            )
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"دریافت «{r.name}»",
                        callback_data=f"loy:redeem:{r.id}",
                    )
                ]
            )
    rows.append([InlineKeyboardButton(text="بازگشت", callback_data="loy:home")])
    await message.answer(
        format_message("🎁 جوایز", "\n".join(lines)),
        reply_markup=kb.loyalty_reply_keyboard(ui),
    )
    await message.answer(
        "انتخاب جایزه:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


async def open_loyalty_history_message(
    message: Message, session: AsyncSession, db_user: BotUser
) -> None:
    ui = await get_all_settings(session)
    rows = await list_points_history(session, db_user.id, limit=8, offset=0)
    await session.refresh(db_user)
    if not rows:
        body = "تاریخچه‌ای نیست."
    else:
        lines = []
        for t in rows:
            sign = "+" if t.amount >= 0 else ""
            lines.append(f"{sign}{t.amount} — {t.description or t.tx_type}")
        body = "\n".join(lines)
    body += f"\n\nموجودی فعلی: <b>{int(db_user.points_balance or 0)}</b>"
    await message.answer(
        format_message("📜 تاریخچه امتیاز", body),
        reply_markup=kb.loyalty_reply_keyboard(ui),
    )
    nav_rows: list[list[InlineKeyboardButton]] = []
    if len(rows) >= 8:
        nav_rows.append(
            [InlineKeyboardButton(text="بعدی ▶️", callback_data="loy:hist:1")]
        )
    nav_rows.append([InlineKeyboardButton(text="بازگشت", callback_data="loy:home")])
    await message.answer(
        "صفحه‌بندی:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=nav_rows),
    )


async def open_referral_message(message: Message, session: AsyncSession, db_user: BotUser) -> None:
    """Legacy reply entry — invite is a subset of customer club."""
    await open_loyalty_referral_message(message, session, db_user, state=None, push=True)


# ---------------------------------------------------------------------------
# Staff reply-keyboard openers
# ---------------------------------------------------------------------------


async def open_admin_loyalty_hub(
    message: Message,
    session: AsyncSession,
    db_user: BotUser,
    state: FSMContext | None = None,
    *,
    is_reseller_bot: bool = False,
    reseller_owner_id: int | None = None,
    push: bool = True,
) -> None:
    from app.bot import menu_nav as nav

    scope_info = await resolve_loyalty_manage_scope(
        session,
        db_user,
        is_reseller_bot=is_reseller_bot,
        reseller_owner_id=reseller_owner_id,
    )
    if scope_info is None:
        await message.answer("دسترسی به مدیریت باشگاه مشتریان ندارید.")
        return
    scope, can_tiers = scope_info
    await ensure_loyalty_defaults(session, reseller_id=scope)
    enabled = await loyalty_enabled(session, reseller_id=scope)
    status = "فعال ✅" if enabled else "غیرفعال ⛔️"
    who = "فروشگاه شما" if scope is not None else "پلتفرم"
    extra = ""
    if not can_tiers:
        extra = "\nسطح‌ها سراسری‌اند و فقط ادمین پلتفرم مدیریت می‌کند."
    await nav.show_nav_keyboard(
        message,
        session,
        db_user,
        nav.NAV_ADMIN_LOYALTY,
        text=(
            f"⭐ <b>باشگاه مشتریان</b> ({who})\n"
            f"وضعیت: <b>{status}</b>\n"
            "از کیبورد پایین بخش را انتخاب کنید؛ جزئیات زیر پیام اینلاین است."
            f"{extra}"
        ),
        state=state,
        push=push,
        is_reseller_bot=is_reseller_bot,
        reseller_owner_id=reseller_owner_id,
    )


async def open_admin_loyalty_overview(
    message: Message,
    session: AsyncSession,
    db_user: BotUser,
    *,
    is_reseller_bot: bool = False,
    reseller_owner_id: int | None = None,
) -> None:
    scope_info = await resolve_loyalty_manage_scope(
        session,
        db_user,
        is_reseller_bot=is_reseller_bot,
        reseller_owner_id=reseller_owner_id,
    )
    if scope_info is None:
        await message.answer("دسترسی ندارید.")
        return
    scope, can_tiers = scope_info
    await ensure_loyalty_defaults(session, reseller_id=scope)
    metrics = await overview_metrics(session, reseller_id=scope)
    enabled = await loyalty_enabled(session, reseller_id=scope)
    lines = [
        kv_line("🔘", "وضعیت", "فعال" if enabled else "غیرفعال"),
        kv_line("👥", "دعوت‌ها", str(metrics.get("total_referrals") or 0)),
        kv_line("✅", "واجد شرایط", str(metrics.get("qualified_referrals") or 0)),
        kv_line("⭐", "امتیاز صادرشده", str(metrics.get("points_issued") or 0)),
        kv_line("♻️", "امتیاز بازخرید", str(metrics.get("points_redeemed") or 0)),
        kv_line("💰", "اعتبار کیف از جایزه", str(metrics.get("wallet_credits_issued") or 0)),
        kv_line("🎁", "جوایز فعال", str(metrics.get("active_rewards") or 0)),
    ]
    await message.answer(
        format_message("📊 نمای کلی باشگاه", "\n".join(lines)),
        reply_markup=kb.admin_loyalty_reply_keyboard(None, include_tiers=can_tiers),
    )


async def _scoped_rules(session: AsyncSession, scope: int | None) -> list[PointsRule]:
    if scope is None:
        q = select(PointsRule).where(PointsRule.reseller_id.is_(None))
    else:
        q = select(PointsRule).where(PointsRule.reseller_id == int(scope))
    return list(
        (
            await session.execute(q.order_by(PointsRule.sort_order.asc(), PointsRule.id.asc()))
        ).scalars().all()
    )


async def _scoped_rewards(session: AsyncSession, scope: int | None) -> list[LoyaltyReward]:
    if scope is None:
        q = select(LoyaltyReward).where(LoyaltyReward.reseller_id.is_(None))
    else:
        q = select(LoyaltyReward).where(LoyaltyReward.reseller_id == int(scope))
    return list(
        (
            await session.execute(
                q.order_by(LoyaltyReward.sort_order.asc(), LoyaltyReward.id.asc())
            )
        ).scalars().all()
    )


def _staff_rules_markup(rules: list[PointsRule]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for r in rules[:20]:
        mark = "✅" if r.enabled else "⛔️"
        label = EVENT_LABELS.get(r.event_key, r.name)[:28]
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{mark} {label}",
                    callback_data=f"loyadm:rule:tog:{r.id}",
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton(text="🔄 تازه‌سازی", callback_data="loyadm:rules")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _staff_rewards_markup(rewards: list[LoyaltyReward]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for r in rewards[:20]:
        if r.archived:
            continue
        mark = "✅" if r.enabled else "⛔️"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{mark} {r.name[:28]}",
                    callback_data=f"loyadm:rew:tog:{r.id}",
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton(text="🔄 تازه‌سازی", callback_data="loyadm:rewards")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def open_admin_loyalty_rules(
    message: Message,
    session: AsyncSession,
    db_user: BotUser,
    *,
    is_reseller_bot: bool = False,
    reseller_owner_id: int | None = None,
) -> None:
    scope_info = await resolve_loyalty_manage_scope(
        session,
        db_user,
        is_reseller_bot=is_reseller_bot,
        reseller_owner_id=reseller_owner_id,
    )
    if scope_info is None:
        await message.answer("دسترسی ندارید.")
        return
    scope, can_tiers = scope_info
    await ensure_loyalty_defaults(session, reseller_id=scope)
    rules = await _scoped_rules(session, scope)
    if not rules:
        body = "قانونی تعریف نشده — پیش‌فرض‌ها را از وب‌پنل هم می‌توانید ببینید."
    else:
        lines = []
        for r in rules:
            ev = EVENT_LABELS.get(r.event_key, r.event_key)
            mode = "به‌ازای گیگ" if r.amount_mode == "per_gb" else "ثابت"
            st = "فعال" if r.enabled else "خاموش"
            lines.append(f"• <b>{r.name}</b>\n  {ev} · {mode}: {r.amount} · {st}")
        body = "\n".join(lines)
    await message.answer(
        format_message("📐 قوانین امتیاز", body + "\n\nبرای روشن/خاموش کردن از دکمه‌های زیر استفاده کنید."),
        reply_markup=kb.admin_loyalty_reply_keyboard(None, include_tiers=can_tiers),
    )
    await message.answer("قوانین:", reply_markup=_staff_rules_markup(rules))


async def open_admin_loyalty_rewards(
    message: Message,
    session: AsyncSession,
    db_user: BotUser,
    *,
    is_reseller_bot: bool = False,
    reseller_owner_id: int | None = None,
) -> None:
    scope_info = await resolve_loyalty_manage_scope(
        session,
        db_user,
        is_reseller_bot=is_reseller_bot,
        reseller_owner_id=reseller_owner_id,
    )
    if scope_info is None:
        await message.answer("دسترسی ندارید.")
        return
    scope, can_tiers = scope_info
    await ensure_loyalty_defaults(session, reseller_id=scope)
    rewards = await _scoped_rewards(session, scope)
    active = [r for r in rewards if not r.archived]
    if not active:
        body = "جایزه‌ای نیست."
    else:
        lines = []
        for r in active:
            tl = REWARD_TYPE_LABELS.get(r.reward_type, r.reward_type)
            st = "فعال" if r.enabled else "خاموش"
            lines.append(
                f"• <b>{r.name}</b>\n  {tl}: {r.reward_value} · {r.points_cost} امتیاز · {st}"
            )
        body = "\n".join(lines)
    await message.answer(
        format_message("🎁 جوایز باشگاه", body + "\n\nافزودن/ویرایش کامل از وب‌پنل؛ اینجا روشن/خاموش."),
        reply_markup=kb.admin_loyalty_reply_keyboard(None, include_tiers=can_tiers),
    )
    await message.answer("جوایز:", reply_markup=_staff_rewards_markup(rewards))


async def open_admin_loyalty_tiers(
    message: Message,
    session: AsyncSession,
    db_user: BotUser,
    *,
    is_reseller_bot: bool = False,
    reseller_owner_id: int | None = None,
) -> None:
    scope_info = await resolve_loyalty_manage_scope(
        session,
        db_user,
        is_reseller_bot=is_reseller_bot,
        reseller_owner_id=reseller_owner_id,
    )
    if scope_info is None:
        await message.answer("دسترسی ندارید.")
        return
    scope, can_tiers = scope_info
    if not can_tiers:
        await message.answer(
            "سطح‌ها سراسری‌اند و فقط ادمین پلتفرم می‌تواند آن‌ها را مدیریت کند.",
            reply_markup=kb.admin_loyalty_reply_keyboard(None, include_tiers=False),
        )
        return
    await ensure_loyalty_defaults(session, reseller_id=scope)
    tiers = list(
        (
            await session.execute(
                select(LoyaltyTier).order_by(LoyaltyTier.sort_order.asc(), LoyaltyTier.id.asc())
            )
        ).scalars().all()
    )
    if not tiers:
        body = "سطحی تعریف نشده."
    else:
        lines = []
        for t in tiers:
            mx = "∞" if t.max_points is None else str(t.max_points)
            lines.append(
                f"• <b>{t.name}</b> — {t.min_points} تا {mx}"
                f" · ضریب {int(t.multiplier_bps or 10000) / 100:.0f}٪"
            )
        body = "\n".join(lines)
    await message.answer(
        format_message(
            "🏅 سطوح باشگاه",
            body + "\n\nویرایش سطوح فقط از وب‌پنل (ادمین پلتفرم).",
        ),
        reply_markup=kb.admin_loyalty_reply_keyboard(None, include_tiers=True),
    )


def _staff_settings_markup(*, enabled: bool) -> InlineKeyboardMarkup:
    mark = "✅ فعال" if enabled else "⛔️ غیرفعال"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"باشگاه: {mark}",
                    callback_data="loyadm:tog:enabled",
                )
            ],
            [
                InlineKeyboardButton(
                    text="✏️ نرخ امتیاز→کیف پول",
                    callback_data="loyadm:edit:rate",
                )
            ],
            [InlineKeyboardButton(text="🔄 تازه‌سازی", callback_data="loyadm:settings")],
        ]
    )


async def open_admin_loyalty_settings(
    message: Message,
    session: AsyncSession,
    db_user: BotUser,
    *,
    is_reseller_bot: bool = False,
    reseller_owner_id: int | None = None,
) -> None:
    scope_info = await resolve_loyalty_manage_scope(
        session,
        db_user,
        is_reseller_bot=is_reseller_bot,
        reseller_owner_id=reseller_owner_id,
    )
    if scope_info is None:
        await message.answer("دسترسی ندارید.")
        return
    scope, can_tiers = scope_info
    await ensure_loyalty_defaults(session, reseller_id=scope)
    enabled = await loyalty_enabled(session, reseller_id=scope)
    rate = await get_setting(
        session, SETTING_POINTS_TO_WALLET_RATE, "100", reseller_id=scope
    )
    body = "\n".join(
        [
            kv_line("🔘", "باشگاه", "فعال" if enabled else "غیرفعال"),
            kv_line("💱", "نرخ امتیاز→تومان", str(rate)),
            "",
            "تغییر وضعیت و نرخ از دکمه‌های اینلاین؛ جزئیات بیشتر در وب‌پنل.",
        ]
    )
    await message.answer(
        format_message("⚙️ تنظیمات باشگاه", body),
        reply_markup=kb.admin_loyalty_reply_keyboard(None, include_tiers=can_tiers),
    )
    await message.answer("تنظیمات:", reply_markup=_staff_settings_markup(enabled=enabled))


async def open_admin_loyalty_ref_text(
    message: Message,
    session: AsyncSession,
    db_user: BotUser,
    state: FSMContext,
    *,
    is_reseller_bot: bool = False,
    reseller_owner_id: int | None = None,
) -> None:
    scope_info = await resolve_loyalty_manage_scope(
        session,
        db_user,
        is_reseller_bot=is_reseller_bot,
        reseller_owner_id=reseller_owner_id,
    )
    if scope_info is None:
        await message.answer("دسترسی ندارید.")
        return
    scope, can_tiers = scope_info
    # Reseller may edit referral text only with shop_settings (same as web panel)
    if scope is not None:
        from app.services.reseller_access import load_reseller_actor
        from app.services.resellers import has_bot_perm

        _, profile = await load_reseller_actor(
            session,
            db_user,
            is_reseller_bot=is_reseller_bot,
            reseller_owner_id=reseller_owner_id,
        )
        if not profile or not (
            has_bot_perm(profile, "loyalty") and has_bot_perm(profile, "shop_settings")
        ):
            await message.answer(
                "ویرایش متن دعوت نیاز به دسترسی «تنظیمات فروشگاه» هم دارد.",
                reply_markup=kb.admin_loyalty_reply_keyboard(None, include_tiers=False),
            )
            return
    cur = await get_setting(session, "referral_text", "", reseller_id=scope)
    preview = (cur or "").strip() or "—"
    if len(preview) > 400:
        preview = preview[:399] + "…"
    await message.answer(
        format_message(
            "📝 متن دعوت",
            f"فعلی:\n<code>{preview}</code>\n\n"
            "متغیرها: <code>{code}</code> و <code>{link}</code>\n"
            "متن جدید را بفرستید یا «انصراف» بزنید.",
        ),
        reply_markup=kb.cancel_reply(),
    )
    await state.set_state(LoyaltyManageStates.edit_referral_text)
    await state.update_data(
        _loy_edit_scope=scope if scope is not None else 0,
        _loy_edit_is_shop=1 if scope is not None else 0,
        _loy_edit_reseller_bot=1 if is_reseller_bot else 0,
        _loy_edit_owner=int(reseller_owner_id or 0),
    )
    _ = can_tiers


# ---------------------------------------------------------------------------
# Customer callbacks (legacy inline)
# ---------------------------------------------------------------------------


@router.callback_query(F.data == "ref:home")
async def referral_home(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    await callback.answer()
    uname = await _bot_username(callback)
    text, link = await build_referral_text(session, db_user, uname)
    share = f"https://t.me/share/url?url={link}&text="
    if callback.message:
        await safe_edit_text(
            callback.message,
            text,
            reply_markup=_ref_keyboard(share_url=share),
        )


@router.callback_query(F.data == "ref:stats")
async def referral_stats_cb(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    await callback.answer()
    stats = await referral_stats(session, db_user.id)
    body = "\n".join(
        [
            kv_line("👤", "کل دعوت‌شده‌ها", str(stats["total"])),
            kv_line("✅", "واجد شرایط", str(stats["qualified"])),
            kv_line("⭐", "امتیاز کسب‌شده", str(stats["earned_points"])),
        ]
    )
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="بازگشت", callback_data="ref:home")],
            [InlineKeyboardButton(text="🏠 خانه", callback_data="menu:home")],
        ]
    )
    if callback.message:
        await safe_edit_text(
            callback.message,
            format_message("📊 آمار دعوت", body),
            reply_markup=markup,
        )


@router.callback_query(F.data == "loy:home")
async def loyalty_home(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    await callback.answer()
    if not await loyalty_enabled(session, reseller_id=db_user.reseller_id):
        if callback.message:
            await safe_edit_text(
                callback.message,
                format_message("⭐ باشگاه مشتریان", "این بخش فعلاً غیرفعال است."),
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(text="🏠 خانه", callback_data="menu:home")]]
                ),
            )
        return
    text = await build_loyalty_text(session, db_user)
    if callback.message:
        await safe_edit_text(callback.message, text, reply_markup=_loy_keyboard())


@router.callback_query(F.data == "loy:rewards")
async def loyalty_rewards(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    await callback.answer()
    await session.refresh(db_user)
    rewards = await list_active_rewards(session, reseller_id=db_user.reseller_id)
    lines = [kv_line("⭐", "امتیاز فعلی", f"<b>{int(db_user.points_balance or 0)}</b>"), ""]
    rows: list[list[InlineKeyboardButton]] = []
    if not rewards:
        lines.append("هنوز جایزه‌ای تعریف نشده است.")
    else:
        for r in rewards:
            type_label = REWARD_TYPE_LABELS.get(r.reward_type, r.reward_type)
            desc = (r.description or "").strip()
            lines.append(
                f"• <b>{r.name}</b>\n"
                f"  {type_label}: {r.reward_value} · هزینه: {r.points_cost} امتیاز"
                + (f"\n  <i>{desc}</i>" if desc else "")
            )
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"دریافت «{r.name}»",
                        callback_data=f"loy:redeem:{r.id}",
                    )
                ]
            )
    rows.append([InlineKeyboardButton(text="بازگشت", callback_data="loy:home")])
    rows.append([InlineKeyboardButton(text="🏠 خانه", callback_data="menu:home")])
    if callback.message:
        await safe_edit_text(
            callback.message,
            format_message("🎁 جوایز", "\n".join(lines)),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )


@router.callback_query(F.data.startswith("loy:redeem:"))
async def loyalty_redeem(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    try:
        reward_id = int(callback.data.split(":")[-1])
    except (TypeError, ValueError):
        await callback.answer("نامعتبر", show_alert=True)
        return

    reward = await session.get(LoyaltyReward, reward_id)
    if not reward or not reward.enabled or reward.archived:
        await callback.answer("جایزه فعال نیست", show_alert=True)
        return

    if reward.reward_type in ("traffic_gb", "time_days"):
        services = list(
            (
                await session.execute(
                    select(UserService)
                    .where(UserService.bot_user_id == db_user.id)
                    .order_by(UserService.id.desc())
                    .limit(10)
                )
            ).scalars().all()
        )
        if not services:
            await callback.answer("سرویس فعالی ندارید", show_alert=True)
            return
        if len(services) == 1:
            await _do_redeem(callback, session, db_user, reward_id, services[0].id)
            return
        rows = [
            [
                InlineKeyboardButton(
                    text=s.pg_username or f"سرویس #{s.id}",
                    callback_data=f"loy:redeemsvc:{reward_id}:{s.id}",
                )
            ]
            for s in services
        ]
        rows.append([InlineKeyboardButton(text="انصراف", callback_data="loy:rewards")])
        await callback.answer()
        if callback.message:
            await safe_edit_text(
                callback.message,
                format_message("🎁 انتخاب سرویس", "سرویسی که جایزه روی آن اعمال شود را انتخاب کنید:"),
                reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
            )
        return

    await _do_redeem(callback, session, db_user, reward_id, None)


@router.callback_query(F.data.startswith("loy:redeemsvc:"))
async def loyalty_redeem_svc(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    parts = (callback.data or "").split(":")
    try:
        reward_id = int(parts[2])
        service_id = int(parts[3])
    except (IndexError, TypeError, ValueError):
        await callback.answer("نامعتبر", show_alert=True)
        return
    await _do_redeem(callback, session, db_user, reward_id, service_id)


async def _do_redeem(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: BotUser,
    reward_id: int,
    service_id: int | None,
) -> None:
    key = f"tg:{callback.id}:{db_user.id}:{reward_id}:{service_id or 0}"
    try:
        red = await redeem_reward(
            session,
            db_user,
            reward_id,
            service_id=service_id,
            idempotency_key=key,
        )
    except ValueError as e:
        await callback.answer(str(e)[:180], show_alert=True)
        return
    except Exception:
        await callback.answer("خطا در بازخرید. دوباره تلاش کنید.", show_alert=True)
        return
    await callback.answer("جایزه با موفقیت دریافت شد ✅", show_alert=True)
    await session.refresh(db_user)
    type_label = REWARD_TYPE_LABELS.get(red.reward_type, red.reward_type)
    lines = [
        "جایزه اعمال شد.",
        kv_line("🎁", "نوع", type_label),
        kv_line("📦", "مقدار", str(red.reward_value)),
        kv_line("⭐", "امتیاز باقی‌مانده", str(int(db_user.points_balance or 0))),
    ]
    if red.reward_type == "discount_percent" and red.discount_code:
        lines.extend(
            [
                "",
                kv_line("🏷", "کد تخفیف", f"<code>{red.discount_code}</code>"),
                "در خرید بعدی از دکمه «کد تخفیف» استفاده کنید.",
            ]
        )
    if callback.message:
        await safe_edit_text(
            callback.message,
            format_message("✅ بازخرید موفق", "\n".join(lines)),
            reply_markup=_loy_keyboard(),
        )


@router.callback_query(F.data == "loy:discounts")
async def loyalty_discounts(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    await callback.answer()
    ents = await list_available_discounts(session, db_user.id)
    if not ents:
        body = "تخفیف فعالی ندارید.\nاز بخش جوایز یک تخفیف بازخرید کنید."
    else:
        lines = []
        for e in ents:
            exp = "بدون انقضا"
            if e.expires_at:
                exp = e.expires_at.strftime("%Y-%m-%d")
            max_d = (
                format_toman(int(e.max_discount_toman), get_settings().currency)
                if e.max_discount_toman is not None
                else "بدون سقف"
            )
            min_p = (
                format_toman(int(e.min_purchase_toman), get_settings().currency)
                if int(e.min_purchase_toman or 0) > 0
                else "—"
            )
            lines.append(
                "\n".join(
                    [
                        f"• <b>{e.percent}٪</b> — کد: <code>{e.code}</code>",
                        f"  انقضا: {exp}",
                        f"  حداقل خرید: {min_p}",
                        f"  سقف تخفیف: {max_d}",
                    ]
                )
            )
        body = "\n\n".join(lines) + "\n\nدر صفحه پرداخت سفارش، کد را وارد کنید."
    if callback.message:
        await safe_edit_text(
            callback.message,
            format_message("🏷 تخفیف‌های من", body),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="بازگشت", callback_data="loy:home")],
                    [InlineKeyboardButton(text="🏠 خانه", callback_data="menu:home")],
                ]
            ),
        )


@router.callback_query(F.data.startswith("loy:hist:"))
async def loyalty_history(callback: CallbackQuery, session: AsyncSession, db_user: BotUser):
    await callback.answer()
    try:
        page = int((callback.data or "loy:hist:0").split(":")[-1])
    except ValueError:
        page = 0
    page = max(0, page)
    limit = 8
    rows = await list_points_history(session, db_user.id, limit=limit, offset=page * limit)
    await session.refresh(db_user)
    if not rows:
        body = "تاریخچه‌ای نیست."
    else:
        lines = []
        for t in rows:
            sign = "+" if t.amount >= 0 else ""
            lines.append(f"{sign}{t.amount} — {t.description or t.tx_type}")
        body = "\n".join(lines)
    body += f"\n\nموجودی فعلی: <b>{int(db_user.points_balance or 0)}</b>"
    nav_btns: list[InlineKeyboardButton] = []
    if page > 0:
        nav_btns.append(InlineKeyboardButton(text="◀️ قبلی", callback_data=f"loy:hist:{page - 1}"))
    if len(rows) >= limit:
        nav_btns.append(InlineKeyboardButton(text="بعدی ▶️", callback_data=f"loy:hist:{page + 1}"))
    kb_rows: list[list[InlineKeyboardButton]] = []
    if nav_btns:
        kb_rows.append(nav_btns)
    kb_rows.append([InlineKeyboardButton(text="بازگشت", callback_data="loy:home")])
    if callback.message:
        await safe_edit_text(
            callback.message,
            format_message("📜 تاریخچه امتیاز", body),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows),
        )


# ---------------------------------------------------------------------------
# Staff inline callbacks
# ---------------------------------------------------------------------------


async def _staff_scope_from_callback(
    session: AsyncSession,
    db_user: BotUser,
    *,
    is_reseller_bot: bool = False,
    reseller_owner_id: int | None = None,
) -> tuple[int | None, bool] | None:
    return await resolve_loyalty_manage_scope(
        session,
        db_user,
        is_reseller_bot=is_reseller_bot,
        reseller_owner_id=reseller_owner_id,
    )


@router.callback_query(F.data == "loyadm:tog:enabled")
async def staff_tog_enabled(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: BotUser,
    is_reseller_bot: bool = False,
    reseller_owner_id: int | None = None,
):
    scope_info = await _staff_scope_from_callback(
        session,
        db_user,
        is_reseller_bot=is_reseller_bot,
        reseller_owner_id=reseller_owner_id,
    )
    if scope_info is None:
        await callback.answer("دسترسی ندارید", show_alert=True)
        return
    scope, _ = scope_info
    cur = await get_setting(session, SETTING_LOYALTY_ENABLED, "1", reseller_id=scope)
    new_val = "0" if on(cur) else "1"
    await set_setting(session, SETTING_LOYALTY_ENABLED, new_val, reseller_id=scope)
    await callback.answer("ذخیره شد")
    if callback.message:
        await safe_edit_text(
            callback.message,
            "تنظیمات باشگاه به‌روز شد.",
            reply_markup=_staff_settings_markup(enabled=new_val == "1"),
        )


@router.callback_query(F.data == "loyadm:settings")
async def staff_settings_refresh(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: BotUser,
    is_reseller_bot: bool = False,
    reseller_owner_id: int | None = None,
):
    await callback.answer()
    scope_info = await _staff_scope_from_callback(
        session,
        db_user,
        is_reseller_bot=is_reseller_bot,
        reseller_owner_id=reseller_owner_id,
    )
    if scope_info is None or not callback.message:
        return
    scope, _ = scope_info
    enabled = await loyalty_enabled(session, reseller_id=scope)
    rate = await get_setting(
        session, SETTING_POINTS_TO_WALLET_RATE, "100", reseller_id=scope
    )
    body = "\n".join(
        [
            kv_line("🔘", "باشگاه", "فعال" if enabled else "غیرفعال"),
            kv_line("💱", "نرخ امتیاز→تومان", str(rate)),
        ]
    )
    await safe_edit_text(
        callback.message,
        format_message("⚙️ تنظیمات باشگاه", body),
        reply_markup=_staff_settings_markup(enabled=enabled),
    )


@router.callback_query(F.data == "loyadm:edit:rate")
async def staff_edit_rate_start(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: BotUser,
    state: FSMContext,
    is_reseller_bot: bool = False,
    reseller_owner_id: int | None = None,
):
    scope_info = await _staff_scope_from_callback(
        session,
        db_user,
        is_reseller_bot=is_reseller_bot,
        reseller_owner_id=reseller_owner_id,
    )
    if scope_info is None:
        await callback.answer("دسترسی ندارید", show_alert=True)
        return
    scope, _ = scope_info
    cur = await get_setting(
        session, SETTING_POINTS_TO_WALLET_RATE, "100", reseller_id=scope
    )
    await callback.answer()
    await state.set_state(LoyaltyManageStates.edit_wallet_rate)
    await state.update_data(
        _loy_edit_scope=scope if scope is not None else 0,
        _loy_edit_is_shop=1 if scope is not None else 0,
        _loy_edit_reseller_bot=1 if is_reseller_bot else 0,
        _loy_edit_owner=int(reseller_owner_id or 0),
    )
    if callback.message:
        await callback.message.answer(
            f"نرخ فعلی: <code>{cur}</code>\nعدد جدید (تومان به‌ازای ۱ امتیاز) را بفرستید:",
            reply_markup=kb.cancel_reply(),
        )


@router.callback_query(F.data.startswith("loyadm:rule:tog:"))
async def staff_rule_toggle(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: BotUser,
    is_reseller_bot: bool = False,
    reseller_owner_id: int | None = None,
):
    scope_info = await _staff_scope_from_callback(
        session,
        db_user,
        is_reseller_bot=is_reseller_bot,
        reseller_owner_id=reseller_owner_id,
    )
    if scope_info is None:
        await callback.answer("دسترسی ندارید", show_alert=True)
        return
    scope, _ = scope_info
    try:
        rid = int((callback.data or "").split(":")[-1])
    except ValueError:
        await callback.answer("نامعتبر", show_alert=True)
        return
    rule = await session.get(PointsRule, rid)
    if not rule or not _rule_in_scope(rule, scope):
        await callback.answer("این قانون در محدوده شما نیست", show_alert=True)
        return
    rule.enabled = not bool(rule.enabled)
    await session.commit()
    await callback.answer("ذخیره شد")
    rules = await _scoped_rules(session, scope)
    if callback.message:
        await safe_edit_text(
            callback.message,
            "قوانین (لمس برای روشن/خاموش):",
            reply_markup=_staff_rules_markup(rules),
        )


@router.callback_query(F.data.startswith("loyadm:rew:tog:"))
async def staff_reward_toggle(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: BotUser,
    is_reseller_bot: bool = False,
    reseller_owner_id: int | None = None,
):
    scope_info = await _staff_scope_from_callback(
        session,
        db_user,
        is_reseller_bot=is_reseller_bot,
        reseller_owner_id=reseller_owner_id,
    )
    if scope_info is None:
        await callback.answer("دسترسی ندارید", show_alert=True)
        return
    scope, _ = scope_info
    try:
        rid = int((callback.data or "").split(":")[-1])
    except ValueError:
        await callback.answer("نامعتبر", show_alert=True)
        return
    reward = await session.get(LoyaltyReward, rid)
    if not reward or not _reward_in_scope(reward, scope):
        await callback.answer("این جایزه در محدوده شما نیست", show_alert=True)
        return
    reward.enabled = not bool(reward.enabled)
    await session.commit()
    await callback.answer("ذخیره شد")
    rewards = await _scoped_rewards(session, scope)
    if callback.message:
        await safe_edit_text(
            callback.message,
            "جوایز (لمس برای روشن/خاموش):",
            reply_markup=_staff_rewards_markup(rewards),
        )


@router.callback_query(F.data == "loyadm:rules")
async def staff_rules_refresh(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: BotUser,
    is_reseller_bot: bool = False,
    reseller_owner_id: int | None = None,
):
    await callback.answer()
    scope_info = await _staff_scope_from_callback(
        session,
        db_user,
        is_reseller_bot=is_reseller_bot,
        reseller_owner_id=reseller_owner_id,
    )
    if scope_info is None or not callback.message:
        return
    scope, _ = scope_info
    rules = await _scoped_rules(session, scope)
    await safe_edit_text(
        callback.message,
        "قوانین (لمس برای روشن/خاموش):",
        reply_markup=_staff_rules_markup(rules),
    )


@router.callback_query(F.data == "loyadm:rewards")
async def staff_rewards_refresh(
    callback: CallbackQuery,
    session: AsyncSession,
    db_user: BotUser,
    is_reseller_bot: bool = False,
    reseller_owner_id: int | None = None,
):
    await callback.answer()
    scope_info = await _staff_scope_from_callback(
        session,
        db_user,
        is_reseller_bot=is_reseller_bot,
        reseller_owner_id=reseller_owner_id,
    )
    if scope_info is None or not callback.message:
        return
    scope, _ = scope_info
    rewards = await _scoped_rewards(session, scope)
    await safe_edit_text(
        callback.message,
        "جوایز (لمس برای روشن/خاموش):",
        reply_markup=_staff_rewards_markup(rewards),
    )


@router.message(LoyaltyManageStates.edit_wallet_rate)
async def staff_save_wallet_rate(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    db_user: BotUser,
    is_reseller_bot: bool = False,
    reseller_owner_id: int | None = None,
):
    text = (message.text or "").strip()
    data = await state.get_data()
    shop = bool(data.get("_loy_edit_is_shop"))
    scope = int(data.get("_loy_edit_scope") or 0) if shop else None
    # Re-check ACL — never trust FSM alone
    scope_info = await resolve_loyalty_manage_scope(
        session,
        db_user,
        is_reseller_bot=bool(data.get("_loy_edit_reseller_bot")) or is_reseller_bot,
        reseller_owner_id=int(data.get("_loy_edit_owner") or 0) or reseller_owner_id,
    )
    if scope_info is None:
        await state.clear()
        await message.answer("دسترسی ندارید.")
        return
    live_scope, can_tiers = scope_info
    if live_scope != scope:
        await state.clear()
        await message.answer("محدوده تنظیمات نامعتبر است.")
        return
    if kb.is_cancel_text(text):
        await state.clear()
        await message.answer(
            "لغو شد.",
            reply_markup=kb.admin_loyalty_reply_keyboard(None, include_tiers=can_tiers),
        )
        return
    raw = text.replace(",", "").replace("٬", "").strip()
    try:
        rate = int(raw)
        if rate < 0:
            raise ValueError("neg")
    except ValueError:
        await message.answer("عدد معتبر بفرستید.")
        return
    await set_setting(
        session, SETTING_POINTS_TO_WALLET_RATE, str(rate), reseller_id=scope
    )
    await state.clear()
    await message.answer(
        f"نرخ ذخیره شد: <b>{rate}</b>",
        reply_markup=kb.admin_loyalty_reply_keyboard(None, include_tiers=can_tiers),
    )


@router.message(LoyaltyManageStates.edit_referral_text)
async def staff_save_referral_text(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    db_user: BotUser,
    is_reseller_bot: bool = False,
    reseller_owner_id: int | None = None,
):
    text = (message.text or "").strip()
    data = await state.get_data()
    shop = bool(data.get("_loy_edit_is_shop"))
    scope = int(data.get("_loy_edit_scope") or 0) if shop else None
    scope_info = await resolve_loyalty_manage_scope(
        session,
        db_user,
        is_reseller_bot=bool(data.get("_loy_edit_reseller_bot")) or is_reseller_bot,
        reseller_owner_id=int(data.get("_loy_edit_owner") or 0) or reseller_owner_id,
    )
    if scope_info is None:
        await state.clear()
        await message.answer("دسترسی ندارید.")
        return
    live_scope, can_tiers = scope_info
    if live_scope != scope:
        await state.clear()
        await message.answer("محدوده تنظیمات نامعتبر است.")
        return
    if scope is not None:
        from app.services.reseller_access import load_reseller_actor
        from app.services.resellers import has_bot_perm

        _, profile = await load_reseller_actor(
            session,
            db_user,
            is_reseller_bot=True,
            reseller_owner_id=live_scope,
        )
        if not profile or not has_bot_perm(profile, "shop_settings"):
            await state.clear()
            await message.answer("دسترسی تنظیمات فروشگاه ندارید.")
            return
    if kb.is_cancel_text(text):
        await state.clear()
        await message.answer(
            "لغو شد.",
            reply_markup=kb.admin_loyalty_reply_keyboard(None, include_tiers=can_tiers),
        )
        return
    if not text:
        await message.answer("متن خالی نباشد.")
        return
    await set_setting(session, "referral_text", text, reseller_id=scope)
    await state.clear()
    await message.answer(
        "متن دعوت ذخیره شد ✅",
        reply_markup=kb.admin_loyalty_reply_keyboard(None, include_tiers=can_tiers),
    )
