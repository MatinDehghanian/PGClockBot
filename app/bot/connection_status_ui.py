"""Safe Persian monitoring presentation and trusted bot Owner identity adapter."""

from __future__ import annotations

import html
from datetime import datetime

from aiogram.filters import BaseFilter
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.auth import resolve_bot_owner_principal
from app.db.models import BotUser
from app.services.authz import authz_from_staff
from app.services.connection_monitor_access import MONITOR_ACCESS_DENIED, MonitorAccess
from app.services.connection_monitor_views import MonitorAdminPage, MonitorTargetView
from app.services.connection_status_texts import REASON_LABELS, STATUS_LABELS as STATUS_LABELS, connection_check_time
from app.services.formatting import format_number
from app.services.org_principals import attach_org_principal_fields
from app.services.safe_format import safe_format
from app.services.users import get_all_settings


class MonitorAdminLabel(BaseFilter):
    async def __call__(self, message: Message, session: AsyncSession, is_reseller_bot: bool = False) -> bool:
        if is_reseller_bot or not message.text:
            return False
        ui = await get_all_settings(session)
        return message.text.strip() == ui["btn_connection_status_admin"].strip()


async def bot_monitor_access(session: AsyncSession, user: BotUser, *, is_reseller_bot: bool) -> MonitorAccess:
    principal = await resolve_bot_owner_principal(session, user, is_reseller_bot=is_reseller_bot)
    if principal is None:
        raise ValueError(MONITOR_ACCESS_DENIED)
    staff = attach_org_principal_fields({"role": "admin"}, principal)
    return MonitorAccess(authz_from_staff(staff), not is_reseller_bot)


def monitor_text(ui: dict[str, str], key: str) -> str:
    return html.escape(safe_format(ui[key]))


def checked_time(value: datetime | None) -> str:
    if value is None:
        return "هنوز نتیجهٔ معتبر ندارد"
    return f"<code>{connection_check_time(value)}</code>"


def button(label: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=label, callback_data=data)


def admin_page_text(page: MonitorAdminPage, ui: dict[str, str]) -> str:
    runtime = "فعال" if page.settings.enabled else "متوقف"
    account = "متصل" if page.settings.has_account else "تنظیم نشده"
    lines = [f"<b>{monitor_text(ui, 'connection_status_admin_title')}</b>", "بررسی از سرور ربات",
             f"تست خودکار: {runtime} | Test user: {account}"]
    if page.settings.username:
        lines.append(f"Username: <code>{html.escape(page.settings.username)}</code>")
    if not page.settings.has_account:
        lines.append("۱. Test user را ثبت کنید. ۲. هاست اضافه کنید. ۳. تست‌ها را روشن کنید.")
    for target in page.targets:
        name = html.escape(target.public_name) or f"هاست {format_number(target.host_id)}"
        lines.append(f"{name}: {STATUS_LABELS[target.health.status]}")
    if not page.targets:
        lines.append("هنوز هاستی انتخاب نشده است.")
    return "\n".join(lines)


def admin_page_keyboard(page: MonitorAdminPage) -> InlineKeyboardMarkup:
    rows = [[button("👤 تنظیم Test user", "cma:account"), button("➕ اضافه کردن هاست", "cma:hosts:0")],
            [button("⏹ توقف تست‌ها" if page.settings.enabled else "▶️ شروع تست‌ها", f"cma:run:{int(not page.settings.enabled)}")]]
    rows.extend([button(target.public_name or f"هاست {format_number(target.host_id)}", f"cma:item:{target.id}")] for target in page.targets)
    if page.next_id is not None:
        rows.append([button("صفحهٔ بعد", f"cma:home:{page.next_id}")])
    rows.append([button("🔄 تازه‌سازی", "cma:home:0")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def target_text(target: MonitorTargetView) -> str:
    name = html.escape(target.public_name) or "تنظیم نشده"
    health = target.health
    delay = f"{format_number(health.delay_ms)} میلی‌ثانیه" if health.delay_ms is not None else "—"
    return "\n".join([
        f"<b>هاست {format_number(target.host_id)}</b> | {STATUS_LABELS[health.status]}",
        "بررسی از سرور ربات", f"نام نمایشی در ربات: {name}", f"نمایش به کاربران: {'روشن' if target.is_public else 'خاموش'}",
        f"ترتیب: {format_number(target.display_order)}", f"Real delay: {delay}",
        f"مسیرهای بررسی‌شده: {format_number(health.covered)}/{format_number(health.expected)}", f"آخرین بررسی: {checked_time(health.checked_at)}",
        REASON_LABELS.get(target.reason, ""),
        "تست در صف است؛ نتیجه بعد از اجرا نمایش داده می‌شود." if target.manual_pending else "با «تست الان» درخواست تست جدید ثبت می‌شود.",
    ])


def target_keyboard(target: MonitorTargetView) -> InlineKeyboardMarkup:
    rows = []
    if target.test_enabled:
        rows = [[button("🔄 تست الان", f"cma:check:{target.id}"), button("⏸ توقف این هاست", f"cma:pause:{target.id}")],
                [button("✏️ نام نمایشی", f"cma:name:{target.id}"), button("ترتیب نمایش", f"cma:order:{target.id}")],
                [button("🙈 مخفی از کاربران" if target.is_public else "👁 نمایش به کاربران", f"cma:public:{target.id}:{int(not target.is_public)}")]]
    else:
        rows = [[button("▶️ فعال کردن تست هاست", f"cma:select:{target.host_id}")]]
    rows.append([button("بازگشت", "cma:home:0")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
