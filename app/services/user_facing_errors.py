"""Map internal deny/error codes to short Persian copy the user can act on."""

from __future__ import annotations

_MAP = {
    "pg_outage": "پاسارگارد الان در دسترس نیست. چند دقیقه دیگر دوباره تلاش کنید یا با پشتیبانی بگویید.",
    "pg_capabilities_unavailable": "دسترسی پاسارگارد الان خوانده نشد. کمی بعد دوباره تلاش کنید.",
    "pg_forbidden": "برای این کار دسترسی ندارید.",
    "not_authenticated": "نشست شما منقضی شده. دوباره وارد شوید.",
    "shop_maintenance": "فروشگاه موقتاً در حال به‌روزرسانی است. تمدید و پشتیبانی فعال است.",
    "wallet_empty": "موجودی کیف پول کافی نیست. اول شارژ کنید، بعد خرید را تکرار کنید.",
    "pay_disabled": "این روش پرداخت الان خاموش است. روش دیگری را انتخاب کنید.",
    "plan_inactive": "این پلن الان فعال نیست. پلن دیگری را انتخاب کنید.",
    "delivery_failed": "پرداخت ثبت شد ولی تحویل کامل نشد. از پشتیبانی پیگیری کنید.",
}


def user_facing_error(reason: str | None, *, fallback: str | None = None) -> str:
    key = str(reason or "").strip()
    if key in _MAP:
        return _MAP[key]
    text = (fallback or "").strip()
    if text and "\n" not in text and len(text) <= 180 and "Traceback" not in text:
        return text
    return "الان امکان انجام این کار نیست. کمی بعد دوباره تلاش کنید."
