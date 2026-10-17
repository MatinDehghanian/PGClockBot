"""Bot screens whose button texts and colors can be edited, and how to build them.

Each screen names the real keyboard builder it shows. ``screen_buttons`` builds
that keyboard while recording button sources and returns every button in
display order with the settings behind its text and color, so an editor based
on this list edits exactly the menu the user was looking at.

Screens that are a step inside an input flow (amount entry, payment method
pick, confirmations) are deliberately absent: opening an editor there would
drop the flow's state.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup

from app.bot import nav_inline as hubs
from app.bot import reply_keyboards as rk
from app.bot.button_sources import recording_button_sources
from app.services.button_styles import CATALOG_IDS, STYLE_ALIASES, resolve_style_id, setting_key

Markup = InlineKeyboardMarkup | ReplyKeyboardMarkup

# Screen ids travel in callback data (64-byte limit), so keep them short.
SCREEN_ID_MAX_LENGTH = 24


class Audience(StrEnum):
    """Who sees the screen; decides which editor permissions apply later."""

    CUSTOMER = "customer"
    RESELLER = "reseller"
    ADMIN = "admin"


@dataclass(frozen=True, slots=True)
class ScreenContext:
    """What a screen builder needs: the viewer's settings and, for shop panels, the shop."""

    ui: dict[str, str]
    profile: Any = None


@dataclass(frozen=True, slots=True)
class ScreenSpec:
    id: str
    title: str
    audience: Audience
    build: Callable[[ScreenContext], Markup]


@dataclass(frozen=True, slots=True)
class ScreenButton:
    """One button as shown, with the settings that control it (None = fixed in code)."""

    row: int
    column: int
    text: str
    label_key: str | None
    style_id: str | None

    @property
    def style_setting_key(self) -> str | None:
        return setting_key(self.style_id) if self.style_id else None

    @property
    def is_editable(self) -> bool:
        return self.label_key is not None or self.style_id is not None


def _customer_screens() -> list[ScreenSpec]:
    return [
        ScreenSpec(
            "c.main",
            "منوی اصلی",
            Audience.CUSTOMER,
            lambda ctx: rk.main_reply_keyboard("user", has_services=True, ui=ctx.ui),
        ),
        ScreenSpec("c.wallet", "کیف پول", Audience.CUSTOMER, lambda ctx: hubs.wallet_hub_keyboard(ctx.ui)),
        ScreenSpec("c.support", "پشتیبانی", Audience.CUSTOMER, lambda ctx: hubs.support_hub_keyboard(ctx.ui)),
        ScreenSpec("c.loyalty", "باشگاه مشتریان", Audience.CUSTOMER, lambda ctx: hubs.loyalty_hub_keyboard(ctx.ui)),
        ScreenSpec(
            "c.services",
            "سرویس‌های من",
            Audience.CUSTOMER,
            lambda ctx: hubs.services_list_keyboard([], ctx.ui, allow_import=True),
        ),
        ScreenSpec(
            "c.service",
            "کارت سرویس",
            Audience.CUSTOMER,
            lambda ctx: hubs.service_card_keyboard(0, ctx.ui),
        ),
    ]


