"""Validate accessible test users without requiring a panel Owner identity."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

from app.services.credential_policy import validate_pg_username
from app.services.formatting import parse_expire
from app.services.pasarguard import PasarGuardError, get_pg
from app.services.service_import import parse_subscription_token


ACCOUNT_UNAVAILABLE = "Test user تنظیم نشده یا قابل استفاده نیست؛ دوباره آن را ثبت کنید."
ACCOUNT_MESSAGES = {
    "invalid_username": "فقط username معتبر Test user را بفرستید؛ لینک یا password لازم نیست.",
    "not_found": "این username در پنل پیدا نشد؛ نام دقیق آن را از PasarGuard کپی کنید.",
    "panel_denied": "دسترسی API ربات به این user کافی نیست؛ دسترسی اکانت متصل به پنل را بررسی کنید.",
    "panel_timeout": "پنل در زمان تعیین‌شده پاسخ نداد؛ کمی بعد دوباره تلاش کنید.",
    "panel_unavailable": "ارتباط با پنل برقرار نشد؛ تنظیمات اتصال PasarGuard را بررسی کنید.",
    "invalid_record": "اطلاعات Test user از پنل کامل یا معتبر نیست.",
    "inactive": "Test user فعال نیست؛ ابتدا وضعیت آن را در پنل روی active بگذارید.",
    "traffic_exhausted": "حجم Test user تمام شده؛ ابتدا حجم آن را در پنل افزایش دهید.",
    "expired": "تاریخ Test user گذشته؛ ابتدا آن را در پنل تمدید کنید.",
    "invalid_subscription": "لینک subscription این user در پاسخ پنل معتبر نیست؛ تنظیمات subscription پنل را بررسی کنید.",
    "customer_account": "این user به سرویس مشتری وصل است؛ یک user جدا برای تست اتصال انتخاب کنید.",
    "secret_unavailable": "ذخیره یا خواندن امن Test user ممکن نشد؛ تنظیم WEB_SECRET سرور را بررسی کنید.",
    "account_changed": "Test user یا لینک subscription آن تغییر کرده؛ username را دوباره ثبت کنید.",
}


class MonitorAccountError(ValueError):
    """Carry a fixed reason, never a panel response or subscription token."""

    def __init__(self, code: str) -> None:
        self.code = code if code in ACCOUNT_MESSAGES else "invalid_record"
        super().__init__(ACCOUNT_MESSAGES[self.code])


@dataclass(frozen=True, slots=True)
class ValidatedMonitorAccount:
    user_id: int
    username: str
    token: str = field(repr=False)


def validate_monitor_username(username: str) -> str:
    if not isinstance(username, str) or not 1 <= len(username) <= 128 or username != username.strip():
        raise MonitorAccountError("invalid_username")
    cleaned, error = validate_pg_username(username)
    if error or cleaned != username:
        raise MonitorAccountError("invalid_username")
    return cleaned


def validate_monitor_account(record: object, *, username: str) -> ValidatedMonitorAccount:
    if not isinstance(record, dict) or not isinstance(record.get("username"), str):
        raise MonitorAccountError("invalid_record")
    actual_username = validate_monitor_username(record["username"])
    if actual_username.casefold() != username.casefold():
        raise MonitorAccountError("account_changed")
    user_id = record.get("id")
    if type(user_id) is not int or not 1 <= user_id <= 2147483647:
        raise MonitorAccountError("invalid_record")
    if record.get("status") != "active":
        raise MonitorAccountError("inactive")
    _validate_capacity(record)
    subscription_url = record.get("subscription_url")
    token = parse_subscription_token(subscription_url) if isinstance(subscription_url, str) else None
    if not token:
        raise MonitorAccountError("invalid_subscription")
    return ValidatedMonitorAccount(user_id, actual_username, token)


def _validate_capacity(record: dict[str, Any]) -> None:
    used, limit = record.get("used_traffic"), record.get("data_limit")
    maximum = 9223372036854775807
    if type(used) is not int or not 0 <= used <= maximum:
        raise MonitorAccountError("invalid_record")
    if limit is not None and (type(limit) is not int or not 0 <= limit <= maximum):
        raise MonitorAccountError("invalid_record")
    if limit and used >= limit:
        raise MonitorAccountError("traffic_exhausted")
    expire = record.get("expire")
    if expire is None or (type(expire) is int and expire == 0):
        return
    if type(expire) not in (int, str):
        raise MonitorAccountError("invalid_record")
    try:
        parsed = parse_expire(expire)
    except (ValueError, OverflowError, OSError):
        raise MonitorAccountError("invalid_record") from None
    if parsed is None or parsed.tzinfo is None:
        raise MonitorAccountError("invalid_record")
    if parsed <= datetime.now(timezone.utc):
        raise MonitorAccountError("expired")


def panel_account_error(error: Exception) -> MonitorAccountError:
    if isinstance(error, (TimeoutError, httpx.TimeoutException)):
        return MonitorAccountError("panel_timeout")
    if isinstance(error, PasarGuardError):
        if error.status_code == 404:
            return MonitorAccountError("not_found")
        if error.status_code in (401, 403):
            return MonitorAccountError("panel_denied")
    return MonitorAccountError("panel_unavailable")


async def read_monitor_account(username: str) -> ValidatedMonitorAccount:
    try:
        async with asyncio.timeout(5):
            record = await get_pg().get_user_by_username(username)
    except (PasarGuardError, httpx.HTTPError, TimeoutError) as exc:
        raise panel_account_error(exc) from None
    return validate_monitor_account(record, username=username)
