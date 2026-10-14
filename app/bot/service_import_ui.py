"""Shared pieces of the «افزودن سرویس قبلی» entry point in the customer's service list."""

from __future__ import annotations

from collections.abc import Mapping

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.keyboards import _ikb, _style
from app.services.service_import import SETTING_KEY
from app.services.users import on

ADD_CALLBACK = "svc:add"
ADD_BUTTON_LABEL = "➕ افزودن سرویس قبلی"
EMPTY_LIST_HINT = "اگر سرویسی بیرون از ربات گرفته‌اید، با لینک اشتراک آن را اضافه کنید."


def import_enabled(ui: Mapping[str, str] | None) -> bool:
    return on((ui or {}).get(SETTING_KEY, "0"))


def add_existing_row(ui: dict | None) -> list[InlineKeyboardButton]:
    return [_ikb(ADD_BUTTON_LABEL, callback_data=ADD_CALLBACK, ui=ui, style=_style(ui, "svc_add_existing"))]


def empty_services_keyboard(ui: dict | None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[add_existing_row(ui)])
