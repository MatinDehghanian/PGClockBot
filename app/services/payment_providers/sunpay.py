"""SunPay PSP adapter — request → redirect → callback → verify (amounts in Toman).

Follows the SunPay merchant API:
  GET  {PAY_URL}/api/request   JSON body → token
  GET  {PAY_URL}/pay/{token}   browser checkout
  GET/POST {PAY_URL}/api/verified  JSON body → amount/reference (read-only)

Verify never cancels or refunds; callers must match amount and invoice_id locally.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

import httpx

from app.services.payment_providers.base import CheckoutRequest, CheckoutResult, VerifyResult

logger = logging.getLogger(__name__)

MIN_AMOUNT_TOMAN = 1000
_HTTP_TIMEOUT = 20.0
_PLACEHOLDER_KEYS = frozenset(
    {"", "changeme", "your-api-key", "YOUR_API_KEY", "your_api_key"}
)


def _is_success_flag(raw: Any) -> bool:
    """SunPay callback/API success: 1 / \"1\" / true."""
    if raw is True:
        return True
    if raw is False or raw is None:
        return False
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return int(raw) == 1
    text = str(raw).strip().lower()
    return text in {"1", "true", "yes", "ok", "success"}


def _is_http_url(value: str) -> bool:
    try:
        parts = urlparse(value)
    except Exception:
        return False
    return parts.scheme in {"http", "https"} and bool(parts.netloc)


def _safe_int(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{field} نامعتبر است")
    if isinstance(value, float) and not value.is_integer():
        raise ValueError(f"{field} باید عدد صحیح باشد")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} نامعتبر است") from exc
    return number


def _api_error_text(data: Any) -> str:
    if not isinstance(data, dict):
        return "پاسخ نامعتبر درگاه سان‌پی"
    err = data.get("error")
    if isinstance(err, dict):
        code = str(err.get("code") or "").strip()
        if code:
            return f"خطای درگاه سان‌پی ({code})"
    return "درخواست سان‌پی ناموفق بود"


