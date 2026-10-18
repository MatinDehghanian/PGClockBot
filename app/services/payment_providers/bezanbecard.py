"""BezanBeCard (بزن به کارت) HTTP client — create order + verify by re-fetch.

Security rules:
  - Never trust a callback body alone; always re-fetch order status with the
    merchant API key before settling.
  - Amounts on the wire are Iranian Rial; the bot stores catalog amounts in Toman.
  - Fail closed on missing credentials, unknown tokens, or non-paid statuses.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

API_BASE = "https://bezanbecard.ir"
PROVIDER_NAME = "bezanbecard"

# Shown in web panel field help and Telegram settings intro (HTML-safe, no secrets).
SETUP_HELP_FA = (
    "سایت: https://bezanbecard.ir\n"
    "آموزش کوتاه:\n"
    "۱) در سایت ثبت‌نام کنید\n"
    "۲) کارت مقصد را در داشبورد ثبت کنید\n"
    "۳) طرح دارای API بگیرید (طرح رایگان API ندارد)\n"
    "۴) کلید API بسازید و در تنظیمات ربات بگذارید\n"
    "۵) روش «بزن به کارت» را روشن کنید\n\n"
    "تأیید و تحویل سرویس در این ربات فقط از مسیر API انجام می‌شود "
    "(callback + استعلام مجدد + پایش خودکار).\n"
    "اعلان تلگرام و تأیید دستی/اپ در حساب بزن به کارت فقط برای اطلاع یا "
    "تأیید سمت همان سرویس است؛ اگر آنجا سفارش را paid کنید، ربات با استعلام "
    "API همان را می‌فهمد و تحویل می‌دهد — نیازی به اتصال جداگانه نیست."
)

SETUP_HELP_HTML = (
    "سایت: <code>https://bezanbecard.ir</code>\n"
    "<b>آموزش کوتاه</b>\n"
    "۱) در سایت ثبت‌نام کنید\n"
    "۲) کارت مقصد را در داشبورد ثبت کنید\n"
    "۳) طرح دارای API بگیرید (طرح رایگان API ندارد)\n"
    "۴) کلید API بسازید و اینجا بگذارید\n"
    "۵) روش «بزن به کارت» را روشن کنید\n\n"
    "تأیید و تحویل در ربات از <b>API</b> است.\n"
    "اعلان تلگرام / تأیید دستی یا اپ بزن به کارت اختیاری‌اند و جایگزین "
    "تأیید ربات نیستند؛ اگر آنجا paid شود، ربات با استعلام API تحویل می‌دهد."
)
STATUS_PAID = "paid"
STATUS_PENDING = "pending"
STATUS_NEEDS_REVIEW = "needs_review"
STATUS_EXPIRED = "expired"
_TIMEOUT = httpx.Timeout(20.0, connect=10.0)
_MIN_RIAL = 10_000
_MAX_RIAL = 1_000_000_000


@dataclass(frozen=True, slots=True)
class BbcCreateResult:
    order_id: str
    payment_token: str
    payment_url: str
    unique_amount_rial: int
    base_amount_rial: int
    status: str
    raw: dict[str, Any]


@dataclass(frozen=True, slots=True)
class BbcOrderStatus:
    order_id: str
    payment_token: str
    status: str
    unique_amount_rial: int | None
    base_amount_rial: int | None
    merchant_order_id: str | None
    raw: dict[str, Any]


def toman_to_rial(amount_toman: int) -> int:
    """Catalog amounts are Toman; BezanBeCard expects Rial (×10)."""
    try:
        toman = int(amount_toman)
    except (TypeError, ValueError) as exc:
        raise ValueError("مبلغ نامعتبر") from exc
    if isinstance(amount_toman, bool) or toman <= 0:
        raise ValueError("مبلغ نامعتبر")
    rial = toman * 10
    if rial < _MIN_RIAL:
        raise ValueError("مبلغ کمتر از حداقل درگاه بزن به کارت است")
    if rial > _MAX_RIAL:
        raise ValueError("مبلغ بیشتر از سقف درگاه بزن به کارت است")
    return rial


def format_unique_rial(amount_rial: int) -> str:
    """Exact transfer amount for the payer (Rial — unique suffix must stay intact)."""
    from app.services.formatting import format_number

    return f"\u200f{format_number(int(amount_rial))} ریال"


def _headers(api_key: str, *, idempotency_key: str | None = None) -> dict[str, str]:
    key = (api_key or "").strip()
    if not key or len(key) < 8:
        raise ValueError("کلید API بزن به کارت تنظیم نشده")
    headers = {
        "x-api-key": key,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key[:255]
    return headers


def _safe_error_detail(data: Any) -> str:
    if isinstance(data, dict):
        detail = data.get("detail") or data.get("message") or data.get("code")
        if detail:
            return str(detail)[:200]
    return "خطا در ارتباط با بزن به کارت"


async def create_order(
    *,
    api_key: str,
    amount_toman: int,
    merchant_order_id: str,
    callback_url: str,
    return_url: str | None = None,
    description: str = "",
    idempotency_key: str | None = None,
    expiry_minutes: int | None = None,
) -> BbcCreateResult:
    amount_rial = toman_to_rial(amount_toman)
    payload: dict[str, Any] = {
        "amount": amount_rial,
        "merchant_order_id": str(merchant_order_id)[:64],
        "callback_url": callback_url[:2048],
        "description": (description or "")[:500],
    }
    if return_url:
        payload["return_url"] = str(return_url)[:2048]
    if expiry_minutes is not None:
        mins = int(expiry_minutes)
        if 15 <= mins <= 120:
            payload["expiry_minutes"] = mins

    url = f"{API_BASE}/api/v1/public/orders"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                url,
                headers=_headers(api_key, idempotency_key=idempotency_key),
                json=payload,
            )
            data = resp.json() if resp.content else {}
    except httpx.HTTPError as exc:
        logger.warning("bezanbecard create_order network error: %s", exc)
        raise ValueError("خطا در ارتباط با بزن به کارت") from None

    if resp.status_code >= 400 or not isinstance(data, dict):
        raise ValueError(_safe_error_detail(data) if isinstance(data, dict) else "ساخت سفارش ناموفق بود")

    token = str(data.get("payment_token") or "").strip()
    pay_url = str(data.get("payment_url") or "").strip()
    try:
        unique = int(data.get("unique_amount"))
    except (TypeError, ValueError):
        unique = 0
    try:
        base = int(data.get("base_amount") or amount_rial)
    except (TypeError, ValueError):
        base = amount_rial
    order_id = str(data.get("order_id") or "").strip()
    status = str(data.get("status") or STATUS_PENDING).strip().lower()

    if not token or not pay_url or unique <= 0 or not order_id:
        raise ValueError("پاسخ بزن به کارت ناقص بود")
    if not (pay_url.startswith("https://") or pay_url.startswith("http://")):
        raise ValueError("لینک پرداخت نامعتبر است")

    return BbcCreateResult(
        order_id=order_id[:128],
        payment_token=token[:128],
        payment_url=pay_url[:2048],
        unique_amount_rial=unique,
        base_amount_rial=base,
        status=status,
        raw=data,
    )


async def get_order(*, api_key: str, payment_token: str) -> BbcOrderStatus:
    token = (payment_token or "").strip()
    if not token or len(token) > 128:
        raise ValueError("توکن پرداخت نامعتبر است")
    url = f"{API_BASE}/api/v1/public/orders/{token}"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(url, headers=_headers(api_key))
            data = resp.json() if resp.content else {}
    except httpx.HTTPError as exc:
        logger.warning("bezanbecard get_order network error: %s", exc)
        raise ValueError("خطا در استعلام بزن به کارت") from None

    if resp.status_code == 404:
        raise ValueError("سفارش بزن به کارت یافت نشد")
    if resp.status_code >= 400 or not isinstance(data, dict):
        raise ValueError(_safe_error_detail(data) if isinstance(data, dict) else "استعلام ناموفق بود")

    status = str(data.get("status") or "").strip().lower()
    unique = data.get("unique_amount")
    base = data.get("base_amount")
    try:
        unique_i = int(unique) if unique is not None else None
    except (TypeError, ValueError):
        unique_i = None
    try:
        base_i = int(base) if base is not None else None
    except (TypeError, ValueError):
        base_i = None
    merchant = data.get("merchant_order_id")
    merchant_s = str(merchant).strip() if merchant is not None else None

    return BbcOrderStatus(
        order_id=str(data.get("order_id") or "")[:128],
        payment_token=token[:128],
        status=status,
        unique_amount_rial=unique_i,
        base_amount_rial=base_i,
        merchant_order_id=merchant_s[:64] if merchant_s else None,
        raw=data,
    )


async def ping_account(*, api_key: str) -> dict[str, Any]:
    """Lightweight credential check for settings UI (fail-closed)."""
    url = f"{API_BASE}/api/v1/public/me"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(url, headers=_headers(api_key))
            data = resp.json() if resp.content else {}
    except httpx.HTTPError as exc:
        logger.warning("bezanbecard ping network error: %s", exc)
        raise ValueError("خطا در ارتباط با بزن به کارت") from None
    if resp.status_code >= 400 or not isinstance(data, dict):
        raise ValueError(_safe_error_detail(data) if isinstance(data, dict) else "کلید API نامعتبر است")
    if not data.get("merchant_id"):
        raise ValueError("کلید API نامعتبر است")
    return data