def _admin_screens() -> list[ScreenSpec]:
    def admin(screen_id: str, title: str, build: Callable[[ScreenContext], Markup]) -> ScreenSpec:
        return ScreenSpec(screen_id, title, Audience.ADMIN, build)

    return [
        admin("a.home", "پنل ادمین", lambda ctx: hubs.admin_groups_hub_keyboard(ctx.ui)),
        admin("a.ops", "عملیات روزانه", lambda ctx: hubs.admin_ops_hub_keyboard(ctx.ui)),
        admin("a.people", "کاربران و نمایندگان", lambda ctx: hubs.admin_people_hub_keyboard(ctx.ui)),
        admin("a.product", "محصول و پنل", lambda ctx: hubs.admin_product_hub_keyboard(ctx.ui)),
        admin("a.marketing", "بازاریابی", lambda ctx: hubs.admin_marketing_hub_keyboard(ctx.ui)),
        admin("a.system", "سیستم", lambda ctx: hubs.admin_system_hub_keyboard(ctx.ui)),
        admin("a.pg", "پاسارگارد", lambda ctx: hubs.pg_hub_keyboard(ctx.ui)),
        admin("a.loyalty", "مدیریت باشگاه", lambda ctx: hubs.admin_loyalty_manage_hub_keyboard(ctx.ui)),
        admin("a.users", "کاربران", lambda ctx: hubs.admin_users_hub_keyboard(ctx.ui)),
        admin("a.resellers", "نمایندگان", lambda ctx: hubs.admin_resellers_hub_keyboard(ctx.ui)),
        admin("a.settings", "تنظیمات", lambda ctx: hubs.admin_settings_hub_keyboard(ctx.ui)),
        admin("a.backup", "بکاپ", lambda ctx: hubs.admin_backup_hub_keyboard(ctx.ui)),
        admin("a.broadcast", "پیام همگانی", lambda ctx: hubs.admin_broadcast_hub_keyboard(ctx.ui)),
        admin("a.plans", "پلن‌ها", lambda ctx: hubs.admin_plans_audience_hub_keyboard(ctx.ui)),
        admin(
            "a.plans.users",
            "پلن‌های کاربران",
            lambda ctx: hubs.admin_plans_kind_hub_keyboard("users", ctx.ui),
        ),
        admin(
            "a.plans.resellers",
            "پلن‌های نمایندگان",
            lambda ctx: hubs.admin_plans_kind_hub_keyboard("resellers", ctx.ui),
        ),
    ]


def _reseller_screens() -> list[ScreenSpec]:
    return [
        ScreenSpec(
            "r.home",
            "پنل نماینده",
            Audience.RESELLER,
            lambda ctx: hubs.reseller_manage_hub_keyboard(ctx.profile, ctx.ui),
        ),
        ScreenSpec(
            "r.settings",
            "تنظیمات فروشگاه",
            Audience.RESELLER,
            lambda ctx: hubs.reseller_settings_hub_keyboard(ctx.ui),
        ),
        ScreenSpec(
            "r.plans",
            "پلن‌های فروش",
            Audience.RESELLER,
            lambda ctx: hubs.reseller_plans_hub_keyboard(ctx.ui),
        ),
    ]


SCREENS: dict[str, ScreenSpec] = {
    spec.id: spec for spec in [*_customer_screens(), *_admin_screens(), *_reseller_screens()]
}


def _rows(markup: Markup) -> list[list[Any]]:
    if isinstance(markup, InlineKeyboardMarkup):
        return markup.inline_keyboard
    return markup.keyboard


def _catalog_style_id(style_id: str | None) -> str | None:
    # A color id outside the catalog has no default or settings row, so it is not offered.
    return style_id if style_id in CATALOG_IDS else None


def screen_buttons(screen_id: str, ctx: ScreenContext) -> list[ScreenButton]:
    """Every button of the screen in display order, with the settings behind it."""
    spec = SCREENS.get(screen_id)
    if spec is None:
        raise ValueError(f"unknown screen {screen_id!r}")
    with recording_button_sources() as log:
        markup = spec.build(ctx)
    buttons: list[ScreenButton] = []
    for row_index, row in enumerate(_rows(markup)):
        for column_index, button in enumerate(row):
            source = log.source_of(button)
            buttons.append(
                ScreenButton(
                    row=row_index,
                    column=column_index,
                    text=button.text,
                    label_key=source.label_key if source else None,
                    style_id=_catalog_style_id(source.style_id if source else None),
                )
            )
    return buttons


def style_ids_sharing_setting(style_id: str) -> tuple[str, ...]:
    """Every catalog id whose color is stored in the same setting as *style_id*."""
    target = resolve_style_id(style_id)
    sharing = {target} | {alias for alias, canonical in STYLE_ALIASES.items() if canonical == target}
    return tuple(sorted(sharing))