class SunPayAdapter:
    name = "sunpay"

    def __init__(self, *, api_key: str, pay_url: str):
        self.api_key = (api_key or "").strip()
        self.pay_url = (pay_url or "").strip().rstrip("/")

    def _require_config(self) -> None:
        if self.api_key in _PLACEHOLDER_KEYS:
            raise ValueError("کلید API سان‌پی تنظیم نشده")
        if not self.pay_url or not _is_http_url(self.pay_url):
            raise ValueError("آدرس پایه سان‌پی (PAY_URL) تنظیم نشده")

    def _request_url(self) -> str:
        return f"{self.pay_url}/api/request"

    def _verify_url(self) -> str:
        return f"{self.pay_url}/api/verified"

    def checkout_page_url(self, token: str) -> str:
        return f"{self.pay_url}/pay/{token}"

    async def create_checkout(self, req: CheckoutRequest) -> CheckoutResult:
        self._require_config()
        amount = _safe_int(req.amount, field="مبلغ")
        if amount < MIN_AMOUNT_TOMAN:
            raise ValueError(f"حداقل مبلغ سان‌پی {MIN_AMOUNT_TOMAN} تومان است")
        invoice_id = _safe_int(req.settlement_id, field="invoice_id")
        if invoice_id <= 0:
            raise ValueError("invoice_id باید بزرگ‌تر از صفر باشد")
        callback = (req.callback_url or "").strip()
        if not _is_http_url(callback):
            raise ValueError("آدرس بازگشت سان‌پی نامعتبر است")

        payload = {
            "api_key": self.api_key,
            "callback": callback,
            "amount": amount,
            "invoice_id": invoice_id,
        }
        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                # Documented as GET with JSON body + Content-Type: application/json.
                resp = await client.request(
                    "GET",
                    self._request_url(),
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                data = resp.json() if resp.content else {}
        except httpx.HTTPError as exc:
            logger.warning("sunpay request network error: %s", exc)
            raise ValueError("خطا در ارتباط با درگاه سان‌پی") from exc
        except ValueError as exc:
            # resp.json() decode failure
            logger.warning("sunpay request non-json response: %s", exc)
            raise ValueError("پاسخ نامعتبر درگاه سان‌پی") from exc

        if not isinstance(data, dict) or not _is_success_flag(data.get("success")):
            raise ValueError(_api_error_text(data))
        result = data.get("data") if isinstance(data.get("data"), dict) else {}
        token = str((result or {}).get("token") or "").strip()
        if not token:
            raise ValueError("توکن پرداخت سان‌پی دریافت نشد")
        return CheckoutResult(
            external_ref=token,
            checkout_url=self.checkout_page_url(token),
            raw=data,
        )

    async def verify(
        self,
        *,
        external_ref: str,
        amount: int,
        callback_params: dict[str, Any],
    ) -> VerifyResult:
        token = str(external_ref or "").strip()
        cb_token = str(callback_params.get("token") or "").strip()
        if cb_token and token and cb_token.lower() != token.lower():
            return VerifyResult(
                ok=False,
                external_ref=token,
                message="توکن تراکنش با تسویه هم‌خوانی ندارد",
            )
        if cb_token and not token:
            token = cb_token
        if not token:
            return VerifyResult(ok=False, external_ref="", message="توکن تراکنش موجود نیست")

        # Docs §5.1: only look up / verify when callback success=1.
        if "success" not in callback_params or not _is_success_flag(
            callback_params.get("success")
        ):
            return VerifyResult(
                ok=False,
                external_ref=token,
                message="پرداخت توسط کاربر تکمیل نشد",
            )

        try:
            expected_amount = _safe_int(amount, field="مبلغ")
        except ValueError as exc:
            return VerifyResult(ok=False, external_ref=token, message=str(exc))

        if self.api_key in _PLACEHOLDER_KEYS or not self.pay_url:
            return VerifyResult(
                ok=False,
                external_ref=token,
                message="کلید API سان‌پی تنظیم نشده",
            )

        payload = {"api_key": self.api_key, "token": token}
        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                # Docs allow GET or POST; POST keeps the JSON body reliable.
                resp = await client.request(
                    "POST",
                    self._verify_url(),
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                data = resp.json() if resp.content else {}
        except httpx.HTTPError as exc:
            logger.warning("sunpay verify network error: %s", exc)
            return VerifyResult(
                ok=False,
                external_ref=token,
                message="خطا در ارتباط با درگاه سان‌پی",
            )
        except ValueError:
            logger.warning("sunpay verify non-json response")
            return VerifyResult(
                ok=False,
                external_ref=token,
                message="پاسخ نامعتبر درگاه سان‌پی",
            )

        if not isinstance(data, dict) or not _is_success_flag(data.get("success")):
            return VerifyResult(
                ok=False,
                external_ref=token,
                message=_api_error_text(data),
                raw=data if isinstance(data, dict) else None,
            )

        result = data.get("data") if isinstance(data.get("data"), dict) else {}
        try:
            paid_amount = _safe_int((result or {}).get("amount"), field="مبلغ")
        except ValueError:
            return VerifyResult(
                ok=False,
                external_ref=token,
                message="مبلغ تأییدشده نامعتبر است",
                raw=data,
            )
        if paid_amount != expected_amount:
            return VerifyResult(
                ok=False,
                external_ref=token,
                amount=paid_amount,
                message="مبلغ تأییدشده با سفارش هم‌خوانی ندارد",
                raw=data,
            )

        # Optional invoice_id from verify payload — must match callback when both present.
        raw_invoice = (result or {}).get("invoice_id")
        cb_invoice = callback_params.get("invoice_id")
        if raw_invoice is not None and cb_invoice is not None and str(cb_invoice).strip():
            try:
                if _safe_int(raw_invoice, field="invoice_id") != _safe_int(
                    cb_invoice, field="invoice_id"
                ):
                    return VerifyResult(
                        ok=False,
                        external_ref=token,
                        amount=paid_amount,
                        message="شناسه فاکتور با پاسخ درگاه هم‌خوانی ندارد",
                        raw=data,
                    )
            except ValueError as exc:
                return VerifyResult(
                    ok=False,
                    external_ref=token,
                    amount=paid_amount,
                    message=str(exc),
                    raw=data,
                )

        reference = str((result or {}).get("reference") or "").strip()
        return VerifyResult(
            ok=True,
            external_ref=token,
            amount=paid_amount,
            message=reference or "verified",
            raw=data,
        )
